#!/usr/bin/env python3
"""The GPU node's own device bytes reach the report, from the right host.

Run: python3 tests/test_device_bytes_collection.py

An L3 run on msl-ssg-dgx1 had device IOPS, latency and queue depth but no
device bandwidth anywhere -- the bandwidth-per-tier chart drew no L3 line and
the device tile could only say "not measured".  Three causes:

  * the nvme_driver collector read /sys/block/<dev>/stat fields 0, 3, 4, 7-10
    and skipped 2 and 6, the sector counters, so it never had bytes; the
    writer then hard-coded bandwidth to 0 as "no byte counters in pre-4.18
    layout", which is not true of any kernel since 2.6;
  * with no --prom-instance the fetch did not pin a host, so the amoprof
    device gauges were avg()-ed across dgx1, dgx3 and the memory node cx03
    -- 10,051 "IOPS" was a three-machine blend;
  * with no --nvme-device each node_disk_* counter picked its own device,
    "the one with the highest cumulative value", so bytes came from an
    OS disk with a large lifetime total while I/Os came from the HiCache
    device.
"""
import csv
import json
import pathlib
import sys
import tempfile

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))

_RESULTS = []
MIB = 1048576.0


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _fetch(url, instance=""):
    from amoprof.report.amoprof import collect_from_prometheus_api
    out = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_fetch_")) / "raw"
    out.mkdir(parents=True)
    t0 = 1_790_000_000
    collect_from_prometheus_api(url, t0, t0 + 600, step_s=60, output_dir=out,
                                instance=instance)
    p = out / "nvme_driver_timeseries.csv"
    return list(csv.DictReader(p.open())) if p.exists() else []


def main() -> int:
    print("\nThe collector reads the sector counters")
    from amoprof.collectors.nvme_driver import NvmeDriverMonitor
    mon = NvmeDriverMonitor("nvme6n1", interval_s=1.0)
    # Two /sys/block/nvme6n1/stat readings 10 s apart: 600 MiB read and
    # 300 MiB written, i.e. 60 / 30 MiB/s.
    s0 = {"_ts": 100.0, "rd_ios": 0, "rd_sectors": 0, "rd_ms": 0,
          "wr_ios": 0, "wr_sectors": 0, "wr_ms": 0, "inflight": 1,
          "io_ms": 0, "weighted_io_ms": 0}
    s1 = dict(s0, _ts=110.0, rd_ios=5000, wr_ios=2000,
              rd_sectors=int(600 * MIB / 512), wr_sectors=int(300 * MIB / 512))
    mon._samples = [s0]
    mon._read_stat = lambda: s1      # stop() takes a final reading
    mon._read_queue_params = lambda: {}
    summ = mon.stop()
    _check("read bandwidth from Δsectors x 512", summ.get("nvme_rd_bw_mbs_sysfs"), 60.0)
    _check("write bandwidth too", summ.get("nvme_wr_bw_mbs_sysfs"), 30.0)
    _check("IOPS are unchanged", summ.get("nvme_rd_iops_sysfs"), 500.0)
    # A real stat line: reads, merges, SECTORS, ms, writes, merges, SECTORS, ...
    import builtins, io
    _line = "5000 0 1228800 900 2000 0 614400 4000 3 7000 12000 0 0 0 0 0 0\n"
    _orig_open = builtins.open
    builtins.open = lambda p, *a, **k: (io.StringIO(_line)
                                        if str(p).endswith("/stat") else _orig_open(p, *a, **k))
    try:
        _st = NvmeDriverMonitor("nvme6n1")._read_stat()
    finally:
        builtins.open = _orig_open
    _check("the stat reader keeps field 2 (sectors read)", _st.get("rd_sectors"), 1228800)
    _check("and field 6 (sectors written)", _st.get("wr_sectors"), 614400)

    print("\nThe writer derives per-sample bandwidth from them")
    from amoprof.writer import write_nvme_driver_timeseries
    raw = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_wr_"))
    rows = [dict(s0, ts=100.0), dict(s1, ts=110.0)]
    (raw / "nvme_driver_timeseries.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    write_nvme_driver_timeseries(raw, 100.0)
    out = list(csv.DictReader((raw / "nvme_driver_timeseries.csv").open()))
    _check("the second sample carries 60 MiB/s read",
           float(out[-1]["rd_bw_mbs"]), 60.0)
    _check("and 30 MiB/s write", float(out[-1]["wr_bw_mbs"]), 30.0)
    old = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_wr_old_"))
    (old / "nvme_driver_timeseries.jsonl").write_text("\n".join(
        json.dumps({k: v for k, v in r.items() if "sectors" not in k})
        for r in rows) + "\n")
    write_nvme_driver_timeseries(old, 100.0)
    _old = list(csv.DictReader((old / "nvme_driver_timeseries.csv").open()))
    _check("samples from an older collector stay 0 (= not measured)",
           float(_old[-1]["rd_bw_mbs"]), 0.0)

    print("\nAn unpinned fetch reads the SGLang host, and one device")
    import stub_prometheus_multihost as stub
    srv, url = stub.serve()
    try:
        r = _fetch(url)
        _check("the device file was written", len(r) > 1, True)
        _check("IOPS are dgx1's 1,000, not the three-host average 10,000",
               float(r[0]["rd_iops"]), 1000.0)
        _check("bandwidth is dgx1's sysfs 300 MB/s",
               float(r[0]["rd_bw_mbs"]), 300.0)
        _d_bytes = float(r[1]["rd_bytes"]) - float(r[0]["rd_bytes"])
        _check("bytes come from the busy HiCache device nvme6n1 (300 MiB/s)",
               round(_d_bytes / 60.0 / MIB), 300)
        _check("not from the OS disk with the larger lifetime total",
               float(r[0]["rd_bytes"]) < 9e15, True)
        _check("and the I/O counter is the same device's",
               round((float(r[1]["rd_ios"]) - float(r[0]["rd_ios"])) / 60.0), 1000)

        print("\nAn explicit --prom-instance still wins")
        r3 = _fetch(url, instance=f"{stub.DGX3}:9100")
        _check("dgx3 asked for, dgx3's 5,000 IOPS returned",
               float(r3[0]["rd_iops"]), 5000.0)
    finally:
        srv.shutdown()

    failed = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(failed)}/{len(_RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
