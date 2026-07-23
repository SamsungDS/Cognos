"""End-to-end-ish test: collect_from_prometheus_api(server_type="vllm") must
fetch vllm:* metrics and write the canonical sglang_* schema the reports read.

The Prometheus HTTP layer is mocked by monkeypatching the bundled report
module's low-level helpers (_prom_list_metrics / _prom_query_range), so no
network or live server is required.
"""
from __future__ import annotations

import json
import pandas as pd
import pytest

from amoprof.prometheus_source import _load_bundled_report


# vLLM metric names → synthetic 2-point timeseries (monotonic counters).
# Histograms are exposed as _sum/_count; gauges/counters directly.
_VLLM_SERIES = {
    # TTFT histogram: sum grows 0→40 over 20s, count 0→4 → mean 10s = 10000ms
    "vllm:time_to_first_token_seconds_sum":   [(0.0, 0.0), (20.0, 40.0)],
    "vllm:time_to_first_token_seconds_count": [(0.0, 0.0), (20.0, 4.0)],
    # ITL: sum 0→0.8, count 0→4 → mean 0.2s = 200ms
    "vllm:time_per_output_token_seconds_sum":   [(0.0, 0.0), (20.0, 0.8)],
    "vllm:time_per_output_token_seconds_count": [(0.0, 0.0), (20.0, 4.0)],
    # E2E: sum 0→80, count 0→4 → mean 20s = 20000ms
    "vllm:e2e_request_latency_seconds_sum":   [(0.0, 0.0), (20.0, 80.0)],
    "vllm:e2e_request_latency_seconds_count": [(0.0, 0.0), (20.0, 4.0)],
    # Gauges
    "vllm:num_requests_running": [(0.0, 2.0), (20.0, 5.0)],
    "vllm:num_requests_waiting": [(0.0, 0.0), (20.0, 1.0)],
    "vllm:gpu_cache_usage_perc": [(0.0, 0.10), (20.0, 0.55)],
    # Counters
    "vllm:prompt_tokens_total":      [(0.0, 0.0), (20.0, 2000.0)],
    "vllm:generation_tokens_total":  [(0.0, 0.0), (20.0, 800.0)],
    "vllm:prefix_cache_hits_total":  [(0.0, 0.0), (20.0, 600.0)],
}


@pytest.fixture
def patched_report(monkeypatch):
    mod = _load_bundled_report()
    avail = set(_VLLM_SERIES.keys())

    def fake_list_metrics(base_url):
        return list(avail)

    def fake_query_range(base_url, metric, start, end, step=15, timeout=30.0):
        # metric may carry a label selector like name{job="vllm"}; strip it.
        name = metric.split("{", 1)[0]
        pts = _VLLM_SERIES.get(name)
        if not pts:
            return pd.DataFrame()
        rows = [{"time_sec": float(t) - 0.0, "value": float(v)} for t, v in pts]
        # collect_from_prometheus_api passes real start; emulate offset=0 simply.
        df = pd.DataFrame(
            [{"time_sec": float(t), "value": float(v)} for t, v in pts])
        return df

    def fake_discover_targets(base_url, hostname=""):
        return {"vllm": ["host:8000"]}

    monkeypatch.setattr(mod, "_prom_list_metrics", fake_list_metrics)
    monkeypatch.setattr(mod, "_prom_query_range", fake_query_range)
    monkeypatch.setattr(mod, "_prom_discover_targets", fake_discover_targets)
    return mod


def test_vllm_collect_writes_canonical_files(patched_report, tmp_path):
    out = tmp_path / "raw"
    data = patched_report.collect_from_prometheus_api(
        prom_base_url="http://host:9090",
        start_time=1000.0, end_time=1020.0, step_s=10,
        output_dir=out, server_type="vllm",
    )

    # Canonical files written
    ts_path = out / "sglang_timeseries.csv"
    sum_path = out / "sglang_summary.json"
    assert ts_path.exists(), "sglang_timeseries.csv must be written for vLLM"
    assert sum_path.exists(), "sglang_summary.json must be written for vLLM"

    # Timeseries columns use canonical sglang_ names, not vllm:
    cols = pd.read_csv(ts_path).columns.tolist()
    joined = ",".join(cols)
    assert "sglang_time_to_first_token_seconds_sum" in joined
    assert "sglang_num_running_reqs" in joined
    assert "vllm:" not in joined, f"raw vLLM names leaked into columns: {cols}"

    summary = json.loads(sum_path.read_text())
    assert summary["server_type"] == "vllm"
    # Latency means derived from canonical _sum/_count deltas
    assert round(summary["server_ttft_ms"]) == 10000
    assert round(summary["server_e2e_ms"]) == 20000
    # Cache-hit token-weighted: 600 prefix hits / 2000 prompt tokens = 30%
    assert round(summary["cache_hit_token_weighted_pct"]) == 30
