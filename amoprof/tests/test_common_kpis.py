
"""Formula regression tests for amoprof.report.common_kpis.

Run manually from the package root:
    python3 -m pytest amoprof/tests/test_common_kpis.py

These tests intentionally cover previous regressions:
  * cache hit must prefer vetted summary and not loose raw denominator matching
  * TTFT/TPOT/E2E mean must use selected-window Δsum/Δcount
  * p50 must use percentile timeseries when available
  * throughput mean/p50 must use active samples/counter fallback
"""
from __future__ import annotations

import json
from pathlib import Path

from amoprof.report.common_kpis import compute_common_kpis, _find_col


def _write(raw: Path, name: str, text: str) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    (raw / name).write_text(text, encoding="utf-8")


def test_common_kpis_formula_core(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    _write(raw, "sglang_timeseries.csv",
        "time_sec,sglang_time_to_first_token_seconds_sum,sglang_time_to_first_token_seconds_count,"
        "sglang_inter_token_latency_seconds_sum,sglang_inter_token_latency_seconds_count,"
        "sglang_e2e_request_latency_seconds_sum,sglang_e2e_request_latency_seconds_count,"
        "sglang_gen_throughput,sglang_generation_tokens_total,"
        "sglang_cached_tokens_total,sglang_prompt_tokens_total\\n"
        "0,0,0,0,0,0,0,0,0,0,0\\n"
        "10,20,2,0.4,2,40,2,10,0,100,1000\\n"
        "20,60,4,0.8,4,80,4,30,800,200,2000\\n"
    )
    _write(raw, "sglang_percentiles_timeseries.json", json.dumps({
        "ttft": {"p50": [14000, 15000]},
        "itl": {"p50": [15, 17]},
        "e2e": {"p50": [19000, 20000]},
    }))
    _write(raw, "sglang_summary.json", json.dumps({
        "cache_hit_token_weighted_pct": 61.27,
        "cache_hit_calc_method": "selected_window_token_weighted_cached_tokens_over_prompt_tokens",
    }))
    k = compute_common_kpis(raw)
    assert round(k["ttft_ms"], 3) == 15000.0
    assert round(k["tpot_ms"], 3) == 200.0
    assert round(k["e2e_ms"], 3) == 20000.0
    assert round(k["ttft_p50_ms"], 3) == 14500.0
    assert round(k["tpot_p50_ms"], 3) == 16.0
    assert round(k["e2e_p50_ms"], 3) == 19500.0
    assert round(k["throughput_mean"], 3) == 20.0
    assert round(k["throughput_p50"], 3) == 20.0
    assert round(k["cache_hit_pct"], 3) == 61.27


def test_cache_hit_prefers_vetted_summary_over_raw_counter_ratio(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    # Raw counters would produce 9.6%, but the vetted report value is 61.27%.
    _write(raw, "sglang_timeseries.csv",
        "time_sec,sglang_cached_tokens_total,sglang_prompt_tokens_total\\n"
        "0,0,0\\n"
        "10,96,1000\\n"
    )
    _write(raw, "sglang_summary.json", json.dumps({
        "cache_hit_token_weighted_pct": 61.27,
        "cache_hit_calc_method": "selected_window_token_weighted_cached_tokens_over_prompt_tokens",
    }))
    _write(raw, "sglang_percentiles_timeseries.json", "{}")
    assert round(compute_common_kpis(raw)["cache_hit_pct"], 3) == 61.27


def test_find_col_does_not_pick_helper_substring_columns() -> None:
    rows = [{
        "time_sec": "0",
        "debug_sglang_prompt_tokens_total_bad": "123",
        "sglang_prompt_tokens_total_helper": "456",
    }, {
        "time_sec": "10",
        "debug_sglang_prompt_tokens_total_bad": "124",
        "sglang_prompt_tokens_total_helper": "457",
    }]
    assert _find_col(rows, "sglang_prompt_tokens_total") == ""

    rows2 = [{
        "time_sec": "0",
        "prefix_sglang_prompt_tokens_total": "1",
    }]
    assert _find_col(rows2, "sglang_prompt_tokens_total") == "prefix_sglang_prompt_tokens_total"
