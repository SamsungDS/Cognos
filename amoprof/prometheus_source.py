"""
amoprof/prometheus_source.py — Fetch timeseries data from a Prometheus
server via /api/v1/query_range and emit the canonical amoprof CSV/JSON
files into a raw/ directory.

This is the analyze-side counterpart to the live SGLangMetricsSampler
collector. It lets users build a report from historical Prometheus
data instead of (or in addition to) a local AMOprof collect run.

Three modes are supported:

  1. Prometheus-only — fetch everything from a Prom server.
     amoprof analyze --prometheus http://host:9090 --start -1h --end now

  2. Local-only — re-analyze a previous collect run (existing behaviour).
     amoprof analyze --run-dir results/metrics_run_20260514

  3. Merge — combine both. Files present in local raw/ are kept;
     anything missing is filled in from Prometheus. Useful when local
     collection captured NVMe / blktrace / AMDuProf but not SGLang
     (e.g. because the SGLang server was on a remote node and the
     central Prometheus server is the only path to it).
     amoprof analyze --run-dir results/foo --prometheus http://host:9090

The actual Prometheus fetch happens via the bundled amoprof report's
collect_from_prometheus_api(), which we import dynamically because
that module also pulls matplotlib at module-import time and we don't
want that cost for callers who never use Prometheus.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("amoprof.prom_source")


# ─── Time parsing ────────────────────────────────────────────────────────────
def parse_time_arg(s: str, now: float | None = None) -> float:
    """Parse a time argument into a Unix timestamp.

    Accepts:
      - Empty string         → 0 (caller decides default)
      - Literal 'now'        → current time
      - Unix timestamp       → '1715623200' or '1715623200.5'
      - ISO datetime         → '2026-04-25T10:00:00' / '2026-04-25 10:00:00'
                               / '2026-04-25' (treated as UTC)
      - Relative offset      → '-1h', '-30m', '-2d' (subtract from now)

    Returns 0 for unparseable / empty strings so the caller can supply
    a fallback. Raises ValueError only for clearly malformed offsets.
    """
    if not s:
        return 0.0
    s = s.strip()
    if s.lower() in ("now", ""):
        return now if now is not None else time.time()
    if now is None:
        now = time.time()
    # Unix timestamp (10+ digits, optional decimal)
    if re.match(r"^\d{10,}(\.\d+)?$", s):
        return float(s)
    # Relative offset: -<n>{h,m,d,s}
    m = re.match(r"^-(\d+)([hmds])$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return now - n * {"h": 3600, "m": 60, "d": 86400, "s": 1}[unit]
    # ISO datetime — treat naive datetimes as UTC.  Accept fractional
    # seconds and trailing Z because Prometheus query_range examples often
    # use RFC3339 timestamps such as 2026-05-21T21:24:28.081653Z.
    iso = s.strip()
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass
    return 0.0


def parse_labels_arg(label_args: list[str] | None) -> dict[str, str]:
    """Parse ['key1=val1', 'key2=val2'] into a dict."""
    out: dict[str, str] = {}
    for item in (label_args or []):
        item = item.strip().strip('"').strip("'")
        if "=" in item:
            k, _, v = item.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ─── Bundled-amoprof loader ─────────────────────────────────────────────────
# The bundled report at amoprof/report/amoprof.py defines the actual
# Prometheus query helpers. Loading it as a sibling module would shadow our
# own `amoprof` package, so we load it under a distinct name via importlib.
_REPORT_MODULE = None


def _load_bundled_report():
    global _REPORT_MODULE
    if _REPORT_MODULE is not None:
        return _REPORT_MODULE
    import importlib.util as _ilu
    report_py = Path(__file__).resolve().parent / "report" / "amoprof.py"
    if not report_py.exists():
        raise RuntimeError(f"bundled amoprof report not found at {report_py}")
    # Use a name that can't collide with our package
    spec = _ilu.spec_from_file_location("amoprof_bundled_report", report_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to build importlib spec for {report_py}")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _REPORT_MODULE = mod
    return mod


# ─── Target discovery ───────────────────────────────────────────────────────
def discover_targets(prom_base_url: str, hostname: str = "") -> dict[str, list[str]]:
    """Return {job: [instance, ...]} from /api/v1/targets.

    Used by `amoprof analyze --prometheus URL --list-targets`.
    """
    mod = _load_bundled_report()
    return mod._prom_discover_targets(prom_base_url, hostname)


# ─── Main fetch ──────────────────────────────────────────────────────────────
# Files the bundled collect_from_prometheus_api can produce.
CANONICAL_FILES = (
    "sglang_timeseries.csv",
    "sglang_summary.json",
    "sglang_percentiles_timeseries.json",
    "gpu_timeseries.csv",
    "gpu_summary.json",
    "nvme_driver_timeseries.csv",
    "vmstat_timeseries.csv",
    "power_timeseries.csv",
)

# When a user supplies --prometheus with an explicit --start/--end/--prom-instance,
# these files should normally reflect the Prometheus window, not stale local
# collection files from a previous run.  Keep local-only low-level data such as
# blktrace/biosnoop, but refresh Prometheus-owned timeseries even if
# --prefer remains the historical default of 'local'.
PROM_WINDOW_FILES = {
    "sglang_timeseries.csv",
    "sglang_summary.json",
    "sglang_percentiles_timeseries.json",
    "gpu_timeseries.csv",
    "gpu_summary.json",
    "nvme_driver_timeseries.csv",
    "vmstat_timeseries.csv",
    "power_timeseries.csv",
}


def fetch_from_prometheus(
    prom_url: str,
    output_dir: Path,
    start: str = "",
    end: str = "",
    step_s: int = 15,
    instance: str = "",
    job: str = "",
    extra_labels: dict[str, str] | None = None,
    label: str = "prom",
    nvme_device: str = "",
) -> dict[str, Any]:
    """Pull timeseries from a Prometheus server and write canonical CSVs.

    Args:
      prom_url     : Prometheus base URL (e.g. http://host:9090)
      output_dir   : Destination raw/ directory. Will be created.
      start, end   : Time range strings (see parse_time_arg).
                     Empty → default to last 1 hour.
      step_s       : query_range resolution (seconds).
      instance     : Filter to {instance="..."} on every PromQL query.
      job          : Filter to {job="..."} on every PromQL query.
      extra_labels : Additional {key:value} label filters (ANDed).
      label        : Run label for output filenames.
      nvme_device  : NVMe device name hint (e.g. "nvme0n1") to pin
                     node_disk_* metrics to the right device.

    Returns a dict describing what was written, suitable for logging.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load the bundled amoprof report module — it owns the actual
    # collect_from_prometheus_api implementation.
    try:
        mod = _load_bundled_report()
        collect_from_prometheus_api = mod.collect_from_prometheus_api
    except Exception as e:
        raise RuntimeError(
            "Unable to load the bundled amoprof report module: "
            f"{e!r}. Ensure amoprof/report/amoprof.py is present."
        ) from e

    now_ts = time.time()
    t_end   = parse_time_arg(end,   now_ts) or now_ts
    t_start = parse_time_arg(start, now_ts) or (t_end - 3600)

    if t_start >= t_end:
        raise ValueError(
            f"Empty time range: start={t_start} >= end={t_end}. "
            "Check --start / --end arguments."
        )

    window_s = t_end - t_start
    log.info("Prometheus fetch: %s  window=%.0fs  step=%ds  instance=%r  job=%r",
             prom_url, window_s, step_s, instance or "(any)", job or "(any)")

    labels = dict(extra_labels or {})
    if nvme_device:
        labels.setdefault("nvme_device", nvme_device)

    # Snapshot existing files so we can tell what got produced.
    before = {f.name for f in output_dir.iterdir() if f.is_file()}

    data = collect_from_prometheus_api(
        prom_base_url=prom_url,
        start_time=t_start,
        end_time=t_end,
        step_s=step_s,
        label=label,
        output_dir=output_dir,
        instance=instance,
        job=job,
        extra_labels=labels,
    )

    after = {f.name for f in output_dir.iterdir() if f.is_file()}
    new_files = sorted(after - before)
    overwritten = sorted(after & before)

    # Fetch percentile summary + per-tick percentile timeseries from
    # histogram buckets. These give true per-request P50/P90/P99 (matching
    # what bench_serving prints) — distinct from the per-tick gauge means
    # already in sglang_summary.json.
    pct_summary: dict = {}
    pct_ts: dict = {}
    try:
        from .percentiles import (
            fetch_percentile_summary, fetch_percentile_timeseries,
        )
        pct_summary = fetch_percentile_summary(
            prom_url, t_start, t_end,
            instance=instance, job=job, extra_labels=labels)
        if pct_summary:
            # Merge percentile fields into sglang_summary.json if present
            sg_path = output_dir / "sglang_summary.json"
            if sg_path.exists():
                try:
                    sg = json.loads(sg_path.read_text())
                except Exception:
                    sg = {}
            else:
                sg = {}
            sg.update(pct_summary)
            sg["cache_hit_calc_method"] = sg.get(
                "cache_hit_calc_method", "histogram_quantile_window")
            sg_path.write_text(json.dumps(sg, indent=2, default=str))
            log.info("Merged %d percentile fields into sglang_summary.json",
                     len(pct_summary))

        pct_ts = fetch_percentile_timeseries(
            prom_url, t_start, t_end, step_s=step_s,
            instance=instance, job=job, extra_labels=labels)
        if pct_ts:
            pts_path = output_dir / "sglang_percentiles_timeseries.json"
            # Filter out None values for cleaner JSON
            def _clean(d):
                if isinstance(d, dict):
                    return {k: _clean(v) for k, v in d.items()}
                if isinstance(d, list):
                    return [None if v is None else v for v in d]
                return d
            pts_path.write_text(json.dumps(_clean(pct_ts), indent=2, default=str))
            log.info("Wrote percentile timeseries (%d metrics) → %s",
                     len(pct_ts), pts_path.name)
    except Exception as e:
        log.warning("percentile fetch failed: %s", e)

    return {
        "prom_url":    prom_url,
        "start":       t_start,
        "end":         t_end,
        "step_s":      step_s,
        "instance":    instance,
        "job":         job,
        "labels":      labels,
        "new_files":   sorted(set(new_files) | {f.name for f in output_dir.iterdir() if f.is_file()} - before),
        "overwritten": overwritten,
        "percentile_fields": list(pct_summary.keys()),
        "percentile_timeseries_metrics": list(pct_ts.keys()),
        "data_keys":   sorted(data.keys()) if isinstance(data, dict) else [],
    }


# ─── Merge: fill gaps in local raw/ with Prometheus data ────────────────────
def merge_prometheus_into_local(
    prom_url: str,
    local_raw_dir: Path,
    prefer: str = "local",
    **fetch_kwargs: Any,
) -> dict[str, Any]:
    """Combine a local raw/ dir with a Prometheus fetch.

    Files present locally are kept (when prefer='local'), gaps filled
    from Prometheus. If prefer='prometheus', the Prometheus values win
    for any file present in both.

    Args:
      prom_url      : Prometheus server URL.
      local_raw_dir : Existing raw/ directory with locally-collected CSVs.
      prefer        : 'local' (default) or 'prometheus' — conflict policy.
      **fetch_kwargs: forwarded to fetch_from_prometheus().

    Returns a manifest describing what was kept, fetched, and skipped.
    """
    local_raw_dir = Path(local_raw_dir)
    local_raw_dir.mkdir(parents=True, exist_ok=True)

    # 1. Snapshot which canonical files already exist locally.
    locally_present = {
        name for name in CANONICAL_FILES
        if (local_raw_dir / name).exists()
        and (local_raw_dir / name).stat().st_size > 0
    }

    # 2. Fetch Prometheus into a temp sibling dir, then selectively copy.
    prom_stage = local_raw_dir / ".prom_stage"
    if prom_stage.exists():
        shutil.rmtree(prom_stage)
    prom_stage.mkdir(parents=True, exist_ok=True)

    try:
        fetch_result = fetch_from_prometheus(prom_url=prom_url,
                                              output_dir=prom_stage,
                                              **fetch_kwargs)

        copied: list[str] = []
        kept_local: list[str] = []
        skipped_empty_prom: list[str] = []

        for name in CANONICAL_FILES:
            src = prom_stage / name
            dst = local_raw_dir / name
            if not src.exists() or src.stat().st_size == 0:
                # Prometheus had no data for this file.
                if name in locally_present:
                    kept_local.append(name)
                else:
                    skipped_empty_prom.append(name)
                continue
            # Prometheus-owned files should be refreshed from the requested
            # Prometheus window even when --prefer is left at its default
            # ('local'). Otherwise the report can silently use stale local
            # sglang_summary/sglang_timeseries files and miss
            # sglang_cache_hit_rate samples, exactly the cache-hit mismatch
            # this path is intended to debug.
            force_prom = name in PROM_WINDOW_FILES
            if name in locally_present and prefer == "local" and not force_prom:
                kept_local.append(name)
                continue
            # Either no local copy, prefer=='prometheus', or this file belongs
            # to the explicit Prometheus time window — overwrite.
            shutil.copyfile(src, dst)
            copied.append(name)

        return {
            "prefer":            prefer,
            "locally_present":   sorted(locally_present),
            "copied_from_prom":  copied,
            "kept_local":        kept_local,
            "skipped_empty_prom": skipped_empty_prom,
            "fetch":              fetch_result,
        }
    finally:
        if prom_stage.exists():
            shutil.rmtree(prom_stage)
