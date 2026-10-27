"""Executive latency values print like the KPI tiles: 6730 ms, not 6,730.22."""
import re

from amoprof.report.combined import (
    _amoprof_exec_svg_percentile_bars, _amoprof_exec_svg_tier_occupancy, _fmt_latency)

COLORS = {"p50": "#38bdf8", "p90": "#f59e0b", "p99": "#ef4444"}


def test_fmt_latency_matches_tiles():
    assert _fmt_latency(6730.22, "ms") == "6730"
    assert _fmt_latency(78736.6, "ms") == "78737"
    assert _fmt_latency(133.41, "ms/tok") == "133.4"
    assert _fmt_latency(7400.0, "ms", " ms") == "7400 ms"


def test_latency_bars_have_no_thousands_separator_or_decimals():
    svg = _amoprof_exec_svg_percentile_bars(
        "TTFT — p50 / p90 / p99", "", "ms",
        {"p50": 6730.22, "p90": 36122.17, "p99": 76267.74}, COLORS)
    assert "TTFT p50: 6730 ms" in svg            # hover
    assert ">6730<" in svg and ">76268<" in svg  # bar labels
    assert not re.search(r"\d,\d{3}", svg)       # axis ticks too


def test_token_bars_keep_their_format():
    svg = _amoprof_exec_svg_percentile_bars(
        "Input tokens / request — p50 / p90 / p99", "", "tokens",
        {"p50": 1234.0, "p90": 5678.0, "p99": 9012.0}, COLORS)
    assert "1,234.00 tokens" in svg              # only latency changed


def test_over_the_run_legend_and_hover():
    series = [{"tier": "L1", "label": "p50", "t": [0, 60, 120], "v": [7400.0, 52857.14, 9000.0],
               "cap": 6730.22, "color": "#38bdf8", "cap_label": "run p50 6730 ms (dashed)"}]
    svg = _amoprof_exec_svg_tier_occupancy(series, window=(0, 120), mode="abs",
                                           title="TTFT percentiles over the run",
                                           yaxis="ms", unit_label="ms")
    assert "peak 52857 ms" in svg
    assert "7400 ms" in svg and "e+03" not in svg
