"""GPU util headline = mean over every sample, not the busy-only mean."""
import csv

import validate_report as vr
from amoprof.report.enhancer import _gpu_tooltip_stats_from_timeseries


def _gpu_csv(tmp_path, utils):
    with open(tmp_path / "gpu_timeseries.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_sec", "gpu_idx", "gpu_util", "mem_used", "power"])
        for i, u in enumerate(utils):
            w.writerow([i, 0, u, 1000, 100])
    return tmp_path


def test_tooltip_mean_counts_idle_samples(tmp_path):
    # Busy at 99% for 2 of 10 samples, idle otherwise: the mean is ~20%, not 99%.
    raw = _gpu_csv(tmp_path, [99, 99, 0, 0, 0, 0, 0, 0, 0, 0])
    s = _gpu_tooltip_stats_from_timeseries(raw, {})
    assert s["gpu_util_mean"] == 19.8
    assert s["gpu_util_busy_mean"] == 99.0


def test_tooltip_prefers_the_tiles_decomposition(tmp_path):
    raw = _gpu_csv(tmp_path, [99, 0])
    s = _gpu_tooltip_stats_from_timeseries(
        raw, {"gpu_util_overall_mean": 19.3, "gpu_util_active_mean": 99.4})
    assert s["gpu_util_mean"] == 19.3 and s["gpu_util_busy_mean"] == 99.4


def _tile(value, note):
    return (f'<div class="kpi-label">GPU util</div><div class="kpi-value">{value}</div>'
            f'<div class="kpi-note">{note}</div>')


def test_validator_flags_busy_only_headline():
    note = "overall 19.3% · busy 99.4% when active (>0%) · idle 80.5% of samples"
    bad = vr.validate_html(_tile("99.4%", note) * 4, "bad")
    good = vr.validate_html(_tile("19.3%", note) * 4, "good")
    assert any("GPU util' headline is the overall mean" in f for f in bad.failures)
    assert not any("GPU util' headline is the overall mean" in f for f in good.failures)
