"""End Report header tiles keep their formula collapsed after the KPI rewrite.

The shared KPIs are written into the End Report's header tiles by a regex
rewrite.  It replaced each tile's collapsed formula with a plain div, so the
rewritten tiles (TTFT, TPOT, throughput) printed their formula in full while
the tiles it left alone showed only the "formula" pill.
"""
import re

from amoprof.report.amoprof import kv_card
from amoprof.report.common_kpis import _replace_kpi_value_by_label


def _visible_notes(html):
    """Note divs printed outside a <details> disclosure."""
    return [n for n in re.findall(
        r'<div style="font-size:10px;color:#64748b;margin-top:2px">(.*?)</div>\s*</div>',
        html, re.S) if not n.lstrip().startswith("<details")]


def test_rewritten_tile_keeps_the_formula_collapsed():
    tile = kv_card("TTFT mean", "426", "ms", sub="old formula")
    assert '<details class="fx">' in tile
    out = _replace_kpi_value_by_label(tile, ["TTFT mean"], "ttft_ms", 11669.0, {"ttft_ms": 11669.0})
    assert "11669" in out
    assert out.count('<details class="fx">') == 1
    assert "time_to_first_token" in out                 # the formula is still there
    assert not _visible_notes(out)


def test_every_rewritten_tile_matches_its_untouched_neighbour():
    tiles = "".join(kv_card(lbl, "1", "ms", sub="f") for lbl in (
        "TTFT mean", "TTFT p50", "TPOT / ITL mean", "Input throughput"))
    out = tiles
    for key, lbl, v in (("ttft_ms", "TTFT mean", 11669.0), ("ttft_p50_ms", "TTFT p50", 3915.0),
                        ("tpot_ms", "TPOT / ITL mean", 555.6)):
        out = _replace_kpi_value_by_label(out, [lbl], key, v, {key: v})
    assert out.count('<details class="fx">') == 4       # one per tile, none expanded
    assert not _visible_notes(out)
    assert out.count("kpi-") == tiles.count("kpi-")     # no tile swallowed its neighbour
    assert out.count('min-width:120px') == 4
