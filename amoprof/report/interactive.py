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
            height: int = 460, ts: list[float] | None = None,
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
            "x": 0.02, "y": 0.97, "xanchor": "left", "yanchor": "top",
        },
        "height": height,
        # Bottom margin needs room for the x-axis tick labels AND the legend
        # below them. The legend is anchored at y=-0.18 (below chart) and can
        # wrap to 2-3 rows for charts with many traces (e.g. 8-GPU chart).
        # 130px holds 3 legend rows + tick labels comfortably.
        "margin": {"l": 64, "r": 80, "t": 60, "b": 130},
        "plot_bgcolor": "#f8fafc",
        "paper_bgcolor": "#ffffff",
        "font": {"color": "#0f172a", "size": 13, "family": "Inter, system-ui, sans-serif"},
        "xaxis": (_time_axis_config(ts, t0_epoch=t0) if ts is not None else {
            "title": {"text": "Wall-clock time (UTC)" if t0 > 0 else "Time",
                      "font": {"size": 13}, "standoff": 15},
            "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
            "linecolor": "#475569", "tickcolor": "#475569",
            "tickfont": {"size": 12, "color": "#0f172a"},
            "type": "date",
            "automargin": True,
        }),
        "yaxis": {
            "title": {"text": ylabel, "font": {"size": 13}, "standoff": 10},
            "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
            "linecolor": "#475569", "tickcolor": "#475569",
            "tickfont": {"size": 12, "color": "#0f172a"},
            "automargin": True,
        },
        "hovermode": "x unified",
        "hoverlabel": {"bgcolor": "#1e293b", "bordercolor": "#0f172a",
                        "font": {"color": "#f1f5f9", "size": 13}},
        # Legend: horizontal row(s) below the x-axis. Plotly wraps automatically
        # when items don't fit on one row. Use xanchor="left" so the legend
        # left-aligns with the plot area. Anchor at top so the legend grows
        # downward (the chart's bottom margin reserves space for it).
        # y=-0.18 leaves ~30px gap between x-axis tick labels and legend.
        "legend": {"orientation": "h",
                    "yanchor": "top", "y": -0.18,
                    "xanchor": "left", "x": 0,
                    "font": {"size": 11, "color": "#0f172a"},
                    "bgcolor": "rgba(248,250,252,0.92)",
                    "bordercolor": "#cbd5e1", "borderwidth": 1,
                    "itemwidth": 40,
                    "itemsizing": "constant",
                    "tracegroupgap": 8,
                    "entrywidth": 0,
                    "entrywidthmode": "pixels"},
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
                              height=480, ts=all_ts)}


def _chart_power(power: list[dict], gpu: list[dict] | None = None) -> dict | None:
    """System GPU power chart.

    Primary source: power_timeseries.csv (already summed across GPUs).
    Fallback: gpu_timeseries.csv per-GPU 'power' column summed by timestamp,
    used when the primary source is missing or all-zero.
    """
    ts: list[float] = []
    pw: list[float] = []
    if power:
        ts = _col(power, "time_sec")
        pw = _col(power, "gpu_power")
    # If primary source absent or all-zero, synthesize from per-GPU gpu_ts
    if (not pw or not any(pw)) and gpu:
        try:
            from collections import defaultdict
            sums: dict[float, float] = defaultdict(float)
            for r in gpu:
                t = _to_float(r.get("time_sec"))
                p = _to_float(r.get("power"))
                if t is not None and p:
                    sums[t] += p
            if sums:
                ts = sorted(sums.keys())
                pw = [sums[t] for t in ts]
        except Exception:
            pass
    if not pw or not any(pw):
        return None
    xs = _ts_to_dates(ts)
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
                      "Pages / sec", "Major faults / sec", height=480, ts=ts)
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


def _chart_qd_timeseries(qd_ts: list[dict]) -> dict | None:
    """Interactive time-series of NVMe queue depth (from blktrace Q→C walk).

    qd_ts rows are: t_sec, qd_total, qd_read, qd_write — produced by
    blktrace_analyzer._compute_queue_depth_timeseries.

    Two stacked traces (read + write) so a viewer can see whether saturation
    is read-driven (HiCache load-back) or write-driven (KV offload). The
    total trace sits on top as a thin overlay line for at-a-glance peak QD.
    """
    if not qd_ts:
        return None
    ts = [_to_float(r.get("t_sec")) or 0 for r in qd_ts]
    qd_t = [_to_float(r.get("qd_total")) or 0 for r in qd_ts]
    qd_r = [_to_float(r.get("qd_read"))  or 0 for r in qd_ts]
    qd_w = [_to_float(r.get("qd_write")) or 0 for r in qd_ts]
    layout = dict(_layout("NVMe Queue Depth Over Time", "Outstanding I/Os", ts=ts))
    layout["hovermode"] = "x unified"
    return {
        "data": [
            {"x": _ts_to_dates(ts), "y": qd_r, "type": "scatter", "mode": "lines",
             "name": "Read QD",   "stackgroup": "qd",
             "line": {"color": "#3b82f6", "width": 0},
             "fillcolor": "rgba(59,130,246,0.55)",
             "hovertemplate": "<b>%{y:.0f}</b> reads in-flight<extra></extra>"},
            {"x": _ts_to_dates(ts), "y": qd_w, "type": "scatter", "mode": "lines",
             "name": "Write QD",  "stackgroup": "qd",
             "line": {"color": "#ef4444", "width": 0},
             "fillcolor": "rgba(239,68,68,0.55)",
             "hovertemplate": "<b>%{y:.0f}</b> writes in-flight<extra></extra>"},
            {"x": _ts_to_dates(ts), "y": qd_t, "type": "scatter", "mode": "lines",
             "name": "Total QD (peak per bucket)",
             "line": {"color": "#7c3aed", "width": 2.2},
             "hovertemplate": "<b>%{y:.0f}</b> total outstanding<extra></extra>"},
        ],
        "layout": layout,
    }


def _chart_qd_distribution(qd_dist: list[dict]) -> dict | None:
    """Time-weighted histogram: what % of trace time was spent at each QD value.

    qd_dist rows are: qd_value, time_sec, pct_of_run.
    Bar chart with x = QD bucket, y = % of run time. Log-x scale would compress
    the readable area; we keep linear and let the user scroll if their QD
    distribution is unusually wide.
    """
    if not qd_dist:
        return None
    qds  = [int(_to_float(r.get("qd_value")) or 0) for r in qd_dist]
    pcts = [_to_float(r.get("pct_of_run")) or 0 for r in qd_dist]
    # Color saturation buckets red, healthy ones green
    colors = []
    for q in qds:
        if q >= 128:   colors.append("#ef4444")
        elif q >= 32:  colors.append("#f59e0b")
        elif q >= 2:   colors.append("#22c55e")
        else:          colors.append("#0ea5e9")
    layout = dict(_layout("Queue Depth Distribution (time-weighted)",
                          "% of trace time", height=380))
    # X axis is QD value, not time — explicitly set to linear (inherits date by default)
    layout["xaxis"] = {
        "type": "linear",
        "title": {"text": "Queue depth (outstanding I/Os)", "standoff": 12},
        "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
        "linecolor": "#475569", "tickcolor": "#475569",
        "tickfont": {"size": 12, "color": "#0f172a"},
        "automargin": True,
    }
    layout["hovermode"] = "closest"
    return {
        "data": [
            {"x": qds, "y": pcts, "type": "bar",
             "marker": {"color": colors},
             "hovertemplate": "<b>QD=%{x}</b><br>%{y:.2f}% of trace<extra></extra>"}
        ],
        "layout": layout,
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
                              "Tokens", height=480, ts=ts)}


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


def _kv_bytes_per_token_for_model(model_name: str, kv_dtype: str) -> float:
    """Estimate KV cache bytes per token from model architecture.

    Mirrored from amoprof.KV_ARCH_DB / combined._kv_bytes_per_token_kb so
    the interactive tab can derive byte-level L3 BW from token-level SGLang
    counters without depending on the static-report module.
    """
    arch_db = {
        "gpt-oss-120b": (36, 8, 64, "GQA"),
        "gpt-oss-20b":  (24, 8, 64, "GQA"),
        "deepseek-r1-distill-llama-70b": (80, 8, 128, "GQA"),
        "deepseek-r1-distill-qwen-32b":  (64, 8, 128, "GQA"),
        "deepseek-r1-distill-qwen-14b":  (48, 8, 128, "GQA"),
        "deepseek-v3":      (61, 128, 512, "MLA"),
        "qwen3-235b":       (94, 4, 512, "MLA"),
        "llama-3.1-405b":  (126, 8, 128, "GQA"),
        "llama-3.1-70b":    (80, 8, 128, "GQA"),
        "llama-3-70b":      (80, 8, 128, "GQA"),
    }
    ml = (model_name or "").lower()
    arch = None
    for key, val in arch_db.items():
        if key in ml:
            arch = val; break
    if arch is None:
        for hint, val in [("671b",(61,128,512,"MLA")),
                          ("405b",(126,8,128,"GQA")),
                          ("235b",(94,4,512,"MLA")),
                          ("120b",(36,8,64,"GQA")),
                          ("72b",(80,8,128,"GQA")),
                          ("70b",(80,8,128,"GQA")),
                          ("32b",(64,8,128,"GQA")),
                          ("20b",(24,8,64,"GQA")),
                          ("14b",(48,8,128,"GQA")),
                          ("13b",(40,8,128,"GQA")),
                          ("8b",(32,8,128,"GQA")),
                          ("7b",(28,4,128,"GQA")),
                          ("3b",(32,8,128,"GQA"))]:
            if hint in ml:
                arch = val; break
    if arch is None:
        arch = (80, 8, 128, "GQA")
    n_layers, n_kv_heads, head_dim, attn = arch
    dtype_bytes = 1 if (kv_dtype or "").lower().startswith(("fp8","int8","int4")) else 2
    if attn == "MLA":
        return n_layers * head_dim * dtype_bytes * 2  # bytes, not KB
    return n_layers * n_kv_heads * head_dim * 2 * dtype_bytes


def _chart_l3_prom_bandwidth(sglang: list[dict],
                              kv_bytes_per_token: float) -> dict | None:
    """Interactive estimated L3 bandwidth in MB/s (Prometheus-derived).

    Multiplies per-second backuped/load-back token rates by kv_bytes_per_token
    to give an estimate of L3 read / write bandwidth that's directly usable
    for sizing. This is the Prometheus-only analog of the blktrace-derived
    NVMe BW chart; it's the only L3 BW signal available in Prom-only runs.

    Caveat: byte estimate is "useful work" not raw device bytes (the device
    sees additional metadata / FS overhead). Accurate to within 5-15% for
    KV-cache workloads.

    Returns None when SGLang token counters aren't present or
    kv_bytes_per_token isn't set.
    """
    if not sglang or kv_bytes_per_token <= 0:
        return None
    ts = _col(sglang, "time_sec")
    if not ts:
        return None
    lb_col = _find_col(sglang, "load_back_tokens_total")
    bk_col = _find_col(sglang, "backuped_tokens_total")
    if not (lb_col or bk_col):
        return None

    def _rate_mbs(col: str) -> list[float]:
        if not col: return [0.0] * len(ts)
        v = _col(sglang, col)
        out = [0.0]
        for i in range(1, len(v)):
            dt = ts[i] - ts[i-1]
            tok_per_s = max((v[i] - v[i-1]) / dt, 0) if dt > 0 else 0
            # tok/s × bytes/tok / 1e6 = MB/s
            out.append(tok_per_s * kv_bytes_per_token / 1e6)
        return out

    xs = _ts_to_dates(ts)
    traces = []
    if lb_col:
        rd_mbs = _rate_mbs(lb_col)
        traces.append({
            "x": xs, "y": rd_mbs,
            "type": "scatter", "mode": "lines", "name": "L3 Read MB/s (est)",
            "line": {"color": "#22c55e", "width": 2.2},
            "fill": "tozeroy", "fillcolor": "rgba(34,197,94,0.15)",
            "hovertemplate": "<b>%{y:.1f}</b> MB/s estimated read<extra></extra>",
        })
    if bk_col:
        wr_mbs = _rate_mbs(bk_col)
        traces.append({
            "x": xs, "y": wr_mbs,
            "type": "scatter", "mode": "lines", "name": "L3 Write MB/s (est)",
            "line": {"color": "#3b82f6", "width": 2.2},
            "fill": "tozeroy", "fillcolor": "rgba(59,130,246,0.15)",
            "hovertemplate": "<b>%{y:.1f}</b> MB/s estimated write<extra></extra>",
        })
    return {
        "data": traces,
        "layout": _layout(
            f"L3 Cache Bandwidth — Prometheus-derived  "
            f"(× {kv_bytes_per_token/1024:.0f} KB/tok)",
            "MB/s (estimated)", ts=ts),
    }


def _chart_l3_prom_cumulative(sglang: list[dict],
                               kv_bytes_per_token: float) -> dict | None:
    """Cumulative L3 read/write bytes over time (Prometheus-derived).

    Useful for sizing the endurance footprint of an L3 backend over a
    representative window. Plots cumulative tokens × bytes/tok / 1e9 = GB.
    """
    if not sglang or kv_bytes_per_token <= 0:
        return None
    ts = _col(sglang, "time_sec")
    if not ts:
        return None
    lb_col = _find_col(sglang, "load_back_tokens_total")
    bk_col = _find_col(sglang, "backuped_tokens_total")
    if not (lb_col or bk_col):
        return None

    def _cum_gb(col: str) -> list[float]:
        if not col: return [0.0] * len(ts)
        v = _col(sglang, col)
        v0 = v[0] if v else 0
        return [max((vi - v0), 0) * kv_bytes_per_token / 1e9 for vi in v]

    xs = _ts_to_dates(ts)
    traces = []
    if lb_col:
        traces.append({
            "x": xs, "y": _cum_gb(lb_col),
            "type": "scatter", "mode": "lines", "name": "L3 reads (cumulative GB)",
            "line": {"color": "#22c55e", "width": 2.2},
            "hovertemplate": "<b>%{y:.2f}</b> GB cumulative read<extra></extra>",
        })
    if bk_col:
        traces.append({
            "x": xs, "y": _cum_gb(bk_col),
            "type": "scatter", "mode": "lines", "name": "L3 writes (cumulative GB)",
            "line": {"color": "#3b82f6", "width": 2.2},
            "hovertemplate": "<b>%{y:.2f}</b> GB cumulative write<extra></extra>",
        })
    return {
        "data": traces,
        "layout": _layout(
            "L3 Cache Traffic — Cumulative Bytes (Prometheus-derived)",
            "Cumulative GB (estimated)", ts=ts),
    }


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
                          "MB per window", height=460)
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
                                 "Stream (pid:comm)", height=580),
                       "xaxis": {"title": {"text": "MiB / sec"},
                                 "tickfont": {"size": 12, "color": "#0f172a"}},
                       "barmode": "group"}}


def _chart_dram_bw_from_timeseries(rows: list[dict]) -> dict | None:
    """Build DRAM BW chart from collector-normalized PCM timeseries CSV.

    Accepts both modern column names:
      time_sec, dram_total_gb_s, dram_read_gb_s, dram_write_gb_s
    and older aliases:
      total_bw_gbs/total_gb_s, read_bw_gbs/read_gb_s, write_bw_gbs/write_gb_s.
    """
    if not rows:
        return None

    def _pick_col(candidates):
        keys = set()
        for r in rows[:5]:
            keys.update(r.keys())
        for c in candidates:
            if c in keys:
                return c
        # fallback: substring match
        lower = {str(k).lower(): k for k in keys}
        for c in candidates:
            cl = c.lower()
            for lk, orig in lower.items():
                if cl in lk:
                    return orig
        return None

    total_col = _pick_col(["dram_total_gb_s", "total_bw_gbs", "total_gb_s", "pcm_dram_total_gb_s", "Total Mem Bw"])
    read_col  = _pick_col(["dram_read_gb_s", "read_bw_gbs", "read_gb_s", "pcm_dram_read_gb_s", "Total Mem RdBw"])
    write_col = _pick_col(["dram_write_gb_s", "write_bw_gbs", "write_gb_s", "pcm_dram_write_gb_s", "Total Mem WrBw"])
    if not (total_col or read_col or write_col):
        return None

    ts = _col(rows, "time_sec") if "time_sec" in rows[0] else [i * 1.2 for i in range(len(rows))]
    rd_bw = _col(rows, read_col) if read_col else [0.0 for _ in rows]
    wr_bw = _col(rows, write_col) if write_col else [0.0 for _ in rows]
    if total_col:
        tot_bw = _col(rows, total_col)
    else:
        tot_bw = [r + w for r, w in zip(rd_bw, wr_bw)]

    # Drop all-zero parser artifacts.
    if max([abs(v) for v in tot_bw] or [0.0]) <= 0:
        return None

    xs = _ts_to_dates(ts)
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
                          "GB / sec", ts=ts)
    }


def _chart_dram_bw(amduprof_txt: Path) -> dict | None:
    """Parse AMDuProf PCM raw text/CSV and build DRAM BW chart.

    This intentionally mirrors the static report parser instead of using
    pandas.read_csv(), because AMDuProfPcm output is a multi-section CSV-like
    text file and normal CSV tokenization often fails with variable-width
    headers.  The parser searches the DF METRICS header containing Total Mem Bw,
    Total Mem RdBw and Total Mem WrBw, resolves the real column indices, and
    then reads only numeric rows from that section.
    """
    raw_path: Path | None = None
    candidates = [
        amduprof_txt,
        amduprof_txt.with_suffix(".csv"),
        amduprof_txt.with_suffix(".txt"),
        amduprof_txt.parent / "amduprof_pcm_raw.csv",
        amduprof_txt.parent / "amduprof_pcm_raw.txt",
        amduprof_txt.parent / "amduprof_pcm_raw",
    ]
    seen = set()
    for candidate in candidates:
        candidate = Path(candidate)
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists() and candidate.stat().st_size > 0:
            raw_path = candidate
            break
    if raw_path is None:
        return None

    def _nums(parts):
        out = []
        for p in parts:
            try:
                out.append(float(str(p).strip()))
            except Exception:
                out.append(0.0)
        return out

    rd_bw, wr_bw, tot_bw = [], [], []
    col_total: int | None = None
    col_rd:    int | None = None
    col_wr:    int | None = None
    in_data = False

    for line in raw_path.read_text(errors="replace").splitlines():
        ll = line.strip().rstrip(",")
        if not ll:
            continue

        # Header detection — accept both AMDuProf long names and short aliases.
        if ("Total Mem Bw" in ll or "Mem Bw" in ll) and ("RdBw" in ll or "WrBw" in ll):
            cols = [c.strip() for c in ll.split(",")]
            col_total = col_rd = col_wr = None
            for i, c in enumerate(cols):
                cl = c.lower().strip()
                if col_total is None and "total mem bw" in cl and "rdbw" not in cl and "wrbw" not in cl:
                    col_total = i
                elif col_rd is None and ("total mem rdbw" in cl or cl == "rdbw" or "mem rdbw" in cl):
                    col_rd = i
                elif col_wr is None and ("total mem wrbw" in cl or cl == "wrbw" or "mem wrbw" in cl):
                    col_wr = i
            if col_total is not None or col_rd is not None or col_wr is not None:
                in_data = True
            continue

        if not in_data:
            continue

        # Data rows in AMDuProf PCM sections normally start with RecordId or timestamp.
        # Stop when a new non-numeric section begins.
        first = ll.split(",", 1)[0].strip()
        try:
            float(first)
        except Exception:
            in_data = False
            continue

        parts = _nums(ll.split(","))
        n = len(parts)
        i_t = col_total if col_total is not None and col_total < n else None
        i_r = col_rd    if col_rd    is not None and col_rd    < n else None
        i_w = col_wr    if col_wr    is not None and col_wr    < n else None
        if i_t is None and i_r is None and i_w is None:
            continue
        r = parts[i_r] if i_r is not None else 0.0
        w = parts[i_w] if i_w is not None else 0.0
        t = parts[i_t] if i_t is not None else (r + w)
        if t != 0 or r != 0 or w != 0:
            tot_bw.append(t); rd_bw.append(r); wr_bw.append(w)

    if not tot_bw:
        return None

    interval_s = 1.2
    ts_elapsed = [i * interval_s for i in range(len(tot_bw))]
    xs = _ts_to_dates(ts_elapsed)
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


def _chart_hot_regions(hr: list[dict],
                       lba_dist: list[dict] | None = None,
                       ssd_capacity_gb: float = 0.0,
                       ssd_used_gb: float = 0.0,
                       fs_partition_start_gb: float = 0.0) -> dict | None:
    """SSD I/O distribution across LBA space + hot regions overlay.

    Shows where on the disk this run's I/O landed and how spread out it was.

    Important — TWO different "GB" quantities visible in this section:
      • Bars (and "X GB" in legend) = bytes accessed during the collect window
        only. Limited by `summary.json :: duration_sec` (your run = 1096 s,
        148 GB writes). Does NOT include I/O before tracing started.
      • Dashed `df filesystem-used` line = files on the mount AT ANALYZE TIME,
        cumulative across all previous runs. The bars will typically be far
        below this line because pre-existing KV blocks aren't re-written.

    The hot-regions CSV only keeps the top 50 buckets per op (~15% of bytes
    on a write-heavy KV-offload workload). This chart shows two layers:

      1. **I/O distribution this window** (background bars) — every LBA
         bucket that saw traffic, binned into ~120 equal-width slots across
         the device's full capacity. Y axis = bytes (log) accessed per slot.
         Answers "how spread out was THIS run's I/O".
      2. **Hot regions** (foreground diamonds) — top 30 hottest buckets per
         op from hot_regions_overall.csv.

    X axis spans 0 → `ssd_capacity_gb` so position matches the SSD's physical
    layout. Dotted vertical line at capacity; dashed line at df-used as
    cumulative-state context.
    """
    if not hr and not lba_dist:
        return None

    palette = {"read": "#22c55e", "write": "#f43f5e", "trim": "#eab308"}
    traces: list[dict] = []

    # ── Layer 1: full distribution, binned ──────────────────────────────────
    if lba_dist:
        # Determine X-axis range: prefer the device capacity (so the chart
        # spans the physical SSD), else the max observed LBA.
        max_lba_observed_b = max(
            (_to_float(r.get("lba_bucket_end")) or _to_float(r.get("lba_bucket_start")) or 0)
            for r in lba_dist
        )
        max_x_gb = max(ssd_capacity_gb, max_lba_observed_b / 1e9, 1.0)

        # Bin into ~120 equal-width slots
        N_BINS = 120
        bin_size_gb = max_x_gb / N_BINS

        from collections import defaultdict
        per_op_bins: dict[str, list[float]] = defaultdict(lambda: [0.0] * N_BINS)
        per_op_total: dict[str, float] = defaultdict(float)
        for r in lba_dist:
            op = (r.get("op") or "").lower()
            if op not in palette:
                continue
            lba_start_gb = _to_float(r.get("lba_bucket_start")) / 1e9
            bytes_ = _to_float(r.get("bytes")) or 0
            if bytes_ <= 0:
                continue
            bin_idx = min(int(lba_start_gb / bin_size_gb), N_BINS - 1)
            per_op_bins[op][bin_idx] += bytes_
            per_op_total[op] += bytes_

        bin_centers_gb = [(i + 0.5) * bin_size_gb for i in range(N_BINS)]
        for op in ("read", "write", "trim"):
            bins = per_op_bins.get(op)
            if not bins or per_op_total[op] <= 0:
                continue
            total_gb = per_op_total[op] / 1e9
            buckets_used = sum(1 for v in bins if v > 0)
            coverage_pct = buckets_used / N_BINS * 100.0
            traces.append({
                "x": bin_centers_gb,
                # Replace empty bins with None so the log y-axis doesn't render
                # them as -infinity bars (those produce "NaN GB" hover tooltips
                # on some browsers when the user hovers over the bin center).
                # None makes Plotly skip the bar entirely — no visual artifact,
                # no spurious tooltip.
                "y": [(v / 1e6) if v > 0 else None for v in bins],  # MB
                "type": "bar",
                "name": f"{op.title()} traffic ({total_gb:.1f} GB written in window, touches {coverage_pct:.0f}% of device)",
                "marker": {"color": palette[op], "opacity": 0.45,
                            "line": {"color": palette[op], "width": 0}},
                "width": bin_size_gb * 0.95,
                "offsetgroup": op,
                "hovertemplate": (
                    f"<b>{op.title()} distribution</b><br>"
                    "LBA range: %{x:.1f} GB ± "
                    f"{bin_size_gb/2:.1f} GB<br>"
                    "Bytes in bin: <b>%{y:.2f} MB</b><extra></extra>"),
                "legendgroup": "dist",
            })

    # ── Layer 2: hot regions on top (top 30 per op) ─────────────────────────
    if hr:
        for op in ("read", "write", "trim"):
            rows = [r for r in hr if (r.get("op") or "").lower() == op][:30]
            if not rows:
                continue
            traces.append({
                "x": [_to_float(r.get("lba_bucket_start")) / 1e9 for r in rows],
                "y": [(_to_float(r.get("bytes")) or 0) / 1e6 for r in rows],
                "type": "scatter", "mode": "markers",
                "name": f"{op.title()} hot regions (top 30)",
                "marker": {"color": palette.get(op), "size": 11, "opacity": 0.9,
                            "symbol": "diamond",
                            "line": {"color": "#0f172a", "width": 1.2}},
                "hovertemplate": (
                    f"<b>{op.title()} hot region</b><br>"
                    "LBA: %{x:.3f} GB<br>"
                    "Bytes: <b>%{y:.1f} MB</b><extra></extra>"),
                "legendgroup": "hot",
            })

    if not traces:
        return None

    # ── Layout with optional vlines for capacity and used-space ─────────────
    layout = dict(_layout("SSD I/O Distribution Across LBA Space",
                          "Bytes accessed in bin (MB, log)", height=520))
    # X-axis: span the SSD capacity, label in GB
    max_x_gb = max(ssd_capacity_gb,
                    (max((_to_float(r.get("lba_bucket_start")) for r in (lba_dist or [])), default=0)
                     / 1e9), 1.0)
    # CRITICAL: _layout() defaults xaxis type to "date" because most amoprof
    # charts are time-series. This chart's X axis is GB-of-LBA-offset, so we
    # MUST force the type back to "linear". Without this, Plotly treats x
    # values as Unix-epoch milliseconds — 0 becomes Dec 31 1969 and the
    # hovertemplate's "%{x:.1f} GB" formats a date as a number giving NaN GB.
    layout["xaxis"] = {
        "type": "linear",
        "title": {"text": (f"Disk LBA offset (GB) — device capacity "
                            f"{ssd_capacity_gb:.0f} GB" if ssd_capacity_gb > 0
                            else "Disk LBA offset (GB)"),
                   "standoff": 15},
        "range": [0, max_x_gb * 1.02],
        "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
        "linecolor": "#475569", "tickcolor": "#475569",
        "tickfont": {"size": 12, "color": "#0f172a"},
        "automargin": True,
    }
    # Y-axis: log scale to make sparse activity visible alongside hot peaks.
    # Replace the default linear y-axis from _layout(); explicit type avoids
    # any chance of inheriting an unexpected type.
    layout["yaxis"] = {
        "type": "log",
        "title": {"text": "Bytes per bin (MB, log)", "standoff": 10},
        "gridcolor": "#cbd5e1", "zerolinecolor": "#94a3b8",
        "linecolor": "#475569", "tickcolor": "#475569",
        "tickfont": {"size": 12, "color": "#0f172a"},
        "automargin": True,
    }
    # hovermode default from _layout is "x unified" which is wrong for a
    # non-time axis (it lines all traces up on x; here we want per-trace).
    layout["hovermode"] = "closest"
    layout["barmode"] = "overlay"
    shapes = []
    annotations = []
    # The df-used number is FS-relative (GB used inside the partition).
    # Plot it in device-absolute LBA = partition_start + fs_used so the
    # dashed line lines up correctly with where the FS data actually lives.
    df_used_lba_gb = fs_partition_start_gb + ssd_used_gb
    if ssd_used_gb > 0 and df_used_lba_gb < max_x_gb:
        shapes.append({
            "type": "line", "xref": "x", "yref": "paper",
            "x0": df_used_lba_gb, "x1": df_used_lba_gb, "y0": 0, "y1": 1,
            "line": {"color": "#0ea5e9", "width": 2, "dash": "dash"},
        })
        _df_label = (f"df at analyze time: {ssd_used_gb:.0f} GB FS-used "
                      f"(at device LBA {df_used_lba_gb:.0f} GB)"
                      if fs_partition_start_gb > 0
                      else f"df at analyze time: {ssd_used_gb:.0f} GB filesystem-used "
                            "(cumulative across runs, not just this window)")
        annotations.append({
            "x": df_used_lba_gb, "y": 1.02, "xref": "x", "yref": "paper",
            "text": _df_label,
            "showarrow": False, "yanchor": "bottom",
            "font": {"size": 10, "color": "#0ea5e9"},
            "bgcolor": "rgba(14,165,233,0.08)",
            "bordercolor": "#0ea5e9", "borderwidth": 1, "borderpad": 3,
        })
    # Partition-start marker (only when traced device is whole-disk and FS
    # lives on a partition — i.e. fs_partition_start_gb > 0). Helps explain
    # why hot-LBA cluster is centered around the partition's logical zero
    # rather than the device's physical zero.
    if fs_partition_start_gb > 0 and fs_partition_start_gb < max_x_gb:
        shapes.append({
            "type": "line", "xref": "x", "yref": "paper",
            "x0": fs_partition_start_gb, "x1": fs_partition_start_gb,
            "y0": 0, "y1": 1,
            "line": {"color": "#16a34a", "width": 2, "dash": "dashdot"},
        })
        annotations.append({
            "x": fs_partition_start_gb, "y": 0.88, "xref": "x", "yref": "paper",
            "text": f"FS partition start ({fs_partition_start_gb:.0f} GB)",
            "showarrow": False, "yanchor": "top",
            "font": {"size": 10, "color": "#16a34a"},
            "bgcolor": "rgba(22,163,74,0.08)",
            "bordercolor": "#16a34a", "borderwidth": 1, "borderpad": 3,
        })
    if ssd_capacity_gb > 0:
        shapes.append({
            "type": "line", "xref": "x", "yref": "paper",
            "x0": ssd_capacity_gb, "x1": ssd_capacity_gb, "y0": 0, "y1": 1,
            "line": {"color": "#475569", "width": 2, "dash": "dot"},
        })
        annotations.append({
            "x": ssd_capacity_gb, "y": 0.95, "xref": "x", "yref": "paper",
            "text": f"capacity {ssd_capacity_gb:.0f} GB",
            "showarrow": False, "yanchor": "top", "xanchor": "right",
            "font": {"size": 11, "color": "#475569"},
        })
    if shapes:
        layout["shapes"] = shapes
    if annotations:
        layout["annotations"] = annotations
    return {"data": traces, "layout": layout}


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
            height=480, ts=ts),
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
                              "seconds (log scale)", height=480),
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
                              "tokens", height=460),
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
            "seconds (log scale)", height=460),
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
    """Render an interactive chart section.

    Empty sections (fig is None) are wrapped in a collapsed <details> with
    a single-line muted summary. The user can expand to see the explanation
    of why no data is available, but the section doesn't take up vertical
    real estate by default. This addresses long pages with many "requires
    blktrace / requires AMDuProf / no L3 activity" sections that scroll
    interesting content off-screen.

    Sections WITH data render expanded as before — no extra clicks needed.
    """
    if fig is None:
        # Empty section: collapsed by default. The summary row stays visible
        # so the user knows the section exists and can be expanded.
        return f"""
<section class="card empty-card">
  <details class="empty-details">
    <summary class="empty-summary">
      <span class="empty-icon">⊘</span>
      <span class="empty-title">{title}</span>
      <span class="empty-hint">no data — click to expand</span>
    </summary>
    <div class="no-data">No data available for this chart.<br>
      <small>{note or 'Check that the corresponding collector ran during capture.'}</small>
    </div>
  </details>
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
    # The blktrace analyzer (v1.38.15+) writes its analysis CSVs to the
    # raw_dir/blktrace_analysis/ subdir so they don't clobber the collect-time
    # summary.json. Prefer that subdir; fall back to raw_dir for older runs.
    _ba_dir = raw_dir / "blktrace_analysis"
    def _ba_csv(name: str) -> list[dict]:
        p_sub = _ba_dir / name
        if p_sub.exists() and p_sub.stat().st_size > 0:
            return _read_csv(p_sub)
        return _read_csv(raw_dir / name)
    # Derive per-sample rate columns (rd_iops, wr_iops, rd_bw_mbs, wr_bw_mbs,
    # rd_lat_ms, wr_lat_ms, io_util_pct) from the raw cumulative counters that
    # the Prometheus loader writes.  If these columns are already present
    # (e.g. from a live iostat collection), _derive_nvme_columns() is a no-op.
    nvme_ts = _derive_nvme_columns(nvme_ts)
    # If the NVMe driver / iostat timeseries is empty or all-zero (a common
    # case when /sys/block stats weren't captured but blktrace was), synthesize
    # a per-window NVMe timeseries from the blktrace temporal pattern so the
    # NVMe BW / IOPS / utilization charts still reflect the real device I/O.
    def _nvme_ts_has_data(rows: list[dict]) -> bool:
        if not rows:
            return False
        for r in rows:
            for k in ("rd_bw_mbs", "wr_bw_mbs", "rd_iops", "wr_iops"):
                try:
                    if float(r.get(k, 0) or 0) > 0:
                        return True
                except (TypeError, ValueError):
                    continue
        return False
    if not _nvme_ts_has_data(nvme_ts):
        _tp_rows = _ba_csv("temporal_read_write_trim_pattern.csv")
        if _tp_rows:
            _WIN = 10.0  # temporal pattern window seconds (blktrace_analyzer.WINDOW_S)
            _synth: list[dict] = []
            for _r in _tp_rows:
                try:
                    _t0 = float(_r.get("window_start_sec", 0) or 0)
                    _t1 = float(_r.get("window_end_sec", _t0 + _WIN) or (_t0 + _WIN))
                    _dur = max(_t1 - _t0, 1e-6)
                    _rb = float(_r.get("read", 0) or 0)
                    _wb = float(_r.get("write", 0) or 0)
                    _tb = float(_r.get("trim", 0) or 0)
                    _rc = float(_r.get("read_count", 0) or 0)
                    _wc = float(_r.get("write_count", 0) or 0)
                    _tc = float(_r.get("trim_count", 0) or 0)
                    _busy = 1.0 if (_rb + _wb + _tb) > 0 else 0.0
                    _synth.append({
                        "time_sec":   round(_t0, 1),
                        "rd_bw_mbs":  round(_rb / 1e6 / _dur, 3),
                        "wr_bw_mbs":  round(_wb / 1e6 / _dur, 3),
                        "rd_iops":    round(_rc / _dur, 2),
                        "wr_iops":    round(_wc / _dur, 2),
                        "disc_ios":   round(_tc / _dur, 4),
                        "io_util_pct": round(_busy * 100.0, 1),
                        # latency unknown from temporal pattern; leave 0
                        "rd_lat_ms":  0.0,
                        "wr_lat_ms":  0.0,
                    })
                except (TypeError, ValueError):
                    continue
            if _synth:
                nvme_ts = _synth
    smart_sum   = _read_json(raw_dir / "smart_summary.json")
    reqsize     = _ba_csv("request_size_distribution.csv")
    iat         = _ba_csv("interarrival_distribution.csv")
    temporal    = _ba_csv("temporal_read_write_trim_pattern.csv")
    bw_stream   = _ba_csv("bandwidth_per_stream.csv")
    hot_regions = _ba_csv("hot_regions_overall.csv")
    # Complete per-bucket LBA distribution (every bucket that saw traffic).
    # Written by blktrace_analyzer v1.38.29+; reports generated against
    # older runs degrade gracefully — the chart shows only hot regions.
    lba_dist = _ba_csv("lba_distribution_full.csv")
    # Queue-depth analysis (v40+) — time-series + time-weighted histogram.
    # Empty list when the run pre-dates QD analysis; sections degrade gracefully.
    qd_ts_data   = _ba_csv("queue_depth_timeseries.csv")
    qd_dist_data = _ba_csv("queue_depth_distribution.csv")
    # Capacity/used context for the SSD I/O Distribution chart
    _ssd_cap_gb  = _to_float(smart_sum.get("nvme_device_capacity_gb")) or 0.0
    _ssd_used_gb = _to_float(smart_sum.get("hicache_fs_used_gb")) or \
                   _to_float(smart_sum.get("hicache_size_gb")) or 0.0
    # blktrace analysis summary lives in the subdir; merge with collect summary.
    bt_summary  = _read_json(raw_dir / "summary.json")
    _ba_summary = _read_json(_ba_dir / "summary.json")
    if _ba_summary:
        # Fill NVMe BW/IOPS/bytes from blktrace analysis when absent.
        for _k, _v in _ba_summary.items():
            bt_summary.setdefault(_k, _v)
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
    # Cross-fill: when the real Model is provided but Model path is missing
    # (or vice-versa), propagate the populated one rather than letting the
    # hardcoded DeepSeek default win. Without this the setup table shows
    # "Model: gpt-oss-120b" alongside "Model path: deepseek-ai/...".
    real_model = setup.get("Model")
    real_path  = setup.get("Model path")
    default_id = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B"
    if real_model and not _is_missing_setup_value(real_model) and real_model != default_id:
        # Real Model exists; if Model path is the stale DeepSeek default, replace it.
        if real_path == default_id or _is_missing_setup_value(real_path):
            setup["Model path"] = real_model
            if "Model path" in defaulted:
                defaulted.remove("Model path")
    elif real_path and not _is_missing_setup_value(real_path) and real_path != default_id:
        if real_model == default_id or _is_missing_setup_value(real_model):
            setup["Model"] = real_path
            if "Model" in defaulted:
                defaulted.remove("Model")
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

    def _setup_value(*keys, default="—"):
        for k in keys:
            v = setup.get(k)
            if not _is_missing_setup_value(v):
                return str(v)
        return default

    def _active_sglang_throughput() -> tuple[str, str]:
        """Return display value/note for throughput KPI.

        Prefer explicit summary fields. If those are absent or zero, compute
        the script-compatible active-window mean from sglang_timeseries.csv
        gen_throughput. If there are no SGLang samples in the selected
        Prometheus window, show N/A instead of a misleading 0.0 tok/s.
        """
        for key in ("ai_op_decode_tok_s", "gen_tp_active_mean", "gen_tp_mean", "decode_tok_s", "output_token_throughput"):
            try:
                v = float(sglang_sum.get(key, 0) or 0)
                if v > 0:
                    return f"{v:.1f}", f"From sglang_summary.json:{key}"
            except Exception:
                pass
        gen_col = _find_col(sglang_ts, "gen_throughput") if sglang_ts else None
        if gen_col:
            vals = [_to_float(r.get(gen_col)) for r in sglang_ts]
            active = [v for v in vals if v > 0]
            if active:
                return f"{(sum(active) / len(active)):.1f}", f"Active mean from {len(active)}/{len(vals)} gen_throughput samples"
            if vals:
                return "0.0", "SGLang gen_throughput samples were present but all zero"
        return "N/A", "No SGLang gen_throughput samples in this Prometheus window"

    # KPI tiles
    kpis = []
    if sglang_sum:
        kpis += [
            _kpi_tile("Model", _setup_value("Model", "Model path")[-40:],
                      note="From setup/server configuration"),
            _kpi_tile("TTFT",
                      f"{(sglang_sum.get('server_ttft_ms') or sglang_sum.get('server_ttft_p50_ms') or 0):.0f}",
                      "ms", "Time to first token (mean)"),
            _kpi_tile("TPOT",
                      f"{(sglang_sum.get('server_itl_ms') or sglang_sum.get('server_itl_p50_ms') or 0):.1f}",
                      "ms", "Inter-token latency (mean)"),
            _kpi_tile("E2E",
                      f"{(sglang_sum.get('server_e2e_ms') or sglang_sum.get('server_e2e_p50_ms') or 0):.0f}",
                      "ms", "End-to-end request latency"),
            _kpi_tile("Throughput", _active_sglang_throughput()[0],
                      "tok/s" if _active_sglang_throughput()[0] != "N/A" else "", _active_sglang_throughput()[1]),
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

    # ── L3 cache bandwidth (Prometheus-derived) ───────────────────────────
    # When the operator runs in Prom-only mode (no blktrace), the only L3
    # bandwidth signal available is the per-second delta of SGLang's
    # cumulative token counters multiplied by KV-bytes-per-token. These two
    # charts surface that signal in the interactive tab so users can see when
    # L3 was active, identify burst patterns, and read endurance footprint
    # off the cumulative trace. Both gracefully no-op if the counters are
    # zero or absent.
    _kv_b_pt = _kv_bytes_per_token_for_model(
        sglang_sum.get("model_name", ""),
        sglang_sum.get("kv_cache_dtype", "fp16"))
    sections_html.append(_section(
        "L3 Cache Bandwidth — Prometheus-derived (MB/s)",
        "ch_l3_bw",
        _chart_l3_prom_bandwidth(sglang_ts, _kv_b_pt),
        f"Estimated from SGLang backuped/load-back token counters × "
        f"{_kv_b_pt/1024:.0f} KB/tok (model arch). Useful work, not raw "
        f"device bytes. Accurate to within 5-15% for KV-cache workloads."))
    sections_html.append(_section(
        "L3 Cache Traffic — Cumulative GB (Prometheus-derived)",
        "ch_l3_cum",
        _chart_l3_prom_cumulative(sglang_ts, _kv_b_pt),
        "Endurance footprint over the collection window. Use for SSD TBW "
        "sizing when extrapolating to a longer production timeframe."))

    sections_html.append(_layer_header("layer-l1", "A3/A2/A1 · L1 HBM / CUDA / GPU", "GPU kernel/runtime layer, HBM occupancy, HBM bandwidth pressure, GPU power and utilization.", "#2f8a4e"))
    sections_html.append(_section("GPU Utilization & HBM (per GPU)",
                                   "ch_gpu", _chart_gpu(gpu_ts),
                                   "Per-GPU lines — click legend entries to isolate one GPU"))
    sections_html.append(_section("Total GPU Power Draw",
                                   "ch_power", _chart_power(power_ts, gpu_ts)))

    sections_html.append(_layer_header("layer-l2", "A3/A2/A1 · L2 DRAM / OS Memory Manager", "Host DRAM and OS memory behavior: page faults, swap activity, NUMA effects and DRAM bandwidth.", "#7a3f97"))
    sections_html.append(_section("Swap Storm — Page Activity",
                                   "ch_swap", _chart_swap_storm(vmstat_ts),
                                   "Per-second rates derived from /proc/vmstat cumulative counters"))
    # DRAM BW: prefer normalized AMDuProf PCM timeseries when present;
    # otherwise parse the raw multi-section AMDuProf CSV/TXT exactly like the
    # static report. This keeps the interactive tab consistent with the static tab.
    _dram_ts_rows = (_read_csv(raw_dir / "amduprof_pcm_timeseries.csv") or
                     _read_csv(raw_dir / "pcm_timeseries.csv"))
    _dram_path = (raw_dir / "amduprof_pcm_raw.txt"
                  if (raw_dir / "amduprof_pcm_raw.txt").exists()
                     and (raw_dir / "amduprof_pcm_raw.txt").stat().st_size > 0
                  else raw_dir / "amduprof_pcm_raw.csv")
    _dram_fig = _chart_dram_bw_from_timeseries(_dram_ts_rows) or _chart_dram_bw(_dram_path)
    sections_html.append(_section("System DRAM Bandwidth (AMD EPYC PMU)",
                                   "ch_dram",
                                   _dram_fig,
                                   "From AMDuProf PCM normalized timeseries or raw Data Fabric counters (1.2s interval)"))

    sections_html.append(_layer_header("layer-l3", "A3/A2/A1 · L3 SSD / OS Block / NVMe", "Storage-tier behavior: NVMe driver, OS block layer, NAND, request-size/IAT distributions, stream bandwidth, and hot/cold regions.", "#a45714"))
    sections_html.append(_section("NVMe IOPS (Read / Write / Trim)",
                                   "ch_nvme_iops", _chart_nvme_iops(nvme_ts)))
    sections_html.append(_section("NVMe Bandwidth",
                                   "ch_nvme_bw", _chart_nvme_bw(nvme_ts)))
    sections_html.append(_section("NVMe Latency & Device Utilization",
                                   "ch_nvme_lat", _chart_nvme_latency(nvme_ts)))
    # ── Queue depth section (only when blktrace QD data is present) ────────
    # Two charts: stacked R/W in-flight over time, then the time-weighted
    # histogram showing what fraction of the run was spent at each QD value.
    if qd_ts_data:
        sections_html.append(_section(
            "NVMe Queue Depth Over Time",
            "ch_qd_ts",
            _chart_qd_timeseries(qd_ts_data),
            ("Exact queue depth derived from blktrace Q (queued) → C (completed) events. "
             "Stacked area shows read vs write in-flight count; purple line is total. "
             "<b>QD = 1</b> means the device serves requests one at a time (latency-bound). "
             "<b>QD ≥ 32 sustained</b> means the device queue is the bottleneck.")))
    if qd_dist_data:
        sections_html.append(_section(
            "Queue Depth Distribution (time-weighted)",
            "ch_qd_dist",
            _chart_qd_distribution(qd_dist_data),
            ("Histogram is time-weighted: bar height = fraction of trace time spent at "
             "that QD value (NOT count of events). Blue: idle (QD ≤ 1) · "
             "green: healthy parallel I/O · amber: deep queue · red: saturation. "
             "Read left-to-right to find where the device actually spends its time.")))
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
    # Coverage warning surfaced inline with the SSD I/O chart, so a reader
    # who jumps directly to it sees the "this is under-counted" caveat next
    # to the data being doubted.
    _ba_cov_warning = (_ba_summary or {}).get("coverage_warning", "")
    _ba_kernel_gb   = _to_float((_ba_summary or {}).get("kernel_wr_gb_delta")) or 0.0
    _ba_capture_pct = (_to_float((_ba_summary or {}).get("captured_vs_kernel_ratio")) or 0.0) * 100
    # Write churn = total write traffic during the window / current FS-used at
    # analyze time. Ratio > 1 means the workload was overwriting/deleting (the
    # common HiCache eviction pattern). Ratio < 1 means writes accumulated
    # without compaction. Surface this number explicitly so the reader doesn't
    # have to mentally compare bar-totals against df.
    _total_write_gb_from_dist = sum(
        (_to_float(r.get("bytes")) or 0)
        for r in (lba_dist or [])
        if (r.get("op") or "").lower() == "write"
    ) / 1e9
    _churn_ratio = (_total_write_gb_from_dist / _ssd_used_gb) if _ssd_used_gb > 0 else 0
    _churn_line = ""
    if _total_write_gb_from_dist > 0 and _ssd_used_gb > 0:
        _churn_line = (
            f"<b>This run:</b> {_total_write_gb_from_dist:.0f} GB of writes "
            f"during the trace window vs <b>{_ssd_used_gb:.0f} GB of files</b> "
            f"on disk at analyze time"
            + (f" — write churn ratio <b>{_churn_ratio:.1f}×</b> "
                f"(workload overwrites/deletes {_churn_ratio:.1f}× as many bytes "
                f"as it leaves behind)." if _churn_ratio > 1.2
                else f" — workload accumulating without major churn "
                     f"({_churn_ratio:.2f}× ratio).")
            + "<br>"
        )
    # Device geometry surfaced by _refresh_smart_capacity — explains why
    # hot LBAs can sit far above the df-used line when blktrace traces the
    # whole device but the FS lives on a partition.
    _traced_device     = smart_sum.get("traced_device", "") or ""
    _fs_backing_dev    = smart_sum.get("fs_backing_device", "") or ""
    _fs_part_start_gb  = _to_float(smart_sum.get("fs_partition_start_gb")) or 0.0
    _lba_offset_warn   = smart_sum.get("lba_offset_warning", "") or ""

    _device_geom_line = ""
    if _traced_device or _fs_backing_dev:
        _device_geom_line = (
            f"<strong>Trace target:</strong> /dev/{_traced_device or '?'} &nbsp;·&nbsp; "
            f"<strong>FS backing device:</strong> /dev/{_fs_backing_dev or '?'}"
            + (f" (partition starts at LBA {_fs_part_start_gb:.0f} GB on device)"
                if _fs_part_start_gb > 0 else "")
            + "<br>"
        )

    _ssd_chart_caption = (
        _device_geom_line +
        _churn_line +
        "Bars (log scale) show <b>total bytes written or read per ~120 equal-width "
        "LBA bins during the collection window</b>. This is cumulative I/O traffic, "
        "not current file allocation: a workload that creates and overwrites or "
        "deletes KV blocks will rack up many TB of writes even if df shows only a "
        "few hundred GB of files at the end. "
        "Diamonds mark the 30 hottest 16 MB buckets per op. "
        "Dotted line = device capacity. The dashed line at 'df' marks the "
        "filesystem byte total at analyze time — it's a different quantity than "
        "the bars: <b>df = files that currently exist</b>, <b>bars = bytes written "
        "during the trace</b>. They can disagree in either direction. "
        "If the bars sum to MORE than df, the workload was churning (writing then "
        "deleting/overwriting). If the bars sum to LESS, pre-existing files weren't "
        "re-touched during this window."
    )
    if _lba_offset_warn:
        _ssd_chart_caption = (
            f"<div style='background:#fef3c7;border-left:4px solid #f59e0b;"
            f"padding:8px 10px;margin-bottom:8px;border-radius:4px'>"
            f"⚠ <strong>LBA addressing mismatch:</strong> {_lba_offset_warn} "
            f"Subtract {_fs_part_start_gb:.0f} GB from hot-LBA values to get "
            f"file-offset within the FS.</div>"
        ) + _ssd_chart_caption
    if _ba_cov_warning:
        _ssd_chart_caption = (
            f"⚠ <strong>Coverage warning:</strong> blktrace captured only "
            f"{_ba_capture_pct:.0f}% of the bytes the kernel's /sys/block counter "
            f"observed during this trace ({_ba_kernel_gb:.0f} GB at the kernel "
            f"vs the bar totals below). The shape below is real but the "
            f"magnitudes are under-counted. See the top finding in the "
            f"executive summary for the cause.<br><br>"
        ) + _ssd_chart_caption
    sections_html.append(_section("SSD I/O Distribution Across LBA Space",
                                   "ch_hot",
                                   _chart_hot_regions(hot_regions,
                                                       lba_dist=lba_dist,
                                                       ssd_capacity_gb=_ssd_cap_gb,
                                                       ssd_used_gb=_ssd_used_gb,
                                                       fs_partition_start_gb=_fs_part_start_gb),
                                   _ssd_chart_caption))

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

    /* Collapsed-empty section styling. The whole <section.card.empty-card>
       collapses to a single muted row when the section has no data, so
       long-tail "requires blktrace" / "Prom-only" sections don't push
       interesting content off-screen. Click anywhere on the summary row
       to expand and read the explanation. */
    section.card.empty-card {{
      padding: 0;
      background: #f8fafc;
      border-color: #e2e8f0;
    }}
    .empty-details {{ margin: 0; }}
    .empty-summary {{
      display: flex; align-items: center; gap: 10px;
      padding: 10px 16px;
      cursor: pointer; user-select: none;
      list-style: none;  /* hide default disclosure triangle on most browsers */
      font-size: 13px; color: #64748b;
      border-radius: 8px;
      transition: background 80ms ease-in-out;
    }}
    .empty-summary::-webkit-details-marker {{ display: none; }}
    .empty-summary:hover {{ background: #f1f5f9; }}
    .empty-details[open] .empty-summary {{
      border-bottom: 1px solid #e2e8f0;
      border-radius: 8px 8px 0 0;
    }}
    .empty-icon {{
      font-size: 16px; color: #94a3b8;
      transition: transform 120ms ease-in-out;
    }}
    .empty-details[open] .empty-icon {{ transform: rotate(45deg); }}
    .empty-title {{
      flex: 1; font-weight: 600; color: #475569;
    }}
    .empty-hint {{
      font-size: 11px; color: #94a3b8; font-style: italic;
    }}
    .empty-details[open] .empty-hint {{ display: none; }}
    .empty-details .no-data {{
      margin: 0; border-radius: 0 0 8px 8px;
      background: #f8fafc;
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
      Model: {_setup_value('Model', 'Model path')}
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
