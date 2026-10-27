"""TTFT percentile charts and p50 KPIs across report tabs."""
import csv
import json

import pytest

from amoprof.report.combined import (
    _amoprof_bucket_series, _amoprof_histogram_window_percentiles)
from amoprof.report.common_kpis import _window_quantile_ms, compute_common_kpis
from amoprof.report.metric_kernels import percentiles_from_bucket_deltas

BASE = "sglang_time_to_first_token_seconds_bucket"
LES = ["1", "10", "100", "+Inf"]


def _col(le, streaming):
    return f"{BASE}[is_streaming={streaming},job=sglang,le={le}]"


def _write_csv(path, rows):
    """rows: list of (time_sec, {(le, streaming): cumulative count or None})."""
    cols = [_col(le, s) for s in ("false", "true") for le in LES]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_sec"] + cols)
        for t, counts in rows:
            w.writerow([t] + ["" if counts.get(c) is None else counts[c] for c in cols])


def _counts(nonstream, stream):
    out = {_col(le, "false"): v for le, v in zip(LES, nonstream)}
    out.update({_col(le, "true"): v for le, v in zip(LES, stream)})
    return out


@pytest.fixture
def two_label_sets(tmp_path):
    # Non-streaming: 10 fast (<=1 s) requests.  Streaming: 10 slow (10-100 s),
    # and its series is missing on the first row (appears mid-window).
    p = tmp_path / "sglang_timeseries.csv"
    _write_csv(p, [
        (0, _counts([0, 0, 0, 0], [None] * 4)),
        (15, _counts([0, 0, 0, 0], [0, 0, 0, 0])),
        (30, _counts([10, 10, 10, 10], [0, 0, 10, 10])),
    ])
    return p


def test_bucket_series_sums_label_sets_per_le(two_label_sets):
    times, series = _amoprof_bucket_series(two_label_sets, "time_to_first_token_seconds")
    assert times == [0, 15, 30]
    assert [le for le, _ in series] == [1.0, 10.0, 100.0, float("inf")]   # each le once
    assert dict(series)[100.0] == [0, 0, 20]       # 10 + 10; leading gap back-filled


def test_interval_quantiles_interpolate_instead_of_snapping_to_edges(two_label_sets):
    _, series = _amoprof_bucket_series(two_label_sets, "time_to_first_token_seconds")
    out = percentiles_from_bucket_deltas(series)
    p50, p90 = out[0.5][-1], out[0.9][-1]
    # 20 completions: 10 in (0,1], 10 in (10,100].  p50 = target 10 -> 1 s
    # (top of the fast bucket); p90 = target 18 -> 10 + 90 * 8/10 = 82 s.
    assert p50 == pytest.approx(1.0)
    assert p90 == pytest.approx(82.0)


def test_window_percentiles_count_both_label_sets(two_label_sets):
    pw = _amoprof_histogram_window_percentiles(
        two_label_sets, "time_to_first_token_seconds", (0.5, 0.9), 1000.0)
    assert pw["observations"] == 20
    assert pw["p90"] == pytest.approx(82000.0)


def test_window_quantile_ms_matches_prometheus_semantics(two_label_sets):
    with open(two_label_sets, newline="") as f:
        rows = list(csv.DictReader(f))
    assert _window_quantile_ms(rows, "time_to_first_token_seconds", 0.9) == pytest.approx(82000.0)
    # A quantile in the +Inf bucket reports the highest finite le (100 s).
    rows[-1][_col("+Inf", "true")] = "1000"
    assert _window_quantile_ms(rows, "time_to_first_token_seconds", 0.99) == pytest.approx(100000.0)


def test_common_kpi_p50_is_whole_window_not_mean_of_rolling_p50(tmp_path, two_label_sets):
    raw = tmp_path
    (raw / "sglang_summary.json").write_text(json.dumps({"server_ttft_p50_ms": 6730.22}))
    (raw / "sglang_percentiles_timeseries.json").write_text(json.dumps(
        {"ttft": {"p50": [10000.0, 17572.0]}}))      # mean 13,786
    assert compute_common_kpis(raw)["ttft_p50_ms"] == pytest.approx(6730.22)

    # Without the Prometheus summary value, fall back to the window's buckets.
    (raw / "sglang_summary.json").write_text(json.dumps({}))
    assert compute_common_kpis(raw)["ttft_p50_ms"] == pytest.approx(1000.0)
