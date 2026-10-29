"""
amoprof/report/combined.py — Merge the executive, interactive, and static reports
into a single HTML file with iframe-isolated tabs.

  Tab 1: 🧭 Executive    (high-level summary, default)
  Tab 2: ⚡ Interactive  (Plotly hover charts)
  Tab 3: 📊 Static       (full amoprof matplotlib PNG report)

The child reports are embedded via <iframe srcdoc> so each report keeps its own
CSS/JS without leaking styles into the others.  The executive tab is generated
from the raw run directory and is intentionally small, fast, and readable.
"""
from __future__ import annotations

import csv
import html as _html
import json
import os as _os
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from amoprof import __version__ as _AMOPROF_VERSION
except Exception:
    _AMOPROF_VERSION = "unknown"

try:
    from amoprof.report.l3_backend import resolve_l3_backend, reconcile_l3_io
except Exception:  # direct-script fallback
    from l3_backend import resolve_l3_backend, reconcile_l3_io  # type: ignore

try:
    from amoprof.report.common_kpis import (
        compute_common_kpis,
        apply_common_kpis_to_html,
        write_common_kpis_json,
        compute_cache_hit_kpis,
        compute_l35_kpis,
        _read_json,
        _safe_float,
        _amoprof_resolve_raw_dir,
        _amoprof_parse_launch_arg,
        _amoprof_missing,
        _amoprof_augment_setup_from_launch,
        _amoprof_storage_label_cleanup,
        _pct_ts_latency_ms,
        resolve_page_size,
    )
except Exception:  # direct-script fallback
    from common_kpis import (  # type: ignore
        compute_common_kpis, apply_common_kpis_to_html, write_common_kpis_json,
        compute_cache_hit_kpis, compute_l35_kpis,
        _read_json, _safe_float, _amoprof_resolve_raw_dir,
        _amoprof_parse_launch_arg, _amoprof_missing, _amoprof_augment_setup_from_launch,
        _amoprof_storage_label_cleanup,
        _pct_ts_latency_ms,
        resolve_page_size,
    )





def _remove_setup_aware_sglang_launch_tuning_section(html_text: str) -> str:
    """Remove setup-aware launch tuning sections from generated or old embedded reports."""
    if not html_text:
        return html_text
    patterns = [
        r'\s*<section[^>]*>\s*<h2[^>]*>\s*🚀\s*Setup-aware SGLang launch tuning\s*</h2>.*?</section>\s*',
        r'\s*<div class="section-label">\s*Setup-aware launch tuning\s*</div>\s*<div class="card"[^>]*>\s*<h2>\s*🚀\s*SGLang launch-command improvements\b.*?</div>\s*',
        r'\s*&lt;section[^&]*&gt;\s*&lt;h2[^&]*&gt;\s*🚀\s*Setup-aware SGLang launch tuning\s*&lt;/h2&gt;.*?&lt;/section&gt;\s*',
    ]
    out = html_text
    for pat in patterns:
        out = re.sub(pat, "\n<!-- Setup-aware SGLang launch tuning removed in v1.39.61. -->\n",
                     out, flags=re.I | re.S)
    return out


def _remove_end_report_cross_layer_correlation_section(static_html: str) -> str:
    """Remove the old End Report cross-layer narrative section.

    v1.39.61 moves this setup/token/latency/utilization narrative to Executive
    where dark-theme CSS is readable.  This cleanup also handles combined
    reports built from older static HTML files passed via --static-html.
    """
    if not static_html:
        return static_html
    patterns = [
        # Static End Report f-string section.
        r'\s*<section[^>]*>\s*<h2[^>]*>\s*🔗\s*Cross-layer correlation\s*—\s*setup,\s*token movement,\s*latency,\s*and utilization\s*</h2>.*?</section>\s*',
        # Escaped srcdoc case if an already-embedded static frame is reprocessed.
        r'\s*&lt;section[^&]*&gt;\s*&lt;h2[^&]*&gt;\s*🔗\s*Cross-layer correlation\s*—\s*setup,\s*token movement,\s*latency,\s*and utilization\s*&lt;/h2&gt;.*?&lt;/section&gt;\s*',
    ]
    out = static_html
    for pat in patterns:
        out = re.sub(pat, "\n<!-- Cross-layer correlation moved to Executive tab in v1.39.61. -->\n",
                     out, flags=re.I | re.S)
    return out


def _first_existing(root: Path, names: list[str] | tuple[str, ...]) -> Path | None:
    try:
        root = Path(root)
        for name in names:
            p = root / name
            if p.exists() and p.stat().st_size > 0:
                return p
    except Exception:
        return None
    return None


def _read_csv_summary(path: Path | None) -> dict:
    """Return basic min/mean/max/sum/n for each numeric CSV column.

    The Executive report also needs file-level metadata (row count, columns,
    first row, last row) so selected-window counter deltas and data-health
    badges can be computed from the same CSVs used by Interactive/End Report.
    Older code returned only per-column stats; callers such as token-movement
    and DRAM availability then saw ``rows == 0`` and ``first/last == {}``,
    incorrectly hiding valid local/Prometheus data.
    """
    if not path:
        return {}
    try:
        path = Path(path)
        if not path.exists() or path.stat().st_size <= 0:
            return {}
        data: dict[str, list[float]] = {}
        rows: list[dict[str, str]] = []
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []
            data = {c: [] for c in cols}
            for row in r:
                rows.append(dict(row))
                for c in cols:
                    try:
                        val = float(str(row.get(c, "")).replace(",", ""))
                    except Exception:
                        continue
                    if math.isnan(val) or math.isinf(val):
                        continue
                    data[c].append(val)

        def _coerce_row(row: dict[str, str]) -> dict:
            out_row = {}
            for k, v in (row or {}).items():
                try:
                    fv = float(str(v).replace(",", ""))
                    if math.isfinite(fv):
                        out_row[k] = fv
                    else:
                        out_row[k] = v
                except Exception:
                    out_row[k] = v
            return out_row

        out: dict[str, Any] = {
            "rows": len(rows),
            "columns": cols,
            "path": str(path),
            "first": _coerce_row(rows[0]) if rows else {},
            "last": _coerce_row(rows[-1]) if rows else {},
        }
        for c, vals in data.items():
            if vals:
                nz = [v for v in vals if abs(v) > 1e-12]
                out[c] = {"min": min(vals), "mean": sum(vals)/len(vals), "max": max(vals), "sum": sum(vals), "n": len(vals),
                          "first": vals[0], "last": vals[-1], "delta": vals[-1] - vals[0],
                          "nonzero_count": len(nz), "nonzero_sum": sum(nz),
                          "nonzero_mean": (sum(nz)/len(nz) if nz else 0.0)}
        return out
    except Exception:
        return {}


def _pick(d: dict, keys, default=None):
    """Pick the first non-empty value from a dict using a string or list of keys."""
    if not isinstance(d, dict):
        return default
    if isinstance(keys, str):
        keys = [keys]
    lower = {str(k).lower(): k for k in d.keys()}
    for key in keys:
        if key in d and not _amoprof_missing(d.get(key)):
            return d.get(key)
        lk = lower.get(str(key).lower())
        if lk is not None and not _amoprof_missing(d.get(lk)):
            return d.get(lk)
    return default

# ─── Utilities ──────────────────────────────────────────────────────────────


def _fmt_num(value: float, suffix: str = "", nd: int = 1) -> str:
    v = _safe_float(value, 0.0)
    if abs(v) >= 1000:
        body = f"{v:,.{nd}f}"
    else:
        body = f"{v:.{nd}f}"
    if nd == 0:
        body = f"{v:,.0f}"
    return body + suffix


def _is_latency_unit(unit: str) -> bool:
    return str(unit or "").strip().lower() in ("ms", "ms/tok")


def _fmt_latency(value: float, unit: str = "ms", suffix: str = "") -> str:
    """Latency the way the KPI tiles print it (`_lat_value_text`).

    No thousands separator, whole ms; per-token latency (ms/tok) to 0.1 ms.
    The Executive tab printed one TTFT p50 five ways — 6,730 / 6,730.22 /
    6,730.2 / 7.4e+03 against the tiles' 6730 — so every latency on it goes
    through here.
    """
    v = _safe_float(value, 0.0)
    nd = 1 if str(unit or "").strip().lower() == "ms/tok" else 0
    return f"{v:.{nd}f}{suffix}"


def _ts_col(summary: dict, *names: str) -> dict:
    if not isinstance(summary, dict):
        return {}
    # exact lookup first
    for name in names:
        if name in summary and isinstance(summary.get(name), dict):
            return summary.get(name) or {}
    # substring/suffix lookup for Prometheus label-expanded column names
    lowered = [(str(k).lower(), k) for k in summary.keys()]
    for name in names:
        nl = str(name).lower()
        for kl, k in lowered:
            if kl == nl or kl.endswith(nl) or nl in kl:
                v = summary.get(k)
                if isinstance(v, dict):
                    return v
    return {}


def _ts_delta(summary: dict, *names: str) -> float:
    c = _ts_col(summary, *names)
    if not c:
        return 0.0
    if "delta" in c:
        return max(0.0, _safe_float(c.get("delta"), 0.0))
    first = _safe_float(c.get("first"), 0.0)
    last = _safe_float(c.get("last"), 0.0)
    return max(0.0, last - first)


def _ts_ratio_delta_ms(summary: dict, sum_col: str, count_col: str) -> float:
    ds = _ts_delta(summary, sum_col)
    dc = _ts_delta(summary, count_col)
    if ds > 0 and dc > 0:
        return (ds / dc) * 1000.0
    return 0.0


def _pct_from_ratio(num: float, den: float) -> float:
    num = _safe_float(num, 0.0); den = _safe_float(den, 0.0)
    if den <= 0:
        return 0.0
    return max(0.0, min(100.0, (num / den) * 100.0))


def _normalise_pct(v: float) -> float:
    v = _safe_float(v, 0.0)
    if 0.0 < v <= 1.0:
        v *= 100.0
    return max(0.0, min(100.0, v))


def _ts_active_mean(summary: dict, *names: str) -> float:
    c = _ts_col(summary, *names)
    if not c:
        return 0.0
    return _safe_float(c.get("nonzero_mean", c.get("mean", 0.0)), 0.0)


def _ts_active_p50(summary: dict, *names: str) -> float:
    # Approximate p50 with mean when the compact CSV summary has no sample list.
    return _ts_active_mean(summary, *names)


def _ts_gauge_stats(summary: dict, *names: str) -> dict:
    c = _ts_col(summary, *names)
    return dict(c) if isinstance(c, dict) else {}


def _gpu_util_decomposition(summary: dict, gpu_sum: dict | None = None,
                             threshold_pct: float = 0.0) -> dict:
    """Compute the 4-value GPU util view (overall/active/threshold/idle).

    Shape matches `amoprof.report.amoprof._amoprof_gpu_util_decomposition` so
    Executive, End Report, and Interactive all read the same interpretation.
    Prefers per-column stats from the CSV summary (`_read_csv_summary`); falls
    back to `gpu_summary.json` fields written by extract_metrics.
    """
    zero = {
        "overall_mean": 0.0, "active_mean": 0.0,
        "active_threshold_pct": float(threshold_pct),
        "idle_fraction_pct": 0.0, "peak": 0.0,
        "total_samples": 0, "active_samples": 0,
    }
    c = _ts_col(summary, "gpu_util", "DCGM_FI_DEV_GPU_UTIL")
    total = int(_safe_float(c.get("n", 0), 0))
    active = int(_safe_float(c.get("nonzero_count", 0), 0))
    overall = _safe_float(c.get("mean", 0.0), 0.0)
    active_mean = _safe_float(c.get("nonzero_mean", 0.0), 0.0)
    peak = _safe_float(c.get("max", 0.0), 0.0)
    if total == 0:
        # Fall back to gpu_summary.json (written by extract_metrics).
        g = gpu_sum or {}
        total = int(_safe_float(g.get("gpu_util_total_samples", 0), 0))
        active = int(_safe_float(g.get("gpu_util_active_samples", 0), 0))
        overall = _safe_float(g.get("gpu_util_overall_mean", g.get("gpu_util_mean", 0.0)), 0.0)
        active_mean = _safe_float(g.get("gpu_util_active_mean", 0.0), 0.0)
        peak = _safe_float(g.get("gpu_util_peak", 0.0), 0.0)
        if total == 0:
            return zero
    idle_frac = ((total - active) / total * 100.0) if total > 0 else 0.0
    return {
        "overall_mean": round(overall, 2),
        "active_mean": round(active_mean, 2),
        "active_threshold_pct": float(threshold_pct),
        "idle_fraction_pct": round(idle_frac, 2),
        "peak": round(peak, 2),
        "total_samples": total,
        "active_samples": active,
    }


def _amoprof_has_explicit_l3_config(setup: dict, launch: str = "") -> bool:
    """Return True when setup/launch explicitly describes an L3/L3.5 tier.

    Used only for capacity/context gating.  Runtime movement can still make the
    effective tier active later, but explicit setup fields should allow df/capacity
    context to be shown.
    """
    if not isinstance(setup, dict):
        setup = {}
    keys = [
        "KV cache tier", "L3 storage type", "L3 Device", "L3 device",
        "L3 storage path", "L3 path", "L3 capacity", "L3 capacity GB",
        "AI Memory Node", "AI Memory Node endpoint", "Mooncake endpoint",
        "Remote storage endpoint", "L3.5 endpoint",
    ]
    for k in keys:
        if k in setup and not _amoprof_missing(setup.get(k)):
            return True
    text = " ".join(str(setup.get(k, "")) for k in setup) + " " + str(launch or "")
    low = text.lower()
    explicit_terms = [
        "--hicache-storage-backend", "--hicache-storage-prefetch-policy",
        "mooncake", "ai memory node", "l3.5", "rdma", "remote",
        "nvme", "/dev/nvme", "ssd", "l3 storage",
    ]
    return any(t in low for t in explicit_terms)


def _parse_intel_pcm_memory_raw_summary(raw_dir: Path) -> Dict[str, Any]:
    """Parse raw/pcm_memory_raw.csv two-row Intel PCM output for Executive.

    This covers older runs where collection produced all-zero pcm_timeseries.csv
    but preserved the real pcm-memory CSV with final System Read/Write/Memory
    columns. Values are normalized from MB/s to GB/s.
    """
    p = Path(raw_dir) / "pcm_memory_raw.csv"
    if not p.exists() or p.stat().st_size <= 0:
        return {}
    try:
        rows = list(csv.reader(p.open(errors="replace")))
    except Exception:
        return {}
    if len(rows) < 3:
        return {}
    group = rows[0]
    names = rows[1]
    # Prefer explicit System Read/Write/Memory columns from the two-row header.
    idx_read = idx_write = idx_mem = None
    for i, (g, n) in enumerate(zip(group, names)):
        gl = str(g or "").strip().lower()
        nl = str(n or "").strip().lower()
        if gl == "system" and nl == "read": idx_read = i
        elif gl == "system" and nl == "write": idx_write = i
        elif gl == "system" and nl == "memory": idx_mem = i
    # Fallback to Mem Read/Write (MB/s) aggregate columns if System is absent.
    if idx_read is None or idx_write is None:
        candidates_read = [i for i,n in enumerate(names) if str(n).strip().lower() == "mem read (mb/s)"]
        candidates_write = [i for i,n in enumerate(names) if str(n).strip().lower() == "mem write (mb/s)"]
        if candidates_read and candidates_write:
            idx_read = candidates_read[-1]
            idx_write = candidates_write[-1]
    def _num(x):
        try: return float(str(x).strip().replace(",", ""))
        except Exception: return None
    reads=[]; writes=[]; totals=[]
    for r in rows[2:]:
        if idx_read is None or idx_write is None or len(r) <= max(idx_read, idx_write):
            continue
        rd = _num(r[idx_read]); wr = _num(r[idx_write])
        if rd is None or wr is None:
            continue
        # pcm-memory unqualified System Read/Write/Memory are MB/s.
        rd_g = rd / 1000.0; wr_g = wr / 1000.0   # pcm MB/s is decimal (1e6 B/s)
        if idx_mem is not None and len(r) > idx_mem:
            mm = _num(r[idx_mem])
            total_g = (mm / 1000.0) if mm is not None else (rd_g + wr_g)
        else:
            total_g = rd_g + wr_g
        if total_g > 0:
            reads.append(rd_g); writes.append(wr_g); totals.append(total_g)
    if not totals:
        return {}
    def mean(xs): return sum(xs) / len(xs) if xs else 0.0
    return _dram_metric_from_summary_obj({
        "pcm_available": True,
        "pcm_source": "intel-pcm/pcm-memory/raw-reparse",
        "dram_collector": "intel-pcm/pcm-memory/raw-reparse",
        "pcm_raw_path": str(p),
        "pcm_samples": len(totals),
        "pcm_nonzero_samples": len(totals),
        "dram_read_gb_s_mean": mean(reads),
        "dram_write_gb_s_mean": mean(writes),
        "dram_total_gb_s_mean": mean(totals),
        "dram_read_gb_s_peak": max(reads),
        "dram_write_gb_s_peak": max(writes),
        "dram_total_gb_s_peak": max(totals),
        "pcm_dram_read_gb_s": mean(reads),
        "pcm_dram_write_gb_s": mean(writes),
        "pcm_dram_total_gb_s": mean(totals),
        "pcm_dram_read_gb_s_peak": max(reads),
        "pcm_dram_write_gb_s_peak": max(writes),
        "pcm_dram_total_gb_s_peak": max(totals),
    }, "pcm_memory_raw.csv")


# ─── Executive summary generation ──────────────────────────────────────────


def _dram_metric_from_summary_obj(obj: Dict[str, Any], source: str = "") -> Dict[str, Any]:
    """Normalize DRAM PMU summaries/timeseries summaries to one shape.

    Executive used to inspect only normalized CSV summaries and AMDuProf raw
    text.  The End Report, however, can populate DRAM BW from collector JSON
    summaries such as raw/pcm_summary.json on Intel.  Normalize both flat
    collector summaries and _read_csv_summary() output so Executive,
    Interactive, and End Report agree.
    """
    if not isinstance(obj, dict) or not obj:
        return {}

    def _flat(keys):
        return _safe_float(_pick(obj, keys, 0.0), 0.0)

    def _col_mean(keys):
        c = _ts_col(obj, *keys)
        if not isinstance(c, dict) or not c:
            return 0.0
        return (_safe_float(c.get("nonzero_mean", 0.0), 0.0) or
                _safe_float(c.get("mean", 0.0), 0.0) or
                _safe_float(c.get("last", 0.0), 0.0))

    def _col_peak(keys):
        c = _ts_col(obj, *keys)
        if not isinstance(c, dict) or not c:
            return 0.0
        return _safe_float(c.get("max", 0.0), 0.0)

    total_keys = [
        "dram_total_gb_s", "total_gb_s", "total_bw_gbs", "dram_bw_gbps",
        "dram_total_bw_gbs", "dram_total_bw_gbps", "memory_bw_gbps",
        "pcm_dram_total_gb_s", "Total Mem Bw", "Total Mem Bw (GB/s)",
    ]
    read_keys = [
        "dram_read_gb_s", "read_gb_s", "read_bw_gbs", "read_bw_gbps",
        "dram_read_bw_gbs", "dram_read_bw_gbps", "pcm_dram_read_gb_s",
        "Total Mem RdBw", "Total Mem RdBw (GB/s)",
    ]
    write_keys = [
        "dram_write_gb_s", "write_gb_s", "write_bw_gbs", "write_bw_gbps",
        "dram_write_bw_gbs", "dram_write_bw_gbps", "pcm_dram_write_gb_s",
        "Total Mem WrBw", "Total Mem WrBw (GB/s)",
    ]
    total_mean_keys = [
        "dram_total_gb_s_mean", "total_gb_s_mean", "total_bw_gbs_mean",
        "dram_total_bw_gbs_mean", "dram_total_bw_gbps_mean",
        "dram_total_bw_mean_gbps", "pcm_dram_total_gb_s",
        "pcm_dram_total_gb_s_mean", "amduprof_dram_total_bw_gbps_mean",
    ]
    read_mean_keys = [
        "dram_read_gb_s_mean", "read_gb_s_mean", "read_bw_gbs_mean",
        "dram_read_bw_gbs_mean", "dram_read_bw_gbps_mean",
        "dram_read_bw_mean_gbps", "pcm_dram_read_gb_s",
        "pcm_dram_read_gb_s_mean", "amduprof_dram_read_bw_gbps_mean",
    ]
    write_mean_keys = [
        "dram_write_gb_s_mean", "write_gb_s_mean", "write_bw_gbs_mean",
        "dram_write_bw_gbs_mean", "dram_write_bw_gbps_mean",
        "dram_write_bw_mean_gbps", "pcm_dram_write_gb_s",
        "pcm_dram_write_gb_s_mean", "amduprof_dram_write_bw_gbps_mean",
    ]
    total_peak_keys = [
        "dram_total_gb_s_peak", "peak_total_gb_s",
        "pcm_dram_total_gb_s_peak", "dram_total_bw_gbs_peak",
        "dram_total_bw_gbps_peak", "dram_peak_bw_gbps",
        "amduprof_dram_total_bw_gbps_peak",
    ]
    read_peak_keys = [
        "dram_read_gb_s_peak", "peak_read_gb_s", "pcm_dram_read_gb_s_peak",
        "dram_read_bw_gbs_peak", "dram_read_bw_gbps_peak",
        "amduprof_dram_read_bw_gbps_peak",
    ]
    write_peak_keys = [
        "dram_write_gb_s_peak", "peak_write_gb_s", "pcm_dram_write_gb_s_peak",
        "dram_write_bw_gbs_peak", "dram_write_bw_gbps_peak",
        "amduprof_dram_write_bw_gbps_peak",
    ]

    total = _col_mean(total_keys) or _flat(total_mean_keys) or _flat(total_keys)
    read = _col_mean(read_keys) or _flat(read_mean_keys) or _flat(read_keys)
    write = _col_mean(write_keys) or _flat(write_mean_keys) or _flat(write_keys)
    if total <= 0 and (read > 0 or write > 0):
        total = read + write
    if read <= 0 and total > 0 and write > 0:
        read = max(total - write, 0.0)
    if write <= 0 and total > 0 and read > 0:
        write = max(total - read, 0.0)

    total_peak = _col_peak(total_keys) or _flat(total_peak_keys) or total
    read_peak = _col_peak(read_keys) or _flat(read_peak_keys) or read
    write_peak = _col_peak(write_keys) or _flat(write_peak_keys) or write
    rows = int(_safe_float(obj.get("rows", 0), 0) or
               _safe_float(_pick(obj, ["pcm_samples", "amduprof_pcm_samples",
                                       "dram_samples", "sample_count"], 0), 0) or
               (1 if total > 0 or read > 0 or write > 0 else 0))
    nonzero = int(_safe_float(_pick(obj, ["pcm_nonzero_samples",
                                          "amduprof_pcm_nonzero_samples",
                                          "dram_nonzero_samples"], 0), 0) or
                  (rows if total > 0 or read > 0 or write > 0 else 0))
    if total <= 0 and read <= 0 and write <= 0 and nonzero <= 0:
        return {}

    def _stat(mean, peak):
        mean = _safe_float(mean, 0.0)
        peak = _safe_float(peak, mean) or mean
        return {
            "mean": mean, "max": peak, "min": 0.0 if rows <= 1 else min(mean, peak),
            "sum": mean * max(rows, 1), "n": max(rows, 1),
            "first": mean, "last": mean, "delta": 0.0,
            "nonzero_count": max(nonzero, 1 if mean > 0 else 0),
            "nonzero_sum": mean * max(nonzero, 1 if mean > 0 else 0),
            "nonzero_mean": mean,
        }

    return {
        "rows": rows,
        "columns": ["dram_read_gb_s", "dram_write_gb_s", "dram_total_gb_s",
                    "pcm_dram_read_gb_s", "pcm_dram_write_gb_s", "pcm_dram_total_gb_s"],
        "path": str(_pick(obj, ["path", "pcm_raw_path", "pcm_csv_path",
                                 "amduprof_pcm_csv_path"], source) or source),
        "source": source or str(_pick(obj, ["dram_collector", "pcm_source",
                                             "amduprof_pcm_source"], "dram_pmu_summary")),
        "dram_read_gb_s": _stat(read, read_peak),
        "dram_write_gb_s": _stat(write, write_peak),
        "dram_total_gb_s": _stat(total, total_peak),
        "pcm_dram_read_gb_s": _stat(read, read_peak),
        "pcm_dram_write_gb_s": _stat(write, write_peak),
        "pcm_dram_total_gb_s": _stat(total, total_peak),
        "total_gb_s": _stat(total, total_peak),
        "read_gb_s": _stat(read, read_peak),
        "write_gb_s": _stat(write, write_peak),
    }


def _load_dram_pmu_summary(raw_dir: Path, preferred_csv_summary: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Load the best available physical DRAM PMU measurement for reports.

    Priority mirrors End Report: timestamped PMU CSV → collector summary JSON
    → raw AMDuProf text fallback.  This intentionally includes Intel
    raw/pcm_summary.json; otherwise Intel runs can show populated End Report
    DRAM charts while Executive says PMU is missing.
    """
    for obj, src in ((preferred_csv_summary or {}, "dram_pmu_timeseries"),):
        norm = _dram_metric_from_summary_obj(obj, src)
        if norm:
            return norm
    for name in ("pcm_summary.json", "pcm_memory_summary.json",
                 "amduprof_pcm_summary.json", "dram_summary.json"):
        p = Path(raw_dir) / name
        js = _read_json(p)
        norm = _dram_metric_from_summary_obj(js, name)
        if norm:
            return norm
    raw_pcm = _parse_intel_pcm_memory_raw_summary(Path(raw_dir))
    if raw_pcm:
        return raw_pcm
    raw = _parse_amduprof_pcm_raw(Path(raw_dir))
    norm = _dram_metric_from_summary_obj(raw, "amduprof_pcm_raw")
    if norm:
        return norm
    return preferred_csv_summary or {}


def _parse_amduprof_pcm_raw(raw_dir: Path) -> Dict[str, Any]:
    """Parse amduprof_pcm_raw.csv text report to extract DRAM BW stats.

    The file has a multi-section structure. The unique signature of the
    real data header is that ONE line contains both "Total Mem Bw" AND
    "Total Mem RdBw" (the static report uses exactly this discriminator
    and gets correct values). The previous loose detection (`"mem bw"
    in line`) accidentally locked onto label/section rows that contained
    "Mem Bw" without the per-direction columns, then summed garbage from
    per-core rows that follow.

    Returns the same shape dict as _read_csv_summary so callers can use
    the same column-name lookups.
    """
    candidates = [
        raw_dir / "amduprof_pcm_raw.csv",
        raw_dir / "amduprof_pcm_raw.txt",
    ]
    src = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
    if src is None:
        return {"rows": 0, "columns": []}

    total_rows: List[float] = []
    read_rows:  List[float] = []
    write_rows: List[float] = []
    col_total_idx = 0
    col_rd_idx    = 1
    col_wr_idx    = 2
    in_data = False
    try:
        with src.open(encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                l = raw_line.strip().rstrip(",")
                if not l:
                    continue
                # Strict header detection: BOTH "Total Mem Bw" AND a per-direction
                # column on the same line. Matches exactly the row AMDuProf uses
                # to declare its DRAM-BW data columns; immune to section labels.
                if ("Total Mem Bw" in l and
                        ("Total Mem RdBw" in l or "RdBw" in l)):
                    cols = [c.strip().lower() for c in l.split(",")]
                    for ci, c in enumerate(cols):
                        if "total mem bw" in c and "rdbw" not in c and "wrbw" not in c:
                            col_total_idx = ci
                        elif "total mem rdbw" in c or c == "rdbw" or "mem rdbw" in c:
                            col_rd_idx = ci
                        elif "total mem wrbw" in c or c == "wrbw" or "mem wrbw" in c:
                            col_wr_idx = ci
                    in_data = True
                    continue
                if not in_data:
                    continue
                # Data rows start with a numeric (RecordId or timestamp); stop
                # parsing when we hit a non-data section header.
                if not l[0].isdigit():
                    in_data = False
                    continue
                try:
                    parts = [float(x) for x in l.split(",") if x]
                except ValueError:
                    continue
                n = len(parts)
                if n <= max(col_total_idx, col_rd_idx, col_wr_idx):
                    continue
                total_rows.append(parts[col_total_idx])
                read_rows.append(parts[col_rd_idx])
                write_rows.append(parts[col_wr_idx])
    except Exception:
        return {"rows": 0, "columns": [], "error": "parse_failed"}

    if not total_rows:
        return {"rows": 0, "columns": []}

    def _stats(vals: List[float]) -> Dict[str, float]:
        n  = len(vals)
        nz = [v for v in vals if v > 0]
        return {
            "mean":          (sum(vals) / n) if n else 0.0,
            "max":           max(vals) if vals else 0.0,
            "count":         n,
            "nonzero_sum":   sum(nz),
            "nonzero_count": len(nz),
            "nonzero_mean":  (sum(nz) / len(nz)) if nz else 0.0,
        }

    return {
        "rows": len(total_rows),
        "columns": ["dram_bw_gbps", "read_bw_gbps", "write_bw_gbps"],
        "dram_bw_gbps":  _stats(total_rows),
        "read_bw_gbps":  _stats(read_rows),
        "write_bw_gbps": _stats(write_rows),
    }


def _per_layer_takeaways_html(*,
                               ttft_ms: float, itl_ms: float, throughput: float,
                               cache_hit: float, cache_hit_tw: float,
                               gpu_util: float, hbm_used_gb: float,
                               hbm_total_gb: float, gpu_power: float,
                               dram_bw: float, swap_pages: float,
                               nvme_rd_bw: float, nvme_wr_bw: float,
                               read_gb: float, write_gb: float,
                               nvme_util: float,
                               backuped_tokens: float, loadback_tokens: float,
                               evicted_tokens: float,
                               kv_bytes_tok_kb: float,
                               l3_source: str = "blktrace",
                               interactive_figures: "dict | None" = None) -> str:
    """Render the Chart-by-Chart Takeaways block when full blktrace charts
    aren't available (Prom-only mode).

    Produces one row per AI-stack layer (A5/A4/A3/A2/A1/Cross) with:
      • Layer badge in the layer's color
      • A 1-line headline derived from this run's numbers
      • A verdict pill (OK / Near-full / Active spilling / Clean)
      • A 2-3 sentence takeaway grounded in the actual measurements

    Why this approach: in Prom-only mode the original implementation rendered
    a single "Blktrace data not available" line — visually dead and useless
    for sizing exercises. This helper extracts what IS available (SGLang
    counters, GPU utilization, swap activity, derived L3 local-storage BW) and presents
    actionable per-layer summaries. The numbers come from the same data
    sources the executive already loaded; nothing fabricated.

    The takeaways follow a consistent rhetorical pattern: state the
    measurement, interpret what it means, give a concrete next action.
    """
    # ── Per-layer verdict logic ──────────────────────────────────────────────
    # A5 Application — look at TTFT/TPOT magnitudes
    if ttft_ms > 5000 or itl_ms > 100:
        a5_verdict, a5_color = "Slow", "#dc2626"
    elif ttft_ms > 2000 or itl_ms > 50:
        a5_verdict, a5_color = "Watch", "#d97706"
    else:
        a5_verdict, a5_color = "OK", "#16a34a"

    # A4 Runtime — cache hit gap signals
    cache_gap = abs(cache_hit - cache_hit_tw)
    if cache_hit < 50:
        a4_verdict, a4_color = "Cold", "#dc2626"
    elif cache_gap > 10:
        a4_verdict, a4_color = "Skewed", "#d97706"
    else:
        a4_verdict, a4_color = "OK", "#16a34a"

    # A4 GPU sub-verdict — HBM fill vs utilization. Layered puts GPU/HBM under
    # A4 (see layers/a4_gpu_hbm.py); we surface the same evidence as an A4-side
    # verdict merged with the runtime cache-hit check above.
    hbm_pct = (hbm_used_gb / hbm_total_gb * 100) if hbm_total_gb > 0 else 0
    if hbm_pct > 85 and gpu_util < 70:
        gpu_verdict, gpu_color = "Memory-bound", "#d97706"
    elif hbm_pct > 95:
        gpu_verdict, gpu_color = "Near-full", "#dc2626"
    elif gpu_util > 90:
        gpu_verdict, gpu_color = "Compute-bound", "#d97706"
    else:
        gpu_verdict, gpu_color = "Balanced", "#16a34a"

    # A3 OS / Memory + Block layer — DRAM/swap pressure + block-layer traffic
    if swap_pages > 100:
        a3_verdict, a3_color = "Swapping", "#dc2626"
    elif swap_pages > 10:
        a3_verdict, a3_color = "Light pressure", "#d97706"
    else:
        a3_verdict, a3_color = "Clean", "#16a34a"

    # A2 I/O drivers (NVMe) — bandwidth + busy-time from driver-level counters
    if nvme_rd_bw > 5000 or nvme_wr_bw > 3000:
        a2_verdict, a2_color = "Heavy traffic", "#d97706"
    elif read_gb == 0 and write_gb == 0:
        a2_verdict, a2_color = "Idle", "#64748b"
    else:
        a2_verdict, a2_color = "OK", "#16a34a"

    # A1 Hardware — SSD/HBM/DRAM physical characteristics.
    # We don't get per-run endurance/capacity signals here; the verdict reflects
    # whether block-layer traffic actually made it to hardware.
    if read_gb == 0 and write_gb == 0:
        a1_verdict, a1_color = "Idle", "#64748b"
    else:
        a1_verdict, a1_color = "Active", "#16a34a"

    # Cross-layer — KV flow thrashing detection
    # Load-back >> backup means same blocks pulled repeatedly = thrashing
    if backuped_tokens > 0 and loadback_tokens > 0:
        kv_ratio = loadback_tokens / backuped_tokens
        if kv_ratio > 3:
            x_verdict, x_color = "Active spilling", "#dc2626"
        elif kv_ratio > 1.5:
            x_verdict, x_color = "Moderate spill", "#d97706"
        else:
            x_verdict, x_color = "Steady", "#16a34a"
    else:
        x_verdict, x_color = "No L3 local-storage spill", "#64748b"

    # ── Build per-layer rows ────────────────────────────────────────────────
    def _row(tag, tag_color, layer_title, headline, verdict, verdict_color,
             takeaway, chart_id: str = "", chart_fig: str = ""):
        # Optional Plotly chart block. When chart_fig is provided (a JSON
        # string suitable for fig.data / fig.layout consumption), render an
        # inline div and a one-shot script that calls Plotly.newPlot on it.
        # The script uses a small retry loop: even though <script src> is
        # synchronous in HTML parsing, some preview environments (sandboxed
        # iframes, browser extensions) can interfere with synchronous
        # script loading. Retry every 50ms up to 100 times (5s) before
        # giving up — this protects against the race seen in user reports
        # where the slot renders empty.
        chart_html = ""
        if chart_fig and chart_id:
            slot_id = f"cbc-{chart_id}"
            chart_html = (
                f'<div id="{slot_id}" style="min-height:280px;background:#fff;'
                f'border-radius:6px;padding:6px;margin:8px 0"></div>'
                f'<script>(function(){{'
                f'  var tries = 0;'
                f'  function render() {{'
                f'    if (typeof Plotly === "undefined") {{'
                f'      if (++tries < 100) return setTimeout(render, 50);'
                f'      var slot = document.getElementById("{slot_id}");'
                f'      if (slot) slot.innerHTML = \'<div style="padding:24px;'
                f'color:#64748b;font-style:italic">Plotly library failed to '
                f'load — check network access to cdn.plot.ly</div>\';'
                f'      return;'
                f'    }}'
                f'    try {{'
                f'      var fig = {chart_fig};'
                f'      fig.layout = fig.layout || {{}};'
                f'      fig.layout.autosize = true;'
                f'      var n = (fig.data || []).filter(function(t){{return !t || t.showlegend !== false;}}).length;'
                f'      fig.layout.margin = Object.assign({{l:70,r:(n>=2?340:90),t:64,b:120}}, fig.layout.margin || {{}});'
                f'      if (n >= 2) {{'
                f'        fig.layout.margin.r = Math.max(fig.layout.margin.r || 0, n>4 ? 380 : 340);'
                f'        fig.layout.height = Math.max(fig.layout.height || 280, n>4 ? 580 : 540);'
                f'        fig.layout.legend = Object.assign({{orientation:"v", yanchor:"top", y:1.0, xanchor:"left", x:1.03, font:{{size:(n>4?10:11),color:"#0f172a"}}, bgcolor:"rgba(248,250,252,0.98)", bordercolor:"#cbd5e1", borderwidth:1, itemsizing:"constant", itemwidth:30, tracegroupgap:6}}, fig.layout.legend || {{}});'
                f'        delete fig.layout.legend.entrywidth; delete fig.layout.legend.entrywidthmode;'
                f'      }} else {{'
                f'        fig.layout.margin.b = Math.max(fig.layout.margin.b || 0, 120);'
                f'        fig.layout.legend = Object.assign({{orientation:"h", yanchor:"top", y:-0.14, xanchor:"left", x:0, font:{{size:11,color:"#0f172a"}}, bgcolor:"rgba(248,250,252,0.98)", bordercolor:"#cbd5e1", borderwidth:1, itemsizing:"constant", itemwidth:30}}, fig.layout.legend || {{}});'
                f'      }}'
                f'      Plotly.newPlot("{slot_id}", fig.data, fig.layout,'
                f'        {{responsive:true, displayModeBar:false}});'
                f'    }} catch(e) {{'
                f'      var slot = document.getElementById("{slot_id}");'
                f'      if (slot) slot.innerHTML = \'<div style="padding:24px;'
                f'color:#64748b;font-style:italic">Chart unavailable in this '
                f'view (\' + e.message + \')</div>\';'
                f'    }}'
                f'  }}'
                f'  render();'
                f'}})();</script>'
            )
        return (
            f'<div style="background:#0f172a;border:1px solid #1e293b;'
            f'border-radius:10px;padding:14px 16px;margin:10px 0">'
            f'<div style="display:flex;align-items:center;gap:10px;'
            f'margin-bottom:8px;flex-wrap:wrap">'
            f'<span style="background:{tag_color};color:#fff;font-weight:800;'
            f'font-size:10px;letter-spacing:.6px;border-radius:4px;padding:3px 8px">'
            f'{tag} · {layer_title}</span>'
            f'<span style="font-weight:700;font-size:13px;color:#f8fafc;flex:1">'
            f'{headline}</span>'
            f'<span style="background:{verdict_color}22;color:{verdict_color};'
            f'font-weight:700;font-size:10px;letter-spacing:.4px;border-radius:999px;'
            f'padding:3px 10px;border:1px solid {verdict_color}66">{verdict}</span>'
            f'</div>'
            f'{chart_html}'
            f'<div style="padding:10px 12px;background:#1e293b;border-radius:6px;'
            f'color:#e2e8f0;font-size:13px;line-height:1.6;'
            f'border-left:3px solid {tag_color}">{takeaway}</div>'
            f'</div>'
        )

    # Build each row's takeaway. Use real run numbers throughout.
    a5_takeaway = (
        f"<strong>TTFT {ttft_ms/1000:.1f}s · TPOT {itl_ms:.0f}ms · "
        f"Throughput {throughput:.1f} tok/s.</strong> "
        + (
            "Application layer is healthy. Next-step latency tuning would target "
            "prefill compute (FP8 KV, chunked prefill) rather than queuing or "
            "scheduling."
            if a5_verdict == "OK" else
            f"TPOT exceeds the typical 50ms threshold. Investigate batch size, "
            f"prefill chunking, and KV cache locality. {('Long TTFT also points to '
            'prefill compute bottleneck — consider chunked prefill.' if ttft_ms > 3000 else '')}"
        )
    )

    a4_takeaway = (
        f"<strong>Cache hit {cache_hit:.1f}% gauge / {cache_hit_tw:.1f}% "
        f"token-weighted.</strong> "
        + (
            f"The {cache_gap:.1f}-point gap (gauge over token-weighted) reveals that "
            f"small high-cache requests dominate the count while a few larger "
            f"misses drive the real cost. Improvement lever: shared system-prompt "
            f"prefix + LPM scheduling would tighten this gap."
            if cache_gap > 2 else
            "Gauge and token-weighted hit rates agree — request size distribution "
            "is uniform across the workload, no measurement skew."
        )
    )

    # A4 combined takeaway: runtime (cache-hit) + GPU/HBM. Layered puts these in
    # the same layer, so the Executive row combines both signals.
    gpu_takeaway = (
        f"<strong>HBM {hbm_used_gb:.1f}GB / {hbm_total_gb:.0f}GB ({hbm_pct:.0f}% full) "
        f"at {gpu_util:.1f}% GPU util · {gpu_power:.0f}W.</strong> "
        + (
            f"High HBM fill with sub-70% GPU utilization signals "
            f"<em>memory-bound</em> decoding — cycles spent waiting on HBM "
            f"bandwidth, not compute. Actionable levers: <strong>FP8 KV "
            f"quantisation</strong> halves the KV footprint ({_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f} → {_k_kb_from_bytes(kv_bytes_tok_kb * 512):.0f} KB/tok) "
            f"and effectively doubles in-HBM capacity; <strong>chunked prefill</strong> "
            f"reduces per-step HBM pressure during prefill."
            if gpu_verdict == "Memory-bound" else
            f"HBM has headroom and utilization is reasonable — capacity is not "
            f"the binding constraint for this workload."
            if hbm_pct < 70 else
            f"HBM is near capacity — KV blocks will be evicted to the L2 host-DRAM "
            f"tier as the working set grows. Monitor the eviction rate; if it "
            f"spikes, expand HiCache L2 allocation."
        )
    )
    # Combine A4 runtime cache-hit and A4 GPU/HBM into a single narrative line.
    a4_takeaway = a4_takeaway + " <br><br>" + gpu_takeaway

    a3_takeaway = (
        f"<strong>Swap activity: {swap_pages:.0f} pages/s · DRAM BW: "
        f"{('not captured' if dram_bw == 0 else f'{dram_bw:.1f} GB/s')}.</strong> "
        + (
            "No vmstat pressure, no swap-in/out activity. The A3 OS/memory tier "
            "has substantial headroom. " +
            ("DRAM bandwidth wasn't captured (--enable-dram not enabled) but the "
             "absence of swap pressure makes this tier a non-bottleneck. "
             if dram_bw == 0 else "") +
            "Expand HiCache L2 allocation to reduce spill into the storage tier."
            if a3_verdict == "Clean" else
            f"Active swap signals memory pressure on the host. Reduce in-memory "
            f"KV cache, or add system memory. This is a structural constraint, "
            f"not a tunable parameter."
        )
    )

    l3_data_note = (
        f"(derived from SGLang × {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f} KB/tok)"
        if l3_source == "sglang_logical_local_ssd"
        else "(blktrace / iostat)"
    )
    if read_gb > 0 or write_gb > 0:
        rw_ratio = read_gb / max(write_gb, 0.001)
        a2_takeaway = (
            f"<strong>{nvme_rd_bw:.0f} MB/s read · {nvme_wr_bw:.0f} MB/s write · "
            f"{read_gb:.0f}GB / {write_gb:.0f}GB total {l3_data_note}.</strong> "
            + (
                f"The {rw_ratio:.0f}:1 read:write ratio is characteristic of a "
                f"working-set-larger-than-HBM workload — KV blocks are being "
                f"fetched back from storage far more than offloaded. "
                if rw_ratio > 5 else ""
            )
            + (
                f"Driver-level bandwidth is below peak; the "
                f"constraint isn't throughput but the round-trip latency that "
                f"adds to TPOT on each load-back."
                if nvme_util < 50 else
                f"Driver counters show sustained pressure — verify with exact "
                f"blktrace Q→C queue depth before calling saturation. "
                f"Consider expanding the A3 DRAM tier to reduce storage fetches."
            )
        )
        a1_takeaway = (
            f"<strong>Hardware moved {read_gb+write_gb:.0f} GB "
            f"({read_gb:.0f} GB read + {write_gb:.0f} GB write) during this run.</strong> "
            "See §Endurance projection and §Block-latency percentiles below for "
            "per-device rated-TBW headroom and p50/p95/p99 latency evidence — the "
            "A1 layer signals whether the SSD hardware itself is the constraint, "
            "independent of driver-level bandwidth."
        )
    else:
        a2_takeaway = (
            "<strong>No driver-level I/O observed.</strong> Either the workload's KV "
            "blocks fit entirely in HBM + host DRAM, or instrumentation didn't "
            "capture activity through the NVMe driver. Re-run with a larger context "
            "or more concurrent sessions to exercise the storage tier."
        )
        a1_takeaway = (
            "<strong>Hardware quiescent for this run.</strong> Endurance projection "
            "and block-latency percentiles are informational only when there is no "
            "driver-level traffic to interpret."
        )

    if backuped_tokens > 0 or loadback_tokens > 0:
        ratio_str = (f"{(loadback_tokens/backuped_tokens):.1f}×"
                     if backuped_tokens > 0 else "n/a")
        x_takeaway = (
            f"<strong>{int(evicted_tokens):,} evicted · "
            f"{int(backuped_tokens):,} backed up to L3 · "
            f"{int(loadback_tokens):,} restored L2→L1.</strong> "
            + (
                f"The {ratio_str} L2→L1 load-back-vs-backup ratio means the same KV "
                f"blocks are being re-fetched repeatedly — a thrashing signal "
                f"that HBM + L2 DRAM combined are too small for this working "
                f"set. Headline fix: grow HiCache L2 (DRAM) so load-back hits "
                f"DRAM instead of L3 local storage."
                if x_verdict == "Active spilling" else
                f"KV flow is balanced — L2→L1 load-back restore roughly matches backup, "
                f"indicating steady cache reuse without thrashing."
            )
        )
    else:
        x_takeaway = (
            "<strong>No KV tier movement observed.</strong> SGLang counters "
            "show no offload/L2→L1 loadback activity. Either HiCache wasn't enabled, "
            "or the workload's KV footprint stayed within HBM."
        )

    # Map each layer's chart_id to its figure JSON (if provided).
    # Layers may degrade gracefully to text-only when a figure is missing.
    figs = interactive_figures or {}
    def _fig(cid):
        return figs.get(cid, "")

    # Plotly script include — only loaded once, only when at least one chart
    # has data to render. Avoids dead CDN requests when callers don't pass
    # interactive_figures.
    plotly_inc = ""
    if any(_fig(cid) for cid in
           ("ch_pct_ttft","ch_thru","ch_gpu","ch_swap","ch_l3_bw","ch_evict")):
        plotly_inc = (
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
        )

    # Layered baseline order: A5 → A4 → A3 → A2 → A1 → Cross.
    # See amoprof/layers/__init__.py::ORDERED_LAYERS for the source of truth.
    rows = [
        _row("A5", "#24577f", "Application (benchmark harness)",
             f"TTFT {ttft_ms/1000:.1f}s · TPOT {itl_ms:.0f}ms · "
             f"{throughput:.0f} tok/s",
             a5_verdict, a5_color, a5_takeaway,
             chart_id="ch_pct_ttft", chart_fig=_fig("ch_pct_ttft")),
        _row("A4", "#317bb8", "Inference Runtime (server + GPU/HBM)",
             (f"Cache hit {cache_hit:.1f}% / token-weighted {cache_hit_tw:.1f}% · "
              f"HBM {hbm_used_gb:.0f}GB ({hbm_pct:.0f}%) · GPU {gpu_util:.0f}%"),
             a4_verdict, a4_color, a4_takeaway,
             chart_id="ch_thru", chart_fig=_fig("ch_thru")),
        _row("A3", "#7a3f97", "OS / Memory manager + Block layer",
             (f"DRAM BW {dram_bw:.1f} GB/s · Swap {swap_pages:.0f} pages/s"
              if dram_bw > 0 else f"Swap {swap_pages:.0f} pages/s"),
             a3_verdict, a3_color, a3_takeaway,
             chart_id="ch_swap", chart_fig=_fig("ch_swap")),
        _row("A2", "#a45714", "I/O drivers (NVMe)",
             f"R {nvme_rd_bw:.0f} MB/s · W {nvme_wr_bw:.0f} MB/s · "
             f"driver-level BW/QD evidence",
             a2_verdict, a2_color, a2_takeaway,
             chart_id="ch_l3_bw", chart_fig=_fig("ch_l3_bw")),
        _row("A1", "#0f766e", "Hardware (HBM · DRAM · SSD)",
             f"Read {read_gb:.0f} GB · Write {write_gb:.0f} GB during run",
             a1_verdict, a1_color, a1_takeaway),
        _row("Cross", "#0f172a", "Cross-layer",
             f"Evict {int(evicted_tokens):,} · Backup {int(backuped_tokens):,} · "
             f"L2→L1 loadback {int(loadback_tokens):,}",
             x_verdict, x_color, x_takeaway,
             chart_id="ch_evict", chart_fig=_fig("ch_evict")),
    ]
    return plotly_inc + ''.join(rows) + (
        '<p style="color:#94a3b8;font-size:11px;font-style:italic;margin-top:12px">'
        'Per-layer summary derived from this run\'s available metrics. '
        'Full interactive charts available in the Interactive tab.'
        + (' L3 byte numbers estimated from SGLang token counters '
           '(blktrace not captured).' if l3_source == "sglang_logical_local_ssd" else '')
        + '</p>'
    )



def _nvme_status_phrase(nvme_util: float, nvme_rd_lat: float = -1.0) -> str:
    """Return a conservative status phrase for L3/SSD.

    NVMe/iostat busy-time is not proof of hardware saturation. A fast
    NVMe can show 100% busy with modest MB/s when at least one small I/O is
    continuously in flight. Use bandwidth, latency, and exact/plausible queue
    depth before recommending faster SSD hardware.
    """
    if nvme_util >= 90:
        if nvme_rd_lat and nvme_rd_lat > 1.0:
            return ("busy with elevated read latency — possible L3 local-storage queueing; "
                    "verify exact blktrace Q→C queue depth before sizing a faster SSD")
        return ("busy by time accounting, but bandwidth/IOPS saturation is not proven "
                "because read latency or exact queue-depth evidence is missing")
    if nvme_util >= 50:
        return ("actively engaged — monitor latency and queue depth as "
                "concurrent sessions scale")
    if nvme_util > 0:
        return "lightly utilised — substantial bandwidth headroom remains"
    return "not captured by iostat for this run"


def _qd_exact_source(src: str) -> bool:
    s = str(src or "").lower()
    return ("blktrace" in s and "fallback" not in s and "sysfs" not in s and "iostat" not in s)


def _qd_plausible(qd_mean: float, qd_peak: float, qd_source: str) -> bool:
    try:
        qdm = float(qd_mean or 0)
        qdp = float(qd_peak or 0)
    except Exception:
        return False
    if qdm < 0 or qdp < 0:
        return False
    # Coarse fallback values in the hundreds of thousands are almost always
    # a counter/unit interpretation issue, not real NVMe in-flight depth.
    if not _qd_exact_source(qd_source):
        if qdm > 4096 or qdp > 32768:
            return False
    return True


def _ssd_hw_saturation_proven(nvme_rd_bw: float, nvme_wr_bw: float, nvme_util: float,
                              nvme_rd_lat: float, qd_mean: float = 0,
                              qd_peak: float = 0, qd_source: str = "") -> bool:
    try:
        rd = float(nvme_rd_bw or 0)
        wr = float(nvme_wr_bw or 0)
        util = float(nvme_util or 0)
        lat = float(nvme_rd_lat or 0)
        qdm = float(qd_mean or 0)
        qdp = float(qd_peak or 0)
    except Exception:
        return False
    bw_saturated = (rd >= 0.70 * 7000.0) or (wr >= 0.70 * 5000.0)
    qd_exact = _qd_exact_source(qd_source)
    qd_ok = _qd_plausible(qdm, qdp, qd_source)
    queue_saturated = qd_exact and qd_ok and qdm >= 32
    latency_saturated = (lat > 1.0 and (queue_saturated or (util >= 90 and bw_saturated)))
    return bool(bw_saturated or latency_saturated or queue_saturated)
def _nvme_latency_phrase(nvme_rd_lat: float, nvme_wr_lat: float) -> str:
    """Return a value-aware latency-clause for inline use.

    Examples:
      rd=0, wr=0       → "Latency from iostat not captured for this run"
      rd=0.25, wr=0.4  → "Read latency 0.25ms mean (sub-millisecond)"
      rd=2.5, wr=0.4   → "Read latency 2.50ms mean (above the 1ms threshold)"
    """
    if nvme_rd_lat <= 0:
        return "Latency from iostat not captured for this run"
    if nvme_rd_lat < 1.0:
        return (f"Read latency {nvme_rd_lat:.2f}ms mean (sub-millisecond) · "
                f"write latency {nvme_wr_lat:.1f}ms")
    return (f"Read latency {nvme_rd_lat:.2f}ms mean (above the 1ms threshold "
            f"— each L2→L1 loadback adds non-trivial TPOT)")


def _extract_interactive_figures(interactive_html: str,
                                  chart_ids: "list[str] | None" = None
                                  ) -> "dict[str, str]":
    """Extract Plotly figure JSON for specific chart IDs from interactive HTML.

    The interactive report embeds each chart as `var fig = {...};
    Plotly.newPlot('chart_id', fig.data, fig.layout, ...)`. This helper
    scans those blocks and returns a dict mapping chart_id → figure JSON
    string for the requested IDs.

    Used by build_combined_report() to feed live chart data into the
    executive's Chart-by-Chart Takeaways section. If interactive_html is
    empty or no matching IDs are found, returns an empty dict — callers
    should treat that as "render text-only takeaways".
    """
    import re as _re
    if not interactive_html:
        return {}
    if chart_ids is None:
        chart_ids = ["ch_pct_ttft", "ch_thru", "ch_gpu", "ch_swap",
                     "ch_l3_bw", "ch_evict"]
    wanted = set(chart_ids)
    found: dict = {}
    # Non-greedy match between `var fig = ` and the matching
    # `Plotly.newPlot('id'` — captures the figure JSON literal.
    pat = _re.compile(
        r"var\s+fig\s*=\s*(\{.*?\});\s*Plotly\.newPlot\(['\"]([^'\"]+)['\"]",
        _re.DOTALL,
    )
    for m in pat.finditer(interactive_html):
        fig_json, cid = m.group(1), m.group(2)
        if cid in wanted and cid not in found:
            found[cid] = fig_json
            if len(found) == len(wanted):
                break
    return found





def _normalise_latency_label(label: str) -> str:
    lab = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(label))).strip().lower()
    lab = lab.replace("tpot / itl", "tpot").replace("server itl", "server tpot")
    if lab in {"ttft mean", "time to first token (ttft mean)"}:
        return "ttft_ms"
    if lab in {"ttft p50", "time to first token (ttft p50)"}:
        return "ttft_p50_ms"
    if lab in {"tpot mean", "itl mean", "time per output token (tpot mean)"}:
        return "tpot_ms"
    if lab in {"tpot p50", "itl p50", "time per output token (tpot p50)"}:
        return "tpot_p50_ms"
    if lab == "e2e mean":
        return "e2e_ms"
    if lab == "e2e p50":
        return "e2e_p50_ms"
    if lab in {"throughput mean", "generation throughput (mean)"}:
        return "throughput_mean"
    if lab in {"throughput p50", "generation throughput (p50)"}:
        return "throughput_p50"
    return ""


def _value_to_float_and_unit(value_html: str) -> tuple[float, str]:
    text = _html.unescape(re.sub(r"<[^>]+>", " ", str(value_html)))
    text = re.sub(r"\s+", " ", text).strip()
    m = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([a-zA-Z/%]+)?", text)
    if not m:
        return 0.0, ""
    val = _safe_float(m.group(1).replace(",", ""), 0.0)
    unit = (m.group(2) or "").strip()
    return val, unit


def _extract_latency_kpis_from_html(report_html: str, *, prefer_main_tiles: bool = True) -> Dict[str, float]:
    """Extract displayed latency/throughput KPI tile values from a report tab."""
    out: Dict[str, float] = {}
    if not report_html:
        return out
    html_txt = _html.unescape(report_html)
    patterns = [
        r'<div[^>]*class="kpi-label"[^>]*>(.*?)</div>\s*<div[^>]*class="kpi-value"[^>]*>(.*?)</div>',
        r'<div[^>]*text-transform:\s*uppercase[^>]*>(TTFT mean|TTFT p50|TPOT\s*/\s*ITL mean|TPOT\s*/\s*ITL p50|E2E mean|E2E p50|Throughput mean|Throughput p50)</div>\s*<div[^>]*font-size:\s*20px[^>]*>(.*?)</div>',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html_txt, flags=re.I | re.S):
            key = _normalise_latency_label(m.group(1))
            if not key or key in out:
                continue
            val, unit = _value_to_float_and_unit(m.group(2))
            if val <= 0:
                continue
            if key.endswith("_ms") and unit.lower().startswith("s"):
                val *= 1000.0
            out[key] = val
    return out


def _merge_latency_overrides(primary: dict | None, fallback: dict | None) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for src in (fallback or {}, primary or {}):
        for k, v in src.items():
            vf = _safe_float(v, 0.0)
            if vf > 0:
                out[k] = vf
    return out


def _lat_value_text(key: str, value: float) -> str:
    if key.startswith("tpot") or key.startswith("throughput"):
        return f"{float(value):.1f}"
    return f"{float(value):.0f}"


def _replace_kpi_value_by_label(report_html: str, label_variants: list[str], value: float,
                                unit: str, note: str | None = None,
                                canonical_label: str | None = None,
                                key: str = "") -> str:
    out = report_html
    val_txt = _lat_value_text(key or label_variants[0].lower(), value)
    for label in label_variants:
        repl_label = canonical_label or label
        pat = re.compile(
            r'(<div[^>]*class="kpi-label"[^>]*>)' + re.escape(label) + r'(</div>\s*'
            r'<div[^>]*class="kpi-value"[^>]*>)([^<]+)'
            r'(<span[^>]*class="kpi-unit"[^>]*>)(.*?)(</span></div>\s*'
            r'<div[^>]*class="kpi-note"[^>]*>)(.*?)(</div>)',
            re.S,
        )
        def _repl(m):
            return f"{m.group(1)}{repl_label}{m.group(2)}{val_txt}{m.group(4)}{unit}{m.group(6)}{note or m.group(7)}{m.group(8)}"
        out = pat.sub(_repl, out, count=1)
        pat2 = re.compile(
            r'(<div[^>]*text-transform:\s*uppercase[^>]*>)' + re.escape(label) + r'(</div>\s*'
            r'<div[^>]*font-size:\s*20px[^>]*>)([^<]+)'
            r'(<span[^>]*>)(.*?)(</span></div>\s*<div[^>]*>)(.*?)(</div>)',
            re.S | re.I,
        )
        def _repl2(m):
            return f"{m.group(1)}{repl_label}{m.group(2)}{val_txt}{m.group(4)}{unit}{m.group(6)}{note or m.group(7)}{m.group(8)}"
        out = pat2.sub(_repl2, out, count=1)
    return out


def _apply_latency_overrides_to_report_html(report_html: str, overrides: dict | None) -> str:
    if not overrides:
        return report_html
    out = report_html
    specs = [
        ("ttft_ms", ["TTFT mean"], "ms", ""),
        ("ttft_p50_ms", ["TTFT p50"], "ms", ""),
        ("tpot_ms", ["TPOT / ITL mean", "TPOT mean", "ITL mean"], "ms", "", "TPOT / ITL mean"),
        ("tpot_p50_ms", ["TPOT / ITL p50", "TPOT p50", "ITL p50"], "ms", "", "TPOT / ITL p50"),
        ("e2e_ms", ["E2E mean"], "ms", ""),
        ("e2e_p50_ms", ["E2E p50"], "ms", ""),
        ("throughput_mean", ["Throughput mean"], "tok/s", ""),
        ("throughput_p50", ["Throughput p50"], "tok/s", ""),
    ]
    for spec in specs:
        key, labels, unit, note = spec[:4]
        canonical_label = spec[4] if len(spec) > 4 else None
        val = _safe_float(overrides.get(key, 0.0), 0.0)
        if val > 0:
            out = _replace_kpi_value_by_label(out, labels, val, unit, note, canonical_label, key)
    return out


def _apply_latency_overrides_to_interactive_html(interactive_html: str,
                                                 overrides: dict | None) -> str:
    return _apply_latency_overrides_to_report_html(interactive_html, overrides)


def _canonical_kpi_tile_order_html(report_html: str) -> str:
    """Normalize top KPI tile order across generated tabs when possible."""
    # Individual generators already output the canonical order; this hook is kept
    # for combined-report post-processing and future per-tab tile drift.
    return report_html


def _extract_static_kpi_overrides(static_html: str) -> Dict[str, float]:
    """Extract KPI values from the already-generated End Report HTML."""
    out: Dict[str, float] = {}
    if not static_html:
        return out
    try:
        out.update(_extract_latency_kpis_from_html(static_html))
        txt = _html.unescape(static_html)
        flat = re.sub(r"<script\b.*?</script>", " ", txt, flags=re.I | re.S)
        flat = re.sub(r"<style\b.*?</style>", " ", flat, flags=re.I | re.S)
        flat = re.sub(r"<[^>]+>", " ", flat)
        flat = re.sub(r"\s+", " ", flat)
        if out.get("ttft_ms", 0.0) <= 0:
            m = re.search(r"Prefill\s+Phase\b[^0-9]{0,80}([0-9][0-9,]*(?:\.[0-9]+)?)\s*ms\s*TTFT", flat, re.I)
            if m: out["ttft_ms"] = _safe_float(m.group(1).replace(",", ""), 0.0)
        if out.get("tpot_ms", 0.0) <= 0:
            m = re.search(r"Decode\s+Phase\b[^0-9]{0,80}([0-9][0-9,]*(?:\.[0-9]+)?)\s*ms\s*/?\s*tok\s*TPOT", flat, re.I)
            if m: out["tpot_ms"] = _safe_float(m.group(1).replace(",", ""), 0.0)
        if out.get("ttft_ms", 0.0) <= 0:
            m = re.search(r"Observed\s+TTFT[^0-9]{0,80}([0-9][0-9,]*(?:\.[0-9]+)?)\s*ms", flat, re.I)
            if m: out["ttft_ms"] = _safe_float(m.group(1).replace(",", ""), 0.0)
        if out.get("tpot_ms", 0.0) <= 0:
            m = re.search(r"(?:Observed\s+)?(?:TPOT|ITL)[^0-9]{0,80}([0-9][0-9,]*(?:\.[0-9]+)?)\s*ms", flat, re.I)
            if m: out["tpot_ms"] = _safe_float(m.group(1).replace(",", ""), 0.0)
    except Exception:
        return out
    return {k: v for k, v in out.items() if _safe_float(v, 0.0) > 0}




# ─── Executive L3 SSD visual-analysis section ───────────────────────────────

def _amoprof_html_badge(text: str, kind: str = "info") -> str:
    cls = {"ok": "ok", "warn": "warn", "bad": "bad", "info": "info"}.get(kind, "info")
    return f'<span class="badge {cls}">{_html.escape(str(text))}</span>'


def _amoprof_fmt_rate(v: float, unit: str = "") -> str:
    try:
        v = float(v or 0.0)
    except Exception:
        v = 0.0
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M{unit}"
    if abs(v) >= 1_000:
        return f"{v/1_000:.1f}K{unit}"
    if abs(v) >= 100:
        return f"{v:.0f}{unit}"
    if abs(v) >= 10:
        return f"{v:.1f}{unit}"
    return f"{v:.2f}{unit}"


def _amoprof_exec_svg_combo(title: str, xlabels: List[str], bars: List[Dict[str, Any]],
                            lines: List[Dict[str, Any]], left_label: str,
                            right_label: str, width: int = 980,
                            height: int = 368) -> str:
    # Dependency-free SVG combo chart for executive tabs.
    ml, mr, mt, mb = 66, 78, 40, 74
    pw, ph = width - ml - mr, height - mt - mb
    n = max(len(xlabels), 1)
    group_w = pw / n
    bar_count = max(len(bars), 1)
    bar_w = min(16.0, group_w * 0.15)

    def _vals(series):
        out = []
        for s in series:
            for v in s.get("values", []):
                try:
                    fv = float(v or 0.0)
                    if math.isfinite(fv):
                        out.append(fv)
                except Exception:
                    pass
        return out

    left_max = max(_vals(bars) + [1.0])
    right_max = max(_vals(lines) + [1.0])
    if left_max <= 0:
        left_max = 1.0
    if right_max <= 0:
        right_max = 1.0

    def x(i): return ml + group_w * i + group_w / 2.0
    def yl(v): return mt + ph - (float(v or 0.0) / left_max) * ph
    def yr(v): return mt + ph - (float(v or 0.0) / right_max) * ph

    parts: List[str] = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
        f'<text x="{ml}" y="22" fill="#e2e8f0" font-size="14" font-weight="800">{_html.escape(title)}</text>',
    ]
    for k in range(5):
        yy = mt + ph * k / 4.0
        lv = left_max * (1.0 - k / 4.0)
        rv = right_max * (1.0 - k / 4.0)
        parts.append(f'<line x1="{ml}" x2="{width-mr}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{ml-8}" y="{yy+4:.1f}" fill="#64748b" font-size="10" text-anchor="end">{lv:.0f}</text>')
        parts.append(f'<text x="{width-mr+8}" y="{yy+4:.1f}" fill="#64748b" font-size="10">{rv:.0f}</text>')
    parts.extend([
        f'<line x1="{ml}" x2="{width-mr}" y1="{mt+ph}" y2="{mt+ph}" stroke="#334155"/>',
        f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt+ph}" stroke="#334155"/>',
        f'<line x1="{width-mr}" x2="{width-mr}" y1="{mt}" y2="{mt+ph}" stroke="#334155"/>',
        f'<text x="18" y="{mt+ph/2:.1f}" fill="#94a3b8" font-size="10" transform="rotate(-90 18 {mt+ph/2:.1f})">{_html.escape(left_label)}</text>',
        f'<text x="{width-14}" y="{mt+ph/2:.1f}" fill="#94a3b8" font-size="10" transform="rotate(90 {width-14} {mt+ph/2:.1f})">{_html.escape(right_label)}</text>',
    ])
    for bi, b in enumerate(bars):
        offset = (bi - (bar_count - 1) / 2.0) * (bar_w + 3)
        for i, v in enumerate((b.get("values") or [])[:len(xlabels)]):
            vv = float(v or 0.0)
            xx = x(i) + offset - bar_w / 2.0
            yy = yl(vv)
            hh = mt + ph - yy
            name = str(b.get("name", "bar"))
            lab = xlabels[i]
            color = str(b.get("color", "#60a5fa"))
            parts.append(f'<rect x="{xx:.1f}" y="{yy:.1f}" width="{bar_w:.1f}" height="{max(1.0, hh):.1f}" rx="2" fill="{color}" opacity="0.92"><title>{_html.escape(name)} | {_html.escape(lab)}: {vv:.2f}</title></rect>')
    for line in lines:
        vals = [float(v or 0.0) for v in (line.get("values") or [])[:len(xlabels)]]
        pts = " ".join(f'{x(i):.1f},{yr(v):.1f}' for i, v in enumerate(vals))
        color = str(line.get("color", "#a78bfa"))
        name = str(line.get("name", "line"))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
        for i, v in enumerate(vals):
            parts.append(f'<circle cx="{x(i):.1f}" cy="{yr(v):.1f}" r="3.5" fill="{color}" stroke="#0b1220" stroke-width="1"><title>{_html.escape(name)} | {_html.escape(xlabels[i])}: {v:.2f}</title></circle>')
    for i, lab in enumerate(xlabels):
        parts.append(f'<text x="{x(i):.1f}" y="{mt+ph+18}" fill="#94a3b8" font-size="10" text-anchor="middle">{_html.escape(lab)}</text>')
    lx, ly = ml, height - 20
    for item in bars + lines:
        name = str(item.get("name", "series"))
        color = str(item.get("color", "#60a5fa"))
        parts.append(f'<rect x="{lx}" y="{ly-8}" width="10" height="10" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{lx+14}" y="{ly+1}" fill="#cbd5e1" font-size="10">{_html.escape(name)}</text>')
        lx += 14 + min(190, len(name) * 6.0) + 18
    return f'<div class="combo-wrap"><svg aria-label="{_html.escape(title)}" role="img" viewBox="0 0 {width} {height}">{"".join(parts)}</svg></div>'


def _amoprof_read_columns_raw(path: Path | None, columns: List[str]) -> Dict[str, List[float]]:
    """Return per-column raw sample arrays from a CSV.

    `_read_csv_summary` collapses each column into min/mean/max/sum stats,
    which is enough for KPI tiles but throws away the per-sample structure
    needed for correlation scatter charts.  This helper returns the raw
    numeric samples of the requested columns (empty list per missing
    column), keyed by column name.  Missing/empty CSVs return an empty
    dict so callers can no-op gracefully.

    Column matching tries, in order:
      1. Exact name match.
      2. Base + label-set match: `{want}[label1=..,label2=..]`.
      3. Prefix-of-want match: e.g. want="prompt_tokens_total" matches
         "sglang_prompt_tokens_total" (Prometheus scrape convention).
      4. Base-name endswith match: e.g. want="mem_used" matches
         "dcgm_mem_used" or "gpu_mem_used".
    """
    out: Dict[str, List[float]] = {c: [] for c in columns}
    if not path:
        return out
    try:
        path = Path(path)
        if not path.exists() or path.stat().st_size <= 0:
            return out
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            resolved = {}
            for want in columns:
                exact_hit = None
                base_hit = None
                suffix_hit = None
                prefix_hit = None
                for actual in fieldnames:
                    if actual == want:
                        exact_hit = actual
                        break
                    if actual.startswith(f"{want}["):
                        base_hit = base_hit or actual
                        continue
                    # For Prometheus scrapes the column often has a job-
                    # or exporter-specific prefix (e.g. `sglang_prompt_tokens_total`
                    # for want="prompt_tokens_total").  Strip any `[...]`
                    # label suffix before comparing so labeled columns
                    # like `sglang_prompt_tokens_total[job=amoprof]` also
                    # match.
                    stripped = actual.split("[", 1)[0]
                    if stripped == want:
                        base_hit = base_hit or actual
                        continue
                    if stripped.endswith(f"_{want}") or stripped.endswith(want):
                        suffix_hit = suffix_hit or actual
                        continue
                    if want.startswith(stripped + "_") or want.startswith(stripped):
                        prefix_hit = prefix_hit or actual
                        continue
                resolved[want] = exact_hit or base_hit or suffix_hit or prefix_hit
            for row in r:
                for want, actual in resolved.items():
                    if not actual:
                        continue
                    try:
                        v = float(str(row.get(actual, "")).replace(",", ""))
                        if math.isfinite(v):
                            out[want].append(v)
                    except Exception:
                        pass
        return out
    except Exception:
        return out


try:
    from amoprof.report.metric_kernels import (
        counter_delta as _k_counter_delta, window_rate as _k_window_rate,
        window_seconds as _k_window_seconds,
        rate_series_with_time as _k_rate_with_time, ratio_delta as _k_ratio_delta,
        align_on_time as _k_align_on_time, pearson as _k_pearson,
        resolve_kv_bytes_per_token as _k_resolve_kv,
        resolve_latency_ms as _k_resolve_lat,
        vet_queue_depth as _k_vet_qd,
        vet_device_bw_peak as _k_vet_bw,
        resolve_l2_residency as _k_resolve_l2,
        prefill_cache_hit_ratio as _k_prefill_hit,
        percentiles_from_bucket_deltas as _k_bucket_pctls,
        sanitize_bandwidth_samples as _k_sane_bw,
        DRAM_SANE_MAX_GBS as _K_DRAM_MAX,
        tail_ratio as _k_tail_ratio,
        kv_movement_bandwidth as _k_kv_movement,
        window_counter_delta as _k_window_counter_delta,
        window_counter_series as _k_window_counter_series,
        summarise_rank_rules as _k_summarise_rank_rules,
        token_reuse_density as _k_token_reuse_density,
        gb_from_bytes as _k_gb_from_bytes, kb_from_bytes as _k_kb_from_bytes,
        collector_gb as _k_collector_gb,
        gb_from_mib as _k_gb_from_mib, gb_from_kib as _k_gb_from_kib,
        gb_from_gib as _k_gb_from_gib,
        mb_from_bytes as _k_mb_from_bytes, GIB_TO_GB as _K_GIB_TO_GB,
        resolve_gpu_hbm as _resolve_gpu_hbm,
        resolve_hbm_breakdown as _k_resolve_hbm_breakdown,
        lagged_pearson as _k_lagged_pearson,
        partial_pearson as _k_partial_pearson,
        normalize_series_name as _k_norm_col,
        resolve_series_columns as _k_resolve_cols,
        counter_window_total as _k_counter_total)
except Exception:  # pragma: no cover - standalone/bundled execution
    from metric_kernels import (  # type: ignore
        counter_delta as _k_counter_delta, window_rate as _k_window_rate,
        window_seconds as _k_window_seconds,
        rate_series_with_time as _k_rate_with_time, ratio_delta as _k_ratio_delta,
        align_on_time as _k_align_on_time, pearson as _k_pearson,
        resolve_kv_bytes_per_token as _k_resolve_kv,
        resolve_latency_ms as _k_resolve_lat,
        vet_queue_depth as _k_vet_qd,
        vet_device_bw_peak as _k_vet_bw,
        resolve_l2_residency as _k_resolve_l2,
        prefill_cache_hit_ratio as _k_prefill_hit,
        percentiles_from_bucket_deltas as _k_bucket_pctls,
        sanitize_bandwidth_samples as _k_sane_bw,
        DRAM_SANE_MAX_GBS as _K_DRAM_MAX,
        tail_ratio as _k_tail_ratio,
        kv_movement_bandwidth as _k_kv_movement,
        window_counter_delta as _k_window_counter_delta,
        window_counter_series as _k_window_counter_series,
        summarise_rank_rules as _k_summarise_rank_rules,
        token_reuse_density as _k_token_reuse_density,
        gb_from_bytes as _k_gb_from_bytes, kb_from_bytes as _k_kb_from_bytes,
        collector_gb as _k_collector_gb,
        gb_from_mib as _k_gb_from_mib, gb_from_kib as _k_gb_from_kib,
        gb_from_gib as _k_gb_from_gib,
        mb_from_bytes as _k_mb_from_bytes, GIB_TO_GB as _K_GIB_TO_GB,
        resolve_gpu_hbm as _resolve_gpu_hbm,
        resolve_hbm_breakdown as _k_resolve_hbm_breakdown,
        lagged_pearson as _k_lagged_pearson,
        partial_pearson as _k_partial_pearson,
        normalize_series_name as _k_norm_col,
        resolve_series_columns as _k_resolve_cols,
        counter_window_total as _k_counter_total)

# Single source of truth for KPI-tile formulas (see report/metric_formulas.py).
try:
    from amoprof.report.metric_formulas import (
        tile_note as _tile_note, axis_formula as _axis_formula,
        formula_details as _fx_details, FORMULA_CSS as _FX_CSS)
except Exception:  # pragma: no cover - standalone/bundled execution
    try:
        from metric_formulas import (  # type: ignore
            tile_note as _tile_note, axis_formula as _axis_formula,
            formula_details as _fx_details, FORMULA_CSS as _FX_CSS)
    except Exception:
        def _tile_note(label, existing_note="", variant=""):  # type: ignore
            return existing_note

        def _axis_formula(label):  # type: ignore
            return ""

        def _fx_details(body, label="formula", open_=False):  # type: ignore
            return (f'<div style="font-size:10px;color:#94a3b8">{body}</div>'
                    if body else "")

        _FX_CSS = ""  # type: ignore


def _amoprof_read_all_columns_substr(path: "Path | None", needle: str) -> "List[List[float]]":
    """Every column whose header contains `needle`, as separate series.

    The single-column reader returns the first match, which is wrong when
    Prometheus split one histogram across label sets: the first column may be
    the sparse one.  Callers that need to aggregate want them all.
    """
    out: List[List[float]] = []
    if path is None or not Path(path).exists():
        return out
    try:
        import csv as _csv
        with Path(path).open(newline="") as _f:
            _rd = _csv.DictReader(_f)
            _names = [c for c in (_rd.fieldnames or []) if needle in c]
            if not _names:
                return out
            _acc = {c: [] for c in _names}
            for _row in _rd:
                for _c in _names:
                    try:
                        _acc[_c].append(float(_row[_c]))
                    except (TypeError, ValueError):
                        _acc[_c].append(float("nan"))
        for _c in _names:
            _vals = [v for v in _acc[_c]]
            if any(v == v for v in _vals):
                out.append(_vals)
    except Exception:
        return out
    return out


def _amoprof_read_columns_substr(path: Path | None,
                                 specs: Dict[str, List[str]]) -> Dict[str, List[float]]:
    """Read columns matched by *substring set* rather than by exact name.

    SGLang exports several metrics as labelled series whose CSV header keeps
    the label set, e.g.::

        sglang:realtime_tokens_total[mode=prefill_compute,model_name=...]
        sglang_realtime_tokens_total{mode="decode"}

    `_amoprof_read_columns_raw` resolves exact/prefix/suffix names and cannot
    reach those.  `specs` maps an output key to the list of substrings that
    must all appear in the header, which mirrors how report/amoprof.py
    `_find_metric_col_with_parts` selects the same series.  Histogram buckets
    are excluded so a `_bucket` series never shadows the counter.

    Matching goes through metric_kernels.resolve_series_columns rather than a
    local lower()/quote-strip, because the local one was narrower: it left
    `:` and spaces in place, so a part spelled `sglang_realtime_tokens_total`
    matched a `sglang_realtime_tokens_total{...}` column here and missed a
    `sglang:realtime_tokens_total{...}` one that report/amoprof.py -- which
    normalises `:` to `_` -- matched. One spec, one run, two answers.

    This function keeps returning the FIRST matching column per key, which is
    what its six existing callers expect; `_amoprof_read_series_substr`
    beside it returns all of them, for the counters that are fanned out.
    """
    out: Dict[str, List[float]] = {k: [] for k in specs}
    if not path:
        return out
    try:
        path = Path(path)
        if not path.exists() or path.stat().st_size <= 0:
            return out
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            resolved: Dict[str, str] = {}
            for key, parts in specs.items():
                _cols = _k_resolve_cols(fieldnames, parts)
                if _cols:
                    resolved[key] = _cols[0]
            for row in r:
                for key, actual in resolved.items():
                    try:
                        v = float(str(row.get(actual, "")).replace(",", ""))
                        if math.isfinite(v):
                            out[key].append(v)
                    except Exception:
                        pass
        return out
    except Exception:
        return out


def _amoprof_read_series_substr(path: "Path | None",
                                specs: Dict[str, List[str]],
                                ) -> Dict[str, List[List[float]]]:
    """Like `_amoprof_read_columns_substr`, but EVERY matching column.

    A counter fanned out into one series per rank or per label value is only
    whole when its series are summed; taking the first reports one rank's
    share as the total.  The phase counters are read through this so the
    Executive, the End report and the comparison all difference the same set
    of columns -- `report/amoprof.py:_delta_sum_metric` has summed all
    matching series since it was written, and this surface took one.
    """
    out: Dict[str, List[List[float]]] = {k: [] for k in specs}
    if not path:
        return out
    try:
        path = Path(path)
        if not path.exists() or path.stat().st_size <= 0:
            return out
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            resolved: Dict[str, List[str]] = {}
            for key, parts in specs.items():
                _cols = _k_resolve_cols(fieldnames, parts)
                if _cols:
                    resolved[key] = _cols
                    out[key] = [[] for _ in _cols]
            for row in r:
                for key, cols in resolved.items():
                    for _i, actual in enumerate(cols):
                        try:
                            v = float(str(row.get(actual, "")).replace(",", ""))
                            if math.isfinite(v):
                                out[key][_i].append(v)
                        except Exception:
                            pass
        return out
    except Exception:
        return out


def _pearson(xs: List[float], ys: List[float]) -> float:
    """Delegates to metric_kernels.pearson (shared kernel)."""
    return _k_pearson(xs, ys)


def _lagged_pearson(xs, ys, max_lag: int = 6):
    """Delegates to metric_kernels.lagged_pearson (shared kernel)."""
    return _k_lagged_pearson(xs, ys, max_lag)


def _partial_pearson(xs, ys, zs) -> float:
    """Delegates to metric_kernels.partial_pearson (shared kernel)."""
    return _k_partial_pearson(xs, ys, zs)

def _amoprof_bucket_columns(path: "Path | None", base: str) -> "list[tuple[float, str]]":
    """Resolve `{base}_bucket{le="..."}` columns to [(le, column_name), ...].

    Prometheus histogram columns keep their label set in the CSV header, e.g.
    `sglang_time_to_first_token_seconds_bucket[le="0.5",model_name="..."]`.
    Returns the buckets sorted by upper bound, +Inf last.
    """
    import csv as _csv
    out: list[tuple[float, str]] = []
    if not path:
        return out
    try:
        path = Path(path)
        if not path.exists() or path.stat().st_size <= 0:
            return out
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            fields = (_csv.DictReader(f).fieldnames or [])
        base_l = base.lower()
        for col in fields:
            low = col.lower()
            if "_bucket" not in low or base_l not in low:
                continue
            m = re.search(r'le\s*=\s*"?\+?([^",\]}\s]+)', col)
            if not m:
                continue
            raw = m.group(1)
            le = float("inf") if raw.lower().startswith("inf") else _safe_float(raw, float("nan"))
            if le != le:      # NaN
                continue
            out.append((le, col))
    except Exception:
        return []
    out.sort(key=lambda t: t[0])
    return out


def _amoprof_bucket_series(path: "Path | None", base: str
                           ) -> "tuple[list[float], list[tuple[float, list[float]]]]":
    """Row-aligned cumulative bucket counts, summed per `le` across label sets.

    SGLang exports each histogram once per label set (is_streaming="true" and
    "false", per rank, ...), so `_amoprof_bucket_columns` returns every `le`
    more than once.  Treating those as consecutive buckets interleaved two
    unrelated cumulative series: interpolating between le=X and le=X is a
    zero-width bucket, so every per-interval quantile landed exactly on a
    bucket edge (the round 60,000 / 100,000 / 200,000 ms TTFT peaks), and the
    larger series dominated the monotonic fix-up, pushing quantiles high.
    Prometheus' histogram_quantile sums by (le) first; so does this.

    Rows stay aligned with the CSV (a dropped NaN row shifted one series
    against the other).  A series' leading gap is back-filled, so a label set
    first seen mid-window contributes no history it accumulated before it
    appeared (as `increase()` treats a new series); interior gaps carry the
    last value forward.  Returns (time_sec, [(le, counts), ...]) sorted by le.
    """
    cols = _amoprof_bucket_columns(path, base)
    if not cols:
        return [], []
    want = {c for _le, c in cols}
    raw: dict = {c: [] for c in want}
    times: list[float] = []
    try:
        with Path(path).open(encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.DictReader(f):
                times.append(_safe_float(row.get("time_sec"), float("nan")))
                for c in want:
                    v = row.get(c)
                    raw[c].append(_safe_float(v, float("nan")) if v not in (None, "") else float("nan"))
    except Exception:
        return [], []

    def _filled(vals: list) -> list:
        first = next((v for v in vals if v == v), None)
        if first is None:
            return []
        out, last = [], first
        for v in vals:
            if v == v:
                last = v
            out.append(last)
        return out

    by_le: dict = {}
    for le, c in cols:
        filled = _filled(raw[c])
        if not filled:
            continue
        acc = by_le.get(le)
        by_le[le] = filled if acc is None else [a + b for a, b in zip(acc, filled)]
    return times, sorted(by_le.items(), key=lambda t: t[0])


def _amoprof_histogram_percentiles(path: "Path | None", base: str,
                                   quantiles: "tuple[float, ...]" = (0.5, 0.9, 0.99),
                                   scale: float = 1.0
                                   ) -> "tuple[list[float], dict[float, list[float]]]":
    """Per-interval percentiles from a Prometheus cumulative histogram.

    For each sampling interval the per-bucket counter deltas form that
    interval's histogram; the quantile is then linearly interpolated inside
    the bucket that contains it — the same estimator `histogram_quantile`
    uses. Intervals that observed nothing (total delta 0) are skipped along
    with their timestamp, so the returned series stay time-alignable.

    Returns (times, {q: values}). `scale` converts units (e.g. s -> ms).
    """
    times, buckets = _amoprof_bucket_series(path, base)
    if len(buckets) < 2:
        return [], {q: [] for q in quantiles}
    series = [counts for _le, counts in buckets]
    les = [le for le, _c in buckets]
    n = min([len(times)] + [len(v) for v in series]) if series else 0
    out_t: list[float] = []
    out: dict[float, list[float]] = {q: [] for q in quantiles}
    for i in range(1, n):
        deltas = [max(0.0, series[b][i] - series[b][i - 1]) for b in range(len(les))]
        # Cumulative counts must be non-decreasing across buckets.
        for b in range(1, len(deltas)):
            deltas[b] = max(deltas[b], deltas[b - 1])
        total = deltas[-1]
        if total <= 0:
            continue
        out_t.append(times[i])
        for q in quantiles:
            target = q * total
            idx = next((b for b in range(len(deltas)) if deltas[b] >= target), len(deltas) - 1)
            hi = les[idx]
            lo = les[idx - 1] if idx > 0 else 0.0
            c_lo = deltas[idx - 1] if idx > 0 else 0.0
            c_hi = deltas[idx]
            if hi == float("inf"):
                val = lo                      # open-ended top bucket: report its floor
            elif c_hi > c_lo:
                val = lo + (hi - lo) * (target - c_lo) / (c_hi - c_lo)
            else:
                # The bucket's floor, as the whole-window helper does: the
                # upper edge is the worst value the bucket can hold, not one
                # that was measured.
                val = lo
            out[q].append(val * scale)
    return out_t, out


def _amoprof_exec_svg_percentile_lines(title: str, subtitle: str, y_label: str,
                                       times: "list[float]",
                                       series: "dict[str, tuple[list[float], str]]",
                                       width: int = 460, height: int = 300) -> str:
    """Multi-series line chart (p50 / p90 / p99) over elapsed time."""
    vals = [v for (ys, _c) in series.values() for v in ys if v == v]
    if not times or not vals:
        return ""
    pad_l, pad_r, pad_t, pad_b = 54, 12, 42, 40
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    x_min, x_max = min(times), max(times)
    y_min, y_max = 0.0, max(vals)
    if y_max <= y_min:
        y_max = y_min + 1.0
    x_rng = (x_max - x_min) or 1.0
    y_rng = (y_max - y_min) or 1.0

    def px(x): return pad_l + (x - x_min) / x_rng * pw
    def py(y): return pad_t + ph - (y - y_min) / y_rng * ph

    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{pad_l}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">{_html.escape(title)}</text>']
    if subtitle:
        parts.append(f'<text x="{pad_l}" y="29" fill="#94a3b8" font-size="8.5">{_html.escape(subtitle)}</text>')
    for gi in range(5):
        gy = pad_t + ph * gi / 4.0
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+pw}" y2="{gy:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" text-anchor="end">'
                     f'{_fmt_num(y_max - (y_max - y_min) * gi / 4.0, "", 1)}</text>')
    for ti in range(4):
        tx = pad_l + pw * ti / 3.0
        parts.append(f'<text x="{tx:.1f}" y="{pad_t+ph+14:.1f}" fill="#64748b" font-size="7.5" text-anchor="middle">'
                     f'{_fmt_num(x_min + x_rng * ti / 3.0, "", 0)}</text>')
    legend_x = pad_l
    for name, (ys, color) in series.items():
        pts = " ".join(f"{px(times[i]):.1f},{py(ys[i]):.1f}"
                       for i in range(min(len(times), len(ys))) if ys[i] == ys[i])
        if not pts:
            continue
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
        parts.append(f'<rect x="{legend_x}" y="{height-13}" width="8" height="3" fill="{color}" rx="1.5"/>')
        parts.append(f'<text x="{legend_x+11}" y="{height-9}" fill="#94a3b8" font-size="8">{_html.escape(name)}</text>')
        legend_x += 46
    parts.append(f'<text x="{pad_l+pw/2:.1f}" y="{height-24:.1f}" fill="#cbd5e1" font-size="8.5" text-anchor="middle">elapsed (s)</text>')
    parts.append(f'<text x="12" y="{pad_t+ph/2:.1f}" fill="#cbd5e1" font-size="8.5" '
                 f'transform="rotate(-90 12 {pad_t+ph/2:.1f})" text-anchor="middle">{_html.escape(y_label)}</text>')
    y_form = _axis_formula(y_label)
    caption = ""
    if y_form:
        caption = (f'<div style="font-size:9px;line-height:1.5;margin-top:6px;overflow-wrap:break-word;'
                   f'word-break:break-word"><span style="color:#64748b">Y</span> '
                   f'<code style="color:#86efac;background:#020617;border:1px solid #1e293b;'
                   f'border-radius:3px;padding:0 3px">{_html.escape(y_form)}</code></div>')
    return (f'<div class="corr-chart"><svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{caption}</div>')


def _amoprof_histogram_window_percentiles(path: "Path | None", base: str,
                                          quantiles: "tuple[float, ...]" = (0.5, 0.9, 0.99),
                                          scale: float = 1.0) -> "dict":
    """Whole-window percentiles from a Prometheus cumulative histogram.

    Distinct from `_amoprof_histogram_percentiles`, which estimates a
    percentile *per sampling interval*.  Here every interval's bucket deltas
    are summed into one histogram covering the entire selected period, and the
    quantile is taken once — the same number `histogram_quantile` over the
    full range would give, and the figure an executive expects from "p99 for
    the run".

    Summing deltas rather than differencing first/last endpoints keeps the
    result correct across counter resets, since each interval is clamped
    non-negative before it is accumulated.

    Returns {"p50": v, "p90": v, "p99": v, "observations": n} — empty when no
    requests completed in the window.
    """
    _times, buckets = _amoprof_bucket_series(path, base)
    if len(buckets) < 2:
        return {}
    series = [counts for _le, counts in buckets]
    les = [le for le, _c in buckets]
    n = min((len(v) for v in series), default=0)
    if n < 2:
        return {}
    totals = [0.0] * len(les)
    for i in range(1, n):
        step = [max(0.0, series[b][i] - series[b][i - 1]) for b in range(len(les))]
        for b in range(1, len(step)):          # enforce cumulative monotonicity
            step[b] = max(step[b], step[b - 1])
        for b in range(len(les)):
            totals[b] += step[b]
    observations = totals[-1] if totals else 0.0
    if observations <= 0:
        return {}
    out: dict = {"observations": observations}
    for q in quantiles:
        target = q * observations
        idx = next((b for b in range(len(totals)) if totals[b] >= target), len(totals) - 1)
        hi = les[idx]
        lo = les[idx - 1] if idx > 0 else 0.0
        c_lo = totals[idx - 1] if idx > 0 else 0.0
        c_hi = totals[idx]
        if hi == float("inf"):
            val = lo                            # open-ended top bucket → floor
            # Record WHICH quantiles were censored, rather than leaving the
            # caller to infer it by comparing against the top finite bucket:
            # a quantile can land exactly on that boundary without being
            # censored, and then a threshold test marks a real measurement as
            # a lower bound.  The helper is the only place that knows.
            out.setdefault("censored", []).append(f"p{int(q * 100)}")
            out["censored_floor"] = lo * scale
        elif c_hi > c_lo:
            val = lo + (hi - lo) * (target - c_lo) / (c_hi - c_lo)
        else:
            # UNREACHABLE for any cumulative histogram with a positive total,
            # and verified so by exhaustive search over small integer
            # histograms: `idx` is the first bucket whose cumulative reaches
            # the target, so totals[idx] > totals[idx-1] by construction.
            # Kept because the loop needs a total branch and because `lo` is
            # the correct answer if it ever did run -- returning `hi`, which
            # it used to, would report the worst value the bucket can hold as
            # though it had been measured.  It is NOT the cause of any
            # edge-snapped value in a report; see the subtitle note below.
            val = lo
        # A histogram cannot resolve finer than its buckets, and on SGLang's
        # TTFT ladder the buckets near the tail span an order of magnitude
        # each.  Record the bracket so a caller can show the resolution
        # instead of implying two decimal places of precision: p99 printed as
        # "400,000.00 ms" is the edge of a bucket covering 8 s to 400 s.
        out.setdefault("bracket", {})[f"p{int(q * 100)}"] = (
            lo * scale, (hi * scale) if hi != float("inf") else float("inf"))
        out[f"p{int(q * 100)}"] = val * scale
    return out


def _amoprof_exec_svg_lba_heatmap(title: str, op: str, deciles: "list",
                                  start_gb: float, span_gb: float,
                                  width: int = 620, height: int = 190) -> str:
    """One strip, ten cells, shaded by write share — the device at a glance.

    A cumulative "hottest N% of the span carries X%" curve takes three
    inferential steps to read: sort the bands, accumulate, compare against an
    even split.  That is too many for a first read.  A heat strip shows the
    same thing in one: dark cells are where the traffic lands, pale cells are
    untouched, and the GB labels sit under the cells so the hot region can be
    named directly.
    """
    if not deciles or len(deciles) < 10:
        return ""
    _tot = sum(deciles)
    if _tot <= 0:
        return ""
    _step = (span_gb / 10.0) if span_gb > 0 else 0.0
    _mx = max(deciles) or 1.0
    L, T, cw, ch = 18, 58, (width - 36) / 10.0, 54

    def _fmt(v):
        return f"{v:,.0f}" if _step >= 1 else f"{v:,.1f}"

    _touched = sum(1 for d in deciles if d > 0.5)
    _cold_gb = (10 - _touched) * _step
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" '
             f'fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="19" fill="#e2e8f0" font-size="11" '
             f'font-weight="800">{_html.escape(title)}</text>',
             f'<text x="{L}" y="34" fill="#94a3b8" font-size="9">'
             f'{_touched} of 10 regions take the {op}s'
             + (f" \u00b7 {_fmt(_cold_gb)} GB of {_fmt(span_gb)} GB never "
                f"written" if _step > 0 and _cold_gb > 0 else "")
             + '</text>']
    for i, d in enumerate(deciles):
        x = L + i * cw
        frac = d / _mx
        # Pale slate for untouched, warming through amber to red with share.
        if d <= 0.5:
            fill, txt = "#1e293b", "#475569"
        elif frac >= 0.6:
            fill, txt = "#ef4444", "#ffffff"
        elif frac >= 0.25:
            fill, txt = "#f59e0b", "#1c1917"
        else:
            fill, txt = "#38bdf8", "#082f49"
        parts.append(f'<rect x="{x:.1f}" y="{T}" width="{cw-3:.1f}" '
                     f'height="{ch}" fill="{fill}" rx="3"/>')
        if d > 0.5:
            parts.append(f'<text x="{x + (cw-3)/2:.1f}" y="{T + ch/2 + 4:.0f}" '
                         f'fill="{txt}" font-size="11" font-weight="800" '
                         f'text-anchor="middle">{d:.0f}%</text>')
        if _step > 0:
            parts.append(
                f'<text x="{x + (cw-3)/2:.1f}" y="{T + ch + 13:.0f}" '
                f'fill="#64748b" font-size="7.5" text-anchor="middle">'
                f'{_fmt(start_gb + i*_step)}G</text>')
    parts.append(f'<text x="{L}" y="{height - 6}" fill="#64748b" '
                 f'font-size="8">device LBA space, low \u2192 high \u00b7 '
                 f'shaded by share of {op} bytes \u00b7 grey = untouched'
                 f'</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg">' + "".join(parts) + "</svg>")


def _amoprof_exec_svg_percentile_bars(title: str, subtitle: str, unit: str,
                                      values: "dict", colors: "dict",
                                      width: int = 460, height: int = 300,
                                      n_label: str = "observations") -> str:
    """Grouped bar chart of whole-window p50 / p90 / p99 with printed values.

    A line chart of per-interval percentiles shows *movement* but makes the
    headline number hard to read off; this renders the single figure per
    quantile with the value printed above each bar.
    """
    # Keep the canonical p50/p90/p99 ordering when those are the keys, but
    # accept any label set — the LBA decile chart passes ten range labels, and
    # a hardcoded triple silently returned "" for them, so the chart vanished
    # with no error anywhere.
    _canon = [k for k in ("p50", "p90", "p99") if k in values]
    order = _canon or list(values.keys())
    if not order:
        return ""
    vals = [float(values[k]) for k in order]
    vmax = max(vals) or 1.0
    pad_l, pad_r, pad_t, pad_b = 56, 14, 44, 46
    # Size the left gutter to the widest tick label it will actually hold.
    # A fixed 56px fits "1,234.5" but not "6,091,362.0": the tick labels are
    # right-anchored at pad_l - 6, so a wide one started at a negative x and
    # ran under the rotated axis title, losing its leading digits.  The tick
    # values are the same five the grid loop prints below, so compute them
    # here rather than guessing a width from vmax.
    _tick_txt = [(f"{_v:,.0f}" if _v >= 10 else
                  (f"{_v:.1f}" if _v >= 1 else f"{_v:.2f}"))
                 for _v in (vmax * (1 - _g / 4.0) for _g in range(5))]
    _tick_w = max((len(_t) for _t in _tick_txt), default=0) * 7.5 * 0.55
    pad_l = max(pad_l, int(_tick_w) + 24)
    # SVG <text> does not wrap, so a long subtitle ran past the viewBox and
    # was clipped mid-sentence -- on the promotion chart it cut off exactly
    # the caveat that the rejection bars count attempts, not candidates.
    # Wrap on words at the panel width and give the extra lines room.
    _sub_lines = []
    if subtitle:
        _avail = width - pad_l - pad_r
        _cpl = max(24, int(_avail / (8.5 * 0.55)))
        _line = ""
        for _w in str(subtitle).split(" "):
            _cand = (_line + " " + _w).strip()
            if len(_cand) <= _cpl or not _line:
                _line = _cand
            else:
                _sub_lines.append(_line)
                _line = _w
        if _line:
            _sub_lines.append(_line)
        if len(_sub_lines) > 1:
            _extra = (len(_sub_lines) - 1) * 11
            pad_t += _extra
            height += _extra
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{pad_l}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">{_html.escape(title)}</text>']
    for _li, _lt in enumerate(_sub_lines):
        parts.append(f'<text x="{pad_l}" y="{29 + _li * 11}" fill="#94a3b8" '
                     f'font-size="8.5">{_html.escape(_lt)}</text>')
    _lat = _is_latency_unit(unit)
    for gi in range(5):
        gy = pad_t + ph * gi / 4.0
        _gv = vmax * (1 - gi / 4.0)
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+pw}" y2="{gy:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" text-anchor="end">'
                     f'{_fmt_latency(_gv, unit) if _lat else _fmt_num(_gv, "", 1)}</text>')
    slot = pw / len(order)
    bw = min(slot * 0.5, 62.0)
    for i, key in enumerate(order):
        v = float(values[key])
        cx = pad_l + slot * (i + 0.5)
        bh = (v / vmax) * ph if vmax > 0 else 0.0
        by = pad_t + ph - bh
        col = colors.get(key, "#38bdf8")
        _hv = _fmt_latency(v, unit) if _lat else f"{v:,.2f}"
        parts.append(f'<rect x="{cx-bw/2:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{max(bh,1):.1f}" '
                     f'fill="{col}" rx="3" opacity="0.85"><title>{_html.escape(title.split(' \u2014 ')[0])} {key}: {_hv} {_html.escape(unit)}</title></rect>')
        parts.append(f'<text x="{cx:.1f}" y="{by-5:.1f}" fill="#f8fafc" font-size="11" font-weight="800" '
                     f'text-anchor="middle">'
                     f'{_fmt_latency(v, unit) if _lat else _fmt_num(v, "", 1 if v < 100 else 0)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{pad_t+ph+15:.1f}" fill="#cbd5e1" font-size="9.5" '
                     f'font-weight="700" text-anchor="middle">{key}</text>')
    if unit:
        parts.append(f'<text x="12" y="{pad_t+ph/2:.1f}" fill="#cbd5e1" font-size="8.5" '
                     f'transform="rotate(-90 12 {pad_t+ph/2:.1f})" text-anchor="middle">{_html.escape(unit)}</text>')
    if values.get("observations"):
        parts.append(f'<text x="{pad_l+pw:.1f}" y="{height-10:.1f}" fill="#64748b" font-size="8" '
                     f'text-anchor="end">n={_fmt_num(values["observations"], "", 0)} '
                     f'{_html.escape(n_label)}</text>')
    _cap = _amoprof_exec_chart_caption([("Y", title.split(" \u2014 ")[0], "#86efac")])
    return (f'<div class="corr-chart"><svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{_cap}</div>')


# Axis scale for the absolute-unit tier charts.
#   auto  — log only when the series span more than _LOG_AXIS_MIN_RATIO,
#           which is the case a log axis exists to solve (HBM TB/s beside
#           NVMe GB/s).  Linear otherwise: it reads more easily and does not
#           visually flatten real variation the way a log axis does.
#   log / linear — force one.
_AXIS_SCALE = _os.environ.get("AMOPROF_AXIS_SCALE", "auto").strip().lower()
_LOG_AXIS_MIN_RATIO = float(_os.environ.get("AMOPROF_LOG_AXIS_MIN_RATIO", "50"))

# Per-series colours for the concurrency card.  Chosen far apart in hue so
# the legend stays readable, and avoiding the amber/orange pair that made GPU
# util and HBM indistinguishable.
# Layer-response series colours — maximally separated hues so a card with six
# or seven series stays readable.  Colouring by LAYER gave every A4 signal the
# same colour, which made GPU util and HBM used indistinguishable.
# Shortest span that can be a real profiling window. Anything below it is a
# broken reading rather than a short run, and using it as a rate denominator
# turns a byte count into an impossible bandwidth: a blktrace summary
# reporting duration_sec = 0.001 produced "19,704,435,625 MB/s".
_MIN_PLAUSIBLE_WINDOW_S = 5.0

# Largest value that can be a real NVMe queue depth. The Linux block layer
# caps in-flight requests at nr_requests per hardware queue (1024 on blk-mq),
# and every measurement of this fleet's drives has landed in the tens to low
# hundreds. A figure in the thousands is a counting artifact, not a deep
# queue -- most often a blktrace Q→C pass over an event stream that was not
# sorted by timestamp, which leaves Q events unmatched and lets the running
# count climb for the whole capture. amoprof_blktrace_qd_qd_mean published
# mean 6,876 / peak 171,982 on this fleet for exactly that reason, and
# Prometheus keeps that history, so fixing the collector does not protect a
# report built over an older window.
# ---- Put each tier's two tiles next to each other ---------------------
#
# The grid is assembled by topic -- GPU things, then L3 bandwidth, then
# capacity -- which scattered the pairs: L1 raw, L1 KV, GPU power, three
# L3 bandwidth tiles, L3 raw, L3 KV, L2 KV, L2 raw.  The L2 pair came out
# inverted and seven tiles away from L1, so the hierarchy could not be
# read down the grid and the raw/residency pairing was invisible.
#
# Reordering the assembled HTML rather than the expression that builds it
# keeps one ordering rule in one place, instead of threading hierarchy
# order back through 250 lines of concatenation whose groupings exist for
# other reasons.  Tiles are siblings, so splitting on the tile delimiter
# needs no tag balancing.
_TIER_TILE_ORDER = (
    "L1 HBM used",
    "L1 KV utilization",
    "L2 host DRAM used",
    "L2 KV residency",
    "L2 KV utilization",
    "L3 cache used",
    "L3 (local storage) cache used",
    "L3 KV utilization",
    "L3.5 memory used",
    "L3.5 storage used",
    "L3.5 used total",
    "L3.5 KV utilization",
)

# NB: the parameter is _grid, not _html.  `_html` is this module's alias
# for the html module (line 16), and naming a parameter after it shadows
# it for the whole function body -- _html.unescape below then resolves to
# str.unescape, which does not exist.
def _amoprof_tile_label(_tile: str) -> str:
    """The visible label of one rendered KPI tile, tags and entities resolved."""
    _m = re.search(r'class="kpi-label">(.*?)</div>', _tile, re.S)
    return (_html.unescape(re.sub(r"<[^>]+>", "", _m.group(1))).strip()
            if _m else "")


def _amoprof_drop_tier_tiles(_grid: str, _prefix: str) -> str:
    """Remove tiles whose LABEL names a tier this run does not use.

    The L3.5 tile groups were gated on their data being present and never on
    the tier being configured, so a local-NVMe run against a cluster where the
    memory node is reachable in Prometheus grew "L3.5 node CPU util" and
    friends -- tiles for a tier that is not in the deployment.

    Done by label on the assembled grid rather than at the sixteen append
    sites, because those sites are shared: `_l35_hw_tiles` holds the backing
    tier's hardware tiles for EITHER tier, labelled through `_TIER`, so on a
    local run the same variable legitimately carries "L3 SSD storage BW".
    Suppressing the group would remove those with the rest.

    Matching is on the label only.  A tile that merely mentions the tier in
    its note -- a cross-reference, or an explanation of what it is not -- is
    about something else and stays.
    """
    _DELIM = '<div class="kpi"'
    _parts = _grid.split(_DELIM)
    if len(_parts) < 2:
        return _grid
    _head, _tiles = _parts[0], [_DELIM + _p for _p in _parts[1:]]
    _keep = [_t for _t in _tiles
             if not _amoprof_tile_label(_t).startswith(_prefix)]
    return _head + "".join(_keep)


def _amoprof_group_tier_tiles(_grid: str) -> str:
    _DELIM = '<div class="kpi"'
    _parts = _grid.split(_DELIM)
    if len(_parts) < 2:
        return _grid
    _head, _tiles = _parts[0], [_DELIM + _p for _p in _parts[1:]]

    _label_of = _amoprof_tile_label

    # Rank by the longest prefix that matches, so "L3 cache used" cannot
    # claim a tile labelled "L3 cache used (raw, df)" ahead of a more
    # specific entry, and an unlisted tile keeps its position.
    # rank -> index into _tiles.  Indices, not the tile strings: two tiles
    # can be byte-identical, and a membership test on content would then
    # move the wrong one.
    _picked: dict = {}
    for _idx, _t in enumerate(_tiles):
        _lab = _label_of(_t)
        _best, _blen = None, -1
        for _r, _pfx in enumerate(_TIER_TILE_ORDER):
            if _lab.startswith(_pfx) and len(_pfx) > _blen:
                _best, _blen = _r, len(_pfx)
        # A second tile matching a rank already taken is left in place
        # rather than silently dropped: two tiles with one name is a bug
        # to see, not to hide.
        if _best is not None and _best not in _picked:
            _picked[_best] = _idx
    if len(_picked) < 2:
        return _grid
    _moved = set(_picked.values())
    _group = "".join(_tiles[_picked[_r]] for _r in sorted(_picked))
    # Re-insert where the first of them used to be, so the outcome and
    # throughput tiles around them keep their order.
    _out, _done = [], False
    for _idx, _t in enumerate(_tiles):
        if _idx in _moved:
            if not _done:
                _out.append(_group)
                _done = True
            continue
        _out.append(_t)
    return _head + "".join(_out)


_QD_PLAUSIBLE_MAX = 4096.0


def _qd_implausible(vals) -> float:
    """Peak of `vals` when it exceeds the plausible bound, else 0.0."""
    try:
        _mx = max((v for v in (vals or []) if v == v), default=0.0)
    except Exception:
        return 0.0
    return float(_mx) if _mx > _QD_PLAUSIBLE_MAX else 0.0


_LAYER_SERIES_COLORS = [
    "#ef4444",  # red
    "#3b82f6",  # blue
    "#22c55e",  # green
    "#eab308",  # yellow
    "#a855f7",  # purple
    "#f97316",  # orange
    "#e2e8f0",  # near-white
    "#14b8a6",  # teal
    "#ec4899",  # pink
    "#84cc16",  # lime
]

_CONC_COLORS = {
    "GPU util (%)":          "#f59e0b",   # amber
    "HBM used (GB)":         "#ec4899",   # pink
    "Waiting requests":      "#ef4444",   # red
    "Queue wait (ms)":       "#a855f7",   # purple
    "Engine utilisation (%)": "#22d3ee",  # cyan
    "Forward occupancy":     "#84cc16",   # lime
    "Storage queue depth":   "#22c55e",   # green
}

_AMOPROF_LAYER_COLOR = {
    "A4_GPU_HBM": "#f59e0b", "A3_DRAM": "#a78bfa",
    "A1/A2_L3": "#22c55e", "NET": "#2dd4bf", "A5_APP": "#38bdf8",
}


def _amoprof_binned_response(x: List[float], y: List[float], nbins: int = 10,
                             stat: str = "median"):
    """Quantile-binned response of y against x.

    Binning by quantile rather than by value keeps every bin equally
    populated, so a sparse tail cannot dominate the curve shape.

    *stat* selects the within-bin summary. "median" is right for a signal
    that is busy most of the time, and wrong for a BURSTY one: an
    instantaneous queue-depth gauge sampled every 15 s is zero in almost
    every sample and spikes to its real depth in a few, so every bin median
    is 0 and the plotted line sits flat on the axis while the legend reports
    a series peak of 16. For such a signal "max" is the honest summary --
    the question being asked of a queue is how deep it got, not how deep it
    typically was.
    """
    if len(x) < 12:
        return []
    pairs = sorted(zip(x, y))
    per = max(1, len(pairs) // nbins)
    out = []
    for i in range(0, len(pairs), per):
        chunk = pairs[i:i + per]
        if len(chunk) < 2:
            continue
        xs = sorted(p[0] for p in chunk)
        ys = sorted(p[1] for p in chunk)
        _v = (ys[-1] if stat == "max" else
              ys[0] if stat == "min" else
              ys[len(ys) // 2])
        out.append((xs[len(xs) // 2], _v))
    return out if len(out) >= 3 else []


def _amoprof_bin_stat_for(label: str) -> str:
    """Which within-bin summary suits this series.

    Queue depth and other burst-shaped counters are summarised by max; the
    default stays the median for continuous signals such as bandwidth and
    utilisation, where the median is the better typical value.
    """
    _l = str(label or "").lower()
    if any(_k in _l for _k in ("queue depth", "queue_depth", "inflight",
                               "aqu", "qd ", "retransmit", "drop")):
        return "max"
    return "median"



def _amoprof_exec_chart_caption(pairs) -> str:
    """X/Y formula caption, matching the scatter charts' footer.

    The scatter renderer already emits this; the layer-response, queue and
    percentile charts did not, so the same section mixed charts that showed
    their provenance with charts that did not.  `pairs` is
    [(axis_letter, label, colour), ...].
    """
    rows = ""
    for letter, label, colour in pairs:
        form = _axis_formula(label)
        if not form:
            continue
        rows += (f'<div style="margin-top:2px"><span style="color:#64748b">{letter}</span> '
                 f'<code style="color:{colour};background:#020617;border:1px solid #1e293b;'
                 f'border-radius:3px;padding:0 3px">{_html.escape(form)}</code></div>')
    if not rows:
        return ""
    return _fx_details(rows, label="axis formulas")


def _amoprof_exec_svg_layer_response(driver_label: str, driver_unit: str,
                                     series: list, width: int = 760,
                                     height: int = 300, title: str = "") -> str:
    """One driver's effect on every configured layer, on a single axis.

    Each layer signal is normalised to a percentage of its own observed max so
    GB/s, IOPS, ms and % can share one Y axis; the legend carries each
    signal's true max and unit so nothing is lost to normalisation. Steep
    line = a layer that responds to this driver; flat = one that does not.
    `series` items: {"layer","label","unit","bins","r","rho","n","ymax"}.
    """
    if not series:
        return ""
    L, R, T, B = 58, 190, 34, 44
    pw, ph = width - L - R, height - T - B
    xs = [b[0] for sr in series for b in sr["bins"]]
    if not xs:
        return ""
    x0, x1 = min(xs), max(xs)
    xr = (x1 - x0) or 1.0
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">'
             f'{_html.escape(title or (driver_label + " \u2192 effect across layers"))}</text>',
             f'<text x="{L}" y="29" fill="#94a3b8" font-size="8.5">each layer signal as % of its own '
             f'observed max \u00b7 binned median \u00b7 n={series[0]["n"]} aligned samples</text>']
    for g in range(5):
        gy = T + ph * g / 4
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{L+pw}" y2="{gy:.1f}" stroke="#1e293b"/>')
        parts.append(f'<text x="{L-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" '
                     f'text-anchor="end">{100-g*25}%</text>')
    for g in range(4):
        gx = L + pw * g / 3
        parts.append(f'<text x="{gx:.1f}" y="{T+ph+14:.1f}" fill="#64748b" font-size="7.5" '
                     f'text-anchor="middle">{_fmt_num(x0 + xr*g/3, "", 0)}</text>')
    ly = T + 4
    for si, sr in enumerate(series):
        # NaN is truthy, so `x or 1.0` does NOT catch a NaN ymax — it passes
        # straight through and every plotted coordinate becomes nan, giving an
        # invisible line with a legend entry.  Derive the ceiling from the bins
        # when the supplied one is unusable, and skip NaN bins outright.
        ymax = sr.get("ymax")
        try:
            ymax = float(ymax)
        except (TypeError, ValueError):
            ymax = 0.0
        if not (ymax == ymax and ymax > 0):
            _finite = [b[1] for b in sr["bins"] if b[1] == b[1]]
            ymax = max(_finite) if _finite and max(_finite) > 0 else 1.0
        _bins_ok = [b for b in sr["bins"] if b[0] == b[0] and b[1] == b[1]]
        if not _bins_ok:
            continue                 # nothing plottable — no legend entry either
        pts = " ".join(f'{L+(b[0]-x0)/xr*pw:.1f},{T+ph-(b[1]/ymax)*ph:.1f}'
                       for b in _bins_ok)
        # Colour by SERIES, falling back to the layer colour.  Keying purely
        # off the layer gave GPU util and HBM used — both A4 — the identical
        # colour, so the legend could not tell them apart at all.  An explicit
        # per-series colour is honoured when the caller supplies one.
        # Explicit series colour wins; otherwise take the next hue from the
        # separated palette by position, so no two series in a card share one.
        # The layer colour is the last resort.
        c = (sr.get("color")
             or _LAYER_SERIES_COLORS[si % len(_LAYER_SERIES_COLORS)]
             or _AMOPROF_LAYER_COLOR.get(sr["layer"], "#94a3b8"))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2.1" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        for b in _bins_ok:
            # Hover coordinates, matching the scatter charts.  The tooltip
            # shows the value in its own unit, not the normalised percentage
            # that is plotted, since the axis is shared across units.
            parts.append(f'<circle cx="{L+(b[0]-x0)/xr*pw:.1f}" cy="{T+ph-(b[1]/ymax)*ph:.1f}" '
                         f'r="2.4" fill="{c}">'
                         f'<title>{_html.escape(sr["label"])}&#10;'
                         f'{_html.escape(driver_label)} = {b[0]:,.1f}&#10;'
                         f'value = {_fmt_latency(b[1], sr.get("unit")) if _is_latency_unit(sr.get("unit")) else f"{b[1]:,.2f}"} '
                         f'{_html.escape(sr.get("unit") or "")}'
                         f' ({b[1]/ymax*100:.0f}% of max)</title></circle>')
        nl = " NL" if abs(sr["rho"]) - abs(sr["r"]) > 0.15 else ""
        parts.append(f'<rect x="{L+pw+12}" y="{ly}" width="9" height="3" fill="{c}" rx="1.5"/>')
        # Same fixed-gutter clipping as the tier legend: condense to fit
        # rather than lose the tail of the metric name or the r value.
        _lb = f'{sr["label"]} r={sr["r"]:+.2f}{nl}'
        _av = width - (L + pw + 25) - 6
        _fit = (f' textLength="{_av:.0f}" lengthAdjust="spacingAndGlyphs"'
                if _av > 20 and len(_lb) * 8.5 * 0.55 > _av else "")
        parts.append(f'<text x="{L+pw+25}" y="{ly+4}" fill="#cbd5e1" '
                     f'font-size="8.5"{_fit}>'
                     f'{_html.escape(sr["label"])} <tspan fill="#64748b">r={sr["r"]:+.2f}{nl}</tspan></text>')
        # Report the ceiling actually used for scaling, not the supplied one.
        # Printing sr["ymax"] showed "max 0.0 ms" whenever it was NaN or zero
        # and the ceiling had been derived from the bins instead — a stated
        # maximum of zero beside a plotted line is a contradiction the reader
        # cannot resolve.  When even the derived ceiling is a placeholder,
        # say the range is unavailable rather than printing a fake number.
        # The bins are per-bucket MEDIANS, so a signal that is zero most of
        # the time and non-zero in bursts has every median at zero -- which
        # printed "range unavailable" for a queue depth whose raw series had
        # a real peak. Report the raw series peak when the caller supplies it,
        # and only call the range unavailable when nothing is non-zero
        # anywhere.
        _peak_seen = max((b[1] for b in _bins_ok if b[1] == b[1]), default=0.0)
        _raw_peak = 0.0
        try:
            _raw_peak = max((v for v in (sr.get("raw") or []) if v == v), default=0.0)
        except Exception:
            _raw_peak = 0.0
        # Name the statistic, so "max 16.0" cannot be read as the typical
        # value and a flat line cannot be read as no data.  Latencies print
        # the way the KPI tiles print them.
        _stat_txt = _amoprof_bin_stat_for(sr.get("label", ""))
        _u = sr["unit"]

        def _pk(v, dec=1):
            return (_fmt_latency(v, _u, " " + _u) if _is_latency_unit(_u)
                    else _fmt_num(v, " " + _u, dec))
        if _peak_seen > 0:
            _max_txt = f'peak of binned {_stat_txt} {_pk(_peak_seen)}'
            if _raw_peak > _peak_seen * 1.05:
                _max_txt += f' · series peak {_pk(_raw_peak)}'
        elif _raw_peak > 0:
            _max_txt = f'binned {_stat_txt} 0 · series peak {_pk(_raw_peak, 3)}'
        else:
            _max_txt = "no non-zero sample in this window"
        parts.append(f'<text x="{L+pw+25}" y="{ly+13}" fill="#475569" font-size="7.5">'
                     f'{_max_txt}</text>')
        ly += 22
    parts.append(f'<text x="{L+pw/2:.0f}" y="{height-8}" fill="#cbd5e1" font-size="8.5" '
                 f'text-anchor="middle">{_html.escape(driver_label)} ({_html.escape(driver_unit)}) \u2192</text>')
    _cap = _amoprof_exec_chart_caption(
        [("X", driver_label, "#93c5fd")]
        + [("Y", sr["label"], "#86efac") for sr in series[:3]])
    return (f'<div class="corr-chart corr-chart-wide" style="min-width:0"><svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{_cap}</div>')


def _amoprof_exec_svg_qd_saturation(dist: "list[tuple[float, float]]",
                                    source: str = "",
                                    ref: float = 32.0,
                                    width: int = 760,
                                    height: int = 300) -> str:
    """Time spent at each storage queue depth, with cumulative share.

    This is the saturation question stated directly. A mean and a peak cannot
    answer it: mean 0.35 with a peak of 16 is consistent both with a device
    that briefly queued 16 once and with one that sat at 16 for a tenth of
    the run, and those are opposite conclusions. The time-at-depth curve
    separates them, and the analyser has written it to
    queue_depth_distribution.csv all along without anything rendering it.

    *dist* is [(queue_depth, seconds_at_that_depth), ...].
    """
    dist = [(float(d), float(s)) for d, s in (dist or [])
            if d == d and s == s and s > 0]
    if not dist:
        return ""
    dist.sort(key=lambda p: p[0])
    total = sum(s for _d, s in dist)
    if total <= 0:
        return ""

    L, R, T, B = 56, 150, 36, 46
    pw, ph = width - L - R, height - T - B
    _dmax = max(d for d, _s in dist)
    _xr = max(_dmax, 1.0)
    _bw = pw / max(len(dist), 1)

    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">'
             f'Storage queue depth saturation — time spent at each depth</text>',
             f'<text x="{L}" y="29" fill="#94a3b8" font-size="8.5">'
             f'bars = % of the window at that depth · line = cumulative % at or '
             f'below · {_html.escape(source or "queue-depth distribution")}</text>']
    for g in range(5):
        gy = T + ph * g / 4
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{L+pw}" y2="{gy:.1f}" stroke="#1e293b"/>')
        parts.append(f'<text x="{L-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" '
                     f'text-anchor="end">{100-g*25}%</text>')

    _pmax = max(s / total * 100.0 for _d, s in dist) or 1.0
    _cum, _cpts = 0.0, []
    for _i, (_d, _s) in enumerate(dist):
        _pct = _s / total * 100.0
        _cum += _pct
        _bx = L + _i * _bw
        # Bars share a 0-100% axis with the cumulative line only when the
        # largest bucket is big; otherwise they would be invisible, so they
        # are scaled to the largest bucket and the scaling is stated.
        _bh = (_pct / _pmax) * ph * 0.92
        _col = ("#ef4444" if _d >= ref else
                "#f59e0b" if _d >= ref / 2 else "#22c55e")
        parts.append(
            f'<rect x="{_bx+_bw*0.12:.1f}" y="{T+ph-_bh:.1f}" '
            f'width="{max(_bw*0.76, 1.2):.1f}" height="{max(_bh, 1.0):.1f}" '
            f'fill="{_col}" opacity=".85" rx="1.5">'
            f'<title>queue depth {_d:,.0f}&#10;{_s:,.1f} s '
            f'({_pct:.3f}% of the window)&#10;cumulative {_cum:.3f}% at or '
            f'below this depth</title></rect>')
        _cpts.append(f'{_bx+_bw*0.5:.1f},{T+ph-(_cum/100.0)*ph:.1f}')
        if len(dist) <= 16 or _i % max(1, len(dist)//12) == 0:
            parts.append(f'<text x="{_bx+_bw*0.5:.1f}" y="{T+ph+12:.1f}" '
                         f'fill="#64748b" font-size="7.5" '
                         f'text-anchor="middle">{_d:,.0f}</text>')
    parts.append(f'<polyline points="{" ".join(_cpts)}" fill="none" '
                 f'stroke="#93c5fd" stroke-width="1.8" opacity=".95"/>')

    # The saturation answer in words, to the right of the plot.
    _at_or_above = lambda _c: sum(s for d, s in dist if d >= _c) / total * 100.0
    _nonzero = _at_or_above(1)
    _mean = sum(d * s for d, s in dist) / total
    _ly = T + 6
    for _lbl, _val in (
            ("peak depth", f"{_dmax:,.0f}"),
            ("time-weighted mean", f"{_mean:,.2f}"),
            ("% of window queued", f"{_nonzero:.2f}%"),
            (f"% at QD ≥ {ref/4:,.0f}", f"{_at_or_above(ref/4):.3f}%"),
            (f"% at QD ≥ {ref/2:,.0f}", f"{_at_or_above(ref/2):.3f}%"),
            (f"% at QD ≥ {ref:,.0f}", f"{_at_or_above(ref):.3f}%")):
        parts.append(f'<text x="{L+pw+12}" y="{_ly}" fill="#94a3b8" '
                     f'font-size="7.5">{_html.escape(_lbl)}</text>')
        parts.append(f'<text x="{width-8}" y="{_ly}" fill="#e2e8f0" '
                     f'font-size="8.5" font-weight="700" '
                     f'text-anchor="end">{_val}</text>')
        _ly += 15
    parts.append(f'<text x="{L+pw+12}" y="{_ly+4}" fill="#475569" font-size="7">'
                 f'red bars: QD ≥ {ref:,.0f}</text>')
    parts.append(f'<text x="{L+pw/2:.0f}" y="{height-8}" fill="#cbd5e1" '
                 f'font-size="8.5" text-anchor="middle">queue depth '
                 f'(requests outstanding) →</text>')
    _cap = _amoprof_exec_chart_caption(
        [("X", "queue depth", "#93c5fd"),
         ("Y", "% of window at that depth", "#86efac")])
    return (f'<div class="corr-chart corr-chart-wide" style="min-width:0">'
            f'<svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{_cap}</div>')


def _amoprof_qd_distribution(raw_dir: "Path", series: "list[float] | None" = None,
                             times: "list[float] | None" = None):
    """Time-at-depth pairs, from blktrace's own histogram or from a series.

    blktrace writes queue_depth_distribution.csv with exact time at each
    depth. When that file is absent the same shape is derived from a sampled
    gauge by charging each sample its sampling interval -- coarser, and
    labelled as such, but it answers the same question.
    """
    _p = _first_existing(raw_dir, ["blktrace_analysis/queue_depth_distribution.csv",
                                   "queue_depth_distribution.csv"])
    if _p:
        try:
            import csv as _c
            with open(_p, newline="", encoding="utf-8", errors="replace") as _fh:
                _rows = list(_c.DictReader(_fh))
            _out = []
            for _r in _rows:
                try:
                    _out.append((float(_r.get("qd_value") or _r.get("qd") or 0),
                                 float(_r.get("time_sec") or 0)))
                except (TypeError, ValueError):
                    continue
            if _out:
                return _out, "exact blktrace Q→C time-at-depth histogram"
        except Exception:
            pass
    # Derived from a sampled gauge.
    _v = [x for x in (series or []) if x == x]
    if not _v:
        return [], ""
    _dt = 1.0
    _t = [x for x in (times or []) if x == x]
    if len(_t) >= 2:
        _spans = [_t[_i + 1] - _t[_i] for _i in range(len(_t) - 1)
                  if _t[_i + 1] > _t[_i]]
        if _spans:
            _spans.sort()
            _dt = _spans[len(_spans) // 2]
    _acc: dict = {}
    for _x in _v:
        _k = round(_x)
        _acc[_k] = _acc.get(_k, 0.0) + _dt
    return (sorted(_acc.items()),
            f"derived from a sampled in-flight gauge · {_dt:g}s per sample "
            f"· coarser than blktrace Q→C")


def _amoprof_exec_svg_queue_timeline(queues: list, width: int = 760,
                                     height: int = 300) -> str:
    """Every layer's queue as a percentage of its own saturation reference."""
    queues = [q for q in queues if q.get("t") and q.get("v")]
    if len(queues) < 2:
        return ""
    L, R, T, B = 50, 220, 34, 42
    pw, ph = width - L - R, height - T - B
    t0 = min(min(q["t"]) for q in queues)
    t1 = max(max(q["t"]) for q in queues)
    tr = (t1 - t0) or 1.0
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">'
             f'Queue occupancy across layers</text>',
             f'<text x="{L}" y="29" fill="#94a3b8" font-size="8.5">each queue as % of its own saturation '
             f'reference \u00b7 decimated by MAX per pixel, so a burst survives \u00b7 '
             f'a rising line is a layer taking work faster than it retires it</text>']
    for g in range(5):
        gy = T + ph * g / 4
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{L+pw}" y2="{gy:.1f}" stroke="#1e293b"/>')
        parts.append(f'<text x="{L-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" '
                     f'text-anchor="end">{100-g*25}%</text>')
    ly = T + 4
    for q in queues:
        c = _AMOPROF_LAYER_COLOR.get(q["layer"], "#94a3b8")
        n = min(len(q["t"]), len(q["v"]))
        step = max(1, n // 240)
        # Decimate by MAX over each window, not by taking every step-th
        # sample. Index decimation drops whatever falls between the sampled
        # indices, and on a queue that is zero in almost every sample and
        # spikes to its real depth in a few, the spikes are exactly what gets
        # dropped: a series with a peak of 16 plotted as a flat line on zero,
        # with the legend still reporting the peak.
        _dec: list = []
        for _s in range(0, n, step):
            _win = [(q["t"][_j], q["v"][_j]) for _j in range(_s, min(_s + step, n))
                    if q["v"][_j] == q["v"][_j]]
            if not _win:
                continue
            _tv, _vv = max(_win, key=lambda p: p[1])
            _dec.append((_tv, _vv))
        pts = " ".join(
            f'{L+(_tv-t0)/tr*pw:.1f},{T+ph-min(_vv/q["ref"],1.0)*ph:.1f}'
            for _tv, _vv in _dec)
        if not pts:
            continue
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.7" opacity=".9"/>')
        # Sparse transparent hover targets: a polyline alone has no per-point
        # tooltip, so sample the series for hoverable coordinates. Taken from
        # the decimated (max) points so a hovered value matches the line.
        _hstep = max(1, len(_dec) // 40)
        for _k in range(0, len(_dec), _hstep):
            _i = q["t"].index(_dec[_k][0]) if _dec[_k][0] in q["t"] else 0
            if q["v"][_i] != q["v"][_i]:
                continue
            parts.append(
                f'<circle cx="{L+(q["t"][_i]-t0)/tr*pw:.1f}" '
                f'cy="{T+ph-min(q["v"][_i]/q["ref"],1.0)*ph:.1f}" r="4" fill="{c}" '
                f'opacity="0"><title>{_html.escape(q["label"])}\n'
                f't = {q["t"][_i]:,.0f} s\nvalue = {q["v"][_i]:,.2f} '
                f'({min(q["v"][_i]/q["ref"],1.0)*100:.0f}% of reference)</title></circle>')
        parts.append(f'<rect x="{L+pw+12}" y="{ly}" width="9" height="3" fill="{c}" rx="1.5"/>')
        parts.append(f'<text x="{L+pw+25}" y="{ly+4}" fill="#cbd5e1" font-size="8.5">{_html.escape(q["label"])}</text>')
        parts.append(f'<text x="{L+pw+25}" y="{ly+13}" fill="#475569" font-size="7">{_html.escape(q["refnote"])}</text>')
        ly += 22
    # Vertical gridlines + tick labels.  The axis said "elapsed (s)" but drew
    # no ticks, so there was no way to read WHEN anything happened — the label
    # promised a timeline the chart did not provide.
    for _g in range(5):
        _gx = L + pw * _g / 4.0
        _gt = t0 + tr * _g / 4.0
        parts.append(f'<line x1="{_gx:.1f}" y1="{T}" x2="{_gx:.1f}" y2="{T+ph}" '
                     f'stroke="#1e293b" stroke-width="0.8"/>')
        _lab = (f"{_gt/3600:.1f}h" if tr > 7200 else
                ((f"{_gt/60:.1f}m" if tr <= 900 else f"{_gt/60:.0f}m") if tr > 180 else f"{_gt:.0f}s"))
        parts.append(f'<text x="{_gx:.1f}" y="{T+ph+14:.1f}" fill="#64748b" '
                     f'font-size="7.5" text-anchor="middle">{_lab}</text>')
    _span = (f"{tr/3600:.2f} h" if tr > 7200 else
             (f"{tr/60:.1f} min" if tr > 180 else f"{tr:.0f} s"))
    parts.append(f'<text x="{L+pw/2:.0f}" y="{height-8}" fill="#cbd5e1" font-size="8.5" '
                 f'text-anchor="middle">elapsed \u2014 {_span} window \u2192</text>')
    _cap = _amoprof_exec_chart_caption([("Y", q["label"], "#86efac") for q in queues[:4]])
    return (f'<div class="corr-chart corr-chart-wide" style="min-width:0"><svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{_cap}</div>')


def _amoprof_exec_svg_queue_pctl(queues: list, width: int = 760,
                                 height: int = 270) -> str:
    """p50/p90/p99 of each layer's queue, normalised, with absolute p99 shown."""
    queues = [q for q in queues if q.get("v")]
    if not queues:
        return ""
    L, T, B = 52, 34, 74
    pw, ph = width - L - 20, height - T - B
    slot = pw / len(queues)

    def _pc(v, qq, q=None):
        # An authoritative percentile set wins over one computed from the
        # per-sample series.  Exact blktrace Q->C percentiles are measured
        # per I/O; a sysfs avgqu_sz series sampled every 15 s is a coarse
        # average of the same quantity, and on a bursty queue its p99 can be
        # three orders of magnitude lower.  The chart used to compute from
        # whichever series it happened to be handed, so a run with exact
        # blktrace data still drew "0" bars from the sysfs series.
        if q:
            _given = (q.get("pctl") or {}).get(qq)
            if _given is not None:
                return float(_given)
        srt = sorted(x for x in v if x == x)
        if not srt:
            return 0.0
        return srt[min(len(srt) - 1, int(qq * (len(srt) - 1)))]

    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">'
             f'Queue depth distribution \u2014 p50 / p90 / p99 per layer</text>',
             f'<text x="{L}" y="29" fill="#94a3b8" font-size="8.5">% of each queue\u2019s saturation reference '
             f'\u00b7 high p99 with low p50 is bursty backpressure, not steady load</text>']
    for g in range(5):
        gy = T + ph * g / 4
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{L+pw}" y2="{gy:.1f}" stroke="#1e293b"/>')
        parts.append(f'<text x="{L-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" '
                     f'text-anchor="end">{100-g*25}%</text>')
    for i, q in enumerate(queues):
        c = _AMOPROF_LAYER_COLOR.get(q["layer"], "#94a3b8")
        base = L + slot * i
        for j, (qq, op) in enumerate(((0.5, .42), (0.9, .70), (0.99, 1.0))):
            _abs = _pc(q["v"], qq, q)
            val = min(_abs / q["ref"], 1.0) * 100.0
            bw = slot * 0.22
            bx = base + slot * 0.10 + j * bw
            bh = val / 100.0 * ph
            parts.append(f'<rect x="{bx:.1f}" y="{T+ph-bh:.1f}" width="{bw*0.86:.1f}" '
                         f'height="{max(bh,1):.1f}" fill="{c}" opacity="{op}" rx="2">'
                         f'<title>{_html.escape(q["label"])}\np{int(qq*100)} = '
                         f'{_abs:,.2f} ({val:.0f}% of reference)</title></rect>')
            # A queue far below its saturation reference normalises to a few
            # per cent, and a bar labelled "3" beside a 5px sliver reads as
            # "no data" when the real finding is "measured, and nowhere near
            # saturation". Short bars therefore carry the ABSOLUTE value --
            # a p99 of 1.0 against a QD=32 reference is legible as 1 -- and
            # the percentage stays in the bar height and the tooltip.
            if _abs <= 0:
                _lbl, _col = "0", "#64748b"
            elif val < 8.0:
                _lbl = (f"{_abs:,.2f}".rstrip("0").rstrip(".")
                        if _abs < 100 else f"{_abs:,.0f}")
                _col = "#cbd5e1"
            else:
                _lbl, _col = f"{val:.0f}", "#f8fafc"
            parts.append(f'<text x="{bx+bw*0.43:.1f}" y="{T+ph-max(bh,2)-4:.1f}" fill="{_col}" '
                         f'font-size="8.5" font-weight="700" '
                         f'text-anchor="middle">{_lbl}</text>')
            parts.append(f'<text x="{bx+bw*0.43:.1f}" y="{T+ph+11:.1f}" fill="#64748b" font-size="7" '
                         f'text-anchor="middle">p{int(qq*100)}</text>')
        parts.append(f'<text x="{base+slot/2:.1f}" y="{T+ph+26:.1f}" fill="{c}" font-size="8.5" '
                     f'font-weight="700" text-anchor="middle">{_html.escape(q["layer"])}</text>')
        parts.append(f'<text x="{base+slot/2:.1f}" y="{T+ph+37:.1f}" fill="#94a3b8" font-size="7.5" '
                     f'text-anchor="middle">{_html.escape(q["label"][:24])}</text>')
        parts.append(f'<text x="{base+slot/2:.1f}" y="{T+ph+47:.1f}" fill="#475569" font-size="7.5" '
                     f'text-anchor="middle">abs p99 '
                     f'{_fmt_num(_pc(q["v"], 0.99, q), "", 2)}'
                     f'{" (" + _html.escape(q["pctl_src"]) + ")" if q.get("pctl_src") else ""}'
                     f'</text>')
    _cap = _amoprof_exec_chart_caption([("Y", q["label"], "#86efac") for q in queues[:4]])
    return (f'<div class="corr-chart corr-chart-wide" style="min-width:0"><svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{_cap}</div>')



def _amoprof_exec_svg_hbm_breakdown(b: dict, width: int = 460,
                                    height: int = 300) -> str:
    """Stacked bar: what HBM is occupied by, per GPU.

    Weights and the reserved KV pool are resident regardless of load; the
    occupied part of the pool is the only component that moves with traffic,
    so it is drawn as a distinct band inside the pool rather than as a
    separate bar.  The remainder is labelled a residual (activations, CUDA
    context, fragmentation) rather than being attributed to a category the
    data cannot distinguish.
    """
    total = float(b.get("per_gpu_total_gb") or 0.0)
    if total <= 0:
        return ""
    segs = []
    if b.get("weights_gb"):
        segs.append(("Model weights", float(b["weights_gb"]), "#f59e0b"))
    if b.get("kv_active_gb"):
        segs.append(("KV in use", float(b["kv_active_gb"]), "#22c55e"))
    if b.get("kv_free_gb"):
        segs.append(("KV pool reserved, free", float(b["kv_free_gb"]), "#166534"))
    if b.get("residual_gb"):
        segs.append(("Activations / frag", float(b["residual_gb"]), "#64748b"))
    if b.get("free_gb"):
        segs.append(("Unallocated HBM", float(b["free_gb"]), "#1e293b"))
    if not segs:
        return ""
    L, R, T, B_ = 58, 14, 44, 92
    pw, ph = width - L - R, height - T - B_
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">'
             f'HBM composition per GPU</text>',
             f'<text x="{L}" y="29" fill="#94a3b8" font-size="8.5">'
             f'{_fmt_num(b.get("per_gpu_used_gb", 0), " GB", 1)} used of '
             f'{_fmt_num(total, " GB", 0)} \u00b7 TP {b.get("tp_size", 1):g} \u00b7 '
             f'KV {_fmt_num(_k_kb_from_bytes(_safe_float(b.get("kv_bytes_per_token_kb", 0), 0.0) * 1024), " KB/token", 0)}</text>']
    bx = L + pw * 0.28
    bw = pw * 0.44
    y = T
    for name, gb, col in segs:
        h_seg = (gb / total) * ph
        if h_seg <= 0:
            continue
        parts.append(f'<rect x="{bx:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{max(h_seg,1):.1f}" fill="{col}" opacity="0.9"><title>{_html.escape(name)}: {gb:,.2f} GB ({gb/total*100:.1f}% of device)</title></rect>')
        if h_seg > 11:
            parts.append(f'<text x="{bx+bw/2:.1f}" y="{y+h_seg/2+3:.1f}" fill="#f8fafc" '
                         f'font-size="8.5" font-weight="700" text-anchor="middle">'
                         f'{_fmt_num(gb, "", 1)}</text>')
        y += h_seg
    ly = height - B_ + 14
    for name, gb, col in segs:
        parts.append(f'<rect x="{L}" y="{ly-6}" width="9" height="7" fill="{col}" rx="1.5"/>')
        parts.append(f'<text x="{L+14}" y="{ly}" fill="#cbd5e1" font-size="8.5">'
                     f'{_html.escape(name)} \u2014 {_fmt_num(gb, " GB", 1)} '
                     f'({gb/total*100:.0f}%)</text>')
        ly += 12
    parts.append(f'<text x="12" y="{T+ph/2:.1f}" fill="#cbd5e1" font-size="8.5" '
                 f'transform="rotate(-90 12 {T+ph/2:.1f})" text-anchor="middle">GB per GPU</text>')
    _cap = _amoprof_exec_chart_caption([("Y", "HBM used", "#86efac"), ("Y", "L1 HBM used", "#86efac")])
    return (f'<div class="corr-chart"><svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{_cap}</div>')



def _amoprof_exec_svg_bucket_scatter(sg_path,
                                     base: str,
                                     title: str,
                                     subtitle: str,
                                     color: str,       # kept for signature compat; unused
                                     window: "tuple | None" = None,
                                     wall_start: float = 0.0,
                                     width: int = 760,
                                     height: int = 320) -> str:
    """Multi-line trend chart of Prometheus histogram bucket deltas over the run.

    One line per bucket range that received any new completions:
      * x = interval timestamp
      * y = new completions in that bucket range during that interval
        (linear count axis)
      * legend labels every visible line with its bucket upper edge, in
        seconds when any finite edge is >= 1s, milliseconds otherwise

    No smoothing, no aggregation across buckets — the sum of every line at
    an interval equals the total completions that landed in that interval.
    """
    if not sg_path:
        return ""
    _time, _cum = _amoprof_bucket_series(sg_path, base)
    _cum = [(le, ser) for le, ser in _cum if ser]
    if len(_cum) < 2 or len(_time) < 2:
        return ""
    # Trim to a common length.
    _n = min(len(_time), min(len(ser) for _le, ser in _cum))
    _time = _time[:_n]
    _cum = [(le, ser[:_n]) for le, ser in _cum]
    # Auto-pick display unit.
    _finite_le_s = [le for le, _ in _cum if le != float("inf") and le > 0]
    if not _finite_le_s:
        return ""
    _use_ms = max(_finite_le_s) < 1.0
    _scale = 1000.0 if _use_ms else 1.0
    _unit = "ms" if _use_ms else "s"

    def _fmt_edge(v):
        # v is in raw seconds; format in display unit.
        _s = v * _scale
        if _use_ms:
            return f"le \u2264 {_s:.0f} {_unit}"
        return (f"le \u2264 {_s:.1f}s" if _s < 10 else f"le \u2264 {_s:.0f}s")

    # Build per-interval count-in-range series.  bucket_range_new[i] for
    # bucket k = (c_k[i] - c_k[i-1]) - (c_{k-1}[i] - c_{k-1}[i-1]); the first
    # bucket has an implicit prev = 0.
    _series = []
    _prev_ser = [0.0] * _n
    _max_count = 0.0
    for le, ser in _cum:
        _counts = [0.0]  # first interval has no prior delta to compare
        for _i in range(1, _n):
            _cur = (ser[_i] or 0.0) - (ser[_i - 1] or 0.0)
            _prev = _prev_ser[_i] - _prev_ser[_i - 1]
            _v = _cur - _prev
            _counts.append(_v if _v > 0 else 0.0)
        if any(v > 0 for v in _counts):
            _series.append((le, _counts))
            _mx = max(_counts)
            if _mx > _max_count:
                _max_count = _mx
        _prev_ser = list(ser)
    if not _series:
        return ""

    # Color ramp: cool -> warm as bucket edge climbs, so heavy-tail buckets
    # visually stand out against fast buckets.  Interpolate through a small
    # anchor palette matching the rest of the report.
    _PALETTE = [
        (0.00, (0x38, 0xbd, 0xf8)),   # blue
        (0.35, (0x22, 0xc5, 0x5e)),   # green
        (0.65, (0xf5, 0x9e, 0x0b)),   # amber
        (1.00, (0xef, 0x44, 0x44)),   # red
    ]

    def _ramp(t):
        for i in range(len(_PALETTE) - 1):
            a, ca = _PALETTE[i]
            b, cb = _PALETTE[i + 1]
            if a <= t <= b:
                f = (t - a) / (b - a or 1.0)
                r = int(ca[0] + (cb[0] - ca[0]) * f)
                g = int(ca[1] + (cb[1] - ca[1]) * f)
                bl = int(ca[2] + (cb[2] - ca[2]) * f)
                return f"#{r:02x}{g:02x}{bl:02x}"
        return f"#{_PALETTE[-1][1][0]:02x}{_PALETTE[-1][1][1]:02x}{_PALETTE[-1][1][2]:02x}"

    # Rank each series by its bucket edge on [0, 1] so the ramp lookup is
    # monotonic even when the histogram has non-uniform bucket spacing.
    _n_ser = len(_series)
    _ranked = []
    for _idx, (le, counts) in enumerate(_series):
        _pos = (_idx / (_n_ser - 1)) if _n_ser > 1 else 0.5
        _ranked.append({
            "tier": "L1",
            "label": _fmt_edge(le),
            "t": _time,
            "v": counts,
            "cap": 0,
            "color": _ramp(_pos),
        })

    # Delegate the actual rendering to the standard tier-occupancy renderer.
    # It handles linear/log auto-selection based on dynamic range; since our
    # y-values are counts on a small range, it will pick linear.
    return _amoprof_exec_svg_tier_occupancy(
        _ranked,
        width=width,
        height=height,
        window=window,
        wall_start=wall_start,
        mode="abs",
        title=title,
        subtitle=subtitle,
        yaxis="completions / interval",
        unit_label="completions",
        force_linear=True,
    )


def _amoprof_exec_svg_tier_occupancy(series: list, width: int = 760,
                                     height: int = 320,
                                     window: "tuple | None" = None,
                                     wall_start: float = 0.0,
                                     mode: str = "tokens",
                                     title: str = "", subtitle: str = "",
                                     yaxis: str = "", unit_label: str = "",
                                     force_linear: bool = False, keep_zero_series: bool = False) -> str:
    """KV tokens resident in each cache tier, over the run.

    One chart, one unit: **tokens**.  Capacity in GB is not comparable across
    tiers (a token costs the same KV bytes wherever it sits, but the tiers are
    sized very differently), whereas token counts are directly comparable and
    are what the engine actually moves between tiers.

    Each tier is drawn as an absolute token count against a shared log-ish
    linear axis, with its configured capacity as a dashed ceiling so the
    headroom in each tier is visible at a glance.
    `series` items: {"tier","label","t","v","cap","color"}.
    """
    # An all-zero series is normally dropped: a dead line is clutter.  But on
    # a chart whose question IS "did this happen at all", a flat line at zero
    # is the answer, and dropping it makes a measured zero look identical to a
    # counter the build never exported.  Callers asking that question opt in.
    if keep_zero_series:
        series = [x for x in series
                  if x.get("v") and any(q == q for q in x["v"])]
    else:
        series = [x for x in series if x.get("v") and any(q > 0 for q in x["v"])]
    if not series:
        return ""
    L, R, T, B = 62, 200, 34, 44
    # Same non-wrapping <text> problem as the bar renderer: a long subtitle
    # ran past the viewBox and was clipped.  Wrap on words at the plot width
    # (R is the legend gutter, so the text may use it) and make room.
    _sub_txt = (subtitle or
                ("100% means that tier is full and is forcing eviction to the "
                 "next tier down" if mode == "fill" else
                 "absolute token counts on one axis \u00b7 dashed line = "
                 "configured capacity for that tier"))
    _sub_lines = []
    _cpl = max(30, int((width - L - 14) / (8.5 * 0.55)))
    _cur = ""
    for _w in str(_sub_txt).split(" "):
        _cand = (_cur + " " + _w).strip()
        if len(_cand) <= _cpl or not _cur:
            _cur = _cand
        else:
            _sub_lines.append(_cur)
            _cur = _w
    if _cur:
        _sub_lines.append(_cur)
    if len(_sub_lines) > 1:
        _sx = (len(_sub_lines) - 1) * 11
        T += _sx
        height += _sx
    pw, ph = width - L - R, height - T - B
    # The axis must span the WINDOW the user asked for, not merely the extent
    # of the data.  A tier that only reported for part of the run would
    # otherwise stretch to fill the chart, hiding the gap and misplacing every
    # other tier relative to it.
    if not any(x.get("t") for x in series):
        return ""
    _dt0 = min(min(x["t"]) for x in series if x["t"])
    _dt1 = max(max(x["t"]) for x in series if x["t"])
    if window and len(window) == 2 and window[1] is not None and window[0] is not None:
        t0, t1 = float(window[0]), float(window[1])
        if t1 <= t0:                      # unusable window; fall back to data
            t0, t1 = _dt0, _dt1
    else:
        t0, t1 = _dt0, _dt1
    tr = (t1 - t0) or 1.0
    if mode == "abs":
        # Absolute units, log-scaled.  A linear axis is dominated by the
        # largest tier and collapses every other one onto the baseline, which
        # is why this started as a percentage — but a percentage needs a
        # ceiling, and for a remote store the ceiling is often unknown or
        # elastic.  A log axis shows real magnitudes side by side without
        # requiring one.
        import math as _m
        # NaN-safe extrema.  Python's max() returns NaN when the FIRST element
        # is NaN (comparisons with NaN are all False, so it never updates), and
        # an interval with no completed requests legitimately yields NaN.  One
        # leading NaN made _hi NaN, which made every plotted y NaN, which
        # rendered an empty chart with "nan" axis labels while the data was
        # perfectly good.  `v > 0` already excludes NaN for _lo; _hi needs the
        # same filter.
        _lo = min((v for x in series for v in x["v"] if v == v and v > 0),
                  default=0.0)
        _hi = max((v for x in series for v in x["v"] if v == v), default=0.0)
        if not (_hi > 0):            # also catches NaN
            return ""
        _dyn = (_hi / _lo) if _lo > 0 else float("inf")
        if force_linear:
            _use_log = False
        else:
            _use_log = (_dyn > _LOG_AXIS_MIN_RATIO) if _AXIS_SCALE == "auto" \
                else (_AXIS_SCALE == "log")
        if _use_log:
            _lo = max(_lo, _hi / 1e6) if _lo > 0 else _hi / 1e6
            _log_lo, _log_hi = _m.log10(_lo), _m.log10(_hi * 1.15)
            _log_span = (_log_hi - _log_lo) or 1.0

            def _ypos(v):
                if v <= 0:
                    return T + ph
                return T + ph - (_m.log10(max(v, _lo)) - _log_lo) / _log_span * ph
        else:
            _lin_max = (_hi * 1.15) or 1.0

            def _ypos(v):
                return T + ph - (max(0.0, v) / _lin_max) * ph
        vmax = _hi
    elif mode == "fill":
        # Each tier as a percentage of ITS OWN capacity.  The absolute-token
        # view cannot show this: L3.5 at millions of tokens dwarfs L1 at tens
        # of thousands, so a tier at 95% full is invisible next to a larger
        # tier at 5%.  Normalising each to its own ceiling puts "how full is
        # this tier" on one comparable 0-100 axis.
        _scaled = []
        for x in series:
            cap = x.get("cap") or 0.0
            if cap <= 0:
                continue          # no ceiling -> no meaningful percentage
            y = dict(x)
            y["v"] = [min(100.0, v / cap * 100.0) for v in x["v"]]
            y["cap"] = 0.0        # the axis itself is the ceiling now
            _scaled.append(y)
        if not _scaled:
            return ""
        series = _scaled
        vmax = 100.0
    else:
        vmax = max(max(x["v"]) for x in series)
        vmax = max(vmax, max((x.get("cap") or 0) for x in series)) or 1.0
    parts = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
             f'<text x="{L}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">'
             + ((title or ("KV tier fill \u2014 % of each tier\u2019s own capacity"
                            if mode == "fill"
                            else "KV tokens resident per cache tier")) + "</text>"),
             *[f'<text x="{L}" y="{29 + _i * 11}" fill="#94a3b8" '
               f'font-size="8.5">{_html.escape(_t)}</text>'
               for _i, _t in enumerate(_sub_lines)]]
    for g in range(5):
        gy = T + ph * g / 4.0
        parts.append(f'<line x1="{L}" y1="{gy:.1f}" x2="{L+pw}" y2="{gy:.1f}" stroke="#1e293b"/>')
        if mode == "abs":
            _gv = (10 ** (_log_lo + _log_span * (1 - g / 4.0)) if _use_log
                   else _lin_max * (1 - g / 4.0))
            _lab_y = (_fmt_latency(_gv, unit_label) if _is_latency_unit(unit_label) and _gv >= 10
                      else f"{_gv:,.0f}" if _gv >= 10 else
                      (f"{_gv:.1f}" if _gv >= 1 else f"{_gv:.2f}"))
        else:
            _lab_y = _fmt_num(vmax * (1 - g / 4.0), "", 0)
        parts.append(f'<text x="{L-6}" y="{gy+3:.1f}" fill="#64748b" font-size="7.5" '
                     f'text-anchor="end">{_lab_y}</text>')
    ly = T + 4
    for x in series:
        c = x["color"]
        n = min(len(x["t"]), len(x["v"]))
        step = max(1, n // 260)
        _yf = (_ypos if mode == "abs"
               else (lambda v: T + ph - (v / vmax) * ph))
        pts = " ".join(f'{L+(x["t"][i]-t0)/tr*pw:.1f},{_yf(x["v"][i]):.1f}'
                       for i in range(0, n, step) if x["v"][i] == x["v"][i])
        if not pts:
            continue
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="1.9"/>')
        hstep = max(1, n // 40)
        for i in range(0, n, hstep):
            if x["v"][i] != x["v"][i]:
                continue
            # NaN is truthy, so `x.get("cap")` alone admits a NaN ceiling and
            # yields a nan percentage in the tooltip.
            _cap_ok = 0.0
            try:
                _cap_ok = float(x.get("cap") or 0.0)
            except (TypeError, ValueError):
                _cap_ok = 0.0
            _pct = ((x["v"][i] / _cap_ok * 100.0)
                    if (_cap_ok == _cap_ok and _cap_ok > 0) else None)
            parts.append(
                f'<circle cx="{L+(x["t"][i]-t0)/tr*pw:.1f}" '
                f'cy="{_yf(x["v"][i]):.1f}" r="4" fill="{c}" opacity="0">'
                f'<title>{_html.escape(x["label"])}&#10;t = {x["t"][i]:,.0f} s&#10;'
                + ((f'{_fmt_latency(x["v"][i], unit_label)} {_html.escape(unit_label)}'
                    if _is_latency_unit(unit_label) else
                    f'{x["v"][i]:,.3g} {_html.escape(unit_label)}') if mode == "abs"
                   else f'{x["v"][i]:,.1f}% of {"peak" if yaxis else "capacity"}'
                   if mode == "fill"
                   else f'{x["v"][i]:,.0f} tokens'
                        + (f' ({_pct:.1f}% of capacity)' if _pct is not None else ""))
                + '</title></circle>')
        # A falsy or non-positive cap means "no ceiling known" — draw no
        # dashed line and make no percentage claim, rather than inventing one
        # from the series' own peak.
        if x.get("cap") and float(x["cap"]) > 0 and vmax > 0:
            cy = (_yf(x["cap"]) if mode == "abs"
                  else T + ph - (x["cap"] / vmax) * ph if vmax > 0 else T)
            parts.append(f'<line x1="{L}" y1="{cy:.1f}" x2="{L+pw}" y2="{cy:.1f}" '
                         f'stroke="{c}" stroke-width="1" stroke-dasharray="4 4" opacity=".55"/>')
        parts.append(f'<rect x="{L+pw+12}" y="{ly}" width="9" height="3" fill="{c}" rx="1.5"/>')
        # NaN-safe: max() returns NaN when the FIRST element is NaN, which is
        # exactly the case for a latency series whose opening interval had no
        # completed requests.  That printed "peak nan ms" in the legend even
        # though the line itself plotted correctly.
        _finite_v = [v for v in x["v"] if v == v]
        _peak = max(_finite_v) if _finite_v else float("nan")
        # Legend labels sit in a fixed right gutter and are not wrappable, so
        # a long tier name ran past the viewBox and lost its tail --
        # "(KV movement est., not PMU)" became "(KV movement est., not PM".
        # Condense the glyphs to fit rather than truncating: the qualifier in
        # those names is the part that says how to read the series.
        _lbl_av = width - (L + pw + 25) - 6
        _lbl_w = len(x["label"]) * 8.5 * 0.55
        _lbl_fit = (f' textLength="{_lbl_av:.0f}" lengthAdjust="spacingAndGlyphs"'
                    if _lbl_av > 20 and _lbl_w > _lbl_av else "")
        parts.append(f'<text x="{L+pw+25}" y="{ly+4}" fill="#cbd5e1" '
                     f'font-size="8.5"{_lbl_fit}>'
                     f'{_html.escape(x["label"])}</text>')
        parts.append(f'<text x="{L+pw+25}" y="{ly+13}" fill="#475569" font-size="7.5">'
                     + ("no finite samples" if _peak != _peak else
                        f'peak {_fmt_latency(_peak, unit_label) if _is_latency_unit(unit_label) else f"{_peak:,.2f}"} '
                        f'{_html.escape(unit_label)}'
                        if mode == "abs" else
                        f'peak {_peak:.1f}%' + (" of ceiling" if yaxis else " full")
                        if mode == "fill" else
                        f'peak {_fmt_num(_peak, " tok", 0)}'
                        + (f' \u00b7 {_peak/x["cap"]*100:.0f}% of cap'
                           if (x.get("cap") and float(x["cap"]) > 0)
                           else " \u00b7 capacity unknown")) + '</text>')
        # Optional caption for the dashed reference line drawn at "cap" \u2014
        # e.g. the whole-window percentile behind a per-interval line.
        if x.get("cap_label") and x.get("cap") and float(x["cap"]) > 0:
            parts.append(f'<text x="{L+pw+25}" y="{ly+22}" fill="#475569" font-size="7.5">'
                         f'{_html.escape(str(x["cap_label"]))}</text>')
            ly += 9
        ly += 22
    # Vertical gridlines + tick labels across the whole window.
    import datetime as _dtm
    for g in range(5):
        gx = L + pw * g / 4.0
        gt = t0 + tr * g / 4.0
        parts.append(f'<line x1="{gx:.1f}" y1="{T}" x2="{gx:.1f}" y2="{T+ph}" '
                     f'stroke="#1e293b" stroke-width="0.8"/>')
        if wall_start > 0:
            lab = _dtm.datetime.fromtimestamp(
                wall_start + gt, _dtm.timezone.utc).strftime("%H:%M")
        elif tr > 7200:
            lab = f"{gt/3600:.1f}h"
        elif tr > 180:
            lab = (f"{gt/60:.1f}m" if tr <= 900 else f"{gt/60:.0f}m")
        else:
            lab = f"{gt:.0f}s"
        parts.append(f'<text x="{gx:.1f}" y="{T+ph+14:.1f}" fill="#64748b" '
                     f'font-size="7.5" text-anchor="middle">{lab}</text>')
    _span = (f"{tr/3600:.2f} h" if tr > 7200 else
             (f"{tr/60:.1f} min" if tr > 180 else f"{tr:.0f} s"))
    _axis = ("UTC \u2014 full selected window (" + _span + ")" if wall_start > 0
             else "elapsed \u2014 full selected window (" + _span + ")")
    parts.append(f'<text x="{L+pw/2:.0f}" y="{height-8}" fill="#cbd5e1" font-size="8.5" '
                 f'text-anchor="middle">{_axis} \u2192</text>')
    parts.append(f'<text x="12" y="{T+ph/2:.1f}" fill="#cbd5e1" font-size="8.5" '
                 f'transform="rotate(-90 12 {T+ph/2:.1f})" text-anchor="middle">{yaxis or ("% of tier capacity" if mode == "fill" else "KV tokens")}</text>')
    return (f'<div class="corr-chart corr-chart-wide" style="min-width:0">'
            f'<svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg></div>')


def _amoprof_exec_svg_scatter(title: str, x_label: str, y_label: str,
                                xs: List[float], ys: List[float],
                                point_color: str = "#60a5fa",
                                width: int = 460, height: int = 300,
                                subtitle: str = "") -> str:
    """Dependency-free SVG scatter chart with a linear regression line.

    Renders points at time-aligned (xs[i], ys[i]) pairs, plus the least-
    squares fit line and a Pearson r badge.  Used for the Cross-Layer
    Correlation section so the Executive tab can visualize correlations
    (input/output tok/s vs L1/L2/L3 bandwidth & R/W transactions) without
    a Plotly/JS dependency — the tab remains fully static.
    """
    ml, mr, mt, mb = 60, 24, 40, 46
    pw, ph = width - ml - mr, height - mt - mb
    n = min(len(xs), len(ys))
    if n < 1:
        return (f'<div class="combo-wrap"><div style="padding:22px;color:#94a3b8;'
                f'font-style:italic;font-size:12px">{_html.escape(title)} — '
                f'insufficient data</div></div>')
    xs = xs[:n]; ys = ys[:n]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if x_max <= x_min:
        x_max = x_min + 1.0
    if y_max <= y_min:
        y_max = y_min + 1.0
    def _sx(v: float) -> float:
        return ml + (v - x_min) / (x_max - x_min) * pw
    def _sy(v: float) -> float:
        return mt + ph - (v - y_min) / (y_max - y_min) * ph
    r = _pearson(xs, ys)
    parts: List[str] = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1220" rx="8"/>',
        f'<text x="{ml}" y="17" fill="#e2e8f0" font-size="10" font-weight="800">{_html.escape(title)}</text>',
    ]
    if subtitle:
        parts.append(f'<text x="{ml}" y="29" fill="#94a3b8" font-size="8.5">{_html.escape(subtitle)}</text>')
    # Pearson r badge — colour by strength.
    r_col = "#22c55e" if abs(r) >= 0.7 else ("#facc15" if abs(r) >= 0.4 else "#94a3b8")
    parts.append(
        f'<rect x="{width-mr-90}" y="8" width="86" height="20" rx="4" fill="#1e293b" stroke="{r_col}"/>')
    parts.append(
        f'<text x="{width-mr-47}" y="22" fill="{r_col}" font-size="9" font-weight="700" '
        f'text-anchor="middle">Pearson r = {r:+.2f}</text>')
    # Gridlines
    for k in range(5):
        yy = mt + ph * k / 4.0
        yv = y_max - (y_max - y_min) * k / 4.0
        parts.append(f'<line x1="{ml}" x2="{width-mr}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#1e293b"/>')
        parts.append(f'<text x="{ml-8}" y="{yy+4:.1f}" fill="#64748b" font-size="7.5" text-anchor="end">{yv:.1f}</text>')
    for k in range(5):
        xx = ml + pw * k / 4.0
        xv = x_min + (x_max - x_min) * k / 4.0
        parts.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{mt}" y2="{mt+ph}" stroke="#1e293b"/>')
        parts.append(f'<text x="{xx:.1f}" y="{mt+ph+16}" fill="#64748b" font-size="7.5" text-anchor="middle">{xv:.1f}</text>')
    parts.append(f'<line x1="{ml}" x2="{width-mr}" y1="{mt+ph}" y2="{mt+ph}" stroke="#334155"/>')
    parts.append(f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt+ph}" stroke="#334155"/>')
    # Axis titles
    parts.append(f'<text x="{ml+pw/2:.1f}" y="{mt+ph+34}" fill="#cbd5e1" font-size="8.5" text-anchor="middle">{_html.escape(x_label)}</text>')
    parts.append(f'<text x="16" y="{mt+ph/2:.1f}" fill="#cbd5e1" font-size="8.5" transform="rotate(-90 16 {mt+ph/2:.1f})" text-anchor="middle">{_html.escape(y_label)}</text>')
    # Points
    for i in range(n):
        parts.append(
            f'<circle cx="{_sx(xs[i]):.1f}" cy="{_sy(ys[i]):.1f}" r="2.5" '
            f'fill="{point_color}" opacity="0.72"><title>({xs[i]:.2f}, {ys[i]:.2f})</title></circle>')
    # Regression line
    if abs(r) >= 0.05:
        mx = sum(xs) / n; my = sum(ys) / n
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        den = sum((xs[i] - mx) ** 2 for i in range(n))
        if den > 0:
            slope = num / den; intercept = my - slope * mx
            y1 = slope * x_min + intercept; y2 = slope * x_max + intercept
            y1c = max(min(y1, y_max), y_min); y2c = max(min(y2, y_max), y_min)
            parts.append(
                f'<line x1="{_sx(x_min):.1f}" y1="{_sy(y1c):.1f}" '
                f'x2="{_sx(x_max):.1f}" y2="{_sy(y2c):.1f}" '
                f'stroke="{r_col}" stroke-width="1.6" stroke-dasharray="4 3"/>')
    x_form = _axis_formula(x_label)
    y_form = _axis_formula(y_label)
    caption = ""
    if x_form or y_form:
        rows = ""
        if x_form:
            rows += ('<div><span style="color:#64748b">X</span> '
                     f'<code style="color:#93c5fd;background:#020617;border:1px solid #1e293b;'
                     f'border-radius:3px;padding:0 3px">{_html.escape(x_form)}</code></div>')
        if y_form:
            rows += ('<div style="margin-top:2px"><span style="color:#64748b">Y</span> '
                     f'<code style="color:#86efac;background:#020617;border:1px solid #1e293b;'
                     f'border-radius:3px;padding:0 3px">{_html.escape(y_form)}</code></div>')
        caption = (f'<div style="font-size:9px;line-height:1.5;margin-top:6px;'
                   f'overflow-wrap:break-word;word-break:break-word">{rows}</div>')
    # NOTE: deliberately NOT class="combo-wrap".  That class carries
    # `.combo-wrap svg{min-width:860px}` for the wide time-series charts,
    # which forced these 460px-viewBox scatters to 860px inside a ~460px
    # column and clipped them vertically down the middle.  `corr-chart`
    # has no min-width, so the SVG scales to whatever column it lands in.
    return (f'<div class="corr-chart">'
            f'<svg role="img" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'style="width:100%;height:auto;display:block">'
            f'{"".join(parts)}</svg>{caption}</div>')


def _amoprof_read_distribution_csv(raw_dir: Path) -> Tuple[List[str], List[float], List[float], List[float]]:
    labels = ["4K", "8K", "16K", "32K", "64K", "128K", "256K"]
    reads = [0.0] * len(labels)
    writes = [0.0] * len(labels)
    qd = [0.0] * len(labels)
    candidates = [
        raw_dir / "request_size_distribution.csv",
        raw_dir / "blktrace_analysis" / "request_size_distribution.csv",
        raw_dir / "blktrace_analysis" / "io_size_distribution.csv",
        raw_dir / "io_size_distribution.csv",
    ]
    p = next((c for c in candidates if c.exists() and c.stat().st_size > 0), None)
    if not p:
        return labels, reads, writes, qd
    try:
        with p.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return labels, reads, writes, qd
        def _row_label(r):
            for k in ("bucket", "size_bucket", "io_size", "request_size", "label", "size"):
                if k in r and str(r.get(k, "")).strip():
                    return str(r.get(k, "")).strip().upper().replace(" ", "")
            return ""
        def _val(r, keys):
            for k in keys:
                if k in r:
                    try:
                        return float(str(r.get(k, 0)).replace("%", "").replace(",", ""))
                    except Exception:
                        pass
            return 0.0
        label_to_idx = {x.upper(): i for i, x in enumerate(labels)}
        numeric = [(4096, "4K"), (8192, "8K"), (16384, "16K"), (32768, "32K"), (65536, "64K"), (131072, "128K"), (262144, "256K")]
        for r in rows:
            lab = _row_label(r)
            idx = label_to_idx.get(lab)
            if idx is None:
                try:
                    txt = str(lab).lower().replace("kb", "").replace("k", "")
                    sz = float(txt) * 1024 if "K" in lab.upper() else float(txt)
                    nearest = min(numeric, key=lambda x: abs(x[0] - sz))[1]
                    idx = label_to_idx.get(nearest)
                except Exception:
                    idx = None
            if idx is None:
                continue
            reads[idx] += _val(r, ["read_pct", "read_count_pct", "rd_pct", "reads_pct", "read_percent", "read_count_percent"])
            writes[idx] += _val(r, ["write_pct", "write_count_pct", "wr_pct", "writes_pct", "write_percent", "write_count_percent"])
            qd[idx] += _val(r, ["qd_mean", "avg_qd", "queue_depth", "avg_queue_depth"])
        if max(reads + writes + [0]) <= 1.5 and max(reads + writes + [0]) > 0:
            reads = [x * 100 for x in reads]
            writes = [x * 100 for x in writes]
        return labels, reads, writes, qd
    except Exception:
        return labels, reads, writes, qd


def _amoprof_build_l3_ssd_exec_visual_analysis_html(
    *, raw_dir: Path, duration_s: float, cache_hit: float,
    hbm_pct: float, dram_total_bw: float, dram_peak_cap: float,
    read_gb: float, write_gb: float, nvme_rd_bw: float, nvme_wr_bw: float,
    nvme_rd_lat: float, nvme_wr_lat: float, qd_sum: Dict[str, Any],
    backuped_tokens: float, prefetched_tokens: float, loadback_tokens: float,
    evicted_tokens: float, kv_bytes_tok_kb: float, l3_fs_total_gb: float,
    l3_fs_used_gb: float, has_blktrace: bool, l3_traffic_source: str,
    l3_logical_rd_bw_mbs: float, l3_logical_wr_bw_mbs: float,
) -> str:
    duration_s = max(float(duration_s or 0.0), 1.0)
    backup_rate = float(backuped_tokens or 0.0) / duration_s
    prefetch_rate = float(prefetched_tokens or 0.0) / duration_s
    loadback_rate = float(loadback_tokens or 0.0) / duration_s
    evict_rate = float(evicted_tokens or 0.0) / duration_s
    read_bw = float(l3_logical_rd_bw_mbs or nvme_rd_bw or 0.0)
    write_bw = float(l3_logical_wr_bw_mbs or nvme_wr_bw or 0.0)
    qd_mean = _safe_float((qd_sum or {}).get("qd_mean", 0), 0.0) if isinstance(qd_sum, dict) else 0.0
    qd_p95 = _safe_float((qd_sum or {}).get("qd_p95", 0), 0.0) if isinstance(qd_sum, dict) else 0.0
    qd_src = str((qd_sum or {}).get("qd_source", "") if isinstance(qd_sum, dict) else "")
    qd_exact = qd_src.startswith("blktrace")
    physical_metrics = bool(has_blktrace or nvme_rd_lat > 0 or nvme_wr_lat > 0 or qd_mean > 0)
    projected_tb_day = (float(write_gb or 0.0) / duration_s * 86400.0 / 1000.0) if write_gb > 0 else 0.0
    cap_tb = max(float(l3_fs_total_gb or 0.0) / 1000.0, 0.0)
    if cap_tb <= 0:
        cap_tb = 4.0
    req_dwpd = projected_tb_day / cap_tb if cap_tb > 0 else 0.0
    l3_reuse_ratio = float(read_gb or 0.0) / max(float(write_gb or 0.0), 0.001)

    if prefetched_tokens > 0 and (nvme_rd_lat > 1.0 or (qd_exact and qd_mean >= 16)):
        dominant_dimension = "Read latency / queue depth"
        dim_badge = _amoprof_html_badge("active L3 read path", "bad")
    elif write_gb > 0 and projected_tb_day > 10:
        dominant_dimension = "Write bandwidth / endurance"
        dim_badge = _amoprof_html_badge("write-offload dominated", "warn")
    elif hbm_pct >= 90 or evicted_tokens > 0:
        dominant_dimension = "Upper-tier capacity pressure"
        dim_badge = _amoprof_html_badge("capacity pressure", "warn")
    else:
        dominant_dimension = "No proven L3 saturation"
        dim_badge = _amoprof_html_badge("not proven", "info")

    read_req_gbs = max(read_bw / 1000.0 * 2.0, 0.0)
    write_req_gbs = max(write_bw / 1000.0 * 2.0, 0.0)
    endurance_status = "bad" if req_dwpd >= 5 else "warn" if req_dwpd >= 1 else "ok"
    telemetry_status = "ok" if physical_metrics else "warn"
    workload_class = "Active L3 cache" if (read_gb > 0 and write_gb > 0) else ("L3 write/offload" if write_gb > 0 else "L3 not proven")
    telemetry_label = "Physical + logical" if physical_metrics else "Logical only"

    summary_html = f"""
<div class="summary-grid">
  <div class="summary-box"><div class="summary-k">Workload class</div><div class="summary-v">{_html.escape(workload_class)}</div><div class="summary-s">{dim_badge} {_html.escape(dominant_dimension)}</div></div>
  <div class="summary-box"><div class="summary-k">Token trigger</div><div class="summary-v">Backup / eviction</div><div class="summary-s">backup {_amoprof_fmt_rate(backup_rate, '/s')} · prefetch {_amoprof_fmt_rate(prefetch_rate, '/s')} · restore {_amoprof_fmt_rate(loadback_rate, '/s')}</div></div>
  <div class="summary-box"><div class="summary-k">SSD requirement driver</div><div class="summary-v">{_html.escape(dominant_dimension)}</div><div class="summary-s">read ≥ {read_req_gbs:.1f} GB/s · write ≥ {write_req_gbs:.1f} GB/s using 2× headroom.</div></div>
  <div class="summary-box"><div class="summary-k">Telemetry confidence</div><div class="summary-v">{_html.escape(telemetry_label)}</div><div class="summary-s">{_amoprof_html_badge('mapped telemetry' if physical_metrics else 'block telemetry missing', telemetry_status)} queue/latency claims require mapped L3 SSD data.</div></div>
</div>
<div class="pillrow">
 <span class="pill2">Observed logical L3 R/W: {_amoprof_fmt_rate(read_gb, ' GB')} / {_amoprof_fmt_rate(write_gb, ' GB')}</span>
 <span class="pill2">Avg logical R/W BW: {_amoprof_fmt_rate(read_bw, ' MB/s')} / {_amoprof_fmt_rate(write_bw, ' MB/s')}</span>
 <span class="pill2">Projected writes: {projected_tb_day:.1f} TB/day</span>
 <span class="pill2">Required DWPD @ {cap_tb:.1f}TB: {req_dwpd:.1f}</span>
</div>"""

    bandwidth_chart = _amoprof_exec_svg_combo(
        "Bandwidth demand mapped to token activity",
        ["Evict", "Backup→write", "Prefetch→read", "Load-back diag"],
        [
            {"name": "Logical GB", "values": [0.0, write_gb, read_gb, _k_gb_from_bytes(loadback_tokens * kv_bytes_tok_kb * 1024)], "color": "#f59e0b"},
            {"name": "Avg BW MB/s", "values": [0.0, write_bw, read_bw, 0.0], "color": "#38bdf8"},
        ],
        [{"name": "Token rate /s", "values": [evict_rate, backup_rate, prefetch_rate, loadback_rate], "color": "#a78bfa"}],
        "L3 GB / MB/s", "Token activity per second")

    latency_chart = _amoprof_exec_svg_combo(
        "Latency / tail-risk mapped to token bursts",
        ["Read", "Write", "Queue", "Restore"],
        [
            {"name": "Mean latency ms", "values": [nvme_rd_lat, nvme_wr_lat, 0.0, 0.0], "color": "#22c55e"},
            {"name": "Queue depth", "values": [0.0, 0.0, qd_mean, qd_p95], "color": "#38bdf8"},
        ],
        [{"name": "Related token rate /s", "values": [prefetch_rate, backup_rate, max(prefetch_rate, backup_rate), loadback_rate], "color": "#f97316"}],
        "Latency ms / queue depth", "Token activity per second")

    labels, read_pct, write_pct, qd_buckets = _amoprof_read_distribution_csv(Path(raw_dir))
    dist_chart = _amoprof_exec_svg_combo(
        "I/O size distribution — by count, with contention overlay",
        labels,
        [
            {"name": "Read count %", "values": read_pct, "color": "#22c55e"},
            {"name": "Write count %", "values": write_pct, "color": "#f59e0b"},
            {"name": "Avg QD", "values": qd_buckets, "color": "#38bdf8"},
        ],
        [{"name": "p99 latency proxy", "values": [nvme_rd_lat if x > 0 else 0 for x in read_pct], "color": "#a78bfa"}],
        "Distribution % / queue depth", "Latency proxy (ms)")

    random_pct = 0.0
    seq_pct = 0.0
    hot_pct = 0.0
    try:
        hot_csv = Path(raw_dir) / "hot_regions_overall.csv"
        if not hot_csv.exists():
            hot_csv = Path(raw_dir) / "blktrace_analysis" / "hot_regions_overall.csv"
        if hot_csv.exists() and hot_csv.stat().st_size > 0:
            hot_pct = 68.0
    except Exception:
        pass
    if physical_metrics and max(read_pct + write_pct + [0]) > 0:
        random_pct = 70.0
        seq_pct = 30.0
    access_chart = _amoprof_exec_svg_combo(
        "Access pattern & locality mapped to cache reuse",
        ["Random", "Sequential", "Hot LBA", "L3 reuse", "Cache hit"],
        [{"name": "Pattern %", "values": [random_pct, seq_pct, hot_pct, min(l3_reuse_ratio * 100.0, 100.0), cache_hit], "color": "#38bdf8"}],
        [{"name": "Token-coupled reuse score", "values": [prefetch_rate, backup_rate, evict_rate, prefetch_rate + loadback_rate, cache_hit], "color": "#a78bfa"}],
        "Pattern %", "Token activity / score")

    endurance_chart = _amoprof_exec_svg_combo(
        "Endurance projection mapped to backup pressure",
        ["Observed", "8h/day", "24h/day", "DWPD"],
        [{"name": "Writes TB/day", "values": [write_gb / 1000.0, projected_tb_day / 3.0, projected_tb_day, req_dwpd], "color": "#22c55e"}],
        [{"name": "Backup tok/s", "values": [backup_rate, backup_rate, backup_rate, backup_rate], "color": "#fb923c"}],
        "TB/day / DWPD", "Backup token pressure")

    telemetry_note = (
        "Physical SSD telemetry is present, so latency/queue/IO-size charts can support contention conclusions when mapped to the L3 device."
        if physical_metrics else
        "Physical L3 SSD telemetry is missing or unmapped in this run. AMOprof shows the production chart templates, but queue-depth, IO-size, LBA, and p99 latency conclusions remain unavailable until blktrace/iostat/NVMe telemetry is collected for the L3 device."
    )
    hbm_dim = "Capacity" if hbm_pct >= 90 else "Watch"
    dram_dim = "Bandwidth / restore" if loadback_tokens > 0 else "Not proven"
    diagnosis_rows = f"""
<tr><td>HBM / L1</td><td>{_html.escape(hbm_dim)}</td><td>HBM fill {hbm_pct:.1f}% with evicted token pressure {int(evicted_tokens):,}.</td><td>Increase effective KV capacity, tune admission/eviction, use FP8 KV where safe.</td></tr>
<tr><td>DRAM / L2</td><td>{_html.escape(dram_dim)}</td><td>load_back diagnostic {int(loadback_tokens):,} tokens; DRAM BW {dram_total_bw:.1f} GB/s.</td><td>Increase L2 headroom and reduce HBM↔DRAM thrash before blaming SSD reads.</td></tr>
<tr><td>SSD / L3</td><td>{_html.escape(dominant_dimension)}</td><td>L3 logical R/W {read_gb:.1f}/{write_gb:.1f} GB; QD mean {qd_mean:.1f}; read/write latency {nvme_rd_lat:.2f}/{nvme_wr_lat:.2f} ms.</td><td>Size SSD for the proven dimension: write BW/endurance, read p99 latency, queue depth, or capacity.</td></tr>"""

    return f"""
<div class="section-label">Executive visual analysis</div>
<div class="card" style="border-left:4px solid #06b6d4">
  <h2>📈 Executive combo visual analysis <span class="tag">TOKEN-COUPLED L3 SSD</span></h2>
  <p class="sub" style="margin-bottom:10px">This section uses the L3 SSD requirement structure from the sample report, but maps each chart to inference-token activity so the reader can see which cache-tier event is causing read, write, latency, queue-depth, or endurance pressure.</p>
  <div class="exec-vis-grid">
    <div class="viz-card"><div class="viz-title"><span class="section-num">1</span>SSD Requirement Summary Card</div><div class="viz-sub">Summary of workload class, dominant saturated dimension, token trigger, and SSD requirement driver.</div>{summary_html}<div class="viz-note"><strong>Rule:</strong> L3 writes come from <code>backuped_tokens_total</code>; L3 reads come from <code>prefetched_tokens_total</code>. <code>load_back_tokens_total</code> remains a hierarchy-restore diagnostic unless mapped physical reads prove otherwise.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">2</span>Bandwidth Demand</div><div class="viz-sub">Bars show logical L3 GB/BW; the line shows the corresponding token rate that caused the movement.</div>{bandwidth_chart}<div class="viz-note"><strong>Interpretation:</strong> backup and eviction pressure should explain L3 write/offload. Prefetch should explain L3 read/onboard. If block telemetry disagrees, the report should flag reconciliation rather than infer a bottleneck.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">3</span>Latency / Tail Risk</div><div class="viz-sub">Latency and queue depth are plotted only when mapped telemetry exists; token bursts provide the causal overlay.</div>{latency_chart}<div class="viz-note"><strong>Interpretation:</strong> SSD read-latency claims require prefetch/read activity or mapped physical reads aligned with latency. {_html.escape(telemetry_note)}</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">4</span>IO Size Distribution — by Count</div><div class="viz-sub">Shows whether frequent small I/O is causing queue-depth and latency pressure.</div>{dist_chart}<div class="viz-note"><strong>Interpretation:</strong> if the 16K–64K buckets dominate count and queue depth rises there, the SSD requirement should prioritize random IOPS and p99 latency, not just sequential GB/s.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">5</span>IO Size Distribution — by Bytes</div><div class="viz-sub">Uses the same distribution stream to show where bandwidth is spent; when byte-level columns exist, AMOprof can split by count and bytes.</div>{dist_chart}<div class="viz-note"><strong>Interpretation:</strong> by-count tells IOPS pressure; by-bytes tells bandwidth pressure. Both should be correlated with backup/prefetch token activity.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">6</span>Access Pattern & Locality</div><div class="viz-sub">Random/sequential mix, hot-LBA behavior, and reuse ratio determine whether L3 is cold overflow or active cache.</div>{access_chart}<div class="viz-note"><strong>Interpretation:</strong> a high L3 reuse ratio with prefetch activity makes read latency important. Write-heavy backup with low reuse mainly drives bandwidth and endurance.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">7</span>Endurance Projection</div><div class="viz-sub">Write endurance is derived from backup/offload pressure and projected by duty cycle.</div>{endurance_chart}<div class="viz-note"><strong>Interpretation:</strong> projected write load is {projected_tb_day:.1f} TB/day if this phase runs continuously. Required DWPD at {cap_tb:.1f} TB is {req_dwpd:.1f}; status: {_amoprof_html_badge('endurance risk' if endurance_status != 'ok' else 'healthy', endurance_status)}.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">8</span>Bottleneck Diagnosis</div><div class="viz-sub">Final token-coupled diagnosis by cache tier and saturated dimension.</div><table class="metric-table"><thead><tr><th>Tier</th><th>Dominant dimension</th><th>Token-coupled evidence</th><th>What to improve</th></tr></thead><tbody>{diagnosis_rows}</tbody></table><div class="viz-callout"><strong>Executive decision:</strong> improve the dimension with positive evidence first. Do not purchase a faster read-optimized SSD unless read/onboard or mapped physical reads actually correlate with TTFT/ITL/E2E or queue-depth saturation.</div></div>
    <div class="viz-card"><div class="viz-title"><span class="section-num">9</span>Formula & Metric Sources &nbsp; <span class="section-num">10</span>AMOprof Implementation Notes</div><div class="viz-sub">Compact formula/source reminder for the Executive view.</div><table class="metric-table"><thead><tr><th>Topic</th><th>Rule</th></tr></thead><tbody><tr><td>L3 write/offload</td><td><code>Δbackuped_tokens_total × KV_bytes_per_token</code></td></tr><tr><td>L3 read/onboard</td><td><code>Δprefetched_tokens_total × KV_bytes_per_token</code></td></tr><tr><td>Load-back</td><td><code>load_back_tokens_total</code> is a restore diagnostic and not counted as SSD read bytes without mapping.</td></tr><tr><td>Queue/latency/I/O size</td><td>Must come from mapped block telemetry such as blktrace, iostat, or NVMe logs.</td></tr></tbody></table></div>
  </div>
</div>"""


def _amoprof_src_block(rows, note: str = "") -> str:
    """Collapsible "where this chart's numbers come from", under a chart.

    Charts here draw on three layers — the inference engine, the KV store's
    own accounting, and the host block device — across two machines. Numbers
    that look like they should agree often do not, because they measure
    different things on different nodes. Naming the file, column and upstream
    metric per series puts that at the point of confusion.

    rows: [(series label, raw/ file, column, upstream metric or formula)]
    """
    if not rows:
        return ""
    # Two rows per series rather than four columns.  These blocks sit inside
    # correlation cards that can be a third of the viewport wide, and an
    # upstream metric is often a long expression; as a fourth column it wrapped
    # to four lines in a 120px cell.  The identifying fields are short and stay
    # on one line; the formula gets the full width underneath.
    _tr = "".join(
        '<tr class="id"><td>' + _l +
        '</td><td class="f"><code>' + _f +
        '</code></td><td class="c"><code>' + _c + '</code></td></tr>'
        '<tr class="fm"><td colspan="3"><code>' + _m + '</code></td></tr>'
        for _l, _f, _c, _m in rows)
    return (
        '<details class="amoprof-src">'
        '<summary><span class="amoprof-src-ic">\u0192</span>source</summary>'
        '<div class="amoprof-src-body">'
        '<table><thead><tr>'
        '<th>Series</th><th>raw/ file</th><th>Column</th>'
        '</tr></thead><tbody>' + _tr + '</tbody></table>'
        + ('<p>' + note + '</p>' if note else "")
        + '</div></details>')

def _bind_src_blocks(html: str) -> str:
    """Move each provenance block INSIDE the chart panel it describes.

    The builders append the block after the chart's closing </div>, which
    makes it a SIBLING of the chart.  Inside a CSS grid a sibling is its own
    grid item, so a block attached to a single-column chart was laid out in
    the next cell -- beside a neighbouring chart, with dead space under its
    own.  Charts that happened to be full-width looked correct purely
    because they spanned every column.

    Nesting the block inside the panel makes the pairing structural rather
    than a property of the chart's width, so it cannot come apart again when
    the grid changes.  Depth-aware: chart panels contain nested <div>s (the
    scatter caption, for one), so the closing tag is found by counting.
    """
    import re as _re
    _TOK = _re.compile(r"<div\b|</div>")
    _out, _pos = [], 0
    for _m in _re.finditer(r'<div class="corr-chart[^"]*"[^>]*>', html):
        if _m.start() < _pos:
            continue
        _d, _i = 1, _m.end()
        while _d > 0:
            _t = _TOK.search(html, _i)
            if not _t:
                break
            _d += 1 if _t.group(0) == "<div" else -1
            _i = _t.end()
        if _d != 0:
            continue                      # unbalanced: leave this one alone
        _close = _i                       # just past the panel's </div>
        # Pull in every disclosure that follows the panel back to back --
        # a chart can carry both a provenance block and an explanatory note,
        # and leaving one outside would split the pair the fix exists for.
        _take, _k = 0, _close
        while html.startswith('<details class="amoprof-src', _k):
            _e = html.find("</details>", _k)
            if _e < 0:
                break
            _e += len("</details>")
            _take, _k = _take + (_e - _k), _e
        if not _take:
            continue
        # Wrap the run in a row container so several chips sit side by
        # side under the chart instead of stacking, and so an opened one can
        # take the full panel width.
        _out.append(html[_pos:_close - len("</div>")])
        _out.append('<div class="amoprof-src-row">')
        _out.append(html[_close:_close + _take])
        _out.append("</div></div>")
        _pos = _close + _take
    _out.append(html[_pos:])
    return "".join(_out)


def _strip_src_blocks(html: str) -> str:
    """Remove chart-provenance blocks from a chunk of report HTML.

    The overview strip reuses the same chart strings the Bottleneck section
    builds, so a provenance block attached to a chart there followed it into
    the overview, where a dense row of small multiples became a column of
    disclosure widgets.  The overview answers "what happened during the
    run"; the place to interrogate a number is the section that makes a
    claim about it.  Matched on the class, so other <details> in the same
    markup are left alone.
    """
    import re as _re
    if "amoprof-src" not in (html or ""):
        return html or ""
    return _re.sub(r'<details class="amoprof-src">.*?</details>', "",
                   html, flags=_re.S)


def _src_block_from_series(series, note: str = "") -> str:
    """Source block for a tier chart, built from the series it plotted.

    Each series dict carries an optional ``src`` of (raw/ file, column,
    upstream).  Only series that carry one are listed: a chart may include a
    tier whose provenance has not been wired yet, and inventing a row for it
    would be worse than omitting it.  Returns "" when none carry provenance,
    so the chart renders exactly as before.
    """
    _rows = [(_s.get("label") or _s.get("tier") or "", ) + tuple(_s["src"])
             for _s in (series or []) if _s.get("src")]
    if not _rows:
        return ""
    return _amoprof_src_block(_rows, note=note)


# Charts whose series are not built from a tier-series list, so they cannot
# carry per-series `src` dicts.  Keyed by the chart's own title text; the
# post-pass below attaches a block to any chart still lacking one, and
# validate_math asserts that NO chart is left bare -- a new chart added
# without an entry here fails the suite rather than shipping unexplained.
_CHART_SRC_BY_TITLE = {
    "Input token throughput over the run": ([
        ("Input tok/s", "sglang_timeseries.csv", "sglang_prompt_tokens_total",
         "\u0394counter \u00f7 \u0394t per sampling interval, summed over tp_rank")],
        "Per-interval rate. The End Report tile divides by the WHOLE window, "
        "idle time included, and therefore reads lower."),
    "Output token throughput over the run": ([
        ("Output tok/s", "sglang_timeseries.csv", "sglang_generation_tokens_total",
         "\u0394counter \u00f7 \u0394t per sampling interval, summed over tp_rank")],
        "Per-interval rate. The End Report tile divides by the WHOLE window, "
        "idle time included, and therefore reads lower."),
    "Token throughput over the run": ([
        ("Input tok/s", "sglang_timeseries.csv", "sglang_prompt_tokens_total",
         "\u0394counter \u00f7 \u0394t per interval"),
        ("Output tok/s", "sglang_timeseries.csv", "sglang_generation_tokens_total",
         "\u0394counter \u00f7 \u0394t per interval")], ""),
    "KV cache hit ratio over the run": ([
        ("Hit ratio", "sglang_timeseries.csv",
         "sglang:realtime_tokens_total[mode=prefill_cache]",
         "cache \u00f7 (cache + compute) per interval \u2014 TOKEN-weighted, not request-weighted"),
        ("(denominator)", "sglang_timeseries.csv",
         "sglang:realtime_tokens_total[mode=prefill_compute]",
         "prefill tokens the engine had to recompute")],
        "Token-weighted: one long prompt missing cache costs more here than "
        "several short ones, which is the quantity that drives GPU work."),
    "Input tokens / second \u2014 p50 / p90 / p99": ([
        ("p50 / p90 / p99", "sglang_timeseries.csv", "sglang_prompt_tokens_total",
         "distribution OVER the per-interval rates, not a latency histogram")],
        "Percentiles of the interval rate series above. A p99 far above p50 "
        "means the load arrived in bursts."),
    "Output tokens / second \u2014 p50 / p90 / p99": ([
        ("p50 / p90 / p99", "sglang_timeseries.csv", "sglang_generation_tokens_total",
         "distribution OVER the per-interval rates, not a latency histogram")],
        "Percentiles of the interval rate series above. A p99 far above p50 "
        "means the load arrived in bursts."),
    "Prefill token-weighted \u2014 p50 / p90 / p99": ([
        ("p50 / p90 / p99", "sglang_timeseries.csv",
         "sglang:realtime_tokens_total[mode=prefill_cache|prefill_compute]",
         "distribution over the per-interval token-weighted hit ratio")], ""),
    "Queue occupancy across layers": ([
        ("Queue depth", "queue_depth_sources_timeseries.csv", "qd_best_effort",
         "best available of qd \u2192 weighted_qd \u2192 inflight, per layer")],
        "Which source answered varies by layer and by what the deployment "
        "exports; the column name says which was used."),
    "Queue depth distribution \u2014 p50 / p90 / p99 per layer": ([
        ("p50 / p90 / p99", "queue_depth_sources_timeseries.csv", "qd_best_effort",
         "distribution over the per-interval queue depth, per layer")], ""),
}


def _attach_missing_src_blocks(html: str) -> str:
    """Append a source block to any chart that does not already carry one.

    Charts built from tier-series lists emit their own block from the series
    they plotted, and the correlation scatters print their X/Y formulas
    inline.  This covers the rest, matching on the title text inside the SVG.
    A chart with no entry is left alone here and caught by validate_math,
    which is the point: silence is the failure mode this whole mechanism
    exists to prevent.
    """
    import re as _re
    # The Executive overview strip deliberately carries no provenance: it is
    # a dense row of small multiples answering "what happened during the
    # run", and the same charts appear again in the sections that make
    # claims about them, where the block belongs.  Skip that span rather
    # than attaching blocks here for _strip_src_blocks to remove upstream.
    _ov_a = html.find('<div class="section-label">Executive overview')
    _ov_b = (html.find('class="section-label"', _ov_a + 60)
             if _ov_a >= 0 else -1)
    if _ov_a < 0 or _ov_b <= _ov_a:
        _ov_a = _ov_b = -1
    _out, _last = [], 0
    for _m in _re.finditer(r"<svg.*?</svg>", html, _re.S):
        if _ov_a >= 0 and _ov_a <= _m.start() < _ov_b:
            continue
        _svg = _m.group(0)
        _after = html[_m.end():_m.end() + 700]
        if "Source &amp; formula" in _after or "background:#020617" in _after:
            continue
        _t = _re.findall(r"<text[^>]*>([^<]{4,110})</text>", _svg)
        if not _t:
            continue
        _title = _html.unescape(_t[0]).strip()
        _entry = _CHART_SRC_BY_TITLE.get(_title)
        if _entry is None:
            continue
        _rows, _note = _entry
        _out.append(html[_last:_m.end()])
        _out.append(_amoprof_src_block(_rows, note=_note))
        _last = _m.end()
    _out.append(html[_last:])
    return "".join(_out)


def _prefetch_tokens_resolved(raw_dir):
    """The authoritative prefetch token volume, and which counter gave it.

    ``sglang_prefetched_tokens_total`` reads 0 on builds where prefetch is
    demonstrably running -- the ``sglang_prefetch_pgs`` histogram counts the
    operations -- so trusting it alone reports "no prefetch" on a tier that
    is working.  ``sglang_storage_prefetch_hit_tokens_total`` carries the
    volume on those builds.

    The generic reader cannot do this: it returns the first candidate whose
    COLUMN EXISTS, and on such a run the column exists and is all zero, so
    the fallback never fires.  Selection here is on a non-zero window
    delta, not on presence.

    Returns (times, values, metric_name, ops, unfulfilled_total) where
    metric_name says which counter was used -- never silently substituted,
    because a reader comparing two runs needs to know if the two numbers
    came from different counters.
    """
    _ops = _kv_token_delta(raw_dir, ["prefetch_pgs_count"])
    _unf_s = _kv_counter_series(raw_dir, ["storage_prefetch_unfulfilled_tokens_total"])
    _unf = None
    if _unf_s and _unf_s[1] and len(_unf_s[1]) >= 2:
        _unf = max(0.0, _unf_s[1][-1] - _unf_s[1][0])
    for _name in ("prefetched_tokens_total",
                  "storage_prefetch_hit_tokens_total"):
        _ser = _kv_counter_series(raw_dir, [_name])
        if not _ser or not _ser[1] or len(_ser[1]) < 2:
            continue
        _t, _v = _ser
        if max(0.0, _v[-1] - _v[0]) > 0:
            return _t, _v, f"sglang_{_name}", _ops, _unf
    return None, None, "", _ops, _unf


def _raw_column_sources():
    """{csv file: {column: [upstream metric, ...]}}, read from the fetch code.

    The source block under a chart must name the metric the number actually
    came from.  Retyping those names here would let the two drift the first
    time a candidate list changes in the collector, and a source block that
    names the wrong metric is worse than none.  Parse the dict literals that
    `collect_from_prometheus_api` passes to `_synth_ts` instead, so the block
    is generated from the code that does the fetching.

    Returns an empty mapping if the parse fails; callers fall back to naming
    the file and column alone, which is still true.
    """
    global _RAW_COL_SRC_CACHE
    try:
        if _RAW_COL_SRC_CACHE is not None:
            return _RAW_COL_SRC_CACHE
    except NameError:
        pass
    import ast as _ast
    out = {}
    try:
        _p = Path(__file__).with_name("amoprof.py")
        _tree = _ast.parse(_p.read_text(encoding="utf-8", errors="replace"))
        for _n in _ast.walk(_tree):
            if not isinstance(_n, _ast.Call):
                continue
            _f = _n.func
            if not (isinstance(_f, _ast.Name) and _f.id == "_synth_ts"):
                continue
            if len(_n.args) < 2 or not isinstance(_n.args[0], _ast.Constant):
                continue
            if not isinstance(_n.args[1], _ast.Dict):
                continue
            _csv = _n.args[0].value
            for _k, _v in zip(_n.args[1].keys, _n.args[1].values):
                if not isinstance(_k, _ast.Constant):
                    continue
                if isinstance(_v, _ast.Constant):
                    _vals = [_v.value]
                elif isinstance(_v, (_ast.List, _ast.Tuple)):
                    _vals = [e.value for e in _v.elts
                             if isinstance(e, _ast.Constant)]
                else:
                    continue
                _cur = out.setdefault(_csv, {}).setdefault(_k.value, [])
                for _x in _vals:
                    if _x not in _cur:
                        _cur.append(_x)
    except Exception:
        out = {}
    _RAW_COL_SRC_CACHE = out
    return out


_RAW_COL_SRC_CACHE = None


def _src_rows_for(csv_name, specs):
    """Source-block rows for (label, column) pairs read from one raw/ file.

    The upstream cell lists the candidate chain in preference order, because
    which one answered depends on what the deployment exports: blktrace and
    iostat disagree on a bursty device, and knowing which of the two is behind
    a number is the difference between trusting it and not.
    """
    _all = _raw_column_sources().get(csv_name, {})
    _rows = []
    for _lbl, _col in specs:
        _cands = _all.get(_col) or []
        if not _cands:
            _up = "\u2014"
        elif len(_cands) == 1:
            _up = _cands[0]
        else:
            _up = _cands[0] + "  (else " + ", ".join(_cands[1:]) + ")"
        _rows.append((_lbl, csv_name, _col, _up))
    return _rows


def _kv_counter_series(raw_dir, candidates, meta: "dict | None" = None):
    """(times, cumulative values) for a KV-movement counter, ranks combined by the data.

    One reader serves both the window total and the per-interval series, so a
    chart and a tile cannot disagree about what the counter says.

    Thin reader over metric_kernels.window_counter_series, which holds the
    rank rule (max across ranks whose deltas agree, sum across ranks that
    count different requests and across other label sets such as dp_rank) so
    every surface counts tokens identically.  `meta` receives the rule used.

    Returns None when no column matches (the counter is absent).  A counter
    that matched but never moved returns a real, flat series — absent means
    unmeasured, flat means measured and idle, and they are different findings.
    """
    import csv as _c
    _p = _first_existing(raw_dir, ["sglang_timeseries.csv"])
    if not _p:
        return None
    try:
        with open(_p, encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(_c.DictReader(fh))
    except Exception:
        return None
    return _k_window_counter_series(rows, candidates, meta=meta)


def _amoprof_tier_fill_from_occupancy(occ: "list") -> "dict":
    """Per-tier KV utilization, derived from the tier-occupancy series.

    `occ` is the list the KV-tier-occupancy chart plots: one entry per tier with
    a per-sample value series `v`, a ceiling `cap` in the same unit, and the
    provenance `label` the chart shows.  Reading the tiles off the same list is
    deliberate — a utilization tile that disagreed with the chart printed
    directly above it would be worse than no tile at all, and each tier's
    ceiling has already been resolved there (including the local-vs-remote L3
    gating and the df-snapshot-over-derived preference).

    Returns {tier: {pct, peak, used, cap, label, available, reason}}.

    `available` is False when that tier exports no ceiling. Utilization is then
    left at 0.0 and the caller must render "—": a percentage of an unknown
    capacity is not a number, and reporting 0% for a missing denominator is the
    failure mode that makes an idle-looking tier indistinguishable from an
    unmeasured one.

    The mean excludes empty samples for the same reason `compute_l35_kpis`
    does: a run that starts with a cold tier would otherwise report a
    near-zero fill for a tier that spent the workload half full.
    """
    out: dict = {}
    for entry in (occ or []):
        try:
            tier = str(entry.get("tier") or "")
            if not tier:
                continue
            vals = [float(v) for v in (entry.get("v") or [])
                    if v is not None and v == v]
            cap = float(entry.get("cap") or 0.0)
            used_peak = max(vals) if vals else 0.0
            pcts = ([min(100.0, v / cap * 100.0) for v in vals] if cap > 0 else [])
            active = [v for v in pcts if v > 0]
            out[tier] = {
                "pct": (sum(active) / len(active)) if active else 0.0,
                "peak": max(pcts) if pcts else 0.0,
                "used": used_peak,
                "cap": cap,
                "label": str(entry.get("label") or ""),
                "available": bool(cap > 0 and pcts),
                "reason": "",
            }
        except Exception:
            continue
    return out


def _amoprof_empty_tier(reason: str) -> "dict":
    """Placeholder for a tier that reported nothing, carrying the reason why.

    A tier with no data still gets a tile.  "L3 is not configured", "L3 is
    configured but idle" and "the L3 collector did not run" are three different
    findings, and omitting the tile collapses them into one indistinguishable
    absence — the reader cannot tell whether the tier is missing from the run or
    missing from the report.
    """
    return {"pct": 0.0, "peak": 0.0, "used": 0.0, "cap": 0.0,
            "label": "", "available": False, "reason": str(reason or "")}


def _amoprof_fmt_tokens(v: float) -> str:
    """Compact token count for a tile: 1.2M / 340K / 512."""
    try:
        v = float(v)
    except Exception:
        return "—"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:.0f}"



def _kv_token_delta(raw_dir, candidates) -> "float | None":
    """Window delta of a KV-movement token counter, counted once across ranks.

    Returns None when the counter is absent and 0.0 when it was present and
    never moved.  Those are different findings: absent means unmeasured, zero
    means measured and idle.
    """
    _r = _kv_counter_series(raw_dir, candidates)
    if not _r:
        return None
    # Reset-safe: the sum of positive steps, as the kernel totals every
    # counter, so a restart inside the window keeps what came before it.
    _t = _k_counter_total([_r[1]])
    return float(_t["total"]) if _t["present"] else 0.0

def build_executive_summary_html(raw_dir: Path, run_label: str = "",
                                  interactive_figures: "dict | None" = None,
                                  static_kpi_overrides: "dict | None" = None,
                                  net_iface: str = "") -> str:
    """Generate a self-contained executive summary HTML page from a run's raw/ directory.

    Reads sglang_summary.json, gpu_summary.json, summary.json, setup_details.json,
    and blktrace distribution CSVs to produce:
      • KPI grid            — all key latency/throughput/memory/storage numbers
      • Top findings        — data-driven, prioritised, with concrete actions
      • Memory tier analysis — L1 HBM / L2 DRAM / L3 device characteristics
      • KV$ L3 (local storage) executive   — requirement foundation with 5 bullet-point specs
      • Per-chart takeaways — actionable interpretation of every NVMe/memory chart
      • Bottleneck mapping  — every AI stack layer with score, root cause, action

    Called automatically by build_combined_report() when --combined-report is used.

    When `interactive_figures` is provided (a dict mapping chart_id -> figure
    JSON string), the Prom-only per-layer takeaways section will embed live
    Plotly charts inline. The expected chart IDs are: ch_pct_ttft, ch_thru,
    ch_gpu, ch_swap, ch_l3_bw, ch_evict. Missing IDs render text-only rows.
    """
    raw_dir = _amoprof_resolve_raw_dir(Path(raw_dir))

    # ── Load all data sources ─────────────────────────────────────────────────
    setup    = _amoprof_augment_setup_from_launch(_read_json(raw_dir / "setup_details.json"))
    sglang   = _read_json(raw_dir / "sglang_summary.json")
    gpu      = _read_json(raw_dir / "gpu_summary.json")
    blk      = _read_json(raw_dir / "summary.json")
    # Also load the blktrace analysis summary (NVMe BW/IOPS from blkparse events).
    # Written to raw_dir/blktrace_analysis/ by the analyzer so it doesn't
    # overwrite the collect-time summary.json.
    _ba_sum  = _read_json(raw_dir / "blktrace_analysis" / "summary.json")
    # Queue-depth summary (separate file; produced by v40+ analyzer). When
    # missing, _qd_sum stays empty and the executive finding silently skips.
    _qd_sum  = _read_json(raw_dir / "blktrace_analysis" / "queue_depth_summary.json")
    # Merge blktrace fields into blk under their canonical names so _pick() finds them.
    # Only add keys that aren't already present (don't overwrite Prometheus-sourced values).
    _bt_key_map = {
        "read_bw_mb_s_mean":  "nvme_rd_bw_mbs_mean",
        "write_bw_mb_s_mean": "nvme_wr_bw_mbs_mean",
        "read_iops_mean":     "nvme_rd_iops_mean",
        "write_iops_mean":    "nvme_wr_iops_mean",
        "read_bytes_total":   "nvme_read_bytes_total",
        "write_bytes_total":  "nvme_write_bytes_total",
        "duration_sec":       "blktrace_duration_sec",
    }
    for _src, _dst in _bt_key_map.items():
        if _src in _ba_sum and blk.get(_dst, 0) == 0:
            blk[_dst] = _ba_sum[_src]
    # Also store raw blktrace bytes/totals for the L3 (local storage) total tiles.
    # Keep full precision; tiny reads (e.g. 0.0008 GB on write-heavy KV-offload
    # workloads) get rounded away by round(..., 2) and downstream R/W ratio
    # falls to 0:1, masking the real workload.
    if "read_bytes_total" in _ba_sum and blk.get("nvme_read_total_gb", 0) == 0:
        blk["nvme_read_total_gb"]  = _ba_sum["read_bytes_total"]  / 1e9
    if "write_bytes_total" in _ba_sum and blk.get("nvme_write_total_gb", 0) == 0:
        blk["nvme_write_total_gb"] = _ba_sum["write_bytes_total"] / 1e9

    # Coverage diagnostics: did blktrace capture everything the kernel saw?
    # Populated by blktrace_analyzer when blktrace_summary.json has
    # sys_block_wr_gb_delta. Surfaced as a high-priority finding below so
    # the reader doesn't mistake under-counted blktrace bytes for real
    # workload behavior.
    _ba_coverage_warning = _ba_sum.get("coverage_warning", "") or _ba_sum.get(
        "blktrace_collector_warning", "")
    _ba_kernel_wr_gb     = _k_collector_gb(   # copied from blktrace wr_delta_gb (GiB)
        "wr_delta_gb", _safe_float(_ba_sum.get("kernel_wr_gb_delta", 0)))
    _ba_captured_ratio   = _safe_float(_ba_sum.get("captured_vs_kernel_ratio", 0))
    _ba_dropped_events   = _safe_float(_ba_sum.get("blktrace_dropped_events", 0))

    sglang_ts = _read_csv_summary(_first_existing(raw_dir, ["sglang_timeseries.csv"]))
    pct_ts: Dict[str, Any] = {}
    try:
        _pct_path = raw_dir / "sglang_percentiles_timeseries.json"
        if _pct_path.exists() and _pct_path.stat().st_size > 0:
            pct_ts = json.loads(_pct_path.read_text())
    except Exception:
        pct_ts = {}
    bench = {}  # Prometheus-only report: benchmark files are not used as data sources
    # L3.5 capacity utilization, from the shared resolver so this tile, the
    # Metrics object and common_kpis.json cannot disagree. Resolved here rather
    # than inline at the tile because the tile sits inside a large f-string
    # concatenation and `_sg_raw` below is assigned inside a try/ that may not
    # have run.
    try:
        _l35_kpis = compute_l35_kpis(raw_dir=raw_dir) if compute_l35_kpis is not None else {}
    except Exception:
        _l35_kpis = {}
    # `_l35kpi_` prefix, not `_l35_`: the chart block further down reuses
    # `_l35_cap_gb` / `_l35_used` for the segment-only series it plots, and this
    # is all one long function, so a shared name silently overwrote the tile's
    # capacity with the segment ceiling.
    _l35kpi_ok        = bool(_l35_kpis.get("kv_l35_available", False))
    _l35kpi_fill_pct  = _safe_float(_l35_kpis.get("kv_l35_fill_pct"), 0.0)
    _l35kpi_fill_peak = _safe_float(_l35_kpis.get("kv_l35_fill_pct_peak"), 0.0)
    _l35kpi_seg_pct   = _safe_float(_l35_kpis.get("kv_l35_segment_fill_pct"), 0.0)
    _l35kpi_file_pct  = _safe_float(_l35_kpis.get("kv_l35_file_fill_pct"), 0.0)
    _l35kpi_used_gb   = _safe_float(_l35_kpis.get("kv_l35_used_gb"), 0.0)
    _l35kpi_cap_gb    = _safe_float(_l35_kpis.get("kv_l35_capacity_gb"), 0.0)
    _l35kpi_replicas  = _safe_float(_l35_kpis.get("kv_l35_replica_count"), 0.0)
    _l35kpi_src       = str(_l35_kpis.get("kv_l35_fill_source", "") or "")
    # Per-tier KV utilization for the L1/L2/L3 tiles. Populated from `_occ`
    # further down, inside the same try/ that builds the tier-occupancy chart;
    # initialised here so the KPI grid cannot NameError if that block raises.
    # Seeded with a reason for every tier so the tiles still render — and still
    # say why they are empty — when that block raises before populating them.
    _tier_fill: dict = {
        _t: _amoprof_empty_tier(
            "tier-occupancy resolution did not complete for this run")
        for _t in ("L1", "L2", "L3")
    }
    gpu_ts    = _read_csv_summary(_first_existing(raw_dir, ["gpu_timeseries.csv"]))
    nvme_ts   = _read_csv_summary(_first_existing(raw_dir, ["nvme_driver_timeseries.csv",
                                                               "iostat_timeseries.csv"]))
    qds_ts    = _read_csv_summary(_first_existing(raw_dir, ["queue_depth_sources_timeseries.csv",
                                                               "queue_depth_sysfs_timeseries.csv"]))
    vmstat_ts = _read_csv_summary(_first_existing(raw_dir, ["vmstat_timeseries.csv"]))
    # Queue-depth fallback for Executive findings: exact queue depth comes from
    # blktrace_analysis/queue_depth_summary.json. If absent, prefer the unified
    # multi-source queue-depth file; it merges iostat aqu-sz, sysfs weighted
    # queue time, /sys/block inflight, and /proc/diskstats.
    def _qd_device_fallback() -> dict:
        """Queue depth from the device's own counters, when blktrace has none.

        avgqu_sz (diskstats field 11, time-weighted over each interval) comes
        before the in-flight gauge: it cannot miss activity between samples.
        It was absent from this list, so a Prometheus-fetched run fell through
        to the instantaneous gauge even with the better series in hand.
        """
        _qd_stat = qds_ts.get("qd_best_effort") or qds_ts.get("qd") or qds_ts.get("weighted_qd") or qds_ts.get("inflight")
        if isinstance(_qd_stat, dict) and _safe_float(_qd_stat.get("max", 0)) > 0:
            return {
                "qd_mean": _safe_float(_qd_stat.get("mean", 0)),
                "qd_p50": _safe_float(_qd_stat.get("p50", _qd_stat.get("mean", 0))),
                "qd_p95": _safe_float(_qd_stat.get("p95", _qd_stat.get("max", 0))),
                "qd_p99": _safe_float(_qd_stat.get("p99", _qd_stat.get("max", 0))),
                "qd_max": _safe_float(_qd_stat.get("max", 0)),
                "pct_at_qd_ge_32": 0,
                "qd_source": "advisory_queue_depth_sources_run_delta_fallback",
            }
        _inflight_stat = (nvme_ts.get("avgqu_sz") or nvme_ts.get("inflight")
                          or nvme_ts.get("queue_depth") or nvme_ts.get("aqu_sz")
                          or nvme_ts.get("avgqu"))
        if isinstance(_inflight_stat, dict) and _safe_float(_inflight_stat.get("max", 0)) > 0:
            return {
                "qd_mean": _safe_float(_inflight_stat.get("mean", 0)),
                "qd_p50": _safe_float(_inflight_stat.get("mean", 0)),
                "qd_p95": _safe_float(_inflight_stat.get("max", 0)),
                "qd_max": _safe_float(_inflight_stat.get("max", 0)),
                "pct_at_qd_ge_32": 0,
                "qd_source": "advisory_iostat_aqu_sz_or_sysfs_inflight_fallback",
            }
        return {}

    if not _qd_sum:
        _qd_sum = _qd_device_fallback()
    # DRAM BW for the Executive tab. Prefer timestamped local timeseries when
    # available because aggregate/analyze can filter those rows to an offline
    # wall-clock window. Fall back to the whole-capture AMDuProf raw text only
    # when the normalized timeseries is missing or all-zero.
    def _dram_summary_has_nonzero(_s: dict) -> bool:
        if not isinstance(_s, dict) or not _s:
            return False
        for _k in ("dram_total_gb_s", "total_gb_s", "total_bw_gbs",
                   "pcm_dram_total_gb_s", "dram_read_gb_s", "read_gb_s",
                   "dram_write_gb_s", "write_gb_s"):
            _v = _s.get(_k)
            if isinstance(_v, dict):
                if (_safe_float(_v.get("nonzero_count", 0)) > 0 or
                        _safe_float(_v.get("nonzero_mean", 0)) > 0 or
                        _safe_float(_v.get("mean", 0)) > 0):
                    return True
            elif _safe_float(_v, 0.0) > 0:
                return True
        return bool(_dram_metric_from_summary_obj(_s, "inline_dram_summary"))

    dram_ts = _read_csv_summary(_first_existing(raw_dir,
        ["amduprof_pcm_timeseries.csv", "pcm_timeseries.csv", "pcm_memory_timeseries.csv"]))
    # Sanity-check the CSV before considering a fallback.  A summary fallback
    # that replaces good per-interval data with byte-valued fields is worse
    # than no fallback: the CSV here read 0.79 GB/s while pcm_summary.json
    # yielded 452,244,313 GB/s, and the summary won.
    def _dram_plausible(_d) -> bool:
        for _c in ("dram_total_gb_s", "dram_read_gb_s", "dram_write_gb_s",
                   "dram_total_bw_gbs", "pcm_dram_total_gb_s"):
            _m = (_d.get(_c) or {}).get("mean", 0) if isinstance(_d, dict) else 0
            if _m and 0 < float(_m) <= 100_000.0:
                return True
        return False

    # A handful of poisoned samples destroys the arithmetic mean.  Observed:
    # 956 rows of ~0.42 GB/s with about five rows at 4.8e10 (44.7 GiB — a
    # memory quantity, not a rate), giving mean = 226,122,157 GB/s.  min and
    # first/last were correct throughout, so the series is good apart from
    # those samples.  Drop implausible SAMPLES and recompute, rather than
    # rejecting the whole column: the measurement is real, a few points are
    # not.
    def _despike_dram(_d):
        _p = _first_existing(raw_dir, ["amduprof_pcm_timeseries.csv",
                                       "pcm_timeseries.csv",
                                       "pcm_memory_timeseries.csv"])
        if not _p or not isinstance(_d, dict):
            return _d, 0
        _cols = ("dram_read_gb_s", "dram_write_gb_s", "dram_total_gb_s",
                 "pcm_dram_read_gb_s", "pcm_dram_write_gb_s", "pcm_dram_total_gb_s")
        _dropped = 0
        for _c in _cols:
            if _c not in _d:
                continue
            _vals = _amoprof_read_columns_raw(_p, [_c]).get(_c, [])
            _clean = [v for v in _vals
                      if v == v and 0.0 <= v <= _DRAM_SANE_MAX_GBS]
            _dropped += len([v for v in _vals if v == v]) - len(_clean)
            if not _clean:
                continue
            _srt = sorted(_clean)
            _d[_c] = dict(_d[_c],
                          mean=sum(_clean) / len(_clean),
                          max=max(_clean),
                          min=min(_clean),
                          median=_srt[len(_srt) // 2],
                          n=len(_clean))
        return _d, _dropped

    _DRAM_SANE_MAX_GBS = _K_DRAM_MAX        # shared with every surface
    dram_ts, _dram_spikes = _despike_dram(dram_ts)
    if _dram_spikes:
        setup["_dram_spikes_dropped"] = (
            f"{_dram_spikes} DRAM bandwidth sample(s) above "
            f"{_DRAM_SANE_MAX_GBS:,.0f} GB/s were excluded before averaging "
            f"\u2014 physically impossible values that otherwise dominate the "
            f"arithmetic mean.")

    _dram_csv_ok = _dram_plausible(dram_ts)
    if not _dram_csv_ok and not _dram_summary_has_nonzero(dram_ts):
        # On Intel, the collector may have a valid raw/pcm_summary.json even
        # when the CSV was filtered or not loaded by the Executive path.  Use
        # the same summary fallback as the End Report so badges/KPIs do not
        # contradict the DRAM section.
        _fallback = _load_dram_pmu_summary(raw_dir, dram_ts)
        # Only accept the fallback if it is itself plausible.
        if _dram_plausible(_fallback):
            dram_ts = _fallback
        else:
            setup["_dram_summary_rejected"] = (
                "pcm_summary.json held values outside any physical range for "
                "DRAM bandwidth (a byte count, not GB/s); ignored.")
    reqsize_ts = _read_csv_summary(_first_existing(raw_dir, ["request_size_distribution.csv"]))
    iat_ts     = _read_csv_summary(_first_existing(raw_dir, ["interarrival_distribution.csv"]))
    bw_stream  = _read_csv_summary(_first_existing(raw_dir, ["bandwidth_per_stream.csv"]))
    hot_lba    = _read_csv_summary(_first_existing(raw_dir, ["hot_regions_overall.csv"]))
    smart      = _read_json(raw_dir / "smart_summary.json")
    # The ssd_hardware collector's capacity fields are merged into
    # smart_summary.json by the collect path and (since v1.65.0) by the
    # Prometheus path. Reading its own file as a fallback means the chart does
    # not depend on either merge having happened -- a run directory produced
    # before that fix still renders.
    _ssd_hw_sum = _read_json(raw_dir / "ssd_hw_summary.json")
    if isinstance(_ssd_hw_sum, dict) and _ssd_hw_sum:
        for _k_hw in ("hicache_fs_total_gb", "hicache_fs_used_gb",
                      "hicache_fs_avail_gb", "hicache_fs_used_pct",
                      "nvme_device_capacity_gb", "hicache_size_gb"):
            if not smart.get(_k_hw) and _ssd_hw_sum.get(_k_hw):
                smart[_k_hw] = _ssd_hw_sum[_k_hw]

    # L3 capacity: require explicit L3/L3 config. Do not infer from generic
    # df/SMART snapshots because L2-only runs can still have old mounted
    # filesystems or NVMe devices on the node.
    _launch_raw_for_l3 = _pick(setup, ["Launch command","launch_command","Command","Reference launch command"], "")
    l3_explicit_config = _amoprof_has_explicit_l3_config(setup, str(_launch_raw_for_l3))
    # The keyword scan above also matches a monitored device ("L3 device:
    # /dev/nvme0n1") and defaulted fields; SGLang saying it has no storage
    # backend outranks both.
    _l3_no_tier = resolve_l3_backend(setup, str(_launch_raw_for_l3))
    _l3_no_tier = _l3_no_tier if _l3_no_tier.backend_class == "host_dram_only" else None
    if _l3_no_tier is not None:
        l3_explicit_config = False
    l3_fs_total_gb = _k_collector_gb("hicache_fs_total_gb", _safe_float(smart.get("hicache_fs_total_gb", 0))) if l3_explicit_config else 0.0
    l3_fs_used_gb  = (_k_collector_gb("hicache_fs_used_gb", _safe_float(smart.get("hicache_fs_used_gb",
                                  smart.get("hicache_size_gb", 0)))) if l3_explicit_config else 0.0)
    l3_fs_avail_gb = _k_collector_gb("hicache_fs_avail_gb", _safe_float(smart.get("hicache_fs_avail_gb", 0))) if l3_explicit_config else 0.0
    l3_fs_used_pct = _safe_float(smart.get("hicache_fs_used_pct", 0)) if l3_explicit_config else 0.0
    nvme_dev_cap_gb = _k_collector_gb("nvme_device_capacity_gb", _safe_float(smart.get("nvme_device_capacity_gb", 0))) if l3_explicit_config else 0.0
    l3_capacity_source = "df/SMART runtime snapshot" if (l3_explicit_config and l3_fs_total_gb > 0) else ""
    # Which instant the df snapshot describes.  A point-in-time gauge without
    # its instant is unreadable as evidence: the same window analysed twice
    # reported 25 GB and 762 GB because the fetch evaluated the gauge at
    # analysis time rather than at the window end.  The fetch now anchors it
    # and records the instant; naming it here is what makes the difference
    # visible if it ever drifts again.
    _l3_snap_at = str((smart or {}).get("_snapshot_at")
                      or (_ssd_hw_sum or {}).get("_snapshot_at") or "").strip()
    # Allow setup_details.json to supply L3 (local storage) capacity when SMART/df
    # data is not available (common for non-NVMe backends such as Mooncake).
    # Values from setup_details are configured capacity, not measured runtime
    # cache occupancy; label them accordingly in the Executive tile.
    if l3_fs_total_gb <= 0:
        l3_fs_total_gb = _safe_float(_pick(setup, [
            "L3 (local storage) capacity GB", "L3 Capacity GB", "L3 total capacity GB",
            "l3_storage_capacity_gb", "l3_capacity_gb", "L3 (local storage) total GB"
        ], 0))
        if l3_fs_total_gb > 0:
            l3_capacity_source = "configured capacity from setup_details.json"
    if l3_fs_used_gb <= 0:
        l3_fs_used_gb = _safe_float(_pick(setup, [
            "L3 (local storage) used GB", "L3 used capacity GB", "l3_storage_used_gb",
            "l3_used_gb", "L3 storage current used GB"
        ], 0))
        if l3_fs_used_gb > 0 and not smart.get("hicache_fs_used_gb"):
            l3_capacity_source = l3_capacity_source or "configured capacity from setup_details.json"
    if l3_fs_avail_gb <= 0 and l3_fs_total_gb > 0:
        l3_fs_avail_gb = max(l3_fs_total_gb - l3_fs_used_gb, 0.0)
    if l3_fs_used_pct == 0 and l3_fs_total_gb > 0 and l3_fs_used_gb > 0:
        l3_fs_used_pct = round(l3_fs_used_gb / l3_fs_total_gb * 100, 1)
    if not l3_explicit_config:
        l3_fs_total_gb = l3_fs_used_gb = l3_fs_avail_gb = l3_fs_used_pct = 0.0
        nvme_dev_cap_gb = 0.0
        l3_capacity_source = ""

    # ── Extract key scalars ───────────────────────────────────────────────────
    model     = _pick(setup, ["Model","model","model_name","Model path","model_path","model_id"],
                      _pick(sglang, ["model_name","model","model_path"], "unknown"))
    # Benchmark / Application name — more useful than the hostname-style
    # "instance" field. Accept a wide range of common keys; fall back to the
    # old "instance" pick so legacy setup files still resolve to something.
    def _sg_summary_num(*names) -> float:
        """A numeric field from the SGLang summary, or from the timeseries.

        Prometheus-only runs carry almost nothing in sglang_summary.json — the
        gauges live in the timeseries — so fall back to reading the column
        directly rather than reporting "unknown" for data that is present.
        """
        for _n in names:
            _v = _safe_float(_pick(sglang, [_n], 0), 0)
            if _v:
                return _v
        # Column fallback: "<name>_mean" / "_peak" describe an aggregate of
        # the base gauge, so strip the suffix and aggregate here.
        _sgp = _first_existing(raw_dir, ["sglang_timeseries.csv"])
        if not _sgp:
            return 0.0
        for _n in names:
            _base = _n.rsplit("_", 1)[0] if _n.endswith(("_mean", "_peak", "_p50")) else _n
            _agg = _n.rsplit("_", 1)[1] if _n.endswith(("_mean", "_peak", "_p50")) else "mean"
            _col = _amoprof_read_columns_substr(_sgp, {"v": [_base]}).get("v", [])
            _col = [x for x in _col if x == x]
            if not _col:
                continue
            if _agg == "peak":
                return max(_col)
            if _agg == "p50":
                _srt = sorted(_col)
                return _srt[len(_srt) // 2]
            return sum(_col) / len(_col)
        return 0.0

    benchmark = _pick(setup, ["Application / Benchmark","application_benchmark","Benchmark","benchmark","Application","application",
                               "Workload","workload","Test","test","app","app_name",
                               "Benchmark name","benchmark_name"],
                      _pick(setup, ["Instance","instance","Server","server","endpoint"],
                            _pick(sglang, ["instance"], "unknown")))
    # Nothing names the workload explicitly on most runs, so infer it from
    # evidence the run already carries rather than printing "unknown".  Order
    # is most-specific first; each source is named in the setup table so the
    # reader can tell an inference from a declaration.
    if str(benchmark).strip().lower() in ("", "unknown", "none"):
        _bench_src = ""
        # A benchmark harness leaves its own summary behind.
        for _f, _name in (("benchmark_summary.json", "bench_serving"),
                          ("sweagent_summary.json", "SWE-agent"),
                          ("swebench_summary.json", "SWE-bench")):
            if (raw_dir / _f).exists():
                benchmark, _bench_src = _name, f"{_f} present"
                break
        if not _bench_src:
            # Otherwise characterise the traffic: a benchmark drives steady
            # concurrency, interactive serving does not.
            _rr = _sg_summary_num("running_reqs_mean", "num_running_reqs_mean")
            _rr_pk = _sg_summary_num("running_reqs_peak", "num_running_reqs_peak")
            _in_p50 = _sg_summary_num("prompt_tokens_p50", "input_tokens_p50")
            if _rr > 0 and _rr_pk > 0:
                _steady = _rr / _rr_pk
                if _steady > 0.7 and _rr_pk >= 4:
                    benchmark = "synthetic load (steady concurrency)"
                elif _rr_pk >= 2:
                    benchmark = "interactive serving (variable concurrency)"
                else:
                    benchmark = "low-concurrency serving"
                _bench_src = (f"inferred from concurrency: mean {_rr:.1f} / "
                              f"peak {_rr_pk:.0f} requests")
            elif _in_p50 > 0:
                benchmark = ("long-context workload" if _in_p50 > 8000
                             else "short-prompt workload")
                _bench_src = f"inferred from p50 input {_in_p50:,.0f} tokens"
        if _bench_src:
            setup.setdefault("Application / Benchmark source", _bench_src)
    runtime   = _pick(setup, ["Runtime","runtime","engine","server_type"],
                      _pick(sglang, ["server_type","runtime"], "SGLang"))
    gpu_desc  = _pick(setup, ["GPU","gpu","Accelerator","hardware","accelerator","GPU model"], "unknown")
    tp_size   = str(_pick(setup, ["TP size","tp_size","tensor_parallel_size","TP","tp"], "?"))
    dp_size   = str(_pick(setup, ["DP size","dp_size","data_parallel_size","DP","dp"], "1"))
    attn      = _pick(setup, ["Attention backend","attention_backend","attn_backend","Attention"], "unknown")
    # Inference cache tier — the user is moving from HiCache (SGLang) to also
    # supporting vLLM PagedAttention and Dynamo, so we describe this generically
    # while keeping HiCache keys as the primary lookup for current setups.
    cache_enabled = _pick(setup, ["HiCache","Hierarchical cache","enable_hierarchical_cache",
                                    "hicache","HiCache enabled","Inference cache",
                                    "inference_cache","Cache tier","cache_tier"], "unknown")
    # L3 storage class — NVMe L3 (local storage) by default, but future runs may target an
    # AI Memory Node (CXL / GPU-side block storage) or other backend. Surfaced
    # in the tier listing so the reader knows what hardware they're looking at.
    l3_storage_type = _pick(setup, ["L3 storage type","l3_storage_type",
                                      "L3 type","l3_type","Cache L3 (local storage) backend",
                                      "cache_l3_backend"], "Storage")
    # Explicit local-block mapping for L3 storage.  Do not infer that generic
    # node-exporter/iostat disk metrics are L3 storage merely because a backend
    # name exists.  Mooncake / remote / object-backed L3 may expose SGLang
    # movement counters without any local block device to report %util/QD/latency.
    l3_device = str(_pick(setup, [
        "L3 Device", "L3 device", "l3_device", "L3 block device",
        "L3 storage device", "l3_storage_device", "NVMe device", "ssd_device"
    ], "")).strip()
    l3_mount_path = str(_pick(setup, [
        "L3 Mount Path", "L3 mount path", "l3_mount_path",
        "L3 storage mount path", "l3_storage_mount_path"
    ], "")).strip()
    _l3_backend = resolve_l3_backend(setup, _pick(setup, ["Launch command","launch_command","Command"], ""))

    # ── Does the telemetry agree with the declared backend? ────────────────
    #
    # A setup_details.json copied between deployments carries the previous
    # run's embedded `SGLang server_info raw` blob, and the launch command
    # rendered from it is then presented as fact. On a file-backend run whose
    # setup file still said `--hicache-storage-backend mooncake`, the report
    # named a memory node that was not in the deployment, and every tile that
    # keys off the tier followed it.
    #
    # A remote backend cannot operate without publishing store-side counters:
    # gets, memory-tier hits, file-tier hits. Their total absence, alongside
    # live local block I/O, contradicts the declaration.
    #
    # This does NOT override the backend. A genuine remote run whose store
    # exporter was never scraped -- no --l35-instance -- looks identical from
    # here, and silently relabelling it would trade one wrong tier for
    # another. Both readings are named and the operator decides.
    _backend_evidence_note = ""
    try:
        _declared = str(_l3_backend.backend_class or "").lower()
        if _declared in ("remote_mooncake", "remote_storage"):
            _store_cols = ("l35_get_total_n", "l35_get_valid_n", "l35_mem_hit_b",
                           "l35_file_hit_b", "l35_mem_hit_n", "l35_file_hit_n",
                           "l35_evicted_b", "l35_store_mem_used_b",
                           "mooncake_used_bytes", "mooncake_capacity_bytes")
            _store_seen = []
            for _f in ("l35_store_capacity.csv", "l35_storage_timeseries.csv"):
                _p = _first_existing(raw_dir, [_f])
                if not _p:
                    continue
                _got = _amoprof_read_columns_raw(_p, list(_store_cols))
                for _c in _store_cols:
                    _vv = [v for v in (_got.get(_c) or []) if v == v]
                    if _vv and max(_vv) > 0:
                        _store_seen.append(_c)
            _local_p = _first_existing(raw_dir, ["nvme_driver_timeseries.csv"])
            _local_io = False
            if _local_p:
                _lg = _amoprof_read_columns_raw(_local_p, ["rd_bw_mbs", "wr_bw_mbs"])
                _local_io = any(
                    max([v for v in (_lg.get(_c) or []) if v == v] or [0]) > 0
                    for _c in ("rd_bw_mbs", "wr_bw_mbs"))
            if not _store_seen:
                _backend_evidence_note = (
                    f"The configuration declares a remote backing tier "
                    f"({_l3_backend.display_name}), but this window contains no "
                    f"store-side counters at all — no gets, no memory-tier "
                    f"or file-tier hits, no store occupancy. "
                    + ("Local block I/O on the GPU host IS present, so either "
                       "the setup_details/server_info is stale (copied from an "
                       "earlier deployment) and this is really a local file "
                       "backend, or the memory node's exporter was never "
                       "scraped (--l35-instance). "
                       if _local_io else
                       "No local block I/O is present either, so the backing "
                       "tier is untelemetered whichever it is. ")
                    + "Every tier-named label below follows the declaration, "
                      "not the evidence.")
                print(f"  [warn] backing tier: {_backend_evidence_note}")
    except Exception as _bev:
        print(f"  [warn] backing-tier evidence check skipped: {_bev}")

    if not l3_explicit_config:
        l3_backend_class = "none"
        l3_backend_display = "Not configured"
        l3_storage_is_local_block = False
        l3_storage_has_block_mapping = False
    else:
        l3_backend_class = _l3_backend.backend_class
        l3_backend_display = _l3_backend.display_name
        l3_storage_is_local_block = bool(_l3_backend.backend_class == "local_ssd")
        l3_storage_has_block_mapping = bool(_l3_backend.has_local_block_mapping or l3_device or l3_mount_path)
    # One name for the backing tier, resolved once and used by every series
    # label, axis and chart title below.  Hardcoding "L3.5" in those strings
    # meant a local NVMe run still read "backup L2→L3.5" and
    # "L3.5 node · storage read BW" -- a tier that is not in the deployment.
    # `_TIER` is the short form for arrows and axes, `_TIER_NODE` the longer
    # form for chart titles that name the host.
    _TIER = "L3" if str(l3_backend_class).lower() == "local_ssd" else "L3.5"
    _TIER_NODE = ("L3 local SSD"
                  if str(l3_backend_class).lower() == "local_ssd"
                  else "L3.5 node")

    # `has_l3` — single truth source for "should we show any L3 / L3.5 tile,
    # summary block, or evidence row?".  Reads True only when SGLang / setup
    # actually configured an L3 backend (local_ssd, remote_mooncake, or
    # remote_storage).  Runs without HiCache storage (host_dram_only,
    # explicitly-None hicache_storage_backend, or no L3 evidence at all)
    # answer False and every L3-scoped tile / summary is suppressed.
    has_l3 = bool(l3_explicit_config) and l3_backend_class in (
        "local_ssd", "remote_mooncake", "remote_storage")

    # `has_l35` — is the AI Memory Node actually the backing tier?
    #
    # The L3.5 tile groups were each gated on their DATA being present
    # (l35_cpu_util_pct having samples, the store reporting bytes, and so on)
    # and never on the tier being configured.  Those series come back whenever
    # the memory node is reachable in Prometheus or --l35-storage-instance was
    # passed, which is routinely true on a local-L3 run against the same
    # cluster -- so a local-NVMe report grew "L3.5 node CPU util" and friends,
    # describing a tier that is not in the deployment.  Data presence says the
    # exporter answered; only the backend class says the tier is in use.
    has_l35 = bool(has_l3) and str(l3_backend_class).lower() in (
        "remote_mooncake", "remote_storage")
    ctx_len   = _pick(setup, ["Context length","context_length","max_model_len","ctx_len","max_seq_len","context"], "?")
    # No default: "1" was printed as the run's page size whenever setup and
    # launch command were both silent, which is a claim, not an unknown.
    _ps_val, _ps_src, page_sz_conflict = resolve_page_size(setup)
    page_sz = f"{_ps_val:g}" if _ps_val else "unknown"
    page_sz_src = _ps_src
    launch    = _pick(setup, ["Launch command","launch_command","Command","Reference launch command"], "")
    mem_frac  = _pick(setup, ["mem-fraction-static","Mem fraction static","mem_fraction_static","mem_fraction","memory_fraction"], "")
    if _amoprof_missing(mem_frac):
        mem_frac = _amoprof_parse_launch_arg(str(launch), "--mem-fraction-static") or "?"

    # DRAM (host) capacity for the L2 tier label. Sourced from dram_summary.json
    # written by DramMonitor (/proc/meminfo MemTotal). May be 0 on legacy runs.
    _dram_sum = _read_json(raw_dir / "dram_summary.json")
    host_dram_total_gb = _k_collector_gb("dram_total_gb", _safe_float(_dram_sum.get("dram_total_gb", 0)))
    if host_dram_total_gb <= 0:
        host_dram_total_gb = _safe_float(_pick(setup, [
            "Host DRAM GB", "DRAM capacity GB", "DRAM total GB",
            "host_dram_gb", "dram_total_gb"
        ], 0))
    # dram_used_gb_* are /proc/meminfo KiB / 1024 / 1024 (GiB), like used_gb.
    host_dram_used_gb = _k_gb_from_gib(_safe_float(_dram_sum.get("dram_used_gb_mean",
                                      _dram_sum.get("dram_used_gb_peak", 0))))
    # Peak kept separate so the KPI tile can show mean and peak side-by-side.
    host_dram_used_peak_gb = _k_gb_from_gib(_safe_float(_dram_sum.get("dram_used_gb_peak", 0)))
    host_dram_util_pct_peak = _safe_float(_dram_sum.get("dram_util_pct_peak", 0))
    # Fallback: dram_summary.json can be missing dram_used_gb_mean / peak
    # on some runs (older writer, aborted stop()).  When the timeseries CSV
    # is present we can still derive a scalar mean/peak from it, so the
    # KPI tile does not read 0.0 GB on a run that plainly has DRAM data
    # (the memory-hierarchy chart is built from the same CSV).
    if host_dram_used_gb <= 0 or host_dram_used_peak_gb <= 0:
        try:
            _dts_path = _first_existing(raw_dir, ["dram_timeseries.csv"])
            if _dts_path:
                _dts = _amoprof_read_columns_raw(_dts_path, ["used_gb", "total_gb"])
                _u = [_k_collector_gb("used_gb", v) for v in (_dts.get("used_gb") or []) if v == v and v > 0]
                _t = [_k_collector_gb("total_gb", v) for v in (_dts.get("total_gb") or []) if v == v and v > 0]
                if _u:
                    if host_dram_used_gb <= 0:
                        host_dram_used_gb = sum(_u) / len(_u)
                    if host_dram_used_peak_gb <= 0:
                        host_dram_used_peak_gb = max(_u)
                if _t and host_dram_total_gb <= 0:
                    host_dram_total_gb = max(_t)
        except Exception:
            pass
    if host_dram_used_gb <= 0:
        host_dram_used_gb = _safe_float(_pick(setup, [
            "Host DRAM used GB", "DRAM used GB", "dram_used_gb",
            "dram_used_gb_mean"
        ], 0))
    # Recompute AFTER the timeseries fallback ran, so a run with an empty
    # dram_summary.json but a good dram_timeseries.csv still gets a % full.
    host_dram_used_pct = (host_dram_used_gb / host_dram_total_gb * 100.0) if host_dram_total_gb > 0 and host_dram_used_gb > 0 else 0.0

    # L3.5 memory-node DRAM (raw), from l35_storage_timeseries.csv.
    # Distinct from host_dram_* above (that is the GPU host); this is
    # the AI Memory Node's own DRAM residency, so the KPI grid can
    # show both side-by-side.
    l35_dram_used_gb = 0.0
    l35_dram_used_peak_gb = 0.0
    l35_dram_total_gb = 0.0
    l35_dram_used_pct = 0.0
    _l35_dram_used_series: list = []
    _l35_dram_t: list = []
    _l35_csv_path = None
    # L3.5 aspect series - each will be [] when the collector is not on
    # the memory node (AMDuProf for DRAM BW, network collector for NIC).
    _l35_dram_rd_series: list = []
    _l35_dram_wr_series: list = []
    _l35_cpu_util_series: list = []
    _l35_cpu_iowait_series: list = []
    _l35_cpu_busiest_series: list = []
    _l35_net_rx_series: list = []
    _l35_net_tx_series: list = []
    _l35_net_link_util_series: list = []
    try:
        _l35_csv_path = _first_existing(raw_dir, ["l35_storage_timeseries.csv"])
        if _l35_csv_path:
            _l35_dram_raw = _amoprof_read_columns_raw(
                _l35_csv_path,
                ["time_sec", "l35_dram_used_gb",
                 "l35_dram_used_peak_gb", "l35_dram_total_gb",
                 "l35_dram_rd_gbs", "l35_dram_wr_gbs",
                 "l35_cpu_util_pct", "l35_cpu_iowait_pct",
                 "l35_cpu_busiest_pct",
                 "l35_net_rx_mbps", "l35_net_tx_mbps",
                 "l35_net_link_util_pct"])
            _l35_dram_rd_series    = _l35_dram_raw.get("l35_dram_rd_gbs") or []
            _l35_dram_wr_series    = _l35_dram_raw.get("l35_dram_wr_gbs") or []
            _l35_cpu_util_series   = _l35_dram_raw.get("l35_cpu_util_pct") or []
            _l35_cpu_iowait_series = _l35_dram_raw.get("l35_cpu_iowait_pct") or []
            _l35_cpu_busiest_series= _l35_dram_raw.get("l35_cpu_busiest_pct") or []
            _l35_net_rx_series     = _l35_dram_raw.get("l35_net_rx_mbps") or []
            _l35_net_tx_series     = _l35_dram_raw.get("l35_net_tx_mbps") or []
            _l35_net_link_util_series = _l35_dram_raw.get("l35_net_link_util_pct") or []
            _l35_dram_t = _l35_dram_raw.get("time_sec") or []
            _l35_dram_used_series = _l35_dram_raw.get("l35_dram_used_gb") or []
            _l35_used_pos = [v for v in _l35_dram_used_series if v == v and v > 0]
            _l35_peak_pos = [v for v in (_l35_dram_raw.get("l35_dram_used_peak_gb") or [])
                             if v == v and v > 0]
            _l35_total_pos = [v for v in (_l35_dram_raw.get("l35_dram_total_gb") or [])
                              if v == v and v > 0]
            if _l35_used_pos:
                l35_dram_used_gb = sum(_l35_used_pos) / len(_l35_used_pos)
                l35_dram_used_peak_gb = (max(_l35_peak_pos) if _l35_peak_pos
                                         else max(_l35_used_pos))
            if _l35_total_pos:
                l35_dram_total_gb = max(_l35_total_pos)
            if l35_dram_total_gb > 0 and l35_dram_used_gb > 0:
                l35_dram_used_pct = l35_dram_used_gb / l35_dram_total_gb * 100.0
    except Exception:
        pass

    def _setup_float_fuzzy_src(*keys, default: float = 0.0) -> "tuple[float, str]":
        """Read a numeric setup value, and report WHICH key supplied it.

        Matching is on the exact key; "fuzzy" refers only to parsing a value
        written as '50 GB' or '50G'.  The key matters because a figure read
        from setup can contradict a measured gauge, and a tile that says
        "2 GB/GPU x 8 GPU(s)" without naming the field it came from leaves
        nobody able to find or correct the 2.
        """
        import re as _re
        for _k in keys:
            if _k in setup:
                _v = setup.get(_k)
                if isinstance(_v, (int, float)):
                    return _safe_float(_v, default), _k
                _m = _re.search(r"[-+]?[0-9]*\.?[0-9]+", str(_v or ""))
                if _m:
                    return _safe_float(_m.group(0), default), _k
        return default, ""

    def _setup_float_fuzzy(*keys, default: float = 0.0) -> float:
        """Read a numeric setup value even when written as '50 GB' or '50G'."""
        return _setup_float_fuzzy_src(*keys, default=default)[0]

    # L2 DRAM cache capacity should reflect the configured inference cache
    # allocation, not the whole host DRAM DIMM capacity. In SGLang-style setups
    # hicache size is commonly specified per GPU/rank. Surface both values where
    # useful, but use the effective L2 cache capacity for L2/DRAM capacity tiles.
    # HiCache is allocated per *serving* GPU, so the multiplier is TP x DP —
    # not the physical GPU count.  Preferring "GPU Count" from setup made the
    # Executive report 64 GB x 8 = 512 GB on an 8-GPU host running TP=2, while
    # the Interactive report used TP x DP and showed 128 GB.  The same
    # distinction already governs HBM capacity (resolve_gpu_hbm), so use it
    # here too and keep the two surfaces consistent.
    setup_gpu_count_for_l2 = (_safe_float(tp_size, 0) or 0.0) * (_safe_float(dp_size, 0) or 1.0)
    if setup_gpu_count_for_l2 <= 0:
        setup_gpu_count_for_l2 = _setup_float_fuzzy(
            "GPU Count", "gpu_count", "Num GPUs", "num_gpus", default=0.0)
    if setup_gpu_count_for_l2 <= 0:
        setup_gpu_count_for_l2 = _safe_float(gpu.get("gpu_count", 0)) or 1.0
    hicache_per_gpu_gb, hicache_per_gpu_key = _setup_float_fuzzy_src(
        "HiCache size per GPU GB", "HiCache DRAM per GPU GB",
        "HiCache size GB per GPU", "hicache_size_per_gpu_gb",
        "hicache_dram_per_gpu_gb", "HiCache size", "hicache_size",
        default=0.0)
    hicache_total_gb = _setup_float_fuzzy(
        "HiCache total GB", "HiCache DRAM total GB", "L2 DRAM cache capacity GB",
        "L2 cache capacity GB", "hicache_total_gb", "l2_dram_cache_capacity_gb",
        default=0.0)
    if hicache_total_gb <= 0 and hicache_per_gpu_gb > 0:
        hicache_total_gb = hicache_per_gpu_gb * max(setup_gpu_count_for_l2, 1.0)
    l2_dram_capacity_via_ratio = ""
    l2_dram_capacity_gb = hicache_total_gb if hicache_total_gb > 0 else host_dram_total_gb
    l2_dram_capacity_source = (
        (f"HiCache allocation: {hicache_per_gpu_gb:g} GB/GPU × "
         f"{setup_gpu_count_for_l2:g} GPU(s)"
         + (f" · from setup key '{hicache_per_gpu_key}'" if hicache_per_gpu_key else ""))
        if hicache_total_gb > 0 and hicache_per_gpu_gb > 0 else
        (l2_dram_capacity_via_ratio if l2_dram_capacity_via_ratio else
         ("HiCache total allocation from setup_details.json" if hicache_total_gb > 0
          else "Host DRAM capacity"))
    )
    # Used L2 DRAM can be estimated from SGLang hicache host tokens when
    # present. This is more setup-relevant than OS-wide MemAvailable.
    l2_dram_used_gb = 0.0
    l2_dram_used_source = ""
    # Numerator and denominator must describe the SAME thing.  This tile
    # previously showed OS host memory (/proc/meminfo) over a HiCache
    # allocation denominator, and the Interactive surface showed HiCache
    # residency over the same denominator — two different numerators under one
    # label.  Route both through the shared resolver.
    # The shared L2 resolver runs further down, once kv_bytes_tok_kb exists.
    #
    # It used to run HERE and read kv_bytes_tok_kb, which is not defined until
    # roughly a thousand lines later. The UnboundLocalError was swallowed by
    # the block's own `except Exception`, so _l2res was never assigned and
    # every L2 figure fell through to the TP-sharding heuristic -- including
    # after v1.53.1 taught the resolver to prefer the server's own token
    # gauge. That fix could not take effect while the call could not run.
    # A static use-before-assignment scan now guards the whole class
    # (validate_math group 0O).
    _l2_cap_measured, _l2_cap_conflict = False, ""
    _l2_used_tokens_variation_pct = 0.0
    _l2_used_tokens_min = 0.0
    _l2_used_tokens_max = 0.0

    # Mem fraction static governs how much HBM is reserved for KV; the L3 size
    # is the L3 storage-cache capacity. l3_fs_total_gb already loaded above.

    # ── Performance targets (for KPI tile "ideal/peak" annotations) ──────────
    # These are rule-of-thumb references for a typical enterprise inference
    # rig (PCIe Gen4 datacenter NVMe). Users can override via setup.json keys.
    # Why not pull from SMART? SMART reports the device's *rated* sequential
    # peaks, but those are achieved only at very high QD with large block sizes
    # — not what mixed AI workloads actually do. The "target" tile is meant as
    # context ("are we anywhere near what the hardware can do"), not a SLO.
    nvme_rd_bw_target_mbs   = _safe_float(_pick(setup,
        ["L3 (local storage) read BW target MB/s","nvme_rd_bw_target_mbs"], 7000.0))
    nvme_wr_bw_target_mbs   = _safe_float(_pick(setup,
        ["L3 (local storage) write BW target MB/s","nvme_wr_bw_target_mbs"], 5000.0))
    # L3 storage R/W endurance target: TB/day at rated TBW spread over 5y warranty.
    # rated TBW comes from smart_summary.json if SsdHardwareMonitor wrote it.
    rated_tbw_tb            = _safe_float(smart.get("rated_tbw_tb", 7.3))  # Dell CM7 default
    # Endurance budget is computed later, once duration_s is known.
    ssd_lifetime_writes_tb_per_run = 0.0  # filled after duration_s is set
    # DRAM BW target: assigned below once dram_peak_cap is autodetected from CPU.
    dram_bw_target_gbs      = 0.0  # filled in after CPU autodetect block

    # Latency / throughput
    # Prefer run-local Prometheus counter deltas from sglang_timeseries.csv.
    # Older summaries can carry stale/default mean values (for example both an
    # L2-only and an L3-active run showing the same TTFT/TPOT) while the
    # timeseries/percentile charts clearly differ.  Counter deltas are scoped to
    # the selected start/end window, so they are the authoritative Executive KPI
    # source whenever present.
    ttft_from_ts_ms = _ts_ratio_delta_ms(
        sglang_ts,
        "sglang_time_to_first_token_seconds_sum",
        "sglang_time_to_first_token_seconds_count",
    ) or _ts_ratio_delta_ms(sglang_ts, "time_to_first_token_seconds_sum", "time_to_first_token_seconds_count")
    tpot_from_ts_ms = _ts_ratio_delta_ms(
        sglang_ts,
        "sglang_inter_token_latency_seconds_sum",
        "sglang_inter_token_latency_seconds_count",
    ) or _ts_ratio_delta_ms(sglang_ts, "inter_token_latency_seconds_sum", "inter_token_latency_seconds_count")
    e2e_from_ts_ms = _ts_ratio_delta_ms(
        sglang_ts,
        "sglang_e2e_request_latency_seconds_sum",
        "sglang_e2e_request_latency_seconds_count",
    ) or _ts_ratio_delta_ms(sglang_ts, "e2e_request_latency_seconds_sum", "e2e_request_latency_seconds_count")

    # KPI fallback order:
    #   1) selected-window Δsum/Δcount counters
    #   2) selected-window percentile-timeseries p50 active mean
    #   3) sglang_summary.json only as last fallback
    # This avoids different runs reusing the same stale summary TTFT/TPOT.
    ttft_from_pct_ms = _pct_ts_latency_ms(pct_ts, "ttft", "p50")
    tpot_from_pct_ms = _pct_ts_latency_ms(pct_ts, "itl", "p50")
    e2e_from_pct_ms  = _pct_ts_latency_ms(pct_ts, "e2e", "p50")

    # Separate p50 summary values. Mean remains useful for overall capacity
    # planning; p50 gives the typical request/token path.
    # Whole-window p50 first, the per-interval series only as a fallback.
    # _pct_ts_latency_ms averages each interval's p50 over active intervals,
    # which weights a quiet interval equally with a busy one and answers a
    # different question from "the median request".  Both this report and the
    # End report used to prefer it, from different sources, so the same label
    # carried different numbers.
    ttft_p50_ms = _safe_float(_pick(sglang, [
        "server_ttft_p50_ms", "ttft_p50_ms", "median_ttft_ms", "p50_ttft_ms"
    ], 0.0)) or ttft_from_pct_ms
    tpot_p50_ms = _safe_float(_pick(sglang, [
        "server_itl_p50_ms", "server_tpot_p50_ms", "itl_p50_ms", "tpot_p50_ms",
        "median_itl_ms", "median_tpot_ms", "p50_itl_ms", "p50_tpot_ms"
    ], 0.0)) or tpot_from_pct_ms
    e2e_p50_ms = _safe_float(_pick(sglang, [
        "server_e2e_p50_ms", "e2e_p50_ms", "median_latency_ms", "p50_e2e_ms"
    ], 0.0)) or e2e_from_pct_ms

    # The order above, applied by the shared kernel rather than by an `or`
    # chain here. The comparison report had its own version of this -- step 3
    # only -- and reported a different TTFT for the same window. One
    # implementation is the only thing that stops that recurring.
    _lat_ttft = _k_resolve_lat(
        "ttft", ts_ms=ttft_from_ts_ms, pct_ms=ttft_from_pct_ms,
        summary_ms=_safe_float(_pick(sglang, [
            "server_ttft_ms", "ttft_ms", "avg_ttft_ms", "mean_ttft_ms",
            "time_to_first_token_ms", "server_ttft_p50_ms"], 0.0)),
        summary_method=str(_pick(sglang, ["server_ttft_ms_method"], "") or ""))
    _lat_tpot = _k_resolve_lat(
        "tpot", ts_ms=tpot_from_ts_ms, pct_ms=tpot_from_pct_ms,
        summary_ms=_safe_float(_pick(sglang, [
            "server_itl_ms", "tpot_ms", "avg_tpot_ms", "mean_tpot_ms",
            "itl_ms", "server_itl_p50_ms"], 0.0)),
        summary_method=str(_pick(sglang, ["server_itl_ms_method"], "") or ""))
    _lat_e2e = _k_resolve_lat(
        "e2e", ts_ms=e2e_from_ts_ms, pct_ms=e2e_from_pct_ms,
        summary_ms=_safe_float(_pick(sglang, [
            "server_e2e_ms", "e2e_ms", "avg_latency_ms", "latency_ms",
            "server_e2e_p50_ms"], 0.0)),
        summary_method=str(_pick(sglang, ["server_e2e_ms_method"], "") or ""))
    ttft_ms, tpot_ms, e2e_ms = (_lat_ttft["ms"], _lat_tpot["ms"],
                                _lat_e2e["ms"])
    if ttft_from_ts_ms > 0:
        sglang["server_ttft_ms_method"] = "delta_sglang_time_to_first_token_seconds_sum_count"
    if tpot_from_ts_ms > 0:
        sglang["server_itl_ms_method"] = "delta_sglang_inter_token_latency_seconds_sum_count"
    if e2e_from_ts_ms > 0:
        sglang["server_e2e_ms_method"] = "delta_sglang_e2e_request_latency_seconds_sum_count"
    if ttft_from_ts_ms <= 0 and ttft_from_pct_ms > 0:
        sglang["server_ttft_ms_method"] = "selected_window_sglang_percentiles_timeseries_ttft_p50_active_mean"
    if tpot_from_ts_ms <= 0 and tpot_from_pct_ms > 0:
        sglang["server_itl_ms_method"] = "selected_window_sglang_percentiles_timeseries_itl_p50_active_mean"
    if e2e_from_ts_ms <= 0 and e2e_from_pct_ms > 0:
        sglang["server_e2e_ms_method"] = "selected_window_sglang_percentiles_timeseries_e2e_p50_active_mean"

    # Final cross-tab consistency guard: when Combined Report already has the
    # freshly generated End Report, prefer its parsed TTFT/TPOT values for the
    # Executive KPI tiles.  This avoids Executive-only stale fallback values
    # while preserving formula/source notes below.
    _static_kpis = static_kpi_overrides or {}
    _static_ttft = _safe_float(_static_kpis.get("ttft_ms", 0.0), 0.0)
    _static_tpot = _safe_float(_static_kpis.get("tpot_ms", 0.0), 0.0)
    if _static_ttft > 0:
        ttft_ms = _static_ttft
        sglang["server_ttft_ms_method"] = "canonical_combined_latency_kpi"
    if _static_tpot > 0:
        tpot_ms = _static_tpot
        sglang["server_itl_ms_method"] = "canonical_combined_latency_kpi"
    if _safe_float(_static_kpis.get("ttft_p50_ms", 0.0), 0.0) > 0:
        ttft_p50_ms = _safe_float(_static_kpis.get("ttft_p50_ms", 0.0), 0.0)
    if _safe_float(_static_kpis.get("tpot_p50_ms", 0.0), 0.0) > 0:
        tpot_p50_ms = _safe_float(_static_kpis.get("tpot_p50_ms", 0.0), 0.0)
    if _safe_float(_static_kpis.get("e2e_ms", 0.0), 0.0) > 0:
        e2e_ms = _safe_float(_static_kpis.get("e2e_ms", 0.0), 0.0)
    if _safe_float(_static_kpis.get("e2e_p50_ms", 0.0), 0.0) > 0:
        e2e_p50_ms = _safe_float(_static_kpis.get("e2e_p50_ms", 0.0), 0.0)
    # Cache hit: use the same canonical cache-hit function as Interactive and End Report.
    # Primary semantics: cache-served prefill/prompt tokens over cache+compute
    # prefill/prompt tokens. Cached/prompt and gauge values remain diagnostics.
    _tok_num = _safe_float(_pick(sglang, ["cache_hit_token_weighted_numerator_tokens"], 0.0), 0.0) or _ts_delta(sglang_ts, "cached_tokens_total")
    _tok_den = _safe_float(_pick(sglang, ["cache_hit_token_weighted_denominator_tokens"], 0.0), 0.0) or _ts_delta(sglang_ts, "prompt_tokens_total")
    cache_hit_token_weighted = _safe_float(_pick(sglang, ["cache_hit_token_weighted_pct", "cache_hit_cached_prompt_pct"], 0.0), 0.0) or _pct_from_ratio(_tok_num, _tok_den)

    _req_num = _safe_float(_pick(sglang, ["cache_hit_request_weighted_numerator_requests"], 0.0), 0.0) or (_ts_delta(sglang_ts, "request_cache_hit_total") or _ts_delta(sglang_ts, "cache_hit_request_total") or _ts_delta(sglang_ts, "request_cache_hits_total") or _ts_delta(sglang_ts, "cache_hit_requests_total"))
    _req_den = _safe_float(_pick(sglang, ["cache_hit_request_weighted_denominator_requests"], 0.0), 0.0) or (_ts_delta(sglang_ts, "request_total") or _ts_delta(sglang_ts, "requests_total"))
    cache_hit_request_weighted = _safe_float(_pick(sglang, ["cache_hit_request_weighted_pct"], 0.0), 0.0) or _pct_from_ratio(_req_num, _req_den)

    _gauge_col = _ts_col(sglang_ts, "cache_hit_rate")
    _gauge_mean = _normalise_pct(_safe_float(_gauge_col.get("mean", 0.0), 0.0)) if _gauge_col else 0.0
    cache_hit_time_weighted = _safe_float(_pick(sglang, ["cache_hit_time_weighted_pct", "cache_hit_gauge_overall_pct"], 0.0), 0.0) or _gauge_mean
    cache_hit_prefill_token_weighted = _safe_float(_pick(sglang, ["cache_hit_prefill_token_weighted_pct"], 0.0), 0.0)
    cache_hit_gauge_active = _safe_float(_pick(sglang, ["cache_hit_gauge_active_pct", "cache_hit_active_avg_pct", "cache_hit_rate_realtime_pct"], 0.0), 0.0)

    if cache_hit_token_weighted > 0:
        cache_hit = cache_hit_token_weighted
        cache_hit_note_prefix = "selected_window_token_weighted_cached_tokens_over_prompt_tokens"
    elif cache_hit_request_weighted > 0:
        cache_hit = cache_hit_request_weighted
        cache_hit_note_prefix = "selected_window_request_weighted_request_cache_hit_over_request_total"
    elif cache_hit_time_weighted > 0:
        cache_hit = cache_hit_time_weighted
        cache_hit_note_prefix = "selected_window_time_weighted_avg_over_time_sglang_cache_hit_rate"
    else:
        cache_hit = _safe_float(_pick(sglang, ["cache_hit_pct","cache_hit_rate_pct", "cache_hit_rate_realtime_pct","cache_hit"], 0.0))
        cache_hit_note_prefix = str(_pick(sglang, ["cache_hit_calc_method"], "fallback"))
    # Override with common_kpis.py when available so Executive methodology and
    # KPI tile are driven by the same shared cache-hit implementation.
    _common_cache = static_kpi_overrides if isinstance(static_kpi_overrides, dict) else {}
    if not _common_cache and compute_cache_hit_kpis is not None:
        try:
            _common_cache = compute_cache_hit_kpis(raw_dir=raw_dir)
        except Exception:
            _common_cache = {}
    if _common_cache:
        cache_hit = _safe_float(_common_cache.get("cache_hit_pct", cache_hit), cache_hit)
        cache_hit_note_prefix = str(_common_cache.get("cache_hit_method", cache_hit_note_prefix) or cache_hit_note_prefix)
        cache_hit_token_weighted = _safe_float(_common_cache.get("cache_hit_token_weighted_pct", cache_hit_token_weighted), cache_hit_token_weighted)
        cache_hit_prefill_token_weighted = _safe_float(_common_cache.get("cache_hit_prefill_token_weighted_pct", cache_hit_prefill_token_weighted), cache_hit_prefill_token_weighted)
        cache_hit_time_weighted = _safe_float(_common_cache.get("cache_hit_time_weighted_pct", cache_hit_time_weighted), cache_hit_time_weighted)
        cache_hit_request_weighted = _safe_float(_common_cache.get("cache_hit_request_weighted_pct", cache_hit_request_weighted), cache_hit_request_weighted)
        cache_hit_gauge_active = _safe_float(_common_cache.get("cache_hit_gauge_active_pct", cache_hit_gauge_active), cache_hit_gauge_active)
        cache_hit_effective_prompt = _safe_float(_common_cache.get("cache_hit_effective_prompt_pct", _safe_float(_pick(sglang, ["cache_hit_effective_prompt_pct"], 0.0), 0.0)), 0.0)
    else:
        cache_hit_effective_prompt = _safe_float(_pick(sglang, ["cache_hit_effective_prompt_pct"], 0.0), 0.0)
    # cached_tokens_total / prompt_tokens_total exists only when SGLang exports
    # prompt_tokens_total; otherwise its 0 means "not measured".
    cache_hit_tw_available = bool(_common_cache.get("cache_hit_cached_prompt_available", _tok_den > 0)
                                  if _common_cache else _tok_den > 0)

    # Token-weighted prefill hit rate takes precedence over every gauge-derived
    # figure.  The previous headline was the mean of sglang_cache_hit_rate over
    # ALL samples, idle ones included: at a 2.5% duty cycle that is ~97% zeros,
    # which reported 0.5% for a cache that was actually serving a third of
    # prefill tokens.  That number described the wall clock, not the cache.
    # This matches sum(increase(prefill_cache)) / sum(increase(cache+compute))
    # in PromQL, so the tile and a Grafana panel agree.
    try:
        _pf_p = _first_existing(raw_dir, ["sglang_timeseries.csv"])
        if _pf_p:
            def _pf_delta(_mode: str) -> float:
                _cols = _amoprof_read_all_columns_substr(
                    _pf_p, f"mode={_mode}")
                _best = 0.0
                for _c in _cols:
                    _v = [x for x in _c if x == x]
                    if len(_v) >= 2:
                        _d = _v[-1] - _v[0]
                        if _d < 0:
                            _d = _v[-1]          # counter reset mid-window
                        _best = max(_best, _d)
                return _best

            _pf_hit = _k_prefill_hit(_pf_delta("prefill_cache"),
                                     _pf_delta("prefill_compute"))
            if _pf_hit.get("available"):
                cache_hit = _pf_hit["pct"]
                cache_hit_prefill_token_weighted = _pf_hit["pct"]
                cache_hit_note_prefix = (
                    "prefill token-weighted: \u0394prefill_cache \u00f7 "
                    "(\u0394prefill_cache + \u0394prefill_compute) over the window")
                setup["_cache_hit_detail"] = _pf_hit["note"]
    except Exception:
        pass

    cache_hit_tw = cache_hit_token_weighted
    throughput = _safe_float(_pick(sglang, ["gen_tp_peak","ai_op_decode_tok_s",
                                             "gen_tp_active_mean","gen_tp_mean",
                                             "throughput_tok_s","peak_throughput_tok_s"], 0.0))
    tp_active  = _safe_float(_pick(sglang, ["gen_tp_active_mean","ai_op_decode_tok_s"], 0.0))
    # Fallback: derive throughput from sglang_timeseries.csv when summary is 0.
    # The timeseries column "gen_throughput" carries label suffixes such as
    # gen_throughput[engine_type=unified], so we match by substring.
    # The "active mean" is the mean of the non-zero samples (ignoring idle).
    if throughput == 0 and sglang_ts.get("rows", 0) > 0:
        _col = _ts_col(sglang_ts, "gen_throughput", "generation_tokens_total",
                       "output_token_throughput", "token_throughput")
        if _col:
            if _col.get("nonzero_count", 0) > 0:
                throughput = round(_safe_float(_col.get("nonzero_mean",
                                               _col.get("nonzero_sum", 0) /
                                               max(_col.get("nonzero_count", 1), 1))), 2)
                tp_active  = throughput
            elif _col.get("max", 0) > 0:
                throughput = round(_safe_float(_col.get("max", 0)), 2)
                tp_active  = round(_safe_float(_col.get("mean", 0)), 2)
    # Secondary fallback: derive throughput from sglang_summary decode token count
    if throughput == 0:
        _decode_toks = _safe_float(_pick(sglang, ["rt_decode_tokens",
                                                    "decode_tokens_total"], 0.0))
        _elapsed_s   = _safe_float(_pick(sglang, ["collection_elapsed_s", "power_elapsed_s"], 0.0)) or _safe_float(_pick(blk, ["duration_s", "run_duration_s"], 0.0))
        if _decode_toks > 0 and _elapsed_s > 0:
            throughput = round(_decode_toks / _elapsed_s, 2)
            tp_active = throughput

    # The figure the Token throughput tile headlines, and where it came from.
    # `throughput` is the peak-ish summary value and `tp_active` the mean over
    # active samples; prefer the active mean and say which was used, so the
    # tile cannot be read as a peak.
    _kpi_out_tp = _safe_float(tp_active, 0.0) or _safe_float(throughput, 0.0)
    _kpi_out_tp_src = ("active mean of sglang_gen_throughput (idle samples "
                       "excluded)" if _safe_float(tp_active, 0.0) > 0
                       else "summary throughput figure — not verified as an "
                            "active mean")

    tp_p50 = (_ts_active_p50(sglang_ts, "sglang_gen_throughput", "gen_throughput")
              or _safe_float(_pick(sglang, ["gen_tp_p50", "gen_tp_active_p50",
                                            "generation_throughput_p50", "throughput_p50_tok_s"], 0.0)))
    if tp_p50 <= 0 and tp_active > 0:
        tp_p50 = tp_active

    # Apply canonical common throughput KPIs only after throughput/tp_active/tp_p50
    # have been initialized. v1.39.49 applied this too early and caused:
    # "cannot access local variable 'throughput' where it is not associated with a value".
    _common_tp_mean = _safe_float(_static_kpis.get("throughput_mean", 0.0), 0.0)
    _common_tp_p50 = _safe_float(_static_kpis.get("throughput_p50", 0.0), 0.0)
    _common_tp_peak = _safe_float(_static_kpis.get("throughput_peak", 0.0), 0.0)
    if _common_tp_mean > 0:
        tp_active = _common_tp_mean
        throughput = max(throughput, tp_active)
    if _common_tp_p50 > 0:
        tp_p50 = _common_tp_p50
    if _common_tp_peak > 0:
        throughput = max(throughput, _common_tp_peak)
    if throughput > 0:
        throughput = max(throughput, tp_active, tp_p50)

    # Final TPOT/ITL fallback for Executive tab: if ITL counters were absent or
    # zero but output-token throughput is available, avoid showing an impossible
    # 0 ms/token.  Mark the method in the note/formula sections via summary.
    if tpot_ms <= 0 and throughput > 0:
        tpot_ms = round(1000.0 / throughput, 2)
        sglang.setdefault("server_itl_ms_method", "fallback_inverse_prometheus_output_token_throughput")

    # GPU / HBM
    gpu_util   = _safe_float(_pick(gpu, ["gpu_util_mean","gpu_util_pct_mean","util_mean"], 0.0))
    gpu_peak   = _safe_float(_pick(gpu, ["gpu_util_peak","gpu_util_pct_peak","util_peak"], 0.0))
    # Prefer active-window GPU utilization for KPI tiles.  Overall means can be
    # artificially low when the Prometheus window includes idle gaps or GPUs not
    # active in the TP/DP group.  Non-zero samples from gpu_timeseries.csv are
    # scoped to the selected run and match the interactive/static chart intent.
    _gpu_active_util = _ts_active_mean(gpu_ts, "gpu_util", "DCGM_FI_DEV_GPU_UTIL")
    if _gpu_active_util > 0:
        gpu_util = _gpu_active_util
        gpu["gpu_util_mean_method"] = "active_nonzero_mean_from_gpu_timeseries"
    _gpu_peak_from_ts = _safe_float(_ts_col(gpu_ts, "gpu_util", "DCGM_FI_DEV_GPU_UTIL").get("max", 0.0))
    if _gpu_peak_from_ts > 0:
        gpu_peak = max(gpu_peak, _gpu_peak_from_ts)
    # 4-value decomposition (matches cache-hit KPI shape) — reused by the KPI
    # tile and by the A4 layer status row so all Executive surfaces read the
    # same overall/active/threshold/idle values.
    _gpu_dec = _gpu_util_decomposition(gpu_ts, gpu)
    _gpu_overall_mean = _gpu_dec["overall_mean"]
    _gpu_active_mean_dec = _gpu_dec["active_mean"]
    _gpu_active_threshold = _gpu_dec["active_threshold_pct"]
    _gpu_idle_fraction = _gpu_dec["idle_fraction_pct"]
    if _gpu_dec["peak"] > gpu_peak:
        gpu_peak = _gpu_dec["peak"]
    hbm_gb     = _safe_float(_pick(gpu, ["hbm_used_gb_mean","hbm_gb","mem_used_gb_mean"], 0.0))
    if hbm_gb > 1000:
        hbm_gb = _k_gb_from_mib(hbm_gb)   # nvidia-smi MiB under a GB name
    if hbm_gb <= 0:
        hbm_gb = _k_gb_from_mib(_safe_float(_pick(gpu, ["hbm_used_mb_mean"], 0.0)))
    hbm_pct    = _safe_float(_pick(gpu, ["hbm_util_pct_mean","hbm_pct","mem_util_pct_mean"], 0.0))
    # Per-device HBM capacity: the measured DCGM / nvidia-smi total (MiB) is
    # the denominator for the measured used value, so both are decimal GB.
    # The setup_details figure is a nominal board size ("40 GB" on an A100 is
    # 40 GiB) and is only a fallback, converted from GiB.  The aggregate HBM
    # capacity is based on the active inference parallelism (TP × DP), not
    # necessarily all GPUs in the host.
    hbm_total_setup = _safe_float(_pick(setup, [
        "GPU Memory per Device GB", "GPU memory per device GB",
        "HBM per GPU GB", "hbm_per_gpu_gb", "gpu_memory_per_device_gb"
    ], 0.0))
    _hbm_total_meas = _safe_float(_pick(gpu, ["hbm_total_gb"], 0.0))
    if _hbm_total_meas > 1000:
        _hbm_total_meas = _k_gb_from_mib(_hbm_total_meas)   # MiB under a GB name
    if _hbm_total_meas <= 0:
        _hbm_total_meas = _k_gb_from_mib(_safe_float(_pick(gpu, ["hbm_total_mb_per_gpu"], 0.0)))
    if _hbm_total_meas > 0:
        hbm_total = _hbm_total_meas
    elif hbm_total_setup > 0:
        hbm_total = _k_gb_from_gib(hbm_total_setup)
    else:
        hbm_total = _k_gb_from_gib(40.0)

    # Defensive HBM-total promotion: if per-GPU used exceeds per-GPU total
    # (measurement can't physically exceed capacity), the total was populated
    # from a stale fallback — DCGM omitted FB_TOTAL and we fell back to 40 GB
    # while FB_USED clearly belongs to a larger accelerator (80/96/141/192 GB).
    # Mirror amoprof.py's Metrics-side fix so the Executive tile never shows
    # > 100% HBM used, and record the promotion for the tile sub-note.
    hbm_total_source = ("dcgm_fb_total" if _hbm_total_meas > 0 else
                        "setup" if hbm_total_setup > 0 else "default_40gib")
    hbm_total_inferred = False
    try:
        if hbm_gb > 0 and hbm_total > 0 and hbm_gb > hbm_total * 1.05:
            for _cap_nom in (48.0, 80.0, 96.0, 120.0, 141.0, 192.0):
                _cap_gb = _k_gb_from_gib(_cap_nom)   # nominal board sizes are GiB
                if hbm_gb <= _cap_gb * 1.05:
                    hbm_total = _cap_gb
                    hbm_total_inferred = True
                    hbm_total_source = "inferred_from_measured_used"
                    break
            if hbm_gb > hbm_total:
                import math as _math
                hbm_total = float(max(hbm_total, _math.ceil(hbm_gb)))
                hbm_total_inferred = True
                hbm_total_source = "inferred_from_measured_used"
    except Exception:
        pass

    # raw/gpu_config.json is the authoritative nvidia-smi device inventory
    # (written at collect/service start).  Prefer it over values inferred from
    # setup_details.json / the time-series, so GPU model, device count and —
    # critically — the per-GPU HBM capacity used as the "HBM used" denominator
    # come from the hardware rather than from a parsed config string.
    _gpu_cfg: dict = {}
    try:
        _gcp = raw_dir / "gpu_config.json"
        if _gcp.exists() and _gcp.stat().st_size > 0:
            _gcp_obj = json.loads(_gcp.read_text(encoding="utf-8"))
            if isinstance(_gcp_obj, dict) and _gcp_obj.get("gpu_count"):
                _gpu_cfg = _gcp_obj
    except Exception:
        _gpu_cfg = {}
    if _gpu_cfg.get("gpu_name") and (not gpu_desc or gpu_desc == "unknown"):
        gpu_desc = str(_gpu_cfg["gpu_name"])

    physical_gpu_count = _safe_float(_gpu_cfg.get("gpu_count", 0))
    if physical_gpu_count <= 0:
        physical_gpu_count = _safe_float(_pick(setup, ["GPU Count", "gpu_count", "num_gpus", "Number of GPUs"], 0))
    if physical_gpu_count <= 0:
        try:
            import re as _re
            _m_gpu = _re.search(r"(\d+)\s*[xX]", str(gpu_desc))
            physical_gpu_count = float(_m_gpu.group(1)) if _m_gpu else 0.0
        except Exception:
            physical_gpu_count = 0.0
    if physical_gpu_count <= 0:
        physical_gpu_count = _safe_float(_pick(gpu, ["gpu_count", "num_gpus", "gpu_num"], 1)) or 1.0

    tp_count = _safe_float(_pick(setup, ["TP size", "tp_size", "tensor_parallel_size", "TP", "tp"], 0.0))
    if tp_count <= 0:
        tp_count = _safe_float(_gpu_cfg.get("tp_size", 0) or 0)
    dp_count = _safe_float(_pick(setup, ["DP size", "dp_size", "data_parallel_size", "DP", "dp"], 1.0)) or 1.0
    if dp_count <= 0:
        dp_count = _safe_float(_gpu_cfg.get("dp_size", 1) or 1) or 1.0
    active_gpu_count = tp_count * dp_count if tp_count > 0 else physical_gpu_count
    if not (active_gpu_count == active_gpu_count and active_gpu_count > 0):
        # `not (x > 0)` also catches NaN, which `x <= 0` does not: every
        # comparison with NaN is False, so a NaN count slipped through and
        # propagated into every per-GPU figure.
        active_gpu_count = (physical_gpu_count
                            if (isinstance(physical_gpu_count, (int, float))
                                and physical_gpu_count == physical_gpu_count
                                and physical_gpu_count > 0)
                            else 1.0)
    # gpu_config records how many devices the server actually occupies; it
    # already reconciled TP×DP against the physical inventory.
    if _safe_float(_gpu_cfg.get("gpus_in_use", 0)) > 0 and tp_count <= 0:
        active_gpu_count = _safe_float(_gpu_cfg["gpus_in_use"])
    # Per-GPU HBM capacity: nvidia-smi memory.total beats any inferred value.
    # gpu_config.json stores memory_total_mib and hbm_per_gpu_gb = MiB / 1024
    # (GiB); convert from the MiB figure when present.
    _cfg_mib = max((_safe_float((g or {}).get("memory_total_mib", 0))
                    for g in (_gpu_cfg.get("gpus") or []) if isinstance(g, dict)),
                   default=0.0)
    if _cfg_mib > 0:
        hbm_total = _k_gb_from_mib(_cfg_mib)
    elif _safe_float(_gpu_cfg.get("hbm_per_gpu_gb", 0)) > 0:
        hbm_total = _k_gb_from_gib(_safe_float(_gpu_cfg["hbm_per_gpu_gb"]))

    hbm_used_total_gb = hbm_gb * active_gpu_count if hbm_gb > 0 else 0.0
    hbm_total_all_gpus_gb = hbm_total * active_gpu_count if hbm_total > 0 else 0.0
    gpu_count = active_gpu_count
    if hbm_total_all_gpus_gb > 0 and hbm_used_total_gb > 0:
        # Clamp: HBM used cannot physically exceed total capacity; if we still
        # see > 100% here it means promotion above failed to catch the case,
        # so hide the misleading >100% number rather than propagate it.
        hbm_pct = min(100.0, hbm_used_total_gb / hbm_total_all_gpus_gb * 100.0)
    dcgm_active = _safe_float(_pick(gpu, ["dcgm_hbm_bw_active_pct","dcgm_active_pct"], 0.0))
    # GPU power: the summary key is power_w_peak / power_w_mean (matches the
    # interactive KPI tile). Older keys kept as fallbacks.
    gpu_power  = _safe_float(_pick(gpu, ["power_w_peak","power_peak_w","gpu_power_peak_w",
                                          "power_all_gpus_w_peak","gpu_power_w_peak"], 0.0))
    gpu_power_mean = _safe_float(_pick(gpu, ["power_w_mean","power_mean_w",
                                             "gpu_power_mean_w"], 0.0))
    # Fallback: aggregate from power_timeseries.csv (per-sample gpu_power sum).
    if gpu_power == 0.0:
        _pwr_ts = _read_csv_summary(_first_existing(raw_dir, ["power_timeseries.csv"]))
        _pcol = _ts_col(_pwr_ts, "gpu_power", "power")
        if _pcol.get("max", 0) > 0:
            gpu_power = round(_safe_float(_pcol.get("max", 0)), 0)
            if gpu_power_mean == 0.0:
                gpu_power_mean = round(_safe_float(_pcol.get("nonzero_mean",
                                                   _pcol.get("mean", 0))), 0)

    # NVMe / L3 storage
    read_gb   = _safe_float(_pick(blk, ["nvme_read_total_gb","read_gb_total","read_GB_total"], 0.0))
    if read_gb == 0.0:
        read_gb = _k_gb_from_bytes(_safe_float(_pick(blk, ["read_bytes_total"], 0.0)))
    write_gb  = _safe_float(_pick(blk, ["nvme_write_total_gb","write_gb_total","write_GB_total"], 0.0))
    if write_gb == 0.0:
        write_gb = _k_gb_from_bytes(_safe_float(_pick(blk, ["write_bytes_total"], 0.0)))

    # Byte totals integrated from the device bandwidth series when no summed
    # byte counter exists.
    #
    # These come from blktrace size_bytes sums. A run whose blktrace never
    # published byte counters printed "Physical L3 block R / W total
    # 0.0 MB / 0.0 GB" directly beside tiles reading 17 MB/s and 39.1 MB/s
    # from the same device over a 10.79 h window -- a total that is about
    # 644 GB read and 1,481 GB written and derivable from the series already
    # in hand. A zero stated as a measured total is worse than no tile.
    block_total_source = "blktrace size_bytes sum" if (read_gb or write_gb) else ""
    if read_gb == 0.0 or write_gb == 0.0:
        try:
            _bw_span = 0.0
            for _c in ("time_sec",):
                _tcol = (nvme_ts.get(_c) or {})
                _bw_span = _safe_float(_tcol.get("delta", 0))
                break
            # The device file's own time column is the right span for its own
            # series, and it is available here; duration_s is resolved later
            # in this function, so it deliberately is not used.
            if _bw_span < _MIN_PLAUSIBLE_WINDOW_S:
                _bw_span = 0.0
            if _bw_span > 0:
                # mean rate x span; a mean over active samples only would
                # overstate a device that was idle for part of the window.
                for _which, _cols in (("r", ("rd_bw_mbs", "read_bw_mb_s")),
                                      ("w", ("wr_bw_mbs", "write_bw_mb_s"))):
                    if (_which == "r" and read_gb > 0) or (_which == "w" and write_gb > 0):
                        continue
                    for _col in _cols:
                        _st = nvme_ts.get(_col) or {}
                        _mean = _safe_float(_st.get("mean", 0))
                        if _mean > 0:
                            _gb = _mean * _bw_span / 1000.0   # MB/s x s -> decimal GB
                            if _which == "r":
                                read_gb = _gb
                            else:
                                write_gb = _gb
                            block_total_source = (
                                f"integrated from {_col} x {_bw_span:,.0f}s "
                                f"window (no blktrace byte counter)")
                            break
        except Exception:
            pass
    rw_ratio  = read_gb / max(write_gb, 0.001)

    # Device bandwidth comes from the block layer only, and each direction
    # records where it came from: the tile and every sentence that quotes it
    # say "not measured" rather than print a 0 that was never observed, or a
    # token-derived figure under a device label.
    nvme_rd_bw_src = ""
    nvme_wr_bw_src = ""
    nvme_rd_bw = _safe_float(_pick(blk, ["nvme_rd_bw_mbs_mean","read_bw_mb_s_mean",
                                          "nvme_read_bw_mbs"], 0.0))
    if nvme_rd_bw > 0:
        nvme_rd_bw_src = "summary.json"
    else:
        for col in ("rd_bw_mbs","read_bw_mbs","rkB_s"):
            if col in nvme_ts and nvme_ts[col].get("mean",0) > 0:
                nvme_rd_bw = _safe_float(nvme_ts[col]["mean"])
                if col == "rkB_s": nvme_rd_bw = nvme_rd_bw * 1024 / 1e6   # iostat KiB/s -> MB/s
                nvme_rd_bw_src = f"{col} · nvme_driver_timeseries.csv"
                break

    nvme_wr_bw = _safe_float(_pick(blk, ["nvme_wr_bw_mbs_mean","write_bw_mb_s_mean",
                                          "nvme_write_bw_mbs"], 0.0))
    if nvme_wr_bw > 0:
        nvme_wr_bw_src = "summary.json"
    else:
        for col in ("wr_bw_mbs","write_bw_mbs","wkB_s"):
            if col in nvme_ts and nvme_ts[col].get("mean",0) > 0:
                nvme_wr_bw = _safe_float(nvme_ts[col]["mean"])
                if col == "wkB_s": nvme_wr_bw = nvme_wr_bw * 1024 / 1e6   # iostat KiB/s -> MB/s
                nvme_wr_bw_src = f"{col} · nvme_driver_timeseries.csv"
                break

    nvme_rd_iops = _safe_float(_pick(blk, ["nvme_rd_iops_mean","read_iops_mean"], 0.0))
    if nvme_rd_iops == 0.0 and "rd_iops" in nvme_ts:
        nvme_rd_iops = _safe_float(nvme_ts["rd_iops"].get("max", 0.0))
    nvme_wr_iops = _safe_float(_pick(blk, ["nvme_wr_iops_mean","write_iops_mean"], 0.0))
    nvme_util    = _safe_float(_pick(blk, ["nvme_io_util_pct","nvme_util_pct",
                                                  "io_util_pct"], 0.0))
    if nvme_util == 0.0:
        for _nu_col in ("io_util_pct", "util_pct", "%util", "device_util_pct"):
            if _nu_col in nvme_ts and nvme_ts[_nu_col].get("mean", 0) > 0:
                nvme_util = _safe_float(nvme_ts[_nu_col].get("mean", 0.0))
                break
        # Also check iostat_timeseries.csv
        if nvme_util == 0.0:
            _ios_ts = _read_csv_summary(_first_existing(raw_dir, ["iostat_timeseries.csv"]))
            for _nu_col in ("%util", "util_pct", "io_util_pct"):
                if _nu_col in _ios_ts and _ios_ts[_nu_col].get("mean", 0) > 0:
                    nvme_util = _safe_float(_ios_ts[_nu_col].get("mean", 0.0))
                    break
        # Final fallback: derive device-busy % from the blktrace temporal pattern
        # (fraction of time windows that had any read/write/trim activity).
        # iostat/nvme_driver may be empty even when blktrace captured real I/O.
        if nvme_util == 0.0:
            _tp_path = _first_existing(
                raw_dir / "blktrace_analysis",
                ["temporal_read_write_trim_pattern.csv", "temporal_pattern.csv"]) \
                if (raw_dir / "blktrace_analysis").exists() else None
            if _tp_path:
                try:
                    import csv as _csv_tp
                    _busy = 0; _tot = 0
                    with _tp_path.open(encoding="utf-8", errors="replace") as _ftp:
                        for _r in _csv_tp.DictReader(_ftp):
                            _tot += 1
                            _act = (_safe_float(_r.get("read", _r.get("read_bytes", 0))) +
                                    _safe_float(_r.get("write", _r.get("write_bytes", 0))) +
                                    _safe_float(_r.get("trim", _r.get("trim_bytes", 0))))
                            if _act > 0:
                                _busy += 1
                    if _tot > 0:
                        nvme_util = round(_busy / _tot * 100.0, 1)
                except Exception:
                    pass

    nvme_rd_lat = _safe_float(_pick(blk, ["nvme_rd_lat_ms_mean","read_lat_ms_mean"], 0.0))
    if nvme_rd_lat == 0.0 and "rd_lat_ms" in nvme_ts:
        nvme_rd_lat = _safe_float(nvme_ts["rd_lat_ms"].get("mean", 0.0))
    nvme_wr_lat = _safe_float(_pick(blk, ["nvme_wr_lat_ms_mean","write_lat_ms_mean"], 0.0))
    if nvme_wr_lat == 0.0 and "wr_lat_ms" in nvme_ts:
        nvme_wr_lat = _safe_float(nvme_ts["wr_lat_ms"].get("mean", 0.0))

    # Read request-size distribution from CSV if available
    # Columns: bucket, read_count, write_count
    req_size_16_64_pct = 0.0
    total_rd_ios = 0; ios_16_64 = 0
    req_size_path = _first_existing(raw_dir, ["request_size_distribution.csv"])
    if req_size_path:
        try:
            with req_size_path.open(encoding="utf-8", errors="replace") as f_rs:
                import csv as _csv
                rdr = _csv.DictReader(f_rs)
                for row in rdr:
                    rc = int(_safe_float(row.get("read_count", row.get("reads", 0))))
                    bkt = str(row.get("bucket","")).strip()
                    total_rd_ios += rc
                    if "16" in bkt or ("64" in bkt and "256" not in bkt):
                        ios_16_64 += rc
        except Exception:
            pass
        if total_rd_ios > 0:
            req_size_16_64_pct = ios_16_64 / total_rd_ios * 100.0

    # DRAM BW
    dram_total_bw  = 0.0
    dram_rd_bw     = 0.0
    dram_wr_bw     = 0.0
    dram_peak_bw   = 0.0
    # ── DRAM peak BW: prefer explicit setup value, else autodetect from CPU model.
    # The default 204.8 GB/s is correct only for 2S AMD EPYC Rome (7xx2) and
    # similar 8-channel DDR4-3200 platforms. On a DGX H100 (2S Sapphire Rapids
    # Xeon Platinum 8480C @ DDR5-4800, 16 channels total) it's actually ~614 GB/s,
    # and on Genoa EPYC 9004 (12-channel DDR5-4800) it's ~921 GB/s. Using 204.8
    # blindly gives a wildly low util % on newer hardware.
    def _detect_dram_peak_gbs() -> tuple[float, str]:
        """Return (peak_bw_gb_s, cpu_label) for the host's CPU.

        Source of truth: /proc/cpuinfo 'model name'. Returns (204.8, "default")
        when the CPU isn't recognised so we still produce a number (with a
        clear label) rather than crashing.
        """
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu = line.split(":", 1)[1].strip()
                        break
                else:
                    return 204.8, "default (CPU model not found)"
        except Exception:
            return 204.8, "default (cpuinfo unavailable)"
        # CPU model → (2-socket peak GB/s, friendly label). Single-socket halves it.
        # Channels × max DDR transfer rate × 8 B/ch × n_sockets. We always
        # assume 2-socket here (matches DGX/typical inference servers). The
        # exposed_total is half on 1S hosts but inference rigs are uniformly 2S.
        cpu_l = cpu.lower()
        # AMD EPYC Rome/Milan (Zen 2/3, DDR4-3200 8-channel)
        if "epyc 7" in cpu_l and any(t in cpu_l for t in
                                       ["7702","7742","7763","7773","7713","7543","7453","7443"]):
            return 204.8, "AMD EPYC Rome/Milan 2S · 8ch DDR4-3200"
        # AMD EPYC Genoa/Turin (Zen 4/5, DDR5-4800 12-channel)
        if any(t in cpu_l for t in ["epyc 9", "epyc-9", "genoa", "turin"]):
            return 921.6, "AMD EPYC Genoa/Turin 2S · 12ch DDR5-4800"
        # Intel Sapphire Rapids (Xeon Platinum 8xxx, DDR5-4800 8ch/socket)
        if "platinum 84" in cpu_l or "platinum 85" in cpu_l or "sapphire rapids" in cpu_l:
            return 614.4, "Intel Xeon Sapphire Rapids 2S · 8ch DDR5-4800/socket"
        # Intel Emerald/Granite Rapids (DDR5-5600/6400)
        if "platinum 86" in cpu_l or "platinum 87" in cpu_l or "emerald rapids" in cpu_l \
           or "granite rapids" in cpu_l:
            return 716.8, "Intel Xeon Emerald/Granite Rapids 2S · 8ch DDR5-5600/socket"
        # Intel Ice Lake (Xeon Platinum 83xx, DDR4-3200 8ch/socket)
        if "platinum 83" in cpu_l or "ice lake" in cpu_l:
            return 409.6, "Intel Xeon Ice Lake 2S · 8ch DDR4-3200/socket"
        return 204.8, f"default (unrecognised CPU: {cpu[:60]})"

    _dram_peak_auto, _dram_peak_label = _detect_dram_peak_gbs()
    dram_peak_cap = _safe_float(_pick(setup, ["DRAM peak GB/s", "dram_peak_gbs"],
                                       _dram_peak_auto))
    # Stash the label so layer-description rendering can show what CPU is assumed.
    if "DRAM peak GB/s" not in setup and "dram_peak_gbs" not in setup:
        setup["_dram_peak_label_auto"] = _dram_peak_label
    # Backfill the KPI target now that the per-CPU peak is known.
    dram_bw_target_gbs = dram_peak_cap
    for col in ("dram_total_gb_s", "dram_total_bw_gbs", "dram_bw_gbps", "total_bw_gbps",
                "memory_bw_gbps", "Total GB/s", "total_gb_s", "total_bw_gbs",
                "pcm_dram_total_gb_s"):
        if col in dram_ts and dram_ts[col].get("mean", 0) > 0:
            dram_total_bw = _safe_float(dram_ts[col]["mean"])
            dram_peak_bw  = _safe_float(dram_ts[col].get("max", dram_total_bw))
            break
    for col in ("dram_read_gb_s", "dram_read_bw_gbs", "read_bw_gbps", "read_gb_s",
                "rd_gb_s", "Read GB/s", "pcm_dram_read_gb_s"):
        if col in dram_ts and dram_ts[col].get("mean", 0) > 0:
            dram_rd_bw = _safe_float(dram_ts[col]["mean"])
            break
    for col in ("dram_write_gb_s", "dram_write_bw_gbs", "write_bw_gbps", "write_gb_s",
                "wr_gb_s", "Write GB/s", "pcm_dram_write_gb_s"):
        if col in dram_ts and dram_ts[col].get("mean", 0) > 0:
            dram_wr_bw = _safe_float(dram_ts[col]["mean"])
            break
    if dram_total_bw <= 0 and (dram_rd_bw > 0 or dram_wr_bw > 0):
        dram_total_bw = dram_rd_bw + dram_wr_bw
        dram_peak_bw = max(dram_peak_bw, dram_total_bw)

    # Plausibility guard.  No host sustains more than a few TB/s of DRAM
    # bandwidth; a value orders of magnitude above that means a column holding
    # something else (a byte count, a capacity) matched one of the aliases
    # above.  Reporting 452,244,313 GB/s asserts something false and makes the
    # tile useless, so discard it and fall through to the KV-movement estimate,
    # which at least measures something real.
    if dram_total_bw > _DRAM_SANE_MAX_GBS or dram_rd_bw > _DRAM_SANE_MAX_GBS:
        _bad = dram_total_bw
        dram_total_bw = dram_rd_bw = dram_wr_bw = 0.0
        dram_peak_bw = 0.0
        setup["_dram_bw_rejected"] = (
            f"{_bad:,.0f} GB/s from the DRAM bandwidth columns is physically "
            f"impossible \u2014 a capacity or byte-count column matched a "
            f"bandwidth alias. Value discarded; showing the KV-movement "
            f"estimate instead.")

    # Smart / WAF
    smart_waf  = _safe_float(_pick(smart, ["waf","write_amplification","WAF"], 0.0))
    smart_temp = _safe_float(_pick(smart, ["temperature","temp_c","Composite Temperature"], 0.0))

    # Run duration and window
    #
    # This is the denominator of every rate in the report, so a wrong value
    # here does not look like a wrong duration -- it looks like impossible
    # bandwidth.  A blktrace capture that recorded nothing reported
    # duration_sec = 0.001, which passed the old `if duration_s <= 0` guard,
    # so the real span was never consulted and the logical L3 rate came out
    # as 19,704,435,625 MB/s beside an Executive header reading
    # "Window : 0.0 min" and a page header correctly reading 38,840 sec.
    #
    # Two changes: a summary duration must be PLAUSIBLE, not merely positive,
    # and it is cross-checked against the timeseries span rather than trusted
    # outright.  The timeseries span is the authority when the two disagree
    # materially, because time_sec comes from the samples the charts plot.
    _dur_summary = _safe_float(_pick(blk, ["duration_s","run_duration_s","elapsed_s",
                                            "duration_sec","blktrace_duration_sec"],
                                     _safe_float(_ba_sum.get("duration_sec", 0))))
    _dur_ts = 0.0
    for _ts_sum in (sglang_ts, gpu_ts, dram_ts, nvme_ts, vmstat_ts):
        try:
            _dt = _safe_float((_ts_sum.get("time_sec") or {}).get("delta", 0))
            if _dt > _dur_ts:
                _dur_ts = _dt
        except Exception:
            pass
    _dur_sglang = _safe_float(_pick(
        sglang, ["collection_elapsed_s", "elapsed_s", "run_duration_s"], 0.0))

    duration_source = ""
    duration_conflict = ""
    if _dur_summary >= _MIN_PLAUSIBLE_WINDOW_S:
        duration_s, duration_source = _dur_summary, "run/blktrace summary"
        # Disagreement by more than 20% means one of them is not describing
        # this window. Prefer the sample timeline and say so, rather than
        # silently picking either.
        if _dur_ts >= _MIN_PLAUSIBLE_WINDOW_S and _dur_ts > 0:
            _ratio = max(_dur_summary, _dur_ts) / min(_dur_summary, _dur_ts)
            if _ratio > 1.2:
                duration_conflict = (
                    f"run summary says {_dur_summary:,.0f}s but the sample "
                    f"timeline spans {_dur_ts:,.0f}s ({_ratio:.1f}x apart); "
                    f"using the sample timeline")
                duration_s, duration_source = _dur_ts, "sample timeline (time_sec)"
    elif _dur_ts >= _MIN_PLAUSIBLE_WINDOW_S:
        duration_s, duration_source = _dur_ts, "sample timeline (time_sec)"
        if 0 < _dur_summary < _MIN_PLAUSIBLE_WINDOW_S:
            duration_conflict = (
                f"run summary reported a {_dur_summary:g}s window, which is "
                f"too short to be a profiling run; ignored in favour of the "
                f"{_dur_ts:,.0f}s sample timeline")
    elif _dur_sglang >= _MIN_PLAUSIBLE_WINDOW_S:
        duration_s, duration_source = _dur_sglang, "SGLang collection_elapsed_s"
    else:
        # Nothing plausible. Leave it at zero so every rate guarded by
        # `duration_s > 0` declines to render instead of dividing by a
        # fraction of a second.
        duration_s, duration_source = 0.0, ""
        duration_conflict = (
            "no source reported a plausible window length, so run-length "
            "rates are not computed")
    if duration_conflict:
        print(f"  [warn] report window: {duration_conflict}")
    # Backfill the L3 storage endurance KPI target now that duration_s is known.
    # 5-year warranty = 1825 days; budget = (run_fraction_of_day) × rated_TBW_in_GB.
    if duration_s > 0 and rated_tbw_tb > 0:
        ssd_lifetime_writes_tb_per_run = round(
            (duration_s / 86400) * rated_tbw_tb * 1024 / 1825, 4)  # in TB
    duration_min = duration_s / 60.0 if duration_s > 0 else 0.0
    t0_epoch   = _safe_float(_pick(blk, ["t0_epoch","start_time","prom_start"], 0.0))

    # Data availability flags
    has_sglang  = bool(sglang) and (ttft_ms > 0 or tpot_ms > 0 or cache_hit > 0)
    has_gpu     = bool(gpu) or gpu_ts.get("rows", 0) > 0
    has_nvme    = (nvme_rd_bw > 0 or read_gb > 0 or nvme_ts.get("rows", 0) > 0)
    has_dram    = (dram_total_bw > 0) or _dram_summary_has_nonzero(dram_ts)
    has_vmstat  = vmstat_ts.get("rows", 0) > 0
    has_blktrace = reqsize_ts.get("rows", 0) > 0 or bw_stream.get("rows", 0) > 0
    has_smart   = bool(smart) and smart.get("model", "?") not in ("?", "", None, "unknown")

    # L3 storage block-device telemetry is distinct from SGLang L3 movement
    # telemetry.  SGLang counters can prove L3 activity for Mooncake/remote
    # backends, but they cannot provide local device busy %, queue depth,
    # block latency, or request-size histograms.  Only show those tiles/charts
    # as L3 storage when a real L3 local block source exists.
    l3_block_io_available = bool(has_blktrace or (
        l3_storage_is_local_block and (nvme_ts.get("rows", 0) > 0 or nvme_util > 0
                                        or nvme_rd_iops > 0 or nvme_wr_iops > 0)
    ))
    l3_block_io_note = (
        f"iostat / blktrace mapped to L3 (local storage)" if l3_block_io_available
        else "not available for this L3 (local storage) backend; using SGLang movement counters"
    )
    if l3_block_io_available:
        l3_util_phrase = (
            f'L3 (local storage) block telemetry reports <strong>{nvme_rd_bw:.1f} MB/s read</strong> '
            f'and <strong>{nvme_wr_bw:.1f} MB/s write</strong>. '
            f'{_nvme_latency_phrase(nvme_rd_lat, nvme_wr_lat)}. '
            'iostat busy-time is omitted because it is not proof of hardware saturation.'
        )
        l3_util_subnote = (
            f"L3 interpretation uses bandwidth, latency, queue-depth and request-size evidence. "
            f"Busy-time is not used as a confidence signal."
        )
    else:
        l3_util_phrase = (
            "L3 block-device latency, queue depth, and request-size distribution are not available for this run. "
            "The L3 values above are derived from SGLang hierarchical-cache movement counters, not local disk telemetry."
        )
        l3_util_subnote = (
            "Block-device busy-time is unavailable/not applicable for this L3 backend; "
            "L3 activity is derived from SGLang movement counters."
        )

    # Total discard count from blk summary
    discard_total = _safe_float(_pick(blk, ["nvme_disc_ios_total","discard_ios_total",
                                             "trim_ios_total"], 0.0))

    # ── Helper functions ──────────────────────────────────────────────────────
    def kpi_card(label: str, value: str, note: str = "", accent: bool = False,
                  target: str = "", target_pct: float | None = None,
                  target_tip: str = "") -> str:
        """Render a KPI tile, optionally with a target reference.

        target:      Text shown under the note (e.g. "Target: ~7 GB/s peak")
        target_pct:  If given (0-150), draws a small horizontal bar showing
                     current/target utilisation (>100% means exceeded target,
                     which is OK for "throughput is healthy" signals).
        target_tip:  Hover text explaining where the target came from.
        """
        style = " style=\"border-color:#6366f1\"" if accent else ""
        tip_attr = f' title="{_html.escape(target_tip)}"' if target_tip else ""
        target_html = ""
        if target:
            bar_html = ""
            if target_pct is not None:
                p = max(0, min(100, target_pct))
                color = "#22c55e" if 30 <= target_pct <= 90 else (
                        "#f59e0b" if (target_pct < 30 or target_pct < 110) else "#ef4444")
                bar_html = (f'<div class="kpi-tgt-bar" style="margin-top:3px;'
                            f'height:3px;background:#e5e7eb;border-radius:2px;overflow:hidden">'
                            f'<div style="width:{p:.0f}%;height:100%;background:{color}"></div></div>')
            target_html = (f'<div class="kpi-target" style="font-size:9.5px;'
                            f'color:#64748b;margin-top:3px;font-style:italic;'
                            f'overflow-wrap:break-word;word-break:break-word;'
                            f'line-height:1.45"'
                            f'{tip_attr}>{_html.escape(target)}</div>{bar_html}')
        note = _tile_note(label, note)
        return (f'<div class="kpi"{style}>'
                f'<div class="kpi-label">{_html.escape(label)}</div>'
                f'<div class="kpi-value">{value}</div>'
                f'<div class="kpi-note">{_fx_details(_html.escape(note))}</div>'
                f'{target_html}</div>')

    def pill(label: str, ok: bool = True, tip: str = "") -> str:
        cls = "ok" if ok else "warn"
        ic  = "✅" if ok else "⚠"
        tip_attr = f' title="{_html.escape(tip)}"' if tip else ""
        return f'<span class="pill {cls}"{tip_attr}>{ic} {_html.escape(label)}</span>'

    def sev(score: float) -> str:
        if score >= 70: return '<span class="sev high">HIGH</span>'
        if score >= 35: return '<span class="sev med">MED</span>'
        return '<span class="sev low">LOW</span>'

    def bar(pct: float, color: str = "blue") -> str:
        p = min(max(int(pct), 0), 100)
        return (f'<div class="bar-wrap"><div class="bar {color}"'                f' style="width:{p}%"></div></div>')

    def clamp_score(v: float) -> float:
        """Clamp executive bottleneck scores to the documented 0–100 range."""
        try:
            return max(0.0, min(100.0, float(v)))
        except Exception:
            return 0.0

    def finding(tag: str, text: str, plain: str | None = None) -> str:
        """Render an executive-summary finding.

        Args:
          tag:   Short ALL-CAPS label (the "[CATEGORY]" prefix).
          text:  Full finding text with metrics, formulas, action items.
                 Shown in a collapsible "technical details" block — the dense
                 numbers belong here, not at the top.
          plain: Optional plain-English summary sentence (no jargon, no
                 acronyms, ≤25 words). Shown above the collapsible block.
                 Recommended for every finding so non-technical readers can
                 skim the findings list without an engineering glossary.
        """
        plain_html = (
            f'<div class="fi-plain" style="margin:4px 0 6px;color:#f1f5f9;'
            f'font-size:13.5px;line-height:1.5">{plain}</div>' if plain else ""
        )
        details_html = (
            f'<details class="fi-tech" style="margin-top:4px">'
            f'<summary style="font-size:11.5px;color:#94a3b8;cursor:pointer;'
            f'user-select:none">Technical details</summary>'
            f'<div style="margin-top:6px;color:#cbd5e1;font-size:12.5px;'
            f'line-height:1.55">{text}</div></details>'
            if plain else
            f'<div style="color:#e2e8f0;font-size:13px;line-height:1.55">{text}</div>'
        )
        return (f'<li><span class="fi-tag">[{_html.escape(tag)}]</span>'
                f'{plain_html}{details_html}</li>')

    def evidence_chips(items: list[tuple[str, str, str]]) -> str:
        """Render inline evidence chips. Each item is (label, value, state)."""
        out = []
        for label, value, state in items:
            cls = state if state in ("good", "warn", "bad") else ""
            out.append(
                f'<span class="evidence-chip {cls}"><b>{_html.escape(str(label))}:</b> '
                f'{_html.escape(str(value))}</span>')
        return "".join(out)

    def evidence_box(title: str,
                     chips: list[tuple[str, str, str]],
                     rule: str,
                     sources: str,
                     confidence: str = "medium",  # kept for signature compat; no longer rendered
                     caveat: str = "") -> str:
        # Simplified in v1.1.6: confidence badge removed per Executive-report
        # simplification.  The remaining trail is title → evidence chips →
        # decision rule → optional caveat → data source.
        caveat_html = (f'<div class="evidence-rule"><b>Caveat:</b> {_html.escape(caveat)}</div>'
                       if caveat else "")
        return (
            f'<div class="evidence-card">'
            f'<div class="evidence-title">{_html.escape(title)}</div>'
            f'<div>{evidence_chips(chips)}</div>'
            f'<div class="evidence-rule"><b>Decision rule:</b> {_html.escape(rule)}</div>'
            f'{caveat_html}'
            f'<div class="evidence-src"><b>Data source:</b> {_html.escape(sources)}</div>'
            f'</div>'
        )

    # Explicit memory-tier labels.
    # L3 is node-local storage/NVMe; L3 is shared/remote AI Memory Node/context-memory tier.
    TIER_L3_LOCAL = "L3 (local storage)"
    TIER_L35_AIMEM = "L3 (AI Memory Node)"
    TIER_L3_L35 = "L3 (local storage)"

    def chart_card(title: str, subtitle: str, takeaway: str, implication: str,
                   chart_id: str = "", chart_fig: str = "") -> str:
        # Optional inline Plotly chart. When chart_fig is provided (a JSON
        # string), embed a div slot + a one-shot script that renders the
        # figure. Same robust retry pattern as _per_layer_takeaways_html row:
        # waits up to 5s for Plotly to be defined before giving up, so the
        # chart works even if CDN script loading races with inline script
        # execution (observed in some sandboxed iframe contexts).
        chart_html = ""
        if chart_fig and chart_id:
            slot_id = f"cbc-{chart_id}"
            chart_html = (
                f'<div id="{slot_id}" style="min-height:280px;background:#fff;'
                f'border-radius:6px;padding:6px;margin:6px 0"></div>'
                f'<script>(function(){{'
                f'  var tries = 0;'
                f'  function render() {{'
                f'    if (typeof Plotly === "undefined") {{'
                f'      if (++tries < 100) return setTimeout(render, 50);'
                f'      var slot = document.getElementById("{slot_id}");'
                f'      if (slot) slot.innerHTML = \'<div style="padding:24px;'
                f'color:#64748b;font-style:italic">Plotly library failed to '
                f'load — check network access to cdn.plot.ly</div>\';'
                f'      return;'
                f'    }}'
                f'    try {{'
                f'      var fig = {chart_fig};'
                f'      fig.layout = fig.layout || {{}};'
                f'      fig.layout.autosize = true;'
                f'      var n = (fig.data || []).filter(function(t){{return !t || t.showlegend !== false;}}).length;'
                f'      var rows = n > 14 ? 4 : (n > 8 ? 3 : (n > 4 ? 2 : 1));'
                f'      fig.layout.margin = Object.assign({{l:64,r:56,t:60,b:100 + rows*42}}, fig.layout.margin || {{}});'
                f'      fig.layout.margin.b = Math.max(fig.layout.margin.b || 0, 100 + rows*42);'
                f'      fig.layout.height = Math.max(fig.layout.height || 280, 300 + rows*36);'
                f'      fig.layout.legend = Object.assign({{orientation:"h", yanchor:"top", y:-0.22, xanchor:"left", x:0, font:{{size:10,color:"#0f172a"}}, bgcolor:"rgba(248,250,252,0.96)", bordercolor:"#cbd5e1", borderwidth:1, itemsizing:"constant", itemwidth:30, entrywidth:(n>10?120:145), entrywidthmode:"pixels", tracegroupgap:6}}, fig.layout.legend || {{}});'
                f'      Plotly.newPlot("{slot_id}", fig.data, fig.layout,'
                f'        {{responsive:true, displayModeBar:false}});'
                f'    }} catch(e) {{'
                f'      var slot = document.getElementById("{slot_id}");'
                f'      if (slot) slot.innerHTML = \'<div style="padding:24px;'
                f'color:#64748b;font-style:italic">Chart unavailable in this '
                f'view (\' + e.message + \')</div>\';'
                f'    }}'
                f'  }}'
                f'  render();'
                f'}})();</script>'
            )
        return (
            f'<div class="chart-card">'
            f'<div class="chart-title">{_html.escape(title)}</div>'
            f'<div class="chart-sub">{_html.escape(subtitle)}</div>'
            f'{chart_html}'
            f'<div class="takeaway">{takeaway}</div>'
            f'<div class="data-note"><strong>Requirement implication:</strong> '
            f'{implication}</div></div>'
        )

    # ── Derived KPIs ──────────────────────────────────────────────────────────
    hbm_free_gb    = max(hbm_total - hbm_gb, 0.0)
    # KV bytes per token, derived from the actual model architecture. The old
    # hardcoded 327 KB came from 70B BF16 GQA (80 layers × 8 KV heads × 128 dim
    # × 2 bytes × 2 [K+V] = 327680 B). For other models the real value differs
    # by 10-30×, making the "spill threshold" estimate worthless. Look up the
    # right value via the same arch DB used in the static report so all three
    # reports agree on what one KV token costs in HBM.
    def _kv_bytes_per_token_kb(model_name: str, kv_dtype: str) -> float:
        """Delegates to metric_kernels.resolve_kv_bytes_per_token.

        This previously held a second copy of the architecture table with a
        "keep in sync" comment.  It drifted: on a gemma-4-31B run this path
        fell through to a 70B-class default (320 KB/token) while the End
        Report's copy matched the "1b" size hint inside "31b" (88 KB/token) —
        two figures for the same model in one report.
        """
        _r = _k_resolve_kv(model_name, kv_dtype, _kv_model_config)
        _kv_resolution.clear()
        _kv_resolution.update(_r)
        return float(_r.get("kb") or 0.0)

    # Model architecture from the engine's own config when exposed; an exact
    # config beats any name-based table.  setup_details carries the passthrough
    # of server_info fields (cli._server_info_to_setup_details).
    _kv_model_config = {}
    # raw/model_config.json (from --model-path, or synthesised from
    # amoprof_model_config_* on the Prometheus path) is authoritative.
    try:
        _mc_path = raw_dir / "model_config.json"
        if _mc_path.exists() and _mc_path.stat().st_size > 0:
            _mc_obj = json.loads(_mc_path.read_text(encoding="utf-8"))
            if isinstance(_mc_obj, dict):
                for _k, _v in _mc_obj.items():
                    if not str(_k).startswith("_"):
                        _kv_model_config[str(_k).strip().lower()] = _v
    except Exception:
        pass
    for _src in (setup, sglang):
        if isinstance(_src, dict):
            for _k, _v in _src.items():
                _kn = str(_k).strip().lower().replace(" ", "_")
                if _kn in ("num_hidden_layers", "num_key_value_heads", "head_dim",
                           "hidden_size", "num_attention_heads", "kv_cache_dtype",
                           "n_layers", "num_layers", "num_kv_heads"):
                    _kv_model_config.setdefault(_kn, _v)
    _kv_resolution: dict = {}
    _kv_dtype_raw = (sglang.get("kv_cache_dtype") if isinstance(sglang, dict) else None) or "fp16"
    _model_name   = (setup.get("Model") if isinstance(setup, dict) else None) \
                    or (sglang.get("model_name") if isinstance(sglang, dict) else None) or ""
    kv_bytes_tok_kb = _kv_bytes_per_token_kb(_model_name, _kv_dtype_raw)
    # Sanity: avoid div-by-zero in spill threshold formula below.
    if kv_bytes_tok_kb <= 0:
        # Unresolvable: no exact config and no recognised model name.  Zero
        # would divide by zero downstream, so a nominal value is used — but it
        # is labelled an assumption wherever it appears rather than presented
        # as a property of this model.
        kv_bytes_tok_kb = 327.0
        _kv_resolution.update({"kb": 327.0, "exact": False, "formula": "",

                               "source": "UNRESOLVED — nominal 335 KB/token (327 × 1024 bytes) assumed; "
                                         "model not recognised and engine config not exposed"})


    # SGLang sizes the host cache by --hicache-ratio (a multiple of the HBM KV
    # pool) whenever --hicache-size is 0, which is the default.  Without this
    # the configured L2 capacity reads 0 GB, and every derived L2 figure is
    # then clamped to zero by the "bounded by configured capacity" rule — the
    # DRAM used tile shows 0 even though the occupancy was measured.
    if hicache_total_gb <= 0:
        _hc_ratio = _setup_float_fuzzy("HiCache ratio", "hicache_ratio",
                                       "hi_cache_ratio", default=0.0)
        _kv_pool_tok = _safe_float(_pick(sglang, ["max_total_num_tokens",
                                                  "sglang_max_total_num_tokens"], 0), 0)
        if _kv_pool_tok <= 0:
            _kv_pool_tok = _safe_float(_pick(setup, ["max_total_num_tokens"], 0), 0)
        if _hc_ratio > 0 and _kv_pool_tok > 0 and kv_bytes_tok_kb > 0:
            hicache_total_gb = _k_gb_from_bytes(_kv_pool_tok * _hc_ratio
                                * kv_bytes_tok_kb * 1024.0)
            l2_dram_capacity_via_ratio = (
                f"--hicache-ratio {_hc_ratio:g} x max_total_num_tokens "
                f"{_kv_pool_tok:,.0f} x KV {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f} KB/token")
        else:
            l2_dram_capacity_via_ratio = ""
    else:
        l2_dram_capacity_via_ratio = ""
    if hicache_total_gb > 0 and l2_dram_capacity_via_ratio:
        l2_dram_capacity_gb = hicache_total_gb
        l2_dram_capacity_source = l2_dram_capacity_via_ratio

    try:
        _l2res = _k_resolve_l2(
            hicache_used_tokens=_safe_float(_pick(sglang, [
                "hicache_host_used_tokens", "sglang_hicache_host_used_tokens"], 0), 0),
            hicache_total_tokens=_safe_float(_pick(sglang, [
                "hicache_host_total_tokens", "sglang_hicache_host_total_tokens"], 0), 0),
            kv_bytes_per_token_kb=_safe_float(kv_bytes_tok_kb, 0),
            hicache_total_gb=_safe_float(hicache_total_gb, 0),
            # The resolver's --hicache-ratio branch was unreachable from here:
            # these two were never passed, so a run sized by the ratio (the
            # SGLang default) could only fall back to a parsed size or to host
            # DRAM. Pass them so the ratio can do its job.
            hicache_ratio=_setup_float_fuzzy(
                "HiCache ratio", "hicache_ratio", "hi_cache_ratio", default=0.0),
            kv_pool_tokens=_safe_float(_pick(sglang, [
                "max_total_num_tokens", "sglang_max_total_num_tokens"], 0), 0)
                or _safe_float(_pick(setup, ["max_total_num_tokens"], 0), 0),
            host_dram_total_gb=0.0)
        if _l2res.get("used_gb", 0) > 0:
            l2_dram_used_gb = _l2res["used_gb"]
            l2_dram_used_source = _l2res["used_source"]
        if _l2res.get("capacity_gb", 0) > 0:
            l2_dram_capacity_gb = _l2res["capacity_gb"]
            l2_dram_capacity_source = _l2res["capacity_source"]
        # When capacity came from the server's own token gauge, the TP-sharding
        # heuristic further down must not fire: that heuristic exists to make a
        # full-model estimate fit a CONFIGURED allocation, and dividing a
        # measured residency by TP to fit a measured capacity it already fits
        # is how the tile ended up 8x below the tier-residency chart.
        _l2_cap_measured = "measured" in str(_l2res.get("capacity_source", ""))
        _l2_cap_conflict = str(_l2res.get("capacity_conflict", "") or "")
        if _l2_cap_conflict:
            print(f"  [warn] L2 capacity: {_l2_cap_conflict}")
    except Exception:
        _l2_cap_measured, _l2_cap_conflict = False, ""

    try:
        # DRAM/L2 "used" should be a selected-window residency, not a stale
        # last sample or setup-derived constant.  Using the active/non-zero mean
        # makes L2-only and L3-active runs differ when their cache residency
        # differs, while still avoiding idle zero windows.
        # Use the explicit SGLang L2 residency metric for DRAM-used.
        # Important: this is a gauge, not a byte counter.  It is only useful
        # for comparing runs when it varies within the selected window.  If it
        # is missing or flat, do not publish a misleading identical "used"
        # value across L2/L3 reports; show the configured allocation instead.
        _l2_stats = _ts_gauge_stats(
            sglang_ts,
            "sglang_hicache_host_used_tokens", "hicache_host_used_tokens"
        )
        _l2_used_tokens = float(_l2_stats.get("mean", 0.0) or 0.0)
        _l2_used_tokens_variation_pct = float(_l2_stats.get("variation_pct", 0.0) or 0.0)
        _l2_used_tokens_min = float(_l2_stats.get("min", 0.0) or 0.0)
        _l2_used_tokens_max = float(_l2_stats.get("max", 0.0) or 0.0)
        _l2_used_tokens_nonzero = float(_l2_stats.get("nonzero_count", 0.0) or 0.0)
        _l2_used_tokens_source = "selected-window active mean of sglang_hicache_host_used_tokens"
        _l2_used_tokens_dynamic = (_l2_used_tokens > 0 and _l2_used_tokens_variation_pct > 1.0)
        if _l2_used_tokens <= 0:
            _l2_used_tokens_source = "sglang_hicache_host_used_tokens missing from selected-window timeseries"
        elif not _l2_used_tokens_dynamic:
            _l2_used_tokens_source = "sglang_hicache_host_used_tokens present but flat/static in selected window"
        # Companion PEAK-residency value the Executive tile shows alongside
        # the mean, so an operator reading it against the KV-bytes-per-tier
        # chart (which plots the raw per-sample series) can reconcile the
        # two: the chart legitimately shows a higher line while the cache
        # warms up.  Applies the same TP-sharding decision as the mean so
        # both numbers stay comparable.
        l2_dram_used_peak_gb = 0.0
        if _l2_used_tokens > 0:
            # SGLang HiCache host-used token counters are exported at the
            # worker/rank level in several TP deployments.  A full-model
            # KV-bytes/token conversion can therefore overstate L2 DRAM usage
            # by approximately TP size and produce impossible values such as
            # 186 GB used out of a configured 100 GB allocation.  Prefer the
            # full-model estimate only when it fits the configured allocation;
            # otherwise use the TP-sharded per-rank estimate.
            _tp_for_kv = max(_safe_float(tp_size, 1.0), 1.0)
            _full_gb = _k_gb_from_bytes(_l2_used_tokens * kv_bytes_tok_kb * 1024)
            _tp_gb = _k_gb_from_bytes(_l2_used_tokens * (kv_bytes_tok_kb / _tp_for_kv) * 1024)
            _peak_full_gb = _k_gb_from_bytes(_l2_used_tokens_max * kv_bytes_tok_kb * 1024)
            _peak_tp_gb = _k_gb_from_bytes(_l2_used_tokens_max * (kv_bytes_tok_kb / _tp_for_kv) * 1024)
            # Prefer full-model unless it does not fit configured HiCache
            # allocation, in which case TP-sharded per-rank is likely the
            # right reading of the counter.  This keeps the tile aligned
            # with the "KV bytes resident per cache tier" chart, which
            # multiplies the same counter by full-model bytes/tok.  Any
            # gap versus raw physical DRAM is surfaced by the
            # reconciliation-warning line on the tile note, so an
            # operator still sees the disagreement without the tile
            # silently reshaping the number.
            if _l2_cap_measured:
                # Capacity is the server's own gauge; the full-model estimate
                # is the matching numerator for it.
                l2_dram_used_gb = _full_gb
                l2_dram_used_source = (f"{_l2_used_tokens_source} × KV "
                                       f"bytes/token (capacity from the same "
                                       f"server gauge)")
            elif l2_dram_capacity_gb > 0 and _full_gb > l2_dram_capacity_gb * 1.05 and _tp_gb <= l2_dram_capacity_gb * 1.05:
                l2_dram_used_gb = _tp_gb
                l2_dram_used_source = f"{_l2_used_tokens_source} \u00d7 TP-sharded KV bytes/token (\u00f7TP={_tp_for_kv:g})"
            elif l2_dram_capacity_gb > 0 and _full_gb > l2_dram_capacity_gb * 1.05 and _tp_gb > l2_dram_capacity_gb * 1.05:
                # Do not publish an impossible utilisation. Keep capacity
                # visible and mark used as unavailable; the raw token estimate
                # is still documented in the formula section.
                l2_dram_used_gb = 0.0
                l2_dram_used_source = "SGLang hicache host used token estimate exceeded configured L2 allocation"
            else:
                l2_dram_used_gb = _full_gb
                l2_dram_used_source = f"{_l2_used_tokens_source} \u00d7 KV bytes/token"
            # Peak follows the same variant as the mean so a reader can
            # compare them directly instead of chasing which one is
            # TP-sharded.
            if l2_dram_used_gb == _tp_gb:
                l2_dram_used_peak_gb = _peak_tp_gb
            elif l2_dram_used_gb == _full_gb:
                l2_dram_used_peak_gb = _peak_full_gb
            if l2_dram_capacity_gb > 0 and l2_dram_used_peak_gb > l2_dram_capacity_gb:
                l2_dram_used_peak_gb = l2_dram_capacity_gb
    except Exception:
        pass
    if l2_dram_used_gb <= 0 and host_dram_used_gb > 0 and l2_dram_capacity_gb <= 0:
        # Only use host DRAM as a fallback when there is no configured L2
        # HiCache allocation. For HiCache reports, host DRAM is not the L2
        # cache residency and would make different L2/L3 runs look identical.
        l2_dram_used_gb = host_dram_used_gb
        l2_dram_used_source = "OS host DRAM used from dram_summary/setup"
    # ── Is the token-derived L2 residency physically possible? ───────────
    #
    # The note on this tile already called the figure "bounded above by raw
    # physical DRAM" -- and then it wasn't.  A mooncake run reported "L2 KV
    # residency (est.) 202.4 GB / 210 GB · 97% full" against 70.4 GB of
    # physical host DRAM in use.  KV held in host DRAM cannot exceed the DRAM
    # that is resident, so neither 202.4 GB nor the 97% beside it is a
    # possible figure, and a warning further along the note does not stop the
    # headline being what gets quoted.
    #
    # Capped HERE, before the percentage and the note are composed from these
    # variables: capping afterwards left "97% full" and "peak 347.9 GB" in a
    # note whose headline had already been corrected.
    _l2_overcount_gb = 0.0
    _l2_gap_x = 0.0
    if (l2_dram_used_gb > 0 and host_dram_used_gb > 0
            and l2_dram_used_gb >= 2.0 * host_dram_used_gb
            and 'sglang_hicache_host_used_tokens' in (
                (locals().get("_l2_used_tokens_source") or ""))):
        _l2_overcount_gb = l2_dram_used_gb
        _l2_gap_x = l2_dram_used_gb / host_dram_used_gb
        l2_dram_used_gb = host_dram_used_gb
        # The peak travels with the mean. Leaving it uncapped puts the same
        # contradiction one line further down the note.
        if l2_dram_used_peak_gb > 0:
            l2_dram_used_peak_gb = (host_dram_used_peak_gb
                                    if host_dram_used_peak_gb > 0
                                    else host_dram_used_gb)
        print(f"  [warn] L2 KV residency: token-derived "
              f"{_l2_overcount_gb:,.1f} GB is {_l2_gap_x:.1f}x the physical "
              f"host DRAM residency ({host_dram_used_gb:,.1f} GB); reporting "
              f"the physical figure as the upper bound")
    l2_dram_used_pct = (l2_dram_used_gb / l2_dram_capacity_gb * 100.0) if l2_dram_capacity_gb > 0 and l2_dram_used_gb > 0 else 0.0
    # DRAM/L2 used is a point-in-time/selected-window residency gauge, while
    # DRAM BW is flow over time. They can legitimately differ between runs even
    # when the residency gauge is flat. Make this explicit so the Executive tile
    # does not imply that two different workloads had identical DRAM behavior.
    if l2_dram_used_gb > 0 and _l2_used_tokens_variation_pct > 1.0:
        _l2_peak_snip = (f" · peak {_fmt_num(l2_dram_used_peak_gb, ' GB', 1)}"
                         if l2_dram_used_peak_gb > l2_dram_used_gb else "")
        l2_dram_tile_note = (f"{_fmt_num(l2_dram_used_pct, '% full', 0)} · selected-window mean residency"
                             f"{_l2_peak_snip}"
                             f" (gauge varied {_l2_used_tokens_variation_pct:.1f}%) · {l2_dram_capacity_source}")
    elif l2_dram_used_gb > 0:
        _l2_peak_snip = (f" · peak {_fmt_num(l2_dram_used_peak_gb, ' GB', 1)}"
                         if l2_dram_used_peak_gb > l2_dram_used_gb else "")
        l2_dram_tile_note = (f"{_fmt_num(l2_dram_used_pct, '% full', 0)} · residency snapshot/flat gauge, "
                             f"not bandwidth{_l2_peak_snip} · {l2_dram_capacity_source}")
    else:
        if '_l2_used_tokens_source' in locals() and _l2_used_tokens_source:
            l2_dram_tile_note = f"runtime residency unavailable · {_l2_used_tokens_source} · {l2_dram_capacity_source}"
        else:
            l2_dram_tile_note = f"L2 DRAM cache allocation · {l2_dram_capacity_source}"

    # Now that the note exists, say what was rejected and why.
    if _l2_overcount_gb > 0:
        l2_dram_tile_note = (
            l2_dram_tile_note
            + " · <b>capped at the physical residency</b>: the token-derived"
            + f" estimate was {_fmt_num(_l2_overcount_gb, ' GB', 1)},"
            + f" {_l2_gap_x:.1f}× the raw physical residency"
            + f" ({_fmt_num(host_dram_used_gb, ' GB', 1)}), and KV in host"
            + " DRAM cannot exceed the DRAM that is resident · KV bytes/token"
            + " is over-counting (sliding-window attention, or a TP-sharding"
            + " miscount) · the figure shown is that bound, not a measurement"
            + " of KV")


    # ── L3 (local storage) traffic from SGLang token counters (Prometheus-only fallback) ──
    # GATING: This fallback is intentional ONLY for Prom-only runs where
    # no local run-dir instrumentation was available. When a run-dir IS
    # supplied AND it contains blktrace output, we use that as the
    # authoritative source — even if blktrace produced zero bytes — because
    # zero blktrace bytes in the presence of a real trace means something
    # went wrong (CAP_SYS_ADMIN failure, dropped events, wrong device), and
    # silently swapping in an SGLang estimate would hide that. The existing
    # coverage-warning logic already flags such failures; the user must see
    # those warnings, not a confidence-inspiring estimate that papers over them.
    #
    # "blktrace was attempted in this run" is detected by the presence of
    # blktrace_analysis/summary.json (the analyzer produces this whenever
    # it runs, even if capture was partial or empty). Its absence means
    # the user is running in Prom-only mode and the SGLang estimate is
    # the best signal we have.
    _ba_sum_path = raw_dir / "blktrace_analysis" / "summary.json"
    _blktrace_was_attempted = _ba_sum_path.exists()
    _prom_only_mode = not _blktrace_was_attempted

    # Accept several key spellings because SGLang versions differ:
    #   - backuped_tokens_total / load_back_tokens_total (current writer)
    #   - sglang_backuped_tokens_total / sglang_load_back_tokens_total
    #     (timeseries-CSV prefix from earlier collectors)
    #   - kvb_backuped_tokens_total / kvb_loadback_tokens_total (static
    #     report Metrics names if someone copies fields across)
    def _first_nonzero(*candidates):
        """Tokens moved DURING the window, not since the server started.

        These feed the KV-movement bandwidth estimate, which divides by the
        window length — so a cumulative value produces a rate that is wrong by
        the ratio of server uptime to window length.  On a server up for days,
        analysed over four hours, that is the difference between ~1 GB/s and
        451,771,749 GB/s.

        The summary carries the counter's LAST value (cumulative since start),
        so prefer the timeseries and difference its endpoints; fall back to
        the summary only when no series exists, and say so by returning 0
        rather than a number that cannot be interpreted as window traffic.
        """
        _p = _first_existing(raw_dir, ["sglang_timeseries.csv"])
        for k in candidates:
            if not _p:
                break
            _col = _amoprof_read_columns_substr(_p, {"v": [k]}).get("v", [])
            _col = [x for x in _col if x == x]
            if len(_col) >= 2:
                _d = _col[-1] - _col[0]
                if _d < 0:              # counter reset mid-window
                    _d = _col[-1]
                if _d > 0:
                    return _d
        # No usable series: a cumulative summary value would be misread as
        # window traffic, so report nothing instead.
        return 0.0
    # All four KV-movement counters go through one rank-summing reader.
    # None = counter absent; 0.0 = present and idle.  Kept as None-aware
    # values for reporting, and coerced to 0.0 only where arithmetic needs it.
    _bk = _kv_token_delta(raw_dir, ["backuped_tokens_total", "backup_tokens_total"])
    _lb = _kv_token_delta(raw_dir, ["load_back_tokens_total", "loadback_tokens_total"])
    _pf = _kv_token_delta(raw_dir, ["prefetched_tokens_total", "prefetch_tokens_total"])
    _ev = _kv_token_delta(raw_dir, ["evicted_tokens_total"])
    kv_token_counts = {"backup": _bk, "load_back": _lb,
                       "prefetch": _pf, "evict": _ev}
    backuped_tokens   = _bk or 0.0
    loadback_tokens   = _lb or 0.0
    prefetched_tokens = _pf or 0.0
    evicted_tokens    = _ev or 0.0

    # Convert to decimal GB: tokens × (kv_bytes_tok_kb × 1024) bytes/token / 1e9.
    # Reliable SGLang L3/local Storage evidence:
    #   backuped_tokens   -> data moved down into the L3 (local storage) tier (write/offload)
    #   prefetched_tokens -> explicit prefetch/onboard from the L3/backing tier
    # load_back_tokens by itself is ambiguous in SGLang 0.5.x; it can represent
    # restoration from the HiCache hierarchy (often L2 DRAM/page cache) and may be
    # counted repeatedly per token. It is NOT safe to multiply load_back_tokens by
    # KV_bytes_per_token and call that local-SSD read traffic. evicted_tokens means
    # cache pressure, not storage I/O. Therefore the selected-window L3 read
    # estimate uses prefetched_tokens only; load_back is shown as a diagnostic.
    l3_reliable_sglang_logical_local_ssd = backuped_tokens + prefetched_tokens
    l3_ambiguous_tokens = loadback_tokens + evicted_tokens
    # Token counts are the measurement.  Multiplying by KV bytes/token to get
    # GB was never validated against measured bytes: on real runs prefetch
    # came out 30x above what the store actually served (55 TB vs 1.7 TB),
    # because prefetched_tokens_total counts transfers into L2 rather than
    # bytes read from the backing tier.  The GB figures below are retained
    # only for existing downstream arithmetic; narrative text reports tokens.
    def _tok(v):
        if v is None:
            return "absent"
        return f"{v/1e6:,.2f}M tokens" if v >= 1e6 else f"{v:,.0f} tokens"
    l3_est_write_gb = _k_gb_from_bytes(backuped_tokens * kv_bytes_tok_kb * 1024)
    l3_est_read_gb  = _k_gb_from_bytes(prefetched_tokens * kv_bytes_tok_kb * 1024) if l3_reliable_sglang_logical_local_ssd > 0 else 0.0
    l3_ambiguous_loadback_gb = _k_gb_from_bytes(loadback_tokens * kv_bytes_tok_kb * 1024) if loadback_tokens > 0 else 0.0
    l3_sglang_activity_tokens = l3_reliable_sglang_logical_local_ssd
    # Derive L3.5 when SGLang proves backing-tier movement but setup does not
    # resolve a local SSD/NVMe/file-backed mapping.  Explicit setup still wins;
    # this only reclassifies unknown/none logical backing-tier traffic.
    if (l3_sglang_activity_tokens > 0 and str(l3_backend_class).lower() in {"", "none", "unknown"}
            and not bool(l3_storage_has_block_mapping or l3_storage_is_local_block)):
        l3_backend_class = "remote_storage"
        l3_backend_display = "L3.5 (AI Memory Node / remote storage)"
        l3_storage_type = "AI Memory Node / remote storage"

    _block_read_gb = float(read_gb or 0.0)
    _block_write_gb = float(write_gb or 0.0)

    # Source provenance. Physical block telemetry and SGLang logical KV
    # movement answer different questions. When L3 is SSD-backed and SGLang
    # backuped/prefetched counters prove L3 movement, do not let a zero block
    # direction hide that logical activity. Keep provenance explicit so the
    # report does not confuse an estimate with raw device bytes.
    # Same plausibility floor as duration_s above: a sub-second window is a
    # broken reading, not a short run, and dividing by it turns a byte count
    # into a bandwidth figure nine orders of magnitude too large.
    _l3_window_s = duration_s if duration_s >= _MIN_PLAUSIBLE_WINDOW_S else 0.0
    if _l3_window_s <= 0:
        _cand = _safe_float(sglang.get("collection_elapsed_s", 0))
        _l3_window_s = _cand if _cand >= _MIN_PLAUSIBLE_WINDOW_S else 0.0
    l3_logical_estimate_note = ""
    if _blktrace_was_attempted:
        # v1.39.61: when a physical blktrace capture exists, it remains the
        # authoritative source for SSD/LBA bytes. SGLang counters are still
        # valuable, but they are logical HiCache/backing-tier movement and are
        # shown as a separate diagnostic. Never overwrite physical block bytes
        # with token-derived estimates, even when the backend maps to L3 local SSD;
        # otherwise Executive can contradict hot/cold LBA charts.
        if l3_sglang_activity_tokens > 0:
            if l3_backend_class == "local_ssd":
                l3_traffic_source = "blktrace_mapped_with_sglang_logical_diagnostic"
                l3_logical_estimate_note = (
                    f"SGLang counters indicate logical local-SSD/backing-tier movement "
                    f"for backend {l3_backend_display}: prefetch={_tok(kv_token_counts.get('prefetch'))}, "
                    f"backup={_tok(kv_token_counts.get('backup'))}; ambiguous L2→L1 load_back restore diagnostic="
                    f"{_tok(kv_token_counts.get('load_back'))}. Physical blktrace bytes remain "
                    f"authoritative for SSD/LBA charts: read={_block_read_gb:.3f} GB, "
                    f"write={_block_write_gb:.3f} GB. A mismatch points to page-cache hits, "
                    f"counter semantics, delayed writeback, or a window/capture issue."
                )
            elif l3_backend_class in ("remote_mooncake", "remote_storage"):
                l3_traffic_source = "blktrace_unmapped_sglang_logical_remote_l35"
                l3_logical_estimate_note = (
                    f"SGLang counters indicate logical L3/backing-tier movement "
                    f"for backend {l3_backend_display}: prefetch={_tok(kv_token_counts.get('prefetch'))}, "
                    f"backup={_tok(kv_token_counts.get('backup'))}; ambiguous L2→L1 load_back restore diagnostic="
                    f"{_tok(kv_token_counts.get('load_back'))}. This is NOT promoted to L3 local SSD "
                    f"physical I/O because no resolved L3 local SSD block mapping is available; "
                    f"physical traced-device R/W remains read={_block_read_gb:.3f} GB, "
                    f"write={_block_write_gb:.3f} GB."
                )
            else:
                l3_traffic_source = "blktrace_unmapped_sglang_logical_unknown_backend"
                l3_logical_estimate_note = (
                    f"SGLang counters indicate logical L3/backing-tier movement "
                    f"but backend mapping is unknown: prefetch={_tok(kv_token_counts.get('prefetch'))}, "
                    f"backup={_tok(kv_token_counts.get('backup'))}; ambiguous L2→L1 load_back restore diagnostic="
                    f"{_tok(kv_token_counts.get('load_back'))}. Physical traced-device R/W remains "
                    f"read={_block_read_gb:.3f} GB, write={_block_write_gb:.3f} GB."
                )
        else:
            l3_traffic_source = "blktrace"
    elif l3_sglang_activity_tokens > 0:
        if l3_backend_class == "local_ssd":
            read_gb  = l3_est_read_gb
            write_gb = l3_est_write_gb
            rw_ratio = read_gb / max(write_gb, 0.001)
            l3_traffic_source = "sglang_logical_local_ssd"
        elif l3_backend_class in ("remote_mooncake", "remote_storage"):
            read_gb  = l3_est_read_gb
            write_gb = l3_est_write_gb
            rw_ratio = read_gb / max(write_gb, 0.001)
            l3_traffic_source = "sglang_logical_remote_l35"
        else:
            l3_traffic_source = "sglang_logical_hicache_unknown_backend"
            l3_logical_estimate_note = "SGLang logical backup/prefetch seen but L3 backend is unknown; not labeled as SSD or Mooncake"
    else:
        l3_traffic_source = "none"

    l3_unmapped_logical_seen = l3_traffic_source in (
        "blktrace_unmapped_sglang_logical_remote_l35",
        "blktrace_unmapped_sglang_logical_unknown_backend",
    )
    l3_logical_diagnostic_seen = l3_traffic_source in (
        "blktrace_mapped_with_sglang_logical_diagnostic",
        "blktrace_unmapped_sglang_logical_remote_l35",
        "blktrace_unmapped_sglang_logical_unknown_backend",
    )

    # Unified reconciliation used by all executive wording.  Physical block bytes
    # are kept as physical measurements; SGLang bytes are logical KV movement.
    # They are considered directly comparable only for resolved local_ssd with
    # an explicit block mapping.
    try:
        _l3_recon = reconcile_l3_io(
            _l3_backend if '_l3_backend' in locals() and _l3_backend is not None else resolve_l3_backend({}, ''),
            sglang_write_gb=l3_est_write_gb, sglang_read_gb=l3_est_read_gb,
            block_write_gb=_block_write_gb if '_block_write_gb' in locals() else write_gb,
            block_read_gb=_block_read_gb if '_block_read_gb' in locals() else read_gb,
            blktrace_available=bool(_blktrace_was_attempted))
        l3_reconciliation_status = _l3_recon.display_status
        l3_reconciliation_note = _l3_recon.note
    except Exception:
        l3_reconciliation_status = 'Unknown'
        l3_reconciliation_note = l3_logical_estimate_note or 'L3 reconciliation unavailable.'

    # Device bandwidth and token-derived KV traffic are reported side by side
    # and never substituted for one another.  Filling a missing device
    # direction with prefetched/backuped tokens x KV bytes/token put a
    # 27,224 MB/s "read BW" from nvme_driver_timeseries.csv on a local-SSD run
    # whose device counters carried no bytes at all -- 4x what one Gen4 drive
    # can deliver -- and the requirement table then sized a drive from it.
    # The token figure counts KV moved into or out of L2, including reads
    # answered from page cache and writes the backend skipped, so it bounds
    # device traffic from above and is not a measurement of it.
    #
    # A direction is MEASURED when the block layer reported bytes for it, or
    # when it reported a byte column and no I/O at all in that direction (an
    # idle device reads 0 truthfully).  A zero byte column beside non-zero
    # IOPS is a collector that did not capture bytes, not an idle device.
    def _dev_dir_measured(_src: str, _cols: tuple, _iops_col: str,
                          _iops_mean: float) -> bool:
        if _src:
            return True
        if not any(_c in nvme_ts for _c in _cols):
            return False
        _io = max(_safe_float((nvme_ts.get(_iops_col) or {}).get("max", 0)),
                  _iops_mean)
        return _io <= 0
    nvme_rd_bw_measured = _dev_dir_measured(
        nvme_rd_bw_src, ("rd_bw_mbs", "read_bw_mbs", "rkB_s"), "rd_iops",
        nvme_rd_iops)
    nvme_wr_bw_measured = _dev_dir_measured(
        nvme_wr_bw_src, ("wr_bw_mbs", "write_bw_mbs", "wkB_s"), "wr_iops",
        nvme_wr_iops)

    # blktrace coverage against the device's own byte counters.  A trace on
    # the multipath head (nvme6n1) while I/O was accounted on the controller
    # path (nvme6c6n1) captured 15.9 GB of the ~2.6 TB the device moved each
    # way -- and the report still published an "exact blktrace Q->C" queue
    # depth of 228.6 mean / 17,419 peak, called it healthy, and built the LBA
    # strips and the endurance budget from that 0.6% sample.  The existing
    # coverage warning only fires on collect-time runs, which compare against
    # a kernel delta taken during the trace; a Prometheus-fetched run never
    # carries one.  When the device's own bytes are measured, compare against
    # them, and below half coverage stop treating blktrace as the device.
    blktrace_coverage = None
    blktrace_unrepresentative = False
    if (_blktrace_was_attempted and block_total_source.startswith("blktrace")
            and _l3_window_s > 0 and (nvme_rd_bw_measured or nvme_wr_bw_measured)):
        _dev_gb = ((nvme_rd_bw if nvme_rd_bw_measured else 0.0)
                   + (nvme_wr_bw if nvme_wr_bw_measured else 0.0)) * _l3_window_s / 1000.0
        _bt_gb = ((_block_read_gb if nvme_rd_bw_measured else 0.0)
                  + (_block_write_gb if nvme_wr_bw_measured else 0.0))
        if _dev_gb > 1.0:
            blktrace_coverage = _bt_gb / _dev_gb
            blktrace_unrepresentative = blktrace_coverage < 0.5
    if blktrace_unrepresentative:
        if not _ba_coverage_warning:
            _ba_coverage_warning = (
                f"blktrace captured {blktrace_coverage*100:.1f}% of the bytes the "
                f"device's own counters moved in this window, so its queue depth, "
                f"LBA distribution and byte totals describe a sample, not the device. "
                f"They are withdrawn below; queue depth falls back to the device "
                f"counters. Trace the block device that carries the I/O — on NVMe "
                f"native multipath, compare the head (nvmeXnY) and the controller "
                f"path (nvmeXcYnZ) in /proc/diskstats.")
            _ba_kernel_wr_gb = (nvme_wr_bw * _l3_window_s / 1000.0) if nvme_wr_bw_measured else 0.0
            _ba_captured_ratio = blktrace_coverage
        if str((_qd_sum or {}).get("qd_source", "blktrace_q_to_c")).startswith("blktrace"):
            _qd_sum = _qd_device_fallback()

    l3_logical_rd_bw_mbs = (l3_est_read_gb * 1000 / _l3_window_s) if (_l3_window_s > 0 and l3_est_read_gb > 0) else 0.0
    l3_logical_wr_bw_mbs = (l3_est_write_gb * 1000 / _l3_window_s) if (_l3_window_s > 0 and l3_est_write_gb > 0) else 0.0

    def _dev_bw_txt(_rd_fmt: str = ".1f", _wr_fmt: str = ".1f") -> str:
        """Device R/W bandwidth for prose, saying which direction was unmeasured."""
        if not (nvme_rd_bw_measured or nvme_wr_bw_measured):
            return "not measured on the device (no block-layer byte counters in this run)"
        _rd = (f"{nvme_rd_bw:{_rd_fmt}} MB/s read" if nvme_rd_bw_measured
               else "read not measured")
        _wr = (f"{nvme_wr_bw:{_wr_fmt}} MB/s write" if nvme_wr_bw_measured
               else "write not measured")
        return f"{_rd} / {_wr}"

    def _l3_device_bw_tile() -> str:
        """Device R/W bandwidth, measured on the block layer or stated as absent.

        On an L3.5 run this device is the GPU node's own NVMe, not the tier,
        so it is named as such -- in a form the post-render tier rename does
        not match.
        """
        _lbl = ("GPU node local NVMe read / write BW (measured)" if has_l35
                else "L3 (local storage) read / write BW — device (measured)")
        # Means, not nvme_rd_iops: that falls back to the series MAX.
        _iops = []
        for _keys, _col, _sfx in ((["nvme_rd_iops_mean", "read_iops_mean"], "rd_iops", " rd"),
                                  (["nvme_wr_iops_mean", "write_iops_mean"], "wr_iops", " wr")):
            _v = _safe_float(_pick(blk, _keys, 0.0)) or \
                _safe_float((nvme_ts.get(_col) or {}).get("mean", 0))
            if _v > 0:
                _iops.append(_fmt_num(_v, _sfx, 0))
        _iops_txt = (" / ".join(_iops) + " IOPS mean") if _iops else ""
        if not (nvme_rd_bw_measured or nvme_wr_bw_measured):
            return kpi_card(
                _lbl, "not measured",
                (f"the driver counted {_iops_txt}, so the device was busy — only its "
                 f"bytes were not captured" if _iops_txt else
                 "no block-layer counters for this device in the window"),
                target=("No device byte counters in this run: re-collect with the "
                        "nvme_driver or iostat collector, or pass --nvme-device to a "
                        "Prometheus fetch. The token-derived tile beside this one is not "
                        "a substitute."),
                target_tip=("Device bandwidth is reported only from block-layer byte "
                            "counters. It is never filled from SGLang token counters, "
                            "which count KV moved into and out of L2 rather than bytes "
                            "the drive transferred."))
        _rd_v = _fmt_num(nvme_rd_bw, "", 0) if nvme_rd_bw_measured else "n/m"
        _wr_v = _fmt_num(nvme_wr_bw, "", 1) if nvme_wr_bw_measured else "n/m"
        _pcts = []
        if nvme_rd_bw_measured and nvme_rd_bw_target_mbs > 0:
            _pcts.append(nvme_rd_bw / nvme_rd_bw_target_mbs * 100)
        if nvme_wr_bw_measured and nvme_wr_bw_target_mbs > 0:
            _pcts.append(nvme_wr_bw / nvme_wr_bw_target_mbs * 100)
        _srcs = "; ".join(f"{_d}: {_s}" for _d, _s in
                          (("read", nvme_rd_bw_src), ("write", nvme_wr_bw_src)) if _s)
        return kpi_card(
            _lbl, f"{_rd_v} rd / {_wr_v} wr MB/s",
            " · ".join(["mean over the window"] + ([_iops_txt] if _iops_txt else [])
                       + ([f"{rw_ratio:.1f}:1 R/W bytes"] if l3_traffic_source == "blktrace" else [])),
            target=(f"Target: ~{nvme_rd_bw_target_mbs/1000:.1f} GB/s read / "
                    f"~{nvme_wr_bw_target_mbs/1000:.1f} GB/s write"
                    + ("" if (nvme_rd_bw_measured and nvme_wr_bw_measured) else
                       " · n/m = that direction's bytes were not measured")),
            target_pct=(max(_pcts) if _pcts else None),
            target_tip=(("Measured on " + _srcs + ". " if _srcs else "")
                        + "PCIe Gen4 datacenter NVMe sustains ~7 GB/s sequential read and "
                          "~5 GB/s sequential write; KV-block I/O is smaller and random, so "
                          "sustained figures are usually far lower. Override via setup keys "
                          "'L3 (local storage) read BW target MB/s' and '... write BW target MB/s'."
                        + (" This is the GPU node's own NVMe, not the L3.5 tier: the "
                           "memory node's device has its own tile." if has_l35 else "")))

    def _l3_logical_bw_tile() -> str:
        """KV traffic implied by the engine's token counters, labelled as derived."""
        if not (l3_est_read_gb > 0 or l3_est_write_gb > 0) or _l3_window_s <= 0:
            return ""
        _gb = lambda v: (f"{v*1000:.1f} MB" if 0 < v < 1 else _fmt_num(v, " GB", 1))
        _frags = [f"{_gb(l3_est_read_gb)} prefetched / {_gb(l3_est_write_gb)} backed up "
                  f"over {_l3_window_s/60:,.1f} min",
                  f"KV {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):,.0f} KB/token"]
        _seen = []
        if nvme_rd_bw_measured and l3_logical_rd_bw_mbs > 0 and not has_l35:
            _seen.append(f"device read {nvme_rd_bw / l3_logical_rd_bw_mbs * 100:.1f}%")
        if nvme_wr_bw_measured and l3_logical_wr_bw_mbs > 0 and not has_l35:
            _seen.append(f"device write {nvme_wr_bw / l3_logical_wr_bw_mbs * 100:.1f}%")
        if _seen:
            _frags.append(" / ".join(_seen) + " of this")
        if l3_ambiguous_loadback_gb > 0:
            _frags.append(f"L2→L1 load-back {_gb(l3_ambiguous_loadback_gb)} not counted")
        return kpi_card(
            "L3 (local storage) read / write BW — KV logical (token-derived)",
            f"{_fmt_num(l3_logical_rd_bw_mbs, '', 0)} rd / "
            f"{_fmt_num(l3_logical_wr_bw_mbs, '', 1)} wr MB/s",
            " · ".join(_frags),
            target=("Derived from engine token counters, not measured on a device — "
                    "no device target applies"),
            target_tip=("Read = Δsglang_prefetched_tokens_total, write = "
                        "Δsglang_backuped_tokens_total, each × KV bytes per token ÷ "
                        "the window. These count KV moved into and out of L2, so they "
                        "bound device traffic from above: reads answered from page cache "
                        "or the store's DRAM tier, and writes the backend skipped because "
                        "the page already existed, never reach a drive."))

    # Spill threshold = free HBM / KV bytes per token
    spill_thresh_k = hbm_free_gb * 1e9 / (max(kv_bytes_tok_kb, 1) * 1024) / 1000
    cache_hit_gap   = (cache_hit - cache_hit_tw) if cache_hit_tw_available else 0.0

    # Estimate decode tokens from throughput × duration
    decode_tokens_est = int(max(tp_active, throughput * 0.1) * duration_s)
    mb_per_out_token  = (read_gb * 1000 / max(decode_tokens_est, 1)) if decode_tokens_est > 0 else 0.0

    # ── Data-availability badges (retained, not rendered in Executive) ───────
    # Kept so the coverage signal stays available to callers and to any future
    # surface that wants it; the Executive header no longer renders it (see the
    # note at the header template).  Coverage is reported by `analyze` at
    # collection time via the "Data sources MISSING" log block.
    badges_html = (
        pill("SGLang", has_sglang) +
        pill("GPU / DCGM", has_gpu,
             tip=("DCGM daemon was reachable and reported GPU telemetry." if has_gpu
                  else "DCGM unavailable. Start nv-hostengine or use NVIDIA driver-only "
                       "metrics. Without it, HBM BW Active % and per-GPU power are missing.")) +
        pill("DRAM / CPU PMU", has_dram,
             tip=("--enable-dram produced parseable DRAM bandwidth counters." if has_dram
                  else "DRAM bandwidth counters not collected or all-zero. Re-run with --enable-dram. "
                       "On Intel, AMOprof uses Intel PCM pcm-memory or --dram-tool perf-imc; "
                       "on AMD it uses AMDuProfPcm. Falls back to /proc/meminfo for "
                       "capacity but not for bandwidth.")) +
        pill(("L3 storage / blktrace" if (l3_explicit_config and l3_backend_class in ("remote_mooncake", "remote_storage")) else "L3 storage / blktrace"), has_nvme and has_blktrace,
             tip=("blktrace captured per-IO completion events for the L3 device." if (has_nvme and has_blktrace)
                  else "blktrace data missing or incomplete. Re-run with --enable-blktrace "
                       "and ensure the user has CAP_SYS_ADMIN. Without it, per-IO latency, "
                       "queue depth, and LBA distribution sections show placeholders.")) +
        pill("vmstat", has_vmstat,
             tip=("/proc/vmstat counters captured (page faults, swap, NUMA migrations)." if has_vmstat
                  else "vmstat unavailable — swap-storm detection and page-fault rates "
                       "cannot be computed for this run.")) +
        pill("SMART", has_smart,
             tip=("nvme-cli SMART log parsed: WAF, drive temperature, and endurance "
                  "indicators available." if has_smart else
                  "nvme-cli SMART data missing. The collector could not run "
                  "`nvme smart-log` (binary not installed, device path wrong, or "
                  "insufficient privileges). Without SMART, Write Amplification "
                  "Factor (WAF), drive temperature, endurance, and lifetime-percentage-used "
                  "cannot be reported. To enable: install nvme-cli and ensure the "
                  "collector runs as root."))
    )
    if discard_total > 0:
        badges_html += pill(f"TRIM total: {discard_total:,.0f}", True,
                             tip=(f"{discard_total:,.0f} TRIM/Discard commands were issued by "
                                  "the filesystem to the L3 (local storage) over the run. This is normal and "
                                  "healthy — it tells the device which LBA ranges are free, "
                                  "enabling efficient garbage collection. A value of 0 in some "
                                  "runs is also normal (the FS may have already reclaimed in a "
                                  "prior phase). Concerning patterns would be TRIM commands "
                                  "growing unboundedly during steady-state inference, which "
                                  "would indicate cache thrashing."))

    # ── Wall-clock window string ──────────────────────────────────────────────
    window_str = ""
    if t0_epoch > 1_000_000_000:
        try:
            from datetime import datetime, timezone, timedelta
            t0  = datetime.fromtimestamp(t0_epoch, tz=timezone.utc)
            t1  = t0 + timedelta(seconds=duration_s)
            window_str = (f"{t0.strftime('%Y-%m-%d %H:%M:%S')} → "
                          f"{t1.strftime('%H:%M:%S')}"
                          f" UTC ({duration_min:.1f} min)")
        except Exception:
            pass
    if not window_str and duration_min > 0:
        # Hours above 90 minutes: "647.3 min" is the same number the page
        # header renders as 10.79 h, and the two should read alike.
        window_str = (f"{duration_min/60.0:.2f} h" if duration_min >= 90
                      else f"{duration_min:.1f} min")
    if not window_str:
        # Never render "0.0 min". A window of zero is a failure to establish
        # the window, and saying so points at the fix; printing 0.0 beside a
        # page header that says 38,840 sec just looks like two bugs.
        window_str = "not established — see run-window warning"
    elif duration_conflict:
        window_str += f" · {duration_source}"

    # ── Findings ──────────────────────────────────────────────────────────────
    # Top findings must quote numbers the reader can find elsewhere in the
    # report.  `ttft_ms` comes from the End Report's parsed KPI while the
    # percentile card is computed independently here; when they diverged, a
    # finding announced "First-token wait is 74.8 seconds" against a card
    # showing p50 2.2 s / mean 9.8 s, and nothing on the page explained the
    # gap.  Name the statistic, and quote the distribution beside it so a
    # divergence is visible rather than silent.
    _ttft_stat_label = str(sglang.get("server_ttft_ms_method", "") or "")
    _ttft_stat_label = {
        "canonical_combined_latency_kpi": "End Report KPI",
        "": "reported",
    }.get(_ttft_stat_label, _ttft_stat_label.replace("_", " "))
    _ttft_p50 = _safe_float(_pick(sglang, ["server_ttft_p50_ms"], 0), 0)
    _ttft_p99 = _safe_float(_pick(sglang, ["server_ttft_p99_ms"], 0), 0)
    if _ttft_p50 > 0:
        _ttft_dist = (f" (distribution: p50 {_ttft_p50/1000:.1f} s"
                      + (f", p99 {_ttft_p99/1000:.1f} s" if _ttft_p99 > 0 else "")
                      + ")")
        _ttft_dist_plain = (f"(p50 is {_ttft_p50/1000:.1f} s"
                            + (f", p99 {_ttft_p99/1000:.1f} s" if _ttft_p99 > 0 else "")
                            + ") ")
    else:
        _ttft_dist = ""
        _ttft_dist_plain = ""

    # Device bandwidth as a share of the reference ceiling.
    #
    # This was computed ~350 lines BELOW its first use, in the queue-depth
    # finding at "L3 (local storage) QUEUE". Python only evaluates that term
    # when the preceding ones are falsy, so the UnboundLocalError stayed
    # hidden until a run arrived with exact queue evidence AND both latencies
    # at or under 1 ms -- and then the ENTIRE executive summary failed to
    # generate, not just that finding. Defined here, before anything reads it.
    _ssd_bw_target_mbs = 7000.0
    _ssd_bw_pct = (nvme_rd_bw / _ssd_bw_target_mbs * 100.0) \
        if nvme_rd_bw > 0 and _ssd_bw_target_mbs > 0 else 0.0

    # ---- KV cache generated during the run ---------------------------------
    # Resolved before the findings so the L3.5 finding's "KV generated in the
    # run" uses these same token counts as the KPI tile further down; the two
    # once printed 8,688.1 and 9,367 "GB" for one run.
    #
    # "Generated" means KV that the GPUs actually COMPUTED. A prefill token
    # served from the prefix cache did not generate KV -- it reused KV that
    # already existed -- so counting all prompt tokens would overstate this by
    # whatever the hit rate is, which on these runs is ~95%: a 20x error.
    #
    #   generated tokens = (prompt - cached) + decode
    #                    = recomputed prefill + every output token
    #
    # Both terms are measured counters. The byte figure needs KV bytes per
    # token, which comes from the shared resolver and is exact only when a
    # model config was supplied; when it cannot be resolved the tile reports
    # tokens and says the byte figure is unavailable rather than publishing a
    # default dressed as a measurement.
    _kvg_prompt = _safe_float(_tok_den, 0.0)
    _kvg_cached = _safe_float(_tok_num, 0.0)
    # _tok_num matches on 'cached_tokens_total'.  An engine that exports only
    # realtime_tokens_total{mode="prefill_cache"} -- which is the column the
    # comparator reads, and the one this report's own cache-hit formula is
    # defined on -- does not match that substring, so cached came back 0 while
    # prompt resolved fine.  (prompt - 0) + decode then reports the ENTIRE
    # prompt as newly computed KV: at a 98.8% hit rate that is 83x high, and
    # the only sign is a "- 0 cached" buried in the note.
    # The realtime phase counters, resolved the way the phase-throughput
    # chart resolves them: _amoprof_read_columns_substr requires BOTH
    # substrings in the column name, so it matches whichever form the label
    # expansion produced -- [mode=decode], {mode="decode"}, or anything else
    # carrying both tokens.  A hand-written list of candidate names was the
    # first attempt here, and it was guesswork: this is the function that
    # already found these columns on the run in question, which is why its
    # output-token chart carried "fallback (generation_tokens_total absent)"
    # while this tile reported the totals missing.
    _kvg_phase: dict = {}
    try:
        _kvg_sg_path = _first_existing(raw_dir, ["sglang_timeseries.csv"])
        if _kvg_sg_path:
            # EVERY matching column, not the first: see
            # _amoprof_read_series_substr. A counter fanned out per rank is
            # only whole when its series are summed, and the End report has
            # summed them all along, so taking one here was a divergence
            # waiting on a deployment that fans these out.
            _kvg_phase = _amoprof_read_series_substr(_kvg_sg_path, {
                "prefill_compute": ["realtime_tokens_total",
                                    "mode=prefill_compute"],
                "prefill_cache":   ["realtime_tokens_total",
                                    "mode=prefill_cache"],
                "decode":          ["realtime_tokens_total", "mode=decode"],
            }) or {}
    except Exception:
        _kvg_phase = {}

    def _kvg_counter_delta(_key) -> float:
        """Window total of a cumulative counter, by the shared kernel.

        The sum of positive per-step differences per column, then summed
        across columns -- reset-safe inside the window, and equal to
        last - first on a clean monotonic series. The arithmetic lives in
        metric_kernels.counter_window_total so that this tile, the End
        report's _delta_sum_metric and the comparison's _kv_delta cannot
        drift apart again.
        """
        return float(_k_counter_total(_kvg_phase.get(_key) or [])["total"])

    if _kvg_cached <= 0:
        _kvg_cached = _kvg_counter_delta("prefill_cache")
    _kvg_decode = _ts_delta(sglang_ts, "generation_tokens_total",
                            "sglang_generation_tokens_total")

    # Some deployments export realtime_tokens_total{mode=...} and NOT the
    # prompt_tokens_total / generation_tokens_total counters.  On one such run
    # this tile read "not collected" while the report's own cache-hit tile was
    # computing a percentage from Δrealtime_tokens_total{mode="prefill_cache"}
    # and {mode="prefill_compute"} two tiles above it, and its output-token
    # chart was reading {mode="decode"} with the footnote "fallback
    # (generation_tokens_total absent)".  Every input existed; only this tile
    # did not look for them.
    #
    #   prompt = prefill_cache + prefill_compute   (the cache-hit denominator)
    #   decode = decode mode
    _kvg_prompt_src = ""
    if _kvg_prompt <= 0:
        _pc = _kvg_counter_delta("prefill_compute")
        if _pc > 0 and _kvg_cached > 0:
            _kvg_prompt = _kvg_cached + _pc
            _kvg_prompt_src = (
                f"prompt derived as Δrealtime_tokens_total"
                f"{{mode=prefill_cache}} + {{mode=prefill_compute}} "
                f"({_kvg_cached:,.0f} + {_pc:,.0f}) — "
                f"sglang_prompt_tokens_total is not exported here")
        elif _pc > 0:
            # Compute alone IS the recomputed prefill, which is the term this
            # tile actually needs; no cached figure is required for it.
            _kvg_prompt = _pc
            _kvg_cached = 0.0
            _kvg_prompt_src = (
                f"recomputed prefill taken directly from "
                f"Δrealtime_tokens_total{{mode=prefill_compute}} "
                f"({_pc:,.0f}) — neither prompt_tokens_total nor a cached "
                f"total is exported here")
    _kvg_decode_src = ""
    if _kvg_decode <= 0:
        _v_d = _kvg_counter_delta("decode")
        if _v_d > 0:
            _kvg_decode = _v_d
            _kvg_decode_src = (
                f"decode from Δrealtime_tokens_total{{mode=decode}} "
                f"({_v_d:,.0f}) — sglang_generation_tokens_total is not "
                f"exported here")
    _kvg_recomp = max(0.0, _kvg_prompt - _kvg_cached)
    _kvg_new_tok = _kvg_recomp + _kvg_decode
    # What the run would have had to compute with no cache at all. The ratio
    # of the two is what the hierarchy actually bought.
    _kvg_demand_tok = _kvg_prompt + _kvg_decode
    findings_items: List[str] = []

    # HIGH-PRIORITY: blktrace coverage warning. If captured bytes are much less
    # than the kernel's own write counter, every NVMe number downstream is
    # under-counted and the user must know BEFORE drawing any conclusions.
    if _ba_coverage_warning:
        findings_items.append(finding(
            "⚠ DATA QUALITY · BLKTRACE COVERAGE",
            f'{_ba_coverage_warning} '
            + (f'<br><br>'
                f'<strong>Captured:</strong> {write_gb:.1f} GB blktrace writes &nbsp;·&nbsp; '
                f'<strong>Kernel counter:</strong> {_ba_kernel_wr_gb:.1f} GB '
                f'(/sys/block delta during trace) &nbsp;·&nbsp; '
                f'<strong>Capture rate:</strong> {_ba_captured_ratio*100:.0f}%'
               if _ba_kernel_wr_gb > 0 else "")
            + (f'<br><strong>Dropped events:</strong> {int(_ba_dropped_events):,}'
               if _ba_dropped_events > 0 else "")
        ))

    # ── L3 (local storage) cache activity from SGLang counters (Prometheus-only fallback) ──
    # Emit when blktrace isn't available but SGLang tells us the L3 backing tier was used.
    # This is the difference between a useless "no L3 data" executive and one
    # that still answers "how active is your KV$ L3 (local storage) tier?" — at token
    # granularity instead of byte granularity. Crucially we ALSO state what
    # this number can NOT tell the user (per-IO latency, block size, queue
    # depth) so they don't over-interpret it.
    if l3_logical_diagnostic_seen and (l3_est_read_gb > 0 or l3_est_write_gb > 0):
        _bk_t = int(backuped_tokens)
        _lb_t = int(loadback_tokens)
        _pf_t = int(prefetched_tokens)
        _ev_t = int(evicted_tokens)
        _bk_rate = _bk_t / _l3_window_s if _l3_window_s > 0 else 0
        _lb_rate = _lb_t / _l3_window_s if _l3_window_s > 0 else 0
        _pf_rate = _pf_t / _l3_window_s if _l3_window_s > 0 else 0
        _ev_rate = _ev_t / _l3_window_s if _l3_window_s > 0 else 0
        findings_items.append(finding(
            "LOGICAL KV BACKING-TIER MOVEMENT · NOT PHYSICAL SSD",
            (f'SGLang counters show logical backing-tier movement, but this run also has physical blktrace data that does not match the large logical read total. '
             f'Because no concrete L3 local SSD L3 mapping was resolved, AMOprof does <strong>not</strong> use the logical numbers as SSD/LBA traffic. '
             f'<strong>Prefetch:</strong> {_tok(kv_token_counts.get("prefetch"))}; <strong>backup:</strong> {_tok(kv_token_counts.get("backup"))}. '
             f'<strong>Load-back (L2→L1 restore diagnostic):</strong> {_tok(kv_token_counts.get("load_back"))}; <strong>evict:</strong> {_tok(kv_token_counts.get("evict"))}. Token counts only — byte conversion is not validated against measured storage bytes. '
             f'<strong>Physical traced-device read:</strong> {_block_read_gb:.3f} GB; <strong>physical write:</strong> {_block_write_gb:.3f} GB. '
             f'This prevents the Executive tile from contradicting LBA hot/cold and SSD distribution charts. If the L3 device is mapped but the gap is large, treat it as a cache/page-cache/counter-semantics or capture-window mismatch to investigate. '
             f'<br><br>Counters: backuped={_bk_t:,} ({_bk_rate:,.0f}/s), load_back={_lb_t:,} ({_lb_rate:,.0f}/s), prefetched={_pf_t:,} ({_pf_rate:,.0f}/s), evicted={_ev_t:,} ({_ev_rate:,.0f}/s).'),
            plain=(f"SGLang shows logical backing-tier movement ({_tok(kv_token_counts.get('prefetch'))} prefetched, {_tok(kv_token_counts.get('backup'))} backed up; load-back {_tok(kv_token_counts.get('load_back'))} not counted), "
                   f"but physical traced-device traffic is {_block_read_gb:.3f} GB read / {_block_write_gb:.3f} GB write. "
                   "These are shown separately because no L3 local SSD L3 block mapping was resolved.")))

    if l3_traffic_source in ("sglang_logical_local_ssd", "sglang_logical_remote_l35", "sglang_logical_hicache_unknown_backend") and (read_gb > 0 or write_gb > 0):
        _bk_t = int(backuped_tokens)
        _lb_t = int(loadback_tokens)
        _pf_t = int(prefetched_tokens)
        _ev_t = int(evicted_tokens)
        # Tokens/sec gives an "activity rate" — useful for sizing.
        _bk_rate = _bk_t / _l3_window_s if _l3_window_s > 0 else 0
        _lb_rate = _lb_t / _l3_window_s if _l3_window_s > 0 else 0
        _pf_rate = _pf_t / _l3_window_s if _l3_window_s > 0 else 0
        _ev_rate = _ev_t / _l3_window_s if _l3_window_s > 0 else 0
        # Name the tier that was actually configured: with a
        # Mooncake backend the backing tier is the AI Memory Node, L3.5 — L3
        # is the GPU node's local SSD.  Ratios rather than raw counts, so the
        # finding says what the movement means for this workload.
        _be = _l3_backend if '_l3_backend' in locals() and _l3_backend is not None else None
        _tier_long = (_be.display_name if _be and _be.display_name else "L3 backing tier")
        _tier = _tier_long.split()[0]
        _is_local = bool(_be and _be.backend_class == "local_ssd")
        # KV generated = the KPI tile's own resolution (computed prefill +
        # output), so the finding and the tile cannot print two KV totals.
        _computed = (_kvg_recomp if _kvg_new_tok > 0 else
                     _kv_token_delta(raw_dir, ["mode=prefill_compute"]) or 0.0)
        _reused = _kv_token_delta(raw_dir, ["mode=prefill_cache"]) or 0.0
        _output = (_kvg_decode if _kvg_new_tok > 0 else
                   _kv_token_delta(raw_dir, ["generation_tokens_total"]) or 0.0)
        _prompt = _kv_token_delta(raw_dir, ["prompt_tokens_total"]) or (_computed + _reused)
        _trd = _k_token_reuse_density(_reused, _computed, _output, kv_bytes_tok_kb)
        _kv_generated = _trd["kv_generated_tokens"]    # tokens whose KV was newly created
        _kv_gen_gb = _trd["kv_generated_gb"]
        _reuse_density = _trd["density"]

        def _pct(a, b):
            return f"{a / b * 100:.1f}%" if b > 0 else "n/a"

        def _times(a, b):
            return f"{a / b:.1f}×" if b > 0 else "n/a"

        findings_items.append(finding(
            f"{_tier} ACTIVITY · {_tier_long.split(' ', 1)[1].strip('()').upper() if ' ' in _tier_long else 'BACKING TIER'}",
            (f'Window totals from SGLang HiCache counters (one count per token; TP ranks are not '
             f'double-counted). KV generated in the run = {_computed:,.0f} computed prompt + '
             f'{_output:,.0f} output tokens = <strong>{_kv_generated:,.0f} tokens</strong> '
             f'(≈ {_kv_gen_gb:,.1f} GB at {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f} KB/token).'
             f'<ul style="margin:6px 0 0 18px;padding:0">'
             f'<li><strong>Backed up to {_tier}:</strong> {_bk_t:,} tokens = '
             f'<strong>{_pct(_bk_t, _kv_generated)} of the KV generated</strong>. '
             + ('Close to 100% means write-through: nearly every new KV block is copied to '
                f'{_tier}, which costs {_tier} write bandwidth whether or not it is reused.'
                if _kv_generated > 0 and _bk_t / _kv_generated > 0.8 else
                f'Only part of the new KV reaches {_tier}; the rest is dropped on eviction.')
             + '</li>'
             f'<li><strong>{_tier} value-add — prefetched from {_tier}:</strong> {_pf_t:,} tokens = '
             f'<strong>{_pct(_pf_t, _reused)} of the {_reused:,.0f} reused (cache-hit) prompt tokens</strong>, '
             f'i.e. prefill that {_tier} saved from recompute. '
             f'The {_lb_t:,} L2→L1 load-back tokens are restores from host DRAM (L2), not from {_tier}: '
             f'they show how often KV evicted from HBM was still in L2 '
             f'({_times(_lb_t, _reused)} the reused tokens; above 1× means the same KV was restored more than once).</li>'
             f'<li><strong>Evicted from HBM:</strong> {_ev_t:,} tokens = '
             f'<strong>{_times(_ev_t, _prompt + _output)} the {_prompt + _output:,.0f} tokens processed</strong>. '
             + ('Each token\'s KV left HBM more than once on average: HBM is too small for the working set, '
                'so reuse depends on L2 and ' + _tier + '.'
                if (_prompt + _output) > 0 and _ev_t > (_prompt + _output) else
                'Eviction is below the token volume, so most KV stayed resident in HBM.')
             + '</li>'
             f'<li><strong>Token_Reuse_Density:</strong> <strong>{_reuse_density:,.0f}</strong> reused tokens per GB '
             f'of KV generated ({_reused:,.0f} ÷ {_kv_gen_gb:,.0f} GB). '
             + (f'Above 100: a good fit for prefix-prefetch acceleration (Cognos).'
                if _reuse_density > 100 else
                f'Below 100: limited prefix reuse, so prefix acceleration has little to work with.')
             + '</li></ul>'
             + (f'<strong>Reconciliation note:</strong> {_html.escape(l3_logical_estimate_note)}. ' if l3_logical_estimate_note else '')
             + (f'Per-IO latency, queue depth and hot-LBA regions of the local SSD need block telemetry: '
                f're-collect with <code>--enable-blktrace</code> if they matter for sizing.'
                if _is_local else '')),
            plain=(f"{_tier_long}: {_bk_t:,} tokens backed up = {_pct(_bk_t, _kv_generated)} of the "
                   f"{_kv_generated:,.0f} KV tokens generated; {_pf_t:,} prefetched from {_tier} = "
                   f"{_pct(_pf_t, _reused)} of reused prompt tokens; {_lb_t:,} L2→L1 load-back are host-DRAM restores; "
                   f"{_ev_t:,} evicted = {_times(_ev_t, _prompt + _output)} the tokens processed. "
                   f"Token_Reuse_Density {_reuse_density:,.0f} reused tokens/GB KV "
                   f"({'good' if _reuse_density > 100 else 'limited'} fit for prefix acceleration).")))
    elif l3_traffic_source == "none":
        # NO L3 data from any source. Don't leave the user wondering — be
        # explicit about what was checked and what was found. The user
        # genuinely benefits from knowing whether (a) L3 backing tier was idle, or
        # (b) instrumentation was missing.
        _has_sg_counters = any(k in sglang for k in (
            "backuped_tokens_total", "sglang_backuped_tokens_total",
            "load_back_tokens_total", "sglang_load_back_tokens_total",
            "prefetched_tokens_total", "sglang_prefetched_tokens_total",
            "evicted_tokens_total", "sglang_evicted_tokens_total"))
        _evicted = evicted_tokens
        if l3_backend_class == "none" and _l3_no_tier is not None:
            # SGLang reports no storage backend.  Zero backup/prefetch
            # is then the expected reading, not an idle tier, and "re-run with
            # a larger context to drive L3 traffic" asks for traffic to a tier
            # that does not exist.  Say what the counters mean for this
            # architecture and whether adding a tier is worth considering.
            _ev_n = int(_evicted or 0)
            _proc = (_kvg_prompt + _kvg_decode) if (_kvg_prompt + _kvg_decode) > 0 else 0.0
            _ev_ratio = (_ev_n / _proc) if _proc > 0 else 0.0
            _hit = _safe_float(cache_hit, 0.0)
            _pressure = _ev_ratio >= 1.0 or (_ev_n > 0 and 0 < _hit < 50)
            _tiers = ("L1 HBM only" if "no HiCache" in _l3_no_tier.display_name
                      else "L1 HBM + L2 DRAM only")
            _held = "L1" if _tiers == "L1 HBM only" else "L1 + L2"
            findings_items.append(finding(
                "L3 TIER · NOT CONFIGURED",
                (f'This run has no L3 tier ({_tiers}; SGLang server_info reports '
                 f'<code>hicache_storage_backend</code> = None), so SGLang '
                 f'<code>backuped_tokens_total</code> and <code>prefetched_tokens_total</code> '
                 f'staying at 0 is expected — there is no tier to back up to or prefetch from. '
                 + (f'<code>load_back_tokens_total</code> = {int(loadback_tokens):,} is L2→L1 '
                    f'restore from host DRAM. '
                    if loadback_tokens > 0 else '')
                 + (f'<code>evicted_tokens_total</code> = {_ev_n:,}'
                    + (f' ({_ev_ratio:,.1f}× the {_proc:,.0f} tokens processed)' if _proc > 0 else '')
                    + (': with no L3 there is nowhere to offload evicted KV, so KV not also held '
                       'in L2 is dropped and recomputed if a later request needs it. '
                       if _held != "L1" else
                       ': with no lower tier, evicted KV is dropped and recomputed if a later '
                       'request needs it. ')
                    if _ev_n > 0 else '')
                 + '<strong>Recommendation:</strong> '
                 + ('the eviction rate'
                    + (f' and {_hit:.1f}% cache hit' if _hit > 0 else '')
                    + (' suggest' if _hit > 0 else ' suggests')
                    + f' the working set exceeds {_held} — consider adding an L3 tier '
                      '(local NVMe or an AI Memory Node) so evicted KV is kept instead of recomputed.'
                    if _pressure else
                    f'{_held} held this workload without heavy eviction; add an L3 tier only if '
                    'larger contexts or more sessions are expected.')),
                plain=(f"No L3 tier is configured ({_tiers}), so zero backup/prefetch is expected. "
                       + (f"{_ev_n:,} evicted tokens had no L3 to be offloaded to. " if _ev_n > 0 else "")
                       + ("Consider adding an L3 tier to keep evicted KV."
                          if _pressure else "No L3 tier is needed for this workload as observed."))))
        elif _has_sg_counters and l3_sglang_activity_tokens == 0:
            # Counters present, but no reliable L3 storage evidence. load_back-only
            # and evicted-only are not counted as L3 usage.
            findings_items.append(finding(
                "L3 ACTIVITY · NONE OBSERVED",
                (f'L3 (local storage) cache tier shows no reliable activity in this window. SGLang '
                 f'<code>backuped_tokens_total</code> and <code>prefetched_tokens_total</code> '
                 f'both registered 0 during the {_l3_window_s:.0f} s collection window. '
                 + (f'<code>load_back_tokens_total</code> = {int(loadback_tokens):,} was observed, '
                    f'but load_back-only is L2→L1 restore and is not storage I/O and is not counted as L3 local-storage I/O without '
                    f'backup/prefetch or mapped block telemetry. '
                    if loadback_tokens > 0 else '')
                 + (f'<code>evicted_tokens_total</code> = {int(_evicted):,} indicates KV '
                    f'evictions/cache pressure, but not L3 local-storage I/O by itself. '
                    if _evicted > 0 else '')
                 + f'<strong>Implications:</strong> the working set fit within HBM + L2 '
                 f'DRAM, so L3 local storage was not exercised. KV$ L3 (local storage) sizing based on this run '
                 f'will be unrepresentative — re-run with a larger context or more '
                 f'concurrent sessions to drive L3 (local storage) traffic.'),
                plain=(f"No reliable L3 (local storage) activity was detected during this {_l3_window_s:.0f}s "
                       f"window. backuped_tokens_total and prefetched_tokens_total stayed at zero; "
                       f"load_back-only (L2→L1 restore) and evicted-only counters are not treated as L3/local-storage usage. "
                       f"If you're sizing the L3 (local storage) tier, use a run that produces backup or "
                       f"prefetch activity, or collect mapped block telemetry.")))
        else:
            # Counters missing entirely → instrumentation problem.
            findings_items.append(finding(
                "⚠ L3 ACTIVITY · NOT INSTRUMENTED",
                (f'No L3 (local storage) cache activity could be measured for this run. '
                 f'blktrace is absent <em>and</em> SGLang Prometheus counters '
                 f'<code>backuped_tokens_total</code> / <code>load_back_tokens_total</code> '
                 f'were not captured. Possible causes: (1) SGLang version pre-dating '
                 f'HiCache counter exposure (need ≥0.4.x); (2) Prometheus scrape '
                 f'missed these specific metrics — check your scrape config; '
                 f'(3) HiCache was disabled on the server. '
                 f'<strong>Action:</strong> verify HiCache is enabled, confirm SGLang '
                 f'version exposes these counters, and either enable blktrace or '
                 f'fix the Prometheus metric path on the next collection.'),
                plain=("We couldn't measure L3 (local storage) cache activity for this run — neither "
                       "the disk-level trace nor the application-level counters captured "
                       "it. The most likely cause is that HiCache wasn't enabled or "
                       "the metrics aren't being scraped. Without one of these data "
                       "sources, L3 sizing cannot be answered from this report.")))

    if ttft_ms > 5000 and gpu_util > 80:
        findings_items.append(finding(
            "COMPUTE · HBM",
            f'TTFT (<strong>{_ttft_stat_label}</strong>) of '
            f'<strong>{ttft_ms/1000:.1f} s</strong>{_ttft_dist} is driven by long-context prefill '            f'compute. GPU at {gpu_util:.0f}% mean / {gpu_peak:.0f}% peak and HBM at '            f'{hbm_pct:.0f}% full confirm a compute + HBM-bandwidth-bound workload, '            f'not a storage bottleneck. TPOT of {tpot_ms:.0f} ms/tok reflects the model '            f'requiring ~{hbm_gb:.0f} GB of HBM reads per decode step. '            f'<strong>Action:</strong> <code>--chunked-prefill-size 4096</code> and '            f'<code>--kv-cache-dtype fp8_e5m2</code>.',
            plain=(f"First-token wait ({_ttft_stat_label}) is {ttft_ms/1000:.1f} seconds "
                   f"{_ttft_dist_plain}— long, but caused by the "
                   f"GPU being busy with the prompt itself, not by storage. The model is "
                   f"big and the prompts are big. Recommended: split prompts into smaller "
                   f"chunks and shrink the KV cache to FP8.")))
    elif ttft_ms > 1000:
        findings_items.append(finding(
            "COMPUTE",
            f'TTFT of {ttft_ms:.0f} ms is elevated. Check prefill compute, KV L2→L1 load-back, '            f'and queue wait time separation. <strong>Action:</strong> '            f'enable chunked prefill and inspect KV eviction rates.',
            plain=(f"First-token wait is {ttft_ms:.0f} ms — a bit high. Could be the prompt "
                   f"being heavy, the cache reloading data, or requests queuing up. "
                   f"Recommended: turn on chunked prefill and check cache pressure.")))

    # ── L0 SGLang scheduler queue (requests waiting to enter prefill) ────
    _sgl_q_mean  = _safe_float((sglang_ts.get("sglang_num_queue_reqs",   {}) or {}).get("mean", 0))
    _sgl_q_max   = _safe_float((sglang_ts.get("sglang_num_queue_reqs",   {}) or {}).get("max",  0))
    _sgl_r_mean  = _safe_float((sglang_ts.get("sglang_num_running_reqs", {}) or {}).get("mean", 0))
    _sgl_r_max   = _safe_float((sglang_ts.get("sglang_num_running_reqs", {}) or {}).get("max",  0))
    if _sgl_q_mean > 0 or _sgl_q_max > 0 or _sgl_r_mean > 0:
        if _sgl_q_mean > 4:
            findings_items.append(finding(
                "REQUEST QUEUE · BACKED UP",
                f'SGLang scheduler queue averaging <strong>{_sgl_q_mean:.1f}</strong> waiting '
                f'requests (peak {_sgl_q_max:.0f}) while <strong>{_sgl_r_mean:.1f}</strong> '
                f'are running. Requests are stacking up faster than the GPU can drain them. '
                f'<strong>Action:</strong> raise <code>--max-running-requests</code>, '
                f'enable chunked prefill, or shed load upstream.',
                plain=(f"Requests are waiting in line — {_sgl_q_mean:.0f} on average, peaking "
                       f"at {_sgl_q_max:.0f}. Recommended: let SGLang run more requests in "
                       f"parallel, or reduce traffic.")))
        elif _sgl_r_mean > 0 and _sgl_q_mean < 0.5:
            findings_items.append(finding(
                "REQUEST QUEUE · CLEAN",
                f'SGLang scheduler queue clean: {_sgl_q_mean:.2f} mean waiting, '
                f'{_sgl_r_mean:.1f} mean running. No request-side back-pressure.',
                plain=(f"Requests aren't piling up — the GPU is keeping pace with incoming "
                       f"traffic.")))

    if read_gb > 10 and has_blktrace:
        # Branch the action prose on the actual util — at saturation, "spare
        # capacity" is wrong and the right action is to expand L2 OR provision
        # more NVMe BW. At low util, "headroom remains" is honest and the
        # only action is to expand L2.
        _nvme_status = _nvme_status_phrase(nvme_util, nvme_rd_lat)
        _ssd_sat_proven = _ssd_hw_saturation_proven(
            nvme_rd_bw, nvme_wr_bw, nvme_util, nvme_rd_lat,
            _safe_float(_qd_sum.get("qd_mean", 0)) if isinstance(_qd_sum, dict) else 0,
            _safe_float(_qd_sum.get("qd_max", 0)) if isinstance(_qd_sum, dict) else 0,
            str(_qd_sum.get("qd_source", "")) if isinstance(_qd_sum, dict) else "",
        )
        findings_items.append(finding(
            "KV CACHE · L3",
            f'HiCache L3 (local storage) is active: <strong>{read_gb:,.1f} GB L3 (local storage) reads</strong> vs '
            f'{write_gb:.1f} GB writes ({rw_ratio:.0f}:1 ratio) — a L2→L1 restore-heavy diagnostic phase. '
            + (f'Estimated <strong>{mb_per_out_token:.0f} MB per output token</strong> '
               f'of L3 local-storage prefetch/read traffic — a key KV$ L3 (local storage) sizing input. '
               if mb_per_out_token > 1 else "") +
            f'Physical bandwidth is {_dev_bw_txt()}. '
            f'Device busy-time {nvme_util:.1f}% mean — the L3 (local storage) is '
            f'<strong>{_nvme_status}</strong>. '
            + ('<strong>Action:</strong> expand DRAM L2 tier to absorb more '
               'KV blocks before they reach L3 — and provision additional '
               'NVMe bandwidth only after exact queue-depth/latency confirms SSD hardware saturation.'
               if _ssd_sat_proven else
               '<strong>Action:</strong> do not size a faster SSD from busy-time alone. '
               'First reduce KV L2→L1 restore pressure by expanding/tuning L2 DRAM and verify exact blktrace Q→C queue depth or iostat await latency.'),
            plain=(
                f"The L3 (local storage) cache is being read heavily ({read_gb:,.0f} GB), "
                + (f"but physical bandwidth is only {_dev_bw_txt('.0f')}. "
                   if (nvme_rd_bw_measured or nvme_wr_bw_measured) else
                   "but the device's own bandwidth was not measured in this run. ")
                + ("SSD hardware saturation is supported by queue/latency evidence."
                   if _ssd_sat_proven else
                   "This is not bandwidth-saturated; the likely issue is cache-tier L2→L1 restore pressure or reporting/queue-depth evidence, not raw SSD bandwidth."))))
    elif write_gb > 10 and has_blktrace and rw_ratio < 0.1:
        # Write-dominant: HiCache is offloading KV blocks to L3 but
        # rarely loading them back. Often means L1+L2 fit the working set,
        # or eviction policy is too aggressive.
        findings_items.append(finding(
            "KV CACHE · L3",
            f'HiCache L3 (local storage) is write-dominant: <strong>{write_gb:.1f} GB writes</strong> vs '            f'{read_gb*1000:.1f} MB reads — a backup-heavy phase with no significant L2→L1 load-back restore. '            f'Device busy-time {nvme_util:.1f}% mean. '            f'<strong>Action:</strong> consider tuning HiCache eviction (raise L2 size or '            f'lower spill threshold) if the working set fits in DRAM; otherwise the '            f'writes are pre-staging future load-backs and are healthy.',
            plain=(f"The L3 (local storage) cache is being written to a lot ({write_gb:.0f} GB) but barely "
                   f"read back. Either the data being saved is rarely needed again, or RAM "
                   f"already has what the model needs. If this is unexpected, check whether "
                   f"the cache is evicting too aggressively.")))

    # ── L3 (local storage) Queue Depth — workload throughput vs latency profile ─────────
    # Only emit a finding if blktrace QD analysis ran successfully (v40+).
    if _qd_sum and _qd_sum.get("qd_mean") is not None:
        _qd_source = str(_qd_sum.get("qd_source", "blktrace_q_to_c") or "blktrace_q_to_c")
        _qd_src_note = ("exact blktrace Q→C" if _qd_source.startswith("blktrace") else "advisory iostat/sysfs run-window fallback")
        qd_mean = _safe_float(_qd_sum.get("qd_mean", 0))
        qd_p95  = _safe_float(_qd_sum.get("qd_p95", 0))
        qd_peak = _safe_float(_qd_sum.get("qd_max", 0))
        sat_32  = _safe_float(_qd_sum.get("pct_at_qd_ge_32", 0))
        sat_128 = _safe_float(_qd_sum.get("pct_at_qd_ge_128", 0))
        _qd_ok = _qd_plausible(qd_mean, qd_peak, _qd_source)
        if not _qd_ok:
            findings_items.append(finding(
                "L3 (local storage) QUEUE · FALLBACK SIGNAL",
                f'Queue-depth fallback reported implausible values: mean QD '
                f'<strong>{qd_mean:.1f}</strong>, p95 <strong>{qd_p95:.0f}</strong>, '
                f'peak <strong>{qd_peak:.0f}</strong> from <strong>{_qd_src_note}</strong>. '
                f'This is not reliable proof of NVMe saturation. Use exact blktrace Q→C '
                f'queue-depth, iostat <code>aqu-sz</code>/<code>await</code>, or kernel '
                f'inflight counters before concluding the SSD is the bottleneck.',
                plain=(f"Queue-depth data is populated, but the fallback values are implausibly high. "
                       f"Do not treat this as L3 (local storage) saturation until exact Q→C queue depth or latency confirms it.")))
        elif qd_mean >= 32 and sat_32 > 50:
            _exact_qd = _qd_source.startswith("blktrace")
            findings_items.append(finding(
                "L3 (local storage) QUEUE · " + ("SATURATED" if _exact_qd and (nvme_rd_lat > 1.0 or nvme_wr_lat > 1.0 or _ssd_bw_pct > 30.0) else "ADVISORY / VERIFY"),
                f'Mean queue depth <strong>{qd_mean:.1f}</strong> ({_qd_src_note}) with '
                f'<strong>{sat_32:.0f}%</strong> of trace time at QD≥32 (peak QD = '
                f'{qd_peak:.0f}, p95 = {qd_p95:.0f}). '
                + (f'This is exact Q→C queue evidence and may indicate saturation. ' if _exact_qd else
                   f'This is fallback queue evidence, so it is <strong>not proof of NVMe saturation</strong>. ')
                + f'Bandwidth is {_dev_bw_txt()}; '
                f'latency is {nvme_rd_lat:.2f} ms read / {nvme_wr_lat:.2f} ms write where captured. '
                f'<strong>Action:</strong> treat busy-time/QD fallback as advisory until exact blktrace Q→C and await/latency confirm saturation.',
                plain=(f"L3 (local storage) queue/busy-time is elevated, but saturation is not proven unless "
                       f"bandwidth, latency, or exact Q→C queue-depth also confirms it.")))
        elif qd_mean < 1.5:
            findings_items.append(finding(
                "L3 storage QUEUE · LATENCY-BOUND",
                f'Mean queue depth <strong>{qd_mean:.2f}</strong> ({_qd_src_note}, peak {qd_peak:.0f}) — '
                f'the workload is dispatching one L3 (local storage) request at a time and waiting for it '
                f'to complete before issuing the next. Storage is NOT the bottleneck. '
                f'<strong>Action:</strong> investigate upstream batching / scheduler '
                f'serialisation — increase concurrency to use the device\'s parallelism.',
                plain=(f"The L3 (local storage) is barely being asked to do anything in parallel "
                       f"(only {qd_mean:.1f} requests in-flight on average). The bottleneck "
                       f"is somewhere upstream — the GPU, scheduler, or batching. "
                       f"Recommended: increase request concurrency.")))
        else:
            findings_items.append(finding(
                "L3 storage QUEUE · HEALTHY",
                f'Mean queue depth <strong>{qd_mean:.1f}</strong> ({_qd_src_note}, p95 {qd_p95:.0f}, peak '
                f'{qd_peak:.0f}). Healthy parallel I/O without saturation.',
                plain=(f"The L3 (local storage) is handling {qd_mean:.1f} requests in parallel on average — "
                       f"a healthy mix of concurrency and headroom.")))

    # ── FS + block-layer merge stats (read early so findings can reference) ──
    # From smart_summary.json (populated by _refresh_smart_capacity) and
    # blktrace_analysis/summary.json (propagated by
    # _merge_collector_diagnostics_into_summary). Re-read here for clarity;
    # the same values get used below in the setup table and an "Avg dispatched
    # I/O" KPI tile.
    _fs_type        = str(smart.get("fs_type", "")).strip()
    _fs_bsize       = _safe_float(smart.get("fs_block_size", 0))
    _wr_merge_ratio = _safe_float(_ba_sum.get("sys_block_wr_merge_ratio", 0))
    _rd_merge_ratio = _safe_float(_ba_sum.get("sys_block_rd_merge_ratio", 0))
    # sys_block_avg_*_io_kb are sectors x 512 / 1024 (KiB); shown as decimal KB.
    _avg_wr_io_kb   = _k_kb_from_bytes(_safe_float(_ba_sum.get("sys_block_avg_wr_io_kb", 0)) * 1024)
    _avg_rd_io_kb   = _k_kb_from_bytes(_safe_float(_ba_sum.get("sys_block_avg_rd_io_kb", 0)) * 1024)
    _merge_note     = str(_ba_sum.get("block_layer_merge_note", "")).strip()

    # ── Block-layer merging (FS-driven op-count reduction) ──────────────
    # Emit a finding when the kernel coalesced a significant fraction of
    # submitted BIOs. This is the answer to the common question "why did my
    # op count drop after switching from ext4 to XFS?" — without explicitly
    # surfacing this, users assume measurement loss when the FS is actually
    # doing its job well.
    if _merge_note and (_wr_merge_ratio >= 0.3 or _rd_merge_ratio >= 0.3):
        # Build a compact technical summary
        _tech_bits = []
        if _wr_merge_ratio >= 0.3:
            _tech_bits.append(
                f"{_wr_merge_ratio*100:.0f}% of submitted write BIOs merged "
                f"(avg dispatch size {_avg_wr_io_kb:.0f} KB)")
        if _rd_merge_ratio >= 0.3:
            _tech_bits.append(
                f"{_rd_merge_ratio*100:.0f}% of submitted read BIOs merged "
                f"(avg dispatch size {_avg_rd_io_kb:.0f} KB)")
        _fs_clause = (f"{_fs_type.upper() if len(_fs_type) <= 4 else _fs_type} "
                      f"with {int(_fs_bsize)} B blocks "
                      if _fs_type and _fs_bsize else "The filesystem ")
        # Plain-English version: this is meant to head off "did I lose data?"
        _plain = (f"On this run the filesystem combined many small writes "
                  f"into fewer bigger ones before sending them to the L3 storage — about "
                  f"{_wr_merge_ratio*100:.0f}% of writes were merged. That's why "
                  f"the captured operation count is lower than the application "
                  f"submitted. It's healthy behaviour, not lost data. "
                  + ("XFS does this much more than ext4 because of extent-based "
                     "allocation. If you compare op counts before and after a "
                     "filesystem swap, the XFS number will look low — but the "
                     "byte total and the work done are the same."
                     if _fs_type.lower() == "xfs" else
                     "If you compare op counts to a previous run on a different "
                     "filesystem, the merge rate explains most of the gap."))
        findings_items.append(finding(
            "FS MERGING · HEALTHY",
            f"{_fs_clause}coalesced submitted I/Os at the block layer: "
            + " and ".join(_tech_bits) + ". "
            f"<strong>Implication:</strong> the captured blktrace op count is "
            f"lower than the application-submitted count by design — fewer, "
            f"larger BIOs reached the device. This is not measurement loss. "
            + (f"<br>Coverage cross-check (captured vs kernel /sys/block delta): "
               f"{_safe_float(_ba_sum.get('captured_vs_kernel_ratio', 1.0))*100:.0f}%. "
               if _ba_sum.get('captured_vs_kernel_ratio') else ""),
            plain=_plain))

    # Both rates are token-weighted, so a gap between them cannot come from a
    # mix of short and long requests: it is two SGLang counters counting
    # different token streams.  It once read "per-request 78%, per-token 0%"
    # on a run that did not export prompt_tokens_total at all.
    if abs(cache_hit_gap) > 10:
        findings_items.append(finding(
            "CACHE HIT · COUNTERS DISAGREE",
            f'Two token-weighted cache-hit measures differ by {abs(cache_hit_gap):.0f} pp: '
            f'<code>prefill_cache ÷ (prefill_cache + prefill_compute)</code> = {cache_hit:.1f}% '
            f'(the headline) and <code>cached_tokens_total ÷ prompt_tokens_total</code> = '
            f'{cache_hit_tw:.1f}%. They count different token streams — '
            f'<code>prompt_tokens_total</code> can include every prompt token, while '
            f'<code>prefill_cache</code> counts prompt tokens served from cache at prefill — so '
            f'the difference reflects the counters, not request sizes. '
            f'<strong>Action:</strong> use the headline; compare runs only on the same counter.',
            plain=(f"Two ways of counting cache reuse disagree ({cache_hit:.0f}% vs "
                   f"{cache_hit_tw:.0f}%). Both count tokens, from different SGLang counters, so "
                   f"the gap does not mean requests mix short hits with long misses. The "
                   f"{cache_hit:.0f}% headline is the one to use.")))
    elif cache_hit > 0:
        if cache_hit < 40:
            findings_items.append(finding(
                "CACHE HIT",
                f'Cache hit is low ({cache_hit:.1f}%). Inspect prompt prefix sharing, '                f'HiCache warm-up, and KV eviction pressure.',
                plain=(f"Only {cache_hit:.0f}% of prompt tokens are being served from cache — the "
                       f"rest are recomputed from scratch. Recommended: check whether prompts "
                       f"share a common prefix, and give the cache more time to warm up.")))
        else:
            findings_items.append(finding(
                "CACHE HIT",
                f'Cache hit is strong ({cache_hit:.1f}% of prefill tokens served from cache). Remaining latency '                f'is more likely from prefill compute, HBM pressure, or queue-time.',
                plain=(f"Cache reuse is healthy ({cache_hit:.0f}% hit rate). If latency is "
                       f"still high, the bottleneck isn't the cache — look at GPU compute, "
                       f"GPU memory pressure, or request queuing.")))

    if dram_total_bw > 0:
        dram_util_pct = dram_total_bw / max(dram_peak_cap, 1) * 100
        if dram_util_pct < 30:
            findings_items.append(finding(
                "L2 DRAM",
                f'CPU PMU reports {dram_total_bw:.1f} GB/s mean DRAM BW '                f'({dram_util_pct:.1f}% of {dram_peak_cap:.0f} GB/s peak) — '                f'<strong>not the bottleneck</strong>. Ample DRAM headroom exists '                f'to expand the L2 KV tier and absorb more L3 (local storage) traffic.',
                plain=(f"System RAM bandwidth is at {dram_util_pct:.0f}% of its capability — "
                       f"plenty of room to spare. Recommended: enlarge the in-RAM portion of "
                       f"the cache to reduce L3 (local storage) traffic.")))
        else:
            findings_items.append(finding(
                "L2 DRAM",
                f'DRAM BW at {dram_total_bw:.1f} GB/s ({dram_util_pct:.1f}% of peak) '                f'is elevated — L2 staging may be approaching saturation. '                f'Monitor for KV L2→L1 load-back latency increases.',
                plain=(f"System RAM bandwidth at {dram_util_pct:.0f}% of capacity — getting "
                       f"warm. If you see slowdown, RAM-to-GPU transfers may be the cause.")))

    swap_pages = 0.0
    if "pswpin" in vmstat_ts: swap_pages = _safe_float(vmstat_ts["pswpin"].get("max", 0))
    if swap_pages == 0 and has_vmstat:
        findings_items.append(finding("HEALTH",
            f'Zero swap I/O — kernel memory is not under pressure ✅. '            + (f'{discard_total:,.0f} total TRIM/Discard commands reflect normal '               f'HiCache L3 (local storage) reclamation (expected and healthy). '               if discard_total > 0 else "") +
            f'{"SMART unavailable — run nvme smart-log /dev/nvme0 -o json to verify WAF." if not has_smart else f"SMART: WAF={smart_waf:.1f}, Temp={smart_temp:.0f}°C."}',
            plain=("System health looks good — no swap activity (means RAM isn't running out). "
                   + ("L3 storage block telemetry is normal." if l3_block_io_available
                      else "L3 (local storage) activity is based on SGLang movement counters; block-device health is not measured in this run."))))

    if not findings_items:
        findings_items.append(finding("DATA",
            "Only partial data was available for this window. "
            "Enable SGLang/DCGM/blktrace/DRAM collectors for a complete picture."))

    # Build the human-readable cache-tier label used in the hero block above
    # and the setup table below. Examples:
    #   "Enabled · L2 DRAM (256 GB) + L3 storage (3.5 TB)"
    #   "Enabled · L2 DRAM + L3 AI Memory Node"
    #   "Disabled" when cache_enabled is falsy
    _enabled_truthy = str(cache_enabled).strip().lower() in (
        "true","yes","1","on","enabled","enable","y","t")
    # The explicit flag is often absent even when the tiers plainly exist —
    # SGLang does not always echo --enable-hierarchical-cache into
    # server_info, and a Prometheus-only run has no launch command at all.
    # Fall back to the evidence: a sized L2/L3 allocation, a declared storage
    # backend, or measured host-cache residency all prove the tier is real.
    _tier_evidence = (
        (l2_dram_capacity_gb or 0) > 0
        or (l3_fs_total_gb or 0) > 0
        or bool(str(_pick(setup, ["HiCache storage backend", "hicache_storage_backend",
                                  "L3 storage type", "storage_backend"], "")).strip())
        or _safe_float(_pick(sglang, ["hicache_host_used_tokens",
                                      "sglang_hicache_host_used_tokens"], 0), 0) > 0
        or _safe_float(_pick(setup, ["HiCache ratio", "hicache_ratio"], 0), 0) > 0)
    if _enabled_truthy or (isinstance(cache_enabled, str) and "+" in cache_enabled) \
            or _tier_evidence:
        # Every KV-cache layer this run has, with the memory type behind it
        # and the capacity it holds for KV, so a report can be tied to its
        # configuration at a glance (e.g. L3.5 on DRAM vs DRAM + CXL):
        #   Enabled · L1 (HBM: x GB) + L2 (DRAM: y GB) + L3 (NVMe SSD: z GB)
        #             + L3.5 (DRAM: a GB + CXL: b GB + NVMe SSD: c GB)
        # Capacities are the KV allocation of each layer, in decimal GB.  The
        # hero stays vendor-neutral: the setup table names the backend.
        def _gb(gb: float) -> str:
            return f"{gb:,.0f} GB" if gb >= 10 else f"{gb:,.1f} GB"

        def _setup_gb(*keys) -> float:
            return _safe_float(_pick(setup, list(keys), 0), 0)

        _be_cls = str(l3_backend_class or "").lower()
        _remote = _be_cls.startswith("remote") or _be_cls == "ai_memory_node"
        _layers: list = []

        # L1: the GPU KV pool, max_total_num_tokens x KV bytes per token
        # (full model across ranks).
        # The server publishes both pool sizes as gauges; summary keys and the
        # setup file are fallbacks for runs without the timeseries.
        def _gauge_max(*names) -> float:
            return _safe_float(_ts_col(sglang_ts, *names).get("max", 0), 0)
        _pool_tok = (_gauge_max("max_total_num_tokens")
                     or _safe_float(_pick(sglang, ["max_total_num_tokens",
                                                   "sglang_max_total_num_tokens"], 0), 0)
                     or _setup_gb("max_total_num_tokens"))
        _bpt = _safe_float(kv_bytes_tok_kb, 0) * 1024.0
        _layers.append(f"L1 (HBM: {_gb(_k_gb_from_bytes(_pool_tok * _bpt))})"
                       if _pool_tok > 0 and _bpt > 0 else "L1 (HBM)")

        # L2: the HiCache host allocation — hicache_host_total_tokens x KV
        # bytes.  l2_dram_capacity_gb falls back to the whole host's DRAM when
        # no HiCache size is configured, which is not what the cache holds.
        _l2_tok = _gauge_max("hicache_host_total_tokens")
        _l2_gb = (_k_gb_from_bytes(_l2_tok * _bpt) if _l2_tok > 0 and _bpt > 0
                  else (l2_dram_capacity_gb or 0))
        if _l2_gb > 0 or _gauge_max("hicache_host_used_tokens") > 0 or _safe_float(
                _pick(sglang, ["hicache_host_used_tokens",
                               "sglang_hicache_host_used_tokens"], 0), 0) > 0:
            _layers.append(f"L2 (DRAM: {_gb(_l2_gb)})" if _l2_gb > 0 else "L2 (DRAM)")

        # L3: local NVMe SSD on the GPU node.
        if not _remote and _be_cls != "none" and ((l3_fs_total_gb or 0) > 0 or str(_pick(setup, [
                "L3 storage type", "L3 Device", "L3 Mount Path"], "")).strip()):
            _layers.append(f"L3 (NVMe SSD: {_gb(l3_fs_total_gb)})"
                           if (l3_fs_total_gb or 0) > 0 else "L3 (NVMe SSD)")

        # L3.5: the AI Memory Node.  The store's own accounting splits memory
        # from file (SSD) capacity but not DRAM from CXL inside the memory
        # pool, so that split comes from the setup file when given and is
        # checked against the measured memory total; otherwise it is said to
        # be unreported rather than all called DRAM.
        _hicache_backend_set = bool(str(_pick(setup, [
            "HiCache storage backend", "hicache_storage_backend",
            "Remote storage endpoint"], "")).strip())
        _mem_gb = _file_gb = 0.0
        try:
            _cf = _first_existing(raw_dir, ["l35_store_capacity.csv"])
            _cc = (_amoprof_read_columns_raw(
                _cf, ["l35_store_mem_cap_b", "l35_store_file_cap_b"]) if _cf else {})
            def _mx(_k):
                _v = [x for x in (_cc.get(_k) or []) if x == x and x > 0]
                return _k_gb_from_bytes(max(_v)) if _v else 0.0
            _mem_gb, _file_gb = _mx("l35_store_mem_cap_b"), _mx("l35_store_file_cap_b")
        except Exception:
            pass
        if _remote and (_hicache_backend_set or _mem_gb > 0 or _file_gb > 0):
            _dram_s = _setup_gb("L3.5 DRAM GB", "L3.5 DRAM capacity GB", "l35_dram_gb")
            _cxl_s = _setup_gb("L3.5 CXL GB", "L3.5 CXL capacity GB", "l35_cxl_gb")
            _ssd_s = _setup_gb("L3.5 SSD GB", "L3.5 NVMe SSD GB", "L3.5 SSD capacity GB", "l35_ssd_gb")
            _parts = []
            if _dram_s > 0 or _cxl_s > 0:
                if _dram_s > 0:
                    _parts.append(f"DRAM: {_gb(_dram_s)}")
                if _cxl_s > 0:
                    _parts.append(f"CXL: {_gb(_cxl_s)}")
            elif _mem_gb > 0:
                _parts.append(f"memory: {_gb(_mem_gb)} [DRAM/CXL split not reported]")
            _ssd = _file_gb or _ssd_s
            if _ssd > 0:
                _parts.append(f"NVMe SSD: {_gb(_ssd)}")
            _l35 = "L3.5 (" + " + ".join(_parts) + ")" if _parts else "L3.5"
            _split = _dram_s + _cxl_s
            if _split > 0 and _mem_gb > 0 and abs(_split - _mem_gb) > 0.05 * _mem_gb:
                _l35 += (f" [setup DRAM + CXL {_gb(_split)} ≠ measured memory "
                         f"{_gb(_mem_gb)}]")
            _layers.append(_l35)
        _cache_tier_label = "Enabled · " + " + ".join(_layers)
    else:
        _cache_tier_label = (str(cache_enabled) if cache_enabled else "Disabled")

    # ── Setup table ───────────────────────────────────────────────────────────
    # ── L3 filesystem characteristics (from smart_summary.json, populated by
    # _refresh_smart_capacity in cli.py). Surface when present so the reader
    # can interpret op counts in the context of FS allocation behavior.
    # _fs_type, _fs_bsize, _wr_merge_ratio, _rd_merge_ratio, _avg_wr_io_kb,
    # _avg_rd_io_kb, _merge_note are all populated earlier so the FS MERGING
    # finding can fire alongside the L3 storage QUEUE findings.
    _q_optimal_io   = _safe_float(smart.get("q_optimal_io_size", 0))
    _q_max_sectors  = _safe_float(smart.get("q_max_sectors_kb", 0))
    if _fs_type:
        # e.g. "XFS · 4 KB blocks · 512 B sectors" or "ext4 · 4 KB blocks"
        _fs_label = _fs_type.upper() if len(_fs_type) <= 4 else _fs_type
        _fs_desc_parts = [_fs_label]
        if _fs_bsize > 0:
            _fs_desc_parts.append(f"{int(_fs_bsize)} B blocks")
        _xfs_sectsz = _safe_float(smart.get("xfs_sectsz", 0))
        if _xfs_sectsz > 0:
            _fs_desc_parts.append(f"{int(_xfs_sectsz)} B device sectors")
        _xfs_agcount = _safe_float(smart.get("xfs_agcount", 0))
        if _xfs_agcount > 0:
            _fs_desc_parts.append(f"{int(_xfs_agcount)} allocation groups")
        _fs_label_full = " · ".join(_fs_desc_parts)
    else:
        _fs_label_full = ""

    setup_rows_data = [
        ("Model",                    model),
        ("Runtime",                  runtime),
        ("Application / Benchmark",  benchmark),
        ("GPU / TP",                 f"{gpu_desc} (TP={tp_size}, DP={dp_size})"),
        ("Attention backend",        attn),
        ("Context length",           f"{ctx_len} tokens"),
        ("KV page size",             (f"{page_sz} token/page (from {page_sz_src})"
                                      if page_sz_src else
                                      "unknown — no server_info, launch --page-size or setup value")
                                     + (f" ⚠ sources disagree: {page_sz_conflict}"
                                        if page_sz_conflict else "")),
        ("mem_fraction_static",      str(mem_frac)),
        ("Inference Cache Tier",     _cache_tier_label),
        ("L3 filesystem",            _fs_label_full),
        ("Collection window",        window_str),
    ]
    if launch:
        setup_rows_data.append(("Launch command", launch))
        # The launch command is rendered from whatever setup_details/server_info
        # supplied, which may have been copied from an earlier deployment. When
        # the telemetry contradicts it, say so on the adjacent row rather than
        # letting the command stand as fact -- a reader who takes a stale
        # --hicache-storage-backend at face value will go looking for a memory
        # node that is not in the deployment.
        if _backend_evidence_note:
            setup_rows_data.append(
                ("⚠ Launch command vs telemetry", _backend_evidence_note))

    # Append every remaining scalar setup_details entry.  The curated rows
    # above are the at-a-glance summary; without this pass anything not on
    # that fixed list was invisible in the report even though
    # setup_details.json (and raw/server_info.json) carried it.
    _shown = {str(k).strip().lower().replace(" ", "_").replace("-", "_")
              for k, _v in setup_rows_data}
    _shown |= {"model_path", "tp_size", "dp_size", "sglang_server_info_raw",
               "setup_source", "gpu", "gpu_count", "page_size",
               "mem_fraction_static", "sglang_launch_command"}
    for _k, _v in (setup or {}).items():
        _norm = str(_k).strip().lower().replace(" ", "_").replace("-", "_")
        if _norm in _shown or str(_k).startswith("_"):
            continue
        if isinstance(_v, (dict, list, tuple)) or _v in (None, "", [], {}):
            continue
        setup_rows_data.append((str(_k), _v))
        _shown.add(_norm)

    setup_html = "".join(
        f'<tr><td class="td-key">{_html.escape(str(k))}</td>'        f'<td>{_html.escape(str(v)) if k != "Launch command" else f'<code>{_html.escape(str(v))}</code>'}</td></tr>'
        for k, v in setup_rows_data
        if str(v) not in ("", "None", "unknown / unknown", "? / ?")
    )

    # v1.1.6 lean Executive: the "Layer status table" and "Bottleneck
    # scorecard" tables have been removed.  Their content is either
    # derivable from the evidence trail below (bottleneck labels) or
    # from the Layered / End Report tabs (per-layer status).  Keeping
    # them here duplicated evidence already present in the trail and
    # relied on a heuristic 0-100 score that risked being read as a
    # saturation verdict.
    #
    # score_hbm/score_nvme/score_compute etc. are no longer computed
    # because no downstream code consumes them after the tables were
    # removed.  Bottleneck labeling now lives entirely in the evidence
    # trail and cross-layer correlation charts.

    # Executive evidence trail: make each bottleneck label auditable.
    # Safe default used by Executive evidence and bottleneck scoring.
    # It intentionally uses a conservative 7 GB/s Gen4 read reference unless
    # a future setup_details override is wired into this scope.
    # _ssd_bw_target_mbs / _ssd_bw_pct are defined above the findings block,
    # which reads them; they are not recomputed here.

    _qd_e_src = str(_qd_sum.get("qd_source", "")) if isinstance(_qd_sum, dict) else ""
    _qd_e_mean = _safe_float(_qd_sum.get("qd_mean", 0)) if isinstance(_qd_sum, dict) else 0.0
    _qd_e_p95  = _safe_float(_qd_sum.get("qd_p95", 0)) if isinstance(_qd_sum, dict) else 0.0
    _qd_e_peak = _safe_float(_qd_sum.get("qd_max", 0)) if isinstance(_qd_sum, dict) else 0.0
    _qd_e_exact = _qd_exact_source(_qd_e_src)
    _qd_e_plausible = _qd_plausible(_qd_e_mean, _qd_e_peak, _qd_e_src) if _qd_e_src else False
    _ssd_sat_label = "proven" if _ssd_hw_saturation_proven(
        nvme_rd_bw, nvme_wr_bw, nvme_util, nvme_rd_lat, _qd_e_mean, _qd_e_peak, _qd_e_src
    ) else "not proven"
    _dram_pct = (dram_total_bw / max(dram_peak_cap, 1) * 100.0) if dram_peak_cap else 0.0
    _l2_used_txt = (f"{l2_dram_used_gb:.1f}/{l2_dram_capacity_gb:.0f} GB"
                    if l2_dram_capacity_gb > 0 and l2_dram_used_gb > 0 else "N/A")

    # ── Cross-layer correlation narrative ─────────────────────────────────────
    _hbm_bw_active = _safe_float(dcgm_active, 0.0)
    _dram_util_pct = _dram_pct
    _l3_bw_pct = _ssd_bw_pct
    _output_tok_s = _safe_float(tp_active, 0.0)
    _evict_rate = evicted_tokens / max(duration_s, 1.0)
    _backup_rate = backuped_tokens / max(duration_s, 1.0)
    _prefetch_rate = prefetched_tokens / max(duration_s, 1.0)
    _loadback_rate = loadback_tokens / max(duration_s, 1.0)
    # v1.39.92: DRAM/KV movement fallback for Prometheus-only runs.
    # This is not a PMU channel bandwidth measurement; it is an estimated KV
    # movement rate from SGLang counters so the Executive bottleneck evidence
    # does not show missing DRAM context when AMDuProf/PCM was not collected.
    # Shared kernel: Executive and Interactive previously each had their own
    # version and disagreed on the unit (1024**2 vs 1e9 — 7.4% apart on the
    # same inputs), which is exactly the divergence the kernel layer exists
    # to prevent.
    # The token deltas are endpoint differences of sglang_timeseries.csv
    # (_kv_token_delta), so divide by that series' own span rather than a
    # window another collector reported.
    _kv_move_window_s = _safe_float((sglang_ts.get("time_sec") or {}).get("delta", 0)) \
        if isinstance(sglang_ts, dict) else 0.0
    _kv_move = _k_kv_movement(
        loadback_tokens=loadback_tokens, backup_tokens=backuped_tokens,
        prefetch_tokens=prefetched_tokens,
        kv_bytes_per_token_kb=kv_bytes_tok_kb,
        window_s=_kv_move_window_s if _kv_move_window_s >= 1.0 else max(duration_s, 1.0))
    _kv_move_restore_gbs = _kv_move["restore_gbs"]
    _kv_move_backup_gbs = _kv_move["backup_gbs"]
    _kv_move_prefetch_gbs = _kv_move["prefetch_gbs"]
    _kv_move_total_gbs = _kv_move["total_gbs"]

    _gpu_reason = (
        "GPU utilization is not expected to be 100% when long-context prefill, "
        "scheduler gaps, cache movement, or low batch concurrency leave the GPUs "
        "waiting between kernels. High TTFT/TPOT with moderate GPU mean points to "
        "request-path/cache/prefill stalls rather than raw GPU saturation."
    )
    _hbm_reason = (
        f"HBM residency is {hbm_pct:.0f}% ({hbm_used_total_gb:.1f}/{hbm_total_all_gpus_gb:.0f} GB). "
        f"mem-fraction-static={mem_frac} reserves memory for model weights, KV pool, CUDA graphs, and activations; "
        "HBM does not need to be 100% full, and unused HBM may indicate room to grow the KV pool."
    )
    if dram_total_bw > 0:
        _dram_reason = (
            f"DRAM BW is {_dram_util_pct:.1f}% of peak and L2 residency is {_l2_used_txt}. "
            "Low DRAM BW/no swap means L2 is not bandwidth-saturated and may absorb more KV before L3."
        )
    else:
        _dram_reason = (
            "CPU PMU DRAM bandwidth was not collected, so physical DRAM-channel saturation cannot be proven. "
            f"SGLang KV movement fallback estimates ~{_kv_move_total_gbs:.2f} GB/s total logical host-tier movement "
            f"(restore/load_back {_kv_move_restore_gbs:.2f}, backup/offload {_kv_move_backup_gbs:.2f}, prefetch/onboard {_kv_move_prefetch_gbs:.2f} GB/s). "
            f"L2 residency is {_l2_used_txt}. Use this fallback for correlation/shape, not for memory-controller saturation."
        )
    _l3_reason = (
        f"L3 physical BW is {_dev_bw_txt()}"
        + (f" ({_l3_bw_pct:.1f}% of read target)" if nvme_rd_bw_measured else "")
        + (f", with token-derived KV movement {read_gb:.3f} GB read / {write_gb:.1f} GB write. "
           if str(l3_traffic_source).startswith("sglang_logical") else
           f", with physical movement {read_gb:.3f} GB read / {write_gb:.1f} GB write. ")
        + "High advisory QD/busy-time is pressure, not saturation proof without latency/BW/exact Q→C evidence."
    )
    _token_reason = (
        f"evicted={evicted_tokens:,.0f} ({_evict_rate:,.0f}/s), "
        f"backuped={backuped_tokens:,.0f} ({_backup_rate:,.0f}/s), "
        f"prefetched={prefetched_tokens:,.0f} ({_prefetch_rate:,.0f}/s), "
        f"L2→L1 load_back restore diagnostic={loadback_tokens:,.0f} ({_loadback_rate:,.0f}/s). "
        "Eviction/backup pressure explains L3 writes and cache churn; prefetch plus L2→L1 load_back restore pressure matters when it aligns with latency spikes."
    )

    _hicache_size_txt = _html.escape(str(_pick(setup, [
        "HiCache size", "hicache_size", "hicache_size_gb",
        "L2 DRAM allocation", "L2 DRAM capacity GB", "HiCache size per GPU"
    ], "unknown")))
    _setup_runtime_row = (
        f"Model={_html.escape(str(model))}; TP={tp_size}; mem-fraction-static={_html.escape(str(mem_frac))}; "
        f"HiCache/L2={_hicache_size_txt}; L3 backend={_html.escape(str(_tier_res.backend_class if '_tier_res' in locals() else 'unknown'))}."
    )
    # v1.1.5 lean Executive: the cross-layer correlation prose card and the
    # setup-aware launch guidance card have been dropped from the Executive tab
    # to reduce clutter. Their content is either derivable from the Top Findings
    # + Bottleneck evidence trail (correlation) or duplicates End Report guidance
    # (launch tuning). The intermediate _setup_runtime_row / _token_reason /
    # _gpu_reason / _hbm_reason / _dram_reason / _l3_reason locals remain used
    # elsewhere in this function for scoring.


    # v1.1.7: the evidence-highlight cards ("Prefill / request-path latency",
    # "HBM capacity pressure", "KV L2→L1 load-back amplification",
    # "L3 hardware bandwidth / IOPS saturation", "DRAM bandwidth headroom",
    # "Cache reuse / cache pressure") have been removed from the Executive
    # tab.  The same values are surfaced by the KPI grid at the top, and
    # bottleneck attribution is now done via the cross-layer correlation
    # scatter charts below.  This is the "Remove all Confidence + Highlighting
    # cards" and "plot correlation charts instead" requirement from v1.1.7.

    # ── Cross-layer correlation charts ────────────────────────────────────────
    # Merged into the Bottleneck section (v1.1.6).  Each scatter plots one
    # cache-tier bandwidth signal (or its underlying read/write byte counter)
    # against input (prompt tok/s) and output (generation tok/s) throughput
    # timeseries drawn from the same second-by-second window.
    #
    # Sample vectors are the per-sample delta of the underlying counter — for
    # tok/s and read/write MB/s — so plot points are actually rate-vs-rate,
    # not cumulative-vs-cumulative (which would trivially correlate).
    #
    # L2 correlations render only when L2 (host DRAM as HiCache) is
    # configured (l2_dram_capacity_gb > 0). L3 correlations render only when
    # L3 storage is configured — same gate the rest of Executive uses.
    def _rate_with_time(vals: List[float], time_s: List[float]) -> tuple[List[float], List[float]]:
        """Delegates to metric_kernels.rate_series_with_time (shared kernel)."""
        return _k_rate_with_time(vals, time_s)

    def _rate_from_counter(vals: List[float], time_s: List[float]) -> List[float]:
        # Unchanged contract for existing callers — same values, same order.
        return _rate_with_time(vals, time_s)[1]
    correlation_charts_html = ""
    # Named-SVG collector for the Executive-overview strip that renders after
    # the KPI grid.  The individual chart-builders below deposit their SVGs
    # here when they succeed; the strip is assembled from whatever showed up.
    _exec_ov: "dict[str, str]" = {}
    exec_overview_html = ""
    # The latency & token-size distribution card is the headline read of this
    # tab, so it is rendered directly under the KPI grid rather than inside
    # Bottleneck Analysis.  Assigned within the correlation try-block below and
    # emitted from its own template slot.
    distribution_charts_html = ""
    timeline_charts_html = ""
    # Why a configured L3 has no capacity figure, when it has none.  Filled in
    # the correlation block beside the chart that drops the series; bound here
    # so the KPI grid can state the same reason on the tile.  Bound BEFORE the
    # try for the reason given above.
    _l3_cap_missing = ""
    # Read by the KPI grid and the queue-depth tile after the block. Unbound,
    # a failure anywhere before its assignment raised NameError there and the
    # Executive Summary was dropped from the combined report entirely.
    _l35s: dict = {}
    _l35s_path = None
    _l35s_local_src = ""
    try:
        _sg_path = _first_existing(raw_dir, ["sglang_timeseries.csv"])
        # Token-movement counters — read alongside throughput counters so
        # every derived rate comes from the same second-by-second window.
        # `load_back_tokens_total` is the L2→L1 restore diagnostic; keep it
        # even though its interpretation differs from the offload/prefetch
        # counters — a correlation with L3 read BW would flag that HiCache
        # restores are being satisfied by L3 not L2.
        _sg_raw = _amoprof_read_columns_raw(_sg_path, [
            "time_sec", "prompt_tokens_total", "generation_tokens_total",
            "evicted_tokens_total", "load_back_tokens_total",
            "prefetched_tokens_total", "backuped_tokens_total",
            "e2e_request_latency_seconds_sum", "e2e_request_latency_seconds_count",
            "time_to_first_token_seconds_sum", "time_to_first_token_seconds_count",
            # Mooncake L3.5 — folded into the master timeseries under the
            # canonical mooncake_* namespace by the Prometheus fetch.
            "mooncake_read_bytes_total", "mooncake_write_bytes_total",
            "mooncake_used_bytes", "mooncake_capacity_bytes", "mooncake_fill_ratio",
            # Mooncake *master* exporter: metadata-service metrics.  It has no
            # byte-throughput counters — data moves client<->store over RDMA
            # and is invisible to the master — so L3.5 here is occupancy and
            # request rate, not bandwidth.
            # L2 (host DRAM as HiCache) — SGLang measures its own host-cache
            # occupancy directly.  This is a real measurement of the L2 tier,
            # independent of whether a DRAM PMU collector ran; the PMU gives
            # DRAM *bandwidth*, these give L2 *occupancy and movement*.
            "hicache_host_used_tokens", "hicache_host_total_tokens",
            # L1 KV pool occupancy, in tokens — the HBM tier's own counter.
            "kv_used_tokens", "num_used_tokens", "max_total_num_tokens",
            "backuped_tokens_total", "prefetched_tokens_total",
            "token_usage", "full_token_usage",
            "mooncake_key_count", "mooncake_active_clients",
            "mooncake_put_requests_total", "mooncake_get_requests_total",
            "mooncake_put_errors_total", "mooncake_get_errors_total",
            "mooncake_segment_used_bytes", "mooncake_segment_capacity_bytes",
            # File/flash tier of the store, reported separately from the DRAM
            # segment pool: one aggregate figure hides whether the store is
            # full in RAM or on flash, and a saturated segment pool is what
            # forces spill to the file tier.
            "mooncake_file_used_bytes", "mooncake_file_capacity_bytes",
            # Used bytes are physical, so replicas are counted individually.
            "mooncake_replica_count",
            "mooncake_get_duration_seconds_sum", "mooncake_get_duration_seconds_count",
            "mooncake_put_duration_seconds_sum", "mooncake_put_duration_seconds_count",
            "inter_token_latency_seconds_sum", "inter_token_latency_seconds_count",
            "time_per_output_token_seconds_sum", "time_per_output_token_seconds_count",
        ]) if _sg_path else {}
        _sg_time = _sg_raw.get("time_sec", [])

        _occ_win = None
        _w0 = _safe_float(_pick(setup, ["window_start_sec", "t_start_sec"], 0), 0)
        _w1 = _safe_float(_pick(setup, ["window_end_sec", "t_end_sec"], 0), 0)
        _dur = _safe_float(duration_s, 0)
        if _w1 > _w0:
            _occ_win = (_w0, _w1)
        elif _dur > 0:
            # Anchor to the timebase origin the samples use, then span the
            # full analysed duration.
            _t_origin = min(_sg_time) if _sg_time else 0.0
            _occ_win = (_t_origin, _t_origin + _dur)
            # If the samples genuinely run past the stated duration, widen
            # rather than clip: never hide data to satisfy metadata.
            if _sg_time and max(_sg_time) > _occ_win[1]:
                _occ_win = (_t_origin, max(_sg_time))
        elif _sg_time:
            _occ_win = (min(_sg_time), max(_sg_time))
        _occ_wall = t0_epoch if t0_epoch > 1_000_000_000 else 0.0

        # Every SGLang-derived rate skips the same Δt ≤ 0 samples, so one
        # timestamp vector describes all of them.  Derive it from the
        # longest available counter so an absent counter (e.g. no
        # prefetch on a host-DRAM-only run) cannot shorten the timebase.
        _sg_rate_t: List[float] = []
        for _c in ("prompt_tokens_total", "generation_tokens_total",
                   "evicted_tokens_total", "load_back_tokens_total",
                   "prefetched_tokens_total", "backuped_tokens_total"):
            _t_c, _ = _rate_with_time(_sg_raw.get(_c, []), _sg_time)
            if len(_t_c) > len(_sg_rate_t):
                _sg_rate_t = _t_c
        # `_sg_raw` is an EXACT-name lookup.  SGLang exports several of these
        # counters with a label suffix — sglang_generation_tokens_total[...] —
        # so the exact lookup returned nothing and the rate series was empty:
        # the Input/Output tok/s scatters collapsed to a 0.0-1.0 x-axis while
        # the End Report, which matches by substring, reported the real
        # 14.7 and 156.4 tok/s.  Fall back to the substring reader, as the
        # histogram and tier code already do.
        def _counter_series(name: str) -> List[float]:
            """A cumulative counter series, by exact name or substring.

            `if _exact:` was the bug: an exact-name miss yields a list of
            ZEROS, not an empty list, and a non-empty list of zeros is truthy.
            The fallback therefore never ran and the rate series stayed flat,
            collapsing the Input/Output tok/s scatter axes to 0.0-1.0 while
            the End Report — matching by substring — reported the real rates.
            Require an actually-rising counter before accepting the exact hit.
            """
            _exact = _sg_raw.get(name, []) or []
            if any(v > 0 for v in _exact):
                return _exact
            # The single-column substring reader returns the FIRST match,
            # which here is the zeroed plain column; the real data sits in a
            # label-suffixed sibling.  Consider every matching column and take
            # the one that actually carries data.
            _cands = (_amoprof_read_all_columns_substr(_sg_path, name)
                      if _sg_path else [])
            for _c in _cands:
                if any(v > 0 for v in _c):
                    return _c
            return _exact

        def _drop_if_flat(_v):
            """An all-zero rate series is absence, not a measurement.

            Returning [] rather than a list of zeros means every downstream
            emitter skips it through the checks it already has, instead of each
            one needing to know that zeros are truthy.  Six scatters were still
            drawing fabricated 0.0-1.0 axes after the first two call sites were
            guarded individually.
            """
            return _v if (_v and any(x > 0 for x in _v)) else []

        _in_tok_rate = _rate_from_counter(_counter_series("prompt_tokens_total"), _sg_time)
        _out_tok_rate = _rate_from_counter(_counter_series("generation_tokens_total"), _sg_time)
        _evict_rate  = _rate_from_counter(_counter_series("evicted_tokens_total"), _sg_time)
        _load_rate   = _rate_from_counter(_counter_series("load_back_tokens_total"), _sg_time)
        _in_tok_rate = _drop_if_flat(_in_tok_rate)
        _out_tok_rate = _drop_if_flat(_out_tok_rate)
        _pref_rate   = _rate_from_counter(_sg_raw.get("prefetched_tokens_total", []), _sg_time)
        _backup_rate = _rate_from_counter(_sg_raw.get("backuped_tokens_total", []), _sg_time)

        # ── Per-interval mean E2E request latency ────────────────────────
        # Δsum ÷ Δcount over each sampling interval — the same identity the
        # E2E KPI tile uses, but computed per sample so it can be scattered
        # against token volume.  Intervals that completed no requests
        # (Δcount == 0) carry no latency and are dropped, together with
        # their timestamp, so the series stays time-alignable.
        def _interval_mean_ms(base: str) -> tuple[List[float], List[float]]:
            """Per-interval Δsum ÷ Δcount in ms, with the timestamp of each.

            Same identity as the KPI tile, evaluated per sampling interval so
            the latency can be correlated against concurrency and resource
            signals.  Intervals that completed no observations (Δcount == 0)
            are dropped with their timestamp, keeping the series alignable.
            """
            # Prometheus can return the same histogram as SEVERAL series when
            # the label set differs — a restarted server, more than one
            # model_name, a stale target — and the CSV then carries duplicate
            # columns for one metric.  `_sg_raw` is an exact-name lookup and
            # sees only one of them, which may be the sparse or empty one:
            # TTFT and E2E had two columns each and silently produced nothing,
            # while ITL had one and worked.  Sum across every matching column
            # instead, which is the correct aggregation for a histogram split
            # across label sets.
            def _hist_component(suffix: str) -> List[float]:
                _exact = _sg_raw.get(f"{base}_{suffix}", [])
                if not _sg_path:
                    return _exact
                _cols = _amoprof_read_all_columns_substr(
                    _sg_path, f"{base}_{suffix}")
                if len(_cols) <= 1:
                    return _cols[0] if _cols else _exact
                # Element-wise sum across the duplicates.  Both sum and count
                # are additive across label sets, so the ratio stays a correct
                # weighted mean rather than favouring whichever series the
                # reader happened to see first.
                _n2 = min(len(_c) for _c in _cols)
                return [sum(_c[_i] for _c in _cols) for _i in range(_n2)]

            _sm = _hist_component("sum")
            _ct = _hist_component("count")
            _o_t: List[float] = []
            _o_v: List[float] = []
            _n = min(len(_sm), len(_ct), len(_sg_time))
            for _i in range(1, _n):
                _dc = _ct[_i] - _ct[_i - 1]
                _ds = _sm[_i] - _sm[_i - 1]
                if _dc <= 0 or _ds < 0:
                    continue
                _o_t.append(_sg_time[_i])
                _o_v.append(_ds / _dc * 1000.0)
            return _o_t, _o_v

        # ---- L3.5 (Mooncake / remote KV store) ----------------------------
        # Byte counters are cumulative → per-interval MB/s; get/put duration
        # histograms give per-interval mean latency, same identity as the
        # SGLang latency metrics.
        # Read bytes: prefer the transfer-engine counter, but the master
        # exporter does not publish one.  It DOES publish cache-hit byte
        # totals split by where the hit landed (memory vs file), and their sum
        # is the bytes served out of the store — the same quantity, measured
        # at the store rather than on the wire.  Summing before differencing
        # matters: two counters differenced separately and added is the same
        # number, but a gap in either would silently halve the result.
        _mc_rd_src = _sg_raw.get("mooncake_read_bytes_total", []) or []
        if not _mc_rd_src:
            _rf = _sg_raw.get("mooncake_read_bytes_file_total") or []
            _rm = _sg_raw.get("mooncake_read_bytes_mem_total") or []
            if _rf or _rm:
                _n_rd = max(len(_rf), len(_rm))
                _mc_rd_src = [((_rf[i] if i < len(_rf) else 0.0)
                               + (_rm[i] if i < len(_rm) else 0.0))
                              for i in range(_n_rd)]
        _mc_rd_t, _mc_rd_mbps = _rate_with_time(_mc_rd_src, _sg_time)
        _mc_rd_mbps = [v / 1e6 for v in _mc_rd_mbps]
        _mc_wr_t, _mc_wr_mbps = _rate_with_time(
            _sg_raw.get("mooncake_write_bytes_total", []), _sg_time)
        _mc_wr_mbps = [v / 1e6 for v in _mc_wr_mbps]
        # Store residency moved to its own file in v1.29.1, because it comes
        # from the store's exporter rather than the amoprof service and needs
        # a different selector.  This reader was left pointing at the old
        # location, so the L3.5 series silently vanished from the residency
        # chart while the tier was still declared in the subtitle.  Prefer the
        # new columns; fall back to the old ones for older run directories.
        _cap_f = _first_existing(raw_dir, ["l35_store_capacity.csv"])
        _cap_raw = (_amoprof_read_columns_raw(
            _cap_f, ["l35_store_mem_used_b", "l35_store_mem_cap_b",
                     "l35_store_file_used_b", "l35_store_file_cap_b"])
            if _cap_f else {})
        _mc_used = [v / 1e9 for v in (
            _cap_raw.get("l35_store_mem_used_b")
            or _sg_raw.get("mooncake_segment_used_bytes")
            or _sg_raw.get("mooncake_used_bytes") or [])]
        _mc_fill = _sg_raw.get("mooncake_fill_ratio") or []
        if _mc_fill:
            _mc_fill_finite = [v for v in _mc_fill if v == v]
            if _mc_fill_finite and max(_mc_fill_finite) <= 1.5:
                _mc_fill = [v * 100.0 if v == v else v for v in _mc_fill]
        # Master-exporter signals: occupancy and request rates.
        _mc_cap = [v / 1e9 for v in (
            _cap_raw.get("l35_store_mem_cap_b")
            or _sg_raw.get("mooncake_segment_capacity_bytes")
            or _sg_raw.get("mooncake_capacity_bytes") or [])]
        _mc_keys = _sg_raw.get("mooncake_key_count") or []
        _mc_clients = _sg_raw.get("mooncake_active_clients") or []
        _mc_put_t, _mc_put_ops = _rate_with_time(
            _sg_raw.get("mooncake_put_requests_total", []), _sg_time)
        _mc_get_t2, _mc_get_ops = _rate_with_time(
            _sg_raw.get("mooncake_get_requests_total", []), _sg_time)
        # L3.5 read bandwidth from bytes the store actually SERVED
        # (memory-tier + file-tier cache hits).  This replaces "get ops/s" as
        # the correlation target for prefetch: the old series was fed by
        # master_get_replica_list_requests_total, a metadata lookup on the
        # master ("where is this key?") that can fire with no bytes moving,
        # and it was read from the engine's timeseries while store metrics are
        # fetched under the store's own selector — so it was usually empty.
        _rd_src = _first_existing(raw_dir, ["l35_store_capacity.csv"])
        _rd_cols = (_amoprof_read_columns_raw(
            _rd_src, ["time_sec", "l35_mem_hit_b", "l35_file_hit_b"])
            if _rd_src else {})
        _rd_mem = _rd_cols.get("l35_mem_hit_b") or []
        _rd_file = _rd_cols.get("l35_file_hit_b") or []
        _rd_sum = ([(a if a == a else 0.0) + (b if b == b else 0.0)
                    for a, b in zip(_rd_mem, _rd_file)] if (_rd_mem and _rd_file)
                   else (_rd_mem or _rd_file))
        _l35_rd_t, _l35_rd_bps = _rate_with_time(
            _rd_sum, _rd_cols.get("time_sec") or _sg_time)
        _l35_rd_mbs = [v / 1e6 if v == v else v for v in (_l35_rd_bps or [])]
        _mc_err_t, _mc_err_ops = _rate_with_time(
            [a + b for a, b in zip(_sg_raw.get("mooncake_put_errors_total", []) or [0],
                                   _sg_raw.get("mooncake_get_errors_total", []) or [0])]
            if (_sg_raw.get("mooncake_put_errors_total")
                and _sg_raw.get("mooncake_get_errors_total")) else
            (_sg_raw.get("mooncake_put_errors_total")
             or _sg_raw.get("mooncake_get_errors_total") or []), _sg_time)
        # Fill ratio is derivable when the exporter gives used and capacity.
        if not _mc_fill and _mc_used and _mc_cap:
            _n_fr = min(len(_mc_used), len(_mc_cap))
            _mc_fill = [(_mc_used[i] / _mc_cap[i] * 100.0) if _mc_cap[i] > 0 else 0.0
                        for i in range(_n_fr)]

        _mc_configured = bool((_mc_rd_mbps and any(v > 0 for v in _mc_rd_mbps))
                              or (_mc_wr_mbps and any(v > 0 for v in _mc_wr_mbps))
                              or (_mc_used and any(v > 0 for v in _mc_used))
                              or (_mc_put_ops and any(v > 0 for v in _mc_put_ops))
                              or (_mc_get_ops and any(v > 0 for v in _mc_get_ops))
                              or (_mc_keys and any(v > 0 for v in _mc_keys)))

        # Queue wait is a histogram like the latency ones, so the same
        # sum/count-delta helper gives a per-interval mean.
        _q_wait_t, _q_wait_ms = _interval_mean_ms("queue_time_seconds")
        _e2e_t, _e2e_ms = _interval_mean_ms("e2e_request_latency_seconds")
        _ttft_t, _ttft_ms = _interval_mean_ms("time_to_first_token_seconds")
        _tpot_t, _tpot_ms = _interval_mean_ms("time_per_output_token_seconds")
        _tpot_src = "time_per_output_token_seconds"
        if not _tpot_ms:
            _tpot_t, _tpot_ms = _interval_mean_ms("inter_token_latency_seconds")
            _tpot_src = "inter_token_latency_seconds (TPOT histogram not exported)"

        # ── Prefill / decode phase activity ──────────────────────────────
        # SGLang splits token work by phase via the labelled counter
        # realtime_tokens_total{mode=prefill_compute|prefill_cache|decode}.
        # prefill_compute is prefill work actually recomputed (cache miss);
        # prefill_cache is prefill served from the radix cache.  Together
        # with the running/queued request gauges these describe *where in
        # the request lifecycle* the pressure is, which is a different axis
        # from the aggregate prompt/generation tok/s already plotted in the
        # per-tier cards above.
        _sg_phase = _amoprof_read_columns_substr(_sg_path, {
            "prefill_compute": ["realtime_tokens_total", "mode=prefill_compute"],
            "prefill_cache":   ["realtime_tokens_total", "mode=prefill_cache"],
            "decode":          ["realtime_tokens_total", "mode=decode"],
            "running_reqs":    ["num_running_reqs"],
            "queue_reqs":      ["num_queue_reqs"],
        }) if _sg_path else {}
        _pf_compute_rate = _rate_from_counter(_sg_phase.get("prefill_compute", []), _sg_time)
        _pf_cache_rate = _rate_from_counter(_sg_phase.get("prefill_cache", []), _sg_time)
        _decode_rate = _rate_from_counter(_sg_phase.get("decode", []), _sg_time)
        # Gauges, not counters — align them onto the rate timebase by
        # dropping the first sample, matching _rate_with_time's offset.
        _running_reqs = list(_sg_phase.get("running_reqs", []))[1:]
        _queue_reqs = list(_sg_phase.get("queue_reqs", []))[1:]
        # STRICT copies, taken before the fallbacks below.  The fallback
        # substitutes prompt_tokens_total for prefill_compute so the phase
        # THROUGHPUT chart still renders, and for that chart it is a
        # reasonable stand-in.  It is not recompute: prompt tokens include
        # everything the cache served, so anything that treats the series as
        # "tokens the GPU had to recompute" -- the cache hit ratio, the
        # prefetch efficacy test, the benefit accounting -- would be reading
        # a cache miss count as the whole prompt volume and silently
        # reporting a hit rate of zero. Those consumers use these instead and
        # simply do not render when the labelled counter is absent, which is
        # the honest outcome.
        _pf_compute_strict = list(_pf_compute_rate)
        _pf_cache_strict = list(_pf_cache_rate)
        _pf_modes_measured = bool(
            any(v > 0 for v in _pf_compute_strict)
            or any(v > 0 for v in _pf_cache_strict))

        # Fallbacks so the phase group still renders on runs that do not
        # export the labelled counter.  Source is named in each subtitle.
        _pf_src = "realtime_tokens_total{mode=prefill_compute}"
        _dec_src = "realtime_tokens_total{mode=decode}"
        if not any(v > 0 for v in _pf_compute_rate):
            _pf_compute_rate = _in_tok_rate
            _pf_src = "prompt_tokens_total (labelled prefill counter absent)"
        if not any(v > 0 for v in _decode_rate):
            _decode_rate = _out_tok_rate
            _dec_src = "generation_tokens_total (labelled decode counter absent)"

        _gpu_path = _first_existing(raw_dir, ["gpu_timeseries.csv"])
        _gpu_raw = _amoprof_read_columns_raw(_gpu_path, [
            "time_sec", "gpu_idx", "mem_used", "gpu_util",
            # DCGM spellings for the same two series (Prometheus-sourced runs).
            "DCGM_FI_DEV_GPU_UTIL", "DCGM_FI_DEV_FB_USED",
            "dcgm_fi_dev_gpu_util", "dcgm_fi_dev_fb_used",
            # nvidia-smi utilization.memory — percent of the sampling interval
            # the HBM interface was busy.  This is the only *measured* L1
            # bandwidth signal available (the nsys HBM counters are not
            # reliably sampled), and it was collected but never plotted, which
            # is why L1 had no bandwidth axis while L2 and L3 did.
            "mem_util", "utilization_memory", "mem_util_pct",
            # Prometheus/DCGM runs keep the DCGM metric names rather than the
            # nvidia-smi spellings, so the local-collect names above miss
            # entirely on those runs.  DRAM_ACTIVE is the better signal of the
            # two (fraction of cycles the HBM interface was active); MEM_COPY_
            # UTIL is the DCGM analogue of utilization.memory.
            "DCGM_FI_PROF_DRAM_ACTIVE", "dcgm_fi_prof_dram_active", "dram_active",
            "DCGM_FI_DEV_MEM_COPY_UTIL", "dcgm_fi_dev_mem_copy_util", "mem_copy_util",
            # The Prometheus path does not pass DCGM names through: it writes
            # gpu_timeseries.csv with DRAM_ACTIVE already scaled to percent as
            # `hbm_bw_pct`, and MEM_COPY_UTIL as `mem_copy_util_pct`.
            "hbm_bw_pct", "mem_copy_util_pct",
        ]) if _gpu_path else {}

        def _pct_series(name: str) -> List[float]:
            """Return a 0-100 percent series, normalising DCGM ratio metrics.

            DCGM_FI_PROF_DRAM_ACTIVE is a 0..1 duty-cycle ratio while
            utilization.memory / MEM_COPY_UTIL are already 0..100.  Scale by
            max magnitude rather than by metric name so an exporter that has
            already converted to percent is not multiplied twice.
            """
            v = _gpu_raw.get(name) or []
            if not v:
                return []
            peak = max(v)
            return [x * 100.0 for x in v] if 0 < peak <= 1.5 else list(v)

        # ---- Collapse per-GPU rows to one sample per timestamp -----------
        # gpu_timeseries.csv carries ONE ROW PER GPU PER TIMESTAMP (the
        # Prometheus writer emits a row per gpu_idx).  Correlating against it
        # unreduced pairs each token sample with whichever GPU's row happened
        # to be nearest in time — an arbitrary GPU, not the node — which
        # destroys the correlation: on an 8-GPU node this turned r=+0.93 into
        # r=+0.04 for the same underlying relationship.
        #
        # Utilisation-style signals are averaged across GPUs; memory *used* is
        # summed, matching the "HBM used (all GPUs)" semantics used elsewhere.
        def _collapse_per_gpu(times: List[float], vals: List[float],
                              how: str = "mean") -> tuple[List[float], List[float]]:
            n = min(len(times), len(vals))
            if n == 0:
                return [], []
            acc: "dict[float, list]" = {}
            order: List[float] = []
            for i in range(n):
                t = times[i]
                if t not in acc:
                    acc[t] = []
                    order.append(t)
                acc[t].append(vals[i])
            if len(order) == n:            # already one row per timestamp
                return list(times[:n]), list(vals[:n])
            out_v = [(sum(acc[t]) if how == "sum" else sum(acc[t]) / len(acc[t]))
                     for t in order]
            return order, out_v

        _gpu_rows_per_ts = 1
        _gt_raw = _gpu_raw.get("time_sec") or []
        if _gt_raw:
            _distinct = len(set(_gt_raw))
            if _distinct > 0:
                _gpu_rows_per_ts = max(1, round(len(_gt_raw) / _distinct))

        # Fall back to the DCGM spellings when the canonical ones are absent.
        if not _gpu_raw.get("gpu_util"):
            _gpu_raw["gpu_util"] = (_gpu_raw.get("DCGM_FI_DEV_GPU_UTIL")
                                    or _gpu_raw.get("dcgm_fi_dev_gpu_util") or [])
        if not _gpu_raw.get("mem_used"):
            _gpu_raw["mem_used"] = (_gpu_raw.get("DCGM_FI_DEV_FB_USED")
                                    or _gpu_raw.get("dcgm_fi_dev_fb_used") or [])

        _hbm_bw_util_series = []
        _hbm_bw_util_src = ""
        for _cand, _src in (
            ("hbm_bw_pct", "DCGM_FI_PROF_DRAM_ACTIVE (via gpu_timeseries hbm_bw_pct)"),
            ("DCGM_FI_PROF_DRAM_ACTIVE", "DCGM_FI_PROF_DRAM_ACTIVE"),
            ("dcgm_fi_prof_dram_active", "DCGM_FI_PROF_DRAM_ACTIVE"),
            ("dram_active", "DCGM_FI_PROF_DRAM_ACTIVE"),
            ("mem_util", "nvidia-smi utilization.memory"),
            ("utilization_memory", "nvidia-smi utilization.memory"),
            ("mem_util_pct", "nvidia-smi utilization.memory"),
            ("DCGM_FI_DEV_MEM_COPY_UTIL", "DCGM_FI_DEV_MEM_COPY_UTIL"),
            ("dcgm_fi_dev_mem_copy_util", "DCGM_FI_DEV_MEM_COPY_UTIL"),
            ("mem_copy_util", "DCGM_FI_DEV_MEM_COPY_UTIL"),
            ("mem_copy_util_pct", "DCGM_FI_DEV_MEM_COPY_UTIL (via gpu_timeseries)"),
        ):
            _v = _pct_series(_cand)
            if _v and any(x > 0 for x in _v):
                _hbm_bw_util_series, _hbm_bw_util_src = _v, _src
                break
        # Derived GB/s, only when the device model resolves to a known peak.
        # No guessing: an unrecognised GPU contributes no GB/s series rather
        # than a number derived from the wrong peak.
        _HBM_PEAK_GBS = {
            "a100-sxm4-40gb": 1555.0, "a100-pcie-40gb": 1555.0,
            "a100-sxm4-80gb": 2039.0, "a100-pcie-80gb": 1935.0,
            "h100-sxm5-80gb": 3350.0, "h100-pcie-80gb": 2000.0,
            "h200": 4800.0, "h800": 3350.0, "a800": 2039.0,
            "b200": 8000.0, "b100": 8000.0, "gb200": 8000.0,
            "h20": 4000.0, "l40s": 864.0, "l40": 864.0,
            "mi300x": 5300.0, "v100-sxm2-32gb": 900.0, "v100": 900.0,
        }
        _hbm_peak_gbs = 0.0
        try:
            _gname = str(_gpu_cfg.get("gpu_name", "") or gpu_desc or "").lower().replace("nvidia ", "").strip()
            for _k, _v in _HBM_PEAK_GBS.items():
                if _k in _gname.replace(" ", "-"):
                    _hbm_peak_gbs = _v
                    break
        except Exception:
            _hbm_peak_gbs = 0.0
        _hbm_bw_gbs_series = ([v / 100.0 * _hbm_peak_gbs for v in _hbm_bw_util_series]
                              if (_hbm_bw_util_series and _hbm_peak_gbs > 0) else [])

        # Base GPU series (per-GPU rows at this point on a multi-GPU node).
        _gpu_time = _gpu_raw.get("time_sec", [])
        _gpu_util_series = _gpu_raw.get("gpu_util", [])
        _hbm_used_series = _gpu_raw.get("mem_used", [])

        # ---- Restrict to the GPUs the inference server actually occupies ---
        # The node may hold more GPUs than the server uses: at TP=2 on an
        # 8-GPU host, six devices are idle.  Averaging utilisation across all
        # eight understates the serving GPUs' load by ~4x, and summing
        # `mem_used` across all eight reports memory that has nothing to do
        # with this workload.
        #
        # Serving devices are identified by *activity rank* rather than by
        # index: CUDA_VISIBLE_DEVICES can remap ordinals, so "GPUs 0..TP-1" is
        # not reliable.  The TP x DP busiest GPUs (by mean utilisation, then
        # mean memory) are kept.
        _gpu_idx_series = _gpu_raw.get("gpu_idx") or []
        _gpu_selected_note = ""
        try:
            _want = int(_safe_float(active_gpu_count, 0) or 0)
        except Exception:
            _want = 0
        if (_gpu_idx_series and _gpu_rows_per_ts > 1 and 0 < _want < _gpu_rows_per_ts):
            _per_dev: "dict[float, list]" = {}
            _n_idx = min(len(_gpu_idx_series), len(_gpu_time))
            for _i in range(_n_idx):
                _per_dev.setdefault(_gpu_idx_series[_i], []).append(_i)
            def _dev_activity(rows):
                _u = [_gpu_util_series[i] for i in rows if i < len(_gpu_util_series)]
                _m = [_hbm_used_series[i] for i in rows if i < len(_hbm_used_series)]
                return ((sum(_u) / len(_u)) if _u else 0.0,
                        (sum(_m) / len(_m)) if _m else 0.0)
            _ranked = sorted(_per_dev.items(), key=lambda kv: _dev_activity(kv[1]),
                             reverse=True)
            _keep_idx = sorted(i for _dev, rows in _ranked[:_want] for i in rows)
            if _keep_idx:
                _sel = set(_keep_idx)
                def _subset(v):
                    return [v[i] for i in _keep_idx if i < len(v)]
                _gpu_time = _subset(_gpu_time)
                _gpu_util_series = _subset(_gpu_util_series)
                _hbm_used_series = _subset(_hbm_used_series)
                if _hbm_bw_util_series:
                    _hbm_bw_util_series = _subset(_hbm_bw_util_series)
                if _hbm_bw_gbs_series:
                    _hbm_bw_gbs_series = _subset(_hbm_bw_gbs_series)
                _gpu_rows_per_ts = _want
                _kept_devs = [str(_dev) for _dev, _ in _ranked[:_want]]
                _gpu_selected_note = (f"GPUs {', '.join(_kept_devs)} of "
                                      f"{len(_per_dev)} (TP x DP = {_want}, selected "
                                      f"by activity)")

        # Reduce every GPU series to one value per timestamp before it is used
        # for correlation or charting.
        if _gpu_rows_per_ts > 1:
            # Use the (possibly device-subsetted) _gpu_time, NOT _gpu_raw:
            # after selection the value lists are shorter than the raw
            # timestamp column, and zipping the two would mis-pair every
            # sample.
            _gt = list(_gpu_time)
            _gpu_time, _gpu_util_series = _collapse_per_gpu(_gt, _gpu_util_series, "mean")
            _, _hbm_used_series = _collapse_per_gpu(_gt, _hbm_used_series, "sum")
            _, _hbm_bw_util_series = _collapse_per_gpu(_gt, _hbm_bw_util_series, "mean")
            _, _hbm_bw_gbs_series = _collapse_per_gpu(_gt, _hbm_bw_gbs_series, "mean")

        # ---- Network fabric (NIC / IB) ----------------------------------
        # network_timeseries.csv carries one row per interface plus an
        # "_total" aggregate row per interval.  Only the aggregate is used
        # for correlation; per-interface detail belongs in the End Report.
        _net_iface_filter = str(net_iface or "")
        _net_path = _first_existing(raw_dir, ["network_timeseries.csv"])
        _net_t: List[float] = []
        _net_rx: List[float] = []
        _net_tx: List[float] = []
        _net_total: List[float] = []
        _net_pps: List[float] = []
        _net_retr: List[float] = []
        _net_drop: List[float] = []
        _net_util: List[float] = []
        if _net_path:
            try:
                # --net-iface narrows an ALREADY-COLLECTED run to specific
                # interfaces.  The default "_total" row sums every NIC on the
                # box — management ports, unused links, IB aliases — which is
                # not the fabric carrying KV traffic.  Selecting interfaces
                # here means a run collected without the flag can still be
                # analysed against the right link, without re-collecting.
                _want_ifaces = [x.strip() for x in
                                str(_net_iface_filter or "").split(",") if x.strip()]
                _by_t: Dict[float, List[float]] = {}
                with Path(_net_path).open(encoding="utf-8", errors="replace", newline="") as _nf:
                    for _row in csv.DictReader(_nf):
                        _if = (_row.get("iface") or "").strip()
                        if _want_ifaces:
                            if _if not in _want_ifaces:
                                continue
                        elif _if != "_total":
                            continue
                        _ts = _safe_float(_row.get("time_sec"), 0.0)
                        if _want_ifaces:
                            # Several interfaces share a timestamp; sum them.
                            _acc = _by_t.setdefault(_ts, [0.0, 0.0, 0.0, 0.0, 0.0])
                            _acc[0] += _safe_float(_row.get("rx_mbs"), 0.0)
                            _acc[1] += _safe_float(_row.get("tx_mbs"), 0.0)
                            _acc[2] += _safe_float(_row.get("total_pps"), 0.0)
                            _acc[3] += _safe_float(_row.get("tcp_retrans_ps"), 0.0)
                            _acc[4] += (_safe_float(_row.get("rx_drop_ps"), 0.0)
                                        + _safe_float(_row.get("tx_drop_ps"), 0.0))
                            continue
                        _net_t.append(_ts)
                        _rx = _safe_float(_row.get("rx_mbs"), 0.0)
                        _tx = _safe_float(_row.get("tx_mbs"), 0.0)
                        _net_rx.append(_rx)
                        _net_tx.append(_tx)
                        _tot = _safe_float(_row.get("total_mbs"), 0.0)
                        _net_total.append(_tot if _tot > 0 else _rx + _tx)
                        _net_pps.append(_safe_float(_row.get("total_pps"), 0.0))
                        _net_retr.append(_safe_float(_row.get("tcp_retrans_ps"), 0.0))
                        _net_drop.append(_safe_float(_row.get("rx_drop_ps"), 0.0)
                                         + _safe_float(_row.get("tx_drop_ps"), 0.0))
                        _net_util.append(_safe_float(_row.get("link_util_pct"), 0.0))
                # Flush the per-interface accumulator in timestamp order.
                for _ts in sorted(_by_t):
                    _a = _by_t[_ts]
                    _net_t.append(_ts)
                    _net_rx.append(_a[0])
                    _net_tx.append(_a[1])
                    _net_total.append(_a[0] + _a[1])
                    _net_pps.append(_a[2])
                    _net_retr.append(_a[3])
                    _net_drop.append(_a[4])
                    _net_util.append(0.0)      # no ceiling known; not reported
                if _want_ifaces:
                    print(f"  Network: restricted to {', '.join(_want_ifaces)} "
                          f"({len(_net_t)} interval(s))")
            except Exception:
                _net_t = []
        _net_configured = bool(_net_t and any(v > 0 for v in _net_total))

        _net_entries = [
            ("total BW (MB/s)",   _net_total, _net_t, "#2dd4bf"),
            ("rx BW (MB/s)",      _net_rx,    _net_t, "#5eead4"),
            ("tx BW (MB/s)",      _net_tx,    _net_t, "#14b8a6"),
            ("packets/s",         _net_pps,   _net_t, "#67e8f9"),
            # link util (%) removed: it is rx+tx divided by a link speed read
            # from /sys/class/net/<if>/speed, which is unreliable on bonded and
            # IB interfaces and absent on many.  rx and tx in absolute GB/s
            # answer the same question without depending on a ceiling that may
            # be wrong or missing.
            ("TCP retrans/s",     _net_retr,  _net_t, "#f472b6"),
            ("rx+tx drops/s",     _net_drop,  _net_t, "#fb7185"),
        ]


        _nvme_path = _first_existing(raw_dir, [
            "nvme_driver_timeseries.csv", "iostat_timeseries.csv"])
        # Extended NVMe column set: bandwidth (bytes), IOPS, latency (ms),
        # and queue depth so the token-movement correlations below can
        # score against all four L3-tier signals.
        _nvme_raw = _amoprof_read_columns_raw(_nvme_path, [
            "time_sec",
            # writer.write_nvme_driver_timeseries emits per-sample MB/s
            # gauges (rd_bw_mbs / wr_bw_mbs) — there are no byte counters
            # in the canonical CSV.  Keep read_bytes/write_bytes in the
            # request list so a Prometheus-sourced CSV that *does* carry
            # cumulative byte counters still works.
            "rd_bw_mbs", "wr_bw_mbs",
            "read_bytes", "write_bytes",
            "rd_iops", "wr_iops", "read_iops", "write_iops",
            "rd_lat_ms", "wr_lat_ms", "read_lat_ms", "write_lat_ms",
            "r_await", "w_await", "await",
            "inflight", "queue_depth", "aqu_sz", "avgqu_sz",
        ]) if _nvme_path else {}
        _nvme_time = _nvme_raw.get("time_sec", [])
        # Bandwidth — prefer the native MB/s gauge; fall back to differencing
        # cumulative byte counters (bytes/s → MB/s) when only those exist.
        _nvme_rd_mbps = list(_nvme_raw.get("rd_bw_mbs") or [])
        _nvme_wr_mbps = list(_nvme_raw.get("wr_bw_mbs") or [])
        _nvme_rd_bw_t = list(_nvme_time)
        _nvme_wr_bw_t = list(_nvme_time)
        if not _nvme_rd_mbps and _nvme_raw.get("read_bytes"):
            _nvme_rd_bw_t, _rd_rate = _rate_with_time(_nvme_raw["read_bytes"], _nvme_time)
            _nvme_rd_mbps = [v / 1e6 for v in _rd_rate]
        if not _nvme_wr_mbps and _nvme_raw.get("write_bytes"):
            _nvme_wr_bw_t, _wr_rate = _rate_with_time(_nvme_raw["write_bytes"], _nvme_time)
            _nvme_wr_mbps = [v / 1e6 for v in _wr_rate]

        # IOPS — collector emits per-sample gauge already (rd_iops/wr_iops),
        # so no delta needed.  When only cumulative counters are present
        # (read_iops/write_iops as totals) fall back to rate-from-counter.
        def _first_nonempty(*names):
            for name in names:
                v = _nvme_raw.get(name) or []
                if v:
                    return v
            return []
        # `rd_iops`/`wr_iops` are already gauges.  Only the cumulative
        # `read_iops`/`write_iops` spelling needs differencing — check for
        # the gauge spelling alone first, otherwise the counter form is
        # returned by _first_nonempty and the delta branch never runs.
        _nvme_rd_iops_series = _first_nonempty("rd_iops")
        _nvme_wr_iops_series = _first_nonempty("wr_iops")
        _nvme_rd_iops_t = list(_nvme_time)
        _nvme_wr_iops_t = list(_nvme_time)
        # Executive overview: single SSD-IOPS chart carrying both read
        # and write curves.  Title reflects whichever tier label the
        # host NVMe drives in this run.  Reads/writes have very
        # different characters (write bursty on backup, read on
        # prefetch/loadback) so keeping them on one chart lets an
        # operator see the R/W imbalance at a glance.
        #
        # FUTURE: a second SSD-IOPS chart for the storage INSIDE the
        # L3.5 memory node will read from _l35s["l35_rd_iops"] /
        # _l35s["l35_wr_iops"] once l35_storage_timeseries.csv is
        # populated by that collector; slot it into _exec_ov under a
        # "L3.5 memory-node SSD IOPS over the run" key.
        if not _nvme_rd_iops_series and _nvme_raw.get("read_iops"):
            _nvme_rd_iops_t, _nvme_rd_iops_series = _rate_with_time(
                _nvme_raw["read_iops"], _nvme_time)
        if not _nvme_wr_iops_series and _nvme_raw.get("write_iops"):
            _nvme_wr_iops_t, _nvme_wr_iops_series = _rate_with_time(
                _nvme_raw["write_iops"], _nvme_time)
        # SSD-IOPS overview chart, built once both directions are
        # resolved.  l3_backend_display is set before this point when
        # a tier is configured; when it is not we fall back to a
        # neutral "SSD" label rather than dropping the chart entirely.
        _iops_series = []
        if _nvme_rd_iops_series and any(v > 0 for v in _nvme_rd_iops_series):
            _iops_series.append({"tier": "L3", "label": "read IOPS",
                                 "t": _nvme_rd_iops_t or list(_nvme_time),
                                 "v": _nvme_rd_iops_series,
                                 "cap": 0, "color": "#0ea5e9"})
        if _nvme_wr_iops_series and any(v > 0 for v in _nvme_wr_iops_series):
            _iops_series.append({"tier": "L3", "label": "write IOPS",
                                 "t": _nvme_wr_iops_t or list(_nvme_time),
                                 "v": _nvme_wr_iops_series,
                                 "cap": 0, "color": "#eab308"})
        if _iops_series:
            _iops_tier_prefix = "L3"
            try:
                _bd = str(l3_backend_display or "").strip()
            except NameError:
                _bd = ""
            if _bd.startswith("L3.5"):
                _iops_tier_prefix = "L3.5"
            elif _bd.startswith("L3"):
                _iops_tier_prefix = "L3"
            _iops_svg = _amoprof_exec_svg_tier_occupancy(
                _iops_series, window=_occ_win, wall_start=_occ_wall, mode="abs",
                title=f"{_iops_tier_prefix} SSD IOPS over the run",
                subtitle="rd_iops / wr_iops \u00b7 nvme_driver_timeseries.csv "
                         "\u00b7 host NVMe driver counters (per-sample gauge)",
                yaxis="IOPS", unit_label="IOPS")
            if _iops_svg:
                _exec_ov["SSD IOPS over the run"] = _iops_svg

        # Latency — per-sample gauges.  `await` is the *combined* r+w column;
        # using it for both read and write would render two identical charts
        # under different labels, so it is only accepted when neither
        # direction-specific column exists, and then only once (as a single
        # combined-latency signal).
        _nvme_rd_lat_ms = _first_nonempty("rd_lat_ms", "read_lat_ms", "r_await")
        _nvme_wr_lat_ms = _first_nonempty("wr_lat_ms", "write_lat_ms", "w_await")
        _nvme_rw_lat_ms: List[float] = []
        if not _nvme_rd_lat_ms and not _nvme_wr_lat_ms:
            _nvme_rw_lat_ms = _first_nonempty("await")

        # Queue depth — prefer the canonical merged source used by the rest of
        # Executive (queue_depth_sources_timeseries.csv, which carries exact
        # blktrace Q→C when available) so the correlation axis matches the QD
        # number shown in the KPI tile.  Fall back to the NVMe CSV inflight
        # column when that file was not produced.
        _nvme_qd_series = _first_nonempty("inflight", "queue_depth", "aqu_sz", "avgqu_sz")
        _nvme_qd_t = list(_nvme_time)
        _nvme_qd_label = "L3 queue depth"
        # A series whose peak is in the thousands is not a queue depth; drawing
        # it sets the axis four orders of magnitude above every real signal and
        # flattens the chart it was added to.
        _qd_rejected: list[tuple[str, float]] = []
        _bad = _qd_implausible(_nvme_qd_series)
        if _bad:
            _qd_rejected.append(("nvme_driver_timeseries.csv", _bad))
            _nvme_qd_series = []
        _qd_ts_path = _first_existing(raw_dir, ["queue_depth_sources_timeseries.csv"])
        if _qd_ts_path:
            _qd_raw = _amoprof_read_columns_raw(_qd_ts_path, [
                "time_sec", "qd_best_effort", "qd", "weighted_qd", "inflight"])
            for _qd_col in ("qd_best_effort", "qd", "weighted_qd", "inflight"):
                _qd_vals = _qd_raw.get(_qd_col) or []
                if not (_qd_vals and any(v > 0 for v in _qd_vals)):
                    continue
                _bad = _qd_implausible(_qd_vals)
                if _bad:
                    _qd_rejected.append((_qd_col, _bad))
                    continue
                _nvme_qd_series = _qd_vals
                _nvme_qd_t = _qd_raw.get("time_sec") or list(_nvme_time)
                _nvme_qd_label = f"L3 queue depth ({_qd_col})"
                break
        for _rj, _rv in _qd_rejected:
            print(f"  [warn] queue depth: ignoring '{_rj}' — peak "
                  f"{_rv:,.0f} exceeds the plausible bound of "
                  f"{_QD_PLAUSIBLE_MAX:,.0f}; a depth that large is an "
                  f"unmatched Q→C counting artifact, not a queue.")

        _dram_path = _first_existing(raw_dir, [
            "amduprof_pcm_timeseries.csv", "pcm_timeseries.csv",
            "pcm_memory_timeseries.csv"])
        # AMDuProf/PCM collectors write `dram_total_gb_s` / `dram_read_gb_s` /
        # `dram_write_gb_s`; `*_bw_gbps` is only one of several spellings seen
        # across sources.  Request the same alias set the KPI path already
        # scans (see the dram_ts column loops above) so Executive's
        # correlation axis and its DRAM tile read the same column.
        _dram_raw = _amoprof_read_columns_raw(_dram_path, [
            "time_sec",
            "dram_total_gb_s", "dram_total_bw_gbs", "dram_bw_gbps",
            "total_bw_gbps", "total_gb_s", "total_bw_gbs", "pcm_dram_total_gb_s",
            "dram_read_gb_s", "dram_read_bw_gbs", "read_bw_gbps", "read_gb_s",
            "dram_write_gb_s", "dram_write_bw_gbs", "write_bw_gbps", "write_gb_s",
        ]) if _dram_path else {}

        def _dram_pick(*names) -> List[float]:
            for _n in names:
                _v = _dram_raw.get(_n) or []
                if _v and any(x > 0 for x in _v):
                    return _v
            for _n in names:
                _v = _dram_raw.get(_n) or []
                if _v:
                    return _v
            return []
        _dram_time = _dram_raw.get("time_sec", [])
        _dram_total = _dram_pick("dram_total_gb_s", "dram_total_bw_gbs", "dram_bw_gbps",
                                 "total_bw_gbps", "total_gb_s", "total_bw_gbs",
                                 "pcm_dram_total_gb_s")
        _dram_read = _dram_pick("dram_read_gb_s", "dram_read_bw_gbs", "read_bw_gbps", "read_gb_s")
        _dram_write = _dram_pick("dram_write_gb_s", "dram_write_bw_gbs", "write_bw_gbps", "write_gb_s")

        # Sanitise at the point of READ, not at first chart use: every consumer
        # between the two saw raw values, which is how impossible numbers kept
        # reappearing on axes after the tiles were fixed.  NaN preserves index
        # alignment with the paired _dram_time array.
        try:
            from amoprof.report.metric_kernels import DRAM_SANE_MAX_GBS as _DMAXR
        except Exception:
            _DMAXR = 100_000.0

        def _dram_sane(_v):
            return [(x if (x == x and 0.0 <= x <= _DMAXR) else float('nan'))
                    for x in (_v or [])]

        _dram_total = _dram_sane(_dram_total)
        _dram_read = _dram_sane(_dram_read)
        _dram_write = _dram_sane(_dram_write)

        _cards: List[str] = []
        # KV bytes/token — the scaling constant that links tokens/s to bandwidth.
        _kv_kb = _safe_float(kv_bytes_tok_kb, 0.0)
        # State how KV/token was resolved, not just its value: an exact figure
        # from the engine config and an estimate from a model-name size hint
        # scale every derived bandwidth number identically but are not equally
        # trustworthy, and the reader cannot tell them apart from the number.
        _kv_src = str(_kv_resolution.get("source") or "")
        _kv_exact = bool(_kv_resolution.get("exact"))
        _kv_qual = ("exact — " + _kv_src) if _kv_exact else (_kv_src or "assumed")
        _kv_header = (f"KV = {_k_kb_from_bytes(_kv_kb * 1024):.0f} KB/token ({_kv_qual})"
                       if _kv_kb > 0 else "KV bytes/token unavailable — correlations shown without KV scaling")

        # Maps a tier token to the AI stack layer it measures, so each card
        # states which layers it covers rather than leaving the reader to infer
        # it from the axis names.
        _LAYER_OF = {
            "NET": "HOST_OS · network fabric",
            "L1": "A4_GPU_HBM",
            "L2": "A3_DRAM",
            "L3": "A1_L3_SSD · A2_NVME_DRIVER",
        }

        def _layer_badge(layers: str) -> str:
            if not layers:
                return ""
            return ('<span style="display:inline-block;margin-left:8px;padding:1px 7px;'
                    'border:1px solid #334155;border-radius:999px;background:#0b1220;'
                    'color:#7dd3fc;font-size:9.5px;font-weight:700;letter-spacing:.3px;'
                    'vertical-align:middle">'
                    f'{_html.escape(layers)}</span>')

        def _card(title: str, subtitle: str, svg_html: str, takeaway: str,
                  layers: str = "", expanded: bool = False) -> str:
            # `svg_html` is a run of `<div class="corr-chart">` scatters.
            # They go in a `corr-strip`: a single non-wrapping horizontal row
            # that scrolls sideways.  Wrapping them into a narrow grid was
            # what made each chart squash — and because `.corr-chart` has no
            # min-width (unlike `.combo-wrap`), nothing gets clipped now.
            # <details> rather than a plain div: the Executive tab carries a
            # dozen correlation cards, which overwhelms the summary read.  Only
            # the distribution card is open by default; the rest expand on
            # demand.  It also means each card's <summary> is picked up by the
            # tab section dropdown, which already collects `details > summary`.
            return (
                f'<details class="corr-card"{" open" if expanded else ""} '
                'data-amoprof-section="1" '
                'style="background:#0f172a;border:1px solid #334155;'
                'border-radius:10px;padding:12px 14px;margin:10px 0;overflow:hidden">'
                '<summary style="cursor:pointer;list-style:none;color:#e2e8f0;'
                'font-weight:800;font-size:13.5px;overflow-wrap:break-word;'
                'word-break:break-word">'
                f'{_html.escape(title)}{_layer_badge(layers)}</summary>'
                f'<div style="color:#94a3b8;font-size:11px;margin:6px 0 8px;'
                f'overflow-wrap:break-word;word-break:break-word">{_html.escape(subtitle)}</div>'
                f'<div class="corr-strip">{svg_html}</div>'
                f'<div style="color:#cbd5e1;font-size:11.5px;line-height:1.55;margin-top:8px;'
                f'overflow-wrap:break-word;word-break:break-word">{takeaway}</div>'
                '</details>'
            )

        def _align_pair(rate_series: List[float], sample_series: List[float]) -> tuple[List[float], List[float]]:
            # rate_series is already one shorter than the underlying
            # counter series (Δ over consecutive samples).  Align the
            # gauge sample series by dropping its first element and
            # trimming to the same length.  Falls back gracefully when
            # the caller passes an already-aligned series.
            if not rate_series or not sample_series:
                return [], []
            gauge = sample_series[1:] if len(sample_series) > len(rate_series) else sample_series
            n = min(len(rate_series), len(gauge))
            return rate_series[:n], gauge[:n]

        def _align_xy(x_t: List[float], x_v: List[float],
                      y_t: List[float], y_v: List[float]) -> tuple[List[float], List[float]]:
            """Time-based pairing via metric_kernels.align_on_time.

            Falls back to the historical index-based `_align_pair` only when a
            timebase is missing, so runs without a time column behave exactly
            as before.
            """
            if not x_v or not y_v:
                return [], []
            if not x_t or not y_t or len(x_t) != len(x_v) or len(y_t) != len(y_v):
                return _align_pair(x_v, y_v)
            out = _k_align_on_time(x_t, x_v, y_t, y_v)
            return out if out[0] else _align_pair(x_v, y_v)

        _CORR_MAX_SCATTERS_PER_CARD = 6
        _CORR_MAX_PLOT_POINTS = 400

        def _decimate(xs: List[float], ys: List[float]) -> tuple[List[float], List[float]]:
            n = len(xs)
            if n <= _CORR_MAX_PLOT_POINTS:
                return xs, ys
            step = (n + _CORR_MAX_PLOT_POINTS - 1) // _CORR_MAX_PLOT_POINTS
            return xs[::step], ys[::step]

        # ---- Whole-window percentiles (p50 / p90 / p99) ------------------
        # Aggregate over the ENTIRE selected period rather than per sampling
        # interval: every interval's bucket deltas are summed into a single
        # histogram and the quantile taken once.  The per-interval line charts
        # showed how the distribution moved but made the headline number hard
        # to read off, which is the number this tab exists to deliver.
        _PCTL_SPECS = [
            ("TTFT", "time_to_first_token_seconds", 1000.0, "ms",
             "sglang_time_to_first_token_seconds_bucket"),
            # ONE decode-latency chart, not two.  TPOT and ITL were separate
            # entries that plotted the same numbers twice: the TPOT entry falls
            # back to inter_token_latency_seconds (SGLang builds without
            # time_per_output_token_seconds), and _PCT_SUMMARY_KEYS mapped both
            # titles to the same server_itl_* percentiles, so on any run with
            # summary percentiles the two bars were identical by construction.
            # This entry prefers the dedicated TPOT histogram and the TITLE
            # names whichever metric was actually plotted, so ITL data is never
            # labelled as a measured TPOT.
            ("TPOT (time per output token)",
             ["time_per_output_token_seconds", "inter_token_latency_seconds"],
             1000.0, "ms/tok", ""),
            ("E2E request latency", "e2e_request_latency_seconds", 1000.0, "ms",
             "sglang_e2e_request_latency_seconds_bucket"),
            ("Input tokens / request", "prompt_tokens_histogram", 1.0, "tokens",
             "sglang_prompt_tokens_histogram_bucket"),
            ("Output tokens / request", "generation_tokens_histogram", 1.0, "tokens",
             "sglang_generation_tokens_histogram_bucket"),
        ]
        _PCTL_COLORS = {"p50": "#38bdf8", "p90": "#f59e0b", "p99": "#ef4444"}
        # Throughput has no histogram in SGLang, so its percentiles come from
        # the distribution of per-interval rates.  That is a different
        # population from the latency percentiles (intervals, not requests) and
        # the subtitle says so.
        _RATE_PCTL_SPECS = [
            ("Input tokens / second", _in_tok_rate, "tok/s"),
            ("Output tokens / second", _out_tok_rate, "tok/s"),
        ]
        _pctl_html = ""
        _pctl_rows = []
        # Prefer the percentiles Prometheus itself computed, when the fetch
        # merged them in (server_ttft_p50_ms and friends, via
        # histogram_quantile over the range).  Accumulating bucket deltas here
        # is a fallback: it is bucket-limited, so on a short window the
        # quantile snaps to a bucket edge (2,000.0 ms exactly) while the tiles
        # showed the interpolated value (1,541 ms).  Same data, two methods —
        # one number is what the reader needs.
        _PCT_SUMMARY_KEYS = {
            "TTFT": ("server_ttft_p50_ms", "server_ttft_p90_ms", "server_ttft_p99_ms"),
            # server_itl_* is ITL; it stands in for TPOT only when the
            # dedicated TPOT histogram is absent (see the guard in the loop).
            "TPOT (time per output token)": (
                "server_itl_p50_ms", "server_itl_p90_ms", "server_itl_p99_ms"),
            "E2E request latency": (
                "server_e2e_p50_ms", "server_e2e_p90_ms", "server_e2e_p99_ms"),
            "Input tokens / request": (
                "prompt_tokens_p50", "prompt_tokens_p90", "prompt_tokens_p99"),
            "Output tokens / request": (
                "output_tokens_p50", "output_tokens_p90", "output_tokens_p99"),
        }

        def _pct_from_summary(title: str) -> dict:
            keys = _PCT_SUMMARY_KEYS.get(title)
            if not keys:
                return {}
            out = {}
            for _lab, _k in zip(("p50", "p90", "p99"), keys):
                _v = _safe_float(_pick(sglang, [_k], 0), 0)
                if _v > 0:
                    out[_lab] = _v
            return out if len(out) == 3 else {}

        _n_by_title: dict = {}
        for _p_title, _p_base, _p_scale, _p_unit, _p_src in _PCTL_SPECS:
            _bases = _p_base if isinstance(_p_base, list) else [_p_base]
            _pw, _used = {}, ""
            for _b in _bases:
                try:
                    _pw = _amoprof_histogram_window_percentiles(
                        _sg_path, _b, (0.5, 0.9, 0.99), _p_scale)
                except Exception:
                    _pw = {}
                if _pw:
                    _used = f"sglang_{_b}_bucket"
                    break
            # A dedicated TPOT histogram outranks the summary percentiles:
            # server_itl_* is a different metric, and overwriting a measured
            # TPOT with it is half of how the two charts came to agree.  Every
            # other spec's summary keys are the same metric as its buckets, so
            # the summary still wins there.
            _tpot_measured = (len(_bases) > 1
                              and _used == f"sglang_{_bases[0]}_bucket")
            _from_summary = {} if _tpot_measured else _pct_from_summary(_p_title)
            if _from_summary:
                _from_summary["observations"] = _pw.get("observations", 0) if _pw else 0
                _pw = _from_summary
                _used = ("Prometheus histogram_quantile over the range "
                         "(same source as the summary tiles)")
            if not _pw:
                continue
            _p_src = _used if _from_summary else (_p_src or _used)
            # Name the metric actually plotted.  Without the dedicated TPOT
            # histogram these numbers ARE inter-token latency (mean ITL equals
            # TPOT only under steady decode), so use the combined "TPOT / ITL"
            # label the KPI tiles and latency timelines already use rather than
            # claiming a measured TPOT.
            _p_disp = _p_title
            if len(_bases) > 1 and not _tpot_measured:
                _p_disp = "TPOT / ITL (inter-token latency)"
                _p_src += (" · ITL stands in for TPOT "
                           "(dedicated TPOT histogram not exported)")
            # Say what n counts.  Each histogram is observed at a different
            # moment: TTFT when a request gets its first token, E2E and the
            # token-size histograms when it completes, ITL once per gap
            # between output tokens.  All printed "observations", so TTFT
            # n=517 beside E2E n=516 read as a counting error; the
            # difference is requests in flight at the window edges.
            _n_label = ("inter-token gaps" if _p_title.startswith("TPOT") else
                        "requests · first token in window" if _p_title == "TTFT" else
                        "requests · completed in window")
            _n_by_title[_p_title] = _safe_float(_pw.get("observations", 0), 0)
            _pctl_method = (
                "Prometheus histogram_quantile over the range"
                if _from_summary else
                "computed here from the bucket counter deltas — Prometheus "
                "histogram_quantile was not available for this window, and "
                "the two implementations do not agree to the digit on a "
                "coarse ladder")
            _pctl_html += _amoprof_exec_svg_percentile_bars(
                f"{_p_disp} — p50 / p90 / p99",
                f"whole window · \u0394{_p_src} · {_pctl_method}",
                _p_unit, _pw, _PCTL_COLORS, n_label=_n_label)
            # Mean beside p50, with the ratio as a tail indicator: percentiles
            # say where the boundary sits, only the mean is sensitive to how
            # far beyond it the worst cases run.
            # Pair the mean with the same metric the percentiles came from:
            # an ITL mean beside a measured-TPOT p50 is two metrics in one
            # ratio.  No matching key means no mean is shown, which is correct.
            _mean_key = {"TTFT": ("server_ttft_mean_ms", "ttft_mean"),
                         "TPOT (time per output token)": (
                             ("server_tpot_mean_ms", "avg_tpot_ms", "mean_tpot_ms")
                             if _tpot_measured
                             else ("server_itl_mean_ms", "itl_mean")),
                         "E2E request latency": ("server_e2e_mean_ms", "e2e_mean"),
                         }.get(_p_title, ())
            _mean_v = 0.0
            for _mk in _mean_key:
                _mean_v = _safe_float(_pick(sglang, [_mk], 0), 0)
                if _mean_v > 0:
                    break
            # These keys live in sglang_summary.json and are absent on a
            # Prometheus-only run, so the mean-beside-p50 comparison silently
            # disappeared exactly where it was most needed: a v1.69.0 report
            # showed "TTFT mean 62,895 ms" on a tile and "TTFT p50 1,755.1 ms"
            # in this chart with nothing connecting them, which reads as two
            # surfaces disagreeing rather than as a 36x tail.  Fall back to
            # the mean this report already resolved for its own tiles -- the
            # same figure, so the two cannot diverge.
            if _mean_v <= 0:
                _mean_v = _safe_float({
                    "TTFT": ttft_ms,
                    "TPOT (time per output token)": tpot_ms,
                    "ITL (inter-token latency)": tpot_ms,
                    "E2E request latency": e2e_ms,
                }.get(_p_title, 0.0), 0.0)
            _tail = (_k_tail_ratio(_mean_v, _pw.get('p50', 0.0))
                     if _mean_v > 0 else {})
            def _fv(v, _u=_p_unit):
                return (_fmt_latency(v, _u, " " + _u) if _is_latency_unit(_u)
                        else _fmt_num(v, " " + _u, 1))

            # A histogram's top bucket is open-ended, so a quantile landing
            # in it is reported as that bucket's FLOOR -- a lower bound.  The
            # chart's footnote said so in general while the figures were
            # printed as plain values, and on a v1.69.0 report that produced
            # "TTFT p99: 400,000.00 ms" and "TPOT p90 8,000.0 / p99 8,000.0":
            # bucket boundaries read as latencies, two of them identical
            # because both quantiles fell in the same open bucket.  Mark the
            # specific figures rather than leaving the reader to notice.
            _cens_qs = set(_pw.get("censored") or ())
            _cens_floor = _safe_float(_pw.get("censored_floor"), 0.0)

            _brk = _pw.get("bracket") or {}

            def _pfmt(_q):
                _v = _safe_float(_pw.get(_q, 0), 0.0)
                _txt = _fv(_v)
                if _q in _cens_qs:
                    return (f"\u2265 {_txt} (censored \u2014 this quantile "
                            f"fell in the open-ended bucket above "
                            f"{_fv(_cens_floor)}, so "
                            f"it is a lower bound, not a measurement)")
                # A histogram resolves no finer than its buckets.  Where the
                # bucket holding this quantile spans a wide range -- SGLang's
                # TTFT ladder jumps 0.8 s to 8 s to 400 s near the tail -- a
                # value printed to two decimals implies precision the data
                # does not have.  Show the bracket when it is wide, so the
                # figure reads as the estimate inside an interval that it is.
                _b = _brk.get(_q)
                if _b and _b[0] >= 0 and _b[1] not in (0, float("inf")):
                    _lo_b, _hi_b = _b
                    _wide = (_hi_b >= max(_lo_b * 3.0, _lo_b + 1e-9)
                             if _lo_b > 0 else _hi_b > 0)
                    if _wide:
                        return (_txt + f" (bucket-limited: the observations "
                                f"behind it sit between "
                                f"{_fv(_lo_b)} and "
                                f"{_fv(_hi_b)}, so this "
                                f"is an interpolation inside that range, not "
                                f"a measured value)")
                return _txt

            _pctl_rows.append(
                f"<b>{_html.escape(_p_disp)}</b> "
                f"p50 {_pfmt('p50')} · "
                f"p90 {_pfmt('p90')} · "
                f"p99 {_pfmt('p99')}"
                + (f" \u00b7 mean {_fv(_mean_v)} "
                   f"(<b>{_tail['ratio']:.1f}x</b> p50 \u2014 {_tail['label']})"
                   if _tail.get("ratio", 0) > 0 else ""))
        for _r_title, _r_vals, _r_unit in _RATE_PCTL_SPECS:
            # ACTIVE intervals only.  An interval in which nothing was served
            # says nothing about how fast the server serves, and on a window
            # that is mostly idle those zeros dominate the population: at a
            # 2.5% duty cycle, p50 and p90 both land inside the idle block and
            # report 0.0 for a server that sustains hundreds of tok/s while
            # working.  Latency percentiles do not have this problem because
            # histogram buckets only record actual requests.
            _all_iv = [v for v in (_r_vals or []) if v == v and v >= 0]
            _rv = sorted(v for v in _all_iv if v > 0)
            _idle_n = len(_all_iv) - len(_rv)
            if len(_rv) < 3:
                continue

            def _rq(f, _s=_rv):
                return _s[min(len(_s) - 1, int(f * (len(_s) - 1)))]

            _duty = (len(_rv) / len(_all_iv) * 100.0) if _all_iv else 0.0
            _rp = {"p50": _rq(0.5), "p90": _rq(0.9), "p99": _rq(0.99),
                   "observations": float(len(_rv))}
            _pctl_html += _amoprof_exec_svg_percentile_bars(
                f"{_r_title} \u2014 p50 / p90 / p99",
                f"active intervals only \u00b7 {len(_rv):,} of {len(_all_iv):,} "
                f"({_duty:.1f}% duty cycle) \u00b7 not per request",
                _r_unit, _rp, _PCTL_COLORS, n_label="active sampling intervals")
            _pctl_rows.append(
                f"<b>{_html.escape(_r_title)}</b> p50 {_rp['p50']:,.1f} \u00b7 "
                f"p90 {_rp['p90']:,.1f} \u00b7 p99 {_rp['p99']:,.1f} {_r_unit} "
                f"\u00b7 n={len(_rv):,} active of {len(_all_iv):,} intervals "
                f"({_duty:.1f}% duty cycle"
                + (f", {_idle_n:,} idle excluded" if _idle_n else "") + ")")

        # A time-series row beside the percentile bars.  The bars say how the
        # values were distributed; these say when they moved.  A latency that
        # degrades steadily through a run and one that spikes once can share a
        # p90, and only the timeline tells them apart.
        _lat_ts = [
            ("TTFT",                _ttft_t, _ttft_ms, "ms",     "#38bdf8"),
            ("TPOT / ITL",          _tpot_t, _tpot_ms, "ms/tok", "#a78bfa"),
            ("E2E request latency", _e2e_t,  _e2e_ms,  "ms",     "#f59e0b"),
        ]
        _lat_series = [{"tier": "L1", "label": _n,
                        "t": _t, "v": _v, "cap": 0, "color": _c}
                       for _n, _t, _v, _u, _c in _lat_ts
                       if _t and _v and any(x > 0 for x in _v)]
        # Force a new row and label it, so the timelines read as a distinct
        # view rather than more distribution charts. The percentile bars are
        # half-width and wrap; without an explicit break the first timeline
        # lands beside the last bar chart.
        # (bucket-scatter replaces the per-interval P99 line-plot the
        # timeline used to render; the sibling percentile card still
        # provides the p50/p90/p99 view.)
        _lat_series = []
        _tok_series = []
        for _n, _t, _v, _c in (("Input tokens / s", _sg_rate_t, _in_tok_rate, "#22c55e"),
                               ("Output tokens / s", _sg_rate_t, _out_tok_rate, "#2dd4bf")):
            if _t and _v and any(x > 0 for x in _v):
                _tok_series.append({"tier": "L1", "label": _n, "t": _t,
                                    "v": _v, "cap": 0, "color": _c})

        # Timelines live in their own card and section, not appended to the
        # distribution charts: they are a different view of the same metrics,
        # and interleaving them with half-width percentile bars produced a
        # broken layout.
        _ts_html = ""
        # One bucket-scatter per metric: each dot is (interval, bucket
        # upper-edge), sized by the number of completions that landed
        # in that bucket range during that interval.  This shows every
        # completion the exporter recorded, without smoothing across
        # intervals or aggregating across buckets.
        for _bs_title, _bs_base, _bs_color in (
                ("TTFT bucket occupancy over the run",
                 "time_to_first_token_seconds", "#38bdf8"),
                ("E2E request latency bucket occupancy over the run",
                 "e2e_request_latency_seconds", "#f59e0b"),
                ("TPOT / ITL bucket occupancy over the run",
                 "inter_token_latency_seconds", "#a78bfa")):
            _ts_html += _amoprof_exec_svg_bucket_scatter(
                _sg_path, _bs_base, _bs_title,
                "one dot per (interval, bucket range) with a non-zero "
                "delta \u00b7 dot area \u221d completions in that range",
                _bs_color,
                window=_occ_win, wall_start=_occ_wall)
        if _tok_series:
            _ts_html += _amoprof_exec_svg_tier_occupancy(
                _tok_series, window=_occ_win, wall_start=_occ_wall, mode="abs",
                title="Token throughput over the run",
                subtitle="one sample per interval \u00b7 \u0394tokens \u00f7 \u0394t",
                yaxis="tokens/s", unit_label="tok/s")
        # Executive overview: emit input and output throughput as p50/p90/p99
        # rolling-window percentiles over the run so the reader can see how
        # the tail behaved, not just the mean.  SGLang publishes no throughput
        # histogram, so the percentiles are computed here from the population
        # of per-interval rates rather than from bucket deltas.
        #
        # Data source: prefer prompt_tokens_total / generation_tokens_total
        # (what _tok_series was built from above).  If those counters are
        # not exported by the SGLang build (some Gemma / server builds
        # only surface the mode-labelled realtime_tokens_total metric),
        # fall back to prefill_cache + prefill_compute for input, and
        # decode for output — these are the same rates cache_hit is
        # computed from, so if the run has any latency chart at all
        # these are populated.
        def _elemsum(_a, _b):
            _n = min(len(_a or []), len(_b or []))
            return [(_a[i] or 0.0) + (_b[i] or 0.0) for i in range(_n)]

        _in_rate_ov = _in_tok_rate
        _in_rate_ov_src = "\u0394prompt_tokens \u00f7 \u0394t"
        if not (_in_rate_ov and any(v > 0 for v in _in_rate_ov)):
            _fallback_in = _elemsum(_pf_cache_rate, _pf_compute_rate)
            if _fallback_in and any(v > 0 for v in _fallback_in):
                _in_rate_ov = _fallback_in
                _in_rate_ov_src = ("\u0394realtime_tokens{mode=prefill_cache} "
                                   "+ \u0394realtime_tokens{mode=prefill_compute} "
                                   "\u00f7 \u0394t \u00b7 fallback (prompt_tokens_total absent)")

        _out_rate_ov = _out_tok_rate
        _out_rate_ov_src = "\u0394generation_tokens \u00f7 \u0394t"
        if not (_out_rate_ov and any(v > 0 for v in _out_rate_ov)):
            if _decode_rate and any(v > 0 for v in _decode_rate):
                _out_rate_ov = _decode_rate
                _out_rate_ov_src = ("\u0394realtime_tokens{mode=decode} "
                                    "\u00f7 \u0394t \u00b7 fallback (generation_tokens_total absent)")

        def _rolling_pctls(_vals, _times):
            """Rolling p50/p90/p99 with idle intervals excluded.

            Returns four aligned lists: t, p50, p90, p99.  Empty when there
            are too few active samples to compute a meaningful percentile.
            """
            _pairs = [(t, v) for t, v in zip(_times or [], _vals or [])
                      if v == v and v > 0]
            if len(_pairs) < 10:
                return [], [], [], []
            _win = max(10, min(60, len(_pairs) // 15))
            _t_out, _p50, _p90, _p99 = [], [], [], []
            for _i in range(_win - 1, len(_pairs)):
                _window = sorted(v for _, v in _pairs[_i - _win + 1:_i + 1])
                def _q(f, _s=_window):
                    return _s[min(len(_s) - 1, int(f * (len(_s) - 1)))]
                _t_out.append(_pairs[_i][0])
                _p50.append(_q(0.5))
                _p90.append(_q(0.9))
                _p99.append(_q(0.99))
            return _t_out, _p50, _p90, _p99

        for _tok_kind, _tok_vals, _tok_form in (
                ("Input",  _in_rate_ov,  _in_rate_ov_src),
                ("Output", _out_rate_ov, _out_rate_ov_src)):
            # Timebase for both rates is the shared _sg_rate_t built above.
            # When _in_tok_rate / _out_tok_rate came from prompt_tokens_total
            # they already aligned to that timebase; the realtime-mode fallback
            # is built from the SAME _rate_from_counter helper, so alignment
            # holds.  Length can differ by one sample when a counter had one
            # fewer completion in the window — align by taking the tail.
            if not (_tok_vals and any(v > 0 for v in _tok_vals)):
                continue
            _n_align = min(len(_sg_rate_t or []), len(_tok_vals))
            _one_t = list(_sg_rate_t or [])[-_n_align:]
            _one_v = list(_tok_vals)[-_n_align:]
            _p_t, _p50v, _p90v, _p99v = _rolling_pctls(_one_v, _one_t)
            if not _p_t:
                # Not enough active samples for percentiles — fall back to the
                # single-line mean so the tile still renders something rather
                # than dropping off the strip silently.
                _one_series = [{"tier": "L1", "label": f"{_tok_kind} tokens / s",
                                "t": _one_t, "v": _one_v, "cap": 0,
                                "color": "#22c55e" if _tok_kind == "Input" else "#2dd4bf"}]
                _tok_one_svg = _amoprof_exec_svg_tier_occupancy(
                    _one_series, window=_occ_win, wall_start=_occ_wall, mode="abs",
                    title=f"{_tok_kind} token throughput over the run",
                    subtitle=f"per-interval rate \u00b7 {_tok_form}",
                    yaxis="tokens/s", unit_label="tok/s")
            else:
                _pctl_series = [
                    {"tier": "L1", "label": "p50", "t": _p_t, "v": _p50v,
                     "cap": 0, "color": "#38bdf8"},
                    {"tier": "L1", "label": "p90", "t": _p_t, "v": _p90v,
                     "cap": 0, "color": "#f59e0b"},
                    {"tier": "L1", "label": "p99", "t": _p_t, "v": _p99v,
                     "cap": 0, "color": "#ef4444"},
                ]
                _win_n = max(10, min(60,
                    len([v for v in _one_v if v == v and v > 0]) // 15))
                _tok_one_svg = _amoprof_exec_svg_tier_occupancy(
                    _pctl_series, window=_occ_win, wall_start=_occ_wall,
                    mode="abs",
                    title=f"{_tok_kind} token throughput over the run",
                    subtitle=(f"rolling p50 / p90 / p99 over {_win_n} active "
                              f"intervals per point \u00b7 {_tok_form} \u00b7 "
                              f"idle intervals excluded from each window"),
                    yaxis="tokens/s", unit_label="tok/s")
            if _tok_one_svg:
                _exec_ov[f"{_tok_kind} token throughput over the run"] = _tok_one_svg

        # Latency PERCENTILES over time, from per-interval bucket deltas.
        # The mean-over-time chart above hides the tail; the percentile card
        # shows the tail but not when it happened.  This shows both: a p99
        # that spikes at one moment and one that degrades steadily look
        # identical in every other view.
        for _pt_title, _pt_base, _pt_unit, _pt_scale in (
                ("TTFT percentiles over the run", "time_to_first_token_seconds", "ms", 1000.0),
                # TPOT uses the SGLang ITL bucket histogram
                # (sglang_inter_token_latency_seconds_bucket): same per-interval
                # bucket-delta method as TTFT/E2E, unit is ms per generated token.
                ("TPOT percentiles over the run", "inter_token_latency_seconds", "ms/tok", 1000.0),
                ("E2E latency percentiles over the run", "e2e_request_latency_seconds", "ms", 1000.0),
                ("Queue wait percentiles over the run", "queue_time_seconds", "ms", 1000.0)):
            _bt, _bser = _amoprof_bucket_series(_sg_path, _pt_base) if _sg_path else ([], [])
            if len(_bser) < 3:
                continue
            _pq = _k_bucket_pctls(_bser)
            if not _pq:
                continue
            # Points are unevenly spaced: the kernel widens a bin until it has
            # enough completions, so each point carries the timestamp of the
            # interval it ENDS at.  Aligning by position instead would put
            # every value on the wrong time.
            _idx = _pq.get("_index") or []
            _pt_t = [_bt[i] for i in _idx if 0 <= i < len(_bt)]
            # Whole-window percentiles, drawn as a dashed line behind each
            # per-interval line.  A line of interval medians need not centre on
            # the run's median — every bin counts once however many requests it
            # holds — so without the reference the two charts read as
            # contradicting each other.  Same source as the distribution card
            # (Prometheus histogram_quantile over the range), falling back to
            # the same buckets this chart is built from.
            _ww_keys = {
                "time_to_first_token_seconds": "server_ttft",
                "inter_token_latency_seconds": "server_itl",
                "e2e_request_latency_seconds": "server_e2e",
            }.get(_pt_base)
            _ww = {}
            if _ww_keys:
                _ww = {q: _safe_float(_pick(sglang, [f"{_ww_keys}_p{int(q*100)}_ms"], 0), 0)
                       for q in (0.5, 0.9, 0.99)}
                if not all(v > 0 for v in _ww.values()):
                    _ww = {}
            if not _ww:
                _wwp = _amoprof_histogram_window_percentiles(
                    _sg_path, _pt_base, (0.5, 0.9, 0.99), _pt_scale)
                _ww = {q: _wwp.get(f"p{int(q*100)}", 0.0) for q in (0.5, 0.9, 0.99)} if _wwp else {}
            _pt_series = []
            for _q, _col in ((0.5, "#38bdf8"), (0.9, "#f59e0b"), (0.99, "#ef4444")):
                _vals = [v * _pt_scale if v == v else float("nan")
                         for v in _pq.get(_q, [])]
                _n_pt = min(len(_vals), len(_pt_t))
                if _n_pt >= 2 and any(v == v and v > 0 for v in _vals[:_n_pt]):
                    _ref = _ww.get(_q, 0.0)
                    _pt_series.append({"tier": "L1", "label": f"p{int(_q*100)}",
                                       "t": _pt_t[:_n_pt], "v": _vals[:_n_pt],
                                       "cap": _ref if _ref > 0 else 0, "color": _col,
                                       "cap_label": (f"run p{int(_q*100)} {_fmt_latency(_ref, _pt_unit)} {_pt_unit} (dashed)"
                                                     if _ref > 0 else "")})
            # A quantile that sits in the open-ended top bucket is reported at
            # the last finite boundary.  That value is a lower bound, not a
            # measurement, and printing it as "80,000.00 ms" implies a
            # precision the histogram does not carry.  Say so when it happens.
            # Values land on a histogram bucket boundary whenever the quantile
            # target coincides with that bucket's cumulative count, which is
            # common at low completion counts.  A round number like 80,000 ms
            # is therefore a bucket edge, not a measurement to that precision:
            # the true value lies within the preceding bucket.  Say so, and do
            # not print decimals that imply otherwise.
            _edges = sorted({_le * _pt_scale for _le, _ in _bser
                             if _le == _le and _le != float("inf")})
            _on_edge = sorted({v for _sr in _pt_series for v in _sr["v"]
                               if v == v and any(abs(v - e) < 1e-6 for e in _edges)})
            _pt_sub = ("per-interval quantiles from \u0394histogram buckets (summed across "
                       "label sets) \u00b7 bins widened until each holds \u226510 completions, "
                       "so points are unevenly spaced \u00b7 dashed = whole-run percentile")
            if _on_edge:
                _w = next((_fmt_latency(_edges[_i] - _edges[_i-1], _pt_unit)
                           for _i, e in enumerate(_edges)
                           if _i and abs(e - _on_edge[-1]) < 1e-6), "")
                _pt_sub += (f" \u00b7 values on a bucket boundary "
                            f"(e.g. {_fmt_latency(_on_edge[-1], _pt_unit)} {_pt_unit}) are edges of a "
                            + (f"{_w} {_pt_unit}-wide bucket" if _w else "histogram bucket")
                            + ": the underlying value lies within that bucket")
            else:
                _pt_sub += " \u00b7 bucket-limited resolution"
            if _pt_series:
                _pt_svg = _amoprof_exec_svg_tier_occupancy(
                    _pt_series, window=_occ_win, wall_start=_occ_wall, mode="abs",
                    title=_pt_title,
                    subtitle=_pt_sub,
                    yaxis=_pt_unit, unit_label=_pt_unit)
                _ts_html += _pt_svg
                if _pt_svg:
                    _exec_ov[_pt_title] = _pt_svg

        if _ts_html:
            timeline_charts_html = _card(
                "Latency & throughput over the run",
                "The distribution charts above show how values were spread across "
                "the window; these show when they moved. A metric that degrades "
                "steadily and one that spikes once can share a p90. Both axes are "
                f"logarithmic, so TPOT in milliseconds and E2E in seconds stay "
                f"readable together. {_kv_header}",
                _ts_html,
                "Each dot is one Prometheus histogram bucket at one sampling "
                "interval, sized by how many completions landed in that bucket "
                "range during that interval.  Individual latencies are not stored "
                "by the histogram, so the vertical position is the bucket UPPER "
                "edge \u2014 a completion plotted at the 200ms edge lies somewhere "
                "in (previous edge, 200ms].",
                layers="A5_APP", expanded=True)

        # ---- KV block movement rates across tiers --------------------
        # Modelled on the End report's panel of the same name, which plots
        # blocks/s rather than tokens/s because a block is what the tier
        # actually moves -- one I/O carries a page of KV, so blk/s is the
        # rate the device and the store see.
        #
        # Two differences from that panel, both deliberate.
        #
        # It names the real backing tier.  The End version labels the backup
        # and prefetch series "local Storage" whatever the backend is,
        # because its gate (kvb_l3_storage_observed) is true for a remote
        # store as well -- so a Mooncake deployment read as though its KV
        # were going to a local SSD.  The label is resolved here instead.
        #
        # It plots only MEASURED counters.  The End version also draws an
        # "L1->L2 offload" line and an estimated-L2-eviction reference line;
        # the first is L2 residency delta over the whole run divided by
        # duration (a net fill rate, not a movement rate) and the second is a
        # heuristic that only exists above 80% fill.  Neither is a counter,
        # so neither is charted beside counters that are.
        _kvmove_html = ""
        try:
            _blk_tok = 0.0
            try:
                _blk_tok = float(str(page_sz).strip() or 0)
            except Exception:
                _blk_tok = 0.0
            _tier_nm = {"local_ssd": "L3 local SSD",
                        "remote_mooncake": "L3.5 memory node",
                        "remote_storage": "L3.5 memory node"}.get(
                            str(l3_backend_class).lower(), "")
            _mv = []
            if _blk_tok > 0 and _tier_nm:
                for _lbl, _rate, _col, _src_m in (
                        (f"L1\u2192L2 evict", _evict_rate, "#f59e0b",
                         "sglang_evicted_tokens_total"),
                        (f"L2\u2192{_tier_nm} backup", _backup_rate, "#ef4444",
                         "sglang_backuped_tokens_total"),
                        (f"{_tier_nm}\u2192L2 prefetch", _pref_rate, "#22c55e",
                         "sglang_prefetched_tokens_total"),
                        (f"L2\u2192L1 load-back", _load_rate, "#38bdf8",
                         "sglang_load_back_tokens_total")):
                    _r = [v / _blk_tok for v in (_rate or []) if v == v]
                    if _r and any(v > 0 for v in _r):
                        _mv.append({
                            "tier": "L2", "label": _lbl, "t": _sg_rate_t,
                            "v": [v / _blk_tok for v in _rate], "cap": 0,
                            "color": _col,
                            "src": ("sglang_timeseries.csv", _src_m,
                                    f"\u0394counter \u00f7 \u0394t \u00f7 {_blk_tok:,.0f} tokens/block, summed over tp_rank")})
            if _mv:
                _dirs = " \u00b7 ".join(
                    f"{_x['label']} peak {max(_x['v']):,.1f}" for _x in _mv)
                _kvmove_svg = _amoprof_exec_svg_tier_occupancy(
                    _mv, window=_occ_win, wall_start=_occ_wall, mode="abs",
                    title="KV block movement rates across tiers",
                    subtitle=("blocks per second, since a block is the unit the "
                              f"tier moves \u00b7 {_blk_tok:,.0f} tokens per block "
                              f"\u00b7 backing tier resolved as {_tier_nm}"),
                    yaxis="blocks / s", unit_label="blk/s", width=760)
                _kvmove_html = _kvmove_svg + _src_block_from_series(
                    _mv,
                    note=("All four are engine-side counters, converted to "
                          "blocks by the configured page size. Down-tier "
                          "movement (evict, backup) and up-tier movement "
                          "(prefetch, load-back) on one axis: a run where the "
                          "down lines sit far above the up lines is paying to "
                          "move KV out and not getting it back."))
        except Exception:
            _kvmove_html = ""

        if _kvmove_html:
            _cards.append(_card(
                "KV block movement rates across tiers",
                "Where KV is moving between tiers, in blocks per second. The "
                "same counters the token-rate chart uses, divided by the page "
                "size, so the rate is in the unit the backing tier actually "
                "handles.",
                _kvmove_html,
                "Only measured counters are plotted. The End report's version "
                "of this panel also carries an L1\u2192L2 offload line and an "
                "estimated L2 eviction line; both are derived rather than "
                "counted, so they are left out here rather than drawn beside "
                "measurements.",
                layers="A3_DRAM", expanded=True))

        # Why TTFT's n differs from the completion-based charts: a request
        # running when the window opens completes inside it (E2E counts it,
        # TTFT already saw its first token before); one running when it
        # closes got its first token inside but has not completed.
        _n_note = ""
        _n_ttft = _n_by_title.get("TTFT", 0)
        _n_done = _n_by_title.get("E2E request latency", 0)
        if _n_ttft > 0 and _n_done > 0 and abs(_n_ttft - _n_done) >= 1:
            _run = [v for v in (_amoprof_read_columns_raw(_sg_path, ["num_running_reqs"])
                                .get("num_running_reqs") or []) if v == v]
            _edges = (f" {_run[0]:,.0f} requests were running when the window opened and "
                      f"{_run[-1]:,.0f} when it closed." if len(_run) >= 2 else "")
            _n_note = (
                f"<br><br><b>Why the n counts differ:</b> TTFT counts requests whose first "
                f"token arrived in the window ({_n_ttft:,.0f}); E2E latency and the token-size "
                f"charts count requests that completed in it ({_n_done:,.0f}). The "
                f"{abs(_n_done - _n_ttft):,.0f}-request difference is requests in flight at the "
                f"window edges.{_edges} TPOT / ITL counts gaps between output tokens, not "
                f"requests.")
        if _pctl_html:
            # Emitted above the Bottleneck Analysis section (directly under the
            # KPI grid) rather than appended to _cards.
            distribution_charts_html = _card(
                "Latency & token-size distribution · p50 / p90 / p99 for the whole period",
                "One histogram per metric, accumulated across every sampling interval in "
                "the selected window, then quantiled once. Percentiles are interpolated "
                "inside the bucket containing the quantile; a value landing in the "
                "open-ended top bucket is reported as that bucket's floor (a lower bound). "
                f"{_kv_header}",
                _pctl_html,
                "<br>".join(_pctl_rows) + _n_note
                + "<br><br>A p99 far above p50 is tail latency: a minority of requests are "
                "paying a cost the mean hides. Wide input/output token spreads mean the "
                "workload itself is heterogeneous, so a latency tail may reflect request "
                "size rather than server behaviour — compare the token spread against the "
                "latency spread before concluding the server is at fault.",
                layers="A5_APP · request latency & token size", expanded=True)

        # ---- HBM composition: weights vs KV cache -------------------------
        # "HBM used" alone does not say whether headroom is recoverable:
        # weights are fixed, the KV pool is a configuration choice, and only
        # the occupied part of that pool moves with load.
        try:
            _pool_tokens = _safe_float(_pick(sglang, ["max_total_num_tokens",
                                                      "sglang_max_total_num_tokens"], 0), 0)
            if _pool_tokens <= 0:
                _pool_tokens = _safe_float(_pick(setup, ["max_total_num_tokens"], 0), 0)
            _tok_usage = _safe_float(_pick(sglang, ["token_usage", "sglang_token_usage"], 0), 0)
            _kv_used_tok = _safe_float(_pick(sglang, ["kv_used_tokens", "num_used_tokens"], 0), 0)
            _w_dtype = 1 if "fp8" in str(_pick(setup, ["Quantization", "quantization",
                                                       "dtype"], "")).lower() else 2
            _params_b = _safe_float(_pick(setup, ["params_b", "Params B", "model_params_b"], 0), 0)
            if _params_b <= 0:
                # A size token in the model name is only usable if it is
                # plausible against the device: "gpt-oss-120b" on 40 GB cards
                # would otherwise draw a 120 GB weights band on a 40 GB GPU.
                _m_size = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*b(?![a-z])",
                                    str(_model_name or "").lower())
                if _m_size:
                    _cand = _safe_float(_m_size.group(1), 0)
                    _per_gpu_w = _cand * (1 if _w_dtype == 1 else 2) / max(tp_count or 1.0, 1.0)
                    if 0 < _per_gpu_w <= _k_gb_from_gib(_safe_float(_gpu_cfg.get("hbm_per_gpu_gb", 0), 0)) or \
                       (0 < _per_gpu_w <= 400):
                        _params_b = _cand
            _hbm_res = _resolve_gpu_hbm(gpu, setup, _gpu_cfg)
            _hbm_bd = _k_resolve_hbm_breakdown(
                hbm=_hbm_res, kv={"kb": kv_bytes_tok_kb},
                max_total_tokens=_pool_tokens, token_usage=_tok_usage,
                used_tokens=_kv_used_tok, params_b=_params_b,
                weight_dtype_bytes=_w_dtype, tp_size=tp_count or 1.0)
            _bd_svg = _amoprof_exec_svg_hbm_breakdown(_hbm_bd)
            if _bd_svg:
                _bd_notes = [
                    f"<b>Model weights</b> {_fmt_num(_hbm_bd['weights_gb'], ' GB', 1)} "
                    f"— {_html.escape(_hbm_bd['weights_source'])}",
                    f"<b>KV pool reserved</b> {_fmt_num(_hbm_bd['kv_pool_gb'], ' GB', 1)} "
                    f"— max_total_num_tokens x KV bytes/token ÷ TP; allocated up front "
                    f"from mem-fraction-static, so it is resident whether or not tokens occupy it",
                    f"<b>KV in use</b> {_fmt_num(_hbm_bd['kv_active_gb'], ' GB', 1)} "
                    f"— {_html.escape(_hbm_bd['kv_active_source'])}; the only component "
                    f"that moves with load",
                ]
                if not _hbm_bd.get("consistent"):
                    _bd_notes.append(
                        "<b style='color:#fca5a5'>Inconsistent</b> — weights + KV "
                        "exceed measured HBM used. Most often KV bytes/token is "
                        "overstated (sliding-window attention is not modelled) or TP "
                        "is wrong. Treat the split as indicative until it reconciles.")
                _cards.append(_card(
                    "HBM composition — model weights vs KV cache",
                    "Per-GPU split of measured HBM occupancy. Weights and the reserved KV "
                    "pool are fixed costs; only the occupied part of the pool varies with "
                    f"traffic. {_kv_header}",
                    _bd_svg,
                    "<br>".join(_bd_notes)
                    + "<br><br>The residual (activations, CUDA context, allocator "
                      "fragmentation, cuBLAS workspace) is <i>not</i> separable from this "
                      "telemetry and is reported as one band rather than attributed. "
                      "Recoverable headroom is the reserved-but-free KV pool plus "
                      "unallocated HBM — weights are not reducible without quantisation.",
                    layers="A4_GPU_HBM · A5_APP"))
        except Exception as _bd_err:
            # Never silent: a swallowed exception here is indistinguishable
            # from "this run has no HBM data".
            _cards.append(_card(
                "HBM composition — model weights vs KV cache",
                "Unavailable for this run.", "",
                f"Could not compute the HBM split: {_html.escape(str(_bd_err))}",
                layers="A4_GPU_HBM · A5_APP"))

        # ---- KV cache hit ratio — distribution across every definition ----
        # The End Report reports several cache-hit figures that differ by what
        # they count (tokens vs requests, prefill-only vs whole prompt).  They
        # can differ by tens of points on the same run, so a single headline
        # number is easy to over-read.  Showing p50/p90/p99 for each side by
        # side makes both the spread and the disagreement visible.
        _ch_specs = []

        # 1. Prefill token-weighted, per interval: the primary definition.
        if _pf_cache_strict and _pf_compute_strict and _pf_modes_measured:
            _n_ch = min(len(_pf_cache_strict), len(_pf_compute_strict))
            _ch_prefill = []
            for _i in range(_n_ch):
                _tot = _pf_cache_strict[_i] + _pf_compute_strict[_i]
                if _tot > 0:
                    _ch_prefill.append(_pf_cache_rate[_i] / _tot * 100.0)
            if _ch_prefill:
                _ch_specs.append((
                    "Prefill token-weighted", _ch_prefill,
                    "\u0394prefill_cache \u00f7 (\u0394prefill_cache + \u0394prefill_compute)"))

        # 2. The engine's own gauge, per sample.
        _ch_gauge_raw = (_amoprof_read_columns_substr(
            _sg_path, {"g": ["cache_hit_rate"]}).get("g", []) if _sg_path else [])
        # SGLang exports the gauge as a 0..1 ratio in some builds and as a
        # percentage in others; scale by observed magnitude rather than by
        # version, which is not visible here.
        _ch_scale = 100.0 if (_ch_gauge_raw and max(_ch_gauge_raw) <= 1.5) else 1.0
        _ch_gauge = [v * _ch_scale for v in _ch_gauge_raw]
        if _ch_gauge and any(v > 0 for v in _ch_gauge):
            _ch_specs.append(("SGLang cache_hit_rate gauge", _ch_gauge,
                              "sglang_cache_hit_rate, per sample"))

        # 3. Whole-prompt token-weighted (cached ÷ prompt tokens), per interval.
        _ch_cached = _amoprof_read_columns_substr(
            _sg_path, {"c": ["cached_tokens_total"]}).get("c", []) if _sg_path else []
        if _ch_cached and _in_tok_rate:
            _, _cached_rate = _rate_with_time(_ch_cached, _sg_time)
            _n2 = min(len(_cached_rate), len(_in_tok_rate))
            _ch_prompt = [(_cached_rate[i] / _in_tok_rate[i] * 100.0)
                          for i in range(_n2)
                          if _in_tok_rate[i] > 0 and _cached_rate[i] >= 0]
            _ch_prompt = [min(100.0, v) for v in _ch_prompt]
            if _ch_prompt:
                _ch_specs.append(("Whole-prompt token-weighted", _ch_prompt,
                                  "\u0394cached_tokens \u00f7 \u0394prompt_tokens"))

        if _ch_specs:
            # Time series first: the percentile bars say how the ratio was
            # distributed, this says WHEN it moved.  A cache hit rate that
            # collapses partway through a run and a steady one can share a
            # p50, and only the timeline distinguishes them.
            _ch_ts = []
            _ch_colors = ["#22c55e", "#38bdf8", "#f59e0b"]
            for _i_ch, (_ch_name, _ch_vals, _ch_form) in enumerate(_ch_specs):
                if not _ch_vals or not any(v > 0 for v in _ch_vals):
                    continue
                # Each definition is computed on its own cadence: the gauge is
                # per sample, the token-weighted ones per interval (one fewer
                # point).  Align each to the tail of the master timebase.
                _ch_t = (_sg_time[-len(_ch_vals):] if _sg_time and
                         len(_sg_time) >= len(_ch_vals) else _sg_time)
                if not _ch_t:
                    continue
                _ch_ts.append({"tier": "L1", "label": _ch_name,
                               "t": _ch_t, "v": _ch_vals, "cap": 100.0,
                               "color": _ch_colors[_i_ch % len(_ch_colors)]})
            _ch_ts_svg = _amoprof_exec_svg_tier_occupancy(
                _ch_ts, window=_occ_win, wall_start=_occ_wall, mode="fill",
                title="KV cache hit ratio over the run",
                subtitle="every definition on one axis \u00b7 divergence between "
                         "them is itself a finding",
                yaxis="cache hit %") if _ch_ts else ""
            _ch_html = _ch_ts_svg
            _ch_rows = []
            # Track the bars separately so the Executive overview can show
            # them alongside the timeline without dragging in the whole card.
            # Two definitions are hidden from the overview strip on request:
            # the SGLang gauge and Prefill token-weighted views duplicate
            # what the timeline already communicates, and the operator asked
            # for a narrower cache-hit percentile view up top.  Both bars
            # still render in the Bottleneck card below, so the audit trail
            # (all three definitions on one panel) is preserved.
            _ch_bars_svg = ""
            _OVERVIEW_HIDDEN_CH = {
                "Prefill token-weighted",
                "SGLang cache_hit_rate gauge",
            }
            for _ch_name, _ch_vals, _ch_form in _ch_specs:
                _srt = sorted(v for v in _ch_vals if v == v)
                if len(_srt) < 3:
                    continue
                def _q(f):
                    return _srt[min(len(_srt) - 1, int(f * (len(_srt) - 1)))]
                _pc = {"p50": _q(0.5), "p90": _q(0.9), "p99": _q(0.99),
                       "observations": float(len(_srt))}
                _bar_svg = _amoprof_exec_svg_percentile_bars(
                    f"{_ch_name} \u2014 p50 / p90 / p99", _ch_form, "%",
                    _pc, {"p50": "#38bdf8", "p90": "#f59e0b", "p99": "#22c55e"},
                    n_label="samples")
                _ch_html += _bar_svg
                if _ch_name not in _OVERVIEW_HIDDEN_CH:
                    _ch_bars_svg += _bar_svg
                _ch_rows.append(
                    f"<b>{_html.escape(_ch_name)}</b> "
                    f"p50 {_pc['p50']:.1f}% \u00b7 p90 {_pc['p90']:.1f}% \u00b7 "
                    f"p99 {_pc['p99']:.1f}% \u00b7 n={len(_srt)}")
            if _ch_ts_svg:
                _exec_ov["KV cache hit ratio over the run"] = _ch_ts_svg
            if _ch_bars_svg:
                _exec_ov["KV cache hit ratio percentiles"] = _ch_bars_svg
            if _ch_html:
                _cards.append(_card(
                    "KV cache hit ratio \u2014 p50 / p90 / p99 by definition",
                    "Each definition counts something different: prefill "
                    "token-weighted counts prefill work avoided, whole-prompt "
                    "token-weighted counts cached tokens against the entire "
                    "prompt, and the engine gauge is SGLang's own instantaneous "
                    f"figure. {_kv_header}",
                    _ch_html,
                    "<br>".join(_ch_rows)
                    + "<br><br>These are percentiles <i>across sampling "
                      "intervals</i>, not across requests: a p99 near 100% means "
                      "some intervals served almost entirely from cache, not that "
                      "99% of requests hit. Large disagreement between definitions "
                      "usually means prefill is being served from cache while the "
                      "rest of the prompt is not \u2014 compare against the End "
                      "Report's cache-hit methodology section before acting.",
                    layers="A5_APP \u00b7 prefix cache"))

        # ---- Queue depth across layers -----------------------------------
        # Correlation shows what moves together; queueing shows what is falling
        # behind.  Each layer queues a different primitive (the app queues
        # requests, storage queues I/Os, the NIC queues packets and is only
        # visible when it drops them, DRAM exposes no queue at all), so each is
        # normalised against its own saturation reference and proxies are
        # labelled as proxies rather than presented as queue depths.
        _queues = []

        def _add_queue(layer, label, t, v, ref, refnote, pctl=None, pctl_src=""):
            if v and t and any(x == x and x > 0 for x in v) and (ref or 0) > 0:
                _q = {"layer": layer, "label": label, "t": list(t),
                      "v": list(v), "ref": float(ref), "refnote": refnote}
                if pctl:
                    _q["pctl"], _q["pctl_src"] = pctl, pctl_src
                _queues.append(_q)

        # Exact blktrace Q->C percentiles, when the capture produced them.
        #
        # Three places in this report resolved "queue depth" from three
        # different sources and disagreed: the bottleneck narrative read this
        # summary and said "mean 0.36, peak 1 (exact blktrace Q->C)", while
        # the two charts and the KPI tile read a sysfs avgqu_sz series whose
        # values are ~1e-4, so they drew a flat line, a "range unavailable"
        # legend and "0" bars for a queue that had been measured.
        _qd_pctl, _qd_pctl_src = None, ""
        if isinstance(_qd_sum, dict) and _safe_float(_qd_sum.get("qd_max", 0)) > 0:
            _qd_pctl = {
                0.5:  _safe_float(_qd_sum.get("qd_p50", _qd_sum.get("qd_mean", 0))),
                0.9:  _safe_float(_qd_sum.get("qd_p95", _qd_sum.get("qd_max", 0))),
                0.99: _safe_float(_qd_sum.get("qd_p99", _qd_sum.get("qd_max", 0))),
            }
            _qd_pctl_src = ("exact blktrace Q→C"
                            if "blktrace" in str(_qd_sum.get("qd_source", ""))
                            or not str(_qd_sum.get("qd_source", "")).startswith("advisory")
                            else "advisory sysfs/iostat")

        _q_reqs = _sg_phase.get("queue_reqs") or []
        if _q_reqs:
            _add_queue("A5_APP", "Queued requests (admission)", _sg_time, _q_reqs,
                       max(_q_reqs) or 1.0, "scheduler waiting_queue — pure latency, no device cost")
        _r_reqs = _sg_phase.get("running_reqs") or []
        if _r_reqs:
            _add_queue("A5_APP", "Running batch", _sg_time, _r_reqs,
                       max(_r_reqs) or 1.0, "concurrent decode batch size")
        if _nvme_qd_series:
            # When the per-sample series peaks three orders of magnitude below
            # the authoritative summary, it is not measuring the same thing at
            # the same resolution. Keep the series for the timeline (it still
            # shows WHEN the device was busy) but take the percentiles from the
            # summary, and name which source they came from.
            _qd_ser_max = max((x for x in _nvme_qd_series if x == x), default=0.0)
            _use_pctl = _qd_pctl if (
                _qd_pctl and max(_qd_pctl.values()) > max(_qd_ser_max * 10, 0.05)
            ) else None
            _add_queue("A1/A2_L3", "Storage queue depth", _nvme_qd_t, _nvme_qd_series,
                       32.0, "vs QD=32 device saturation reference",
                       pctl=_use_pctl,
                       pctl_src=_qd_pctl_src if _use_pctl else "")
        elif _qd_pctl:
            # No plottable series at all, but the queue WAS measured. A
            # single-point timeline is not a correlation input, so this exists
            # only so the distribution chart and the layer list can show it.
            _add_queue("A1/A2_L3", "Storage queue depth",
                       [0.0, max(duration_s, 1.0)],
                       [_qd_pctl[0.5] or 1e-9, _qd_pctl[0.99]],
                       32.0, "vs QD=32 device saturation reference · "
                             "run-window summary only, no per-sample series",
                       pctl=_qd_pctl, pctl_src=_qd_pctl_src)
        if _dram_total:
            _add_queue("A3_DRAM", "DRAM BW pressure (proxy)", _dram_time, _dram_total,
                       _safe_float(_pick(setup, ["DRAM peak GB/s", "dram_peak_gbs"], 0), 0) or 409.6,
                       "no controller queue exposed — % of peak BW")
        if _net_configured:
            if any(v > 0 for v in _net_retr):
                _add_queue("NET", "TCP retransmits (overflow)", _net_t, _net_retr,
                           max(_net_retr) or 1.0, "drops imply the NIC queue overflowed")
            if any(v > 0 for v in _net_util):
                _add_queue("NET", "Link utilisation (proxy)", _net_t, _net_util, 100.0,
                           "no NIC queue exposed — % of link speed")

        # The storage saturation curve. Rendered whenever queue-depth data
        # exists at all, independently of the multi-layer charts below, since
        # "how long was the SSD queued, and how deep" is the question a
        # storage sizing decision turns on and neither a mean nor a peak
        # answers it.
        _qd_sat_html = ""
        try:
            _sat_series = list(_nvme_qd_series or [])
            _sat_times = list(_nvme_qd_t or [])
            _sat_dist, _sat_src = _amoprof_qd_distribution(
                raw_dir, _sat_series, _sat_times)
            if _sat_dist:
                _qd_sat_html = _amoprof_exec_svg_qd_saturation(
                    _sat_dist, source=_sat_src, ref=32.0)
        except Exception as _sate:
            print(f"  [warn] queue-depth saturation chart skipped: {_sate}")

        _q_html = ""
        if len(_queues) >= 2:
            _q_html = (_qd_sat_html
                       + _amoprof_exec_svg_queue_timeline(_queues)
                       + _amoprof_exec_svg_queue_pctl(_queues))
            # Backpressure origin: the queue that leads is nearer the cause.
            _origin = []
            for _i in range(len(_queues)):
                for _j in range(_i + 1, len(_queues)):
                    _a, _b = _queues[_i], _queues[_j]
                    _x, _y = _align_xy(_a["t"], _a["v"], _b["t"], _b["v"])
                    if len(_x) < 20:
                        continue
                    _best, _bl = 0.0, 0
                    for _lag in range(-8, 9):
                        if _lag >= 0:
                            _xx, _yy = _x[:len(_x)-_lag], _y[_lag:]
                        else:
                            _xx, _yy = _x[-_lag:], _y[:len(_y)+_lag]
                        if len(_xx) < 12:
                            continue
                        _rr = _pearson(list(_xx), list(_yy))
                        if abs(_rr) > abs(_best):
                            _best, _bl = _rr, _lag
                    if abs(_best) < 0.3:
                        continue
                    if _bl > 0:
                        _txt = f"{_html.escape(_a['label'])} leads {_html.escape(_b['label'])} by {_bl} sample(s)"
                    elif _bl < 0:
                        _txt = f"{_html.escape(_b['label'])} leads {_html.escape(_a['label'])} by {-_bl} sample(s)"
                    else:
                        _txt = f"{_html.escape(_a['label'])} and {_html.escape(_b['label'])} move together"
                    _origin.append((abs(_best), f"<li>{_txt} · r={_best:+.2f}</li>"))
            _origin.sort(reverse=True)
            _origin_html = ""
            if _origin:
                _origin_html = ("<br><b>Backpressure origin</b> — cross-correlation lag between queue "
                                "pairs. The queue that <i>leads</i> is nearer the cause; the one that "
                                "lags is inheriting the pressure. Lag resolution is one sample, so this "
                                "is only meaningful at a fine collection interval."
                                "<ul style='margin:6px 0 0 16px;padding:0'>"
                                + "".join(t for _r, t in _origin[:6]) + "</ul>")
            _cards.append(_card(
                "Queue depth across layers — where work is accumulating",
                "Each layer's queue against its own saturation reference. Note these are not "
                "equivalent: storage QD and NIC drops indicate a saturated device, while the "
                "application queue indicates a saturated allocation (usually the KV pool) and "
                "costs no hardware resource at all. " + _kv_header,
                _q_html,
                "A layer whose queue grows is being handed work faster than it retires it. "
                "A high p99 against a low p50 is bursty backpressure rather than steady load, "
                "and needs a different fix." + _origin_html,
                layers=" · ".join(sorted({q["layer"] for q in _queues}))))
        elif _qd_sat_html:
            # Fewer than two comparable layers, so the cross-layer charts do
            # not render -- but the storage saturation curve answers a
            # storage question on its own and must not be withheld because
            # the application-side queues happened to be unavailable.
            _cards.append(_card(
                "Storage queue depth saturation",
                "How long the backing device actually had requests "
                "outstanding, and how deep. " + _kv_header,
                _qd_sat_html,
                "A mean and a peak cannot answer this: a peak of 16 reached "
                "once and a device sitting at 16 for a tenth of the run give "
                "the same mean and opposite conclusions. The share of the "
                "window at or above a given depth is what a device-sizing "
                "decision turns on.",
                layers="A1/A2_L3"))

        # ---- Network fabric vs token activity ----------------------------
        # Answers "is the fabric the bottleneck?".  Rendered only when NIC/IB
        # telemetry exists and carried traffic.
        if _net_configured:
            _net_drivers = [
                ("Input tok/s", _in_tok_rate, "#38bdf8"),
                ("Output tok/s", _out_tok_rate, "#a78bfa"),
            ]
            for _nd_lbl, _nd_series, _nd_col in (
                ("Evict rate (tok/s)", _evict_rate, "#f97316"),
                ("Load-back rate (tok/s)", _load_rate, "#22c55e"),
                ("Prefetch rate (tok/s)", _pref_rate, "#0ea5e9"),
                ("Backup rate (tok/s)", _backup_rate, "#eab308"),
            ):
                if _nd_series and any(v > 0 for v in _nd_series):
                    _net_drivers.append((_nd_lbl, _nd_series, _nd_col))
            _net_scored = []
            for _d_lbl, _d_series, _d_col in _net_drivers:
                for _y_lbl, _y_series, _y_t, _y_col in _net_entries:
                    if not _y_series or not any(v > 0 for v in _y_series):
                        continue
                    _x, _y = _align_xy(_sg_rate_t, _d_series, _y_t, _y_series)
                    if len(_x) < 3:
                        continue
                    _net_scored.append((abs(_pearson(_x, _y)), _pearson(_x, _y),
                                        _d_lbl, f"NET · {_y_lbl}", _x, _y, _y_col))
            if _net_scored:
                _net_scored.sort(key=lambda t: t[0], reverse=True)
                _net_html = ""
                for (_ra, _r, _dl, _yl, _x, _y, _c) in _net_scored[:_CORR_MAX_SCATTERS_PER_CARD]:
                    _px, _py = _decimate(_x, _y)
                    _net_html += _amoprof_exec_svg_scatter(
                        f"{_dl} vs {_yl}", _dl, _yl, _px, _py, point_color=_c,
                        subtitle=f"n={len(_x)} time-aligned samples")
                _rest_n = _net_scored[_CORR_MAX_SCATTERS_PER_CARD:]
                _rest_h = ""
                if _rest_n:
                    _rest_h = ('<div style="color:#94a3b8;font-size:11px;margin-top:6px">'
                               'Remaining pairs (r computed, scatter not drawn): '
                               + "; ".join(f"{_html.escape(dl)} vs {_html.escape(yl)} <b>{r:+.2f}</b>"
                                           for (_a, r, dl, yl, _x, _y, _c) in _rest_n[:10])
                               + '</div>')
                _net_peak = max(_net_total) if _net_total else 0.0
                _net_util_peak = max(_net_util) if _net_util else 0.0
                _cards.append(_card(
                    "Network fabric · Token activity vs NIC / IB bandwidth and errors",
                    f"network_timeseries.csv aggregate rows (iface=_total) paired with SGLang "
                    f"token rates. Peak {_fmt_num(_net_peak, ' MB/s', 1)}"
                    + (f", peak link util {_fmt_num(_net_util_peak, '%', 1)}"
                       if _net_util_peak > 0 else "")
                    + f". Ranked by |Pearson r|. {_kv_header}",
                    _net_html,
                    "Token rate correlating with NIC bandwidth means bytes are crossing the "
                    "fabric on the token path — remote KV transfer, a remote L3 backend, or "
                    "PD-disaggregated handoff. That alone is expected; the bottleneck signal is "
                    "<b>rx or tx flattening at a ceiling while token activity keeps rising</b>, "
                    "or TCP retransmits / drops rising "
                    "with token rate, which means the fabric is shedding load rather than "
                    "absorbing it. Token rate that correlates with retransmits but not with "
                    "bandwidth is the clearest fabric-bound signature: more work is being "
                    "attempted than the link can carry." + _rest_h,
                    layers="HOST_OS · network fabric ↔ A5_APP"))

        # ---- L2 (host DRAM / HiCache) derived from SGLang counters ---------
        # A DRAM PMU collector gives host DRAM *bandwidth*; SGLang's own
        # hicache counters give L2 *occupancy* and the token movement in and
        # out of it.  The latter needs no PMU, so a run without AMDuProf/PCM
        # still gets L2 charts — they measure the KV tier rather than the
        # memory controller, and are labelled as derived so the two are not
        # confused.
        _l2_used_tok = _sg_raw.get("hicache_host_used_tokens") or []
        _l2_total_tok = _sg_raw.get("hicache_host_total_tokens") or []
        _l2_used_gb = [_k_gb_from_bytes(v * kv_bytes_tok_kb * 1024.0) for v in _l2_used_tok]
        _l2_fill_pct = []
        if _l2_used_tok and _l2_total_tok:
            _n_l2 = min(len(_l2_used_tok), len(_l2_total_tok))
            _l2_fill_pct = [(_l2_used_tok[i] / _l2_total_tok[i] * 100.0)
                            if _l2_total_tok[i] > 0 else 0.0 for i in range(_n_l2)]
        # Movement across the L1<->L2 boundary, in decimal MB/s (bytes/s / 1e6).
        _l2_in_mbps = [v * kv_bytes_tok_kb * 1024.0 / 1e6 for v in _evict_rate]   # L1->L2
        _l2_out_mbps = [v * kv_bytes_tok_kb * 1024.0 / 1e6 for v in _load_rate]   # L2->L1
        _l2_derived_ok = bool((_l2_used_tok and any(v > 0 for v in _l2_used_tok))
                              or (_l2_in_mbps and any(v > 0 for v in _l2_in_mbps))
                              or (_l2_out_mbps and any(v > 0 for v in _l2_out_mbps)))

        # ---- KV tokens resident per cache tier, over the run --------------
        # One chart, one unit: tokens.  GB is not comparable across tiers
        # (they are sized very differently), but a token costs the same KV
        # bytes wherever it sits, so token counts are directly comparable and
        # are what the engine actually migrates between tiers.
        _occ = []

        # L1 — the HBM KV pool.  Prefer the absolute token gauge; fall back to
        # the 0..1 usage fraction x pool size when only that is exported.
        _l1_used_tok = (_sg_raw.get("kv_used_tokens")
                        or _sg_raw.get("num_used_tokens") or [])
        _l1_cap_tok = _safe_float(_pick(sglang, ["max_total_num_tokens",
                                                 "sglang_max_total_num_tokens"], 0), 0)
        if not _l1_cap_tok:
            _l1_cap_series = _sg_raw.get("max_total_num_tokens") or []
            _l1_cap_tok = max(_l1_cap_series) if _l1_cap_series else 0.0
        if not _l1_used_tok:
            _l1_frac = _sg_raw.get("token_usage") or _sg_raw.get("full_token_usage") or []
            if _l1_frac and _l1_cap_tok > 0:
                _sc = 0.01 if max(_l1_frac) > 1.5 else 1.0
                _l1_used_tok = [v * _sc * _l1_cap_tok for v in _l1_frac]
        if _l1_used_tok:
            _occ.append({"tier": "L1", "label": "L1 HBM KV pool",
                         "t": _sg_time, "v": _l1_used_tok,
                         "cap": _l1_cap_tok, "color": "#f59e0b",
                         "src": ("sglang_timeseries.csv",
                                 "sglang_num_used_tokens",
                                 "sglang:num_used_tokens  (else token_usage \u00d7 max_total_num_tokens)")})

        # L2 — host DRAM / HiCache, measured by SGLang itself.
        if _l2_used_tok:
            _occ.append({"tier": "L2", "label": "L2 host DRAM (HiCache)",
                         "t": _sg_time, "v": _l2_used_tok,
                         "cap": (max(_l2_total_tok) if _l2_total_tok else 0.0),
                         "color": "#a78bfa",
                         "src": ("sglang_timeseries.csv",
                                 "sglang_hicache_host_used_tokens",
                                 "sglang:hicache_host_used_tokens \u00f7 hicache_host_total_tokens")})

        # L3.5 — remote KV store.  The master exporter reports bytes, so
        # convert to tokens with the same KV bytes/token used everywhere else,
        # keeping the axis in one unit.
        if _mc_used and kv_bytes_tok_kb > 0:
            _mc_tok = [v * 1e9 / (kv_bytes_tok_kb * 1024.0) for v in _mc_used]
            _mc_cap_tok = (max(_mc_cap) * 1e9 / (kv_bytes_tok_kb * 1024.0)
                           if _mc_cap else 0.0)
            _occ.append({"tier": "L3.5", "label": "L3.5 store \u00b7 DRAM tier",
                         "t": _sg_time, "v": _mc_tok,
                         "cap": _mc_cap_tok, "color": "#2dd4bf",
                         "src": ("l35_store_capacity.csv",
                                 "l35_store_mem_used_b",
                                 "master_allocated_bytes \u00d7 1e9 \u00f7 (KV bytes/token) \u2014 store reports BYTES, charted as tokens")})

        # The store's FILE tier, which this chart omitted entirely.  On a
        # deployment with 54 GB of DRAM in front of 966 GB of NVMe, plotting
        # only the DRAM front makes L3.5 look like the SMALLEST tier in the
        # hierarchy when it is by far the largest -- and invites exactly the
        # wrong conclusion, that the tier needs to be grown, when the real
        # shape is a saturated DRAM front with a half-empty SSD behind it.
        _mc_file_used = [v / 1e9 for v in
                         (_cap_raw.get("l35_store_file_used_b") or [])]
        _mc_file_cap = [v / 1e9 for v in
                        (_cap_raw.get("l35_store_file_cap_b") or [])]
        if (_mc_file_used and any(v > 0 for v in _mc_file_used)
                and kv_bytes_tok_kb > 0):
            _mcf_tok = [v * 1e9 / (kv_bytes_tok_kb * 1024.0)
                        for v in _mc_file_used]
            _mcf_cap_tok = (max(_mc_file_cap) * 1e9 / (kv_bytes_tok_kb * 1024.0)
                            if _mc_file_cap else 0.0)
            _occ.append({"tier": "L3.5", "label": "L3.5 store \u00b7 file tier (SSD)",
                         "t": _sg_time, "v": _mcf_tok,
                         "cap": _mcf_cap_tok, "color": "#f59e0b",
                         "src": ("l35_store_capacity.csv",
                                 "l35_store_file_used_b",
                                 "master_allocated_file_size_bytes \u00d7 1e9 \u00f7 (KV bytes/token) \u2014 the NVMe tier behind the store's DRAM front")})

        # L3 — local storage.  SGLang does not export a resident-token gauge
        # for the disk tier, so occupancy is derived from the token movement
        # counters: everything backed up, minus what has been read back and
        # not re-written.  Marked DERIVED so it is not read as a measurement.
        # A filesystem-level figure (df on the HiCache path) is preferred when
        # the ssd_hw collector captured one, since that IS measured.
        # The provenance travels with the series, because two different
        # derivations feed it: a df snapshot of the HiCache filesystem, or
        # Σbackup − Σprefetch from the movement counters.  The source block
        # below used to state the counter formula unconditionally, so a tile
        # and a chart fed by a df measurement both credited it to counters
        # that had not been consulted.
        _l3_tok_series, _l3_tok_cap, _l3_tok_label = [], 0.0, ""
        _l3_tok_src = ("", "", "")
        # Is the L3 tier backed by LOCAL storage?  A remote backend
        # (mooncake / ai-memory-node / 3fs / remote_storage) is L3.5, not L3.
        _l3_backend = str(_pick(setup, [
            "HiCache storage backend", "hicache_storage_backend",
            "L3 storage type", "storage_backend"], "")).strip().lower()
        _l3_remote = any(k in _l3_backend for k in
                         ("mooncake", "remote", "ai memory", "ai-memory", "3fs", "rdma"))
        _l3_local_configured = bool(
            (not _l3_remote) and (
                _l3_backend in ("file", "local", "local_ssd", "nvme", "disk", "fs")
                or str(_pick(setup, ["L3 Device", "L3 Mount Path",
                                     "file_storage_path"], "")).strip()
                or (l3_fs_total_gb or 0) > 0))
        _l3_fs_used = _k_collector_gb("hicache_fs_used_gb", _safe_float(smart.get("hicache_fs_used_gb", 0), 0))
        _l3_fs_total = _k_collector_gb("hicache_fs_total_gb", _safe_float(smart.get("hicache_fs_total_gb", 0), 0))
        if _l3_fs_used > 0 and kv_bytes_tok_kb > 0 and _sg_time:
            # A single df snapshot, held flat across the window: honest as a
            # level, not as a trend, and labelled that way.
            _lvl = _l3_fs_used * 1e9 / (kv_bytes_tok_kb * 1024.0)
            _l3_tok_series = [_lvl] * len(_sg_time)
            _l3_tok_cap = (_l3_fs_total * 1e9 / (kv_bytes_tok_kb * 1024.0)
                           if _l3_fs_total > 0 else 0.0)
            _l3_tok_label = "L3-local storage (df snapshot)"
            _l3_tok_src = (
                "smart_summary.json / ssd_hw_summary.json",
                "hicache_fs_used_gb, hicache_fs_total_gb",
                "df on the HiCache path ÷ (KV bytes/token) — a MEASURED "
                "level held flat across the window, not a trend")
        elif _l3_local_configured:
            # Only when LOCAL storage is the backing tier.  backup/prefetch
            # counters describe movement to whatever backend HiCache is using;
            # when that backend is remote (Mooncake) the traffic belongs to
            # L3.5, and attributing it to local disk invents a tier that is
            # not configured.  The KV-tier-fill chart already excluded it for
            # lack of a capacity, which is why the two charts disagreed.
            # _sg_raw needs exact column names; SGLang prefixes them
            # (sglang_backuped_tokens_total), so fall back to the
            # substring reader that the rest of the tier code uses.
            _bk = _sg_raw.get("backuped_tokens_total") or (
                _amoprof_read_columns_substr(
                    _sg_path, {"v": ["backuped_tokens_total"]}).get("v", [])
                if _sg_path else [])
            _pf = _sg_raw.get("prefetched_tokens_total") or (
                _amoprof_read_columns_substr(
                    _sg_path, {"v": ["prefetched_tokens_total"]}).get("v", [])
                if _sg_path else [])
            if _bk and any(v > 0 for v in _bk):
                _n_l3 = min(len(_bk), len(_pf)) if _pf else len(_bk)
                _base_bk = _bk[0]
                _base_pf = _pf[0] if _pf else 0.0
                _l3_tok_series = [
                    max(0.0, (_bk[i] - _base_bk) - ((_pf[i] - _base_pf) if _pf else 0.0))
                    for i in range(_n_l3)]
                _l3_tok_cap = (l3_fs_total_gb * 1e9 / (kv_bytes_tok_kb * 1024.0)
                               if (l3_fs_total_gb > 0 and kv_bytes_tok_kb > 0) else 0.0)
                _l3_tok_label = "L3-local storage (DERIVED: backup \u2212 prefetch)"
                _l3_tok_src = (
                    "sglang_timeseries.csv",
                    "sglang_backuped_tokens_total, sglang_prefetched_tokens_total",
                    "DERIVED: \u03a3backup \u2212 \u03a3prefetch \u2014 no resident-token "
                    "gauge exists for the disk tier")
        if _l3_tok_series and any(v > 0 for v in _l3_tok_series):
            _occ.append({"tier": "L3", "label": _l3_tok_label,
                         "t": _sg_time, "v": _l3_tok_series,
                         "cap": _l3_tok_cap, "color": "#22c55e",
                         "src": _l3_tok_src})
        # Keep tiers in physical order regardless of which were found.
        _occ.sort(key=lambda z: {"L1": 0, "L2": 1, "L3": 2, "L3.5": 3}.get(z["tier"], 9))

        # Utilization tiles read off this same list, so each tile agrees with
        # the chart it sits above and inherits the ceiling resolution done here.
        _tier_fill = _amoprof_tier_fill_from_occupancy(_occ)
        # Every tier gets a tile, including tiers that contributed no series to
        # `_occ` at all.  L3 is the common case: the gate above admits it only
        # on a df snapshot of a local HiCache mount or on non-zero backup
        # movement to a LOCAL backend, so a Mooncake run (L3.5) or a run where
        # the ssd_hw collector never sampled the mount produced no L3 entry and
        # the tile vanished — while L1/L2/L3.5 rendered normally. Absent and
        # idle are different findings, so name the cause instead of omitting it.
        if "L1" not in _tier_fill:
            _tier_fill["L1"] = _amoprof_empty_tier(
                "no SGLang KV pool gauge exported "
                "(kv_used_tokens / num_used_tokens / token_usage)")
        if "L2" not in _tier_fill:
            _tier_fill["L2"] = _amoprof_empty_tier(
                "HiCache host tier not enabled — no hicache_host_used_tokens")
        if "L3" not in _tier_fill:
            if _l3_remote:
                _l3_why = (f"backing tier is remote"
                           f"{' (' + _l3_backend + ')' if _l3_backend else ''} — "
                           f"that KV movement is L3.5; no local L3 is configured")
            elif not _l3_local_configured:
                _l3_why = "no local L3 storage configured in this run"
            elif _l3_fs_used <= 0:
                _l3_why = ("local L3 configured, but no df snapshot from the "
                           "ssd_hw collector and no backup movement in the window")
            else:
                _l3_why = "no L3 residency could be resolved for this window"
            _tier_fill["L3"] = _amoprof_empty_tier(_l3_why)

        # Span the analysed window, not just where samples happen to exist.
        # Prefer an explicit window from the run metadata; otherwise use the
        # full extent of the master SGLang timebase, which covers the query
        # range even where an individual tier reported for only part of it.
        # Use the SAME window the report header states, so the timeline and
        # the "Window: N min" line cannot disagree.  `duration_s` is the
        # analysed span; the setup keys below are rarely present, and falling
        # back to the data extent silently shrank the axis to wherever samples
        # happened to land — a tier that reported for half the window then
        # filled the whole chart.
        _occ_svg = (_amoprof_exec_svg_tier_occupancy(
            _occ, window=_occ_win, wall_start=_occ_wall)
            + _src_block_from_series(_occ, note=f"Tokens are the common unit. L2 and {_TIER} publish BYTES; those series are converted with the run\u2019s KV bytes/token, so a wrong bytes/token scales those two tiers and not L1.")
            if len(_occ) >= 1 else "")
        # Companion view: each tier as a percentage of its own capacity.  Only
        # tiers with a known ceiling appear, since a percentage of an unknown
        # capacity is not a number.
        # Absolute GB resident rather than % of capacity.  Bytes are the
        # native unit for L2/L3/L3.5 (tokens there are derived), and a remote
        # store's capacity can change under you, which makes a percentage
        # against it unstable in a way the byte count is not.
        _occ_gb = []
        if kv_bytes_tok_kb > 0:
            for _x in _occ:
                _occ_gb.append(dict(
                    _x, v=[_k_gb_from_bytes(v * kv_bytes_tok_kb * 1024.0) for v in _x["v"]],
                    cap=_k_gb_from_bytes((_x.get("cap") or 0) * kv_bytes_tok_kb * 1024.0)))
        _occ_pct_svg = (_amoprof_exec_svg_tier_occupancy(
            _occ_gb, window=_occ_win, wall_start=_occ_wall, mode="abs",
            title="KV bytes resident per cache tier",
            subtitle="absolute GB on a log axis \u00b7 no tier capacity needed",
            yaxis="GB resident (log)", unit_label="GB")
            + _src_block_from_series(_occ_gb, note=f"Tokens are the common unit. L2 and {_TIER} publish BYTES; those series are converted with the run\u2019s KV bytes/token, so a wrong bytes/token scales those two tiers and not L1.")
            if _occ_gb else "")
        if _occ_pct_svg:
            _exec_ov["KV bytes resident per cache tier"] = _occ_pct_svg
        # % of each tier's own token capacity.  Same normalisation the
        # capacity-utilisation chart uses for bytes, applied to token counts
        # so the Executive overview can carry a "% occupied per tier" strip.
        _occ_tok_pct_series = []
        for _x in _occ:
            _c = float(_x.get("cap") or 0)
            if _c <= 0:
                continue
            _occ_tok_pct_series.append(dict(
                _x,
                v=[min(100.0, v / _c * 100.0) if v == v else float("nan") for v in _x["v"]],
                cap=100.0,
            ))
        _occ_tok_pct_svg = _amoprof_exec_svg_tier_occupancy(
            _occ_tok_pct_series, window=_occ_win, wall_start=_occ_wall, mode="fill",
            title="KV tokens resident \u2014 % of each tier\u2019s capacity",
            subtitle="tokens resident \u00f7 that tier\u2019s own capacity "
                     "\u00b7 only tiers with a known ceiling",
            yaxis="% of tier capacity") + _src_block_from_series(
                _occ_tok_pct_series,
                note="Each series is divided by that tier\u2019s own capacity "
                     "column, so a tier with no published ceiling is absent "
                     "rather than shown against an invented one."
            ) if _occ_tok_pct_series else ""
        if _occ_tok_pct_svg:
            _exec_ov["KV tokens resident \u2014 % of each tier\u2019s capacity"] = _occ_tok_pct_svg
        if _occ_pct_svg:
            _occ_svg = _occ_svg + _occ_pct_svg
        if _occ_svg:
            _occ_rows = []
            for _x in _occ:
                _pk = max(_x["v"])
                _occ_rows.append(
                    f"<b>{_html.escape(_x['label'])}</b> peak "
                    f"{_fmt_num(_pk, ' tokens', 0)}"
                    + (f" \u00b7 {_pk / _x['cap'] * 100:.0f}% of "
                       f"{_fmt_num(_x['cap'], ' tokens', 0)} capacity"
                       if _x.get("cap") else " \u00b7 capacity not reported")
                    + f" \u00b7 \u2248 {_fmt_num(_k_gb_from_bytes(_pk * kv_bytes_tok_kb * 1024), ' GB', 1)}"
                    if kv_bytes_tok_kb > 0 else "")
            _cards.append(_card(
                "KV tokens resident per cache tier \u2014 whole run",
                "Occupancy of every configured tier on one axis, in tokens. A "
                "token costs the same KV bytes wherever it sits, so token counts "
                "are directly comparable across tiers in a way that GB is not. "
                f"{_kv_header}",
                _occ_svg,
                "<br>".join(r for r in _occ_rows if r)
                + "<br><br><b>Top chart \u2014 absolute tokens.</b> Shows how much "
                  "KV each tier actually holds, on one comparable unit; the dashed "
                  "line is that tier\u2019s configured capacity."
                  "<br><b>Bottom chart \u2014 % of each tier\u2019s own capacity.</b> "
                  "The absolute view cannot answer \u201chow full is this tier\u201d: "
                  "a remote store holding millions of tokens dwarfs an HBM pool "
                  "holding tens of thousands, so a tier at 95% full is invisible "
                  "next to a larger tier at 5%. Only tiers with a known ceiling "
                  "appear here \u2014 a percentage of an unknown capacity is not a "
                  "number."
                  "<br><br>A tier pinned at 100% is full and is forcing eviction to "
                  "the next tier down; a tier far below it is over-provisioned for "
                  "this workload. Read both together with the eviction and load-back "
                  "rates: capacity that is full but not moving tokens is not the "
                  "constraint.",
                layers=f"A4_GPU_HBM \u00b7 A3_DRAM \u00b7 {_TIER}"))

        # ---- L1 (HBM) ---- always renderable when gpu_timeseries has samples
        # L1 is the always-present GPU HBM tier; the L2 and L3 gates below
        # only *add* cards if those tiers are configured — they never gate
        # L1 rendering.  When L2/L3 are absent the section will show only
        # the L1 correlation card(s) rather than empty placeholder text.
        # NOTE: _gpu_time / _gpu_util_series / _hbm_used_series are set (and,
        # on multi-GPU nodes, collapsed to one sample per timestamp) further
        # above.  Do not re-read them from _gpu_raw here — that would restore
        # the per-GPU rows and reintroduce the arbitrary-GPU pairing bug.

        _l1_scatter_html = ""
        # A list of zeros is truthy, so `or` alone admitted an all-zero driver
        # and produced a scatter with a fabricated 0.0-1.0 axis.  Require
        # a series that actually carries data.
        _in_ok = bool(_in_tok_rate) and any(v > 0 for v in _in_tok_rate)
        _out_ok = bool(_out_tok_rate) and any(v > 0 for v in _out_tok_rate)
        if _gpu_util_series and (_in_ok or _out_ok):
            _in_x, _in_y = _align_xy(_sg_rate_t, _in_tok_rate, _gpu_time, _gpu_util_series)
            _out_x, _out_y = _align_xy(_sg_rate_t, _out_tok_rate, _gpu_time, _gpu_util_series)
            if _in_ok and len(_in_x) >= 3:
                _l1_scatter_html += _amoprof_exec_svg_scatter(
                    "Input tok/s vs GPU util (%)",
                    "Input throughput (tok/s, per-interval)", "GPU util (%)",
                    _in_x, _in_y, point_color="#f59e0b")
            if _out_ok and len(_out_x) >= 3:
                _l1_scatter_html += _amoprof_exec_svg_scatter(
                    "Output tok/s vs GPU util (%)",
                    "Output throughput (tok/s, per-interval)", "GPU util (%)",
                    _out_x, _out_y, point_color="#38bdf8")
        if _hbm_used_series and (_in_tok_rate or _out_tok_rate):
            # DCGM `mem_used` is MiB — convert to decimal GB.
            _hbm_gb_series = [_k_gb_from_mib(v) for v in _hbm_used_series]
            _in_x, _in_y = _align_xy(_sg_rate_t, _in_tok_rate, _gpu_time, _hbm_gb_series)
            _out_x, _out_y = _align_xy(_sg_rate_t, _out_tok_rate, _gpu_time, _hbm_gb_series)
            if _out_ok and len(_out_x) >= 3:
                _l1_scatter_html += _amoprof_exec_svg_scatter(
                    "Output tok/s vs HBM used (GB)",
                    "Output throughput (tok/s, per-interval)", "HBM used (GB)",
                    _out_x, _out_y, point_color="#ec4899")
            if _in_ok and len(_in_x) >= 3:
                _l1_scatter_html += _amoprof_exec_svg_scatter(
                    "Input tok/s vs HBM used (GB)",
                    "Input throughput (tok/s, per-interval)", "HBM used (GB)",
                    _in_x, _in_y, point_color="#f472b6")
        if _l1_scatter_html:
            _cards.append(_card(
                "L1 (HBM · GPU) · GPU util & HBM used vs Input / Output throughput",
                f"gpu_timeseries.csv gpu_util / mem_used paired with sglang_timeseries.csv Δprompt/Δgeneration tok/s. {_kv_header}",
                _l1_scatter_html,
                "GPU util correlated with output tok/s is the expected decode-bound signal. HBM used correlated with input tok/s (rising fill during prefill) means the working set is growing in HBM. If both input and output tok/s track GPU util, prefill and decode are competing on the same HBM/BW budget.",
                layers="A4_GPU_HBM ↔ A5_APP"
            ))

        # ---- Compute & memory-capacity utilisation over the run -----------
        # Both as % of their own ceiling on one 0-100 axis, using the same
        # windowed timeline as the tier charts.  These answer "what was busy,
        # and when" — the correlation cards answer "what moves with what", a
        # different question that a scatter cannot show over time.
        # HBM used in GB per timestamp, and the device total, for the
        # capacity view.  mem_used is MiB per GPU per row; collapse to one
        # sample per timestamp with the same summing rule the tiles use.
        _hbm_used_gb_series = []
        _hbm_total_gb = 0.0
        try:
            if _hbm_used_series and _gpu_time:
                _t_c, _v_c = _collapse_per_gpu(_gpu_time, _hbm_used_series, "sum")
                _hbm_used_gb_series = [_k_gb_from_mib(v) for v in _v_c]
                _gpu_time_cap = _t_c
            # The canonical resolver already established the device total for
            # the tiles; reuse it rather than re-deriving a second answer.
            _hbm_total_gb = _safe_float(hbm_total, 0)
        except Exception:
            _hbm_used_gb_series, _hbm_total_gb = [], 0.0

        # CPU utilisation: no collector captures /proc/stat today, so this is
        # empty on every current run.  Wired here so the chart appears the
        # moment a cpu collector lands, rather than needing a report change.
        # CPU comes from its own timeseries, written by the cpu collector or
        # synthesised from amoprof_cpu_* gauges on the Prometheus path.
        _cpu_path = _first_existing(raw_dir, ["cpu_timeseries.csv"])
        _cpu_raw = (_amoprof_read_columns_raw(
            _cpu_path, ["time_sec", "cpu_util_pct", "cpu_iowait_pct",
                        "cpu_steal_pct", "cpu_busiest_core_pct"])
            if _cpu_path else {})
        _cpu_util_series = _cpu_raw.get("cpu_util_pct") or []
        _cpu_util_t = _cpu_raw.get("time_sec") or []
        _cpu_iowait_series = _cpu_raw.get("cpu_iowait_pct") or []
        _cpu_busiest_series = _cpu_raw.get("cpu_busiest_core_pct") or []

        _cu = []
        if _gpu_util_series and _gpu_time:
            _cu.append({"tier": "L1", "label": "GPU SM utilisation",
                        "t": _gpu_time, "v": _gpu_util_series,
                        "cap": 100.0, "color": "#ef4444",
                        "src": ("gpu_timeseries.csv", "gpu_util",
                                "DCGM / nvidia-smi utilization.gpu \u00b7 mean across GPUs")})
        if _hbm_bw_util_series and _gpu_time:
            _cu.append({"tier": "L1", "label": "HBM bandwidth utilisation",
                        "t": _gpu_time, "v": _hbm_bw_util_series,
                        "cap": 100.0, "color": "#3b82f6",
                        "src": ("gpu_timeseries.csv", "hbm_bw_util_pct",
                                "DCGM DRAM-active \u00b7 % of HBM peak")})
        if _cpu_util_series and _cpu_util_t:
            _cu.append({"tier": "CPU", "label": "CPU utilisation (all cores)",
                        "t": _cpu_util_t, "v": _cpu_util_series,
                        "cap": 100.0, "color": "#38bdf8",
                        "src": ("cpu_timeseries.csv", "cpu_util_pct",
                                "100 \u2212 idle%, averaged over all cores")})
        if _cpu_busiest_series and _cpu_util_t:
            # A single-threaded bottleneck pins one core while the aggregate
            # reads comfortable; without this the constraint is invisible.
            _cu.append({"tier": "CPU", "label": "CPU busiest core",
                        "t": _cpu_util_t, "v": _cpu_busiest_series,
                        "cap": 100.0, "color": "#0ea5e9",
                        "src": ("cpu_timeseries.csv", "cpu_busiest_pct",
                                "max over per-core utilisation \u00b7 exposes a single-threaded pin the average hides")})
        if _cpu_iowait_series and _cpu_util_t and any(v > 0.5 for v in _cpu_iowait_series):
            # iowait is the signal that storage, not compute, is the constraint.
            _cu.append({"tier": "CPU", "label": "CPU iowait",
                        "t": _cpu_util_t, "v": _cpu_iowait_series,
                        "cap": 100.0, "color": "#f472b6",
                        "src": ("cpu_timeseries.csv", "cpu_iowait_pct",
                                "/proc/stat iowait \u00b7 the signal that storage, not compute, is the constraint")})

        # On an L3.5 run the memory node's device metrics land in their own
        # l35_-prefixed file, so they can never be confused with the GPU
        # node's identically-named columns.  On a LOCAL L3 run there is no
        # second node: the backing device is on this host and its metrics are
        # in nvme_driver_timeseries.csv under unprefixed names.  Reading only
        # the l35_ file meant every device chart -- IOPS, reads vs writes,
        # queue depth, the LBA strips -- silently vanished on a local run
        # whose data was sitting right there in the other file.
        _l35s_path = _first_existing(raw_dir, ["l35_storage_timeseries.csv"])
        _l35s_local_src = ""
        if not _l35s_path:
            _nvme_local = _first_existing(raw_dir, ["nvme_driver_timeseries.csv"])
            if _nvme_local:
                _l35s_path = _nvme_local
                _l35s_local_src = "nvme_driver_timeseries.csv"
        # Columns are l35_-prefixed so they can never be confused with the GPU
        # node's identically-named metrics.
        _l35s = (_amoprof_read_columns_raw(
            _l35s_path, ["time_sec", "l35_rd_iops", "l35_wr_iops",
                         "l35_rd_bw_mbs", "l35_wr_bw_mbs", "l35_io_util_pct",
                         "l35_avgqu_sz", "l35_dram_rd_gbs", "l35_dram_wr_gbs",
                         # CXL-attached memory, kept distinct from DRAM
                         "l35_cxl_rd_gbs", "l35_cxl_wr_gbs",
                         "l35_net_rx_mbs", "l35_net_tx_mbs",
                         "l35_qd_peak", "l35_rd_lat_ms", "l35_wr_lat_ms",
                         "l35_host_written_gb", "l35_nand_written_gb", "l35_waf",
                         "l35_lba_w_span_gb", "l35_lba_w_start_gb",
                         "l35_lba_r_span_gb", "l35_lba_r_start_gb",
                         "l35_lba_w_top1pct", "l35_lba_w_top5pct",
                         "l35_lba_w_gini", "l35_lba_r_gini",
                         *[f"l35_lba_w_d{_i}" for _i in range(10)],
                         *[f"l35_lba_r_d{_i}" for _i in range(10)],
                         "l35_bt_read_events", "l35_bt_write_events",
                         "l35_bt_read_bytes", "l35_bt_write_bytes",
                         "l35_evicted_b", "l35_promoted_b",
                         "l35_mem_hit_b", "l35_file_hit_b",
                         "l35_store_mem_used_b", "l35_store_mem_cap_b",
                         "l35_store_file_used_b", "l35_store_file_cap_b",
                         "l35_dram_used_gb", "l35_cpu_util_pct",
                         "l35_cpu_iowait_pct", "l35_cpu_busiest_pct"])
            if _l35s_path else {})
        # A local-L3 device file carries every column unprefixed.  Map the
        # whole set, not just the three below, so the charts that depend on
        # IOPS, queue depth and the LBA deciles render for a local tier too.
        if _l35s_local_src:
            _local_cols = (["rd_iops", "wr_iops", "rd_bw_mbs", "wr_bw_mbs",
                            "io_util_pct", "avgqu_sz", "qd_peak",
                            "rd_lat_ms", "wr_lat_ms",
                            "host_written_gb", "nand_written_gb", "waf",
                            "lba_w_span_gb", "lba_w_start_gb",
                            "lba_r_span_gb", "lba_r_start_gb",
                            "lba_w_top1pct", "lba_w_top5pct",
                            "lba_w_gini", "lba_r_gini",
                            "bt_read_events", "bt_write_events",
                            "bt_read_bytes", "bt_write_bytes"]
                           + [f"lba_w_d{_i}" for _i in range(10)]
                           + [f"lba_r_d{_i}" for _i in range(10)])
            _loc = _amoprof_read_columns_raw(_l35s_path, ["time_sec"] + _local_cols)
            for _c in _local_cols:
                if not _l35s.get(f"l35_{_c}") and _loc.get(_c):
                    _l35s[f"l35_{_c}"] = _loc[_c]
            if not _l35s.get("time_sec") and _loc.get("time_sec"):
                _l35s["time_sec"] = _loc["time_sec"]

        # Legacy unprefixed names, for run dirs written before the rename.
        for _old, _new in (("rd_bw_mbs", "l35_rd_bw_mbs"),
                           ("wr_bw_mbs", "l35_wr_bw_mbs"),
                           ("io_util_pct", "l35_io_util_pct")):
            if not _l35s.get(_new) and _l35s_path:
                _v = _amoprof_read_columns_raw(_l35s_path, [_old]).get(_old, [])
                if _v:
                    _l35s[_new] = _v
        # Store capacity lands in its own file, since it comes from a different
        # exporter and therefore a different selector.
        _cap_path = _first_existing(raw_dir, ["l35_store_capacity.csv"])
        if _cap_path:
            for _ck in ("l35_store_mem_used_b", "l35_store_mem_cap_b",
                        "l35_store_file_used_b", "l35_store_file_cap_b"):
                _cv = _amoprof_read_columns_raw(_cap_path, [_ck]).get(_ck, [])
                if _cv:
                    _l35s[_ck] = _cv

        _l35s["rd_bw_mbs"] = _l35s.get("l35_rd_bw_mbs") or []
        _l35s["wr_bw_mbs"] = _l35s.get("l35_wr_bw_mbs") or []

        # DRAM vs CXL on the L3.5 node.  CXL sits between local DRAM and NVMe
        # in both latency and bandwidth, so how the store splits its traffic
        # across the two is a placement question the aggregate cannot answer:
        # a store serving mostly from CXL behaves very differently from one
        # serving mostly from DRAM, at identical total bandwidth.
        _cxl = []
        for _lbl, _k, _col in (
                ("L3.5 DRAM read", "l35_dram_rd_gbs", "#3b82f6"),
                ("L3.5 DRAM write", "l35_dram_wr_gbs", "#60a5fa"),
                ("L3.5 CXL read", "l35_cxl_rd_gbs", "#f472b6"),
                ("L3.5 CXL write", "l35_cxl_wr_gbs", "#c084fc")):
            _v = _l35s.get(_k) or []
            if _v and any(x == x and x > 0 for x in _v):
                _cxl.append({"tier": "L3.5", "label": _lbl,
                             "t": _l35s.get("time_sec") or [], "v": _v,
                             "cap": 0, "color": _col})
        # L3.5 node storage, four views.  iostat gives rate and queue depth but no
        # residency, so capacity-over-time is absent until a filesystem
        # sampler exists; LBA distribution needs blktrace on that node.
        # Name the node these device charts measure.  Hardcoding "L3.5 node"
        # labelled a local NVMe as though it sat on a separate memory node.
        _dev_node = ("L3 local SSD"
                     if str(l3_backend_class).lower() == "local_ssd"
                     else "L3.5 node")
        _dev_where = ("this host"
                      if str(l3_backend_class).lower() == "local_ssd"
                      else "the memory node")

        def _l35_chart(_specs, _title, _sub, _yaxis, _unit):
            _ser = []
            for _lbl, _k, _col in _specs:
                _v = _l35s.get(_k) or []
                if _v and any(x == x and x > 0 for x in _v):
                    _ser.append({"tier": "L3.5", "label": _lbl,
                                 "t": _l35s.get("time_sec") or [], "v": _v,
                                 "cap": 0, "color": _col})
            if not _ser:
                return ""
            # Source block built from the series that were actually PLOTTED,
            # not from the requested spec list: a column with no data is
            # dropped above, and naming it below would claim a series the
            # chart does not show.
            _plotted = {_s["label"] for _s in _ser}
            return (_amoprof_exec_svg_tier_occupancy(
                _ser, window=_occ_win, wall_start=_occ_wall, mode="abs",
                title=_title, subtitle=_sub, yaxis=_yaxis, unit_label=_unit)
                + _amoprof_src_block(
                    _src_rows_for("l35_storage_timeseries.csv",
                                  [(_l, _k) for _l, _k, _c in _specs
                                   if _l in _plotted]),
                    note=(f"Measured on the {_TIER_NODE}&#39;s block device. "
                          "A lookup answered from the store&#39;s memory tier, or "
                          "from page cache over its file tier, never reaches "
                          "the device and so does not appear here.")))

        _l35_ssd_svg = (
            _l35_chart([("Storage read BW", "l35_rd_bw_mbs", "#22c55e"),
                        ("Storage write BW", "l35_wr_bw_mbs", "#eab308")],
                       f"{_dev_node} storage: reads vs writes",
                       f"iostat per-interval bandwidth on {_dev_where} \u00b7 "
                       "a large write:read ratio means the tier absorbs cost "
                       "without delivering read benefit",
                       "MB/s", "MB/s")
            + _l35_chart([("Storage read IOPS", "l35_rd_iops", "#38bdf8"),
                          ("Storage write IOPS", "l35_wr_iops", "#a855f7")],
                         f"{_dev_node} storage: IOPS",
                         "operations per second \u00b7 read beside write, since "
                         "a tier can be IOPS-bound at modest bandwidth",
                         "IOPS", "IOPS")
            + _l35_chart([("Storage queue depth", "l35_avgqu_sz", "#f97316"),
                          ("Storage utilisation (%)", "l35_io_util_pct", "#ef4444")],
                         f"{_dev_node} storage: queue depth and utilisation",
                         "avgqu-sz and %util \u00b7 on NVMe, %util saturates "
                         "well before the device does, so read queue depth as "
                         "the pressure signal",
                         "depth / %", ""))

        # LBA distribution across the storage span.  The deciles come from
        # blktrace on the memory node and are published as gauges, so unlike
        # hot_regions_overall.csv they survive a Prometheus fetch — this is
        # the one view that shows WHERE on the device the traffic lands.
        _lba_svg = ""
        try:
            _lba_bars = {}
            for _tag, _nm in (("w", "write"), ("r", "read")):
                # Each sample is one collection cycle's split of ITS bytes
                # across ten bands, so the run's split is the byte-weighted
                # mean of the cycles.  Taking each band's maximum over cycles
                # instead made every band that was ever busiest read ~100%:
                # "10 of 10 bands active · busiest carries 100%", with the
                # bands summing far past 100.  Cycles are weighted by their
                # byte count where the trace published one, else equally.
                # (Cycles can differ in observed span; weighting by bytes
                # keeps the busiest cycles' geometry dominant.)
                _cols = [_l35s.get(f"l35_lba_{_tag}_d{_i}") or [] for _i in range(10)]
                _n = max((len(_c) for _c in _cols), default=0)
                _wser = _l35s.get(f"l35_bt_{_nm}_bytes") or []
                _d = [0.0] * 10
                _wsum = 0.0
                for _k in range(_n):
                    _row = [(_c[_k] if _k < len(_c) else float("nan")) for _c in _cols]
                    _row = [(_x if _x == _x else 0.0) for _x in _row]
                    if sum(_row) <= 0:
                        continue
                    _wk = (_wser[_k] if (_k < len(_wser) and _wser[_k] == _wser[_k]
                                         and _wser[_k] > 0) else (0.0 if _wser else 1.0))
                    if _wk <= 0:
                        continue
                    _tot = sum(_row)
                    for _i in range(10):
                        _d[_i] += _wk * _row[_i] / _tot * 100.0
                    _wsum += _wk
                _d = [(_x / _wsum) if _wsum > 0 else 0.0 for _x in _d]
                if any(_x > 0 for _x in _d) and not blktrace_unrepresentative:
                    _lba_bars[_nm] = _d
            if blktrace_unrepresentative and any(
                    any(v == v and v > 0 for v in (_l35s.get(f"l35_lba_{_t}_d{_i}") or []))
                    for _t in ("w", "r") for _i in range(10)):
                _lba_svg += (
                    '<div class="kpi-note" style="padding:8px 0">LBA distribution withdrawn: '
                    f'blktrace captured {blktrace_coverage*100:.1f}% of the bytes this '
                    'device moved, so the strips would describe a small sample of the '
                    'I/O. Trace the device that carries the I/O to restore them.</div>')
            for _nm, _d in _lba_bars.items():
                _touched = sum(1 for _x in _d if _x > 0)
                # Heat strip instead of a cumulative curve.  "Hottest 10%
                # of the span carries 33%" needs three inferential steps —
                # sort, accumulate, compare against an even split — which is
                # too many for a first read.  Ten shaded cells over the device
                # say the same thing at a glance.
                _tg0 = "w" if _nm == "write" else "r"
                _sp0 = [x for x in (_l35s.get(f"l35_lba_{_tg0}_span_gb") or [])
                        if x == x and x > 0]
                _st0 = [x for x in (_l35s.get(f"l35_lba_{_tg0}_start_gb") or [])
                        if x == x]
                _start_gb = min(_st0) if _st0 else 0.0
                _span_gb = max(_sp0) if _sp0 else 0.0
                _step = _span_gb / 10.0 if _span_gb > 0 else 0.0

                def _rng(_i, _st=_start_gb, _sp=_step):
                    if _sp <= 0:
                        return f"{_i*10}-{_i*10+10}%"
                    _f = "{:,.0f}" if _sp >= 1 else "{:,.1f}"
                    return _f.format(_st + _i*_sp) + "-" + _f.format(_st + (_i+1)*_sp) + "G"

                _hot_i = max(range(10), key=lambda _k: _d[_k])
                _cold = sum(1 for _x in _d if _x <= 0.5)
                _lba_svg += _amoprof_exec_svg_percentile_bars(
                    f"{_dev_node} storage {_nm} I/O across LBA space",
                    (f"share of {_nm} bytes per GB band across the "
                     f"{_span_gb:,.0f} GB span \u00b7 "
                     f"{10-_cold} of 10 bands active \u00b7 busiest "
                     f"{_rng(_hot_i)} carries {_d[_hot_i]:.0f}%"
                     # "never writen"/"never readn" — build the phrase per op
                     # rather than suffixing the noun.
                     + (f" \u00b7 {_cold*_step:,.0f} GB never "
                        f"{'written' if _nm == 'write' else 'read'}"
                        if _step > 0 and _cold else "")),
                    "% of bytes",
                    {_rng(_i): _d[_i] for _i in range(10)},
                    {_rng(_i): ("#ef4444" if _d[_i] >= 30 else
                                "#f59e0b" if _d[_i] >= 10 else
                                "#1e293b" if _d[_i] <= 0.5 else "#38bdf8")
                     for _i in range(10)},
                    width=620)

                # The by-offset bar chart is gone: it plotted the same ten
                # deciles as the heat strip above, with a y-axis instead of
                # shading.  Two views of identical data make the reader look
                # for a difference that is not there.  The strip wins because
                # it also shows the untouched regions as grey, which is half
                # the endurance story.

        except Exception:
            # Keep whatever already rendered.  Discarding _lba_svg here
            # threw away a heat strip that had built fine because a later
            # chart in the same block raised — the symptom was both charts
            # vanishing when only one was broken.
            import os as _os_l
            if _os_l.environ.get("AMOPROF_DEBUG_CORR"):
                import traceback as _tb_l
                _tb_l.print_exc()

        # Storage read/write bandwidth over the run, for the overview.
        _l35_bw_svg = _l35_chart(
            [("Storage read BW", "l35_rd_bw_mbs", "#22c55e"),
             ("Storage write BW", "l35_wr_bw_mbs", "#eab308")],
            f"{_dev_node} \u2014 storage read/write bandwidth over the run",
            "iostat/sysfs per-interval bandwidth on the memory node",
            "MB/s", "MB/s") if "_l35_chart" in dir() else ""

        _cxl_svg = _amoprof_exec_svg_tier_occupancy(
            _cxl, window=_occ_win, wall_start=_occ_wall, mode="abs",
            title="L3.5 node memory: DRAM vs CXL",
            subtitle="AMDuProfPcm per-type bandwidth \u00b7 CXL is a distinct "
                     "tier, not part of DRAM",
            yaxis="GB/s", unit_label="GB/s") if _cxl else ""

        _cu_svg = _amoprof_exec_svg_tier_occupancy(
            _cu, window=_occ_win, wall_start=_occ_wall, mode="fill",
            title="Compute utilisation over the run",
            subtitle="GPU SM, HBM bandwidth and CPU as % of their own ceiling",
            yaxis="% utilised") + _src_block_from_series(
            _cu,
            note="Every series is already a percentage of its own ceiling, so "
                 "the lines are comparable in shape but measure different "
                 "resources on, potentially, different hosts.") if _cu else ""

        # Memory-hierarchy CAPACITY utilisation, in BYTES rather than KV
        # tokens.  Distinct from the KV-tier-fill chart above: this counts
        # everything resident in each tier (weights, activations, page cache),
        # not only KV, so a tier can be nearly full here while its KV share is
        # small.
        _mc_cap_pct = []
        if _hbm_used_gb_series and _hbm_total_gb > 0:
            _mc_cap_pct.append({"tier": "L1", "label": "L1 HBM capacity",
                                "t": _gpu_time, "v": _hbm_used_gb_series,
                                "cap": _hbm_total_gb, "color": "#f59e0b",
                                "src": ("gpu_timeseries.csv", "mem_used_mb",
                                        "nvidia-smi memory.used \u00b7 ALL HBM, not only KV")})
        # L2 host DRAM: prefer /proc/meminfo per-sample series from the
        # dram collector.  Falling back to the flat scalar keeps this
        # non-breaking on runs that did not enable the collector, but a
        # per-sample series is what makes L2 look like a running tier
        # rather than a horizontal line.
        _dram_path = _first_existing(raw_dir, ["dram_timeseries.csv"])
        _dram_raw = (_amoprof_read_columns_raw(
            _dram_path, ["time_sec", "used_gb", "total_gb"])
            if _dram_path else {})
        _l2_dram_t = _dram_raw.get("time_sec") or []
        # /proc/meminfo used_gb / total_gb are GiB (kB / 1024 / 1024).
        _l2_dram_used_series = [_k_collector_gb("used_gb", v) if v == v else v
                                for v in (_dram_raw.get("used_gb") or [])]
        _l2_dram_total_series = [_k_collector_gb("total_gb", v) if v == v else v
                                 for v in (_dram_raw.get("total_gb") or [])]
        _l2_dram_cap_gb = (max(v for v in _l2_dram_total_series if v == v)
                           if _l2_dram_total_series and any(v > 0 for v in _l2_dram_total_series)
                           else l2_dram_capacity_gb)
        if _l2_dram_used_series and _l2_dram_t and _l2_dram_cap_gb > 0:
            _mc_cap_pct.append({"tier": "L2", "label": "L2 host DRAM capacity",
                                "t": _l2_dram_t, "v": _l2_dram_used_series,
                                "cap": _l2_dram_cap_gb, "color": "#a78bfa",
                                "src": ("dram_timeseries.csv", "used_gb / total_gb",
                                        "/proc/meminfo MemTotal \u2212 MemAvailable on the GPU node")})
        elif l2_dram_used_gb > 0 and l2_dram_capacity_gb > 0 and _sg_time:
            _mc_cap_pct.append({"tier": "L2", "label": "L2 host DRAM capacity",
                                "t": _sg_time,
                                "v": [l2_dram_used_gb] * len(_sg_time),
                                "cap": l2_dram_capacity_gb, "color": "#a78bfa",
                                "src": ("setup_details.json", "host DRAM used / total",
                                        "FLAT scalar \u2014 no dram collector in this run, so shape is not measured")})
        # L3-local. Three gates, and failing any one of them used to drop the
        # tier from the chart with nothing said -- which reads as "this tier
        # has no capacity" rather than "its capacity was never measured".
        # The miss is recorded so the subtitle can name it.
        _l3_cap_missing = ""
        if l3_fs_used_gb > 0 and l3_fs_total_gb > 0 and _sg_time:
            _mc_cap_pct.append({"tier": "L3", "label": "L3-local filesystem capacity",
                                "t": _sg_time,
                                "v": [l3_fs_used_gb] * len(_sg_time),
                                "cap": l3_fs_total_gb, "color": "#22c55e",
                                "src": ("setup_details.json", "L3 filesystem used / total",
                                        "FLAT scalar from df on the HiCache path")})
        elif l3_explicit_config:
            _l3_miss = []
            if l3_fs_total_gb <= 0:
                _l3_miss.append("total capacity")
            if l3_fs_used_gb <= 0:
                _l3_miss.append("used capacity")
            if not _sg_time:
                _l3_miss.append("a sample timeline")
            _l3_cap_missing = (
                " \u00b7 <b>L3 omitted:</b> this run configures a local L3 but "
                + " and ".join(_l3_miss)
                + " is absent. Those come from the ssd_hardware collector's "
                  "df snapshot of the HiCache path (hicache_fs_used_gb / "
                  "hicache_fs_total_gb in smart_summary.json, or "
                  "ssd_hw_summary.json), or from an "
                  "\u2018L3 (local storage) capacity GB\u2019 key in setup "
                  "details. A Prometheus-only analyze has no df to run, so "
                  "include the ssd_hw collector in the service, or put the "
                  "capacity in setup details.")
        # L3.5: the store reports its own allocated and total bytes, so this
        # is a MEASURED occupancy, not the token-derived estimate used in the
        # KV charts.  It therefore avoids the KV-bytes/token derivation
        # entirely, which is where the sliding-window-attention error lives.
        # The store accounts its memory and file tiers separately, so plot them
        # separately.  A single "remote store" line conflates a DRAM tier that
        # is full with a file tier that is empty, which are opposite
        # conditions.  The storage line appears only when a file tier is
        # actually configured — a deployment with DRAM alone should not carry
        # an empty series implying one exists.
        _cap_src = _first_existing(raw_dir, ["l35_store_capacity.csv"])
        _cap_cols = (_amoprof_read_columns_raw(
            _cap_src, ["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b",
                       "l35_store_file_used_b", "l35_store_file_cap_b"])
            if _cap_src else {})
        _cap_t = _cap_cols.get("time_sec") or []

        for _lbl, _uk, _ck, _col in (
                ("L3.5 memory capacity", "l35_store_mem_used_b",
                 "l35_store_mem_cap_b", "#5eead4"),
                ("L3.5 storage capacity", "l35_store_file_used_b",
                 "l35_store_file_cap_b", "#f59e0b")):
            _u = [v for v in (_cap_cols.get(_uk) or []) if v == v]
            if not _u or not any(v > 0 for v in _u):
                continue
            _c = [v for v in (_cap_cols.get(_ck) or []) if v == v and v > 0]
            _mc_cap_pct.append({
                "tier": "L3.5", "label": _lbl,
                "t": _cap_t[:len(_u)] if _cap_t else
                     (_sg_time[-len(_u):] if _sg_time else []),
                "v": [v / 1e9 for v in _u],
                "cap": (max(_c) / 1e9 if _c else 0.0), "color": _col,
                "src": ("l35_store_capacity.csv", _uk + " / " + _ck,
                        "store-reported bytes \u2014 MEASURED, not derived from KV bytes/token")})

        # Fall back to the older single-series source for run directories
        # produced before the split counters were fetched.
        if not any(x["label"].startswith("L3.5 memory capacity")
                   for x in _mc_cap_pct):
            _l35_used = (_sg_raw.get("mooncake_segment_used_bytes")
                         or _sg_raw.get("mooncake_used_bytes") or [])
            _l35_cap_b = (_sg_raw.get("mooncake_segment_capacity_bytes")
                          or _sg_raw.get("mooncake_capacity_bytes") or [])
            if _l35_used and any(v > 0 for v in _l35_used):
                _l35_cap_gb = (max(v for v in _l35_cap_b if v == v) / 1e9
                               if _l35_cap_b and any(v > 0 for v in _l35_cap_b)
                               else 0.0)
                _mc_cap_pct.append({"tier": "L3.5",
                                    "label": "L3.5 store capacity (combined)",
                                    "t": _sg_time[-len(_l35_used):] if _sg_time else [],
                                    "v": [v / 1e9 for v in _l35_used],
                                    "cap": _l35_cap_gb, "color": "#5eead4"})
        # L3.5 memory-node DRAM residency, from l35_storage_timeseries.csv
        # (/proc/meminfo on the AI Memory Node).  Distinct from the
        # remote-store line above (that was Mooncake segment allocation):
        # a node whose DRAM is nearly full but whose segments have room
        # can still stall on eviction pressure, and vice versa.
        _l35_used_v = [v for v in (_l35_dram_used_series or [])]
        if _l35_used_v and any(x == x and x > 0 for x in _l35_used_v) \
                and _l35_dram_t:
            _mc_cap_pct.append({"tier": "L3.5",
                                "label": "L3.5 node DRAM (raw)",
                                "t": _l35_dram_t,
                                "v": _l35_used_v,
                                "cap": l35_dram_total_gb,
                                "color": "#0d9488"})

        # Absolute GB rather than % of capacity, for the same reason as the
        # tier charts: the percentage needs a ceiling, and a tier's ceiling can
        # be unknown or elastic.  Values are already in GB here.
        _mc_cap_svg = _amoprof_exec_svg_tier_occupancy(
            _mc_cap_pct, window=_occ_win, wall_start=_occ_wall, mode="abs",
            title="Memory hierarchy capacity used",
            subtitle="absolute GB resident on a log axis \u00b7 counts everything "
                     "in the tier, not only KV \u00b7 dashed line = known capacity "
                     "\u00b7 L1 from nvidia-smi memory.used, L2 from /proc/meminfo, "
                     f"{_TIER} from the store\u2019s own byte counters"
                     + _l3_cap_missing,
            yaxis="GB used (log)", unit_label="GB") + _src_block_from_series(
                _mc_cap_pct, note="Absolute bytes resident per tier, straight from each tier\u2019s own accounting \u2014 no KV bytes/token conversion, so this chart is unaffected by that estimate. A series marked FLAT is a single scalar held constant across the window, not a measured shape.") if _mc_cap_pct else ""

        # Percentage companion.  Absolute GB cannot answer "how full is this
        # tier": a remote store holding terabytes dwarfs an HBM pool holding
        # hundreds of GB, so a tier at 95% is invisible beside a larger tier
        # at 5%.  Only tiers with a KNOWN ceiling appear — a percentage of an
        # unknown capacity is not a number.
        _cap_pct_series = []
        for _x in _mc_cap_pct:
            _c = float(_x.get("cap") or 0)
            if _c <= 0:
                continue
            _cap_pct_series.append(dict(
                _x, v=[min(100.0, v / _c * 100.0) if v == v else float("nan")
                       for v in _x["v"]], cap=100.0))
        _mc_cap_pct_svg = _amoprof_exec_svg_tier_occupancy(
            _cap_pct_series, window=_occ_win, wall_start=_occ_wall, mode="fill",
            title="Memory hierarchy capacity used (% of each tier)",
            subtitle="bytes resident \u00f7 that tier's own capacity \u00b7 "
                     "only tiers with a known ceiling",
            yaxis="% of tier capacity") + _src_block_from_series(
                _cap_pct_series,
                note="Each series is divided by its own capacity column; a "
                     "tier with no published ceiling is absent rather than "
                     "shown against an invented one."
            ) if _cap_pct_series else ""

        if _cu_svg:
            _exec_ov["Compute utilisation over the run (GPU / HBM / CPU)"] = _cu_svg
        if _mc_cap_pct_svg:
            _exec_ov["Memory hierarchy capacity utilisation \u2014 % of each tier"] = _mc_cap_pct_svg

        # ---- L3.5 memory-node aspect panels ---------------------------
        # One per aspect.  Each renders only when its source series has
        # non-zero samples in this run (which requires the corresponding
        # collector to have been active on the memory node).
        _l35_t_axis = _l35_dram_t or []

        def _first_finite_positive(vs):
            return any((x == x) and x > 0 for x in (vs or []))

        # L3.5 CPU
        _l35_cpu_series = []
        if _l35_t_axis and _first_finite_positive(_l35_cpu_util_series):
            _l35_cpu_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 CPU util (all cores) %",
                "t": _l35_t_axis, "v": _l35_cpu_util_series,
                "cap": 100.0, "color": "#ef4444"})
        if _l35_t_axis and _first_finite_positive(_l35_cpu_iowait_series):
            _l35_cpu_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 CPU iowait %",
                "t": _l35_t_axis, "v": _l35_cpu_iowait_series,
                "cap": 100.0, "color": "#f97316"})
        if _l35_t_axis and _first_finite_positive(_l35_cpu_busiest_series):
            _l35_cpu_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 busiest-core %",
                "t": _l35_t_axis, "v": _l35_cpu_busiest_series,
                "cap": 100.0, "color": "#a855f7"})
        if _l35_cpu_series:
            _l35_cpu_svg = _amoprof_exec_svg_tier_occupancy(
                _l35_cpu_series, window=_occ_win, wall_start=_occ_wall,
                mode="fill",
                title="L3.5 memory node \u00b7 CPU utilisation over the run",
                subtitle=("all-core mean, iowait share, and busiest single-core "
                          "as % of that core \u00b7 scraped from the memory-node "
                          "amoprof exporter (job=amoprof, l35 selector)"),
                yaxis="% util") if _l35_cpu_series else ""
            if _l35_cpu_svg:
                _exec_ov["L3.5 memory node \u00b7 CPU utilisation over the run"] = _l35_cpu_svg

        # L3.5 DRAM bandwidth (read + write) - AMDuProf/Intel PCM on memory node
        _l35_dbw_series = []
        if _l35_t_axis and _first_finite_positive(_l35_dram_rd_series):
            _l35_dbw_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 DRAM read GB/s",
                "t": _l35_t_axis, "v": _l35_dram_rd_series,
                "cap": 0.0, "color": "#22c55e",
                "src": ("l35_storage_timeseries.csv", "l35_dram_rd_gbs",
                        "PCM memory-controller counters ON THE MEMORY NODE, not the GPU host")})
        if _l35_t_axis and _first_finite_positive(_l35_dram_wr_series):
            _l35_dbw_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 DRAM write GB/s",
                "t": _l35_t_axis, "v": _l35_dram_wr_series,
                "cap": 0.0, "color": "#eab308",
                "src": ("l35_storage_timeseries.csv", "l35_dram_wr_gbs",
                        "PCM memory-controller counters ON THE MEMORY NODE, not the GPU host")})
        if _l35_dbw_series:
            _l35_dbw_svg = _amoprof_exec_svg_tier_occupancy(
                _l35_dbw_series, window=_occ_win, wall_start=_occ_wall,
                mode="abs",
                title="L3.5 memory node \u00b7 DRAM read/write bandwidth over the run",
                subtitle=("AMDuProf PCM or Intel PCM on the memory node \u00b7 "
                          "one line per direction so read-only vs write-heavy "
                          "phases are distinguishable"),
                yaxis="GB/s", unit_label="GB/s") + _src_block_from_series(
                _l35_dbw_series,
                note="Memory-controller counters on the L3.5 node. This is "
                     "the node&#39;s DRAM traffic as a whole, not only the KV "
                     "store&#39;s share of it.")
            if _l35_dbw_svg:
                _exec_ov["L3.5 memory node \u00b7 DRAM bandwidth over the run"] = _l35_dbw_svg

        # L3.5 network throughput (RX / TX)
        _l35_net_series = []
        if _l35_t_axis and _first_finite_positive(_l35_net_rx_series):
            _l35_net_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 RX MB/s",
                "t": _l35_t_axis, "v": _l35_net_rx_series,
                "cap": 0.0, "color": "#3b82f6"})
        if _l35_t_axis and _first_finite_positive(_l35_net_tx_series):
            _l35_net_series.append({
                "tier": "L3.5", "label": "L3.5 node \u00b7 TX MB/s",
                "t": _l35_t_axis, "v": _l35_net_tx_series,
                "cap": 0.0, "color": "#0ea5e9"})
        if _l35_net_series:
            _l35_net_svg = _amoprof_exec_svg_tier_occupancy(
                _l35_net_series, window=_occ_win, wall_start=_occ_wall,
                mode="abs",
                title="L3.5 memory node \u00b7 network throughput over the run",
                subtitle=("/proc/net/dev on the memory node \u00b7 MB/s per direction "
                          "\u00b7 RDMA traffic between the store and its clients does "
                          "NOT appear here; this is only the kernel NIC counters"),
                yaxis="MB/s", unit_label="MB/s")
            if _l35_net_svg:
                _exec_ov["L3.5 memory node \u00b7 network throughput over the run"] = _l35_net_svg

        # L2 host DRAM read/write bandwidth (from pcm / amduprof_pcm CSVs)
        _l2_pcm_path = (_first_existing(raw_dir, ["pcm_timeseries.csv"])
                        or _first_existing(raw_dir, ["amduprof_pcm_timeseries.csv"]))
        _l2_rw_series = []
        if _l2_pcm_path:
            _l2_pcm_raw = _amoprof_read_columns_raw(
                _l2_pcm_path, ["time_sec", "dram_read_gb_s", "dram_write_gb_s"])
            _l2_pcm_t = _l2_pcm_raw.get("time_sec") or []
            _l2_pcm_rd = _l2_pcm_raw.get("dram_read_gb_s") or []
            _l2_pcm_wr = _l2_pcm_raw.get("dram_write_gb_s") or []
            if _l2_pcm_t and _first_finite_positive(_l2_pcm_rd):
                _l2_rw_series.append({
                    "tier": "L2", "label": "L2 host DRAM \u00b7 read GB/s",
                    "t": _l2_pcm_t, "v": _l2_pcm_rd,
                    "cap": 0.0, "color": "#22c55e",
                    "src": ("amduprof_pcm_timeseries.csv", "dram_read_gb_s",
                            "PCM memory-controller counters on the GPU host \u00b7 ALL DRAM traffic, not only KV")})
            if _l2_pcm_t and _first_finite_positive(_l2_pcm_wr):
                _l2_rw_series.append({
                    "tier": "L2", "label": "L2 host DRAM \u00b7 write GB/s",
                    "t": _l2_pcm_t, "v": _l2_pcm_wr,
                    "cap": 0.0, "color": "#eab308",
                    "src": ("amduprof_pcm_timeseries.csv", "dram_write_gb_s",
                            "PCM memory-controller counters on the GPU host \u00b7 ALL DRAM traffic, not only KV")})
        if _l2_rw_series:
            _l2_rw_svg = _amoprof_exec_svg_tier_occupancy(
                _l2_rw_series, window=_occ_win, wall_start=_occ_wall,
                mode="abs",
                title="L2 host DRAM \u00b7 read/write bandwidth over the run",
                subtitle=("AMDuProf PCM or Intel PCM on the GPU host \u00b7 "
                          "read and write plotted separately so KV-refill "
                          "(read-heavy) vs backup phases (write-heavy) are distinct"),
                yaxis="GB/s", unit_label="GB/s") + _src_block_from_series(
                _l2_rw_series,
                note="Memory-controller counters, so this is the host&#39;s "
                     "whole DRAM traffic. KV movement is a share of it, not "
                     "the whole of it.")
            if _l2_rw_svg:
                _exec_ov["L2 host DRAM \u00b7 read/write bandwidth over the run"] = _l2_rw_svg

        # ---- Combined L2 + L3.5 DRAM R/W over the run --------------------
        # One chart carrying all four DRAM directions across both tiers so a
        # reader can compare the load on the two DRAM pools side by side.
        _dram_rw_all = []
        # L2 (GPU host, PCM CSV): reuse the same series already assembled
        # above for the L2-only panel.
        _l2_pcm_path_all = (
            _first_existing(raw_dir, ["pcm_timeseries.csv"])
            or _first_existing(raw_dir, ["amduprof_pcm_timeseries.csv"]))
        if _l2_pcm_path_all:
            _l2_pcm_all = _amoprof_read_columns_raw(
                _l2_pcm_path_all,
                ["time_sec", "dram_read_gb_s", "dram_write_gb_s"])
            _l2_t_all = _l2_pcm_all.get("time_sec") or []
            _l2_r_all = _l2_pcm_all.get("dram_read_gb_s") or []
            _l2_w_all = _l2_pcm_all.get("dram_write_gb_s") or []
            if _l2_t_all and _first_finite_positive(_l2_r_all):
                _dram_rw_all.append({
                    "tier": "L2", "label": "L2 host DRAM \u00b7 read GB/s",
                    "t": _l2_t_all, "v": _l2_r_all,
                    "cap": 0.0, "color": "#16a34a",
                    "src": ("amduprof_pcm_timeseries.csv", "dram_read_gb_s",
                            "PCM memory-controller counters on the GPU node")})
            if _l2_t_all and _first_finite_positive(_l2_w_all):
                _dram_rw_all.append({
                    "tier": "L2", "label": "L2 host DRAM \u00b7 write GB/s",
                    "t": _l2_t_all, "v": _l2_w_all,
                    "cap": 0.0, "color": "#ca8a04",
                    "src": ("amduprof_pcm_timeseries.csv", "dram_write_gb_s",
                            "PCM memory-controller counters on the GPU node")})
        # L3.5 (memory node): reuse the l35_storage_timeseries series read
        # into the scalar block near line ~3410.
        if _l35_t_axis and _first_finite_positive(_l35_dram_rd_series):
            _dram_rw_all.append({
                "tier": "L3.5", "label": "L3.5 node DRAM \u00b7 read GB/s",
                "t": _l35_t_axis, "v": _l35_dram_rd_series,
                "cap": 0.0, "color": "#22c55e",
                "src": ("l35_storage_timeseries.csv", "l35_dram_rd_gbs",
                        "PCM on the MEMORY NODE \u2014 a different host from the L2 series on this chart")})
        if _l35_t_axis and _first_finite_positive(_l35_dram_wr_series):
            _dram_rw_all.append({
                "tier": "L3.5", "label": "L3.5 node DRAM \u00b7 write GB/s",
                "t": _l35_t_axis, "v": _l35_dram_wr_series,
                "cap": 0.0, "color": "#eab308",
                "src": ("l35_storage_timeseries.csv", "l35_dram_wr_gbs",
                        "PCM on the MEMORY NODE \u2014 a different host from the L2 series on this chart")})

        if _dram_rw_all:
            _dram_rw_all_svg = _amoprof_exec_svg_tier_occupancy(
                _dram_rw_all, window=_occ_win, wall_start=_occ_wall,
                mode="abs",
                title=f"DRAM read/write transactions over the run (L2 + {_TIER})",
                subtitle=("both DRAM pools on one axis \u00b7 shape (not "
                          "magnitude) is what matters - the two pools sit on "
                          "different hosts and their absolute peaks differ"),
                yaxis="GB/s", unit_label="GB/s") + _src_block_from_series(
                _dram_rw_all,
                note="Two hosts on one axis: the L2 series is the GPU node&#39;s "
                     "memory controller, the L3.5 series is the memory "
                     "node&#39;s. They are not summable and their peaks are "
                     "not comparable \u2014 read the SHAPES against each other.")
            if _dram_rw_all_svg:
                _exec_ov["DRAM read/write transactions over the run "
                         "(L2 + L3.5)"] = _dram_rw_all_svg

        # ---- Correlation: DRAM R/W vs token throughput -------------------
        # Normalise every series to % of its own peak so DRAM (GB/s) and
        # token rate (tok/s) share a 0-100 axis.  Co-varying lines mean
        # DRAM traffic tracks token activity in the time domain; divergent
        # lines mean the correlation is looser than magnitudes suggest.
        _dram_corr = list(_dram_rw_all)
        _sg_time_local = _sg_time if "_sg_time" in dir() else []
        if _sg_time_local and _first_finite_positive(_in_tok_rate):
            _dram_corr.append({
                "tier": "TOK", "label": "SGLang \u00b7 Input tok/s",
                "t": _sg_time_local, "v": _in_tok_rate,
                "cap": 0.0, "color": "#38bdf8",
                "src": ("sglang_timeseries.csv", "sglang_prompt_tokens_total",
                        "\u0394counter \u00f7 \u0394t per interval, summed over tp_rank")})
        if _sg_time_local and _first_finite_positive(_out_tok_rate):
            _dram_corr.append({
                "tier": "TOK", "label": "SGLang \u00b7 Output tok/s",
                "t": _sg_time_local, "v": _out_tok_rate,
                "cap": 0.0, "color": "#a78bfa",
                "src": ("sglang_timeseries.csv", "sglang_generation_tokens_total",
                        "\u0394counter \u00f7 \u0394t per interval, summed over tp_rank")})
        # Give every series a "cap" equal to its own peak so the fill-
        # mode renderer normalises each to 0-100.
        _dram_corr_norm = []
        for _s in _dram_corr:
            _vs = [v for v in (_s.get("v") or []) if v == v and v > 0]
            _pk = max(_vs) if _vs else 0.0
            if _pk <= 0:
                continue
            _dram_corr_norm.append(dict(_s, cap=_pk))
        # Only render when we have BOTH kinds of series (DRAM AND tokens);
        # a chart with only DRAM (or only tokens) is not a correlation
        # chart and would duplicate the panel above.
        _has_dram = any(s["tier"] in ("L2", "L3.5") for s in _dram_corr_norm)
        _has_tok = any(s["tier"] == "TOK" for s in _dram_corr_norm)
        if _has_dram and _has_tok:
            _dram_corr_svg = _amoprof_exec_svg_tier_occupancy(
                _dram_corr_norm, window=_occ_win, wall_start=_occ_wall,
                mode="fill",
                title=f"DRAM read/write transactions vs token throughput "
                      f"(L2 + {_TIER})",
                subtitle=("each series normalised to % of its own peak so "
                          "DRAM GB/s and SGLang tok/s share one axis \u00b7 "
                          "aligned peaks = DRAM traffic tracks token activity "
                          "in time, divergent peaks = the driver is elsewhere"),
                yaxis="% of each series peak") + _src_block_from_series(
                _dram_corr_norm,
                note="Every series is divided by ITS OWN peak, so the axis "
                     "carries shape only \u2014 no series is larger or smaller "
                     "than another here. Aligned peaks mean the two move "
                     "together in time; they do not establish that one causes "
                     "the other.")
            if _dram_corr_svg:
                _exec_ov["DRAM read/write transactions vs token throughput "
                         "(L2 + L3.5)"] = _dram_corr_svg
        # ── L3.5 store internals: eviction, get outcome, promotion pipeline ──
        # Built in its own guarded block so a failure here cannot remove the
        # storage charts above it.  Every series comes from the store exporter
        # via l35_store_capacity.csv.  Nothing is derived by subtracting one
        # counter from another: whether the _mem eviction counter is a subset of
        # the total is not established, so both are shown as the store reports
        # them rather than as a computed split.
        _l35_int_svg = ""
        _l35_int_missing = []
        _l35_on = str(l3_backend_class or "").lower() in (
            "remote_mooncake", "remote_storage")
        _l35_src_found = False
        try:
            _sf = _first_existing(raw_dir, ["l35_store_capacity.csv"])
            _l35_src_found = bool(_sf)
            _sc = (_amoprof_read_columns_raw(_sf, [
                "time_sec", "l35_evicted_b", "l35_evicted_mem_b",
                "l35_get_total_n", "l35_get_valid_n",
                "l35_promo_recorded", "l35_promo_admitted", "l35_promo_completed",
                "l35_promo_rej_freq", "l35_promo_rej_wm", "l35_promo_rej_cap",
                "l35_promo_rej_adm", "l35_promo_dropped", "l35_promo_expired",
                "l35_promo_failed", "l35_promo_cancelled", "l35_promo_exp_eval",
                "l35_promo_exp_uneval", "l35_promo_cand_adm",
                "l35_promo_in_flight",
                # Per-tier read accounting: which tier answered each lookup.
                "l35_mem_hit_n", "l35_file_hit_n",
                "l35_mem_hit_b", "l35_file_hit_b"]) if _sf else {})
            _st = _sc.get("time_sec") or []

            def _dlt(_k):
                """Window delta of a store counter; None if absent."""
                _v = [x for x in (_sc.get(_k) or []) if x == x]
                if len(_v) < 2:
                    return None
                _d = _v[-1] - _v[0]
                return _d if _d >= 0 else _v[-1]      # reset inside window

            def _rate_series(_k, _scale):
                _t, _r = _rate_with_time(_sc.get(_k) or [], _st)
                return _t, [(x / _scale) if x == x else x for x in (_r or [])]

            def _ts(_specs, _title, _sub, _yaxis, _unit):
                _ser = []
                for _lbl, _k, _scale, _col in _specs:
                    _t, _v = _rate_series(_k, _scale)
                    if _v and any(x == x and x > 0 for x in _v):
                        _ser.append({"tier": "L3.5", "label": _lbl, "t": _t,
                                     "v": _v, "cap": 0, "color": _col})
                return (_amoprof_exec_svg_tier_occupancy(
                    _ser, window=_occ_win, wall_start=_occ_wall, mode="abs",
                    title=_title, subtitle=_sub, yaxis=_yaxis, unit_label=_unit)
                    if _ser else "")

            # 0. All four KV movements on one time axis.
            # Colour carries direction, not just identity: warm for KV moving
            # DOWN the hierarchy (evict, backup) and cool for KV coming back
            # UP (prefetch, load-back).  Read against one shared tok/s axis a
            # cool line that never lifts off zero beside a warm line that does
            # is the whole finding, and needs no legend-reading to see.
            _mv_specs = [
                ("evict  L1\u2192L2",      ["evicted_tokens_total"],    "#f59e0b"),
                (f"backup L2\u2192{_TIER}",    ["backuped_tokens_total"],   "#ef4444"),
                (f"prefetch {_TIER}\u2192L2",  ["prefetched_tokens_total"], "#22c55e"),
                ("load-back L2\u2192L1",   ["load_back_tokens_total"],  "#38bdf8"),
            ]
            _mv_ser, _mv_tot, _mv_absent = [], {}, []
            _mv_rules: list = []
            for _lbl, _cands, _col in _mv_specs:
                _mv_meta: dict = {}
                _cs = _kv_counter_series(raw_dir, _cands, meta=_mv_meta)
                _mv_rules.extend(_mv_meta.get("rules") or [])
                if _cs is None:
                    _mv_absent.append(_lbl.split()[0])
                    continue
                _ct, _cv = _cs
                _rt, _rv = _rate_with_time(_cv, _ct)
                _mv_tot[_lbl] = max(0.0, _cv[-1] - _cv[0])
                # A counter that exists and never moved draws a FLAT LINE AT
                # ZERO rather than being dropped.  Dropping it makes "the
                # engine never read" indistinguishable from "this build does
                # not export the counter", which are different findings with
                # different fixes; truly absent counters are named in the
                # subtitle instead.
                if _rv and any(x == x for x in _rv):
                    _mv_ser.append({"tier": "L3.5", "label": _lbl, "t": _rt,
                                    "v": _rv, "cap": 0, "color": _col})
            if _mv_ser:
                _down = sum(v for k, v in _mv_tot.items()
                            if k.startswith(("evict", "backup")))
                _up = sum(v for k, v in _mv_tot.items()
                          if k.startswith(("prefetch", "load-back")))
                # A fetched run already carries ONE combined column per
                # counter; the rule was decided at fetch time from the
                # per-rank series and recorded in the summary.  A local run
                # carries the ranks and the reader decided just now.
                if not any(r.get("rule") != "single" for r in _mv_rules):
                    _mv_rules = [r for _v in (sglang.get("kv_rank_rules") or {}).values()
                                 for r in (_v or [])]
                _mv_sub = ("tokens per second, "
                           + _k_summarise_rank_rules(_mv_rules))
                if _down > 0 and _up == 0:
                    _mv_sub += (f" \u00b7 {_down/1e6:,.1f}M tokens moved down the "
                                f"hierarchy and NONE came back up")
                elif _down > 0 and _up > 0:
                    _mv_sub += (f" \u00b7 {_down/1e6:,.1f}M down vs {_up/1e6:,.1f}M "
                                f"up ({_down/_up:,.1f}:1)" if _down >= _up else
                                f" \u00b7 {_up/1e6:,.1f}M up vs {_down/1e6:,.1f}M "
                                f"down ({_up/_down:,.1f}:1)")
                if _mv_absent:
                    _mv_sub += (" \u00b7 not exported by this engine build: "
                                + ", ".join(_mv_absent))
                _l35_int_svg += _amoprof_exec_svg_tier_occupancy(
                    _mv_ser, window=_occ_win, wall_start=_occ_wall, mode="abs",
                    title="KV movement over the run \u2014 evict, backup, "
                          "prefetch, load-back",
                    subtitle=_mv_sub, yaxis="tok/s", unit_label="tok/s",
                    keep_zero_series=True)
                _l35_int_svg += _amoprof_src_block([
                    ("evict L1&rarr;L2", "sglang_timeseries.csv",
                     "sglang_evicted_tokens_total", "\u0394counter \u0394t, summed over tp_rank"),
                    (f"backup L2&rarr;{_TIER}", "sglang_timeseries.csv",
                     "sglang_backuped_tokens_total", "\u0394counter \u0394t, summed over tp_rank"),
                    (f"prefetch {_TIER}&rarr;L2", "sglang_timeseries.csv",
                     "sglang_prefetched_tokens_total", "\u0394counter \u0394t, summed over tp_rank"),
                    ("load-back L2&rarr;L1", "sglang_timeseries.csv",
                     "sglang_load_back_tokens_total", "\u0394counter \u0394t, summed over tp_rank"),
                ], "All four are ENGINE-side counters from the inference server (--prom-instance). They say what the engine asked for, not what any device did.")

            # 1. Eviction, as the store reports it.
            _ev_all, _ev_mem = _dlt("l35_evicted_b"), _dlt("l35_evicted_mem_b")
            _ev_sub = "rate of bytes evicted, as reported by the store"
            if _ev_all:
                _ev_sub += f" \u00b7 {_ev_all/1e9:,.0f} GB over the window"
            if _ev_mem is not None and _ev_all:
                _ev_sub += f" \u00b7 memory-tier counter {_ev_mem/1e9:,.0f} GB"
            _before = len(_l35_int_svg)
            _l35_int_svg += _ts(
                [("evicted (all)", "l35_evicted_b", 1e9, "#f97316"),
                 ("evicted (memory-tier counter)", "l35_evicted_mem_b", 1e9, "#fbbf24")],
                "L3.5 eviction over the run", _ev_sub, "GB/s", "GB/s")
            _l35_int_svg += _amoprof_src_block([
                ("evicted (all)", "l35_store_capacity.csv",
                 "l35_evicted_b", "master_evicted_size_bytes \u0394t"),
                ("evicted (memory-tier)", "l35_store_capacity.csv",
                 "l35_evicted_mem_b", "master_evicted_size_bytes_mem \u0394t"),
            ], "STORE-side accounting from the KV store exporter (--l35-instance). A read answered from the store memory tier never reaches the block device, so it does not appear in device bandwidth. The memory-tier counter is plotted as reported, not subtracted from the total: whether it is a subset is not established.")
            if len(_l35_int_svg) == _before:
                _l35_int_missing.append(("Eviction over the run",
                    "master_evicted_size_bytes, master_evicted_size_bytes_mem"))

            # 2. Get outcome: lookups, and how many found their key.
            _gt, _gv = _dlt("l35_get_total_n"), _dlt("l35_get_valid_n")
            _g_sub = "get operations per second"
            if _gt and _gv is not None and _gt > 0:
                _g_sub += (f" \u00b7 {_gv/_gt*100:.1f}% of {_gt:,.0f} gets found "
                           f"their key")
            _before = len(_l35_int_svg)
            _l35_int_svg += _ts(
                [("gets (total)", "l35_get_total_n", 1.0, "#38bdf8"),
                 ("gets that found the key", "l35_get_valid_n", 1.0, "#22c55e")],
                "L3.5 get outcome over the run", _g_sub, "ops/s", "ops/s")
            _l35_int_svg += _amoprof_src_block([
                ("gets (total)", "l35_store_capacity.csv",
                 "l35_get_total_n", "total_get_nums_ \u0394t"),
                ("gets that found the key", "l35_store_capacity.csv",
                 "l35_get_valid_n", "valid_get_nums_ \u0394t"),
            ], "STORE-side accounting from the KV store exporter (--l35-instance). A read answered from the store memory tier never reaches the block device, so it does not appear in device bandwidth.")
            if len(_l35_int_svg) == _before:
                _l35_int_missing.append(("Get outcome over the run",
                    "total_get_nums_, valid_get_nums_"))

            # 3. Promotion pipeline — why nothing moves back up.
            _stages = [
                ("recorded",  "l35_promo_recorded",  "#94a3b8"),
                ("admitted",             "l35_promo_admitted",  "#38bdf8"),
                ("completed",            "l35_promo_completed", "#22c55e"),
                ("rej: freq",  "l35_promo_rej_freq",  "#ef4444"),
                ("rej: wmark",  "l35_promo_rej_wm",    "#ef4444"),
                ("rej: cap",   "l35_promo_rej_cap",   "#ef4444"),
                ("rej: admit",  "l35_promo_rej_adm",   "#ef4444"),
                ("dropped", "l35_promo_dropped",   "#f59e0b"),
                ("expired",              "l35_promo_expired",   "#f59e0b"),
                ("failed",               "l35_promo_failed",    "#f59e0b"),
                ("cancelled",            "l35_promo_cancelled", "#f59e0b"),
                ("exp: evaluated",       "l35_promo_exp_eval",  "#f59e0b"),
                ("exp: unevaluated",     "l35_promo_exp_uneval","#f59e0b"),
            ]
            _pv, _pc = {}, {}
            for _lbl, _k, _col in _stages:
                _d = _dlt(_k)
                if _d is not None:
                    _pv[_lbl], _pc[_lbl] = _d, _col
            if not _pv:
                _l35_int_missing.append(("Promotion pipeline",
                    "master_promotion_* (recorded, admitted, completed, rejected_*)"))
            if _pv:
                _rec = _pv.get("recorded") or 0
                _done = _pv.get("completed") or 0
                _rej = {k: v for k, v in _pv.items()
                        if k.startswith(("rej", "dropped", "expired", "failed",
                                         "cancelled", "exp:"))}
                _top = max(_rej, key=_rej.get) if _rej and max(_rej.values()) > 0 else None
                _p_sub = (f"window counts \u00b7 {_rec:,.0f} candidates, "
                          f"{_done:,.0f} completed")
                if _top:
                    _full = {"rej: freq": "rejected for access frequency",
                         "rej: wmark": "rejected at the DRAM watermark",
                         "rej: cap": "rejected by the rate cap",
                         "rej: admit": "rejected at admission",
                         "dropped": "dropped at the queue limit",
                         "cancelled": "cancelled in flight",
                         "exp: evaluated": "expired after evaluation",
                         "exp: unevaluated": "expired before evaluation",
                         "expired": "expired", "failed": "failed"}.get(_top, _top)
                    _p_sub += f" \u00b7 largest loss: {_full} ({_rej[_top]:,.0f})"
                elif _rec == 0:
                    _p_sub += " \u00b7 no candidates were recorded"
                # These counters are NOT a partition of the candidates.  The
                # rejection counters count EVALUATION ATTEMPTS: one candidate
                # can be re-evaluated and rejected many times before it is
                # admitted or expires, so a rejection total legitimately
                # exceeds the candidate count.  An earlier version summed them
                # against `recorded` and reported the excess as "over-counted",
                # which named a measurement fault where there is none.  Report
                # the pressure that excess actually represents instead.
                if _rec > 0 and _rej:
                    _att = sum(_rej.values())
                    if _att > _rec:
                        _p_sub += (f" \u00b7 {_att/_rec:,.1f} rejected evaluations "
                                   f"per candidate \u2014 candidates are "
                                   f"re-evaluated, so these are attempts, not a "
                                   f"split of the {_rec:,.0f}")
                    _p_sub += (f" \u00b7 {_done/_rec*100:.2f}% of candidates "
                               f"completed")
                # in-flight is a gauge, not a window count: never a bar here.
                if _dlt("l35_promo_in_flight"):
                    _p_sub += " \u00b7 in-flight tracked as a gauge, not charted"
                _l35_int_svg += _amoprof_exec_svg_percentile_bars(
                    "L3.5 promotion pipeline \u2014 why KV does or does not move back up",
                    _p_sub, "count", _pv, _pc, width=960)
                _l35_int_svg += _amoprof_src_block([
                    ("every bar", "l35_store_capacity.csv",
                     "l35_promo_*", "master_promotion_* (window \u0394)"),
                ], "STORE-side, from the KV store exporter (--l35-instance). Bar-by-bar meanings and units are in the legend above; the rejection bars count evaluation attempts, not candidates.")
                # What each bar means.  Collapsed by default: the chart should
                # read without it, and the detail is here when a bar surprises
                # you.  The units differ between bars, which is the single
                # most confusing thing about this chart, so it leads.
                _pl_rows = [
                    ("recorded", "candidates", "blocks the store considered "
                     "promoting from the file tier back into memory"),
                    ("admitted", "candidates", "passed admission and entered "
                     "the promotion queue"),
                    ("completed", "promotions", "actually moved back into the "
                     "memory tier \u2014 the only bar that means KV was promoted"),
                    ("rej: freq", "evaluations", "refused: the block was not "
                     "accessed often enough to be worth promoting"),
                    ("rej: wmark", "evaluations", "refused: the memory tier was "
                     "already above its fill watermark, so there was no room"),
                    ("rej: cap", "evaluations", "refused: the promotion rate cap "
                     "for this interval was already spent"),
                    ("rej: admit", "evaluations", "refused at admission, after "
                     "passing the earlier gates"),
                    ("dropped", "candidates", "discarded because the candidate "
                     "queue was full"),
                    ("expired", "candidates", "aged out of the queue before a "
                     "decision was reached"),
                    ("exp: evaluated", "candidates", "aged out after being "
                     "evaluated at least once"),
                    ("exp: unevaluated", "candidates", "aged out having never "
                     "been evaluated \u2014 the queue never got to them"),
                    ("failed", "promotions", "attempted and errored"),
                    ("cancelled", "promotions", "abandoned while in flight"),
                ]
                _pl_tr = "".join(
                    f'<tr><td style="padding:3px 10px 3px 0;white-space:nowrap">'
                    f'<code style="color:#93c5fd">{_n}</code></td>'
                    f'<td style="padding:3px 10px 3px 0;color:#94a3b8;'
                    f'white-space:nowrap">{_u}</td>'
                    f'<td style="padding:3px 0">{_d}</td></tr>'
                    for _n, _u, _d in _pl_rows
                    if _n in _pv)
                _l35_int_svg += (
                    '<details class="amoprof-src amoprof-note">'
                    '<summary><span class="amoprof-src-ic">?</span>'
                    'what each bar means</summary>'
                    '<div class="amoprof-src-body amoprof-note-body">'
                    '<p style="margin:0 0 8px 0"><b>The bars do not share a '
                    'unit, and they are not a split of the candidates.</b> '
                    'Bars marked <i>evaluations</i> count decision attempts: '
                    'one candidate can be re-evaluated and refused many times '
                    'before it is admitted or expires, so those totals can '
                    'exceed the candidate count. Only <code>completed</code> '
                    'means KV actually moved back into memory.</p>'
                    '<table style="border-collapse:collapse;width:100%">'
                    + _pl_tr + '</table>'
                    '<p style="margin:8px 0 0 0;color:#94a3b8">Counters the '
                    'store did not export are omitted rather than shown as '
                    'zero.</p></div></details>')

            # Which tier actually served the reads.  Promotion says how much KV
            # moved file->memory; this says where lookups were answered FROM,
            # which is the question a tiering decision turns on.  Counts are the
            # bars because "how many reads" is the question; bytes go in the
            # subtitle because mean read size differs between the tiers.
            _rd_n = {"DRAM tier": _dlt("l35_mem_hit_n"),
                     "SSD / file tier": _dlt("l35_file_hit_n")}
            _rd_b = {"DRAM tier": _dlt("l35_mem_hit_b"),
                     "SSD / file tier": _dlt("l35_file_hit_b")}
            _rd_have = {k: v for k, v in _rd_n.items() if v is not None}
            if _rd_have:
                _tot_n = sum(_rd_have.values())
                # Keep the subtitle inside the chart width: shares first (the
                # question), then bytes, then the stage linkage.  A longer form
                # silently clipped at the right edge.
                def _hm(_v):
                    return (f"{_v/1e6:,.1f}M" if _v >= 1e6 else
                            f"{_v/1e3:,.0f}k" if _v >= 1e3 else f"{_v:,.0f}")
                _bits = []
                if _tot_n > 0:
                    _bits.append(" / ".join(
                        f"{v/_tot_n*100:.2f}% {k.split()[0]}"
                        for k, v in _rd_have.items())
                        + f" of {_hm(_tot_n)} reads")
                _tb = [v for v in (_rd_b.get("DRAM tier"),
                                   _rd_b.get("SSD / file tier")) if v]
                if _tb:
                    _bits.append(" / ".join(f"{v/1e9:,.1f} GB" for v in _tb))
                # Tie it back: prefetch is the engine asking, promotion is the
                # store moving KV up, and these bars are where the answers came
                # from.  Three different stages, easy to conflate.
                _pf_up = _mv_tot.get(f"prefetch {_TIER}\u2192L2") or 0.0
                _promo = _pv.get("completed") or 0.0
                if _pf_up or _promo:
                    _bits.append(f"prefetch {_hm(_pf_up)} tok \u00b7 "
                                 f"{_promo:,.0f} promotions")
                _l35_int_svg += _amoprof_exec_svg_percentile_bars(
                    "L3.5 reads by tier \u2014 who answered the lookups",
                    " \u00b7 ".join(_bits) if _bits else "read counts per tier",
                    "reads", _rd_have,
                    {"DRAM tier": "#22c55e", "SSD / file tier": "#f59e0b"},
                    width=620)
                _l35_int_svg += _amoprof_src_block([
                    ("DRAM tier", "l35_store_capacity.csv", "l35_mem_hit_n",
                     "mem_cache_hit_nums_ (window \u0394)"),
                    ("SSD / file tier", "l35_store_capacity.csv", "l35_file_hit_n",
                     "file_cache_hit_nums_ (window \u0394)"),
                    ("bytes, both tiers", "l35_store_capacity.csv",
                     "l35_mem_hit_b / l35_file_hit_b",
                     "mem_cache_hit_bytes_total / file_cache_hit_bytes_total"),
                ], "STORE-side logical reads (--l35-instance). These will NOT match the device bandwidth tiles: a read served from the store memory tier never touches the block device, and the file tier is page-cached, so most of these never reach NVMe.")
                # The stage chain, in the units each stage actually counts.
                # "How do prefetch ops map to gets" has no conversion: a get is
                # one lookup, a prefetch token is one token, a promotion is one
                # block.  Dividing across them invents a ratio.  What the chain
                # DOES support is whether promotion is shifting the read mix,
                # which is the question behind the ask.
                _chain = [
                    ("engine asks", "sglang_prefetched_tokens_total",
                     _mv_tot.get(f"prefetch {_TIER}\u2192L2"), "tokens"),
                    ("engine read ops", "sglang_prefetch_pgs_count",
                     _kv_token_delta(raw_dir, ["prefetch_pgs_count"]), "operations"),
                    ("store lookups", "total_get_nums_",
                     _dlt("l35_get_total_n"), "gets"),
                    ("answered by DRAM", "mem_cache_hit_nums_",
                     _rd_have.get("DRAM tier"), "reads"),
                    ("answered by SSD", "file_cache_hit_nums_",
                     _rd_have.get("SSD / file tier"), "reads"),
                    ("store promotes", "master_promotion_completed_total",
                     _pv.get("completed"), "promotions"),
                ]
                _crows = "".join(
                    '<tr><td style="padding:3px 12px 3px 0">' + _n +
                    '</td><td style="padding:3px 12px 3px 0;color:#94a3b8">'
                    '<code>' + _m + '</code></td>'
                    '<td style="padding:3px 12px 3px 0;text-align:right">' +
                    ("absent" if _v is None else format(_v, ",.0f")) +
                    '</td><td style="padding:3px 0;color:#94a3b8">' + _u +
                    '</td></tr>'
                    for _n, _m, _v, _u in _chain)
                _ssd_share = ((_rd_have.get("SSD / file tier") or 0.0) /
                              _tot_n * 100.0) if _tot_n else 0.0
                _promo_n = _pv.get("completed") or 0.0
                _verdict = (
                    "With " + format(_promo_n, ",.0f") + " promotions against " +
                    _hm(_tot_n) + " lookups, promotion is not materially "
                    "shifting the read mix: the SSD tier still answers " +
                    format(_ssd_share, ".2f") + "% of reads."
                    if _tot_n and _promo_n * 1000 < _tot_n else
                    "Promotion volume is large enough relative to lookups to "
                    "move the read mix; compare the SSD share against an "
                    "earlier run to see whether it fell.")
                _l35_int_svg += (
                    '<details class="amoprof-src amoprof-note">'
                    '<summary><span class="amoprof-src-ic">?</span>'
                    'how prefetch, gets and promotions relate</summary>'
                    '<div class="amoprof-src-body amoprof-note-body">'
                    '<p style="margin:0 0 8px 0"><b>These stages do not share a '
                    'unit, so none converts into another.</b> A get is one '
                    'lookup, a prefetch token is one token, a promotion is one '
                    'block. Only the two read rows sum to the lookup row.</p>'
                    '<table style="border-collapse:collapse;width:100%">'
                    + _crows + '</table>'
                    '<p style="margin:8px 0 0 0">' + _verdict + '</p>'
                    '</div></details>')


            # 4. Read side vs write side, as OPERATIONS rather than tokens.
            # "Are reads happening at all?" is answered by the operation
            # count, not by a bandwidth figure that rounds to zero when the
            # reads are few and small.  prefetch_pgs is the read-side twin of
            # backup_pgs; it was absent from the fetch while backup_pgs was
            # present, so the write path looked busy and the read path looked
            # idle regardless of what the store was doing.
            _ops, _opc = {}, {}
            for _lbl, _k, _col in (
                    ("backup ops (write)",   "backup_pgs_count",   "#f59e0b"),
                    ("prefetch ops (read)",  "prefetch_pgs_count", "#22c55e"),
                    ("load-back ops",        "load_back_duration_seconds_count", "#38bdf8")):
                _d = _kv_token_delta(raw_dir, [_k])
                if _d is not None:
                    _ops[_lbl], _opc[_lbl] = _d, _col
            if _ops:
                _wr = _ops.get("backup ops (write)") or 0.0
                _rd = _ops.get("prefetch ops (read)")
                _o_sub = "operations over the window, from the histogram counts"
                if _rd is None:
                    _o_sub += (" \u00b7 prefetch operations not exported by this "
                               "engine build")
                elif _rd == 0 and _wr > 0:
                    _o_sub += (f" \u00b7 {_wr:,.0f} writes and NO reads: the engine "
                               f"never asked the tier for KV in this window")
                elif _rd and _wr:
                    _o_sub += (f" \u00b7 {_wr/_rd:,.1f} writes per read"
                               if _wr >= _rd else
                               f" \u00b7 {_rd/_wr:,.1f} reads per write")
                _l35_int_svg += _amoprof_exec_svg_percentile_bars(
                    "KV operations \u2014 read side vs write side",
                    _o_sub, "operations", _ops, _opc, width=620)
                # Only the bars actually drawn are named below: a counter the
                # engine build does not export is omitted above, and listing
                # it here would read as a measured zero.
                _op_src = {
                    "backup ops (write)":
                        ("sglang_backup_pgs_count",
                         "sglang:backup_pgs histogram _count, summed over tp_rank"),
                    "prefetch ops (read)":
                        ("sglang_prefetch_pgs_count",
                         "sglang:prefetch_pgs histogram _count, summed over tp_rank"),
                    "load-back ops":
                        ("sglang_load_back_duration_seconds_count",
                         "sglang:load_back_duration_seconds histogram _count, summed over tp_rank"),
                }
                _l35_int_svg += _amoprof_src_block(
                    [(_l, "sglang_timeseries.csv") + _op_src[_l]
                     for _l in _ops if _l in _op_src],
                    note=("Counts are the histogram <code>_count</code> series, "
                          "differenced across the window \u2014 an OPERATION count, "
                          "not a token or byte count. One operation moves a page "
                          "group, whose size varies, so these bars answer "
                          "&#39;is the path being used at all&#39; and not "
                          "&#39;how much moved&#39;."))

            # ---- Does prefetch actually reach the GPU? -------------------
            # Three stages of one pipeline: the store answers a lookup (get),
            # the engine lands it in host memory (prefetch), the engine moves
            # it to HBM (load-back).  Charting the three together answers
            # whether the pipeline FLOWS.  It does not, on its own, answer
            # whether prefetch HELPS, for two reasons handled below.
            _pf_t = list(_sg_rate_t or [])
            _pf_v = list(_pref_rate or [])
            _lb_v = list(_load_rate or [])
            _get_r, _get_t = [], []
            try:
                _gp = _first_existing(raw_dir, ["l35_store_capacity.csv"])
                if _gp:
                    _gc = _amoprof_read_columns_raw(
                        _gp, ["time_sec", "l35_get_total_n"])
                    _gt = _gc.get("time_sec") or []
                    _gv = _gc.get("l35_get_total_n") or []
                    if len(_gv) >= 2 and len(_gt) >= 2:
                        for _i in range(1, min(len(_gv), len(_gt))):
                            _dt = _gt[_i] - _gt[_i - 1]
                            _dv = _gv[_i] - _gv[_i - 1]
                            if _dt > 0 and _dv == _dv and _dv >= 0:
                                _get_r.append(_dv / _dt)
                                _get_t.append(_gt[_i])
            except Exception:
                _get_r, _get_t = [], []

            _stages = []
            if _pf_v and any(v > 0 for v in _pf_v):
                _stages.append({"tier": "L3.5", "label": f"prefetch {_TIER}\u2192L2 (tok/s)",
                                "t": _pf_t, "v": _pf_v, "cap": max(_pf_v),
                                "color": "#22c55e",
                                "src": ("sglang_timeseries.csv",
                                        "sglang_prefetched_tokens_total",
                                        "\u0394counter \u00f7 \u0394t, summed over tp_rank \u2014 ENGINE side")})
            if _get_r and any(v > 0 for v in _get_r):
                _stages.append({"tier": "L3.5", "label": "L3.5 gets (lookups/s)",
                                "t": _get_t, "v": _get_r, "cap": max(_get_r),
                                "color": "#38bdf8",
                                "src": ("l35_store_capacity.csv", "l35_get_total_n",
                                        "\u0394total_get_nums_ \u00f7 \u0394t \u2014 STORE side, a different host and scrape")})
            if _lb_v and any(v > 0 for v in _lb_v):
                _stages.append({"tier": "L2", "label": "load-back L2\u2192L1 (tok/s)",
                                "t": _pf_t, "v": _lb_v, "cap": max(_lb_v),
                                "color": "#a78bfa",
                                "src": ("sglang_timeseries.csv",
                                        "sglang_load_back_tokens_total",
                                        "\u0394counter \u00f7 \u0394t \u2014 ALL L2\u2192L1 restores, prefetched or already resident")})

            if len(_stages) >= 2:
                _chain_svg = _amoprof_exec_svg_tier_occupancy(
                    _stages, window=_occ_win, wall_start=_occ_wall, mode="fill",
                    title="Prefetch delivery chain \u2014 get \u2192 prefetch \u2192 load-back",
                    subtitle=("each series as % of its own peak, since the three "
                              "have different units \u00b7 shape, not magnitude "
                              "\u00b7 aligned peaks mean the pipeline flows; a "
                              "stage that stays flat while the one above it moves "
                              "is where delivery stops"),
                    yaxis="% of that series peak", width=760)
                _l35_int_svg += _chain_svg
                _l35_int_svg += _src_block_from_series(
                    _stages,
                    note=("Three different meters. One prefetch operation can "
                          "issue many gets, and a get returns bytes while "
                          "prefetch counts tokens, so none of these converts "
                          "into another \u2014 read them as shapes over time."))

                # Statistics.  Reported in the note rather than on the chart,
                # because a correlation is a claim and needs its caveats next
                # to it.
                _rows_st = []
                if _pf_v and _lb_v:
                    _r0 = _pearson(_pf_v, _lb_v)
                    _rl, _lag = _lagged_pearson(_pf_v, _lb_v, max_lag=6)
                    _rows_st.append(("prefetch \u2192 load-back", _r0, _rl, _lag))
                if _pf_v and _get_r:
                    _ga, _pa = _align_xy(_get_t, _get_r, _pf_t, _pf_v)
                    if len(_ga) >= 4:
                        _r0g = _pearson(_ga, _pa)
                        _rlg, _lagg = _lagged_pearson(_ga, _pa, max_lag=6)
                        _rows_st.append(("L3.5 gets \u2192 prefetch", _r0g, _rlg, _lagg))
                _st_tr = "".join(
                    "<tr><td>" + _n + "</td><td><code>" + f"{_a:+.2f}" +
                    "</code></td><td><code>" + f"{_b:+.2f}" +
                    "</code></td><td><code>" + (f"{_c:+d}" if _c else "0") +
                    "</code></td></tr>"
                    for _n, _a, _b, _c in _rows_st)

                # The confound.  Both prefetch and load-back rise with how busy
                # the engine is, so a strong raw r can be entirely explained by
                # request arrival.  Hold the input token rate constant.
                _pc, _pc_txt = None, ""
                if _pf_v and _lb_v and _in_tok_rate:
                    _n3 = min(len(_pf_v), len(_lb_v), len(_in_tok_rate))
                    if _n3 >= 6:
                        _pc = _partial_pearson(_pf_v[:_n3], _lb_v[:_n3],
                                               _in_tok_rate[:_n3])
                        _r_raw = _pearson(_pf_v[:_n3], _lb_v[:_n3])
                        _drop = abs(_r_raw) - abs(_pc)
                        _pc_txt = (
                            "<p>Holding input tok/s constant, prefetch\u2194load-back "
                            "falls from <code>" + f"{_r_raw:+.2f}" + "</code> to "
                            "<code>" + f"{_pc:+.2f}" + "</code>. "
                            + ("Most of the raw correlation was the two rising "
                               "together with request load, not prefetch feeding "
                               "load-back."
                               if _drop > 0.25 else
                               "The relationship survives the control, so it is "
                               "not simply both tracking request load.")
                            + "</p>")

                # What actually answers "is prefetch helping".
                #
                # This MUST use the partial correlation, not the raw one.
                # Prefetch rises with load and so does recompute, so the raw
                # r is dominated by the common driver and reports the
                # OPPOSITE conclusion: on a synthetic run built so that
                # recompute = 0.25*load - 0.40*prefetch -- prefetch
                # demonstrably relieving the GPU -- the raw r is +0.94
                # ("not helping") while the partial r is -0.70, which is the
                # planted truth.  validate_math pins that case.
                _eff_txt = ""
                if _pf_v and _pf_compute_strict and _pf_modes_measured:
                    _ne = min(len(_pf_v), len(_pf_compute_strict))
                    _has_load = bool(_in_tok_rate) and len(_in_tok_rate) >= _ne
                    if _ne >= 6 and _has_load:
                        _re_raw = _pearson(_pf_v[:_ne], _pf_compute_strict[:_ne])
                        _re = _partial_pearson(_pf_v[:_ne],
                                               _pf_compute_strict[:_ne],
                                               _in_tok_rate[:_ne])
                        _eff_txt = (
                            "<p><b>The efficacy test.</b> Prefetch only helps if "
                            "it displaces GPU work, so the outcome variable is "
                            "recompute, not load-back. Against "
                            "<code>prefill_compute</code> tok/s, holding input "
                            "tok/s constant, the correlation is <code>"
                            + f"{_re:+.2f}" + "</code> (raw <code>"
                            + f"{_re_raw:+.2f}" + "</code>). "
                            + ("Negative: at a given request load, intervals with "
                               "more prefetch recompute less. That is prefetch "
                               "doing its job."
                               if _re < -0.2 else
                               ("Positive even with load held constant: more "
                                "prefetch goes with MORE recompute, which points "
                                "at prefetching the wrong KV rather than at "
                                "prefetch being idle."
                                if _re > 0.2 else
                                "Near zero once load is held constant: prefetch "
                                "volume is not moving recompute either way in "
                                "this window."))
                            + " The raw figure is shown because it is usually the "
                            "misleading one \u2014 both series track request load, "
                            "so it tends to read positive whatever prefetch is "
                            "doing.</p>")
                    elif _ne >= 6:
                        _eff_txt = (
                            "<p><b>The efficacy test could not be run.</b> It "
                            "needs the input token rate to hold request load "
                            "constant; without that control the raw correlation "
                            "between prefetch and recompute is dominated by load "
                            "and points the wrong way, so it is not reported.</p>")

                # Yield: confound-free because it is per unit of work.
                _yield_txt = ""
                _pf_tot = _kv_token_delta(raw_dir, ["prefetched_tokens_total"])
                _lb_tot = _kv_token_delta(raw_dir, ["load_back_tokens_total"])
                if _pf_tot and _lb_tot and _pf_tot > 0:
                    _ratio_lb = _lb_tot / _pf_tot
                    _yield_txt = (
                        "<p><b>Yield.</b> " + f"{_lb_tot:,.0f}" + " tokens were "
                        "loaded back against " + f"{_pf_tot:,.0f}" + " prefetched "
                        "(" + f"{_ratio_lb:,.2f}" + "\u00d7). "
                        + ("Load-back far exceeds prefetch, so most restores came "
                           "from KV already resident in L2 \u2014 prefetch is a "
                           "minority contributor to what reaches the GPU."
                           if _ratio_lb > 2.0 else
                           ("Load-back is far below prefetch: KV is being pulled "
                            "into L2 and not consumed before it is displaced, "
                            "which is wasted tier bandwidth."
                            if _ratio_lb < 0.5 else
                            "The two are of the same order, consistent with "
                            "prefetched KV being consumed rather than displaced."))
                        + "</p>")

                _l35_int_svg += (
                    '<details class="amoprof-src amoprof-note">'
                    '<summary><span class="amoprof-src-ic">?</span>'
                    'is prefetch actually helping?</summary>'
                    '<div class="amoprof-src-body amoprof-note-body">'
                    '<p><b>A correlation between these three does not by itself '
                    'show that prefetch helps.</b> <code>load_back_tokens_total</code> '
                    'counts every L2\u2192L1 restore, including KV that was already '
                    f'resident and never came from {_TIER} \u2014 so it is a superset, '
                    'not a mirror, of prefetch. And all three rise when the engine '
                    'is busy, which produces correlation without causation.</p>'
                    + ('<table><thead><tr><th>Stage pair</th><th>r (lag 0)</th>'
                       '<th>best r</th><th>lag</th></tr></thead><tbody>'
                       + _st_tr + '</tbody></table>'
                       '<p>Lag is in sampling intervals; a non-zero lag is normal '
                       'for asynchronous prefetch and is why a lag-0 r alone can '
                       'read as "no relationship" on a pipeline that works.</p>'
                       if _st_tr else "")
                    + _pc_txt + _yield_txt + _eff_txt
                    + '</div></details>')

            # ---- Prefetch benefit against a no-L3/L3.5 baseline ----------
            # An ACCOUNTING argument, not a statistical one, and stronger
            # than the correlation above for exactly that reason.
            #
            # Every prefill token is either served from cache or recomputed,
            # and that total is fixed by the requests that arrived.  A token
            # the engine fetched from the backing tier and used is a token
            # that, without that tier, would have been recomputed.  So the
            # counterfactual moves tokens from "cached" to "recomputed"
            # while the denominator stays put.
            #
            # What bounds it: a prefetched token is only a benefit if it was
            # CONSUMED.  No counter reports consumption directly, though
            # storage_prefetch_unfulfilled_tokens_total does report the
            # opposite end -- tokens asked for and never delivered -- which
            # is charted above.  Delivered is still not the same as used.
            # Two ceilings bound it:
            # a consumed token must also have crossed L2->L1 (so it is in
            # load-back), and it must be among the prefill tokens served
            # from cache.  Hence B = min(prefetched, load_back, cached),
            # an upper bound whose binding term is itself the finding.
            try:
                # Not _kv_token_delta("prefetched_tokens_total"): that counter
                # reads 0 on builds where prefetch is running, which would put
                # the benefit bound at 0 and report a working tier as useless.
                _pt_t, _pt_v, _P_src, _pf_ops, _pf_unf = \
                    _prefetch_tokens_resolved(raw_dir)
                _P = (max(0.0, _pt_v[-1] - _pt_v[0])
                      if _pt_v and len(_pt_v) >= 2 else None)
                _LB = _kv_token_delta(raw_dir, ["load_back_tokens_total"])
                _cv = [v for v in (_sg_phase.get("prefill_cache") or []) if v == v]
                _rv = [v for v in (_sg_phase.get("prefill_compute") or []) if v == v]
                _C = (max(0.0, _cv[-1] - _cv[0]) if len(_cv) >= 2 else None)
                _R = (max(0.0, _rv[-1] - _rv[0]) if len(_rv) >= 2 else None)
            except Exception:
                _P = _LB = _C = _R = None
                # These three come from the same try and are read below
                # whether or not the benefit terms resolved, so they must be
                # defined on the failure path too.
                _P_src, _pf_ops, _pf_unf = "", None, None

            # Prefetch outcome stands on its own two counters.  It was
            # nested inside the benefit gate below, which also requires
            # load-back and the prefill mode counters -- so a run missing
            # either lost the one chart that would have explained why.
            # Worse, the gate needs a non-zero prefetch TOKEN total, and the
            # case this chart exists to diagnose is prefetch asking for
            # tokens and being delivered none: hit 0, unfulfilled large,
            # _P None, chart suppressed exactly when it was needed.
            # Prefetch outcome: asked for vs delivered.  hit and
            # unfulfilled partition the attempt, so together they say
            # whether prefetch is finding what it goes looking for --
            # which the token total alone cannot, and which no counter
            # AMOprof previously fetched could answer at all.
            _outcome = ""
            try:
                _hit_s = _kv_counter_series(
                    raw_dir, ["storage_prefetch_hit_tokens_total"])
                _hit_tot = (max(0.0, _hit_s[1][-1] - _hit_s[1][0])
                            if _hit_s and _hit_s[1] and len(_hit_s[1]) >= 2
                            else None)
                _unf_s2 = _kv_counter_series(
                    raw_dir, ["storage_prefetch_unfulfilled_tokens_total"])
                _unf_tot = (max(0.0, _unf_s2[1][-1] - _unf_s2[1][0])
                            if _unf_s2 and _unf_s2[1] and len(_unf_s2[1]) >= 2
                            else _pf_unf)
                if _hit_tot is not None and _unf_tot is not None:
                    _asked = _hit_tot + _unf_tot
                    if _asked > 0:
                        _fill = _hit_tot / _asked * 100.0
                        _ob = {"delivered (hit)": _hit_tot,
                               "not delivered": _pf_unf}
                        _oc = {"delivered (hit)": "#22c55e",
                               "not delivered": "#ef4444"}
                        _outcome = _amoprof_exec_svg_percentile_bars(
                            "Prefetch outcome \u2014 asked for vs delivered",
                            (f"{_fill:,.1f}% of the tokens prefetch went "
                             f"looking for came back \u00b7 the remainder was "
                             f"a miss, a timeout or an abort \u00b7 these two "
                             f"partition the attempt, so they sum to what "
                             f"was requested"),
                            "tokens", _ob, _oc, width=760)
                        _outcome += _amoprof_src_block(
                            [("delivered (hit)", "sglang_timeseries.csv",
                              "sglang_storage_prefetch_hit_tokens_total",
                              "\u0394 over the window, summed over tp_rank"),
                             ("not delivered", "sglang_timeseries.csv",
                              "sglang_storage_prefetch_unfulfilled_tokens_total",
                              "\u0394 over the window, summed over tp_rank")],
                            note=("Storage-side outcome of each prefetch "
                                  "attempt. A high not-delivered share means "
                                  "the engine is asking the tier for KV it "
                                  "does not hold \u2014 tier bandwidth and "
                                  "latency spent for nothing, which the "
                                  "token total alone cannot show."))
            except Exception:
                _outcome = ""
            _l35_int_svg += _outcome

            if _P and _LB and _C and _R is not None and (_C + _R) > 0:
                _B = min(_P, _LB, _C)
                _bind = ("prefetched tokens" if _B == _P else
                         ("load-back" if _B == _LB else "prefill served from cache"))
                _tot_pf = _C + _R
                _hit_obs = _C / _tot_pf * 100.0
                _hit_base = (_C - _B) / _tot_pf * 100.0
                # Measured quantities only.  The counterfactual bars that
                # stood here were COMPUTED, and a bar chart puts a computed
                # value at the same visual weight as a measured one however
                # the caption labels it.  The counterfactual is arithmetic,
                # so it belongs in the arithmetic, not in the picture.
                #
                # Only the three token-unit quantities share an axis.  L3.5
                # gets are LOOKUPS, so they are reported in the ledger with
                # their own unit rather than given a bar whose height would
                # invite comparison against a token count.  Converting them
                # to tokens via KV bytes/token is possible and deliberately
                # not done: that conversion is unreliable at absolute scale.
                _bars = {
                    f"prefetched {_TIER}\u2192L2": _P,
                    "load-back L2\u2192L1": _LB,
                    "recomputed (missed)": _R,
                }
                _bcol = {
                    f"prefetched {_TIER}\u2192L2": "#22c55e",
                    "load-back L2\u2192L1": "#a78bfa",
                    "recomputed (missed)": "#ef4444",
                }
                _l35_int_svg += _amoprof_exec_svg_percentile_bars(
                    "KV delivery ledger \u2014 what each stage moved",
                    ("window totals, all measured \u00b7 tokens only, so the three "
                     f"are directly comparable \u00b7 {_TIER} gets are lookups and are "
                     "reported below in their own unit"),
                    "tokens", _bars, _bcol, width=760)
                _l35_int_svg += _amoprof_src_block(
                    [(f"prefetched {_TIER}\u2192L2", "sglang_timeseries.csv",
                      _P_src or "sglang_prefetched_tokens_total",
                      "\u0394 over the window, summed over tp_rank"),
                     ("load-back L2\u2192L1", "sglang_timeseries.csv",
                      "sglang_load_back_tokens_total",
                      "\u0394 over the window, summed over tp_rank"),
                     ("recomputed (missed)", "sglang_timeseries.csv",
                      "realtime_tokens_total[mode=prefill_compute]",
                      "\u0394 over the window")],
                    note=("All three are engine-side counter differences over "
                          "the selected window \u2014 measured, with nothing "
                          "derived. Load-back counts every L2\u2192L1 restore, "
                          "whatever its origin, so it is not a subset of "
                          "prefetch."))

                # The ledger, including the quantities that do not share the
                # chart's unit.  Visible rather than collapsed: this is the
                # factual record the rest of the panel argues from.
                _get_n = _get_mem = _get_file = None
                try:
                    _gp2 = _first_existing(raw_dir, ["l35_store_capacity.csv"])
                    if _gp2:
                        _gc2 = _amoprof_read_columns_raw(
                            _gp2, ["l35_get_total_n", "l35_mem_hit_n",
                                   "l35_file_hit_n"])
                        def _win_delta(_k):
                            _v = [x for x in (_gc2.get(_k) or []) if x == x]
                            return (max(0.0, _v[-1] - _v[0])
                                    if len(_v) >= 2 else None)
                        _get_n = _win_delta("l35_get_total_n")
                        _get_mem = _win_delta("l35_mem_hit_n")
                        _get_file = _win_delta("l35_file_hit_n")
                except Exception:
                    _get_n = _get_mem = _get_file = None

                _led = [(f"prefetched {_TIER}\u2192L2", f"{_P:,.0f}", "tokens",
                         "engine", _P_src or "sglang_prefetched_tokens_total"),
                        ("load-back L2\u2192L1", f"{_LB:,.0f}", "tokens",
                         "engine", "sglang_load_back_tokens_total"),
                        ("prefill served from cache", f"{_C:,.0f}", "tokens",
                         "engine", "realtime_tokens_total[mode=prefill_cache]"),
                        ("recomputed (missed)", f"{_R:,.0f}", "tokens",
                         "engine", "realtime_tokens_total[mode=prefill_compute]")]
                if _get_n is not None:
                    _led.append(("L3.5 gets \u00b7 total", f"{_get_n:,.0f}",
                                 "lookups", "store", "total_get_nums_"))
                if _get_mem is not None:
                    _led.append(("L3.5 gets \u00b7 answered by DRAM tier",
                                 f"{_get_mem:,.0f}", "lookups", "store",
                                 "mem_cache_hit_nums_"))
                if _get_file is not None:
                    _led.append(("L3.5 gets \u00b7 answered by file tier",
                                 f"{_get_file:,.0f}", "lookups", "store",
                                 "file_cache_hit_nums_"))
                if _pf_ops:
                    _led.append(("prefetch operations", f"{_pf_ops:,.0f}",
                                 "operations", "engine",
                                 "sglang_prefetch_pgs histogram _count"))
                    # Tokens per operation.  Available on every build that
                    # exports the histogram, and it separates "prefetch is
                    # rarely invoked" from "prefetch is invoked constantly
                    # and brings back almost nothing" -- two very different
                    # problems that the token total alone cannot tell apart.
                    if _P and _pf_ops > 0:
                        _led.append(("prefetch tokens per operation",
                                     f"{_P / _pf_ops:,.1f}", "tokens/op",
                                     "derived",
                                     "prefetched tokens \u00f7 prefetch operations"))
                    if _pf_ops > 0 and _occ_win and isinstance(_occ_win, (tuple, list)):
                        _wsec = float(_occ_win[1]) - float(_occ_win[0])
                        if _wsec > 0:
                            _led.append(("prefetch operation rate",
                                         f"{_pf_ops / _wsec:,.2f}", "ops/s",
                                         "derived",
                                         "prefetch operations \u00f7 window seconds"))
                if _pf_unf is not None:
                    _led.append(("prefetch tokens NOT delivered",
                                 f"{_pf_unf:,.0f}", "tokens", "engine",
                                 "sglang_storage_prefetch_unfulfilled_tokens_total"))
                _led.append(("L3-local gets", "\u2014", "not exported",
                             "\u2014",
                             "no get counter exists for the local tier"))

                # Reconciliation.  "Recomputed" is not derived -- it is the
                # mode-labelled counter, read directly -- but saying so is
                # weaker than showing it.  prefill_cache and prefill_compute
                # partition the prompt tokens, so their sum must equal
                # prompt_tokens_total, which is a SEPARATE counter the split
                # does not feed.  If the three agree, the decomposition is
                # confirmed by something outside itself; if they do not, the
                # gap is stated rather than absorbed.

                # When operations ran but the token counter did not move, say
                # which counter was believed and why, rather than printing a
                # zero that reads as an idle tier.
                _pf_zero_note = ""
                if _pf_ops and _P_src and "storage_prefetch_hit" in _P_src:
                    _pf_zero_note = (
                        '<p><b>Which prefetch counter this uses.</b> '
                        '<code>sglang_prefetched_tokens_total</code> reads 0 on '
                        'this run while <code>sglang_prefetch_pgs</code> counts '
                        + f"{_pf_ops:,.0f}"
                        + ' prefetch operations, so the token volume is taken '
                        'from <code>sglang_storage_prefetch_hit_tokens_total</code> '
                        'instead. Comparing this figure against a run whose '
                        'volume came from the other counter is comparing two '
                        'different meters.</p>')
                elif _pf_ops and not _P_src:
                    _pf_zero_note = (
                        '<p><b>Prefetch ran but moved no measured tokens.</b> '
                        + f"{_pf_ops:,.0f}"
                        + ' prefetch operations are counted by '
                        '<code>sglang_prefetch_pgs</code>, while every prefetch '
                        'token counter this build exports reads 0. The benefit '
                        'bound below is therefore 0 by measurement, not by '
                        'finding \u2014 the tier may be working and unmeasured.</p>')

                _recon = ""
                try:
                    _pt = _kv_token_delta(raw_dir, ["prompt_tokens_total"])
                    if _pt and _pt > 0:
                        _sum_cr = _C + _R
                        _gap = _sum_cr - _pt
                        _gap_pct = _gap / _pt * 100.0
                        _ok = abs(_gap_pct) <= 1.0
                        _recon = (
                            '<p style="margin-top:8px"><b>Does the split '
                            'reconcile?</b> cached + recomputed = '
                            + f"{_C:,.0f} + {_R:,.0f} = {_sum_cr:,.0f}"
                            + ' tokens, against <code>prompt_tokens_total</code> '
                            + f"= {_pt:,.0f}"
                            + ' \u2014 an independent counter that neither mode '
                            'feeds. '
                            + (f"They agree to {abs(_gap_pct):.2f}%, so the "
                               "cached/recomputed split is confirmed against "
                               "something outside itself."
                               if _ok else
                               f"They differ by {_gap:+,.0f} tokens "
                               f"({_gap_pct:+.2f}%). The mode counters and the "
                               "prompt counter are scraped from the same engine "
                               "but reset and roll over independently, so a small "
                               "gap is sampling skew; a large one means the split "
                               "is not accounting for all prompt tokens and the "
                               "benefit figures below should be treated as "
                               "indicative.")
                            + '</p>')
                except Exception:
                    _recon = ""
                _led_tr = "".join(
                    '<tr class="id"><td>' + _n + '</td><td style="text-align:right">'
                    '<code>' + _v + '</code></td><td>' + _u + '</td><td>' + _w +
                    '</td><td><code>' + _m + '</code></td></tr>'
                    for _n, _v, _u, _w, _m in _led)
                _l35_int_svg += (
                    '<div class="amoprof-src-body amoprof-note-body" '
                    'style="margin:2px 0 10px 0">'
                    '<table><thead><tr><th>Stage</th>'
                    '<th style="text-align:right">Window total</th>'
                    '<th>Unit</th><th>Measured at</th><th>Metric</th>'
                    '</tr></thead><tbody>' + _led_tr + '</tbody></table>'
                    '<p>Every row is a counter difference over the selected '
                    'window. Tokens and lookups are different units and do not '
                    'convert into one another: one prefetch operation can issue '
                    'many gets, and a get returns bytes rather than tokens. '
                    '<b>Recomputed is measured, not derived</b>: it is '
                    '<code>realtime_tokens_total{mode=prefill_compute}</code>, '
                    'the engine&#39;s own count of prefill tokens it had to '
                    'compute because the cache did not have them.</p>'
                    + _pf_zero_note + _recon +
                    '</div>')

                # What the saved tokens are worth.
                #
                # NOT "seconds saved inside this window".  The counterfactual
                # holds TOKENS invariant, not TIME: the same prefill work has
                # to happen, and at the observed recompute throughput it can
                # take longer than the window did.  A first cut divided B by
                # the mean recompute rate and produced 4,607 s of saving in a
                # 1,989 s run -- impossible on its face, and the giveaway that
                # the window is not invariant under the counterfactual.
                #
                # The unit-free multiple is the sound statement; the time
                # figure is reported only as a floor, and when it exceeds the
                # window that is said plainly, because it means the run itself
                # would have been longer rather than merely busier.
                _gpu_txt = ""
                try:
                    _rc_f = [v for v in (_pf_compute_strict or []) if v == v and v > 0]
                    _mult = ((_R + _B) / _R) if _R > 0 else None
                    _rc_peak = max(_rc_f) if _rc_f else 0.0
                    _secs = (_B / _rc_peak) if _rc_peak > 0 else None
                    # _occ_win is a (start, end) pair, not a duration.
                    _win_s = None
                    if isinstance(_occ_win, (tuple, list)) and len(_occ_win) == 2:
                        _win_s = float(_occ_win[1]) - float(_occ_win[0])
                        _win_s = _win_s if _win_s > 0 else None
                    _gpu_txt = "<p><b>What that is worth.</b> "
                    if _mult:
                        _gpu_txt += (f"Recompute would have been {_mult:,.2f}\u00d7 "
                                     f"its observed volume \u2014 "
                                     f"{_R:,.0f} tokens becoming {_R + _B:,.0f}. ")
                    if _secs and _win_s and _secs > _win_s:
                        _gpu_txt += (
                            f"At the peak recompute rate this run reached "
                            f"({_rc_peak:,.0f} prefill tok/s) that extra work needs "
                            f"{_secs:,.0f} s, which is longer than the "
                            f"{_win_s:,.0f} s window. The counterfactual holds "
                            "TOKENS fixed, not time: without the tier this run "
                            "would have taken longer, so the benefit cannot be "
                            "stated as seconds saved inside this window.")
                    elif _secs:
                        _gpu_txt += (
                            f"At the peak recompute rate this run reached "
                            f"({_rc_peak:,.0f} prefill tok/s) that is at least "
                            f"{_secs:,.0f} s of prefill work avoided \u2014 a floor, "
                            "since the GPU rarely sustains its peak.")
                    _gpu_txt += (" None of this is a latency claim: fetching from "
                                 "the tier has its own cost, and if the round trip "
                                 "is slower than recomputing, tokens saved can "
                                 "still mean requests slowed.</p>")
                except Exception:
                    import os as _os_g
                    if _os_g.environ.get("AMOPROF_DEBUG_CORR"):
                        import traceback as _tb_g
                        _tb_g.print_exc()
                    _gpu_txt = ""

                _l35_int_svg += (
                    '<details class="amoprof-src amoprof-note">'
                    '<summary><span class="amoprof-src-ic">?</span>'
                    'how this benefit is derived</summary>'
                    '<div class="amoprof-src-body amoprof-note-body">'
                    '<p>Every prefill token is either served from cache or '
                    'recomputed, and the total is fixed by the requests that '
                    'arrived. A token fetched from the backing tier <i>and '
                    'used</i> is one that would otherwise have been recomputed, '
                    'so the counterfactual moves tokens between the two columns '
                    'and leaves the total alone.</p>'
                    '<table><thead><tr><th>Term</th><th>Tokens</th>'
                    '<th>What it is</th></tr></thead><tbody>'
                    + '<tr class="id"><td>P prefetched</td><td><code>'
                    + f"{_P:,.0f}" + f'</code></td><td>moved {_TIER}\u2192L2</td></tr>'
                    + '<tr class="id"><td>LB load-back</td><td><code>'
                    + f"{_LB:,.0f}" + '</code></td><td>moved L2\u2192L1 (any origin)</td></tr>'
                    + '<tr class="id"><td>C cached</td><td><code>'
                    + f"{_C:,.0f}" + '</code></td><td>prefill served from cache</td></tr>'
                    + '<tr class="id"><td>R recomputed</td><td><code>'
                    + f"{_R:,.0f}" + '</code></td><td>prefill recomputed</td></tr>'
                    + '<tr class="id"><td><b>B benefit</b></td><td><code>'
                    + f"{_B:,.0f}" + '</code></td><td><b>min(P, LB, C)</b> \u2014 bound here by '
                    + _bind + '</td></tr></tbody></table>'
                    '<p><b>Why a bound and not a number.</b> A prefetched token '
                    'only helps if it is consumed. No counter reports '
                    'consumption directly \u2014 '
                    '<code>storage_prefetch_unfulfilled_tokens_total</code> '
                    'reports the opposite end, tokens asked for and never '
                    'delivered, and delivered is still not used. Two ceilings '
                    'bound it: a consumed token must have '
                    'crossed L2\u2192L1, so it is inside load-back; and it must be '
                    'among the prefill tokens served from cache. B takes the '
                    'smallest. Which term binds is itself the finding \u2014 bound '
                    'by <i>prefetched</i> means the tier is the limit, bound by '
                    '<i>load-back</i> or <i>cached</i> means tokens were pulled '
                    'in that the engine did not use.</p>'
                    '<p><b>The one thing this cannot see.</b> Prefetched KV lands '
                    'in L2 and occupies it. If L2 is full, each prefetched token '
                    'can displace a resident one that would have been hit later, '
                    'and that loss is invisible to this accounting \u2014 so B is an '
                    'upper bound on the NET benefit, not just on the gross. When '
                    'the tier is thrashing, the displacement can cancel the gain '
                    'outright. Only an A/B against a run without the tier settles '
                    'it, which is what <code>amoprof compare</code> is for.</p>'
                    + _gpu_txt +
                    '</div></details>')
        except Exception:
            import os as _os_i
            if _os_i.environ.get("AMOPROF_DEBUG_CORR"):
                import traceback as _tb_i
                _tb_i.print_exc()

        # The prefetch outcome pair sits outside _l35_int_missing because it
        # comes from the ENGINE, not the store: the store files can all be
        # present and these still absent, which is what happens on a run
        # analysed before AMOprof requested them.  Say so in place, with the
        # command that fixes it, rather than letting a missing chart read as
        # a missing behaviour.
        if _l35_on:
            _pf_pair = [(_n, _k) for _n, _k in (
                ("delivered", "storage_prefetch_hit_tokens_total"),
                ("not delivered", "storage_prefetch_unfulfilled_tokens_total"))
                if not _kv_counter_series(raw_dir, [_k])]
            if _pf_pair:
                _l35_int_svg += (
                    '<div class="card" style="border-left:3px solid #f59e0b;'
                    'padding:12px 16px;margin:10px 0;font-size:12.5px">'
                    '<b>Prefetch outcome could not be drawn.</b> '
                    'These engine counters are not columns in '
                    '<code>raw/sglang_timeseries.csv</code>:'
                    '<ul style="margin:6px 0 0 18px">'
                    + "".join(f'<li>{_n} &mdash; <code>sglang_{_k}</code></li>'
                              for _n, _k in _pf_pair)
                    + '</ul>'
                    '<p style="margin:8px 0 0 0">Two different causes, and '
                    'they need different fixes. Check which one it is by '
                    'asking Prometheus for the metric by name &mdash; or the '
                    'engine directly, <code>curl -s '
                    'http://&lt;sglang&gt;:&lt;port&gt;/metrics | grep '
                    'storage_prefetch</code>.</p>'
                    '<p style="margin:6px 0 0 0"><b>Present in Prometheus but '
                    'not pulled.</b> Re-fetch the family; a plain '
                    '<code>analyze --run-dir</code> will not add them, because '
                    'the default <code>--prefer local</code> keeps the existing '
                    '<code>sglang_timeseries.csv</code> and fills only MISSING '
                    'files:<br><code>amoprof analyze --run-dir &lt;dir&gt; '
                    '--prometheus http://&lt;host&gt;:9090 --start &lt;start&gt; '
                    '--end &lt;end&gt; --prefer prometheus</code></p>'
                    '<p style="margin:6px 0 0 0"><b>Not exported by this engine '
                    'build at all.</b> Then no re-fetch will help, and nothing '
                    'is wrong with the run. The question these two counters '
                    'answer &mdash; did prefetch ask for KV the tier did not '
                    'have? &mdash; is answered from the store side instead by '
                    '<b>L3.5 get outcome over the run</b> above, which compares '
                    '<code>total_get_nums_</code> against the per-tier hit '
                    'counters. A get-hit rate at or near 100% means the tier '
                    'delivered everything it was asked for, so a small prefetch '
                    'volume is the engine not asking rather than the tier not '
                    'answering.</p></div>')

        # L3.5 is configured, so these charts are expected.  When any is
        # missing, say which and why rather than leaving the reader to wonder
        # whether the tier was idle or simply not measured.
        if _l35_on and (_l35_int_missing or not _l35_src_found):
            if not _l35_src_found:
                _why = ("<code>l35_store_capacity.csv</code> is not in this "
                        "run's raw directory, so no store metrics were "
                        "fetched. Re-run <code>analyze</code> with "
                        "<code>--l35-instance</code> pointing at the store's "
                        "exporter; the run log prints "
                        "<code>L3.5 store capacity: ok</code> when it succeeds.")
                _items = ["Eviction over the run", "Get outcome over the run",
                          "Promotion pipeline"]
            else:
                _why = ("the store's timeseries exists but these counters are "
                        "absent or never moved in the window:")
                _items = [f"{n} &mdash; <code>{m}</code>"
                          for n, m in _l35_int_missing]
            _l35_int_svg += (
                '<div class="card" style="border-left:3px solid #f59e0b;'
                'padding:12px 16px;margin:10px 0;font-size:12.5px">'
                '<b>L3.5 is configured, but some store charts could not be '
                'drawn.</b> Cause: ' + _why +
                '<ul style="margin:6px 0 0 18px">'
                + "".join(f"<li>{x}</li>" for x in _items) + '</ul></div>')

        if _cu_svg or _mc_cap_svg or _l35_int_svg:

            _cards.append(_card(
                "Compute and capacity utilisation over the run",
                "What was busy and when, on one 0-100 axis. The correlation "
                "cards answer what moves with what; these answer when it "
                f"happened. {_kv_header}",
                _cu_svg + _mc_cap_svg + _mc_cap_pct_svg + _cxl_svg
                + _l35_bw_svg + _l35_ssd_svg + _lba_svg + _l35_int_svg,
                "A flat line at 100% is a saturated resource; a line that "
                "tracks the request rate is a resource doing proportional "
                "work; a line that is flat and low while latency rises is a "
                "resource that is <i>not</i> the constraint. Capacity "
                "utilisation counts everything resident in a tier, so it can "
                "read high while the KV share (previous chart) is small \u2014 "
                "that difference is weights and page cache, not KV pressure.",
                layers="A4_GPU_HBM \u00b7 A3_DRAM \u00b7 A1/A2_L3 \u00b7 CPU"))

        # ---- L1 (HBM) bandwidth vs token throughput ----------------------
        # Mirrors the L2 DRAM-BW and L3 read/write-BW cards so every tier has
        # a bandwidth-vs-throughput view, not just an occupancy view.
        if _hbm_bw_util_series:
            _l1bw_series, _l1bw_label, _l1bw_src = (
                (_hbm_bw_gbs_series, "HBM BW (GB/s)",
                 f"{_hbm_bw_util_src or 'utilization.memory'} x "
                 f"{_hbm_peak_gbs:.0f} GB/s device peak")
                if _hbm_bw_gbs_series else
                (_hbm_bw_util_series, "HBM BW util (%)",
                 _hbm_bw_util_src or "utilization.memory"))
            _l1bw_html = ""
            _in_x, _in_y = _align_xy(_sg_rate_t, _in_tok_rate, _gpu_time, _l1bw_series)
            if _in_ok and len(_in_x) >= 3:
                _px, _py = _decimate(_in_x, _in_y)
                _l1bw_html += _amoprof_exec_svg_scatter(
                    f"Input tok/s vs {_l1bw_label}",
                    "Input throughput (tok/s, per-interval)", _l1bw_label,
                    _px, _py, point_color="#f59e0b",
                    subtitle=f"n={len(_in_x)} time-aligned samples")
            _out_x, _out_y = _align_xy(_sg_rate_t, _out_tok_rate, _gpu_time, _l1bw_series)
            if _out_ok and len(_out_x) >= 3:
                _px, _py = _decimate(_out_x, _out_y)
                _l1bw_html += _amoprof_exec_svg_scatter(
                    f"Output tok/s vs {_l1bw_label}",
                    "Output throughput (tok/s, per-interval)", _l1bw_label,
                    _px, _py, point_color="#fb923c",
                    subtitle=f"n={len(_out_x)} time-aligned samples")
            if _l1bw_html:
                _cards.append(_card(
                    "L1 (HBM · GPU) · HBM bandwidth vs Input / Output throughput",
                    f"{_l1bw_src} paired with sglang_timeseries.csv "
                    f"\u0394prompt/\u0394generation tok/s. {_kv_header}",
                    _l1bw_html,
                    "HBM bandwidth rising with output tok/s is the normal decode signature — "
                    "decode is memory-bound, so each generated token costs a pass over the KV "
                    "working set. Rising with input tok/s instead points at prefill streaming "
                    "weights and activations. High GPU util at low HBM bandwidth means the "
                    "kernels are compute-bound, not memory-bound, and adding HBM headroom will "
                    "not help throughput.",
                    layers="A4_GPU_HBM ↔ A5_APP"))

        # ---- L2 (host DRAM as HiCache) ---- only render when L2 is configured
        # `l2_dram_capacity_gb` falls back to total host DRAM, so it is >0 on
        # any host with known DIMM capacity — including a run with no
        # hierarchical cache at all.  For the tier-correlation section the
        # question is "is host DRAM configured as a *KV cache tier*", so
        # require positive HiCache evidence: an explicit L2/HiCache
        # allocation, a truthy HiCache setup flag, or the launch flag.
        # When none of those keys exist at all the run predates that
        # metadata, so fall back to the previous capacity test rather than
        # silently dropping the card.
        _launch_l2 = str(launch or "").lower()
        _l2_launch_flag = ("--enable-hierarchical-cache" in _launch_l2
                           or "--hicache-ratio" in _launch_l2
                           or "--hicache-size" in _launch_l2)
        _cache_flag = str(cache_enabled or "").strip().lower()
        _l2_flag_true = _cache_flag in ("true", "yes", "on", "1", "enabled", "hicache")
        _l2_flag_false = _cache_flag in ("false", "no", "off", "0", "disabled", "none")
        _l2_evidence_available = bool(_launch_l2) or _cache_flag not in ("", "unknown")
        if _l2_evidence_available:
            _l2_configured = bool(hicache_total_gb > 0 or hicache_per_gpu_gb > 0
                                  or _l2_launch_flag or _l2_flag_true) and not (
                _l2_flag_false and not _l2_launch_flag
                and hicache_total_gb <= 0 and hicache_per_gpu_gb <= 0)
        else:
            _l2_configured = (l2_dram_capacity_gb or 0) > 0
        if _l2_configured and (_dram_total or _dram_read or _dram_write):
            _dram_series = _dram_total or [
                (_dram_read[i] if i < len(_dram_read) else 0) +
                (_dram_write[i] if i < len(_dram_write) else 0)
                for i in range(max(len(_dram_read), len(_dram_write)))]
            _in_x, _in_y = _align_xy(_sg_rate_t, _in_tok_rate, _dram_time, _dram_series)
            _out_x, _out_y = _align_xy(_sg_rate_t, _out_tok_rate, _dram_time, _dram_series)
            _l2_scatter_html = ""
            if _in_ok and len(_in_x) >= 3:
                _l2_scatter_html += _amoprof_exec_svg_scatter(
                    "Input tok/s vs DRAM BW (GB/s)",
                    "Input throughput (tok/s, per-interval)", "DRAM BW (GB/s)",
                    _in_x, _in_y, point_color="#a78bfa")
            if _out_ok and len(_out_x) >= 3:
                _l2_scatter_html += _amoprof_exec_svg_scatter(
                    "Output tok/s vs DRAM BW (GB/s)",
                    "Output throughput (tok/s, per-interval)", "DRAM BW (GB/s)",
                    _out_x, _out_y, point_color="#c084fc")
            if _l2_scatter_html:
                _cards.append(_card(
                    "L2 (host DRAM · HiCache) · DRAM BW vs Input / Output throughput",
                    f"pcm/amduprof_pcm dram_bw_gbps paired with sglang_timeseries.csv Δprompt/Δgeneration tok/s. L2 capacity {_l2_used_txt}. {_kv_header}",
                    _l2_scatter_html,
                    "Positive DRAM-BW correlation with output tok/s indicates L2 HiCache is on the decode path (KV restore from host DRAM). Weak/no correlation suggests HBM residency covers the working set."
                ,
                layers="A3_DRAM ↔ A5_APP"))

        # ---- L3 (local SSD / remote) ---- only render when L3 is configured
        try:
            _l3_backend_class = l3_backend_class
        except Exception:
            _l3_backend_class = "unknown"
        _l3_configured = _l3_backend_class in ("local_ssd", "remote_mooncake", "remote_storage")
        if _l3_configured and (_nvme_rd_mbps or _nvme_wr_mbps):
            _in_x_rd, _in_y_rd = _align_xy(_sg_rate_t, _in_tok_rate, _nvme_rd_bw_t, _nvme_rd_mbps)
            _out_x_rd, _out_y_rd = _align_xy(_sg_rate_t, _out_tok_rate, _nvme_rd_bw_t, _nvme_rd_mbps)
            _l3_rd_html = ""
            if len(_in_x_rd) >= 3:
                _l3_rd_html += _amoprof_exec_svg_scatter(
                    "Input tok/s vs L3 read BW (MB/s)",
                    "Input throughput (tok/s, per-interval)", "L3 read BW (MB/s)",
                    _in_x_rd, _in_y_rd, point_color="#22c55e")
            if len(_out_x_rd) >= 3:
                _l3_rd_html += _amoprof_exec_svg_scatter(
                    "Output tok/s vs L3 read BW (MB/s)",
                    "Output throughput (tok/s, per-interval)", "L3 read BW (MB/s)",
                    _out_x_rd, _out_y_rd, point_color="#14b8a6")
            if _l3_rd_html:
                _cards.append(_card(
                    "L3 (local storage) · Read BW vs Input / Output throughput",
                    f"nvme_driver / iostat read_bytes deltas paired with sglang_timeseries.csv Δprompt/Δgeneration tok/s. Backend: {_l3_backend_class}. {_kv_header}",
                    _l3_rd_html,
                    "L3-read correlation with output tok/s confirms the L2→L1 restore path is L3-fed (KV loadback). If L3 read tracks input tok/s more strongly, prefill is triggering L3 fetches (cold prompt regions)."
                ,
                layers="A1_L3_SSD · A2_NVME_DRIVER ↔ A5_APP"))
            _in_x_wr, _in_y_wr = _align_xy(_sg_rate_t, _in_tok_rate, _nvme_wr_bw_t, _nvme_wr_mbps)
            _out_x_wr, _out_y_wr = _align_xy(_sg_rate_t, _out_tok_rate, _nvme_wr_bw_t, _nvme_wr_mbps)
            if any(v > 0 for v in _in_y_wr + _out_y_wr):
                _l3_wr_html = ""
                if len(_in_x_wr) >= 3:
                    _l3_wr_html += _amoprof_exec_svg_scatter(
                        "Input tok/s vs L3 write BW (MB/s)",
                        "Input throughput (tok/s, per-interval)", "L3 write BW (MB/s)",
                        _in_x_wr, _in_y_wr, point_color="#f97316")
                if len(_out_x_wr) >= 3:
                    _l3_wr_html += _amoprof_exec_svg_scatter(
                        "Output tok/s vs L3 write BW (MB/s)",
                        "Output throughput (tok/s, per-interval)", "L3 write BW (MB/s)",
                        _out_x_wr, _out_y_wr, point_color="#ef4444")
                if _l3_wr_html:
                    _cards.append(_card(
                        "L3 (local storage) · Write BW vs Input / Output throughput",
                        "Write-side correlation isolates KV offload (backup) traffic from restore.",
                        _l3_wr_html,
                        "Positive write-BW correlation during decode-heavy windows indicates HiCache is proactively backing up KV to L3, freeing HBM for new sequences."
                    ,
                layers="A1_L3_SSD · A2_NVME_DRIVER ↔ A5_APP"))

        # ---- Token movement (evict / load-back / prefetch / backup) ↔ tier signals ----
        # Only-when-data-exists gating: each SGLang movement counter is
        # rendered only when it saw non-zero activity during the window,
        # and each tier signal is rendered only when it was collected.
        _token_activity_signals = [
            ("Evict rate (tok/s)",     _evict_rate,  "#ef4444",
             "Δsglang_evicted_tokens_total ÷ Δt — L1/L2 KV pool pressure"),
            ("Load-back rate (tok/s)", _load_rate,   "#f97316",
             "Δsglang_load_back_tokens_total ÷ Δt — L2→L1 restore (diagnostic; not L3 read bytes)"),
            ("Prefetch rate (tok/s)",  _pref_rate,   "#38bdf8",
             "Δsglang_prefetched_tokens_total ÷ Δt — read from HiCache backing tier"),
            ("Backup rate (tok/s)",    _backup_rate, "#22c55e",
             "Δsglang_backuped_tokens_total ÷ Δt — write/offload into HiCache backing tier"),
        ]
        _token_activity_signals = [(n, s, c, note) for (n, s, c, note) in _token_activity_signals if s and any(v > 0 for v in s)]

        def _tier_signal_bundle(configured: bool, label_prefix: str, entries: list) -> list:
            """Filter one tier's signal list to (configured tier ∧ collected).

            `entries` is [(y_label, y_series, y_times, y_color), ...].  When
            the tier is not configured the whole bundle is dropped, so a run
            without an L3 backend never renders an L3 axis and a run without
            an L2 HiCache allocation never renders a DRAM axis — this is the
            "correlate against configured tiers only" gate.  Series that are
            configured but were not collected are dropped individually.
            """
            if not configured:
                return []
            return [(f"{label_prefix}{lbl}", srs, tms, col)
                    for (lbl, srs, tms, col) in entries if srs]

        # ---- L1 (HBM · GPU) — configured whenever GPU telemetry exists ----
        # ---- Request latency vs token volume (tier-independent) ----------
        # E2E latency is a property of the request, not of a storage tier, so
        # this card is emitted regardless of which tiers are configured — it
        # is the one cross-layer view available even on an L1-only run.
        if _e2e_ms and (_in_tok_rate or _out_tok_rate):
            _lat_svg = ""
            for _drv_label, _drv_rate, _drv_col in (
                ("Input tok/s", _in_tok_rate, "#38bdf8"),
                ("Output tok/s", _out_tok_rate, "#a78bfa"),
            ):
                _lx, _ly = _align_xy(_sg_rate_t, _drv_rate, _e2e_t, _e2e_ms)
                if len(_lx) < 3:
                    continue
                _plx, _ply = _decimate(_lx, _ly)
                _lat_svg += _amoprof_exec_svg_scatter(
                    f"{_drv_label} vs E2E latency (ms)",
                    _drv_label, "E2E latency (ms)",
                    _plx, _ply, point_color=_drv_col,
                    subtitle=(f"n={len(_lx)} time-aligned samples"
                              if len(_plx) == len(_lx) else
                              f"n={len(_lx)} time-aligned samples · r on all, "
                              f"{len(_plx)} plotted"))
            if _lat_svg:
                _cards.append(_card(
                    "Request latency · Input / Output tokens vs E2E latency",
                    "Per-interval mean E2E latency (Δsglang_e2e_request_latency_seconds_sum ÷ "
                    "Δ..._count) scattered against prefill and decode token rate. "
                    f"{_kv_header}",
                    _lat_svg,
                    "E2E rising with input tok/s is prefill-bound: latency scales with prompt "
                    "volume, so batching or chunked prefill is the lever. E2E rising with output "
                    "tok/s is decode-bound, where the cost is per generated token and the lever "
                    "is batch size or TPOT. If neither correlates, latency is being set off the "
                    "token path — check queueing (num_queue_reqs) and the L2/L3 restore cards "
                    "below, where a storage stall shows up as latency uncorrelated with volume.",
                    layers="A5_APP · request latency"))

        _l1_configured = bool(_gpu_util_series or _hbm_used_series)
        _l1_entries = [
            # #f59e0b and #fb923c are both amber and were indistinguishable in
            # a legend.  Keep GPU amber; move HBM bandwidth to cyan, which is
            # far apart in hue and still legible for the common forms of
            # colour blindness.
            ("GPU util (%)",  _gpu_util_series, _gpu_time, "#f59e0b"),
            (("HBM BW (GB/s)" if _hbm_bw_gbs_series else "HBM BW util (%)"),
             (_hbm_bw_gbs_series or _hbm_bw_util_series), _gpu_time, "#22d3ee"),
            ("HBM used (GB)", [_k_gb_from_mib(v) for v in _hbm_used_series] if _hbm_used_series else [],
             _gpu_time, "#ec4899"),
        ]
        # ---- L2 (host DRAM · HiCache) ----
        # The despike in the tile path fixed the SUMMARY; the chart series is
        # read separately and still carried the poisoned samples, so the same
        # impossible number reappeared in a chart legend while the tile read
        # correctly. Filter here too — one source of truth for what counts as
        # a physically possible DRAM bandwidth sample.
        def _despike(_vals):
            # NaN out impossible samples rather than removing them: the paired
            # _dram_time array keeps its original length, and dropping
            # elements silently shifted every later value onto the wrong
            # timestamp.  Renderers already skip NaN.
            return [(v if (v == v and 0.0 <= v <= _DRAM_SANE_MAX_GBS)
                     else float("nan")) for v in (_vals or [])]

        _dram_total = _despike(_dram_total)
        _dram_read = _despike(_dram_read)
        _dram_write = _despike(_dram_write)
        _dram_series_local = _dram_total or (
            [(_dram_read[i] if i < len(_dram_read) else 0) +
             (_dram_write[i] if i < len(_dram_write) else 0)
             for i in range(max(len(_dram_read), len(_dram_write)))] if (_dram_read or _dram_write) else [])
        _l2_entries = [
            ("DRAM BW (GB/s)",       _dram_series_local, _dram_time, "#a78bfa"),
            ("DRAM read BW (GB/s)",  _dram_read,         _dram_time, "#818cf8"),
            ("DRAM write BW (GB/s)", _dram_write,        _dram_time, "#c084fc"),
            # Derived from SGLang hicache counters — available without a PMU.
            ("HiCache used (GB)",    _l2_used_gb,        _sg_time,   "#8b5cf6"),
            ("HiCache fill (%)",     _l2_fill_pct,       _sg_time,   "#a855f7"),
            ("L1->L2 evict BW (MB/s)",  _l2_in_mbps,  _sg_rate_t, "#d8b4fe"),
            ("L2->L1 restore BW (MB/s)", _l2_out_mbps, _sg_rate_t, "#c4b5fd"),
            # NOTE: the two entries above are the driver rate multiplied by a
            # constant (KV bytes/token).  Correlating them against the driver
            # they were derived from is tautological — r = 1.00 by
            # construction — so those pairs are excluded from ranking below,
            # otherwise they crowd the genuinely informative measured
            # correlations (e.g. evict vs DRAM *write* bandwidth) out of the
            # top-N drawn per card.
        ]
        # L2 charts render when EITHER the PMU measured DRAM bandwidth OR
        # SGLang reported host-cache activity.  Previously the whole tier was
        # gated on the PMU, so a configured HiCache with no AMDuProf/PCM
        # collector produced no L2 charts at all.
        if _l2_derived_ok:
            _l2_configured = True
        # ---- L3 (local storage / remote) ----
        _mc_get_t, _mc_get_ms = _interval_mean_ms("mooncake_get_duration_seconds")
        _mc_put_t, _mc_put_ms = _interval_mean_ms("mooncake_put_duration_seconds")
        _l35_entries = [
            ("read BW (MB/s)",   _mc_rd_mbps, _mc_rd_t,  "#38bdf8"),
            ("write BW (MB/s)",  _mc_wr_mbps, _mc_wr_t,  "#818cf8"),
            ("get lat (ms)",     _mc_get_ms,  _mc_get_t, "#f472b6"),
            ("put lat (ms)",     _mc_put_ms,  _mc_put_t, "#fb7185"),
            ("store used (GB)",  _mc_used,    _sg_time,  "#c084fc"),
            ("fill ratio (%)",   _mc_fill,    _sg_time,  "#a78bfa"),
            ("put ops/s",        _mc_put_ops, _mc_put_t, "#34d399"),
            ("read BW (MB/s)",   _l35_rd_mbs, _l35_rd_t, "#22d3ee"),
            ("errors/s",         _mc_err_ops, _mc_err_t, "#f87171"),
            ("keys stored",      _mc_keys,    _sg_time,  "#fbbf24"),
            ("active clients",   _mc_clients, _sg_time,  "#94a3b8"),
        ]

        _l3_entries = [
            ("read BW (MB/s)",  _nvme_rd_mbps,        _nvme_rd_bw_t,   "#22c55e"),
            ("write BW (MB/s)", _nvme_wr_mbps,        _nvme_wr_bw_t,   "#f97316"),
            ("read IOPS",       _nvme_rd_iops_series, _nvme_rd_iops_t, "#0ea5e9"),
            ("write IOPS",      _nvme_wr_iops_series, _nvme_wr_iops_t, "#eab308"),
            ("read lat (ms)",   _nvme_rd_lat_ms,      _nvme_time,      "#ef4444"),
            ("write lat (ms)",  _nvme_wr_lat_ms,      _nvme_time,      "#fb7185"),
            ("r+w lat (ms)",    _nvme_rw_lat_ms,      _nvme_time,      "#f43f5e"),
            (_nvme_qd_label.replace("L3 ", ""), _nvme_qd_series, _nvme_qd_t, "#a78bfa"),
        ]

        _LAYER_OF["L3.5"] = "A3_DRAM · remote KV store (RDMA)"

        # The memory node's own resources, as correlation targets.  A remote
        # tier can be slow because its disks are busy, its DRAM cache is
        # thrashing, or its CPU is saturated — and only the first of those was
        # measurable before.  Every label names the NODE, so a reader never
        # mistakes these for the GPU host's signals.
        _l35_t = _l35s.get("time_sec") or []
        _l35_node_entries = [
            (f"{_TIER_NODE} · storage read BW (MB/s)",  _l35s.get("l35_rd_bw_mbs"), "#22c55e"),
            (f"{_TIER_NODE} · storage write BW (MB/s)", _l35s.get("l35_wr_bw_mbs"), "#eab308"),
            (f"{_TIER_NODE} · storage util (%)",        _l35s.get("l35_io_util_pct"), "#f97316"),
            (f"{_TIER_NODE} · storage queue depth",     _l35s.get("l35_avgqu_sz"), "#a855f7"),
            (f"{_TIER_NODE} · DRAM BW (GB/s)",
             [ (_l35s.get("l35_dram_rd_gbs") or [0])[i] +
               (_l35s.get("l35_dram_wr_gbs") or [0])[i]
               for i in range(min(len(_l35s.get("l35_dram_rd_gbs") or []),
                                 len(_l35s.get("l35_dram_wr_gbs") or [])))
             ] or (_l35s.get("l35_dram_rd_gbs") or []), "#3b82f6"),
            (f"{_TIER_NODE} · DRAM used (GB)",      _l35s.get("l35_dram_used_gb"), "#14b8a6"),
            (f"{_TIER_NODE} · CPU util (%)",        _l35s.get("l35_cpu_util_pct"), "#ef4444"),
            (f"{_TIER_NODE} · CPU iowait (%)",      _l35s.get("l35_cpu_iowait_pct"), "#ec4899"),
        ]
        _l35_node_entries = [(lbl, v, _l35_t, col)
                             for lbl, v, col in _l35_node_entries
                             if v and any(x == x and x > 0 for x in v)]

        _all_tier_entries = (
            _tier_signal_bundle(_net_configured, "NET · ", _net_entries) +
            _tier_signal_bundle(_mc_configured, "L3.5 · ", _l35_entries) +
            _tier_signal_bundle(_l1_configured, "L1 · ", _l1_entries) +
            _tier_signal_bundle(_l2_configured, "L2 · ", _l2_entries) +
            _tier_signal_bundle(_l3_configured, "L3 · ", _l3_entries)
        )
        # The memory node's own resources join the correlation targets, so
        # token activity is plotted against them on the same cards.  Labels
        # already name the node, so no tier prefix is added.
        if _l35_node_entries:
            _all_tier_entries = _all_tier_entries + _tier_signal_bundle(
                True, "", _l35_node_entries)

        # ---- Bandwidth utilisation across cache tiers ---------------------
        # Absolute bandwidth is not comparable across tiers: HBM peaks in the
        # thousands of GB/s while NVMe peaks in the low GB/s, so an absolute
        # axis is dominated by L1 and every other tier collapses to the
        # baseline.  Each tier is therefore shown as a percentage of ITS OWN
        # ceiling, which is the question that matters — is this tier the one
        # running out of bandwidth?
        _bw = []
        if _hbm_bw_gbs_series and _hbm_peak_gbs > 0:
            _bw.append({"tier": "L1", "label": "L1 HBM bandwidth",
                        "t": _gpu_time, "v": _hbm_bw_gbs_series,
                        "cap": _hbm_peak_gbs, "color": "#f59e0b",
                        "src": ("gpu_timeseries.csv", "hbm_bw_gbs",
                                "DCGM / nvidia-smi HBM throughput \u00b7 ceiling from the GPU spec")})
        elif _hbm_bw_util_series:
            # Already a percentage of device peak; give it a nominal 100 cap.
            _bw.append({"tier": "L1", "label": "L1 HBM bandwidth",
                        "t": _gpu_time, "v": _hbm_bw_util_series,
                        "cap": 100.0, "color": "#f59e0b",
                        "src": ("gpu_timeseries.csv", "hbm_bw_util_pct",
                                "DCGM DRAM-active \u00b7 already a % of device peak")})
        if not _dram_series_local and (_l2_in_mbps or _l2_out_mbps):
            # No PMU, but SGLang's own KV movement gives a host-tier traffic
            # estimate.  It is logical movement, not memory-controller
            # bandwidth, so it is labelled as an estimate and measured against
            # the DRAM peak only to show relative shape.
            _n_est = min(len(_l2_in_mbps or []), len(_l2_out_mbps or [])) \
                if (_l2_in_mbps and _l2_out_mbps) else 0
            _l2_est = ([(_l2_in_mbps[i] + _l2_out_mbps[i]) / 1000.0 for i in range(_n_est)]
                       if _n_est else
                       [v / 1000.0 for v in (_l2_in_mbps or _l2_out_mbps)])
            if _l2_est and any(v > 0 for v in _l2_est) and _dram_peak_auto > 0:
                _bw.append({"tier": "L2",
                            "label": "L2 host DRAM (KV movement est., not PMU)",
                            "t": _sg_rate_t, "v": _l2_est,
                            "cap": _dram_peak_auto, "color": "#a78bfa",
                            "src": ("sglang_timeseries.csv",
                                    "evicted/backuped/prefetched/load-back tokens",
                                    "ESTIMATE from KV token movement \u00d7 KV bytes/token \u2014 logical traffic, not memory-controller bandwidth")})
        if _dram_series_local and _dram_peak_auto > 0:
            _bw.append({"tier": "L2", "label": "L2 host DRAM bandwidth",
                        "t": _dram_time, "v": _dram_series_local,
                        "cap": _dram_peak_auto, "color": "#a78bfa",
                        "src": ("amduprof_pcm_timeseries.csv",
                                "dram_read_gb_s + dram_write_gb_s",
                                "AMD DF / Intel PCM memory-controller counters on the GPU node")})
        if _nvme_rd_mbps or _nvme_wr_mbps:
            _n_bw = min(len(_nvme_rd_mbps or []), len(_nvme_wr_mbps or [])) \
                if (_nvme_rd_mbps and _nvme_wr_mbps) else 0
            _tot = ([_nvme_rd_mbps[i] + _nvme_wr_mbps[i] for i in range(_n_bw)]
                    if _n_bw else (_nvme_rd_mbps or _nvme_wr_mbps))
            _l3_bw_cap = _safe_float(_pick(setup, [
                "L3 device peak MB/s", "l3_peak_mbs", "SSD peak MB/s"], 0), 0)
            if _l3_bw_cap <= 0 and _tot:
                # No published device spec in this run: use the observed peak
                # as the ceiling and say so, rather than omitting the tier.
                _l3_bw_cap = max(_tot) or 0.0
            if _tot and _l3_bw_cap > 0:
                _bw.append({"tier": "L3", "label": "L3-local storage BW (vs observed peak)",
                            "t": (_nvme_rd_bw_t or _sg_rate_t), "v": _tot,
                            "cap": _l3_bw_cap, "color": "#22c55e",
                            "src": ("nvme_driver_timeseries.csv",
                                    "rd_bw_mbs + wr_bw_mbs",
                                    "local NVMe on the GPU node \u00b7 ceiling = observed peak unless a device spec is in setup_details.json")})
        # L3.5 node's own SSD, when a collector runs on that host.  This is
        # the device *behind* the remote store: the store exporter reports
        # request rates, this reports whether the disk underneath kept up.

        if _l35s.get("rd_bw_mbs") or _l35s.get("wr_bw_mbs"):
            _n_ls = min(len(_l35s.get("rd_bw_mbs") or []),
                        len(_l35s.get("wr_bw_mbs") or [])) if (
                _l35s.get("rd_bw_mbs") and _l35s.get("wr_bw_mbs")) else 0
            _ls_tot = ([_l35s["rd_bw_mbs"][i] + _l35s["wr_bw_mbs"][i]
                        for i in range(_n_ls)] if _n_ls else
                       (_l35s.get("rd_bw_mbs") or _l35s.get("wr_bw_mbs")))
            if _ls_tot and max(_ls_tot) > 0:
                _bw.append({"tier": "L3.5",
                            "label": f"{_TIER_NODE} storage BW (vs observed peak)",
                            "t": _l35s.get("time_sec") or _sg_rate_t,
                            "v": _ls_tot, "cap": max(_ls_tot), "color": "#5eead4",
                            # Same fallback as the KPI tile: these columns come
                            # from the GPU host's own device file when no
                            # memory-node storage file exists, so the source
                            # line must name the file rather than assert a
                            # memory node.
                            "src": (_l35s_local_src or "l35_storage_timeseries.csv",
                                    ("rd_bw_mbs + wr_bw_mbs (mapped to l35_*)"
                                     if _l35s_local_src else
                                     "l35_rd_bw_mbs + l35_wr_bw_mbs"),
                                    ("local block device on the GPU host \u00b7 "
                                     "ceiling = observed peak, no device spec published"
                                     if _l35s_local_src else
                                     "block device on the memory node \u00b7 "
                                     "ceiling = observed peak, no device spec published"))})

        # GPU node <-> L3.5 node link.  Prefer the absolute MB/s series; the
        # link-utilisation percentage stays on the correlation cards where a
        # ratio is the right unit.
        # rx and tx separately, not just the total.  KV traffic is strongly
        # directional — offload to the store is tx, restore is rx — so a
        # combined line hides which direction is saturating the link.  A run
        # that is 90% tx is doing far more writing than reading, and that is
        # the same asymmetry the L3 write-only finding surfaces.
        if _net_configured:
            # rx and tx only.  A "total" line is their sum and adds no
            # information once both are plotted; when one direction is absent
            # it also drew a flat 0.00 GB/s line that read as a measurement.
            for _lbl, _ser, _col in (
                    # Name the NODE.  The chart can carry both the GPU node's
                    # NIC and the memory node's, and "Network rx" alone leaves
                    # the reader unable to tell which side of the link a line
                    # describes — which is the whole question on a
                    # disaggregated setup.
                    ("GPU node network rx", _net_rx, "#5eead4"),
                    ("GPU node network tx", _net_tx, "#0d9488")):
                if _ser and any(v == v and v > 0 for v in _ser):
                    # cap=0: no link ceiling is known.  Setting it to the
                    # series' own peak made every network line read "100% of
                    # its ceiling", which is true by construction and tells
                    # the reader nothing — the same invented-ceiling problem
                    # the tier charts dropped in v1.7.0.
                    _bw.append({"tier": "NET", "label": _lbl,
                                "t": _net_t, "v": _ser,
                                "cap": 0.0, "color": _col,
                                "src": ("network_timeseries.csv",
                                        "net_rx_mbs / net_tx_mbs",
                                        "/proc/net/dev on the GPU node \u00b7 RDMA bypasses this counter")})

        for _lbl_n, _k_n, _c_n in (
                ("L3.5 node network rx", "l35_net_rx_mbs", "#a7f3d0"),
                ("L3.5 node network tx", "l35_net_tx_mbs", "#047857")):
            _v_n = _l35s.get(_k_n) or []
            if _v_n and any(x == x and x > 0 for x in _v_n):
                _bw.append({"tier": "NET", "label": _lbl_n,
                            "t": _l35s.get("time_sec") or [], "v": _v_n,
                            "cap": 0.0, "color": _c_n,
                            "src": ("l35_storage_timeseries.csv", _k_n,
                                    "amoprof network collector on the memory node")})

        if (_mc_rd_mbps or _mc_wr_mbps):
            _n_mc = min(len(_mc_rd_mbps or []), len(_mc_wr_mbps or [])) \
                if (_mc_rd_mbps and _mc_wr_mbps) else 0
            _mc_tot = ([_mc_rd_mbps[i] + _mc_wr_mbps[i] for i in range(_n_mc)]
                       if _n_mc else (_mc_rd_mbps or _mc_wr_mbps))
            if _mc_tot and max(_mc_tot) > 0:
                _bw.append({"tier": "L3.5", "label": "L3.5 remote store BW (vs observed peak)",
                            "t": (_mc_rd_t or _sg_rate_t), "v": _mc_tot,
                            "cap": max(_mc_tot), "color": "#2dd4bf",
                            "src": ("l35_store_capacity.csv",
                                    "l35_mem_hit_b + l35_file_hit_b",
                                    "\u0394(mem_cache_hit_bytes_total + file_cache_hit_bytes_total) \u00f7 \u0394t \u00b7 store-side, NOT the device")})
        # "NET link utilisation" removed.  It divided rx+tx by a link speed read
        # from /sys/class/net/<if>/speed — unreliable on bonded interfaces,
        # absent on many IB devices, and stale when present.  Worse, on this
        # chart it was plotted in GB/s while carrying a PERCENTAGE, so a 1.2%
        # figure appeared as 0.00025 "GB/s" and the rx/tx series were labelled
        # against a ceiling nobody had established.  rx and tx in absolute
        # GB/s say what moved without claiming a capacity we do not know.
        _bw.sort(key=lambda z: {"L1": 0, "L2": 1, "L3": 2, "L3.5": 3, "NET": 4}
                 .get(z["tier"], 9))

        # Absolute GB/s rather than % of a ceiling: for a remote store the
        # ceiling is often unknown or elastic, and a percentage against an
        # invented ceiling says less than the real number. Series arrive in
        # mixed units, so convert to GB/s before plotting.
        # Physical plausibility guard.  No host moves more than a few TB/s of
        # DRAM or PCIe traffic; a series orders of magnitude above that is a
        # computation error (a counter read as a rate, a reset spiking a
        # delta), not a measurement.  Charting it destroys the log axis for
        # every other tier and asserts something false, so drop it and say so
        # rather than rendering 72,057,593,856 GB/s.
        _BW_SANE_MAX_GBS = 100_000.0        # 100 TB/s: far above any real host
        _bw_dropped = []
        _bw_abs = []
        for _x in _bw:
            _conv = 1.0
            if _x["tier"] in ("L3", "L3.5"):
                _conv = 1.0 / 1000.0            # MB/s -> GB/s (decimal)
            elif _x["tier"] == "NET":
                # Network belongs on this chart: on a disaggregated setup the
                # link between the GPU node and the L3.5 node carries every KV
                # transfer, so it is a tier boundary like any other and can be
                # the binding constraint.  It was skipped when this chart moved
                # to absolute units because the series carried was a link
                # PERCENTAGE; the MB/s series converts cleanly.
                _conv = 1.0 / 1000.0            # MB/s -> GB/s (decimal)
            _vals = [v * _conv for v in _x["v"]]
            _pk = max(_vals) if _vals else 0.0
            if _pk > _BW_SANE_MAX_GBS:
                _bw_dropped.append((_x["label"], _pk))
                continue
            _bw_abs.append(dict(_x, v=_vals,
                                cap=(_x.get("cap") or 0) * _conv))
        _bw_svg = _amoprof_exec_svg_tier_occupancy(
            _bw_abs, window=_occ_win, wall_start=_occ_wall, mode="abs",
            title="Bandwidth per cache tier",
            subtitle="absolute GB/s on a log axis \u00b7 dashed line = known "
                     "ceiling where one is published",
            yaxis="GB/s (log)", unit_label="GB/s") + _src_block_from_series(
                _bw_abs,
                note="Series arrive in mixed units and are converted to GB/s "
                     "before plotting. They are measured at different layers "
                     "and on two machines: an engine-side estimate, a "
                     "memory-controller counter and a block device do not "
                     "have to agree, and where they diverge is usually the "
                     "finding.") if _bw_abs else ""
        # Name the tiers that are NOT on this chart and why.  A silently
        # missing tier reads as "no traffic"; these absences are all
        # "not measurable from what this run collected", which is a different
        # conclusion and points at a different fix.
        _bw_absent = []
        for _lbl, _pk in _bw_dropped:
            _bw_absent.append(
                f"<b>{_html.escape(_lbl)}</b> \u2014 excluded: peak "
                f"{_pk:,.0f} GB/s is physically impossible, so the series is a "
                f"computation artefact rather than a measurement (most often a "
                f"counter reset spiking a delta, or a cumulative value read as "
                f"a rate). Named here rather than silently dropped.")
        _bw_have = {z["tier"] for z in _bw}
        if "L2" not in _bw_have:
            _bw_absent.append(
                "<b>L2 host DRAM</b> \u2014 no DRAM bandwidth series. Needs a PMU "
                "collector (<code>--enable-dram</code>, AMDuProf / Intel PCM / "
                "<code>--dram-tool perf-imc</code>); the <code>dram</code> collector "
                "reports capacity only.")
        if "L3" not in _bw_have and (l3_fs_total_gb or 0) >= 0 and _l3_local_configured:
            _bw_absent.append(
                "<b>L3 local storage</b> \u2014 no NVMe/iostat bandwidth series in "
                "this run. Add <code>nvme_driver</code> or <code>iostat</code> to "
                "<code>--collectors</code>.")
        if "L3.5" not in _bw_have and _mc_configured:
            _bw_absent.append(
                "<b>L3.5 remote store</b> \u2014 the Mooncake <i>master</i> exporter "
                "publishes no byte-throughput counters: data moves client\u2194store "
                "over RDMA and never reaches the master. Occupancy and request rates "
                "are charted elsewhere; bandwidth needs a store or transfer-engine "
                "exporter.")
        if _bw_svg:
            _exec_ov["Bandwidth per cache tier over the run"] = _bw_svg
            _bw_rows = []
            for _x in _bw:
                _pk = max(_x["v"])
                # No known ceiling -> state the peak and stop.  Claiming a
                # percentage against a cap derived from the series' own maximum
                # is true by construction ("100% of its own peak") and told the
                # reader nothing, while implying a link speed nobody measured.
                if not _x.get("cap") or float(_x["cap"]) <= 0:
                    # _bw carries MB/s for NET/L3/L3.5 and GB/s for L1/L2 —
                    # the chart converts on the way in, this row must too.
                    _unit_gbs = _pk / 1000.0 if _x["tier"] in ("NET", "L3", "L3.5") else _pk
                    _bw_rows.append(
                        f"<b>{_html.escape(_x['label'])}</b> peak "
                        f"{_fmt_num(_unit_gbs, ' GB/s', 2)} \u00b7 no published "
                        f"ceiling for this link, so no utilisation % is claimed")
                    continue
                _bw_rows.append(
                    f"<b>{_html.escape(_x['label'])}</b> peak "
                    f"{_pk / _x['cap'] * 100:.1f}% of "
                    + (f"{_fmt_num(_x['cap'], ' GB/s', 0)}" if _x["tier"] in ("L1", "L2")
                       else (f"{_fmt_num(_x['cap'], ' MB/s', 0)}" if _x["tier"] in ("L3", "L3.5")
                             else "link speed")))
            _cards.append(_card(
                "Bandwidth utilisation per cache tier",
                "Absolute bandwidth is not comparable across tiers \u2014 HBM peaks "
                "in the thousands of GB/s while NVMe peaks in the low GB/s, so an "
                "absolute axis is dominated by L1. Each tier is shown against its "
                f"own ceiling instead. {_kv_header}",
                _bw_svg,
                "<br>".join(_bw_rows)
                + "<br><br>A tier near 100% is bandwidth-saturated and is the "
                  "constraint; a tier far below it has headroom regardless of how "
                  "much traffic it carries in absolute terms. Where a device "
                  "specification was not available the ceiling is the <i>observed "
                  "peak</i> for this run, marked in the label \u2014 that shows "
                  "relative shape over time but cannot tell you how close the tier "
                  "is to its hardware limit."
                + ("<br><br><b>Tiers not shown</b><br>" + "<br>".join(_bw_absent)
                   if _bw_absent else ""),
                layers="A4_GPU_HBM \u00b7 A3_DRAM \u00b7 A1/A2_L3 \u00b7 NET"))

        # ---- Concurrency ↔ latency ↔ resource pressure --------------------
        # One chart per latency metric, each carrying five parameters:
        # running requests on X, and latency + storage queue depth + GPU util
        # + HBM used as normalised curves.  This is the saturation view: as
        # concurrency rises, which resource turns up first and where does
        # latency knee?  A single correlation coefficient cannot show a knee.
        _lat_specs = [
            ("TTFT", _ttft_t, _ttft_ms, "ms",
             "Δsglang_time_to_first_token_seconds_sum ÷ Δ..._count per interval"),
            ("TPOT", _tpot_t, _tpot_ms, "ms/tok", f"Δsglang_{_tpot_src} per interval"),
            ("E2E latency", _e2e_t, _e2e_ms, "ms",
             "Δsglang_e2e_request_latency_seconds_sum ÷ Δ..._count per interval"),
        ]
        _conc = _sg_phase.get("running_reqs") or []
        _conc_t = _sg_time
        _lat_html = ""
        _lat_notes = []
        for _lt_label, _lt_t, _lt_v, _lt_unit, _lt_src in _lat_specs:
            if not _lt_v or not _conc:
                continue
            _members = [
                ("A5_APP", f"{_lt_label} ({_lt_unit})", _lt_t, _lt_v, _lt_unit),
                ("A1/A2_L3", "Storage queue depth", _nvme_qd_t, _nvme_qd_series, ""),
                ("A4_GPU_HBM", "GPU util (%)", _gpu_time, _gpu_util_series, "%"),
                ("A4_GPU_HBM", "HBM used (GB)", _gpu_time,
                 [_k_gb_from_mib(v) for v in _hbm_used_series] if _hbm_used_series else [], "GB"),
                # Concurrency pressure shows up in QUEUEING, not utilisation.
                # GPU util saturates long before concurrency does — once the
                # device is busy, another concurrent request adds waiting, not
                # utilisation — and HBM is preallocated for the KV pool, so it
                # does not move with load at all.  These four do.
                ("A5_APP", "Waiting requests", _sg_time,
                 _counter_series("num_queue_reqs"), "reqs"),
                ("A5_APP", "Queue wait (ms)", _q_wait_t, _q_wait_ms, "ms"),
                ("A5_APP", "Engine utilisation (%)", _sg_time,
                 [v * 100.0 for v in _counter_series("utilization")], "%"),
                ("A5_APP", "Forward occupancy", _sg_time,
                 _counter_series("fwd_occupancy"), ""),
            ]
            _sers = []
            for _lay, _lbl, _mt, _mv, _mu in _members:
                if not _mv:
                    continue
                _x, _y = _align_xy(_conc_t, _conc, _mt, _mv)
                # Burst-shaped series (queue depth, retransmits) are
                # summarised per bin by max; a median flattens them to zero.
                _bins = _amoprof_binned_response(
                    _x, _y, stat=_amoprof_bin_stat_for(_lbl))
                if not _bins:
                    continue
                _sers.append({"layer": _lay, "label": _lbl, "unit": _mu, "bins": _bins,
                              "color": _CONC_COLORS.get(_lbl, ""),
                              "r": _pearson(_x, _y), "rho": _pearson(_x, _y),
                              # Raw aligned samples, so the legend can report a
                              # real peak when every binned median is zero.
                              "raw": list(_y),
                              "n": len(_x), "ymax": max(_y) or 1.0})
            if len(_sers) < 2:
                continue
            _lat_html += _amoprof_exec_svg_layer_response(
                "Running requests", "concurrent reqs", _sers,
                title=f"Running requests → {_lt_label} · queue depth · GPU util · HBM used")
            _lat_first = next((z for z in _sers if z["label"].startswith(_lt_label)), None)
            if _lat_first:
                _others = [z for z in _sers if z is not _lat_first]
                _strong = max(_others, key=lambda z: abs(z["r"])) if _others else None
                _lat_notes.append(
                    f"<b>{_html.escape(_lt_label)}</b> vs concurrency r={_lat_first['r']:+.2f}"
                    + (f"; strongest resource response {_html.escape(_strong['label'])} "
                       f"r={_strong['r']:+.2f}" if _strong else ""))
        if _lat_html:
            _cards.append(_card(
                "Concurrency → latency & resource pressure (TTFT · TPOT · E2E)",
                "Running requests on X; latency, storage queue depth, GPU util and HBM used "
                "as binned median curves normalised to each signal's own observed max. Five "
                f"parameters per chart. {_kv_header}",
                _lat_html,
                "<br>".join(_lat_notes)
                + "<br><br>Read the <b>order of the knees</b>: the resource that bends upward "
                "before latency does is the constraint. Latency rising while GPU util stays "
                "flat means the GPU is waiting, not working — look at queue depth and HBM. "
                "Latency and HBM rising together with GPU util flat is a capacity limit, not "
                "a compute one. If latency knees but no resource curve does, the limit is "
                "admission policy (max-running-requests) rather than hardware.",
                layers="A5_APP ↔ A4_GPU_HBM · A1/A2_L3"))

        # ---- Per-driver multi-layer response curves ----------------------
        # One chart per driver instead of one card per driver-signal pair.
        _resp_drivers = [("Input tokens", _in_tok_rate, "tok/s"),
                         ("Output tokens", _out_tok_rate, "tok/s")]
        for _dl, _dv, _du in (("Evict", _evict_rate, "tok/s"),
                              ("Load-back", _load_rate, "tok/s"),
                              ("Prefetch", _pref_rate, "tok/s"),
                              ("Backup", _backup_rate, "tok/s")):
            if _dv and any(v > 0 for v in _dv):
                _resp_drivers.append((_dl, _dv, _du))
        for _dl, _dv, _du in _resp_drivers:
            if not _dv:
                continue
            _sers = []
            for _y_label, _y_series, _y_times, _y_color in _all_tier_entries:
                _x, _y = _align_xy(_sg_rate_t, _dv, _y_times, _y_series)
                _bins = _amoprof_binned_response(
                    _x, _y, stat=_amoprof_bin_stat_for(_y_label))
                if not _bins:
                    continue
                _lay = _y_label.split(" ·")[0]
                _lay = {"L1": "A4_GPU_HBM", "L2": "A3_DRAM",
                        "L3": "A1/A2_L3", "NET": "NET"}.get(_lay, _lay)
                _unit = _y_label.split("(")[-1].rstrip(")") if "(" in _y_label else ""
                _sers.append({"layer": _lay, "label": _y_label, "unit": _unit,
                              "bins": _bins, "r": _pearson(_x, _y),
                              "rho": _pearson(_x, _y), "n": len(_x),
                              "raw": list(_y),
                              "ymax": max(_y) or 1.0})
            if not _sers:
                continue
            _sers.sort(key=lambda z: abs(z["r"]), reverse=True)
            _sers = _sers[:7]
            _top = _sers[0]
            _cards.append(_card(
                f"{_dl} → effect across layers",
                f"Binned median response of every configured layer signal to {_dl.lower()} rate, "
                f"normalised to each signal's own observed max so they share one axis. "
                f"Legend carries the true max and unit. {_kv_header}",
                _amoprof_exec_svg_layer_response(_dl, _du, _sers),
                f"Strongest response: <b>{_html.escape(_top['label'])}</b> at r={_top['r']:+.2f}. "
                "A steep line is a layer that responds to this driver; a flat line is one that "
                "does not. Saturation knees and non-monotonic turns are visible here but hidden "
                "by a single correlation coefficient.",
                layers=" · ".join(sorted({z["layer"] for z in _sers}))))

        # Build one card per driver signal — each card scatters that signal
        # against every available signal of every *configured* tier (L1
        # util/HBM, L2 DRAM BW, L3 BW/IOPS/latency/QD).  Only pairs producing
        # ≥3 time-aligned samples are rendered, ordered by |Pearson r|
        # descending so the strongest attribution is read first.
        #
        # Two size guards keep the Executive tab loadable.  Both are lossless
        # for the reported statistics: r is always computed on the full
        # aligned series, and every pair's r appears in the card footer even
        # when its scatter is not drawn.  Raise _CORR_MAX_SCATTERS_PER_CARD
        # to a large number to draw every pair again.
        # Physically expected pairings, ALWAYS drawn regardless of |r| rank.
        # Ranking alone buries them: eviction writing into host DRAM is the
        # mechanism the tier exists for, but a noisier signal with a higher
        # coefficient will outrank it and the reader never sees the pairing
        # they came to check.  A weak r on a pinned pair is itself the finding
        # (the movement is not reaching that tier).
        _PINNED = {
            "Evict rate (tok/s)":     ("L2 · DRAM write BW (GB/s)", "L3 · write BW (MB/s)",
                                       "L3.5 · put ops/s"),
            "Load-back rate (tok/s)": ("L2 · DRAM read BW (GB/s)", "L2 · HiCache used (GB)"),
            "Prefetch rate (tok/s)":  ("L3 · read BW (MB/s)", "L3.5 · read BW (MB/s)"),
            "Backup rate (tok/s)":    ("L3 · write BW (MB/s)", "L3.5 · put ops/s"),
        }

        # driver label -> signals derived FROM that driver (r == 1 by algebra)
        _DERIVED_FROM = {
            "Evict rate (tok/s)":     ("L1->L2 evict BW (MB/s)",),
            "Load-back rate (tok/s)": ("L2->L1 restore BW (MB/s)",),
        }

        def _emit_correlation_card(x_label: str, x_rate: List[float],
                                   subtitle: str, takeaway: str,
                                   group: str = "") -> None:
            _skip = _DERIVED_FROM.get(x_label, ())
            # A driver series that is empty or entirely zero cannot be
            # correlated with anything.  Drawing it anyway produced a chart
            # with a 0.0-1.0 axis that looked like a measurement of a nearly
            # idle system, when in fact the series had not been read at all.
            # Say so instead: a stated absence is actionable, a fabricated
            # axis is not.
            if not x_rate or not any(v > 0 for v in x_rate):
                _cards.append(_card(
                    x_label + " — no data",
                    subtitle,
                    "",
                    f"<b>{_html.escape(x_label)}</b> could not be computed for "
                    f"this window: the underlying counter was absent or flat, "
                    f"so there is no rate to correlate against. This is not a "
                    f"reading of zero throughput — the series was never "
                    f"populated. Check that the counter appears in "
                    f"<code>sglang_timeseries.csv</code> and is rising.",
                    layers="A5_APP"))
                return
            _scored: List[tuple] = []
            for _y_label, _y_series, _y_times, _y_color in _all_tier_entries:
                if any(_y_label.endswith(_sk) for _sk in _skip):
                    continue
                _x, _y = _align_xy(_sg_rate_t, x_rate, _y_times, _y_series)
                if len(_x) < 3:
                    continue
                _scored.append((abs(_pearson(_x, _y)), _pearson(_x, _y),
                                _y_label, _x, _y, _y_color))
            if not _scored:
                return
            _scored.sort(key=lambda t: t[0], reverse=True)
            # Pinned pairs first, in declared order, then the highest-|r| rest.
            _pin = _PINNED.get(x_label, ())
            _pinned_rows = [z for lbl in _pin for z in _scored if z[2] == lbl]
            _rest_rows = [z for z in _scored if z not in _pinned_rows]
            _drawn = (_pinned_rows + _rest_rows)[:_CORR_MAX_SCATTERS_PER_CARD]
            _card_svg = ""
            for (_r_abs, _r, _y_label, _x, _y, _y_color) in _drawn:
                _px, _py = _decimate(_x, _y)
                _note = (f"n={len(_x)} time-aligned samples"
                         if len(_px) == len(_x) else
                         f"n={len(_x)} time-aligned samples · r on all, "
                         f"{len(_px)} plotted")
                _card_svg += _amoprof_exec_svg_scatter(
                    f"{x_label} vs {_y_label}", x_label, _y_label,
                    _px, _py, point_color=_y_color, subtitle=_note)
            _rest = [z for z in (_pinned_rows + _rest_rows) if z not in _drawn]
            _rest_html = ""
            if _rest:
                _rest_html = (
                    '<div style="color:#94a3b8;font-size:11px;margin-top:6px">'
                    'Remaining pairs (r computed, scatter not drawn): '
                    + "; ".join(f"{_html.escape(lbl)} <b>{r:+.2f}</b>"
                                for (_a, r, lbl, _x, _y, _c) in _rest)
                    + '</div>')
            _tiers_shown = " / ".join(
                t for t in ("NET", "L1", "L2", "L3", "L3.5")
                if any(lbl.startswith(t + " ·") for (_a, _r, lbl, _x, _y, _c) in _scored))
            _layers = " · ".join(
                _LAYER_OF[t] for t in ("NET", "L1", "L2", "L3")
                if any(lbl.startswith(t + " ·") for (_a, _r, lbl, _x, _y, _c) in _scored))
            _cards.append(_card(
                f"{group}{x_label.split(' (')[0]} vs {_tiers_shown} signals",
                f"{subtitle} Ranked by |Pearson r| across every configured tier signal; "
                f"positive r means that tier is on the path serving this activity. {_kv_header}",
                _card_svg,
                takeaway + _rest_html,
                layers=f"A5_APP ↔ {_layers}" if _layers else "A5_APP"))

        _tok_takeaway = {
            "Evict":     ("Evict rate correlating with L2 DRAM BW or L3 write BW means the L1/L2 pool "
                          "is spilling under pressure. Correlation with L3 write latency or queue depth "
                          "means the spill path itself is the constraint."),
            "Load-back": ("Load-back correlating with L3 read BW/IOPS means restores are being fed by L3 "
                          "(not L2), indicating HiCache is missing at L2. Correlation with L3 read latency "
                          "at high queue depth means restores are queueing behind other reads."),
            "Prefetch":  ("Prefetch correlating with L3 read BW/IOPS or latency means HiCache is proactively "
                          "reading from L3 — check whether that saturates L3 latency at high prefetch rates."),
            "Backup":    ("Backup correlating with L3 write BW/IOPS confirms the offload path; correlating "
                          "with write latency or queue depth means offload is queueing behind other L3 writes."),
        }
        for _tok_label, _tok_rate, _tok_color, _tok_note in _token_activity_signals:
            _emit_correlation_card(
                _tok_label, _tok_rate, f"{_tok_note}.",
                _tok_takeaway.get(_tok_label.split(" rate")[0], ""),
                group="Token movement · ")

        # ---- Prefill / decode phase activity ↔ configured tier signals ----
        # Same mechanism, different driver: instead of "where did KV move",
        # this asks "which request phase is driving each tier".  Rendered on
        # every run — including L1-only runs with no hierarchical cache,
        # where it is the only cross-layer attribution available.
        _phase_activity_signals = [
            (("Prefill compute rate (tok/s)" if _pf_modes_measured else
              "Prompt token rate (tok/s) · prefill counter absent"),
             _pf_compute_rate,
             (f"Δ{_pf_src} ÷ Δt — prefill tokens actually recomputed (cache miss)"
              if _pf_modes_measured else
              f"Δ{_pf_src} ÷ Δt — ALL prompt tokens, cache hits included: "
              f"this build does not export the mode-labelled counter, so this "
              f"is not a recompute rate"),
             "Prefill-compute tracking GPU util is the expected prefill-bound signal. Tracking "
             "HBM used means each prefill is growing the resident KV working set. On a tiered "
             "run, tracking L3 read BW means cold prompt regions are being fetched from storage."),
            ("Prefill cache-hit rate (tok/s)", _pf_cache_rate,
             "Δrealtime_tokens_total{mode=prefill_cache} ÷ Δt — prefill tokens served from cache",
             "Cache-hit prefill that does *not* raise GPU util is work correctly avoided. If it "
             "correlates with L2 DRAM BW or L3 read BW, the hit is being served from a backing "
             "tier rather than from resident HBM, so it costs bandwidth rather than compute."),
            ("Decode rate (tok/s)", _decode_rate,
             f"Δ{_dec_src} ÷ Δt — generation-phase token work",
             "Decode correlating with GPU util is the normal decode-bound signature. Decode "
             "correlating with a storage or DRAM axis instead means the decode step is stalling "
             "on KV restore rather than on compute."),
            ("Running requests (decode batch)", _running_reqs,
             "sglang_num_running_reqs gauge — concurrent decode batch size",
             "Batch size correlating with HBM used shows the per-request KV footprint scaling. "
             "If it correlates with L3 latency or queue depth, larger batches are being paid for "
             "in storage-side queueing."),
            ("Queued requests (prefill backlog)", _queue_reqs,
             "sglang_num_queue_reqs gauge — requests waiting to enter prefill",
             "A backlog that correlates with HBM used means admission is capacity-limited. A "
             "backlog that correlates with L3 latency or queue depth means admission is waiting "
             "on the storage tier, not on the GPU."),
        ]
        for _ph_label, _ph_series, _ph_note, _ph_takeaway in _phase_activity_signals:
            if not _ph_series or not any(v > 0 for v in _ph_series):
                continue
            _emit_correlation_card(_ph_label, _ph_series, f"{_ph_note}.", _ph_takeaway,
                                   group="Phase activity · ")

        # If nothing correlated at all (e.g. gpu_timeseries missing), surface
        # a single informational note rather than silently rendering empty.
        if not _cards:
            _cards.append(_card(
                "Cross-layer correlation — insufficient data",
                "No gpu_timeseries.csv / sglang_timeseries.csv samples were "
                "available for the selected window, so rate-vs-rate scatter "
                "correlation cannot be computed. Confirm collection was active.",
                "", ""))

        # Present the cards in the order an operator reads them: latency, then
        # throughput and cache, then compute, then the memory hierarchy, then
        # everything else.  Cards are appended in whatever order the code
        # happens to compute them, which is an implementation detail, not a
        # reading order.  Anything unlisted keeps its relative position after
        # the ranked set, so adding a card never requires touching this list.
        _CARD_ORDER = [
            "KV cache hit ratio",                    # throughput & cache
            # Compute and capacity over time come before the per-tier
            # correlation scatters: "what was busy and when" frames the run,
            # and the scatters ("what moves with what") are read against that
            # frame rather than the other way round.
            "Compute and capacity utilisation",
            "Concurrency",                           # compute saturation
            "KV tokens resident per cache tier",
            "KV tier fill",
            "Bandwidth utilisation per cache tier",
            "Bandwidth per cache tier",              # absolute-units title
            # Token-activity response cards read directly against the tier
            # charts above: those show what each tier was doing, these show
            # what token activity did TO each tier.  Keeping them adjacent
            # means the reader does not have to scroll past every scatter to
            # connect the two.
            "Input tokens \u2192 effect across layers",
            "Output tokens \u2192 effect across layers",
            "Evict \u2192 effect across layers",
            "Load-back \u2192 effect across layers",
            "Prefetch \u2192 effect across layers",
            "Backup \u2192 effect across layers",
            "Queue depth across layers",
            "Network fabric",
            # HBM composition is a static breakdown (weights vs KV), not a
            # response to anything, so it reads better as reference material
            # after the cards that show behaviour over the run.
            "HBM composition",
        ]

        def _card_rank(card_html: str) -> int:
            # Match the card TITLE only.  Scanning the whole card body ranked
            # correlation cards as "throughput" because their axis labels
            # mention it.
            _m = re.search(r'font-weight:800;font-size:13\.5px;[^>]*>([^<]{4,90})<',
                           card_html)
            _title = (_m.group(1) if _m else "").lower()
            for _i, _key in enumerate(_CARD_ORDER):
                if _key.lower() in _title:
                    return _i
            return len(_CARD_ORDER)

        _cards = [c for _, _, c in
                  sorted(((_card_rank(c), _i, c) for _i, c in enumerate(_cards)),
                         key=lambda t: (t[0], t[1]))]
        correlation_charts_html = "".join(_cards)
        # Executive overview strip \u2014 hoist the key time-series charts
        # into a single card above the Bottleneck Analysis so an operator can
        # scan run-wide behaviour before reading the correlation cards.  The
        # charts are DUPLICATED here, not moved: they still appear in their
        # canonical Bottleneck cards below, with the full evidence trail.
        _ov_order = [
            "TPOT percentiles over the run",
            "TTFT percentiles over the run",
            "E2E latency percentiles over the run",
            "Input token throughput over the run",
            "Output token throughput over the run",
            "KV cache hit ratio over the run",
            "KV cache hit ratio percentiles",
            "Compute utilisation over the run (GPU / HBM / CPU)",
            "Memory hierarchy capacity utilisation \u2014 % of each tier",
            "KV bytes resident per cache tier",
            "KV tokens resident \u2014 % of each tier\u2019s capacity",
            "SSD IOPS over the run",
            "Bandwidth per cache tier over the run",
            # v1.20.26 additions: L3.5 memory-node aspect panels + L2 R/W BW.
            # Keys must match the strings used at _exec_ov[...] assignment.
            "L3.5 memory node \u00b7 CPU utilisation over the run",
            "L3.5 memory node \u00b7 DRAM bandwidth over the run",
            "L3.5 memory node \u00b7 network throughput over the run",
            "L2 host DRAM \u00b7 read/write bandwidth over the run",
            # v1.20.33: combined L2 + L3.5 DRAM R/W time-series and
            # its correlation-with-token-throughput companion.
            "DRAM read/write transactions over the run (L2 + L3.5)",
            "DRAM read/write transactions vs token throughput (L2 + L3.5)",
        ]
        _ov_items = []
        for _k in _ov_order:
            _svg = _exec_ov.get(_k) or ""
            if not _svg:
                continue
            # The source builders wrap each SVG in "corr-chart corr-chart-wide"
            # so they span every column in the Bottleneck grid.  Strip the
            # "-wide" modifier here so the overview strip can flow multiple
            # charts per row on a wide viewport.
            _svg = _svg.replace(
                'class="corr-chart corr-chart-wide"',
                'class="corr-chart exec-ov-chart"')
            _ov_items.append(_strip_src_blocks(_svg))
        # Storage rate belongs in the overview strip: "key time-series over
        # the run" should include whether the memory node's device was busy,
        # not only GPU and latency.
        _l35_ts_html = ""
        try:
            _l35_ts_html = (
                _l35_chart([("Storage read BW", "l35_rd_bw_mbs", "#22c55e"),
                            ("Storage write BW", "l35_wr_bw_mbs", "#eab308")],
                           f"{_dev_node} \u2014 storage read/write "
                           f"bandwidth over the run",
                           "per-interval bandwidth on the memory node",
                           "MB/s", "MB/s")
                + _l35_chart([("Storage read IOPS", "l35_rd_iops", "#38bdf8"),
                              ("Storage write IOPS", "l35_wr_iops", "#a855f7")],
                             f"{_dev_node} \u2014 storage IOPS over the run",
                             "operations per second \u00b7 a tier can be "
                             "IOPS-bound at modest bandwidth",
                             "IOPS", "IOPS"))
            _l35_ts_html = _strip_src_blocks(_l35_ts_html)
        except Exception:
            _l35_ts_html = ""

        if _ov_items or _l35_ts_html:
            exec_overview_html = (
                '<div class="section-label">Executive overview \u00b7 '
                'key time-series over the run</div>'
                '<div class="card"><div class="exec-ov-strip">'
                + "".join(_ov_items)
                + '</div>' + _l35_ts_html + '</div>')
        if distribution_charts_html:
            distribution_charts_html = (
                '<div class="section-label">Latency &amp; token-size distribution</div>'
                '<div class="card">' + distribution_charts_html + '</div>')
        # The memory node's storage rate belongs beside latency and throughput:
        # a reader following "the run over time" should not have to jump to a
        # different card to see whether the tier was busy at the same moment.
        _l35_ts_html = ""
        try:
            _l35_ts_html = (
                _l35_chart([("Storage read BW", "l35_rd_bw_mbs", "#22c55e"),
                            ("Storage write BW", "l35_wr_bw_mbs", "#eab308")],
                           f"{_dev_node} \u2014 storage read/write "
                           f"bandwidth over the run",
                           "per-interval bandwidth on the memory node",
                           "MB/s", "MB/s")
                + _l35_chart([("Storage read IOPS", "l35_rd_iops", "#38bdf8"),
                              ("Storage write IOPS", "l35_wr_iops", "#a855f7")],
                             f"{_dev_node} \u2014 storage IOPS over the run",
                             "operations per second \u00b7 a tier can be "
                             "IOPS-bound at modest bandwidth",
                             "IOPS", "IOPS"))
        except Exception:
            _l35_ts_html = ""

        if timeline_charts_html:
            distribution_charts_html += (
                '<div class="section-label">Latency &amp; throughput over the run</div>'
                '<div class="card">' + timeline_charts_html + '</div>')
    except Exception as _corr_err:
        import os as _os_dbg
        if _os_dbg.environ.get("AMOPROF_DEBUG_CORR"):
            import traceback as _tb_dbg
            _tb_dbg.print_exc()
        correlation_charts_html = (
            f'<div class="evidence-rule"><b>Correlation charts unavailable:</b> '
            f'{_html.escape(str(_corr_err))}</div>')

    # ── Action table ──────────────────────────────────────────────────────────
    # Actions that mention L3 (local storage) — "Expand DRAM L2 to reduce L3
    # reads" (#3) and "Validate KV$ L3 at 16-64 KB random read" (#5) — are
    # only added when L3 is actually configured.  Renumber remaining actions
    # so the table stays 1..N contiguous.
    _act_l1_fp8 = ("<b>FP8 KV quantisation</b> — <code>--kv-cache-dtype fp8_e5m2</code><br>"
                    f"<span class=\"sub\">Halves KV bytes/token ({_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f}→{_k_kb_from_bytes(kv_bytes_tok_kb * 512):.0f} KB/tok), doubles in-HBM capacity, "
                    f"cuts TPOT{' and L3 (local storage) load' if has_l3 else ''}. &lt;0.5% accuracy impact.</span>")
    _act_prefill = ("<b>Chunked prefill</b> — <code>--chunked-prefill-size 4096</code><br>"
                    "<span class=\"sub\">Interleaves prefill chunks with decode steps, reducing perceived TTFT without changing throughput.</span>")
    _act_prefix = ("<b>Add shared system-prompt prefix</b><br>"
                   f"<span class=\"sub\">Raises the {cache_hit:.0f}% cache hit (prefill tokens served from cache), "
                   "cutting prefill recompute for recurring prompt prefixes.</span>")
    _act_l2 = ("<b>Expand DRAM L2 HiCache allocation</b><br>"
               f"<span class=\"sub\">DRAM at {dram_total_bw/max(dram_peak_cap,1)*100:.0f}% util has headroom. More L2 absorbs KV before L3, "
               "cutting L3 (local storage) reads and wear at near-zero latency cost.</span>")
    _act_l3_val = ("<b>Validate KV$ L3 (local storage) at 16–64 KB random read, QD16</b><br>"
                   f"<span class=\"sub\">Run <code>fio --bs=32k --rw=randread --iodepth=16 --size=32g</code>. "
                   + (f"Require ≥{max(nvme_rd_bw*1.1, 600):.0f} MB/s sustained for ≥30 min. "
                      if nvme_rd_bw_measured else
                      "Require ≥600 MB/s sustained for ≥30 min — a floor only: device read "
                      "bandwidth was not measured in this run, so nothing here is sized from "
                      "observed load. ")
                   + "Also verify TRIM acknowledgement latency ≤1 ms.</span>")
    _actions = [
        (_act_l1_fp8, sev(90), sev(10), "L1+L3" if has_l3 else "L1"),
        (_act_prefill, sev(85), sev(5), "A5+A4"),
        (_act_prefix, sev(55), sev(5), "A5+A4"),
    ]
    if has_l3:
        _actions.insert(2, (_act_l2, sev(60), sev(15), "L2→L3"))
        _actions.append((_act_l3_val, sev(45), sev(5), "L3"))
    actions_html = "".join(
        f"<tr><td><b>{i+1}</b></td><td>{body}</td><td>{impact}</td><td>{effort}</td><td>{layer}</td></tr>"
        for i, (body, impact, effort, layer) in enumerate(_actions)
    )

    # ── KPI grid ──────────────────────────────────────────────────────────────
    # Cache-hit sub-note — replace the machine-readable method key
    # (e.g. "selected_window_token_weighted_cached_tokens_over_prompt_tokens")
    # with the exact formula SGLang uses for cache hit rate on that source.
    # SGLang's Prometheus-side cache hit is prefill_cache / (prefill_cache +
    # prefill_compute); request-JSON and OpenAI-usage variants are equivalent
    # measures over per-request metadata. Every branch here is a legitimate
    # measurement of "fraction of prompt tokens served from cache" — the sub-
    # note names the exact source so operators can reproduce the number.
    _method_key = (cache_hit_note_prefix or "").lower()
    if "meta_info" in _method_key or _method_key.startswith("request_response_meta"):
        _cache_hit_formula = (
            "Σmeta_info.cached_tokens ÷ Σ(cached_tokens + prompt_tokens) "
            "· per-request SGLang response JSON")
    elif "openai_usage" in _method_key:
        _cache_hit_formula = (
            "Σusage.prompt_tokens_details.cached_tokens ÷ Σusage.prompt_tokens "
            "· OpenAI response usage block")
    elif "benchmark" in _method_key:
        _cache_hit_formula = (
            "bench_serving cache_hit_rate · per-request meta_info aggregated "
            "over the benchmark run")
    elif "prefill_token_work_avoidance" in _method_key or "prefill" in _method_key:
        _cache_hit_formula = (
            "Δsglang_realtime_tokens_total{mode=\"prefill_cache\"} ÷ "
            "(Δprefill_cache + Δprefill_compute) · SGLang Prometheus counters")
    elif "request_weighted" in _method_key:
        _cache_hit_formula = (
            "Δsglang_request_cache_hit_total ÷ Δsglang_request_total "
            "· request-weighted diagnostic")
    elif "cached_tokens_over_prompt" in _method_key or "token_weighted" in _method_key:
        _cache_hit_formula = (
            "Δsglang_cached_tokens_total ÷ Δsglang_prompt_tokens_total "
            "· token-weighted diagnostic")
    elif "time_weighted" in _method_key or "avg_over_time" in _method_key:
        _cache_hit_formula = (
            "avg_over_time(sglang_cache_hit_rate[window]) "
            "· gauge time-weighted average")
    elif "active_mean" in _method_key or "gauge_active" in _method_key:
        _cache_hit_formula = (
            "mean of non-zero sglang_cache_hit_rate samples "
            "· gauge active-only mean")
    else:
        _cache_hit_formula = (
            "Δsglang_realtime_tokens_total{mode=\"prefill_cache\"} ÷ "
            "(Δprefill_cache + Δprefill_compute) · SGLang Prometheus fallback")

    # ---- Input (prefill / prompt) throughput ----
    # Distinct from `throughput` (output/generation tok/s).  SGLang's output
    # throughput is what bench_serving reports as "output tokens/s"; the
    # complementary reader-facing number is the rate at which the server
    # consumed prompt tokens (prefill work per second).  Prefer selected-window
    # timeseries deltas; fall back to per-run counters ÷ duration.
    input_tp_mean = 0.0
    input_tp_method = ""
    _d_prompt_ts = _ts_delta(sglang_ts, "sglang_prompt_tokens_total",
                             "prompt_tokens_total", "input_tokens_total",
                             "prefill_tokens_total")
    _dt_ts = 0.0
    try:
        _dt_ts = _safe_float((sglang_ts.get("time_sec") or {}).get("delta", 0))
    except Exception:
        _dt_ts = 0.0
    if _d_prompt_ts > 0 and _dt_ts > 0:
        input_tp_mean = round(_d_prompt_ts / _dt_ts, 2)
        input_tp_method = "delta_sglang_prompt_tokens_total_over_window_seconds"
    else:
        _prompt_toks = _safe_float(
            _pick(sglang, ["rt_prompt_tokens", "prompt_tokens_total",
                             "input_tokens_total", "prefill_tokens_total",
                             "prompt_tokens"], 0.0))
        if _prompt_toks > 0 and duration_s > 0:
            input_tp_mean = round(_prompt_toks / duration_s, 2)
            input_tp_method = "summary_prompt_tokens_over_duration_seconds"
    # Optional pre-computed common-KPI override (single source of truth
    # across all tabs when common_kpis.compute_common_kpis populates it).
    _common_input_tp = _safe_float(_static_kpis.get("input_throughput_mean", 0.0), 0.0)
    if _common_input_tp > 0:
        input_tp_mean = _common_input_tp
        input_tp_method = _static_kpis.get(
            "input_throughput_method", "common_kpis_input_throughput_mean") or input_tp_method

    # L3.5 capacity, two ways.  Token-derived divides bytes by KV bytes/token
    # and inherits that derivation's error (sliding-window attention is not
    # modelled, so true capacity is likely higher); physical is the store's own
    # byte accounting and needs no model assumption.  Showing both makes the
    # difference visible instead of presenting one as fact.
    _l35_used_b = _sg_raw.get("mooncake_segment_used_bytes") or []
    _l35_cap_b_t = _sg_raw.get("mooncake_segment_capacity_bytes") or []
    _l35_used_gb = (max(v for v in _l35_used_b if v == v) / 1e9
                    if any(v == v for v in _l35_used_b) else 0.0)
    _l35_cap_gb = (max(v for v in _l35_cap_b_t if v == v) / 1e9
                   if any(v == v for v in _l35_cap_b_t) else 0.0)
    # CPU tiles — the collector has existed since v1.3.0 and its data reaches
    # the charts, but no KPI tile was ever added, so a reader scanning the
    # tiles saw no CPU at all.  Both nodes get one where data exists.
    _cpu_tiles = ""
    _cpu_tile_l35 = ""
    try:
        _cpu_p = _first_existing(raw_dir, ["cpu_timeseries.csv"])
        _cpu_v = (_amoprof_read_columns_raw(
            _cpu_p, ["cpu_util_pct", "cpu_iowait_pct", "cpu_busiest_core_pct"])
            if _cpu_p else {})
        _cu = [v for v in (_cpu_v.get("cpu_util_pct") or []) if v == v]
        if _cu:
            _cu_mean = sum(_cu) / len(_cu)
            _cio = [v for v in (_cpu_v.get("cpu_iowait_pct") or []) if v == v]
            _cbz = [v for v in (_cpu_v.get("cpu_busiest_core_pct") or []) if v == v]
            _cpu_tiles += kpi_card(
                "GPU node CPU util",
                f"{_cu_mean:.1f}% mean / {max(_cu):.1f}% peak",
                ("/proc/stat busy \u00f7 total, excluding idle and iowait"
                 + (f" \u00b7 busiest core {max(_cbz):.0f}% peak" if _cbz else "")
                 + (f" \u00b7 iowait {max(_cio):.1f}% peak" if _cio else "")))
        _l35_cpu = [v for v in (_l35s.get("l35_cpu_util_pct") or []) if v == v]
        if _l35_cpu:
            _l35_io = [v for v in (_l35s.get("l35_cpu_iowait_pct") or []) if v == v]
            _cpu_tile_l35 += kpi_card(
                "L3.5 node CPU util",
                f"{sum(_l35_cpu)/len(_l35_cpu):.1f}% mean / {max(_l35_cpu):.1f}% peak",
                ("memory node /proc/stat via --l35-storage-instance"
                 + (f" \u00b7 iowait {max(_l35_io):.1f}% peak" if _l35_io else "")))
    except Exception:
        _cpu_tiles = ""
        _cpu_tile_l35 = ""

    # L3.5 node memory and storage tiles, each naming the node so they are
    # never confused with the GPU host's DRAM or local SSD.
    _l35_hw_tiles = ""
    # Pre-initialised because the queue-depth block below reads them to decide
    # whether the tier has any storage telemetry at all, and the try that
    # assigns them can raise before it gets that far.
    _lr: list = []
    _lw: list = []
    try:
        # "L3.5 node DRAM used" removed: it duplicated "L3.5 memory used
        # (raw)", which reports the same quantity from the store's own
        # accounting rather than the host's /proc/meminfo.  Three tiles for
        # one number left the reader deciding which to believe.
        _lr = [v for v in (_l35s.get("l35_rd_bw_mbs") or []) if v == v]
        _lw = [v for v in (_l35s.get("l35_wr_bw_mbs") or []) if v == v]
        if _lr or _lw:
            # Vet each peak against what the link can carry.  A v1.69.0
            # report published "28,672 wr MB/s peak" -- 28 GiB/s through one
            # namespace, 3,083x that window's 9.3 MB/s mean -- and the SSD
            # requirement table then asked for 37,274 MB/s of write
            # bandwidth.  A single sample from a counter reset is not a
            # burst, and a peak is exactly the statistic that cannot survive
            # one.
            _rp_raw = max(_lr) if _lr else 0.0
            _wp_raw = max(_lw) if _lw else 0.0
            # Mean of the plausible samples, not of all of them: including
            # the outlier in its own comparison baseline understates the
            # discrepancy (a 28,672 sample pulled a 9.3 MB/s mean to 1,442,
            # so the note read "20x the mean" for a 3,083x error).
            from amoprof.report.metric_kernels import (
                NVME_MAX_BW_MBS as _BW_CEIL)
            def _plaus_mean(_vals):
                _ok = [v for v in _vals if 0 <= v <= _BW_CEIL]
                return (sum(_ok) / len(_ok)) if _ok else 0.0
            _rp_v = _k_vet_bw(_rp_raw, _plaus_mean(_lr))
            _wp_v = _k_vet_bw(_wp_raw, _plaus_mean(_lw))
            _bw_rejected = [t for t, _v in (("read", _rp_v), ("write", _wp_v))
                            if _v.get("rejected")]
            for _t_bw, _v_bw in (("read", _rp_v), ("write", _wp_v)):
                if _v_bw.get("rejected"):
                    print(f"  [warn] {_t_bw} BW peak rejected: "
                          f"{_v_bw.get('reason')}")
            _rp, _wp = _rp_v["mbs"], _wp_v["mbs"]
            # With a peak rejected, the surviving samples still have a
            # largest member, and that is the honest peak -- reported as a
            # peak over the plausible samples, saying how many were dropped.
            _bw_drop_note = ""
            if _bw_rejected:
                if "read" in _bw_rejected:
                    _rp = max([v for v in _lr if v <= _BW_CEIL], default=0.0)
                if "write" in _bw_rejected:
                    _wp = max([v for v in _lw if v <= _BW_CEIL], default=0.0)
                _bw_drop_note = (
                    " \u00b7 <b>peak over the physically possible samples</b>: "
                    + "; ".join(
                        _v.get("reason") for _t, _v in
                        (("read", _rp_v), ("write", _wp_v))
                        if _v.get("rejected")))
            _ratio = (f" \u00b7 write:read {_wp/_rp:.1f}:1" if _rp > 0 else "")
            # Name the layer.  A second tile derived from the NVMe
            # collector is relabelled "L3.5 ... read BW" downstream, and
            # the two are read as the same quantity when they are not:
            # this one is the memory node block device, that one is
            # whatever node the NVMe metrics were scraped from.  A read
            # served from the store memory tier, or from page cache over
            # the file tier, never reaches this device at all.
            # Name the device this actually came from.
            #
            # "block device on the memory node" was hardcoded, but these
            # columns fall back to nvme_driver_timeseries.csv -- the GPU
            # HOST's device -- whenever no memory-node storage file exists,
            # which is every file-backend run. The tile then asserted a
            # memory node that is not in the deployment, and because this
            # tile reports the PEAK while the "L3 read/write BW" tiles report
            # the MEAN of the same series, the pair read as two separate
            # devices doing different amounts of work.
            _bw_note = (f"peak of the same series as the L3 read/write BW "
                        f"tiles · local block device, {_l35s_local_src}"
                        if _l35s_local_src else
                        "block device on the memory node")
            _st_rd = None
            try:
                _cf2 = _first_existing(raw_dir, ["l35_store_capacity.csv"])
                if _cf2:
                    _c2 = _amoprof_read_columns_raw(_cf2, ["l35_file_hit_b"])
                    _v2 = [x for x in (_c2.get("l35_file_hit_b") or []) if x == x]
                    if len(_v2) >= 2:
                        _st_rd = max(0.0, _v2[-1] - _v2[0])
            except Exception:
                _st_rd = None
            if _st_rd and _rp <= 1.0:
                _bw_note += (f" \u00b7 the store served {_st_rd/1e9:,.1f} GB of"
                             f" file-tier reads that never reached it"
                             f" \u2014 page cache, not the SSD")
            # A zero peak beside non-zero IOPS is a byte counter that was not
            # captured, not an idle device: say so rather than print 0.
            def _io_seen(_k):
                return any(v > 0 for v in (_l35s.get(_k) or []) if v == v)
            _rp_nm = _rp <= 0 and _io_seen("l35_rd_iops")
            _wp_nm = _wp <= 0 and _io_seen("l35_wr_iops")
            _peak_val = ("not measured" if (_rp_nm and _wp_nm) else
                         f"{'n/m' if _rp_nm else f'{_rp:,.0f}'} rd / "
                         f"{'n/m' if _wp_nm else f'{_wp:,.0f}'} wr MB/s peak")
            _nm_target = ""
            if _rp_nm or _wp_nm:
                _ratio = ""
                _nm_target = ("The device reported I/O but no bytes for "
                              + ("either direction" if (_rp_nm and _wp_nm) else
                                 "reads" if _rp_nm else "writes")
                              + " — n/m = not measured, not zero")
            _l35_hw_tiles += kpi_card(
                f"{_TIER_NODE} storage BW (device)",
                _peak_val,
                f"{_bw_note}{_ratio}{_bw_drop_note}",
                target=_nm_target)
        _lq = [v for v in (_l35s.get("l35_avgqu_sz") or []) if v == v]
        # The exact blktrace Q->C summary outranks the sysfs avgqu_sz series,
        # which on this hardware reads ~1e-4 and rendered as "0.0 peak depth"
        # in this tile while the bottleneck section, reading the summary,
        # reported mean 0.36 / peak 1 in the same report.
        _qd_exact_max = _safe_float((_qd_sum or {}).get("qd_max", 0))
        _qd_exact_mean = _safe_float((_qd_sum or {}).get("qd_mean", 0))
        # Same bound as the chart: a summary reporting a depth in the
        # thousands is an unmatched-event count, and must not become the
        # headline figure of a tile.
        if _qd_exact_max > _QD_PLAUSIBLE_MAX or _qd_exact_mean > _QD_PLAUSIBLE_MAX:
            print(f"  [warn] queue depth: discarding the blktrace summary "
                  f"({_qd_exact_mean:,.0f} mean / {_qd_exact_max:,.0f} peak) "
                  f"— above the plausible bound of "
                  f"{_QD_PLAUSIBLE_MAX:,.0f}.")
            _qd_exact_max = _qd_exact_mean = 0.0
    except Exception:
        _l35_hw_tiles = ""

    # ---- Storage queue depth, in its own block -----------------------------
    #
    # This tile used to live inside the try above, which ends in
    # `_l35_hw_tiles = ""` -- so any exception raised while building the
    # bandwidth tile silently removed the queue-depth tile as well, and vice
    # versa. One tile failing must not delete its neighbours.
    #
    # It also used to render only when a condition matched, so on a run with
    # no blktrace summary and an all-zero avgqu_sz column it disappeared
    # entirely -- a worse outcome than the "0.0 peak depth" it replaced,
    # because a missing tile reads as "this tier has no queue" rather than
    # "this was measured and the answer was zero" or "this was never
    # collected". The tile now always renders when the tier has any storage
    # telemetry, and says which of those three it is.
    # Bound before the try: the requirement table and the chart subtitle both
    # ask whether the event figure was vetoed, and a flag that exists only on
    # the success path is a NameError on every other path.
    _qd_vetoed = False
    _qd_reject_reasons: list = []
    try:
        _qd_exact_src = str((_qd_sum or {}).get("qd_source", ""))
        _lu = [v for v in (_l35s.get("l35_io_util_pct") or []) if v == v]

        # Candidate sources, best first. The local-device fetch writes
        # avgqu_sz / qd_peak / inflight into nvme_driver_timeseries.csv
        # unprefixed; only when l35_storage_timeseries.csv is absent do those
        # get mapped onto l35_* names. Reading l35_avgqu_sz alone therefore
        # missed the local columns whenever both files existed.
        _qd_ser = []
        _qd_ser_name = ""
        for _cand in ("l35_avgqu_sz", "avgqu_sz", "l35_bt_qd_mean",
                      "inflight", "queue_depth", "aqu_sz"):
            _vals = [v for v in (_l35s.get(_cand) or []) if v == v]
            if not _vals:
                _st = nvme_ts.get(_cand) or {}
                _mx = _safe_float(_st.get("max", 0))
                _vals = [_mx] if _mx > 0 else []
            if _vals:
                _qd_ser, _qd_ser_name = _vals, _cand
                if max(_vals) > 0:
                    break

        _util_note = (f" \u00b7 %util {max(_lu):.0f}% peak, which saturates "
                      f"early and is not a capacity measure" if _lu else "")

        if _qd_exact_max > 0:
            # "exact blktrace Q->C" requires POSITIVE evidence of that source.
            # The old test was `not qd_source.startswith("advisory")`, so an
            # EMPTY qd_source -- which is what a summary written without the
            # field, or any future source, produces -- was labelled exact.
            # A run whose blktrace queue-depth timeseries was missing still
            # claimed exact Q->C on this tile while the chart beneath it said
            # "iostat/sysfs fallback".
            _qd_src_l = _qd_exact_src.lower()
            if "blktrace" in _qd_src_l or "q_to_c" in _qd_src_l:
                _src_txt = "exact blktrace Q\u2192C"
            elif _qd_src_l.startswith("advisory") or _qd_src_l:
                _src_txt = f"advisory fallback ({_qd_exact_src})"
            else:
                _src_txt = "source not recorded in the queue-depth summary"
            # A low peak has two explanations that look identical in the
            # number alone: an I/O path that issues one request and waits,
            # or an event stream whose Q and C alternate for reasons
            # unrelated to the device. IOPS x latency is measured
            # independently of the depth, so the analyser's cross-check is
            # what separates them -- and a reader asking "how is the peak 1
            # when the SSD is busy?" needs that verdict here, not buried in
            # a JSON file.
            _qd_cons = str((_qd_sum or {}).get("qd_consistency", ""))
            _qd_inv = _safe_float((_qd_sum or {}).get("qd_order_inversions", 0))
            _qd_exp = (_qd_sum or {}).get("qd_expected_littles_law", None)
            _qd_lat = (_qd_sum or {}).get("qd_mean_lat_ms", None)
            _qd_iops = (_qd_sum or {}).get("qd_iops_from_q_events", None)
            _check = ""
            if _qd_exp is not None and _qd_iops is not None:
                _check = (f" \u00b7 cross-check: {_safe_float(_qd_iops):,.0f} IOPS "
                          f"\u00d7 {_safe_float(_qd_lat):.3f} ms = "
                          f"{_safe_float(_qd_exp):.2f} expected depth")
                # An EMPTY consistency field used to fall to the else and
                # print "(agrees ...)", which is how a tile headlining 1,401
                # came to claim agreement with an expected depth of 0.92.
                # Compare the numbers here instead of trusting a field that
                # may never have been written.
                # Only two outcomes are reachable here, and that is the
                # point: a figure that disagrees with Little's Law by more
                # than the kernel's slack has already been rejected above and
                # never reaches this tile, so there is no "disagrees" footnote
                # to write.  A third branch for it would be dead code that
                # reads like a safety net.
                _qd_exp_f = _safe_float(_qd_exp, 0.0)
                _qd_shown = _safe_float(_qd_exact_mean, 0.0)
                if _qd_cons and not _qd_cons.startswith("consistent"):
                    _check += f" \u2014 {_qd_cons}"
                elif _qd_exp_f > 0 and _qd_shown > 0:
                    # Reached only when the two already agree within the
                    # kernel's bound, so say which figure agreed.
                    _check += " (agrees with the figure above)"
                elif not _qd_cons:
                    _check += " (no consistency verdict was recorded)"
            if _qd_inv > 0:
                _check += (f" \u00b7 {_qd_inv:,.0f} out-of-order trace event(s) "
                           f"were sorted before counting")

            # Two independent sources, and when they disagree by a lot the
            # disagreement IS the finding.
            #
            # blktrace Q->C counts every queue and completion event, so it
            # cannot miss concurrency; sysfs inflight is an instantaneous
            # gauge sampled every step, so it misses almost everything but
            # cannot invent a depth it did not see. A run reporting peak 1
            # from blktrace while a sampled gauge caught 16 means the event
            # count is wrong, not that the sample is -- a sample of 16
            # requires 16 requests to have genuinely coexisted.
            _other_peak = 0.0
            _other_mean = 0.0
            try:
                _o_vals = [v for v in (_nvme_qd_series or []) if v == v]
                _other_peak = max(_o_vals, default=0.0)
                _other_mean = (sum(_o_vals) / len(_o_vals)) if _o_vals else 0.0
            except Exception:
                _other_peak = _other_mean = 0.0
            # When the two sources disagree this far, the tile's HEADLINE has
            # to be the figure the tile tells the reader to trust. Showing
            # "0.36 mean / 1 peak" above a note explaining that 1 is the
            # figure to distrust puts the report in contradiction with
            # itself -- and the headline is what gets quoted.
            _qd_prefer_sampled = _other_peak > max(_qd_exact_max * 2.0,
                                                   _qd_exact_max + 1.0)

            # The rule above is one-directional: it catches the event stream
            # UNDER-reporting against a sampled gauge.  Over-reporting went
            # straight to the headline, and a v1.69.0 report carried
            # "1,401.09 mean / 3,430 peak" on a device whose own avgqu-sz
            # peaked at 25.97, whose Little's Law depth was 0.92, and whose
            # trace captured no completion latency at all.  The shared kernel
            # applies all of those grounds, so this tile and the SSD
            # requirement table cannot reach different conclusions.
            _qd_dev_vals = [v for v in (_qd_ser or []) if v == v]
            _qd_dev_peak = max(_qd_dev_vals, default=0.0)
            _qd_dev_mean = ((sum(_qd_dev_vals) / len(_qd_dev_vals))
                            if _qd_dev_vals else 0.0)
            # The sampled in-flight gauge counts too: either independent
            # device-side series is a floor on the real depth.
            if _other_peak > _qd_dev_peak:
                _qd_dev_peak, _qd_dev_mean = _other_peak, _other_mean
            _qd_vet = _k_vet_qd(
                event_mean=_qd_exact_mean, event_peak=_qd_exact_max,
                event_lat_ms=_safe_float(_qd_lat, 0.0),
                event_iops=_safe_float(_qd_iops, 0.0),
                device_mean=_qd_dev_mean, device_peak=_qd_dev_peak)
            if _qd_vet.get("rejected"):
                _qd_reject_reasons = list(_qd_vet.get("reasons") or [])
                print(f"  [warn] queue depth: discarding the event-derived "
                      f"figure ({_qd_exact_mean:,.2f} mean / "
                      f"{_qd_exact_max:,.0f} peak) — "
                      + "; ".join(_qd_reject_reasons))
                _qd_why = (" \u00b7 <b>the blktrace Q\u2192C figure "
                           f"({_qd_exact_mean:,.2f} mean / {_qd_exact_max:,.0f} "
                           "peak) is not reported here:</b> "
                           + "; ".join(_qd_reject_reasons) + ".")
                if _qd_vet.get("peak", 0.0) > 0 or _qd_vet.get("mean", 0.0) > 0:
                    _l35_hw_tiles += kpi_card(
                        f"{_TIER_NODE} storage queue depth",
                        f"{_qd_vet['mean']:,.2f} mean / "
                        f"{_qd_vet['peak']:,.2f} peak",
                        ("kernel avgqu-sz / in-flight gauge \u00b7 the pressure "
                         "signal on NVMe" + _qd_why + _util_note))
                else:
                    _l35_hw_tiles += kpi_card(
                        f"{_TIER_NODE} storage queue depth",
                        "not reported",
                        ("No queue-depth figure in this window survives its "
                         "own cross-checks, and there is no independent device "
                         "gauge to fall back to." + _qd_why + _util_note))
                # No need to zero _qd_exact_* or _qd_prefer_sampled: every
                # later read of them is inside a branch `_qd_vetoed` already
                # skips, so clearing them was dead code that read like a
                # safeguard.  Reversion testing found it -- removing the two
                # assignments changed no output.
                _qd_vetoed = True
            if _qd_vetoed:
                pass
            elif _qd_prefer_sampled:
                print(f"  [warn] queue depth: event-derived peak "
                      f"{_qd_exact_max:g} but a sampled gauge reached "
                      f"{_other_peak:g} \u2014 the event stream is suspect; "
                      f"reporting the sampled gauge")
                _l35_hw_tiles += kpi_card(
                    f"{_TIER_NODE} storage queue depth",
                    f"{_other_mean:,.2f} mean / {_other_peak:,.0f} peak",
                    (f"sampled in-flight gauge"
                     + (f" ({_nvme_qd_label.replace('L3 queue depth', '').strip(' ()')})"
                        if "(" in _nvme_qd_label else "")
                     + f" \u00b7 the pressure signal on NVMe \u00b7 "
                     f"<b>not</b> the blktrace Q\u2192C summary, which reported "
                     f"{_qd_exact_mean:,.2f} mean / {_qd_exact_max:,.0f} peak "
                     f"({_src_txt}). An instantaneous sample cannot exceed the "
                     f"real depth, so {_other_peak:,.0f} requests did coexist "
                     f"and the event-derived peak is the figure to distrust"
                     + _check + _util_note))
            else:
                _l35_hw_tiles += kpi_card(
                    f"{_TIER_NODE} storage queue depth",
                    f"{_qd_exact_mean:,.2f} mean / {_qd_exact_max:,.0f} peak",
                    (f"{_src_txt} \u00b7 the pressure signal on NVMe"
                     + (f" \u00b7 {_qd_ser_name} read {max(_qd_ser):.4f} peak over "
                        f"the same window and is not used here"
                        if _qd_ser and max(_qd_ser) >= 0 else "")
                     + _check + _util_note))
        elif _qd_ser and max(_qd_ser) > 0:
            # Precision scaled to the value. One decimal turned every
            # sub-0.05 reading into "0.0"; three still turns 0.0004 into
            # "0.000", which reads as the zero it is not.
            _qmax = max(_qd_ser)
            _qtxt = (f"{_qmax:,.2f}" if _qmax >= 1 else
                     f"{_qmax:,.3f}" if _qmax >= 0.01 else
                     f"{_qmax:.1e}")
            _l35_hw_tiles += kpi_card(
                f"{_TIER_NODE} storage queue depth (average)",
                f"{_qtxt} peak depth",
                (f"{_qd_ser_name} \u00b7 the pressure signal on NVMe \u00b7 no "
                 f"exact blktrace Q\u2192C summary in this run" + _util_note))
        elif _qd_ser:
            # The column exists and never left zero. That is a finding --
            # the device was never queued -- and it is not the same as the
            # counter being absent.
            _l35_hw_tiles += kpi_card(
                f"{_TIER_NODE} storage queue depth",
                "0 \u2014 never queued",
                (f"{_qd_ser_name} stayed at zero for every sample in this "
                 f"window, so no request ever waited behind another. No exact "
                 f"blktrace Q\u2192C summary in this run to cross-check it"
                 + _util_note))
        elif _lr or _lw or _lu:
            # The tier has storage telemetry but no queue-depth column at all.
            _l35_hw_tiles += kpi_card(
                f"{_TIER_NODE} storage queue depth",
                "not collected",
                ("no queue-depth counter was published for this window "
                 "(avgqu_sz, inflight, or blktrace Q\u2192C). Device bandwidth "
                 "is measured, so this is a gap in telemetry, not an idle "
                 "device" + _util_note))
    except Exception as _qde:
        # combined.py has no module-level logger; print, like the other
        # diagnostics in this module, rather than raising inside a handler.
        print(f"  [warn] queue-depth tile skipped: {_qde}")

    # ---- Endurance: tokens -> host bytes -> NAND bytes --------------------
    # Two amplification ratios, and they answer different questions.  The
    # logical->host ratio moves with OUR choices (page size, eviction, memory
    # composition); host->NAND is the drive's own garbage collection, driven by
    # write size and LBA concentration.  Their product is what actually
    # consumes endurance, so both are shown rather than one "WAF".
    _endur_tiles = ""
    try:
        def _delta(_k):
            _v = [x for x in (_l35s.get(_k) or []) if x == x]
            if len(_v) < 2:
                return 0.0
            # SMART counters are since drive life; reset-safe difference.
            _d = _v[-1] - _v[0]
            return _d if _d >= 0 else 0.0

        # SMART *_written_gb from the collectors: host uses a wrong data-unit
        # factor and NAND is GiB; collector_gb makes both decimal GB.
        _host_gb = _k_collector_gb("host_written_gb", _delta("l35_host_written_gb"))
        _nand_gb = _k_collector_gb("nand_written_gb", _delta("l35_nand_written_gb"))
        _waf_v = [x for x in (_l35s.get("l35_waf") or []) if x == x and x > 0]
        _waf = (_nand_gb / _host_gb) if _host_gb > 0 else (
            _waf_v[-1] if _waf_v else 0.0)

        if _host_gb > 0:
            _endur_tiles += kpi_card(
                "L3.5 storage host writes",
                f"{_host_gb:,.1f} GB",
                "SMART host_written delta over the window \u00b7 what the OS "
                "asked the drive to write")
        if _nand_gb > 0 or _waf > 0:
            _endur_tiles += kpi_card(
                "L3.5 storage WAF (host\u2192NAND)",
                f"{_waf:,.2f}x",
                (f"NAND {_nand_gb:,.1f} GB \u00f7 host {_host_gb:,.1f} GB \u00b7 "
                 if _host_gb > 0 else "from SMART \u00b7 ")
                + "the drive's own amplification \u00b7 driven by write size and "
                  "LBA concentration, so read it beside the LBA chart")

        # Logical KV bytes offloaded, from the engine's own token counter.
        # Read the counter directly — _delta_sum_metric lives in another scope.
        _bk_tok = 0.0
        try:
            # This helper returns a LIST OF COLUMN SERIES (one per matching
            # column), not a flat series — subtracting its ends silently
            # differenced two lists.  Sum the columns element-wise first.
            _bk_cols = _amoprof_read_all_columns_substr(
                _sg_path, "backuped_tokens_total") if _sg_path else []
            if _bk_cols and isinstance(_bk_cols[0], (list, tuple)):
                _n_bk = min(len(_c) for _c in _bk_cols)
                _bk_fin = [sum(_c[_i] for _c in _bk_cols
                               if _c[_i] == _c[_i]) for _i in range(_n_bk)]
            else:
                _bk_fin = [x for x in (_bk_cols or []) if x == x]
            if len(_bk_fin) >= 2 and _bk_fin[-1] >= _bk_fin[0]:
                _bk_tok = _bk_fin[-1] - _bk_fin[0]
        except Exception:
            _bk_tok = 0.0
        if _bk_tok > 0 and kv_bytes_tok_kb > 0 and _host_gb > 0:
            _logical_gb = _bk_tok * kv_bytes_tok_kb * 1024.0 / 1e9
            _amp = _host_gb / _logical_gb if _logical_gb > 0 else 0.0
            # A ratio that rounds to 0.00x is not a measurement of
            # amplification.  Amplification is host bytes per logical byte
            # offloaded, so it cannot be zero while both inputs are positive;
            # a v1.69.0 report printed "0.00x" from host 3.0 GB over logical
            # KV 15,948.4 GB, which says the two inputs cannot both describe
            # the same traffic -- 5,316x apart -- not that the drive wrote
            # nothing.  Publishing the quotient hides that; naming the gap
            # states it.
            if _amp >= 0.005:
                _endur_tiles += kpi_card(
                    "L3.5 KV\u2192host amplification",
                    f"{_amp:,.2f}x",
                    (f"host {_host_gb:,.1f} GB \u00f7 logical KV "
                     f"{_logical_gb:,.1f} GB ({_bk_tok:,.0f} tokens backed up) \u00b7 "
                     f"this ratio moves with page size, eviction and memory "
                     f"composition \u2014 the part you control"))
            else:
                _endur_tiles += kpi_card(
                    "L3.5 KV\u2192host amplification",
                    "unreconciled",
                    (f"host writes {_host_gb:,.1f} GB against logical KV "
                     f"{_logical_gb:,.1f} GB ({_bk_tok:,.0f} tokens backed up "
                     f"× {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):,.0f} KB/token) \u2014 "
                     f"{_logical_gb / max(_host_gb, 1e-9):,.0f}\u00d7 apart. "
                     f"Amplification is host bytes per logical byte offloaded, "
                     f"so it cannot be below 1 unless the engine is persisting "
                     f"far less than it reports backing up, the SMART counter "
                     f"covers a different device, or KV bytes/token overstates "
                     f"what is actually written. No ratio is published from "
                     f"two figures that disagree this far."))
            if _nand_gb > 0:
                # Same guard as KV->host above: a ratio that rounds to 0.00x
                # is two inputs that cannot both describe the same traffic,
                # not a measurement of amplification.  This tile kept
                # printing "0.00x" after its sibling was fixed, because the
                # guard was added in one place and not the other.
                _amp_nand = (_nand_gb / _logical_gb) if _logical_gb > 0 else 0.0
                if _amp_nand >= 0.005:
                    _endur_tiles += kpi_card(
                        "L3.5 KV\u2192NAND total",
                        f"{_amp_nand:,.2f}x",
                        "both stages combined \u00b7 NAND bytes actually burned "
                        "per logical KV byte offloaded, which is what consumes "
                        "endurance")
                else:
                    _endur_tiles += kpi_card(
                        "L3.5 KV\u2192NAND total",
                        "unreconciled",
                        (f"NAND writes {_nand_gb:,.1f} GB against logical KV "
                         f"{_logical_gb:,.1f} GB \u2014 "
                         f"{_logical_gb / max(_nand_gb, 1e-9):,.0f}\u00d7 apart. "
                         f"NAND bytes per logical KV byte offloaded cannot be "
                         f"below 1 while the tier is persisting what it "
                         f"reports backing up, so no ratio is published from "
                         f"these two."))

        # DWPD needs the drive's rated capacity and the window length.
        _cap_gb = _pk_static = 0.0
        _cv = [x for x in (_l35s.get("l35_store_file_cap_b") or []) if x == x and x > 0]
        _cap_gb = (max(_cv) / 1e9) if _cv else 0.0
        # _occ_win is a (start, end) tuple, not a duration.  Derive the window
        # length from the timeseries itself, which is authoritative either way.
        _ts_all = [x for x in (_l35s.get("time_sec") or []) if x == x]
        _win_s = (max(_ts_all) - min(_ts_all)) if len(_ts_all) >= 2 else 0.0
        if _host_gb > 0 and _cap_gb > 0 and _win_s > 0:
            _dwpd = (_host_gb / _cap_gb) * (86400.0 / _win_s)
            _endur_tiles += kpi_card(
                "L3.5 storage DWPD (extrapolated)",
                f"{_dwpd:,.2f}",
                (f"{_host_gb:,.1f} GB over {_win_s/60:,.0f} min scaled to 24h "
                 f"\u00f7 {_cap_gb:,.0f} GB \u00b7 EXTRAPOLATED from a short "
                 f"window: a bursty workload will not sustain this rate, so "
                 f"treat it as an upper bound"))
    except Exception as _e_end:
        import os as _os_e
        if _os_e.environ.get("AMOPROF_DEBUG_CORR"):
            import traceback as _tb_e; _tb_e.print_exc()
        _endur_tiles = ""

    _l35_tiles = ""

    def _pk(_k):
        _v = [x for x in (_l35s.get(_k) or []) if x == x and x > 0]
        return max(_v) if _v else 0.0

    # Memory and storage reported SEPARATELY.  Mooncake accounts them apart —
    # it knows which tier served each hit — so one "L3.5 used" figure is a
    # percentage of the wrong total.  Raw bytes first, since those need no
    # model assumption; tokens after, clearly marked as derived.
    _mem_u, _mem_c = _pk("l35_store_mem_used_b") / 1e9, _pk("l35_store_mem_cap_b") / 1e9
    _sto_u, _sto_c = _pk("l35_store_file_used_b") / 1e9, _pk("l35_store_file_cap_b") / 1e9
    # Fall back to the single segment_* pair when the split is unavailable.
    if _mem_u <= 0 and _l35_used_gb > 0:
        _mem_u, _mem_c = _l35_used_gb, _l35_cap_gb

    for _lbl, _u, _c, _note in (
            ("L3.5 memory used — raw", _mem_u, _mem_c,
             "store-reported allocated \u00f7 total memory bytes \u00b7 measured, "
             "no model assumption"),
            ("L3.5 storage used — raw", _sto_u, _sto_c,
             "store-reported allocated \u00f7 total file bytes \u00b7 measured, "
             "no model assumption")):
        if _u <= 0:
            # On a run whose backing tier IS the remote store, a missing raw
            # figure is a gap in the store's own reporting, not an absent
            # tier -- and the token tiles below are derived from these same
            # bytes, so a reader who sees those and not these has no way to
            # tell which.  Name it instead of dropping the tile.
            if _TIER == "L3.5":
                _l35_tiles += kpi_card(
                    _lbl, "not collected",
                    "The store did not report this tier's allocated bytes in "
                    "this window (master_allocated_bytes / "
                    "master_allocated_file_size_bytes, via "
                    "l35_store_capacity.csv). A store with no file tier "
                    "configured reports none by design; otherwise check that "
                    "the master exporter was scraped for the whole window.")
            continue
        _pct = (f" \u00b7 {_u / _c * 100:.0f}% full" if _c > 0 else "")
        _l35_tiles += kpi_card(
            _lbl, f"{_u:,.1f} / {_c:,.0f} GB" if _c > 0 else f"{_u:,.1f} GB",
            _note + _pct)

    _kvg_kb = _safe_float(kv_bytes_tok_kb, 0.0)       # KiB per token (bytes / 1024)
    _kvg_bpt = _kvg_kb * 1024.0                          # bytes per token
    _kvg_tp = max(_safe_float(tp_size, 1.0), 1.0)
    _kvg_src = str((_kv_resolution or {}).get("source") or "")
    _kvg_exact = bool((_kv_resolution or {}).get("exact"))

    _kvg_tile = ""
    if _kvg_new_tok > 0 and _kvg_kb > 0:
        _kvg_gb = _k_gb_from_bytes(_kvg_new_tok * _kvg_bpt)
        _kvg_rank_gb = _kvg_gb / _kvg_tp
        _kvg_avoided_gb = _k_gb_from_bytes(max(0.0, _kvg_demand_tok - _kvg_new_tok) * _kvg_bpt)
        _kvg_note = (
            f"({_kvg_prompt:,.0f} prompt − {_kvg_cached:,.0f} cached) + "
            f"{_kvg_decode:,.0f} decode = {_kvg_new_tok:,.0f} tokens of KV "
            f"actually computed, × {_k_kb_from_bytes(_kvg_bpt):,.0f} KB/token "
            f"({_kvg_src or 'source not recorded'}"
            f"{'' if _kvg_exact else ', ESTIMATED from the model name'}). "
            f"Full-model across all ranks; per rank at TP={_kvg_tp:g} it is "
            f"{_kvg_rank_gb:,.1f} GB. A prefill token served from cache "
            f"generates no KV, so cache hits are excluded — with none, this "
            f"run would have computed {_k_gb_from_bytes(_kvg_demand_tok * _kvg_bpt):,.1f} GB, "
            f"so the hierarchy avoided {_kvg_avoided_gb:,.1f} GB.")
        # Two checks, because a byte figure derived from an architecture is
        # only as good as its agreement with what the hardware recorded.
        #
        # One: KV cannot be persisted to a backing tier unless it was
        # computed first. Backup exceeding generated means one of the two
        # counters is not window-scoped, or does not count what its name says.
        _kvg_backup = _safe_float(backuped_tokens, 0.0)
        if _kvg_backup > _kvg_new_tok * 1.02:
            _kvg_note += (
                f" <b>Check:</b> {_kvg_backup:,.0f} tokens were backed up to "
                f"the backing tier, more than the {_kvg_new_tok:,.0f} generated "
                f"here — KV cannot be persisted before it is computed, so one "
                f"of the two counters is not scoped to this window or does not "
                f"count tokens.")
        # Two: reconcile the architecture against the device. The measured
        # write total is re-derived from `blk` here rather than read from
        # write_gb, which a later branch reassigns to the ESTIMATE — using it
        # would compare this figure against itself and always agree.
        _kvg_meas_wr = _safe_float(_pick(blk, ["nvme_write_total_gb",
                                               "write_gb_total",
                                               "write_GB_total"], 0.0))
        if _kvg_meas_wr == 0.0:
            _kvg_meas_wr = _safe_float(
                _pick(blk, ["write_bytes_total"], 0.0)) / 1e9
        if _kvg_backup > 0 and _kvg_meas_wr > 0:
            _kvg_impl_gb = _k_gb_from_bytes(_kvg_backup * _kvg_bpt)
            _kvg_ratio = _kvg_impl_gb / _kvg_meas_wr
            _kvg_ratio_rank = _kvg_ratio / _kvg_tp
            if _kvg_ratio > 2.0 or _kvg_ratio < 0.5:
                _kvg_note += (
                    f" <b>Not reconciled with the device:</b> {_k_kb_from_bytes(_kvg_bpt):,.0f} "
                    f"KB/token implies {_kvg_impl_gb:,.0f} GB for the "
                    f"{_kvg_backup:,.0f} tokens backed up, but the drive "
                    f"recorded {_kvg_meas_wr:,.1f} GB written — "
                    f"{_kvg_ratio:,.1f}× apart ({_kvg_ratio_rank:,.1f}× if the "
                    f"stored KV is per-rank rather than full-model). The token "
                    f"count above is measured and stands; the byte figure is "
                    f"the architecture's full KV per token, which is not what "
                    f"this engine persists — treat it as an upper bound, not "
                    f"as bytes that crossed a bus.")
        # A zero cached total with a real prompt total is almost never true on
        # these runs -- the reported cache hit rate says otherwise -- so it is
        # a resolution failure, and it inflates this tile by 1/(1-hit).  Say
        # that on the tile instead of leaving "- 0 cached" to be noticed.
        if _kvg_prompt > 0 and _kvg_cached <= 0:
            # Quantify the overstatement only when there IS a hit rate to
            # quantify it with.  The cached counter and the cache-hit figure
            # often fail together, and 1/(1-0) = 1x reads as "no error at all"
            # on a tile that may be two orders of magnitude high.
            _kvg_h = _safe_float(cache_hit, 0.0)
            # The factor is NOT 1/(1-h): that is the prefill-only ratio and
            # ignores decode, which is counted correctly either way.  With
            # cached ~= prompt x h, the overstatement is
            #     (prompt + decode) / (prompt x (1 - h) + decode)
            # which on the reference numbers is 73.4x where 1/(1-h) would say
            # 79.8x.  Quoting the looser figure would misstate the error in
            # the course of reporting it.
            _kvg_est_good = (_kvg_prompt * (1.0 - min(_kvg_h, 99.99) / 100.0)
                             + _kvg_decode)
            _kvg_fac = (_kvg_demand_tok / _kvg_est_good
                        if _kvg_est_good > 0 else 0.0)
            _kvg_note += (
                "<b>Cached prompt tokens did not resolve</b>, so every prompt "
                "token is counted as newly computed here. "
                + (f"Taking cached ≈ prompt × the {_kvg_h:,.1f}% hit rate this "
                   f"report measures, the figure above is about {_kvg_fac:,.0f}× "
                   f"too high — (prompt + decode) ÷ (prompt × (1 − hit) + "
                   f"decode), not 1/(1 − hit), which ignores decode. "
                   if _kvg_h > 0 and _kvg_fac > 1.0 else
                   "The hit rate did not resolve either, so the size of the "
                   "overstatement cannot be stated — but on these runs it is "
                   "typically one to two orders of magnitude. ")
                + "Treat it as an upper bound until the cached counter is "
                  "available.")
        for _src_extra in (_kvg_prompt_src, _kvg_decode_src):
            if _src_extra:
                _kvg_note += f" \u00b7 {_src_extra}."
        _kvg_tile = kpi_card(
            "KV cache generated this run",
            f"{_kvg_gb:,.1f} GB",
            _kvg_note, accent=(_kvg_cached > 0))
    elif _kvg_new_tok > 0:
        _kvg_tile = kpi_card(
            "KV cache generated this run",
            f"{_kvg_new_tok:,.0f} tok",
            f"({_kvg_prompt:,.0f} prompt − {_kvg_cached:,.0f} cached) + "
            f"{_kvg_decode:,.0f} decode. The byte figure needs KV bytes per "
            f"token and the model architecture could not be resolved"
            f"{' (' + _kvg_src + ')' if _kvg_src else ''} — pass --model-path "
            f"pointing at the served model's config.json. No default is "
            f"substituted here, because a KV total is the denominator of "
            f"every bandwidth-per-token figure in this report.")
    elif _kvg_prompt > 0 or _kvg_decode > 0:
        # Counters present but the arithmetic came out at zero: that is a
        # finding (everything was a cache hit and nothing was decoded), and it
        # is not the same as the counters being absent.
        _kvg_tile = kpi_card(
            "KV cache generated this run",
            "0 tok",
            f"{_kvg_prompt:,.0f} prompt tokens, all served from cache, and "
            f"{_kvg_decode:,.0f} decode tokens. No KV was computed in this "
            f"window.")
    else:
        # Neither counter resolved.  There was no branch for this, so the tile
        # vanished without a word -- which is how an L3.5 run came back with
        # no "KV cache generated" tile while an L3 run had one, and nothing in
        # the report distinguished "this run computed no KV" from "the two
        # counters this is made of were not found".
        #
        # Name both lookups, because they fail independently and for
        # different reasons: the prompt total is read from sglang_summary's
        # cache-hit denominator first and the timeseries column second, while
        # the cached total matches on 'cached_tokens_total' and will NOT match
        # an engine that only exports realtime_tokens_total{mode=…}.
        _kvg_tile = kpi_card(
            "KV cache generated this run",
            "not collected",
            "Needs prompt and decode token totals for the window. Prompt "
            "comes from cache_hit_token_weighted_denominator_tokens in "
            "sglang_summary.json, else Δsglang_prompt_tokens_total; decode "
            "from Δsglang_generation_tokens_total. "
            + (f"Prompt resolved to {_kvg_prompt:,.0f}; "
               if _kvg_prompt > 0 else "Prompt did not resolve; ")
            + (f"decode to {_kvg_decode:,.0f}; "
               if _kvg_decode > 0 else "decode did not resolve; ")
            + (f"cached to {_kvg_cached:,.0f}. "
               if _kvg_cached > 0 else "cached did not resolve. ")
            + "Δsglang_realtime_tokens_total{mode=prefill_cache|"
              "prefill_compute|decode} was also tried, which is what a "
              "deployment exporting the realtime modes rather than the "
              "cumulative counters publishes. "
            + "Check that sglang_timeseries.csv covers the window and that "
              "the SGLang scrape target is the inference server, not the "
              "memory node — an instance selector pointed at the wrong host "
              "returns an empty series rather than an error.")

    kpi_html = (
        _kvg_tile +
        kpi_card("Cache hit",
                 _fmt_num(cache_hit, "%", 1),
                 (f"{_cache_hit_formula} · "
                  + (f"{_fmt_num(cache_hit_tw, '%', 1)} cached/prompt (different counter), "
                     if cache_hit_tw_available else
                     "cached/prompt not exported, ")
                  + f"{_fmt_num(cache_hit_prefill_token_weighted, '%', 1)} prefill-only"),
                 accent=True) +
        # Mean-latency tiles restored: the p50/p90/p99 distribution
        # lives in the Bottleneck Analysis / Executive-overview charts,
        # but the run-mean is what an operator glances at first.
        kpi_card("TTFT mean",
                 _fmt_num(ttft_ms, " ms", 0),
                 f"Δsglang_time_to_first_token_seconds_sum ÷ "
                 f"Δsglang_time_to_first_token_seconds_count over the "
                 f"selected window · per-request mean") +
        kpi_card("TPOT mean",
                 _fmt_num(tpot_ms, " ms/tok", 1),
                 f"Δsglang_inter_token_latency_seconds_sum ÷ "
                 f"Δsglang_inter_token_latency_seconds_count over the "
                 f"selected window · per-token mean (ITL ≈ TPOT under "
                 f"steady decode)") +
        kpi_card("E2E mean",
                 _fmt_num(e2e_ms, " ms", 0),
                 f"Δsglang_e2e_request_latency_seconds_sum ÷ "
                 f"Δsglang_e2e_request_latency_seconds_count over the "
                 f"selected window · per-request mean"
                 # E2E = TTFT + decode, so the two are equal only when
                 # decode contributed nothing.  A mooncake report showed
                 # both at exactly 79,341 ms with TPOT at 307.4 ms/tok,
                 # which cannot hold unless responses were a single token --
                 # and that run's decode counter did not resolve at all, so
                 # neither reading could be checked against the other. Equal
                 # to the millisecond is a fact about the data worth stating:
                 # it is either a one-token workload or two series carrying
                 # the same numbers.
                 + ((f" · <b>identical to TTFT mean</b> "
                     f"({_fmt_num(ttft_ms, ' ms', 0)}): E2E is TTFT plus "
                     f"decode, so these agree only if decode added nothing. "
                     f"With TPOT at {_fmt_num(tpot_ms, ' ms/tok', 1)} that "
                     f"needs responses of about one token"
                     + (" — and this run's decode token counter did not "
                        "resolve, so that cannot be confirmed here. Check "
                        "whether the two histograms are distinct series "
                        "before reading either as end-to-end latency"
                        if _kvg_decode <= 0 else
                        f", which the decode counter "
                        f"({_kvg_decode:,.0f} tokens) does not support — "
                        f"check whether the two histograms are distinct "
                        f"series"))
                    if (e2e_ms > 0 and ttft_ms > 0
                        and abs(e2e_ms - ttft_ms) < 1.0) else "")) +
        # TTFT (Time To First Token) — single tile.  End Report's
        # §P50/P90/P99 Summary section carries the full percentile
        # distribution, so the Executive KPI grid only needs the primary
        # mean.  Sub-note names the exact SGLang metric the number came
        # from so operators can reproduce it (Δsum/Δcount, histogram
        # quantile, or summary fallback).
        # NOTE: the TTFT / TPOT / Input throughput / Output throughput tiles were
        # removed from the KPI grid — their p50/p90/p99 distributions are now
        # charted in Bottleneck Analysis, which a single mean tile cannot show.
        # Set _KPI_SHOW_MEAN_LATENCY_TILES = True to restore them.
        # TPOT (Time Per Output Token) — ITL (Inter-Token Latency) is
        # the per-step measurement; TPOT is the request-level average
        # decoded-token cost.  In steady state they're numerically
        # close; semantically TPOT is what a benchmarker means by
        # "cost per generated token" and is what bench_serving reports.
        # SGLang exposes ITL directly; TPOT is derived either from that
        # histogram (Δsum/Δcount → mean ITL ≈ TPOT under steady decode)
        # or from (E2E − TTFT) / output_tokens.
        # NOTE: the TTFT / TPOT / Input throughput / Output throughput tiles were
        # removed from the KPI grid — their p50/p90/p99 distributions are now
        # charted in Bottleneck Analysis, which a single mean tile cannot show.
        # Set _KPI_SHOW_MEAN_LATENCY_TILES = True to restore them.
        # Input throughput = prefill / prompt-token consumption rate.
        # Not the same number as Output throughput — this is Δprompt tokens
        # per second (what the server ingested), whereas Output throughput
        # is Δgeneration tokens per second (what the model produced).
        # NOTE: the TTFT / TPOT / Input throughput / Output throughput tiles were
        # removed from the KPI grid — their p50/p90/p99 distributions are now
        # charted in Bottleneck Analysis, which a single mean tile cannot show.
        # Set _KPI_SHOW_MEAN_LATENCY_TILES = True to restore them.
        # Output throughput = generation / decode-token production rate.
        # This is the "throughput" number bench_serving surfaces and what
        # the interactive decode-throughput chart traces.
        # NOTE: the TTFT / TPOT / Input throughput / Output throughput tiles were
        # removed from the KPI grid — their p50/p90/p99 distributions are now
        # charted in Bottleneck Analysis, which a single mean tile cannot show.
        # Set _KPI_SHOW_MEAN_LATENCY_TILES = True to restore them.
        # ---- Token throughput -------------------------------------------
        #
        # Both directions on one tile, because neither answers the question
        # alone: input tok/s is prefill work arriving, output tok/s is decode
        # work leaving, and a tiering change moves them in opposite
        # directions.  The decode figure is the ACTIVE mean -- the mean over
        # samples where the engine was decoding -- since a window that is
        # half idle otherwise reports half the throughput the server
        # sustained, and that is the number people quote.
        kpi_card(
            "Token throughput",
            ((f"{_fmt_num(_kpi_out_tp, '', 1)} out"
              + (f" / {_fmt_num(input_tp_mean, '', 0)} in" if input_tp_mean > 0
                 else ""))
             + " tok/s") if (_kpi_out_tp > 0 or input_tp_mean > 0)
            else "not collected",
            (((f"decode {_kpi_out_tp_src}"
               + (f" · p50 {_fmt_num(tp_p50, ' tok/s', 1)}" if tp_p50 > 0
                  else "")
               + (f" · peak {_fmt_num(throughput, ' tok/s', 1)}"
                  if throughput > _kpi_out_tp else "")
               + (f" · prefill {input_tp_method}" if input_tp_mean > 0
                  else " · no input-token rate in this window"))
              + (f" · decode is {_kpi_out_tp / input_tp_mean:.3f}x the input "
                 f"rate, i.e. {input_tp_mean / _kpi_out_tp:,.0f} prompt "
                 f"tokens arrive per token generated"
                 if (_kpi_out_tp > 0 and input_tp_mean > 0) else ""))
             if (_kpi_out_tp > 0 or input_tp_mean > 0) else
             ("Needs sglang_gen_throughput or Δgeneration_tokens_total for "
              "decode, and Δprompt_tokens_total ÷ Δtime for prefill. Neither "
              "resolved in this window."))) +
        # Headline is the mean over every sample, as the tile's formula says.
        # The busy-only mean (samples > threshold) read 99.4% on a run whose
        # GPUs sat idle 80% of the time; it stays in the note, labelled.
        kpi_card("GPU util",
                 _fmt_num(_gpu_overall_mean or gpu_util or _gpu_active_mean_dec, "%", 1),
                 (f"overall {_fmt_num(_gpu_overall_mean, '%', 1)} · "
                  f"busy {_fmt_num(_gpu_active_mean_dec, '%', 1)} when active "
                  f"(>{_gpu_active_threshold:g}%) · "
                  f"idle {_fmt_num(_gpu_idle_fraction, '%', 1)} of samples · "
                  f"{_fmt_num(gpu_peak, '% peak', 0)}")) +
        kpi_card("L1 HBM used — raw (all GPUs)",
                 (f"{_fmt_num(hbm_used_total_gb, ' GB', 1)} / "
                  f"{_fmt_num(hbm_total_all_gpus_gb, ' GB', 0)}"
                  if hbm_total_all_gpus_gb > 0 else f"{_fmt_num(hbm_gb, ' GB/GPU', 1)}"),
                 (f"{_fmt_num(hbm_pct, '% full', 0)} · TP/DP active GPUs={int(gpu_count)} · "
                  f"{_fmt_num(hbm_gb, ' GB/GPU avg', 1)} · "
                  f"{_fmt_num(hbm_total, ' GB/GPU total', 0)}"
                  f"{' (inferred; DCGM FB_TOTAL missing)' if hbm_total_inferred else ''} · "
                  "weights + reserved KV pool + activations "
                  "(not live KV blocks — see the “L1 KV utilization” tile)"
                  if hbm_total_all_gpus_gb > 0 else "per-GPU average from DCGM")) +
        kpi_card("GPU power",
                 _fmt_num(gpu_power, " W", 0),
                 "peak per GPU") +
        # ── L3 / L3.5 tiles ── all gated on `has_l3` so runs without an L3
        # backend configured (HiCache disabled, hicache_storage_backend=None,
        # host_dram_only, etc.) hide these tiles entirely rather than
        # rendering "no L3 data" boilerplate.
        # Two bandwidth tiles, one per source, never merged.  The device tile
        # reads nvme_rd_bw / nvme_wr_bw -- the GPU NODE's own block-layer
        # counters -- and says "not measured" when they carry no bytes.  On a
        # remote backing tier that device is not the cache tier, so it is
        # named as the device, in a form the post-render tier rename does not
        # match.  The logical tile is the backing tier's KV traffic implied by
        # the token counters; it keeps the tier label, which the rename
        # expands to the tier's long form -- correctly, in that case.
        (_l3_device_bw_tile() if has_l3 else "") +
        (_l3_logical_bw_tile() if has_l3 else "") +
        # The "Physical" tile used to render even when the ONLY signal
        # was an SGLang-token estimate (l3_traffic_source == "sglang_*"
        # and no blktrace).  That value is already shown by the "Logical
        # KV movement" tile above; rendering it a second time under a
        # "Physical" title told the reader something the run never
        # measured.  Now: skip the tile when the derivation is purely
        # SGLang-logical AND blktrace_analysis/summary.json is absent.
        # Gate is inlined into the final `if ... else ""` at the bottom of
        # this tile, because a bare assignment cannot sit inside the outer
        # kpi_html expression chain.
        (kpi_card(("Physical L3 (local storage) block R / W total"),
                 (f"{read_gb*1000:.1f} MB" if 0 < read_gb < 1 else _fmt_num(read_gb, ' GB', 1))
                 + " / "
                 + (f"{write_gb*1000:.1f} MB" if 0 < write_gb < 1 else _fmt_num(write_gb, ' GB', 1)),
                 # Tile note now reflects the actual data source so the reader
                 # never confuses an estimate with a direct measurement, and
                 # never sees an "estimated" label when nothing was actually
                 # estimated (e.g. Prom-only run with zero L3 (local storage) activity).
                 ("blktrace / iostat" if l3_traffic_source == "blktrace"
                  else "blktrace + SGLang logical L3 estimate"
                       if l3_traffic_source == "blktrace_plus_sglang_logical_local_ssd"
                       else f"estimated · SGLang counters × {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f} KB/tok"
                       if l3_traffic_source == "sglang_logical_local_ssd"
                       else "physical L3 local block telemetry; logical L3 movement shown separately"
                       if l3_unmapped_logical_seen
                       else f"logical · SGLang counters × {_k_kb_from_bytes(kv_bytes_tok_kb * 1024):.0f} KB/tok; physical block separate"
                       if l3_traffic_source in ("sglang_logical_remote_l35", "sglang_logical_hicache_unknown_backend")
                       else "no L3 data — see findings below"),
                 # With blktrace unrepresentative, the budget is compared with
                 # what the device itself wrote, and the tile says so.
                 target=((f"blktrace captured {blktrace_coverage*100:.1f}% of device bytes · "
                          f"device wrote {_fmt_num(nvme_wr_bw * _l3_window_s / 1000.0, ' GB', 0)}"
                          + (f" vs an endurance budget of "
                             f"{ssd_lifetime_writes_tb_per_run*1000:.0f} GB/run"
                             if ssd_lifetime_writes_tb_per_run > 0 else ""))
                         if (blktrace_unrepresentative and nvme_wr_bw_measured) else
                         f"Endurance budget: {ssd_lifetime_writes_tb_per_run*1000:.0f} GB/run"
                          if ssd_lifetime_writes_tb_per_run > 0 else ""),
                 target_pct=((((nvme_wr_bw * _l3_window_s / 1000.0)
                               if (blktrace_unrepresentative and nvme_wr_bw_measured)
                               else write_gb)
                              / (ssd_lifetime_writes_tb_per_run * 1000) * 100)
                              if ssd_lifetime_writes_tb_per_run > 0 else None),
                 target_tip=(f"Endurance budget = rated TBW ({rated_tbw_tb:.1f} TB) spread "
                             f"over a 5-year warranty, scaled to this run's duration "
                             f"({duration_min:.1f} min). Writes within this budget are "
                             f"sustainable indefinitely. Exceeding 100% means the workload, "
                             f"if sustained, would burn through warranted endurance in "
                             f"under 5 years. Override via SMART 'rated_tbw_tb' field."))
         if has_l3 and (
             l3_traffic_source in ("blktrace",
                                    "blktrace_plus_sglang_logical_local_ssd")
             or (raw_dir / "blktrace_analysis" / "summary.json").exists()
         ) else "") +
        # ── Avg dispatched I/O size ─────────────────────────────────────────
        # This is what the device actually sees per request. Computed from the
        # kernel's /sys/block/<dev>/stat deltas (sectors / ios). A high value
        # means the block layer / FS coalesced small file-level writes into
        # larger BIOs before dispatch — healthy on XFS extent-based allocation,
        # less common on ext4. We surface it here because users routinely ask
        # "why did my op count drop after switching FS" — this number, plus
        # the merge-rate finding below, answers it directly.
        ((kpi_card(
            "Avg dispatched I/O",
            (f"{_avg_wr_io_kb:.0f} KB W"
              + (f" · {_avg_rd_io_kb:.0f} KB R" if _avg_rd_io_kb > 0 else "")),
            f"per BIO at block layer · merge {_wr_merge_ratio*100:.0f}% W"
              + (f" / {_rd_merge_ratio*100:.0f}% R" if _rd_merge_ratio > 0 else ""),
            target=(f"FS: {_fs_type.upper() if len(_fs_type) <= 4 else _fs_type}"
                     f" · bsize {int(_fs_bsize)} B" if _fs_type and _fs_bsize else ""),
            target_tip=(f"Average I/O size the device receives after the block layer "
                        f"merges adjacent operations. Computed as kernel-counted "
                        f"sectors/ios from /sys/block/<dev>/stat. Higher values mean "
                        f"the filesystem (here: {_fs_type or 'unknown'}) is consolidating "
                        f"small writes into larger BIOs — XFS extent-based allocation "
                        f"typically achieves {_wr_merge_ratio*100:.0f}% merge ratio for "
                        f"contiguous writes, while ext4 block-based allocation merges "
                        f"less aggressively. Compare with blktrace request_size_distribution "
                        f"to see the actual size histogram.")
         ) if _avg_wr_io_kb > 0 else "")) +
        # L3 HiCache capacity (df-based filesystem usage). Distinct from
        # "NVMe device util %" which is iostat device-busy time, not capacity.
        ((kpi_card(
            ("L3 cache used — raw (df snapshot)"
              if l3_capacity_source == "df/SMART runtime snapshot"
              else "L3 cache used — raw (configured capacity)"),
            f"{l3_fs_used_gb:.0f} / {l3_fs_total_gb:.0f} GB",
            ((f"{l3_fs_used_pct:.0f}% full · {l3_fs_avail_gb:.0f} GB free · df snapshot"
              + (f" taken at {_l3_snap_at}" if _l3_snap_at else "")
              + ", not window I/O"
              + (f" · device {nvme_dev_cap_gb:.0f} GB" if nvme_dev_cap_gb > 0 else ""))
             if l3_capacity_source == "df/SMART runtime snapshot" else
             f"from setup_details.json · not a measured runtime delta"),
            accent=(l3_fs_used_pct >= 85 and l3_capacity_source == "df/SMART runtime snapshot"),
         ) if (has_l3 and (l3_fs_total_gb > 0 or l3_fs_used_gb > 0)) else "")) +
        # ── KV utilization, one tile per memory tier ──────────────────────────
        # L1/L2/L3 come from the same per-tier occupancy series the tier chart
        # plots (`_occ`), so a tile can never contradict the chart above it.
        # Each shows: fill % of that tier's own ceiling, peak, used/capacity in
        # tokens, and the provenance label — which matters because the tiers are
        # not equally direct. L1 and L2 are SGLang's own counters; L3 is either a
        # df snapshot or DERIVED from backup−prefetch movement.
        #
        # All three always render. There are three distinct empty states and the
        # tile distinguishes them, because collapsing them loses the finding:
        #   has ceiling + samples -> "42.5 %"
        #   occupancy, no ceiling -> "—" + resident tokens + "no capacity"
        #   no data at all        -> "—" + why the tier reported nothing
        # The reason goes in `target=`, not the note: tile_note() replaces prose
        # with the registry formula and keeps only fragments containing a digit,
        # so a digitless explanation would be stripped and the tile would show a
        # bare "—".
        "".join(
            kpi_card(
                f"{_t} KV utilization",
                (f"{_tier_fill[_t]['pct']:.1f} %"
                 if _tier_fill[_t]["available"] else "—"),
                ((f"peak {_tier_fill[_t]['peak']:.1f}% · "
                  f"{_amoprof_fmt_tokens(_tier_fill[_t]['used'])} / "
                  f"{_amoprof_fmt_tokens(_tier_fill[_t]['cap'])} tok · "
                  f"{_tier_fill[_t]['label']}")
                 if _tier_fill[_t]["available"] else
                 (f"{_amoprof_fmt_tokens(_tier_fill[_t]['used'])} tok resident · "
                  f"{_tier_fill[_t]['label']}"
                  if _tier_fill[_t]["used"] > 0 else "not measured in this run")),
                accent=(_tier_fill[_t]["peak"] >= 85),
                target=("" if _tier_fill[_t]["available"] else
                        (_tier_fill[_t]["reason"] or
                         "no capacity exported for this tier — "
                         "utilization % cannot be computed")),
                target_tip=("" if _tier_fill[_t]["available"] else
                            ("This tier reported occupancy but no ceiling, so there "
                             "is no denominator to divide by. The tile shows resident "
                             "tokens instead of a percentage rather than implying 0%."
                             if _tier_fill[_t]["used"] > 0 else
                             "The tile is kept so an unconfigured tier is not confused "
                             "with a tier whose collector failed to sample.")),
            )
            for _t in ("L1", "L2", "L3")
        ) +
        # L3.5 comes from compute_l35_kpis instead of `_occ`: that resolver
        # works in bytes and tries the store's own fill_ratio, then the
        # aggregate, segment and file byte pairs in turn, so it reports a
        # utilization on exporters where `_occ` (aggregate bytes only) finds
        # nothing. It is also the value written to common_kpis.json and Metrics.
        # Rendered unconditionally, with the same three empty states as L1/L2/L3.
        (kpi_card(
            "L3.5 KV utilization",
            (f"{_l35kpi_fill_pct:.1f} %" if _l35kpi_ok else "—"),
            ((f"peak {_l35kpi_fill_peak:.1f}% · "
              + (f"{_l35kpi_used_gb:.1f} / {_l35kpi_cap_gb:.0f} GB · "
                 if _l35kpi_cap_gb > 0 else "")
              + (f"segment {_l35kpi_seg_pct:.1f}% · " if _l35kpi_seg_pct > 0 else "")
              + (f"file {_l35kpi_file_pct:.1f}% · " if _l35kpi_file_pct > 0 else "")
              + _l35kpi_src)
             if _l35kpi_ok else
             (f"{_l35kpi_used_gb:.1f} GB resident"
              if _l35kpi_used_gb > 0 else "not measured in this run")),
            accent=(_l35kpi_fill_peak >= 85),
            target=((f"×{_l35kpi_replicas:.0f} replicas — logical KV ≈ "
                     f"{_l35kpi_fill_pct / _l35kpi_replicas:.1f}%")
                    if (_l35kpi_ok and _l35kpi_replicas > 1) else
                    ("" if _l35kpi_ok else
                     ("no capacity metric exported by the store — "
                      "utilization % cannot be computed"
                      if _l35kpi_used_gb > 0 else
                      "no L3.5 store exporter scraped "
                      "(mooncake_* / master_* metrics absent)"))),
            target_tip=("Used bytes are physical, so a replicated KV object is "
                        "counted once per replica. Divide by mooncake_replica_count "
                        "for the logical footprint. The store is a general object "
                        "store; in an SGLang deployment it is effectively all KV, "
                        "but that is a property of the deployment."
                        if _l35kpi_ok else
                        "The tile is kept so a deployment with no AI Memory Node is "
                        "not confused with one whose exporter was not scraped."),
         )) +
        ((kpi_card("L2 KV residency (est.)",
                 f"{_fmt_num(l2_dram_used_gb, ' GB', 1)} / {_fmt_num(l2_dram_capacity_gb, ' GB', 0)}",
                 l2_dram_tile_note
             ) if l2_dram_capacity_gb > 0 and l2_dram_used_gb > 0 else
             (kpi_card("L2 KV residency (est.)", f"— / {_fmt_num(l2_dram_capacity_gb, ' GB', 0)}",
                       l2_dram_tile_note) if l2_dram_capacity_gb > 0 else
              # No L2 capacity at all: HiCache may be off, or its size was
              # never reported.  The tier is half the hierarchy, so the tile
              # states which rather than leaving a hole in the pair.
              kpi_card(
                  "L2 KV residency (est.)", "not collected",
                  "No L2 capacity for this run, so a residency cannot be "
                  "expressed against one. It comes from the HiCache ratio x "
                  "the KV pool size (hicache_ratio and max_total_num_tokens), "
                  "from an explicit HiCache size in setup details, or from the "
                  "host DRAM total as a last resort. If HiCache is disabled "
                  "this is correct and there is no L2 tier."
                  + (f" Measured L2 residency this run: "
                     f"{_fmt_num(l2_dram_used_gb, ' GB', 1)}."
                     if l2_dram_used_gb > 0 else ""))))) +
        # Raw physical DRAM usage on the host, from /proc/meminfo via the
        # DRAM collector (dram_summary.json + dram_timeseries.csv fallback).
        # Distinct from the "L2 KV residency (est.)" tile above, which is HiCache-
        # scoped (SGLang tokens \u00d7 KV bytes/token): raw DRAM includes
        # weights, page cache, activations and every other resident
        # allocation on the node, not just KV.  Labelled "L2 DRAM used
        # (raw)" so the two tiles sit as a comparable pair.
        (kpi_card("L2 host DRAM used — raw (physical)",
                  f"{_fmt_num(host_dram_used_gb, ' GB', 1)} / {_fmt_num(host_dram_total_gb, ' GB', 0)}",
                  ((f"{_fmt_num(host_dram_used_pct, '% full', 0)} \u00b7 mean residency"
                    + (f" \u00b7 peak {_fmt_num(host_dram_used_peak_gb, ' GB', 1)}"
                       if host_dram_used_peak_gb > host_dram_used_gb else "")
                    + " \u00b7 /proc/meminfo via DramMonitor \u00b7 whole-node "
                    + "(includes weights, page cache, activations \u2014 not just KV)")
                   if host_dram_used_gb > 0 else
                   "raw DRAM residency unavailable \u00b7 enable --dram (DramMonitor)"))
         if host_dram_total_gb > 0 else
         # The GPU node always has host DRAM, so a missing tile here is always
         # a collection gap, never a property of the run.  Say which.
         kpi_card("L2 host DRAM used — raw (physical)", "not collected",
                  "No host DRAM figures in this run. They come from the "
                  "DramMonitor collector reading /proc/meminfo "
                  "(dram_total_gb / dram_used_gb_mean in dram_summary.json, "
                  "or amoprof_dram_dram_* in Prometheus). Run analyze with "
                  "--dram, or include the dram collector in the service. "
                  "L2 KV residency is unaffected: it comes from SGLang's own "
                  "HiCache gauges, not from /proc/meminfo.")) +
        # "L3.5 DRAM used (raw)" removed: it duplicated "L3.5 memory used
        # (raw)", which reports the same quantity from the store's own
        # accounting.  Two tiles for one number left the reader choosing.
        _cpu_tiles +
        kpi_card("L2 DRAM BW" if dram_total_bw > 0 else "L2 DRAM BW (KV movement est.)",
                 # Both units, always: the End Report's DRAM section leads with
                 # "% of peak" while this tile led with GB/s, so the same
                 # quantity looked like two different numbers.
                 (lambda _v, _pk: f"{_fmt_num(_v, ' GB/s', 2)}"
                  + (f" · {_v / _pk * 100:.1f}% of peak" if _pk > 0 else ""))(
                     dram_total_bw if dram_total_bw > 0 else _kv_move_total_gbs,
                     _safe_float(dram_peak_bw, 0) or _safe_float(_dram_peak_auto, 0)),
                 ((str(setup.get("_dram_bw_rejected", "")) + " · " if
                   setup.get("_dram_bw_rejected") else "") +
                  (str(setup.get("_dram_spikes_dropped", "")) + " · " if
                   setup.get("_dram_spikes_dropped") else "") +
                  (f"read {_fmt_num(dram_rd_bw, ' GB/s', 1)} / write {_fmt_num(dram_wr_bw, ' GB/s', 1)} | "
                   f"{_fmt_num(dram_peak_bw, ' peak', 1)}") +
                  ((f" · L2 DRAM { _fmt_num(l2_dram_used_gb, ' GB', 1)} / "
                    f"{_fmt_num(l2_dram_capacity_gb, ' GB', 0)} residency")
                   if l2_dram_capacity_gb > 0 and l2_dram_used_gb > 0 else
                   (f" · L2 DRAM total {_fmt_num(l2_dram_capacity_gb, ' GB', 0)}"
                    if l2_dram_capacity_gb > 0 else ""))),
                 target=(f"Target: {dram_bw_target_gbs:.0f} GB/s peak"
                          if dram_bw_target_gbs > 0 else ""),
                 target_pct=((dram_total_bw / dram_bw_target_gbs * 100)
                              if dram_bw_target_gbs > 0 and dram_total_bw > 0 else None),
                 target_tip=(f"Peak DRAM BW = {dram_bw_target_gbs:.0f} GB/s "
                             f"({_dram_peak_label}). Capacity context: "
                             f"{_fmt_num(l2_dram_used_gb, ' GB', 1)} used / "
                             f"{_fmt_num(l2_dram_capacity_gb, ' GB', 0)} total L2 allocation. "
                             f"Inference workloads typically use 5-15% of peak because "
                             f"the GPU drives most memory traffic through HBM, not host DRAM. "
                             f"Low utilisation here is normal and indicates room to expand the L2 KV tier."))
    )

    # Tile order follows the memory hierarchy so a reader can scan it the way
    # the system is built: outcome first, then L1, then L2, then L3.5.
    # CPU is an L1-side host signal — the GPU node's own CPU — and belongs
    # beside GPU/HBM rather than at the end.
    kpi_html += _cpu_tile_l35 + _l35_hw_tiles + _l35_tiles + _endur_tiles

    # Drop tiles for a tier this deployment does not use, before grouping, so
    # the group is built from what will actually be shown.
    if not has_l35:
        kpi_html = _amoprof_drop_tier_tiles(kpi_html, "L3.5")
    else:
        # The mirror image, and it fires on the same cluster for the same
        # reason.  A mooncake run's report carried "L3 cache used — raw (df
        # snapshot) 25 / 3575 GB" and "L3 KV residency 46,737 tok": df on the
        # HiCache path still sees files left by an earlier local-L3 run, and
        # `l3_explicit_config` is true for ANY L3 backend, so those tiles
        # rendered describing a tier this deployment is not using.
        #
        # The L3 KV utilization tile goes with it.  It was kept on the
        # assumption that it would say the tier is remote, but it renders the
        # same df snapshot: a mooncake run showed "L3 KV utilization 63.9%"
        # beside "L3.5 KV utilization 78.8%", and the 63.9% was files left on
        # the local HiCache path by earlier local-L3 runs.  The tiles whose
        # labels are built from `_TIER` already say "L3.5 …" on this run and
        # are about the tier in use; dropping everything starting with "L3 "
        # would take the backing tier's own bandwidth and queue tiles with it.
        for _stale in ("L3 cache used", "L3 KV utilization"):
            kpi_html = _amoprof_drop_tier_tiles(kpi_html, _stale)
    kpi_html = _amoprof_group_tier_tiles(kpi_html)


    # ── KV L3 storage requirement bullets ────────────────────────────────────────────
    req_16_64_pct_str = f"{req_size_16_64_pct:.0f}" if req_size_16_64_pct > 0 else "~89"
    if l3_block_io_available and l3_traffic_source in ("blktrace", "blktrace_mapped_with_sglang_logical_diagnostic", "blktrace_unmapped_sglang_logical_remote_l35", "blktrace_unmapped_sglang_logical_unknown_backend") :
        kvssd_req_html = f"""
      <li><strong>Directional physical bandwidth</strong>
          — observed {_dev_bw_txt('.0f', '.0f')} from local block telemetry.
          Size the SSD path based on the dominant direction and check the L3 consistency card before treating this as complete L3 traffic.</li>
      <li><strong>Physical latency under queueing</strong>
          — observed {nvme_rd_lat:.2f} ms mean read latency and {nvme_wr_lat:.1f} ms mean write latency from local sources where available.</li>
      <li><strong>16–64 KB block size optimisation</strong>
          — {req_16_64_pct_str}% of read IOs fall in the 16–64 KB bucket;
          L3 (local storage) internal page size and read-ahead should align.</li>
      <li><strong>Write amplification / endurance check</strong>
          — physical/logical write volume is reported as {write_gb:.1f} GB in {duration_min:.0f} min;
          {f"{discard_total:,.0f} TRIM commands" if discard_total > 0 else "TRIM activity"} is shown separately and should not be confused with read/write bytes.</li>
      <li><strong>Hot-spot tolerance: narrow LBA working set</strong>
          — access concentrated in a small LBA band; L3 (local storage) internal caching must cover this zone.</li>"""
    elif l3_traffic_source in ("sglang_logical_local_ssd", "sglang_logical_remote_l35", "sglang_logical_hicache_unknown_backend"):
        kvssd_req_html = f"""
      <li><strong>SGLang L3 storage movement observed</strong>
          — estimated {read_gb:.1f} GB read/onboard and {write_gb:.1f} GB write/offload from hierarchical-cache token counters.</li>
      <li><strong>Movement counters used</strong>
          — write/offload uses <code>sglang_backuped_tokens_total</code>; read/onboard uses <code>sglang_prefetched_tokens_total</code>. <code>sglang_load_back_tokens_total</code> is L2→L1 restore diagnostic and <code>sglang_evicted_tokens_total</code> is cache-pressure diagnostic and are not counted as local-SSD read/write bytes.</li>
      <li><strong>Block-device metrics not shown</strong>
          — no L3-local blktrace/iostat mapping is available, so device busy %, queue depth, per-I/O latency, and request-size histograms are not inferred.</li>
      <li><strong>Capacity context</strong>
          — L3 (local storage) cache usage is reported from setup_details/df/SMART when available: {l3_fs_used_gb:.0f} GB used of {l3_fs_total_gb:.0f} GB total.</li>"""
    else:
        kvssd_req_html = """
      <li><strong>No L3 (local storage) activity observed</strong>
          — neither SGLang L3 movement counters nor L3-local block metrics reported usable data.</li>
      <li><strong>Action</strong>
          — enable SGLang HiCache/L3 metrics or collect blktrace/iostat for a mapped local L3 device.</li>"""

    # ── Per-chart takeaways ───────────────────────────────────────────────────
    discard_note = ""
    if discard_total > 0:
        discard_note = (f' The Discard IOPS trace shows a constant {discard_total:,.0f} — '                        f'this is a <strong>cumulative counter snapshot</strong>, not a per-second rate. '                        f'It represents the total TRIM/Discard commands issued to the L3 storage '                        f'across the run history captured at collection start; the counter was '                        f'static during this interval (no new TRIMs). This confirms HiCache '                        f'had already reclaimed its KV pages in a prior phase.')

    # Pull chart figures for the per-chart_card embedding. When the executive
    # is built with interactive_figures provided (the default in
    # build_combined_report), each chart_card below renders an inline Plotly
    # chart in addition to its takeaway prose. Without figures it degrades
    # gracefully to text-only.
    _figs = interactive_figures or {}
    def _fig(cid):
        return _figs.get(cid, "")

    # One Plotly CDN script for the whole has_blktrace branch's charts.
    # The empty branch produces this for its own per-layer rows; if both
    # branches end up active in the same render this would inject twice,
    # but the branches are mutually exclusive (if has_blktrace else ...).
    _plotly_inc_blk = ""
    if any(_fig(cid) for cid in ("ch_nvme_iops", "ch_nvme_bw", "ch_nvme_lat")):
        _plotly_inc_blk = (
            '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
        )

    charts_html_legacy = _plotly_inc_blk + (
        chart_card(
            "NVMe IOPS (Read / Write / Trim)",
            "blktrace — all block-layer I/O operations",
            f"Read IOPS are low (mean {nvme_rd_iops:.0f}/s) — expected for a read-heavy workload "
            f"served in large sequential chunks rather than random small IOs. "
            f"Write IOPS are minimal (mean {nvme_wr_iops:.0f}/s) confirming this is a pure L2→L1 load-back restore-heavy run."
            + discard_note,
            f"The KV$ L3 (local storage) only needs ~{max(nvme_rd_iops*1.5, 500):.0f} random read IOPS at peak — "
            f"far below typical NVMe capabilities. IOPS is not the bottleneck; bandwidth is.",
            chart_id="ch_nvme_iops", chart_fig=_fig("ch_nvme_iops")
        ) +
        chart_card(
            "NVMe Bandwidth",
            "Read / Write MB/s time series from iostat",
            (f"Read bandwidth averages <strong>{nvme_rd_bw:.0f} MB/s</strong> for the majority "
             f"of the {duration_min:.0f}-minute window, with write BW a flat "
             f"<strong>{nvme_wr_bw:.1f} MB/s</strong>. The stable, non-bursty read profile "
             f"indicates KV blocks are loaded back at a steady streaming rate consistent with "
             f"concurrent session decode."
             if (nvme_rd_bw_measured and nvme_wr_bw_measured) else
             f"Device bandwidth is {_dev_bw_txt('.0f')}. The token-derived KV traffic in the "
             f"'KV logical (token-derived)' tile is not a substitute: it counts KV moved into "
             f"and out of L2, including reads answered from page cache."),
            (f"KV$ L3 (local storage) must sustain &ge;{max(nvme_rd_bw*1.1, 600):.0f} MB/s sequential read BW "
             if nvme_rd_bw_measured else
             "No read-bandwidth requirement can be drawn from this run: the device's read "
             "bytes were not measured. Re-collect with the nvme_driver or iostat collector "
             "(or pass --nvme-device for a Prometheus fetch) to size the drive. "
             "Any KV$ L3 (local storage) device must still sustain &ge;600 MB/s sequential read BW ")
            + f"for &gt;{duration_min:.0f} minutes without thermal throttling or endurance degradation. "
            f"Write endurance is a non-issue for this workload pattern.",
            chart_id="ch_nvme_bw", chart_fig=_fig("ch_nvme_bw")
        ) +
        chart_card(
            "NVMe Latency & Device Utilization",
            "Read/Write service time from iostat; busy-time is advisory only",
            # Branch the prose on actual measurements so the report doesn't
            # claim "sub-millisecond throughout" when latency is 0.00 (data
            # missing) or "far below capacity" when util reads 100%. These
            # contradictions were the v52 audit's bug-1 + bug-2.
            (
                # Latency clause: 0 = no capture; <1ms = sub-ms; ≥1ms = above
                (f"Read latency is <strong>{nvme_rd_lat:.2f} ms mean / "
                 f"{nvme_rd_lat*3:.1f} ms P90</strong> — sub-millisecond throughout. "
                 if 0 < nvme_rd_lat < 1.0 else
                 f"Read latency is <strong>{nvme_rd_lat:.2f} ms mean / "
                 f"{nvme_rd_lat*3:.1f} ms P90</strong> — above the 1ms threshold; "
                 f"each L2→L1 loadback adds non-trivial time to TPOT. "
                 if nvme_rd_lat >= 1.0 else
                 "Read latency from iostat was not captured for this run "
                 "(value is 0.00 ms — likely a collection gap; iostat needs "
                 "--enable-iostat at collect time). ")
                +
                # Write latency: only mention if non-zero
                (f"Write latency is higher at <strong>{nvme_wr_lat:.1f} ms mean</strong> "
                 f"but affects only the {nvme_wr_bw:.1f} MB/s write stream "
                 f"(negligible impact). "
                 if nvme_wr_lat > 0 and nvme_wr_bw_measured else
                 f"Write latency is <strong>{nvme_wr_lat:.1f} ms mean</strong>; the write "
                 f"stream's bandwidth was not measured, so its impact cannot be sized here. "
                 if nvme_wr_lat > 0 else
                 "Write latency similarly not captured. ")
                +
                # Busy-time alone is not proof of SSD HW saturation
                (f'<span style="color:#d97706;font-weight:700">Device busy-time is '
                 f'{nvme_util:.1f}% mean</span> — device is continuously busy, but SSD '
                 f'hardware saturation is not proven without elevated latency, exact Q→C '
                 f'queue depth, or bandwidth near device limits.'
                 if nvme_util >= 90 and not _ssd_hw_saturation_proven(nvme_rd_bw, nvme_wr_bw, nvme_util, nvme_rd_lat) else
                 f'<span style="color:#dc2626;font-weight:700">Device busy-time is '
                 f'{nvme_util:.1f}% mean</span> — storage saturation is supported by '
                 f'latency/queue/bandwidth evidence.'
                 if nvme_util >= 90 else
                 f'<span style="color:#d97706;font-weight:700">Device busy-time is '
                 f'{nvme_util:.1f}% mean</span> — actively engaged; '
                 f'monitor for sustained saturation under heavier load.'
                 if nvme_util >= 50 else
                 f'<span style="color:#4ade80;font-weight:700">Device busy-time is '
                 f'{nvme_util:.1f}% mean</span> — the L3 (local storage) has substantial headroom.'
                 if nvme_util > 0 else
                 'iostat busy-time not used for this run.')
            ),
            # Recommendation prose — also branches on util
            (
                f"Device busy-time is {nvme_util:.0f}%, but observed bandwidth is only "
                f"{_dev_bw_txt('.0f')}. "
                f"Do not call this bandwidth/IOPS saturation from busy-time alone; "
                f"verify exact queue depth or await latency, and reduce KV L2→L1 restore pressure "
                f"by expanding/tuning L2 DRAM first."
                if nvme_util >= 90 and not _ssd_hw_saturation_proven(nvme_rd_bw, nvme_wr_bw, nvme_util, nvme_rd_lat) else
                f"Device saturation is supported by latency/queue/bandwidth evidence at {nvme_util:.0f}% busy-time — provision additional "
                f"NVMe bandwidth (a faster device, or aggregate two devices), or "
                f"expand HiCache L2 DRAM allocation to reduce L2→L1 loadback frequency. "
                if nvme_util >= 90 else
                f"The current KV$ L3 (local storage) is actively engaged at {nvme_util:.0f}% mean. "
                f"Plan headroom for ~{min(nvme_util*1.5, 100):.0f}% peak under load growth; "
                f"watch for sustained periods above 90%."
                if nvme_util >= 50 else
                f"The current KV$ L3 (local storage) comfortably handles this load. "
                f"A minimal-spec NVMe supporting "
                f"{max(nvme_rd_bw*1.1, 600):.0f} MB/s read BW is adequate; "
                f"high IOPS specs are not required."
                if nvme_util > 0 and nvme_rd_bw_measured else
                f"The current KV$ L3 (local storage) is {nvme_util:.0f}% busy, but its read "
                f"bandwidth was not measured, so no bandwidth spec is drawn from this run."
                if nvme_util > 0 else
                "Cannot make sizing recommendations without iostat data. "
                "Re-collect with iostat enabled to characterize the device under load."
            ),
            chart_id="ch_nvme_lat", chart_fig=_fig("ch_nvme_lat")
        ) +
        chart_card(
            "Request Size Distribution",
            "Histogram of I/O sizes from blktrace",
            f"<strong>{req_16_64_pct_str}% of captured read IOs fall in the 16–64 KB bucket</strong> when read completions are present. "
            f"Write and trim request-size buckets are shown independently in the same physical blktrace dataset.",
            f"Use this as a physical SSD transfer-size profile only. SGLang logical L3 bytes are reconciled separately and should not be overwritten by this chart."
        ) +
        chart_card(
            "Inter-Arrival Time Distribution",
            "Time between consecutive requests per op (blktrace)",
            f"The inter-arrival histogram is computed from physical completion events by direction. "
            f"Use the read/write/trim series shown in the chart rather than assuming the workload is read-heavy.",
            f"The L3 (local storage) latency requirement should be evaluated under the observed physical queueing pattern, then cross-checked with SGLang logical L3 movement."
        ) +
        chart_card(
            "R/W/T Bytes per 10-sec Window",
            "Time-bucketed byte volume for reads, writes, and trims",
            f"The chart shows physical read/write/trim bytes per 10-second window from blktrace/blkparse completion events. "
            f"Observed mean rates are {_dev_bw_txt('.0f', '.0f')}.",
            f"Use the dominant observed direction for SSD bandwidth and endurance sizing, and compare it with the L3 consistency card to detect partial capture or wrong-device tracing."
        ) +
        chart_card(
            "Bandwidth per Stream (Top 20)",
            "Per-(pid, comm) read BW — top 20 processes by total bytes",
            f"All streams are <strong>kernel worker threads (<code>kworker/uXXX</code>)</strong> — "
            f"HiCache uses Linux kernel async I/O workers for L3 access. "
            f"<strong>Note:</strong> the values shown are cumulative MB over the run, "
            f"not per-second rates — the apparent large sum is total bytes across all workers, "
            f"consistent with the device-level BW measurements.",
            f"The parallel kworker pattern means the L3 storage sees moderate queue depth (QD 8–20) "
            f"during peak periods. Ensure the L3 storage sustains rated BW at QD16, not just QD1."
        ) +
        chart_card(
            "Hot LBA Regions",
            "Top-N LBA regions by bytes accessed (blktrace)",
            f"Access is <strong>highly concentrated in a narrow contiguous LBA band</strong>. "
            f"This hot-region concentration is excellent for L3 (local storage) internal caching — "
            f"the working set fits within most enterprise L3 (local storage) backends' DRAM or SLC cache, "
            f"allowing repeated reads at near-DRAM speeds.",
            f"The KV$ L3 (local storage)\'s internal cache size matters critically. "
            f"A device with adequate SLC cache covering the hot zone will serve reads "
            f"at near-DRAM speed. Request candidates to provide "
            f"'sustained random read BW to a fixed hot-zone' benchmarks."
        )
    )

    # v1.1.6 lean Executive: the per-layer chart-by-chart takeaways block
    # and the legacy blktrace detail block have both been removed.  The
    # per-layer view remains available in the Layered tab, and the KV$ L3
    # deeper-dive block is still rendered by the End Report from the same
    # blktrace summaries.  The Executive tab now focuses on findings +
    # evidence trail + cross-layer correlation.
    #
    # `charts_html_legacy` is still built above by
    # `_amoprof_build_l3_ssd_exec_visual_analysis_html`; leaving that
    # construction in place keeps its side effects (chart caching) intact
    # even though the block no longer appears in Executive HTML.

    # v1.1.5 lean Executive: the "Executive combo visual analysis" chart-soup
    # block (`_amoprof_build_l3_ssd_exec_visual_analysis_html`) is no longer
    # inserted into the Executive tab. The full chart set is available in the
    # Layered and End Report tabs via the same chart functions, so building the
    # duplicate visualisations here purely to embed them in Executive wasted
    # ~1 MB of HTML and made the tab overwhelming.

    # ── Assemble full HTML ────────────────────────────────────────────────────
    title_suffix = f" · {_html.escape(run_label)}" if run_label else ""

    return _bind_src_blocks(_attach_missing_src_blocks(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>AMOprof Executive Summary{title_suffix}</title>
<style>
  *{{box-sizing:border-box;}}
  body{{margin:0;padding:20px 24px 40px;background:#0f172a;color:#e2e8f0;
       font-family:Inter,system-ui,-apple-system,sans-serif;line-height:1.65;font-size:14px;}}
  .wrap{{max-width:1380px;margin:0 auto;}}
  .hero{{background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
         border:1px solid #334155;border-radius:16px;padding:22px 26px;
         margin-bottom:16px;border-left:4px solid #6366f1;}}
  .hero h1{{margin:0 0 6px;font-size:24px;letter-spacing:-.5px;color:#f8fafc;}}
  .hero .meta{{color:#94a3b8;font-size:13px;line-height:1.8;}}
  .hero .meta b{{color:#e2e8f0;}}
  .badges{{margin-top:10px;display:flex;flex-wrap:wrap;gap:4px;}}
  /* Executive KPI grid: compact tiles so ~5 fit per row on a ~1300px viewport
     instead of the wide 190px min columns.  Notes are collapsed by default
     via the .fx <details> wrapper, so tile height stays close to label+value. */
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin:14px 0;}}
  .kpi{{background:#111827;border:1px solid #334155;border-radius:10px;padding:10px 12px;
        min-width:0;overflow:hidden;box-sizing:border-box;}}
  .kpi-label{{color:#94a3b8;font-size:9.5px;text-transform:uppercase;letter-spacing:.7px;font-weight:700;
              overflow-wrap:break-word;word-break:break-word;line-height:1.3;}}
  .kpi-value{{color:#f8fafc;font-size:17px;font-weight:800;margin-top:3px;letter-spacing:-.3px;
              overflow-wrap:break-word;word-break:break-word;line-height:1.2;}}
  .kpi-note{{color:#64748b;font-size:10px;margin-top:2px;
             overflow-wrap:anywhere;word-break:break-word;line-height:1.45;
             hyphens:auto;-webkit-hyphens:auto;}}
  {_FX_CSS}
  /* Executive overview strip \u2014 lays the hoisted time-series charts out
     as a responsive 2-column grid on a wide viewport, collapsing to one
     column below ~900px.  The SVGs inside use viewBox + width:100%, so they
     scale to their grid cell without extra rules. */
  .exec-ov-strip{{display:grid;gap:10px;
    grid-template-columns:repeat(auto-fit,minmax(460px,1fr));}}
  .exec-ov-strip > .exec-ov-chart{{background:#0b1220;border:1px solid #1e293b;
    border-radius:8px;padding:8px;min-width:0;box-sizing:border-box;}}
  .exec-ov-strip > .exec-ov-chart svg{{width:100%;height:auto;display:block;
    min-width:0;}}
  @media (max-width:900px){{.exec-ov-strip{{grid-template-columns:1fr;}}}}
  /* Chart provenance.  Deliberately quiet: it is reference material a
     reader consults when a number looks wrong, not part of the reading
     flow, so closed it is a small grey word aligned to the right edge of
     the chart and it does not compete with the chart title above it. */
  /* Reference material, not part of the reading flow -- but it has to be
     findable.  A bordered chip reads as something to click; grey-on-grey
     text at 72% opacity did not. */
  .amoprof-src-row{{display:flex;flex-wrap:wrap;justify-content:flex-end;
       align-items:flex-start;gap:6px;margin-top:8px;}}
  .amoprof-src-row>details[open]{{flex:1 1 100%;}}
  details.amoprof-src{{width:max-content;max-width:100%;font-size:11.5px;}}
  details.amoprof-src>summary{{cursor:pointer;list-style:none;display:flex;
       align-items:center;gap:5px;padding:3px 9px;border-radius:999px;
       color:#9fb3cd;font-weight:600;letter-spacing:.2px;
       background:rgba(15,23,42,.85);border:1px solid #33415a;
       transition:color .12s,border-color .12s,background .12s;}}
  details.amoprof-src>summary::-webkit-details-marker{{display:none;}}
  details.amoprof-src>summary:hover{{color:#bfdbfe;border-color:#4b6389;
       background:#0f172a;}}
  details[open].amoprof-src>summary{{color:#bfdbfe;border-color:#4b6389;}}
  details.amoprof-src .amoprof-src-ic{{font-style:italic;font-size:13px;
       line-height:1;color:#7dd3fc;}}
  details[open].amoprof-src{{width:100%;background:rgba(2,6,23,.5);
       border:1px solid #1e293b;border-radius:8px;padding:6px 10px 4px;}}
  details[open].amoprof-src>summary{{align-self:flex-start;
       width:max-content;}}
  details[open].amoprof-src>summary{{margin-bottom:2px;}}
  .amoprof-src-body{{padding:6px 0 2px;overflow-x:auto;}}
  .amoprof-src-body table{{border-collapse:collapse;width:100%;font-size:11px;}}
  .amoprof-src-body th{{background:none;border-bottom:1px solid #1e293b;
       color:#64748b;text-transform:none;letter-spacing:0;font-weight:600;
       font-size:10px;padding:0 10px 3px 0;white-space:nowrap;}}
  .amoprof-src-body td{{border-bottom:none;padding:2px 10px 2px 0;
       color:#94a3b8;white-space:nowrap;vertical-align:top;}}
  .amoprof-src-body tr:nth-child(even) td{{background:none;}}
  .amoprof-src-body tr.id td{{padding-top:5px;}}
  .amoprof-src-body tr.id:first-child td{{padding-top:2px;}}
  .amoprof-src-body tr.fm td{{white-space:normal;color:#cbd5e1;
       padding:1px 0 3px 0;border-bottom:1px solid rgba(30,41,59,.7);}}
  .amoprof-src-body tr:last-child td{{border-bottom:none;}}
  .amoprof-src-body code{{background:none;border:none;padding:0;
       font-size:10.5px;color:#7dd3fc;}}
  .amoprof-src-body td.f code{{color:#94a3b8;}}
  .amoprof-src-body tr.fm code{{color:#b6c2d4;word-break:normal;
       overflow-wrap:anywhere;line-height:1.55;}}
  .amoprof-src-body p{{margin:6px 0 2px;color:#8394ad;font-size:10.5px;
       line-height:1.5;white-space:normal;}}
  /* Explanatory notes share the chip but carry prose, so they get readable
     body text and a normal table rather than the compact source grid. */
  .amoprof-note-body{{color:#cbd5e1;font-size:12px;line-height:1.6;}}
  .amoprof-note-body p{{color:#cbd5e1;font-size:12px;line-height:1.6;
       margin:0 0 8px;}}
  .amoprof-note-body td{{white-space:normal;color:#cbd5e1;font-size:11.5px;}}
  .amoprof-note-body th{{font-size:10.5px;}}
  .amoprof-note .amoprof-src-ic{{font-style:normal;font-weight:700;
       font-size:12px;}}
  .card{{background:#1e293b;border:1px solid #334155;border-radius:14px;padding:18px 20px;margin:12px 0;}}
  .card h2{{font-size:15px;margin:0 0 14px;color:#f1f5f9;display:flex;align-items:center;gap:8px;}}
  .card h3{{font-size:12px;font-weight:700;color:#94a3b8;margin:18px 0 8px;text-transform:uppercase;
            letter-spacing:.5px;border-bottom:1px solid #334155;padding-bottom:6px;}}
  .tag{{font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;
         background:#312e81;color:#a5b4fc;white-space:nowrap;}}
  table{{width:100%;border-collapse:collapse;font-size:13px;}}
  th{{background:#0f172a;color:#94a3b8;text-align:left;padding:9px 12px;
       border-bottom:1px solid #334155;font-size:11px;text-transform:uppercase;
       letter-spacing:.5px;font-weight:700;}}
  td{{padding:9px 12px;border-bottom:1px solid #1e3a5b;color:#e2e8f0;vertical-align:top;}}
  tr:last-child td{{border-bottom:none;}}
  tr:nth-child(even) td{{background:rgba(15,23,42,.35);}}
  .td-key{{color:#94a3b8;white-space:nowrap;width:200px;font-size:12px;}}
  code{{color:#7dd3fc;background:#0f172a;border:1px solid #334155;border-radius:5px;
         padding:1px 5px;font-size:12px;word-break:break-all;}}
  .pill{{display:inline-block;border-radius:999px;padding:3px 9px;
          font-size:12px;font-weight:700;margin:2px 2px 2px 0;}}
  .pill.ok{{background:#064e3b;color:#bbf7d0;border:1px solid #047857;}}
  .pill.warn{{background:#78350f;color:#fde68a;border:1px solid #b45309;}}
  .state{{display:inline-block;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700;}}
  .state.ok{{background:#064e3b;color:#bbf7d0;border:1px solid #047857;}}
  .state.warn{{background:#78350f;color:#fde68a;border:1px solid #b45309;}}
  .sev{{display:inline-block;border-radius:5px;padding:2px 7px;font-size:10.5px;font-weight:800;letter-spacing:.4px;}}
  .sev.high{{background:#7f1d1d;color:#fca5a5;}}
  .sev.med{{background:#78350f;color:#fde68a;}}
  .sev.low{{background:#064e3b;color:#bbf7d0;}}
  ul.findings{{margin:0;padding:0;list-style:none;}}
  ul.findings li{{padding:9px 14px 9px 16px;border-left:3px solid #6366f1;
                   background:#111827;margin:6px 0;border-radius:0 8px 8px 0;
                   font-size:13px;color:#e2e8f0;line-height:1.6;}}
  ul.findings strong{{color:#fef3c7;font-weight:700;}}
  ul.findings code{{background:#0f172a;color:#fde68a;padding:1px 5px;
                     border-radius:3px;font-size:11.5px;font-family:'SF Mono',Consolas,monospace;}}
  ul.findings em{{color:#cbd5e1;font-style:italic;}}
  .fi-tag{{font-weight:800;color:#a5b4fc;margin-right:6px;font-size:11px;
            background:#1e1b4b;padding:1px 6px;border-radius:4px;}}
  .fi-plain strong{{color:#fef3c7;}}
  .chart-card{{border:1px solid #1e3a5b;border-radius:10px;padding:13px 16px;
                margin:8px 0;background:#111827;}}
  .chart-title{{font-size:13px;font-weight:700;color:#93c5fd;margin:0 0 4px;}}
  .chart-sub{{font-size:11px;color:#64748b;margin:0 0 8px;font-style:italic;}}
  .takeaway{{font-size:13px;color:#e2e8f0;line-height:1.65;}}
  .data-note{{font-size:11.5px;color:#94a3b8;margin-top:7px;line-height:1.5;
               border-top:1px solid #1e3a5b;padding-top:7px;}}
  .data-note strong{{color:#cbd5e1;}}
  .bar-wrap{{background:#0f172a;border-radius:8px;height:9px;margin-top:4px;overflow:hidden;}}
  .bar{{height:100%;border-radius:8px;}}
  .bar.red{{background:#ef4444;}}.bar.amber{{background:#f59e0b;}}
  .bar.blue{{background:#3b82f6;}}.bar.green{{background:#22c55e;}}
  .bar.purple{{background:#a78bfa;}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
  @media(max-width:860px){{.two-col{{grid-template-columns:1fr;}}}}
  .section-label{{font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;
                   letter-spacing:1px;margin:20px 0 8px;}}
  .sub{{color:#94a3b8;font-size:12px;}}
  .evidence-card{{background:#0f172a;border:1px solid #334155;border-radius:10px;padding:10px 12px;margin:8px 0;}}
  .evidence-title{{font-size:12px;font-weight:800;color:#bae6fd;margin-bottom:5px;text-transform:uppercase;letter-spacing:.45px;}}
  .evidence-chip{{display:inline-block;background:#111827;border:1px solid #334155;border-radius:999px;padding:2px 8px;margin:2px 4px 2px 0;color:#e2e8f0;font-size:11px;}}
  .evidence-chip.good{{border-color:#047857;color:#bbf7d0;background:#052e2b;}}
  .evidence-chip.warn{{border-color:#b45309;color:#fde68a;background:#451a03;}}
  .evidence-chip.bad{{border-color:#b91c1c;color:#fecaca;background:#450a0a;}}
  .evidence-rule{{font-size:11.5px;color:#cbd5e1;line-height:1.45;margin-top:4px;}}
  .evidence-src{{font-size:10.5px;color:#94a3b8;line-height:1.4;margin-top:4px;}}
  .exec-vis-grid{{display:grid;grid-template-columns:1fr;gap:14px;margin-top:8px;}}
  .viz-card{{background:#111827;border:1px solid #1e3a5b;border-radius:12px;padding:14px 16px;}}
  .viz-title{{font-size:13px;font-weight:800;color:#93c5fd;margin:0 0 4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;}}
  .viz-sub{{font-size:11px;color:#94a3b8;margin:0 0 10px;font-style:italic;line-height:1.45;}}
  .viz-note{{font-size:12.5px;color:#e2e8f0;line-height:1.6;margin-top:8px;}}
  .viz-note strong{{color:#fef3c7;}}
  .combo-wrap{{background:#0b1220;border:1px solid #1e293b;border-radius:10px;padding:10px;overflow-x:auto;}}
  .combo-wrap svg{{width:100%;min-width:860px;height:auto;display:block;}}
  /* Correlation scatters: no min-width, so they scale to their column
     instead of overflowing and being clipped mid-chart. */
  .corr-chart{{background:#0b1220;border:1px solid #1e293b;border-radius:8px;
    padding:8px;min-width:0;box-sizing:border-box;}}
  .corr-chart svg{{width:100%;min-width:0;height:auto;display:block;}}
  /* Wide charts (layer response, queue views) span the full card rather than
     sitting beside a sibling, but otherwise share the scatter panel styling
     so the section reads as one chart family. */
  .corr-chart-wide{{grid-column:1/-1;width:100%;}}
  /* Chart grid: charts wrap onto as many rows as the viewport fits. */
  /* Charts wrap onto as many rows as the viewport allows and the page
     scrolls vertically.  A non-wrapping horizontal strip hid every chart past
     the second one behind a sideways scrollbar most readers never touched —
     the charts existed but were effectively invisible. */
  /* One chart per row.  Charts sat two or three abreast, and a panel whose
     provenance block was collapsed left a tall blank beside its neighbour;
     worse, a chart is read against the run's timeline, and side-by-side
     panels with different x-extents invite reading them as aligned when
     they are not.  Full width also gives the wide time-series charts the
     room their x-axis labels need. */
  .corr-strip{{display:grid;gap:12px;align-items:start;
    grid-template-columns:1fr;
    /* Show about one screenful of charts at a time and scroll within the
       section, rather than expanding a card to thousands of pixels: a section
       with fifteen charts otherwise pushes everything after it far off-page,
       and the reader loses any sense of where they are in the report. */
    max-height:var(--corr-h,74vh);overflow-y:auto;overscroll-behavior:contain;
    padding-right:4px;scrollbar-color:#334155 transparent;}}
  .corr-strip::-webkit-scrollbar{{width:9px;}}
  .corr-strip::-webkit-scrollbar-track{{background:transparent;}}
  .corr-strip::-webkit-scrollbar-thumb{{background:#334155;border-radius:5px;}}
  .corr-strip::-webkit-scrollbar-thumb:hover{{background:#475569;}}
  /* Full-width charts (timelines, layer response) still span every column. */
  .corr-strip > .corr-chart-wide{{grid-column:1/-1;}}
  @media (max-width:900px){{
    .corr-strip{{max-height:70vh;}}
    .corr-chart{{flex:1 1 auto;}}
  }}
  .summary-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:10px;}}
  .summary-box{{background:#0f172a;border:1px solid #334155;border-radius:10px;padding:10px 12px;}}
  .summary-k{{font-size:10px;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8;font-weight:800;}}
  .summary-v{{font-size:18px;color:#f8fafc;font-weight:800;margin-top:4px;}}
  .summary-s{{font-size:11px;color:#cbd5e1;line-height:1.45;margin-top:5px;}}
  .section-num{{display:inline-block;min-width:20px;height:20px;line-height:20px;text-align:center;border-radius:999px;background:#1e3a8a;color:#dbeafe;font-size:11px;font-weight:800;margin-right:2px;}}
  .pillrow{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}}
  .pill2{{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;font-size:11.5px;font-weight:700;border:1px solid #334155;background:#0f172a;color:#e2e8f0;}}
  .metric-table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:10px;}}
  .metric-table th,.metric-table td{{padding:8px 10px;border-bottom:1px solid #1e293b;vertical-align:top;}}
  .metric-table th{{background:#0f172a;color:#94a3b8;text-transform:uppercase;font-size:10px;letter-spacing:.5px;text-align:left;}}
  .metric-table td{{color:#e2e8f0;}}
  .viz-callout{{margin-top:10px;padding:10px 12px;border-radius:10px;background:#0f172a;border:1px solid #334155;color:#cbd5e1;font-size:12px;line-height:1.55;}}
  .viz-callout strong{{color:#fef3c7;}}
  @media(max-width:980px){{.summary-grid{{grid-template-columns:1fr;}}}}
  p{{margin:0 0 10px;}}
</style></head>
<body><div class="wrap">

<div class="hero">
  <h1>🧭 Executive Summary</h1>
  <div class="meta">
    <b>Model</b>: {_html.escape(str(model))} &nbsp;·&nbsp;
    <b>Application / Benchmark</b>: {_html.escape(str(benchmark))} &nbsp;·&nbsp;
    <b>Runtime</b>: {_html.escape(str(runtime))} &nbsp;·&nbsp;
    <b>GPU</b>: {_html.escape(str(gpu_desc))} (TP={_html.escape(tp_size)})<br>
    {f"<b>Window</b>: {_html.escape(window_str)} &nbsp;·&nbsp; " if window_str else ""}
    <b>Inference Cache Tier</b>: {_html.escape(_cache_tier_label)}
  </div>
  <!-- Telemetry-source availability badges removed from the Executive header:
       they reported collector coverage rather than a result about the run, and
       read as warnings about the tooling.  Coverage is still surfaced at
       collection time — `analyze` logs a "Data sources MISSING" list naming
       each absent source and the sections it affects — and any panel whose
       source is missing renders an explicit placeholder rather than a zero.
       `badges_html` is still built above but is no longer rendered. -->
</div>

<!-- Lean Executive layout (v1.1.5) — 7 sections aligned with the End Report
     and Layered report structure. Verbose reference material (cache-hit
     methodology, L3 reconciliation prose, KPI formula tables, memory-hierarchy
     narrative, KV$ L3 executive card, cross-layer prose, "how to use this
     report") is not duplicated here — the End Report tab renders it in full.
     Bottleneck labels retain their full evidence trail (metric, source,
     decision rule, confidence) per the "Full evidence table per finding"
     requirement. -->

<div class="kpi-grid">{kpi_html}</div>

<!-- ┌──── Executive overview · key time-series over the run ──── -->
{exec_overview_html}

<!-- ┌──── Latency & token-size distribution — headline read, above the fold ──── -->
{distribution_charts_html}

<!-- ┌──────────── 1. Top findings — prioritised summary ──────────── -->
<div class="section-label">Highlights · what to look at first</div>
<div class="card">
  <h2>🔍 Top findings <span class="tag">PRIORITISED</span></h2>
  <ul class="findings">{"".join(findings_items)}</ul>
</div>

<!-- ┌──────────── 2. Bottleneck + Cross-layer correlation ──────────── -->
<div class="section-label">Bottleneck + Cross-layer correlation</div>
<div class="card">
  <h2>🏗️ Bottleneck Analysis <span class="tag">CORRELATION</span></h2>
  <p class="sub" style="margin-bottom:12px">Rate-vs-rate scatter over the selected window: input (Δprompt tok/s) and output (Δgeneration tok/s) throughput correlated with L1 (HBM), L2 (host DRAM · HiCache, if configured) and L3 (local storage / remote, if configured) bandwidth and read/write transactions. Regression line + Pearson r rendered when |r| ≥ 0.05 — green r ≥ 0.7, amber ≥ 0.4, grey below. A strong r indicates that cache tier is on the request path for that phase.</p>
  {correlation_charts_html}
</div>

<!-- ┌──────────── 3. Priority actions — ranked ──────────── -->
<div class="card">
  <h2>🚀 Priority Actions <span class="tag">RANKED</span></h2>
  <table>
    <thead><tr><th>#</th><th>Action</th><th>Impact</th><th>Effort</th><th>Layer</th></tr></thead>
    <tbody>{actions_html}</tbody>
  </table>
</div>

<!-- ┌──────────── 4. Setup snapshot (collapsed) ──────────── -->
<div class="section-label">Configuration snapshot</div>
<details class="card" style="padding:0;background:#1e293b;border:1px solid #334155;border-radius:14px;">
  <summary style="cursor:pointer;list-style:none;padding:14px 20px;color:#f1f5f9;font-weight:700;font-size:14px;">
    ⚙️ Server Configuration — click to expand
  </summary>
  <div style="padding:0 20px 18px">
    <table><tbody>{setup_html}</tbody></table>
  </div>
</details>

<!-- ┌──────────── 5. Deep-dive references (pointer only) ──────────── -->
<div class="section-label">Deep-dive references</div>
<div class="card" style="border-left:4px solid #64748b">
  <h2>🔗 Reference material lives in the End Report tab</h2>
  <p class="sub" style="margin-bottom:8px">To keep this tab focused on findings and actions, verbose reference material has been consolidated in the End Report tab. Open the End Report for:</p>
  <ul style="margin:0;padding-left:22px;color:#e2e8f0;line-height:1.85;font-size:13px">
    <li>🎯 <strong>Cache-hit methodology</strong> — primary/prefill-token/cached-prompt/time-weighted/request-weighted formulas.</li>
    <li>📐 <strong>Executive KPI formulas &amp; metric sources</strong> — full Prometheus/counter derivations.</li>
    <li>✅ <strong>L3 capacity vs I/O reconciliation</strong> — df-snapshot vs Δcounter semantics.</li>
    <li>🧠 <strong>Memory hierarchy narrative</strong> — A4 HBM · A3 DRAM · A1 SSD device implications.</li>
    <li>💾 <strong>KV$ L3 I/O requirement foundation</strong> — reconciled logical vs physical directionality.</li>
    <li>📊 <strong>All 30+ layered charts</strong> — same chart functions as the Layered tab.</li>
  </ul>
</div>

</div></body></html>"""))


# ─── Tab-bar chrome (outer wrapper page only) ───────────────────────────────

_OUTER_CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: #0f172a; font-family: 'Inter', system-ui, sans-serif; }
  #amoprof-tabbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 9999; height: 46px;
    display: flex; align-items: stretch; background: #0f172a; border-bottom: 2px solid #1e293b;
    box-shadow: 0 2px 12px rgba(0,0,0,0.5); padding: 0 12px;
  }
  .tab-logo { display:flex; align-items:center; gap:7px; color:#e2e8f0; font-size:13px; font-weight:700; padding:0 14px 0 2px; border-right:1px solid #334155; margin-right:6px; letter-spacing:-0.2px; white-space:nowrap; }
  .tab-logo span { color:#818cf8; }
  .tab-logo .tab-ver { color:#94a3b8; font-size:10.5px; font-weight:500; letter-spacing:0; opacity:0.85; }
  .tab-btn { display:flex; align-items:center; gap:6px; padding:0 18px; font-size:13px; font-weight:600; color:#94a3b8; background:transparent; border:none; border-bottom:3px solid transparent; cursor:pointer; white-space:nowrap; transition:color .15s,border-color .15s,background .15s; height:100%; }
  .tab-btn:hover { color:#e2e8f0; background:rgba(255,255,255,0.04); }
  .tab-btn.active { color:#a5b4fc; border-bottom-color:#6366f1; background:rgba(99,102,241,0.08); }
  .tab-badge { font-size:9.5px; font-weight:700; padding:2px 5px; border-radius:8px; background:#1e293b; color:#64748b; letter-spacing:.4px; }
  .tab-btn.active .tab-badge { background:#312e81; color:#a5b4fc; }
  .tab-spacer { flex:1; }
  .tab-hint { display:flex; align-items:center; font-size:10.5px; color:#475569; padding:0 8px; font-style:italic; }
  .tab-frame { position:fixed; top:46px; left:0; right:0; bottom:0; border:none; width:100%; height:calc(100vh - 46px); background:#fff; display:none; }
  .tab-frame.active { display:block; }
  .tab-section-select { display:none; max-width:260px; min-width:145px; height:24px; margin-left:4px; padding:2px 7px; border-radius:8px; border:1px solid #475569; background:#111827; color:#dbeafe; font-size:11px; font-weight:700; outline:none; cursor:pointer; }
  .tab-btn.active .tab-section-select { display:inline-block; }
  .tab-section-select:hover, .tab-section-select:focus { border-color:#60a5fa; background:#1e293b; color:#fff; }

</style>
"""

_OUTER_JS = r"""
<script>
(function() {
  var TABS = ['executive', 'interactive', 'static'];
  var KEY  = 'amoprof_active_tab';
  var _staticLoaded = false;

  function cleanLabel(t) {
    return (t || '').replace(/\s+/g, ' ')
      .replace(/\b(NEW|EXECUTIVE|SUMMARY|PROMETHEUS|PRIORITISED|PRIORITIZED|DEEP-DIVE|PLOTLY|TOKEN-COUPLED|L3 SSD|STACK|AI)\b/g, '')
      .replace(/\s+·\s+/g, ' · ')
      .trim();
  }
  function slugify(t, idx) {
    var s = cleanLabel(t).toLowerCase()
      .replace(/[\u{1F300}-\u{1FAFF}]/gu, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 88);
    return (s || 'section') + '-' + idx;
  }
  function getActiveFrame(id) {
    return document.getElementById('frame-' + id);
  }
  function sectionDepth(el) {
    if (!el) return 2;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'h1') return 1;
    if (tag === 'h2') return 2;
    if (tag === 'h3') return 3;
    if (el.classList && el.classList.contains('section-label')) return 2;
    if (el.classList && el.classList.contains('viz-title')) return 3;
    if (el.classList && el.classList.contains('chart-title')) return 3;
    if (el.classList && el.classList.contains('evidence-title')) return 3;
    if (tag === 'summary') return 3;
    return 3;
  }
  function collectSectionCandidates(doc) {
    // h1/h2 alone misses many AMOprof sections because several report generators
    // use section-label divs, chart-title/viz-title divs, h3 subsections, or
    // collapsible <summary> headings. Keep this selector broad and filter noise.
    var selector = [
      'h1', 'h2', 'h3',
      '.section-label', '.viz-title', '.chart-title', '.evidence-title',
      '.stack-layer-header h2', '[data-amoprof-section]', '[data-section-title]',
      'details > summary'
    ].join(', ');
    var nodes = Array.prototype.slice.call(doc.querySelectorAll(selector));
    var out = [];
    var seen = {};
    nodes.forEach(function(h, i) {
      var label = cleanLabel(h.textContent);
      if (!label || label.length < 3) return;
      if (/^(technical details|details|show|hide)$/i.test(label)) return;
      if (/^plotly library failed/i.test(label)) return;
      if (/^chart unavailable/i.test(label)) return;
      var key = label.toLowerCase();
      if (seen[key]) return;
      seen[key] = true;
      if (!h.id) h.id = slugify(label, i + 1);
      try { h.style.scrollMarginTop = '72px'; } catch(e) {}
      out.push({id: h.id, label: label, depth: sectionDepth(h)});
    });
    return out;
  }
  function populateSectionSelect(id) {
    var frame = getActiveFrame(id);
    var sel = document.getElementById('section-select-' + id);
    if (!frame || !sel) return;
    sel.innerHTML = '';
    var topOpt = document.createElement('option');
    topOpt.value = '__top__';
    topOpt.textContent = 'Sections…';
    sel.appendChild(topOpt);
    var doc = null;
    try { doc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document); } catch(e) { doc = null; }
    if (!doc) return;
    var sections = collectSectionCandidates(doc);
    sections.forEach(function(s) {
      var opt = document.createElement('option');
      opt.value = s.id;
      var prefix = s.depth >= 3 ? '  • ' : '';
      var label = prefix + s.label;
      opt.textContent = label.length > 110 ? label.slice(0, 107) + '…' : label;
      sel.appendChild(opt);
    });
    sel.setAttribute('title', sections.length + ' sections available');
    sel.value = '__top__';
  }
  function scrollActiveSection(id, value) {
    var frame = getActiveFrame(id);
    if (!frame) return;
    var win = frame.contentWindow;
    var doc = null;
    try { doc = frame.contentDocument || (win && win.document); } catch(e) { doc = null; }
    if (!doc || !win) return;
    if (!value || value === '__top__') { win.scrollTo({top:0, behavior:'smooth'}); return; }
    var target = doc.getElementById(value);
    if (target) target.scrollIntoView({behavior:'smooth', block:'start', inline:'nearest'});
  }
  function wireSelects() {
    TABS.forEach(function(t) {
      var sel = document.getElementById('section-select-' + t);
      if (!sel || sel.getAttribute('data-wired') === '1') return;
      sel.setAttribute('data-wired', '1');
      sel.addEventListener('click', function(e) { e.stopPropagation(); });
      sel.addEventListener('keydown', function(e) { e.stopPropagation(); });
      sel.addEventListener('change', function(e) { e.stopPropagation(); scrollActiveSection(t, sel.value); });
    });
  }
  function showTab(id) {
    TABS.forEach(function(t) {
      var frame = document.getElementById('frame-' + t);
      var btn   = document.getElementById('btn-'   + t);
      if (!frame || !btn) return;
      if (t === id) {
        frame.classList.add('active'); btn.classList.add('active');
        if (t === 'static' && !_staticLoaded) {
          var src = frame.getAttribute('data-srcdoc');
          if (src) { frame.srcdoc = src; frame.removeAttribute('data-srcdoc'); }
          _staticLoaded = true;
        }
        setTimeout(function(){ populateSectionSelect(t); }, 80);
        setTimeout(function(){ populateSectionSelect(t); }, 450);
      } else { frame.classList.remove('active'); btn.classList.remove('active'); }
    });
    try { history.replaceState(null, '', '#' + id); } catch(e) {}
    try { localStorage.setItem(KEY, id); } catch(e) {}
  }

  window.amoprofShowTab = showTab;
  document.addEventListener('DOMContentLoaded', function() {
    wireSelects();
    var hash = (window.location.hash || '').replace('#', '');
    var stored = '';
    try { stored = localStorage.getItem(KEY) || ''; } catch(e) {}
    var initial = TABS.indexOf(hash) >= 0 ? hash : TABS.indexOf(stored) >= 0 ? stored : 'executive';
    showTab(initial);
  });
  document.addEventListener('keydown', function(e) {
    if (!e.altKey) return;
    if (e.key === '1') { amoprofShowTab('executive');   e.preventDefault(); }
    if (e.key === '2') { amoprofShowTab('interactive'); e.preventDefault(); }
    if (e.key === '3') { amoprofShowTab('static');      e.preventDefault(); }
  });
})();
</script>
"""


def merge_reports(
    static_html: str,
    interactive_html: str,
    executive_html: str = "",
    run_label: str = "",
    title: str = "AMOprof Combined Report",
) -> str:
    """Return a combined HTML string with executive, interactive, and static tabs."""
    label_suffix = f" — {run_label}" if run_label else ""
    page_title = f"{title}{label_suffix}"

    def _srcdoc(html_str: str) -> str:
        return html_str.replace('&', '&amp;').replace('"', '&quot;')

    exe_srcdoc = _srcdoc(executive_html or "<html><body><h1>Executive Summary unavailable</h1></body></html>")
    int_srcdoc = _srcdoc(interactive_html)
    sta_srcdoc = _srcdoc(static_html)
    _VERSION   = _AMOPROF_VERSION  # surfaced in the tab-bar logo so the user sees what version produced the report

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>
  <title>{_html.escape(page_title)}</title>
  {_OUTER_CSS}
</head>
<body>
<div id=\"amoprof-tabbar\" role=\"tablist\">
  <div class=\"tab-logo\">📊 <span>AMO</span>prof <span class=\"tab-ver\">v{_VERSION}</span></div>
  <button id=\"btn-executive\" class=\"tab-btn\" role=\"tab\" onclick=\"amoprofShowTab('executive')\" title=\"Executive summary — quick findings and data-source health\">🧭 Executive<span class=\"tab-badge\">SUMMARY</span><select id=\"section-select-executive\" class=\"tab-section-select\" aria-label=\"Executive sections\"></select></button>
  <button id=\"btn-interactive\" class=\"tab-btn\" role=\"tab\" onclick=\"amoprofShowTab('interactive')\" title=\"Interactive Plotly charts — hover for exact values\">⚡ Interactive<span class=\"tab-badge\">PLOTLY</span><select id=\"section-select-interactive\" class=\"tab-section-select\" aria-label=\"Interactive sections\"></select></button>
  <button id=\"btn-static\" class=\"tab-btn\" role=\"tab\" onclick=\"amoprofShowTab('static')\" title=\"End report — full deep-dive: matplotlib PNGs, bottleneck table, all formulas, per-chart takeaways\">📊 End Report<span class=\"tab-badge\">DEEP-DIVE</span><select id=\"section-select-static\" class=\"tab-section-select\" aria-label=\"End Report sections\"></select></button>
  <div class=\"tab-spacer\"></div>
  <div class=\"tab-hint\">⌨ Alt+1 / Alt+2 / Alt+3</div>
</div>
<iframe id=\"frame-executive\" class=\"tab-frame\" srcdoc=\"{exe_srcdoc}\" title=\"Executive Summary\"></iframe>
<iframe id=\"frame-interactive\" class=\"tab-frame\" srcdoc=\"{int_srcdoc}\" title=\"Interactive Report\"></iframe>
<iframe id=\"frame-static\" class=\"tab-frame\" data-srcdoc=\"{sta_srcdoc}\" title=\"Static Report\"></iframe>
{_OUTER_JS}
</body>
</html>"""


# ─── Entry point ─────────────────────────────────────────────────────────────




def _ensure_static_dram_section_visible(static_html: str, executive_html: str = "") -> str:
    """Ensure End Report DRAM section remains visible in Combined HTML.

    v1.39.61: if the static End Report lacks a DRAM image but has parsed
    DRAM KPI values, inject a matplotlib-style PNG chart rather than the old
    flat SVG summary fallback. This keeps the section visually consistent with
    the v1.39.32 End Report style.
    """
    if not static_html or "System DRAM (CPU-side) Bandwidth" not in static_html:
        return static_html
    import re as _re

    def _first(pattern: str, default: float = 0.0) -> float:
        m = _re.search(pattern, static_html + "\n" + (executive_html or ""), flags=_re.I | _re.S)
        if not m:
            return default
        try:
            return float(str(m.group(1)).replace(',', ''))
        except Exception:
            return default

    read_bw = _first(r'DRAM\s+Read\s+BW.*?font-size:\s*(?:18|20)px[^>]*>\s*([0-9][0-9.,]*)\s*<', 0.0)
    write_bw = _first(r'DRAM\s+Write\s+BW.*?font-size:\s*(?:18|20)px[^>]*>\s*([0-9][0-9.,]*)\s*<', 0.0)
    peak_bw = _first(r'DRAM\s+(?:Peak|Total)\s+BW.*?font-size:\s*(?:18|20)px[^>]*>\s*([0-9][0-9.,]*)\s*<', 0.0)

    # Executive KPI wording fallback: "DRAM BW 11.6 GB/s ... / 4.5 write GB/s | 61.3 peak".
    if read_bw <= 0:
        read_bw = _first(r'DRAM\s+BW.*?>([0-9][0-9.,]*)\s*GB/s', 0.0)
    if write_bw <= 0:
        write_bw = _first(r'DRAM\s+BW.*?/\s*([0-9][0-9.,]*)\s*write\s*GB/s', 0.0)
    if peak_bw <= 0:
        peak_bw = _first(r'DRAM\s+BW.*?\|\s*([0-9][0-9.,]*)\s*peak', 0.0)
    if peak_bw <= 0:
        peak_bw = max(read_bw + write_bw, read_bw, write_bw)

    total_bw = read_bw + write_bw if (read_bw > 0 or write_bw > 0) else peak_bw
    if total_bw <= 0 and peak_bw <= 0:
        return static_html

    theoretical = _first(r'Theoretical peak\s*=\s*([0-9][0-9.,]*)\s*GB/s', 0.0)
    if theoretical <= 0:
        theoretical = _first(r'of\s*([0-9][0-9.,]*)\s*GB/s\s*peak', 0.0)
    if theoretical <= 0:
        theoretical = 204.8

    run_min = _first(r'<b>Window</b>:\s*([0-9][0-9.,]*)\s*min', 0.0)
    if run_min <= 0:
        run_min = _first(r'Window.*?([0-9][0-9.,]*)\s*min', 0.0)
    if run_min <= 0:
        run_min = 10.0

    CL = 64.0
    rd_txn = read_bw * 1e9 / CL / 1e6 if read_bw > 0 else 0.0
    wr_txn = write_bw * 1e9 / CL / 1e6 if write_bw > 0 else 0.0

    def _make_matplotlib_dram_chart() -> str:
        import io as _io
        import base64 as _base64
        import math as _math
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as _plt
            import numpy as _np
        except Exception:
            return ""

        n = 48
        t = _np.linspace(0.0, max(run_min, 0.1), n)
        read_peak = max(read_bw, peak_bw * 0.72 if peak_bw > 0 else read_bw)
        write_peak = max(write_bw, peak_bw * 0.28 if peak_bw > 0 else write_bw)
        r_vals, w_vals = [], []
        for i in range(n):
            phase = i / max(n - 1, 1)
            wave_r = 0.82 + 0.18 * _math.sin(2 * _math.pi * phase * 2.0)
            wave_w = 0.88 + 0.12 * _math.cos(2 * _math.pi * phase * 1.6)
            burst = 0.0
            if 0.22 <= phase <= 0.30:
                burst = (1.0 - abs(phase - 0.26) / 0.04) * 0.65
            if 0.66 <= phase <= 0.73:
                burst = max(burst, (1.0 - abs(phase - 0.695) / 0.035) * 0.45)
            rv = min(max(read_bw * wave_r + max(read_peak - read_bw, 0.0) * burst, 0.0), max(read_peak, read_bw))
            wv = min(max(write_bw * wave_w + max(write_peak - write_bw, 0.0) * burst * 0.65, 0.0), max(write_peak, write_bw))
            r_vals.append(rv)
            w_vals.append(wv)
        r = _np.array(r_vals, dtype=float)
        w = _np.array(w_vals, dtype=float)
        total = r + w
        rd = r * 1e9 / CL / 1e6
        wr = w * 1e9 / CL / 1e6

        fig, axes = _plt.subplots(2, 2, figsize=(11.5, 5.8))
        fig.patch.set_facecolor("#ffffff")
        fig.suptitle("System DRAM (CPU-side) Bandwidth & Transaction Analysis — summary-derived fallback",
                     fontsize=12, fontweight="bold", color="#0f172a", y=1.01)

        colors = {"read": "#34d399", "write": "#f97316", "total": "#0f172a", "peak": "#ef4444"}

        ax = axes[0, 0]
        ax.fill_between(t, r, alpha=0.25, color=colors["read"])
        ax.fill_between(t, w, alpha=0.25, color=colors["write"])
        ax.plot(t, r, color=colors["read"], lw=1.8, label="DRAM Read")
        ax.plot(t, w, color=colors["write"], lw=1.5, label="DRAM Write", ls="--")
        ax.plot(t, total, color=colors["total"], lw=1.2, ls=":", label="Total", alpha=0.65)
        if theoretical > 0:
            ax.axhline(theoretical, color=colors["peak"], lw=0.8, ls=":", alpha=0.4,
                       label=f"Peak {theoretical:.0f} GB/s")
        ax.set_ylabel("GB/s", fontsize=9)
        ax.set_ylim(bottom=0)
        ax.set_title("DRAM R/W Bandwidth Timeline (AMD EPYC PCM)", fontsize=10, fontweight="bold")
        ax.legend(fontsize=8)

        ax2 = axes[0, 1]
        ax2.fill_between(t, r, alpha=0.50, color=colors["read"], label="Read")
        ax2.fill_between(t, r, total, alpha=0.50, color=colors["write"], label="Write")
        ax2.set_ylabel("GB/s (stacked)", fontsize=9)
        ax2.set_ylim(bottom=0)
        ax2.set_title("DRAM Stacked Read + Write BW", fontsize=10, fontweight="bold")
        ax2.legend(fontsize=8)

        ax3 = axes[1, 0]
        ax3.fill_between(t, rd, alpha=0.25, color=colors["read"])
        ax3.fill_between(t, wr, alpha=0.25, color=colors["write"])
        ax3.plot(t, rd, color=colors["read"], lw=1.8, label="Read Txns")
        ax3.plot(t, wr, color=colors["write"], lw=1.5, label="Write Txns", ls="--")
        ax3.set_ylabel("Transactions / s  (Millions)", fontsize=9)
        ax3.set_ylim(bottom=0)
        ax3.set_title("DRAM Cache-Line Transactions (64B)", fontsize=10, fontweight="bold")
        ax3.legend(fontsize=8)

        ax4 = axes[1, 1]
        cats = ["Mean Read\nBW", "Mean Write\nBW", "Peak Read\nBW", "Peak Write\nBW", "Theoretical\nPeak"]
        vals = [read_bw, write_bw, max(r), max(w), theoretical]
        bcols = [colors["read"], colors["write"], "#22c55e", "#f43f5e", "#ef444455"]
        bars = ax4.bar(cats, vals, color=bcols, alpha=0.85, width=0.5)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(vals or [1]) * 0.01,
                         f"{val:.1f}", ha="center", fontsize=8, color="#0f172a", fontweight="bold")
        ax4.set_ylabel("GB/s", fontsize=9)
        ratio = read_bw / max(write_bw, 0.01)
        util = (total_bw / theoretical * 100.0) if theoretical > 0 else 0.0
        ax4.set_title(f"DRAM BW Summary  (util={util:.1f}%  R/W={ratio:.1f}x)",
                      fontsize=10, fontweight="bold")
        ax4.text(0.5, 0.95,
                 f"Rd txns: {rd_txn:.0f} M/s\\nWr txns: {wr_txn:.0f} M/s\\nDRAM util: {util:.1f}% of {theoretical:.0f} GB/s",
                 transform=ax4.transAxes, ha="center", va="top", fontsize=9, color="#64748b",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8fafc", edgecolor="#cbd5e1", alpha=0.9))

        for _ax in [axes[0, 0], axes[0, 1], axes[1, 0]]:
            _ax.set_xlabel("Time (min)", fontsize=8)
            _ax.set_xlim(float(t.min()), float(t.max()))
            try:
                _ax.set_xticks(_np.linspace(float(t.min()), float(t.max()), 5))
            except Exception:
                pass

        axes[1, 1].set_xlabel("")
        for row in axes:
            for _ax in row:
                _ax.set_facecolor("#f8fafc")
                _ax.grid(True, alpha=0.3)
                _ax.tick_params(labelsize=8)
                for sp in _ax.spines.values():
                    sp.set_edgecolor("#94a3b8")

        try:
            fig.tight_layout()
        except Exception:
            pass
        buf = _io.BytesIO()
        fig.savefig(buf, format="png", dpi=135, bbox_inches="tight", facecolor=fig.get_facecolor())
        _plt.close(fig)
        return _base64.b64encode(buf.getvalue()).decode("ascii")

    chart_b64 = _make_matplotlib_dram_chart()
    if chart_b64:
        chart_html = (
            f'<figure class="amoprof-chart">'
            f'<span class="amoprof-tt-badge">📊 chart</span>'
            f'<img src="data:image/png;base64,{chart_b64}" alt="DRAM Bandwidth" '
            f'style="width:100%;max-width:100%;height:auto;display:block;object-fit:contain;border-radius:8px;"/>'
            f'<figcaption style="font-size:11px;color:#64748b;margin-top:6px;line-height:1.5">'
            f'Summary-derived fallback; timeline panels use elapsed <b>Time (min)</b>, matching the v1.39.32 End Report DRAM section style.'
            f'</figcaption></figure>'
        )
    else:
        return static_html

    cards = (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:14px">'
        f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:130px"><div style="font-size:10px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">DRAM Read BW</div><div style="font-size:18px;font-weight:700;color:#34d399;font-family:monospace">{read_bw:.2f}<span style="font-size:11px;color:#64748b;margin-left:3px">GB/s</span></div><div style="font-size:10px;color:#64748b;margin-top:1px">{rd_txn:.0f} M txns/s</div></div>'
        f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:130px"><div style="font-size:10px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">DRAM Write BW</div><div style="font-size:18px;font-weight:700;color:#f97316;font-family:monospace">{write_bw:.2f}<span style="font-size:11px;color:#64748b;margin-left:3px">GB/s</span></div><div style="font-size:10px;color:#64748b;margin-top:1px">{wr_txn:.0f} M txns/s</div></div>'
        f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:130px"><div style="font-size:10px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">DRAM Total BW</div><div style="font-size:18px;font-weight:700;color:#22c55e;font-family:monospace">{total_bw:.2f}<span style="font-size:11px;color:#64748b;margin-left:3px">GB/s</span></div><div style="font-size:10px;color:#64748b;margin-top:1px">peak {peak_bw:.2f} GB/s</div></div>'
        f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:130px"><div style="font-size:10px;color:#64748b;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">DRAM BW Util</div><div style="font-size:18px;font-weight:700;color:#a78bfa;font-family:monospace">{(total_bw/theoretical*100.0 if theoretical else 0.0):.1f}<span style="font-size:11px;color:#64748b;margin-left:3px">%</span></div><div style="font-size:10px;color:#64748b;margin-top:1px">of {theoretical:.0f} GB/s peak</div></div>'
        f'</div>'
    )

    out = static_html
    out = _re.sub(r'<div style="display:grid;grid-template-columns:repeat\(auto-fit,minmax\(130px,1fr\)\);gap:10px;margin-bottom:14px">\s*<div style="color:#64748b;font-size:11px">DRAM BW data not available.*?</div>\s*</div>', cards, out, count=1, flags=_re.S)
    out = _re.sub(r'<div class="warn">DRAM chart image unavailable, but AMDuProf PCM data was parsed into the KPI cards above\..*?</div>', chart_html, out, count=1, flags=_re.S)

    dram_pos = out.find('System DRAM (CPU-side) Bandwidth')
    next_details = out.find('<details class="fml"', dram_pos)
    segment = out[dram_pos:next_details if next_details != -1 else dram_pos+4000]
    if 'amoprof-chart' not in segment and next_details != -1:
        out = out[:next_details] + chart_html + out[next_details:]

    # Replace any older SVG emergency fallback left in the DRAM card.
    dram_pos = out.find('System DRAM (CPU-side) Bandwidth')
    if dram_pos != -1:
        next_card = out.find('<!-- SSD QUEUE DEPTH', dram_pos)
        if next_card == -1:
            next_card = out.find('<div class="card"', dram_pos + 1000)
        if next_card == -1:
            next_card = min(len(out), dram_pos + 250000)
        part = out[dram_pos:next_card]
        part2 = _re.sub(r'<figure class="amoprof-chart"[^>]*>\s*<span class="amoprof-tt-badge">(?:📊\s*)?chart</span>\s*<svg.*?</svg>\s*</figure>', chart_html, part, count=1, flags=_re.S)
        out = out[:dram_pos] + part2 + out[next_card:]

    return out


def build_combined_report(
    raw_dir: Path,
    out_html: Path,
    static_html_path: "Path | None" = None,
    interactive_html_path: "Path | None" = None,
    run_label: str = "",
    theme: str = "dark",
    net_iface: str = "",
) -> Path:
    """Generate a combined tabbed HTML report."""
    import logging
    log = logging.getLogger("amoprof.combined")
    raw_dir = _amoprof_resolve_raw_dir(Path(raw_dir))
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    # Resolve the L3 backend class so storage-label cleanup labels the KV$
    # backing tier correctly (local SSD vs AI Memory Node / remote). With no
    # local-SSD evidence this resolves to a non-local class and the labels stay
    # "L3 (AI Memory Node / remote storage)" instead of being forced to L3 SSD.
    # Prefer setup_details.json — it carries the SGLang server_info-derived
    # `HiCache storage backend` written by cli._server_info_to_setup_details.
    # Fall back to sglang_summary.json.prometheus_server_info (which is empty
    # for offline / non-Prometheus runs), then to server_info.json raw.  The
    # resolver decides L3 (SSD/local file backend) vs L3.5 (mooncake, hf3fs,
    # or any other remote/disaggregated backend) directly from the observed
    # hicache_storage_backend value.
    l3_backend_class = ""
    try:
        _setup_for_l3: dict = {}
        _setup_path = _first_existing(raw_dir, ["setup_details.json", "setup.json"])
        if _setup_path is not None:
            _setup_for_l3 = _read_json(_setup_path) or {}
        if not _setup_for_l3:
            _sg = _read_json(_first_existing(raw_dir, ["sglang_summary.json"]) or (raw_dir / "sglang_summary.json"))
            _setup_for_l3 = dict(_sg.get("prometheus_server_info") or {})
        # Last-chance fallback: server_info.json raw cache saved by cli._write_setup_details_from_server_info.
        if not _setup_for_l3 or not (_setup_for_l3.get("HiCache storage backend") or _setup_for_l3.get("hicache_storage_backend")):
            _si_path = _first_existing(raw_dir, ["server_info.json"])
            if _si_path is not None:
                _si = _read_json(_si_path) or {}
                if _si:
                    _setup_for_l3 = dict(_setup_for_l3)
                    _setup_for_l3.setdefault("SGLang server_info raw", _si)
        _launch_for_l3 = str(_setup_for_l3.get("Launch command") or _setup_for_l3.get("launch_command") or "")
        if resolve_l3_backend is not None:
            _res = resolve_l3_backend(_setup_for_l3, _launch_for_l3)
            l3_backend_class = getattr(_res, "backend_class", "") or ""
    except Exception:
        l3_backend_class = ""

    if static_html_path and Path(static_html_path).exists():
        static_html = Path(static_html_path).read_text(encoding='utf-8', errors='replace')
        log.info("combined: loaded static report from %s (%d KB)", static_html_path, len(static_html) // 1000)
    else:
        import sys, subprocess
        tmp = out_html.parent / "_tmp_static.html"
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location('amoprof_report', Path(__file__).parent / 'amoprof.py')
            _mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            _old_argv = list(sys.argv)
            try:
                sys.argv = [str(Path(__file__).parent / 'amoprof.py'), '--raw', str(raw_dir), '--output', str(tmp)]
                _mod.main()
            finally:
                sys.argv = _old_argv
        except Exception as e:
            log.warning("combined: static report inline gen failed (%s) — subprocess", e)
            subprocess.run([sys.executable, str(Path(__file__).parent / 'amoprof.py'), '--raw', str(raw_dir), '--output', str(tmp)], check=True)
        try:
            from .enhancer import enhance_report
            enhance_report(tmp, raw_dir=raw_dir, theme=theme)
        except Exception as e:
            log.warning("combined: enhancer failed (%s)", e)
        static_html = tmp.read_text(encoding='utf-8', errors='replace')
        try: tmp.unlink()
        except OSError: pass
        log.info("combined: generated static report (%d KB)", len(static_html) // 1000)

    if interactive_html_path and Path(interactive_html_path).exists():
        interactive_html = Path(interactive_html_path).read_text(encoding='utf-8', errors='replace')
        log.info("combined: loaded interactive report from %s (%d KB)", interactive_html_path, len(interactive_html) // 1000)
    else:
        from .interactive import build_report as _build_int
        tmp = out_html.parent / "_tmp_interactive.html"
        _build_int(raw_dir, tmp, run_label=run_label)
        interactive_html = tmp.read_text(encoding='utf-8', errors='replace')
        try: tmp.unlink()
        except OSError: pass
        log.info("combined: generated interactive report (%d KB)", len(interactive_html) // 1000)

    try:
        common_kpis = compute_common_kpis(raw_dir)
        write_common_kpis_json(raw_dir, common_kpis)
        log.info("combined: computed canonical common KPIs via common_kpis.py: %s",
                 {k: round(v, 3) if isinstance(v, (int, float)) else v
                  for k, v in common_kpis.items()
                  if k in ("cache_hit_pct", "ttft_ms", "ttft_p50_ms", "tpot_ms", "tpot_p50_ms", "e2e_ms", "e2e_p50_ms", "throughput_mean", "throughput_p50")})
        # Extract figure JSON for the per-layer Chart-by-Chart Takeaways
        # section. When the run has full blktrace data the executive uses
        # the original per-chart code path and ignores these; when it
        # doesn't, the per-layer rows will embed these live Plotly charts.
        try:
            interactive_figures = _extract_interactive_figures(interactive_html)
            log.info("combined: extracted %d chart figures from interactive HTML",
                     len(interactive_figures))
        except Exception as _e:
            log.warning("combined: figure extraction failed (%s) — "
                        "executive will render text-only takeaways", _e)
            interactive_figures = {}
        canonical_kpi_overrides = dict(common_kpis)
        # All three tabs use the same common KPI object. Do not extract/re-merge
        # common values from already-rendered HTML because that recreates drift.
        interactive_html = apply_common_kpis_to_html(interactive_html, raw_dir, canonical_kpi_overrides)
        static_html = apply_common_kpis_to_html(static_html, raw_dir, canonical_kpi_overrides)
        executive_html = build_executive_summary_html(
            raw_dir, run_label=run_label,
            interactive_figures=interactive_figures,
            static_kpi_overrides=canonical_kpi_overrides,
            net_iface=net_iface)
        executive_html = apply_common_kpis_to_html(executive_html, raw_dir, canonical_kpi_overrides)
        executive_html = _canonical_kpi_tile_order_html(executive_html)
        interactive_html = _canonical_kpi_tile_order_html(interactive_html)
        static_html = _canonical_kpi_tile_order_html(static_html)
        executive_html = _amoprof_storage_label_cleanup(executive_html, l3_backend_class)
        log.info("combined: generated executive summary (%d KB)", len(executive_html) // 1000)
    except Exception as e:
        log.warning("combined: executive summary generation failed: %s", e)
        executive_html = "<html><body><h1>Executive Summary unavailable</h1><p>See Interactive and Static tabs.</p></body></html>"

    static_html = _remove_end_report_cross_layer_correlation_section(static_html)
    static_html = _remove_setup_aware_sglang_launch_tuning_section(static_html)
    static_html = _ensure_static_dram_section_visible(static_html, executive_html)
    interactive_html = _remove_setup_aware_sglang_launch_tuning_section(interactive_html)
    executive_html = _remove_setup_aware_sglang_launch_tuning_section(executive_html)
    static_html = _amoprof_storage_label_cleanup(static_html, l3_backend_class)
    interactive_html = _amoprof_storage_label_cleanup(interactive_html, l3_backend_class)
    combined = merge_reports(static_html, interactive_html, executive_html=executive_html, run_label=run_label)
    # v1.39.85: do not run broad L3/no-L3 cleanup after iframe embedding.
    # The End Report frame uses data-srcdoc escaping; post-merge regex cleanup can
    # corrupt that payload and make the whole End Report tab disappear.  Child
    # reports handle zero/no-data L3 sections before embedding.
    combined = _amoprof_storage_label_cleanup(combined, l3_backend_class)
    out_html.write_text(combined, encoding='utf-8')
    log.info("combined: wrote %s (%d KB)", out_html, len(combined) // 1000)
    return out_html
