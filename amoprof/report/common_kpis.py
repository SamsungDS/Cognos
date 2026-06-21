
"""Shared AMOprof report KPI calculations.

This module is the single source of truth for common report tiles used by
Executive, Interactive, and End Report.  Report renderers should not recompute
these independently because small differences in fallback order, rounding, or
label names create confusing cross-tab mismatches.
"""
from __future__ import annotations

import csv
import html as _html
import json
import math
import re
from pathlib import Path
from typing import Any


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


def _read_json(path: Path) -> dict:
    try:
        if path.exists() and path.stat().st_size > 0:
            obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    return {}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size <= 0:
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _metric_stem_norm(name: str) -> str:
    """Normalize only the metric stem, stripping Prometheus label suffixes.

    Examples:
      sglang_gen_throughput[engine_type=unified] -> sglanggenthroughput
      sglang:gen_throughput{engine_type="unified"} -> sglanggenthroughput
    """
    stem = re.split(r"[\[{]", str(name), maxsplit=1)[0]
    return _norm_name(stem)


def _find_col(rows: list[dict[str, Any]], *partials: str) -> str:
    """Find a metric column without loose substring matching.

    Exact/suffix matching is performed on the metric stem only. This preserves
    v1.39.48's regression guard against helper/debug substring matches while
    correctly handling Prometheus-labelled columns such as
    `sglang_gen_throughput[engine_type=unified]`.
    """
    if not rows:
        return ""
    keys: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    wanted = [_norm_name(p) for p in partials if p]

    for k in keys:
        nk = _metric_stem_norm(k)
        if any(nk == w for w in wanted):
            return k

    for k in keys:
        nk = _metric_stem_norm(k)
        if any(w and nk.endswith(w) for w in wanted):
            return k
    return ""


def _delta(rows: list[dict[str, Any]], *partials: str) -> float:
    col = _find_col(rows, *partials)
    if not col or not rows:
        return 0.0
    first = None
    last = None
    for r in rows:
        x = _safe_float(r.get(col), None)  # type: ignore[arg-type]
        if x is None:
            continue
        if first is None:
            first = x
        last = x
    if first is None or last is None:
        return 0.0
    d = float(last) - float(first)
    return d if d > 0 else 0.0


def _ratio_delta_ms(rows: list[dict[str, Any]], sum_name: str, count_name: str) -> float:
    ds = _delta(rows, sum_name)
    dc = _delta(rows, count_name)
    if ds > 0 and dc > 0:
        return ds / dc * 1000.0
    return 0.0


def _active_values(rows: list[dict[str, Any]], *partials: str) -> list[float]:
    col = _find_col(rows, *partials)
    vals: list[float] = []
    if not col:
        return vals
    for r in rows:
        x = _safe_float(r.get(col), 0.0)
        if x > 0:
            vals.append(x)
    return vals


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    xs = sorted(vals)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def _pct_json_value(pct_ts: dict, metric_key: str, percentile: str = "p50") -> float:
    """Return active-window average of percentile samples.

    These samples are generated from Prometheus histogram_quantile when the
    histogram is available. They are preferred over ratio fallback p50 values.
    """
    try:
        block = (pct_ts or {}).get(metric_key) or {}
        vals = block.get(percentile) or []
        clean = []
        for v in vals:
            x = _safe_float(v, 0.0)
            if x > 0:
                clean.append(x)
        return _mean(clean)
    except Exception:
        return 0.0


def _summary_first(summary: dict, *keys: str) -> float:
    for k in keys:
        v = _safe_float(summary.get(k), 0.0)
        if v > 0:
            return v
    return 0.0


def _duration_s(raw_dir: Path, rows: list[dict[str, Any]], summary: dict) -> float:
    sj = _read_json(raw_dir / "summary.json")
    meta = sj.get("meta") if isinstance(sj.get("meta"), dict) else {}
    for v in [meta.get("duration_s"), summary.get("duration_s"), summary.get("elapsed_s")]:
        x = _safe_float(v, 0.0)
        if x > 0:
            return x
    # Try timestamp/time_sec range in rows.
    for cands in [("time_sec",), ("timestamp",), ("ts",)]:
        col = _find_col(rows, *cands)
        if col:
            vals = [_safe_float(r.get(col), 0.0) for r in rows]
            vals = [v for v in vals if v > 0]
            if len(vals) >= 2 and max(vals) > min(vals):
                return max(vals) - min(vals)
    return 0.0


def compute_common_kpis(raw_dir: Path) -> dict[str, Any]:
    """Compute canonical common KPI values once for all report tabs."""
    raw_dir = Path(raw_dir)
    rows = _read_csv_rows(raw_dir / "sglang_timeseries.csv")
    pct_ts = _read_json(raw_dir / "sglang_percentiles_timeseries.json")
    summary = _read_json(raw_dir / "sglang_summary.json")

    out: dict[str, Any] = {
        "source": "amoprof.report.common_kpis.compute_common_kpis",
        "raw_dir": str(raw_dir),
    }

    # Selected-window mean latencies from cumulative counter deltas.
    out["ttft_ms"] = (
        _ratio_delta_ms(rows, "sglang_time_to_first_token_seconds_sum", "sglang_time_to_first_token_seconds_count")
        or _ratio_delta_ms(rows, "time_to_first_token_seconds_sum", "time_to_first_token_seconds_count")
        or _summary_first(summary, "server_ttft_ms", "ttft_ms", "mean_ttft_ms")
    )
    out["tpot_ms"] = (
        _ratio_delta_ms(rows, "sglang_inter_token_latency_seconds_sum", "sglang_inter_token_latency_seconds_count")
        or _ratio_delta_ms(rows, "inter_token_latency_seconds_sum", "inter_token_latency_seconds_count")
        or _summary_first(summary, "server_itl_ms", "server_tpot_ms", "tpot_ms", "itl_ms", "mean_tpot_ms")
    )
    out["e2e_ms"] = (
        _ratio_delta_ms(rows, "sglang_e2e_request_latency_seconds_sum", "sglang_e2e_request_latency_seconds_count")
        or _ratio_delta_ms(rows, "e2e_request_latency_seconds_sum", "e2e_request_latency_seconds_count")
        or _summary_first(summary, "server_e2e_ms", "e2e_ms", "mean_e2e_ms")
    )

    # Percentile values from histogram_quantile-generated percentile file first.
    out["ttft_p50_ms"] = (
        _pct_json_value(pct_ts, "ttft", "p50")
        or _summary_first(summary, "server_ttft_p50_ms", "ttft_p50_ms", "sess_ttft_p50_ms")
    )
    out["tpot_p50_ms"] = (
        _pct_json_value(pct_ts, "itl", "p50")
        or _pct_json_value(pct_ts, "tpot", "p50")
        or _summary_first(summary, "server_itl_p50_ms", "server_tpot_p50_ms", "tpot_p50_ms", "sess_tpot_p50_ms")
    )
    out["e2e_p50_ms"] = (
        _pct_json_value(pct_ts, "e2e", "p50")
        or _summary_first(summary, "server_e2e_p50_ms", "e2e_p50_ms", "sess_e2e_p50_ms")
    )

    # Throughput: keep mean / p50 / peak from one canonical source.
    #
    # Prefer active `sglang_gen_throughput[...]` samples when present because
    # those are the actual selected-window decode-throughput trace used in the
    # interactive chart. Summary fields are fallback only. Peak is never allowed
    # to be below mean or p50.
    tp_vals = (
        _active_values(rows, "sglang_gen_throughput")
        or _active_values(rows, "gen_throughput")
        or _active_values(rows, "generation_throughput")
    )
    if tp_vals:
        out["throughput_mean"] = _mean(tp_vals)
        out["throughput_p50"] = _median(tp_vals)
        out["throughput_peak"] = max(tp_vals)
        out["throughput_method"] = "active_sglang_gen_throughput_samples"
    else:
        tp_summary_mean = _summary_first(summary, "gen_tp_active_mean", "gen_tp_mean", "throughput_mean", "ai_op_decode_tok_s")
        tp_summary_p50 = _summary_first(summary, "gen_tp_active_p50", "gen_tp_p50", "throughput_p50")
        tp_summary_peak = _summary_first(summary, "gen_tp_peak", "throughput_peak", "peak_throughput_tok_s")
        out["throughput_mean"] = tp_summary_mean
        out["throughput_p50"] = tp_summary_p50 or tp_summary_mean
        out["throughput_peak"] = tp_summary_peak
        out["throughput_method"] = "summary_fallback"

    if out["throughput_mean"] <= 0:
        dur = _duration_s(raw_dir, rows, summary)
        gen_delta = _delta(rows, "sglang_generation_tokens_total") or _delta(rows, "generation_tokens_total")
        if gen_delta > 0 and dur > 0:
            out["throughput_mean"] = gen_delta / dur
            out["throughput_p50"] = out["throughput_p50"] or out["throughput_mean"]
            out["throughput_method"] = "generation_token_counter_fallback"

    out["throughput_peak"] = max(out["throughput_peak"], out["throughput_mean"], out["throughput_p50"])


    # Cache hit primary: use AMOprof's vetted cache-hit summary first.
    #
    # Important regression guard:
    #   v1.39.45 briefly recomputed this directly from raw CSV counters. Some
    #   runs contain multiple similarly named prompt-token counters/histogram
    #   helper columns, and the generic column matcher can pick a denominator
    #   that is not the established report KPI denominator. That produced a
    #   false drop such as 61.3% -> 9.6% on identical raw data. The static
    #   cache-methodology table already computes and stores the vetted value in
    #   sglang_summary.json, so common_kpis must trust it first. Counter math is
    #   only a fallback for older raw dirs with no summary cache KPI.
    summary_cache = _summary_first(
        summary,
        "cache_hit_token_weighted_pct",
        "cache_hit_pct",
        "cache_hit_gauge_active_pct",
        "cache_hit_effective_prompt_pct",
        "server_cache_hit_pct",
    )
    if summary_cache > 0:
        out["cache_hit_pct"] = summary_cache
        out["cache_hit_method"] = str(
            summary.get("cache_hit_calc_method")
            or "summary_vetted_cache_hit_token_weighted"
        )
    else:
        cached = _delta(rows, "sglang_cached_tokens_total") or _delta(rows, "cached_tokens_total")
        prompt = _delta(rows, "sglang_prompt_tokens_total") or _delta(rows, "prompt_tokens_total")
        if cached > 0 and prompt > 0:
            ratio = cached / prompt * 100.0
            # Guard against nonsensical denominators from loose column matching.
            out["cache_hit_pct"] = ratio if 0.0 <= ratio <= 100.0 else 0.0
            out["cache_hit_method"] = "fallback_selected_window_counter_ratio_cached_tokens_over_prompt_tokens"
        else:
            out["cache_hit_pct"] = 0.0
            out["cache_hit_method"] = "unavailable"

    # Optional diagnostics kept in the same object for notes/cards.
    ch_vals = _active_values(rows, "sglang_cache_hit_rate") or _active_values(rows, "cache_hit_rate")
    out["cache_hit_time_weighted_pct"] = _mean(ch_vals) * 100.0 if ch_vals and max(ch_vals) <= 1.5 else _mean(ch_vals)

    # Round only at render time; keep numeric values here.
    return out


def _value_text(key: str, value: float) -> str:
    if key in {"cache_hit_pct"}:
        return f"{float(value):.1f}"
    if key.startswith("tpot") or key.startswith("throughput"):
        return f"{float(value):.1f}"
    # TTFT/E2E can be very large; use integer ms for cross-tab exactness.
    return f"{float(value):.0f}"


def _unit_for_key(key: str) -> str:
    if key in {"cache_hit_pct"}:
        return "%"
    if key.startswith("throughput"):
        return "tok/s"
    if key.startswith("tpot"):
        return "ms"
    if key.startswith("ttft") or key.startswith("e2e"):
        return "ms"
    return ""


def _note_for_key(key: str, kpis: dict[str, Any]) -> str:
    if key == "cache_hit_pct":
        return str(kpis.get("cache_hit_method") or "Canonical selected-window cache-hit KPI")
    if key.endswith("_p50_ms"):
        return "Canonical common KPI: histogram percentile when available; shared by Executive, Interactive, and End Report"
    if key.endswith("_ms"):
        return "Canonical common KPI: selected-window Δsum/Δcount; shared by Executive, Interactive, and End Report"
    if key.startswith("throughput"):
        return "Canonical common KPI: active throughput samples/counter fallback; shared by Executive, Interactive, and End Report"
    return "Canonical common KPI shared by Executive, Interactive, and End Report"


def _replace_kpi_value_by_label(report_html: str, label_variants: list[str], key: str,
                                value: float, kpis: dict[str, Any],
                                canonical_label: str | None = None) -> str:
    out = report_html
    unit = _unit_for_key(key)
    val_txt = _value_text(key, value)
    note = _note_for_key(key, kpis)
    unit_span = f'<span style="font-size:13px;color:#94a3b8;margin-left:4px">{_html.escape(unit)}</span>' if unit else ""

    for label in label_variants:
        repl_label = canonical_label or label

        # Standard KPI card/tile with semantic classes: Executive + Interactive.
        pat = re.compile(
            r'(<div[^>]*class=["\'][^"\']*\bkpi-label\b[^"\']*["\'][^>]*>)' + re.escape(label) + r'(</div>\s*'
            r'<div[^>]*class=["\'][^"\']*\bkpi-value\b[^"\']*["\'][^>]*>)(.*?)(</div>\s*'
            r'<div[^>]*class=["\'][^"\']*\bkpi-note\b[^"\']*["\'][^>]*>)(.*?)(</div>)',
            re.S | re.I,
        )

        def repl(m):
            return f"{m.group(1)}{repl_label}{m.group(2)}{val_txt} {unit}{m.group(4)}{_html.escape(note)}{m.group(6)}"

        out = pat.sub(repl, out)

        # Inline styled End Report cards. Some tiles (notably Throughput peak)
        # have no note in the raw static report, so the note block must be
        # optional and must not consume the next KPI card.
        pat2 = re.compile(
            r'(<div\s+style=["\'][^"\']*background:#ffffff;[^"\']*min-width:120px[^"\']*["\']>\s*'
            r'<div\s+style=["\'][^"\']*font-size:10px;[^"\']*text-transform:uppercase[^"\']*["\']>)'
            + re.escape(label) +
            r'(</div>\s*<div\s+style=["\'][^"\']*font-size:20px;[^"\']*["\']>)(.*?)(</div>)'
            r'(\s*<div\s+style=["\'][^"\']*font-size:10px;[^"\']*["\']>.*?</div>)?(\s*</div>)',
            re.S | re.I,
        )

        def repl2(m):
            note_div = f'<div style="font-size:10px;color:#64748b;margin-top:2px">{_html.escape(note)}</div>'
            return f"{m.group(1)}{repl_label}{m.group(2)}{val_txt}{unit_span}{m.group(4)}{note_div}{m.group(6)}"

        out = pat2.sub(repl2, out)

    return out


def _insert_missing_throughput_peak_tile(report_html: str, kpis: dict[str, Any]) -> str:
    """Add a Throughput peak tile to Executive/Interactive if only mean/p50 exist."""
    if "Throughput peak" in report_html:
        return report_html
    peak = _safe_float(kpis.get("throughput_peak"), 0.0)
    if peak <= 0:
        return report_html
    val_txt = _value_text("throughput_peak", peak)
    unit = _unit_for_key("throughput_peak")
    note = _html.escape(_note_for_key("throughput_peak", kpis))

    # Executive card style.
    pat_exec = re.compile(
        r'(<div class="kpi">\s*<div class="kpi-label">Throughput p50</div>\s*'
        r'<div class="kpi-value">.*?</div>\s*<div class="kpi-note">.*?</div>\s*</div>)',
        re.S,
    )
    exec_tile = (
        f'<div class="kpi"><div class="kpi-label">Throughput peak</div>'
        f'<div class="kpi-value">{val_txt} {unit}</div><div class="kpi-note">{note}</div></div>'
    )
    if pat_exec.search(report_html):
        return pat_exec.sub(r'\1' + exec_tile, report_html, count=1)

    # Interactive tile style.
    pat_int = re.compile(
        r'(<div class="kpi-tile"[^>]*>\s*<div class="kpi-label">Throughput p50</div>\s*'
        r'<div class="kpi-value"[^>]*>.*?</div>\s*<div class="kpi-note">.*?</div>\s*</div>)',
        re.S,
    )
    int_tile = (
        f'<div class="kpi-tile" title="Canonical common KPI peak throughput">'
        f'<div class="kpi-label">Throughput peak</div>'
        f'<div class="kpi-value" style="color:#0f172a">{val_txt}<span class="kpi-unit">{unit}</span></div>'
        f'<div class="kpi-note">{note}</div></div>'
    )
    if pat_int.search(report_html):
        return pat_int.sub(r'\1' + int_tile, report_html, count=1)

    return report_html


def apply_common_kpis_to_html(report_html: str, raw_dir: Path | None = None,
                              kpis: dict[str, Any] | None = None) -> str:
    """Apply canonical common KPI values to a report tab's HTML."""
    if not report_html:
        return report_html
    if kpis is None:
        if raw_dir is None:
            return report_html
        kpis = compute_common_kpis(Path(raw_dir))
    specs = [
        ("cache_hit_pct", ["Cache hit", "Cache Hit"], "Cache Hit"),
        ("ttft_ms", ["TTFT mean"], "TTFT mean"),
        ("ttft_p50_ms", ["TTFT p50"], "TTFT p50"),
        ("tpot_ms", ["TPOT / ITL mean", "TPOT mean", "ITL mean"], "TPOT / ITL mean"),
        ("tpot_p50_ms", ["TPOT / ITL p50", "TPOT p50", "ITL p50"], "TPOT / ITL p50"),
        ("e2e_ms", ["E2E mean"], "E2E mean"),
        ("e2e_p50_ms", ["E2E p50"], "E2E p50"),
        ("throughput_mean", ["Throughput mean"], "Throughput mean"),
        ("throughput_p50", ["Throughput p50"], "Throughput p50"),
        ("throughput_peak", ["Throughput peak", "Peak throughput", "Peak"], "Throughput peak"),
    ]
    out = report_html
    for key, labels, canonical in specs:
        v = _safe_float(kpis.get(key), 0.0)
        if v > 0:
            out = _replace_kpi_value_by_label(out, labels, key, v, kpis, canonical)
    out = _insert_missing_throughput_peak_tile(out, kpis)
    return out


def write_common_kpis_json(raw_dir: Path, kpis: dict[str, Any] | None = None) -> Path:
    raw_dir = Path(raw_dir)
    kpis = kpis or compute_common_kpis(raw_dir)
    out = raw_dir / "common_kpis.json"
    try:
        out.write_text(json.dumps(kpis, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
    return out
