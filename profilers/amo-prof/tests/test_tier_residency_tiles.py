#!/usr/bin/env python3
"""Every configured tier gets a RAW usage tile and a KV utilization tile.

Run: python3 tests/test_tier_residency_tiles.py

The two numbers answer different questions and are routinely confused:

    RAW usage        what the system reports for the whole tier -- DCGM for
                     HBM, /proc/meminfo for host DRAM, df for the HiCache
                     filesystem, the store's allocator for L3.5.  Counts
                     weights, activations, page cache, anything resident.

    KV utilization   how full the tier's KV allocation is: SGLang's own pool
                     gauges for L1/L2, df on the HiCache path (or the backup -
                     prefetch counters) for L3, the store for L3.5.

The utilization figures are read off the same `_occ` series the tier-occupancy
charts plot, not recomputed, so a tile and the chart above it cannot disagree.
(Until the 1.77 merge these were per-tier "KV residency" tiles; main's KV
utilization tiles replaced them, and this file followed.)

combined.py is exercised by RENDERING a synthetic run and reading the tiles out
of the HTML.  amoprof.py cannot be: it imports matplotlib, which is absent from
the 3.12 interpreter this suite runs under, so its changes are pinned by
asserting the exact expressions.

Separately, and worse: `kv_active_tokens` held prefill_cache +
prefill_compute -- the run's CUMULATIVE prefill total -- and was rendered as
"N live tokens / pool".  On the reference run that printed 46,529,863 live
tokens against a pool of 38,000: 1,224x the capacity it was shown as a
fraction of.  The same field fed a fallback that clamped it to the pool
capacity with min(), so any run missing the gauge reported its pool exactly
100% full as a measurement.
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

# From the user's v1.57.0 run, cross-checked three ways in that report:
#   cached 36,762,836 / context 46,529,863 = 79.01%, the cache-hit figure
#   the same card states "Max Context (HBM) 38 K tokens"
CTX_TOKENS = 46_529_863
CACHED_TOKENS = 36_762_836
POOL_TOKENS = 38_000
KV_KB = 960.0            # exact from the model config: 2*60*16*256*2 bytes


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


# --------------------------------------------------------------------------
# A synthetic run that configures L1, L2 and L3, with the L3 capacity present
# ONLY in ssd_hw_summary.json -- the state a Prometheus-only analyze leaves.
# --------------------------------------------------------------------------
N = 20
POOL_CAP = 332_000
FILL = [0.05 + 0.55 * i / (N - 1) for i in range(N)]      # 5% -> 60%
FILL_MEAN = sum(FILL) / N                                  # 0.325
L2_USED_TOK = [1_000_000 + 50_000 * i for i in range(N)]
L2_TOTAL_TOK = 4_000_000
L3_FS_USED_GB, L3_FS_TOTAL_GB = 400.0, 1000.0


def _make_run(base: pathlib.Path, *, capacity_in_sidecar=True,
              with_dram=True) -> pathlib.Path:
    raw = base / "raw"
    raw.mkdir(parents=True)
    hdr = ("time_sec,sglang_max_total_num_tokens,sglang_full_token_usage,"
           "sglang_hicache_host_used_tokens,sglang_hicache_host_total_tokens,"
           "sglang_backuped_tokens_total,sglang_prefetched_tokens_total,"
           "sglang_prompt_tokens_total,sglang_generation_tokens_total,"
           "sglang_num_requests_total")
    rows = [hdr]
    for i in range(N):
        rows.append(",".join(str(x) for x in [
            i * 60.0, POOL_CAP, round(FILL[i], 6),
            L2_USED_TOK[i], L2_TOTAL_TOK,
            100_000 * i, 20_000 * i,
            500_000 * i, 5_000 * i, 100 * i]))
    raw.joinpath("sglang_timeseries.csv").write_text("\n".join(rows) + "\n")
    raw.joinpath("setup_details.json").write_text(json.dumps({
        "Model": "google/gemma-4-31b-it", "TP size": 8,
        "HiCache storage backend": "file",
        "L3 Mount Path": "/mnt/kvcache",
        "Launch command": ("python -m sglang.launch_server "
                           "--hicache-storage-backend file --hicache-ratio 2"),
    }))
    raw.joinpath("model_config.json").write_text(json.dumps({
        "num_hidden_layers": 60, "num_key_value_heads": 16,
        "head_dim": 256, "torch_dtype": "bfloat16"}))
    raw.joinpath("gpu_summary.json").write_text(json.dumps({
        "gpu_count": 8, "hbm_used_gb_mean": 33.9, "hbm_total_gb": 40.0,
        "gpu_util_mean": 89.0}))
    if with_dram:
        raw.joinpath("dram_summary.json").write_text(json.dumps({
            "dram_total_gb": 1008.0, "dram_used_gb_mean": 48.5}))
    cap = {"hicache_fs_total_gb": L3_FS_TOTAL_GB,
           "hicache_fs_used_gb": L3_FS_USED_GB,
           "hicache_fs_avail_gb": L3_FS_TOTAL_GB - L3_FS_USED_GB,
           "hicache_fs_used_pct": 40.0,
           "nvme_device_capacity_gb": 1920.0}
    raw.joinpath("ssd_hw_summary.json" if capacity_in_sidecar
                 else "smart_summary.json").write_text(json.dumps(cap))
    return raw


def _tiles(html_s: str) -> dict:
    s = _H.unescape(html_s)
    out = {}
    for lab, val, note in re.findall(
            r'class="kpi-label">(.*?)</div>\s*<div class="kpi-value">(.*?)'
            r'</div>\s*<div class="kpi-note">(.*?)</div>', s, re.S):
        _c = lambda x: _H.unescape(re.sub(r"<[^>]+>", " ", x)).strip()
        out.setdefault(_c(lab), (_c(val), re.sub(r"\s+", " ", _c(note))))
    return out


def main() -> int:
    print("\nThe number that was presented as a residency cannot be one")
    _check("context tokens are 1,224x the pool they were shown against",
           round(CTX_TOKENS / POOL_TOKENS), 1224)
    _check("and they reconcile as the run's prefill total, not a level",
           round(CACHED_TOKENS / CTX_TOKENS * 100, 2), 79.01)
    # 46.5M tokens of KV at this model's geometry:
    _check("holding them at once would need 42,599 GB of HBM",
           round(CTX_TOKENS * KV_KB / (1024 * 1024)), 42_599)
    _check("against 320 GB on the node — 133x over",
           round(CTX_TOKENS * KV_KB / (1024 * 1024) / 320), 133)

    print("\nBoth halves now render for every configured tier")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_tier_"))
    try:
        from amoprof.report.combined import build_executive_summary_html
        raw = _make_run(tmp / "run")
        tl = _tiles(build_executive_summary_html(raw, run_label="t"))
        for tier, rawname, residname in (
                ("L1", "L1 HBM used — raw (all GPUs)", "L1 KV utilization"),
                ("L2", "L2 host DRAM used — raw (physical)",
                 "L2 KV residency (est.)"),
                ("L3", "L3 cache used — raw (df snapshot)",
                 "L3 KV utilization")):
            _check(f"{tier} raw tile present", rawname in tl, True)
            _check(f"{tier} KV residency tile present", residname in tl, True)

        print("\nThe L1 utilization is the pool gauge, meaned over the window")
        _check("mean fill is 32.5% by construction", round(FILL_MEAN, 4), 0.325)
        _check("so L1 KV utilization is 32.5%",
               tl["L1 KV utilization"][0], "32.5 %")
        _check("the tile reports the peak as well as the mean",
               "peak 60.0%" in tl["L1 KV utilization"][1], True)
        _check("and the peak is the gauge's maximum, not the mean's",
               round(max(FILL) * 100, 1), 60.0)
        _check("with the tokens behind it: peak / pool capacity",
               f"{round(max(FILL) * POOL_CAP / 1e3):.0f}K / "
               f"{round(POOL_CAP / 1e3):.0f}K tok" in tl["L1 KV utilization"][1],
               True)

        print("\nThe L3 utilization is the filesystem snapshot")
        _check("400 of 1000 GB on the HiCache path is 40%",
               tl["L3 KV utilization"][0],
               f"{L3_FS_USED_GB / L3_FS_TOTAL_GB * 100:.1f} %")
        # 400 GB / 960 KB per token, GB here being 1024^3-based as df reports.
        _want_l3 = round(L3_FS_USED_GB * 1024 * 1024 / KV_KB)
        _check("400 GB at 960 KB/token is 436,907 tokens", _want_l3, 436_907)
        _check("and the tile carries that token figure",
               f"{round(_want_l3 / 1e3):.0f}K" in tl["L3 KV utilization"][1],
               True)
        _check("the raw tile still shows the whole filesystem",
               tl["L3 cache used — raw (df snapshot)"][0], "400 / 1000 GB")
        _check("so the pair is not the same number twice",
               tl["L3 KV utilization"][0]
               != tl["L3 cache used — raw (df snapshot)"][0], True)

        print("\nThe utilization figures match the tier-occupancy chart")
        _html = build_executive_summary_html(raw, run_label="t")
        _s = _H.unescape(_html)
        _check("the chart plots an L1 series", "L1 HBM KV pool" in _s, True)
        _check("and an L3 series", "L3-local storage" in _s, True)
        _check("the L3 tile names the df snapshot as its measured source",
               "df snapshot, measured" in tl["L3 KV utilization"][1], True)

        print("\nWithout a model config the tiles still render")
        _noc = _make_run(tmp / "noconfig")
        _noc.joinpath("model_config.json").unlink()
        _tl2 = _tiles(build_executive_summary_html(_noc, run_label="t2"))
        _check("L1 utilization survives, because its tokens are measured",
               _tl2["L1 KV utilization"][0], "32.5 %")
        _check("and L3's percentage is df's, which needs no geometry",
               _tl2["L3 KV utilization"][0], tl["L3 KV utilization"][0])

        print("\nWith no df snapshot, the counter branch runs and says so")
        _cnt = _make_run(tmp / "counters")
        (_cnt / "ssd_hw_summary.json").unlink()
        _tl3 = _tiles(build_executive_summary_html(_cnt, run_label="t4"))
        _check("the L3 utilization tile stays", "L3 KV utilization" in _tl3,
               True)
        _check("with no percentage, since there is no capacity to divide by",
               _tl3["L3 KV utilization"][0], "—")
        _n3 = _tl3["L3 KV utilization"][1]
        # Last sample: backup 100,000x19 = 1,900,000, prefetch 20,000x19 =
        # 380,000, both baselined at 0, so residency peaks at the difference.
        _check("showing the resident tokens the counters imply instead",
               f"{(19 * 100_000 - 19 * 20_000) / 1e6:.1f}M tok resident" in _n3,
               True)
        _check("which is Σbackup − Σprefetch = 1,520,000 tokens",
               19 * 100_000 - 19 * 20_000, 1_520_000)

        print("\nA raw tile never vanishes silently for a configured tier")
        _nodram = _make_run(tmp / "nodram", with_dram=False)
        _tl5 = _tiles(build_executive_summary_html(_nodram, run_label="t5"))
        _check("the host DRAM tile renders without DRAM data",
               "L2 host DRAM used — raw (physical)" in _tl5, True)
        _check("as not collected", _tl5["L2 host DRAM used — raw (physical)"][0],
               "not collected")
        _dn = _tl5["L2 host DRAM used — raw (physical)"][1]
        _check("naming the collector", "DramMonitor" in _dn, True)
        _check("and the flag that enables it", "--dram" in _dn, True)
        _check("and saying L2 KV residency does not depend on it",
               "L2 KV residency is unaffected" in _dn, True)
        _check("while a run WITH DRAM data shows the figure, not the notice",
               tl["L2 host DRAM used — raw (physical)"][0], "48.5 GB / 1,008 GB")
        _check("the L2 residency tile also renders without a capacity",
               "L2 KV residency (est.)" in _tl5, True)
        _check("as not collected", _tl5["L2 KV residency (est.)"][0],
               "not collected")
        _check("naming where an L2 capacity comes from",
               "hicache_ratio" in _tl5["L2 KV residency (est.)"][1], True)
        _check("and that a disabled HiCache is a legitimate reason",
               "HiCache is disabled" in _tl5["L2 KV residency (est.)"][1], True)

        print("\nThe remote store's raw tiles behave the same way")
        _l35 = (tmp / "l35" / "raw")
        _l35.mkdir(parents=True)
        shutil.copy(_cnt / "sglang_timeseries.csv",
                    _l35 / "sglang_timeseries.csv")
        shutil.copy(_cnt / "model_config.json", _l35 / "model_config.json")
        _l35.joinpath("setup_details.json").write_text(json.dumps({
            "Model": "google/gemma-4-31b-it", "TP size": 8,
            "HiCache storage backend": "mooncake",
            "Launch command": ("python -m sglang.launch_server "
                               "--hicache-storage-backend mooncake"),
        }))
        _tl6 = _tiles(build_executive_summary_html(_l35, run_label="t6"))
        _check("an L3.5 run with no store bytes still shows the memory tile",
               "L3.5 memory used — raw" in _tl6, True)
        _check("and the storage tile", "L3.5 storage used — raw" in _tl6, True)
        _check("both as not collected",
               [_tl6["L3.5 memory used — raw"][0],
                _tl6["L3.5 storage used — raw"][0]],
               ["not collected", "not collected"])
        _m6 = _tl6["L3.5 memory used — raw"][1]
        _check("naming the store metrics they come from",
               "master_allocated_bytes" in _m6, True)
        _check("and allowing that a store with no file tier reports none",
               "no file tier configured" in _m6, True)
        _check("a local-L3 run gets no L3.5 notices",
               any(k.startswith("L3.5") for k in tl), False)

        print("\nEvery tier in the hierarchy has both halves, or a reason")
        for _nm in ("L1 HBM used — raw (all GPUs)", "L1 KV utilization",
                    "L2 host DRAM used — raw (physical)",
                    "L2 KV residency (est.)",
                    "L3 cache used — raw (df snapshot)",
                    "L3 KV utilization"):
            _check(f"{_nm} is in the grid of a bare Prometheus-style run",
                   _nm in _tl5, True)

        print("\nThe tile is bound even when the correlation block fails")
        _bare = tmp / "bare" / "raw"
        _bare.mkdir(parents=True)
        _bare.joinpath("setup_details.json").write_text(json.dumps(
            {"Model": "google/gemma-4-31b-it"}))
        _h3 = build_executive_summary_html(_bare, run_label="t3")
        _check("a run with no timeseries at all still renders", len(_h3) > 1000,
               True)
        # The utilization tiles always render; with nothing to measure they
        # show "—" and say why, so an unmeasured tier is not mistaken for an
        # idle one -- and the grid did not NameError to get here.
        _bt = _tiles(_h3)
        _check("the L1 utilization tile renders, rather than a NameError",
               "L1 KV utilization" in _bt, True)
        _check("with no figure, since nothing was measured",
               _bt.get("L1 KV utilization", ("", ""))[0], "—")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nThe pairs are adjacent, in hierarchy order")
    tmp2 = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_order_"))
    try:
        from amoprof.report.combined import build_executive_summary_html as _b
        _raw2 = _make_run(tmp2 / "run")
        _order = []
        for _lab in re.findall(r'class="kpi-label">(.*?)</div>',
                               _H.unescape(_b(_raw2, run_label="o"))):
            _l = re.sub(r"\s+", " ",
                        _H.unescape(re.sub(r"<[^>]+>", "", _lab))).strip()
            if _l and _l not in _order:
                _order.append(_l)
        _want = ["L1 HBM used — raw (all GPUs)", "L1 KV utilization",
                 "L2 host DRAM used — raw (physical)",
                 "L2 KV residency (est.)", "L2 KV utilization",
                 "L3 cache used — raw (df snapshot)", "L3 KV utilization"]
        _pos = [_order.index(_w) for _w in _want]
        _check("all seven tier tiles are in the grid", len(_pos), 7)
        _check("in hierarchy order", _pos, sorted(_pos))
        _check("and contiguous, not scattered through it",
               _pos[-1] - _pos[0], 6)
        # Before this they ran L1 raw, L1 KV, GPU power, three L3 bandwidth
        # tiles, L3 raw, L3 KV, L2 KV, L2 raw -- the L2 pair inverted and
        # seven tiles from L1.
        _check("each raw tile precedes its own KV tiles",
               [_pos[0] < _pos[1], _pos[2] < _pos[3] < _pos[4],
                _pos[5] < _pos[6]], [True, True, True])
        _check("every raw tile says so in its name",
               [("raw" in _w) for _w in (_want[0], _want[2], _want[5])],
               [True, True, True])
        _check("and every tile is prefixed with its tier",
               [_w[:2] for _w in _want],
               ["L1", "L1", "L2", "L2", "L2", "L3", "L3"])
        _check("a tile outside the group keeps its place",
               "GPU util" in _order and _order.index("GPU util") < _pos[0],
               True)
        # The reorder splits on the tile delimiter; losing or duplicating a
        # tile would be worse than the scattering it fixes.
        _check("no tile is lost by the reorder",
               len(_order), len(set(_order)))
        for _w in _want:
            _check(f"{_w} appears exactly once",
                   _H.unescape(_b(_raw2, run_label="o")).count(
                       f'class="kpi-label">{_w}'), 1)
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    print("\nA tier the deployment does not use contributes no tiles")
    tmp3 = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_l35leak_"))
    try:
        from amoprof.report.combined import (
            build_executive_summary_html as _b3,
            _amoprof_drop_tier_tiles as _drop,
            _amoprof_tile_label as _tlab)

        def _with_l35(_raw):
            """L3.5 node and store telemetry, as it comes back whenever the
            memory node is reachable in Prometheus -- which is routinely true
            on a local-L3 run against the same cluster."""
            _n = 20
            # The GPU node's own CPU series too: both CPU tiles are built in
            # one try block, so this is what proves the drop is per-tile and
            # not per-block.
            _raw.joinpath("cpu_timeseries.csv").write_text(
                "time_sec,cpu_util_pct,cpu_iowait_pct,cpu_busiest_core_pct\n"
                + "\n".join(f"{_i*60.0},{6.0 + _i*0.05},0.2,{30 + _i}"
                             for _i in range(_n)) + "\n")
            _raw.joinpath("l35_node_timeseries.csv").write_text(
                "time_sec,l35_cpu_util_pct,l35_cpu_iowait_pct\n"
                + "\n".join(f"{_i*60.0},{8.0 + _i*0.1},0.4"
                             for _i in range(_n)) + "\n")
            # One file, every L3.5 storage column: the endurance columns go
            # here too, because this is the file the report reads them from
            # and a second CSV would simply be ignored.  l35_host_written_gb
            # and l35_nand_written_gb are what produced the two tiles that
            # leaked into the v1.69.0 local-L3 report.
            _raw.joinpath("l35_storage_timeseries.csv").write_text(
                "time_sec,l35_cpu_util_pct,l35_cpu_iowait_pct,"
                "l35_rd_bw_mbs,l35_wr_bw_mbs,l35_host_written_gb,"
                "l35_nand_written_gb,l35_waf\n"
                + "\n".join(
                    f"{_i*60.0},{8.0+_i*0.1},0.4,{40+_i},{900+_i},"
                    f"{100.0+_i*0.15},{120.0+_i*0.2},1.33"
                    for _i in range(_n)) + "\n")
            _raw.joinpath("l35_store_capacity.csv").write_text(
                "time_sec,l35_store_mem_used_b,l35_store_mem_cap_b,"
                "l35_store_file_used_b,l35_store_file_cap_b\n"
                + "\n".join(f"{_i*60.0},{50e9+_i*1e9},{107e9},"
                             f"{300e9+_i*1e9},{1000e9}" for _i in range(_n))
                + "\n")
            return _raw

        def _run_with_backend(_dir, _backend):
            _raw = _with_l35(_make_run(_dir))
            _sd = json.loads((_raw / "setup_details.json").read_text())
            _sd["HiCache storage backend"] = _backend
            _sd["Launch command"] = (
                "python -m sglang.launch_server "
                f"--hicache-storage-backend {_backend}"
                + (" --hicache-ratio 2" if _backend == "file" else ""))
            if _backend != "file":
                _sd.pop("L3 Mount Path", None)
            (_raw / "setup_details.json").write_text(json.dumps(_sd))
            return _tiles(_b3(_raw, run_label=_backend))

        _loc = _run_with_backend(tmp3 / "local", "file")
        _rem = _run_with_backend(tmp3 / "remote", "mooncake")
        _check("a local-L3 run shows no L3.5 tile, even with the data present",
               [_k for _k in _loc if _k.startswith("L3.5")], [])
        _check("while a mooncake run shows them",
               len([_k for _k in _rem if _k.startswith("L3.5")]) >= 4, True)
        # The append sites are shared: _l35_hw_tiles carries the backing
        # tier's hardware tiles for EITHER tier, labelled through _TIER.
        # Suppressing the group would take these with it.
        _check("the local run keeps its own device tiles",
               "L3 local SSD storage BW (device)" in _loc, True)
        _check("and its queue depth",
               "L3 local SSD storage queue depth" in _loc, True)
        _check("which on the remote run are named for the node instead",
               "L3.5 node storage BW (device)" in _rem, True)
        _check("the local run keeps all six tier tiles",
               [_k for _k in ("L1 HBM used — raw (all GPUs)",
                              "L1 KV utilization",
                              "L2 host DRAM used — raw (physical)",
                              "L2 KV residency (est.)",
                              "L3 cache used — raw (df snapshot)",
                              "L3 KV utilization") if _k in _loc].__len__(),
               6)
        _check("and the CPU tile for the GPU node, which is not L3.5's",
               "GPU node CPU util" in _loc, True)
        _check("the L3.5 node CPU tile is what goes",
               ["L3.5 node CPU util" in _loc, "L3.5 node CPU util" in _rem],
               [False, True])
        # The two from the v1.69.0 report, by name.
        for _nm35 in ("L3.5 storage host writes",
                      "L3.5 KV→host amplification"):
            _check(f"{_nm35} is gone from the local run", _nm35 in _loc, False)
            _check(f"and still present on the remote run", _nm35 in _rem,
                   True)

        print("\nThe drop matches labels, not notes")
        def _t3(_lab, _note="n"):
            return (f'<div class="kpi"><div class="kpi-label">{_lab}</div>'
                    f'<div class="kpi-value">v</div>'
                    f'<div class="kpi-note">{_note}</div></div>')
        _mixed = (_t3("L1 KV utilization")
                  + _t3("L3.5 node CPU util")
                  + _t3("L3 cache used — raw (df snapshot)",
                        "not the L3.5 memory node — see that tier's own tile")
                  + _t3("L3.5 memory used — raw"))
        _out3 = _drop(_mixed, "L3.5")
        _check("both L3.5-labelled tiles go",
               [_tlab(_x) for _x in _out3.split('<div class="kpi"')[1:]],
               ["L1 KV utilization", "L3 cache used — raw (df snapshot)"])
        _check("a tile that only MENTIONS the tier in its note stays",
               "L3 cache used — raw (df snapshot)" in _out3, True)
        _check("and keeps its note intact",
               "not the L3.5 memory node" in _out3, True)
        _check("a grid with no such tile is unchanged",
               _drop(_t3("L1 KV utilization"), "L3.5"), _t3("L1 KV utilization"))
        _check("an empty grid is unchanged", _drop("", "L3.5"), "")
        _check("the leading fragment survives",
               _drop("<head/>" + _t3("L3.5 node CPU util"),
                     "L3.5"), "<head/>")
        # "L3.5" must not catch "L3 ": prefix, not substring.
        _check("the L3 prefix is not caught by an L3.5 drop",
               "L3 KV utilization" in _drop(_t3("L3 KV utilization"), "L3.5"),
               True)
        # Prefix and substring agree on every label shipping today, so the
        # difference is latent -- which is exactly why it needs a test: a
        # label that NAMES the absent tier while being about a present one
        # must survive. Matching anywhere would delete it.
        _keepers = ("L3 cache used vs L3.5 store",
                    "L2 KV residency (not L3.5)",
                    "L3 vs L3.5 delta")
        for _k3 in _keepers:
            _check(f"a tile labelled {_k3!r} is about L3, so it stays",
                   _tlab(_drop(_t3(_k3), "L3.5").split('<div class="kpi"')[-1])
                   if '<div class="kpi"' in _drop(_t3(_k3), "L3.5") else "",
                   _k3)
        _check("while the same names as a PREFIX are dropped",
               _drop(_t3("L3.5 store vs L3 cache used"), "L3.5"), "")
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)

    print("\nThe predicate is the backend class, not data presence")
    _cc = (_ROOT / "amoprof" / "report" / "combined.py").read_text()
    _check("has_l35 exists", "has_l35 = bool(has_l3)" in _cc, True)
    _check("and reads the resolved backend class",
           'str(l3_backend_class).lower() in (\n        "remote_mooncake", "remote_storage")'
           in _cc, True)
    _check("the drop is applied when it is false",
           'if not has_l35:' in _cc
           and '_amoprof_drop_tier_tiles(kpi_html, "L3.5")' in _cc, True)
    _check("before the grouping, so the group is built from what is shown",
           _cc.index('_amoprof_drop_tier_tiles(kpi_html, "L3.5")')
           < _cc.index("kpi_html = _amoprof_group_tier_tiles(kpi_html)"), True)

    print("\nThe reorder itself, on tiles built for the purpose")
    from amoprof.report.combined import (
        _amoprof_group_tier_tiles as _grp, _TIER_TILE_ORDER as _ORD)

    def _tile(_lab):
        return (f'<div class="kpi"><div class="kpi-label">{_lab}</div>'
                f'<div class="kpi-value">v</div>'
                f'<div class="kpi-note">n</div></div>')

    def _labs(_h):
        return [re.sub(r"<[^>]+>", "", _m) for _m in
                re.findall(r'class="kpi-label">(.*?)</div>', _h)]

    _scattered = ["GPU util", "L1 HBM used — raw (all GPUs)",
                  "L1 KV utilization", "GPU power", "L3 read BW",
                  "L3 cache used — raw (df snapshot)", "L3 KV utilization",
                  "L2 KV residency (est.)",
                  "L2 host DRAM used — raw (physical)", "Block IOs"]
    _got = _labs(_grp("<head/>" + "".join(_tile(_l) for _l in _scattered)))
    _check("no tile is dropped", sorted(_got), sorted(_scattered))
    _check("none is duplicated", len(_got), len(set(_got)))
    _check("the six tier tiles come out in hierarchy order",
           [_l for _l in _got if _l[:2] in ("L1", "L2", "L3")
            and "BW" not in _l],
           ["L1 HBM used — raw (all GPUs)", "L1 KV utilization",
            "L2 host DRAM used — raw (physical)", "L2 KV residency (est.)",
            "L3 cache used — raw (df snapshot)", "L3 KV utilization"])
    _check("they land where the first of them was, after GPU util",
           _got.index("L1 HBM used — raw (all GPUs)"), 1)
    _check("and the non-tier tiles keep their relative order",
           [_l for _l in _got if _l in ("GPU util", "GPU power",
                                        "L3 read BW", "Block IOs")],
           ["GPU util", "GPU power", "L3 read BW", "Block IOs"])
    _check("the leading fragment survives",
           _grp("<head/>" + _tile("L1 KV utilization")
                + _tile("L2 KV residency")).startswith("<head/>"), True)
    # A duplicate label must not displace the tile already placed: two tiles
    # with one name is a bug to see, and silently promoting the second hides
    # whichever one was wrong.
    _dup = ["L1 KV utilization", "L2 KV residency (est.)", "L1 KV utilization"]
    _dgot = _labs(_grp("".join(_tile(_l) for _l in _dup)))
    _check("a duplicate is kept, not dropped", len(_dgot), 3)
    _check("and left in place rather than promoted",
           _dgot, ["L1 KV utilization", "L2 KV residency (est.)",
                   "L1 KV utilization"])
    _check("a grid with fewer than two tier tiles is returned untouched",
           _grp("<head/>" + _tile("GPU util") + _tile("L1 KV utilization")),
           "<head/>" + _tile("GPU util") + _tile("L1 KV utilization"))
    _check("an empty grid is returned untouched", _grp(""), "")
    # Longest-prefix matching: "L3 cache used" must not claim the L3.5 tiles.
    _mix = ["L3.5 memory used — raw", "L3.5 KV utilization",
            "L3 cache used — raw (df snapshot)", "L3 KV utilization"]
    _mgot = _labs(_grp("".join(_tile(_l) for _l in _mix)))
    _check("L3 sorts before L3.5 regardless of input order",
           _mgot, ["L3 cache used — raw (df snapshot)", "L3 KV utilization",
                   "L3.5 memory used — raw", "L3.5 KV utilization"])
    _check("the order table lists L3 before L3.5",
           _ORD.index("L3 KV utilization") < _ORD.index("L3.5 memory used"),
           True)

    print("\nThe interactive tab resolves KV bytes from the model config")
    iv = (_ROOT / "amoprof" / "report" / "interactive.py").read_text()
    _check("it builds a config to hand the resolver",
           "_iv_kv_cfg: dict = {}" in iv, True)
    _check("reading raw/model_config.json", '"model_config.json"' in iv, True)
    _check("and passes it at the L2 residency call site",
           "config=_iv_kv_cfg) / 1024.0" in iv, True)
    _check("and at the L3 bandwidth call site",
           "config=_iv_kv_cfg)" in iv, True)
    # Count on a comment-stripped view: a comment mentioning the keyword
    # inflated this to 3 and made it pass for the wrong reason.
    _iv_code = "\n".join(
        _l.split("#")[0] if not _l.lstrip().startswith("#") else ""
        for _l in iv.splitlines())
    _check("neither call site resolves without it",
           _iv_code.count("_kv_bytes_per_token_for_model(") - 1,  # minus def
           _iv_code.count("config=_iv_kv_cfg"))
    _check("and there are exactly two of them",
           _iv_code.count("_kv_bytes_per_token_for_model(") - 1, 2)
    # 560 KB exact vs the 256 KB name hint is 2.1875x, which is exactly the
    # gap between the two grids on the reference run (198.0 / 90.5 = 2.1878).
    _check("the gap this closes is 2.1875x", round(560 / 256, 4), 2.1875)
    _check("matching the two tiles that disagreed", round(198.0 / 90.5, 2),
           round(560 / 256, 2))

    print("\nAn L2 KV estimate is no longer labelled host DRAM")
    # Both branches that can hold a token-derived figure must name it, so
    # count: changing one and leaving the other passed a substring test.
    _check("both token-derived branches name it L2 KV residency",
           iv.count('_dram_label = "L2 KV residency (est.)"'), 2)
    _check("provenance is tracked, not assumed",
           "_dram_used_kind" in iv, True)
    # And is what selects the label.  Both label strings stay in the source
    # whichever branch wins, so only the condition itself pins the behaviour.
    _check("and is what chooses between the two labels",
           'if _dram_used_kind == "l2kv":' in iv, True)
    _check("initialised from whether the figure came from host DRAM",
           '_dram_used_kind = "host" if dram_used_gb > 0 else ""' in iv, True)
    _check("set where the token derivation happens",
           iv.count('_dram_used_kind = "l2kv"'), 3)
    _check("the note says it is not host DRAM",
           "NOT host DRAM usage" in iv, True)
    _check("and points at the physical figure",
           "L2 host DRAM used — raw" in iv, True)
    _check("a setup-provided figure is still called host DRAM",
           '_dram_label = "GPU node host DRAM used"' in iv, True)
    _check("the old unconditional 'host DRAM' note is gone",
           '_dram_note = f"{_dram_pct:.0f}% full · host DRAM"' in iv, False)

    print("\nThe scanner catches the shadowing shape that bit three times")
    # Run it, rather than reading it: a probe for the function's name passed
    # even with the scan stubbed out to return nothing.
    import subprocess as _sp
    _sh = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_shadow_"))
    try:
        _bug = _sh / "bug.py"
        _bug.write_text(
            "import html\n"
            "import html as _html\n"
            "import re\n"
            "def build(m):\n"
            "    e = html.escape\n"          # shadowed by the assignment below
            "    html = f'<p>{m}</p>'\n"
            "    return e(html)\n"
            "def outer():\n"
            "    def g(_html):\n"            # parameter shadows the alias
            "        return _html.unescape(_html)\n"
            "    return g('x')\n")
        _r = _sp.run([sys.executable,
                      str(_ROOT / "scripts" / "check_unbound_locals.py"),
                      str(_bug)], capture_output=True, text=True)
        _check("the scanner fails on a file with both shadow shapes",
               _r.returncode, 1)
        _check("naming the assignment shadow",
               "shadowed by a assignment" in _r.stdout, True)
        _check("and the parameter shadow",
               "shadowed by a parameter" in _r.stdout, True)
        _check("reporting html.escape", "html.escape" in _r.stdout, True)
        _check("and _html.unescape", "_html.unescape" in _r.stdout, True)

        _ok = _sh / "ok.py"
        _ok.write_text(
            "import html\n"
            "import re\n"
            "def find(html):\n"             # str.find exists: not a fault
            "    return html.find('<div')\n"
            "def sub():\n"
            "    return re.sub('a', 'b', 'aaa')\n")
        _r2 = _sp.run([sys.executable,
                       str(_ROOT / "scripts" / "check_unbound_locals.py"),
                       str(_ok)], capture_output=True, text=True)
        _check("and passes a file whose shadow is harmless",
               _r2.returncode, 0)
        _check("without reporting the legitimate str method",
               "html.find" in _r2.stdout, False)

        # The whole point of the change: a bare run must scan something.
        _r3 = _sp.run([sys.executable,
                       str(_ROOT / "scripts" / "check_unbound_locals.py")],
                      capture_output=True, text=True, cwd=str(_ROOT))
        _check("a bare run scans the package and passes", _r3.returncode, 0)
        _check("reporting a non-zero file count",
               "0 file(s) scanned" in _r3.stdout, False)
        _check("and running both scans, not just the first",
               "shadowed-import" in _r3.stdout, True)
    finally:
        shutil.rmtree(_sh, ignore_errors=True)

    print("\nThe source carries the live-vs-cumulative separation")
    a = (_ROOT / "amoprof" / "report" / "amoprof.py").read_text()
    _check("the cumulative total has its own field",
           "kv_context_tokens_total" in a, True)
    _check("and that is what prefill_cache + prefill_compute is assigned to",
           "m.kv_context_tokens_total = total_ctx" in a, True)
    _check("kv_active_tokens is assigned the live pool figure",
           "m.kv_active_tokens = l1_used" in a, True)
    _check("the min()-against-capacity fallback is gone",
           "l1_used = min(m.kv_active_tokens, l1_cap)" in a, False)
    _check("replaced by the pool-fill derivation",
           "l1_used = safe_int(m.kv_pool_fill_pct / 100.0 * l1_cap)" in a, True)
    _check("HBM utilisation is the live figure over the pool",
           "l1_used / m.kv_hbm_max_tokens * 100" in a, True)
    _check("the card no longer calls a cumulative total live",
           "live tokens / pool" not in a.split("# ")[0]
           and "{m.kv_active_tokens:,} live tokens / pool" not in a, True)
    _check("the card states the capacity the live count is a fraction of",
           "live tokens of {m.kv_l1_capacity_tokens:,}" in a, True)
    _check("and where the figure came from",
           "m.kv_pool_fill_source" in a, True)
    _check("the fill gauge is a window mean, not a last sample",
           "float(_tu.mean())" in a, True)
    _check("with a peak beside it",
           "m.kv_pool_fill_peak_pct = round(float(_tu.max())" in a, True)
    _check("a 0-100 gauge is rescaled rather than read as a fraction",
           "_tu_scale" in a, True)
    _check("the last-sample derivation of l1_used is removed",
           "l1_used = safe_int(_fu_ts * l1_cap)" in a, False)

    print("\nThe chunked-prefill advice no longer calls a run total a context")
    _check("it uses per-request prompt length",
           "mean prompt of" in a and "sess_input_tok_mean:,.0f} tokens per "
           "request" in a, True)
    _check("the cumulative sum is no longer offered as the context",
           "is driven by long context ({m.prefill_cache_tokens+"
           "m.prefill_compute_tokens:,} tokens)" in a, False)
    _check("and it says so when the per-request figure is unavailable",
           "whether long context is the cause is unconfirmed" in a
           or "is unconfirmed here" in a, True)

    print("\nThe capacity fallback reaches the metrics builder too")
    _check("ssd_hw_summary is read there", '"ssd_hw_summary"' in a, True)
    _check("only to fill gaps, never to override smart_summary",
           "if not _smart_s.get(_k_hw) and _ssd_hw_s.get(_k_hw)" in a, True)
    _check("on a copy, since the loader payload is shared",
           "_smart_s = dict(_smart_s)" in a, True)

    print("\nAnd the carrier cannot be unbound in the report")
    c = (_ROOT / "amoprof" / "report" / "combined.py").read_text()
    _lines = c.splitlines()
    _bind = next(i for i, l in enumerate(_lines, 1)
                 if "_tier_fill: dict = {" in l)
    _fill = next(i for i, l in enumerate(_lines, 1)
                 if "_tier_fill = _amoprof_tier_fill_from_occupancy(_occ)" in l)
    _try = max(i for i, l in enumerate(_lines, 1)
               if i < _fill and l.strip() == "try:")
    _check("it is bound before the try that fills it", _bind < _try, True)
    _check("seeded with a reason for every tier, so the tiles still explain "
           "themselves if that block raises",
           "tier-occupancy resolution did not complete" in c, True)
    _check("the tiles are read off the chart's own series, not recomputed",
           "_amoprof_tier_fill_from_occupancy(_occ)" in c, True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
