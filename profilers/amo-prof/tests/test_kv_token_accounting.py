"""KV token accounting from SGLang counters: rank-aware window deltas (TP/PP/EP
ranks count the same tokens once; other label sets are summed) and
Token_Reuse_Density, reused prompt tokens per GB of KV generated."""
import csv

import pytest

from amoprof.report.combined import _kv_token_delta


def _write(tmp_path, cols, first, last):
    p = tmp_path / "sglang_timeseries.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_sec"] + cols)
        w.writerow([0] + first)
        w.writerow([60] + last)
    return tmp_path


def test_tp_ranks_count_the_same_tokens_once(tmp_path):
    # Eight TP ranks each report the same backed-up tokens (Sep 8 run: 31.1M on
    # every rank).  The total is one rank's count, not eight times it.
    cols = [f"sglang_backuped_tokens_total[job=sglang,tp_rank={r}]" for r in range(8)]
    raw = _write(tmp_path, cols, [0] * 8, [1000, 1002, 1000, 1001, 1000, 1003, 1000, 1000])
    assert _kv_token_delta(raw, ["backuped_tokens_total"]) == 1003


def test_dp_ranks_and_other_labels_are_summed(tmp_path):
    # Data-parallel ranks and is_streaming label sets are different requests.
    cols = ["sglang_prompt_tokens_total[is_streaming=true,tp_rank=0,dp_rank=0]",
            "sglang_prompt_tokens_total[is_streaming=true,tp_rank=1,dp_rank=0]",
            "sglang_prompt_tokens_total[is_streaming=true,tp_rank=0,dp_rank=1]",
            "sglang_prompt_tokens_total[is_streaming=false,tp_rank=0,dp_rank=0]"]
    raw = _write(tmp_path, cols, [0, 0, 0, 0], [500, 500, 300, 40])
    assert _kv_token_delta(raw, ["prompt_tokens_total"]) == 500 + 300 + 40


def test_token_reuse_density_per_gb_of_kv_generated():
    from amoprof.report.metric_kernels import token_reuse_density
    # Sep 8 run: 22.66M reused, 32.67M computed prompt + 48K output, 560 KB/token.
    r = token_reuse_density(22_659_071, 32_666_534, 48_252, 560)
    assert r["kv_generated_gb"] == pytest.approx(18_760, rel=1e-3)
    assert r["density"] == pytest.approx(1_208, rel=1e-3)
    assert r["good_fit"]
    assert not token_reuse_density(10, 0, 0, 560)["available"]


def test_phase_analysis_shows_token_reuse_density():
    from amoprof.report.amoprof import Metrics, _token_reuse_density_html
    m = Metrics()
    m.reuse_reused_tokens, m.reuse_computed_tokens, m.reuse_output_tokens = 22_659_071, 32_666_534, 48_252
    m.kv_bytes_per_token_kb, m.reuse_kv_generated_gb, m.token_reuse_density = 560, 18_760.0, 1_207.9
    html = _token_reuse_density_html(m)
    assert "Token_Reuse_Density" in html and ">1,208<" in html and "good fit" in html
    assert "unavailable" in _token_reuse_density_html(Metrics())
