"""
amoprof/report/interactive.py — Generate an interactive HTML report with
hover tooltips, using Plotly.js loaded from CDN.

Unlike the bundled static report which renders matplotlib PNGs, this report
uses Plotly.js for every time-series chart so that hovering any data point
shows the exact value at that timestamp. Charts are emitted as inline
<div> + JSON traces — Plotly.js is loaded once from a CDN.

Designed to consume the same `raw/` directory layout that the static report
uses, so the same collection pipeline feeds both.

Usage:
    from amoprof.report.interactive import build_report
    build_report(raw_dir=Path("/path/to/raw"),
                 out_html=Path("/path/to/report.html"))
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

# Plotly.js version pinned to a known-stable release with broad browser support.
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

# ─── Run-wide wall-clock anchor ──────────────────────────────────────────────
# Set once by build_report() from summary.json "t0_epoch" (Unix timestamp of
# the collection-window start).  All chart functions read this automatically
# via _ts_to_dates() and _layout() so every chart's X axis is anchored to the
# same real wall-clock time — matching the --start / --end the user specified.
#
# When 0 (default), charts fall back to elapsed time from 0.
_T0_EPOCH: float = 0.0


# ─── Data loading ────────────────────────────────────────────────────────────
def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _to_float(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _col(rows: list[dict], key: str) -> list[float]:
    return [_to_float(r.get(key)) for r in rows]


def _find_col(rows: list[dict], partial: str) -> str | None:
    """First column name containing `partial`. Useful for label-suffixed
    Prometheus metric column names like `sglang:cache_hit_rate`."""
    if not rows:
        return None
    for c in rows[0].keys():
        if partial in c:
            return c
    return None


def _time_axis_config(ts_seconds: list[float] | None = None,
                       max_ts: float | None = None,
                       t0_epoch: float | None = None) -> dict:
    """Return Plotly xaxis config.

    Uses the module-level _T0_EPOCH when t0_epoch is not explicitly given.
    When t0 > 0 labels show real wall-clock datetimes matching --start/--end.
    When t0 == 0 labels show elapsed time (HH:MM:SS / MM:SS / SS).
    """
    t0 = _T0_EPOCH if t0_epoch is None else t0_epoch
    if max_ts is None:
        if ts_seconds:
            try:
                max_ts = max(ts_seconds)
            except (ValueError, TypeError):
                max_ts = 0
        else:
            max_ts = 0

    cfg = {
        "gridcolor": "#cbd5e1",
        "zerolinecolor": "#94a3b8",
        "linecolor": "#475569",
        "tickcolor": "#475569",
        "tickfont": {"size": 12, "color": "#0f172a"},
        "type": "date",
    }

    if t0 > 0:
        cfg["tickformat"] = "%H:%M:%S"
        cfg["title"] = {"text": "Wall-clock time (UTC)", "font": {"size": 13}}
        cfg["hoverformat"] = "%Y-%m-%d %H:%M:%S UTC"
    elif max_ts >= 3600:
        cfg["tickformat"] = "%H:%M:%S"
        cfg["title"] = {"text": "Elapsed time (HH:MM:SS)", "font": {"size": 13}}
    elif max_ts >= 60:
        cfg["tickformat"] = "%M:%S"
        cfg["title"] = {"text": "Elapsed time (MM:SS)", "font": {"size": 13}}
    else:
        cfg["tickformat"] = "%Ss"
        cfg["title"] = {"text": "Elapsed time (sec)", "font": {"size": 13}}

    return cfg


def _ts_to_dates(ts_seconds: list[float],
                  t0_epoch: float | None = None) -> list[str]:
    """Convert elapsed-seconds-from-t0 into ISO 8601 datetime strings for Plotly.

    Uses the module-level _T0_EPOCH (set by build_report from summary.json)
    when t0_epoch is not explicitly given.

    When the resolved t0 is 0, anchors at 1970-01-01 so tick labels show
    elapsed time (00:00:00 .. HH:MM:SS).

    When t0 > 0 (a real Unix timestamp), anchors at the actual wall-clock
    start of the collection window so every chart aligns with the
    --start / --end timestamps the user specified.
    """
    from datetime import datetime, timezone, timedelta
    t0 = _T0_EPOCH if t0_epoch is None else t0_epoch
    base = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=t0)
    out: list[str] = []
    for t in ts_seconds:
        try:
            sec = float(t)
        except (TypeError, ValueError):
            sec = 0.0
        if sec < 0:
            sec = 0.0
        dt = base + timedelta(seconds=sec)
        out.append(dt.strftime("%Y-%m-%dT%H:%M:%S.") +
                   f"{dt.microsecond // 1000:03d}")
    return out


# ─── Chart builders — each returns a Plotly figure-spec dict ────────────────
def _layout(title: str, ylabel: str = "", ylabel2: str = "",
            height: int = 380, ts: list[float] | None = None,
            t0_epoch: float | None = None) -> dict:
    """Default Plotly layout.

    Uses the module-level _T0_EPOCH when t0_epoch is not explicitly given.
    When t0 > 0 the X axis shows real wall-clock datetimes so every chart
    lines up with the --start / --end window the user specified.
    """
    t0 = _T0_EPOCH if t0_epoch is None else t0_epoch
    layout = {
        "title": {
            "text": title,
            "font": {"size": 15, "color": "#0f172a",
                     "family": "Inter, system-ui, sans-serif"},
            "x": 0.02, "y": 0.96, "xanchor": "left",
        },
        "height": height,
        "margin": {"l": 64, "r": 80, "t": 56, "b": 50},
        "plot_bgcolor": "#f8fafc",
        "paper_bgcolor": "#ffffff",
        "font": {"color": "#0f172a", "size": 13, "family": "Inter, system-ui, sans-serif"},
        "xaxis": (_time_axis_config(ts, t0_epoch=t0) if ts is not None else {
            "title": {"text": "Wall-clock time (UTC)" if t0 > 0 else "Time",
                      "font": {"size": 13}},
            "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
            "linecolor": "#475569", "tickcolor": "#475569",
            "tickfont": {"size": 12, "color": "#0f172a"},
            "type": "date",
        }),
        "yaxis": {
            "title": {"text": ylabel, "font": {"size": 13}},
            "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
            "linecolor": "#475569", "tickcolor": "#475569",
            "tickfont": {"size": 12, "color": "#0f172a"},
        },
        "hovermode": "x unified",
        "hoverlabel": {"bgcolor": "#1e293b", "bordercolor": "#0f172a",
                        "font": {"color": "#f1f5f9", "size": 13}},
        "legend": {"orientation": "h", "yanchor": "bottom", "y": -0.28,
                    "x": 0, "font": {"size": 12, "color": "#0f172a"},
                    "bgcolor": "rgba(248,250,252,0.85)",
                    "bordercolor": "#cbd5e1", "borderwidth": 1},
    }
    if ylabel2:
        layout["yaxis2"] = {
            "title": {"text": ylabel2, "font": {"size": 13}},
            "overlaying": "y", "side": "right",
            "gridcolor": "transparent", "linecolor": "#475569",
            "tickfont": {"size": 12, "color": "#0f172a"},
        }
    return layout


def _chart_sglang_throughput(sglang: list[dict]) -> dict | None:
    """Chart: token throughput + cache hit rate."""
    if not sglang:
        return None
    gen_col = _find_col(sglang, "gen_throughput")
    cache_col = _find_col(sglang, "cache_hit_rate")
    if not gen_col:
        return None
    ts = _col(sglang, "time_sec")
    xs = _ts_to_dates(ts)
    traces = []
    traces.append({
        "x": xs, "y": _col(sglang, gen_col),
        "type": "scatter", "mode": "lines", "name": "Throughput (tok/s)",
        "line": {"color": "#22d3ee", "width": 2.2},
        "fill": "tozeroy", "fillcolor": "rgba(34,211,238,0.15)",
        "hovertemplate": "<b>%{y:.1f}</b> tok/s<extra></extra>",
    })
    if cache_col:
        cache_vals = [v * 100 if v <= 1 else v for v in _col(sglang, cache_col)]
        traces.append({
            "x": xs, "y": cache_vals,
            "type": "scatter", "mode": "lines", "name": "Cache hit %",
            "line": {"color": "#a78bfa", "width": 2, "dash": "dot"},
            "yaxis": "y2",
            "hovertemplate": "<b>%{y:.1f}%</b> hit<extra></extra>",
        })
    return {"data": traces,
            "layout": _layout("SGLang Token Throughput & Cache Hit Rate",
                              "Throughput (tok/s)", "Cache hit %", ts=ts)}


def _derive_nvme_columns(rows: list[dict]) -> list[dict]:
    """Derive per-sample rate columns that are missing from the raw CSV.

    The nvme_driver_timeseries.csv written by the Prometheus loader contains
    only *cumulative* kernel counters (rd_ios, wr_ios, rd_ms, wr_ms, io_ms,
    rd_bytes, wr_bytes).  The static report derives rate columns inside
    extract_metrics() but does not save them back to the CSV, so the
    interactive report sees all-zero values when it tries to read rd_iops,
    rd_bw_mbs, etc.

    This function adds the missing columns in-place, exactly mirroring the
    derivation logic in amoprof.py::extract_metrics():

      rd_iops    = Δrd_ios  / Δtime_sec          (reads completed per sec)
      wr_iops    = Δwr_ios  / Δtime_sec          (writes completed per sec)
      rd_bw_mbs  = Δrd_bytes / Δtime_sec / 2²⁰  (read MB/s from byte counter)
      wr_bw_mbs  = Δwr_bytes / Δtime_sec / 2²⁰  (write MB/s from byte counter)
      rd_lat_ms  = Δrd_ms   / Δrd_ios            (avg read latency ms)
      wr_lat_ms  = Δwr_ms   / Δwr_ios            (avg write latency ms)
      io_util_pct= Δio_ms   / (Δtime_sec × 1000) × 100  (% time device was busy)

    If the columns are already present (iostat path writes them directly),
    they are left untouched so this function is safe to call unconditionally.

    Returns the same list with new dict keys added (mutates dicts in-place).
    """
    if not rows:
        return rows

    # Check what's already present
    existing = set(rows[0].keys())
    needs_iops   = "rd_iops" not in existing and "wr_iops" not in existing
    needs_bw     = "rd_bw_mbs" not in existing and "wr_bw_mbs" not in existing
    needs_lat    = "rd_lat_ms" not in existing and "wr_lat_ms" not in existing
    needs_util   = "io_util_pct" not in existing
    has_ios      = "rd_ios" in existing
    has_bytes    = "rd_bytes" in existing
    has_ms       = "rd_ms" in existing
    has_io_ms    = "io_ms" in existing

    if not (needs_iops or needs_bw or needs_lat or needs_util):
        return rows  # everything already present

    for i, row in enumerate(rows):
        if i == 0:
            # First row: no prior sample to diff against — set all to 0
            if needs_iops:
                row["rd_iops"] = row.get("rd_iops", 0.0)
                row["wr_iops"] = row.get("wr_iops", 0.0)
            if needs_bw:
                row["rd_bw_mbs"] = row.get("rd_bw_mbs", 0.0)
                row["wr_bw_mbs"] = row.get("wr_bw_mbs", 0.0)
            if needs_lat:
                row["rd_lat_ms"] = row.get("rd_lat_ms", 0.0)
                row["wr_lat_ms"] = row.get("wr_lat_ms", 0.0)
            if needs_util:
                row["io_util_pct"] = row.get("io_util_pct", 0.0)
            continue

        prev = rows[i - 1]
        dt = _to_float(row.get("time_sec")) - _to_float(prev.get("time_sec"))
        if dt <= 0:
            dt = 1.0

        if needs_iops and has_ios:
            d_rd = max(_to_float(row.get("rd_ios")) - _to_float(prev.get("rd_ios")), 0)
            d_wr = max(_to_float(row.get("wr_ios")) - _to_float(prev.get("wr_ios")), 0)
            row["rd_iops"] = round(d_rd / dt, 2)
            row["wr_iops"] = round(d_wr / dt, 2)

        if needs_bw and has_bytes:
            d_rdb = max(_to_float(row.get("rd_bytes")) - _to_float(prev.get("rd_bytes")), 0)
            d_wrb = max(_to_float(row.get("wr_bytes")) - _to_float(prev.get("wr_bytes")), 0)
            row["rd_bw_mbs"] = round(d_rdb / dt / (1024 * 1024), 3)
            row["wr_bw_mbs"] = round(d_wrb / dt / (1024 * 1024), 3)
        elif needs_bw and needs_iops and has_ios:
            # No byte counters: estimate from IOPS × a typical NVMe block size.
            # We use the actual KV block size if we can get it, else 128 KB
            # (typical large-IO average for KV workloads).
            _bsz_mb = 0.128  # 128 KB default
            row["rd_bw_mbs"] = round(_to_float(row.get("rd_iops", 0)) * _bsz_mb, 3)
            row["wr_bw_mbs"] = round(_to_float(row.get("wr_iops", 0)) * _bsz_mb, 3)

        if needs_lat and has_ms and has_ios:
            d_rdm = max(_to_float(row.get("rd_ms")) - _to_float(prev.get("rd_ms")), 0)
            d_wrm = max(_to_float(row.get("wr_ms")) - _to_float(prev.get("wr_ms")), 0)
            d_rd  = max(_to_float(row.get("rd_ios")) - _to_float(prev.get("rd_ios")), 0)
            d_wr  = max(_to_float(row.get("wr_ios")) - _to_float(prev.get("wr_ios")), 0)
            row["rd_lat_ms"] = round(d_rdm / d_rd, 3) if d_rd > 0 else 0.0
            row["wr_lat_ms"] = round(d_wrm / d_wr, 3) if d_wr > 0 else 0.0

        if needs_util and has_io_ms:
            d_iomsec = max(_to_float(row.get("io_ms")) - _to_float(prev.get("io_ms")), 0)
            # io_ms is accumulated milliseconds the device was busy;
            # utilisation = busy_ms / wall_ms * 100
            row["io_util_pct"] = round(min(d_iomsec / (dt * 1000) * 100, 100), 2)

    return rows



    """Chart: token throughput + cache hit rate."""
    if not sglang:
        return None
    gen_col = _find_col(sglang, "gen_throughput")
    cache_col = _find_col(sglang, "cache_hit_rate")
    if not gen_col:
        return None
    ts = _col(sglang, "time_sec")
    xs = _ts_to_dates(ts)
    traces = []
    traces.append({
        "x": xs, "y": _col(sglang, gen_col),
        "type": "scatter", "mode": "lines", "name": "Throughput (tok/s)",
        "line": {"color": "#22d3ee", "width": 2.2},
        "fill": "tozeroy", "fillcolor": "rgba(34,211,238,0.15)",
        "hovertemplate": "<b>%{y:.1f}</b> tok/s<extra></extra>",
    })
    if cache_col:
        cache_vals = [v * 100 if v <= 1 else v for v in _col(sglang, cache_col)]
        traces.append({
            "x": xs, "y": cache_vals,
            "type": "scatter", "mode": "lines", "name": "Cache hit %",
            "line": {"color": "#a78bfa", "width": 2, "dash": "dot"},
            "yaxis": "y2",
            "hovertemplate": "<b>%{y:.1f}%</b> hit<extra></extra>",
        })
    return {"data": traces,
            "layout": _layout("SGLang Token Throughput & Cache Hit Rate",
                              "Throughput (tok/s)", "Cache hit %", ts=ts)}


def _chart_gpu(gpu: list[dict]) -> dict | None:
    """Chart: per-GPU utilization + memory used."""
    if not gpu:
        return None
    by_gpu: dict[str, dict] = {}
    for r in gpu:
        idx = str(r.get("gpu_idx", "0"))
        d = by_gpu.setdefault(idx, {"t": [], "util": [], "mem": [], "power": []})
        d["t"].append(_to_float(r.get("time_sec")))
        d["util"].append(_to_float(r.get("gpu_util")))
        d["mem"].append(_to_float(r.get("mem_used")))
        d["power"].append(_to_float(r.get("power")))
    colors = ["#22d3ee", "#a78bfa", "#f97316", "#22c55e",
              "#ef4444", "#3b82f6", "#eab308", "#ec4899"]
    traces = []
    # Collect all timestamps for axis-format selection
    all_ts: list[float] = []
    for d in by_gpu.values():
        all_ts.extend(d["t"])
    for i, (idx, d) in enumerate(sorted(by_gpu.items(),
                                         key=lambda x: int(x[0]) if x[0].isdigit() else 99)):
        traces.append({
            "x": _ts_to_dates(d["t"]), "y": d["util"],
            "type": "scatter", "mode": "lines", "name": f"GPU{idx} util",
            "line": {"color": colors[i % len(colors)], "width": 1.5},
            "hovertemplate": f"<b>GPU{idx}</b>: %{{y:.1f}}%<extra></extra>",
        })
    # Aggregate mem on secondary axis
    if by_gpu:
        n = len(next(iter(by_gpu.values()))["t"])
        avg_mem = [sum(by_gpu[k]["mem"][i] for k in by_gpu) / len(by_gpu)
                   for i in range(n)]
        avg_ts = next(iter(by_gpu.values()))["t"]
        traces.append({
            "x": _ts_to_dates(avg_ts), "y": avg_mem,
            "type": "scatter", "mode": "lines",
            "name": "Mean mem used (MB)",
            "line": {"color": "#7c3aed", "width": 2.5, "dash": "dashdot"},
            "yaxis": "y2",
            "hovertemplate": "<b>%{y:.0f}</b> MB used (mean)<extra></extra>",
        })
    return {"data": traces,
            "layout": _layout("GPU Utilization & HBM Memory (per GPU)",
                              "Utilization %", "HBM used (MB)",
                              height=420, ts=all_ts)}


def _chart_power(power: list[dict]) -> dict | None:
    if not power:
        return None
    ts = _col(power, "time_sec")
    xs = _ts_to_dates(ts)
    pw = _col(power, "gpu_power")
    if not any(pw):
        return None
    return {
        "data": [{
            "x": xs, "y": pw,
            "type": "scatter", "mode": "lines",
            "name": "Total GPU power (W)",
            "line": {"color": "#fb923c", "width": 2.2},
            "fill": "tozeroy", "fillcolor": "rgba(251,146,60,0.2)",
            "hovertemplate": "<b>%{y:.0f}</b> W total<extra></extra>",
        }],
        "layout": _layout("System GPU Power Draw", "Watts (sum of 8 GPUs)", ts=ts)
    }


def _chart_swap_storm(vmstat: list[dict]) -> dict | None:
    if not vmstat:
        return None
    ts = _col(vmstat, "time_sec")
    xs = _ts_to_dates(ts)
    # Convert cumulative counters to per-second rates
    def _rate(col: str) -> list[float]:
        v = _col(vmstat, col)
        if len(v) < 2: return []
        rates = [0.0]
        for i in range(1, len(v)):
            dt = ts[i] - ts[i-1]
            rates.append((v[i] - v[i-1]) / dt if dt > 0 else 0)
        return rates
    swpin  = _rate("pswpin")
    swpout = _rate("pswpout")
    pgmaj  = _rate("pgmajfault")
    # Render even when swap is zero — major faults and the zero-swap confirmation
    # are both valuable. Previously this returned None if swap counters were
    # all zero, making the chart silently disappear from the interactive report
    # while the static report still showed a placeholder.
    has_any_data = bool(any(swpin) or any(swpout) or any(pgmaj))
    # Build the chart — always render (even if all-zero) so the interactive
    # report matches the static report's coverage. Add a green annotation
    # confirming no swap occurred when swap counters are all-zero.
    layout = _layout("Swap Storm — Page Swap & Major Fault Rates",
                      "Pages / sec", "Major faults / sec", height=380, ts=ts)
    if not any(swpin) and not any(swpout):
        # Add a note that swap did not occur — this is a healthy state
        layout.setdefault("annotations", []).append({
            "text": "✅ No swap I/O detected — kernel memory was not under pressure",
            "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5, "xanchor": "center",
            "showarrow": False,
            "font": {"size": 14, "color": "#22c55e"},
        })
    return {
        "data": [
            {"x": xs, "y": swpin,  "type": "scatter", "mode": "lines",
             "name": "Swap-in pages/s",
             "line": {"color": "#3b82f6", "width": 2},
             "hovertemplate": "<b>%{y:.0f}</b> pages/s in<extra></extra>"},
            {"x": xs, "y": swpout, "type": "scatter", "mode": "lines",
             "name": "Swap-out pages/s",
             "line": {"color": "#ef4444", "width": 2},
             "fill": "tozeroy", "fillcolor": "rgba(239,68,68,0.15)",
             "hovertemplate": "<b>%{y:.0f}</b> pages/s out<extra></extra>"},
            {"x": xs, "y": pgmaj, "type": "scatter", "mode": "lines",
             "name": "Major faults/s", "yaxis": "y2",
             "line": {"color": "#a16207", "width": 1.5, "dash": "dot"},
             "hovertemplate": "<b>%{y:.1f}</b> major/s<extra></extra>"},
        ],
        "layout": layout,
    }


def _chart_nvme_iops(nvme: list[dict]) -> dict | None:
    if not nvme:
        return None
    ts = _col(nvme, "time_sec")
    xs = _ts_to_dates(ts)
    rd = _col(nvme, "rd_iops")
    wr = _col(nvme, "wr_iops")
    disc = _col(nvme, "disc_ios")
    traces = [
        {"x": xs, "y": rd, "type": "scatter", "mode": "lines",
         "name": "Read IOPS",
         "line": {"color": "#22c55e", "width": 1.8},
         "hovertemplate": "<b>%{y:.0f}</b> rd IOPS<extra></extra>"},
        {"x": xs, "y": wr, "type": "scatter", "mode": "lines",
         "name": "Write IOPS",
         "line": {"color": "#f43f5e", "width": 1.8},
         "fill": "tozeroy", "fillcolor": "rgba(244,63,94,0.12)",
         "hovertemplate": "<b>%{y:.0f}</b> wr IOPS<extra></extra>"},
    ]
    if any(disc):
        traces.append({
            "x": xs, "y": disc, "type": "scatter", "mode": "lines",
            "name": "Discard IOPS", "yaxis": "y2",
            "line": {"color": "#eab308", "width": 1.5, "dash": "dash"},
            "hovertemplate": "<b>%{y:.0f}</b> trim IOPS<extra></extra>",
        })
    return {"data": traces,
            "layout": _layout("NVMe I/O Rate (Read / Write / Trim)",
                              "IOPS", "Trim IOPS" if any(disc) else "", ts=ts)}


def _chart_nvme_bw(nvme: list[dict]) -> dict | None:
    if not nvme:
        return None
    ts = _col(nvme, "time_sec")
    xs = _ts_to_dates(ts)
    rd = _col(nvme, "rd_bw_mbs")
    wr = _col(nvme, "wr_bw_mbs")
    return {
        "data": [
            {"x": xs, "y": rd, "type": "scatter", "mode": "lines",
             "name": "Read MB/s",
             "line": {"color": "#22c55e", "width": 2},
             "hovertemplate": "<b>%{y:.1f}</b> MB/s read<extra></extra>"},
            {"x": xs, "y": wr, "type": "scatter", "mode": "lines",
             "name": "Write MB/s",
             "line": {"color": "#f43f5e", "width": 2},
             "fill": "tozeroy", "fillcolor": "rgba(244,63,94,0.12)",
             "hovertemplate": "<b>%{y:.1f}</b> MB/s write<extra></extra>"},
        ],
        "layout": _layout("NVMe Bandwidth (Read / Write)", "MB / sec", ts=ts)
    }


def _chart_nvme_latency(nvme: list[dict]) -> dict | None:
    if not nvme:
        return None
    ts = _col(nvme, "time_sec")
    xs = _ts_to_dates(ts)
    rd = _col(nvme, "rd_lat_ms")
    wr = _col(nvme, "wr_lat_ms")
    util = _col(nvme, "io_util_pct")
    return {
        "data": [
            {"x": xs, "y": rd, "type": "scatter", "mode": "lines",
             "name": "Read latency (ms)",
             "line": {"color": "#3b82f6", "width": 1.8},
             "hovertemplate": "<b>%{y:.3f}</b> ms<extra></extra>"},
            {"x": xs, "y": wr, "type": "scatter", "mode": "lines",
             "name": "Write latency (ms)",
             "line": {"color": "#ef4444", "width": 1.8},
             "hovertemplate": "<b>%{y:.3f}</b> ms<extra></extra>"},
            {"x": xs, "y": util, "type": "scatter", "mode": "lines",
             "name": "Device util %", "yaxis": "y2",
             "line": {"color": "#94a3b8", "width": 1.4, "dash": "dot"},
             "hovertemplate": "<b>%{y:.1f}</b>%% util<extra></extra>"},
        ],
        "layout": _layout("NVMe Latency & Device Utilization",
                          "Latency (ms)", "Util %", ts=ts)
    }


def _chart_kv_tiers(sglang: list[dict]) -> dict | None:
    if not sglang:
        return None
    ts = _col(sglang, "time_sec")
    xs = _ts_to_dates(ts)
    dev_col = _find_col(sglang, "cached_tokens_total[source=device]")
    host_col = _find_col(sglang, "cached_tokens_total[source=host]")
    storage_col = _find_col(sglang, "cached_tokens_total[source=storage]")
    traces = []
    if dev_col:
        traces.append({"x": xs, "y": _col(sglang, dev_col),
                       "type": "scatter", "mode": "lines", "stackgroup": "kv",
                       "name": "L1 Device (HBM)",
                       "line": {"color": "#7c3aed", "width": 0},
                       "fillcolor": "rgba(124,58,237,0.7)",
                       "hovertemplate": "<b>L1</b>: %{y:.0f} tok<extra></extra>"})
    if host_col:
        traces.append({"x": xs, "y": _col(sglang, host_col),
                       "type": "scatter", "mode": "lines", "stackgroup": "kv",
                       "name": "L2 Host (DRAM)",
                       "line": {"color": "#22d3ee", "width": 0},
                       "fillcolor": "rgba(34,211,238,0.65)",
                       "hovertemplate": "<b>L2</b>: %{y:.0f} tok<extra></extra>"})
    if storage_col:
        traces.append({"x": xs, "y": _col(sglang, storage_col),
                       "type": "scatter", "mode": "lines", "stackgroup": "kv",
                       "name": "L3 Storage (SSD)",
                       "line": {"color": "#f97316", "width": 0},
                       "fillcolor": "rgba(249,115,22,0.6)",
                       "hovertemplate": "<b>L3</b>: %{y:.0f} tok<extra></extra>"})

    # Many SGLang builds do not export tier-labeled cached_tokens_total.  In
    # that case do not leave the chart empty; derive an approximate SSD/L3
    # residency and movement timeline from backup/prefetch/load-back counters,
    # the same data used by the Eviction/Load-back chart below.
    if not traces:
        bk_col = _find_col(sglang, "backuped_tokens_total")
        pf_col = _find_col(sglang, "prefetched_tokens_total")
        lb_col = _find_col(sglang, "load_back_tokens_total")
        ev_col = _find_col(sglang, "evicted_tokens_total")
        if bk_col or pf_col or lb_col or ev_col:
            bk = _col(sglang, bk_col) if bk_col else [0.0] * len(ts)
            pf = _col(sglang, pf_col) if pf_col else [0.0] * len(ts)
            lb = _col(sglang, lb_col) if lb_col else [0.0] * len(ts)
            ev = _col(sglang, ev_col) if ev_col else [0.0] * len(ts)
            resident = [max(b - p - l, 0.0) for b, p, l in zip(bk, pf, lb)]
            if any(resident):
                traces.append({"x": xs, "y": resident, "type": "scatter",
                               "mode": "lines", "name": "Approx L3 SSD resident tokens",
                               "fill": "tozeroy", "fillcolor": "rgba(249,115,22,0.18)",
                               "line": {"color": "#f97316", "width": 2},
                               "hovertemplate": "<b>%{y:.0f}</b> approx resident tok<extra></extra>"})
            if any(ev):
                traces.append({"x": xs, "y": ev, "type": "scatter",
                               "mode": "lines", "name": "Cumulative evicted tokens",
                               "line": {"color": "#ef4444", "width": 1.6, "dash": "dot"},
                               "hovertemplate": "<b>%{y:.0f}</b> evicted tok<extra></extra>"})
    if not traces:
        return None
    return {"data": traces,
            "layout": _layout("KV Cache Tier / L3 Movement Occupancy",
                              "Tokens", height=400, ts=ts)}


def _chart_eviction(sglang: list[dict]) -> dict | None:
    if not sglang:
        return None
    ts = _col(sglang, "time_sec")
    xs = _ts_to_dates(ts)
    ev_col = _find_col(sglang, "evicted_tokens_total")
    lb_col = _find_col(sglang, "load_back_tokens_total")
    bk_col = _find_col(sglang, "backuped_tokens_total")
    if not (ev_col or lb_col or bk_col):
        return None
    def _rate(col: str) -> list[float]:
        if not col: return [0.0] * len(ts)
        v = _col(sglang, col)
        out = [0.0]
        for i in range(1, len(v)):
            dt = ts[i] - ts[i-1]
            out.append(max((v[i] - v[i-1]) / dt, 0) if dt > 0 else 0)
        return out
    traces = []
    if ev_col:
        traces.append({"x": xs, "y": _rate(ev_col),
                       "type": "scatter", "mode": "lines", "name": "Evicted tok/s",
                       "line": {"color": "#ef4444", "width": 2},
                       "fill": "tozeroy", "fillcolor": "rgba(239,68,68,0.15)",
                       "hovertemplate": "<b>%{y:.0f}</b> tok/s evicted<extra></extra>"})
    if lb_col:
        traces.append({"x": xs, "y": _rate(lb_col),
                       "type": "scatter", "mode": "lines", "name": "Load-back tok/s",
                       "line": {"color": "#22c55e", "width": 2},
                       "hovertemplate": "<b>%{y:.0f}</b> tok/s loaded<extra></extra>"})
    if bk_col:
        traces.append({"x": xs, "y": _rate(bk_col),
                       "type": "scatter", "mode": "lines", "name": "Backup tok/s",
                       "line": {"color": "#3b82f6", "width": 1.6, "dash": "dot"},
                       "hovertemplate": "<b>%{y:.0f}</b> tok/s backup<extra></extra>"})
    return {"data": traces,
            "layout": _layout("KV Cache Eviction / Load-back / Backup Rates",
                              "Tokens / sec", ts=ts)}


def _chart_request_size_dist(reqsize: list[dict]) -> dict | None:
    """Histogram: read/write/trim sizes by bucket."""
    if not reqsize:
        return None
    buckets = ["≤4KB", "4-16KB", "16-64KB", "64-256KB", "256KB-1MB", ">1MB"]
    counts: dict[str, dict[str, int]] = {b: {"read": 0, "write": 0, "trim": 0}
                                          for b in buckets}
    def _bucket_from_size(sz):
        try: sz = float(sz)
        except Exception: return ""
        if sz <= 4*1024: return "≤4KB"
        if sz <= 16*1024: return "4-16KB"
        if sz <= 64*1024: return "16-64KB"
        if sz <= 256*1024: return "64-256KB"
        if sz <= 1024*1024: return "256KB-1MB"
        return ">1MB"
    def _op_norm(op):
        o = str(op).lower()
        if o.startswith('r'): return 'read'
        if o.startswith('w'): return 'write'
        if o.startswith(('t','d')): return 'trim'
        return o
    for r in reqsize:
        bucket = r.get("size_bucket", "") or _bucket_from_size(r.get("size_bytes", r.get("bytes", r.get("size", 0))))
        op = _op_norm(r.get("op", r.get("type", r.get("operation", ""))))
        if bucket in counts and op in counts[bucket]:
            counts[bucket][op] += 1
    if not any(sum(counts[b].values()) for b in buckets):
        return None
    return {
        "data": [
            {"x": buckets, "y": [counts[b]["read"]  for b in buckets],
             "type": "bar", "name": "Read",
             "marker": {"color": "#22c55e", "line": {"color": "#0f172a", "width": 1}},
             "hovertemplate": "<b>Read</b> %{x}: %{y:,} requests<extra></extra>"},
            {"x": buckets, "y": [counts[b]["write"] for b in buckets],
             "type": "bar", "name": "Write",
             "marker": {"color": "#f43f5e", "line": {"color": "#0f172a", "width": 1}},
             "hovertemplate": "<b>Write</b> %{x}: %{y:,} requests<extra></extra>"},
            {"x": buckets, "y": [counts[b]["trim"]  for b in buckets],
             "type": "bar", "name": "Trim",
             "marker": {"color": "#eab308", "line": {"color": "#0f172a", "width": 1}},
             "hovertemplate": "<b>Trim</b> %{x}: %{y:,} requests<extra></extra>"},
        ],
        "layout": {**_layout("Request Size Distribution by Operation",
                              "Number of requests"),
                   "barmode": "group",
                   "xaxis": {"title": {"text": "Request size bucket"},
                             "tickfont": {"size": 12, "color": "#0f172a"}}}
    }


def _chart_iat_dist(iat: list[dict]) -> dict | None:
    if not iat:
        return None
    by_op: dict[str, dict[str, int]] = {}
    bins_order: list[str] = []
    for r in iat:
        op = r.get("op", "")
        label = r.get("bin_label", "")
        cnt = int(_to_float(r.get("count", 0)))
        by_op.setdefault(op, {})[label] = cnt
        if label not in bins_order:
            bins_order.append(label)
    if not by_op:
        return None
    palette = {"read": "#22c55e", "write": "#f43f5e", "trim": "#eab308"}
    traces = []
    for op, bins in by_op.items():
        traces.append({
            "x": bins_order,
            "y": [bins.get(b, 0) for b in bins_order],
            "type": "bar", "name": op,
            "marker": {"color": palette.get(op, "#94a3b8"),
                        "line": {"color": "#0f172a", "width": 1}},
            "hovertemplate": f"<b>{op}</b> %{{x}}: %{{y:,}} reqs<extra></extra>"
        })
    return {"data": traces,
            "layout": {**_layout("Inter-Arrival Time Distribution",
                                 "Number of requests"),
                       "barmode": "group",
                       "xaxis": {"title": {"text": "IAT bucket"},
                                 "tickfont": {"size": 12, "color": "#0f172a"}}}}


def _chart_temporal_rwt(tp: list[dict]) -> dict | None:
    if not tp:
        return None
    ts = _col(tp, "window_start_sec") or _col(tp, "time_sec") or _col(tp, "start")
    def _first(cols):
        for c in cols:
            vals = _col(tp, c)
            if vals and any(vals):
                return vals
        return [0.0] * len(tp)
    rd_raw = _first(["read", "read_bytes", "rd_bytes"]); wr_raw = _first(["write", "write_bytes", "wr_bytes"]); tr_raw = _first(["trim", "trim_bytes", "discard", "discard_bytes"])
    scale = 1e6 if max(rd_raw + wr_raw + tr_raw + [0]) > 1e4 else 1.0
    rd = [v / scale for v in rd_raw]; wr = [v / scale for v in wr_raw]; tr = [v / scale for v in tr_raw]
    if not any(rd) and not any(wr) and not any(tr):
        return None
    return {
        "data": [
            {"x": ts, "y": rd, "type": "scatter", "mode": "lines",
             "name": "Read MB/window", "stackgroup": "rwt",
             "fillcolor": "rgba(34,197,94,0.6)", "line": {"color": "#22c55e"},
             "hovertemplate": "<b>%{y:.1f}</b> MB read<extra></extra>"},
            {"x": ts, "y": wr, "type": "scatter", "mode": "lines",
             "name": "Write MB/window", "stackgroup": "rwt",
             "fillcolor": "rgba(244,63,94,0.55)", "line": {"color": "#f43f5e"},
             "hovertemplate": "<b>%{y:.1f}</b> MB write<extra></extra>"},
            {"x": ts, "y": tr, "type": "scatter", "mode": "lines",
             "name": "Trim MB/window", "stackgroup": "rwt",
             "fillcolor": "rgba(234,179,8,0.5)", "line": {"color": "#eab308"},
             "hovertemplate": "<b>%{y:.1f}</b> MB trim<extra></extra>"},
        ],
        "layout": _layout("R/W/T Bytes per 10-sec Window (stacked)",
                          "MB per window", height=380)
    }


def _chart_bw_per_stream(bps: list[dict]) -> dict | None:
    if not bps:
        return None
    palette = {"read": "#22c55e", "write": "#f43f5e", "trim": "#eab308"}
    traces = []
    for op in ("read", "write", "trim"):
        rows = [r for r in bps if r.get("op") == op]
        if not rows: continue
        rows.sort(key=lambda r: _to_float(r.get("bandwidth_mib_s")), reverse=True)
        rows = rows[:20]
        labels = [r.get("stream", "?") for r in rows]
        bws = [_to_float(r.get("bandwidth_mib_s")) for r in rows]
        bytes_ = [_to_float(r.get("bytes")) / 1e6 for r in rows]
        traces.append({
            "y": labels, "x": bws,
            "type": "bar", "orientation": "h", "name": op.title(),
            "marker": {"color": palette.get(op, "#94a3b8"),
                        "line": {"color": "#0f172a", "width": 1}},
            "customdata": bytes_,
            "hovertemplate": (f"<b>{op}</b><br>"
                              "Stream: %{y}<br>"
                              "Bandwidth: <b>%{x:.2f} MiB/s</b><br>"
                              "Total: %{customdata:.1f} MB<extra></extra>"),
        })
    if not traces:
        return None
    return {"data": traces,
            "layout": {**_layout("Bandwidth per Stream (top 20 per op)",
                                 "Stream (pid:comm)", height=520),
                       "xaxis": {"title": {"text": "MiB / sec"},
                                 "tickfont": {"size": 12, "color": "#0f172a"}},
                       "barmode": "group"}}


def _chart_dram_bw(amduprof_txt: Path) -> dict | None:
    # The collector writes both amduprof_pcm_raw.csv and amduprof_pcm_raw.txt.
    # Try the supplied path first, then the .csv variant.
    raw_path: Path | None = None
    candidates = [amduprof_txt, amduprof_txt.with_suffix(".csv")]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            raw_path = candidate
            break
    if raw_path is None:
        return None

    rd_bw, wr_bw, tot_bw = [], [], []
    # Column indices resolved from the header line — AMDuProf CSVs have many
    # columns before "Total Mem Bw" (RecordId, Package, Core, Thread, cache
    # hit-rates, …).  Previously the parser assumed fixed indices [0,1,2] which
    # produced RecordId/zeros instead of the actual bandwidth values.
    col_total: int | None = None
    col_rd:    int | None = None
    col_wr:    int | None = None
    in_data = False

    for line in raw_path.read_text(errors="replace").splitlines():
        ll = line.strip().rstrip(",")
        if not ll:
            continue

        # Header detection — accept both "Total Mem RdBw" and bare "RdBw"
        if "Total Mem Bw" in ll and ("Total Mem RdBw" in ll or "RdBw" in ll):
            cols = [c.strip() for c in ll.split(",")]
            # Resolve indices for each BW column (case-insensitive substring)
            for i, c in enumerate(cols):
                cl = c.lower()
                if col_total is None and "total mem bw" in cl:
                    col_total = i
                elif col_rd is None and ("total mem rdbw" in cl or
                                         (cl == "rdbw") or
                                         ("mem rdbw" in cl)):
                    col_rd = i
                elif col_wr is None and ("total mem wrbw" in cl or
                                         (cl == "wrbw") or
                                         ("mem wrbw" in cl)):
                    col_wr = i
            if col_total is not None:
                in_data = True
            continue

        if not in_data:
            continue

        # Data rows: first character must be a digit (catches RecordId rows,
        # timestamp rows, etc.) and stop on section separators
        if not ll[0].isdigit():
            in_data = False
            continue

        parts = [_to_float(p) for p in ll.split(",")]
        n = len(parts)

        # Use header-resolved indices when available; fall back to [0,1,2]
        # only if the header didn't have enough columns (shouldn't happen).
        i_tot = col_total if col_total is not None and col_total < n else 0
        i_rd  = col_rd    if col_rd    is not None and col_rd    < n else 1
        i_wr  = col_wr    if col_wr    is not None and col_wr    < n else 2

        if n > max(i_tot, i_rd, i_wr):
            tot_bw.append(parts[i_tot])
            rd_bw.append(parts[i_rd])
            wr_bw.append(parts[i_wr])

    if not tot_bw:
        return None

    # Use actual AMDuProf sampling interval (1.2 s default) so the DRAM BW
    # x-axis aligns with all other charts that share the same _T0_EPOCH anchor.
    interval_s = 1.2
    ts_elapsed = [i * interval_s for i in range(len(tot_bw))]
    xs = _ts_to_dates(ts_elapsed)   # picks up _T0_EPOCH automatically
    return {
        "data": [
            {"x": xs, "y": tot_bw, "type": "scatter", "mode": "lines",
             "name": "Total (GB/s)",
             "line": {"color": "#a78bfa", "width": 2.2},
             "hovertemplate": "<b>%{y:.2f}</b> GB/s total<extra></extra>"},
            {"x": xs, "y": rd_bw, "type": "scatter", "mode": "lines",
             "name": "Read (GB/s)",
             "line": {"color": "#22c55e", "width": 1.8},
             "hovertemplate": "<b>%{y:.2f}</b> GB/s read<extra></extra>"},
            {"x": xs, "y": wr_bw, "type": "scatter", "mode": "lines",
             "name": "Write (GB/s)",
             "line": {"color": "#f43f5e", "width": 1.8},
             "hovertemplate": "<b>%{y:.2f}</b> GB/s write<extra></extra>"},
        ],
        "layout": _layout("System DRAM Bandwidth (AMDuProf PCM)",
                          "GB / sec", ts=ts_elapsed)
    }


def _chart_hot_regions(hr: list[dict]) -> dict | None:
    if not hr:
        return None
    palette = {"read": "#22c55e", "write": "#f43f5e", "trim": "#eab308"}
    traces = []
    for op in ("read", "write", "trim"):
        rows = [r for r in hr if r.get("op") == op][:30]
        if not rows: continue
        traces.append({
            "x": [_to_float(r.get("lba_bucket_start")) / 1e9 for r in rows],
            "y": [_to_float(r.get("bytes")) / 1e6 for r in rows],
            "type": "scatter", "mode": "markers", "name": op.title(),
            "marker": {"color": palette.get(op),
                        "size": 12, "opacity": 0.7,
                        "line": {"color": "#0f172a", "width": 1}},
            "hovertemplate": (f"<b>{op}</b><br>"
                              "LBA: %{x:.2f} GB<br>"
                              "Bytes: <b>%{y:.1f} MB</b><extra></extra>"),
        })
    if not traces:
        return None
    return {"data": traces,
            "layout": {**_layout("Hot LBA Regions (top 30 per op)",
                                 "Bytes accessed (MB)", height=400),
                       "xaxis": {"title": {"text": "Disk offset (GB)"},
                                 "tickfont": {"size": 12, "color": "#0f172a"}}}}


# ─── KPI tile builder ────────────────────────────────────────────────────────
def _chart_percentile_timeseries(pct_ts: dict, metric_key: str) -> dict | None:
    """Time-series chart: how P50/P90/P99 evolve across the Prometheus window.

    Consumes the `sglang_percentiles_timeseries.json` file written by
    amoprof.percentiles.fetch_percentile_timeseries.

    metric_key is one of: "ttft", "itl", "e2e", "prompt_tokens", "output_tokens".

    Returns None if the metric isn't present (e.g. histogram buckets weren't
    scraped, or analyze ran without --prometheus).
    """
    if not pct_ts:
        return None
    block = pct_ts.get(metric_key)
    if not block or not block.get("time_sec"):
        return None
    ts = block["time_sec"]
    xs = _ts_to_dates(ts)
    traces: list[dict] = []
    # Filter out None values per-series so Plotly doesn't draw gaps incorrectly
    def _clean_series(ys: list) -> list:
        return [None if (y is None or (isinstance(y, float) and y != y)) else float(y)
                for y in ys]
    series_specs = [
        ("p99", "P99", "#ef4444", 2.0, "solid"),
        ("p90", "P90", "#f59e0b", 1.8, "solid"),
        ("p50", "P50 (median)", "#22d3ee", 1.6, "dot"),
    ]
    for key, label, color, width, dash in series_specs:
        ys = block.get(key)
        if not ys:
            continue
        traces.append({
            "x": xs, "y": _clean_series(ys),
            "type": "scatter", "mode": "lines",
            "name": label,
            "line": {"color": color, "width": width, "dash": dash},
            "connectgaps": False,
            "hovertemplate": (f"<b>{label}</b>: "
                              f"%{{y:,.2f}} {block.get('unit', '')}"
                              f"<extra></extra>"),
        })
    if not traces:
        return None
    unit_label = block.get("unit", "")
    metric_label = block.get("label", metric_key.upper())
    return {
        "data": traces,
        "layout": _layout(
            f"{metric_label} — P50 / P90 / P99 over time (Prometheus histogram_quantile)",
            f"{unit_label} (log scale)",
            height=380, ts=ts),
        # Override Y to log; tail latencies span 1-2 decades
        "_yaxis_override": {"type": "log", "tickformat": ",.0f"},
    }


def _apply_yaxis_override(spec: dict | None) -> dict | None:
    """Apply ._yaxis_override into the layout's yaxis if present."""
    if not spec:
        return spec
    override = spec.pop("_yaxis_override", None)
    if override and "layout" in spec and "yaxis" in spec["layout"]:
        spec["layout"]["yaxis"].update(override)
    elif override and "layout" in spec:
        spec["layout"]["yaxis"] = override
    return spec


def _chart_bench_latency_percentiles(bench: dict) -> dict | None:
    """Grouped bar chart: TTFT / ITL / E2E latency at Mean, P50, P90, P99, Max.

    This is the headline view of per-request latency from a benchmark
    summary. Y-axis uses log scale because P99/Max often dwarfs Mean
    (e.g. user's data: avg TTFT 26s, max TTFT 50s — only ~2× spread —
    but ITL avg 1.9s vs max 38s is 20× spread).
    """
    if not bench:
        return None
    # (metric, [Mean, P50, P90, P99, Max] keys)
    series = [
        ("TTFT (s)",  ["avg_ttft_s", "median_ttft_s", "p90_ttft_s", "p99_ttft_s", "max_ttft_s"]),
        ("ITL (s)",   ["avg_itl_s",  "median_itl_s",  "p90_itl_s",  "p99_itl_s",  "max_itl_s"]),
        ("E2E (s)",   ["avg_latency_s", "median_latency_s", "p90_latency_s",
                       "p99_latency_s", "max_latency_s"]),
    ]
    stat_labels = ["Mean", "P50", "P90", "P99", "Max"]
    stat_colors = ["#22d3ee", "#a78bfa", "#f59e0b", "#fb923c", "#ef4444"]
    have_any = False
    traces = []
    metric_names = [s[0] for s in series]
    for i, stat_label in enumerate(stat_labels):
        ys = []
        for _, keys in series:
            v = bench.get(keys[i])
            ys.append(float(v) if v is not None else 0.0)
            if v is not None:
                have_any = True
        traces.append({
            "x": metric_names, "y": ys,
            "type": "bar", "name": stat_label,
            "marker": {"color": stat_colors[i],
                        "line": {"color": "#0f172a", "width": 1}},
            "hovertemplate": (f"<b>{stat_label}</b><br>"
                              "%{x}: <b>%{y:.3f} sec</b><extra></extra>"),
        })
    if not have_any:
        return None
    return {
        "data": traces,
        "layout": {**_layout("Per-Request Latency — Distribution Across Percentiles",
                              "seconds (log scale)", height=420),
                   "barmode": "group",
                   "yaxis": {"type": "log",
                             "title": {"text": "seconds (log scale)",
                                        "font": {"size": 13}},
                             "gridcolor": "#cbd5e1",
                             "tickfont": {"size": 12, "color": "#0f172a"}},
                   "xaxis": {"title": {"text": "Latency metric",
                                       "font": {"size": 13}},
                             "tickfont": {"size": 12, "color": "#0f172a"}}}
    }


def _chart_bench_token_lengths(bench: dict) -> dict | None:
    """Grouped bar chart: prompt vs output token lengths at Mean, P90, P99, Max."""
    if not bench:
        return None
    series = [
        ("Prompt tokens", ["avg_prompt_tokens", "p90_prompt_tokens",
                            "p99_prompt_tokens", "max_prompt_tokens"]),
        ("Output tokens", ["avg_output_tokens", "p90_output_tokens",
                            "p99_output_tokens", "max_output_tokens"]),
    ]
    stat_labels = ["Mean", "P90", "P99", "Max"]
    stat_colors = ["#22c55e", "#f59e0b", "#fb923c", "#ef4444"]
    have_any = False
    traces = []
    metric_names = [s[0] for s in series]
    for i, stat_label in enumerate(stat_labels):
        ys = []
        for _, keys in series:
            v = bench.get(keys[i])
            ys.append(float(v) if v is not None else 0.0)
            if v is not None:
                have_any = True
        traces.append({
            "x": metric_names, "y": ys,
            "type": "bar", "name": stat_label,
            "marker": {"color": stat_colors[i],
                        "line": {"color": "#0f172a", "width": 1}},
            "hovertemplate": (f"<b>{stat_label}</b><br>"
                              "%{x}: <b>%{y:,.0f} tokens</b><extra></extra>"),
        })
    if not have_any:
        return None
    return {
        "data": traces,
        "layout": {**_layout("Prompt & Output Token Length Distribution",
                              "tokens", height=380),
                   "barmode": "group",
                   "yaxis": {"type": "log",
                             "title": {"text": "tokens (log scale)",
                                        "font": {"size": 13}},
                             "gridcolor": "#cbd5e1",
                             "tickfont": {"size": 12, "color": "#0f172a"}},
                   "xaxis": {"title": {"text": "Token sequence",
                                       "font": {"size": 13}},
                             "tickfont": {"size": 12, "color": "#0f172a"}}}
    }


def _chart_bench_throughput_breakdown(bench: dict) -> dict | None:
    """Side-by-side bars for input vs output tok/s, plus request rate.

    Shows the asymmetry typical of long-prompt/short-output workloads
    (user's data: 9748 in tok/s vs 6.82 out tok/s — 1430× ratio).
    """
    if not bench:
        return None
    in_tps  = bench.get("input_tok_per_s")
    out_tps = bench.get("output_tok_per_s")
    if in_tps is None and out_tps is None:
        return None
    traces = [{
        "x": ["Input tok/s", "Output tok/s"],
        "y": [float(in_tps or 0), float(out_tps or 0)],
        "type": "bar",
        "marker": {
            "color": ["#3b82f6", "#22c55e"],
            "line": {"color": "#0f172a", "width": 1.5},
        },
        "text": [f"{float(in_tps or 0):,.1f}",
                  f"{float(out_tps or 0):,.2f}"],
        "textposition": "outside",
        "textfont": {"size": 14, "color": "#0f172a"},
        "hovertemplate": ("<b>%{x}</b>: <b>%{y:,.2f}</b> tokens/sec<extra></extra>"),
        "showlegend": False,
    }]
    ratio = ""
    if in_tps and out_tps and float(out_tps) > 0:
        ratio = f" — input is {float(in_tps)/float(out_tps):.0f}× output"
    return {
        "data": traces,
        "layout": {**_layout("Token Throughput — Input vs Output" + ratio,
                              "tokens/sec (log scale)", height=320),
                   "yaxis": {"type": "log",
                             "title": {"text": "tokens / sec (log scale)",
                                        "font": {"size": 13}},
                             "gridcolor": "#cbd5e1",
                             "tickfont": {"size": 12, "color": "#0f172a"}},
                   "xaxis": {"tickfont": {"size": 13, "color": "#0f172a"}}}
    }


def _chart_bench_latency_ranges(bench: dict) -> dict | None:
    """Box-and-whisker style chart: visualize the spread per metric.

    Plotly's 'box' trace type can be fed pre-computed percentiles via the
    q1/median/q3/lowerfence/upperfence properties — perfect for our case
    where we have summary stats but not the underlying samples.
    """
    if not bench:
        return None
    boxes = []
    palette = {"TTFT": "#22d3ee", "ITL": "#a78bfa", "E2E latency": "#f59e0b"}
    for metric, prefix in [("TTFT", "ttft"), ("ITL", "itl"),
                            ("E2E latency", "latency")]:
        med  = bench.get(f"median_{prefix}_s")
        p90  = bench.get(f"p90_{prefix}_s")
        p99  = bench.get(f"p99_{prefix}_s")
        mx   = bench.get(f"max_{prefix}_s")
        avg  = bench.get(f"avg_{prefix}_s")
        if med is None or p90 is None or p99 is None:
            continue
        # Use median as the "center", P90 as Q3, P99 as upperfence, Max as outlier.
        # Q1 is approximated as max(0, median - (P90 - median)) for visual symmetry
        # — we don't have the actual Q1 but this gives a reasonable lower whisker.
        q1_approx = max(0.0, 2 * float(med) - float(p90))
        boxes.append({
            "name": metric,
            "type": "box",
            "q1": [q1_approx],
            "median": [float(med)],
            "q3": [float(p90)],
            "lowerfence": [q1_approx * 0.5],
            "upperfence": [float(p99)],
            "mean": [float(avg)] if avg is not None else None,
            "sd":   [0],
            "marker": {"color": palette.get(metric, "#94a3b8"),
                        "line": {"color": "#0f172a", "width": 1}},
            "boxpoints": False,
            "hovertemplate": (f"<b>{metric}</b><br>"
                              f"Mean: {avg or 0:.2f}s · P50: {med:.2f}s · "
                              f"P90: {p90:.2f}s · P99: {p99:.2f}s · "
                              f"Max: {mx or 0:.2f}s<extra></extra>"),
        })
    if not boxes:
        return None
    return {
        "data": boxes,
        "layout": {**_layout(
            "Latency Spread (Box = P50→P90, Whiskers = ~Q1→P99)",
            "seconds (log scale)", height=380),
                   "yaxis": {"type": "log",
                             "title": {"text": "seconds (log scale)",
                                        "font": {"size": 13}},
                             "gridcolor": "#cbd5e1",
                             "tickfont": {"size": 12, "color": "#0f172a"}}}
    }



def _kpi_tile(label: str, value: str, unit: str = "",
              note: str = "", color: str = "#0f172a") -> str:
    return f"""
<div class="kpi-tile" title="{note}">
  <div class="kpi-label">{label}</div>
  <div class="kpi-value" style="color:{color}">{value}<span class="kpi-unit">{unit}</span></div>
  {f'<div class="kpi-note">{note}</div>' if note else ''}
</div>"""


def _section(title: str, chart_id: str, fig: dict | None,
             note: str = "") -> str:
    if fig is None:
        return f"""
<section class="card">
  <h2>{title}</h2>
  <div class="no-data">No data available for this chart.<br>
    <small>{note or 'Check that the corresponding collector ran during capture.'}</small>
  </div>
</section>"""
    fig_json = json.dumps(fig, default=str)
    return f"""
<section class="card">
  <h2>{title}</h2>
  <div id="{chart_id}" class="plot"></div>
  {f'<div class="caption">{note}</div>' if note else ''}
  <script>
    (function() {{
      var fig = {fig_json};
      Plotly.newPlot('{chart_id}', fig.data, fig.layout,
        {{responsive:true, displayModeBar:true, displaylogo:false,
          modeBarButtonsToRemove:['select2d','lasso2d']}});
    }})();
  </script>
</section>"""

def _layer_header(layer_id: str, title: str, note: str, color: str) -> str:
    return f"""
<section class="card layer-header" id="{layer_id}" style="background:{color};color:#fff;border-color:{color}">
  <h2 style="color:#fff;border-bottom:1px solid rgba(255,255,255,.35)">{title}</h2>
  <div style="font-size:13px;opacity:.95">{note}</div>
</section>"""


def _setup_section(setup: dict) -> str:
    import html as _html
    rows = []
    for k, v in setup.items():
        key_l = str(k).lower()
        klass = "setup-row-defaulted" if key_l in ("default profile", "defaulted fields") else ""
        rows.append(
            f'<tr class="{klass}"><td class="setup-key">{_html.escape(str(k))}</td>'
            f'<td class="setup-value">{_html.escape(str(v))}</td></tr>'
        )
    return f"""
<section class="card setup-panel">
  <h2>⚙️ Setup / Server Configuration</h2>
  <div class="setup-grid">
    <div><table class="setup-table"><tbody>{''.join(rows)}</tbody></table></div>
    <div class="setup-info-box">
      <div class="setup-info-title">How setup fields were populated</div>
      <p><b>Auto-detected:</b> read from <code>sglang_summary.json</code>, Prometheus labels, and cache config labels when present.</p>
      <p><b>Manual override:</b> <code>setup_details.json</code> or <code>setup.json</code> values override auto-detection.</p>
      <p><b>Defaults:</b> remaining missing SGLang launch parameters use the built-in DeepSeek-R1-70B HiCache reference profile and are listed under <code>Defaulted fields</code>.</p>
    </div>
  </div>
</section>"""


def _stack_overview_section() -> str:
    return """
<section class="card" style="border-left:4px solid #0f766e">
  <h2>🍰 AI Workload Stack — Layered Memory-Tier View</h2>
  <div class="stack-cake">
    <div class="stack-row full a5"><b>A5 · Application Layer</b><span>benchmarks, prompt/output mix, TTFT, TPOT, P99 request latency</span></div>
    <div class="stack-row pair"><div class="a4"><b>A4 · Inference Runtime</b><span>SGLang scheduling, batching, KV$ eviction/load-back</span></div><div class="model"><b>AI Models</b><span>model config, dtype, context length, KV$/token</span></div></div>
    <div class="stack-row trio"><div class="l1"><b>A3/A2/A1 · L1 HBM</b><span>CUDA kernels, GPU driver, HBM capacity/BW</span></div><div class="l2"><b>A3/A2/A1 · L2 DRAM</b><span>OS memory manager, page faults, swap, DRAM BW</span></div><div class="l3"><b>A3/A2/A1 · L3 SSD</b><span>OS block layer, NVMe driver, NAND, blktrace/biosnoop</span></div></div>
  </div>
  <div class="caption">Report sections below are ordered to match this layered view.</div>
</section>"""


# ─── Main entry ──────────────────────────────────────────────────────────────
def build_report(raw_dir: Path, out_html: Path,
                 run_label: str = "") -> Path:
    """Build the interactive HTML report from a raw/ directory.

    Returns the path to the written HTML file.
    """
    global _T0_EPOCH
    raw_dir = Path(raw_dir)
    out_html = Path(out_html)

    # Load all data
    sglang_ts   = _read_csv(raw_dir / "sglang_timeseries.csv")
    sglang_sum  = _read_json(raw_dir / "sglang_summary.json")
    gpu_ts      = _read_csv(raw_dir / "gpu_timeseries.csv")
    gpu_sum     = _read_json(raw_dir / "gpu_summary.json")
    power_ts    = _read_csv(raw_dir / "power_timeseries.csv")
    vmstat_ts   = _read_csv(raw_dir / "vmstat_timeseries.csv")
    nvme_ts     = _read_csv(raw_dir / "nvme_driver_timeseries.csv")
    # Derive per-sample rate columns (rd_iops, wr_iops, rd_bw_mbs, wr_bw_mbs,
    # rd_lat_ms, wr_lat_ms, io_util_pct) from the raw cumulative counters that
    # the Prometheus loader writes.  If these columns are already present
    # (e.g. from a live iostat collection), _derive_nvme_columns() is a no-op.
    nvme_ts = _derive_nvme_columns(nvme_ts)
    smart_sum   = _read_json(raw_dir / "smart_summary.json")
    reqsize     = _read_csv(raw_dir / "request_size_distribution.csv")
    iat         = _read_csv(raw_dir / "interarrival_distribution.csv")
    temporal    = _read_csv(raw_dir / "temporal_read_write_trim_pattern.csv")
    bw_stream   = _read_csv(raw_dir / "bandwidth_per_stream.csv")
    hot_regions = _read_csv(raw_dir / "hot_regions_overall.csv")
    bt_summary  = _read_json(raw_dir / "summary.json")
    manual_setup = _read_json(raw_dir / "setup_details.json") or _read_json(raw_dir / "setup.json")

    # ── Set module-level wall-clock anchor ────────────────────────────────────
    # t0_epoch is the Unix timestamp of the collection-window start, stored in
    # summary.json during both live collect and Prometheus analyze runs.
    # All _ts_to_dates() calls pick this up automatically so every chart's
    # X axis is anchored to the same real wall-clock time — consistent with
    # the --start / --end the user specified on the command line.
    _t0_candidates = [
        bt_summary.get("t0_epoch"),           # live collect primary
        sglang_sum.get("t0_epoch"),            # sglang_summary fallback
        sglang_sum.get("start_time"),          # Prometheus analyze fallback
        bt_summary.get("start_time"),
        bt_summary.get("prom_start"),
    ]
    _T0_EPOCH = 0.0
    for _t0c in _t0_candidates:
        try:
            v = float(_t0c)
            if v > 1_000_000_000:   # sanity: must be a plausible Unix timestamp (> year 2001)
                _T0_EPOCH = v
                break
        except (TypeError, ValueError):
            pass
    setup = {
        "Model": sglang_sum.get("model_name", "unknown"),
        "Runtime": sglang_sum.get("runtime", sglang_sum.get("server_type", "SGLang")),
        "Instance": sglang_sum.get("instance", sglang_sum.get("prom_instance", "unknown")),
        "Job": sglang_sum.get("job", "unknown"),
        "Engine": sglang_sum.get("engine_type", "unknown"),
        "TP size": sglang_sum.get("tp_size", sglang_sum.get("tensor_parallel_size", "unknown")),
        "dtype": sglang_sum.get("dtype", "unknown"),
        "KV dtype": sglang_sum.get("kv_cache_dtype", "unknown"),
        "Context length": sglang_sum.get("context_length", sglang_sum.get("max_context_len", "unknown")),
        "Page size": sglang_sum.get("page_size", sglang_sum.get("sglang_page_size", "unknown")),
        "Num pages/tokens": sglang_sum.get("num_pages", sglang_sum.get("max_total_num_tokens", "unknown")),
        "HiCache": sglang_sum.get("hicache_size", sglang_sum.get("hicache_mem_layout", "unknown")),
    }

    def _is_missing_setup_value(v):
        if v is None:
            return True
        try:
            sv = str(v).strip()
        except Exception:
            return True
        return sv == "" or sv.lower() in {"unknown", "none", "nan", "null", "n/a", "—", "-"}

    def _parse_launch_command_to_setup(cmd: str) -> dict:
        if not cmd:
            return {}
        try:
            import shlex as _shlex_setup
            toks = _shlex_setup.split(str(cmd))
        except Exception:
            toks = str(cmd).split()
        out = {"Reference launch command": str(cmd)}
        mapping = {
            "--model-path": "Model path", "--tp-size": "TP size", "--dp-size": "DP size",
            "--port": "Port", "--host": "Host", "--attention-backend": "Attention backend",
            "--mem-fraction-static": "Mem fraction static", "--hicache-size": "HiCache size",
            "--hicache-storage-backend": "HiCache storage backend",
            "--hicache-write-policy": "HiCache write policy", "--reasoning-parser": "Reasoning parser",
            "--tool-call-parser": "Tool call parser", "--dtype": "dtype",
            "--kv-cache-dtype": "KV dtype", "--context-length": "Context length",
            "--page-size": "Page size", "--schedule-policy": "Schedule policy",
        }
        bool_flags = {
            "--enable-hierarchical-cache": ("Hierarchical cache", "enabled"),
            "--trust-remote-code": ("Trust remote code", "true"),
            "--enable-metrics": ("Metrics enabled", "true"),
            "--enable-cache-report": ("Cache report enabled", "true"),
        }
        i = 0
        while i < len(toks):
            t = toks[i]
            if t in bool_flags:
                k, v = bool_flags[t]; out[k] = v; i += 1; continue
            if t in mapping and i + 1 < len(toks):
                out[mapping[t]] = toks[i+1]; i += 2; continue
            i += 1
        if "Model path" in out and _is_missing_setup_value(out.get("Model")):
            out["Model"] = out["Model path"]
        return out

    if isinstance(manual_setup, dict):
        setup.update({str(k): str(v) for k, v in manual_setup.items()})
        launch_cmd = (setup.get("Launch command") or setup.get("launch_command") or
                      setup.get("SGLang launch command") or setup.get("sglang_launch_command"))
        if launch_cmd:
            for k, v in _parse_launch_command_to_setup(launch_cmd).items():
                if _is_missing_setup_value(setup.get(k)):
                    setup[k] = str(v)

    sglang_default_setup = {
        "Model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        "Model path": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        "Runtime": "SGLang",
        "Host": "0.0.0.0",
        "Port": "30000",
        "TP size": "8",
        "DP size": "1",
        "Attention backend": "triton",
        "Mem fraction static": "0.8",
        "Hierarchical cache": "enabled",
        "HiCache size": "50",
        "HiCache storage backend": "file",
        "HiCache write policy": "write_through",
        "Trust remote code": "true",
        "Metrics enabled": "true",
        "Cache report enabled": "true",
        "Reasoning parser": "deepseek-r1",
        "Tool call parser": "deepseekv3",
        "Reference launch command": "python -m sglang.launch_server --model-path deepseek-ai/DeepSeek-R1-Distill-Llama-70B --tp-size 8 --dp-size 1 --port 30000 --host 0.0.0.0 --attention-backend triton --mem-fraction-static 0.8 --enable-hierarchical-cache --hicache-size 50 --trust-remote-code --enable-metrics --enable-cache-report --reasoning-parser deepseek-r1 --tool-call-parser deepseekv3 --hicache-storage-backend file --hicache-write-policy write_through",
    }
    defaulted = []
    for k, v in sglang_default_setup.items():
        if _is_missing_setup_value(setup.get(k)):
            setup[k] = v
            defaulted.append(k)
    if defaulted:
        setup["Default profile"] = "SGLang DeepSeek-R1-70B HiCache reference launch; defaulted fields are assumed, not observed"
        setup["Defaulted fields"] = ", ".join(defaulted)

    # ── Bench summary (per-request benchmark output) ────────────────────────
    # Auto-discover bench_summary.{json,txt} in raw/; the parser handles
    # both the SGLang bench_serving plaintext and a JSON alias form.
    bench: dict = {}
    try:
        from ..bench_summary import discover_bench_summary, parse_bench_summary
        bench_path = discover_bench_summary(raw_dir)
        if bench_path:
            bench = parse_bench_summary(bench_path)
    except Exception:
        bench = {}

    # Percentile timeseries from Prometheus (P50/P90/P99 over time).
    # Written by amoprof.prometheus_source.fetch_from_prometheus when
    # --prometheus is supplied to `analyze`. Falls back to empty dict
    # otherwise (collect-only runs don't have histogram_quantile data).
    pct_ts: dict = {}
    try:
        pct_ts_path = raw_dir / "sglang_percentiles_timeseries.json"
        if pct_ts_path.exists() and pct_ts_path.stat().st_size > 0:
            import json as _json
            pct_ts = _json.loads(pct_ts_path.read_text())
    except Exception:
        pct_ts = {}

    # KPI tiles
    kpis = []
    if sglang_sum:
        kpis += [
            _kpi_tile("Model", str(sglang_sum.get("model_name", "—"))[-40:],
                      note="From sglang_summary.json"),
            _kpi_tile("TTFT", f"{sglang_sum.get('server_ttft_ms', 0):.0f}", "ms",
                      "Time to first token (mean)"),
            _kpi_tile("TPOT", f"{sglang_sum.get('server_itl_ms', 0):.1f}", "ms",
                      "Inter-token latency (mean)"),
            _kpi_tile("E2E", f"{sglang_sum.get('server_e2e_ms', 0):.0f}", "ms",
                      "End-to-end request latency"),
            _kpi_tile("Throughput", f"{sglang_sum.get('ai_op_decode_tok_s', 0):.1f}",
                      "tok/s", "Mean decode throughput"),
            _kpi_tile("Cache hit", f"{sglang_sum.get('cache_hit_rate_realtime_pct', 0):.1f}",
                      "%", "Realtime KV cache hit rate"),
        ]
    if gpu_sum:
        kpis += [
            _kpi_tile("GPU util", f"{gpu_sum.get('gpu_util_mean', 0):.1f}", "%",
                      f"Peak {gpu_sum.get('gpu_util_peak', 0):.0f}%"),
            _kpi_tile("HBM used", f"{gpu_sum.get('hbm_used_mb_mean', 0)/1024:.1f}",
                      "GB", f"{gpu_sum.get('hbm_util_pct_mean', 0):.0f}% of HBM"),
            _kpi_tile("GPU power", f"{gpu_sum.get('power_w_peak', 0):.0f}", "W",
                      "Peak per-GPU draw"),
        ]
    if smart_sum:
        kpis += [
            _kpi_tile("SSD", str(smart_sum.get('model', '—'))[:24], "",
                      f"Temp {smart_sum.get('temperature_c', 0)}°C  "
                      f"WAF {smart_sum.get('waf', 0):.2f}"),
        ]
    if bt_summary:
        kpis += [
            _kpi_tile("Block IOs", f"{bt_summary.get('total_events', 0):,}", "",
                      f"R={bt_summary.get('read_events',0):,}  "
                      f"W={bt_summary.get('write_events',0):,}  "
                      f"T={bt_summary.get('trim_events',0):,}"),
        ]

    # Prometheus-derived per-request percentiles (server-side ground truth)
    # — present when analyze ran with --prometheus AND the SGLang scrape
    # exposes histogram bucket metrics.
    if sglang_sum and sglang_sum.get("server_ttft_p99_ms") is not None:
        p50 = sglang_sum.get("server_ttft_p50_ms", 0)
        p99 = sglang_sum.get("server_ttft_p99_ms", 0)
        kpis.append(_kpi_tile(
            "Server TTFT (Prom)", f"{p50/1000:.1f}",
            "s P50", f"P99 {p99/1000:.1f}s · histogram_quantile"))
    if sglang_sum and sglang_sum.get("server_itl_p99_ms") is not None:
        p50 = sglang_sum.get("server_itl_p50_ms", 0)
        p99 = sglang_sum.get("server_itl_p99_ms", 0)
        kpis.append(_kpi_tile(
            "Server ITL (Prom)", f"{p50:.0f}",
            "ms P50", f"P99 {p99:.0f}ms · histogram_quantile"))
    if sglang_sum and sglang_sum.get("server_e2e_p99_ms") is not None:
        p50 = sglang_sum.get("server_e2e_p50_ms", 0)
        p99 = sglang_sum.get("server_e2e_p99_ms", 0)
        kpis.append(_kpi_tile(
            "Server E2E (Prom)", f"{p50/1000:.1f}",
            "s P50", f"P99 {p99/1000:.1f}s · histogram_quantile"))

    # Bench-summary KPIs (per-request percentile stats)
    if bench:
        if bench.get("total_requests") is not None:
            kpis.append(_kpi_tile(
                "Bench requests", f"{int(bench['total_requests']):,}",
                "", f"at {bench.get('request_rate', 0):.1f} req/s sent · "
                f"{bench.get('req_per_s', 0):.2f} req/s served"))
        if bench.get("avg_prompt_tokens") is not None:
            kpis.append(_kpi_tile(
                "Avg prompt", f"{int(bench['avg_prompt_tokens']):,}",
                "tok", f"P99 {int(bench.get('p99_prompt_tokens', 0)):,}"))
        if bench.get("avg_output_tokens") is not None:
            kpis.append(_kpi_tile(
                "Avg output", f"{int(bench['avg_output_tokens']):,}",
                "tok", f"P99 {int(bench.get('p99_output_tokens', 0)):,}"))
        if bench.get("avg_ttft_s") is not None:
            kpis.append(_kpi_tile(
                "Bench TTFT", f"{bench['avg_ttft_s']:.1f}",
                "s", f"P99 {bench.get('p99_ttft_s', 0):.1f}s"))
        if bench.get("avg_itl_s") is not None:
            kpis.append(_kpi_tile(
                "Bench ITL", f"{bench['avg_itl_s']*1000:.0f}",
                "ms", f"P99 {bench.get('p99_itl_s', 0)*1000:.0f}ms"))
        if bench.get("input_tok_per_s") is not None:
            kpis.append(_kpi_tile(
                "Input TPS", f"{bench['input_tok_per_s']:,.0f}",
                "tok/s", "Aggregate prompt token rate"))
        if bench.get("output_tok_per_s") is not None:
            kpis.append(_kpi_tile(
                "Output TPS", f"{bench['output_tok_per_s']:,.2f}",
                "tok/s", "Aggregate decode token rate"))
        if bench.get("cache_hit_rate") is not None:
            kpis.append(_kpi_tile(
                "Bench cache hit", f"{bench['cache_hit_rate']*100:.1f}",
                "%", "From bench summary (post-run aggregate)"))

    sections_html = []
    sections_html.append(_setup_section(setup))
    sections_html.append(_stack_overview_section())
    sections_html.append(_layer_header("layer-a5", "A5 · Application Layer", "Benchmark workload, request mix, prompt/output token distributions, TTFT/TPOT and tail latency.", "#24577f"))
    if bench:
        sections_html.append(_section(
            "Bench Summary — Per-Request Latency Percentiles",
            "ch_bench_lat", _chart_bench_latency_percentiles(bench),
            "Mean/P50/P90/P99/Max for TTFT, ITL (inter-token), and E2E "
            "latency. Y-axis is log scale because P99 typically dwarfs Mean."))
        sections_html.append(_section(
            "Bench Summary — Latency Spread (Box Plot)",
            "ch_bench_box", _chart_bench_latency_ranges(bench),
            "Box shows P50→P90 range; whiskers extend toward Q1-ish (lower) "
            "and P99 (upper). Hover for the exact percentiles."))
        sections_html.append(_section(
            "Bench Summary — Token Length Distribution",
            "ch_bench_tokens", _chart_bench_token_lengths(bench),
            "Distribution of prompt vs output token counts across "
            "the benchmark. Tells you whether your workload is "
            "long-prompt/short-output or vice versa."))
        sections_html.append(_section(
            "Bench Summary — Token Throughput (In vs Out)",
            "ch_bench_tps", _chart_bench_throughput_breakdown(bench),
            "Aggregate input and output token rates. A large input:output "
            "ratio (10× or more) indicates a prefill-dominated workload "
            "where most compute goes into processing prompts."))

    # Per-request latency percentile timeseries — only present when analyze
    # was run with --prometheus and the SGLang scrape includes histogram
    # bucket metrics. Each chart shows how P50, P90, P99 evolve through
    # the run, which is impossible to see from summary numbers alone.
    if pct_ts:
        chart_specs = [
            ("ttft",   "Server TTFT — P50 / P90 / P99 Time Series",
             "True per-request percentiles via histogram_quantile() over "
             "sglang_time_to_first_token_seconds_bucket. Watch for P99 "
             "spikes that indicate occasional cold-cache prefills or "
             "queue contention."),
            ("itl",    "Server ITL (Inter-Token Latency) — P50 / P90 / P99",
             "Per-request inter-token latency percentiles. P99 ITL spikes "
             "usually correlate with HBM bandwidth contention or KV-cache "
             "eviction storms; sustained high P50 indicates the model is "
             "memory-bandwidth bound."),
            ("e2e",    "Server E2E Latency — P50 / P90 / P99",
             "Total request latency percentiles. The P99/P50 ratio tells "
             "you how heavy-tailed your latency distribution is — high "
             "ratios mean tail-latency-sensitive workloads will suffer."),
            ("prompt_tokens",  "Prompt Token Length Distribution Over Time",
             "How prompt length distribution shifts during the run. If P99 "
             "rises sharply mid-run, you're likely entering a long-context "
             "phase that will stress KV cache."),
            ("output_tokens", "Output Token Length Distribution Over Time",
             "How output length distribution shifts. Useful for spotting "
             "phase transitions between summarization (short outputs) and "
             "generation (long outputs) workloads."),
        ]
        for metric_key, title, body in chart_specs:
            chart_spec = _chart_percentile_timeseries(pct_ts, metric_key)
            chart_spec = _apply_yaxis_override(chart_spec)
            if chart_spec is None:
                continue
            sections_html.append(_section(
                title, f"ch_pct_{metric_key}", chart_spec, body))

    sections_html.append(_layer_header("layer-a4", "A4 · Inference Runtime + AI Model", "SGLang runtime behavior, model/cache configuration, token throughput, cache-hit, tier residency and KV eviction/load-back.", "#317bb8"))
    sections_html.append(_section("Token Throughput & Cache Hit Rate",
                                   "ch_thru",
                                   _chart_sglang_throughput(sglang_ts),
                                   "SGLang Prometheus scrape — hover any point for values"))
    sections_html.append(_section("KV Cache Tier Occupancy",
                                   "ch_kv_tiers", _chart_kv_tiers(sglang_ts),
                                   "L1=Device(HBM), L2=Host(DRAM), L3=Storage(SSD) — stacked"))
    sections_html.append(_section("KV Cache Eviction / Load-back / Backup Rates",
                                   "ch_evict", _chart_eviction(sglang_ts)))

    sections_html.append(_layer_header("layer-l1", "A3/A2/A1 · L1 HBM / CUDA / GPU", "GPU kernel/runtime layer, HBM occupancy, HBM bandwidth pressure, GPU power and utilization.", "#2f8a4e"))
    sections_html.append(_section("GPU Utilization & HBM (per GPU)",
                                   "ch_gpu", _chart_gpu(gpu_ts),
                                   "Per-GPU lines — click legend entries to isolate one GPU"))
    sections_html.append(_section("Total GPU Power Draw",
                                   "ch_power", _chart_power(power_ts)))

    sections_html.append(_layer_header("layer-l2", "A3/A2/A1 · L2 DRAM / OS Memory Manager", "Host DRAM and OS memory behavior: page faults, swap activity, NUMA effects and DRAM bandwidth.", "#7a3f97"))
    sections_html.append(_section("Swap Storm — Page Activity",
                                   "ch_swap", _chart_swap_storm(vmstat_ts),
                                   "Per-second rates derived from /proc/vmstat cumulative counters"))
    # DRAM BW: try amduprof_pcm_raw.txt first, then .csv (collector may write either).
    # Previously only .txt was tried, which caused an empty chart when only .csv existed.
    _dram_path = (raw_dir / "amduprof_pcm_raw.txt"
                  if (raw_dir / "amduprof_pcm_raw.txt").exists()
                     and (raw_dir / "amduprof_pcm_raw.txt").stat().st_size > 0
                  else raw_dir / "amduprof_pcm_raw.csv")
    sections_html.append(_section("System DRAM Bandwidth (AMD EPYC PMU)",
                                   "ch_dram",
                                   _chart_dram_bw(_dram_path),
                                   "From AMDuProf PCM raw output (Data Fabric counters, 1.2s interval)"))

    sections_html.append(_layer_header("layer-l3", "A3/A2/A1 · L3 SSD / OS Block / NVMe", "Storage-tier behavior: NVMe driver, OS block layer, NAND, request-size/IAT distributions, stream bandwidth, and hot/cold regions.", "#a45714"))
    sections_html.append(_section("NVMe IOPS (Read / Write / Trim)",
                                   "ch_nvme_iops", _chart_nvme_iops(nvme_ts)))
    sections_html.append(_section("NVMe Bandwidth",
                                   "ch_nvme_bw", _chart_nvme_bw(nvme_ts)))
    sections_html.append(_section("NVMe Latency & Device Utilization",
                                   "ch_nvme_lat", _chart_nvme_latency(nvme_ts)))
    sections_html.append(_section("Request Size Distribution",
                                   "ch_reqsize", _chart_request_size_dist(reqsize),
                                   "From blktrace request_size_distribution.csv — bucketed by IO size"))
    sections_html.append(_section("Inter-Arrival Time Distribution",
                                   "ch_iat", _chart_iat_dist(iat),
                                   "Time between consecutive requests per op"))
    sections_html.append(_section("R/W/T Bytes per 10-sec Window (stacked)",
                                   "ch_rwt", _chart_temporal_rwt(temporal)))
    sections_html.append(_section("Bandwidth per Stream (top 20)",
                                   "ch_bps", _chart_bw_per_stream(bw_stream),
                                   "Each stream = (pid, comm) — sorted by bandwidth"))
    sections_html.append(_section("Hot LBA Regions",
                                   "ch_hot",
                                   _chart_hot_regions(hot_regions),
                                   "Top regions of LBA space by bytes accessed"))

    sections_html.append(_layer_header("layer-cross", "Cross-layer Diagnosis", "Use these charts together to connect A5 request symptoms back to A4 runtime behavior and A1–A3 memory/storage tiers.", "#0f172a"))

    # ─── Render full HTML ────────────────────────────────────────────────────
    head_title = f"AMOprof Report — {run_label}" if run_label else "AMOprof Report"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{head_title}</title>
  <script src="{PLOTLY_CDN}" charset="utf-8"></script>
  <style>
    *,*::before,*::after {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 24px;
      font-family: Inter, -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
      color: #0f172a;
      background: #e2e8f0;
      line-height: 1.55;
    }}
    header {{
      max-width: 1400px; margin: 0 auto 24px auto;
      padding: 24px 28px;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #f1f5f9;
      border-radius: 14px;
      box-shadow: 0 4px 12px rgba(15,23,42,0.18);
    }}
    header h1 {{ margin: 0 0 6px 0; font-size: 24px; letter-spacing: -0.3px; }}
    header .sub {{ color: #94a3b8; font-size: 13px; }}
    .kpi-grid {{
      max-width: 1400px; margin: 0 auto 24px auto;
      display: grid; gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .kpi-tile {{
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      padding: 12px 14px;
      box-shadow: 0 1px 3px rgba(15,23,42,0.06);
      transition: transform 0.12s, box-shadow 0.12s;
    }}
    .kpi-tile:hover {{
      transform: translateY(-1px);
      box-shadow: 0 3px 10px rgba(15,23,42,0.12);
    }}
    .kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px;
                  color: #64748b; margin-bottom: 4px; font-weight: 600; }}
    .kpi-value {{ font-size: 22px; font-weight: 700; color: #0f172a; }}
    .kpi-unit  {{ font-size: 13px; font-weight: 500; color: #475569; margin-left: 4px; }}
    .kpi-note  {{ font-size: 11px; color: #64748b; margin-top: 3px; }}
    section.card {{
      max-width: 1400px; margin: 0 auto 18px auto;
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 18px 22px 22px 22px;
      box-shadow: 0 1px 3px rgba(15,23,42,0.05);
    }}
    section.card h2 {{
      margin: 0 0 12px 0;
      font-size: 16px;
      color: #0f172a;
      letter-spacing: -0.2px;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 8px;
    }}
    .plot {{ width: 100%; min-height: 360px; }}
    .caption {{ margin-top: 10px; font-size: 12px; color: #64748b; font-style: italic; }}
    .no-data {{
      padding: 32px; text-align: center; color: #64748b;
      background: #f1f5f9; border-radius: 8px; font-size: 14px;
    }}
    footer {{
      max-width: 1400px; margin: 24px auto 0 auto;
      text-align: center; color: #64748b; font-size: 12px;
      padding: 16px;
    }}
    /* Hover hint banner */
    .hint {{
      background: #fef3c7; border-left: 4px solid #f59e0b;
      color: #78350f; padding: 10px 14px; border-radius: 6px;
      margin: 0 auto 18px auto; max-width: 1400px; font-size: 13px;
    }}

    .setup-panel {{
      background: linear-gradient(135deg, #eef2ff 0%, #f8fafc 100%) !important;
      border: 1px solid #a5b4fc !important;
      border-left: 6px solid #4f46e5 !important;
      color: #0f172a !important;
      box-shadow: 0 4px 14px rgba(79,70,229,0.12) !important;
    }}
    .setup-panel h2 {{ color: #1e1b4b !important; }}
    .setup-grid {{ display:grid; grid-template-columns: 1.35fr .85fr; gap:16px; align-items:start; }}
    .setup-table {{ width:100%; border-collapse:separate; border-spacing:0; overflow:hidden; border-radius:10px; border:1px solid #c7d2fe; background:#ffffff; }}
    .setup-table tr:nth-child(even) td {{ background:#f8fafc; }}
    .setup-table tr:nth-child(odd) td {{ background:#ffffff; }}
    .setup-table tr:hover td {{ background:#dbeafe !important; }}
    .setup-key {{ padding:9px 12px; font-weight:800; color:#1e293b !important; width:34%; border-bottom:1px solid #e2e8f0; vertical-align:top; }}
    .setup-value {{ padding:9px 12px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; color:#0f172a !important; border-bottom:1px solid #e2e8f0; vertical-align:top; overflow-wrap:anywhere; word-break:break-word; }}
    .setup-row-defaulted .setup-key, .setup-row-defaulted .setup-value {{ background:#fff7ed !important; color:#7c2d12 !important; }}
    .setup-info-box {{ background:#ffffff !important; border:1px solid #c7d2fe; border-radius:10px; padding:14px 16px; font-size:12px; color:#334155 !important; line-height:1.65; }}
    .setup-info-box p {{ margin:0 0 9px 0; }}
    .setup-info-box code {{ background:#eef2ff !important; color:#3730a3 !important; padding:1px 4px; border-radius:4px; }}
    .setup-info-title {{ font-size:12px; font-weight:800; color:#312e81; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }}
    .stack-cake {{ display:grid; gap:8px; margin-top:8px; }}
    .stack-row {{ display:grid; gap:8px; }}
    .stack-row.full {{ grid-template-columns:1fr; }}
    .stack-row.pair {{ grid-template-columns:1.6fr 1fr; }}
    .stack-row.trio {{ grid-template-columns:1fr 1fr 1fr; }}
    .stack-row > div, .stack-row.full {{ border-radius:10px; padding:14px 16px; color:#fff; }}
    .stack-row b {{ display:block; font-size:15px; margin-bottom:4px; }}
    .stack-row span {{ font-size:11px; opacity:.92; }}
    .a5 {{ background:#24577f; }} .a4 {{ background:#317bb8; }} .model {{ background:#b89a05; }}
    .l1 {{ background:#2f8a4e; }} .l2 {{ background:#7a3f97; }} .l3 {{ background:#a45714; }}
    @media(max-width:768px) {{ .setup-grid,.stack-row.pair,.stack-row.trio {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>📊 AMOprof — AI Memory &amp; IO Profiler · Interactive Report</h1>
    <div class="sub">
      Model: {sglang_sum.get('model_name','—')}
      &nbsp;·&nbsp; Duration: {sglang_sum.get('collection_elapsed_s', 0):.0f} sec
      &nbsp;·&nbsp; Source: {sglang_sum.get('prometheus_source','offline')}
    </div>
  </header>

  <div class="hint">
    💡 <b>Tip:</b> Hover any chart for exact values. Click a legend entry to hide/show traces.
    Drag to zoom; double-click to reset.
  </div>

  <div class="kpi-grid">
    {''.join(kpis)}
  </div>

  {''.join(sections_html)}

  <footer>
    Generated by AMOprof · static charts available via <code>--report</code> · interactive via <code>--interactive</code>
  </footer>
</body>
</html>"""
    out_html.write_text(html, encoding="utf-8")
    return out_html
