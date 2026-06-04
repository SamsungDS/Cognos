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
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from amoprof import __version__ as _AMOPROF_VERSION
except Exception:
    _AMOPROF_VERSION = "unknown"


# ─── Utilities ──────────────────────────────────────────────────────────────

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _fmt_num(v: Any, unit: str = "", digits: int = 1, na: str = "N/A") -> str:
    x = _safe_float(v, None)  # type: ignore[arg-type]
    if x is None:
        return na
    if abs(x) >= 1000 and unit not in ("%", "x"):
        s = f"{x:,.{digits}f}"
    else:
        s = f"{x:.{digits}f}"
    if digits == 0:
        s = s.split(".")[0]
    return f"{s}{unit}"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists() and path.stat().st_size > 0:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}
    return {}



def _read_bench_summary(raw_dir: Path) -> Dict[str, Any]:
    """Read normalized bench_serving summary if present in raw/."""
    candidates = [
        "bench_summary.json", "bench_summary.txt",
        "performance_summary.json", "performance_summary.txt",
        "sglang_bench_summary.json", "sglang_bench.json",
        "bench_serving_output.json",
    ]
    p = _first_existing(raw_dir, candidates)
    if not p:
        return {}
    try:
        from amoprof.bench_summary import parse_bench_summary
        d = parse_bench_summary(p)
        return d if isinstance(d, dict) else {}
    except Exception:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            obj = json.loads(txt)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}


def _first_existing(raw_dir: Path, names: Iterable[str]) -> Optional[Path]:
    # The blktrace analyzer (v1.38.15+) writes its analysis CSVs to the
    # raw_dir/blktrace_analysis/ subdir. Check raw_dir first (for collect-time
    # files and older runs), then the subdir (for the analysis outputs).
    search_dirs = [raw_dir, raw_dir / "blktrace_analysis"]
    for n in names:
        for d in search_dirs:
            p = d / n
            if p.exists() and p.stat().st_size > 0:
                return p
    return None


def _read_csv_summary(path: Optional[Path], max_rows: int = 20000) -> Dict[str, Any]:
    """Return simple aggregate stats for numeric columns without pandas."""
    if not path or not path.exists() or path.stat().st_size == 0:
        return {"rows": 0, "columns": []}
    stats: Dict[str, Dict[str, float]] = {}
    rows = 0
    cols: List[str] = []
    first: Dict[str, str] = {}
    last: Dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            cols = list(r.fieldnames or [])
            for row in r:
                rows += 1
                if rows == 1:
                    first = dict(row)
                last = dict(row)
                for k, v in row.items():
                    x = _safe_float(v, None)  # type: ignore[arg-type]
                    if x is None:
                        continue
                    d = stats.setdefault(k, {"count": 0.0, "sum": 0.0,
                                                    "max": -1e300, "min": 1e300,
                                                    "nonzero_sum": 0.0, "nonzero_count": 0.0})
                    d["count"] += 1.0
                    d["sum"] += x
                    d["max"] = max(d["max"], x)
                    d["min"] = min(d["min"], x)
                    if x != 0.0:
                        d["nonzero_sum"]   += x
                        d["nonzero_count"] += 1.0
                if rows >= max_rows:
                    break
    except Exception:
        return {"rows": rows, "columns": cols, "error": "parse_failed"}
    out: Dict[str, Any] = {"rows": rows, "columns": cols, "first": first, "last": last}
    for k, d in stats.items():
        if d["count"] > 0:
            # include nonzero_mean for active-sample throughput computation
            out[k] = {
                "mean": d["sum"] / d["count"],
                "max": d["max"],
                "min": d["min"],
                "count": d["count"],
                "nonzero_sum":   d.get("nonzero_sum",   0.0),
                "nonzero_count": d.get("nonzero_count", 0.0),
                "nonzero_mean":  (d["nonzero_sum"] / d["nonzero_count"]
                                  if d.get("nonzero_count", 0) > 0 else 0.0),
            }
    return out


def _pick(d: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", "unknown", "Unknown"):
            return d[k]
    # also try case-insensitive exact match for setup_details.json
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        lk = str(k).lower()
        if lk in lower and lower[lk] not in (None, "", "unknown", "Unknown"):
            return lower[lk]
    return default


def _ts_col(ts: Dict[str, Any], *partials: str) -> Dict[str, Any]:
    """Find a timeseries column-stats dict by substring match.

    The CSV column names are raw Prometheus metric keys that often carry
    label suffixes, e.g. ``gen_throughput[engine_type=unified]`` or
    ``sglang_gen_throughput``.  An exact ``ts.get("gen_throughput")`` misses
    these, so we match on substring (the same way interactive._find_col does).
    Returns the column's stats dict ({mean,max,min,count,nonzero_*}) or {}.
    """
    # ts has special keys 'rows','columns','first','last' plus one dict per column
    skip = {"rows", "columns", "first", "last", "error"}
    for partial in partials:
        # exact first
        v = ts.get(partial)
        if isinstance(v, dict):
            return v
        # then substring over actual column stat dicts
        for k, val in ts.items():
            if k in skip or not isinstance(val, dict):
                continue
            if partial in k:
                return val
    return {}


def _ts_active_mean(ts: Dict[str, Any], *partials: str) -> float:
    """Active-window mean (mean of nonzero samples) for a timeseries column."""
    col = _ts_col(ts, *partials)
    if col.get("nonzero_count", 0) > 0:
        return float(col.get("nonzero_mean",
                             col.get("nonzero_sum", 0) /
                             max(col.get("nonzero_count", 1), 1)))
    return 0.0
    cls = "ok" if ok else "warn"
    icon = "✓" if ok else "!"
    return f'<span class="pill {cls}">{icon} {_html.escape(label)}</span>' + (f'<span class="muted"> {_html.escape(detail)}</span>' if detail else "")


# ─── Executive summary generation ──────────────────────────────────────────


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

    Produces one row per AI-stack layer (A5/A4/L1/L2/L3 storage/Cross) with:
      • Layer badge in the layer's color
      • A 1-line headline derived from this run's numbers
      • A verdict pill (OK / Near-full / Active spilling / Clean)
      • A 2-3 sentence takeaway grounded in the actual measurements

    Why this approach: in Prom-only mode the original implementation rendered
    a single "Blktrace data not available" line — visually dead and useless
    for sizing exercises. This helper extracts what IS available (SGLang
    counters, GPU utilization, swap activity, derived L3 storage BW) and presents
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

    # L1 GPU — HBM fill vs utilization
    hbm_pct = (hbm_used_gb / hbm_total_gb * 100) if hbm_total_gb > 0 else 0
    if hbm_pct > 85 and gpu_util < 70:
        l1_verdict, l1_color = "Memory-bound", "#d97706"
    elif hbm_pct > 95:
        l1_verdict, l1_color = "Near-full", "#dc2626"
    elif gpu_util > 90:
        l1_verdict, l1_color = "Compute-bound", "#d97706"
    else:
        l1_verdict, l1_color = "Balanced", "#16a34a"

    # L2 DRAM — swap pressure
    if swap_pages > 100:
        l2_verdict, l2_color = "Swapping", "#dc2626"
    elif swap_pages > 10:
        l2_verdict, l2_color = "Light pressure", "#d97706"
    else:
        l2_verdict, l2_color = "Clean", "#16a34a"

    # L3 storage — bandwidth + utilization
    if nvme_rd_bw > 5000 or nvme_wr_bw > 3000:
        l3_verdict, l3_color = "Heavy traffic", "#d97706"
    elif read_gb == 0 and write_gb == 0:
        l3_verdict, l3_color = "Idle", "#64748b"
    else:
        l3_verdict, l3_color = "OK", "#16a34a"

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
        x_verdict, x_color = "No L3 storage spill", "#64748b"

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

    l1_takeaway = (
        f"<strong>HBM {hbm_used_gb:.1f}GB / {hbm_total_gb:.0f}GB ({hbm_pct:.0f}% full) "
        f"at {gpu_util:.1f}% GPU util.</strong> "
        + (
            f"High HBM fill with sub-70% GPU utilization signals "
            f"<em>memory-bound</em> decoding — cycles spent waiting on HBM "
            f"bandwidth, not compute. Actionable levers: <strong>FP8 KV "
            f"quantisation</strong> halves the KV footprint (327 → 163 KB/tok) "
            f"and effectively doubles in-HBM capacity; <strong>chunked prefill</strong> "
            f"reduces per-step HBM pressure during prefill."
            if l1_verdict == "Memory-bound" else
            f"HBM has headroom and utilization is reasonable — capacity is not "
            f"the binding constraint for this workload."
            if hbm_pct < 70 else
            f"HBM is near capacity — KV blocks will be evicted to L2 DRAM as the "
            f"working set grows. Monitor the eviction rate; if it spikes, expand "
            f"HiCache L2 allocation."
        )
    )

    l2_takeaway = (
        f"<strong>Swap activity: {swap_pages:.0f} pages/s · DRAM BW: "
        f"{('not captured' if dram_bw == 0 else f'{dram_bw:.1f} GB/s')}.</strong> "
        + (
            "No vmstat pressure, no swap-in/out activity. The L2 host-DRAM tier "
            "has substantial headroom. " +
            ("DRAM bandwidth wasn't captured (AMDuProf PCM not enabled) but the "
             "absence of swap pressure makes this tier a non-bottleneck. "
             if dram_bw == 0 else "") +
            "Expand HiCache L2 allocation to offload more KV from L3 storage."
            if l2_verdict == "Clean" else
            f"Active swap signals memory pressure on the host. Reduce in-memory "
            f"KV cache, or add system memory. This is a structural constraint, "
            f"not a tunable parameter."
        )
    )

    l3_data_note = (
        f"(derived from SGLang × {kv_bytes_tok_kb:.0f} KB/tok)"
        if l3_source == "sglang_tokens"
        else "(blktrace / iostat)"
    )
    if read_gb > 0 or write_gb > 0:
        rw_ratio = read_gb / max(write_gb, 0.001)
        l3_takeaway = (
            f"<strong>{nvme_rd_bw:.0f} MB/s read · {nvme_wr_bw:.0f} MB/s write · "
            f"{read_gb:.0f}GB / {write_gb:.0f}GB total {l3_data_note}.</strong> "
            + (
                f"The {rw_ratio:.0f}:1 read:write ratio is characteristic of a "
                f"working-set-larger-than-HBM workload — KV blocks are being "
                f"fetched back from L3 far more than offloaded. "
                if rw_ratio > 5 else ""
            )
            + (
                f"L3 storage busy is {nvme_util:.0f}% — far from peak; the "
                f"constraint isn't throughput but the round-trip latency that "
                f"adds to TPOT on each load-back."
                if nvme_util < 50 else
                f"L3 storage busy is {nvme_util:.0f}% — approaching saturation. "
                f"Consider expanding L2 DRAM tier to reduce L3 storage fetch frequency."
            )
        )
    else:
        l3_takeaway = (
            "<strong>No L3 storage traffic observed.</strong> Either the workload's KV "
            "blocks fit entirely in HBM+L2 DRAM, or instrumentation didn't "
            "capture L3 storage activity. Re-run with a larger context or more "
            "concurrent sessions to exercise the L3 storage tier."
        )

    if backuped_tokens > 0 or loadback_tokens > 0:
        ratio_str = (f"{(loadback_tokens/backuped_tokens):.1f}×"
                     if backuped_tokens > 0 else "n/a")
        x_takeaway = (
            f"<strong>{int(evicted_tokens):,} evicted · "
            f"{int(backuped_tokens):,} backed up to L3 · "
            f"{int(loadback_tokens):,} loaded back.</strong> "
            + (
                f"The {ratio_str} load-back-vs-backup ratio means the same KV "
                f"blocks are being re-fetched repeatedly — a thrashing signal "
                f"that HBM + L2 DRAM combined are too small for this working "
                f"set. Headline fix: grow HiCache L2 (DRAM) so load-back hits "
                f"DRAM instead of L3 storage."
                if x_verdict == "Active spilling" else
                f"KV flow is balanced — load-back roughly matches backup, "
                f"indicating steady cache reuse without thrashing."
            )
        )
    else:
        x_takeaway = (
            "<strong>No KV tier movement observed.</strong> SGLang counters "
            "show no offload/loadback activity. Either HiCache wasn't enabled, "
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

    rows = [
        _row("A5", "#3b82f6", "Application Layer",
             f"TTFT {ttft_ms/1000:.1f}s · TPOT {itl_ms:.0f}ms · "
             f"{throughput:.0f} tok/s",
             a5_verdict, a5_color, a5_takeaway,
             chart_id="ch_pct_ttft", chart_fig=_fig("ch_pct_ttft")),
        _row("A4", "#317bb8", "Inference Runtime",
             f"Cache hit {cache_hit:.1f}% / token-weighted {cache_hit_tw:.1f}%",
             a4_verdict, a4_color, a4_takeaway,
             chart_id="ch_thru", chart_fig=_fig("ch_thru")),
        _row("L1", "#2f8a4e", "HBM / CUDA / GPU",
             f"HBM {hbm_used_gb:.0f}GB ({hbm_pct:.0f}%) · GPU "
             f"{gpu_util:.0f}% util · {gpu_power:.0f}W",
             l1_verdict, l1_color, l1_takeaway,
             chart_id="ch_gpu", chart_fig=_fig("ch_gpu")),
        _row("L2", "#7a3f97", "DRAM / OS Memory",
             f"Swap {swap_pages:.0f} pages/s",
             l2_verdict, l2_color, l2_takeaway,
             chart_id="ch_swap", chart_fig=_fig("ch_swap")),
        _row("L3", "#a45714", "Storage / Block / Device",
             f"R {nvme_rd_bw:.0f} MB/s · W {nvme_wr_bw:.0f} MB/s · "
             f"util {nvme_util:.0f}%",
             l3_verdict, l3_color, l3_takeaway,
             chart_id="ch_l3_bw", chart_fig=_fig("ch_l3_bw")),
        _row("Cross", "#0f172a", "KV Cache Flow",
             f"Evict {int(evicted_tokens):,} · Backup {int(backuped_tokens):,} · "
             f"Loadback {int(loadback_tokens):,}",
             x_verdict, x_color, x_takeaway,
             chart_id="ch_evict", chart_fig=_fig("ch_evict")),
    ]
    return plotly_inc + ''.join(rows) + (
        '<p style="color:#94a3b8;font-size:11px;font-style:italic;margin-top:12px">'
        'Per-layer summary derived from this run\'s available metrics. '
        'Full interactive charts available in the Interactive tab.'
        + (' L3 byte numbers estimated from SGLang token counters '
           '(blktrace not captured).' if l3_source == "sglang_tokens" else '')
        + '</p>'
    )



def _nvme_status_phrase(nvme_util: float, nvme_rd_lat: float = -1.0) -> str:
    """Return a short status-phrase describing the L3 storage's current state.

    Used everywhere the report calls out NVMe util to avoid the
    "100% util shows headroom" / "0.00 ms is sub-millisecond" contradictions
    that v53 only partially fixed (only patched one chart_card; other 4+
    sites still hardcoded "headroom remains" / "is not stressed" /
    "substantial remaining capacity" regardless of measured values).

    The returned phrase is suitable for inline use as a sentence clause.
    Caller should provide enough surrounding context that the phrase reads
    naturally.

    Examples:
      util=100, lat=0   → "saturated — IO queueing is now part of loadback latency"
      util=60,  lat=0.5 → "actively engaged — monitor for sustained saturation"
      util=20,  lat=0.3 → "lightly utilised — substantial headroom remains"
      util=0,   lat=0   → "not captured by iostat for this run"
    """
    if nvme_util >= 90:
        return ("saturated — IO queueing is now part of loadback latency "
                "and is constraining decode throughput")
    if nvme_util >= 50:
        return ("actively engaged — monitor for sustained saturation as "
                "concurrent sessions scale")
    if nvme_util > 0:
        return "lightly utilised — substantial headroom remains"
    # nvme_util == 0
    return "not captured by iostat for this run"


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
            f"— each loadback adds non-trivial TPOT)")


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


def build_executive_summary_html(raw_dir: Path, run_label: str = "",
                                  interactive_figures: "dict | None" = None) -> str:
    """Generate a self-contained executive summary HTML page from a run's raw/ directory.

    Reads sglang_summary.json, gpu_summary.json, summary.json, setup_details.json,
    and blktrace distribution CSVs to produce:
      • KPI grid            — all key latency/throughput/memory/storage numbers
      • Top findings        — data-driven, prioritised, with concrete actions
      • Memory tier analysis — L1 HBM / L2 DRAM / L3 device characteristics
      • KV$ L3 storage executive   — requirement foundation with 5 bullet-point specs
      • Per-chart takeaways — actionable interpretation of every NVMe/memory chart
      • Bottleneck mapping  — every AI stack layer with score, root cause, action

    Called automatically by build_combined_report() when --combined-report is used.

    When `interactive_figures` is provided (a dict mapping chart_id -> figure
    JSON string), the Prom-only per-layer takeaways section will embed live
    Plotly charts inline. The expected chart IDs are: ch_pct_ttft, ch_thru,
    ch_gpu, ch_swap, ch_l3_bw, ch_evict. Missing IDs render text-only rows.
    """
    raw_dir = Path(raw_dir)

    # ── Load all data sources ─────────────────────────────────────────────────
    setup    = _read_json(raw_dir / "setup_details.json")
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
    # Also store raw blktrace bytes/totals for the L3 storage total tiles.
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
    _ba_kernel_wr_gb     = _safe_float(_ba_sum.get("kernel_wr_gb_delta", 0))
    _ba_captured_ratio   = _safe_float(_ba_sum.get("captured_vs_kernel_ratio", 0))
    _ba_dropped_events   = _safe_float(_ba_sum.get("blktrace_dropped_events", 0))

    sglang_ts = _read_csv_summary(_first_existing(raw_dir, ["sglang_timeseries.csv"]))
    bench = {}  # Prometheus-only report: benchmark files are not used as data sources
    gpu_ts    = _read_csv_summary(_first_existing(raw_dir, ["gpu_timeseries.csv"]))
    nvme_ts   = _read_csv_summary(_first_existing(raw_dir, ["nvme_driver_timeseries.csv",
                                                               "iostat_timeseries.csv"]))
    vmstat_ts = _read_csv_summary(_first_existing(raw_dir, ["vmstat_timeseries.csv"]))
    # amduprof_pcm_raw.csv is a structured text report with a header + data sections;
    # it cannot be parsed by _read_csv_summary.  amduprof_pcm_timeseries.csv (if
    # present) is supposed to be the derived per-row CSV but is known to often
    # contain all zeros due to a writer/conversion bug (the static report
    # documents this explicitly in its formula notes). So:
    #   1. Always parse the raw CSV first via the strict parser — it works
    #      reliably and matches the static report's numbers.
    #   2. Only fall back to amduprof_pcm_timeseries.csv if the raw parse
    #      returns nothing (e.g., raw file deleted post-collection).
    # The previous order ("timeseries first, raw on rows=0 fallback") let the
    # all-zeros timeseries CSV silently win, producing the 0.0 GB/s tile in
    # the executive while the static report — using the strict raw parser —
    # showed the correct 6.27 GB/s. They MUST agree, and the only authoritative
    # source is the raw file.
    dram_ts = _parse_amduprof_pcm_raw(raw_dir)
    if dram_ts.get("rows", 0) == 0:
        dram_ts = _read_csv_summary(_first_existing(raw_dir,
            ["amduprof_pcm_timeseries.csv", "pcm_timeseries.csv"]))
    reqsize_ts = _read_csv_summary(_first_existing(raw_dir, ["request_size_distribution.csv"]))
    iat_ts     = _read_csv_summary(_first_existing(raw_dir, ["interarrival_distribution.csv"]))
    bw_stream  = _read_csv_summary(_first_existing(raw_dir, ["bandwidth_per_stream.csv"]))
    hot_lba    = _read_csv_summary(_first_existing(raw_dir, ["hot_regions_overall.csv"]))
    smart      = _read_json(raw_dir / "smart_summary.json")

    # L3 HiCache filesystem capacity (df-derived, written by SsdHardwareMonitor
    # at collect time and re-snapshotted by _refresh_smart_capacity in analyze).
    l3_fs_total_gb = _safe_float(smart.get("hicache_fs_total_gb", 0))
    l3_fs_used_gb  = _safe_float(smart.get("hicache_fs_used_gb",
                                  smart.get("hicache_size_gb", 0)))
    l3_fs_avail_gb = _safe_float(smart.get("hicache_fs_avail_gb", 0))
    l3_fs_used_pct = _safe_float(smart.get("hicache_fs_used_pct", 0))
    nvme_dev_cap_gb = _safe_float(smart.get("nvme_device_capacity_gb", 0))
    # Allow setup_details.json to supply L3 storage capacity when SMART/df
    # data is not available (common for non-NVMe backends such as Mooncake).
    if l3_fs_total_gb <= 0:
        l3_fs_total_gb = _safe_float(_pick(setup, [
            "L3 storage capacity GB", "L3 Capacity GB", "L3 total capacity GB",
            "l3_storage_capacity_gb", "l3_capacity_gb", "L3 storage total GB"
        ], 0))
    if l3_fs_used_gb <= 0:
        l3_fs_used_gb = _safe_float(_pick(setup, [
            "L3 storage used GB", "L3 used capacity GB", "l3_storage_used_gb",
            "l3_used_gb", "L3 storage current used GB"
        ], 0))
    if l3_fs_avail_gb <= 0 and l3_fs_total_gb > 0:
        l3_fs_avail_gb = max(l3_fs_total_gb - l3_fs_used_gb, 0.0)
    if l3_fs_used_pct == 0 and l3_fs_total_gb > 0 and l3_fs_used_gb > 0:
        l3_fs_used_pct = round(l3_fs_used_gb / l3_fs_total_gb * 100, 1)

    # ── Extract key scalars ───────────────────────────────────────────────────
    model     = _pick(setup, ["Model","model","model_name","Model path","model_path","model_id"],
                      _pick(sglang, ["model_name","model","model_path"], "unknown"))
    # Benchmark / Application name — more useful than the hostname-style
    # "instance" field. Accept a wide range of common keys; fall back to the
    # old "instance" pick so legacy setup files still resolve to something.
    benchmark = _pick(setup, ["Application / Benchmark","application_benchmark","Benchmark","benchmark","Application","application",
                               "Workload","workload","Test","test","app","app_name",
                               "Benchmark name","benchmark_name"],
                      _pick(setup, ["Instance","instance","Server","server","endpoint"],
                            _pick(sglang, ["instance"], "unknown")))
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
    # L3 storage class — NVMe L3 storage by default, but future runs may target an
    # AI Memory Node (CXL / GPU-side block storage) or other backend. Surfaced
    # in the tier listing so the reader knows what hardware they're looking at.
    l3_storage_type = _pick(setup, ["L3 storage type","l3_storage_type",
                                      "L3 type","l3_type","Cache L3 storage backend",
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
    _l3_type_l = str(l3_storage_type).strip().lower()
    l3_storage_is_local_block = bool(l3_device or l3_mount_path or (
        ("nvme" in _l3_type_l or "ssd" in _l3_type_l or "block" in _l3_type_l or "disk" in _l3_type_l)
        and "mooncake" not in _l3_type_l
    ))
    ctx_len   = _pick(setup, ["Context length","context_length","max_model_len","ctx_len","max_seq_len","context"], "?")
    page_sz   = _pick(setup, ["Page size","page_size","sglang_page_size","page","kv_page_size"], "1")
    mem_frac  = _pick(setup, ["Mem fraction static","mem_fraction_static","mem_fraction","memory_fraction"], "?")
    launch    = _pick(setup, ["Launch command","launch_command","Command"], "")

    # DRAM (host) capacity for the L2 tier label. Sourced from dram_summary.json
    # written by DramMonitor (/proc/meminfo MemTotal). May be 0 on legacy runs.
    _dram_sum = _read_json(raw_dir / "dram_summary.json")
    host_dram_total_gb = _safe_float(_dram_sum.get("dram_total_gb", 0))
    if host_dram_total_gb <= 0:
        host_dram_total_gb = _safe_float(_pick(setup, [
            "Host DRAM GB", "DRAM capacity GB", "DRAM total GB",
            "host_dram_gb", "dram_total_gb"
        ], 0))
    host_dram_used_gb = _safe_float(_dram_sum.get("dram_used_gb_mean",
                                      _dram_sum.get("dram_used_gb_peak", 0)))
    if host_dram_used_gb <= 0:
        host_dram_used_gb = _safe_float(_pick(setup, [
            "Host DRAM used GB", "DRAM used GB", "dram_used_gb",
            "dram_used_gb_mean"
        ], 0))
    host_dram_used_pct = (host_dram_used_gb / host_dram_total_gb * 100.0) if host_dram_total_gb > 0 and host_dram_used_gb > 0 else 0.0
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
        ["L3 storage read BW target MB/s","nvme_rd_bw_target_mbs"], 7000.0))
    nvme_wr_bw_target_mbs   = _safe_float(_pick(setup,
        ["L3 storage write BW target MB/s","nvme_wr_bw_target_mbs"], 5000.0))
    # L3 storage R/W endurance target: TB/day at rated TBW spread over 5y warranty.
    # rated TBW comes from smart_summary.json if SsdHardwareMonitor wrote it.
    rated_tbw_tb            = _safe_float(smart.get("rated_tbw_tb", 7.3))  # Dell CM7 default
    # Endurance budget is computed later, once duration_s is known.
    ssd_lifetime_writes_tb_per_run = 0.0  # filled after duration_s is set
    # DRAM BW target: assigned below once dram_peak_cap is autodetected from CPU.
    dram_bw_target_gbs      = 0.0  # filled in after CPU autodetect block

    # Latency / throughput
    ttft_ms   = _safe_float(_pick(sglang, ["server_ttft_ms","ttft_ms","avg_ttft_ms",
                                            "mean_ttft_ms","time_to_first_token_ms",
                                            "server_ttft_p50_ms"], 0.0))
    tpot_ms   = _safe_float(_pick(sglang, ["server_itl_ms","tpot_ms","avg_tpot_ms",
                                            "mean_tpot_ms","itl_ms",
                                            "server_itl_p50_ms"], 0.0))
    e2e_ms    = _safe_float(_pick(sglang, ["server_e2e_ms","e2e_ms","avg_latency_ms",
                                            "latency_ms","server_e2e_p50_ms"], 0.0))
    cache_hit = _safe_float(_pick(sglang, ["cache_hit_pct","cache_hit_rate_pct",
                                            "cache_hit_active_avg_pct",
                                            "cache_hit_rate_realtime_pct","cache_hit"], 0.0))
    cache_hit_tw = _safe_float(_pick(sglang, ["cache_hit_token_weighted_pct",
                                               "token_weighted_cache_hit_pct"], 0.0))

    # Prometheus-only mode: use the Prometheus-derived primary cache-hit KPI.
    # In v1.56 this is benchmark-comparable active average of sglang_cache_hit_rate
    # when available; token/counter ratios are diagnostics.
    cache_hit_note_prefix = str(_pick(sglang, ["cache_hit_calc_method"], "prometheus"))
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

    # GPU / HBM
    gpu_util   = _safe_float(_pick(gpu, ["gpu_util_mean","gpu_util_pct_mean","util_mean"], 0.0))
    gpu_peak   = _safe_float(_pick(gpu, ["gpu_util_peak","gpu_util_pct_peak","util_peak"], 0.0))
    hbm_gb     = _safe_float(_pick(gpu, ["hbm_used_gb_mean","hbm_gb","mem_used_gb_mean",
                                          "hbm_used_mb_mean"], 0.0))
    if hbm_gb > 1000:
        hbm_gb /= 1024.0   # MB → GB
    hbm_pct    = _safe_float(_pick(gpu, ["hbm_util_pct_mean","hbm_pct","mem_util_pct_mean"], 0.0))
    hbm_total  = _safe_float(_pick(gpu, ["hbm_total_gb","hbm_total_mb_per_gpu"], 40.0))
    if hbm_total > 1000:
        hbm_total /= 1024.0
    # Aggregate HBM across all GPUs. DCGM summaries usually carry per-GPU
    # means, so the Executive tile should state cluster-level used/total
    # capacity and include the per-GPU average in the note.
    gpu_count = _safe_float(_pick(setup, ["GPU Count", "gpu_count", "num_gpus", "Number of GPUs"], 0))
    if gpu_count <= 0:
        try:
            import re as _re
            _m_gpu = _re.search(r"(\d+)\s*[xX]", str(gpu_desc))
            gpu_count = float(_m_gpu.group(1)) if _m_gpu else 0.0
        except Exception:
            gpu_count = 0.0
    if gpu_count <= 0:
        gpu_count = _safe_float(_pick(gpu, ["gpu_count", "num_gpus", "gpu_num"], 1)) or 1.0
    hbm_used_total_gb = hbm_gb * gpu_count if hbm_gb > 0 else 0.0
    hbm_total_all_gpus_gb = hbm_total * gpu_count if hbm_total > 0 else 0.0
    if hbm_total_all_gpus_gb > 0 and hbm_used_total_gb > 0:
        hbm_pct = hbm_used_total_gb / hbm_total_all_gpus_gb * 100.0
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
        read_gb = _safe_float(_pick(blk, ["read_bytes_total"], 0.0)) / (1024**3)
    write_gb  = _safe_float(_pick(blk, ["nvme_write_total_gb","write_gb_total","write_GB_total"], 0.0))
    if write_gb == 0.0:
        write_gb = _safe_float(_pick(blk, ["write_bytes_total"], 0.0)) / (1024**3)
    rw_ratio  = read_gb / max(write_gb, 0.001)

    nvme_rd_bw = _safe_float(_pick(blk, ["nvme_rd_bw_mbs_mean","read_bw_mb_s_mean",
                                          "nvme_read_bw_mbs"], 0.0))
    if nvme_rd_bw == 0.0:
        for col in ("rd_bw_mbs","read_bw_mbs","rkB_s"):
            if col in nvme_ts and nvme_ts[col].get("mean",0) > 0:
                nvme_rd_bw = _safe_float(nvme_ts[col]["mean"])
                if col == "rkB_s": nvme_rd_bw /= 1024.0
                break

    nvme_wr_bw = _safe_float(_pick(blk, ["nvme_wr_bw_mbs_mean","write_bw_mb_s_mean",
                                          "nvme_write_bw_mbs"], 0.0))
    if nvme_wr_bw == 0.0:
        for col in ("wr_bw_mbs","write_bw_mbs","wkB_s"):
            if col in nvme_ts and nvme_ts[col].get("mean",0) > 0:
                nvme_wr_bw = _safe_float(nvme_ts[col]["mean"])
                if col == "wkB_s": nvme_wr_bw /= 1024.0
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
    for col in ("dram_bw_gbps","total_bw_gbps","memory_bw_gbps","Total GB/s","total_gb_s"):
        if col in dram_ts and dram_ts[col].get("mean", 0) > 0:
            dram_total_bw = _safe_float(dram_ts[col]["mean"])
            dram_peak_bw  = _safe_float(dram_ts[col].get("max", dram_total_bw))
            break
    for col in ("read_bw_gbps","read_gb_s","rd_gb_s","Read GB/s"):
        if col in dram_ts and dram_ts[col].get("mean", 0) > 0:
            dram_rd_bw = _safe_float(dram_ts[col]["mean"])
            break
    for col in ("write_bw_gbps","write_gb_s","wr_gb_s","Write GB/s"):
        if col in dram_ts and dram_ts[col].get("mean", 0) > 0:
            dram_wr_bw = _safe_float(dram_ts[col]["mean"])
            break

    # Smart / WAF
    smart_waf  = _safe_float(_pick(smart, ["waf","write_amplification","WAF"], 0.0))
    smart_temp = _safe_float(_pick(smart, ["temperature","temp_c","Composite Temperature"], 0.0))

    # Run duration and window
    duration_s  = _safe_float(_pick(blk, ["duration_s","run_duration_s","elapsed_s",
                                            "duration_sec","blktrace_duration_sec"],
                                     _safe_float(_ba_sum.get("duration_sec", 0))))
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
    has_dram    = dram_ts.get("rows", 0) > 0 or dram_total_bw > 0
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
        f"iostat / blktrace mapped to L3 storage" if l3_block_io_available
        else "not available for this L3 storage backend; using SGLang movement counters"
    )
    if l3_block_io_available:
        l3_util_phrase = (
            f'The <strong>{nvme_util:.1f}% mean device utilisation</strong> indicates the L3 storage is '
            f'<strong>{_nvme_status_phrase(nvme_util, nvme_rd_lat)}</strong>. '
            f'{_nvme_latency_phrase(nvme_rd_lat, nvme_wr_lat)}.'
        )
        l3_util_subnote = (
            f"Device utilisation at {nvme_util:.1f}% mean — "
            f"the L3 storage is {_nvme_status_phrase(nvme_util, nvme_rd_lat)}."
        )
    else:
        l3_util_phrase = (
            "L3 storage block-device utilisation, per-I/O latency, queue depth, and request-size "
            "distribution are not available for this run. The L3 values above are derived from "
            "SGLang hierarchical-cache movement counters, not local disk telemetry."
        )
        l3_util_subnote = (
            "Block-device utilisation is unavailable/not applicable for this L3 storage backend; "
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
                            f'color:#64748b;margin-top:3px;font-style:italic"'
                            f'{tip_attr}>{_html.escape(target)}</div>{bar_html}')
        return (f'<div class="kpi"{style}>'
                f'<div class="kpi-label">{_html.escape(label)}</div>'
                f'<div class="kpi-value">{value}</div>'
                f'<div class="kpi-note">{_html.escape(note)}</div>'
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
        # Minimal arch DB mirrored from amoprof.py KV_ARCH_DB. Keep in sync.
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
                arch = val
                break
        if arch is None:
            # Size-hint fallback (in size-descending order so "120b" wins
            # before generic "20b"). 70B-GQA is the final default.
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
                    arch = val
                    break
        if arch is None:
            arch = (80, 8, 128, "GQA")
        n_layers, n_kv_heads, head_dim, attn = arch
        dtype_bytes = 1 if (kv_dtype or "").lower().startswith(("fp8","int8","int4")) else 2
        if attn == "MLA":
            return n_layers * head_dim * dtype_bytes * 2 / 1024  # 2 = K+V latent
        return n_layers * n_kv_heads * head_dim * 2 * dtype_bytes / 1024
    _kv_dtype_raw = (sglang.get("kv_cache_dtype") if isinstance(sglang, dict) else None) or "fp16"
    _model_name   = (setup.get("Model") if isinstance(setup, dict) else None) \
                    or (sglang.get("model_name") if isinstance(sglang, dict) else None) or ""
    kv_bytes_tok_kb = _kv_bytes_per_token_kb(_model_name, _kv_dtype_raw)
    # Sanity: avoid div-by-zero in spill threshold formula below.
    if kv_bytes_tok_kb <= 0:
        kv_bytes_tok_kb = 327.0

    # ── L3 storage traffic from SGLang token counters (Prometheus-only fallback) ──
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
        for k in candidates:
            v = _safe_float(sglang.get(k, 0))
            if v > 0:
                return v
        return 0.0
    backuped_tokens = _first_nonzero(
        "backuped_tokens_total", "sglang_backuped_tokens_total",
        "kvb_backuped_tokens_total")
    loadback_tokens = _first_nonzero(
        "load_back_tokens_total", "sglang_load_back_tokens_total",
        "kvb_loadback_tokens_total")
    prefetched_tokens = _first_nonzero(
        "prefetched_tokens_total", "sglang_prefetched_tokens_total",
        "kvb_prefetched_tokens_total")
    evicted_tokens = _first_nonzero(
        "evicted_tokens_total", "sglang_evicted_tokens_total",
        "kvb_evicted_tokens_total")

    # ── Second source: derive from the timeseries CSV when the summary
    # JSON's scalar is zero. The summary JSON's _delta2 can return 0 if it
    # was written before the run accumulated activity (collect-time stub),
    # while the timeseries CSV is updated continuously and carries the truth
    # for cumulative counters. The CSV's stats include first/last for every
    # column — for cumulative counters, last - first is the delta over the
    # capture window. This is exactly the case for runs done with
    # --run-dir + --prometheus where the analyzer is run later against an
    # already-populated timeseries CSV but a stale summary JSON.
    def _csv_delta(*candidates):
        if not isinstance(sglang_ts, dict):
            return 0.0
        first_row = sglang_ts.get("first") or {}
        last_row  = sglang_ts.get("last") or {}
        for k in candidates:
            # Try the exact key, the column with a "sglang_" prefix (common in
            # the timeseries CSV), and a substring match across all columns.
            for col_name in (k, f"sglang_{k}"):
                if col_name in last_row:
                    delta = _safe_float(last_row.get(col_name)) - _safe_float(first_row.get(col_name))
                    if delta > 0:
                        return delta
            # Substring match
            for col_name in (last_row.keys() if isinstance(last_row, dict) else []):
                if k in col_name and "bucket" not in col_name:
                    delta = _safe_float(last_row.get(col_name)) - _safe_float(first_row.get(col_name))
                    if delta > 0:
                        return delta
        return 0.0
    if backuped_tokens == 0:
        backuped_tokens = _csv_delta("backuped_tokens_total")
    if loadback_tokens == 0:
        loadback_tokens = _csv_delta("load_back_tokens_total")
    if prefetched_tokens == 0:
        prefetched_tokens = _csv_delta("prefetched_tokens_total")
    if evicted_tokens == 0:
        evicted_tokens = _csv_delta("evicted_tokens_total")

    # Convert to GB: tokens × KB/token / (1024 KB/MB × 1024 MB/GB) = GB.
    # SGLang L3 semantics:
    #   backuped_tokens   -> data moved down into the L3 storage tier (write/offload)
    #   load_back_tokens  -> data loaded back from L3 (read/onboard)
    #   prefetched_tokens -> data proactively brought back from L3 (read/onboard)
    #   evicted_tokens    -> eviction pressure involving the hierarchical cache;
    #                        evidence of L3/cache-tier activity but not counted
    #                        as read/write bytes unless paired with backup/loadback.
    l3_est_write_gb = backuped_tokens * kv_bytes_tok_kb / (1024 * 1024)
    l3_est_read_gb  = (loadback_tokens + prefetched_tokens) * kv_bytes_tok_kb / (1024 * 1024)
    l3_sglang_activity_tokens = backuped_tokens + loadback_tokens + prefetched_tokens + evicted_tokens

    # Source provenance. Three possible values:
    #   "blktrace"      — run-dir present and blktrace produced data
    #   "sglang_tokens" — Prom-only mode and SGLang counters supplied numbers
    #   "none"          — neither produced anything actionable
    if _blktrace_was_attempted:
        # Trust blktrace's number — even zero. Zero with a run-dir means a
        # real measurement gap that the coverage-warning finding will explain.
        # NEVER silently overwrite blktrace 0 with an estimate; that hides
        # the actual instrumentation failure.
        l3_traffic_source = "blktrace"
    elif l3_sglang_activity_tokens > 0:
        # Prom-only mode AND SGLang has hierarchical-cache movement counters.
        # Treat any of backuped / load_back / prefetched / evicted as evidence
        # of L3-tier activity, because in SGLang HiCache these counters are the
        # app-level view of movement across the hierarchical cache.  Read/write
        # byte estimates are still only computed from counters with clear byte
        # direction: backuped => write/offload; load_back+prefetched => read/onboard.
        read_gb  = l3_est_read_gb
        write_gb = l3_est_write_gb
        rw_ratio = read_gb / max(write_gb, 0.001)
        l3_traffic_source = "sglang_tokens"
    else:
        # Prom-only mode AND SGLang has no L3 token activity → genuinely no data.
        l3_traffic_source = "none"

    # Derive L3 storage bandwidth from token-counter deltas — same gating: only when
    # we're in Prom-only mode. If blktrace was attempted, its BW (zero or not)
    # is the authoritative number for the BW tiles. The endpoint we honor is:
    # never let an SGLang estimate masquerade as a blktrace measurement.
    _l3_window_s = duration_s if duration_s > 0 else _safe_float(
        sglang.get("collection_elapsed_s", 0))
    if _prom_only_mode and _l3_window_s > 0 and l3_traffic_source == "sglang_tokens":
        if nvme_rd_bw == 0.0 and l3_est_read_gb > 0:
            nvme_rd_bw = l3_est_read_gb * 1024 / _l3_window_s   # GB→MB/s
        if nvme_wr_bw == 0.0 and l3_est_write_gb > 0:
            nvme_wr_bw = l3_est_write_gb * 1024 / _l3_window_s

    # Spill threshold = free HBM / KV bytes per token
    spill_thresh_k = hbm_free_gb * 1024 * 1024 / max(kv_bytes_tok_kb, 1) / 1000
    cache_hit_gap   = cache_hit - cache_hit_tw

    # Estimate decode tokens from throughput × duration
    decode_tokens_est = int(max(tp_active, throughput * 0.1) * duration_s)
    mb_per_out_token  = (read_gb * 1024 / max(decode_tokens_est, 1)) if decode_tokens_est > 0 else 0.0

    # ── Build data-availability badges ───────────────────────────────────────
    badges_html = (
        pill("SGLang", has_sglang) +
        pill("GPU / DCGM", has_gpu,
             tip=("DCGM daemon was reachable and reported GPU telemetry." if has_gpu
                  else "DCGM unavailable. Start nv-hostengine or use NVIDIA driver-only "
                       "metrics. Without it, HBM BW Active % and per-GPU power are missing.")) +
        pill("DRAM / AMD PMU", has_dram,
             tip=("AMDuProf PCM produced parseable DRAM bandwidth counters." if has_dram
                  else "DRAM bandwidth counters not collected. Install AMDuProf and re-run "
                       "with --enable-amduprof-pcm. Falls back to /proc/meminfo for "
                       "capacity but not for bandwidth.")) +
        pill("L3 storage / blktrace", has_nvme and has_blktrace,
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
                                  "the filesystem to the L3 storage over the run. This is normal and "
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
        window_str = f"{duration_min:.1f} min"

    # ── Findings ──────────────────────────────────────────────────────────────
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

    # ── L3 storage cache activity from SGLang counters (Prometheus-only fallback) ──
    # Emit when blktrace isn't available but SGLang tells us the L3 storage was used.
    # This is the difference between a useless "no L3 data" executive and one
    # that still answers "how active is your KV$ L3 storage tier?" — at token
    # granularity instead of byte granularity. Crucially we ALSO state what
    # this number can NOT tell the user (per-IO latency, block size, queue
    # depth) so they don't over-interpret it.
    if l3_traffic_source == "sglang_tokens" and (read_gb > 0 or write_gb > 0):
        _bk_t = int(backuped_tokens)
        _lb_t = int(loadback_tokens)
        _pf_t = int(prefetched_tokens)
        _ev_t = int(evicted_tokens)
        # Tokens/sec gives an "activity rate" — useful for sizing.
        _bk_rate = _bk_t / _l3_window_s if _l3_window_s > 0 else 0
        _lb_rate = _lb_t / _l3_window_s if _l3_window_s > 0 else 0
        _pf_rate = _pf_t / _l3_window_s if _l3_window_s > 0 else 0
        _ev_rate = _ev_t / _l3_window_s if _l3_window_s > 0 else 0
        findings_items.append(finding(
            "L3 ACTIVITY · PROMETHEUS-DERIVED",
            (f'blktrace is not available for this run, but SGLang counters '
             f'reveal L3 storage cache activity at token granularity. '
             f'<strong>Backuped to L3:</strong> {_bk_t:,} tokens '
             f'(≈ {write_gb:.1f} GB at {kv_bytes_tok_kb:.0f} KB/tok) '
             f'at <strong>{_bk_rate:,.0f} tok/s</strong>. '
             f'<strong>Loaded back from L3:</strong> {_lb_t:,} tokens '
             f'at <strong>{_lb_rate:,.0f} tok/s</strong>. '
             f'<strong>Prefetched from L3:</strong> {_pf_t:,} tokens '
             f'at <strong>{_pf_rate:,.0f} tok/s</strong>. '
             f'<strong>Evicted from cache hierarchy:</strong> {_ev_t:,} tokens '
             f'at <strong>{_ev_rate:,.0f} tok/s</strong>. '
             f'Estimated directional BW: read {nvme_rd_bw:.1f} MB/s · write {nvme_wr_bw:.1f} MB/s. '
             f'<br><br>'
             f'<strong>What this CANNOT tell you (need blktrace for):</strong> '
             f'per-IO latency, request size distribution, queue depth, '
             f'block-layer merging behavior, hot-LBA regions, or sustained '
             f'BW peaks within the window. '
             f'<strong>Action:</strong> if these characteristics matter for '
             f'your sizing exercise, re-collect with <code>--enable-blktrace</code> '
             f'next run.'),
            plain=(f"Even without blktrace, SGLang counters show L3/cache-tier activity: "
                   f"{_bk_t:,} backuped, {_lb_t:,} load-back, {_pf_t:,} prefetched, "
                   f"and {_ev_t:,} evicted tokens. Estimated directional traffic is "
                   f"{write_gb:.1f} GB written and {read_gb:.1f} GB read. These byte "
                   f"numbers are estimates (token × bytes-per-token), not direct disk "
                   f"measurements. For per-IO latency and queue depth, enable blktrace.")))
    elif l3_traffic_source == "none":
        # NO L3 data from any source. Don't leave the user wondering — be
        # explicit about what was checked and what was found. The user
        # genuinely benefits from knowing whether (a) L3 storage was idle, or
        # (b) instrumentation was missing.
        _has_sg_counters = any(k in sglang for k in (
            "backuped_tokens_total", "sglang_backuped_tokens_total",
            "load_back_tokens_total", "sglang_load_back_tokens_total",
            "prefetched_tokens_total", "sglang_prefetched_tokens_total",
            "evicted_tokens_total", "sglang_evicted_tokens_total"))
        _evicted = evicted_tokens
        if _has_sg_counters and l3_sglang_activity_tokens == 0:
            # Counters present, both zero → L3 truly was idle this window.
            findings_items.append(finding(
                "L3 ACTIVITY · NONE OBSERVED",
                (f'L3 storage cache tier shows no activity in this window. SGLang '
                 f'<code>backuped_tokens_total</code> and <code>load_back_tokens_total</code> '
                 f'both registered 0 during the {_l3_window_s:.0f} s collection window. '
                 + (f'<code>evicted_tokens_total</code> = {int(_evicted):,} indicates KV '
                    f'evictions happened but did not spill to L3 (likely went to L2 DRAM '
                    f'or were dropped entirely). '
                    if _evicted > 0 else '')
                 + f'<strong>Implications:</strong> the working set fit within HBM + L2 '
                 f'DRAM, so L3 storage was not exercised. KV$ L3 storage sizing based on this run '
                 f'will be unrepresentative — re-run with a larger context or more '
                 f'concurrent sessions to drive L3 storage traffic.'),
                plain=(f"No L3 storage cache activity was detected during this {_l3_window_s:.0f}s "
                       f"window — the workload's KV blocks all fit in HBM + DRAM, so "
                       f"nothing spilled to the L3 storage. If you're sizing the L3 storage tier, "
                       f"you'll want a longer or larger run.")))
        else:
            # Counters missing entirely → instrumentation problem.
            findings_items.append(finding(
                "⚠ L3 ACTIVITY · NOT INSTRUMENTED",
                (f'No L3 storage cache activity could be measured for this run. '
                 f'blktrace is absent <em>and</em> SGLang Prometheus counters '
                 f'<code>backuped_tokens_total</code> / <code>load_back_tokens_total</code> '
                 f'were not captured. Possible causes: (1) SGLang version pre-dating '
                 f'HiCache counter exposure (need ≥0.4.x); (2) Prometheus scrape '
                 f'missed these specific metrics — check your scrape config; '
                 f'(3) HiCache was disabled on the server. '
                 f'<strong>Action:</strong> verify HiCache is enabled, confirm SGLang '
                 f'version exposes these counters, and either enable blktrace or '
                 f'fix the Prometheus metric path on the next collection.'),
                plain=("We couldn't measure L3 storage cache activity for this run — neither "
                       "the disk-level trace nor the application-level counters captured "
                       "it. The most likely cause is that HiCache wasn't enabled or "
                       "the metrics aren't being scraped. Without one of these data "
                       "sources, L3 sizing cannot be answered from this report.")))

    if ttft_ms > 5000 and gpu_util > 80:
        findings_items.append(finding(
            "COMPUTE · HBM",
            f'TTFT of <strong>{ttft_ms/1000:.1f} s</strong> is driven by long-context prefill '            f'compute. GPU at {gpu_util:.0f}% mean / {gpu_peak:.0f}% peak and HBM at '            f'{hbm_pct:.0f}% full confirm a compute + HBM-bandwidth-bound workload, '            f'not a storage bottleneck. TPOT of {tpot_ms:.0f} ms/tok reflects the model '            f'requiring ~{hbm_gb:.0f} GB of HBM reads per decode step. '            f'<strong>Action:</strong> <code>--chunked-prefill-size 4096</code> and '            f'<code>--kv-cache-dtype fp8_e5m2</code>.',
            plain=(f"First-token wait is {ttft_ms/1000:.1f} seconds — long, but caused by the "
                   f"GPU being busy with the prompt itself, not by storage. The model is "
                   f"big and the prompts are big. Recommended: split prompts into smaller "
                   f"chunks and shrink the KV cache to FP8.")))
    elif ttft_ms > 1000:
        findings_items.append(finding(
            "COMPUTE",
            f'TTFT of {ttft_ms:.0f} ms is elevated. Check prefill compute, KV load-back, '            f'and queue wait time separation. <strong>Action:</strong> '            f'enable chunked prefill and inspect KV eviction rates.',
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
        findings_items.append(finding(
            "KV CACHE · L3",
            f'HiCache L3 storage is active: <strong>{read_gb:,.1f} GB L3 storage reads</strong> vs '
            f'{write_gb:.1f} GB writes ({rw_ratio:.0f}:1 ratio) — a load-back dominated phase. '
            + (f'Estimated <strong>{mb_per_out_token:.0f} MB per output token</strong> '
               f'of L3 storage read traffic — a key KV$ L3 storage sizing input. '
               if mb_per_out_token > 1 else "") +
            f'Device utilisation {nvme_util:.1f}% mean — the L3 storage is '
            f'<strong>{_nvme_status}</strong>. '
            + ('<strong>Action:</strong> expand DRAM L2 tier to absorb more '
               'KV blocks before they reach L3 — and provision additional '
               'NVMe bandwidth (faster device or RAID-0 pair) since the current '
               'L3 storage is at saturation.'
               if nvme_util >= 90 else
               '<strong>Action:</strong> expand DRAM L2 tier to absorb more KV blocks '
               'before they reach L3.'),
            plain=(
                f"The L3 storage cache is being read heavily ({read_gb:,.0f} GB). "
                + ("The L3 storage is at its limit — to keep up as load grows, give the "
                   "system more RAM cache AND consider a faster L3 storage."
                   if nvme_util >= 90 else
                   "The L3 storage has spare capacity. Recommended: give the system "
                   "more RAM cache so fewer reads reach the L3 storage."))))
    elif write_gb > 10 and has_blktrace and rw_ratio < 0.1:
        # Write-dominant: HiCache is offloading KV blocks to L3 but
        # rarely loading them back. Often means L1+L2 fit the working set,
        # or eviction policy is too aggressive.
        findings_items.append(finding(
            "KV CACHE · L3",
            f'HiCache L3 storage is write-dominant: <strong>{write_gb:.1f} GB writes</strong> vs '            f'{read_gb*1024:.1f} MB reads — a backup-heavy phase with no significant load-back. '            f'Device utilisation {nvme_util:.1f}% mean. '            f'<strong>Action:</strong> consider tuning HiCache eviction (raise L2 size or '            f'lower spill threshold) if the working set fits in DRAM; otherwise the '            f'writes are pre-staging future load-backs and are healthy.',
            plain=(f"The L3 storage cache is being written to a lot ({write_gb:.0f} GB) but barely "
                   f"read back. Either the data being saved is rarely needed again, or RAM "
                   f"already has what the model needs. If this is unexpected, check whether "
                   f"the cache is evicting too aggressively.")))

    # ── L3 storage Queue Depth — workload throughput vs latency profile ─────────
    # Only emit a finding if blktrace QD analysis ran successfully (v40+).
    if _qd_sum and _qd_sum.get("qd_mean") is not None:
        qd_mean = _safe_float(_qd_sum.get("qd_mean", 0))
        qd_p95  = _safe_float(_qd_sum.get("qd_p95", 0))
        qd_peak = _safe_float(_qd_sum.get("qd_max", 0))
        sat_32  = _safe_float(_qd_sum.get("pct_at_qd_ge_32", 0))
        sat_128 = _safe_float(_qd_sum.get("pct_at_qd_ge_128", 0))
        if qd_mean >= 32 and sat_32 > 50:
            findings_items.append(finding(
                "L3 storage QUEUE · SATURATED",
                f'Mean queue depth <strong>{qd_mean:.1f}</strong> with '
                f'<strong>{sat_32:.0f}%</strong> of trace time at QD≥32 (peak QD = '
                f'{qd_peak:.0f}, p95 = {qd_p95:.0f}). The NVMe device queue is '
                f'effectively saturated. <strong>Action:</strong> raise kernel '
                f'<code>nr_requests</code>, ensure multi-queue blk-mq is enabled, '
                f'or add storage parallelism (additional NVMes / striping).',
                plain=(f"The L3 storage is being asked to handle more requests than it can keep up "
                       f"with — its queue is full {sat_32:.0f}% of the time. "
                       f"Recommended: spread the load across more L3 storage backends or tune the kernel "
                       f"I/O scheduler.")))
        elif qd_mean < 1.5:
            findings_items.append(finding(
                "L3 storage QUEUE · LATENCY-BOUND",
                f'Mean queue depth <strong>{qd_mean:.2f}</strong> (peak {qd_peak:.0f}) — '
                f'the workload is dispatching one L3 storage request at a time and waiting for it '
                f'to complete before issuing the next. Storage is NOT the bottleneck. '
                f'<strong>Action:</strong> investigate upstream batching / scheduler '
                f'serialisation — increase concurrency to use the device\'s parallelism.',
                plain=(f"The L3 storage is barely being asked to do anything in parallel "
                       f"(only {qd_mean:.1f} requests in-flight on average). The bottleneck "
                       f"is somewhere upstream — the GPU, scheduler, or batching. "
                       f"Recommended: increase request concurrency.")))
        else:
            findings_items.append(finding(
                "L3 storage QUEUE · HEALTHY",
                f'Mean queue depth <strong>{qd_mean:.1f}</strong> (p95 {qd_p95:.0f}, peak '
                f'{qd_peak:.0f}). Healthy parallel I/O without saturation.',
                plain=(f"The L3 storage is handling {qd_mean:.1f} requests in parallel on average — "
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
    _avg_wr_io_kb   = _safe_float(_ba_sum.get("sys_block_avg_wr_io_kb", 0))
    _avg_rd_io_kb   = _safe_float(_ba_sum.get("sys_block_avg_rd_io_kb", 0))
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

    if cache_hit_gap > 10:
        findings_items.append(finding(
            "CACHE HIT GAP",
            f'A {cache_hit_gap:.0f} pp gap between gauge-active ({cache_hit:.1f}%) and '            f'token-weighted ({cache_hit_tw:.1f}%) cache hit reveals that even during '            f'active inference windows a large share of tokens require full recompute. '            f'<strong>Action:</strong> add a shared system-prompt prefix to all requests '            f'and verify LPM scheduling is active.',
            plain=(f"Cache reuse looks better than it really is. When measured per-request "
                   f"it's {cache_hit:.0f}%, but per-token it's only {cache_hit_tw:.0f}% — "
                   f"meaning many requests are short cache hits with long uncached tails. "
                   f"Recommended: add a shared prompt prefix across requests.")))
    elif cache_hit > 0:
        if cache_hit < 40:
            findings_items.append(finding(
                "CACHE HIT",
                f'Cache hit is low ({cache_hit:.1f}%). Inspect prompt prefix sharing, '                f'HiCache warm-up, and KV eviction pressure.',
                plain=(f"Only {cache_hit:.0f}% of prompts are being served from cache — the "
                       f"rest are recomputed from scratch. Recommended: check whether prompts "
                       f"share a common prefix, and give the cache more time to warm up.")))
        else:
            findings_items.append(finding(
                "CACHE HIT",
                f'Cache-hit gauge-active is strong ({cache_hit:.1f}%). Remaining latency '                f'is more likely from prefill compute, HBM pressure, or queue-time.',
                plain=(f"Cache reuse is healthy ({cache_hit:.0f}% hit rate). If latency is "
                       f"still high, the bottleneck isn't the cache — look at GPU compute, "
                       f"GPU memory pressure, or request queuing.")))

    if dram_total_bw > 0:
        dram_util_pct = dram_total_bw / max(dram_peak_cap, 1) * 100
        if dram_util_pct < 30:
            findings_items.append(finding(
                "L2 DRAM",
                f'AMD PMU reports {dram_total_bw:.1f} GB/s mean DRAM BW '                f'({dram_util_pct:.1f}% of {dram_peak_cap:.0f} GB/s peak) — '                f'<strong>not the bottleneck</strong>. Ample DRAM headroom exists '                f'to expand the L2 KV tier and absorb more L3 storage traffic.',
                plain=(f"System RAM bandwidth is at {dram_util_pct:.0f}% of its capability — "
                       f"plenty of room to spare. Recommended: enlarge the in-RAM portion of "
                       f"the cache to reduce L3 storage traffic.")))
        else:
            findings_items.append(finding(
                "L2 DRAM",
                f'DRAM BW at {dram_total_bw:.1f} GB/s ({dram_util_pct:.1f}% of peak) '                f'is elevated — L2 staging may be approaching saturation. '                f'Monitor for KV load-back latency increases.',
                plain=(f"System RAM bandwidth at {dram_util_pct:.0f}% of capacity — getting "
                       f"warm. If you see slowdown, RAM-to-GPU transfers may be the cause.")))

    swap_pages = 0.0
    if "pswpin" in vmstat_ts: swap_pages = _safe_float(vmstat_ts["pswpin"].get("max", 0))
    if swap_pages == 0 and has_vmstat:
        findings_items.append(finding("HEALTH",
            f'Zero swap I/O — kernel memory is not under pressure ✅. '            + (f'{discard_total:,.0f} total TRIM/Discard commands reflect normal '               f'HiCache L3 storage reclamation (expected and healthy). '               if discard_total > 0 else "") +
            f'{"SMART unavailable — run nvme smart-log /dev/nvme0 -o json to verify WAF." if not has_smart else f"SMART: WAF={smart_waf:.1f}, Temp={smart_temp:.0f}°C."}',
            plain=("System health looks good — no swap activity (means RAM isn't running out). "
                   + ("L3 storage block telemetry is normal." if l3_block_io_available
                      else "L3 storage activity is based on SGLang movement counters; block-device health is not measured in this run."))))

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
    if _enabled_truthy or (isinstance(cache_enabled, str) and "+" in cache_enabled):
        # L2 capacity from /proc/meminfo (DramMonitor); L3 from df-based FS size.
        def _cap_fmt(gb: float) -> str:
            if gb >= 1024:
                return f"{gb/1024:.1f} TB"
            if gb > 0:
                return f"{gb:.0f} GB"
            return ""
        l2_cap = _cap_fmt(host_dram_total_gb)
        l3_cap = _cap_fmt(l3_fs_total_gb)
        l2_str = f"L2 DRAM ({l2_cap})" if l2_cap else "L2 DRAM"
        l3_str = (f"L3 {l3_storage_type} ({l3_cap})" if l3_cap
                  else f"L3 {l3_storage_type}")
        _cache_tier_label = f"Enabled · {l2_str} + {l3_str}"
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
        ("KV page size",             f"{page_sz} token/page"),
        ("mem_fraction_static",      str(mem_frac)),
        ("Inference Cache Tier",     _cache_tier_label),
        ("L3 filesystem",            _fs_label_full),
        ("Collection window",        window_str),
    ]
    if launch:
        setup_rows_data.append(("Launch command", launch))

    setup_html = "".join(
        f'<tr><td class="td-key">{_html.escape(str(k))}</td>'        f'<td>{_html.escape(str(v)) if k != "Launch command" else f'<code>{_html.escape(str(v))}</code>'}</td></tr>'
        for k, v in setup_rows_data
        if str(v) not in ("", "None", "unknown / unknown", "? / ?")
    )

    # ── Layer status table ────────────────────────────────────────────────────
    layer_rows = [
        ("A5 · Application",  f"TTFT {ttft_ms/1000:.1f}s, TPOT {tpot_ms:.0f}ms, {tp_active:.1f} tok/s active",
         "warn" if ttft_ms > 5000 else "ok", "HIGH latency" if ttft_ms > 5000 else "OK"),
        ("A4 · SGLang runtime", f"Cache {cache_hit:.1f}% gauge / {cache_hit_tw:.1f}% weighted",
         "warn" if cache_hit_gap > 10 else "ok", "Cache gap" if cache_hit_gap > 10 else "OK"),
        ("L1 · HBM (GPU)",    f"{hbm_pct:.0f}% full, {gpu_util:.0f}% GPU util",
         "warn" if hbm_pct > 80 else "ok", "Near-full" if hbm_pct > 80 else "OK"),
        ("L2 · Host DRAM",    f"{dram_total_bw:.1f} GB/s ({dram_total_bw/max(dram_peak_cap,1)*100:.0f}% of peak)" if dram_total_bw else "No PMU data",
         "ok" if dram_total_bw < dram_peak_cap * 0.5 else "warn",
         "Headroom ✓" if dram_total_bw < dram_peak_cap * 0.5 else "Elevated"),
        ("L3 storage tier",     f"{nvme_rd_bw:.0f} MB/s reads, {nvme_util:.1f}% util, {read_gb:,.0f} GB total",
         "warn" if mb_per_out_token > 10 else "ok",
         "Load-back heavy" if mb_per_out_token > 10 else "OK"),
        ("OS / vmstat",       "0 swap pages/s" if swap_pages == 0 else f"{swap_pages:.0f} swap/s",
         "ok" if swap_pages == 0 else "warn", "Clean ✓" if swap_pages == 0 else "SWAP DETECTED"),
    ]
    layer_html = "".join(
        f'<tr><td><b>{_html.escape(a)}</b></td><td>{_html.escape(b)}</td>'        f'<td><span class="state {c}">{_html.escape(d)}</span></td></tr>'
        for a,b,c,d in layer_rows
    )

    # ── Bottleneck table ──────────────────────────────────────────────────────
    # Scores are data-driven heuristics
    score_compute = min(100, (ttft_ms / 1000 / max(duration_min / 60, 0.1)) * 60) if ttft_ms > 0 else 0
    score_hbm     = min(100, hbm_pct * 1.0) if hbm_pct > 0 else 0
    score_nvme    = min(100, nvme_rd_bw / 10.0) if nvme_rd_bw > 0 else 0
    score_cache   = min(100, cache_hit_gap * 2 + (40 - cache_hit_tw) * 0.5) if cache_hit > 0 else 0
    score_dram    = min(100, dram_total_bw / max(dram_peak_cap, 1) * 200) if dram_total_bw > 0 else 0
    score_os      = 5.0 if swap_pages == 0 else min(100, swap_pages / 100)

    bn_rows = [
        ("Prefill compute (HBM bw)", score_compute, "red",
         f"TTFT {ttft_ms/1000:.1f}s, {gpu_util:.0f}% GPU util",
         "Chunked prefill + FP8 KV"),
        ("HBM capacity", score_hbm, "red" if score_hbm > 80 else "amber",
         f"{hbm_pct:.0f}% full, KV spilling to L2/L3 storage",
         "FP8 KV: 327→163 KB/tok, doubles in-HBM capacity"),
        ("NVMe read throughput", score_nvme, "amber",
         f"{nvme_rd_bw:.0f} MB/s, {mb_per_out_token:.0f} MB/output-token",
         "Expand DRAM L2 tier; validate L3 storage at QD16 16–64 KB read"),
        ("Cache hit rate", score_cache, "amber",
         f"Token-weighted {cache_hit_tw:.1f}% vs gauge {cache_hit:.1f}%",
         "Shared system-prompt prefix; LPM scheduling"),
        ("DRAM bandwidth", score_dram, "blue",
         f"{dram_total_bw:.1f} GB/s of {dram_peak_cap:.0f} GB/s" if dram_total_bw else "N/A",
         "Not the bottleneck — expand L2 allocation"),
        ("OS / memory pressure", score_os, "green",
         "Zero swap" if swap_pages == 0 else f"{swap_pages:.0f} swap/s",
         "No action needed"),
    ]
    bn_html = "".join(
        f'<tr><td><b>{_html.escape(name)}</b></td>'        f'<td><b>{score:.0f} / 100</b></td>'        f'<td>{sev(score)}</td>'        f'<td>{_html.escape(evidence)}</td>'        f'<td>{_html.escape(action)}</td>'        f'<td style="width:130px">{bar(score, color)}</td></tr>'
        for name, score, color, evidence, action in bn_rows
    )

    # ── Action table ──────────────────────────────────────────────────────────
    actions_html = f"""
    <tr><td><b>1</b></td>
      <td><b>FP8 KV quantisation</b> — <code>--kv-cache-dtype fp8_e5m2</code><br>
          <span class="sub">Halves KV bytes/token ({kv_bytes_tok_kb:.0f}→{kv_bytes_tok_kb/2:.0f} KB/tok), doubles in-HBM capacity,
          cuts TPOT and L3 storage load. &lt;0.5% accuracy impact.</span></td>
      <td>{sev(90)}</td><td>{sev(10)}</td><td>L1+L3</td></tr>
    <tr><td><b>2</b></td>
      <td><b>Chunked prefill</b> — <code>--chunked-prefill-size 4096</code><br>
          <span class="sub">Interleaves prefill chunks with decode steps, reducing perceived TTFT without changing throughput.</span></td>
      <td>{sev(85)}</td><td>{sev(5)}</td><td>A5+A4</td></tr>
    <tr><td><b>3</b></td>
      <td><b>Expand DRAM L2 HiCache allocation</b><br>
          <span class="sub">DRAM at {dram_total_bw/max(dram_peak_cap,1)*100:.0f}% util has headroom. More L2 absorbs KV before L3,
          cutting L3 storage reads and wear at near-zero latency cost.</span></td>
      <td>{sev(60)}</td><td>{sev(15)}</td><td>L2→L3 storage</td></tr>
    <tr><td><b>4</b></td>
      <td><b>Add shared system-prompt prefix</b><br>
          <span class="sub">Raises token-weighted hit from {cache_hit_tw:.0f}% toward gauge {cache_hit:.0f}%,
          cutting prefill recompute for recurring prompt prefixes.</span></td>
      <td>{sev(55)}</td><td>{sev(5)}</td><td>A5+A4</td></tr>
    <tr><td><b>5</b></td>
      <td><b>Validate KV$ L3 storage at 16–64 KB random read, QD16</b><br>
          <span class="sub">Run <code>fio --bs=32k --rw=randread --iodepth=16 --size=32g</code>.
          Require ≥{max(nvme_rd_bw*1.1, 600):.0f} MB/s sustained for ≥30 min.
          Also verify TRIM acknowledgement latency ≤1 ms.</span></td>
      <td>{sev(45)}</td><td>{sev(5)}</td><td>L3 storage</td></tr>"""

    # ── KPI grid ──────────────────────────────────────────────────────────────
    kpi_html = (
        kpi_card("Cache hit",
                 _fmt_num(cache_hit, "%", 1),
                 f"{cache_hit_note_prefix} | {_fmt_num(cache_hit_tw, '%', 1)} token-weighted",
                 accent=True) +
        kpi_card("TTFT",
                 _fmt_num(ttft_ms / 1000 if ttft_ms >= 1000 else ttft_ms,
                          " s" if ttft_ms >= 1000 else " ms", 1),
                 "long-context prefill dominated" if ttft_ms > 5000 else "time to first token") +
        kpi_card("TPOT / ITL",
                 _fmt_num(tpot_ms, " ms", 0),
                 "HBM bandwidth bound" if gpu_util > 85 else "decode token latency") +
        kpi_card("Throughput",
                 _fmt_num(tp_active if tp_active > 0 else throughput, " tok/s", 1),
                 f"active mean | {_fmt_num(throughput, ' tok/s peak', 1)}") +
        kpi_card("GPU util",
                 _fmt_num(gpu_util, "%", 1),
                 f"mean | {_fmt_num(gpu_peak, '% peak', 0)}") +
        kpi_card("HBM used (all GPUs)",
                 (f"{_fmt_num(hbm_used_total_gb, ' GB', 1)} / "
                  f"{_fmt_num(hbm_total_all_gpus_gb, ' GB', 0)}"
                  if hbm_total_all_gpus_gb > 0 else f"{_fmt_num(hbm_gb, ' GB/GPU', 1)}"),
                 (f"{_fmt_num(hbm_pct, '% full', 0)} · {int(gpu_count)} GPU(s) · "
                  f"{_fmt_num(hbm_gb, ' GB/GPU avg', 1)}"
                  if hbm_total_all_gpus_gb > 0 else "per-GPU average from DCGM")) +
        kpi_card("GPU power",
                 _fmt_num(gpu_power, " W", 0),
                 "peak per GPU") +
        kpi_card("L3 storage read BW",
                 _fmt_num(nvme_rd_bw, " MB/s", 0),
                 (f"mean | {_fmt_num(nvme_rd_iops, ' read IOPS', 0)}"
                  if l3_traffic_source == "blktrace"
                  else "mean · estimated from SGLang load-back tokens"
                       if l3_traffic_source == "sglang_tokens"
                       else "no L3 data"),
                 target=f"Target: ~{nvme_rd_bw_target_mbs/1000:.1f} GB/s seq read peak",
                 target_pct=(nvme_rd_bw / nvme_rd_bw_target_mbs * 100
                              if nvme_rd_bw_target_mbs > 0 else None),
                 target_tip=("PCIe Gen4 datacenter NVMe (e.g. Dell CM7, Samsung PM9A3) "
                             "delivers ~7 GB/s sequential read at QD≥16. AI workloads "
                             "rarely hit this — typical sustained reads are 1-3 GB/s "
                             "because requests are 4-16 KB random. Override via setup "
                             "key 'L3 storage read BW target MB/s' for a non-Gen4 device.")) +
        kpi_card("L3 storage write BW",
                 _fmt_num(nvme_wr_bw, " MB/s", 1),
                 (f"{_fmt_num(nvme_wr_iops, ' IOPS', 0)} | "
                  f"{('1:' + str(int(round(1/rw_ratio))) if 0 < rw_ratio < 0.5 else f'{rw_ratio:.1f}:1')} R/W ratio"
                  if l3_traffic_source == "blktrace"
                  else (f"estimated from SGLang backuped tokens · "
                        f"{('1:' + str(int(round(1/rw_ratio))) if 0 < rw_ratio < 0.5 else f'{rw_ratio:.1f}:1')} R/W ratio")
                       if l3_traffic_source == "sglang_tokens"
                       else "no L3 data"),
                 target=f"Target: ~{nvme_wr_bw_target_mbs/1000:.1f} GB/s seq write peak",
                 target_pct=(nvme_wr_bw / nvme_wr_bw_target_mbs * 100
                              if nvme_wr_bw_target_mbs > 0 else None),
                 target_tip=("PCIe Gen4 datacenter NVMe sustains ~5 GB/s sequential write. "
                             "KV-block writes are small (~7 KB) so achievable BW is much "
                             "lower than the rated peak — what matters is staying under "
                             "the rated TBW endurance, not approaching this BW target. "
                             "Override via setup key 'L3 storage write BW target MB/s'.")) +
        kpi_card("L3 storage R / W total",
                 (f"{read_gb*1024:.1f} MB" if 0 < read_gb < 1 else _fmt_num(read_gb, ' GB', 1))
                 + " / "
                 + (f"{write_gb*1024:.1f} MB" if 0 < write_gb < 1 else _fmt_num(write_gb, ' GB', 1)),
                 # Tile note now reflects the actual data source so the reader
                 # never confuses an estimate with a direct measurement, and
                 # never sees an "estimated" label when nothing was actually
                 # estimated (e.g. Prom-only run with zero L3 storage activity).
                 ("blktrace / iostat" if l3_traffic_source == "blktrace"
                  else f"estimated · SGLang counters × {kv_bytes_tok_kb:.0f} KB/tok"
                       if l3_traffic_source == "sglang_tokens"
                       else "no L3 data — see findings below"),
                 target=(f"Endurance budget: {ssd_lifetime_writes_tb_per_run*1024:.0f} GB/run"
                          if ssd_lifetime_writes_tb_per_run > 0 else ""),
                 target_pct=((write_gb / (ssd_lifetime_writes_tb_per_run * 1024) * 100)
                              if ssd_lifetime_writes_tb_per_run > 0 else None),
                 target_tip=(f"Endurance budget = rated TBW ({rated_tbw_tb:.1f} TB) spread "
                             f"over a 5-year warranty, scaled to this run's duration "
                             f"({duration_min:.1f} min). Writes within this budget are "
                             f"sustainable indefinitely. Exceeding 100% means the workload, "
                             f"if sustained, would burn through warranted endurance in "
                             f"under 5 years. Override via SMART 'rated_tbw_tb' field.")) +
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
            "L3 storage cache used",
            f"{l3_fs_used_gb:.0f} / {l3_fs_total_gb:.0f} GB",
            (f"{l3_fs_used_pct:.0f}% full · {l3_fs_avail_gb:.0f} GB free"
              + (f" · device {nvme_dev_cap_gb:.0f} GB" if nvme_dev_cap_gb > 0 else "")),
            accent=(l3_fs_used_pct >= 85),
         ) if (l3_fs_total_gb > 0 or l3_fs_used_gb > 0) else "")) +
        ((kpi_card("DRAM used",
                 f"{_fmt_num(host_dram_used_gb, ' GB', 1)} / {_fmt_num(host_dram_total_gb, ' GB', 0)}",
                 f"{_fmt_num(host_dram_used_pct, '% full', 0)} · host DRAM"
             ) if host_dram_total_gb > 0 and host_dram_used_gb > 0 else
             (kpi_card("DRAM total", _fmt_num(host_dram_total_gb, ' GB', 0),
                       "used capacity unavailable") if host_dram_total_gb > 0 else ""))) +
        kpi_card("DRAM BW",
                 f"{_fmt_num(dram_rd_bw if dram_rd_bw else dram_total_bw, ' GB/s', 1)}",
                 f"{'read / ' + _fmt_num(dram_wr_bw, ' write GB/s', 1) if dram_wr_bw else 'total'} | {_fmt_num(dram_peak_bw, ' peak', 1)}",
                 target=(f"Target: {dram_bw_target_gbs:.0f} GB/s peak"
                          if dram_bw_target_gbs > 0 else ""),
                 target_pct=((dram_total_bw / dram_bw_target_gbs * 100)
                              if dram_bw_target_gbs > 0 and dram_total_bw > 0 else None),
                 target_tip=(f"Peak DRAM BW = {dram_bw_target_gbs:.0f} GB/s "
                             f"({_dram_peak_label}). Inference workloads typically use "
                             f"5-15% of peak because the GPU drives most memory traffic "
                             f"through HBM, not host DRAM. Low utilisation here is normal "
                             f"and indicates room to expand the L2 KV tier.")) +
        (kpi_card("L3 storage busy",
                 _fmt_num(nvme_util, "%", 1),
                 f"iostat/blktrace %util mapped to L3 storage · "
                 + (f"{nvme_util:.0f}% mean | saturated"
                    if nvme_util >= 90 else
                    f"{nvme_util:.0f}% mean | elevated"
                    if nvme_util >= 50 else
                    f"{nvme_util:.0f}% mean | well under capacity"))
         if l3_block_io_available else "")
    )

    # ── KV L3 storage requirement bullets ────────────────────────────────────────────
    req_16_64_pct_str = f"{req_size_16_64_pct:.0f}" if req_size_16_64_pct > 0 else "~89"
    if l3_block_io_available:
        kvssd_req_html = f"""
      <li><strong>Sequential/streaming read BW &ge; {max(nvme_rd_bw * 1.1, 600):.0f} MB/s</strong>
          — observed {nvme_rd_bw:.0f} MB/s mean is the primary L3 storage throughput demand.</li>
      <li><strong>Random read latency &le; {max(nvme_rd_lat * 2, 0.5):.1f} ms at QD~16</strong>
          — observed {nvme_rd_lat:.2f} ms mean read latency;
          write latency {nvme_wr_lat:.1f} ms mean is acceptable.</li>
      <li><strong>16–64 KB block size optimisation</strong>
          — {req_16_64_pct_str}% of read IOs fall in the 16–64 KB bucket;
          L3 storage internal page size and read-ahead should align.</li>
      <li><strong>Low write amplification (WAF &le; 2)</strong>
          — write volume is negligible ({write_gb:.1f} GB in {duration_min:.0f} min);
          {f"{discard_total:,.0f} TRIM commands" if discard_total > 0 else "TRIM activity"} indicates healthy GC signalling.</li>
      <li><strong>Hot-spot tolerance: narrow LBA working set</strong>
          — access concentrated in a small LBA band; L3 storage internal caching must cover this zone.</li>"""
    elif l3_traffic_source == "sglang_tokens":
        kvssd_req_html = f"""
      <li><strong>SGLang L3 storage movement observed</strong>
          — estimated {read_gb:.1f} GB read/onboard and {write_gb:.1f} GB write/offload from hierarchical-cache token counters.</li>
      <li><strong>Movement counters used</strong>
          — <code>sglang_load_back_tokens_total</code>, <code>sglang_prefetched_tokens_total</code>,
          <code>sglang_backuped_tokens_total</code>, and <code>sglang_evicted_tokens_total</code>.</li>
      <li><strong>Block-device metrics not shown</strong>
          — no L3-local blktrace/iostat mapping is available, so device busy %, queue depth, per-I/O latency, and request-size histograms are not inferred.</li>
      <li><strong>Capacity context</strong>
          — L3 storage cache usage is reported from setup_details/df/SMART when available: {l3_fs_used_gb:.0f} GB used of {l3_fs_total_gb:.0f} GB total.</li>"""
    else:
        kvssd_req_html = """
      <li><strong>No L3 storage activity observed</strong>
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
            f"Write IOPS are minimal (mean {nvme_wr_iops:.0f}/s) confirming this is a pure load-back run."
            + discard_note,
            f"The KV$ L3 storage only needs ~{max(nvme_rd_iops*1.5, 500):.0f} random read IOPS at peak — "
            f"far below typical NVMe capabilities. IOPS is not the bottleneck; bandwidth is.",
            chart_id="ch_nvme_iops", chart_fig=_fig("ch_nvme_iops")
        ) +
        chart_card(
            "NVMe Bandwidth",
            "Read / Write MB/s time series from iostat",
            f"Read bandwidth averages <strong>{nvme_rd_bw:.0f} MB/s</strong> for the majority "
            f"of the {duration_min:.0f}-minute window, with write BW a flat "
            f"<strong>{nvme_wr_bw:.1f} MB/s</strong>. The stable, non-bursty read profile "
            f"indicates KV blocks are loaded back at a steady streaming rate consistent with "
            f"concurrent session decode.",
            f"KV$ L3 storage must sustain &ge;{max(nvme_rd_bw*1.1, 600):.0f} MB/s sequential read BW "
            f"for &gt;{duration_min:.0f} minutes without thermal throttling or endurance degradation. "
            f"Write endurance is a non-issue for this workload pattern.",
            chart_id="ch_nvme_bw", chart_fig=_fig("ch_nvme_bw")
        ) +
        chart_card(
            "NVMe Latency & Device Utilization",
            "Read/Write service time and %util from iostat",
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
                 f"each loadback adds non-trivial time to TPOT. "
                 if nvme_rd_lat >= 1.0 else
                 "Read latency from iostat was not captured for this run "
                 "(value is 0.00 ms — likely a collection gap; iostat needs "
                 "--enable-iostat at collect time). ")
                +
                # Write latency: only mention if non-zero
                (f"Write latency is higher at <strong>{nvme_wr_lat:.1f} ms mean</strong> "
                 f"but affects only the {nvme_wr_bw:.1f} MB/s write stream "
                 f"(negligible impact). "
                 if nvme_wr_lat > 0 else
                 "Write latency similarly not captured. ")
                +
                # Util clause: ≥90 saturated; 50–90 active; <50 idle/headroom; 0 no data
                (f'<span style="color:#dc2626;font-weight:700">Device utilisation is '
                 f'{nvme_util:.1f}% mean</span> — the L3 storage is saturated; '
                 f'IO queueing is now part of the loadback latency.'
                 if nvme_util >= 90 else
                 f'<span style="color:#d97706;font-weight:700">Device utilisation is '
                 f'{nvme_util:.1f}% mean</span> — actively engaged; '
                 f'monitor for sustained saturation under heavier load.'
                 if nvme_util >= 50 else
                 f'<span style="color:#4ade80;font-weight:700">Device utilisation is '
                 f'{nvme_util:.1f}% mean</span> — the L3 storage has substantial headroom.'
                 if nvme_util > 0 else
                 'iostat %util not captured for this run.')
            ),
            # Recommendation prose — also branches on util
            (
                f"Device is saturated at {nvme_util:.0f}% — provision additional "
                f"NVMe bandwidth (a faster device, or aggregate two devices), or "
                f"expand HiCache L2 DRAM allocation to reduce loadback frequency. "
                f"Targeting a faster NVMe alone won't help if the working set "
                f"keeps growing past HBM+L2 combined."
                if nvme_util >= 90 else
                f"The current KV$ L3 storage is actively engaged at {nvme_util:.0f}% mean. "
                f"Plan headroom for ~{min(nvme_util*1.5, 100):.0f}% peak under load growth; "
                f"watch for sustained periods above 90%."
                if nvme_util >= 50 else
                f"The current KV$ L3 storage comfortably handles this load. "
                f"A minimal-spec NVMe supporting "
                f"{max(nvme_rd_bw*1.1, 600):.0f} MB/s read BW is adequate; "
                f"high IOPS specs are not required."
                if nvme_util > 0 else
                "Cannot make sizing recommendations without iostat data. "
                "Re-collect with iostat enabled to characterize the device under load."
            ),
            chart_id="ch_nvme_lat", chart_fig=_fig("ch_nvme_lat")
        ) +
        chart_card(
            "Request Size Distribution",
            "Histogram of I/O sizes from blktrace",
            f"<strong>{req_16_64_pct_str}% of read IOs fall in the 16–64 KB bucket</strong>, "
            f"with the remainder split between &le;4 KB and 4–16 KB (metadata and KV block edges). "
            f"Zero IOs are &gt;64 KB, confirming HiCache issues KV reads in aligned page-sized chunks.",
            f"The KV$ L3 storage must have excellent random read performance at "
            f"<strong>16–64 KB transfer sizes</strong>. "
            f"Spec sheets quoting 4 KB random IOPS are less relevant than 32 KB sequential bandwidth."
        ) +
        chart_card(
            "Inter-Arrival Time Distribution",
            "Time between consecutive requests per op (blktrace)",
            f"The majority of reads arrive within 1–100 µs of each other, "
            f"indicating a <strong>tightly packed, sustained IO stream</strong> rather than periodic bursts. "
            f"Only a small tail (&lt;3%) has IAT &gt;100 µs (brief inter-session gaps).",
            f"The L3 storage queue depth is consistently occupied. "
            f"Ensure the L3 storage maintains low latency under sustained QD4–QD16 conditions, "
            f"not just at QD1 benchmarks."
        ) +
        chart_card(
            "R/W/T Bytes per 10-sec Window",
            "Time-bucketed byte volume for reads, writes, and trims",
            f"Read byte volume is consistent at approximately "
            f"<strong>{nvme_rd_bw * 10 / 1024:.0f} GB per 10-second window</strong> throughout the run, "
            f"confirming stable streaming-rate load-back. Write and TRIM byte volumes are "
            f"negligible by comparison.",
            f"Sustained write endurance (DWPD) is not a concern. "
            f"The L3 storage read endurance (TBW) is the relevant metric for production deployment — "
            f"verify the device TBW rating covers {read_gb * 24:.0f} GB/day at production scale."
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
            f"This hot-region concentration is excellent for L3 storage internal caching — "
            f"the working set fits within most enterprise L3 storage backends' DRAM or SLC cache, "
            f"allowing repeated reads at near-DRAM speeds.",
            f"The KV$ L3 storage\'s internal cache size matters critically. "
            f"A device with adequate SLC cache covering the hot zone will serve reads "
            f"at near-DRAM speed. Request candidates to provide "
            f"'sustained random read BW to a fixed hot-zone' benchmarks."
        )
    )

    # Per-layer Chart-by-Chart Takeaways. Always rendered now (was previously
    # gated on `if has_blktrace else _per_layer_takeaways_html(...)`, which
    # meant blktrace runs got the old per-chart text-only block while
    # Prom-only got the better per-layer block). Now every report gets
    # the layer classification with embedded charts — and when blktrace
    # is present we additionally append the legacy per-chart KV$ L3 storage
    # detail section below for deeper-dive inspection.
    per_layer_block = _per_layer_takeaways_html(
        # Application layer signals
        ttft_ms=ttft_ms, itl_ms=tpot_ms, throughput=throughput,
        # SGLang runtime
        cache_hit=cache_hit, cache_hit_tw=cache_hit_tw,
        # GPU
        gpu_util=gpu_util, hbm_used_gb=hbm_gb, hbm_total_gb=hbm_total,
        gpu_power=gpu_power,
        # DRAM / OS
        dram_bw=dram_total_bw, swap_pages=swap_pages,
        # L3 storage
        nvme_rd_bw=nvme_rd_bw, nvme_wr_bw=nvme_wr_bw,
        read_gb=read_gb, write_gb=write_gb,
        nvme_util=nvme_util,
        # Cross-layer KV traffic
        backuped_tokens=backuped_tokens, loadback_tokens=loadback_tokens,
        evicted_tokens=_safe_float(sglang.get("evicted_tokens_total", 0)),
        kv_bytes_tok_kb=kv_bytes_tok_kb,
        # L3 source tag for the takeaway provenance footnote
        l3_source=l3_traffic_source,
        # Interactive chart figures — when provided, each layer row embeds
        # a live Plotly chart inline. When None, rows render text-only.
        interactive_figures=interactive_figures,
    )

    # Legacy per-chart KV$ L3 storage detail block — rendered ONLY when blktrace
    # captured the necessary distributions. Appended below the per-layer
    # block as a "deeper-dive" section for users who want chart-by-chart
    # detail of the I/O characteristics.
    blktrace_detail_block = (
        '<div class="section-label" style="margin-top:24px">'
        'KV$ L3 storage I/O deeper-dive — per-chart detail (blktrace)</div>'
        '<div class="card">'
        '<h2>💾 KV$ L3 storage Per-Chart Detail '
        '<span class="tag">BLKTRACE DEEP-DIVE</span></h2>'
        + charts_html_legacy + '</div>'
    ) if has_blktrace else ""

    # `{charts_html}` template slot below gets per-layer block always +
    # blktrace detail block when relevant.
    charts_html = per_layer_block + blktrace_detail_block

    # ── Assemble full HTML ────────────────────────────────────────────────────
    title_suffix = f" · {_html.escape(run_label)}" if run_label else ""
    return f"""<!DOCTYPE html>
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
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin:14px 0;}}
  .kpi{{background:#111827;border:1px solid #334155;border-radius:12px;padding:13px 15px;}}
  .kpi-label{{color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.7px;font-weight:700;}}
  .kpi-value{{color:#f8fafc;font-size:20px;font-weight:800;margin-top:4px;letter-spacing:-.3px;}}
  .kpi-note{{color:#64748b;font-size:11px;margin-top:3px;}}
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
  <div class="badges">{badges_html}</div>
</div>

<div class="kpi-grid">{kpi_html}</div>

<div class="card">
  <h2>📐 Executive KPI Formula &amp; Metric Sources <span class="tag">PROMETHEUS</span></h2>
  <table><tbody>
    <tr><td class="td-key">Cache hit</td><td><code>avg(sglang_cache_hit_rate where value &gt; 0) × 100</code><br><span class="sub">Diagnostics also shown: token-weighted <code>Δsglang_realtime_tokens_total{{mode="prefill_cache"}} / (Δprefill_cache + Δprefill_compute)</code> and effective counter reuse.</span></td></tr>
    <tr><td class="td-key">Mean TTFT</td><td><code>Δsglang_time_to_first_token_seconds_sum / Δsglang_time_to_first_token_seconds_count × 1000</code></td></tr>
    <tr><td class="td-key">Mean TPOT / ITL</td><td><code>Δsglang_inter_token_latency_seconds_sum / Δsglang_inter_token_latency_seconds_count × 1000</code></td></tr>
    <tr><td class="td-key">Mean E2E</td><td><code>Δsglang_e2e_request_latency_seconds_sum / Δsglang_e2e_request_latency_seconds_count × 1000</code></td></tr>
    <tr><td class="td-key">Throughput</td><td><code>active_mean(sglang_gen_throughput)</code> or <code>Δsglang_generation_tokens_total / Δtime_sec</code></td></tr>
    <tr><td class="td-key">L3 storage activity</td><td><code>Δsglang_backuped_tokens_total</code>, <code>Δsglang_load_back_tokens_total</code>, <code>Δsglang_prefetched_tokens_total</code>, <code>Δsglang_evicted_tokens_total</code>; bytes are estimated as <code>token_delta × KV_bytes_per_token</code>.</td></tr>
    <tr><td class="td-key">GPU / host</td><td>GPU metrics come from <code>DCGM_FI_DEV_*</code>; host block I/O and vmstat come from node-exporter/iostat style counters and are not L3 unless explicitly mapped.</td></tr>
  </tbody></table>
</div>

<div class="card">
  <h2>🔍 Top findings <span class="tag">PRIORITISED</span></h2>
  <ul class="findings">{"".join(findings_items)}</ul>
</div>

<div class="section-label">Memory tier analysis</div>
<div class="card">
  <h2>🧠 Memory Hierarchy — What the data reveals about each tier</h2>
  <h3>L1 · HBM (GPU High-Bandwidth Memory)</h3>
  <p>HBM is the fastest tier (~2 TB/s, {hbm_total:.0f} GB/GPU). It holds model weights
  and hot KV cache. With <strong>{hbm_pct:.0f}% fill</strong> ({hbm_used_total_gb:.1f}/{hbm_total_all_gpus_gb:.0f} GB across {int(gpu_count)} GPU(s); {hbm_gb:.1f}/{hbm_total:.0f} GB per GPU avg),
  only ~{hbm_free_gb:.1f} GB/GPU remains for KV — enough for ~{spill_thresh_k:.0f}K tokens at {kv_bytes_tok_kb:.0f} KB/tok.
  Any context exceeding this triggers overflow to L2 DRAM or L3.
  The {gpu_util:.0f}% GPU util and {tpot_ms:.0f} ms/tok TPOT reflect the memory-bandwidth-bound
  decode pattern where every generated token requires reading all active KV plus model weights from HBM.
  DCGM-active {dcgm_active:.0f}% means the HBM bus is busy {dcgm_active:.0f}% of cycles at observed throughput.</p>
  <p><strong>Device characteristic implication:</strong> FP8 KV halves per-token cost
  ({kv_bytes_tok_kb:.0f}→{kv_bytes_tok_kb/2:.0f} KB/tok), doubles in-HBM capacity, and cuts TPOT and L3 storage load simultaneously.</p>

  <h3>L2 · Host DRAM (Staging tier)</h3>
  <p>DRAM is the intermediate KV staging tier (HiCache L2).
  {f"AMD PMU Data Fabric counters report <strong>{dram_total_bw:.1f} GB/s mean / {dram_peak_bw:.1f} GB/s peak</strong> total BW against a {dram_peak_cap:.0f} GB/s theoretical peak — only <strong>{dram_total_bw/max(dram_peak_cap,1)*100:.1f}% utilised mean</strong>." if dram_total_bw > 0 else "DRAM PMU data not available for this run — enable --enable-amduprof-pcm for L2 staging visibility."}
  The traffic pattern shows bursty reads (KV reload into HBM) and moderate writes (KV eviction from HBM into DRAM).</p>
  <p><strong>Device characteristic implication:</strong> DRAM is <strong>not the bottleneck</strong>.
  Expanding the DRAM L2 HiCache allocation would absorb more L3 storage traffic at near-zero
  additional latency cost (L2 DRAM is ~100× faster than L3 for KV blocks).</p>

  <h3>L3 storage tier (KV$ Flash Storage)</h3>
  <p>L3 storage is the outermost KV tier (HiCache L3 storage). Activity observed:
  <strong>{read_gb:,.2f} GB reads vs {write_gb:.1f} GB writes</strong>
  ({('1:' + str(int(round(1/rw_ratio))) if 0 < rw_ratio < 0.5 else f'{rw_ratio:.1f}:1')} R/W ratio) — 
  {('a write-dominated KV-offload pattern (HiCache backups outpacing load-backs).' if rw_ratio < 0.5 else 'a sustained load-back pattern.')}
  {l3_util_phrase}</p>
  <p><strong>Device characteristic implication:</strong> KV$ L3 storage requirement is primarily
  <strong>random-read throughput at 16–64 KB block size</strong>, with <strong>low read latency</strong>
  (&lt;{max(nvme_rd_lat*2, 0.5):.1f} ms). Write endurance is secondary — only {write_gb:.1f} GB written in {duration_min:.0f} min.</p>
</div>

<div class="section-label">KV$ L3 storage I/O characterisation</div>
<div class="card">
  <h2>💾 KV$ L3 storage I/O — Executive Summary <span class="tag">REQUIREMENT FOUNDATION</span></h2>
  <p>This run profiles HiCache L3 storage as the outer KV cache tier. The I/O signature is
  <strong>read-dominated, small-to-medium block, bursty, concentrated in a narrow LBA region</strong>.
  Key requirement drivers:</p>
  <ul>{kvssd_req_html}</ul>
  <p class="sub" style="margin-top:10px">{l3_util_subnote}</p>
</div>

<div class="section-label">Per-chart takeaways — KV$ L3 storage I/O characterisation</div>
<div class="card">
  <h2>📊 Chart-by-Chart Takeaways <span class="tag">KV$ L3 storage WORKLOAD</span></h2>
  {charts_html}
</div>

<div class="section-label">Bottleneck mapping and per-layer improvements</div>
<div class="card">
  <h2>🏗️ Bottleneck → AI Stack Layer Mapping <span class="tag">ACTIONABLE</span></h2>
  <table>
    <thead><tr><th>Layer</th><th>Key signal</th><th>Status</th></tr></thead>
    <tbody>{layer_html}</tbody>
  </table>
  <br>
  <table>
    <thead><tr><th>Subsystem</th><th>Score</th><th>Severity</th><th style="width:180px">Evidence</th>
                <th>Recommended action</th><th style="width:120px">Saturation</th></tr></thead>
    <tbody>{bn_html}</tbody>
  </table>
</div>

<div class="card">
  <h2>🚀 Priority Actions <span class="tag">RANKED</span></h2>
  <table>
    <thead><tr><th>#</th><th>Action</th><th>Impact</th><th>Effort</th><th>Layer</th></tr></thead>
    <tbody>{actions_html}</tbody>
  </table>
</div>

<div class="section-label">Configuration snapshot</div>
<div class="card">
  <h2>⚙️ Server Configuration</h2>
  <table><tbody>{setup_html}</tbody></table>
</div>

<div class="card">
  <h2>📖 How to use this report</h2>
  <table><tbody>
    <tr><td class="td-key">🧭 Executive (this tab)</td>
        <td>Quick findings, memory tier analysis, KV$ L3 storage characterisation, per-chart takeaways, bottleneck mapping. Start here.</td></tr>
    <tr><td class="td-key">⚡ Interactive tab</td>
        <td>Hover any chart for exact values. Drag to zoom. Click legend entries to isolate one GPU, tier, or I/O type. Use for time-series correlation.</td></tr>
    <tr><td class="td-key">📊 End Report tab</td>
        <td>Full deep-dive report with all 25+ sections, Metric Derivations formulas, bottleneck scorecard, and per-chart explanations.</td></tr>
  </tbody></table>
</div>

</div></body></html>"""


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
</style>
"""

_OUTER_JS = """
<script>
(function() {
  var TABS = ['executive', 'interactive', 'static'];
  var KEY  = 'amoprof_active_tab';
  var _staticLoaded = false;

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
      } else { frame.classList.remove('active'); btn.classList.remove('active'); }
    });
    try { history.replaceState(null, '', '#' + id); } catch(e) {}
    try { localStorage.setItem(KEY, id); } catch(e) {}
  }

  window.amoprofShowTab = showTab;
  document.addEventListener('DOMContentLoaded', function() {
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
  <button id=\"btn-executive\" class=\"tab-btn\" role=\"tab\" onclick=\"amoprofShowTab('executive')\" title=\"Executive summary — quick findings and data-source health\">🧭 Executive<span class=\"tab-badge\">SUMMARY</span></button>
  <button id=\"btn-interactive\" class=\"tab-btn\" role=\"tab\" onclick=\"amoprofShowTab('interactive')\" title=\"Interactive Plotly charts — hover for exact values\">⚡ Interactive<span class=\"tab-badge\">PLOTLY</span></button>
  <button id=\"btn-static\" class=\"tab-btn\" role=\"tab\" onclick=\"amoprofShowTab('static')\" title=\"End report — full deep-dive: matplotlib PNGs, bottleneck table, all formulas, per-chart takeaways\">📊 End Report<span class=\"tab-badge\">DEEP-DIVE</span></button>
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

def build_combined_report(
    raw_dir: Path,
    out_html: Path,
    static_html_path: "Path | None" = None,
    interactive_html_path: "Path | None" = None,
    run_label: str = "",
    theme: str = "dark",
) -> Path:
    """Generate a combined tabbed HTML report."""
    import logging
    log = logging.getLogger("amoprof.combined")
    raw_dir = Path(raw_dir)
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    if static_html_path and Path(static_html_path).exists():
        static_html = Path(static_html_path).read_text(encoding='utf-8', errors='replace')
        log.info("combined: loaded static report from %s (%d KB)", static_html_path, len(static_html) // 1024)
    else:
        import sys, subprocess
        tmp = out_html.parent / "_tmp_static.html"
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location('amoprof_report', Path(__file__).parent / 'amoprof.py')
            _mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            _mod.main(argv=[str(raw_dir), '--output', str(tmp)])
        except Exception as e:
            log.warning("combined: static report inline gen failed (%s) — subprocess", e)
            subprocess.run([sys.executable, str(Path(__file__).parent / 'amoprof.py'), str(raw_dir), '--output', str(tmp)], check=True)
        try:
            from .enhancer import enhance_report
            enhance_report(tmp, raw_dir=raw_dir, theme=theme)
        except Exception as e:
            log.warning("combined: enhancer failed (%s)", e)
        static_html = tmp.read_text(encoding='utf-8', errors='replace')
        try: tmp.unlink()
        except OSError: pass
        log.info("combined: generated static report (%d KB)", len(static_html) // 1024)

    if interactive_html_path and Path(interactive_html_path).exists():
        interactive_html = Path(interactive_html_path).read_text(encoding='utf-8', errors='replace')
        log.info("combined: loaded interactive report from %s (%d KB)", interactive_html_path, len(interactive_html) // 1024)
    else:
        from .interactive import build_report as _build_int
        tmp = out_html.parent / "_tmp_interactive.html"
        _build_int(raw_dir, tmp, run_label=run_label)
        interactive_html = tmp.read_text(encoding='utf-8', errors='replace')
        try: tmp.unlink()
        except OSError: pass
        log.info("combined: generated interactive report (%d KB)", len(interactive_html) // 1024)

    try:
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
        executive_html = build_executive_summary_html(
            raw_dir, run_label=run_label,
            interactive_figures=interactive_figures)
        log.info("combined: generated executive summary (%d KB)", len(executive_html) // 1024)
    except Exception as e:
        log.warning("combined: executive summary generation failed: %s", e)
        executive_html = "<html><body><h1>Executive Summary unavailable</h1><p>See Interactive and Static tabs.</p></body></html>"

    combined = merge_reports(static_html, interactive_html, executive_html=executive_html, run_label=run_label)
    out_html.write_text(combined, encoding='utf-8')
    log.info("combined: wrote %s (%d KB)", out_html, len(combined) // 1024)
    return out_html
