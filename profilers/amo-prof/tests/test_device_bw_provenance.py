#!/usr/bin/env python3
"""Device bandwidth is measured on the device, and nothing else is called that.

Run: python3 tests/test_device_bw_provenance.py

A local-SSD L3 report (v1.78.0, gemma-4-31b-it, 72.2 min) published

    L3 read BW    27,224 MB/s     rd_bw_mbs · nvme_driver_timeseries.csv
    L3 write BW   28,037.2 MB/s   wr_bw_mbs · nvme_driver_timeseries.csv

against a 7.0 / 5.0 GB/s device target -- four times what one Gen4 drive can
move.  Neither number came from the device.  Its byte counters were empty, so
the report filled each direction with the engine's token counters:

    prefetch  215,803,904 tok x 560 KiB / 4,332 s = 27,243 MiB/s
    backup    222,246,912 tok x 560 KiB / 4,332 s = 28,057 MiB/s

and the tile-formula registry, keyed by title, labelled the result with the
device formula.  The comparison report of the same run said "not exported",
which was the truth.  The End Report did the same three ways: IOPS x KV block
size (8.75 MB) as bandwidth, a token overlay written into the device series
with IOPS invented from it, and the token rate max()-ed into the device means.

Now: one tile for what the device measured -- or "not measured" -- and one for
the token-derived KV traffic, each labelled by source; prose and requirements
never size a drive from tokens.  Also pinned here: the page size has no
default of 1, and the amoprof exporter instance is chosen on the SGLang host.
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

# The reference report's figures.
PF_TOK, BK_TOK, WIN_S, KV_KIB = 215_803_904, 222_246_912, 4_332.0, 560.0
SHOWN_RD, SHOWN_WR = 27_224, 28_037.2

# Synthetic run: 20 samples, 60 s apart; 960 KB/token from the model config.
N = 20
PF_STEP, BK_STEP = 20_000, 22_000          # tokens per sample
KV_KB = 960.0                               # 2 * 60 * 16 * 256 * 2 bytes


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _make_run(base: pathlib.Path, *, rd_bw=0.0, wr_bw=0.0,
              launch_page="--page-size 64", setup_extra=None) -> pathlib.Path:
    raw = base / "raw"
    raw.mkdir(parents=True)
    hdr = ("time_sec,sglang_max_total_num_tokens,sglang_full_token_usage,"
           "sglang_hicache_host_used_tokens,sglang_hicache_host_total_tokens,"
           "sglang_backuped_tokens_total,sglang_prefetched_tokens_total,"
           "sglang_prompt_tokens_total,sglang_generation_tokens_total,"
           "sglang_num_requests_total")
    rows = [hdr] + [",".join(str(x) for x in [
        i * 60.0, 332_000, 0.5, 1_000_000, 4_000_000,
        BK_STEP * i, PF_STEP * i, 500_000 * i, 5_000 * i, 100 * i])
        for i in range(N)]
    raw.joinpath("sglang_timeseries.csv").write_text("\n".join(rows) + "\n")
    setup = {"Model": "google/gemma-4-31b-it", "TP size": 8,
             "HiCache storage backend": "file", "L3 Mount Path": "/mnt/kvcache",
             "Launch command": ("python -m sglang.launch_server "
                                f"--hicache-storage-backend file {launch_page}")}
    setup.update(setup_extra or {})
    raw.joinpath("setup_details.json").write_text(json.dumps(setup))
    raw.joinpath("model_config.json").write_text(json.dumps({
        "num_hidden_layers": 60, "num_key_value_heads": 16,
        "head_dim": 256, "torch_dtype": "bfloat16"}))
    raw.joinpath("gpu_summary.json").write_text(json.dumps({
        "gpu_count": 8, "hbm_used_gb_mean": 33.9, "hbm_total_gb": 40.0,
        "gpu_util_mean": 89.0}))
    # The device was busy (10k read / 5k write IOPS) in both variants; only
    # whether its byte columns carry anything differs.
    nv = ["time_sec,rd_iops,wr_iops,rd_bw_mbs,wr_bw_mbs,rd_lat_ms,wr_lat_ms,"
          "io_util_pct,inflight"]
    nv += [f"{i * 60.0},10000,5000,{rd_bw},{wr_bw},0.29,2.1,37.5,41"
           for i in range(N)]
    raw.joinpath("nvme_driver_timeseries.csv").write_text("\n".join(nv) + "\n")
    return raw


def _tiles(html_s: str) -> dict:
    """label -> (value, whole tile text incl. note and target line)."""
    s = _H.unescape(html_s)
    out = {}
    for m in re.finditer(r'<div class="kpi"[^>]*>(.*?)(?=<div class="kpi"[ >]|</section|$)',
                         s, re.S):
        blk = m.group(1)
        lab = re.search(r'class="kpi-label">(.*?)</div>', blk, re.S)
        val = re.search(r'class="kpi-value">(.*?)</div>', blk, re.S)
        if not (lab and val):
            continue
        c = lambda x: re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
        out.setdefault(c(lab.group(1)), (c(val.group(1)), c(blk)))
    return out


def _text(html_s: str) -> str:
    return re.sub(r"\s+", " ", _H.unescape(re.sub(r"<[^>]+>", " ", html_s)))


def main() -> int:
    print("\nThe published figures are token counters, not device bytes")
    _check("prefetched tokens x 560 KiB / window is 27,243 MiB/s",
           round(PF_TOK * KV_KIB / 1024 / WIN_S), 27_243)
    _check("within 0.1% of the 27,224 MB/s 'read BW' shown",
           abs(PF_TOK * KV_KIB / 1024 / WIN_S - SHOWN_RD) / SHOWN_RD < 0.001, True)
    _check("backed-up tokens give 28,057 MiB/s, the 'write BW' shown",
           round(BK_TOK * KV_KIB / 1024 / WIN_S), 28_057)
    _check("3.9x a 7 GB/s Gen4 drive's sequential read",
           round(SHOWN_RD / 7000, 1), 3.9)

    from amoprof.report.combined import build_executive_summary_html as _b
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_devbw_"))
    try:
        # Decimal MB/s, as the report prints: tokens/s x KiB x 1024 / 1e6.
        _want_rd = PF_STEP / 60.0 * KV_KB * 1024 / 1e6
        _want_wr = BK_STEP / 60.0 * KV_KB * 1024 / 1e6
        DEV = "L3 (local storage) read / write BW — device (measured)"
        LOG = "L3 (local storage) read / write BW — KV logical (token-derived)"

        print("\nNo device bytes: the device tile says so")
        h0 = _b(_make_run(tmp / "nobytes"), run_label="nobytes")
        t0, x0 = _tiles(h0), _text(h0)
        _check("the device tile is present", DEV in t0, True)
        _check("and reads 'not measured'", t0[DEV][0], "not measured")
        _check("it names the collectors that would measure it",
               "nvme_driver or iostat" in t0[DEV][1], True)
        _check("the token-derived tile is present", LOG in t0, True)
        _check("carrying the token rates",
               t0[LOG][0], f"{_want_rd:,.0f} rd / {_want_wr:,.1f} wr MB/s")
        _check("labelled as derived, with no device target",
               "not measured on a device" in t0[LOG][1], True)
        _check("no tile quotes the token read rate as a device figure",
               [k for k, (v, _n) in t0.items()
                if k != LOG and f"{_want_rd:,.0f}" in v
                and re.search(r"BW|bandwidth", k)], [])
        _check("the old per-direction tiles are gone",
               [k for k in t0 if k in ("L3 (local storage) read BW",
                                       "L3 (local storage) write BW")], [])
        _peak = [k for k in t0 if k.endswith("storage BW (device)")]
        _check("the device peak tile does not print 0 for unmeasured bytes",
               [t0[k][0] for k in _peak], ["not measured"])
        _check("prose does not call the token rate physical bandwidth",
               f"Physical bandwidth is {_want_rd:.1f}" in x0, False)
        _check("and the action table does not size a drive from it",
               f"Require ≥{_want_rd * 1.1:.0f} MB/s" in x0, False)
        _check("the floor it does state says it is a floor",
               "a floor only" in x0, True)

        print("\nDevice bytes present: the device tile reports them")
        h1 = _b(_make_run(tmp / "bytes", rd_bw=1500.0, wr_bw=900.0),
                run_label="bytes")
        t1, x1 = _tiles(h1), _text(h1)
        _check("the device tile carries the measured means",
               t1[DEV][0], "1,500 rd / 900.0 wr MB/s")
        _check("with the device's IOPS beside them",
               "10,000 rd / 5,000 wr IOPS mean" in t1[DEV][1], True)
        _check("the token-derived tile is unchanged by them",
               t1[LOG][0], t0[LOG][0])
        _check("requirements are now sized from the measurement",
               "Require ≥1650 MB/s" in x1, True)

        print("\nOne direction measured, the other not")
        h2 = _b(_make_run(tmp / "half", rd_bw=1500.0, wr_bw=0.0),
                run_label="half")
        t2 = _tiles(h2)
        _check("the unmeasured write is n/m, not 0",
               t2[DEV][0], "1,500 rd / n/m wr MB/s")

        print("\nThe End Report keeps device and token figures apart")
        from amoprof.report.amoprof import extract_metrics, load_raw_dir
        m0 = extract_metrics(load_raw_dir(tmp / "nobytes" / "raw"))
        _check("device read mean stays 0 (not measured)",
               round(float(m0.nvme_rd_bw_mbs_mean), 3), 0.0)
        _check("device write mean stays 0 (not measured)",
               round(float(m0.nvme_wr_bw_mbs_mean), 3), 0.0)
        _check("blktrace-style device means too",
               (float(m0.ssd_rd_bw_mbs_mean), float(m0.ssd_wr_bw_mbs_mean)),
               (0.0, 0.0))
        _io = m0.nvme_io_ts
        _check("the device series carries no invented bandwidth",
               bool((_io.get("rd_bw_mbs", 0).fillna(0) > 0).any()
                    or (_io.get("wr_bw_mbs", 0).fillna(0) > 0).any()), False)
        _check("nor invented IOPS: the driver's 10,000 read IOPS survive",
               round(float(_io["rd_iops"].mean())), 10_000)
        _check("the token-derived read rate has its own field",
               float(m0.l3_logical_rd_bw_mbs) > 0, True)
        m1 = extract_metrics(load_raw_dir(tmp / "bytes" / "raw"))
        _check("with bytes, the device mean is the measurement",
               round(float(m1.nvme_rd_bw_mbs_mean)), 1500)

        print("\nPage size: no default, sources compared")
        from amoprof.report.common_kpis import resolve_page_size as _rps
        _check("silent sources give None, not 1",
               _rps({"Launch command": "python -m sglang.launch_server"}),
               (None, "", ""))
        _check("the launch command is read",
               _rps({"Launch command": "x --page-size 64"})[:2],
               (64.0, "--page-size in the launch command"))
        _v, _s, _c = _rps({"Launch command": "x --page-size 64",
                           "HiCache page size": "1 token/page (live page_size)"})
        _check("a stale setup value does not override the launch command",
               _v, 64.0)
        _check("but the disagreement is stated",
               "setup_details 'HiCache page size' says 1" in _c, True)
        _check("live server_info outranks the launch command",
               _rps({"Launch command": "x --page-size 64",
                     "SGLang server_info raw": {"page_size": 32}})[:2],
               (32.0, "SGLang server_info page_size"))
        _check("a defaulted field is ignored",
               _rps({"Page size": "1", "Defaulted fields": ["Page size"]}),
               (None, "", ""))
        hp = _b(_make_run(tmp / "nopage", launch_page=""), run_label="nopage")
        _check("the setup table says unknown instead of 1",
               "KV page size unknown" in _text(hp), True)
        _check("and with --page-size 64 it names the source",
               "64 token/page (from" in x1, True)

        print("\nThe amoprof exporter instance is the SGLang host's")
        from amoprof.report.amoprof import _pick_gpu_node_instance as _pk
        _insts = ["host-cx03.example.com:9101", "host-dgx1.example.com:9101",
                  "host-dgx3.example.com:9101"]
        _check("alphabetical order no longer picks the memory node",
               _pk(_insts, ["host-dgx1.example.com:30000"])[0],
               "host-dgx1.example.com:9101")
        _check("with no SGLang host known, it says the pick is a guess",
               "likely the wrong node" in _pk(_insts, [])[1], True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(failed)}/{len(_RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
