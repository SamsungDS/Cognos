#!/usr/bin/env python3
"""blktrace that saw a sliver of the device is not treated as the device.

Run: python3 tests/test_blktrace_coverage.py

A local-SSD L3 run (gemma-4-31b-it, 73 min) traced the NVMe multipath head
while its I/O was accounted on the controller path.  blktrace captured
15.9 GB each way; the device's own counters moved ~616 / 602 MB/s, about
2.6 TB each way.  From that 0.6% sample the report still published

    "Mean queue depth 228.6 (exact blktrace Q->C, p95 786, peak 17419).
     Healthy parallel I/O without saturation."

against a device queue (diskstats field 11) of 40.9, and drew LBA strips in
which every band read ~100% -- each band's MAXIMUM share over collection
cycles, so ten bands that were each busiest once summed to ~1,000%.

Also pinned: a mooncake run no longer shows the local HiCache path's df as an
"L3 KV utilization" beside the L3.5 one (63.9% vs 78.8% on that run).
"""
import html as _H
import json
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
_RESULTS = []

N, STEP = 42, 105.0                      # 73.5 min at the report's sampling
DEV_RD, DEV_WR = 616.0, 602.0            # MiB/s, the device's own counters
BT_GB = 15.9                             # what blktrace captured, each way


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _make_run(base, *, bt_gb=BT_GB, backend="file", df=False):
    raw = base / "raw"
    (raw / "blktrace_analysis").mkdir(parents=True)
    hdr = ("time_sec,sglang_max_total_num_tokens,sglang_full_token_usage,"
           "sglang_hicache_host_used_tokens,sglang_hicache_host_total_tokens,"
           "sglang_backuped_tokens_total,sglang_prefetched_tokens_total,"
           "sglang_prompt_tokens_total,sglang_generation_tokens_total,"
           "sglang_num_requests_total")
    rows = [hdr] + [",".join(str(x) for x in [
        i * STEP, 196_096, 0.7, 1_000_000, 4_000_000, 6_000 * i * STEP,
        6_000 * i * STEP, 30_000 * i * STEP, 40 * i * STEP, 2 * i * STEP])
        for i in range(N)]
    raw.joinpath("sglang_timeseries.csv").write_text("\n".join(rows) + "\n")
    launch = (f"python -m sglang.launch_server --hicache-storage-backend {backend} "
              "--page-size 64")
    setup = {"Model": "google/gemma-4-31b-it", "TP size": 8,
             "HiCache storage backend": backend, "Launch command": launch}
    if backend == "file":
        setup.update({"L3 Mount Path": "/mnt/kvcache", "L3 Device": "/dev/nvme6n1"})
    raw.joinpath("setup_details.json").write_text(json.dumps(setup))
    raw.joinpath("model_config.json").write_text(json.dumps({
        "num_hidden_layers": 60, "num_key_value_heads": 16, "head_dim": 256,
        "torch_dtype": "bfloat16"}))
    raw.joinpath("gpu_summary.json").write_text(json.dumps({
        "gpu_count": 8, "hbm_used_gb_mean": 33.3, "hbm_total_gb": 40.0,
        "gpu_util_mean": 89.6}))
    # The device: byte counters, IOPS, and a time-weighted queue of ~41.
    # LBA deciles per cycle: the hot band moves, ten cycles each; per-cycle
    # bytes are equal, so the byte-weighted split is 10% per band.
    nv = ["time_sec,rd_iops,wr_iops,rd_bw_mbs,wr_bw_mbs,avgqu_sz,inflight,"
          "bt_write_bytes,bt_read_bytes,lba_w_span_gb,lba_w_start_gb,"
          + ",".join(f"lba_w_d{i}" for i in range(10))]
    for k in range(N):
        hot = k % 10
        dec = ",".join("100" if i == hot else "0" for i in range(10))
        nv.append(f"{k*STEP},10733,4663,{DEV_RD},{DEV_WR},40.9,2,"
                  f"{bt_gb*1e9/N:.0f},{bt_gb*1e9/N:.0f},2881,0,{dec}")
    raw.joinpath("nvme_driver_timeseries.csv").write_text("\n".join(nv) + "\n")
    raw.joinpath("blktrace_analysis/summary.json").write_text(json.dumps({
        "read_bytes_total": bt_gb * 1e9, "write_bytes_total": bt_gb * 1e9}))
    raw.joinpath("blktrace_analysis/queue_depth_summary.json").write_text(json.dumps({
        "qd_mean": 228.6, "qd_p95": 786, "qd_max": 17419, "pct_at_qd_ge_32": 80,
        "qd_source": "blktrace_q_to_c"}))
    if df:
        raw.joinpath("ssd_hw_summary.json").write_text(json.dumps({
            "hicache_fs_total_gb": 3575.0, "hicache_fs_used_gb": 2284.0,
            "hicache_fs_avail_gb": 1291.0, "hicache_fs_used_pct": 63.9}))
    return raw


def _text(h):
    return re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", " ", h)))


def _labels(h):
    return [re.sub(r"<[^>]+>", "", _H.unescape(m))
            for m in re.findall(r'class="kpi-label">(.*?)</div>', h, re.S)]


def main() -> int:
    from amoprof.report.combined import build_executive_summary_html as _b
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_btcov_"))
    try:
        _dev_gb = (DEV_RD + DEV_WR) * (N - 1) * STEP / 1024
        print("\nThe arithmetic")
        _check("the device moved ~2.5 TB each way in 73 min",
               round(DEV_WR * (N - 1) * STEP / 1024 / 1000, 1), 2.5)
        _check("so 15.9 GB is ~0.6% coverage",
               round(2 * BT_GB / _dev_gb * 100, 1), 0.6)

        print("\nLow coverage: blktrace stops standing in for the device")
        h = _b(_make_run(tmp / "low"), run_label="low")
        x = _text(h)
        _check("a data-quality finding says how much blktrace saw",
               "BLKTRACE COVERAGE" in x and "captured 0.6% of the bytes" in x, True)
        _check("the 228.6 'exact Q->C' depth is no longer published",
               "Mean queue depth 228.6" in x or "228.6 requests in parallel" in x, False)
        _check("the queue finding cites the device's own 40.9 instead",
               "Mean queue depth 40.9" in x, True)
        _check("from the device counters, not 'exact blktrace'",
               "Mean queue depth 40.9 (advisory" in x, True)
        _check("the LBA strips are withdrawn, with the reason",
               "LBA distribution withdrawn" in x, True)
        _check("and no strip renders", "I/O across LBA space" in x, False)
        _check("the endurance tile compares the device's own writes",
               "device wrote" in x and "blktrace captured 0.6% of device bytes" in x, True)

        print("\nFull coverage: the strips render, byte-weighted")
        h2 = _b(_make_run(tmp / "full", bt_gb=DEV_WR * (N - 1) * STEP / 1024),
                run_label="full")
        x2 = _text(h2)
        _check("no coverage warning", "BLKTRACE COVERAGE" in x2, False)
        _check("the write strip renders", "write I/O across LBA space" in x2, True)
        _m = re.search(r"busiest [0-9,.\-G]+ carries ([0-9.]+)%", x2)
        # 42 equal-byte cycles over 10 bands: bands 0 and 1 are hot in 5
        # cycles, the rest in 4, so the busiest carries 5/42 = 11.9%.
        _check("the busiest band carries 5/42 = 12% of bytes, not 100%",
               _m.group(1) if _m else None, "12")
        _bands = [float(v) for v in re.findall(r"LBA space [0-9,.\-]+G: ([0-9.]+) % of bytes", x2)]
        _check("and the ten bands sum to 100%",
               round(sum(_bands[:10])), 100)

        print("\nA mooncake run does not show the local path's df as L3 utilization")
        h3 = _b(_make_run(tmp / "mc", backend="mooncake", df=True), run_label="mc")
        _l3 = _labels(h3)
        _check("no 'L3 KV utilization' tile", "L3 KV utilization" in _l3, False)
        _check("no 'L3 cache used' tile either",
               any(l.startswith("L3 cache used") for l in _l3), False)
        _check("the L3.5 utilization tile is still there", "L3.5 KV utilization" in _l3, True)
        h4 = _b(_make_run(tmp / "loc", df=True), run_label="loc")
        _check("a local run keeps its L3 KV utilization tile",
               "L3 KV utilization" in _labels(h4), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(failed)}/{len(_RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
