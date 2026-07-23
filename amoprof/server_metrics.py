"""
amoprof/server_metrics.py — single source of truth for inference-server
backend metric maps and server-type detection.

AMOProf's report layer reads canonical files named `sglang_*` (sglang_timeseries.csv,
sglang_summary.json, sglang_percentiles_timeseries.json) and matches metrics by
normalized substring on the canonical `sglang_*` names. To support additional
backends (currently vLLM) without touching the large report layer, the
Prometheus collection boundary *translates* each backend's native metric names
into these canonical names before writing the canonical files.

This module owns:
  - SERVER_TYPES         : supported backend identifiers
  - detect_server_type() : pick a backend from the set of available metric names
  - VLLM_TO_CANONICAL    : vLLM metric base name -> canonical (sglang_) base name
  - canonical_for()      : translate a single metric name for a given backend
  - vllm_job_candidates(): Prometheus job names to prefer for vLLM target discovery

Keeping vLLM specifics here means the default (SGLang) path stays unchanged.
"""
from __future__ import annotations

SERVER_TYPES = ("sglang", "vllm")


def detect_server_type(available) -> str:
    """Infer the inference-server backend from available Prometheus metric names.

    `available` is any iterable of metric-name strings (e.g. from
    /api/v1/label/__name__/values). Returns one of SERVER_TYPES, defaulting to
    "sglang" when nothing matches so existing behaviour is preserved.
    """
    names = list(available or [])
    if any(str(m).startswith("sglang") for m in names):
        return "sglang"
    if any(str(m).startswith("vllm") for m in names):
        return "vllm"
    return "sglang"


# vLLM -> canonical (sglang_) base-name translation.
# Maps a vLLM metric *base* name to the canonical base name the report layer
# expects. Histogram bases are listed without the _sum/_count/_bucket suffix;
# the caller appends suffixes. Gauges/counters map 1:1 to a canonical column.
# vLLM emits metrics with a `vllm:` prefix; downstream name-resolution accepts
# both colon and underscore spellings, so we key on the colon form vLLM emits.
VLLM_TO_CANONICAL = {
    # Latency / token histograms (base names; suffixes appended by caller)
    "vllm:time_to_first_token_seconds":   "sglang_time_to_first_token_seconds",
    "vllm:time_per_output_token_seconds": "sglang_inter_token_latency_seconds",
    "vllm:e2e_request_latency_seconds":   "sglang_e2e_request_latency_seconds",
    "vllm:request_queue_time_seconds":    "sglang_queue_time_seconds",
    "vllm:request_prompt_tokens":         "sglang_prompt_tokens_histogram",
    "vllm:request_generation_tokens":     "sglang_generation_tokens_histogram",
    # Gauges
    "vllm:num_requests_running": "sglang_num_running_reqs",
    "vllm:num_requests_waiting": "sglang_num_queue_reqs",
    "vllm:gpu_cache_usage_perc": "sglang_token_usage",
    # Counters
    "vllm:prompt_tokens_total":     "sglang_prompt_tokens_total",
    "vllm:generation_tokens_total": "sglang_generation_tokens_total",
    # Prefix-cache hits drive the token-weighted cache-hit numerator. The
    # denominator is sglang_prompt_tokens_total (from prompt_tokens_total), so
    # the existing delta(cached)/delta(prompt) cache-hit math computes
    # prefix_hits / prompt_tokens. vllm:prefix_cache_queries_total is
    # intentionally NOT mapped: it would collide with prompt_tokens_total on the
    # same canonical column and corrupt the master timeseries merge.
    "vllm:prefix_cache_hits_total":    "sglang_cached_tokens_total",
    # KV preemptions are the closest proxy to SGLang's eviction pressure.
    "vllm:num_preemptions_total": "sglang_evicted_tokens_total",
}

# Histogram base names for percentile fetch (P50/P90/P99) for vLLM. Each entry
# mirrors the tuple shape in amoprof/percentiles.py HISTOGRAM_METRICS:
# (canonical_key, vllm_base, scale, unit, label).
VLLM_HISTOGRAM_METRICS = [
    ("ttft", "vllm:time_to_first_token_seconds",   1000.0, "ms",  "TTFT"),
    ("itl",  "vllm:time_per_output_token_seconds", 1000.0, "ms",  "ITL"),
    ("e2e",  "vllm:e2e_request_latency_seconds",   1000.0, "ms",  "E2E"),
    ("prompt_tokens", "vllm:request_prompt_tokens",     1.0, "tok", "Prompt tokens"),
    ("output_tokens", "vllm:request_generation_tokens", 1.0, "tok", "Output tokens"),
]


# vLLM histogram base names — fetched as _sum/_count counter pairs at
# collection time (and as _bucket for percentiles). Everything else in
# VLLM_TO_CANONICAL is a gauge or counter fetched directly.
VLLM_HISTOGRAM_BASES = (
    "vllm:time_to_first_token_seconds",
    "vllm:time_per_output_token_seconds",
    "vllm:e2e_request_latency_seconds",
    "vllm:request_queue_time_seconds",
    "vllm:request_prompt_tokens",
    "vllm:request_generation_tokens",
)


def canonical_for(server_type: str, metric: str) -> str:
    """Return the canonical (sglang_) name for a backend metric.

    For sglang (or anything not explicitly mapped) the name is returned
    unchanged. For vLLM histogram bases passed with a known suffix
    (_sum/_count/_bucket), the suffix is preserved on the canonical base.
    """
    if server_type != "vllm":
        return metric
    for suffix in ("_sum", "_count", "_bucket"):
        if metric.endswith(suffix):
            base = metric[: -len(suffix)]
            canon = VLLM_TO_CANONICAL.get(base)
            if canon:
                return canon + suffix
    return VLLM_TO_CANONICAL.get(metric, metric)


def vllm_job_candidates() -> list[str]:
    """Prometheus job names to prefer when discovering a vLLM target."""
    return ["vllm"]
