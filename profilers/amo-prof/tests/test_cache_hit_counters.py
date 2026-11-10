"""Cache-hit findings compare only what was measured, and name it correctly.

The headline is prefill_cache / (prefill_cache + prefill_compute).  The
"cached/prompt" diagnostic, cached_tokens_total / prompt_tokens_total, counts
a different token stream and exists only when SGLang exports both counters.
A run without prompt_tokens_total once got "per-request it's 78%, per-token
it's only 0%": both figures are per-token, and the 0 was "not exported".
"""
import csv
import pathlib
import re
import sys

from amoprof.report.combined import build_executive_summary_html
from amoprof.report.common_kpis import compute_cache_hit_kpis

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_l35_report_consistency import _mk, N  # noqa: E402

PREFILL_HIT = 68_036_418 / (68_036_418 + 10_500_000) * 100      # fixture: 86.6%


def _add_cached(raw, total):
    """Append a cumulative sglang_cached_tokens_total column rising to `total`."""
    p = raw / "sglang_timeseries.csv"
    rows = list(csv.reader(p.open()))
    rows[0].append("sglang_cached_tokens_total")
    for i, r in enumerate(rows[1:]):
        r.append(str(int(total * i / (N - 1))))
    with p.open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    return raw


def _exec(raw):
    html = build_executive_summary_html(raw.parent, run_label="t")
    return html, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_availability_needs_both_counters(tmp_path):
    no_prompt = compute_cache_hit_kpis(raw_dir=_mk(tmp_path / "a"))
    prompt_only = compute_cache_hit_kpis(raw_dir=_mk(tmp_path / "b", with_cumulative=True))
    both = compute_cache_hit_kpis(raw_dir=_add_cached(_mk(tmp_path / "c", with_cumulative=True), 30e6))
    assert not no_prompt["cache_hit_cached_prompt_available"]
    assert not prompt_only["cache_hit_cached_prompt_available"]
    assert both["cache_hit_cached_prompt_available"]


def test_unexported_diagnostic_is_not_a_gap(tmp_path):
    html, txt = _exec(_mk(tmp_path / "noprompt"))
    assert "CACHE HIT GAP" not in txt and "COUNTERS DISAGREE" not in txt
    assert "per-request" not in txt and "short cache hits" not in txt
    assert f"Cache hit is strong ({PREFILL_HIT:.1f}% of prefill tokens served from cache)" in txt
    assert "gauge-active" not in txt
    assert "cached/prompt not exported" in html


def test_counters_that_disagree_are_named_as_such(tmp_path):
    # 30M cached of 90M prompt = 33.3% against the 86.6% prefill headline.
    _html, txt = _exec(_add_cached(_mk(tmp_path / "both", with_cumulative=True), 30e6))
    i = txt.find("CACHE HIT · COUNTERS DISAGREE")
    assert i >= 0
    seg = txt[i:i + 1500]
    assert f"= {PREFILL_HIT:.1f}% (the headline)" in seg and "= 33.3%" in seg
    assert "not request sizes" in seg
    assert "per-request" not in txt and "short cache hits" not in txt


def test_agreeing_counters_raise_no_finding(tmp_path):
    _html, txt = _exec(_add_cached(_mk(tmp_path / "agree", with_cumulative=True), 78e6))
    assert "COUNTERS DISAGREE" not in txt
    assert "Cache hit is strong" in txt
