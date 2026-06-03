from __future__ import annotations

import argparse
import csv
import re
import json
import logging
import os
import textwrap
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
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
from .bench_swebench import SGLangMetricsSampler
from .nsys_collector import NsysGpuTraceCollector

log = logging.getLogger("amoprof")


def _copy_bench_summary(args, raw_dir: Path) -> None:
    """Copy --bench-summary source file into raw/bench_summary.<ext> so the
    interactive report's auto-discovery picks it up. Idempotent — safe to
    call from multiple subcommands.
    """
    src_path = getattr(args, "bench_summary", "") or ""
    if not src_path:
        return
    src = Path(src_path).expanduser()
    if not src.exists():
        log.warning("--bench-summary file not found: %s", src)
        return
    if src.stat().st_size == 0:
        log.warning("--bench-summary file is empty: %s", src)
        return
    ext = ".json" if src.suffix.lower() == ".json" else ".txt"
    dst = raw_dir / f"bench_summary{ext}"
    try:
        shutil.copyfile(src, dst)
        log.info("Copied bench summary: %s → %s", src, dst)
    except Exception as e:
        log.warning("bench summary copy failed: %s", e)


def _copy_setup_details(args, raw_dir: Path) -> None:
    """Copy --setup-details JSON into raw/setup_details.json so both the
    static and interactive reports can render the Setup / Server Configuration
    panel from the same canonical location.

    The file is intentionally copied, not symlinked, so the run directory is
    self-contained and can be archived or copied to another machine.
    """
    src_path = getattr(args, "setup_details", "") or ""
    if not src_path:
        return
    src = Path(src_path).expanduser()
    if not src.exists():
        log.warning("--setup-details file not found: %s", src)
        return
    if src.stat().st_size == 0:
        log.warning("--setup-details file is empty: %s", src)
        return
    try:
        with open(src, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            log.warning("--setup-details must be a JSON object at top level: %s", src)
            return
    except Exception as e:
        log.warning("--setup-details is not valid JSON: %s (%s)", src, e)
        return
    dst = raw_dir / "setup_details.json"
    try:
        shutil.copyfile(src, dst)
        log.info("Copied setup details: %s → %s", src, dst)
    except Exception as e:
        log.warning("setup details copy failed: %s", e)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _find_pid_by_port(port: int) -> int | None:
    try:
        import psutil  # type: ignore
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                if conn.pid:
                    return int(conn.pid)
    except Exception:
        pass
    return None


def _wait_for_sglang_metrics(port: int, host: str = "127.0.0.1",
                             timeout_s: float = 120.0, settle_s: float = 0.0) -> bool:
    import urllib.request
    deadline = time.time() + max(float(timeout_s), 0.0)
    url = f"http://{host}:{port}/metrics"
    last_err = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    if settle_s > 0:
                        time.sleep(settle_s)
                    return True
        except Exception as e:
            last_err = str(e)
        time.sleep(1.0)
    log.warning("Timed out waiting for SGLang metrics on %s:%s: %s", host, port, last_err)
    return False

def _sanitize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    return value


def _series_from_obj(obj: Any) -> list[dict[str, Any]]:
    if hasattr(obj, "samples") and isinstance(getattr(obj, "samples"), list):
        rows = []
        for item in getattr(obj, "samples"):
            if isinstance(item, dict):
                rows.append(dict(item))
        return rows
    if hasattr(obj, "_samples") and isinstance(getattr(obj, "_samples"), list):
        raw = getattr(obj, "_samples")
        rows = []
        for item in raw:
            if isinstance(item, dict):
                rows.append(dict(item))
            elif isinstance(item, tuple) and len(item) == 3:
                tag, ts, payload = item
                if isinstance(payload, dict):
                    d = {"tag": tag, "ts": ts}
                    d.update(payload)
                    rows.append(d)
        return rows
    return []


def _normalize_ts(rows: list[dict[str, Any]], t0: float) -> list[dict[str, Any]]:
    out = []
    for idx, row in enumerate(rows):
        d = dict(row)
        ts = d.get("ts", d.get("_ts"))
        if isinstance(ts, (int, float)):
            d["ts"] = round(float(ts), 6)
            d["time_sec"] = round(float(ts) - t0, 6)
        else:
            d["time_sec"] = float(idx)
        d["iteration"] = idx
        out.append(d)
    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize(payload), indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_sanitize(row), sort_keys=True) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen = set()
    preferred = ["collector", "iteration", "time_sec", "ts", "tag", "ai_operation"]
    for k in preferred:
        for row in rows:
            if k in row and k not in seen and not isinstance(row[k], (dict, list, tuple)):
                seen.add(k)
                keys.append(k)
                break
    for row in rows:
        for k, v in row.items():
            if isinstance(v, (dict, list, tuple)):
                continue
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            flat = {k: row.get(k, "") for k in keys}
            writer.writerow(flat)


def _flatten_summary(meta: dict[str, Any], summary: dict[str, dict[str, Any]], raw_paths: dict[str, str]) -> dict[str, Any]:
    row: dict[str, Any] = dict(meta)
    for name, metrics in summary.items():
        row[f"raw_{name}_json"] = json.dumps(_sanitize(metrics), sort_keys=True)
        for key, value in metrics.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                row[f"{name}__{key}"] = value
    for name, path in raw_paths.items():
        row[f"raw_{name}_path"] = path
    return row


def _classify_sglang_operation(prev: dict[str, Any] | None, cur: dict[str, Any]) -> str:
    if prev is None:
        if float(cur.get("sglang:num_running_reqs", 0.0) or 0.0) <= 0:
            return "idle"
        return "active"
    def d(key: str) -> float:
        return max(float(cur.get(key, 0.0) or 0.0) - float(prev.get(key, 0.0) or 0.0), 0.0)
    prefill_compute = d("sglang:realtime_tokens_total[mode=prefill_compute]")
    prefill_cache = d("sglang:realtime_tokens_total[mode=prefill_cache]")
    decode = d("sglang:realtime_tokens_total[mode=decode]")
    running = float(cur.get("sglang:num_running_reqs", 0.0) or 0.0)
    queue = float(cur.get("sglang:num_queue_reqs", 0.0) or 0.0)
    gen_tp = float(cur.get("sglang:gen_throughput", 0.0) or 0.0)
    if running <= 0 and queue <= 0 and prefill_compute == 0 and prefill_cache == 0 and decode == 0:
        return "idle"
    if prefill_compute > 0 and decode == 0:
        return "prefill"
    if prefill_cache > 0 and prefill_compute == 0 and decode == 0:
        return "prefill_cache"
    if decode > 0 and (prefill_compute + prefill_cache) == 0:
        return "decode"
    if (prefill_compute + prefill_cache) > 0 and decode > 0:
        return "mixed"
    if queue > 0 and running <= 0:
        return "queued"
    if gen_tp > 0:
        return "decode"
    return "active"


def _build_sglang_operation_rows(sglang_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(sglang_rows, key=lambda r: float(r.get("time_sec", 0.0)))
    op_rows: list[dict[str, Any]] = []
    prev = None
    for row in rows:
        cur = dict(row)
        cur["ai_operation"] = _classify_sglang_operation(prev, cur)
        if prev is not None:
            for key in (
                "sglang:realtime_tokens_total[mode=prefill_compute]",
                "sglang:realtime_tokens_total[mode=prefill_cache]",
                "sglang:realtime_tokens_total[mode=decode]",
                "sglang:evicted_tokens_total",
                "sglang:load_back_tokens_total",
            ):
                cur[f"delta::{key}"] = max(float(cur.get(key, 0.0) or 0.0) - float(prev.get(key, 0.0) or 0.0), 0.0)
            dt = max(float(cur.get("time_sec", 0.0)) - float(prev.get("time_sec", 0.0)), 1e-9)
            cur["window_sec"] = round(dt, 6)
            cur["prefill_compute_tok_s"] = round(cur.get("delta::sglang:realtime_tokens_total[mode=prefill_compute]", 0.0) / dt, 6)
            cur["prefill_cache_tok_s"] = round(cur.get("delta::sglang:realtime_tokens_total[mode=prefill_cache]", 0.0) / dt, 6)
            cur["decode_tok_s"] = round(cur.get("delta::sglang:realtime_tokens_total[mode=decode]", 0.0) / dt, 6)
        else:
            cur["window_sec"] = 0.0
            cur["prefill_compute_tok_s"] = 0.0
            cur["prefill_cache_tok_s"] = 0.0
            cur["decode_tok_s"] = 0.0
        op_rows.append(cur)
        prev = row
    return op_rows


def _nearest_operation(time_sec: float, op_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not op_rows:
        return None
    best = min(op_rows, key=lambda r: abs(float(r.get("time_sec", 0.0)) - time_sec))
    return best


def _aggregate_numeric(rows: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for row in rows:
        for k, v in row.items():
            if isinstance(v, bool):
                continue
            try:
                fv = float(v)
            except Exception:
                continue
            if k in {"iteration", "ts", "time_sec", "window_sec"}:
                continue
            values.setdefault(k, []).append(fv)
    out: dict[str, float] = {}
    for k, xs in values.items():
        if not xs:
            continue
        out[f"{k}__mean"] = round(sum(xs) / len(xs), 6)
        out[f"{k}__max"] = round(max(xs), 6)
        out[f"{k}__min"] = round(min(xs), 6)
    return out


def _preflight_diagnostic(args: argparse.Namespace) -> None:
    """Inspect collect-time args and warn about charts that will be empty.

    This runs once at the start of every `collect` invocation. The goal is
    that the user discovers missing tools BEFORE the run begins, not after
    the report is generated. We don't fail — collection continues with
    whatever is enabled.

    Each optional source maps to a list of charts that won't render in the
    bundled amoprof HTML report without it.
    """
    import shutil as _sh
    missing: list[tuple[str, str, list[str], str]] = []

    # blktrace — per-request NVMe events
    if not getattr(args, "enable_blktrace", False):
        missing.append((
            "blktrace",
            "--enable-blktrace",
            ["§C SSD Read Workload (size/IAT/alignment/LBA hot-cold)",
             "§D SSD Write Workload (size/IAT/alignment)",
             "§H NVMe Deep Profiling (req size/access alignment/seq-vs-random)",
             "KV$ SSD IO Workload Characteristics (8 sub-panels)"],
            "apt install blktrace  (or yum install blktrace)",
        ))
    elif not _sh.which(getattr(args, "blktrace_bin", "blktrace")):
        log.warning("--enable-blktrace passed but blktrace binary not found "
                    "in PATH. Install: apt install blktrace")

    # biosnoop — per-PID I/O attribution
    if not getattr(args, "enable_biosnoop", False):
        missing.append((
            "biosnoop",
            "--enable-biosnoop",
            ["§I per-stream bandwidth (PID → stream attribution)"],
            "apt install bpfcc-tools  (provides biosnoop-bpfcc)",
        ))
    elif not _sh.which(getattr(args, "biosnoop_bin", "biosnoop-bpfcc")):
        log.warning("--enable-biosnoop passed but biosnoop binary not found "
                    "in PATH. Install: apt install bpfcc-tools")

    # AMDuProf PCM — DRAM bandwidth (CPU PMU counters)
    if not getattr(args, "enable_amduprof_pcm", False):
        missing.append((
            "AMDuProf PCM",
            "--enable-amduprof-pcm",
            ["§F DRAM Bandwidth (read/write GB/s from AMD EPYC PMU)"],
            "Install AMDuProf and pass --amduprof-pcm-bin /path/AMDuProfPcm",
        ))
    elif not Path(getattr(args, "amduprof_pcm_bin", "")).exists():
        log.warning("--enable-amduprof-pcm passed but binary not found at %s. "
                    "Pass --amduprof-pcm-bin /opt/AMDuProf_X/bin/AMDuProfPcm",
                    args.amduprof_pcm_bin)

    if not missing:
        log.info("Pre-flight: all optional collectors enabled ✓")
        return

    log.warning("Pre-flight: %d optional collector%s NOT enabled — some charts "
                "will be empty:", len(missing), "s" if len(missing) > 1 else "")
    for name, flag, charts, install in missing:
        log.warning("  %s (%s)", name, flag)
        for c in charts:
            log.warning("      missing chart: %s", c)
        log.warning("      install: %s", install)
    log.warning("Tip: pass --enable-all to turn on every optional collector at once.")


def _audit_raw_dir(raw_dir: Path) -> dict[str, list[str]]:
    """Check a raw/ directory for the presence of each data source and
    return a {present: [...], missing: [...]} dict. Used by analyze to
    tell the user up-front which charts the report will lack.
    """
    sources = {
        # source_key: (filename(s), human label, what will be missing)
        "blktrace":     (["blkparse_events.generated.csv", "blktrace_data"],
                         "blktrace (per-request NVMe events)",
                         "§C/§D/§H request-level NVMe charts"),
        "biosnoop":     (["biosnoop.csv", "biosnoop_events.csv"],
                         "biosnoop (per-PID I/O attribution)",
                         "§I per-stream bandwidth"),
        "amduprof_pcm": (["amduprof_pcm_raw.csv", "amduprof_pcm_raw.txt"],
                         "AMDuProf PCM (DRAM bandwidth)",
                         "§F DRAM Bandwidth chart"),
        "sglang":       (["sglang_timeseries.csv"],
                         "SGLang inference scrape",
                         "all SGLang inference charts"),
        "gpu":          (["gpu_timeseries.csv"],
                         "DCGM GPU metrics",
                         "GPU util/HBM/power timeline"),
        "nvme_driver":  (["nvme_driver_timeseries.csv"],
                         "NVMe driver / iostat",
                         "aggregate NVMe IOPS/BW/latency"),
        "vmstat":       (["vmstat_timeseries.csv"],
                         "/proc/vmstat (swap activity)",
                         "swap storm analysis"),
        "power":        (["power_timeseries.csv"],
                         "IPMI / DCGM power",
                         "system power timeline"),
    }
    present, missing = [], []
    for key, (files, label, _what) in sources.items():
        ok = False
        for fname in files:
            p = raw_dir / fname
            if p.exists() and (p.is_dir() or p.stat().st_size > 0):
                ok = True
                break
        (present if ok else missing).append((key, label, sources[key][2]))
    return {"present": present, "missing": missing}


def _print_audit(audit: dict[str, list[str]]) -> None:
    """Pretty-print the audit results."""
    if audit["present"]:
        log.info("Data sources present (%d):", len(audit["present"]))
        for _k, label, _what in audit["present"]:
            log.info("  ✓ %s", label)
    if audit["missing"]:
        log.warning("Data sources MISSING (%d) — corresponding charts will be empty:",
                    len(audit["missing"]))
        for _k, label, what in audit["missing"]:
            log.warning("  ✗ %s  →  missing: %s", label, what)


def _run_amoprof(raw_dir: Path, output_html: Path,
                 verbose: bool = False,
                 extra_args: list[str] | None = None,
                 sglang_page_size: int = 0) -> int:
    """
    Invoke the bundled amoprof analyzer against a `raw/` directory.

    amoprof produces a self-contained HTML report (with charts inline as base64)
    from the canonical CSV/JSON files written by `write_amoprof_files`.

    Args:
        raw_dir          : Directory containing the canonical CSV/JSON files.
        output_html      : Where to write the HTML report.
        sglang_page_size : SGLang page_size (tokens per KV block). 0 means
                           let amoprof auto-detect from the sglang_page_size
                           metric column if present, else default to 16.
                           Forwarded as --kv-block-size to bundled amoprof.

    Returns the subprocess exit code (0 = success).
    """
    import subprocess as _sp
    import sys as _sys
    amoprof_py = Path(__file__).resolve().parent / "report" / "amoprof.py"
    if not amoprof_py.exists():
        log.warning("amoprof not bundled: missing %s", amoprof_py)
        return 2

    # Ensure the AMDuProf raw CSV has a .txt sibling — the bundled report's
    # load_raw_dir() loads any *.csv into a pandas DataFrame first, which
    # makes the DRAM-BW text parser skip the file. The text parser only
    # runs if a string copy is found, so we mirror .csv → .txt here. This
    # also fixes pre-existing run dirs that were collected before
    # write_amoprof_files learned to create the mirror.
    amd_csv = raw_dir / "amduprof_pcm_raw.csv"
    amd_txt = raw_dir / "amduprof_pcm_raw.txt"
    if amd_csv.exists() and amd_csv.stat().st_size > 0:
        try:
            need_mirror = (not amd_txt.exists()
                           or amd_txt.stat().st_mtime < amd_csv.stat().st_mtime)
            if need_mirror:
                amd_txt.write_text(amd_csv.read_text(errors="replace"),
                                   encoding="utf-8")
                log.info("Mirrored amduprof_pcm_raw.csv → .txt for DRAM-BW parser")
        except Exception as e:
            log.warning("amduprof .txt mirror failed: %s", e)

    cmd = [_sys.executable, str(amoprof_py),
           "--raw", str(raw_dir),
           "--output", str(output_html)]
    if sglang_page_size and sglang_page_size > 0:
        cmd.extend(["--kv-block-size", str(int(sglang_page_size))])
    if extra_args:
        cmd.extend(extra_args)
    # Pass blktrace data automatically if present
    blkparse_csv = raw_dir / "blkparse_events.generated.csv"
    blktrace_bin_dir = raw_dir / "blktrace_data"
    # A CSV with only the header row (or empty) means a prior parse failed.
    # If we have the raw binaries, attempt to re-parse rather than passing
    # the stale empty CSV to amoprof.
    csv_has_data = False
    if blkparse_csv.exists() and blkparse_csv.stat().st_size > 0:
        try:
            with open(blkparse_csv, "r", encoding="utf-8") as _fh:
                _hdr = _fh.readline()
                _first = _fh.readline()
                csv_has_data = bool(_first.strip())
        except Exception:
            csv_has_data = False
    # Do not pass very large per-event blktrace CSVs directly to the HTML
    # report. A multi-GB blkparse_events.generated.csv can make pandas load /
    # chart generation take minutes or hours. The report should consume the
    # compact pre-aggregated analysis CSVs instead.
    max_raw_mb = int(os.environ.get("AMOPROF_MAX_RAW_BLKTRACE_CSV_MB", "256"))
    blkparse_raw_too_large = (
        blkparse_csv.exists()
        and blkparse_csv.stat().st_size > max_raw_mb * 1024 * 1024
    )
    if csv_has_data and not blkparse_raw_too_large:
        cmd.extend(["--blktrace", str(blkparse_csv)])
    elif csv_has_data and blkparse_raw_too_large:
        log.info("blkparse_events.generated.csv is %d MB; skipping raw --blktrace load "
                 "and using pre-aggregated blktrace analysis files instead "
                 "(override with AMOPROF_MAX_RAW_BLKTRACE_CSV_MB).",
                 blkparse_csv.stat().st_size // (1024 * 1024))
    elif blktrace_bin_dir.exists() and any(blktrace_bin_dir.glob("trace.blktrace.*")):
        # Either no CSV, or CSV is header-only. Re-parse from binaries.
        if blkparse_csv.exists():
            log.warning("blkparse_events.generated.csv has no data rows — "
                        "re-parsing from %d binary file(s)",
                        len(list(blktrace_bin_dir.glob("trace.blktrace.*"))))
        try:
            generated = _blkparse_to_csv(blktrace_bin_dir, blkparse_csv)
            if generated and generated.exists() and generated.stat().st_size > 0:
                cmd.extend(["--blktrace", str(generated)])
            else:
                log.error("blkparse re-parse failed — see errors above. "
                          "Manual fix: blkparse -i %s/trace > /tmp/events.txt 2>&1 | head",
                          blktrace_bin_dir)
        except Exception as e:
            log.warning("blkparse-on-analyze failed: %s", e)

    # Pre-aggregate blktrace events into the analysis CSVs that amoprof reads
    # (bandwidth_per_stream, hot_regions, interarrival, burst_windows, etc.).
    # Without these, half the §C/§D/§E charts render as "no data" panels.
    if blkparse_csv.exists() and blkparse_csv.stat().st_size > 0:
        # Re-check whether we now have data rows. For huge CSVs, run the
        # streaming analyzer and pass only the compact analysis dir to the
        # report. If analysis outputs are already present, reuse them unless
        # the raw CSV is newer.
        try:
            with open(blkparse_csv, "r", encoding="utf-8") as _fh:
                _hdr = _fh.readline()
                if _fh.readline().strip():
                    # Write blktrace analysis to a dedicated subdir so it
                    # never overwrites the collect-time summary.json.
                    ba_dir   = raw_dir / "blktrace_analysis"
                    sentinel = ba_dir  / "temporal_read_write_trim_pattern.csv"
                    need_analyze = (
                        not sentinel.exists()
                        or sentinel.stat().st_mtime < blkparse_csv.stat().st_mtime
                    )
                    if need_analyze:
                        ba_dir.mkdir(parents=True, exist_ok=True)
                        from .blktrace_analyzer import (
                            analyze as _bt_analyze,
                            analyze_from_binaries as _bt_analyze_bins,
                        )
                        # If the CSV is capped/missing but raw binaries exist,
                        # stream analysis directly from the binaries.
                        _bin_dir = raw_dir / "blktrace_data"
                        # Re-read csv_has_data now: _blkparse_to_csv may have
                        # just regenerated the CSV, making the earlier check stale.
                        _csv_has_data_now = False
                        if blkparse_csv.exists() and blkparse_csv.stat().st_size > 0:
                            try:
                                with open(blkparse_csv, "r",
                                          encoding="utf-8") as _fh2:
                                    _fh2.readline()  # header
                                    _csv_has_data_now = bool(_fh2.readline().strip())
                            except Exception:
                                _csv_has_data_now = False
                        _use_bins = (
                            _bin_dir.exists()
                            and any(_bin_dir.glob("trace.blktrace.*"))
                            and not _csv_has_data_now   # prefer CSV when available
                        )
                        if _use_bins:
                            log.info("blktrace_analyzer: CSV missing/capped — "
                                     "streaming analysis from %d binary file(s) in %s",
                                     len(list(_bin_dir.glob("trace.blktrace.*"))),
                                     _bin_dir)
                            n_files = _bt_analyze_bins(_bin_dir, ba_dir)
                        else:
                            n_files = _bt_analyze(blkparse_csv, ba_dir)
                        if n_files:
                            log.info("blktrace_analyzer: produced %d analysis CSVs",
                                     len(n_files))
                    else:
                        log.info("blktrace_analyzer: reusing existing analysis CSVs in %s", raw_dir)
                    if sentinel.exists():
                        cmd.extend(["--blktrace-analysis-dir", str(ba_dir)])
        except Exception as e:
            log.warning("blktrace_analyzer failed: %s", e)
    log.info("Running amoprof: %s", " ".join(cmd))
    try:
        rc = _sp.call(cmd)
        return int(rc)
    except FileNotFoundError as e:
        log.warning("amoprof launch failed: %s", e)
        return 127


def _blkparse_to_csv(bin_dir: Path, out_csv: Path,
                     blkparse_bin: str = "blkparse") -> Path | None:
    """Re-parse a directory of `trace.blktrace.N` binaries into amoprof CSV format.

    Captures stderr and rc to surface silent failures. Logs the actual
    command + an unmatched-line sample if the regex misses, so the user
    knows what to fix.
    """
    import subprocess as _sp
    bins = sorted(bin_dir.glob("trace.blktrace.*"))
    if not bins:
        log.warning("_blkparse_to_csv: no trace.blktrace.* files in %s", bin_dir)
        return None
    prefix = bin_dir / "trace"
    # Use default text event output. Do NOT pass -O here: on several
    # blkparse versions -O suppresses/changes normal event formatting and
    # produces summary-like lines, causing the parser to match 0 events.
    cmd = [blkparse_bin, "-i", str(prefix)]
    log.info("_blkparse_to_csv: parsing %d binaries (%d MB total) with: %s",
             len(bins),
             sum(p.stat().st_size for p in bins) // (1024*1024),
             " ".join(cmd))
    line_re = re.compile(
        r"^\s*(?P<major>\d+),(?P<minor>\d+)\s+(?P<cpu>\d+)\s+\d+\s+"
        r"(?P<ts>[\d.]+)\s+(?P<pid>\d+)\s+"
        r"(?P<action>[A-Z])\s+(?P<rwbs>[A-Z\.]+)\s+"
        r"(?P<sector>\d+)\s+\+\s+(?P<nsec>\d+)"
        r"(?:\s+\[(?P<comm>[^\]]+)\])?"
    )
    events = 0
    lines_read = 0
    unmatched_sample: list[str] = []
    try:
        with _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.PIPE, text=True) as proc, \
             open(out_csv, "w", encoding="utf-8", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(["ts", "pid", "action", "rwbs", "op",
                        "sector", "nsectors", "size_bytes",
                        "comm", "dev", "cpu"])
            if proc.stdout is None:
                return None
            for raw in proc.stdout:
                lines_read += 1
                m = line_re.match(raw)
                if not m:
                    if len(unmatched_sample) < 5 and raw.strip():
                        s = raw.strip()
                        if not (s.startswith(("CPU", "Input", "Total",
                                                 "Throughput", "Events"))
                                or "events queued" in s.lower()):
                            unmatched_sample.append(s[:140])
                    continue
                d = m.groupdict()
                rwbs = d["rwbs"]
                op = "D" if "D" in rwbs else "W" if "W" in rwbs else "R" if "R" in rwbs else "?"
                nsec = int(d["nsec"])
                w.writerow([d["ts"], d["pid"], d["action"], rwbs, op,
                            d["sector"], nsec, nsec * 512,
                            d.get("comm") or "",
                            f"{d['major']},{d['minor']}", d["cpu"]])
                events += 1
            # Drain stdout to ensure blkparse can exit even if the loop broke early.
            try:
                if proc.stdout:
                    proc.stdout.read()
            except Exception:
                pass
            _trace_mb_cli = sum(
                p.stat().st_size for p in bin_dir.glob("trace.blktrace.*") if p.exists()
            ) / (1024 * 1024) if bin_dir.exists() else 0
            _wait_cli = max(60, min(int(_trace_mb_cli), 600))
            try:
                proc.wait(timeout=_wait_cli)
            except subprocess.TimeoutExpired:
                log.warning("blkparse still running after %ds — killing", _wait_cli)
                try:
                    proc.kill(); proc.wait(timeout=5)
                except Exception:
                    pass
            stderr_output = (proc.stderr.read() if proc.stderr else "") or ""
            rc = proc.returncode if proc.returncode is not None else 0

        if rc != 0:
            err_tail = stderr_output.strip().splitlines()
            err_msg = err_tail[-1] if err_tail else f"rc={rc}"
            log.error("blkparse failed (rc=%s): %s. cmd=%s",
                      rc, err_msg[:300], " ".join(cmd))
            return None

        if events == 0 and lines_read == 0:
            err_tail = stderr_output.strip().splitlines()
            err_msg = err_tail[-1] if err_tail else "no stderr output"
            log.error("blkparse produced 0 lines of output (rc=0). "
                      "Check that binaries are readable and from this kernel. "
                      "stderr: %s", err_msg[:300])
            return None

        if events == 0 and lines_read > 0:
            log.error("blkparse output %d lines but regex matched 0 events. "
                      "Format may have changed. Unmatched sample: %s",
                      lines_read,
                      " | ".join(unmatched_sample[:3]))
            return None

        log.info("blkparse re-parsed %d events from %d stdout lines (%s)",
                 events, lines_read, bin_dir)
    except _sp.TimeoutExpired:
        log.error("blkparse hung beyond 30s after stdout closed")
        return None
    except Exception as e:
        log.error("blkparse re-parse exception: %s", e)
        return None
    return out_csv if events else None


def _run_analysis(run_dir: Path, verbose: bool = False) -> dict[str, Any]:
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    def _read_csv(path: Path) -> list[dict[str, Any]]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    all_rows = _read_csv(raw_dir / "all_timeseries.csv")
    sglang_rows = _read_csv(raw_dir / "sglang_timeseries.csv")
    op_rows = _build_sglang_operation_rows(sglang_rows) if sglang_rows else []
    if op_rows:
        _write_csv(analysis_dir / "sglang_operation_timeseries.csv", op_rows)
        _write_jsonl(analysis_dir / "sglang_operation_timeseries.jsonl", op_rows)

    aligned_rows: list[dict[str, Any]] = []
    for row in all_rows:
        out = dict(row)
        try:
            t = float(row.get("time_sec", 0.0) or 0.0)
        except Exception:
            t = 0.0
        op = _nearest_operation(t, op_rows)
        if op is not None:
            out["ai_operation"] = op.get("ai_operation", "unknown")
            out["sglang_time_sec"] = op.get("time_sec", "")
            out["sglang_prefill_compute_tok_s"] = op.get("prefill_compute_tok_s", "")
            out["sglang_prefill_cache_tok_s"] = op.get("prefill_cache_tok_s", "")
            out["sglang_decode_tok_s"] = op.get("decode_tok_s", "")
            out["sglang_num_running_reqs"] = op.get("sglang:num_running_reqs", "")
            out["sglang_num_queue_reqs"] = op.get("sglang:num_queue_reqs", "")
        else:
            out.setdefault("ai_operation", "unmapped")
        aligned_rows.append(out)
    if aligned_rows:
        _write_csv(analysis_dir / "all_timeseries_ai_ops.csv", aligned_rows)
        _write_jsonl(analysis_dir / "all_timeseries_ai_ops.jsonl", aligned_rows)

    by_op_collector: list[dict[str, Any]] = []
    split_dir = analysis_dir / "by_operation"
    split_dir.mkdir(parents=True, exist_ok=True)
    operations = sorted({r.get("ai_operation", "unmapped") for r in aligned_rows}) if aligned_rows else []
    for op_name in operations:
        op_subset = [r for r in aligned_rows if r.get("ai_operation") == op_name]
        if op_subset:
            _write_csv(split_dir / f"timeseries_{op_name}.csv", op_subset)
        collectors = sorted({r.get("collector", "") for r in op_subset})
        for collector in collectors:
            subset = [r for r in op_subset if r.get("collector") == collector]
            agg = {
                "ai_operation": op_name,
                "collector": collector,
                "sample_count": len(subset),
            }
            agg.update(_aggregate_numeric(subset))
            by_op_collector.append(agg)
    if by_op_collector:
        _write_csv(analysis_dir / "metrics_by_ai_operation.csv", by_op_collector)

    # Dedicated memory read/write analysis for charting DRAM/HBM traffic by AI operation.
    mem_keys = [
        "dram_read_gb_s", "dram_write_gb_s", "dram_total_gb_s",
        "dram_read_transactions", "dram_write_transactions", "dram_total_transactions",
        "hbm_read_bytes", "hbm_write_bytes", "hbm_total_bytes",
        "hbm_read_gb", "hbm_write_gb", "hbm_total_gb",
    ]
    mem_rows = []
    for row in aligned_rows:
        if not any(k in row and str(row.get(k, "")) != "" for k in mem_keys):
            continue
        out = {
            "collector": row.get("collector", ""),
            "ai_operation": row.get("ai_operation", "unmapped"),
            "iteration": row.get("iteration", ""),
            "time_sec": row.get("time_sec", ""),
            "sglang_time_sec": row.get("sglang_time_sec", ""),
        }
        for k in mem_keys:
            if k in row:
                out[k] = row.get(k, "")
        mem_rows.append(out)
    if mem_rows:
        _write_csv(analysis_dir / "memory_rw_timeseries_by_ai_operation.csv", mem_rows)
        mem_aggs = []
        for op_name in sorted({r.get("ai_operation", "unmapped") for r in mem_rows}):
            for collector in sorted({r.get("collector", "") for r in mem_rows if r.get("ai_operation") == op_name}):
                subset = [r for r in mem_rows if r.get("ai_operation") == op_name and r.get("collector") == collector]
                agg = {"ai_operation": op_name, "collector": collector, "sample_count": len(subset)}
                agg.update(_aggregate_numeric(subset))
                mem_aggs.append(agg)
        _write_csv(analysis_dir / "memory_rw_by_ai_operation.csv", mem_aggs)

    metadata = {
        "run_dir": str(run_dir),
        "analysis_dir": str(analysis_dir),
        "has_sglang": bool(sglang_rows),
        "all_timeseries_samples": len(all_rows),
        "sglang_samples": len(sglang_rows),
        "operation_samples": len(op_rows),
        "aligned_samples": len(aligned_rows),
        "operations": operations,
    }
    _write_json(analysis_dir / "analysis_manifest.json", metadata)
    if verbose:
        log.info("Analysis written to %s", analysis_dir)
    return metadata


def _validate_collection_outputs(out_dir: Path, collectors: dict[str, Any], summary: dict[str, dict[str, Any]], raw_paths: dict[str, str]) -> dict[str, Any]:
    raw_dir = out_dir / "raw"
    rows = []
    manifest: dict[str, Any] = {"out_dir": str(out_dir), "raw_dir": str(raw_dir), "collectors": {}, "missing_files": [], "empty_timeseries": []}
    for name in sorted(collectors):
        summ = summary.get(name, {}) or {}
        ts_csv = raw_dir / f"{name}_timeseries.csv"
        ts_jsonl = raw_dir / f"{name}_timeseries.jsonl"
        sum_json = raw_dir / f"{name}_summary.json"
        sample_count = 0
        try:
            if ts_jsonl.exists() and ts_jsonl.stat().st_size > 0:
                sample_count = sum(1 for _ in ts_jsonl.open("r", encoding="utf-8"))
        except Exception:
            sample_count = 0
        availability_keys = [k for k in summ if k.endswith("_available")]
        available = bool(summ.get(availability_keys[0])) if availability_keys else (True if sample_count > 0 else None)
        info = {"available": available, "sample_count": sample_count, "summary_json": str(sum_json), "timeseries_csv": str(ts_csv), "timeseries_jsonl": str(ts_jsonl), "summary_exists": sum_json.exists(), "timeseries_csv_exists": ts_csv.exists(), "timeseries_jsonl_exists": ts_jsonl.exists()}
        for f in (sum_json, ts_csv, ts_jsonl):
            if not f.exists():
                manifest["missing_files"].append(str(f))
        if sample_count == 0:
            manifest["empty_timeseries"].append(name)
        manifest["collectors"][name] = info
        rows.append({"collector": name, **info})
    for f in (raw_dir / "all_timeseries.csv", raw_dir / "all_timeseries.jsonl"):
        manifest[f.name + "_exists"] = f.exists()
        if not f.exists() and any(v.get("sample_count", 0) for v in manifest["collectors"].values()):
            manifest["missing_files"].append(str(f))
    _write_json(out_dir / "collection_validation.json", manifest)
    _write_csv(out_dir / "collection_validation.csv", rows)
    return manifest




# ── Stop-condition wait loop ───────────────────────────────────────────────────
# This is the mechanism that lets amoprof run exactly as long as the benchmark,
# without a pre-specified --duration-s, even when the benchmark runs on a
# different node.
#
# Three stop strategies (can be combined; first one to fire wins):
#
#   --until-idle       Watch SGLang's own /metrics endpoint.  When
#                      num_running_reqs == 0 and num_queue_reqs == 0 for
#                      --idle-grace-s consecutive seconds, the benchmark
#                      has drained and collection stops.  No coordination
#                      with the remote node required; amoprof already polls
#                      this endpoint every --interval-s for SGLang metrics.
#
#   --stop-file PATH   amoprof polls for a sentinel file every --stop-poll-s.
#                      The remote benchmark node creates this file when it
#                      finishes (e.g. via a shared NFS/sshfs mount, or by
#                      SSHing to the collection host):
#                          ssh dgx1 "touch /tmp/bench_done.sentinel"
#
#   --stop-url URL     amoprof HTTP-GETs a URL every --stop-poll-s.  The
#                      remote benchmark node serves HTTP 200 on this path
#                      only when the run is complete. A one-liner server
#                      works fine:
#                          # on bench node, after run finishes:
#                          python3 -m http.server 9999 &  # serves 200 for any path
#                      Or use nginx with a 200-stub location.
#
# All three strategies respect --max-duration-s as a hard ceiling.


def _wait_for_stop(args: argparse.Namespace, collectors: "dict[str, Any]") -> None:
    """Block until a stop condition fires or the timeout is reached.

    Stop conditions (first to trigger wins):
      1. args.duration_s — fixed time, as before.
      2. args.until_idle — SGLang becomes idle for idle_grace_s seconds.
      3. args.stop_file  — sentinel file appears on disk.
      4. args.stop_url   — HTTP endpoint returns 200.
      5. args.max_duration_s — hard ceiling (used as fallback when
         duration_s is None and a stop condition is given).

    Raises KeyboardInterrupt on Ctrl-C (caller catches it).
    """
    import socket

    duration_s    = getattr(args, "duration_s", None)
    max_duration  = float(getattr(args, "max_duration_s", 7200.0))
    until_idle    = bool(getattr(args, "until_idle", False))
    idle_grace    = float(getattr(args, "idle_grace_s", 15.0))
    stop_file     = getattr(args, "stop_file", None)
    stop_url      = getattr(args, "stop_url", None)
    stop_poll     = float(getattr(args, "stop_poll_s", 5.0))

    # ── Case 1: plain fixed duration (original behaviour) ─────────────────
    if duration_s is not None and not until_idle and not stop_file and not stop_url:
        time.sleep(float(duration_s))
        return

    # ── Case 2: stop-condition mode ────────────────────────────────────────
    deadline = time.monotonic() + (float(duration_s) if duration_s is not None else max_duration)

    # For --until-idle we watch the SGLang scraper that is already running
    # as a collector, rather than opening a separate HTTP connection.
    sglang_collector = collectors.get("sglang")

    idle_since: float | None = None    # monotonic timestamp when idle began
    poll_interval = min(stop_poll, 2.0)  # inner poll cadence

    log.info(
        "Collection running with stop condition(s): %s",
        ", ".join(filter(None, [
            "--until-idle" if until_idle else "",
            f"--stop-file {stop_file}" if stop_file else "",
            f"--stop-url {stop_url}" if stop_url else "",
            f"--duration-s {duration_s}" if duration_s is not None else
            f"--max-duration-s {max_duration} (ceiling)",
        ]))
    )

    def _check_stop_file() -> bool:
        if not stop_file:
            return False
        if Path(stop_file).exists():
            log.info("Stop sentinel file detected: %s — stopping collection", stop_file)
            return True
        return False

    def _check_stop_url() -> bool:
        if not stop_url:
            return False
        try:
            import urllib.request
            req = urllib.request.Request(stop_url, method="GET")
            req.add_header("User-Agent", f"amoprof/{__version__} stop-check")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    log.info("Stop URL returned 200: %s — stopping collection", stop_url)
                    return True
        except Exception:
            pass   # any error (404, timeout, refused) = not done yet
        return False

    def _check_sglang_idle() -> bool:
        """Return True once SGLang has been idle for idle_grace_s seconds."""
        nonlocal idle_since
        if not until_idle:
            return False
        # Pull the latest scrape row from the sglang collector
        if sglang_collector is None:
            log.debug("--until-idle: no sglang collector running; skipping idle check")
            return False
        try:
            rows = list(getattr(sglang_collector, "_rows", []) or [])
            if not rows:
                return False
            last = rows[-1]
            running = float(last.get("sglang:num_running_reqs", 1) or 1)
            queued  = float(last.get("sglang:num_queue_reqs",  1) or 1)
            is_idle = running <= 0 and queued <= 0
        except Exception:
            is_idle = False

        now = time.monotonic()
        if is_idle:
            if idle_since is None:
                idle_since = now
                log.info("--until-idle: SGLang became idle — waiting %.0f s grace period", idle_grace)
            elif now - idle_since >= idle_grace:
                log.info("--until-idle: SGLang idle for %.0f s — stopping collection", now - idle_since)
                return True
        else:
            if idle_since is not None:
                log.info("--until-idle: SGLang active again after %.1f s idle — resetting grace timer", now - idle_since)
            idle_since = None
        return False

    # ── Main wait loop ─────────────────────────────────────────────────────
    elapsed_log_interval = 60.0          # log progress every 60 s
    last_log = time.monotonic()

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.info(
                "Collection time limit reached (%.0f s) — stopping",
                float(duration_s) if duration_s is not None else max_duration,
            )
            break

        # Check all stop conditions each tick
        if _check_stop_file():
            break
        if _check_stop_url():
            break
        if _check_sglang_idle():
            break

        # Progress heartbeat
        now = time.monotonic()
        if now - last_log >= elapsed_log_interval:
            elapsed = (float(duration_s or max_duration)) - remaining
            log.info(
                "Collection in progress — %.0f s elapsed, %.0f s remaining until hard limit",
                elapsed, remaining,
            )
            last_log = now

        time.sleep(min(poll_interval, remaining))


def _collect(args: argparse.Namespace) -> int:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir).expanduser().resolve() / f"metrics_run_{run_id}"
    raw_dir = out_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Honor --enable-all: turn on every optional collector at once.
    if getattr(args, "enable_all", False):
        for flag in ("enable_blktrace", "enable_biosnoop", "enable_amduprof_pcm"):
            if not getattr(args, flag, False):
                setattr(args, flag, True)
                log.info("--enable-all → %s = True", flag)

    # ── Pre-flight diagnostic ───────────────────────────────────────────────
    # Tell the user exactly which optional sources will be missing BEFORE
    # the run starts, so they don't discover it at report-generation time.
    _preflight_diagnostic(args)

    # ── Sanity check — actually invoke each collector briefly ──────────────
    # This catches binary-present-but-fails-at-runtime cases (missing kernel
    # modules, no debugfs, no MSR access, BCC mismatches, SGLang endpoint
    # down, etc.). Skipped with --skip-sanity-check; failures abort unless
    # they're optional collectors (or --strict-sanity raises that bar).
    if not getattr(args, "skip_sanity_check", False):
        try:
            from .preflight import run_sanity_checks, summarize, print_results
            results = run_sanity_checks(args,
                                         sglang_host=getattr(args, "sglang_host", "127.0.0.1"),
                                         sglang_port=getattr(args, "sglang_port", 0) or 0)
            print_results(results)
            s = summarize(results)
            n = s["counts"]
            log.info("Sanity check: %d passed, %d warn, %d failed",
                     n.get("pass", 0), n.get("warn", 0), n.get("fail", 0))

            if s["failed_required"]:
                log.error("ABORTING: %d required collector(s) failed sanity check. "
                           "Fix the issues above or pass --skip-sanity-check to "
                           "bypass (your report will be incomplete).",
                           len(s["failed_required"]))
                return 4
            if s["failed_optional"]:
                if getattr(args, "strict_sanity", False):
                    log.error("ABORTING: --strict-sanity is set and %d optional "
                               "collector(s) failed.", len(s["failed_optional"]))
                    return 5
                log.warning("Proceeding with %d optional collector(s) disabled "
                             "(use --strict-sanity to abort on these).",
                             len(s["failed_optional"]))
                # Disable the failed optional collectors so we don't run them
                for r in s["failed_optional"]:
                    if "--enable-blktrace"     in r.name: args.enable_blktrace = False
                    if "--enable-biosnoop"     in r.name: args.enable_biosnoop = False
                    if "--enable-amduprof-pcm" in r.name: args.enable_amduprof_pcm = False
        except Exception as e:
            log.warning("sanity check itself failed: %s — proceeding anyway", e)
    else:
        log.info("Sanity check skipped (--skip-sanity-check)")

    pid = args.pid
    sglang_host = getattr(args, "sglang_host", "127.0.0.1")
    _sglang_is_remote = sglang_host not in ("127.0.0.1", "localhost", "::1")

    if pid is None and args.sglang_port is not None:
        if _sglang_is_remote:
            log.info("SGLang server is remote (%s) — skipping local PID auto-detection", sglang_host)
        else:
            pid = _find_pid_by_port(args.sglang_port)
            if pid:
                log.info("Detected PID %s listening on port %s", pid, args.sglang_port)

    # ── Resolve effective duration ─────────────────────────────────────────────
    # When --duration-s is not set, we run until a stop condition fires.
    # Collectors that require a fixed duration upfront (blktrace, biosnoop,
    # AMDuProfPcm) get --max-duration-s so they don't terminate early.
    # Polling collectors (iostat, vmstat, gpu, …) are stopped via .stop().
    _has_stop_condition = (
        getattr(args, "until_idle", False)
        or getattr(args, "stop_file", None)
        or getattr(args, "stop_url", None)
    )
    _effective_duration: float
    if args.duration_s is not None:
        _effective_duration = float(args.duration_s)
    elif _has_stop_condition:
        # Use max-duration-s as the ceiling for fixed-duration sub-tools
        _effective_duration = float(args.max_duration_s)
    else:
        # Neither duration-s nor a stop condition — fall back to 300 s default
        _effective_duration = 300.0
        log.info("No --duration-s or stop condition given — defaulting to 300 s")

    collectors: dict[str, Any] = {
        "iostat": IostatMonitor(args.ssd_device, args.interval_s),
        "smart": NvmeSmartMonitor(args.ssd_device, poll_s=max(int(args.interval_s), 1)),
        # Captures NVMe device capacity (/sys/block/<dev>/size) and HiCache
        # filesystem usage (df on hicache_path) into smart_summary.json so the
        # L3 HiCache capacity tile and L3 NVMe SSD layer row populate.
        "ssd_hw": SsdHardwareMonitor(args.ssd_device,
                                     hicache_path=args.hicache_path),
        "biolatency": BiolatencyCollector(args.ssd_device, duration_s=max(int(_effective_duration), 1)),
        "vmstat": VmstatMonitor(args.interval_s),
        "nvlink_pcie": NvlinkPcieMonitor(max(args.interval_s, 1.0)),
        "nvme_driver": NvmeDriverMonitor(args.ssd_device, args.interval_s),
        "gpu": GpuMonitor(args.interval_s),
        "dram": DramMonitor(args.interval_s),
        "power": PowerMonitor(args.interval_s),
        "pcm": PcmMemoryCollector(args.interval_s),
        # New: TRIM/discard time-series from /proc/diskstats — always cheap, always on
        "discard": DiscardStatsMonitor(args.ssd_device, args.interval_s, work_dir=raw_dir),
        # New: per-sample swap rates for swap-storm chart — always cheap, always on
        "swap_storm": SwapStormMonitor(args.interval_s, work_dir=raw_dir),
    }
    # New: blktrace per-request events (opt-in, requires root/sudo + blktrace pkg)
    if getattr(args, "enable_blktrace", False):
        collectors["blktrace"] = BlktraceCollector(
            args.ssd_device,
            duration_s=max(int(_effective_duration), 1),
            work_dir=raw_dir,
            blktrace_bin=getattr(args, "blktrace_bin", "blktrace"),
            blkparse_bin=getattr(args, "blkparse_bin", "blkparse"),
            use_sudo=not getattr(args, "no_sudo", False),
        )
    # New: biosnoop per-IO events with PID attribution (opt-in, requires BCC)
    if getattr(args, "enable_biosnoop", False):
        collectors["biosnoop"] = BiosnoopCollector(
            duration_s=max(int(_effective_duration), 1),
            work_dir=raw_dir,
            device=args.ssd_device,
            binary=getattr(args, "biosnoop_bin", "biosnoop-bpfcc"),
            use_sudo=not getattr(args, "no_sudo", False),
        )
    if args.enable_amduprof_pcm:
        collectors["amduprof_pcm"] = AMDuProfPcmMemoryCollector(
            duration_s=args.amduprof_duration_s or _effective_duration,
            interval_s=args.interval_s,
            binary=args.amduprof_pcm_bin,
            output_csv=str(raw_dir / "amduprof_pcm_raw.csv"),
            extra_args=args.amduprof_extra_arg or [],
        )
    if args.enable_nsys:
        if _sglang_is_remote:
            log.warning(
                "SGLang server is remote (%s) — skipping nsys (requires local PID attachment). "
                "Run AMOprof on the SGLang node for nsys profiling.", sglang_host)
        else:
            nsys_pid = args.nsys_pid or pid
            collectors["nsys"] = NsysGpuTraceCollector(
                pid=nsys_pid,
                duration_s=args.nsys_duration_s or args.duration_s,
                binary=args.nsys_bin,
                stats_binary=args.nsys_stats_bin,
                output_base=str(raw_dir / args.nsys_output_base),
                report=args.nsys_report,
                gpu_metrics_devices=args.nsys_gpu_metrics_devices,
                extra_args=args.nsys_extra_arg or [],
                work_dir=str(raw_dir),
            )
    if args.sglang_port is not None:
        collectors["sglang"] = SGLangMetricsSampler(
            args.sglang_port,
            args.interval_s,
            host=sglang_host,
            debug=bool(getattr(args, "debug_sglang", False)),
            debug_path=str(raw_dir / "sglang_debug.log"),
        )
        if getattr(args, "debug_sglang", False):
            log.info("SGLang debug enabled; diagnostics will be written to %s", raw_dir / "sglang_debug.log")
    if pid is not None:
        if _sglang_is_remote:
            log.warning(
                "SGLang server is remote (%s) — skipping PID-based collectors "
                "(perf, bpf) which require local process attachment. "
                "Run AMOprof on the SGLang node for these metrics.", sglang_host)
        else:
            collectors["perf"] = PerfStatCollector(pid)
            collectors["bpf"] = BpftraceCollector(pid, duration_s=max(int(args.duration_s), 1), work_dir=raw_dir)

    log.info("Starting metrics-only capture")
    log.info("Output directory: %s", out_dir)
    log.info("Target PID: %s", pid if pid is not None else "none")
    log.info("Collectors: %s", ", ".join(sorted(collectors)))

    started: set[str] = set()

    # Nsight Systems profiles an already-running PID; AMOprof does not launch the workload.

    t0 = time.time()
    t0_dt = datetime.fromtimestamp(t0, tz=timezone.utc)

    # Print start timestamp immediately so the user can record it for --start
    print(
        f"\n{'='*68}\n"
        f"  COLLECTION STARTED\n"
        f"  Start time : {t0_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        f"  (epoch: {t0:.0f})\n"
        f"  Run dir    : {out_dir}\n"
        f"{'='*68}\n",
        flush=True,
    )
    for name, collector in collectors.items():
        if name in started:
            continue
        try:
            collector.start()
            started.add(name)
        except Exception as e:
            log.warning("Failed to start %s: %s", name, e)

    interrupted = False
    try:
        _wait_for_stop(args, collectors)
    except KeyboardInterrupt:
        interrupted = True
        log.warning("Interrupted; stopping collectors")

    t_end = time.time()
    t_end_dt = datetime.fromtimestamp(t_end, tz=timezone.utc)
    elapsed_s = t_end - t0

    # Print end timestamp immediately (visible even before post-processing)
    status_str = "INTERRUPTED" if interrupted else "COMPLETED"
    print(
        f"\n{'='*68}\n"
        f"  COLLECTION {status_str}\n"
        f"  Start time : {t0_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        f"  (epoch: {t0:.0f})\n"
        f"  End time   : {t_end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        f"  (epoch: {t_end:.0f})\n"
        f"  Duration   : {elapsed_s:.1f} s"
        f"  ({elapsed_s/60:.1f} min)\n"
        f"\n"
        f"  To analyse this run with Prometheus, use:\n"
        f"    --start {t0:.0f} --end {t_end:.0f}\n"
        f"  Run dir    : {out_dir}\n"
        f"{'='*68}\n",
        flush=True,
    )

    summary: dict[str, dict[str, Any]] = {}
    raw_paths: dict[str, str] = {}
    all_series: list[dict[str, Any]] = []

    for name, collector in collectors.items():
        try:
            result = collector.stop()
        except Exception as e:
            result = {f"{name}_available": False, f"{name}_reason": str(e)}
        if result is None:
            result = {f"{name}_available": False, f"{name}_reason": "collector returned no data"}
        summary[name] = _sanitize(result)

        rows = _normalize_ts(_series_from_obj(collector), t0)
        for row in rows:
            row["collector"] = name
        _write_jsonl(raw_dir / f"{name}_timeseries.jsonl", rows)
        _write_csv(raw_dir / f"{name}_timeseries.csv", rows)
        raw_paths[f"{name}_timeseries_jsonl"] = str(raw_dir / f"{name}_timeseries.jsonl")
        raw_paths[f"{name}_timeseries_csv"] = str(raw_dir / f"{name}_timeseries.csv")
        if rows:
            all_series.extend(rows)

        # Merge ssd_hw (device capacity + df-based HiCache filesystem usage)
        # into the smart_summary.json that the report reads, so the L3 HiCache
        # capacity tile and L3 NVMe SSD layer text populate with df-derived
        # values without the report needing to read two separate files.
        if name == "ssd_hw":
            _smart_path = raw_dir / "smart_summary.json"
            try:
                _existing = (json.loads(_smart_path.read_text(encoding="utf-8"))
                              if _smart_path.exists() else {})
                _existing.update({k: v for k, v in result.items()
                                  if k.startswith("hicache_fs_")
                                  or k in ("nvme_device_capacity_gb",
                                           "hicache_size_gb", "hicache_file_count")})
                _smart_path.write_text(json.dumps(_existing, indent=2),
                                       encoding="utf-8")
            except Exception as _e:
                log.warning("ssd_hw → smart_summary merge failed: %s", _e)

        _write_json(raw_dir / f"{name}_summary.json", result)
        raw_paths[f"{name}_summary_json"] = str(raw_dir / f"{name}_summary.json")
        raw_text_keys = [k for k in result if isinstance(result[k], str) and ("raw" in k or "output" in k)]
        if raw_text_keys:
            txt_path = raw_dir / f"{name}_raw.txt"
            txt_path.write_text("\n\n".join(f"[{k}]\n{result[k]}" for k in raw_text_keys), encoding="utf-8")
            raw_paths[f"{name}_raw_txt"] = str(txt_path)

    all_series = sorted(all_series, key=lambda r: (float(r.get("time_sec", 0.0)), str(r.get("collector", ""))))
    if all_series:
        _write_jsonl(raw_dir / "all_timeseries.jsonl", all_series)
        _write_csv(raw_dir / "all_timeseries.csv", all_series)
        raw_paths["all_timeseries_jsonl"] = str(raw_dir / "all_timeseries.jsonl")
        raw_paths["all_timeseries_csv"] = str(raw_dir / "all_timeseries.csv")

    meta = {
        "run_id": run_id,
        "label": args.label,
        "timestamp": datetime.now().isoformat(),
        "t0_epoch": t0,
        "t_end_epoch": t_end,
        "start_time_utc": t0_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "end_time_utc":   t_end_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "duration_s": round(elapsed_s, 1),   # actual elapsed, not requested
        "requested_duration_s": args.duration_s,
        "stop_condition": (
            "duration_s" if args.duration_s is not None and not
                (getattr(args,"until_idle",False) or getattr(args,"stop_file",None) or getattr(args,"stop_url",None))
            else "until_idle" if getattr(args,"until_idle",False)
            else "stop_file" if getattr(args,"stop_file",None)
            else "stop_url" if getattr(args,"stop_url",None)
            else "max_duration_s"
        ),
        "interval_s": args.interval_s,
        "pid": pid or "",
        "sglang_port": args.sglang_port or "",
        "ssd_device": args.ssd_device,
        "hicache_path": getattr(args, "hicache_path", "/mnt/sglang_dv3"),
        "interrupted": interrupted,
    }
    summary_row = _flatten_summary(meta, summary, raw_paths)
    _write_json(out_dir / "summary.json", {"meta": meta, "summary": summary, "raw_paths": raw_paths})
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_row.keys()))
        writer.writeheader()
        writer.writerow(summary_row)

    validation = _validate_collection_outputs(out_dir, collectors, summary, raw_paths)
    log.info("Collection validation: %d collectors, %d missing files, %d empty time-series", len(validation.get("collectors", {})), len(validation.get("missing_files", [])), len(validation.get("empty_timeseries", [])))

    # ── Write amoprof-compatible files alongside the per-collector CSVs ────────
    # amoprof reads canonical filenames (sglang_timeseries.csv, gpu_timeseries.csv,
    # vmstat_timeseries.csv, power_timeseries.csv, nvme_driver_timeseries.csv,
    # sglang_summary.json) with specific column layouts. We synthesise them here
    # so a third-party analyzer like amoprof can pick up the raw/ dir directly.
    try:
        from .writer import write_amoprof_files
        sglang_samples: list[dict] = []
        sglang_source = ""
        sglang_elapsed = 0.0
        sglang_obj = collectors.get("sglang")
        if sglang_obj is not None:
            sglang_samples = getattr(sglang_obj, "raw_samples", []) or []
            sglang_source  = getattr(sglang_obj, "prometheus_url", "")
            sglang_elapsed = float(getattr(sglang_obj, "elapsed_s", 0.0))
        written = write_amoprof_files(raw_dir, t0,
                                       sglang_samples=sglang_samples,
                                       sglang_source=sglang_source,
                                       sglang_elapsed_s=sglang_elapsed,
                                       sglang_model=str(getattr(args, "model", "unknown")))
        if written:
            log.info("Wrote amoprof-compatible files: %s",
                     ", ".join(sorted(written.keys())))
            for fname, path in written.items():
                raw_paths[f"amoprof_{Path(fname).stem}"] = str(path)
    except Exception as e:
        log.warning("amoprof.writer failed: %s", e)

    if args.analyze:
        manifest = _run_analysis(out_dir, verbose=args.verbose)
        log.info("Analysis operations: %s", ", ".join(manifest.get("operations", [])))

    # ── Resolve effective report flags (same logic as _analyze) ─────────────
    _combined       = getattr(args, "combined_report",    False)
    _do_static      = getattr(args, "amoprof_report",     False) or _combined
    _do_interactive = getattr(args, "interactive_report", False) or _combined
    _theme          = getattr(args, "report_theme", "dark")
    _static_path:      "Path | None" = None
    _interactive_path: "Path | None" = None

    if _do_static:
        _copy_setup_details(args, raw_dir)
        report_path = out_dir / "amoprof_report.html"
        rc = _run_amoprof(raw_dir, report_path,
                          verbose=args.verbose,
                          sglang_page_size=getattr(args, "sglang_page_size", 0))
        if rc == 0:
            log.info("Wrote amoprof report: %s", report_path)
            if _theme != "off":
                try:
                    from .report.enhancer import enhance_report
                    enhance_report(report_path, raw_dir=raw_dir, theme=_theme)
                    log.info("Enhanced report (%s theme): %s", _theme, report_path)
                except Exception as e:
                    log.warning("report enhancer failed: %s", e)
            _static_path = report_path
        else:
            log.warning("amoprof report generation returned %s", rc)

    if _do_interactive:
        try:
            _copy_bench_summary(args, raw_dir)
            _copy_setup_details(args, raw_dir)
            from .report.interactive import build_report as _build_interactive
            int_path = out_dir / "amoprof_interactive.html"
            label = getattr(args, "label", "") or out_dir.name
            _build_interactive(raw_dir, int_path, run_label=str(label))
            log.info("Wrote interactive report: %s", int_path)
            _interactive_path = int_path
        except Exception as e:
            log.warning("interactive report failed: %s", e)

    if _combined and _static_path and _interactive_path:
        try:
            from .report.combined import build_combined_report
            combined_path = out_dir / "amoprof_combined.html"
            build_combined_report(
                raw_dir=raw_dir,
                out_html=combined_path,
                static_html_path=_static_path,
                interactive_html_path=_interactive_path,
                run_label=out_dir.name,
                theme=_theme,
            )
            log.info("Wrote combined report: %s", combined_path)
        except Exception as e:
            log.warning("combined report failed: %s", e)
    elif _combined:
        log.warning("combined report skipped — static or interactive generation failed")

    log.info("Wrote summary CSV:  %s", out_dir / "summary.csv")
    log.info("Wrote summary JSON: %s", out_dir / "summary.json")
    if all_series:
        log.info("Wrote combined timeseries: %s", raw_dir / "all_timeseries.jsonl")

    # Final console summary — repeat timestamps so they're easy to find after
    # report generation may have pushed the earlier banner off-screen.
    _reports = []
    if _static_path:
        _reports.append(f"  Static:      {_static_path}")
    if _do_interactive and _interactive_path:
        _reports.append(f"  Interactive: {_interactive_path}")
    if _combined and _static_path and _interactive_path:
        _reports.append(f"  Combined:    {out_dir / 'amoprof_combined.html'}")
    _reports_str = "\n".join(_reports) + "\n" if _reports else ""

    print(
        f"\n{'='*68}\n"
        f"  COLLECTION {'INTERRUPTED' if interrupted else 'COMPLETE'} — SUMMARY\n"
        f"  Start      : {t0_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC  (epoch: {t0:.0f})\n"
        f"  End        : {t_end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC  (epoch: {t_end:.0f})\n"
        f"  Duration   : {elapsed_s:.1f} s  ({elapsed_s/60:.1f} min)\n"
        f"  Run dir    : {out_dir}\n"
        + (_reports_str)
        + f"\n"
        f"  Analyse with Prometheus:\n"
        f"    amoprof analyze \\\n"
        f"      --run-dir {out_dir} \\\n"
        f"      --prometheus <URL> \\\n"
        f"      --start {t0:.0f} --end {t_end:.0f} \\\n"
        f"      --combined-report\n"
        f"{'='*68}\n",
        flush=True,
    )

    return 130 if interrupted else 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="amoprof",
        description="AMOprof metrics-only collector. Supports `amoprof collect ...` and direct flags like `amoprof --duration-s ...`.",
    )
    p.add_argument("--version", action="version", version=f"amoprof {__version__}")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("collect", help="Collect metrics from a running workload")
    c.add_argument("--output-dir", default=os.environ.get("AMOPROF_OUTPUT_DIR", "./amoprof_results"),
                   help="Directory for summary CSV/JSON and raw time series output")
    c.add_argument("--label", default="", help="Optional run label stored in outputs")
    c.add_argument("--duration-s", type=float, default=None,
                   help="How long to collect metrics, in seconds. "
                        "If omitted, collection runs until a stop condition fires "
                        "(--until-idle, --stop-file, or --stop-url) or until "
                        "--max-duration-s is reached. Default when no stop "
                        "condition is given: 300 s.")
    c.add_argument("--max-duration-s", type=float, default=7200.0,
                   help="Hard upper limit (seconds) when a stop condition is used "
                        "(--until-idle / --stop-file / --stop-url). Prevents "
                        "runaway collection if the remote benchmark hangs. "
                        "Default: 7200 (2 h). Ignored when --duration-s is set.")
    c.add_argument("--until-idle", action="store_true",
                   help="Stop collection automatically when SGLang becomes idle "
                        "(num_running_reqs == 0 and num_queue_reqs == 0 for "
                        "--idle-grace-s consecutive seconds). The benchmark node "
                        "does not need any special support — amoprof watches the "
                        "SGLang /metrics endpoint it is already polling.")
    c.add_argument("--idle-grace-s", type=float, default=15.0,
                   help="With --until-idle: number of consecutive seconds "
                        "SGLang must be idle before collection stops. "
                        "Protects against momentary queue drains between bursts. "
                        "Default: 15 s.")
    c.add_argument("--stop-file", default=None,
                   help="Path to a sentinel file. Collection stops as soon as "
                        "this file appears on disk. The remote benchmark node "
                        "creates the file (e.g. via NFS/sshfs mount or by SSHing "
                        "to this host) when it finishes. "
                        "Example: --stop-file /tmp/bench_done.sentinel")
    c.add_argument("--stop-url", default=None,
                   help="HTTP URL polled every --stop-poll-s seconds. Collection "
                        "stops when the URL returns HTTP 200. The remote benchmark "
                        "node exposes a tiny HTTP server (or nginx stub) that "
                        "returns 200 only after the run completes. "
                        "Example: --stop-url http://bench-node:9999/done")
    c.add_argument("--stop-poll-s", type=float, default=5.0,
                   help="Polling interval (seconds) for --stop-file and --stop-url "
                        "checks. Default: 5 s.")
    c.add_argument("--interval-s", type=float, default=1.0,
                   help="Polling interval for time-series collectors. Default: 1.0")
    c.add_argument("--ssd-device", default=os.environ.get("AMOPROF_SSD_DEVICE", "/dev/nvme0n1"),
                   help="Block device for SSD/NVMe collectors")
    c.add_argument("--hicache-path",
                   default=os.environ.get("AMOPROF_HICACHE_PATH", "/mnt/sglang_dv3"),
                   help="Mount path where HiCache stores L3 KV blocks. df is "
                        "run on this path each collect, and re-run during "
                        "analyze when the path is reachable. Default: "
                        "/mnt/sglang_dv3.  Env: AMOPROF_HICACHE_PATH.")
    c.add_argument("--pid", type=int, default=None,
                   help="Attach perf/bpf collectors to this already-running process")
    c.add_argument("--sglang-port", type=int, default=None,
                   help="Poll SGLang Prometheus metrics from this port and auto-detect PID if possible")
    c.add_argument("--sglang-host", default=os.environ.get("AMOPROF_SGLANG_HOST", "127.0.0.1"),
                   help="Hostname or IP of the SGLang server (default: 127.0.0.1). "
                        "Set when AMOprof runs on a different node than SGLang. "
                        "Env: AMOPROF_SGLANG_HOST. "
                        "Note: PID-based collectors (perf, bpf, nsys, vtune) cannot "
                        "attach to a remote process and are skipped when host is non-local.")
    c.add_argument("--debug-sglang", action="store_true",
                   help="Log SGLang scrape/parser diagnostics and write raw/sglang_debug.log")
    c.add_argument("--enable-amduprof-pcm", action="store_true",
                   help="Collect AMD uProf PCM memory read/write metrics for the interval")
    c.add_argument("--amduprof-pcm-bin", default=os.environ.get("AMOPROF_AMDUPROF_PCM_BIN", "/opt/AMDuProf_5.2-606/bin/AMDuProfPcm"),
                   help="Path to AMDuProfPcm binary")
    c.add_argument("--amduprof-duration-s", type=float, default=None,
                   help="AMDuProfPcm duration. Defaults to --duration-s")
    c.add_argument("--amduprof-extra-arg", action="append", default=[],
                   help="Extra argument passed to AMDuProfPcm. Repeatable")
    # ── New: per-request and per-IO event collectors (require root/sudo) ──────
    c.add_argument("--enable-blktrace", action="store_true",
                   help="Capture per-request block I/O events with blktrace + blkparse. "
                        "Required for §C/§D/§E/§H request-level NVMe charts (size, alignment, "
                        "sequential vs random, IAT, LBA hot/cold, TRIM events). "
                        "Requires root/sudo and the 'blktrace' package.")
    c.add_argument("--blktrace-bin", default=os.environ.get("AMOPROF_BLKTRACE_BIN", "blktrace"),
                   help="Path to blktrace binary")
    c.add_argument("--blkparse-bin", default=os.environ.get("AMOPROF_BLKPARSE_BIN", "blkparse"),
                   help="Path to blkparse binary")
    c.add_argument("--enable-biosnoop", action="store_true",
                   help="Capture per-IO events with PID/comm attribution via BCC biosnoop. "
                        "Required for §I per-stream bandwidth analysis (PID → stream mapping). "
                        "Requires root/sudo and 'bpfcc-tools' (biosnoop-bpfcc).")
    c.add_argument("--biosnoop-bin", default=os.environ.get("AMOPROF_BIOSNOOP_BIN", "biosnoop-bpfcc"),
                   help="Path to biosnoop binary (biosnoop-bpfcc on Ubuntu, biosnoop on RHEL)")
    c.add_argument("--no-sudo", action="store_true",
                   help="Don't prepend 'sudo -n' to blktrace/biosnoop commands. "
                        "Use this if AMOprof itself runs as root or sudoers is preconfigured.")
    c.add_argument("--enable-all", action="store_true",
                   help="Convenience: turn on every optional collector at once — "
                        "blktrace, biosnoop, amduprof_pcm. Equivalent to "
                        "--enable-blktrace --enable-biosnoop --enable-amduprof-pcm. "
                        "Does NOT enable --enable-nsys (which requires explicit PID "
                        "attach). Tools that aren't installed are skipped with a "
                        "warning at collection start.")
    c.add_argument("--skip-sanity-check", action="store_true",
                   help="Skip the pre-flight sanity check that actually invokes "
                        "each enabled collector for ~1-2 sec to verify it can "
                        "produce output. Useful if you know your environment is "
                        "set up and want to save ~5-10 sec at startup.")
    c.add_argument("--strict-sanity", action="store_true",
                   help="Abort collection if ANY enabled collector fails its "
                        "sanity check, including optional ones. Default behaviour "
                        "is to only abort on required-baseline failures (SSD "
                        "device missing, no GPU, SGLang unreachable).")
    c.add_argument("--enable-nsys", action="store_true",
                   help="Collect GPU trace/HBM-related data with Nsight Systems against an already-running PID")
    c.add_argument("--nsys-pid", type=int, default=None,
                   help="PID to profile with nsys. Defaults to --pid or PID auto-detected from --sglang-port")
    c.add_argument("--nsys-bin", default=os.environ.get("AMOPROF_NSYS_BIN", "nsys"),
                   help="Path to nsys binary")
    c.add_argument("--nsys-stats-bin", default=os.environ.get("AMOPROF_NSYS_STATS_BIN", "nsys"),
                   help="Path to nsys stats binary")
    c.add_argument("--nsys-duration-s", type=float, default=None,
                   help="Nsight Systems profiling duration. Defaults to --duration-s")
    c.add_argument("--nsys-output-base", default="dram_record",
                   help="Base filename for raw/dump .nsys-rep output under the run raw directory")
    c.add_argument("--nsys-report", default="cuda_gpu_trace",
                   help="nsys stats report to export as CSV. Default: cuda_gpu_trace")
    c.add_argument("--nsys-gpu-metrics-devices", default="all",
                   help="Value for nsys profile --gpu-metrics-devices. Default: all")
    c.add_argument("--nsys-extra-arg", action="append", default=[],
                   help="Extra argument passed to nsys profile. Repeatable")
    c.add_argument("--analyze", action="store_true",
                   help="Also generate operation-aligned analysis CSVs after collection")
    c.add_argument("--amoprof-report", action="store_true",
                   help="Run the bundled amoprof analyzer after collection and "
                        "produce <run-dir>/amoprof_report.html.")
    c.add_argument("--interactive-report", action="store_true",
                   help="Also produce <run-dir>/amoprof_interactive.html — "
                        "Plotly hover charts, drag-to-zoom, legend toggling.")
    c.add_argument("--combined-report", action="store_true",
                   help="Generate a single amoprof_combined.html that embeds BOTH "
                        "reports in two tabs. Implies --amoprof-report and "
                        "--interactive-report.")
    c.add_argument("--report-theme", default="dark",
                   choices=["dark", "light", "off"],
                   help="Theme applied to the static amoprof report via the enhancer. "
                        "'dark' (default) / 'light' / 'off' to skip.")
    c.add_argument("--model", default=os.environ.get("AMOPROF_MODEL", "unknown"),
                   help="Model name to record in sglang_summary.json (e.g. "
                        "'deepseek-ai/DeepSeek-R1-Distill-Llama-70B'). Env: AMOPROF_MODEL.")
    c.add_argument("--sglang-page-size", type=int,
                   default=int(os.environ.get("AMOPROF_SGLANG_PAGE_SIZE", "0")),
                   help="SGLang page_size in tokens (KV block size). 0 = auto-detect "
                        "from the sglang_page_size metric column if present, else "
                        "fall back to the SGLang default of 16. Use this when "
                        "your server was launched with --page-size <N> different "
                        "from the default (e.g. 32 or 64). Env: AMOPROF_SGLANG_PAGE_SIZE.")
    c.add_argument("--bench-summary", default="",
                   help="Path to a benchmark summary file (JSON or plaintext "
                        "from SGLang bench_serving / similar tools). Adds "
                        "per-request percentile charts (TTFT/ITL/E2E P50/P90/"
                        "P99/Max, prompt/output token length distributions, "
                        "input/output token throughput) to the interactive "
                        "report. File is copied to raw/bench_summary.* on save.")
    c.add_argument("--setup-details", default="",
                   help="Path to a setup_details.json file to embed in both "
                        "static and interactive reports. The JSON must be a "
                        "top-level object. It is copied to raw/setup_details.json "
                        "so the run directory remains self-contained.")
    c.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    a = sub.add_parser("analyze", help="Generate operation-aligned CSVs and reports "
                                         "from an existing run directory, a Prometheus "
                                         "server, or a merge of both.")
    a.add_argument("--run-dir",
                   help="Existing metrics_run_* directory. Required unless "
                        "--prometheus is given (in which case a new directory "
                        "is created at --output-dir/prom_run_<timestamp>/).")
    # ── Prometheus source ───────────────────────────────────────────────────
    a.add_argument("--prometheus", metavar="URL",
                   help="Fetch timeseries from a Prometheus server URL "
                        "(e.g. http://10.0.1.5:9090). Pulls SGLang, DCGM GPU, "
                        "node_exporter NVMe/vmstat, and IPMI power metrics via "
                        "/api/v1/query_range. Combine with --start/--end to "
                        "select a historical window. If --run-dir is also "
                        "specified, files missing from local raw/ are filled "
                        "from Prometheus (see --prefer to control conflicts).")
    a.add_argument("--start", default="",
                   help="Prometheus query window start. Accepts: Unix timestamp, "
                        "ISO datetime (2026-04-25T10:00:00, treated as UTC), or "
                        "relative offset (-1h, -30m, -2d). Default: -1h.")
    a.add_argument("--end", default="",
                   help="Prometheus query window end. Same formats as --start. "
                        "Default: 'now'.")
    a.add_argument("--prom-step", type=int, default=15, metavar="SECONDS",
                   help="Prometheus query_range step (default: 15s). Use 5 for "
                        "high-resolution short windows, 60 for multi-hour windows.")
    a.add_argument("--prom-instance", default="",
                   help="Filter all PromQL queries to one Prometheus 'instance' "
                        "label. Use this to isolate one node when multiple "
                        "nodes report to the same Prometheus server. "
                        "Example: --prom-instance msl-ssg-dgx3.msl.lab:30000")
    a.add_argument("--prom-job", default="",
                   help="Filter to a specific Prometheus job label. "
                        "Example: --prom-job sglang  (or dcgm, node, ipmi_exporter). "
                        "ANDs with --prom-instance.")
    a.add_argument("--prom-labels", nargs="*", default=[],
                   metavar="KEY=VALUE",
                   help="Extra PromQL label filters, space-separated. "
                        "Example: --prom-labels gpu=0 device=nvme9n1")
    a.add_argument("--nvme-device", default="",
                   help="NVMe device name hint for node_disk_* metrics "
                        "(e.g. nvme0n1). Lets Prometheus collector pin the "
                        "right device.")
    a.add_argument("--prefer", default="local", choices=["local", "prometheus"],
                   help="Merge conflict policy when --prometheus AND --run-dir "
                        "are both given. 'local' (default) keeps locally-collected "
                        "files; 'prometheus' overwrites with server data. Files "
                        "missing from one source are always pulled from the other.")
    a.add_argument("--list-targets", action="store_true",
                   help="Print the {job, instance} pairs visible to the "
                        "Prometheus server at --prometheus and exit. Useful for "
                        "discovering valid --prom-instance / --prom-job values.")
    a.add_argument("--output-dir", default="",
                   help="Directory where report files (amoprof_report.html, "
                        "amoprof_interactive.html) are written. "
                        "When --run-dir is also given, raw data stays in "
                        "--run-dir but all report files are written here instead "
                        "(useful for re-analyzing an existing run into a different "
                        "output location). "
                        "When --run-dir is NOT given (Prometheus-only mode), "
                        "a new prom_run_<timestamp>/ directory is created here "
                        "and both raw data and reports land in it. "
                        "Default: the run-dir itself (original behaviour).")
    # ── Report flags (apply in all modes) ───────────────────────────────────
    a.add_argument("--amoprof-report", action="store_true",
                   help="Generate the static amoprof_report.html (matplotlib PNGs "
                        "with full bottleneck analysis, KPI cards, and formulas).")
    a.add_argument("--interactive-report", action="store_true",
                   help="Generate the interactive amoprof_interactive.html "
                        "(Plotly hover charts, cake-ordered sections).")
    a.add_argument("--combined-report", action="store_true",
                   help="Generate a single amoprof_combined.html that embeds BOTH "
                        "the static and interactive reports in two tabs "
                        "(⚡ Interactive | 📊 Static). Implies --amoprof-report "
                        "and --interactive-report — both are generated and then "
                        "merged. Use this as the default one-file-to-share output.")
    a.add_argument("--report-theme", default="dark",
                   choices=["dark", "light", "off"],
                   help="Theme + tooltips + explanations applied to the amoprof "
                        "report. 'dark' (default) / 'light' / 'off' to skip.")
    a.add_argument("--sglang-page-size", type=int,
                   default=int(os.environ.get("AMOPROF_SGLANG_PAGE_SIZE", "0")),
                   help="SGLang page_size in tokens (KV block size). 0 = auto-detect "
                        "from the sglang_page_size metric column if present, else "
                        "fall back to the SGLang default of 16. Use this when your "
                        "server was launched with a non-default --page-size "
                        "(e.g. 32 or 64). Env: AMOPROF_SGLANG_PAGE_SIZE.")
    a.add_argument("--bench-summary", default="",
                   help="Path to a benchmark summary file (JSON or plaintext). "
                        "Same as the collect-side flag — adds per-request "
                        "percentile charts to the interactive report.")
    a.add_argument("--setup-details", default="",
                   help="Path to a setup_details.json file to embed in both "
                        "static and interactive reports. The JSON must be a "
                        "top-level object. It is copied to raw/setup_details.json "
                        "before report generation. This overrides/augments "
                        "auto-detected SGLang/Prometheus server-info labels.")
    a.add_argument("--amoprof-extra-arg", action="append", default=[],
                   help="Extra argument passed through to amoprof. Repeatable. "
                        "Example: --amoprof-extra-arg --excel")
    a.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # ── retime: fix SGLang offset in legacy run-dirs ────────────────────────
    r = sub.add_parser("retime",
                        help="Re-align sglang_timeseries.csv against the run's t0 "
                             "for run-dirs collected with a pre-v1.12 writer. "
                             "Adds a constant offset to every time_sec value so "
                             "the SGLang chart lines up with gpu/nvme/vmstat on "
                             "the X-axis in regenerated reports.")
    r.add_argument("--run-dir", required=True,
                   help="Existing metrics_run_* directory to retime")
    r.add_argument("--sglang-offset-s", type=float, default=None,
                   metavar="SECONDS",
                   help="Manual offset in seconds to ADD to every time_sec in "
                        "sglang_timeseries.csv. Positive shifts SGLang's "
                        "timeline forward (use when SGLang's t=0 should "
                        "actually be t=N). Required for legacy run-dirs that "
                        "don't have t0_epoch in summary.json.")
    r.add_argument("--use-heuristic", action="store_true",
                   help="When recorded values are missing and no manual "
                        "--sglang-offset-s is given, estimate the offset from "
                        "(max_gpu_time - max_sglang_time). Unreliable — "
                        "verify the result by eye after regenerating the report.")
    r.add_argument("--dry-run", action="store_true",
                   help="Print what the retime would do without modifying any files.")
    r.add_argument("--verbose", "-v", action="store_true",
                   help="Enable debug logging")

    # ── aggregate: merge multiple run dirs for a shared Prometheus window ────
    ag = sub.add_parser(
        "aggregate",
        help="Merge multiple local run directories (collected at different "
             "times or under different configs) into a single merged run, "
             "then optionally pull Prometheus data for a shared window and "
             "generate a combined report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Aggregate multiple local run directories for a given Prometheus
            time window.

            Use-cases:
              • Combine several short test runs (e.g. concurrency sweeps) into
                one report covering the full measurement campaign.
              • Re-analyse a set of per-experiment run-dirs against a shared
                Prometheus window to produce a unified comparison report.
              • Fill in gaps: some collectors ran only in certain dirs; the
                merge picks the best available data per CSV column.

            Example:
              amoprof aggregate \\
                --run-dirs ./run_c1 ./run_c4 ./run_c8 \\
                --start 1778871540 --end 1778877078 \\
                --prometheus http://prometheus:9090 \\
                --output-dir ./aggregated \\
                --combined-report
        """),
    )
    ag.add_argument(
        "--run-dirs", nargs="+", required=True, metavar="DIR",
        help="Two or more run directories (metrics_run_* or any directory "
             "containing a raw/ sub-directory). All are merged into a single "
             "synthetic run in --output-dir.")
    ag.add_argument(
        "--start", default="",
        help="Prometheus window start: Unix timestamp, ISO-8601, or relative "
             "offset (e.g. =-1h). Used to (a) filter merged timeseries rows "
             "to this window and (b) pull Prometheus when --prometheus is given.")
    ag.add_argument(
        "--end", default="",
        help="Prometheus window end: Unix timestamp, ISO-8601, or '=now'.")
    ag.add_argument(
        "--prometheus", default="", metavar="URL",
        help="Prometheus server URL. When given, the merged run is further "
             "enriched by fetching any missing metrics (same as analyze "
             "merge-mode). Optional — aggregation works without Prometheus.")
    ag.add_argument("--prom-step", type=int, default=30, metavar="SECS")
    ag.add_argument("--prom-instance", default="", metavar="HOST:PORT")
    ag.add_argument("--prom-job", default="", metavar="JOB")
    ag.add_argument("--prom-labels", default="", metavar="K=V,...")
    ag.add_argument("--nvme-device", default="", metavar="DEV")
    ag.add_argument(
        "--output-dir", default=".", metavar="DIR",
        help="Parent directory for the merged_run_<ts>/ output directory. "
             "Default: current directory.")
    ag.add_argument(
        "--run-label", default="", metavar="LABEL",
        help="Name for the merged run directory. Default: merged_<timestamp>.")
    # Report flags (same as analyze)
    ag.add_argument("--amoprof-report", action="store_true",
                    help="Generate amoprof_report.html after aggregation.")
    ag.add_argument("--interactive-report", action="store_true",
                    help="Generate amoprof_interactive.html after aggregation.")
    ag.add_argument("--combined-report", action="store_true",
                    help="Generate amoprof_combined.html after aggregation "
                         "(implies --amoprof-report + --interactive-report).")
    ag.add_argument("--report-theme", default="dark",
                    choices=["dark", "light", "off"])
    ag.add_argument("--setup-details", default="", metavar="FILE",
                    help="Path to setup_details.json to inject into the merged run.")
    ag.add_argument("--sglang-page-size", type=int, default=0, metavar="N")
    ag.add_argument("--amoprof-extra-arg", action="append", default=[])
    ag.add_argument("--prefer", default="local",
                    choices=["local", "prometheus"],
                    help="Which source wins when both local CSV and Prometheus "
                         "have data for the same metric. Default: local.")
    ag.add_argument("--verbose", "-v", action="store_true")

    # ── compare: side-by-side comparison of multiple runs ────────────────────
    cmp = sub.add_parser(
        "compare",
        help="Compare metrics across multiple run directories side-by-side. "
             "Each run can have its own Prometheus time window and label. "
             "Produces a single HTML report with delta tables, bar charts, "
             "and a performance radar chart.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Compare multiple runs side-by-side.

            Each --run argument is a colon-separated spec:
              label:raw_dir[:start[:end]]

            Examples:
              amoprof compare \\
                --run "Baseline:./run_c1:1778871540:1778877078" \\
                --run "4-way concurrency:./run_c4:1778881540:1778887078" \\
                --run "FP8 KV:./run_fp8:1778891540:1778897078" \\
                --output-dir ./comparison

              # Without timestamps (no window filtering):
              amoprof compare \\
                --run "BF16:./metrics_run_20260515" \\
                --run "FP8:./metrics_run_20260516" \\
                --output comparison.html
        """),
    )
    cmp.add_argument(
        "--run", dest="runs", action="append", required=True,
        metavar="LABEL:DIR[:START[:END]]",
        help="Run specification. Format: label:raw_dir[:prom_start[:prom_end]]. "
             "Repeat for each run to compare. First run is the baseline. "
             "START/END are Unix timestamps or ISO-8601 strings. "
             "Example: 'Baseline:./run_c1:1778871540:1778877078'")
    cmp.add_argument(
        "--output-dir", default=".", metavar="DIR",
        help="Directory where comparison.html is written. Default: current dir.")
    cmp.add_argument(
        "--output", default="", metavar="FILE",
        help="Output filename. Default: amoprof_comparison_<timestamp>.html")
    cmp.add_argument(
        "--title", default="",
        help="Report title. Default: 'AMOprof Comparison — N runs'.")
    cmp.add_argument("--verbose", "-v", action="store_true")

    # ── bench-lc: render lc_bm_results.json as a benchmark summary ───────────
    blc = sub.add_parser(
        "bench-lc",
        help="Parse a long-context benchmark results JSON (lc_bm_results.json "
             "format) and generate a self-contained HTML benchmark summary report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""            Parse a long-context benchmark results JSON and generate a benchmark
            summary report with load-level analysis, latency/throughput curves,
            and saturation analysis.

            The JSON file contains one record per (request_rate, metric) pair
            measured at each load level. Multiple load levels are shown as a
            sweep (latency vs load, throughput vs load) to characterise the
            system under increasing request pressure.

            Example:
              amoprof bench-lc \
                --input lc_bm_results.json \
                --output lc_benchmark_report.html \
                --title "DeepSeek-R1-70B Long-Context Benchmark"
        """),
    )
    blc.add_argument("--input",  "-i", required=True, metavar="FILE",
                     help="Path to lc_bm_results.json")
    blc.add_argument("--output", "-o", default="", metavar="FILE",
                     help="Output HTML path. Default: <input_stem>_report.html")
    blc.add_argument("--title",  default="", metavar="TITLE",
                     help="Report title (appears in the HTML heading).")
    blc.add_argument("--run-label", default="", metavar="LABEL",
                     help="Short label shown in the report subtitle.")
    blc.add_argument("--verbose", "-v", action="store_true")

    return p


def _refresh_smart_capacity(run_dir: Path) -> bool:
    """Re-snapshot NVMe device capacity + HiCache df stats during analyze.

    The collect-time df snapshot stale-ages fast — a long run can fill another
    100 GB of L3 KV blocks between collect-end and analyze. Worse, if a run
    was collected with an amoprof version that pre-dates SsdHardwareMonitor,
    `smart_summary.json` has no `hicache_fs_*` fields at all and the L3
    HiCache capacity tile renders blank.

    This function:
      - Reads `ssd_device` and `hicache_path` from `summary.json :: meta`
      - Re-reads `/sys/block/<dev>/size` for raw device capacity
      - Re-runs `df -B1 <hicache_path>` for live filesystem usage
      - Merges the fresh values into the existing `smart_summary.json`,
        preserving SMART fields (temperature, critical_warning, etc.)

    Silently no-ops if the device or path isn't reachable from the analysis
    host (cross-host analysis). Returns True iff smart_summary.json was
    updated.
    """
    raw_dir = run_dir / "raw"
    sum_path = run_dir / "summary.json"
    if not raw_dir.exists() or not sum_path.exists():
        return False
    try:
        s = json.loads(sum_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    meta = s.get("meta", {}) if isinstance(s.get("meta"), dict) else s
    device = meta.get("ssd_device") or ""
    hicache_path = meta.get("hicache_path") or "/mnt/sglang_dv3"
    if not device:
        return False

    fresh: dict = {}
    # ── 1. Device capacity from /sys/block/<dev>/size ───────────────────────
    try:
        dev_name = Path(device).name
        dev_base = re.sub(r"p\d+$", "", dev_name)
        size_path = Path(f"/sys/block/{dev_base}/size")
        if size_path.exists():
            sectors = int(size_path.read_text().strip())
            fresh["nvme_device_capacity_gb"] = round(sectors * 512 / (1024 ** 3), 1)
    except Exception:
        pass

    # ── 2. HiCache filesystem usage from df ──────────────────────────────────
    try:
        import subprocess as _sp
        if Path(hicache_path).exists():
            r = _sp.run(["df", "-B1", "--output=source,size,used,avail", hicache_path],
                        capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                # df output starts with a header line; data lines have a
                # /dev/... source followed by all-numeric size/used/avail.
                lines = []
                for l in r.stdout.strip().splitlines():
                    parts = l.split()
                    # source field starts with / on real filesystems
                    if len(parts) >= 4 and parts[0].startswith("/") and parts[1].isdigit():
                        lines.append(l)
                if lines:
                    parts = lines[0].split()
                    G = 1024 ** 3
                    fresh["hicache_fs_source"]   = parts[0]
                    fresh["hicache_fs_total_gb"] = round(int(parts[1]) / G, 2)
                    fresh["hicache_fs_used_gb"]  = round(int(parts[2]) / G, 2)
                    fresh["hicache_fs_avail_gb"] = round(int(parts[3]) / G, 2)
                    fresh["hicache_fs_used_pct"] = round(
                        int(parts[2]) / max(int(parts[1]), 1) * 100, 1)
    except Exception:
        pass

    # ── 2b. Partition geometry: compare what blktrace traced vs the FS backs ─
    # The block device's partition layout is needed to interpret hot-LBA
    # offsets. If the FS lives on /dev/nvme7n1p1 but blktrace traced
    # /dev/nvme7n1 (the whole device), then file-offset 0 in the FS shows
    # up at LBA = partition_start_sectors × 512 in blktrace — explaining
    # why writes appear at LBA offsets far beyond df-used.
    try:
        import subprocess as _sp
        fs_source = fresh.get("hicache_fs_source", "")
        if fs_source.startswith("/dev/"):
            fs_dev = Path(fs_source).name  # e.g. 'nvme7n1p1' or 'nvme7n1'
            traced_dev = Path(device).name  # what we asked blktrace to trace
            fresh["traced_device"] = traced_dev
            fresh["fs_backing_device"] = fs_dev
            # Read partition start offset (sectors) from
            # /sys/class/block/<part>/start. This is 0 for whole devices.
            start_path = Path(f"/sys/class/block/{fs_dev}/start")
            if start_path.exists():
                try:
                    part_start_sec = int(start_path.read_text().strip())
                    fresh["fs_partition_start_sectors"] = part_start_sec
                    fresh["fs_partition_start_gb"] = round(part_start_sec * 512 / G, 2)
                except Exception:
                    pass
            # If FS lives on a partition but we traced the whole device,
            # flag it — that produces "writes at LBA 1.9 TB on a 511 GB FS"
            # confusion.
            fs_is_part = re.search(r"p\d+$", fs_dev) is not None
            traced_is_whole = re.search(r"p\d+$", traced_dev) is None
            if fs_is_part and traced_is_whole and fs_dev != traced_dev:
                fresh["lba_offset_warning"] = (
                    f"FS lives on partition /dev/{fs_dev} (starts at LBA "
                    f"{fresh.get('fs_partition_start_gb', 0):.0f} GB on device) but "
                    f"blktrace traced whole device /dev/{traced_dev}. LBAs in the "
                    f"SSD I/O Distribution chart are device-absolute, so write "
                    f"hot spots will appear shifted by the partition offset."
                )
    except Exception:
        pass
        pass

    # ── 2c. Filesystem type + block size on the L3 mount ────────────────────
    # Captured so the report can explain "fewer captured ops on XFS is expected
    # because XFS extent-based allocation merges adjacent writes more
    # aggressively than ext4's block-based allocation." Without this we can't
    # tell the user whether op counts dropped because of measurement loss or
    # because the FS did a better job consolidating I/O.
    try:
        import subprocess as _sp
        # `stat -f -c '%T %s'` returns "FStype block_size" portably across distros.
        r = _sp.run(["stat", "-f", "-c", "%T %S %b %f", hicache_path],
                    capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split()
            if len(parts) >= 2:
                fresh["fs_type"] = parts[0]            # e.g. "xfs", "ext4"
                fresh["fs_block_size"] = int(parts[1]) # filesystem block size
    except Exception:
        pass
    # XFS-specific extra geometry (sunit/swidth, sectsz, agcount) when available.
    # These determine how XFS aggregates I/O into block-layer BIOs.
    try:
        if fresh.get("fs_type") == "xfs":
            import subprocess as _sp
            r = _sp.run(["xfs_info", hicache_path],
                        capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                xtxt = r.stdout
                # Parse the lines we care about. Each looks like:
                #   data     =   sectsz=4096  attr=2, projid32bit=1
                #   data     =   bsize=4096   blocks=854703040
                #   data     =   sunit=0      swidth=0 blks
                m_bsize = re.search(r"bsize=(\d+)",  xtxt)
                m_sectsz = re.search(r"sectsz=(\d+)", xtxt)
                m_sunit  = re.search(r"sunit=(\d+)",  xtxt)
                m_agc    = re.search(r"agcount=(\d+)", xtxt)
                if m_bsize:  fresh["xfs_bsize"]   = int(m_bsize.group(1))
                if m_sectsz: fresh["xfs_sectsz"]  = int(m_sectsz.group(1))
                if m_sunit:  fresh["xfs_sunit"]   = int(m_sunit.group(1))
                if m_agc:    fresh["xfs_agcount"] = int(m_agc.group(1))
    except Exception:
        pass

    # ── 2d. Block-layer queue + merge characteristics ────────────────────────
    # /sys/block/<dev>/queue/* tells us what BIO size the block layer is
    # willing to issue (max_sectors_kb, optimal_io_size). The merge counts
    # are in /sys/block/<dev>/stat columns 1 (rd_merges) and 5 (wr_merges).
    # We can't compute a true rate here (we don't have the trace-start
    # baseline — that's owned by BlktraceCollector), but we record the
    # *snapshot* values so the analyzer's coverage-cross-check can subtract
    # them later. Falling back gracefully on partial reads.
    try:
        dev_base = re.sub(r"p\d+$", "", Path(device).name)
        q_dir = Path(f"/sys/block/{dev_base}/queue")
        for f in ("max_sectors_kb", "optimal_io_size", "nr_requests",
                  "logical_block_size", "physical_block_size",
                  "minimum_io_size", "rotational"):
            p = q_dir / f
            if p.exists():
                try:
                    v = p.read_text().strip()
                    fresh[f"q_{f}"] = int(v) if v.lstrip("-").isdigit() else v
                except Exception:
                    pass
        # Snapshot block-layer stat counters. The BlktraceCollector records
        # the start baseline (sys_block_wr_sectors_start) at trace begin so we
        # only need the END values here — analyzer subtracts to get deltas.
        stat_p = Path(f"/sys/block/{dev_base}/stat")
        if stat_p.exists():
            cols = stat_p.read_text().split()
            # Linux /sys/block/<dev>/stat columns (from kernel iostats docs):
            #  0=rd_ios 1=rd_merges 2=rd_sectors 3=rd_ticks
            #  4=wr_ios 5=wr_merges 6=wr_sectors 7=wr_ticks
            #  8=in_flight 9=io_ticks 10=time_in_queue
            #  11=discard_ios 12=discard_merges 13=discard_sectors 14=discard_ticks
            if len(cols) >= 8:
                fresh["sys_block_rd_ios_end"]     = int(cols[0])
                fresh["sys_block_rd_merges_end"]  = int(cols[1])
                fresh["sys_block_rd_sectors_end"] = int(cols[2])
                fresh["sys_block_wr_ios_end"]     = int(cols[4])
                fresh["sys_block_wr_merges_end"]  = int(cols[5])
                fresh["sys_block_wr_sectors_end"] = int(cols[6])
    except Exception:
        pass

    if not fresh:
        return False

    # ── 3. Merge into smart_summary.json (preserve existing SMART fields) ───
    smart_path = raw_dir / "smart_summary.json"
    try:
        existing = (json.loads(smart_path.read_text(encoding="utf-8"))
                     if smart_path.exists() else {})
        existing.update(fresh)
        smart_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        log.info("Refreshed L3 capacity in smart_summary.json: %s",
                 ", ".join(f"{k}={v}" for k, v in fresh.items()))
        return True
    except Exception as e:
        log.warning("smart_summary.json refresh failed: %s", e)
        return False


def _rebuild_canonical_csvs(run_dir: Path) -> list[str]:
    """Rebuild canonical per-collector CSVs from preserved JSONLs.

    The collector writes both `<name>_timeseries.jsonl` (raw, faithful) and
    `<name>_timeseries.csv` (canonical, for the report). Older versions had
    bugs in the canonical-CSV writers (wrong field aliases, missing per-GPU
    power summation, kB/MB unit confusion), so analyze unconditionally rebuilds
    the canonical CSVs from the JSONLs using the current writers. That way
    upgrading amoprof + re-running analyze on an old run dir produces
    consistent reports without re-collecting.

    Returns the list of CSV filenames actually rebuilt.
    """
    try:
        from .writer import (write_gpu_timeseries, write_power_timeseries,
                              write_vmstat_timeseries, write_nvme_driver_timeseries)
    except Exception as e:
        log.debug("canonical-CSV rebuild: writer import failed: %s", e)
        return []

    raw_dir = run_dir / "raw"
    if not raw_dir.exists():
        return []

    # Recover t0 from summary.json (collect-time epoch anchor)
    t0 = 0.0
    sum_path = run_dir / "summary.json"
    if sum_path.exists():
        try:
            s = json.loads(sum_path.read_text(encoding="utf-8"))
            t0 = float(s.get("t0_epoch") or s.get("meta", {}).get("t0_epoch") or 0.0)
        except Exception:
            pass

    rebuilt: list[str] = []
    for name, writer_fn in [
        ("gpu_timeseries",         write_gpu_timeseries),
        ("power_timeseries",       write_power_timeseries),
        ("vmstat_timeseries",      write_vmstat_timeseries),
        ("nvme_driver_timeseries", write_nvme_driver_timeseries),
    ]:
        # The nvme writer reads either iostat_timeseries.jsonl or
        # nvme_driver_timeseries.jsonl; check both as candidate sources.
        candidates = ([raw_dir / "iostat_timeseries.jsonl",
                        raw_dir / "nvme_driver_timeseries.jsonl"]
                       if name == "nvme_driver_timeseries"
                       else [raw_dir / f"{name}.jsonl"])
        if not any(p.exists() and p.stat().st_size > 0 for p in candidates):
            continue
        try:
            p = writer_fn(raw_dir, t0)
            if p:
                rebuilt.append(p.name)
        except Exception as e:
            log.warning("analyze: failed to rebuild %s.csv: %s", name, e)
    return rebuilt


def _analyze(args) -> int:
    """analyze subcommand dispatcher — supports three modes:

      1. Prom-only:   --prometheus URL  (creates a fresh prom_run_* dir)
      2. Local-only:  --run-dir DIR     (existing behaviour)
      3. Merge:       both flags        (fill local gaps from Prometheus)
    """
    prom_url   = getattr(args, "prometheus", None)
    run_dir_arg = getattr(args, "run_dir", None)

    # ── 0. --list-targets short-circuit ─────────────────────────────────────
    if getattr(args, "list_targets", False):
        if not prom_url:
            log.error("--list-targets requires --prometheus URL")
            return 2
        try:
            from .prometheus_source import discover_targets
        except Exception as e:
            log.error("failed to import prometheus_source: %s", e)
            return 2
        hostname = (args.prom_instance or "").split(":")[0]
        targets = discover_targets(prom_url, hostname=hostname)
        if not targets:
            log.warning("No active targets returned by %s/api/v1/targets "
                        "(or hostname filter %r excluded all). Either the "
                        "server is unreachable or none of its scrape jobs "
                        "are up.", prom_url, hostname)
            return 1
        print(f"Active scrape targets on {prom_url}:")
        print(f"  {'job':<22} {'instance(s)'}")
        print(f"  {'-'*22} {'-'*44}")
        for job, instances in sorted(targets.items()):
            for i, inst in enumerate(instances):
                tag = job if i == 0 else ""
                print(f"  {tag:<22} {inst}")
        print()
        print("Use any of these with:")
        print("  amoprof analyze --prometheus", prom_url, "\\")
        print("    --prom-job <job> --prom-instance <instance>")
        return 0

    # ── 1. Argument validation ──────────────────────────────────────────────
    if not prom_url and not run_dir_arg:
        log.error("analyze requires either --run-dir or --prometheus "
                  "(or both for merge mode). Use --help for options.")
        return 2

    # ── 2. Determine the working run_dir and report_dir ─────────────────────
    # run_dir  = where raw data lives (source for the report builder)
    # report_dir = where HTML report files are written
    #
    # When --run-dir + --output-dir are both given:
    #   raw data stays in --run-dir; reports go to --output-dir.
    # When only --run-dir is given:
    #   reports go into run-dir (original behaviour).
    # When only --output-dir is given (Prometheus-only mode):
    #   a new prom_run_* dir is created inside --output-dir for everything.
    if run_dir_arg:
        run_dir = Path(run_dir_arg).expanduser().resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        if args.output_dir:
            report_dir = Path(args.output_dir).expanduser().resolve()
            report_dir.mkdir(parents=True, exist_ok=True)
            log.info("Reports will be written to --output-dir: %s", report_dir)
        else:
            report_dir = run_dir   # original behaviour
    else:
        # Prom-only mode: create a fresh prom_run_* dir
        base = Path(args.output_dir or ".").expanduser().resolve()
        run_dir = base / f"prom_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_dir = run_dir
        log.info("Prometheus-only mode → created run dir: %s", run_dir)

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # ── 3. Prometheus fetch (if requested) ──────────────────────────────────
    if prom_url:
        try:
            from .prometheus_source import (
                fetch_from_prometheus, merge_prometheus_into_local,
                parse_labels_arg,
            )
        except Exception as e:
            log.error("failed to import prometheus_source: %s", e)
            return 2

        prom_kwargs = dict(
            start=args.start, end=args.end,
            step_s=int(args.prom_step),
            instance=args.prom_instance, job=args.prom_job,
            extra_labels=parse_labels_arg(args.prom_labels),
            nvme_device=args.nvme_device,
            label=run_dir.name,
        )

        if run_dir_arg:
            # MERGE mode — keep local files, fill gaps from Prometheus.
            log.info("Merge mode: local=%s, prometheus=%s, prefer=%s",
                     run_dir, prom_url, args.prefer)
            try:
                manifest = merge_prometheus_into_local(
                    prom_url=prom_url,
                    local_raw_dir=raw_dir,
                    prefer=args.prefer,
                    **prom_kwargs,
                )
                log.info("Merge result: kept_local=%s, "
                         "copied_from_prom=%s, prom_had_no_data=%s",
                         manifest["kept_local"],
                         manifest["copied_from_prom"],
                         manifest["skipped_empty_prom"])
            except Exception as e:
                log.error("Prometheus merge failed: %s", e)
                return 3
        else:
            # PROM-ONLY mode
            try:
                result = fetch_from_prometheus(
                    prom_url=prom_url, output_dir=raw_dir, **prom_kwargs)
                log.info("Wrote %d Prometheus files: %s",
                         len(result["new_files"]),
                         ", ".join(result["new_files"]))
            except Exception as e:
                log.error("Prometheus fetch failed: %s", e)
                return 3

    # ── 3b. Rebuild canonical CSVs from preserved JSONLs ────────────────────
    # Ensures reports reflect any fixes in the writer logic even when re-running
    # analyze on a run dir collected with an older amoprof version.
    rebuilt = _rebuild_canonical_csvs(run_dir)
    if rebuilt:
        log.info("Rebuilt canonical CSVs from JSONLs: %s", ", ".join(rebuilt))

    # ── 3c. Refresh L3 NVMe device capacity + HiCache df stats ─────────────
    # Re-snapshot df + /sys/block size from the analysis host. No-op if the
    # mount/device aren't reachable (cross-host analyze).
    if _refresh_smart_capacity(run_dir):
        log.info("Refreshed L3 HiCache capacity (df + /sys/block) in smart_summary.json")

    # ── 4. Operation-aligned CSV analysis (existing behaviour) ──────────────
    try:
        _run_analysis(run_dir, verbose=args.verbose)
    except Exception as e:
        log.warning("operation-aligned analysis skipped: %s", e)

    # ── 4b. Raw-dir audit — tell the user up-front which charts will be empty
    try:
        _print_audit(_audit_raw_dir(raw_dir))
    except Exception as e:
        log.debug("raw-dir audit failed: %s", e)

    # ── Resolve effective report flags ──────────────────────────────────────
    # --combined-report implies both --amoprof-report and --interactive-report
    _combined = getattr(args, "combined_report", False)
    _do_static      = getattr(args, "amoprof_report",    False) or _combined
    _do_interactive = getattr(args, "interactive_report", False) or _combined

    _static_path:      "Path | None" = None
    _interactive_path: "Path | None" = None
    _theme = getattr(args, "report_theme", "dark")

    # ── 5. Static amoprof HTML report ───────────────────────────────────────
    if _do_static:
        _copy_setup_details(args, raw_dir)
        report_path = report_dir / "amoprof_report.html"
        rc = _run_amoprof(raw_dir, report_path,
                          verbose=args.verbose,
                          extra_args=args.amoprof_extra_arg or [],
                          sglang_page_size=getattr(args, "sglang_page_size", 0))
        if rc == 0:
            log.info("Wrote amoprof report: %s", report_path)
            if _theme != "off":
                try:
                    from .report.enhancer import enhance_report
                    enhance_report(report_path, raw_dir=raw_dir, theme=_theme)
                    log.info("Enhanced report (%s theme): %s", _theme, report_path)
                except Exception as e:
                    log.warning("report enhancer failed: %s", e)
            _static_path = report_path
        else:
            log.warning("amoprof report generation returned %s", rc)

    # ── 6. Interactive Plotly report ────────────────────────────────────────
    if _do_interactive:
        try:
            _copy_bench_summary(args, raw_dir)
            _copy_setup_details(args, raw_dir)
            from .report.interactive import build_report as _build_interactive
            int_path = report_dir / "amoprof_interactive.html"
            _build_interactive(raw_dir, int_path, run_label=run_dir.name)
            log.info("Wrote interactive report: %s", int_path)
            _interactive_path = int_path
        except Exception as e:
            log.warning("interactive report failed: %s", e)

    # ── 7. Combined tabbed report ────────────────────────────────────────────
    if _combined and _static_path and _interactive_path:
        try:
            from .report.combined import build_combined_report
            combined_path = report_dir / "amoprof_combined.html"
            build_combined_report(
                raw_dir=raw_dir,
                out_html=combined_path,
                static_html_path=_static_path,
                interactive_html_path=_interactive_path,
                run_label=run_dir.name,
                theme=_theme,
            )
            log.info("Wrote combined report: %s", combined_path)
        except Exception as e:
            log.warning("combined report failed: %s", e)
    elif _combined:
        log.warning("combined report skipped — static or interactive generation failed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())



def main(argv: list[str] | None = None) -> int:
    import sys as _sys
    parser = _build_parser()
    raw_argv = list(_sys.argv[1:] if argv is None else argv)
    # Backward-compatible direct form: `amoprof --duration-s 30 ...`
    if not raw_argv or raw_argv[0] not in {
            "collect", "analyze", "retime", "aggregate", "compare", "bench-lc",
            "--version", "-h", "--help"}:
        raw_argv = ["collect"] + raw_argv
    args = parser.parse_args(raw_argv)
    _setup_logging(getattr(args, "verbose", False))
    if args.command == "analyze":
        return _analyze(args)
    if args.command == "retime":
        from .retime import retime_run_dir
        return retime_run_dir(
            run_dir=Path(args.run_dir),
            sglang_offset_s=args.sglang_offset_s,
            dry_run=args.dry_run,
            use_heuristic=args.use_heuristic,
        )
    if args.command == "aggregate":
        return _aggregate(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "bench-lc":
        from .bench_lc_results import main_bench_lc
        return main_bench_lc(args)
    return _collect(args)


def _compare(args) -> int:
    """compare subcommand: extract metrics from each --run spec and write comparison HTML."""
    from .comparator import RunSpec, compare_runs
    from .prometheus_source import parse_time_arg

    now = datetime.now(tz=timezone.utc).timestamp()

    # ── Parse --run specs ──────────────────────────────────────────────────
    run_specs: list[RunSpec] = []
    for spec_str in args.runs:
        parts = spec_str.split(":", 3)
        if len(parts) < 2:
            log.error("compare: invalid --run spec %r — expected label:dir[:start[:end]]",
                      spec_str)
            return 2
        label   = parts[0].strip()
        raw_dir = Path(parts[1].strip()).expanduser().resolve()
        if not raw_dir.exists():
            log.error("compare: --run %r: directory not found: %s", label, raw_dir)
            return 2
        # Accept both run_dir/raw and run_dir directly
        actual_raw = raw_dir / "raw" if (raw_dir / "raw").is_dir() else raw_dir

        t_start = parse_time_arg(parts[2].strip(), now=now) if len(parts) >= 3 and parts[2].strip() else 0.0
        t_end   = parse_time_arg(parts[3].strip(), now=now) if len(parts) >= 4 and parts[3].strip() else 0.0

        run_specs.append(RunSpec(
            label=label, raw_dir=actual_raw,
            t_start=t_start, t_end=t_end,
        ))
        log.info("compare: run '%s' → %s (window: %s → %s)",
                 label, actual_raw,
                 t_start or "—", t_end or "—")

    if len(run_specs) < 2:
        log.error("compare requires at least 2 --run arguments")
        return 2

    # ── Output path ────────────────────────────────────────────────────────
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = args.output or f"amoprof_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    out_html = out_dir / fname

    # ── Run comparison ─────────────────────────────────────────────────────
    try:
        compare_runs(
            runs=run_specs,
            out_html=out_html,
            title=args.title or "",
        )
    except Exception as e:
        log.error("compare failed: %s", e)
        if getattr(args, "verbose", False):
            import traceback; traceback.print_exc()
        return 3

    print(f"\nComparison report → {out_html}")
    return 0



def _aggregate(args) -> int:
    """aggregate subcommand: merge multiple run directories, optionally pull
    Prometheus for the shared window, then run the standard report pipeline."""

    from .aggregator import aggregate_run_dirs
    from .prometheus_source import parse_time_arg

    # ── 1. Resolve run directories ─────────────────────────────────────────
    run_dirs: list[Path] = []
    for d in args.run_dirs:
        p = Path(d).expanduser().resolve()
        if not p.exists():
            log.error("aggregate: --run-dirs: directory not found: %s", p)
            return 2
        run_dirs.append(p)

    if len(run_dirs) < 2:
        log.error("aggregate requires at least two --run-dirs")
        return 2

    # ── 2. Parse time window ───────────────────────────────────────────────
    now   = datetime.now(tz=timezone.utc).timestamp()
    t_start = parse_time_arg(args.start, now=now) if args.start else 0.0
    t_end   = parse_time_arg(args.end,   now=now) if args.end   else 0.0

    if t_start > 0 and t_end > 0:
        dur_min = (t_end - t_start) / 60
        from datetime import datetime as _dt, timezone as _tz
        t0_str = _dt.fromtimestamp(t_start, tz=_tz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        t1_str = _dt.fromtimestamp(t_end,   tz=_tz.utc).strftime("%H:%M:%S UTC")
        log.info("Time window: %s → %s (%.1f min)", t0_str, t1_str, dur_min)

    # ── 3. Aggregate raw directories ───────────────────────────────────────
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_label = args.run_label or f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    merged_run = aggregate_run_dirs(
        run_dirs=run_dirs,
        output_dir=output_dir,
        t_start=t_start,
        t_end=t_end,
        run_label=run_label,
    )
    merged_raw = merged_run / "raw"
    log.info("Merged run directory: %s", merged_run)

    # ── 4. Optional: enrich from Prometheus ───────────────────────────────
    prom_url = getattr(args, "prometheus", "") or ""
    if prom_url:
        if not t_start or not t_end:
            log.error("--prometheus requires --start and --end when used with aggregate")
            return 2
        try:
            from .prometheus_source import (
                fetch_from_prometheus, merge_prometheus_into_local,
                parse_labels_arg,
            )
        except Exception as e:
            log.error("Failed to import prometheus_source: %s", e)
            return 2

        prom_kwargs = dict(
            start=args.start, end=args.end,
            step_s=int(args.prom_step),
            instance=args.prom_instance, job=args.prom_job,
            extra_labels=parse_labels_arg(args.prom_labels),
            nvme_device=args.nvme_device,
            label=run_label,
        )
        log.info("Enriching merged run with Prometheus: %s", prom_url)
        try:
            manifest = merge_prometheus_into_local(
                prom_url=prom_url,
                local_raw_dir=merged_raw,
                prefer=args.prefer,
                **prom_kwargs,
            )
            log.info("Prometheus merge: kept_local=%s, from_prom=%s, skipped=%s",
                     manifest["kept_local"],
                     manifest["copied_from_prom"],
                     manifest["skipped_empty_prom"])
        except Exception as e:
            log.warning("Prometheus enrichment failed (continuing without): %s", e)

    # ── 5. setup_details override ─────────────────────────────────────────
    if getattr(args, "setup_details", ""):
        _copy_setup_details(args, merged_raw)

    # ── 6. Reports (same logic as _analyze) ───────────────────────────────
    _combined       = getattr(args, "combined_report",    False)
    _do_static      = getattr(args, "amoprof_report",     False) or _combined
    _do_interactive = getattr(args, "interactive_report", False) or _combined
    _theme          = getattr(args, "report_theme", "dark")
    _static_path:      "Path | None" = None
    _interactive_path: "Path | None" = None
    report_dir = merged_run

    if _do_static:
        report_path = report_dir / "amoprof_report.html"
        rc = _run_amoprof(merged_raw, report_path,
                          verbose=args.verbose,
                          extra_args=args.amoprof_extra_arg or [],
                          sglang_page_size=getattr(args, "sglang_page_size", 0))
        if rc == 0:
            log.info("Wrote static report: %s", report_path)
            if _theme != "off":
                try:
                    from .report.enhancer import enhance_report
                    enhance_report(report_path, raw_dir=merged_raw, theme=_theme)
                except Exception as e:
                    log.warning("Enhancer failed: %s", e)
            _static_path = report_path
        else:
            log.warning("Static report generation returned rc=%s", rc)

    if _do_interactive:
        try:
            from .report.interactive import build_report as _build_int
            int_path = report_dir / "amoprof_interactive.html"
            _build_int(merged_raw, int_path, run_label=run_label)
            log.info("Wrote interactive report: %s", int_path)
            _interactive_path = int_path
        except Exception as e:
            log.warning("Interactive report failed: %s", e)

    if _combined and _static_path and _interactive_path:
        try:
            from .report.combined import build_combined_report
            combined_path = report_dir / "amoprof_combined.html"
            build_combined_report(
                raw_dir=merged_raw,
                out_html=combined_path,
                static_html_path=_static_path,
                interactive_html_path=_interactive_path,
                run_label=run_label,
                theme=_theme,
            )
            log.info("Wrote combined report: %s", combined_path)
        except Exception as e:
            log.warning("Combined report failed: %s", e)
    elif _combined:
        log.warning("Combined report skipped — static or interactive failed")

    print(f"\nAggregate complete → {merged_run}")
    if _do_static and _static_path:
        print(f"  Static:      {_static_path}")
    if _do_interactive and _interactive_path:
        print(f"  Interactive: {_interactive_path}")
    if _combined:
        print(f"  Combined:    {report_dir / 'amoprof_combined.html'}")
    return 0
    """analyze subcommand dispatcher — supports three modes:

      1. Prom-only:   --prometheus URL  (creates a fresh prom_run_* dir)
      2. Local-only:  --run-dir DIR     (existing behaviour)
      3. Merge:       both flags        (fill local gaps from Prometheus)
    """
    prom_url   = getattr(args, "prometheus", None)
    run_dir_arg = getattr(args, "run_dir", None)

    # ── 0. --list-targets short-circuit ─────────────────────────────────────
    if getattr(args, "list_targets", False):
        if not prom_url:
            log.error("--list-targets requires --prometheus URL")
            return 2
        try:
            from .prometheus_source import discover_targets
        except Exception as e:
            log.error("failed to import prometheus_source: %s", e)
            return 2
        hostname = (args.prom_instance or "").split(":")[0]
        targets = discover_targets(prom_url, hostname=hostname)
        if not targets:
            log.warning("No active targets returned by %s/api/v1/targets "
                        "(or hostname filter %r excluded all). Either the "
                        "server is unreachable or none of its scrape jobs "
                        "are up.", prom_url, hostname)
            return 1
        print(f"Active scrape targets on {prom_url}:")
        print(f"  {'job':<22} {'instance(s)'}")
        print(f"  {'-'*22} {'-'*44}")
        for job, instances in sorted(targets.items()):
            for i, inst in enumerate(instances):
                tag = job if i == 0 else ""
                print(f"  {tag:<22} {inst}")
        print()
        print("Use any of these with:")
        print("  amoprof analyze --prometheus", prom_url, "\\")
        print("    --prom-job <job> --prom-instance <instance>")
        return 0

    # ── 1. Argument validation ──────────────────────────────────────────────
    if not prom_url and not run_dir_arg:
        log.error("analyze requires either --run-dir or --prometheus "
                  "(or both for merge mode). Use --help for options.")
        return 2

    # ── 2. Determine the working run_dir and report_dir ─────────────────────
    # run_dir  = where raw data lives (source for the report builder)
    # report_dir = where HTML report files are written
    #
    # When --run-dir + --output-dir are both given:
    #   raw data stays in --run-dir; reports go to --output-dir.
    # When only --run-dir is given:
    #   reports go into run-dir (original behaviour).
    # When only --output-dir is given (Prometheus-only mode):
    #   a new prom_run_* dir is created inside --output-dir for everything.
    if run_dir_arg:
        run_dir = Path(run_dir_arg).expanduser().resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
        if args.output_dir:
            report_dir = Path(args.output_dir).expanduser().resolve()
            report_dir.mkdir(parents=True, exist_ok=True)
            log.info("Reports will be written to --output-dir: %s", report_dir)
        else:
            report_dir = run_dir   # original behaviour
    else:
        # Prom-only mode: create a fresh prom_run_* dir
        base = Path(args.output_dir or ".").expanduser().resolve()
        run_dir = base / f"prom_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_dir = run_dir
        log.info("Prometheus-only mode → created run dir: %s", run_dir)

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # ── 3. Prometheus fetch (if requested) ──────────────────────────────────
    if prom_url:
        try:
            from .prometheus_source import (
                fetch_from_prometheus, merge_prometheus_into_local,
                parse_labels_arg,
            )
        except Exception as e:
            log.error("failed to import prometheus_source: %s", e)
            return 2

        prom_kwargs = dict(
            start=args.start, end=args.end,
            step_s=int(args.prom_step),
            instance=args.prom_instance, job=args.prom_job,
            extra_labels=parse_labels_arg(args.prom_labels),
            nvme_device=args.nvme_device,
            label=run_dir.name,
        )

        if run_dir_arg:
            # MERGE mode — keep local files, fill gaps from Prometheus.
            log.info("Merge mode: local=%s, prometheus=%s, prefer=%s",
                     run_dir, prom_url, args.prefer)
            try:
                manifest = merge_prometheus_into_local(
                    prom_url=prom_url,
                    local_raw_dir=raw_dir,
                    prefer=args.prefer,
                    **prom_kwargs,
                )
                log.info("Merge result: kept_local=%s, "
                         "copied_from_prom=%s, prom_had_no_data=%s",
                         manifest["kept_local"],
                         manifest["copied_from_prom"],
                         manifest["skipped_empty_prom"])
            except Exception as e:
                log.error("Prometheus merge failed: %s", e)
                return 3
        else:
            # PROM-ONLY mode
            try:
                result = fetch_from_prometheus(
                    prom_url=prom_url, output_dir=raw_dir, **prom_kwargs)
                log.info("Wrote %d Prometheus files: %s",
                         len(result["new_files"]),
                         ", ".join(result["new_files"]))
            except Exception as e:
                log.error("Prometheus fetch failed: %s", e)
                return 3

    # ── 3b. Rebuild canonical CSVs from preserved JSONLs ────────────────────
    # Ensures reports reflect any fixes in the writer logic even when re-running
    # analyze on a run dir collected with an older amoprof version.
    rebuilt = _rebuild_canonical_csvs(run_dir)
    if rebuilt:
        log.info("Rebuilt canonical CSVs from JSONLs: %s", ", ".join(rebuilt))

    # ── 3c. Refresh L3 NVMe device capacity + HiCache df stats ─────────────
    # Re-snapshot df + /sys/block size from the analysis host. No-op if the
    # mount/device aren't reachable (cross-host analyze).
    if _refresh_smart_capacity(run_dir):
        log.info("Refreshed L3 HiCache capacity (df + /sys/block) in smart_summary.json")

    # ── 4. Operation-aligned CSV analysis (existing behaviour) ──────────────
    try:
        _run_analysis(run_dir, verbose=args.verbose)
    except Exception as e:
        log.warning("operation-aligned analysis skipped: %s", e)

    # ── 4b. Raw-dir audit — tell the user up-front which charts will be empty
    try:
        _print_audit(_audit_raw_dir(raw_dir))
    except Exception as e:
        log.debug("raw-dir audit failed: %s", e)

    # ── Resolve effective report flags ──────────────────────────────────────
    # --combined-report implies both --amoprof-report and --interactive-report
    _combined = getattr(args, "combined_report", False)
    _do_static      = getattr(args, "amoprof_report",    False) or _combined
    _do_interactive = getattr(args, "interactive_report", False) or _combined

    _static_path:      "Path | None" = None
    _interactive_path: "Path | None" = None
    _theme = getattr(args, "report_theme", "dark")

    # ── 5. Static amoprof HTML report ───────────────────────────────────────
    if _do_static:
        _copy_setup_details(args, raw_dir)
        report_path = report_dir / "amoprof_report.html"
        rc = _run_amoprof(raw_dir, report_path,
                          verbose=args.verbose,
                          extra_args=args.amoprof_extra_arg or [],
                          sglang_page_size=getattr(args, "sglang_page_size", 0))
        if rc == 0:
            log.info("Wrote amoprof report: %s", report_path)
            if _theme != "off":
                try:
                    from .report.enhancer import enhance_report
                    enhance_report(report_path, raw_dir=raw_dir, theme=_theme)
                    log.info("Enhanced report (%s theme): %s", _theme, report_path)
                except Exception as e:
                    log.warning("report enhancer failed: %s", e)
            _static_path = report_path
        else:
            log.warning("amoprof report generation returned %s", rc)

    # ── 6. Interactive Plotly report ────────────────────────────────────────
    if _do_interactive:
        try:
            _copy_bench_summary(args, raw_dir)
            _copy_setup_details(args, raw_dir)
            from .report.interactive import build_report as _build_interactive
            int_path = report_dir / "amoprof_interactive.html"
            _build_interactive(raw_dir, int_path, run_label=run_dir.name)
            log.info("Wrote interactive report: %s", int_path)
            _interactive_path = int_path
        except Exception as e:
            log.warning("interactive report failed: %s", e)

    # ── 7. Combined tabbed report ────────────────────────────────────────────
    if _combined and _static_path and _interactive_path:
        try:
            from .report.combined import build_combined_report
            combined_path = report_dir / "amoprof_combined.html"
            build_combined_report(
                raw_dir=raw_dir,
                out_html=combined_path,
                static_html_path=_static_path,
                interactive_html_path=_interactive_path,
                run_label=run_dir.name,
                theme=_theme,
            )
            log.info("Wrote combined report: %s", combined_path)
        except Exception as e:
            log.warning("combined report failed: %s", e)
    elif _combined:
        log.warning("combined report skipped — static or interactive generation failed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
