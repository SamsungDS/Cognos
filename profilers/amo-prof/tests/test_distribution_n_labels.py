"""Distribution charts say what their n counts, and explain TTFT vs E2E n."""
import validate_report as vr
from amoprof.report.combined import _amoprof_exec_svg_percentile_bars

COLORS = {"p50": "#38bdf8", "p90": "#f59e0b", "p99": "#ef4444"}


def _chart(title, n, label):
    return _amoprof_exec_svg_percentile_bars(
        f"{title} — p50 / p90 / p99", "", "ms",
        {"p50": 1.0, "p90": 2.0, "p99": 3.0, "observations": n}, COLORS, n_label=label)


def test_n_label_is_printed():
    svg = _chart("TTFT", 2774, "requests · first token in window")
    assert "n=2,774 requests · first token in window" in svg
    default = _amoprof_exec_svg_percentile_bars(
        "X — p50 / p90 / p99", "", "ms", {"p50": 1, "p90": 2, "p99": 3, "observations": 5}, COLORS)
    assert "n=5 observations" in default                 # other callers unchanged


def _report(ttft_n, done_ns, note=""):
    html = _chart("TTFT", ttft_n, "requests · first token in window")
    for title, n in zip(("E2E request latency", "Input tokens / request",
                         "Output tokens / request"), done_ns):
        html += _chart(title, n, "requests · completed in window")
    return html + note


def _failed(html, name):
    return any(name in f for f in vr.validate_html(html, "t").failures)


def test_completion_charts_must_agree():
    assert _failed(_report(2801, (2801, 2800, 2801)), "report the same n")
    assert not _failed(_report(2801, (2801, 2801, 2801)), "report the same n")


def test_ttft_difference_must_be_explained():
    unexplained = _report(2774, (2801, 2801, 2801))
    explained = unexplained + "<b>Why the n counts differ:</b> requests in flight"
    assert _failed(unexplained, "difference is explained")
    assert not _failed(explained, "difference is explained")


def test_bare_observations_label_is_flagged():
    html = _chart("TTFT", 10, "observations") + _chart("E2E request latency", 10, "observations")
    assert _failed(html, "n says what it counts")
