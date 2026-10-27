"""End Report chart post-processing applied in fig_to_b64 to every chart image:
legends moved off the plot area, time axes spanning the whole analysed window,
and L3/L3.5 tier wording inside the image matching the report text."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from amoprof.report.amoprof import _legends_outside, _span_full_window  # noqa: E402


def test_legend_inside_plot_moves_outside():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="DRAM Read")
    ax.legend(loc="upper right")
    _legends_outside(fig)
    leg = ax.get_legend()
    assert leg is not None and [t.get_text() for t in leg.get_texts()] == ["DRAM Read"]
    fig.canvas.draw()
    assert leg.get_window_extent().x0 >= ax.get_window_extent().x1   # right of the axes
    plt.close(fig)


def test_twin_axes_get_one_merged_legend():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax.plot([0, 1], [0, 1], label="GPU util")
    ax2.plot([0, 1], [1, 0], label="Power")
    ax.legend(loc="upper left")
    ax2.legend(loc="upper right")
    _legends_outside(fig)
    legends = [a.get_legend() for a in (ax, ax2) if a.get_legend() is not None]
    assert len(legends) == 1
    assert [t.get_text() for t in legends[0].get_texts()] == ["GPU util", "Power"]
    plt.close(fig)


def test_legend_does_not_land_on_the_neighbouring_subplot():
    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4))
    left.bar([0, 1], [1, 2], label="Prompt tokens")
    left.bar([0, 1], [0.5, 1], label="Output tokens")
    left.legend(loc="upper right")
    right.plot([0, 1], [0, 1])
    _legends_outside(fig)
    fig.canvas.draw()
    leg = left.get_legend()
    box = leg.get_window_extent()
    assert not box.overlaps(left.get_window_extent())                    # outside its plot
    assert not box.overlaps(right.get_window_extent())                   # not on the neighbour
    plt.close(fig)


def test_twin_axis_legend_clears_its_ticks_and_neighbour_without_crushing_plot():
    # KV footprint layout: middle plot with a right-hand twin axis, plots on
    # both sides.  The legend once sat on the twin's tick labels and the plot
    # was narrowed until its bar labels collided.
    fig, (a, mid, b) = plt.subplots(1, 3, figsize=(17, 5))
    mid.bar(["FP16", "BF16", "FP8", "INT8", "INT4"], [560, 560, 280, 280, 140])
    twin = mid.twinx()
    twin.plot(range(5), [38, 38, 76, 76, 153], label="Max context (K tok)")
    twin.set_ylabel("Max context tokens (K)")
    twin.legend(loc="upper right")
    width_before = mid.get_position().width
    _legends_outside(fig)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    leg = next(x.get_legend() for x in (mid, twin) if x.get_legend() is not None)
    box = leg.get_window_extent(r)
    twin_deco = twin.get_tightbbox(r, bbox_extra_artists=[])
    assert not box.overlaps(b.get_window_extent())                       # not on neighbour
    beside = box.x0 >= twin_deco.x1 - 1                                  # clear of twin ticks
    below = box.y1 <= twin_deco.y0 + 1
    assert beside or below
    assert mid.get_position().width >= width_before * 0.60 - 1e-9        # plot not crushed
    plt.close(fig)


def test_figure_text_follows_resolved_tier():
    from amoprof.report import amoprof as ap
    fig, ax = plt.subplots()
    fig.suptitle("KV$ L3 (local storage) — Read Workload Characteristics (§C)")
    ax.set_title("L3 local SSD fill")
    ap._CHART_TIER["backend_class"] = "remote_mooncake"
    try:
        ap._relabel_figure_tiers(fig)
    finally:
        ap._CHART_TIER["backend_class"] = ""
    assert fig._suptitle.get_text().startswith("KV$ L3.5 (AI Memory Node / remote storage)")
    assert "L3.5" in ax.get_title() and "L3.5.5" not in ax.get_title()
    plt.close(fig)


def test_time_axis_spans_the_whole_window():
    # 105-minute run, collector with 8 s of samples: axis must still be 0-105 min.
    fig, ax = plt.subplots()
    ax.plot([0.0, 0.14], [1, 2])
    ax.set_xlabel("Time (min)")
    fig._amoprof_wallclock = {"t0_epoch": 0.0, "dur_s": 6300.0, "unit": "min"}
    _span_full_window(fig)
    assert ax.get_xlim() == pytest.approx((0.0, 105.0))
    plt.close(fig)


def test_non_time_axes_are_untouched():
    fig, ax = plt.subplots()
    ax.bar(["p50", "p99"], [1, 2])
    ax.set_xlabel("Percentile")
    before = ax.get_xlim()
    fig._amoprof_wallclock = {"t0_epoch": 0.0, "dur_s": 6300.0, "unit": "min"}
    _span_full_window(fig)
    assert ax.get_xlim() == before
    plt.close(fig)
