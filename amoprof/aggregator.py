"""
amoprof/aggregator.py — Aggregate multiple local run directories into a
single merged raw/ directory for a given Prometheus time window.

Merging strategy per file type
───────────────────────────────
Time-series CSVs (sglang_timeseries, gpu_timeseries, nvme_driver_timeseries,
vmstat_timeseries, power_timeseries, amduprof_pcm_timeseries):
  • Row-union:  rows from all run dirs are concatenated and re-sorted by
    time_sec.  Rows whose time_sec falls outside [start, end] are dropped.
  • Duplicate timestamps: the row from the run dir that has more non-zero
    columns wins (prefer denser data).

Histogram/distribution CSVs (request_size_distribution,
interarrival_distribution, temporal_read_write_trim_pattern,
bandwidth_per_stream, hot_regions_overall):
  • Column-sum: numeric cells are summed across all run dirs.  String keys
    (bucket labels, pid/comm) are kept from the first file that has them.

Summary JSONs (sglang_summary, gpu_summary, smart_summary, summary):
  • Best-of merge: numeric values are averaged (for rates/latencies) or
    summed (for totals).  The merge heuristic is keyed on suffix:
      *_total / *_count / *_ios → sum
      everything else → mean (or max for peak_* / max_* keys)

setup_details.json:
  • First non-empty file wins.

blktrace_events.csv:
  • Row-union (sorted by ts).

Other files (*.txt, *.raw):
  • First non-empty file wins.
"""
from __future__ import annotations

import csv
import json
import logging
import math
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any

log = logging.getLogger("amoprof.aggregator")

# ─── CSV helpers ─────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        with open(path, encoding="utf-8", newline="", errors="replace") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.debug("_read_csv %s: %s", path, e)
        return []


def _write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    # Ensure all keys from all rows are present
    all_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _is_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


# ─── Time-series union ───────────────────────────────────────────────────────

def _merge_timeseries(
    all_rows: list[list[dict]],
    t_start: float,
    t_end: float,
    time_col: str = "time_sec",
    t0_epochs: list[float] | None = None,
) -> list[dict]:
    """
    Concatenate rows from multiple sources, filter to [t_start, t_end],
    sort by time_sec, and deduplicate by keeping the row with the most
    non-zero numeric columns per timestamp.

    When t0_epochs is provided (one Unix epoch per source), each source's
    elapsed time_sec is converted to an absolute timestamp before merging.
    This prevents rows from different runs being silently dropped when they
    share the same relative timestamps (e.g. both start at t=0, t=30, ...).
    After merging, timestamps are re-normalised relative to the earliest row.
    """
    combined: dict[str, dict] = {}  # ts_str → best row

    def _nonzero_count(row: dict) -> int:
        return sum(1 for v in row.values() if _is_numeric(str(v)) and _safe_float(str(v)) != 0)

    for src_idx, source_rows in enumerate(all_rows):
        # Offset: if t0_epochs provided, convert relative time_sec → absolute epoch
        t0_off = (t0_epochs[src_idx]
                  if t0_epochs and src_idx < len(t0_epochs)
                  and t0_epochs[src_idx] > 1_000_000_000
                  else 0.0)
        for row in source_rows:
            ts = _safe_float(row.get(time_col, ""))
            abs_ts = ts + t0_off if t0_off > 0 else ts

            # Filter to window (using absolute or relative ts consistently)
            if t_start > 0 and abs_ts < t_start and ts < t_start:
                continue
            if t_end > 0 and abs_ts > t_end and ts > t_end:
                continue

            # Key on absolute ts so different-origin rows don't collide
            key = f"{abs_ts:.3f}"
            # Keep the row, storing absolute ts for later re-normalisation
            candidate = dict(row)
            if t0_off > 0:
                candidate[time_col] = str(abs_ts)
            if key not in combined or _nonzero_count(candidate) > _nonzero_count(combined[key]):
                combined[key] = candidate

    if not combined:
        return []

    result = sorted(combined.values(),
                    key=lambda r: _safe_float(r.get(time_col, "0")))

    # Re-normalise: subtract the earliest timestamp so elapsed starts at 0
    first_ts = _safe_float(result[0].get(time_col, "0"))
    if first_ts > 1_000_000_000:
        # Absolute epochs — normalise to elapsed
        for row in result:
            row[time_col] = str(round(_safe_float(row.get(time_col, "0")) - first_ts, 3))
    return result


def _normalize_time_sec(
    rows: list[dict],
    t0_epoch: float,
    time_col: str = "time_sec",
) -> list[dict]:
    """
    Ensure time_sec is elapsed seconds since t0_epoch.
    If values look like raw Unix timestamps (> 1e9), subtract t0_epoch.
    Also clamps any negative elapsed values to 0.
    """
    if not rows:
        return rows
    first = _safe_float(rows[0].get(time_col, "0"))
    if first > 1_000_000_000 and t0_epoch > 0:
        for row in rows:
            elapsed = _safe_float(row.get(time_col, "0")) - t0_epoch
            row[time_col] = str(round(max(elapsed, 0.0), 3))
    return rows


# ─── Histogram / distribution sum ───────────────────────────────────────────

def _merge_histograms(
    all_rows: list[list[dict]],
    key_col: str,
) -> list[dict]:
    """Sum numeric columns across all sources, keyed on key_col."""
    acc: dict[str, dict] = {}
    key_order: list[str] = []

    for source_rows in all_rows:
        for row in source_rows:
            k = str(row.get(key_col, ""))
            if k not in acc:
                acc[k] = {c: v for c, v in row.items()}
                key_order.append(k)
            else:
                for col, val in row.items():
                    if col == key_col:
                        continue
                    if _is_numeric(str(val)) and _is_numeric(str(acc[k].get(col, "0"))):
                        acc[k][col] = str(
                            round(_safe_float(acc[k][col]) + _safe_float(val), 6))
    return [acc[k] for k in key_order if k in acc]


# ─── Summary JSON merge ──────────────────────────────────────────────────────

def _merge_summaries(summaries: list[dict]) -> dict:
    """
    Best-of merge for scalar summary JSONs.

    Heuristic per key:
      key ends with _total / _count / _ios / _bytes / _gb → sum
      key starts with peak_ / max_ / contains _max_ → max
      everything else (rates, latencies, percentages) → mean of non-zero values
    """
    if not summaries:
        return {}

    all_keys: list[str] = []
    seen: set[str] = set()
    for s in summaries:
        for k in s:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    result: dict = {}
    for key in all_keys:
        vals = [s[key] for s in summaries if key in s and s[key] is not None]
        if not vals:
            continue

        # Non-numeric: keep first non-empty non-None
        numeric_vals = [_safe_float(v) for v in vals
                        if v is not None and _is_numeric(str(v))]
        if not numeric_vals:
            # Keep first non-empty, non-None value
            non_null = [v for v in vals if v is not None and str(v) not in ("", "null")]
            result[key] = non_null[0] if non_null else None
            continue

        kl = key.lower()
        if any(kl.endswith(s) for s in ("_total", "_count", "_ios",
                                          "_bytes", "_gb", "_tb",
                                          "_reads", "_writes", "_trims")):
            result[key] = round(sum(numeric_vals), 4)
        elif kl.startswith("peak_") or kl.startswith("max_") or "_max_" in kl:
            result[key] = round(max(numeric_vals), 4)
        else:
            nz = [v for v in numeric_vals if v != 0]
            result[key] = round(sum(nz) / len(nz), 4) if nz else 0

    return result


# ─── Main aggregation function ───────────────────────────────────────────────

def aggregate_run_dirs(
    run_dirs: list[Path],
    output_dir: Path,
    t_start: float = 0.0,
    t_end: float = 0.0,
    run_label: str = "",
) -> Path:
    """Merge multiple run directories into a single synthetic raw/ directory.

    Args:
        run_dirs:   List of run directories (each must contain a raw/ sub-dir).
        output_dir: Parent directory for the output merged_run_<ts>/ directory.
        t_start:    Prometheus window start as Unix epoch (0 = no filter).
        t_end:      Prometheus window end as Unix epoch (0 = no filter).
        run_label:  Optional label for the merged run.

    Returns:
        Path to the newly created merged run directory.
    """
    ts_tag   = datetime.now().strftime("%Y%m%d_%H%M%S")
    label    = run_label or f"merged_{ts_tag}"
    out_run  = output_dir / label
    out_raw  = out_run / "raw"
    out_raw.mkdir(parents=True, exist_ok=True)

    t0_epoch = t_start if t_start > 1_000_000_000 else 0.0
    n        = len(run_dirs)
    log.info("Aggregating %d run directories → %s", n, out_run)
    for i, rd in enumerate(run_dirs):
        log.info("  [%d/%d] %s", i + 1, n, rd)

    raw_dirs = []
    for rd in run_dirs:
        raw_candidate = rd / "raw"
        raw_dirs.append(raw_candidate if raw_candidate.is_dir() else rd)

    # Extract per-source t0_epoch values so _merge_timeseries can convert
    # relative time_sec → absolute before deduplication.  This prevents rows
    # from two runs that both start at t=0 from colliding and being dropped.
    #
    # summary.json location depends on how the run was created:
    #   live collect:  run_dir/summary.json  (parent of raw_dir)
    #   analyze/prom:  raw_dir/summary.json
    # We check both, preferring the parent-level file.
    t0_epochs: list[float] = []
    for rd in raw_dirs:
        t0 = 0.0
        # Check parent directory first (live collect path)
        for candidate_dir in (rd.parent, rd):
            meta = _read_json(candidate_dir / "summary.json")
            # summary.json may be {"meta": {"t0_epoch": ...}} or flat {"t0_epoch": ...}
            t0_cand = _safe_float(meta.get("t0_epoch") or meta.get("start_time") or
                                   (meta.get("meta") or {}).get("t0_epoch") or 0)
            if t0_cand > 1_000_000_000:
                t0 = t0_cand
                break
        t0_epochs.append(t0)
        if t0 > 0:
            log.debug("Source %s: t0_epoch=%.0f", rd, t0)
        else:
            log.warning("Source %s: t0_epoch not found in summary.json — "
                        "timeseries rows from different runs may collide during merge. "
                        "Ensure summary.json exists in either %s or %s.",
                        rd, rd, rd.parent)

    # ── Time-series CSVs ─────────────────────────────────────────────────────
    TIMESERIES_FILES = [
        "sglang_timeseries.csv",
        "gpu_timeseries.csv",
        "nvme_driver_timeseries.csv",
        "nvme_driver_timeseries_extra.csv",
        "vmstat_timeseries.csv",
        "power_timeseries.csv",
        "amduprof_pcm_timeseries.csv",
        "pcm_timeseries.csv",
        "iostat_timeseries.csv",
        "blktrace_events.csv",
    ]
    for fname in TIMESERIES_FILES:
        all_rows = [_read_csv(rd / fname) for rd in raw_dirs]
        merged   = _merge_timeseries(all_rows, t_start, t_end, t0_epochs=t0_epochs)
        merged   = _normalize_time_sec(merged, t0_epoch)
        if merged:
            _write_csv(merged, out_raw / fname)
            log.info("  %-42s %6d rows (from %d sources)",
                     fname, len(merged),
                     sum(1 for r in all_rows if r))

    # ── Histogram / distribution CSVs ────────────────────────────────────────
    HISTOGRAM_FILES: dict[str, str] = {
        "request_size_distribution.csv": "bucket",
        "interarrival_distribution.csv": "bucket",
        "temporal_read_write_trim_pattern.csv": "window_s",
        "bandwidth_per_stream.csv": "pid",
        "hot_regions_overall.csv": "lba_gb_start",
    }
    for fname, key_col in HISTOGRAM_FILES.items():
        all_rows = [_read_csv(rd / fname) for rd in raw_dirs]
        merged   = _merge_histograms(all_rows, key_col)
        if merged:
            _write_csv(merged, out_raw / fname)
            log.info("  %-42s %6d rows (summed)", fname, len(merged))

    # ── Summary JSONs ─────────────────────────────────────────────────────────
    SUMMARY_FILES = [
        "sglang_summary.json",
        "gpu_summary.json",
        "smart_summary.json",
        "bpf_summary.json",
        "nvme_smart.json",
    ]
    for fname in SUMMARY_FILES:
        summaries = [_read_json(rd / fname) for rd in raw_dirs]
        summaries = [s for s in summaries if s]
        if summaries:
            merged_j = _merge_summaries(summaries)
            (out_raw / fname).write_text(
                json.dumps(merged_j, indent=2), encoding="utf-8")
            log.info("  %-42s merged (%d sources)", fname, len(summaries))

    # ── summary.json (the run-level metadata) ────────────────────────────────
    meta_list = [_read_json(rd / "summary.json") for rd in raw_dirs]
    meta_list = [m for m in meta_list if m]
    meta_merged = _merge_summaries(meta_list)
    # Override timing fields with the explicit window.
    # Also write t0_epoch at the top level (not just inside "meta") so that
    # analysis tools that read {"t0_epoch": ...} directly can find it.
    resolved_t0 = t0_epoch if t0_epoch > 1_000_000_000 else min(
        (t for t in t0_epochs if t > 1_000_000_000), default=0.0)
    if resolved_t0 > 0:
        meta_merged["t0_epoch"]   = resolved_t0
        meta_merged["start_time"] = resolved_t0
        meta_merged["prom_start"] = resolved_t0
    if t0_epoch > 1_000_000_000:
        meta_merged["t0_epoch"]   = t0_epoch
        meta_merged["start_time"] = t0_epoch
        meta_merged["prom_start"] = t0_epoch
    if t_end > 0:
        meta_merged["end_time"]   = t_end
        meta_merged["prom_end"]   = t_end
    if t_start > 0 and t_end > 0:
        meta_merged["duration_s"] = round(t_end - t_start, 1)
        meta_merged["run_duration_s"] = meta_merged["duration_s"]
    meta_merged["merged_from"] = [str(rd) for rd in run_dirs]
    meta_merged["merged_at"]   = datetime.now(tz=timezone.utc).isoformat()
    meta_merged["n_sources"]   = n
    (out_raw / "summary.json").write_text(
        json.dumps(meta_merged, indent=2), encoding="utf-8")
    log.info("  %-42s written", "summary.json")

    # ── setup_details.json — first non-empty wins ────────────────────────────
    for fname in ("setup_details.json", "setup.json"):
        for rd in raw_dirs:
            j = _read_json(rd / fname)
            if j:
                (out_raw / "setup_details.json").write_text(
                    json.dumps(j, indent=2), encoding="utf-8")
                log.info("  %-42s from %s", "setup_details.json", rd)
                break

    # ── AMDuProf raw files — first non-empty wins ────────────────────────────
    for fname in ("amduprof_pcm_raw.csv", "amduprof_pcm_raw.txt"):
        for rd in raw_dirs:
            src = rd / fname
            if src.exists() and src.stat().st_size > 0:
                shutil.copy2(src, out_raw / fname)
                log.info("  %-42s from %s", fname, rd)
                break

    # ── blktrace distribution files (already handled above as histograms) ────
    # copy biosnoop.csv (row-union, no time filter needed since it's event-based)
    biosnoop_rows: list[list[dict]] = []
    for rd in raw_dirs:
        src = rd / "biosnoop.csv"
        rows = _read_csv(src)
        if rows:
            biosnoop_rows.append(rows)
    if biosnoop_rows:
        combined_bio: list[dict] = []
        for r in biosnoop_rows:
            combined_bio.extend(r)
        combined_bio.sort(key=lambda row: _safe_float(row.get("ts", row.get("time", "0"))))
        _write_csv(combined_bio, out_raw / "biosnoop.csv")
        log.info("  %-42s %6d rows (union)", "biosnoop.csv", len(combined_bio))

    # ── sglang_percentiles_timeseries.json ───────────────────────────────────
    for fname in ("sglang_percentiles_timeseries.json",):
        # Each file is a list of {ts, p50, p90, p99} dicts — union and sort
        all_pct: list[dict] = []
        for rd in raw_dirs:
            src = rd / fname
            if src.exists():
                try:
                    data = json.loads(src.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        for item in data:
                            ts = _safe_float(item.get("ts", 0))
                            if (t_start == 0 or ts >= t_start) and \
                               (t_end   == 0 or ts <= t_end):
                                if t0_epoch > 0 and ts > 1_000_000_000:
                                    item = dict(item)
                                    item["ts"] = round(ts - t0_epoch, 3)
                                all_pct.append(item)
                except Exception:
                    pass
        if all_pct:
            all_pct.sort(key=lambda d: _safe_float(d.get("ts", 0)))
            (out_raw / fname).write_text(
                json.dumps(all_pct, indent=2), encoding="utf-8")
            log.info("  %-42s %6d points (union)", fname, len(all_pct))

    log.info("Aggregation complete: %s", out_raw)
    return out_run
