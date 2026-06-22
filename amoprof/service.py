"""
service.py - AMOprof collection service with Prometheus /metrics endpoint.

Provides:
  MetricsStore       -- thread-safe store for latest collected metrics
  PrometheusServer   -- HTTP server exposing /metrics in Prometheus text format
  run_service        -- main loop: build collectors, cycle, update store
  AVAILABLE_COLLECTORS -- registry of all collector names the service supports

Usage:
  amoprof service --metrics-port 9101 --collectors gpu,dram,vmstat --interval-s 5
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger("amoprof.service")

ALWAYS_COLLECTORS: list[str] = [
    "iostat", "smart", "ssd_hw", "vmstat", "nvlink_pcie",
    "nvme_driver", "gpu", "dram", "power", "pcm", "discard", "swap_storm",
]

OPTIONAL_COLLECTORS: list[str] = [
    "biolatency", "blktrace", "biosnoop", "amduprof_pcm",
    "sglang", "perf", "bpf", "nsys",
]

AVAILABLE_COLLECTORS: list[str] = ALWAYS_COLLECTORS + OPTIONAL_COLLECTORS


# ---------------------------------------------------------------------------
# MetricsStore
# ---------------------------------------------------------------------------

class MetricsStore:
    """Thread-safe store for the latest scrape of each collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self._last_scrape: float = 0.0
        self._scrape_count: int = 0

    def update(self, collector_name: str, summary: dict[str, Any]) -> None:
        with self._lock:
            self._data[collector_name] = dict(summary)
            self._last_scrape = time.time()
            self._scrape_count += 1

    def snapshot(self) -> tuple[dict[str, dict[str, Any]], float, int]:
        """Return (data_copy, last_scrape_epoch, scrape_count)."""
        with self._lock:
            return (
                {k: dict(v) for k, v in self._data.items()},
                self._last_scrape,
                self._scrape_count,
            )


# ---------------------------------------------------------------------------
# Prometheus text-format serialisation
# ---------------------------------------------------------------------------

def _safe_name(s: str) -> str:
    """Convert an arbitrary string to a valid Prometheus metric name segment."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", s).strip("_")


def _to_prometheus_text(store: MetricsStore, service_start_epoch: float) -> str:
    """
    Render the MetricsStore snapshot as Prometheus exposition text format.

    Only numeric (int/float) and boolean values are emitted.
    Metric names: amoprof_<collector>_<key>
    """
    data, last_scrape, scrape_count = store.snapshot()
    lines: list[str] = [
        "# HELP amoprof_service_up 1 if the collection service is running",
        "# TYPE amoprof_service_up gauge",
        "amoprof_service_up 1",
        "# HELP amoprof_service_start_time_seconds Unix epoch when the service started",
        "# TYPE amoprof_service_start_time_seconds gauge",
        f"amoprof_service_start_time_seconds {service_start_epoch:.3f}",
        "# HELP amoprof_service_last_scrape_time_seconds Unix epoch of the last completed collection cycle",
        "# TYPE amoprof_service_last_scrape_time_seconds gauge",
        f"amoprof_service_last_scrape_time_seconds {last_scrape:.3f}",
        "# HELP amoprof_service_scrape_total Total number of completed collection cycles",
        "# TYPE amoprof_service_scrape_total counter",
        f"amoprof_service_scrape_total {scrape_count}",
    ]
    for collector_name, summary in sorted(data.items()):
        safe_coll = _safe_name(collector_name)
        for key, val in sorted(summary.items()):
            if isinstance(val, bool):
                val = 1 if val else 0
            if not isinstance(val, (int, float)):
                continue
            if val != val:   # NaN guard
                continue
            metric_name = f"amoprof_{safe_coll}_{_safe_name(key)}"
            lines += [
                f"# HELP {metric_name} {collector_name}: {key}",
                f"# TYPE {metric_name} gauge",
                f"{metric_name} {val}",
            ]
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTTP handler and server
# ---------------------------------------------------------------------------

def _make_handler(store: MetricsStore, service_start_epoch: float):
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/metrics", "/metrics/"):
                body = _to_prometheus_text(store, service_start_epoch)
                self._respond(200, "text/plain; version=0.0.4; charset=utf-8", body)
            elif self.path in ("/healthz", "/health"):
                self._respond(200, "text/plain", "ok\n")
            else:
                self._respond(404, "text/plain", "Not found\n")

        def _respond(self, code: int, content_type: str, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, fmt, *args):
            pass  # suppress default access log

    return _Handler


class PrometheusServer:
    """Runs the /metrics HTTP server in a background daemon thread."""

    def __init__(self, store: MetricsStore, port: int, host: str = "0.0.0.0",
                 service_start_epoch: float = 0.0) -> None:
        self._store = store
        self._port = port
        self._host = host
        self._start_epoch = service_start_epoch
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = _make_handler(self._store, self._start_epoch)
        self._server = HTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="amoprof-prometheus",
            daemon=True,
        )
        self._thread.start()
        log.info("Prometheus /metrics listening on %s:%d", self._host, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Collector factory
# ---------------------------------------------------------------------------

def _build_collectors(
    args: Any,
    raw_dir: Path,
    enabled: set[str],
    interval_s: float,
    duration_s: float,
    use_sudo: bool,
) -> dict[str, Any]:
    """Instantiate only the collectors present in *enabled*."""
    from .collectors import (
        AMDuProfPcmMemoryCollector,
        BiolatencyCollector,
        BpftraceCollector,
        DramMonitor,
        GpuMonitor,
        IostatMonitor,
        NvlinkPcieMonitor,
        NvmeDriverMonitor,
        NvmeSmartMonitor,
        PcmMemoryCollector,
        PerfStatCollector,
        PowerMonitor,
        SsdHardwareMonitor,
        VmstatMonitor,
    )
    from .collectors_extra import (
        BiosnoopCollector,
        BlktraceCollector,
        DiscardStatsMonitor,
        SwapStormMonitor,
    )

    ssd_device   = getattr(args, "ssd_device",   "/dev/nvme0n1")
    hicache_path = getattr(args, "hicache_path", "/mnt/sglang_dv3")
    pid          = getattr(args, "pid",          None)
    sglang_port  = getattr(args, "sglang_port",  None)
    sglang_host  = getattr(args, "sglang_host",  "127.0.0.1")

    factories: dict[str, Any] = {
        "iostat":       lambda: IostatMonitor(ssd_device, interval_s),
        "smart":        lambda: NvmeSmartMonitor(ssd_device,
                                                 poll_s=max(int(interval_s), 1),
                                                 use_sudo=use_sudo),
        "ssd_hw":       lambda: SsdHardwareMonitor(ssd_device,
                                                   hicache_path=hicache_path,
                                                   use_sudo=use_sudo),
        "biolatency":   lambda: BiolatencyCollector(ssd_device,
                                                    duration_s=max(int(duration_s), 1),
                                                    use_sudo=use_sudo),
        "vmstat":       lambda: VmstatMonitor(interval_s),
        "nvlink_pcie":  lambda: NvlinkPcieMonitor(max(interval_s, 1.0)),
        "nvme_driver":  lambda: NvmeDriverMonitor(ssd_device, interval_s),
        "gpu":          lambda: GpuMonitor(interval_s),
        "dram":         lambda: DramMonitor(interval_s),
        "power":        lambda: PowerMonitor(interval_s, use_sudo=use_sudo),
        "pcm":          lambda: PcmMemoryCollector(interval_s),
        "discard":      lambda: DiscardStatsMonitor(ssd_device, interval_s,
                                                    work_dir=raw_dir),
        "swap_storm":   lambda: SwapStormMonitor(interval_s, work_dir=raw_dir),
        "blktrace":     lambda: BlktraceCollector(
            ssd_device,
            duration_s=max(int(duration_s), 1),
            work_dir=raw_dir,
            blktrace_bin=getattr(args, "blktrace_bin", "blktrace"),
            blkparse_bin=getattr(args, "blkparse_bin", "blkparse"),
            use_sudo=use_sudo,
        ),
        "biosnoop":     lambda: BiosnoopCollector(
            duration_s=max(int(duration_s), 1),
            work_dir=raw_dir,
            device=ssd_device,
            binary=getattr(args, "biosnoop_bin", "biosnoop-bpfcc"),
            use_sudo=use_sudo,
        ),
        "amduprof_pcm": lambda: AMDuProfPcmMemoryCollector(
            duration_s=getattr(args, "amduprof_duration_s", None) or duration_s,
            interval_s=interval_s,
            binary=getattr(args, "amduprof_pcm_bin",
                           "/opt/AMDuProf_5.2-606/bin/AMDuProfPcm"),
            output_csv=str(raw_dir / "amduprof_pcm_raw.csv"),
            extra_args=getattr(args, "amduprof_extra_arg", []) or [],
            use_sudo=use_sudo,
        ),
    }

    if sglang_port is not None:
        from .bench_swebench import SGLangMetricsSampler
        factories["sglang"] = lambda: SGLangMetricsSampler(
            sglang_port, interval_s,
            host=sglang_host,
            debug=bool(getattr(args, "debug_sglang", False)),
            debug_path=str(raw_dir / "sglang_debug.log"),
        )

    if pid is not None:
        factories["perf"] = lambda: PerfStatCollector(pid, use_sudo=use_sudo)
        factories["bpf"]  = lambda: BpftraceCollector(
            pid, duration_s=max(int(duration_s), 1),
            work_dir=raw_dir, use_sudo=use_sudo,
        )

    built: dict[str, Any] = {}
    for name in sorted(enabled):
        if name not in factories:
            log.warning("service: unknown collector %r - skipped", name)
            continue
        try:
            built[name] = factories[name]()
        except Exception as exc:
            log.warning("service: failed to build %r: %s - skipped", name, exc)

    return built


# ---------------------------------------------------------------------------
# Service main loop
# ---------------------------------------------------------------------------

def run_service(args: Any) -> int:
    """
    Long-running collection service.

    Each cycle (length = scrape_duration_s):
      1. Build fresh collector instances for the enabled set.
      2. Start them all.
      3. Sleep for scrape_duration_s (interruptible).
      4. Stop each collector, push its summary into MetricsStore.
      5. Repeat until SIGINT / SIGTERM.

    The Prometheus HTTP server runs throughout in a background thread and
    always serves the most recently completed cycle's data.
    """
    import signal as _signal
    from .blktrace_service import BlktraceServicePoller

    scrape_s:   float = float(getattr(args, "scrape_duration_s", 30.0))
    port:       int   = int(getattr(args,   "metrics_port",      9101))
    host:       str   = getattr(args,       "metrics_host",      "0.0.0.0")
    use_sudo:   bool  = not getattr(args,   "no_sudo",           False)
    interval_s: float = float(getattr(args, "interval_s",        1.0))
    blkparse_interval_s: float = float(getattr(args, "blkparse_interval_s", 10.0))

    # ---- resolve enabled collectors ----------------------------------------
    collectors_arg: str = (getattr(args, "collectors", "") or "").strip()
    if collectors_arg.lower() in ("", "all"):
        enabled: set[str] = set(ALWAYS_COLLECTORS)
    else:
        enabled = {c.strip() for c in collectors_arg.split(",") if c.strip()}
        unknown = enabled - set(AVAILABLE_COLLECTORS)
        if unknown:
            log.warning("service: unrecognised collector(s) %s - ignored",
                        sorted(unknown))
            enabled -= unknown

    if getattr(args, "enable_blktrace",     False): enabled.add("blktrace")
    if getattr(args, "enable_biosnoop",     False): enabled.add("biosnoop")
    if getattr(args, "enable_amduprof_pcm", False): enabled.add("amduprof_pcm")
    if getattr(args, "enable_all",          False): enabled |= {"blktrace", "biosnoop", "amduprof_pcm"}
    if getattr(args, "sglang_port",         None) is not None: enabled.add("sglang")
    if getattr(args, "pid",                 None) is not None: enabled |= {"perf", "bpf"}
    if getattr(args, "enable_nsys",         False): enabled.add("nsys")

    output_base = Path(
        getattr(args, "output_dir",
                os.environ.get("AMOPROF_OUTPUT_DIR", "./amoprof_results"))
    ).expanduser().resolve()
    output_base.mkdir(parents=True, exist_ok=True)

    store = MetricsStore()
    service_start = time.time()

    prom = PrometheusServer(store, port=port, host=host,
                            service_start_epoch=service_start)
    prom.start()

    sep = "=" * 68
    print(
        f"\n{sep}\n"
        f"  AMOprof collection service started\n"
        f"  Collectors     : {', '.join(sorted(enabled))}\n"
        f"  Scrape window  : {scrape_s:.0f} s\n"
        f"  Poll interval  : {interval_s:.1f} s\n"
        f"  Metrics URL    : http://{host}:{port}/metrics\n"
        f"  Health URL     : http://{host}:{port}/healthz\n"
        f"  Output base    : {output_base}\n"
        f"{sep}\n",
        flush=True,
    )

    stop_event = threading.Event()

    def _handle_signal(sig, frame):
        log.info("service: received signal %s - stopping", sig)
        stop_event.set()

    _signal.signal(_signal.SIGINT,  _handle_signal)
    _signal.signal(_signal.SIGTERM, _handle_signal)

    cycle = 0
    while not stop_event.is_set():
        cycle += 1
        cycle_ts = time.strftime("%Y%m%d_%H%M%S")
        raw_dir = output_base / f"service_cycle_{cycle_ts}" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        log.info("service: cycle %d starting (%s)", cycle, cycle_ts)

        collectors = _build_collectors(
            args=args,
            raw_dir=raw_dir,
            enabled=enabled,
            interval_s=interval_s,
            duration_s=scrape_s,
            use_sudo=use_sudo,
        )

        started: set[str] = set()
        for name, c in collectors.items():
            try:
                c.start()
                started.add(name)
            except Exception as exc:
                log.warning("service cycle %d: start %r failed: %s", cycle, name, exc)

        # If blktrace is running, start the incremental blkparse poller.
        # It runs in the background for the duration of this cycle, periodically
        # parsing new binary data and pushing interval metrics to the store.
        blktrace_poller: BlktraceServicePoller | None = None
        blktrace_collector = collectors.get("blktrace")
        if blktrace_collector is not None and "blktrace" in started:
            _trace_prefix = getattr(blktrace_collector, "_trace_prefix", None)
            _csv_path     = getattr(blktrace_collector, "_csv_path", None)
            _blkparse_bin = getattr(blktrace_collector, "blkparse_bin", "blkparse")
            if _trace_prefix is not None and _csv_path is not None:
                blktrace_poller = BlktraceServicePoller(
                    trace_prefix=_trace_prefix,
                    csv_path=_csv_path,
                    store=store,
                    blkparse_bin=_blkparse_bin,
                    interval_s=blkparse_interval_s,
                    use_sudo=use_sudo,
                )
                blktrace_poller.start()
                log.info("service: blktrace poller started (interval=%.0fs)",
                         blkparse_interval_s)

        stop_event.wait(timeout=scrape_s)

        # Stop the blktrace poller first so it does a final parse before
        # the blktrace binary collector is stopped and files are closed.
        if blktrace_poller is not None:
            blktrace_poller.stop()
            log.info("service: blktrace poller stopped")

        for name, c in collectors.items():
            if name not in started:
                continue
            try:
                result = c.stop()
            except Exception as exc:
                result = {f"{name}_available": False, f"{name}_error": str(exc)}
            if result is None:
                result = {f"{name}_available": False}
            store.update(name, result)

        log.info("service: cycle %d complete, store covers %d collector(s)",
                 cycle, len(store.snapshot()[0]))

        if stop_event.is_set():
            break

        # brief gap so successive cycles never share the same timestamp
        stop_event.wait(timeout=0.5)

    prom.stop()
    log.info("service: shut down after %d cycle(s)", cycle)
    print(f"\nAMOprof service stopped after {cycle} cycle(s).\n", flush=True)
    return 0
