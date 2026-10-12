"""Canonical metric kernels — one implementation per computation.

Companion to ``metric_formulas.py``: that module owns the *documentation* of
each metric, this one owns the *arithmetic*. A metric's formula string and
the code that evaluates it should never disagree, so both live in the shared
layer rather than in any single report.

Why this exists
---------------
Each report had grown its own delta/rate helpers — ``combined._ts_delta``,
``combined._rate_from_counter``, ``amoprof._delta``, ``amoprof._counter_delta``,
``interactive._rate`` (twice), ``common_kpis._delta`` — eight implementations
of two ideas. They diverged, and the divergence was not theoretical: the End
Report divided a *cumulative* prompt-token counter by the collection window
and reported ~3.9 M tok/s where the Executive reported ~95 tok/s and the
Bottleneck charts showed thousands.

Every report should call these instead of reimplementing them. New callers
should not add a private variant.

Vocabulary
----------
counter   cumulative, monotonically non-decreasing since process start
          (``sglang_prompt_tokens_total``). Only *deltas* are meaningful.
gauge     instantaneous value (``gpu_util``). Usable as-is.
window    the selected analysis interval — first to last retained sample.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

__all__ = [
    "counter_delta",
    "window_seconds",
    "window_rate",
    "rate_series_with_time",
    "rate_series",
    "aligned_rate_series",
    "ratio_delta",
    "align_on_time",
    "pearson",
    "resolve_gpu_hbm",
    "resolve_kv_bytes_per_token",
    "resolve_hbm_breakdown",
    "resolve_l2_residency",
    "kv_movement_bandwidth",
    "window_counter_delta",
    "window_counter_series",
    "RANK_LABELS",
    "RANK_REPLICA_TOL",
    "rank_combine_rule",
    "summarise_rank_rules",
    "token_reuse_density",
    "tail_ratio",
    "DRAM_SANE_MAX_GBS",
    "sanitize_bandwidth_samples",
    "sane_mean",
    "prefill_cache_hit_ratio",
    "percentiles_from_bucket_deltas",
    "resolve_latency_ms",
    "resolve_latency_percentile",
    "NVME_MAX_BW_MBS",
    "QD_PLAUSIBLE_MAX",
    "vet_device_bw_peak",
    "vet_queue_depth",
    "normalize_series_name",
    "resolve_series_columns",
    "counter_window_total",
    "latency_window_ms",
    "active_window_fraction",
    "bucket_edge_check",
    "admission_stalls",
]


def _finite(v) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _clean(values: Iterable) -> list[float]:
    return [float(v) for v in (values or []) if _finite(v)]


def counter_delta(values: Sequence[float]) -> float:
    """Work done across the window by a cumulative counter.

    ``last - first``, not ``last``. Clamped at zero so a counter reset (server
    restart mid-window) reports no work rather than a negative rate.

    This is the single most misused primitive in the codebase: ``values[-1]``
    is the lifetime total since the *server* started, which is unrelated to
    the collection window and can be orders of magnitude larger.
    """
    v = _clean(values)
    if len(v) < 2:
        return 0.0
    return max(0.0, v[-1] - v[0])


def window_seconds(times: Sequence[float]) -> float:
    """Elapsed seconds spanned by a timestamp column (last - first)."""
    t = _clean(times)
    if len(t) < 2:
        return 0.0
    return max(0.0, t[-1] - t[0])


def window_rate(values: Sequence[float], times: Sequence[float]) -> float:
    """Run-average rate of a cumulative counter: Δcounter ÷ Δtime.

    This is the *whole-window average* and therefore includes idle time — it
    is deliberately not the same number as the per-interval instantaneous
    rate from :func:`rate_series`. A mostly-idle window legitimately yields a
    low average alongside high instantaneous peaks; both are correct and the
    reports must label which one they show.

    Returns 0.0 when the window cannot be established, rather than falling
    back to a lifetime counter.
    """
    dt = window_seconds(times)
    if dt <= 0:
        return 0.0
    return counter_delta(values) / dt


def rate_series_with_time(values: Sequence[float],
                          times: Sequence[float]) -> tuple[list[float], list[float]]:
    """Per-interval instantaneous rate, with the timestamp of each sample.

    Samples where Δt ≤ 0 (duplicate scrape timestamps) are skipped along with
    their timestamp, so the returned lists stay index-aligned with each other
    — the reason this returns times rather than assuming ``len(rate) ==
    len(values) - 1``. Negative deltas are clamped to zero for counter resets.
    """
    v = _clean(values)
    t = _clean(times)
    n = min(len(v), len(t))
    out_t: list[float] = []
    out_r: list[float] = []
    for i in range(1, n):
        dt = t[i] - t[i - 1]
        if dt <= 0:
            continue
        out_t.append(t[i])
        out_r.append(max(0.0, (v[i] - v[i - 1]) / dt))
    return out_t, out_r


def rate_series(values: Sequence[float], times: Sequence[float]) -> list[float]:
    """Per-interval instantaneous rate (values only)."""
    return rate_series_with_time(values, times)[1]


def aligned_rate_series(values: Sequence[float], times: Sequence[float],
                        clamp_negative: bool = True) -> list[float]:
    """Per-interval rate that stays index-aligned with `times`.

    Differs from :func:`rate_series`, which drops samples: this prepends 0.0
    for the first sample and emits 0.0 where Δt <= 0, so ``len(result) ==
    len(values)``. Chart code needs that because the rate is plotted against
    the original time axis — dropping a sample would shift every point.

    ``clamp_negative=True`` floors at zero for cumulative counters; pass False
    for signed deltas where a decrease is meaningful.
    """
    v = _clean(values)
    t = _clean(times)
    n = min(len(v), len(t))
    if n < 2:
        return [0.0] * len(v)
    out = [0.0]
    for i in range(1, n):
        dt = t[i] - t[i - 1]
        if dt <= 0:
            out.append(0.0)
            continue
        r = (v[i] - v[i - 1]) / dt
        out.append(max(r, 0.0) if clamp_negative else r)
    return out


def ratio_delta(sum_values: Sequence[float], count_values: Sequence[float],
                scale: float = 1.0) -> float:
    """Mean of a Prometheus histogram over the window: Δsum ÷ Δcount.

    The canonical estimator for TTFT / TPOT / E2E means. ``scale`` converts
    units (1000.0 for seconds → milliseconds). Returns 0.0 when no
    observations completed in the window.
    """
    d_count = counter_delta(count_values)
    if d_count <= 0:
        return 0.0
    return counter_delta(sum_values) / d_count * scale


def align_on_time(x_t: Sequence[float], x_v: Sequence[float],
                  y_t: Sequence[float], y_v: Sequence[float],
                  tolerance: float = 0.0) -> tuple[list[float], list[float]]:
    """Pair two series on wall-clock time rather than on list position.

    Series from different collectors have different cadences and start
    offsets — local collectors default to ``--interval-s 1.0`` while
    Prometheus-sourced CSVs use a 15 s step, and AMDuProf PCM stays local
    even in Prometheus mode. Index pairing correlates unrelated moments.

    Each X sample is matched to the nearest Y sample within ``tolerance``
    (default: half the coarser median sampling step). Unmatched X samples are
    dropped.
    """
    xv, yv = _clean(x_v), _clean(y_v)
    xt, yt = _clean(x_t), _clean(y_t)
    if not xv or not yv or len(xt) != len(xv) or len(yt) != len(yv):
        return [], []

    def _median_step(ts: list[float]) -> float:
        d = sorted(ts[i] - ts[i - 1] for i in range(1, len(ts)) if ts[i] > ts[i - 1])
        return d[len(d) // 2] if d else 0.0

    tol = tolerance or (max(_median_step(xt), _median_step(yt)) / 2.0)
    if tol <= 0:
        return [], []

    out_x: list[float] = []
    out_y: list[float] = []
    j, ny = 0, len(yt)
    for i, tx in enumerate(xt):
        while j + 1 < ny and abs(yt[j + 1] - tx) <= abs(yt[j] - tx):
            j += 1
        if abs(yt[j] - tx) <= tol:
            out_x.append(xv[i])
            out_y.append(yv[j])
    return out_x, out_y


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Pearson correlation coefficient; 0.0 when undefined."""
    x, y = _clean(xs), _clean(ys)
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[:n], y[:n]
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    if dx <= 0 or dy <= 0:
        return 0.0
    return num / (dx * dy)


def lagged_pearson(xs: Sequence[float], ys: Sequence[float],
                   max_lag: int = 6) -> "tuple[float, int]":
    """Strongest correlation over shifts of `ys` against `xs`, and its lag.

    Returns (r, lag).  A POSITIVE lag means ys had to be shifted LATER to
    line up -- that is, ys responds to xs after `lag` sampling intervals.

    Needed because a zero-lag r understates a real pipeline.  Prefetch that
    completes asynchronously shows up in the load-back counter one or more
    intervals later, and correlating only at lag 0 reports "no relationship"
    for a pipeline that is working perfectly well, just not instantaneously.

    Ties go to the SMALLEST |lag|, so a relationship that is equally strong
    at 0 and 3 is reported as immediate rather than delayed.
    """
    x, y = _clean(xs), _clean(ys)
    n = min(len(x), len(y))
    if n < 4:
        return 0.0, 0
    x, y = x[:n], y[:n]
    _best_r, _best_l = 0.0, 0
    _lim = max(0, min(int(max_lag), n // 3))
    for _l in range(-_lim, _lim + 1):
        if _l >= 0:
            _a, _b = x[:n - _l], y[_l:]
        else:
            _a, _b = x[-_l:], y[:n + _l]
        if len(_a) < 4:
            continue
        _r = pearson(_a, _b)
        if abs(_r) > abs(_best_r) + 1e-12 or (
                abs(abs(_r) - abs(_best_r)) <= 1e-12 and abs(_l) < abs(_best_l)):
            _best_r, _best_l = _r, _l
    return _best_r, _best_l


def partial_pearson(xs: Sequence[float], ys: Sequence[float],
                    zs: Sequence[float]) -> float:
    """Correlation of xs and ys with the influence of zs removed.

    r_xy.z = (r_xy - r_xz * r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2))

    The reason this matters here: nearly every rate in an inference stack
    rises and falls with how busy the engine is.  Two counters can correlate
    strongly while neither drives the other, because request arrival drives
    both.  Holding the workload constant is what separates "these move
    together" from "this one feeds that one".  Returns 0.0 when undefined.
    """
    _rxy = pearson(xs, ys)
    _rxz = pearson(xs, zs)
    _ryz = pearson(ys, zs)
    _den = (1.0 - _rxz * _rxz) * (1.0 - _ryz * _ryz)
    if _den <= 1e-12:
        return 0.0
    _r = (_rxy - _rxz * _ryz) / math.sqrt(_den)
    # Floating-point drift can push a near-perfect result just outside the
    # valid range; a correlation outside [-1, 1] is meaningless, not just ugly.
    return max(-1.0, min(1.0, _r))


# ---------------------------------------------------------------------------
# GPU / HBM capacity resolution
# ---------------------------------------------------------------------------

def _pick_num(d: "dict | None", keys: Sequence[str], default: float = 0.0) -> float:
    """First finite, non-zero numeric value among `keys` (case/format tolerant)."""
    if not d:
        return default
    norm = {str(k).strip().lower().replace(" ", "_"): v for k, v in d.items()}
    for k in keys:
        for cand in (k, str(k).strip().lower().replace(" ", "_")):
            if cand in norm:
                try:
                    v = float(str(norm[cand]).replace(",", ""))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(v) and v != 0:
                    return v
    return default


def resolve_gpu_hbm(gpu_summary: "dict | None" = None,
                    setup: "dict | None" = None,
                    gpu_config: "dict | None" = None) -> dict:
    """Canonical GPU count and HBM used/total, shared by every report.

    Executive and Interactive previously each resolved this from their own key
    lists, and diverged: Interactive read only ``hbm_used_mb_mean`` and fell
    back to a hardcoded **40 GB** per-GPU capacity, which is wrong by 4.5x on a
    179 GB B200. Both now call this.

    Precedence, most authoritative first:

    * per-GPU capacity — ``gpu_config.json`` (nvidia-smi ``memory.total``),
      then setup metadata, then the GPU summary. No hardcoded default: an
      unresolvable capacity returns 0 so callers can say "unknown" rather than
      publish a wrong denominator.
    * GPU count — TP x DP (the devices actually serving), then
      ``gpu_config.gpus_in_use``, then physical count.

    Returns per-GPU and all-GPU used/total in GB plus the resolved count and
    the source of each, so tiles can state provenance.
    """
    per_gpu_used = _pick_num(gpu_summary, [
        "hbm_used_gb_mean", "mem_used_gb_mean", "hbm_gb"])
    used_src = "gpu_summary hbm_used_gb_mean"
    if per_gpu_used <= 0:
        mb = _pick_num(gpu_summary, ["hbm_used_mb_mean", "mem_used_mean_mb", "hbm_used_mb"])
        if mb > 0:
            per_gpu_used, used_src = mb / 1024.0, "gpu_summary hbm_used_mb_mean / 1024"

    per_gpu_total = _pick_num(gpu_config, ["hbm_per_gpu_gb"])
    total_src = "gpu_config.json hbm_per_gpu_gb (nvidia-smi memory.total)"
    if per_gpu_total <= 0:
        per_gpu_total = _pick_num(setup, [
            "gpu_memory_per_device_gb", "hbm_per_gpu_gb", "gpu_memory_gb"])
        total_src = "setup_details GPU memory per device"
    if per_gpu_total <= 0:
        per_gpu_total = _pick_num(gpu_summary, ["hbm_total_gb"])
        total_src = "gpu_summary hbm_total_gb"
    if per_gpu_total <= 0:
        mb = _pick_num(gpu_summary, ["hbm_total_mb", "mem_total_mean_mb"])
        if mb > 0:
            per_gpu_total, total_src = mb / 1024.0, "gpu_summary hbm_total_mb / 1024"
    if per_gpu_total <= 0:
        total_src = "unresolved"          # deliberately no hardcoded fallback

    tp = _pick_num(setup, ["tp_size", "tp", "tensor_parallel_size"])
    if tp <= 0:
        tp = _pick_num(gpu_config, ["tp_size"])
    dp = _pick_num(setup, ["dp_size", "dp", "data_parallel_size"], 1.0) or 1.0
    if dp <= 0:
        dp = _pick_num(gpu_config, ["dp_size"], 1.0) or 1.0
    if tp > 0:
        count, count_src = max(tp * dp, 1.0), f"TP({tp:g}) x DP({dp:g})"
    else:
        count = _pick_num(gpu_config, ["gpus_in_use"])
        count_src = "gpu_config gpus_in_use"
        if count <= 0:
            count = _pick_num(gpu_config, ["gpu_count"]) or _pick_num(
                setup, ["gpu_count", "num_gpus"]) or _pick_num(
                gpu_summary, ["gpu_count"], 1.0) or 1.0
            count_src = "physical GPU count"

    return {
        "gpu_count": count,
        "gpu_count_source": count_src,
        "per_gpu_used_gb": per_gpu_used,
        "per_gpu_total_gb": per_gpu_total,
        "used_gb": per_gpu_used * count,
        "total_gb": per_gpu_total * count,
        "util_pct": (per_gpu_used / per_gpu_total * 100.0) if per_gpu_total > 0 else 0.0,
        "used_source": used_src,
        "total_source": total_src,
    }


# ---------------------------------------------------------------------------
# KV cache bytes per token
# ---------------------------------------------------------------------------

# name fragment -> (n_layers, n_kv_heads, head_dim, attention type)
_KV_ARCH_DB: "dict[str, tuple]" = {
    "gpt-oss-120b": (36, 8, 64, "GQA"),
    "gpt-oss-20b": (24, 8, 64, "GQA"),
    "deepseek-r1-distill-llama-70b": (80, 8, 128, "GQA"),
    "deepseek-r1-distill-qwen-32b": (64, 8, 128, "GQA"),
    "deepseek-r1-distill-qwen-14b": (48, 8, 128, "GQA"),
    "deepseek-v3": (61, 128, 512, "MLA"),
    "qwen3-235b": (94, 4, 512, "MLA"),
    "llama-3.1-405b": (126, 8, 128, "GQA"),
    "llama-3.1-70b": (80, 8, 128, "GQA"),
    "llama-3-70b": (80, 8, 128, "GQA"),
    "gemma-2-27b": (46, 4, 256, "GQA"),
    "gemma-2-9b": (42, 4, 256, "GQA"),
    "gemma-2-2b": (26, 4, 256, "GQA"),
}

# Size hints are matched on a *token boundary*, not as a bare substring.
# Substring matching is why a 31B model silently resolved to the 1B entry:
# "31b" contains "1b".  The pattern requires a non-digit (or string start)
# immediately before the size, so "31b" can never match "1b".
_SIZE_HINTS: "list[tuple[str, tuple]]" = [
    ("671b", (61, 128, 512, "MLA")), ("405b", (126, 8, 128, "GQA")),
    ("235b", (94, 4, 512, "MLA")), ("180b", (60, 8, 128, "GQA")),
    ("120b", (36, 8, 64, "GQA")), ("72b", (80, 8, 128, "GQA")),
    ("70b", (80, 8, 128, "GQA")), ("47b", (32, 8, 128, "GQA")),
    ("34b", (48, 8, 128, "GQA")), ("32b", (64, 8, 128, "GQA")),
    ("31b", (64, 8, 128, "GQA")),
    ("30b", (64, 8, 128, "GQA")), ("27b", (46, 4, 256, "GQA")),
    ("22b", (56, 8, 128, "GQA")), ("20b", (24, 8, 64, "GQA")),
    ("14b", (48, 8, 128, "GQA")), ("13b", (40, 8, 128, "GQA")),
    ("9b", (42, 4, 256, "GQA")), ("8b", (32, 8, 128, "GQA")),
    ("7b", (28, 4, 128, "GQA")), ("4b", (36, 8, 128, "GQA")),
    ("3b", (32, 8, 128, "GQA")), ("2b", (26, 4, 256, "GQA")),
    ("1b", (22, 8, 128, "GQA")),
]


def _dtype_bytes(kv_dtype: str) -> int:
    d = str(kv_dtype or "").lower()
    if d.startswith(("fp8", "e4m3", "e5m2", "int8", "uint8")):
        return 1
    if d.startswith(("int4", "fp4", "nf4")):
        return 1     # sub-byte packing is not modelled; treat as 1 and flag
    return 2


def _swa_layout(config: dict, model_name: str, n_layers: int) -> dict:
    """Detect sliding-window-attention layout from a model config.

    Returns {is_swa, window, n_global, n_swa, source}.  Sources tried:
      1. `sliding_window` in config AND explicit `layer_types` array
         (Gemma-3+, some SGLang deploys). Per-layer authoritative.
      2. `sliding_window_pattern` / `attention_pattern` integer
         (Gemma-2: every N-th layer is FULL attention, rest are SWA).
      3. Model-family default (Gemma-2/3/4: 6:1 SWA:full, i.e. 5/6 SWA;
         Mistral-7B-SWA: 100% SWA; others: no assumption).
    When `sliding_window` is absent or 0, returns is_swa=False.
    """
    if n_layers <= 0:
        return {"is_swa": False, "window": 0, "n_global": 0,
                "n_swa": 0, "source": ""}
    window = 0
    for _k in ("sliding_window", "sliding_window_size"):
        _v = config.get(_k)
        if _v:
            try:
                window = int(_v)
                if window > 0:
                    break
            except (TypeError, ValueError):
                pass
    if window <= 0:
        return {"is_swa": False, "window": 0, "n_global": n_layers,
                "n_swa": 0, "source": "no sliding_window in config"}

    layer_types = (config.get("layer_types")
                   or config.get("attn_layer_types")
                   or config.get("interleaved_attn_pattern"))
    if isinstance(layer_types, list) and len(layer_types) == n_layers:
        n_swa = sum(1 for _t in layer_types
                    if "sliding" in str(_t).lower())
        return {"is_swa": n_swa > 0, "window": window,
                "n_global": n_layers - n_swa, "n_swa": n_swa,
                "source": "config.layer_types (per-layer)"}

    pat = 0
    for _k in ("sliding_window_pattern", "attention_pattern"):
        _v = config.get(_k)
        if _v:
            try:
                pat = int(_v)
                if pat > 1:
                    break
            except (TypeError, ValueError):
                pass
    if pat > 1:
        n_full = n_layers // pat
        return {"is_swa": True, "window": window,
                "n_global": n_full, "n_swa": n_layers - n_full,
                "source": f"config.sliding_window_pattern={pat}"}

    mt = str(config.get("model_type") or "").lower()
    mn = str(model_name or "").lower()
    if "gemma" in mt or "gemma" in mn:
        n_full = n_layers // 6
        return {"is_swa": True, "window": window,
                "n_global": n_full, "n_swa": n_layers - n_full,
                "source": "Gemma-family default (1:6 full:SWA)"}
    if "mistral" in mt or "mistral" in mn:
        return {"is_swa": True, "window": window,
                "n_global": 0, "n_swa": n_layers,
                "source": "Mistral-family default (all-SWA)"}

    # sliding_window is set but no layer-type info and not a known family:
    # treat as full-attention with a note that SWA MAY apply.
    return {"is_swa": False, "window": window, "n_global": n_layers,
            "n_swa": 0,
            "source": "sliding_window set but no layer-type info; "
                      "treating as full attention"}


_LATENCY_KINDS = {
    "ttft": ("time_to_first_token_seconds", "TTFT"),
    "tpot": ("inter_token_latency_seconds", "TPOT / ITL"),
    "e2e":  ("e2e_request_latency_seconds", "end-to-end latency"),
}


def resolve_latency_ms(kind: str, ts_ms: float = 0.0, pct_ms: float = 0.0,
                       summary_ms: float = 0.0,
                       summary_method: str = "") -> dict:
    """One latency figure, by one resolution order, for every report surface.

    The order and its reason were written down once, in the Combined report:

        1) selected-window Δsum/Δcount counters
        2) selected-window percentile-timeseries p50 active mean
        3) sglang_summary.json only as last fallback
        # This avoids different runs reusing the same stale summary TTFT/TPOT.

    The comparison report did step 3 only -- it read server_ttft_ms straight
    out of the summary -- so the two surfaces could report different latencies
    for the same window, and on one reference run they did: 11,514 ms from
    Combined against 11,525 ms from compare.

    0.1% there, but the gap is not bounded at 0.1%. The fetch that writes the
    summary falls back to last(sum)/last(count) when the window delta is zero,
    which is the LIFETIME mean since the server started, and it labels the
    result "delta_..._sum_over_count" either way because that method string is
    a literal in the dict. So a summary figure can be a lifetime average
    wearing a window label, and a surface that trusts the summary inherits it
    while one that recomputes does not.

    ``window_scoped`` is the field that matters to a caller: False means the
    number describes the server's whole life, not the window asked for, and
    no delta between two such figures is a comparison of two windows.

    ``statistic`` is the one that matters next: steps 1 and 3 are MEANS, step
    2 is a MEDIAN. The order mixes the two, so the figure's own identity has
    to travel with it -- a tile headed "TTFT mean" that fell through to step 2
    is showing a p50, and on these runs the mean and the p50 differ by two
    orders of magnitude (79,341 ms against 598 ms on one 30-minute window).
    A caller that prints this figure under a fixed label is wrong half the
    time; one that prints ``statistic`` beside it never is.

    Returns {ms, method, window_scoped, step, statistic}.
    """
    k = str(kind or "").strip().lower()
    base = _LATENCY_KINDS.get(k, (k, k))[0]
    if ts_ms and ts_ms > 0:
        return {"ms": float(ts_ms), "step": 1, "window_scoped": True,
                "statistic": "mean",
                "method": f"Δ{base}_sum ÷ Δ{base}_count over the window"}
    if pct_ms and pct_ms > 0:
        return {"ms": float(pct_ms), "step": 2, "window_scoped": True,
                "statistic": "p50",
                "method": f"{base} p50, mean over active intervals in the window"}
    if summary_ms and summary_ms > 0:
        # The summary's own claimed method is carried through, but it is not
        # evidence of window scoping: see above.
        _lifetime = "last" in str(summary_method).lower() or not summary_method
        return {"ms": float(summary_ms), "step": 3, "window_scoped": False,
                "statistic": "mean",
                "method": ("sglang_summary.json"
                           + (f" ({summary_method})" if summary_method else "")
                           + " — NOT verified as window-scoped")}
    return {"ms": 0.0, "step": 0, "window_scoped": False, "statistic": "",
            "method": f"{base} unavailable"}


def resolve_kv_bytes_per_token(model_name: str = "", kv_dtype: str = "",
                               config: "dict | None" = None,
                               observed_avg_seq_len: float = 0.0) -> dict:
    """KV bytes per token, with the architecture and provenance that produced it.

    One implementation for every report surface.  Executive and the End Report
    previously each carried their own architecture table with a "keep in sync"
    comment; they drifted, and on a `gemma-4-31B-it` run reported 320 KB/token
    and 88 KB/token respectively for the same model — the End Report having
    matched the "1b" size hint inside "31b", and the Executive having fallen
    through to a 70B-class default.

    Resolution order, most authoritative first:

    1. **Explicit config** — `num_hidden_layers`, `num_key_value_heads`,
       `head_dim` (or `hidden_size / num_attention_heads`) from the engine's
       own model config.  Exact.
    2. **Named architecture** in the table above.  Exact for those models.
    3. **Size hint** from the model name, matched on a token boundary.  An
       estimate: it assumes a typical layout for that parameter count.
    4. **Unknown.**  Returns ``kb = 0`` with ``source = "unknown"`` so callers
       can say so rather than publish a default dressed as a measurement.

    Returns {kb, bytes, n_layers, n_kv_heads, head_dim, attention, dtype_bytes,
    source, exact, formula}.
    """
    cfg = {str(k).strip().lower(): v for k, v in (config or {}).items()}

    def _cfg_int(*names) -> int:
        for n in names:
            if n in cfg:
                try:
                    v = int(float(str(cfg[n]).replace(",", "")))
                    if v > 0:
                        return v
                except (TypeError, ValueError):
                    continue
        return 0

    if not kv_dtype:
        kv_dtype = str(cfg.get("kv_cache_dtype") or cfg.get("dtype") or "") or "fp16"
    dbytes = _dtype_bytes(kv_dtype)

    n_layers = _cfg_int("num_hidden_layers", "n_layers", "num_layers")
    n_kv = _cfg_int("num_key_value_heads", "n_kv_heads", "num_kv_heads")
    hdim = _cfg_int("head_dim", "kv_head_dim", "v_head_dim")
    if not hdim:
        hidden = _cfg_int("hidden_size", "d_model")
        n_heads = _cfg_int("num_attention_heads", "n_heads")
        if hidden and n_heads:
            hdim = hidden // n_heads
    attention = str(cfg.get("attention_type") or "GQA").upper()
    source, exact = "", False

    if n_layers and n_kv and hdim:
        source, exact = "model config (exact)", True
    else:
        ml = str(model_name or "").lower()
        arch = None
        for key, val in _KV_ARCH_DB.items():
            if key in ml:
                arch, source, exact = val, f"architecture table: {key}", True
                break
        if arch is None:
            for hint, val in _SIZE_HINTS:
                # Token-boundary match: the character before the size must not
                # be a digit, so "31b" cannot match "1b".
                if re.search(r"(?<!\d)" + re.escape(hint), ml):
                    arch = val
                    source = f"size hint '{hint}' (ESTIMATE — assumed layout)"
                    exact = False
                    break
        if arch is None:
            return {"kb": 0.0, "bytes": 0, "n_layers": 0, "n_kv_heads": 0,
                    "head_dim": 0, "attention": "", "dtype_bytes": dbytes,
                    "source": "unknown — model not recognised and no config supplied",
                    "exact": False, "formula": ""}
        n_layers, n_kv, hdim, attention = arch

    if attention == "MLA":
        naive_total = n_layers * hdim * 2 * dbytes          # 2 = K + V latent
        naive_formula = (f"n_layers x latent_dim x 2 x dtype_bytes = "
                         f"{n_layers} x {hdim} x 2 x {dbytes}")
        per_layer_bytes = hdim * 2 * dbytes
    else:
        naive_total = 2 * n_layers * n_kv * hdim * dbytes
        naive_formula = (f"2 x n_layers x n_kv_heads x head_dim x dtype_bytes "
                         f"= 2 x {n_layers} x {n_kv} x {hdim} x {dbytes}")
        per_layer_bytes = 2 * n_kv * hdim * dbytes

    # SWA-aware effective bytes/token.  MLA does not use SWA in current
    # deployments, so only the GQA branch benefits; leave MLA as-is.
    swa = _swa_layout(cfg, model_name, n_layers) if attention != "MLA" else \
          {"is_swa": False, "window": 0, "n_global": n_layers,
           "n_swa": 0, "source": "MLA (no SWA)"}
    if swa["is_swa"] and per_layer_bytes > 0:
        window = int(swa["window"])
        n_global = int(swa["n_global"])
        n_swa = int(swa["n_swa"])
        # Prefer observed seq_len when the caller can supply it; otherwise
        # use 2 x window as a pragmatic mid-point.  For very small
        # seq_len (< window) SWA density collapses to 1.0 (no reduction),
        # which is the correct behaviour: short sequences fit entirely
        # in the window and every SWA layer stores every token.
        seq_len = float(observed_avg_seq_len) if observed_avg_seq_len > 0 \
                  else (2.0 * window if window > 0 else 8192.0)
        swa_density = min(1.0, window / seq_len) if seq_len > 0 else 1.0
        total = int((n_global + n_swa * swa_density) * per_layer_bytes)
        formula = (f"{naive_formula}  [naive {naive_total:,} B]\n"
                   f"    x SWA-adj: ({n_global} full + {n_swa} SWA "
                   f"@ min(1, {window}/{seq_len:.0f})={swa_density:.2f}) "
                   f"/ {n_layers} = {total:,} B "
                   f"({total/1024.0:.1f} KB/token, "
                   f"{100.0*total/naive_total:.0f}% of naive)")
    else:
        total = naive_total
        formula = (f"{naive_formula} = {total:,} bytes = "
                   f"{total/1024.0:.1f} KB/token")

    return {"kb": total / 1024.0, "bytes": total,
            "naive_kb": naive_total / 1024.0, "naive_bytes": naive_total,
            "n_layers": n_layers, "n_kv_heads": n_kv, "head_dim": hdim,
            "attention": attention, "dtype_bytes": dbytes,
            "source": source, "exact": exact,
            "swa": swa, "seq_len_hint": (
                float(observed_avg_seq_len) if observed_avg_seq_len > 0
                else (2.0 * swa["window"] if swa["is_swa"] and swa["window"] > 0
                      else 0.0)),
            "formula": formula}


# ---------------------------------------------------------------------------
# HBM composition: weights vs KV cache vs everything else
# ---------------------------------------------------------------------------

def resolve_hbm_breakdown(hbm: "dict | None" = None,
                          kv: "dict | None" = None,
                          max_total_tokens: float = 0.0,
                          token_usage: float = 0.0,
                          used_tokens: float = 0.0,
                          params_b: float = 0.0,
                          weight_dtype_bytes: int = 2,
                          tp_size: float = 1.0) -> dict:
    """Split measured HBM occupancy into weights, KV pool, and remainder.

    Inputs are the outputs of :func:`resolve_gpu_hbm` and
    :func:`resolve_kv_bytes_per_token` plus SGLang's pool metrics, so this
    cannot disagree with the HBM and KV figures reported elsewhere.

    Three quantities are genuinely distinct and are kept apart:

    * **KV pool reserved** — `max_total_num_tokens x kv_bytes_per_token`.
      SGLang allocates this up front from `mem-fraction-static`, so it is
      resident whether or not any tokens occupy it. This is what shows up in
      `nvidia-smi`.
    * **KV active** — the occupied part of that pool, from `token_usage` (a
      0..1 fraction) or `kv_used_tokens`. This is the number that varies with
      load; the reserved figure does not.
    * **Weights** — `params x dtype_bytes / TP` when the parameter count is
      known. Otherwise reported as part of the residual rather than guessed.

    The KV pool is sharded across tensor-parallel ranks, so per-GPU figures
    divide by TP.

    Anything left over (`used - weights - KV resident`, where KV resident is
    the pool when known, else KV active) is activations, CUDA context,
    allocator fragmentation and cuBLAS workspace. It is labelled as a
    residual, not as a measured category — attributing it would be invention.

    Returns per-GPU GB for each component plus `exact` flags and notes.
    """
    hbm = hbm or {}
    kv = kv or {}
    tp = max(1.0, float(tp_size or 1.0))
    kv_kb = float(kv.get("kb") or 0.0)

    per_gpu_total = float(hbm.get("per_gpu_total_gb") or 0.0)
    per_gpu_used = float(hbm.get("per_gpu_used_gb") or 0.0)

    # KV pool reserved (per GPU).
    kv_pool_gb = 0.0
    if max_total_tokens > 0 and kv_kb > 0:
        kv_pool_gb = float(max_total_tokens) * kv_kb / 1024.0 / 1024.0 / tp

    # KV actually occupied (per GPU).
    kv_active_gb = 0.0
    kv_active_src = ""
    if used_tokens > 0 and kv_kb > 0:
        kv_active_gb = float(used_tokens) * kv_kb / 1024.0 / 1024.0 / tp
        kv_active_src = "kv_used_tokens x KV bytes/token / TP"
    elif token_usage > 0 and kv_pool_gb > 0:
        frac = float(token_usage)
        if frac > 1.0:                      # exporter already in percent
            frac /= 100.0
        kv_active_gb = kv_pool_gb * max(0.0, min(1.0, frac))
        kv_active_src = "sglang_token_usage x KV pool"
    kv_active_gb = min(kv_active_gb, kv_pool_gb) if kv_pool_gb > 0 else kv_active_gb

    # Model weights (per GPU).
    weights_gb = 0.0
    weights_src = ""
    if params_b > 0:
        weights_gb = float(params_b) * 1e9 * int(weight_dtype_bytes or 2) / 1e9 / tp
        weights_src = (f"{params_b:g}B params x {weight_dtype_bytes} B / TP {tp:g}")

    # A component larger than the card it sits on is not a measurement, it is
    # a bad input (wrong param count, wrong TP, wrong KV bytes/token).  Drop it
    # to the residual rather than drawing a segment that exceeds the device.
    if per_gpu_total > 0 and weights_gb > per_gpu_total:
        weights_src = (f"IMPLAUSIBLE ({weights_gb:.0f} GB > {per_gpu_total:.0f} GB "
                       f"per GPU) — discarded")
        weights_gb = 0.0
    if per_gpu_total > 0 and kv_pool_gb > per_gpu_total:
        kv_pool_gb = 0.0
        kv_active_gb = 0.0
    if per_gpu_total > 0 and kv_active_gb > per_gpu_total:
        kv_active_gb = 0.0

    # KV resident in HBM: the reserved pool when its size is known (the
    # occupied part sits inside it), otherwise just the occupied part.
    # Subtracting only the pool left KV-in-use inside the residual whenever
    # max_total_num_tokens was not exported (pool = 0), so the chart drew the
    # same KV twice: 31.0 + 35.0 + 50.6 + 97.5 = 214.1 GB on a 179 GB card.
    # Bands now always sum to used + unallocated = device.
    kv_resident_gb = kv_pool_gb if kv_pool_gb > 0 else kv_active_gb
    residual_gb = max(0.0, per_gpu_used - weights_gb - kv_resident_gb)
    free_gb = max(0.0, per_gpu_total - per_gpu_used)
    over = (weights_gb + kv_resident_gb) > per_gpu_used > 0

    return {
        "per_gpu_total_gb": per_gpu_total,
        "per_gpu_used_gb": per_gpu_used,
        "weights_gb": weights_gb,
        "weights_source": weights_src or "unknown — folded into residual",
        "kv_pool_gb": kv_pool_gb,
        "kv_active_gb": kv_active_gb,
        "kv_free_gb": max(0.0, kv_pool_gb - kv_active_gb),
        "kv_active_source": kv_active_src or "unavailable",
        "residual_gb": residual_gb,
        "free_gb": free_gb,
        "kv_bytes_per_token_kb": kv_kb,
        "tp_size": tp,
        "consistent": not over,
        "note": ("weights + KV exceed measured HBM used — check KV "
                 "bytes/token and TP" if over else ""),
    }


# ---------------------------------------------------------------------------
# L2 (host DRAM / HiCache) residency
# ---------------------------------------------------------------------------

def resolve_l2_residency(hicache_used_tokens: float = 0.0,
                         hicache_total_tokens: float = 0.0,
                         kv_bytes_per_token_kb: float = 0.0,
                         hicache_total_gb: float = 0.0,
                         hicache_ratio: float = 0.0,
                         kv_pool_tokens: float = 0.0,
                         host_dram_total_gb: float = 0.0) -> dict:
    """Canonical L2 used / capacity, shared by every report surface.

    Executive and Interactive each derived this independently and disagreed on
    real runs (4.0 vs 5.6 GB used; 512 vs 128 GB capacity), which is the same
    failure `resolve_gpu_hbm` was introduced to stop.

    Capacity precedence:

    1. An explicit HiCache allocation (``--hicache-size`` x GPUs).
    2. ``--hicache-ratio x max_total_num_tokens x KV bytes/token`` — SGLang
       sizes the host cache this way whenever ``--hicache-size`` is 0, which
       is the default.  Without it the configured capacity reads 0 and every
       derived L2 figure is clamped away.
    3. Host DRAM total, as a last resort and labelled as such: it is the
       machine's memory, not an allocation this server made.

    Used comes from ``sglang_hicache_host_used_tokens`` x KV bytes/token — a
    measurement, independent of any DRAM PMU.
    """
    used_gb, used_src = 0.0, "unavailable"
    if hicache_used_tokens > 0 and kv_bytes_per_token_kb > 0:
        used_gb = hicache_used_tokens * kv_bytes_per_token_kb / 1024.0 / 1024.0
        used_src = "sglang_hicache_host_used_tokens x KV bytes/token"

    cap_gb, cap_src = 0.0, "unknown"
    cap_conflict = ""
    # A MEASURED gauge outranks a configured figure.
    #
    # sglang_hicache_host_total_tokens is the allocation the server actually
    # made; "2 GB/GPU x 8 GPUs" from setup_details is an input assumption,
    # and the two can disagree by the TP factor or more. Ranking the
    # assumption first produced a 16 GB capacity against a 251,421-token
    # gauge worth 134.3 GB, and the used figure was then divided by TP=8
    # elsewhere to make it fit -- so the tile read "16.6 GB / 16 GB, 103%
    # full" while the tier-residency chart, reading the same gauge directly,
    # read 134.3 GB. The 103% was the tell: an occupancy cannot exceed the
    # allocation it sits in, so the denominator was wrong.
    _gauge_gb = (hicache_total_tokens * kv_bytes_per_token_kb / 1024.0 / 1024.0
                 if (hicache_total_tokens > 0 and kv_bytes_per_token_kb > 0)
                 else 0.0)
    if _gauge_gb > 0:
        cap_gb = _gauge_gb
        cap_src = "sglang_hicache_host_total_tokens x KV bytes/token (measured)"
        if hicache_total_gb > 0:
            _r = (max(_gauge_gb, hicache_total_gb)
                  / max(min(_gauge_gb, hicache_total_gb), 1e-9))
            if _r > 1.2:
                cap_conflict = (
                    f"configured allocation says {hicache_total_gb:,.1f} GB but "
                    f"the server's own hicache_host_total_tokens gauge is worth "
                    f"{_gauge_gb:,.1f} GB ({_r:.1f}x apart); using the gauge")
    elif hicache_ratio > 0 and kv_pool_tokens > 0 and kv_bytes_per_token_kb > 0:
        # --hicache-ratio x device KV pool outranks a parsed --hicache-size.
        #
        # SGLang sizes the host cache from the ratio whenever --hicache-size
        # is 0, which is the default, so the ratio is what actually happened
        # on most runs. On the reference run the ratio path reproduces the
        # server's own gauge to one token (209,517 x 1.2 = 251,420 against a
        # measured 251,421), while a `hicache_size` field worth 2 -- read
        # from setup and multiplied by 8 GPUs -- gave 16 GB, a factor of 8.4
        # out. A stated ratio beats a stated size because only one of them
        # agrees with the device.
        cap_gb = kv_pool_tokens * hicache_ratio * kv_bytes_per_token_kb / 1024.0 / 1024.0
        cap_src = (f"--hicache-ratio {hicache_ratio:g} x max_total_num_tokens "
                   f"{kv_pool_tokens:,.0f} x KV {kv_bytes_per_token_kb:.0f} KB/token")
        if hicache_total_gb > 0:
            _r2 = max(cap_gb, hicache_total_gb) / max(min(cap_gb, hicache_total_gb), 1e-9)
            if _r2 > 1.2:
                cap_conflict = (
                    f"a configured HiCache size implies {hicache_total_gb:,.1f} GB "
                    f"but --hicache-ratio {hicache_ratio:g} on a "
                    f"{kv_pool_tokens:,.0f}-token KV pool implies {cap_gb:,.1f} GB "
                    f"({_r2:.1f}x apart); using the ratio, which is how SGLang "
                    f"sizes the host cache when --hicache-size is 0")
    elif hicache_total_gb > 0:
        cap_gb, cap_src = float(hicache_total_gb), "configured HiCache allocation"
    elif host_dram_total_gb > 0:
        cap_gb, cap_src = float(host_dram_total_gb), "host DRAM total (not an allocation)"

    # Occupancy can never exceed the allocation it sits in. Clamping hides
    # the disagreement, so record what was clamped and by how much: a used
    # figure above capacity means one of the two is derived from the wrong
    # bytes/token or the wrong allocation, and that is worth seeing.
    over_pct = 0.0
    if cap_gb > 0 and used_gb > cap_gb:
        over_pct = (used_gb / cap_gb - 1.0) * 100.0
        used_src += f" (clamped to capacity from {used_gb:.1f} GB)"
        used_gb = cap_gb

    return {
        "used_gb": used_gb,
        "capacity_gb": cap_gb,
        "fill_pct": (used_gb / cap_gb * 100.0) if cap_gb > 0 else 0.0,
        "used_source": used_src,
        "capacity_source": cap_src,
        "capacity_conflict": cap_conflict,
        "over_capacity_pct": over_pct,
        "measured": used_gb > 0,
    }


# ---------------------------------------------------------------------------
# KV movement bandwidth (host-tier estimate when no PMU is available)
# ---------------------------------------------------------------------------

RANK_LABELS = ("tp_rank", "pp_rank", "moe_ep_rank", "attn_tp_rank", "ep_rank")
_RANK_LABELS_RE = re.compile(
    r"\b(?:tp_rank|pp_rank|moe_ep_rank|attn_tp_rank|ep_rank)=\"?[^,\]\"]*\"?")

# Ranks whose window deltas agree to within this share are counting the same
# tokens.  Replicas agree exactly in practice (3,512,089 on all eight ranks of
# the Sep 8 TP=8 run); 1% leaves room for a rank that missed the final scrape.
RANK_REPLICA_TOL = 0.01


def rank_combine_rule(rank_deltas, tol: float = RANK_REPLICA_TOL) -> dict:
    """Max or sum across the ranks of one label set, decided from the data.

    A KV-movement token counter is exported once per rank.  Whether those
    series count the SAME tokens or DIFFERENT ones depends on the topology,
    and the rank label alone does not say which:

      TP / PP / EP over TP   every rank holds a shard of every token, so each
                             counts all of them -- summing reports N x.
      DP / DP-attention      each rank serves its own requests -- the total is
                             the sum.  Usually a dp_rank label separates these
                             and they never meet here; when a build labels them
                             with tp_rank only, they do.

    So the ranks' window deltas are compared.  Within `tol` of each other they
    are replicas and the max is taken; otherwise each rank's count is its own
    and they are summed.  A rule hard-coded either way is wrong for one of
    those layouts, and silently so.

    Returns {rule: "max" | "sum" | "single", ranks, spread_pct, reason}.
    """
    d = [float(x) for x in (rank_deltas or [])
         if x is not None and x == x and float(x) >= 0]
    n = len(d)
    if n <= 1:
        return {"rule": "single", "ranks": n, "spread_pct": 0.0,
                "reason": "one series, nothing to combine"}
    hi, lo = max(d), min(d)
    if hi <= 0:
        return {"rule": "max", "ranks": n, "spread_pct": 0.0,
                "reason": f"{n} ranks, all idle"}
    spread = (hi - lo) / hi
    if spread <= tol:
        return {"rule": "max", "ranks": n, "spread_pct": spread * 100.0,
                "reason": (f"{n} ranks agreed within {spread * 100:.2f}% — "
                           f"replicas of the same tokens, counted once")}
    return {"rule": "sum", "ranks": n, "spread_pct": spread * 100.0,
            "reason": (f"{n} ranks differed by {spread * 100:.1f}% — each "
                       f"counts its own requests, so they are summed")}


def summarise_rank_rules(rules) -> str:
    """One line for a report from several rank_combine_rule results."""
    rules = [r for r in (rules or []) if r and r.get("rule") != "single"]
    if not rules:
        return "one series per counter, no rank combination needed"
    kinds = {r["rule"] for r in rules}
    if kinds == {"max"}:
        n = max(r["ranks"] for r in rules)
        return f"counted once across ranks ({n} ranks agreed — replicas)"
    if kinds == {"sum"}:
        n = max(r["ranks"] for r in rules)
        return f"summed across ranks ({n} ranks counted different requests)"
    return "ranks combined per counter: " + "; ".join(r["reason"] for r in rules)


def window_counter_series(rows, candidates, meta: "dict | None" = None):
    """(times, values) of a SGLang token counter from timeseries rows.

    `rows` are dicts keyed by CSV column (`name[label=...]`).  The first
    candidate substring that matches any column wins.

    Ranks (tp/pp/ep labels) within one label set are combined by
    rank_combine_rule: the max when their window deltas agree (TP, PP and EP
    over TP each count the same tokens; summing reported 8x on TP=8), the sum
    when they do not (each rank counting its own requests).  Every other label
    set (dp_rank, is_streaming, ...) is summed.  Different metric names are
    never summed: a run dir can carry sglang_x and hicache_x for one quantity,
    so one name is chosen, preferring the sglang_ one.

    `meta`, when given, receives {"rules": [rank_combine_rule result per label
    set], "metric": the column group used}.

    Histogram side-series (bucket / _sum / _count) are excluded so they are
    not summed into a token total, unless the caller asked for one by name,
    as it does for an operation count like prefetch_pgs_count.

    Returns None when no column matches (unmeasured).  A counter that matched
    but never moved returns a real, flat series (measured, idle).
    """
    if not rows:
        return None
    _tcol = next((c for c in rows[0] if c and c.strip() == "time_sec"), None)

    def _num(r, c):
        try:
            return float(r.get(c) or "nan")
        except (TypeError, ValueError):
            return float("nan")

    for k in candidates:
        _drop = tuple(x for x in ("bucket", "_sum", "_count") if x not in k)
        cols = [c for c in rows[0]
                if c and k in c and not any(d in c for d in _drop)]
        if not cols:
            continue
        groups: dict = {}
        for c in cols:
            groups.setdefault(c.split("[", 1)[0].strip(), []).append(c)
        base = next((b for b in (f"sglang_{k}", k) if b in groups), next(iter(groups)))
        label_sets: dict = {}
        for c in groups[base]:
            label_sets.setdefault(_RANK_LABELS_RE.sub("", c), []).append(c)
        # Decide, per label set, whether its ranks are replicas or shards.
        combine = {}
        rules = []
        for key, set_cols in label_sets.items():
            deltas = []
            for c in set_cols:
                t = counter_window_total([[v for v in (_num(r, c) for r in rows)
                                           if v == v]])
                deltas.append(t["total"] if t["present"] else float("nan"))
            rule = rank_combine_rule(deltas)
            rules.append(rule)
            combine[key] = sum if rule["rule"] == "sum" else max
        if meta is not None:
            meta["rules"] = rules
            meta["metric"] = base
        times, series = [], []
        for i, r in enumerate(rows):
            tot, seen = 0.0, False
            for key, set_cols in label_sets.items():
                vals = [v for v in (_num(r, c) for c in set_cols) if v == v]
                if vals:
                    tot += combine[key](vals)
                    seen = True
            if seen:
                series.append(tot)
                t = _num(r, _tcol) if _tcol else float("nan")
                times.append(t if t == t else float(i))
        if len(series) < 2:
            continue
        return times, series
    return None


def window_counter_delta(rows, candidates,
                         meta: "dict | None" = None) -> "float | None":
    """Window delta of a SGLang token counter, by window_counter_series' rule.

    Returns None when no column matches (unmeasured) and 0.0 when it matched
    but never moved (measured, idle).
    """
    r = window_counter_series(rows, candidates, meta=meta)
    if not r:
        return None
    series = r[1]
    d = series[-1] - series[0]
    if d < 0:                      # counter reset inside the window
        d = series[-1]
    return max(0.0, d)


def token_reuse_density(reused_tokens: float, computed_tokens: float,
                        output_tokens: float, kv_bytes_per_token_kb: float) -> dict:
    """Token_Reuse_Density = reused prompt tokens per GB of KV generated.

    KV generated is the KV that had to be computed in the run: computed prompt
    tokens plus output tokens (cache-served prompt tokens reuse existing KV).
    The ticket wrote "÷ total_KV_bytes" with a "> 100 is a good fit for prefix
    acceleration" threshold; per byte that can never approach 100, so the
    denominator is GB (1e9 bytes), as agreed with the user.
    """
    kv_gen_tokens = max(0.0, float(computed_tokens or 0)) + max(0.0, float(output_tokens or 0))
    kv_gen_gb = kv_gen_tokens * float(kv_bytes_per_token_kb or 0) * 1024.0 / 1e9
    density = (float(reused_tokens or 0) / kv_gen_gb) if kv_gen_gb > 0 else 0.0
    return {"density": density, "kv_generated_tokens": kv_gen_tokens,
            "kv_generated_gb": kv_gen_gb, "reused_tokens": float(reused_tokens or 0),
            "good_fit": density > 100.0, "available": kv_gen_gb > 0}


def kv_movement_bandwidth(loadback_tokens: float = 0.0,
                          backup_tokens: float = 0.0,
                          prefetch_tokens: float = 0.0,
                          evict_tokens: float = 0.0,
                          kv_bytes_per_token_kb: float = 0.0,
                          window_s: float = 0.0) -> dict:
    """Logical host-tier KV movement in GB/s, when no DRAM PMU was collected.

    NOT memory-controller bandwidth.  It counts only KV bytes the engine says
    it moved between tiers, so it will read far below a PMU figure, and a low
    value cannot prove the DRAM channels have headroom.  Use it for
    correlation and shape.

    Exists in the kernel because Executive and Interactive each had their own
    version and they disagreed on the unit: one divided by 1024**2 (GiB), the
    other by 1e9 (GB), a 7.4% difference on identical inputs.  GB (1e9) is
    used here, matching how DRAM peak bandwidth is quoted by vendors.

    Returns per-direction and total GB/s plus the inputs, so a caller can show
    the working rather than a bare number.
    """
    if kv_bytes_per_token_kb <= 0 or window_s <= 0:
        return {"total_gbs": 0.0, "restore_gbs": 0.0, "backup_gbs": 0.0,
                "prefetch_gbs": 0.0, "evict_gbs": 0.0, "available": False,
                "note": "KV bytes/token or window unknown"}

    def _gbs(tok: float) -> float:
        return max(0.0, float(tok)) * kv_bytes_per_token_kb * 1024.0 / 1e9 / window_s

    restore = _gbs(loadback_tokens)
    backup = _gbs(backup_tokens)
    prefetch = _gbs(prefetch_tokens)
    evict = _gbs(evict_tokens)
    # Eviction is L1->L2 and backup is L2->L3: both cross host memory, but
    # counting eviction here as well would double-count a token that was
    # evicted and then backed up.  Total therefore covers the L2 boundary
    # movements the caller asked for and leaves eviction reported separately.
    total = restore + backup + prefetch
    return {"total_gbs": total, "restore_gbs": restore, "backup_gbs": backup,
            "prefetch_gbs": prefetch, "evict_gbs": evict, "available": total > 0,
            "note": "logical KV movement, not memory-controller bandwidth"}


# ---------------------------------------------------------------------------
# Mean vs median as a tail indicator
# ---------------------------------------------------------------------------

def tail_ratio(mean_value: float, p50_value: float) -> dict:
    """Mean / p50, and what that ratio implies about the distribution's tail.

    Percentiles say where the boundary sits; only the mean is sensitive to how
    far beyond it the worst cases run.  p99 alone cannot distinguish a tail
    that stops just past p99 from one that runs orders of magnitude further,
    but the mean/p50 ratio can.  Reporting the two side by side turns what
    look like two competing latency numbers into one signal.

    The mean is also the statistic Little's Law needs (L = lambda * W); a
    median substituted there gives the wrong queue depth.
    """
    if p50_value <= 0 or mean_value <= 0:
        return {"ratio": 0.0, "label": "", "severity": "unknown",
                "note": "mean or p50 unavailable"}
    r = mean_value / p50_value
    if r < 1.3:
        sev, lab = "tight", "tight \u2014 mean tracks the median"
    elif r < 3.0:
        sev, lab = "normal", "right-skewed \u2014 normal for latency"
    elif r < 10.0:
        sev, lab = "heavy", "heavy tail \u2014 outliers well beyond p50"
    else:
        sev, lab = "extreme", "extreme tail \u2014 check for stalls or a metrics artefact"
    return {"ratio": r, "label": lab, "severity": sev,
            "note": f"mean {mean_value:,.1f} / p50 {p50_value:,.1f} = {r:.1f}x"}


# ---------------------------------------------------------------------------
# Bandwidth sample sanitation
# ---------------------------------------------------------------------------

# No host sustains more than a few TB/s of DRAM bandwidth.  100 TB/s is far
# above any real machine and far below the byte-scale values that appear when
# a capacity leaks into a rate column, so it separates the two cleanly.
DRAM_SANE_MAX_GBS = 100_000.0


def sanitize_bandwidth_samples(values, max_gbs: float = DRAM_SANE_MAX_GBS) -> dict:
    """Drop physically impossible bandwidth samples before aggregating.

    A handful of bad samples destroys an arithmetic mean while leaving min,
    first and last correct — observed on a real run as 956 samples of ~0.42
    GB/s with five at 4.8e10 (44.7 GiB, a memory quantity in a rate column),
    giving a mean of 226,122,157 GB/s.

    Lives in the kernel because every report surface aggregates these series
    and each had its own path: the Executive was fixed while the End Report
    kept showing the impossible figure from the same file.

    Returns the cleaned values, what was dropped, and the resulting stats, so
    a caller can state the exclusion rather than hide it.
    """
    vals = [float(v) for v in (values or []) if v == v]
    clean = [v for v in vals if 0.0 <= v <= max_gbs]
    dropped = len(vals) - len(clean)
    if not clean:
        return {"values": [], "dropped": dropped, "mean": 0.0, "max": 0.0,
                "min": 0.0, "median": 0.0, "n": 0,
                "note": (f"all {len(vals)} sample(s) exceeded {max_gbs:,.0f} GB/s"
                         if vals else "no samples")}
    srt = sorted(clean)
    return {
        "values": clean, "dropped": dropped,
        "mean": sum(clean) / len(clean), "max": srt[-1], "min": srt[0],
        "median": srt[len(srt) // 2], "n": len(clean),
        "note": (f"{dropped} sample(s) above {max_gbs:,.0f} GB/s excluded "
                 f"before averaging \u2014 physically impossible values that "
                 f"otherwise dominate the arithmetic mean." if dropped else ""),
    }


def sane_mean(values, max_gbs: float = DRAM_SANE_MAX_GBS) -> float:
    """Mean of the plausible samples only. Convenience over the above."""
    return sanitize_bandwidth_samples(values, max_gbs)["mean"]


# ---------------------------------------------------------------------------
# Prefill cache hit ratio
# ---------------------------------------------------------------------------

def prefill_cache_hit_ratio(cache_tokens: float, compute_tokens: float) -> dict:
    """Fraction of prefill TOKENS served from cache over the window.

        cache / (cache + compute)

    Token-weighted, using window totals — not a mean of per-sample ratios.
    Those differ, and the difference is large on bursty traffic:

    * A mean over ALL samples includes idle ones, where the gauge reads 0.  At
      a 2.5% duty cycle that is ~97% zeros and drags a real 30% hit rate down
      to 0.5% — which says something about the wall clock, not the cache.
    * A mean over ACTIVE samples gives every sampling interval an equal vote,
      so an interval that prefilled 5 tokens counts as much as one that
      prefilled 100,000.

    Weighting by tokens answers the question a tiering study actually asks:
    of all the prefill work, how much was avoided?  That maps directly to GPU
    time saved.  It is also what
    ``sum(increase(...prefill_cache)) / sum(increase(...prefill_cache + ...prefill_compute))``
    computes in PromQL, so the report and a Grafana panel can agree.
    """
    c = max(0.0, float(cache_tokens or 0.0))
    k = max(0.0, float(compute_tokens or 0.0))
    total = c + k
    if total <= 0:
        return {"pct": 0.0, "cache_tokens": c, "compute_tokens": k,
                "total_tokens": 0.0, "available": False,
                "note": "no prefill tokens in this window"}
    return {"pct": c / total * 100.0, "cache_tokens": c, "compute_tokens": k,
            "total_tokens": total, "available": True,
            "note": (f"{c:,.0f} of {total:,.0f} prefill tokens served from cache "
                     f"(token-weighted over the window)")}


# ---------------------------------------------------------------------------
# Per-interval histogram percentiles
# ---------------------------------------------------------------------------

MIN_COMPLETIONS_FOR_QUANTILE = 10


def percentiles_from_bucket_deltas(bucket_series, quantiles=(0.5, 0.9, 0.99),
                                   min_count: int = MIN_COMPLETIONS_FOR_QUANTILE):
    """Percentiles per interval from cumulative histogram bucket counts.

    `bucket_series` is [(le, [cumulative counts over time]), ...] sorted by le.
    For each interval the per-bucket delta gives the requests that completed in
    that interval, and the quantile is read off that distribution with linear
    interpolation inside the containing bucket.

    Prometheus computes histogram_quantile over a whole range, not as a series,
    so a percentile-over-time has to be reconstructed this way.  Two limits are
    inherent and worth stating wherever the result is shown:

    * Resolution is bucket-limited.  A quantile landing in the +Inf bucket can
      only be reported as ">= the last finite le".
    * An interval with too few completions gives a noisy quantile; intervals
      with no completions yield NaN rather than a fabricated zero.
    """
    if not bucket_series:
        return {}
    les = [le for le, _ in bucket_series]
    cols = [vals for _, vals in bucket_series]
    n = min(len(v) for v in cols) if cols else 0
    if n < 2:
        return {}

    _finite_les = [le for le in les if le == le and le != float("inf")]
    _last_finite = _finite_les[-1] if _finite_les else (les[-1] if les else 0.0)
    # Adaptive binning: accumulate consecutive intervals until the group has
    # enough completions to support distinct quantiles, then emit one point.
    # Dropping sparse intervals outright left the chart empty on a low-duty
    # workload; widening the bin trades TIME resolution — which the reader can
    # see from the point spacing — for quantiles that are real, rather than
    # three identical lines or nothing at all.
    _groups: list[tuple[int, int]] = []
    _start = 1
    for i in range(1, n):
        _tot = 0.0
        for c in cols[-1:]:
            d = c[i] - c[_start - 1]
            _tot = d if d == d and d > 0 else 0.0
        if _tot >= min_count or i == n - 1:
            _groups.append((_start, i))
            _start = i + 1
    if not _groups:
        _groups = [(1, n - 1)]

    out = {q: [] for q in quantiles}
    _times: list[int] = []
    for _lo, _hi in _groups:
        # Cumulative -> per-interval counts, clamped at 0 for counter resets.
        cum = []
        for c in cols:
            d = c[_hi] - c[_lo - 1]
            cum.append(d if d == d and d > 0 else 0.0)
        # Cumulative bucket counts must be non-decreasing across le.  Clamping
        # each delta at 0 independently can break that — a bucket whose delta
        # was clamped ends up BELOW its predecessor — and then the quantile
        # target is never reached, every quantile falls through to the last
        # bucket boundary, and p50/p90/p99 all report the same value.  Restore
        # monotonicity with a running maximum before reading any quantile.
        _run = 0.0
        for _k in range(len(cum)):
            _run = max(_run, cum[_k])
            cum[_k] = _run
        total = cum[-1] if cum else 0.0
        # An interval with too few completions cannot support distinct
        # quantiles: with one request p50 == p90 == p99 by definition, and one
        # such interval anywhere in the run makes all three legend peaks
        # identical.  At a low duty cycle most intervals look like this, so
        # reporting them produces three lines that are really one.  Below the
        # threshold the interval yields NaN and the line breaks.
        _times.append(_hi)
        if total < min_count:
            for q in quantiles:
                out[q].append(float("nan"))
            continue
        for q in quantiles:
            target = q * total
            prev_c, prev_le = 0.0, 0.0
            val = float("nan")
            for le, c in zip(les, cum):
                if c >= target:
                    span = c - prev_c
                    frac = ((target - prev_c) / span) if span > 0 else 0.0
                    val = prev_le + (le - prev_le) * frac
                    break
                prev_c, prev_le = c, le
            # Falling through means the quantile sits in the open-ended top
            # bucket.  Report the last finite boundary — the true value is at
            # least that — rather than a number implying more precision than
            # the histogram carries.
            # A quantile inside the open-ended +Inf bucket interpolates to
            # infinity.  Emit NaN so the line breaks, rather than plotting a
            # number: the reading is unbounded above, not large.
            if val == float("inf"):
                val = float("nan")
            out[q].append(val if val == val else float("nan"))
    # Index of the interval each emitted point covers, so a caller can align
    # the (now unevenly spaced) points to the right timestamps.
    out["_index"] = _times
    # The last finite bucket boundary.  A point equal to this value may be a
    # censored reading — the quantile sat in the open-ended top bucket and the
    # true value is at least this, not exactly this.  Callers that display the
    # value should say so rather than implying a measurement.
    out["_last_finite"] = _last_finite
    return out


# ---------------------------------------------------------------------------
# Device-figure vetting
#
# Two headline numbers in a v1.69.0 local-L3 report were artifacts that every
# other number in the same report contradicted:
#
#   L3 SSD storage queue depth   1,401.09 mean / 3,430 peak
#   L3 SSD storage BW (device)   145 rd / 28,672 wr MB/s peak
#
# The queue depth came from blktrace's QD(t) = count(Q) - count(C).  That
# difference is unbounded when C events are missing, and the same trace
# reported 0.00 ms read / 0.00 ms write latency -- it captured no completion
# dwell at all, so the completions being subtracted were not there.  The
# giveaways were all present: p50 1,385 against a mean of 1,401 (a rising
# counter, not a queue that drains), the device's own avgqu-sz peaking at
# 25.97 over the same window, and the report's own Little's Law line reading
# "3,461 IOPS x 0.265 ms = 0.92 expected depth".  A mean depth of 1,401 at
# 3,461 IOPS implies 405 ms per I/O on an NVMe SSD.
#
# 28,672 MB/s is 28 GiB/s through one namespace, on a drive whose mean write
# bandwidth over the window was 9.3 MB/s.
#
# Both then became procurement requirements: "Queue Depth peak 3,430 - SSD
# must sustain observed peak concurrency" and "Sequential Write BW 28672 MB/s
# x 1.3 = 37274 MB/s".  Vetting lives here so the tile and the requirement
# table cannot reach different conclusions about the same figure.
# ---------------------------------------------------------------------------

# PCIe 5.0 x4 tops out near 16 GB/s of payload; nothing a single NVMe
# namespace reports can legitimately exceed it.  Deliberately generous: the
# purpose is to catch unit and counter-reset artifacts, not to police fast
# hardware.
NVME_MAX_BW_MBS = 16384.0

# Shared with the report's own bound.  An NVMe submission queue holds at most
# 65,536 entries, but a namespace sustaining thousands of outstanding requests
# is an unmatched-event count in every case seen here.
QD_PLAUSIBLE_MAX = 4096.0


def vet_device_bw_peak(peak_mbs, mean_mbs=0.0, label="") -> dict:
    """Is a device bandwidth peak physically possible?

    Returns {mbs, rejected, reason, ratio_to_mean}.  `mbs` is 0.0 when the
    figure cannot stand, so a caller that ignores `rejected` publishes nothing
    rather than the artifact.
    """
    try:
        _p = float(peak_mbs or 0.0)
        _m = float(mean_mbs or 0.0)
    except (TypeError, ValueError):
        return {"mbs": 0.0, "rejected": True, "reason": "not a number",
                "ratio_to_mean": 0.0}
    _ratio = (_p / _m) if _m > 0 else 0.0
    if _p <= 0:
        return {"mbs": 0.0, "rejected": False, "reason": "",
                "ratio_to_mean": 0.0}
    if _p > NVME_MAX_BW_MBS:
        return {"mbs": 0.0, "rejected": True,
                "reason": (f"{_p:,.0f} MB/s is {_p / 1024.0:,.1f} GB/s through "
                           f"one namespace, above the ~{NVME_MAX_BW_MBS / 1024.0:,.0f} "
                           f"GB/s a PCIe 5.0 x4 link can carry"
                           + (f", and {_ratio:,.0f}x this window's mean of "
                              f"{_m:,.1f} MB/s" if _ratio > 0 else "")
                           + " — a counter reset or a unit error, not a burst"),
                "ratio_to_mean": _ratio}
    return {"mbs": _p, "rejected": False, "reason": "", "ratio_to_mean": _ratio}


def vet_queue_depth(event_mean=0.0, event_peak=0.0, event_lat_ms=0.0,
                    event_iops=0.0, device_mean=0.0, device_peak=0.0) -> dict:
    """Decide which queue-depth figure a report may headline.

    `event_*` is the blktrace Q->C summary; `device_*` is the kernel's own
    avgqu-sz / in-flight gauge.  Returns {mean, peak, source, rejected,
    reasons, expected}, where `rejected` refers to the EVENT figure.

    Three independent grounds for rejecting it, each of which has fired:

    1. No completion dwell.  QD(t) subtracts C events from Q events; a trace
       that produced no Q->C latency did not capture the C events, so the
       difference only rises.
    2. Little's Law.  depth = IOPS x latency is computed from counters that
       do not involve the depth, so a mean depth far above it is arithmetic,
       not load.
    3. An instantaneous gauge far below it.  A sample cannot invent requests,
       so the gauge is a floor on the real depth; the converse rule (a gauge
       far ABOVE the event figure) was already applied and is kept.
    """
    def _f(v):
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0

    _em, _ep = _f(event_mean), _f(event_peak)
    _lat, _iops = _f(event_lat_ms), _f(event_iops)
    _dm, _dp = _f(device_mean), _f(device_peak)
    _expected = (_iops * _lat / 1000.0) if (_iops > 0 and _lat > 0) else 0.0

    _reasons = []
    if _ep > 0 or _em > 0:
        if _ep > QD_PLAUSIBLE_MAX or _em > QD_PLAUSIBLE_MAX:
            _reasons.append(
                f"{_em:,.0f} mean / {_ep:,.0f} peak is above the plausible "
                f"bound of {QD_PLAUSIBLE_MAX:,.0f}")
        if _iops > 0 and _lat <= 0:
            _reasons.append(
                "the trace reported no Q→C completion latency, so the "
                "completions that QD(t) = count(Q) − count(C) subtracts "
                "were not captured and the difference can only rise")
        # Allow generous slack: a factor of 10 AND 8 absolute, so a shallow
        # queue measured as 0.9 against an expected 0.3 is not "rejected".
        if _expected > 0 and _em > max(_expected * 10.0, _expected + 8.0):
            _reasons.append(
                f"Little's Law puts the depth at {_expected:,.2f} "
                f"({_iops:,.0f} IOPS × {_lat:.3f} ms), so a mean of "
                f"{_em:,.2f} would need {_em / max(_iops, 1e-9) * 1000.0:,.0f} "
                f"ms per I/O")
        if _dp > 0 and _ep > max(_dp * 10.0, _dp + 8.0):
            _reasons.append(
                f"the kernel's own gauge peaked at {_dp:,.2f} over the same "
                f"window, {_ep / max(_dp, 1e-9):,.0f}x lower")

    if _reasons and (_dp > 0 or _dm > 0):
        return {"mean": _dm, "peak": _dp, "source": "device gauge",
                "rejected": True, "reasons": _reasons, "expected": _expected}
    if _reasons:
        return {"mean": 0.0, "peak": 0.0, "source": "none",
                "rejected": True, "reasons": _reasons, "expected": _expected}
    if _ep > 0 or _em > 0:
        return {"mean": _em, "peak": _ep, "source": "blktrace Q→C",
                "rejected": False, "reasons": [], "expected": _expected}
    return {"mean": _dm, "peak": _dp,
            "source": "device gauge" if (_dp > 0 or _dm > 0) else "none",
            "rejected": False, "reasons": [], "expected": _expected}


def resolve_latency_percentile(kind: str, quantile: float,
                               histogram_ms: float = 0.0,
                               session_ms: float = 0.0,
                               pct_ts_ms: float = 0.0,
                               summary_ms: float = 0.0,
                               top_bucket_ms: float = 0.0,
                               mean_ms: float = 0.0) -> dict:
    """One percentile figure, by one resolution order, for every surface.

    `resolve_latency_ms` did this for the MEAN after the Combined and
    comparison reports were found disagreeing about it.  The percentile paths
    were left alone and drifted further: a v1.69.0 report carried three
    different TTFT p50 values at once --

        62,895 ms   the interactive grid
         1,755 ms   the TTFT p50/p90/p99 chart (histogram)
       190,055 ms   the End report ("Median")

    -- and the first of those was not a percentile at all.  Both
    `interactive.py` and `amoprof.py` resolved it as
    ``_ttft_p50_ms or _ttft_ms`` and ``m.sess_ttft_p50_ms or m.ttft_ms``: when
    the percentile was missing they substituted the MEAN, then labelled it
    "Median" and "histogram_quantile/percentile timeseries".  62,895 ms is
    exactly the TTFT mean tile's value, and E2E p50 was likewise exactly the
    E2E mean.  A mean is never a median, and a tile that says p50 while
    showing a mean is worse than an empty tile: it reads as corroboration.

    So `mean_ms` is accepted here only to be REFUSED, loudly, with the mean's
    value named in the method so a reader can see what was rejected and why.

    Censoring.  A Prometheus histogram's top bucket is open-ended (+Inf), so a
    quantile landing in it is reported as that bucket's floor -- a lower
    bound, not a measurement.  On the same report TTFT p99 read exactly
    400,000.00 ms and TPOT p90 and p99 both read exactly 8,000.0: bucket
    boundaries, not latencies.  Pass `top_bucket_ms` and a figure at or above
    it comes back with censored=True so the surface can mark it.

    Returns {ms, step, method, censored, refused_mean_ms}.
    """
    k = str(kind or "").strip().lower()
    base = _LATENCY_KINDS.get(k, (k, k))[0]
    q = float(quantile or 0.0)
    qlabel = f"p{q * 100:.0f}" if q < 1 else f"p{q:.0f}"

    def _out(ms, step, method):
        _ms = float(ms)
        _cens = bool(top_bucket_ms and _ms >= float(top_bucket_ms) - 1e-9)
        return {"ms": _ms, "step": step, "method": method,
                "censored": _cens,
                "refused_mean_ms": 0.0}

    if histogram_ms and histogram_ms > 0:
        return _out(histogram_ms, 1,
                    f"histogram_quantile({q:g}, rate({base}_bucket[W])) × 1000")
    if session_ms and session_ms > 0:
        return _out(session_ms, 2,
                    f"{qlabel} of per-request {base} over the window")
    if pct_ts_ms and pct_ts_ms > 0:
        return _out(pct_ts_ms, 3,
                    f"{base} {qlabel} series, mean over active intervals")
    if summary_ms and summary_ms > 0:
        return _out(summary_ms, 4,
                    f"sglang_summary.json {qlabel} — NOT verified as "
                    f"window-scoped")
    # Nothing. The mean is NOT a substitute, and saying so is the point.
    _m = float(mean_ms or 0.0)
    return {"ms": 0.0, "step": 0, "censored": False, "refused_mean_ms": _m,
            "method": (f"{base} {qlabel} unavailable"
                       + (f" — the mean ({_m:,.0f} ms) is not substituted for "
                          f"it here" if _m > 0 else ""))}


# ─── Labelled series: one resolver, one window total ─────────────────────────
#
# Why this block exists
# ---------------------
# "The window total of a cumulative counter" had FOUR implementations in this
# tree, and they agreed only on a single clean monotonic column:
#
#   metric_kernels.counter_delta   max(0, last - first), one series
#   amoprof._delta_sum_metric      Σ_col max(0, last_col - first_col)
#   combined._kvg_counter_delta    Σ_steps max(0, step), one column
#   comparator._kv_delta           max(0, (Σ_col last) - (Σ_col first))
#
# The disagreements are not theoretical; each one shows up on real runs.
#
# * comparator sums the COLUMNS of a row and then differences the row totals.
#   A series that joins the window late -- a scrape target whose first sample
#   lands on row 2, which is routine after a restart or a rank coming up --
#   is missing from row 1, so the subtrahend is a partial sum and the delta
#   is inflated by that column's entire starting value. For a lifetime
#   counter that is its whole history, not its window. And for a latency mean
#   of Δsum ÷ Δcount the two inflations do NOT cancel: they are inflated by
#   different amounts (that column's accumulated seconds against its
#   accumulated request count), so the ratio moves toward that one column's
#   lifetime mean.
# * comparator clamps the AGGREGATE at zero, so one column resetting drags
#   every healthy column down with it. amoprof clamps per column.
# * only combined is reset-safe INSIDE the window: last - first silently
#   discards every observation made before a restart.
# * amoprof normalises `:` to `_` and strips spaces before matching;
#   combined strips only quotes. So a part spelled `sglang_realtime_tokens`
#   matched a `sglang:realtime_tokens_total` column on one surface and
#   missed it on the other.
#
# The rule below is the one that reduces to each of those where it is right
# and differs from it only where it is wrong: per column, the sum of positive
# per-step differences; then the sum across columns. On a clean monotonic
# single column it equals last - first exactly, so adopting it changes no
# figure that was already correct.


def normalize_series_name(name) -> str:
    """A Prometheus CSV header reduced to a form label spelling cannot vary.

    `mode="decode"`, `mode=decode`, `mode='decode'` and `mode= decode` all
    normalise to `mode=decode`, and `sglang:x` to `sglang_x`, so a caller can
    spell a part the obvious way and match whatever the exporter wrote.
    """
    try:
        x = str(name).lower()
    except Exception:
        return ""
    for ch in ('"', "'", " ", "\\"):
        x = x.replace(ch, "")
    return x.replace(":", "_")


def resolve_series_columns(fieldnames: Iterable, parts: Iterable,
                           exclude_buckets: bool = True) -> list:
    """Every column whose normalised name contains ALL of `parts`.

    ALL of them, not the first: a counter fanned out into one series per rank
    or per label value is only whole when its series are summed, and taking
    the first silently reports one rank's share as the total. With a single
    matching column the result is that column, so a caller that was right
    before stays right.

    Histogram `_bucket` series are excluded by default so a bucket column
    never shadows the `_sum`/`_count` pair of the same metric.
    """
    out: list = []
    wanted = [normalize_series_name(p) for p in (parts or []) if str(p or "").strip()]
    if not wanted:
        return out
    for col in (fieldnames or []):
        if col is None:
            continue
        low = normalize_series_name(col)
        if not low:
            continue
        if exclude_buckets and "_bucket" in low:
            continue
        if all(w in low for w in wanted):
            out.append(col)
    return out


def counter_window_total(series: Iterable) -> dict:
    """Work done across the window by a cumulative counter, reset-safe.

    `series` is one sequence of samples or a sequence of them (one per
    matching column). Each column contributes the sum of its per-step
    increases; the columns are then summed.

    A step that goes DOWN is a counter reset -- a server restart inside the
    window -- and contributes the post-reset value, which is what the counter
    has accumulated since it restarted. This is Prometheus' own convention in
    ``increase()``, which is the function the reports' formula strings cite,
    so the kernel and the formula shown beside the figure now compute the
    same thing. Discarding the step instead (``max(0, step)``, which is what
    combined._kvg_counter_delta did) silently drops every token moved after
    the restart; on the reference fixture that is 25 of 195.

    Nothing here extrapolates. Prometheus' ``increase()`` also scales the
    result to the full range, which invents work at the window edges; the
    figures in these reports are stated as measured, so the window total is
    only what the samples show.

    Returns {total, columns, usable_columns, resets, reset_recovered,
    samples, present, method}. ``reset_recovered`` is the part of the total
    attributed to post-reset values, kept separate so it can be audited
    rather than folded in invisibly -- a large figure there on a series that
    should not reset is the sign that a GAUGE was passed to a counter path.

    ``present`` is the field that keeps *absent* distinct from *zero*: False
    means no column carried two usable samples, so there was nothing to
    difference -- which is a gap in telemetry, not an idle tier. A caller
    that renders 0.0 for both has turned a missing counter into a
    measurement.
    """
    cols: list = []
    if series is None:
        cols = []
    else:
        _s = list(series)
        if _s and not any(isinstance(x, (list, tuple)) for x in _s):
            cols = [_s]                      # a single flat sequence
        else:
            cols = [list(x) for x in _s if isinstance(x, (list, tuple))]
    total = 0.0
    resets = 0
    recovered = 0.0
    samples = 0
    usable = 0
    for col in cols:
        v = _clean(col)
        samples += len(v)
        if len(v) < 2:
            # A single sample of a MONOTONIC COUNTER carries no window
            # information: its value is the lifetime total since the server
            # started, which is unrelated to the window asked for.
            continue
        usable += 1
        for i in range(1, len(v)):
            d = v[i] - v[i - 1]
            if d >= 0:
                total += d
            else:
                resets += 1
                if v[i] > 0:
                    total += v[i]
                    recovered += v[i]
    return {"total": float(total), "columns": len(cols),
            "usable_columns": usable, "resets": resets,
            "reset_recovered": float(recovered), "samples": samples,
            "present": usable > 0,
            "method": ("Σ per-step increase over "
                       f"{usable} series"
                       + (f", {resets} counter reset(s) spanned "
                          f"({recovered:,.0f} credited post-reset)"
                          if resets else "")
                       if usable else "no series carried two samples")}


def latency_window_ms(sum_series: Iterable, count_series: Iterable) -> dict:
    """Histogram mean over the window: Δsum ÷ Δcount, in milliseconds.

    The same estimator as :func:`ratio_delta`, over the canonical window
    total above and reporting whether the inputs were there at all. Returns
    {ms, d_sum, d_count, present, method}; ``present`` is False when either
    counter was absent or no observation completed, so the caller can say
    "not exported" rather than publish a 0 ms latency.
    """
    _s = counter_window_total(sum_series)
    _c = counter_window_total(count_series)
    if not (_s["present"] and _c["present"]) or _c["total"] <= 0:
        _why = ("no observations completed in the window"
                if (_s["present"] and _c["present"])
                else "the _sum/_count counters were not exported")
        return {"ms": 0.0, "d_sum": _s["total"], "d_count": _c["total"],
                "present": False, "method": _why}
    return {"ms": _s["total"] / _c["total"] * 1000.0,
            "d_sum": _s["total"], "d_count": _c["total"], "present": True,
            "method": (f"Δ_sum ÷ Δ_count over the window "
                       f"({_s['total']:,.3f} s ÷ {_c['total']:,.0f} obs)")}


# ─── How much of the window was alive, and where the dead time sat ──────────
#
# Why this exists
# ---------------
# Two runs of the same workload were compared over windows of 1,800 s and
# 2,925 s. Every time-average favoured the shorter one:
#
#     output throughput   50.1 vs 45.6 tok/s
#     GPU utilisation     84.2% vs 49.1%
#     HBM bandwidth        341 vs 226 GB/s
#
# and all three reversed once the dead time was removed, because the longer
# window's workload had finished inside it. Its HBM bandwidth fell
# monotonically by quartile -- 392, 221, 156, 136 GB/s -- and its last
# samples read 0, 13, 4 GB/s, while the shorter window's were flat at 332,
# 321, 379, 332 and dropped only on the final sample.
#
# A window mean is only a property of the system when the window is a
# property of the workload. Nothing in the comparison said otherwise: the
# duration guard fires above 2x and these windows differ by 1.63x, so a
# 35%-dead window was compared against a 2%-dead one in silence.
#
# `trailing_idle_s` is the figure that catches it, and the active SPAN is the
# denominator a rate should have used.


def active_window_fraction(values: Sequence[float],
                           times: "Sequence[float] | None" = None,
                           threshold: "float | None" = None,
                           rel: float = 0.05) -> dict:
    """What fraction of a window an activity series was doing work.

    `threshold` is absolute when given. Otherwise it is `rel` x the series'
    own robust peak (its 95th percentile, so one spike cannot set the bar),
    which keeps the test meaningful whether the series is a percentage, GB/s
    or tokens per second. The threshold used is returned, because a fraction
    without its threshold is not checkable.

    Returns {fraction, active_samples, samples, threshold, peak,
    active_span_s, lead_idle_s, trail_idle_s, present, method}. The idle
    figures need `times`; without them they are 0.0 and only the fraction is
    meaningful.

    A series shorter than three samples gets present=False: two samples
    cannot distinguish a quiet window from a short one.
    """
    v = _clean(values)
    t = _clean(times) if times is not None else []
    if len(v) < 3:
        return {"fraction": 0.0, "active_samples": 0, "samples": len(v),
                "threshold": 0.0, "peak": (max(v) if v else 0.0),
                "active_span_s": 0.0, "lead_idle_s": 0.0,
                "trail_idle_s": 0.0, "present": False,
                "method": "fewer than 3 samples — no duty cycle to measure"}
    srt = sorted(v)
    # p95 by nearest rank, which on a short series is simply the maximum.
    peak = srt[min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))]
    thr = float(threshold) if threshold is not None else max(0.0, peak * rel)
    idx = [i for i, x in enumerate(v) if x > thr]
    frac = len(idx) / len(v)
    span = lead = trail = 0.0
    if t and len(t) == len(v) and idx:
        span = max(0.0, t[idx[-1]] - t[idx[0]])
        lead = max(0.0, t[idx[0]] - t[0])
        trail = max(0.0, t[-1] - t[idx[-1]])
    return {"fraction": frac, "active_samples": len(idx), "samples": len(v),
            "threshold": thr, "peak": peak, "active_span_s": span,
            "lead_idle_s": lead, "trail_idle_s": trail, "present": True,
            "method": (f"{len(idx)} of {len(v)} samples above "
                       f"{thr:,.3g} ("
                       + (f"{rel:.0%} of the series' p95 peak {peak:,.3g}"
                          if threshold is None else "absolute threshold")
                       + ")")}


def bucket_edge_check(value_ms: float, bucket_les_s: Sequence[float],
                      rel_tol: float = 1e-6) -> dict:
    """Is a reported latency sitting exactly on a histogram bucket boundary?

    A Prometheus histogram resolves no finer than its buckets, so a quantile
    that lands on a boundary carries no information about where inside the
    neighbouring buckets it really is. On the reference ladder -- 0.08, 0.8,
    8, 400 s -- a reported p50 of exactly 800.00 ms is the 0.8 s edge, and
    the span it stands for is 10x wide.

    Returns {on_edge, le_s, lower_s, span_ratio, note}. `span_ratio` is the
    width of the bracket the figure actually stands for, as a multiple: 1.0
    means the boundary is also the resolution.
    """
    v = float(value_ms or 0.0) / 1000.0
    les = sorted({float(x) for x in (bucket_les_s or [])
                  if _finite(x) and float(x) > 0})
    if v <= 0 or not les:
        return {"on_edge": False, "le_s": 0.0, "lower_s": 0.0,
                "span_ratio": 0.0, "note": ""}
    for i, le in enumerate(les):
        if abs(v - le) <= max(abs(le) * rel_tol, 1e-12):
            lower = les[i - 1] if i > 0 else 0.0
            upper = les[i + 1] if i + 1 < len(les) else float("inf")
            ratio = (upper / lower) if (lower > 0 and upper != float("inf")) \
                else 0.0
            return {"on_edge": True, "le_s": le, "lower_s": lower,
                    "span_ratio": ratio,
                    "note": (f"lands exactly on the le={le:g}s bucket "
                             f"boundary, so it is bucket-limited: the "
                             f"histogram cannot place it inside "
                             + (f"{lower:g}–"
                                f"{upper:g}s ({ratio:,.0f}x wide)"
                                if ratio else f"the neighbouring buckets"))}
    return {"on_edge": False, "le_s": 0.0, "lower_s": 0.0, "span_ratio": 0.0,
            "note": ""}


# ─── Idle with work waiting, against idle with nothing to do ────────────────
#
# Why this exists
# ---------------
# active_window_fraction says how much of a window the GPUs were busy. It
# cannot say WHY they were not, and the two reasons point in opposite
# directions:
#
#   no work      nothing queued, nothing running -- the client was quiet.
#                Dividing by the active span is then the right correction.
#   stall        requests were waiting to enter prefill and the GPUs sat
#                idle anyway -- the server held work it had room for.
#                Dividing by the active span EXCUSES exactly the problem.
#
# On the reference pair -- the same ~5,900-request workload on a local-SSD L3
# tier and on an L3.5 memory node -- the L3 run took 50 min against 30, was
# idle for 40% of its window, and only one of those minutes was at the end.
# The rest was two episodes of GPU utilisation at 0% with queue-wait p50
# above 330 s and the L1 KV pool under 12% full. The active-span throughput
# put L3 ahead; the run itself finished 1.66x later.
#
# The caller aligns the series on one time base; this only classifies.


def admission_stalls(times: Sequence[float], busy: Sequence[float],
                     waiting: Sequence[float],
                     running: "Sequence[float] | None" = None,
                     kv_fill_pct: "Sequence[float] | None" = None,
                     busy_threshold: "float | None" = None,
                     rel: float = 0.10, min_samples: int = 2) -> dict:
    """Split a window's idle time into stalls and genuinely idle time.

    `busy` is an activity gauge (GPU utilisation), `waiting` the scheduler's
    waiting-queue gauge, `running` the decode batch and `kv_fill_pct` the L1
    KV pool's fill -- all sampled at `times`. A sample is

      busy      busy > threshold
      stall     not busy, and at least one request waiting
      no work   not busy, nothing waiting, nothing running
      other     not busy, nothing waiting, but requests running

    The threshold is absolute when given, else `rel` x the series' p95 peak,
    the same rule active_window_fraction uses. A stall EPISODE is a run of at
    least `min_samples` consecutive stall samples: one sample of an idle GPU
    beside a non-empty queue is the scheduler between two batches, not a
    stall.

    Each sample stands for the median sampling step, so the seconds returned
    sum to the sampled span plus one step.

    Returns {present, samples, step_s, threshold, busy_s, stall_s,
    no_work_s, other_idle_s, episodes, longest, method}; each episode is
    {t_start, t_end, dur_s, samples, waiting_peak, waiting_mean,
    kv_fill_mean}. present=False when the series do not line up or are
    shorter than three samples.
    """
    t = [float(x) for x in (times or [])]
    b = [float(x) for x in (busy or [])]
    w = [float(x) for x in (waiting or [])]
    r = [float(x) for x in running] if running is not None else []
    k = [float(x) for x in kv_fill_pct] if kv_fill_pct is not None else []
    n = len(t)
    _empty = {"present": False, "samples": n, "step_s": 0.0,
              "threshold": 0.0, "busy_s": 0.0, "stall_s": 0.0,
              "no_work_s": 0.0, "other_idle_s": 0.0, "episodes": [],
              "longest": None}
    if n < 3 or len(b) != n or len(w) != n:
        return {**_empty, "method": "busy, waiting and time series do not "
                                    "line up, or fewer than 3 samples"}
    if r and len(r) != n:
        r = []
    if k and len(k) != n:
        k = []
    _d = sorted(t[i] - t[i - 1] for i in range(1, n) if t[i] > t[i - 1])
    step = _d[len(_d) // 2] if _d else 0.0
    if step <= 0:
        return {**_empty, "method": "time series has no positive step"}
    _fin = sorted(x for x in b if _finite(x))
    if not _fin:
        return {**_empty, "method": "busy series has no finite samples"}
    peak = _fin[min(len(_fin) - 1, int(round(0.95 * (len(_fin) - 1))))]
    thr = float(busy_threshold) if busy_threshold is not None         else max(0.0, peak * rel)

    kind: list[str] = []
    for i in range(n):
        if _finite(b[i]) and b[i] > thr:
            kind.append("busy")
        elif _finite(w[i]) and w[i] >= 1.0:
            kind.append("stall")
        elif r and _finite(r[i]) and r[i] >= 1.0:
            kind.append("other")
        else:
            kind.append("none")

    episodes: list[dict] = []
    i = 0
    while i < n:
        if kind[i] != "stall":
            i += 1
            continue
        j = i
        while j + 1 < n and kind[j + 1] == "stall":
            j += 1
        if j - i + 1 >= min_samples:
            _w = [w[x] for x in range(i, j + 1) if _finite(w[x])]
            _k = [k[x] for x in range(i, j + 1) if k and _finite(k[x])]
            episodes.append({
                "t_start": t[i], "t_end": t[j],
                "dur_s": (t[j] - t[i]) + step, "samples": j - i + 1,
                "waiting_peak": max(_w) if _w else 0.0,
                "waiting_mean": (sum(_w) / len(_w)) if _w else 0.0,
                "kv_fill_mean": (sum(_k) / len(_k)) if _k else None})
        else:
            # Too short to be a stall: the scheduler between two batches.
            for x in range(i, j + 1):
                kind[x] = "other"
        i = j + 1

    _cnt = {c: kind.count(c) for c in ("busy", "stall", "none", "other")}
    longest = max(episodes, key=lambda e: e["dur_s"]) if episodes else None
    return {"present": True, "samples": n, "step_s": step, "threshold": thr,
            "busy_s": _cnt["busy"] * step, "stall_s": _cnt["stall"] * step,
            "no_work_s": _cnt["none"] * step,
            "other_idle_s": _cnt["other"] * step,
            "episodes": episodes, "longest": longest,
            "method": (f"{n} samples at a {step:,.0f} s step; busy above "
                       f"{thr:,.3g} ("
                       + (f"{rel:.0%} of the busy series' p95 {peak:,.3g}"
                          if busy_threshold is None
                          else "absolute threshold")
                       + f"); a stall is ≥{min_samples} consecutive "
                         f"idle samples with ≥1 request waiting")}
