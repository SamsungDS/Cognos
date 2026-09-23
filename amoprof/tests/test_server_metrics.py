"""Unit tests for amoprof.server_metrics (vLLM backend translation layer)."""
from __future__ import annotations

from amoprof.server_metrics import (
    SERVER_TYPES,
    detect_server_type,
    canonical_for,
    VLLM_TO_CANONICAL,
    VLLM_HISTOGRAM_BASES,
)


def test_server_types_contains_both_backends():
    assert "sglang" in SERVER_TYPES
    assert "vllm" in SERVER_TYPES


def test_detect_sglang_only():
    assert detect_server_type(["sglang_gen_throughput", "DCGM_FI_DEV_GPU_UTIL"]) == "sglang"


def test_detect_vllm_only():
    assert detect_server_type(["vllm:num_requests_running", "node_disk_io_now"]) == "vllm"


def test_detect_prefers_sglang_when_both_present():
    # SGLang is checked first to preserve historical behaviour.
    assert detect_server_type(["vllm:foo", "sglang_bar"]) == "sglang"


def test_detect_empty_or_unknown_defaults_sglang():
    assert detect_server_type([]) == "sglang"
    assert detect_server_type(["DCGM_FI_DEV_GPU_UTIL"]) == "sglang"


def test_vllm_map_covers_core_metrics():
    expected = {
        "vllm:time_to_first_token_seconds": "sglang_time_to_first_token_seconds",
        "vllm:time_per_output_token_seconds": "sglang_inter_token_latency_seconds",
        "vllm:e2e_request_latency_seconds": "sglang_e2e_request_latency_seconds",
        "vllm:num_requests_running": "sglang_num_running_reqs",
        "vllm:num_requests_waiting": "sglang_num_queue_reqs",
        "vllm:gpu_cache_usage_perc": "sglang_token_usage",
        "vllm:prompt_tokens_total": "sglang_prompt_tokens_total",
        "vllm:generation_tokens_total": "sglang_generation_tokens_total",
        "vllm:prefix_cache_hits_total": "sglang_cached_tokens_total",
    }
    for src, canon in expected.items():
        assert VLLM_TO_CANONICAL[src] == canon


def test_no_canonical_collision_on_master_columns():
    # Each canonical target must be unique so the timeseries pivot/merge cannot
    # produce duplicate columns. prefix_cache_queries_total is intentionally
    # unmapped to avoid colliding with prompt_tokens_total.
    canon_values = list(VLLM_TO_CANONICAL.values())
    assert len(canon_values) == len(set(canon_values)), (
        f"duplicate canonical targets: {canon_values}")
    assert "vllm:prefix_cache_queries_total" not in VLLM_TO_CANONICAL


def test_canonical_for_sglang_is_passthrough():
    assert canonical_for("sglang", "sglang_gen_throughput") == "sglang_gen_throughput"
    assert canonical_for("auto", "vllm:num_requests_running") == "vllm:num_requests_running"


def test_canonical_for_vllm_gauge():
    assert canonical_for("vllm", "vllm:num_requests_running") == "sglang_num_running_reqs"


def test_canonical_for_vllm_histogram_suffix_preserved():
    base = "vllm:time_to_first_token_seconds"
    assert canonical_for("vllm", base + "_sum") == "sglang_time_to_first_token_seconds_sum"
    assert canonical_for("vllm", base + "_count") == "sglang_time_to_first_token_seconds_count"
    assert canonical_for("vllm", base + "_bucket") == "sglang_time_to_first_token_seconds_bucket"


def test_histogram_bases_are_all_mapped():
    for base in VLLM_HISTOGRAM_BASES:
        assert base in VLLM_TO_CANONICAL
