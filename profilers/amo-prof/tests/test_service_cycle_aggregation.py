import random

import pytest

from amoprof.report.amoprof import _aggregate_service_cycles, _cycle_agg_rule

WIN = (1000.0, 2000.0)


def _cycle(start, dur, scrapes, **vals):
    """Rows for one service cycle, published after it ends and re-scraped
    `scrapes` times (the gauge holds until the next cycle replaces it)."""
    snap = {"collection_start_time_seconds": start, "collection_duration_s": dur,
            "collection_end_time_seconds": start + dur, **vals}
    return [(start + dur + 15 * i, k, v) for i in range(scrapes) for k, v in snap.items()]


def _rows():
    return (
        _cycle(950, 30, 2, util_mean=99.0, energy_wh=9.0)        # midpoint 965: before window
        + _cycle(1100, 30, 3, util_mean=10.0, temp_peak_c=60, page_faults_total=5,
                 gpu_energy_wh=1.0, host_written_gb=2.0, nand_written_gb=4.0, waf=2.0,
                 ssd_media_errors=7, temp_start_c=40, temp_end_c=45, lat_p99=100.0,
                 total_system_energy_wh=1.0, power_efficiency_tok_per_wh=100.0)
        + _cycle(1500, 90, 1, util_mean=40.0, temp_peak_c=70, page_faults_total=7,
                 gpu_energy_wh=3.0, host_written_gb=2.0, nand_written_gb=2.0, waf=1.0,
                 ssd_media_errors=8, temp_start_c=46, temp_end_c=50, lat_p99=200.0,
                 total_system_energy_wh=3.0, power_efficiency_tok_per_wh=0.0)
        + _cycle(1990, 30, 1, util_mean=40.0)                     # midpoint 2005: after window
    )


def test_cycles_fold_with_per_key_semantics():
    out, meta = _aggregate_service_cycles(_rows(), *WIN)
    assert meta["_cycles"] == 2                     # re-scrapes count once; edges excluded
    assert out["util_mean"] == pytest.approx((10 * 30 + 40 * 90) / 120)   # duration-weighted
    assert out["temp_peak_c"] == 70
    assert out["page_faults_total"] == 12 and out["gpu_energy_wh"] == 4.0  # per-cycle sums
    assert out["collection_duration_s"] == 120
    assert out["ssd_media_errors"] == 8             # lifetime counter: last
    assert out["temp_start_c"] == 40 and out["temp_end_c"] == 50
    assert out["waf"] == pytest.approx(6.0 / 4.0)   # sum(nand)/sum(host), not mean of ratios
    assert out["power_efficiency_tok_per_wh"] == pytest.approx(100 * 1 / 4)  # sum(tok)/sum(Wh)
    assert meta["_approximate_keys"] == "lat_p99"
    assert "energy_wh" not in out                   # only seen in the excluded cycle


def test_result_independent_of_row_order():
    rows = _rows()
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    assert _aggregate_service_cycles(rows, *WIN) == _aggregate_service_cycles(shuffled, *WIN)


def test_cycle_published_after_window_end_is_included():
    # Starts at 1980, midpoint 1995 is inside; its only sample lands at 2010.
    out, meta = _aggregate_service_cycles(_cycle(1980, 30, 1, util_mean=5.0), *WIN)
    assert meta["_cycles"] == 1 and out["util_mean"] == 5.0


def test_without_cycle_ids_sums_are_omitted():
    rows = [(1100, "util_mean", 10.0), (1100, "page_faults_total", 5),
            (1200, "util_mean", 30.0), (1200, "page_faults_total", 5)]
    out, meta = _aggregate_service_cycles(rows, *WIN)
    assert out == {"util_mean": 20.0} and meta["_cycles"] == 0


def test_config_targets_take_last_value():
    rows = _cycle(1100, 30, 1, tp_size=4) + _cycle(1500, 30, 1, tp_size=8)
    out, _ = _aggregate_service_cycles(rows, *WIN, config=True)
    assert out["tp_size"] == 8


@pytest.mark.parametrize("key,rule", [
    ("hugepages_total", "mean"), ("dram_total_gb", "mean"), ("gpu_count", "mean"),
    ("hbm_used_gb_peak_all", "max"), ("vmstat_available", "max"),
    ("discard_total_bytes", "sum"), ("biosnoop_events", "sum"), ("dram_samples", "sum"),
    ("ssd_host_written_gb", "sum"), ("ssd_lifetime_tbw", "last"), ("nvme_inflight_p95", "pctl"),
    ("available_gb", "mean"),
])
def test_rule_table(key, rule):
    assert _cycle_agg_rule(key) == rule
