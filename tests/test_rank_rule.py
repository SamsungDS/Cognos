"""KV-movement token counters: ranks are combined by what the data shows.

Each rank exports its own series. Whether those count the SAME tokens or
DIFFERENT ones depends on the topology, and the rank label alone does not say:

  TP / PP / EP over TP   every rank holds a shard of every token and counts
                         all of them -- the Sep 8 TP=8 run read 3,512,089 on
                         all eight ranks; summing reported 8x.
  DP, DP-attention       each rank serves its own requests; the total is the
                         sum. With a dp_rank label the groups are summed as
                         label sets. A build that labels DP-attention ranks
                         tp_rank only must be summed too, and a fixed
                         "max over tp_rank" rule would undercount it.

So the ranks' window deltas are compared: within 1% they are replicas (max),
otherwise shards (sum). The same rule runs in the kernel (Executive, End
Report), the Prometheus fetch, and compare.
"""
import csv

import pandas as pd
import pytest

from amoprof.report.metric_kernels import (
    rank_combine_rule, summarise_rank_rules, window_counter_delta,
    window_counter_series)

N = 10  # samples


def _rows(series: dict) -> list:
    """{column: per-sample increment} -> CSV-like rows of cumulative values."""
    rows = []
    for i in range(N):
        r = {"time_sec": str(i * 15)}
        for col, step in series.items():
            r[col] = str(1000 + step * i)
        rows.append(r)
    return rows


def _col(**labels) -> str:
    return ("sglang_prefetched_tokens_total["
            + ",".join(f"{k}={v}" for k, v in labels.items()) + "]")


# ── the decision ──────────────────────────────────────────────────────────
def test_equal_ranks_are_replicas():
    r = rank_combine_rule([3_512_089.0] * 8)
    assert (r["rule"], r["ranks"]) == ("max", 8)


def test_a_missed_final_scrape_is_still_a_replica():
    assert rank_combine_rule([1000.0] * 7 + [995.0])["rule"] == "max"


def test_ranks_counting_different_requests_are_shards():
    r = rank_combine_rule([100.0, 137.0, 90.0, 120.0])
    assert r["rule"] == "sum" and "differed" in r["reason"]


def test_one_series_and_idle_ranks():
    assert rank_combine_rule([42.0])["rule"] == "single"
    assert rank_combine_rule([0.0, 0.0])["rule"] == "max"


# ── the topologies, through the kernel ────────────────────────────────────
def test_tp8_counts_tokens_once():
    rows = _rows({_col(tp_rank=i): 100 for i in range(8)})
    meta = {}
    assert window_counter_delta(rows, ["prefetched_tokens_total"], meta=meta) == 100 * (N - 1)
    assert meta["rules"][0]["rule"] == "max"


def test_pp_ranks_count_tokens_once():
    rows = _rows({_col(pp_rank=i, tp_rank=0): 50 for i in range(2)})
    assert window_counter_delta(rows, ["prefetched_tokens_total"]) == 50 * (N - 1)


def test_ep_over_tp_counts_tokens_once():
    # tp=4, ep=4: GPU i is one process carrying tp_rank=i and moe_ep_rank=i.
    rows = _rows({_col(moe_ep_rank=i, tp_rank=i): 70 for i in range(4)})
    assert window_counter_delta(rows, ["prefetched_tokens_total"]) == 70 * (N - 1)


def test_dp_groups_with_a_dp_label_are_summed():
    # tp=4 x dp=2: within a DP group the TP ranks agree, across groups not.
    cols = {}
    for dp, step in ((0, 100), (1, 60)):
        for tp in range(4):
            cols[_col(dp_rank=dp, tp_rank=tp)] = step
    rows = _rows(cols)
    meta = {}
    assert window_counter_delta(rows, ["prefetched_tokens_total"], meta=meta) == (100 + 60) * (N - 1)
    assert [r["rule"] for r in meta["rules"]] == ["max", "max"]


def test_dp_attention_labelled_tp_rank_only_is_summed():
    # Each rank serves its own requests but only carries tp_rank: the case a
    # fixed max-over-tp_rank rule would undercount by the DP size.
    steps = [100, 137, 90, 120]
    rows = _rows({_col(tp_rank=i): s for i, s in enumerate(steps)})
    meta = {}
    assert window_counter_delta(rows, ["prefetched_tokens_total"], meta=meta) == sum(steps) * (N - 1)
    assert meta["rules"][0]["rule"] == "sum"


def test_the_series_and_the_total_agree():
    rows = _rows({_col(tp_rank=i): 100 for i in range(8)})
    t, v = window_counter_series(rows, ["prefetched_tokens_total"])
    assert len(t) == len(v) == N and v[-1] - v[0] == 100 * (N - 1)


def test_the_report_states_the_rule():
    assert "counted once" in summarise_rank_rules([rank_combine_rule([5.0] * 8)])
    assert "summed" in summarise_rank_rules([rank_combine_rule([5.0, 9.0])])
    assert "no rank combination" in summarise_rank_rules([])


# ── the Prometheus fetch ──────────────────────────────────────────────────
def _prom_df(per_rank: dict, extra_labels: "dict | None" = None) -> pd.DataFrame:
    """query_range-shaped frame: time_sec, value, one column per label."""
    out = []
    for labels, step in per_rank.items():
        for i in range(N):
            row = {"time_sec": float(i * 15), "value": 1000.0 + step * i}
            row.update(dict(labels))
            row.update(extra_labels or {})
            out.append(row)
    return pd.DataFrame(out)


def test_fetch_writes_one_series_counted_once_for_tp():
    from amoprof.report.amoprof import _combine_rank_series
    df, rules = _combine_rank_series(
        _prom_df({(("tp_rank", str(i)),): 100 for i in range(8)},
                 {"instance": "gpu-node:30000"}))
    assert list(df.columns) == ["time_sec", "value"]
    assert df["value"].iloc[-1] - df["value"].iloc[0] == 100 * (N - 1)
    assert rules[0]["rule"] == "max"


def test_fetch_sums_dp_attention_ranks():
    from amoprof.report.amoprof import _combine_rank_series
    df, rules = _combine_rank_series(
        _prom_df({(("tp_rank", str(i)),): s for i, s in enumerate((100, 137, 90, 120))}))
    assert df["value"].iloc[-1] - df["value"].iloc[0] == (100 + 137 + 90 + 120) * (N - 1)
    assert rules[0]["rule"] == "sum"


def test_fetch_sums_dp_groups_and_dedups_their_tp_ranks():
    from amoprof.report.amoprof import _combine_rank_series
    per = {}
    for dp, step in ((0, 100), (1, 60)):
        for tp in range(4):
            per[(("dp_rank", str(dp)), ("tp_rank", str(tp)))] = step
    df, rules = _combine_rank_series(_prom_df(per))
    assert df["value"].iloc[-1] - df["value"].iloc[0] == 160 * (N - 1)
    assert [r["rule"] for r in rules] == ["max", "max"]
