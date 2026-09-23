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
    "tail_ratio",
    "DRAM_SANE_MAX_GBS",
    "sanitize_bandwidth_samples",
    "sane_mean",
    "prefill_cache_hit_ratio",
    "percentiles_from_bucket_deltas",
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

    Anything left over (`used - weights - kv_pool`) is activations, CUDA
    context, allocator fragmentation and cuBLAS workspace. It is labelled as a
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

    residual_gb = max(0.0, per_gpu_used - weights_gb - kv_pool_gb)
    free_gb = max(0.0, per_gpu_total - per_gpu_used)
    over = (weights_gb + kv_pool_gb) > per_gpu_used > 0

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
        "note": ("weights + KV pool exceed measured HBM used — check KV "
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
    if hicache_total_gb > 0:
        cap_gb, cap_src = float(hicache_total_gb), "configured HiCache allocation"
    elif hicache_total_tokens > 0 and kv_bytes_per_token_kb > 0:
        cap_gb = hicache_total_tokens * kv_bytes_per_token_kb / 1024.0 / 1024.0
        cap_src = "sglang_hicache_host_total_tokens x KV bytes/token"
    elif hicache_ratio > 0 and kv_pool_tokens > 0 and kv_bytes_per_token_kb > 0:
        cap_gb = kv_pool_tokens * hicache_ratio * kv_bytes_per_token_kb / 1024.0 / 1024.0
        cap_src = (f"--hicache-ratio {hicache_ratio:g} x max_total_num_tokens "
                   f"{kv_pool_tokens:,.0f} x KV {kv_bytes_per_token_kb:.0f} KB/token")
    elif host_dram_total_gb > 0:
        cap_gb, cap_src = float(host_dram_total_gb), "host DRAM total (not an allocation)"

    # Occupancy can never exceed the allocation it sits in.
    if cap_gb > 0 and used_gb > cap_gb:
        used_src += f" (clamped to capacity from {used_gb:.1f} GB)"
        used_gb = cap_gb

    return {
        "used_gb": used_gb,
        "capacity_gb": cap_gb,
        "fill_pct": (used_gb / cap_gb * 100.0) if cap_gb > 0 else 0.0,
        "used_source": used_src,
        "capacity_source": cap_src,
        "measured": used_gb > 0,
    }


# ---------------------------------------------------------------------------
# KV movement bandwidth (host-tier estimate when no PMU is available)
# ---------------------------------------------------------------------------

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
