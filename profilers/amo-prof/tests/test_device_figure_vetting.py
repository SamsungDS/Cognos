#!/usr/bin/env python3
"""Two headline figures a v1.69.0 report published, and why neither could be.

Run: python3 tests/test_device_figure_vetting.py

    L3 SSD storage queue depth   1,401.09 mean / 3,430 peak
    L3 SSD storage BW (device)   145 rd / 28,672 wr MB/s peak

Everything else in the same report contradicted both:

  * the device's own avgqu-sz peaked at 25.97 over the same window;
  * the report's own Little's Law line read "3,461 IOPS x 0.265 ms = 0.92
    expected depth" -- and then printed "(agrees, so the shallow queue is
    real)" next to the 1,401;
  * blktrace latency was "0.00 ms read / 0.00 ms write", so the trace captured
    no completion dwell -- and QD(t) = count(Q) - count(C) can only rise when
    the C events are missing;
  * p50 1,385 against a mean of 1,401 is a counter climbing, not a queue
    draining;
  * 28,672 MB/s is 28 GiB/s through one namespace, on a drive whose mean write
    bandwidth over the window was 9.3 MB/s.

Both then became hardware requirements: "Queue Depth peak 3,430 - SSD must
sustain observed peak concurrency" and "Sequential Write BW 28672 MB/s x 1.3 =
37274 MB/s". That is the part that matters: a report that merely shows a wrong
number wastes an afternoon, while one that specs a drive from it spends money.

The vetting lives in metric_kernels so the tile and the requirement table
cannot reach different conclusions about one figure.
"""
import html as _H
import json
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_RESULTS = []

# Every number below is from that report.
QD_MEAN, QD_P50, QD_P99, QD_PEAK = 1401.09, 1385.0, 3387.0, 3430.0
QD_IOPS, QD_LAT_MS, QD_EXPECTED = 3461.0, 0.265, 0.92
DEV_QD_PEAK = 25.9696
WR_BW_PEAK, WR_BW_MEAN = 28672.0, 9.3
HOST_GB, LOGICAL_GB, BK_TOK = 3.0, 15948.4, 27_811_800


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    from amoprof.report.metric_kernels import (
        NVME_MAX_BW_MBS, QD_PLAUSIBLE_MAX,
        vet_device_bw_peak as _vbw, vet_queue_depth as _vqd)

    print("\nThe arithmetic that condemns the queue depth")
    _check("Little's Law puts the depth at 0.92",
           round(QD_IOPS * QD_LAT_MS / 1000.0, 2), QD_EXPECTED)
    _check("so a mean of 1,401 would need 405 ms per I/O",
           round(QD_MEAN / QD_IOPS * 1000.0), 405)
    _check("which is 1,528x the measured 0.265 ms",
           round(QD_MEAN / QD_IOPS * 1000.0 / QD_LAT_MS), 1528)
    _check("the reported mean is 1,523x the expected depth",
           round(QD_MEAN / QD_EXPECTED), 1523)
    _check("and 54x the device's own peak",
           round(QD_MEAN / DEV_QD_PEAK), 54)
    # p50 ~= mean is the signature of a monotonically rising count.
    _check("p50 sits within 2% of the mean, as a rising counter does",
           round(abs(QD_P50 - QD_MEAN) / QD_MEAN * 100, 1) < 2.0, True)
    _check("it is under the old plausibility bound, which is why it passed",
           QD_PEAK < QD_PLAUSIBLE_MAX, True)

    print("\nThe kernel rejects it, on the report's own numbers")
    r = _vqd(event_mean=QD_MEAN, event_peak=QD_PEAK, event_lat_ms=0.0,
             event_iops=QD_IOPS, device_mean=0.36, device_peak=DEV_QD_PEAK)
    _check("rejected", r["rejected"], True)
    _check("and it falls back to the device gauge", r["source"],
           "device gauge")
    _check("reporting 25.97 peak", round(r["peak"], 4), DEV_QD_PEAK)
    _check("naming the missing completions",
           any("no Q→C completion latency" in x for x in r["reasons"]),
           True)
    _check("and the gauge that contradicts it",
           any("kernel's own gauge peaked" in x for x in r["reasons"]), True)

    print("\nEach ground stands on its own")
    # Little's Law alone, with latency present.
    r2 = _vqd(event_mean=QD_MEAN, event_peak=QD_PEAK, event_lat_ms=QD_LAT_MS,
              event_iops=QD_IOPS)
    _check("Little's Law alone rejects it", r2["rejected"], True)
    _check("naming the 405 ms it would require",
           any("405" in x for x in r2["reasons"]), True)
    _check("with no gauge to fall back to, nothing is published",
           (r2["peak"], r2["source"]), (0.0, "none"))
    # The plausibility bound alone.
    r3 = _vqd(event_mean=9000.0, event_peak=12000.0, event_lat_ms=1.0,
              event_iops=1000.0)
    _check("the plausible bound alone rejects it", r3["rejected"], True)
    # The gauge alone.
    r4 = _vqd(event_mean=400.0, event_peak=900.0, device_peak=20.0,
              device_mean=2.0)
    _check("an independent gauge far below it rejects it", r4["rejected"],
           True)

    print("\nAnd a real queue is left alone")
    for _nm, _kw in (
            ("a shallow queue",
             dict(event_mean=0.36, event_peak=1.0, event_lat_ms=0.265,
                  event_iops=3461.0, device_mean=0.3, device_peak=1.0)),
            ("a busy queue",
             dict(event_mean=18.0, event_peak=32.0, event_lat_ms=5.0,
                  event_iops=3600.0, device_mean=2.0, device_peak=16.0)),
            ("a deep but consistent queue",
             dict(event_mean=256.0, event_peak=512.0, event_lat_ms=71.0,
                  event_iops=3600.0, device_mean=30.0, device_peak=300.0))):
        _r = _vqd(**_kw)
        _check(f"{_nm} is kept", _r["rejected"], False)
        _check(f"{_nm} keeps the exact source", _r["source"],
               "blktrace Q→C")
    # Slack matters: a 0.9 mean against an expected 0.3 is 3x and must pass.
    _check("3x over a sub-unit expectation is not rejected",
           _vqd(event_mean=0.9, event_peak=4.0, event_lat_ms=0.26,
                event_iops=1200.0)["rejected"], False)
    _check("nor is an absent event figure",
           _vqd(device_mean=0.4, device_peak=2.0)["source"], "device gauge")
    _check("and an empty input rejects nothing",
           _vqd()["rejected"], False)

    print("\nThe bandwidth peak is not reachable through the link")
    _check("28,672 MB/s is 28.0 GB/s", round(WR_BW_PEAK / 1024.0, 1), 28.0)
    _check("against a ~16 GB/s PCIe 5.0 x4 ceiling",
           round(NVME_MAX_BW_MBS / 1024.0), 16)
    _check("and 3,083x the window's mean",
           round(WR_BW_PEAK / WR_BW_MEAN), 3083)
    w = _vbw(WR_BW_PEAK, WR_BW_MEAN)
    _check("so the kernel rejects it", w["rejected"], True)
    _check("publishing nothing in its place", w["mbs"], 0.0)
    _check("and saying it is a counter reset, not a burst",
           "not a burst" in w["reason"], True)
    _check("a plausible peak passes", _vbw(1080.0, 9.3)["rejected"], False)
    _check("keeping its value", _vbw(1080.0, 9.3)["mbs"], 1080.0)
    _check("a zero peak is not an error",
           _vbw(0.0, 0.0)["rejected"], False)
    _check("and a peak at the ceiling is allowed",
           _vbw(NVME_MAX_BW_MBS, 100.0)["rejected"], False)

    print("\nThe report applies both, and says why")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_vet_"))
    try:
        sys.path.insert(0, str(_ROOT / "tests"))
        from test_tier_residency_tiles import _make_run, _tiles
        from amoprof.report.combined import build_executive_summary_html as _b

        def _mk(_dir, *, qd_mean, qd_peak, qd_lat, dev_qd, wr_peak):
            _raw = _make_run(_dir)
            _n = 20
            _raw.joinpath("nvme_driver_timeseries.csv").write_text(
                "time_sec,rd_bw_mbs,wr_bw_mbs,rd_iops,wr_iops,avgqu_sz,"
                "util_pct\n"
                + "\n".join(
                    f"{_i*60.0},59.0,{wr_peak if _i == 7 else WR_BW_MEAN},"
                    f"900,1200,{dev_qd if _i == 9 else dev_qd * 0.02},62.0"
                    for _i in range(_n)) + "\n")
            _bt = _raw / "blktrace_analysis"
            _bt.mkdir(exist_ok=True)
            _bt.joinpath("queue_depth_summary.json").write_text(json.dumps({
                "qd_mean": qd_mean, "qd_max": qd_peak,
                "qd_p50": qd_mean * 0.99, "qd_p99": qd_peak * 0.99,
                "qd_source": "blktrace_q_to_c",
                "qd_mean_lat_ms": qd_lat,
                "qd_iops_from_q_events": QD_IOPS,
                "qd_expected_littles_law": (QD_IOPS * qd_lat / 1000.0
                                            if qd_lat else None),
                # Empty, exactly as in the report that claimed agreement.
                "qd_consistency": "", "qd_order_inversions": 0}))
            return _raw

        _bad = _tiles(_b(_mk(tmp / "bad", qd_mean=QD_MEAN, qd_peak=QD_PEAK,
                             qd_lat=0.0, dev_qd=DEV_QD_PEAK,
                             wr_peak=WR_BW_PEAK), run_label="bad"))
        _qd_k = [k for k in _bad if "storage queue depth" in k][0]
        _bw_k = [k for k in _bad if "storage BW (device)" in k][0]
        _check("the queue-depth headline is no longer the event figure",
               "1,401" in _bad[_qd_k][0], False)
        _check("it is the device gauge", _bad[_qd_k][0],
               "1.79 mean / 25.97 peak")
        _check("and the note names the figure it dropped",
               "1,401.09 mean / 3,430 peak) is not reported here"
               in _bad[_qd_k][1], True)
        _check("with the reason",
               "no Q→C completion latency" in _bad[_qd_k][1], True)
        _check("the bandwidth headline drops the impossible sample",
               "28,672" in _bad[_bw_k][0], False)
        _check("reporting the largest physically possible one",
               _bad[_bw_k][0], "59 rd / 9 wr MB/s peak")
        _check("and stating the discrepancy against the plausible mean",
               "3,083x this window's mean" in _bad[_bw_k][1], True)

        _ok = _tiles(_b(_mk(tmp / "ok", qd_mean=0.36, qd_peak=1.0,
                            qd_lat=QD_LAT_MS, dev_qd=0.9, wr_peak=1080.0),
                        run_label="ok"))
        _qd_k2 = [k for k in _ok if "storage queue depth" in k][0]
        _bw_k2 = [k for k in _ok if "storage BW (device)" in k][0]
        _check("a healthy run keeps its blktrace figure",
               _ok[_qd_k2][0], "0.36 mean / 1 peak")
        _check("and its real bandwidth peak",
               _ok[_bw_k2][0], "59 rd / 1,080 wr MB/s peak")
        _check("no rejection note appears on it",
               "is not reported here" in _ok[_qd_k2][1], False)
        _check("nor a dropped-sample note",
               "physically possible samples" in _ok[_bw_k2][1], False)

        print("\nThe cross-check verdict refers to the figure above it")
        _check("the healthy run's verdict says so",
               "agrees with the figure above" in _ok[_qd_k2][1], True)
        # The report's own wording was "(agrees, so the shallow queue is
        # real)" printed beside 1,401 -- a verdict about 0.92.
        _check("the old unconditional wording is gone",
               "agrees, so the shallow queue is real"
               in (_ROOT / "amoprof" / "report" / "combined.py").read_text(),
               False)
        # An empty qd_consistency fell to the else and claimed agreement.
        # A figure that disagrees cannot reach a footnote any more: the
        # agreement bound and the rejection bound are the same, so anything
        # that would have been labelled "disagrees" is rejected upstream and
        # the tile shows the device gauge instead. That makes a third
        # "disagrees" branch dead code, and it is not there.
        _disagree = _tiles(_b(_mk(tmp / "dis", qd_mean=40.0, qd_peak=64.0,
                                  qd_lat=QD_LAT_MS, dev_qd=55.0,
                                  wr_peak=1080.0), run_label="dis"))
        _qd_k3 = [k for k in _disagree if "storage queue depth" in k][0]
        _check("a mean of 40 against an expected 0.92 is rejected, not noted",
               _disagree[_qd_k3][0], "3.80 mean / 55.00 peak")
        _check("with Little's Law named as the ground",
               "Little's Law puts the depth at" in _disagree[_qd_k3][1], True)
        _check("and no 'disagrees' footnote exists to reach",
               "does NOT agree with"
               in (_ROOT / "amoprof" / "report" / "combined.py").read_text(),
               False)
        _check("the bound is shared, so agreement and rejection cannot gap",
               [_vqd(event_mean=9.1, event_peak=10.0, event_lat_ms=QD_LAT_MS,
                     event_iops=QD_IOPS)["rejected"],
                _vqd(event_mean=9.3, event_peak=10.0, event_lat_ms=QD_LAT_MS,
                     event_iops=QD_IOPS)["rejected"]],
               [False, True])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nNo requirement is specified from a rejected figure")
    a = (_ROOT / "amoprof" / "report" / "amoprof.py").read_text()
    _check("the table vets the bandwidth peaks",
           "_rd_v = _vet_bw(rd_bw_peak" in a
           and "_wr_v = _vet_bw(wr_bw_peak" in a, True)
    # The vetted values must replace the raw ones. Calling the kernel and
    # then specifying from the originals passes a probe for the call.
    # amoprof.py imports matplotlib, absent from this interpreter, so this
    # is asserted on the source rather than by rendering.
    _check("and specifies from the vetted values, not the raw ones",
           'rd_bw_peak, wr_bw_peak = _rd_v["mbs"], _wr_v["mbs"]' in a, True)
    # Assert that the SYMBOL is shared, not how the import is spelled. The
    # first version of this pinned "vet_device_bw_peak as _vet_bw", an inline
    # package-absolute import that broke script mode; moving it into the
    # module-level guard then failed this test, which had been holding the
    # bug in place.
    _check("through the same kernel as the tiles",
           "vet_device_bw_peak as _k_vet_bw" in a, True)
    _check("imported once, through the module-level guard",
           a.count("vet_device_bw_peak as _k_vet_bw"), 2)   # absolute + flat
    _check("and not re-imported inline at the call site",
           "from amoprof.report.metric_kernels import (\n        vet_device_bw_peak"
           in a, False)
    _check("and vets the queue depth",
           "_qd_v = _vet_qd(" in a, True)
    _check("zeroing it when rejected", "qd_peak, qd_p99 = 0, 0.0" in a, True)
    _check("the BW rows state why there is no requirement",
           a.count('f"No requirement stated: ') >= 3, True)
    _check("and are flagged, not shown as a quiet dash",
           "warn=bool(_wr_bw_why)" in a and "warn=bool(_qd_why)" in a, True)
    # The two figures the table actually printed.
    _check("28672 x 1.3 = 37274 was the write-BW requirement",
           round(WR_BW_PEAK * 1.3), 37274)
    _check("and 3,430 was the queue-depth requirement", int(QD_PEAK), 3430)

    print("\nAn amplification ratio that rounds to zero is not published")
    _check("3.0 GB over 15,948.4 GB rounds to 0.00",
           f"{HOST_GB / LOGICAL_GB:,.2f}", "0.00")
    _check("the two inputs are 5,316x apart",
           round(LOGICAL_GB / HOST_GB), 5316)
    c = (_ROOT / "amoprof" / "report" / "combined.py").read_text()
    _check("so the tile is gated on a publishable ratio",
           "if _amp >= 0.005:" in c, True)
    _check("and otherwise reports it unreconciled",
           '"unreconciled",' in c, True)
    _check("naming the gap", "apart. "
           in c and "cannot be below 1 unless" in c, True)
    _check("and the three things that would explain it",
           c.count("covers a different device") == 1
           and "overstates" in c, True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
