"""vLLM percentile fetch must use vllm:* histogram bases but emit the same
canonical output keys (server_ttft_p99_ms, ttft/itl/e2e blocks) as SGLang.

The Prometheus HTTP layer is mocked via amoprof.percentiles._http_get_json.
"""
from __future__ import annotations

import amoprof.percentiles as pc


def _range_resp(value):
    return {"status": "success",
            "data": {"result": [{"metric": {},
                                 "values": [[1000, str(value)], [1030, str(value)]]}]}}


def _instant_resp(value):
    return {"status": "success",
            "data": {"result": [{"metric": {}, "value": [1030, str(value)]}]}}


def _make_fake_http(server_type_metrics):
    available = set(server_type_metrics)

    def fake_http_get_json(url, params, timeout=30.0):
        if url.endswith("/api/v1/label/__name__/values"):
            return {"status": "success", "data": list(available)}
        query = params.get("query", "")
        # Only answer for vLLM bases; otherwise empty so test proves vLLM path.
        if "vllm:time_to_first_token_seconds" in query:
            return _range_resp(2.0) if "/query_range" in url else _instant_resp(2.0)
        if "vllm:" in query and "/query" in url:
            return _range_resp(1.0) if "/query_range" in url else _instant_resp(1.0)
        return {"status": "success", "data": {"result": []}}

    return fake_http_get_json


def test_vllm_percentile_summary_emits_canonical_keys(monkeypatch):
    metrics = ["vllm:time_to_first_token_seconds_bucket",
               "vllm:e2e_request_latency_seconds_bucket"]
    monkeypatch.setattr(pc, "_http_get_json", _make_fake_http(metrics))
    out = pc.fetch_percentile_summary(
        "http://host:9090", 1000.0, 1030.0, server_type="vllm")
    # TTFT base returns 2.0s → 2000ms across percentiles
    assert out.get("server_ttft_p99_ms") == 2000.0
    assert out.get("server_ttft_p50_ms") == 2000.0
    # Output keys must be the canonical server_<m>_p<pct>_ms shape
    assert any(k.startswith("server_ttft_p") for k in out)


def test_vllm_percentile_timeseries_emits_canonical_blocks(monkeypatch):
    metrics = ["vllm:time_to_first_token_seconds_bucket"]
    monkeypatch.setattr(pc, "_http_get_json", _make_fake_http(metrics))
    ts = pc.fetch_percentile_timeseries(
        "http://host:9090", 1000.0, 1030.0, step_s=30, server_type="vllm")
    assert "ttft" in ts
    block = ts["ttft"]
    assert block["unit"] == "ms"
    assert block["p99"] and all(v == 2000.0 for v in block["p99"])
    # metric_base records the vLLM source it actually queried
    assert block["metric_base"].startswith("vllm:")


def test_sglang_default_unchanged(monkeypatch):
    # With no server_type, SGLang bases are used (regression guard).
    metrics = ["sglang_time_to_first_token_seconds_bucket"]

    def fake(url, params, timeout=30.0):
        if url.endswith("/api/v1/label/__name__/values"):
            return {"status": "success", "data": list(metrics)}
        query = params.get("query", "")
        if "sglang_time_to_first_token_seconds" in query:
            return _instant_resp(3.0)
        return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(pc, "_http_get_json", fake)
    out = pc.fetch_percentile_summary("http://host:9090", 1000.0, 1030.0)
    assert out.get("server_ttft_p99_ms") == 3000.0
