"""Token counters split by label are read whole on every surface.

SGLang exports prompt_tokens_total and generation_tokens_total once per
is_streaming value.  The Executive tile read the first column only -- the
is_streaming=false series, which never moved -- so it reported both counters
as "not exported" and took decode from realtime_tokens_total{mode=decode}:
49,566 against the End Report's 156,119.  In that window generation_tokens
_total rose 156,481 = 8,774 requests' first tokens + 147,637 inter-token
intervals, so it is the output-token count.
"""
import csv
import pathlib
import re
import sys

from amoprof.report.combined import build_executive_summary_html
from amoprof.report.common_kpis import compute_cache_hit_kpis

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_l35_report_consistency import _mk, DECODE  # noqa: E402

PROMPT = 90_000_000                     # fixture's prompt_tokens_total rise


def _split_by_streaming(raw):
    """Rewrite prompt/generation counters as is_streaming=false (flat, first)
    and is_streaming=true (carrying the counts), as SGLang exports them."""
    p = raw / "sglang_timeseries.csv"
    rows = list(csv.reader(p.open()))
    hdr = rows[0]
    out_hdr, plan = [], []
    for i, c in enumerate(hdr):
        if c in ("sglang_prompt_tokens_total", "sglang_generation_tokens_total"):
            out_hdr += [f"{c}[is_streaming=false]", f"{c}[is_streaming=true]"]
            plan.append((i, True))
        else:
            out_hdr.append(c)
            plan.append((i, False))
    # realtime decode reads ~1/3 of output tokens, as on the ticket's run, so
    # a fallback to it shows up as a different number.
    rt = hdr.index("sglang_realtime_tokens_total[mode=decode]")
    out = [out_hdr]
    for r in rows[1:]:
        r[rt] = str(int(r[rt]) // 3)
        new = []
        for i, split in plan:
            new += (["7", r[i]] if split else [r[i]])     # flat 7 = never moved
        out.append(new)
    with p.open("w", newline="") as f:
        csv.writer(f).writerows(out)
    return raw


def _tile_text(raw):
    html = build_executive_summary_html(raw.parent, run_label="t")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_executive_tile_reads_every_label_set(tmp_path):
    txt = _tile_text(_split_by_streaming(_mk(tmp_path / "split", with_cumulative=True)))
    assert f"+ {DECODE:,} decode =" in txt
    assert "generation_tokens_total is not exported" not in txt
    assert "sglang_prompt_tokens_total is not exported" not in txt


def test_split_counters_match_unsplit(tmp_path):
    whole = _tile_text(_mk(tmp_path / "whole", with_cumulative=True))
    split = _tile_text(_split_by_streaming(_mk(tmp_path / "split", with_cumulative=True)))
    pat = r"\(([\d,]+) prompt − ([\d,]+) cached\) \+ ([\d,]+) decode"
    assert re.search(pat, whole).groups() == re.search(pat, split).groups()


def test_cache_kpis_read_the_whole_prompt_counter(tmp_path):
    raw = _split_by_streaming(_mk(tmp_path / "split", with_cumulative=True))
    k = compute_cache_hit_kpis(raw_dir=raw)
    assert k["cache_hit_token_weighted_denominator_tokens"] == PROMPT


def test_realtime_decode_is_only_a_labelled_fallback(tmp_path):
    # No generation_tokens_total at all: decode comes from the realtime
    # counter, and the note says it is a lower bound.
    txt = _tile_text(_mk(tmp_path / "rt"))
    assert "decode from Δrealtime_tokens_total{mode=decode}" in txt
    assert "lower bound" in txt


def test_kernel_keeps_a_numeric_zero_first_sample():
    # Rows from a DataFrame carry floats; a counter starting at 0.0 once lost
    # that sample and read as not exported (vLLM fetch: cached 600 / 2,000).
    from amoprof.report.metric_kernels import window_counter_delta
    rows = [{"time_sec": 0.0, "sglang_prompt_tokens_total": 0.0},
            {"time_sec": 20.0, "sglang_prompt_tokens_total": 2000.0}]
    assert window_counter_delta(rows, ["prompt_tokens_total"]) == 2000.0
    assert window_counter_delta(rows, ["cached_tokens_total"]) is None
