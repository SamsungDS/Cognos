#!/usr/bin/env python3
"""Six things a v1.69.0 mooncake report said that it also contradicted.

Run: python3 tests/test_l35_report_consistency.py

From that report, with its own figures:

1. "KV cache generated this run — not collected", because
   sglang_prompt_tokens_total and sglang_generation_tokens_total are not
   exported on that deployment. Two tiles above it, the cache-hit tile was
   computing a percentage from Δrealtime_tokens_total{mode="prefill_cache"}
   and {mode="prefill_compute"}; further down, the output-token chart carried
   the footnote "fallback (generation_tokens_total absent)" and read
   {mode="decode"}. Every input existed. Only this tile did not look.

2. "L3 cache used — raw (df snapshot) 25 / 3575 GB" and "L3 KV residency
   46,737 tok" on a run whose backing tier is Mooncake: df on the HiCache
   path still sees files from an earlier local-L3 run, and l3_explicit_config
   is true for any L3 backend. The mirror image of the L3.5-on-a-local-run
   leak fixed in v1.70.0, and it fires on the same cluster for the same
   reason.

3. "L2 KV residency (est.) 202.4 GB / 210 GB · 97% full" against "L2 host
   DRAM used — raw (physical) 70.4 GB". The note already described the
   estimate as "bounded above by raw physical DRAM" and warned that it was
   2.9x that bound. KV in host DRAM cannot exceed resident DRAM, so neither
   202.4 GB nor the 97% was possible.

4. "L3.5 KV→NAND total 0.00x" — the guard its KV→host sibling received was
   added in one place and not the other.

5. "L3.5 (AI Memory Node / remote storage) read BW 17 MB/s · write BW 0.0
   MB/s", fed by nvme_driver_timeseries.csv — the GPU node's own device —
   while the memory node's iostat reported 995 MB/s of writes in a different
   tile. A post-render substitution in amoprof.py rewrites every "L3 (local
   storage)" to the tier's long name; it changed the label and not the source.
   Each direction is independently device-measured or token-derived, which is
   why one label cannot cover both.

6. "E2E mean 79341 ms" and "TTFT mean 79341 ms" — equal to the millisecond
   with TPOT at 307.4 ms/tok. E2E is TTFT plus decode, so that holds only for
   one-token responses, and this run's decode counter did not resolve, so
   neither figure could be checked against the other.
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

CACHED, COMPUTE, DECODE = 68_036_418, 10_500_000, 220_000
L2_EST_GB, L2_PHYS_GB, L2_PHYS_PEAK_GB = 202.4, 70.4, 79.8
TTFT_MS = E2E_MS = 79341.0
TPOT_MS = 307.4
N = 20


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _mk(base, *, backend="mooncake", with_cumulative=False,
        wr_bw_local=0.0, e2e_ms=E2E_MS):
    """A run shaped like that report: realtime modes but no cumulative token
    counters, a near-idle local NVMe, a busy memory node, and stale df data
    on the GPU node's HiCache path."""
    raw = base / "raw"
    raw.mkdir(parents=True)
    cols = ["time_sec",
            "sglang_realtime_tokens_total[mode=prefill_cache]",
            "sglang_realtime_tokens_total[mode=prefill_compute]",
            "sglang_realtime_tokens_total[mode=decode]",
            "sglang_hicache_host_used_tokens",
            "sglang_hicache_host_total_tokens",
            "sglang_max_total_num_tokens", "sglang_full_token_usage",
            "sglang_backuped_tokens_total", "sglang_prefetched_tokens_total",
            "sglang_time_to_first_token_seconds_sum",
            "sglang_time_to_first_token_seconds_count",
            "sglang_e2e_request_latency_seconds_sum",
            "sglang_e2e_request_latency_seconds_count",
            "sglang_inter_token_latency_seconds_sum",
            "sglang_inter_token_latency_seconds_count"]
    if with_cumulative:
        cols += ["sglang_prompt_tokens_total", "sglang_generation_tokens_total"]
    rows = []
    for i in range(N):
        f = i / (N - 1)
        r = [i * 90.0, int(CACHED * f), int(COMPUTE * f), int(DECODE * f),
             int(380_000 * f), 392_307, 196_153, round(0.5 * f, 4),
             int(4_000_000 * f), int(900_000 * f),
             TTFT_MS * f, int(1000 * f),
             e2e_ms * f, int(1000 * f),
             TPOT_MS / 1000.0 * 72_000 * f, int(72_000 * f)]
        if with_cumulative:
            r += [int(90_000_000 * f), int(DECODE * f)]
        rows.append(r)
    raw.joinpath("sglang_timeseries.csv").write_text(
        ",".join(cols) + "\n"
        + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n")
    raw.joinpath("setup_details.json").write_text(json.dumps({
        "Model": "google/gemma-4-31b-it", "TP size": 8,
        "HiCache storage backend": backend, "HiCache ratio": 2.0,
        "Launch command": ("python3 -m sglang.launch_server "
                           f"--hicache-storage-backend {backend}")}))
    raw.joinpath("model_config.json").write_text(json.dumps(
        {"num_hidden_layers": 60, "num_key_value_heads": 16,
         "head_dim": 256, "torch_dtype": "bfloat16"}))
    raw.joinpath("gpu_summary.json").write_text(json.dumps(
        {"gpu_count": 8, "hbm_used_gb_mean": 33.1, "hbm_total_gb": 40.0,
         "gpu_util_mean": 95.5}))
    raw.joinpath("dram_summary.json").write_text(json.dumps(
        {"dram_total_gb": 1008.0, "dram_used_gb_mean": L2_PHYS_GB,
         "dram_used_gb_peak": L2_PHYS_PEAK_GB}))
    raw.joinpath("ssd_hw_summary.json").write_text(json.dumps(
        {"hicache_fs_total_gb": 3575.0, "hicache_fs_used_gb": 25.0,
         "hicache_fs_avail_gb": 3550.0, "hicache_fs_used_pct": 0.7,
         "nvme_device_capacity_gb": 3577.0}))
    raw.joinpath("nvme_driver_timeseries.csv").write_text(
        "time_sec,rd_bw_mbs,wr_bw_mbs,rd_iops,wr_iops,avgqu_sz,util_pct\n"
        + "\n".join(f"{i*90.0},17.0,{wr_bw_local},40,0,0.01,1.0"
                    for i in range(N)) + "\n")
    raw.joinpath("l35_storage_timeseries.csv").write_text(
        "time_sec,l35_cpu_util_pct,l35_rd_bw_mbs,l35_wr_bw_mbs,"
        "l35_avgqu_sz,l35_io_util_pct,l35_host_written_gb,"
        "l35_nand_written_gb,l35_waf\n"
        + "\n".join(f"{i*90.0},9.7,0.0,{995.0 if i == 5 else 120.0},"
                    f"{0.34 if i != 7 else 1.0},12.0,"
                    f"{100.0 + i*0.75},{98.0 + i*0.73},0.98"
                    for i in range(N)) + "\n")
    raw.joinpath("l35_store_capacity.csv").write_text(
        "time_sec,l35_store_mem_used_b,l35_store_mem_cap_b,"
        "l35_store_file_used_b,l35_store_file_cap_b\n"
        + "\n".join(f"{i*90.0},{519.6e9},{537e9},{871.7e9},{2000e9}"
                    for i in range(N)) + "\n")
    return raw


def main() -> int:
    sys.path.insert(0, str(_ROOT / "tests"))
    from test_tier_residency_tiles import _tiles
    from amoprof.report.combined import build_executive_summary_html as _b

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_l35c_"))
    try:
        tl = _tiles(_b(_mk(tmp / "l35"), run_label="l35"))

        print("\n1. The token totals were derivable all along")
        _kvg = tl["KV cache generated this run"]
        _check("the tile is no longer 'not collected'", _kvg[0]
               != "not collected", True)
        _check("prompt is prefill_cache + prefill_compute",
               f"{CACHED + COMPUTE:,} prompt" in _kvg[1], True)
        _check("cached is the prefill_cache mode",
               f"{CACHED:,} cached" in _kvg[1], True)
        _check("decode is the decode mode",
               f"{DECODE:,} decode" in _kvg[1], True)
        _check("so the computed total is compute + decode",
               f"{COMPUTE + DECODE:,} tokens of KV actually computed"
               in _kvg[1], True)
        _check("and the derivation is named, not silently substituted",
               "prompt derived as" in _kvg[1], True)
        _check("saying which counter is absent",
               "sglang_prompt_tokens_total is not exported here" in _kvg[1],
               True)
        _check("and the same for decode",
               "sglang_generation_tokens_total is not exported here"
               in _kvg[1], True)
        # A deployment that DOES export the cumulative counters must still
        # prefer them: they are the counters the formula is written against.
        _tlc = _tiles(_b(_mk(tmp / "cum", with_cumulative=True),
                         run_label="cum"))
        _check("a run with the cumulative counters uses those instead",
               "prompt derived as"
               in _tlc["KV cache generated this run"][1], False)
        _check("and reports their larger prompt total",
               "90,000,000 prompt" in _tlc["KV cache generated this run"][1],
               True)

        print("\n1b. Whichever way the label was expanded into a column")
        # The column name depends on how the fetch flattened the Prometheus
        # label, and that is not visible from a report. The resolver requires
        # both "realtime_tokens_total" and "mode=<phase>" as substrings, so
        # every expansion that carries both is matched -- which is the only
        # reason this can be promised without seeing the CSV.
        import re as _re2
        _forms = {
            "bracket": "sglang_realtime_tokens_total[mode={m}]",
            "brace_quoted": 'sglang_realtime_tokens_total{{mode="{m}"}}',
            "brace_bare": "sglang_realtime_tokens_total{{mode={m}}}",
            "prom_colon": "sglang:realtime_tokens_total[mode={m}]",
            "trailing_label": "sglang_realtime_tokens_total_mode={m}",
        }
        for _fname, _tmpl in _forms.items():
            _fr = _mk(tmp / f"form_{_fname}")
            _fp = _fr / "sglang_timeseries.csv"
            _lines = _fp.read_text().splitlines()
            _hdr = _lines[0].split(",")
            for _i, _h in enumerate(_hdr):
                for _mode in ("prefill_cache", "prefill_compute", "decode"):
                    if f"mode={_mode}" in _h:
                        _hdr[_i] = _tmpl.format(m=_mode)
            _fp.write_text(",".join(_hdr) + "\n"
                           + "\n".join(_lines[1:]) + "\n")
            _fv = _tiles(_b(_fr, run_label=_fname))[
                "KV cache generated this run"][0]
            _check(f"the {_fname} form resolves", _fv != "not collected", True)
            _check(f"and gives the same figure ({_fname})", _fv, "9,814.5 GB")
        # A column carrying only ONE of the two substrings must not match: a
        # prompt-token counter is not a phase counter.
        _wr = _mk(tmp / "wrongcol")
        _wp = _wr / "sglang_timeseries.csv"
        _wl = _wp.read_text().splitlines()
        _wh = [("sglang_realtime_tokens_total" if "mode=" in _h else _h)
               for _h in _wl[0].split(",")]
        _wp.write_text(",".join(_wh) + "\n" + "\n".join(_wl[1:]) + "\n")
        # A server restart inside the window resets the counters. last-first
        # then under-reports by everything before the reset; the sum of
        # positive per-step differences does not. A monotonic fixture cannot
        # tell the two apart, which is why this case exists.
        _rr = _mk(tmp / "reset")
        _rp = _rr / "sglang_timeseries.csv"
        _rl = _rp.read_text().splitlines()
        _rhdr = _rl[0].split(",")
        _ridx = {_m: _i for _i, _h in enumerate(_rhdr)
                 for _m in ("prefill_cache", "prefill_compute", "decode")
                 if f"mode={_m}" in _h}
        _rout = [_rl[0]]
        _half = (len(_rl) - 1) // 2
        for _n, _line in enumerate(_rl[1:]):
            _f = _line.split(",")
            if _n >= _half:
                # restart: the counters begin again from zero
                for _m, _i in _ridx.items():
                    _f[_i] = str(int(float(_f[_i]))
                                 - int(float(_rl[1 + _half].split(",")[_i])))
            _rout.append(",".join(_f))
        _rp.write_text("\n".join(_rout) + "\n")
        _rv = _tiles(_b(_rr, run_label="reset"))[
            "KV cache generated this run"][1]
        _m_tok = _re2.search(r"([\d,]+) tokens of KV actually computed", _rv)
        _check("a counter reset inside the window still resolves",
               _m_tok is not None, True)
        _got_tok = int(_m_tok.group(1).replace(",", "")) if _m_tok else 0
        # Summing positive steps keeps both halves; last-first keeps only the
        # second, which on this fixture is a little over half.
        _check("and keeps the pre-reset traffic",
               _got_tok > (COMPUTE + DECODE) * 0.9, True)
        _check("where last-minus-first would lose most of it",
               _got_tok > (COMPUTE + DECODE) * 0.55, True)

        _check("a column missing the mode label does not match",
               _tiles(_b(_wr, run_label="w"))[
                   "KV cache generated this run"][0], "not collected")
        # And the complement: a column carrying the mode label but NOT
        # realtime_tokens_total is a different metric. The decoy has to sit
        # BESIDE the real column and earlier in the header, because that is
        # the only arrangement where a one-substring spec picks the wrong one
        # -- a fixture with the real columns removed says nothing, since
        # neither spec finds anything.
        _dr = _mk(tmp / "decoy")
        _dp = _dr / "sglang_timeseries.csv"
        _dl = _dp.read_text().splitlines()
        _dh = _dl[0].split(",")
        _decoys = {
            "decode": "sglang_phase_latency_seconds_count[mode=decode]",
            "prefill_compute":
                "sglang_phase_latency_seconds_count[mode=prefill_compute]",
            "prefill_cache":
                "sglang_phase_latency_seconds_count[mode=prefill_cache]",
        }
        # Flat series: a decoy that moved would be indistinguishable from a
        # token counter, and the point is which COLUMN was chosen.
        _dh2 = [_dh[0]] + list(_decoys.values()) + _dh[1:]
        _rows2 = []
        for _line in _dl[1:]:
            _f = _line.split(",")
            _rows2.append(",".join([_f[0], "5000", "5000", "5000"] + _f[1:]))
        _dp.write_text(",".join(_dh2) + "\n" + "\n".join(_rows2) + "\n")
        _dv = _tiles(_b(_dr, run_label="d"))["KV cache generated this run"]
        _check("the decoy does not displace the real phase counters",
               _dv[0], "9,814.5 GB")
        _check("so the figure is unchanged by its presence",
               f"{COMPUTE + DECODE:,} tokens of KV actually computed"
               in _dv[1], True)

        print("\n2. Stale local-L3 tiles do not appear on a remote run")
        _check("no L3 cache-used tile",
               [k for k in tl if k.startswith("L3 cache used")], [])
        _check("no L3 KV residency tile",
               [k for k in tl if k.startswith("L3 KV residency")], [])
        _check("while the backing tier's own tiles are present",
               len([k for k in tl if k.startswith("L3.5")]) >= 4, True)
        _tlf = _tiles(_b(_mk(tmp / "local", backend="file"),
                         run_label="local"))
        _check("and a local run keeps them",
               [k for k in _tlf if k.startswith("L3 cache used")] != [], True)
        _check("with no L3.5 tiles of its own",
               [k for k in _tlf if k.startswith("L3.5")], [])

        print("\n3. The L2 estimate is held to its own stated bound")
        _l2 = tl["L2 KV residency (est.)"]
        _check("the headline is the physical residency",
               _l2[0].startswith(f"{L2_PHYS_GB} GB"), True)
        _check("not the token-derived figure",
               "202.4 GB /" in _l2[0] or "174.0 GB /" in _l2[0], False)
        _check("the note says it was capped",
               "capped at the physical residency" in _l2[1], True)
        _check("naming the estimate it rejected",
               "the token-derived estimate was" in _l2[1], True)
        _check("and why that estimate cannot stand",
               "cannot exceed the DRAM that is resident" in _l2[1], True)
        # The percentage and the peak are composed from the same variables,
        # so capping afterwards left "97% full" and an uncapped peak in a
        # note whose headline had already been corrected.
        _check("the percentage follows the capped figure",
               "97% full" in _l2[1], False)
        _check("and so does the peak",
               f"peak {L2_PHYS_PEAK_GB} GB" in _l2[1], True)
        _check("the raw tile is unchanged",
               tl["L2 host DRAM used — raw (physical)"][0],
               f"{L2_PHYS_GB} GB / 1,008 GB")

        print("\n4. KV→NAND gets the guard its sibling got")
        _nand = tl["L3.5 KV→NAND total"]
        _check("it is not published as 0.00x", _nand[0] == "0.00x", False)
        _check("it says unreconciled", _nand[0], "unreconciled")
        _check("naming the gap", "apart." in _nand[1], True)
        _check("and why the ratio cannot be below 1",
               "cannot be below 1" in _nand[1], True)

        print("\n5. A local device does not wear the remote tier's name")
        _check("the read tile names the device it measured",
               "GPU node local NVMe read BW" in tl, True)
        _check("reporting the local series' value",
               tl["GPU node local NVMe read BW"][0], "17 MB/s")
        _check("no tile claims that figure for the backing tier",
               [k for k in tl
                if "remote storage) read BW" in k or "L3.5 read BW" in k], [])
        _check("while the memory node's own device tile is still there",
               [k for k in tl if "node storage BW (device)" in k] != [], True)
        _check("and it reports the node's 995 MB/s peak",
               "995 wr MB/s peak" in
               [v for k, (v, _n) in tl.items()
                if "node storage BW (device)" in k][0], True)
        # Each direction is independently device-measured or token-derived,
        # so a token-derived figure keeps the tier label it belongs to.
        _tle = _tiles(_b(_mk(tmp / "est", wr_bw_local=0.0), run_label="est"))
        _check("a token-derived write keeps the tier label",
               [k for k in _tle if k.endswith("write BW")
                and "GPU node local NVMe" not in k] != [], True)
        _tld = _tiles(_b(_mk(tmp / "dev", wr_bw_local=12.0), run_label="dev"))
        _check("a device-measured write takes the device label",
               "GPU node local NVMe write BW" in _tld, True)
        _check("with the device's own value",
               _tld["GPU node local NVMe write BW"][0], "12.0 MB/s")

        print("\n6. E2E equal to TTFT is stated, not left to be noticed")
        _e2e = tl["E2E mean"]
        _check("the tile says they are identical",
               "identical to TTFT mean" in _e2e[1], True)
        _check("explaining that E2E is TTFT plus decode",
               "E2E is TTFT plus decode" in _e2e[1], True)
        _check("naming the TPOT that makes it implausible",
               f"{TPOT_MS} ms/tok" in _e2e[1], True)
        _check("and the decode count that contradicts it",
               f"{DECODE:,} tokens" in _e2e[1], True)
        # A run where the two genuinely differ must carry no such note.
        _tlx = _tiles(_b(_mk(tmp / "diff", e2e_ms=TTFT_MS + 40_000.0),
                         run_label="diff"))
        _check("a run with distinct latencies is not flagged",
               "identical to TTFT mean" in _tlx["E2E mean"][1], False)
        _check("and its E2E exceeds its TTFT",
               _tlx["E2E mean"][0] != _tlx["TTFT mean"][0], True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
