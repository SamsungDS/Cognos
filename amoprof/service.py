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

import csv
import json
import logging
import os
import platform
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger("amoprof.service")


# ---------------------------------------------------------------------------
# Service-mode local persistence helpers
# ---------------------------------------------------------------------------

def _detect_cpu_vendor() -> str:
    """Return a coarse CPU vendor string for DRAM PMU backend selection."""
    text = ""
    try:
        text = Path("/proc/cpuinfo").read_text(errors="ignore").lower()
    except Exception:
        text = platform.processor().lower()
    if "authenticamd" in text or "amd" in text:
        return "amd"
    if "genuineintel" in text or "intel" in text:
        return "intel"
    return "unknown"


def _resolve_dram_tool(args: Any) -> str:
    """Resolve --enable-dram backend: auto -> AMDuProf on AMD, Intel PCM on Intel."""
    tool = str(getattr(args, "dram_tool", "auto") or "auto").strip().lower()
    if tool in {"none", "off", "disabled"}:
        return "none"
    if tool in {"amduprof", "amd", "amduprof-pcm"}:
        return "amduprof"
    if tool in {"intel", "intel-pcm", "pcm", "pcm-memory"}:
        return "intel-pcm"
    if tool in {"perf", "perf-imc", "imc"}:
        return "perf-imc"
    vendor = _detect_cpu_vendor()
    if vendor == "amd":
        return "amduprof"
    if vendor == "intel":
        # Prefer PCM only when a usable pcm-memory exists AND the CPU is one
        # the build recognises.  PCM refuses to run on a microarchitecture it
        # was not compiled for — every pcm-* binary present, every one exiting
        # with "unsupported processor" — and auto-selecting it there yields a
        # collector that runs and silently produces nothing.  perf-imc reads
        # the same uncore counters through the kernel and has no such table.
        import shutil as _sh
        if _sh.which("pcm-memory") or _sh.which("pcm-memory.x"):
            if not _pcm_rejects_this_cpu():
                return "intel-pcm"
            log.warning("service: Intel PCM does not support this CPU model; "
                        "falling back to --dram-tool perf-imc")
        elif _sh.which("perf"):
            log.info("service: pcm-memory not found; using perf-imc for DRAM bandwidth")
        return "perf-imc" if _sh.which("perf") else "intel-pcm"
    return "intel-pcm"


def _pcm_rejects_this_cpu() -> bool:
    """True when the installed PCM build refuses this microarchitecture.

    Cheap probe against any pcm-* utility: they share the CPU-support table,
    so one refusal means they all refuse.
    """
    import shutil as _sh
    import subprocess as _sp
    probe = _sh.which("pcm-raw") or _sh.which("pcm-core") or _sh.which("pcm-numa")
    if not probe:
        return False
    try:
        out = _sp.run([probe], capture_output=True, text=True, timeout=20)
        return "unsupported processor" in (out.stdout or "").lower()
    except Exception:
        return False


def _json_default(obj: Any) -> str:
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def _iso_utc(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return ""


def _collector_series_rows(obj: Any, t0_epoch: float) -> list[dict[str, Any]]:
    """Extract and normalize per-sample rows from a collector object.

    Each persisted row carries both absolute epoch time and relative time_sec.
    This is what lets offline service-mode data be filtered by an arbitrary
    wall-clock window without depending on Prometheus retention.
    """
    raw: list[Any] = []
    if hasattr(obj, "samples") and isinstance(getattr(obj, "samples"), list):
        raw = getattr(obj, "samples") or []
    elif hasattr(obj, "_samples") and isinstance(getattr(obj, "_samples"), list):
        raw = getattr(obj, "_samples") or []

    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if isinstance(item, dict):
            d = dict(item)
        elif isinstance(item, tuple) and len(item) == 3 and isinstance(item[2], dict):
            tag, ts, payload = item
            d = {"tag": tag, "ts": ts, **payload}
        else:
            continue

        ts_val = d.get("timestamp_epoch", d.get("ts", d.get("_ts")))
        try:
            ts_f = float(ts_val)
        except Exception:
            try:
                rel = float(d.get("time_sec", idx))
            except Exception:
                rel = float(idx)
            ts_f = float(t0_epoch) + rel

        if ts_f > 1_000_000_000:
            d["timestamp_epoch"] = round(ts_f, 6)
            d["ts"] = round(ts_f, 6)
            d["time_sec"] = round(ts_f - float(t0_epoch), 6)
        else:
            rel = ts_f
            d["time_sec"] = round(rel, 6)
            d["timestamp_epoch"] = round(float(t0_epoch) + rel, 6)
            d["ts"] = d["timestamp_epoch"]
        d["timestamp_utc"] = _iso_utc(float(d["timestamp_epoch"]))
        d["iteration"] = idx
        rows.append(d)
    return rows


def _write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys: list[str] = []
    seen: set[str] = set()
    preferred = ["time_sec", "timestamp_epoch", "timestamp_utc", "ts", "iteration", "collector"]
    for k in preferred:
        for row in rows:
            if k in row and k not in seen:
                keys.append(k); seen.add(k)
    for row in rows:
        for k in row:
            if k not in seen:
                keys.append(k); seen.add(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_rows_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=_json_default, sort_keys=True) + "\n")


def _persist_service_cycle(
    *,
    cycle_dir: Path,
    raw_dir: Path,
    cycle: int,
    enabled: set[str],
    collectors: dict[str, Any],
    summaries: dict[str, dict[str, Any]],
    raw_paths: dict[str, str],
    start_epoch: float,
    end_epoch: float,
    interval_s: float,
    scrape_s: float,
    args: Any,
    store: "MetricsStore | None" = None,
) -> dict[str, dict[str, Any]]:
    """Write a service cycle as a normal local AMOprof run directory.

    Returns a dict of any additional synthetic-collector summaries produced
    during persistence (for example the blktrace analyzer's per-op aggregate
    outputs).  When ``store`` is provided, those summaries are also pushed
    into it so the Prometheus /metrics endpoint exposes them under the
    ``amoprof_<pseudo_collector>_<key>`` namespace alongside real collector
    outputs.
    """
    all_rows: list[dict[str, Any]] = []
    for name, summary in summaries.items():
        summary_path = raw_dir / f"{name}_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=_json_default), encoding="utf-8")
        raw_paths[f"{name}_summary_json"] = str(summary_path)

        obj = collectors.get(name)
        if obj is None:
            continue
        rows = _collector_series_rows(obj, start_epoch)
        for row in rows:
            row["collector"] = name
        if rows:
            _write_rows_jsonl(raw_dir / f"{name}_timeseries.jsonl", rows)
            _write_rows_csv(raw_dir / f"{name}_timeseries.csv", rows)
            raw_paths[f"{name}_timeseries_jsonl"] = str(raw_dir / f"{name}_timeseries.jsonl")
            raw_paths[f"{name}_timeseries_csv"] = str(raw_dir / f"{name}_timeseries.csv")
            all_rows.extend(rows)

    if all_rows:
        all_rows = sorted(all_rows, key=lambda r: (float(r.get("time_sec", 0.0)), str(r.get("collector", ""))))
        _write_rows_jsonl(raw_dir / "all_timeseries.jsonl", all_rows)
        _write_rows_csv(raw_dir / "all_timeseries.csv", all_rows)
        raw_paths["all_timeseries_jsonl"] = str(raw_dir / "all_timeseries.jsonl")
        raw_paths["all_timeseries_csv"] = str(raw_dir / "all_timeseries.csv")

    # Create AMOprof-compatible canonical files/mirrors when possible.  This
    # keeps service_cycle_* directories analyzable with the same code path as
    # one-shot collect directories.
    try:
        from .writer import write_amoprof_files
        sglang_obj = collectors.get("sglang")
        sglang_samples = getattr(sglang_obj, "raw_samples", []) if sglang_obj is not None else []
        sglang_source = getattr(sglang_obj, "prometheus_url", "") if sglang_obj is not None else ""
        sglang_elapsed = float(getattr(sglang_obj, "elapsed_s", 0.0) or 0.0) if sglang_obj is not None else 0.0
        written = write_amoprof_files(raw_dir, start_epoch,
                                       sglang_samples=sglang_samples,
                                       sglang_source=sglang_source,
                                       sglang_elapsed_s=sglang_elapsed,
                                       sglang_model=str(getattr(args, "model", "unknown")))
        for fname, path in written.items():
            raw_paths[f"amoprof_{Path(fname).stem}"] = str(path)
    except Exception as exc:
        log.debug("service: canonical writer skipped: %s", exc)

    # Drop setup_details.json + server_info.json into the cycle's raw/ so the
    # L3-backend resolver (report/l3_backend.py::resolve_l3_backend) can read
    # the live hicache_storage_backend value and label the cycle report as
    # L3 (SSD/local) vs L3.5 (Mooncake / AI Memory Node / remote).  Without
    # this, service cycles fall through to the "unknown" branch and every
    # report shows L3.5 regardless of the actual backend.  Also copy any
    # user-supplied --setup-details / --bench-summary so multi-cycle service
    # runs produce reports identical to a single --analyze pass.
    try:
        from .cli import (_write_setup_details_from_server_info,
                           _copy_setup_details, _copy_bench_summary,
                           _write_gpu_config, _write_model_config)
        # Prefer live SGLang server_info when the caller passed --sglang-port
        # or --server-info-url; falls back silently otherwise.
        # Re-fetch server_info only every --server-info-interval-s.  The
        # configuration changes on restart, not continuously, so polling it
        # every cycle adds request load to the inference server for no new
        # information.  The previously fetched file is REUSED between polls
        # rather than skipped, so the published metric stays continuous and a
        # gap in it means the server was unreachable, not that we chose not to
        # look.
        _si_once = bool(getattr(args, "server_info_once", False))
        _si_iv = float(getattr(args, "server_info_interval_s", 300.0) or 0.0)
        if _si_once:
            # argparse rejects both flags together, but AMOPROF_SERVER_INFO_ONCE
            # can still combine with an explicit --server-info-interval-s.  Say
            # which one is in effect rather than letting the interval look
            # honoured when it is not.
            if _si_iv and _si_iv != 300.0:
                log.warning("service: --server-info-once is set (or "
                            "AMOPROF_SERVER_INFO_ONCE=1), so "
                            "--server-info-interval-s %.0f is ignored; "
                            "server_info is fetched once at start", _si_iv)
            # Fetch once, then reuse forever.  An interval no run will reach.
            _si_iv = float("inf")
        _si_now = time.time()
        _si_last = getattr(run_service, "_last_server_info_ts", 0.0)
        # The cache must outlive a single cycle.  raw_dir is
        # <output>/service_cycle_<ts>/raw, so raw_dir.parent is a NEW directory
        # every cycle — the cache written there was never found again and the
        # fallback re-fetched on every cycle regardless of the interval.
        # Anchor it to the run root, which is stable for the service's life.
        _si_cache = raw_dir.parent.parent / ".amoprof_server_info_cache.json"
        if (_si_iv <= 0 and not _si_once) or (_si_now - _si_last) >= _si_iv:
            _write_setup_details_from_server_info(args, raw_dir, allow_overwrite=True)
            run_service._last_server_info_ts = _si_now
            try:
                _fresh = raw_dir / "server_info.json"
                if _fresh.exists() and _fresh.stat().st_size > 0:
                    import shutil as _sh_si
                    _sh_si.copyfile(_fresh, _si_cache)
            except Exception:
                pass
        else:
            # Within the interval: reuse the last good fetch.
            try:
                if _si_cache.exists() and _si_cache.stat().st_size > 0:
                    import shutil as _sh_si
                    _sh_si.copyfile(_si_cache, raw_dir / "server_info.json")
                else:
                    # No cache yet — this is the first cycle.  Fetch, and
                    # populate the cache so later cycles can reuse it;
                    # omitting that made --server-info-once fetch every cycle,
                    # since the reuse branch had nothing to reuse.
                    _write_setup_details_from_server_info(
                        args, raw_dir, allow_overwrite=True)
                    # Only stamp the time if we had never fetched; stamping on
                    # every fallback restarted the interval each cycle.
                    if not _si_last:
                        run_service._last_server_info_ts = _si_now
                    _fresh2 = raw_dir / "server_info.json"
                    if _fresh2.exists() and _fresh2.stat().st_size > 0:
                        import shutil as _sh_si2
                        _sh_si2.copyfile(_fresh2, _si_cache)
            except Exception:
                pass
        # If the operator also passed --setup-details or --bench-summary, honor
        # them so cycle reports reflect the same setup as one-shot runs.
        _copy_setup_details(args, raw_dir)
        _copy_bench_summary(args, raw_dir)
        # Static GPU inventory from nvidia-smi.  Written *after* server_info
        # so the TP/DP values are available and gpu_config.json can record
        # how many devices the inference server actually occupies — that
        # count, not the physical device count, is the HBM-capacity
        # denominator the reports need.
        _write_gpu_config(raw_dir, args)
        # Served model architecture (from --model-path).  Written per
        # cycle so an offline analyze of this run can compute KV
        # bytes/token exactly rather than inferring it from the name.
        _write_model_config(raw_dir, args)
    except Exception as exc:
        log.debug("service: setup_details/server_info hook skipped: %s", exc)

    # Pre-aggregate blktrace events so the analyze step (or a live consumer of
    # this cycle dir) has queue-depth, streams, hot-cold, and Q→C latency
    # already computed.  Mirrors cli._run_amoprof's blktrace-on-analyze pass.
    # Skipped when no blktrace was collected — the check is cheap and idempotent.
    try:
        _blkparse_csv = raw_dir / "blkparse_events.generated.csv"
        _bin_dir      = raw_dir / "blktrace_data"
        _has_csv = _blkparse_csv.exists() and _blkparse_csv.stat().st_size > 0
        _has_bins = _bin_dir.exists() and any(_bin_dir.glob("trace.blktrace.*"))
        if _has_csv or _has_bins:
            from .blktrace_analyzer import (
                analyze as _bt_analyze,
                analyze_from_binaries as _bt_analyze_bins,
            )
            _ba_dir = raw_dir / "blktrace_analysis"
            _sentinel = _ba_dir / "temporal_read_write_trim_pattern.csv"
            _need_analyze = (
                not _sentinel.exists()
                or (_has_csv and _sentinel.stat().st_mtime < _blkparse_csv.stat().st_mtime)
            )
            if _need_analyze:
                _ba_dir.mkdir(parents=True, exist_ok=True)
                # Check whether CSV actually has data rows (headers only means
                # a prior parse failed).  Fall through to binaries when that
                # happens and binaries are available.
                _csv_has_rows = False
                if _has_csv:
                    try:
                        with _blkparse_csv.open("r", encoding="utf-8") as _fh:
                            _fh.readline()  # header
                            _csv_has_rows = bool(_fh.readline().strip())
                    except Exception:
                        _csv_has_rows = False
                if _csv_has_rows:
                    _bt_analyze(_blkparse_csv, _ba_dir)
                elif _has_bins:
                    _bt_analyze_bins(_bin_dir, _ba_dir,
                                      max_events=getattr(args, "blktrace_max_events", None))
                if _sentinel.exists():
                    log.info("service: blktrace_analyzer produced %s", _ba_dir)
    except Exception as exc:
        log.debug("service: blktrace analysis hook skipped: %s", exc)

    # ── Extra scalar aggregates from downstream analyzer outputs ─────────────
    # Every collector's own summary is already in `summaries` (and therefore
    # already in the MetricsStore).  The blktrace analyzer runs *after* the
    # cycle collectors stop and writes its own aggregate JSON/CSV under
    # blktrace_analysis/; those numeric aggregates would otherwise never reach
    # the Prometheus /metrics endpoint.  Gather them under stable pseudo-
    # collector names so the Prometheus exposition emits
    # ``amoprof_blktrace_analysis_<key>`` and
    # ``amoprof_blktrace_qd_<key>`` families for every enabled cycle.
    extra_summaries: dict[str, dict[str, Any]] = {}

    def _numeric_only(d: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in d.items():
            if isinstance(v, bool):
                out[str(k)] = 1 if v else 0
                continue
            if isinstance(v, (int, float)) and not (isinstance(v, float) and v != v):
                out[str(k)] = v
        return out

    def _load_json(p: Path) -> dict[str, Any]:
        try:
            if p.exists() and p.stat().st_size > 0:
                return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
        return {}

    def _load_csv_summary(p: Path, key_col: str, ns: str,
                           value_cols: "list[str] | None" = None) -> dict[str, Any]:
        """Fold a small analyzer CSV into flat scalar keys.

        The analyzer emits per-op rollups like bandwidth_per_stream_summary.csv
        (rows keyed by op R/W/D, columns bw_mbs_mean, count, ...).  These are
        genuinely scalar signals — one number per (op, column) — so we flatten
        them into MetricsStore-friendly gauge keys instead of publishing raw
        tabular data.

        The ``ns`` prefix keeps these per-op keys out of the summary.json's
        already-flat namespace (e.g. summary.json exports ``read_iops_mean``
        as a whole-window scalar; the CSV would collide unless we prefix it as
        ``stream_read_iops_mean`` etc.).  ``value_cols=None`` folds in every
        numeric column found in the CSV.
        """
        out: dict[str, Any] = {}
        try:
            if not (p.exists() and p.stat().st_size > 0):
                return out
            with p.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    op = _safe_name(str(row.get(key_col) or "").strip() or "any").lower()
                    if not op:
                        continue
                    for col, v in row.items():
                        if col == key_col:
                            continue
                        if value_cols is not None and col not in value_cols:
                            continue
                        try:
                            fv = float(v)
                        except (TypeError, ValueError):
                            continue
                        if fv != fv:
                            continue
                        out[f"{ns}_{op}_{_safe_name(col)}"] = fv
        except Exception:
            pass
        return out

    _ba_dir = raw_dir / "blktrace_analysis"
    if _ba_dir.is_dir():
        # Whole-window per-op bytes / event counts / IOPS from the analyzer.
        _ba_summary = _numeric_only(_load_json(_ba_dir / "summary.json"))
        # Extend with per-op stream/skew/degradation aggregates that live as
        # short CSVs; each row is one op (read/write/trim), so we flatten to
        # <op>_<column> keys.
        # Per-op CSV rollups.  Column names differ across analyzer versions,
        # so fold every numeric column and let namespace-prefixed keys avoid
        # colliding with summary.json's whole-window scalars.
        _ba_summary.update(_load_csv_summary(
            _ba_dir / "bandwidth_per_stream_summary.csv", "op", ns="stream",
        ))
        _ba_summary.update(_load_csv_summary(
            _ba_dir / "access_skew_summary.csv", "op", ns="skew",
        ))
        _ba_summary.update(_load_csv_summary(
            _ba_dir / "bandwidth_degradation.csv", "op", ns="deg",
        ))
        _ba_summary.update(_load_csv_summary(
            _ba_dir / "request_size_random_seq_correlation.csv", "op", ns="rand",
        ))
        if _ba_summary:
            extra_summaries["blktrace_analysis"] = _ba_summary

        # Queue-depth aggregate (mean/p50/p95/p99/max, time-at-QD-≥ N%).
        _qd_summary = _numeric_only(_load_json(_ba_dir / "queue_depth_summary.json"))
        if _qd_summary:
            extra_summaries["blktrace_qd"] = _qd_summary

        # Optional Q→C latency histogram summary (blktrace_latency_summary.json
        # is emitted by newer analyzer versions; older runs miss this file).
        _lat_summary = _numeric_only(_load_json(_ba_dir / "blktrace_latency_summary.json"))
        if _lat_summary:
            extra_summaries["blktrace_latency"] = _lat_summary

        # GPU device inventory (gpu_config.json) is written by
        # cli._write_gpu_config() rather than by a collector, so its numbers —
        # per-GPU HBM capacity, device count, TP/DP, and the capacity actually
        # occupied by the inference server — would never reach /metrics.
        # Publish them as amoprof_gpu_config_<key>.
        _gpu_cfg_raw = _load_json(raw_dir / "gpu_config.json")
        _gpu_cfg_summary = _numeric_only(_gpu_cfg_raw)
        if _gpu_cfg_raw.get("gpus"):
            # Per-device HBM capacity, so a mixed-GPU host is visible.
            for _g in _gpu_cfg_raw.get("gpus") or []:
                try:
                    _idx = int(_g.get("index"))
                except Exception:
                    continue
                _mt = _g.get("memory_total_gb")
                if isinstance(_mt, (int, float)):
                    _gpu_cfg_summary[f"gpu{_idx}_memory_total_gb"] = float(_mt)
        if _gpu_cfg_summary:
            extra_summaries["gpu_config"] = _gpu_cfg_summary

        # Model architecture as amoprof_model_config_* gauges, so a Prometheus
        # scrape carries enough to compute KV bytes/token exactly without the
        # raw files being retained.
        _mdl_raw = _load_json(raw_dir / "model_config.json")
        _mdl_summary = _numeric_only(_mdl_raw)
        if _mdl_summary:
            extra_summaries["model_config"] = _mdl_summary

        # Inference-server configuration, captured EVERY cycle rather than
        # once at analyze time.  A server restarted mid-window with a
        # different model, TP size or cache configuration otherwise has its
        # whole window attributed to whichever config happened to be live when
        # the report ran — silently mixing two different systems into one set
        # of numbers.
        #
        # Numeric fields go out as gauges.  A stable hash of the full config
        # goes out alongside them: a change in that single series is what lets
        # analyze detect a reconfiguration without having to diff every field.
        _srv_raw = _load_json(raw_dir / "server_info.json")
        if _srv_raw:
            _srv_summary = _numeric_only(_srv_raw)
            try:
                import hashlib as _hl
                import json as _js
                _ident = {k: _srv_raw.get(k) for k in sorted(_srv_raw)
                          if k in ("model_path", "served_model_name", "tp_size",
                                   "dp_size", "page_size", "enable_hierarchical_cache",
                                   "hicache_ratio", "hicache_size",
                                   "hicache_storage_backend", "max_total_num_tokens",
                                   "kv_cache_dtype", "attention_backend")}
                if _ident:
                    _blob = _js.dumps(_ident, sort_keys=True, default=str)
                    # Truncated to stay exactly representable as a float64
                    # gauge; Prometheus would silently round a longer integer.
                    _srv_summary["config_hash"] = float(
                        int(_hl.sha256(_blob.encode()).hexdigest()[:12], 16))
                    _srv_summary["config_fields"] = float(len(_ident))
            except Exception:
                pass
            if _srv_summary:
                extra_summaries["server_config"] = _srv_summary

    # Push everything into the MetricsStore so the Prometheus endpoint exposes
    # the new metric families the next time it is scraped.  Merge the extras
    # into the returned summaries dict too so any future consumer sees a
    # single unified per-cycle view.
    if store is not None:
        for _pseudo, _agg in extra_summaries.items():
            if _agg:
                store.update(_pseudo, _agg)
    for _pseudo, _agg in extra_summaries.items():
        summaries.setdefault(_pseudo, _agg)

    meta = {
        "run_id": cycle_dir.name,
        "label": cycle_dir.name,
        "service_mode": True,
        "service_cycle": cycle,
        "timestamp": _iso_utc(end_epoch),
        "t0_epoch": start_epoch,
        "start_time": start_epoch,
        "t_end_epoch": end_epoch,
        "end_time": end_epoch,
        "start_time_utc": _iso_utc(start_epoch),
        "end_time_utc": _iso_utc(end_epoch),
        "duration_s": round(end_epoch - start_epoch, 3),
        "requested_duration_s": scrape_s,
        "interval_s": interval_s,
        "collectors": sorted(enabled),
        "ssd_device": getattr(args, "ssd_device", ""),
        "ssd_devices": list(getattr(args, "ssd_devices", []) or
                            ([getattr(args, "ssd_device", "")] if getattr(args, "ssd_device", "") else [])),
        "hicache_path": getattr(args, "hicache_path", ""),
        "sglang_port": getattr(args, "sglang_port", "") or "",
    }
    payload = {"meta": meta, "summary": summaries, "raw_paths": raw_paths}
    (cycle_dir / "summary.json").write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    # Duplicate a compact meta file into raw/ because older aggregate/analyze
    # paths sometimes look in raw/summary.json first.
    (raw_dir / "summary.json").write_text(json.dumps(meta, indent=2, default=_json_default), encoding="utf-8")
    return extra_summaries

def _registry_collector_names() -> "tuple[list[str], list[str]]":
    """(always, optional) collector names, derived from CollectorRegistry.

    These lists used to be hardcoded and duplicated the registry, so a newly
    registered collector was silently rejected by the ``--collectors`` filter
    even though it was importable and instantiable — ``--collectors network``
    was dropped with the service reporting only the collectors it recognised.
    Deriving them means registering a collector is the only step required.

    ``CollectorSpec.optional`` decides the bucket: opt-in collectors (those
    gated behind an ``--enable-*`` flag) are optional, the rest are on by
    default.
    """
    always: list[str] = []
    optional: list[str] = []
    try:
        from .base import CollectorRegistry
        from . import collectors as _collectors  # noqa: F401  (triggers registration)
        for spec in CollectorRegistry.all():
            name = getattr(spec, "name", "")
            if not name:
                continue
            bucket = optional if getattr(spec, "optional", False) else always
            if name not in bucket:
                bucket.append(name)
    except Exception:  # pragma: no cover - registry unavailable
        pass
    # Names the service supports that are not registry-backed collectors
    # (handled by dedicated code paths in this module).
    for extra in ("perf", "bpf", "nsys"):
        if extra not in optional and extra not in always:
            optional.append(extra)
    return sorted(always), sorted(optional)


# Default-on set when --collectors is omitted.  Kept explicit rather than
# derived: `CollectorSpec.optional` marks flag-gated collectors, but some
# non-optional ones (biolatency, queue_depth_sysfs) need BPF/sudo and were
# historically not started by default.  Deriving the default set would have
# silently switched them on, so only the *accepted* set is derived.
DEFAULT_COLLECTORS: list[str] = [
    "iostat", "smart", "ssd_hw", "vmstat", "nvlink_pcie",
    "nvme_driver", "gpu", "dram", "network", "power", "pcm",
    "discard", "swap_storm", "cpu",
]

_REG_ALWAYS, _REG_OPTIONAL = _registry_collector_names()

ALWAYS_COLLECTORS: list[str] = DEFAULT_COLLECTORS

# Everything --collectors will accept: every registered collector plus the
# service-handled extras.  Registering a collector is all that is needed for
# it to become selectable.
OPTIONAL_COLLECTORS: list[str] = [
    n for n in (_REG_ALWAYS + _REG_OPTIONAL) if n not in DEFAULT_COLLECTORS
]

AVAILABLE_COLLECTORS: list[str] = sorted(set(DEFAULT_COLLECTORS)
                                         | set(_REG_ALWAYS) | set(_REG_OPTIONAL))


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
    from .collectors import (
        BiosnoopCollector,
        BlktraceCollector,
        DiscardStatsMonitor,
        SwapStormMonitor,
    )

    from .cli import _resolve_ssd_devices, _ssd_device_slug

    ssd_raw       = getattr(args, "ssd_device", "/dev/nvme0n1")
    ssd_devices   = _resolve_ssd_devices(ssd_raw) or ["/dev/nvme0n1"]
    args.ssd_devices = ssd_devices
    args.ssd_device  = ssd_devices[0]
    ssd_device    = ssd_devices[0]
    hicache_path = getattr(args, "hicache_path", "/mnt/sglang_dv3")
    pid          = getattr(args, "pid",          None)
    sglang_port  = getattr(args, "sglang_port",  None)
    sglang_host  = getattr(args, "sglang_host",  "127.0.0.1")
    dram_tool    = _resolve_dram_tool(args)

    factories: dict[str, Any] = {}
    _host_ctx = {
        "raw_dir": raw_dir,
        "duration_s": duration_s,
        "use_sudo": use_sudo,
        "interval_s": interval_s,
        "dram_tool": dram_tool,
    }
    from .base import CollectorRegistry
    # host-wide collectors — the `enabled` filter decides which get built.
    # (sglang is host-wide too but its factory needs late binding on
    # sglang_port; handled below to match the original conditional.)
    for _spec in CollectorRegistry.host_wide():
        # `sglang` handled in the sglang_port block below to keep the same
        # sglang_port-is-not-None check.
        if _spec.name == "sglang":
            continue
        _cls = CollectorRegistry.get(_spec.layer, _spec.name)
        if _cls is None or not hasattr(_cls, "for_host"):
            continue
        factories[_spec.name] = (
            lambda _c=_cls, _a=args, _x=_host_ctx: _c.for_host(_a, _x)
        )
    # Per-SSD factories driven by CollectorRegistry.  Every SSD-scoped
    # collector class declares a `for_device(device, args, ctx)` classmethod;
    # service just iterates the registry, no per-class boilerplate here.
    from .base import CollectorRegistry
    _ssd_ctx_base = {
        "raw_dir": raw_dir,
        "duration_s": duration_s,
        "use_sudo": use_sudo,
        "interval_s": interval_s,
    }
    for _idx, _dev in enumerate(ssd_devices):
        _slug = _ssd_device_slug(_dev)
        _ksfx = "" if _idx == 0 else ("__" + _slug)
        _fsfx = "" if _idx == 0 else _slug
        _ctx = dict(_ssd_ctx_base)
        _ctx["filename_suffix"] = _fsfx
        for _spec in CollectorRegistry.ssd_scoped():
            _cls = CollectorRegistry.get(_spec.layer, _spec.name)
            if _cls is None or not hasattr(_cls, "for_device"):
                continue
            # Bind dev/args/ctx in the default arg trick so each lambda
            # captures its own values, not the loop variables.
            factories[_spec.name + _ksfx] = (
                lambda _c=_cls, _d=_dev, _a=args, _x=_ctx: _c.for_device(_d, _a, _x)
            )

    # `sglang` is an ordinary optional collector and must respect --collectors
    # like every other one.  It was gated only on --sglang-port, so it ran
    # whenever a port was configured even if the operator had excluded it —
    # and when Prometheus already scrapes the inference server directly, this
    # collector is a second scrape of the same endpoint for the same data.
    # Only an EXPLICIT --collectors list can exclude it.  `enabled` falls back
    # to DEFAULT_COLLECTORS, which does not contain "sglang", so keying off
    # `enabled` alone would have disabled the collector for everyone who never
    # named it — a silent regression rather than the opt-out that was asked
    # for.
    _explicit = str(getattr(args, "collectors", "") or "").strip()
    _sglang_wanted = (("sglang" in enabled) if
                      (_explicit and _explicit.lower() != "all") else True)
    if sglang_port is not None and _sglang_wanted:
        from .collectors import SGLangMetricsSampler
        factories["sglang"] = (
            lambda _c=SGLangMetricsSampler, _a=args, _x=_host_ctx: _c.for_host(_a, _x)
        )
    elif sglang_port is not None:
        log.info("service: sglang collector not in --collectors; skipping the "
                 "local /metrics scrape (Prometheus may already be scraping it)")

    if pid is not None:
        # perf and bpf are PID-scoped; look them up by SPEC and hand the
        # pid through for_pid().
        for _spec in CollectorRegistry.pid_scoped():
            _cls = CollectorRegistry.get(_spec.layer, _spec.name)
            if _cls is None or not hasattr(_cls, "for_pid"):
                continue
            # nsys triggers on --enable-nsys, not implicit --pid; that
            # remains a top-level `factories['nsys']` when the user asks.
            if _spec.name == "nsys":
                continue
            factories[_spec.name] = (
                lambda _c=_cls, _p=pid, _a=args, _x=_host_ctx: _c.for_pid(_p, _a, _x)
            )

    # Expand SSD-scoped collector types (iostat/smart/ssd_hw/biolatency/
    # nvme_driver/discard/blktrace/biosnoop) to per-device keys for devices 2+.
    _ssd_scoped = {"iostat", "smart", "ssd_hw", "biolatency", "nvme_driver",
                   "discard", "blktrace", "biosnoop"}
    _expanded_enabled = set(enabled)
    if len(ssd_devices) > 1:
        for _base in list(enabled):
            if _base in _ssd_scoped:
                for _dev in ssd_devices[1:]:
                    _expanded_enabled.add(_base + "__" + _ssd_device_slug(_dev))

    built: dict[str, Any] = {}
    for name in sorted(_expanded_enabled):
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
            # Loud: a silently-dropped name looks identical to a collector
            # that started and produced nothing.
            log.error("service: unrecognised collector(s) %s — IGNORED. "
                      "Known collectors: %s",
                      ", ".join(sorted(unknown)), ", ".join(AVAILABLE_COLLECTORS))
            enabled -= unknown

    if getattr(args, "enable_blktrace",     False): enabled.add("blktrace")
    if getattr(args, "enable_biosnoop",     False): enabled.add("biosnoop")

    # Generic service-mode DRAM PMU switch.  This mirrors collect-mode
    # --enable-dram so offline service cycles can contain timestamped CPU DRAM
    # bandwidth rows even when no Prometheus server is available.
    if getattr(args, "enable_amduprof_pcm", False):
        setattr(args, "enable_dram", True)
        if not getattr(args, "dram_tool", "auto") or getattr(args, "dram_tool", "auto") == "auto":
            setattr(args, "dram_tool", "amduprof")
    if getattr(args, "enable_dram", False):
        _dram_tool = _resolve_dram_tool(args)
        if _dram_tool == "amduprof":
            enabled.add("amduprof_pcm")
        elif _dram_tool in {"intel-pcm", "perf-imc"}:
            enabled.add("pcm")
        elif _dram_tool != "none":
            log.warning("service: unsupported --dram-tool %r; DRAM PMU collector disabled", _dram_tool)
        # DRAM *bandwidth* needs an external PMU tool.  Enabling the flag
        # without the binary present yields an enabled-but-silent collector,
        # which downstream looks identical to "the flag was never set" — so
        # check for the binary here and say which one is missing.
        import shutil as _sh
        # Check the CONFIGURED binary path first (--amduprof-pcm-bin /
        # --intel-pcm-memory-bin, env AMOPROF_AMDUPROF_PCM_BIN), then PATH.
        # These tools are normally installed outside PATH — AMDuProf lives
        # under /opt/AMDuProf_*/bin — so a PATH-only check false-warns on a
        # correctly configured host.
        _explicit = {"amduprof": getattr(args, "amduprof_pcm_bin", ""),
                     "intel-pcm": getattr(args, "intel_pcm_memory_bin", ""),
                     }.get(_dram_tool, "")
        _need = {"amduprof": ("AMDuProfPcm", "AMDuProfCLI"),
                 "intel-pcm": ("pcm-memory", "pcm-memory.x", "pcm"),
                 "perf-imc": ("perf",)}.get(_dram_tool, ())
        _found = ""
        if _explicit:
            _ep = Path(str(_explicit)).expanduser()
            if _ep.exists() and os.access(_ep, os.X_OK):
                _found = str(_ep)
            elif _ep.exists():
                log.warning("service: %s exists but is not executable — "
                            "DRAM bandwidth will not be collected", _ep)
        if not _found:
            for _b in _need:
                _w = _sh.which(_b)
                if _w:
                    _found = _w
                    break
        if _found:
            log.info("service: DRAM PMU collector = %s (%s)", _dram_tool, _found)
        else:
            log.warning(
                "service: --enable-dram resolved to %r but no usable binary was "
                "found. Checked configured path %r and PATH for %s. DRAM "
                "bandwidth will NOT be collected, so the report will show no L2 "
                "bandwidth charts. Point --amduprof-pcm-bin (env "
                "AMOPROF_AMDUPROF_PCM_BIN) at the binary, or use --dram-tool "
                "perf-imc (needs perf_event_paranoid <= 0).",
                _dram_tool, _explicit or "(unset)", "/".join(_need))
        # A vendor mismatch is silent otherwise: AMDuProf cannot read Intel
        # memory-controller counters and vice versa, so the collector runs and
        # returns nothing.
        _vendor = _detect_cpu_vendor()
        if _vendor == "intel" and _dram_tool == "amduprof":
            log.warning("service: --dram-tool amduprof on an INTEL CPU — AMDuProf "
                        "cannot read Intel memory-controller counters. Use "
                        "--dram-tool intel-pcm or perf-imc.")
        elif _vendor == "amd" and _dram_tool == "intel-pcm":
            log.warning("service: --dram-tool intel-pcm on an AMD CPU — use "
                        "--dram-tool amduprof.")

    if getattr(args, "enable_all",          False):
        enabled |= {"blktrace", "biosnoop"}
        _dram_tool_all = _resolve_dram_tool(args)
        if _dram_tool_all == "amduprof":
            enabled.add("amduprof_pcm")
        elif _dram_tool_all in {"intel-pcm", "perf-imc"}:
            enabled.add("pcm")
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
        cycle_start_epoch = time.time()
        cycle_ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(cycle_start_epoch))
        cycle_dir = output_base / f"service_cycle_{cycle_ts}"
        raw_dir = cycle_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        log.info("service: cycle %d starting (%s; epoch=%.3f)", cycle, cycle_ts, cycle_start_epoch)

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
        # One poller per blktrace collector so multi-SSD runs each parse
        # their own binary trace stream.
        blktrace_pollers: list[BlktraceServicePoller] = []
        for _bt_name, _bt_coll in collectors.items():
            if not (_bt_name == "blktrace" or _bt_name.startswith("blktrace__")):
                continue
            if _bt_name not in started or _bt_coll is None:
                continue
            _trace_prefix = getattr(_bt_coll, "_trace_prefix", None)
            _csv_path     = getattr(_bt_coll, "_csv_path", None)
            _blkparse_bin = getattr(_bt_coll, "blkparse_bin", "blkparse")
            if _trace_prefix is None or _csv_path is None:
                continue
            _poller = BlktraceServicePoller(
                trace_prefix=_trace_prefix,
                csv_path=_csv_path,
                store=store,
                blkparse_bin=_blkparse_bin,
                interval_s=blkparse_interval_s,
                use_sudo=use_sudo,
            )
            _poller.start()
            blktrace_pollers.append(_poller)
            log.info("service: blktrace poller started for %s (interval=%.0fs)",
                     _bt_name, blkparse_interval_s)

        stop_event.wait(timeout=scrape_s)

        # Stop the blktrace pollers first so each does a final parse before
        # the blktrace binary collectors are stopped and files are closed.
        for _poller in blktrace_pollers:
            try:
                _poller.stop()
            except Exception as _e:
                log.warning("service: blktrace poller stop failed: %s", _e)
        if blktrace_pollers:
            log.info("service: %d blktrace poller(s) stopped", len(blktrace_pollers))

        cycle_end_epoch = time.time()
        cycle_summaries: dict[str, dict[str, Any]] = {}
        raw_paths: dict[str, str] = {}
        for name, c in collectors.items():
            if name not in started:
                continue
            try:
                result = c.stop()
            except Exception as exc:
                result = {f"{name}_available": False, f"{name}_error": str(exc)}
            if result is None:
                result = {f"{name}_available": False}
            result = dict(result)
            result.setdefault("collection_start_time_seconds", round(cycle_start_epoch, 6))
            result.setdefault("collection_end_time_seconds", round(cycle_end_epoch, 6))
            result.setdefault("collection_duration_s", round(cycle_end_epoch - cycle_start_epoch, 6))
            cycle_summaries[name] = result
            store.update(name, result)

        try:
            _persist_service_cycle(
                cycle_dir=cycle_dir, raw_dir=raw_dir, cycle=cycle, enabled=enabled,
                collectors=collectors, summaries=cycle_summaries, raw_paths=raw_paths,
                start_epoch=cycle_start_epoch, end_epoch=cycle_end_epoch,
                interval_s=interval_s, scrape_s=scrape_s, args=args,
                store=store,
            )
        except Exception as exc:
            log.warning("service: failed to persist timestamped local cycle %d: %s", cycle, exc)

        log.info("service: cycle %d complete, store covers %d collector(s); local raw=%s",
                 cycle, len(store.snapshot()[0]), raw_dir)

        if stop_event.is_set():
            break

        # brief gap so successive cycles never share the same timestamp
        stop_event.wait(timeout=0.5)

    prom.stop()
    log.info("service: shut down after %d cycle(s)", cycle)
    print(f"\nAMOprof service stopped after {cycle} cycle(s).\n", flush=True)
    return 0
