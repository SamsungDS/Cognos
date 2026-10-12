#!/usr/bin/env python3
"""`compare` compares queueing at every layer, and says where there is none.

Run: python3 tests/test_compare_queue_depth.py

The comparison carried exactly two queue rows, both in the A2 table, both fed
by one field that read the first of avgqu_sz / l35_avgqu_sz / bt_qd_mean to
return anything. Three consequences, each pinned below:

* A local-SSD run and an L3.5 run were compared on one row whose two cells
  measured different devices on different hosts, with nothing saying so.
* The inference scheduler's queue -- the only plain count of waiting work in
  the stack, and the one that decides whether a run was admission-bound --
  was not compared at all.
* Network and DRAM were absent. Leaving them out is right, because neither
  exposes a queue depth; saying nothing about why is not.

Fixtures are written to a temp dir, so this needs no Prometheus. It does need
pandas only if the comparator does; the extraction path under test reads CSVs
with the module's own helpers.
"""
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from amoprof.comparator import (  # noqa: E402
    RunSpec, build_queue_depth_html, extract_metrics,
    _QD_PLAUSIBLE_MAX,
)

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _write(path: pathlib.Path, header: str, rows: "list[tuple]") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n"
                    + "\n".join(",".join(str(c) for c in r) for r in rows)
                    + "\n")


def _mk_local(raw: pathlib.Path) -> None:
    """A run whose L3 is a LOCAL SSD: device queue on this host."""
    _write(raw / "sglang_timeseries.csv",
           "time_sec,num_queue_reqs,num_running_reqs",
           [(0, 0, 4), (15, 12, 48), (30, 31, 64), (45, 5, 40)])
    _write(raw / "nvme_driver_timeseries.csv",
           "time_sec,avgqu_sz,qd_peak,rd_bw_mbs,wr_bw_mbs",
           [(0, 0.0, 0, 10, 20), (15, 0.8, 7, 300, 410),
            (30, 1.6, 12, 520, 690), (45, 0.2, 3, 40, 60)])
    _write(raw / "network_timeseries.csv",
           "time_sec,tcp_retrans_ps,rx_drop_ps,link_util_pct",
           [(0, 0, 0, 1.0), (15, 0.5, 0, 22.0),
            (30, 2.5, 1.0, 61.0), (45, 0, 0, 4.0)])


def _mk_dram(raw: pathlib.Path, peak_gbs: "float | None") -> None:
    """DRAM bandwidth, and optionally the PLATFORM peak in setup details.

    dram_peak_bw_gbs in RunMetrics is the run's own observed maximum, so
    mean / that is a burstiness ratio, not pressure. The share-of-peak proxy
    is computed only against a platform peak from setup details, and left
    absent when there is none.
    """
    _write(raw / "amduprof_pcm_timeseries.csv",
           "time_sec,dram_total_gb_s,dram_read_gb_s,dram_write_gb_s",
           [(0, 40.0, 25.0, 15.0), (15, 120.0, 80.0, 40.0),
            (30, 200.0, 130.0, 70.0), (45, 60.0, 40.0, 20.0)])
    if peak_gbs is not None:
        import json
        (raw / "setup_details.json").write_text(
            json.dumps({"DRAM peak GB/s": peak_gbs}))


def _mk_l35(raw: pathlib.Path) -> None:
    """A run whose L3.5 is a MEMORY NODE: device queue on that node."""
    _write(raw / "sglang_timeseries.csv",
           "time_sec,num_queue_reqs,num_running_reqs",
           [(0, 0, 8), (15, 2, 96), (30, 6, 128), (45, 1, 88)])
    _write(raw / "l35_storage_timeseries.csv",
           "time_sec,l35_avgqu_sz,l35_qd_peak,l35_rd_bw_mbs,l35_wr_bw_mbs",
           [(0, 0.0, 0, 15, 25), (15, 3.4, 44, 900, 1200),
            (30, 5.1, 82, 1400, 1800), (45, 0.5, 9, 120, 160)])
    _write(raw / "network_timeseries.csv",
           "time_sec,tcp_retrans_ps,rx_drop_ps,link_util_pct",
           [(0, 0, 0, 3.0), (15, 18.0, 4.0, 74.0),
            (30, 41.0, 11.0, 93.0), (45, 2.0, 0, 12.0)])


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_qd_"))
    try:
        _mk_local(tmp / "local" / "raw")
        _mk_l35(tmp / "l35" / "raw")
        # Both runs measure DRAM; only one has a platform peak configured.
        _mk_dram(tmp / "local" / "raw", 409.6)
        _mk_dram(tmp / "l35" / "raw", None)
        a = extract_metrics(RunSpec(label="L3 local SSD",
                                    raw_dir=tmp / "local" / "raw"))
        b = extract_metrics(RunSpec(label="L3.5 memory node",
                                    raw_dir=tmp / "l35" / "raw"))

        print("\nThe two devices are no longer one row")
        # mean from avgqu_sz (the time-weighted integral, 0.65), peak from
        # qd_peak (max_over_time of the in-flight gauge, 12) -- two columns,
        # because the peak of an average is not a peak.
        _check("the local run's device queue is on this host",
               (round(a.l3_qd_mean, 3), a.l3_qd_peak), (0.65, 12.0))
        _check("and it reports nothing for the memory node",
               a.l35_qd_mean, None)
        _check("the L3.5 run's device queue is on the memory node",
               (round(b.l35_qd_mean, 3), b.l35_qd_peak), (2.25, 82.0))
        _check("and it reports nothing for this host", b.l3_qd_mean, None)
        _check("so the two runs are never compared on one device row",
               (a.l3_qd_mean is not None and a.l35_qd_mean is None
                and b.l3_qd_mean is None and b.l35_qd_mean is not None), True)
        print("\nAnd each cell can be traced to a column in a file")
        # When the mean and the peak come from different columns, BOTH are
        # named: a pair drawn from two sources must not read as one
        # measurement.
        _check("the local source names the column behind each half",
               a.l3_qd_src,
               "avgqu_sz in nvme_driver_timeseries.csv (mean), "
               "qd_peak in nvme_driver_timeseries.csv (peak)")
        _check("the L3.5 source names its own",
               b.l35_qd_src,
               "l35_avgqu_sz in l35_storage_timeseries.csv (mean), "
               "l35_qd_peak in l35_storage_timeseries.csv (peak)")

        print("\nThe scheduler's queue is compared, which it never was")
        _check("waiting requests, local run",
               (a.sg_queue_reqs_mean, a.sg_queue_reqs_peak), (12.0, 31.0))
        _check("waiting requests, L3.5 run",
               (b.sg_queue_reqs_mean, b.sg_queue_reqs_peak), (2.25, 6.0))
        _check("decode batch, local run",
               (a.sg_running_reqs_mean, a.sg_running_reqs_peak), (39.0, 64.0))
        _check("decode batch, L3.5 run",
               (b.sg_running_reqs_mean, b.sg_running_reqs_peak), (80.0, 128.0))
        # This is the finding such a comparison exists to surface: the L3.5
        # run holds a 2x larger batch while queueing 5x fewer requests, so it
        # was not admission-bound where the local run was.
        _check("the L3.5 run queues far less work at a larger batch",
               (b.sg_queue_reqs_peak < a.sg_queue_reqs_peak
                and b.sg_running_reqs_peak > a.sg_running_reqs_peak), True)

        print("\nNetwork and DRAM are proxies, and are carried as proxies")
        _check("retransmits are read, local run",
               round(a.net_retrans_ps_mean, 3), 0.75)
        _check("retransmits are read, L3.5 run",
               round(b.net_retrans_ps_mean, 3), 15.25)
        _check("link utilisation is read", round(b.net_link_util_pct_mean, 2),
               45.5)
        # mean of 40/120/200/60 = 105 GB/s against a configured 409.6 peak.
        _check("DRAM share-of-peak uses the CONFIGURED platform peak",
               round(a.dram_bw_pct_of_peak, 2), round(105 / 409.6 * 100, 2))
        _check("and names the denominator it used", a.dram_peak_ref_gbs, 409.6)
        _check("the run's own observed maximum is NOT the denominator",
               round(a.dram_bw_pct_of_peak, 1) == round(105 / 200 * 100, 1),
               False)
        _check("a run with no configured peak gets no share-of-peak",
               b.dram_bw_pct_of_peak, None)
        _check("even though its bandwidth was measured",
               b.dram_total_bw_gbs > 0, True)

        print("\nThe rendered section keeps the distinction visible")
        html = build_queue_depth_html([a, b])
        _check("the section renders", bool(html), True)
        _check("this host's device has its own heading",
               "this host&#x27;s block device" in html
               or "this host's block device" in html, True)
        _check("the memory node's device has its own heading",
               "the memory node&#x27;s block device" in html
               or "the memory node's block device" in html, True)
        _check("the scheduler layer is present",
               "inference scheduler" in html, True)
        _check("every proxy row is labelled a proxy",
               html.count(">proxy</span>"), 5)
        _check("and the measured queues are labelled as measured",
               html.count(">measured queue</span>") >= 8, True)
        _check("the reason each proxy exists is given, not just the label",
               "no NIC queue is exposed" in html
               and "no memory-controller queue is exposed" in html, True)
        _check("the sources are named per run",
               "avgqu_sz in nvme_driver_timeseries.csv" in html
               and "l35_avgqu_sz in l35_storage_timeseries.csv" in html, True)
        _check("and the peak's own column is named beside the mean's",
               "qd_peak in nvme_driver_timeseries.csv (peak)" in html, True)
        _check("and the section says why one row for both hosts is wrong",
               "different devices on different hosts" in html, True)

        print("\nA lookalike column is never summed into a depth")
        from amoprof.comparator import _read_csv_col_all, _read_csv_col_exact
        mix = tmp / "mix" / "raw"
        _write(mix / "nvme_driver_timeseries.csv",
               "time_sec,avgqu_sz,qd_peak,bt_qd_mean,bt_qd_peak",
               [(0, 0.0, 0, 0.0, 0), (15, 0.8, 7, 1.1, 9),
                (30, 1.6, 12, 2.4, 18), (45, 0.2, 3, 0.3, 4)])
        _f = mix / "nvme_driver_timeseries.csv"
        _check("the substring reader sums qd_peak with bt_qd_peak",
               max(_read_csv_col_all(_f, "qd_peak")), 30.0)
        _check("which is a depth neither source measured",
               30.0 in (12.0, 18.0), False)
        _check("the exact reader returns only qd_peak",
               max(_read_csv_col_exact(_f, "qd_peak")), 12.0)
        _check("and only bt_qd_peak for the other",
               max(_read_csv_col_exact(_f, "bt_qd_peak")), 18.0)
        _check("an absent column is absent, not approximated",
               _read_csv_col_exact(_f, "l35_qd_peak"), [])
        d = extract_metrics(RunSpec(label="mix", raw_dir=mix))
        _check("so the extracted device peak is the device's own",
               d.l3_qd_peak, 12.0)
        _check("and blktrace keeps its own", d.bt_qd_peak, 18.0)

        print("\nAn implausible depth is refused, not compared")
        bad = tmp / "bad" / "raw"
        _write(bad / "nvme_driver_timeseries.csv",
               "time_sec,avgqu_sz",
               [(0, 6876.316), (15, 171982.370)])
        c = extract_metrics(RunSpec(label="bad", raw_dir=bad))
        _check("the artifact series is rejected", c.l3_qd_mean, None)
        _check("so the A2 row has nothing rather than something impossible",
               c.nvme_qd_mean, None)
        _check("the bound matches the single-run report's", _QD_PLAUSIBLE_MAX,
               4096.0)

        print("\nThe A2 table's single pair still resolves, and by precedence")
        _check("a local run's A2 pair comes from this host",
               (a.nvme_qd_mean, a.nvme_qd_peak), (a.l3_qd_mean, a.l3_qd_peak))
        _check("an L3.5 run's comes from the memory node",
               (b.nvme_qd_mean, b.nvme_qd_peak),
               (b.l35_qd_mean, b.l35_qd_peak))

        print("\nA single run cannot be compared with itself")
        _check("one run renders no section", build_queue_depth_html([a]), "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad_names = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad_names)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad_names)}" if bad_names else ""))
    return 1 if bad_names else 0


if __name__ == "__main__":
    sys.exit(main())
