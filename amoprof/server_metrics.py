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


# ─── Mooncake (L3.5 disaggregated KV store) ──────────────────────────────────
#
# Mooncake is a disaggregated KV cache backend (Moonshot's mooncake-store /
# mooncake-transfer-engine).  When present, its Prometheus exporter fills the
# L3.5 role in AMOprof's memory hierarchy: read/write traffic tracked here is
# real backing-tier byte movement between the inference runtime and the
# disaggregated store.
#
# The report layer already reads canonical logical-L3.5 signals off
# sglang_prefetched_tokens_total (read/onboard) and sglang_backuped_tokens_total
# (write/offload).  We reuse those canonical columns rather than introducing
# a parallel schema, so all existing L3.5 charts / reconciliation code lights
# up without new chart functions.  Mooncake exposes bytes rather than tokens,
# so the translation is "prefer mooncake bytes when present; only use SGLang
# token counters when mooncake is absent".
#
# Mooncake-native mooncake_store_capacity_bytes / mooncake_store_used_bytes are
# stored under new canonical fields so the L3.5 capacity KPI tile can prefer
# the mooncake-reported value over configured/inferred defaults.
MOONCAKE_TO_CANONICAL = {
    # Transfer engine — byte counters.  Mooncake tracks read/write direction
    # separately; write = KV block offloaded from runtime to store, read =
    # loaded back from store to runtime.
    # The master exporter has no transfer-engine byte counters, but it does
    # publish cumulative byte totals that yield the same quantities:
    #
    #   READ  — bytes SERVED to clients on a cache hit, split by where the hit
    #           landed.  Summing the two gives total read bytes out of the
    #           store, and its delta over an interval is read bandwidth.
    #   WRITE — master_value_size_bytes_sum is the cumulative size of values
    #           PUT into the store (a histogram _sum), so its delta over an
    #           interval is write bandwidth.  _count is the number of puts.
    #
    # These are not the transfer engine's own counters, so they measure
    # logical bytes in/out of the store rather than wire bytes; RDMA framing
    # and any replication overhead are not included.
    "file_cache_hit_bytes_total":             "mooncake_read_bytes_file_total",
    "mem_cache_hit_bytes_total":              "mooncake_read_bytes_mem_total",
    "master_value_size_bytes_sum":            "mooncake_write_bytes_total",
    "master_promotion_completed_bytes_total": "mooncake_promoted_bytes_total",
    "master_evicted_size_bytes":              "mooncake_evicted_bytes",
    "segment_allocated_bytes":                "mooncake_segment_used_bytes",
    "segment_total_capacity_bytes":           "mooncake_segment_capacity_bytes",
    "mooncake_transfer_read_bytes_total":     "mooncake_read_bytes_total",
    "mooncake_transfer_written_bytes_total":  "mooncake_write_bytes_total",
    # Some exporter versions collapse read+write into a single counter with a
    # `direction` label.  We fetch both aliases; whichever exists wins.
    "mooncake_bytes_read_total":              "mooncake_read_bytes_total",
    "mooncake_bytes_written_total":           "mooncake_write_bytes_total",
    "mooncake_read_bytes_total":              "mooncake_read_bytes_total",
    "mooncake_written_bytes_total":           "mooncake_write_bytes_total",
    # Store capacity — fill L3.5 tier size KPI.
    "mooncake_store_capacity_bytes":          "mooncake_capacity_bytes",
    "mooncake_store_used_bytes":              "mooncake_used_bytes",
    "mooncake_store_fill_ratio":              "mooncake_fill_ratio",
    "mooncake_capacity_bytes":                "mooncake_capacity_bytes",
    "mooncake_used_bytes":                    "mooncake_used_bytes",
    # Topology / replica count.  Not charted; surfaced in setup panel + as a
    # gauge Prometheus can graph independently.
    "mooncake_replica_count":                 "mooncake_replica_count",
    "mooncake_node_count":                    "mooncake_node_count",
    "mooncake_store_nodes":                   "mooncake_node_count",
    # Request-level counters (optional; some exporters emit these).
    "mooncake_get_requests_total":            "mooncake_get_requests_total",
    "mooncake_put_requests_total":            "mooncake_put_requests_total",
    "mooncake_get_errors_total":              "mooncake_get_errors_total",
    "mooncake_put_errors_total":              "mooncake_put_errors_total",
}


# Mooncake histogram bases — Q→C style latency of the transfer engine.
# Feed L3.5 latency percentiles (P50/P90/P99) via the same histogram_quantile
# machinery percentiles.py already runs against SGLang / vLLM.
# The Mooncake *master* exporter publishes unprefixed names (no `mooncake_`
# namespace).  These are metadata-service metrics: capacity, occupancy, key
# counts and request rates.  Note there are no byte-throughput counters here —
# data movement happens client<->store over RDMA and is not visible to the
# master — so L3.5 bandwidth cannot be measured from this exporter and is not
# fabricated from it.
MOONCAKE_MASTER_TO_CANONICAL: dict[str, str] = {
    "master_allocated_bytes":            "mooncake_used_bytes",
    "master_total_capacity_bytes":       "mooncake_capacity_bytes",
    "segment_allocated_bytes":           "mooncake_segment_used_bytes",
    "segment_total_capacity_bytes":      "mooncake_segment_capacity_bytes",
    "master_allocated_file_size_bytes":  "mooncake_file_used_bytes",
    "master_total_file_capacity_bytes":  "mooncake_file_capacity_bytes",
    # Memory vs storage kept apart.  Mooncake accounts them separately —
    # mem_cache_hit_bytes_total beside file_cache_hit_bytes_total proves the
    # store knows which tier served a hit — so conflating their capacities
    # into one "L3.5 used" figure reports a percentage of the wrong total.
    "master_allocated_bytes":            "mooncake_mem_used_bytes",
    "master_allocated_file_size_bytes":  "mooncake_file_used_bytes",
    "master_key_count":                  "mooncake_key_count",
    "master_soft_pin_key_count":         "mooncake_soft_pin_key_count",
    "master_active_clients":             "mooncake_active_clients",
    "master_put_end_requests_total":     "mooncake_put_requests_total",
    "master_put_start_requests_total":   "mooncake_put_start_requests_total",
    "master_put_end_failures_total":     "mooncake_put_errors_total",
    # A replica-list request is a metadata lookup on the master ("where is
    # this key?"), not a data read — it can fire with no bytes moved.  It was
    # aliased to get_requests and presented as L3.5 read activity.  Kept under
    # its own name so it is not mistaken for data movement.
    "master_get_replica_list_requests_total": "mooncake_replica_lookups_total",
    "master_get_replica_list_failures_total": "mooncake_get_errors_total",
    "master_exist_key_requests_total":   "mooncake_exist_requests_total",
}

MOONCAKE_MASTER_HISTOGRAM_BASES = ("master_value_size_bytes",)

MOONCAKE_HISTOGRAM_BASES = (
    "mooncake_transfer_duration_seconds",
    "mooncake_get_duration_seconds",
    "mooncake_put_duration_seconds",
)


# Percentile-histogram spec for percentiles.py (canonical, base, scale, unit,
# label).  Emits keys `l3_5_transfer_p50_ms` etc. so they can coexist with the
# SGLang/vLLM request-level percentile keys already written to
# sglang_percentiles_timeseries.json.
MOONCAKE_HISTOGRAM_METRICS = [
    ("l3_5_transfer", "mooncake_transfer_duration_seconds", 1000.0, "ms",
     "L3.5 transfer duration"),
    ("l3_5_get",      "mooncake_get_duration_seconds",      1000.0, "ms",
     "L3.5 get duration"),
    ("l3_5_put",      "mooncake_put_duration_seconds",      1000.0, "ms",
     "L3.5 put duration"),
]


def mooncake_job_candidates() -> list[str]:
    """Prometheus job names to prefer when discovering a Mooncake target."""
    return ["mooncake", "mooncake_store", "mooncake_master"]
