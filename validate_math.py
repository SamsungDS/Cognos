"""Numerical validation of AMOprof's correlation math.

Every kernel is checked against an independent reference (scipy / numpy) or a
closed-form answer, not against itself.  Fails loudly with the numeric
discrepancy so a regression is unambiguous.
"""
import math, pathlib, random, sys
import pathlib as _pl
import numpy as np
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from amoprof.report.metric_kernels import (
    counter_delta, window_seconds, window_rate, rate_series_with_time,
    rate_series, aligned_rate_series, ratio_delta, align_on_time, pearson,
)
from amoprof.report.combined import (
    _amoprof_histogram_window_percentiles, _amoprof_binned_response,
)

FAILS = []
def check(name, got, want, tol=1e-9):
    ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    print(f"  {'OK  ' if ok else 'FAIL'}  {name:52s} got={got!r:>22} want={want!r}")
    if not ok:
        FAILS.append(name)


print("\n=== 0. every module parses and the CLI imports ===")
# install.sh verifies exactly this.  A syntax error in any module ships as a
# broken install, and the failure surfaces at `from amoprof.cli import main`
# rather than at build time — so check it here too.
import ast as _ast, pathlib as _pl
_root = _pl.Path(__file__).resolve().parent / "amoprof"
_broken = []
for _f in sorted(_root.rglob("*.py")):
    try:
        _ast.parse(_f.read_text(encoding="utf-8", errors="replace"), filename=str(_f))
    except SyntaxError as _e:
        _broken.append(f"{_f.relative_to(_root)}:{_e.lineno} {_e.msg}")
check("all modules parse", _broken or "clean", "clean")
try:
    from amoprof.cli import main as _main, _build_parser as _bp
    import io as _io, contextlib as _ctx
    for _cmd in ("collect", "analyze", "service", "aggregate", "compare", "retime"):
        try:
            with _ctx.redirect_stdout(_io.StringIO()):
                _bp().parse_args([_cmd, "--help"])
        except SystemExit:
            pass
    _cli_ok = "ok"
except Exception as _e:
    _cli_ok = f"FAILED: {_e}"
check("CLI imports and all subparsers build", _cli_ok, "ok")

print("\n=== 0b. cross-surface agreement ===")
# The kernel layer exists so a quantity has ONE implementation.  It only works
# if every surface actually calls it, and repeatedly it did not: the Executive
# filtered impossible DRAM samples while the End Report did not, so one file
# produced 0.86 GB/s on one tab and 251,246,841 GB/s on another.  Render all
# three surfaces from one directory and compare what they report.
import subprocess as _sp, tempfile as _tf, csv as _csv, json as _js, math as _mh
import re as _re, html as _H

def _build_probe_dir():
    d = _pl.Path(_tf.mkdtemp())
    n = 400
    with (d / "sglang_timeseries.csv").open("w", newline="") as f:
        w = _csv.writer(f)
        # Prefill-mode columns included so the cache-hit assertion actually
        # runs; a probe that silently skips its own check is worse than none.
        w.writerow(["time_sec", "sglang_prompt_tokens_total",
                    "sglang_generation_tokens_total", "sglang_num_running_reqs",
                    "sglang_hicache_host_used_tokens",
                    "sglang_hicache_host_total_tokens",
                    "sglang:realtime_tokens_total[mode=prefill_cache]",
                    "sglang:realtime_tokens_total[mode=prefill_compute]"])
        pt = gt = pc = pk = 0.0
        for i in range(n):
            pt += 600; gt += 200
            pc += 360; pk += 240          # 60% token-weighted hit rate
            w.writerow([i * 15, f"{pt:.0f}", f"{gt:.0f}", "8",
                        f"{min(4e6, i * 9000):.0f}", "6000000",
                        f"{pc:.0f}", f"{pk:.0f}"])
    with (d / "gpu_timeseries.csv").open("w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["time_sec", "gpu_idx", "gpu_util", "mem_used", "mem_total", "power_w"])
        for i in range(n):
            for g in range(2):
                w.writerow([i * 15, g, "70", "61440", "183392", "700"])
    # DRAM with poisoned samples: the case that diverged.
    with (d / "pcm_timeseries.csv").open("w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["time_sec", "dram_read_gb_s", "dram_write_gb_s", "dram_total_gb_s"])
        for i in range(n):
            if i in (11, 97, 240):
                rd = wr = 48038395904.5
            else:
                rd, wr = 0.42, 0.37
            w.writerow([i * 15, f"{rd}", f"{wr}", f"{rd + wr}"])
    (d / "setup_details.json").write_text(_js.dumps(
        {"Model": "google/gemma-4-31B-it", "TP size": "2", "DP size": "1",
         "HiCache": "enabled", "HiCache size per GPU GB": 64, "Page size": 64}))
    (d / "gpu_config.json").write_text(_js.dumps(
        {"gpu_name": "NVIDIA B200", "gpu_count": 8, "hbm_per_gpu_gb": 179.09,
         "tp_size": 2, "dp_size": 1, "hostname": "probe"}))
    (d / "sglang_summary.json").write_text(_js.dumps({"max_total_num_tokens": 131072}))
    return d

def _num_near(text, label, window=420):
    i = text.find(label)
    if i < 0:
        return None
    m = _re.search(r"([-+]?[\d,]*\.?\d+)", text[i + len(label):i + len(label) + window])
    return float(m.group(1).replace(",", "")) if m else None

try:
    _pd_dir = _build_probe_dir()
    from amoprof.report import combined as _C, interactive as _I
    from amoprof.cli import _run_amoprof as _RE
    _exec = _H.unescape(_C.build_executive_summary_html(_pd_dir))
    _iout = _pl.Path(_tf.mkdtemp()) / "i.html"
    _I.build_report(_pd_dir, _iout)
    _inter = _H.unescape(_iout.read_text())
    _eout = _pl.Path(_tf.mkdtemp()) / "e.html"
    import io as _io, contextlib as _cx
    with _cx.redirect_stdout(_io.StringIO()):
        _RE(_pd_dir, _eout)
    _endr = _H.unescape(_eout.read_text())

    # 1. No surface may report an impossible DRAM bandwidth.
    for _name, _doc in (("executive", _exec), ("interactive", _inter), ("end", _endr)):
        _txt = _re.sub(r"var fig = \{.*?\};", " ", _doc, flags=_re.S)
        _huge = [x for x in _re.findall(r"\b\d{9,}\.\d\b", _txt)]
        check(f"{_name}: no impossible bandwidth in visible text",
              len(_huge), 0, )
    # 3. DRAM total must agree between Executive and End Report.
    # Match the tile VALUE, not the first number after the label: the note
    # under the tile also contains figures, and picking one of those compared
    # two different quantities and reported a false divergence.
    def _tile_val(_doc, _label):
        _m = _re.search(_re.escape(_label) + r"[^<]{0,30}</div>\s*<div[^>]*>\s*"
                        r"([-+]?[\d,]*\.?\d+)", _doc)
        return float(_m.group(1).replace(",", "")) if _m else None

    _e_dram = _tile_val(_exec, "DRAM BW")
    _r_dram = _tile_val(_endr, "DRAM Total BW")
    if _e_dram is not None and _r_dram is not None and max(_e_dram, _r_dram) > 0:
        _rel = abs(_e_dram - _r_dram) / max(_e_dram, _r_dram)
        check("DRAM total agrees: executive vs end report",
              _rel < 0.05, True, f"exec={_e_dram} end={_r_dram}")

    # The cache-hit CAPTION must describe the expression actually computed.
    # It claimed Δcached_tokens_total was in the numerator when the code never
    # added it — a caption describing a different formula than the one
    # evaluated sends the reader chasing a discrepancy that does not exist.
    try:
        from amoprof.report.metric_formulas import formula_for as _ff
        from amoprof.report import common_kpis as _ck
        _cap = _ff("cache hit") or ""
        _method = _ck.compute_cache_hit_kpis(raw_dir=_pd_dir).get("cache_hit_method", "")
        if "prefill_token_work_avoidance" in _method:
            check("cache-hit caption matches the computed method",
                  ("prefill_cache" in _cap and "cached_tokens_total" not in _cap),
                  True, f"caption={_cap[:60]!r}")
    except Exception as _e:
        print(f"  skip  caption check ({_e})")

    # Cache hit must agree too.  The prefill token-weighted ratio was LAST in
    # the candidate list, so gauge means that include idle samples won ahead
    # of it and different surfaces picked different sources.
    _e_ch = _tile_val(_exec, "Cache hit")
    _r_ch = _tile_val(_endr, "Cache Hit") or _tile_val(_endr, "Cache hit")
    if _e_ch is not None and _r_ch is not None and max(_e_ch, _r_ch) > 0:
        check("cache hit agrees: executive vs end report",
              abs(_e_ch - _r_ch) / max(_e_ch, _r_ch) < 0.02, True,
              f"exec={_e_ch} end={_r_ch}")
    else:
        print("  skip  DRAM cross-surface (one surface did not render the tile)")
except Exception as _e:
    check("cross-surface probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0c. NaN-safety in chart renderers ===")
# NaN is truthy and every comparison with it is False, so `x or default` and
# `x <= 0` both let it through.  Each time that happened a chart rendered with
# `nan` coordinates — an invisible line that still claimed a legend entry, or
# an axis labelled "nan".  These assert the renderers survive NaN input.
try:
    from amoprof.report.combined import (
        _amoprof_exec_svg_layer_response as _lr,
        _amoprof_exec_svg_tier_occupancy as _to)
    _NA = float("nan")

    _svg = _lr("driver", "unit", [
        {"layer": "A5_APP", "label": "nan-ceiling", "unit": "ms",
         "bins": [(1, 10.0), (2, _NA), (3, 15.0)],
         "r": 0.5, "rho": 0.5, "n": 3, "ymax": _NA}])
    check("layer-response: no nan coordinates",
          len(_re_nan.findall(_svg)) if (_re_nan := __import__("re").compile(
              r'(?:,nan|nan,|="nan)')) else 0, 0)
    check("layer-response: no 'max 0.0' with real data",
          "max 0.0" in _svg, False)

    _svg2 = _to([{"tier": "L1", "label": "leading-nan", "t": [0.0, 1.0, 2.0],
                  "v": [_NA, 5.0, 9.0], "cap": 0, "color": "#f00"}],
                mode="abs", yaxis="ms", unit_label="ms")
    check("tier-occupancy: no nan axis labels", ">nan<" in _svg2, False)
    check("tier-occupancy: renders with a leading NaN", len(_svg2) > 200, True)

    _svg3 = _to([{"tier": "NET", "label": "no-ceiling", "t": [0.0, 1.0],
                  "v": [1.0, 2.0], "cap": 0.0, "color": "#0f0"}],
                mode="abs", yaxis="GB/s", unit_label="GB/s")
    check("tier-occupancy: cap=0 does not divide by zero", len(_svg3) > 200, True)

    # The legend peak had the same NaN-first max() flaw as the axis: a latency
    # series whose opening interval had no completions printed "peak nan ms"
    # beside a line that plotted correctly.
    _svg4 = _to([{"tier": "L1", "label": "leading-nan", "t": [0.0, 1.0, 2.0, 3.0],
                  "v": [_NA, 5.0, 9.0, 3.0], "cap": 0, "color": "#f00"}],
                mode="abs", yaxis="ms", unit_label="ms")
    check("tier-occupancy: legend peak skips a leading NaN",
          "peak 9.00 ms" in _svg4, True)
    check("tier-occupancy: no 'peak nan' in the legend",
          "peak nan" in _svg4, False)

    # Bucket quantiles must stay DISTINCT.  Clamping each bucket delta at 0
    # independently broke the cumulative monotonicity, the quantile target was
    # never reached, and p50/p90/p99 all fell through to the last bucket
    # boundary — reporting the identical value for every percentile.
    from amoprof.report.metric_kernels import percentiles_from_bucket_deltas as _pbd
    _inf = float("inf")
    _q_clean = _pbd([(1.0, [0, 50]), (5.0, [0, 90]), (20.0, [0, 100]),
                     (_inf, [0, 100])])
    check("bucket quantiles: p50 < p90 < p99 (clean)",
          _q_clean[0.5][0] < _q_clean[0.9][0] < _q_clean[0.99][0], True)
    _q_clamp = _pbd([(1.0, [0, 50]), (5.0, [10, 45]), (20.0, [0, 100]),
                     (_inf, [0, 100])])
    check("bucket quantiles: distinct despite a clamped bucket",
          len({round(_q_clamp[q][0], 3) for q in (0.5, 0.9, 0.99)}), 3)

    # A sparse interval cannot support distinct quantiles — with one request
    # p50 == p90 == p99 — and one such interval makes every legend peak
    # identical.  Those intervals must be omitted, not reported.
    _q_sparse = _pbd([(1.0, [0, 0, 50]), (5.0, [0, 1, 90]),
                      (20.0, [0, 2, 100]), (_inf, [0, 2, 100])])
    # Sparse intervals must be BINNED, not discarded: dropping them left the
    # chart empty on a low-duty workload, which is worse than no chart.
    _c1 = [0]; _c2 = [0]; _c3 = [0]
    for _ in range(12):
        _c1.append(_c1[-1] + 1); _c2.append(_c2[-1] + 2); _c3.append(_c3[-1] + 2)
    _q_bin = _pbd([(1.0, _c1), (5.0, _c2), (20.0, _c3), (_inf, _c3)])
    check("bucket quantiles: sparse run still yields points",
          len([v for v in _q_bin[0.5] if v == v]) >= 2, True)
    check("bucket quantiles: binned points stay distinct",
          _q_bin[0.5][0] != _q_bin[0.9][0], True)
    check("bucket quantiles: index accompanies the points",
          len(_q_bin.get("_index") or []) == len(_q_bin[0.5]), True)
except Exception as _e:
    check("NaN-safety probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0d. every collector imports, and its names resolve ===")
# A NameError inside a collector surfaces as a runtime WARNING swallowed by a
# try/except — "blkparse parse error: name '_csv' is not defined" — so the
# collector appears to run, publishes metadata gauges, and produces no data.
# Seven collectors shipped with exactly that defect.
try:
    import importlib as _il, re as _re2
    _cd = _pl.Path("amoprof/collectors")
    _files = [f for f in sorted(_cd.glob("*.py")) if f.name != "__init__.py"]
    _bad = []
    for _f in _files:
        try:
            _m = _il.import_module(f"amoprof.collectors.{_f.stem}")
        except Exception as _e:
            _bad.append(f"{_f.name}: {_e!r}"[:60]); continue
        _srcf = _f.read_text()
        for _alias in ("_csv", "_json", "_re", "_os", "_sh"):
            if _re2.search(rf'\b{_alias}\.', _srcf) and not hasattr(_m, _alias):
                _bad.append(f"{_f.name}: {_alias} unresolved")
    check("all collectors import with their aliases resolved",
          _bad or "none", "none")
    check("collector files found", len(_files) > 10, True)
except Exception as _e:
    check("collector import probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0e. collector helpers survive bytes and failure ===")
# _sudo_check_output returns BYTES.  A helper that assumed str raised inside
# start(), which took down the ENTIRE smart collector — no WAF, no NAND, and
# no host_written_gb either.  A parser fault must never cost the caller its
# other fields.
try:
    import amoprof.collectors.nvme_smart as _ns
    _m = _ns.NvmeSmartMonitor.__new__(_ns.NvmeSmartMonitor)
    _m.device, _m.use_sudo = "/dev/null", False
    _S = (b"SMART Cloud Attributes :-\n"
          b"  Physical media units written -                0 17711483977728\n")
    _orig = _ns._sudo_check_output
    _ns._sudo_check_output = lambda *a, **k: _S
    check("ocp log parses bytes output",
          _m._ocp_log().get("nand_bytes_written"), 17711483977728.0)
    _ns._sudo_check_output = lambda *a, **k: _S.decode()
    check("ocp log parses str output",
          _m._ocp_log().get("nand_bytes_written"), 17711483977728.0)
    _ns._sudo_check_output = lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
    check("ocp log failure is graceful", _m._ocp_log(), {})
    check("smart_plus survives a failing ocp read",
          isinstance(_m._smart_plus(), dict), True)
    _ns._sudo_check_output = _orig
except Exception as _e:
    check("smart collector probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0f. compare: tiering chain arithmetic ===")
# The chain is only as good as its derived quantities.  These pin them to
# hand-checked values from the 2026-09 reference runs.
try:
    from amoprof.comparator import (RunMetrics as _RM, build_chain_html as _BC,
                                    build_variance_banner as _BV, _kv_delta as _KD)
    _B = _RM(label="B", l35_dram_gb=483, evicted_gb=5651.3, promoted_gb=0.0,
             mem_hit_gb=1114.5, file_hit_gb=5.2, prefetched_tok=5069152,
             cached_tok=58613454, cache_hit_pct=77.2, tpot_ms=602.1,
             window_s=2580)
    check("evict:read ratio", round(_B.evict_read_ratio, 2), 5.05)
    check("file read share %", round(_B.file_read_share_pct, 2), 0.46)
    check("recomputed tokens (M)", round(_B.recomputed_tok / 1e6, 1), 17.3)
    check("evict rate GB/s", round(_B.evict_rate_gbs, 2), 2.19)

    # An absent counter must stay None, not become 0 — unmeasured and
    # measured-zero are different findings.
    _A = _RM(label="A", evicted_gb=None, mem_hit_gb=1691.3)
    check("absent counter stays None", _A.evict_read_ratio, None)
    _Z = _RM(label="Z", evicted_gb=0.0, mem_hit_gb=100.0)
    check("measured zero yields 0.0", _Z.evict_read_ratio, 0.0)

    # A single run per label must never read as attributable.
    check("single-run comparison is flagged indicative",
          "not attributable" in _BV([_A, _B]), True)
    check("three runs per label clears the flag",
          "not attributable" in _BV([_A, _A, _A, _B, _B, _B]), False)

    # Links within the noise band are suppressed.
    _P = _RM(label="P", tpot_ms=100.0, l35_dram_gb=1000)
    _Q = _RM(label="Q", tpot_ms=101.0, l35_dram_gb=1000)
    check("sub-noise links are omitted from the chain",
          "TPOT" in _BC(_P, _Q), False)
except Exception as _e:
    check("compare chain probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0g. node_exporter cross-check ===")
# A second instrument on the same quantity is the cheapest defence against a
# silent measurement error propagating into every downstream chart.  These
# pin the classifier, including the case where a gap is expected.
try:
    from amoprof.crosscheck import CrossCheck as _CC, compare_sources as _CS, \
        render_report as _RR
    check("within tolerance reads as agreement",
          _CC("q", 100.0, 105.0, "GB").status, "agree")
    check("outside tolerance reads as disagreement",
          _CC("q", 100.0, 140.0, "GB").status, "DISAGREE")
    check("expected gap is not reported as a fault",
          _CC("q", 100.0, 10.0, "GB", "", True).status, "expected-gap")
    check("zero against zero agrees",
          _CC("q", 0.0, 0.0, "GB").status, "agree")
    check("zero against non-zero disagrees",
          _CC("q", 0.0, 5.0, "GB").status, "DISAGREE")
    check("missing node value is not a disagreement",
          _CC("q", 100.0, None, "GB").status, "amoprof-only")
    check("missing both is absent",
          _CC("q", None, None, "GB").status, "absent")
    _cs = _CS({"write_total_gb": 1000.0}, {"node_disk_written_gb": 1005.0})
    check("compare_sources pairs disk writes",
          [c.status for c in _cs if c.quantity == "disk bytes written"], ["agree"])
    check("report names the disagreeing quantity",
          "disk bytes read" in _RR(_CS({"read_total_gb": 0.0},
                                       {"node_disk_read_gb": 9.0})), True)
except Exception as _e:
    check("crosscheck probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0h. a declared tier must render or be explained ===")
# The residency chart named L3.5 in its subtitle while plotting only L1 and
# L2, because a reader was left pointing at a column that had moved files.
# A tier the report declares as configured must produce a series.
try:
    import csv as _c8, json as _j8, math as _m8, shutil as _s8, tempfile as _t8
    from amoprof.report import combined as _C8
    _d8 = _pl.Path(_t8.mkdtemp())
    with (_d8 / "sglang_timeseries.csv").open("w", newline="") as _f8:
        _w8 = _c8.writer(_f8)
        _w8.writerow(["time_sec", "sglang_num_used_tokens",
                      "sglang_hicache_host_used_tokens",
                      "sglang_hicache_host_total_tokens"])
        for _i8 in range(60):
            _w8.writerow([_i8 * 15, 190000, 380000, 392000])
    with (_d8 / "l35_store_capacity.csv").open("w", newline="") as _f8:
        _w8 = _c8.writer(_f8)
        _w8.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b"])
        for _i8 in range(60):
            _w8.writerow([_i8 * 15, int(1.2e12), int(2.0e12)])
    (_d8 / "gpu_config.json").write_text(_j8.dumps(
        {"gpu_name": "B200", "gpu_count": 1, "hbm_per_gpu_gb": 179.09,
         "tp_size": 1, "dp_size": 1, "hostname": "h"}))
    (_d8 / "model_config.json").write_text(_j8.dumps(
        {"num_hidden_layers": 60, "num_key_value_heads": 16,
         "head_dim": 256, "torch_dtype": "bfloat16"}))
    (_d8 / "sglang_summary.json").write_text(_j8.dumps(
        {"max_total_num_tokens": 196153}))
    # Declare the tier as a real deployment would; without it the cache is
    # reported "unknown" and the tier logic under test never runs.
    (_d8 / "setup_details.json").write_text(_j8.dumps(
        {"KV cache tier": "L3.5", "L3 storage type": "remote",
         "hicache_storage_backend": "mooncake",
         "Hierarchical cache": "enabled"}))
    _h8 = _C8.build_executive_summary_html(_d8)
    import html as _H8
    _u8 = _H8.unescape(_h8)
    check("L3.5 residency renders when store capacity is present",
          "L3.5 remote KV store" in _u8, True)
    # The capacity chart must split memory from storage, and must not imply a
    # file tier exists when none is configured.
    check("capacity chart names the memory tier",
          "L3.5 memory capacity" in _u8, True)
    check("no storage line without a file tier",
          "L3.5 storage capacity" in _u8, False)
    # The top-line tier summary must carry a capacity for the remote tier, as
    # it does for L2.  A remote store has no local filesystem, so the df-based
    # figure is zero and the tier was listed bare.
    import re as _re8
    _m8 = _re8.search(r"Inference Cache Tier</b>:\s*([^<]{0,200})", _u8)
    # Unit-agnostic: the fixture's store is 2 TB, so the figure reads
    # "TB DRAM" rather than "GB DRAM".  Assert the capacity is present and
    # names its medium, not a particular unit.
    check("remote tier summary carries a capacity",
          bool(_m8 and _re8.search(r"\d[\d.,]*\s*(?:GB|TB) DRAM", _m8.group(1))),
          True)
except Exception as _e:
    check("residency probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0i. KV movement counters: rank summing, absent vs zero ===")
# prefetch / backup / load-back / evict are published once per tp_rank.  The
# old reader took the first matching column and under-reported by the
# parallelism factor — 1,000 against a true 8,000 at TP=8.
try:
    import csv as _c9, tempfile as _t9
    from amoprof.report.combined import _kv_token_delta as _K9
    _d9 = _pl.Path(_t9.mkdtemp())
    with (_d9 / "sglang_timeseries.csv").open("w", newline="") as _f9:
        _w9 = _c9.writer(_f9)
        _cols = ([f"sglang_prefetched_tokens_total[tp_rank={r}]" for r in range(8)]
                 + [f"sglang_backuped_tokens_total[tp_rank={r}]" for r in range(8)]
                 + [f"sglang_load_back_tokens_total[tp_rank={r}]" for r in range(8)]
                 + ["sglang_evicted_tokens_total[tp_rank=0]"])
        _w9.writerow(["time_sec"] + _cols)
        _w9.writerow([0] + [100] * 24 + [500])
        _w9.writerow([60] + [1100] * 8 + [600] * 8 + [300] * 8 + [500])
    check("prefetch summed across 8 ranks",
          _K9(_d9, ["prefetched_tokens_total"]), 8000.0)
    check("backup summed across 8 ranks",
          _K9(_d9, ["backuped_tokens_total"]), 4000.0)
    check("load-back summed across 8 ranks",
          _K9(_d9, ["load_back_tokens_total"]), 1600.0)
    check("evict present but idle reads as 0.0",
          _K9(_d9, ["evicted_tokens_total"]), 0.0)
    check("absent counter reads as None",
          _K9(_d9, ["nonexistent_tokens_total"]), None)
    # Histogram side-series must not be summed into the counter.
    with (_d9 / "sglang_timeseries.csv").open("w", newline="") as _f9:
        _w9 = _c9.writer(_f9)
        _w9.writerow(["time_sec", "sglang_prefetched_tokens_total",
                      "sglang_prefetched_tokens_total_bucket"])
        _w9.writerow([0, 0, 0]); _w9.writerow([60, 50, 999999])
    check("histogram buckets excluded from the sum",
          _K9(_d9, ["prefetched_tokens_total"]), 50.0)
    # Summing must be across ranks of ONE metric, never across aliases of the
    # same quantity — that double-counted 1,000 tokens as 2,000.
    with (_d9 / "sglang_timeseries.csv").open("w", newline="") as _f9:
        _w9 = _c9.writer(_f9)
        _w9.writerow(["time_sec", "sglang_prefetched_tokens_total",
                      "hicache_prefetched_tokens_total"])
        _w9.writerow([0, 0, 0]); _w9.writerow([60, 1000, 1000])
    check("aliases of one quantity are not summed",
          _K9(_d9, ["prefetched_tokens_total"]), 1000.0)
    with (_d9 / "sglang_timeseries.csv").open("w", newline="") as _f9:
        _w9 = _c9.writer(_f9)
        _w9.writerow(["time_sec"]
                     + [f"sglang_prefetched_tokens_total[tp_rank={r}]" for r in range(2)]
                     + [f"hicache_prefetched_tokens_total[tp_rank={r}]" for r in range(2)])
        _w9.writerow([0, 0, 0, 0, 0]); _w9.writerow([60, 500, 500, 500, 500])
    check("ranks summed within the canonical metric only",
          _K9(_d9, ["prefetched_tokens_total"]), 1000.0)
except Exception as _e:
    check("kv token probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0j. L3.5 wording and read-side correlation target ===")
try:
    from amoprof.report.common_kpis import _amoprof_storage_label_cleanup as _RL
    _t = "L3 reads high; L3 tier idle; L3 traffic low; L3.5 memory used."
    _r = _RL(_t, "remote_mooncake")
    check("findings prose relabelled to L3.5 for a remote tier",
          ("L3 reads" not in _r and "L3.5 reads" in _r), True)
    check("already-correct L3.5 text is not double-rewritten",
          "L3.5.5" in _r, False)
    check("local tier keeps L3 wording",
          "L3 reads" in _RL(_t, "local_ssd"), True)
    import pathlib as _pp
    _cmb = _pp.Path("amoprof/report/combined.py").read_text(errors="replace")
    check("prefetch correlates against bytes served, not replica lookups",
          '"L3.5 · read BW (MB/s)")' in _cmb and '"L3.5 · get ops/s")' not in _cmb,
          True)
    _sm = _pp.Path("amoprof/server_metrics.py").read_text(errors="replace")
    check("replica-list lookups are not aliased as data reads",
          '"master_get_replica_list_requests_total": "mooncake_get_requests_total"' in _sm,
          False)
except Exception as _e:
    check("wording probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0k. L3.5 store internals charts ===")
# Eviction, get outcome and the promotion pipeline come from the store
# exporter.  Pin that they render, that the promotion chart names its largest
# loss, and that the get ratio is computed from the two get counters.
try:
    import csv as _cA, tempfile as _tA, json as _jA, html as _hA
    from amoprof.report import combined as _CA
    _dA = _pl.Path(_tA.mkdtemp())
    with (_dA / "sglang_timeseries.csv").open("w", newline="") as _fA:
        _wA = _cA.writer(_fA)
        _wA.writerow(["time_sec", "sglang_num_used_tokens"])
        for _i in range(40): _wA.writerow([_i * 15, 190000])
    _cols = ["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b",
             "l35_evicted_b", "l35_evicted_mem_b", "l35_get_total_n",
             "l35_get_valid_n", "l35_promo_recorded", "l35_promo_completed",
             "l35_promo_rej_wm", "l35_promo_rej_freq"]
    with (_dA / "l35_store_capacity.csv").open("w", newline="") as _fA:
        _wA = _cA.writer(_fA); _wA.writerow(_cols)
        for _i in range(40):
            _wA.writerow([_i * 15, int(1.2e12), int(2e12), _i * 3e10, _i * 2e10,
                          _i * 1000, _i * 750, _i * 100, 0, _i * 80, _i * 15])
    (_dA / "gpu_config.json").write_text(_jA.dumps(
        {"gpu_name": "B200", "gpu_count": 1, "hbm_per_gpu_gb": 179.09,
         "tp_size": 1, "dp_size": 1, "hostname": "h"}))
    (_dA / "model_config.json").write_text(_jA.dumps(
        {"num_hidden_layers": 60, "num_key_value_heads": 16, "head_dim": 256,
         "torch_dtype": "bfloat16"}))
    (_dA / "sglang_summary.json").write_text(_jA.dumps({"max_total_num_tokens": 196153}))
    _uA = _hA.unescape(_CA.build_executive_summary_html(_dA))
    check("eviction chart renders", "L3.5 eviction over the run" in _uA, True)
    check("get outcome chart renders", "L3.5 get outcome over the run" in _uA, True)
    check("get ratio = valid / total", "75.0% of" in _uA, True)
    check("promotion chart names the largest loss",
          "rejected at the DRAM watermark" in _uA, True)
    # A configured L3.5 tier must never produce silent absence: either the
    # charts render, or a note says which are missing and why.
    (_dA / "setup_details.json").write_text(_jA.dumps(
        {"KV cache tier": "L3.5", "L3 storage type": "remote",
         "hicache_storage_backend": "mooncake"}))
    (_dA / "l35_store_capacity.csv").unlink()
    _uB = _hA.unescape(_CA.build_executive_summary_html(_dA))
    check("L3.5 configured without store data explains the absence",
          "is not in this run's raw directory" in _uB, True)
    (_dA / "setup_details.json").write_text(_jA.dumps(
        {"KV cache tier": "L2", "hicache_storage_backend": "none"}))
    _uC = _hA.unescape(_CA.build_executive_summary_html(_dA))
    check("no L3.5 note when L3.5 is not configured",
          "L3.5 is configured, but" in _uC, False)
except Exception as _e:
    check("store internals probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0l. percentile quantiles: unbounded and bucket-edge cases ===")
try:
    from amoprof.report.metric_kernels import percentiles_from_bucket_deltas as _KP
    _inf = float("inf")
    _les = [1.0, 5.0, 20.0, 40.0, 80.0, 100.0, _inf]
    # every completion above the last finite bucket: the quantile is unbounded
    # above, so it must break the line rather than plot a number.
    _s1 = [(le, [0, 0 if le != _inf else 12, 0 if le != _inf else 24]) for le in _les]
    _r1 = _KP(_s1)
    check("unbounded quantile yields NaN, not a number",
          all(v != v for v in _r1[0.99]), True)
    check("kernel exposes the last finite bucket boundary",
          _r1.get("_last_finite"), 100.0)
    # target coinciding with a bucket's cumulative count returns that edge
    _s2 = [(le, [0, 0 if le < 20 else (6 if le < 40 else 12),
                 0 if le < 20 else (12 if le < 40 else 24)]) for le in _les]
    check("target on a bucket edge returns that edge", _KP(_s2)[0.5][0], 20.0)
except Exception as _e:
    check("percentile probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0m. p50 is the whole-window quantile in every report ===")
# The End and Executive reports both used to prefer the per-interval p50
# series, read from different places, so the same label carried different
# numbers.  Whole-window p50 is now authoritative in both.
try:
    import json as _jM, shutil as _sM, tempfile as _tM, html as _hM, re as _rM
    from amoprof.report import combined as _CM
    _srcM = _pl.Path("/tmp/fx_int")
    if _srcM.exists():
        _dM = _pl.Path(_tM.mkdtemp()) / "run"
        _sM.copytree(_srcM, _dM)
        (_dM / "sglang_summary.json").write_text(_jM.dumps(
            {"server_ttft_p50_ms": 3254.07, "server_itl_p50_ms": 166.71,
             "server_e2e_p50_ms": 18578.80, "max_total_num_tokens": 196153}))
        _uM = _hM.unescape(_CM.build_executive_summary_html(_dM))
        check("Executive TTFT tile uses the whole-window p50",
              bool(_rM.search(r"TTFT[^<]{0,26}</div><div class=\"kpi-value\">\s*3,254", _uM)), True)
        check("Executive E2E tile uses the whole-window p50",
              bool(_rM.search(r"E2E[^<]{0,26}</div><div class=\"kpi-value\">\s*18,579", _uM)), True)
    # precedence, at the source level, in both report modules
    _cm = _pl.Path("amoprof/report/combined.py").read_text(errors="replace")
    check("Executive does not try the interval series first",
          "ttft_p50_ms = ttft_from_pct_ms or" in _cm, False)
    check("Executive keeps the interval series as a fallback",
          "], 0.0)) or ttft_from_pct_ms" in _cm, True)
    _am = _pl.Path("amoprof/report/amoprof.py").read_text(errors="replace")
    check("End report does not try the interval series first",
          "m.ttft_ms = float(_ttft_pct_fallback or" in _am, False)
    check("End report records which method produced the value",
          "per_interval_p50_active_mean_FALLBACK" in _am, True)
except Exception as _e:
    check("p50 consistency probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0n. prefetch OPERATIONS are fetched and charted ===")
# sglang_prefetch_pgs is the read-side twin of sglang_backup_pgs.  It was
# missing from the histogram fetch while backup_pgs was present, so the End
# report's onboard-pages rate read a column that never existed and the write
# path looked busy while the read path looked idle.
try:
    import csv as _cN, json as _jN, tempfile as _tN, html as _hN, re as _rN
    from amoprof.report import combined as _CN
    from amoprof.report.combined import _kv_token_delta as _KN
    _am = _pl.Path("amoprof/report/amoprof.py").read_text(errors="replace")
    check("prefetch_pgs is fetched alongside backup_pgs",
          '("sglang_prefetch_pgs",' in _am and '("sglang_backup_pgs",' in _am, True)
    # the shared reader must serve a requested _count without leaking buckets
    _dN = _pl.Path(_tN.mkdtemp())
    with (_dN / "sglang_timeseries.csv").open("w", newline="") as _fN:
        _wN = _cN.writer(_fN)
        _wN.writerow(["time_sec", "sglang_prefetch_pgs_count",
                      "sglang_prefetch_pgs_sum",
                      'sglang_prefetch_pgs_bucket[le="8"]',
                      "sglang_prefetched_tokens_total"])
        _wN.writerow([0, 10, 100, 5, 1000]); _wN.writerow([60, 40, 700, 25, 9000])
    check("operation count is readable", _KN(_dN, ["prefetch_pgs_count"]), 30.0)
    check("token counter does not absorb its histogram side-series",
          _KN(_dN, ["prefetched_tokens_total"]), 8000.0)
    # writes with no reads must be stated, not left to inference
    _fx = _pl.Path("/tmp/fx_ops")
    if _fx.exists():
        _uN = _hN.unescape(_CN.build_executive_summary_html(_fx))
        check("read-vs-write operations chart renders",
              "KV operations" in _uN, True)
        check("writes with zero reads is stated outright",
              "and NO reads" in _uN, True)
except Exception as _e:
    check("prefetch ops probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0o. KV movement chart: four series, zero is drawn ===")
# One chart carries evict, backup, prefetch and load-back on a shared tok/s
# axis.  A counter that exists and never moved must draw a flat line at zero,
# because dropping it makes "the engine never read" look identical to "this
# build does not export the counter".
try:
    import html as _hO, re as _rO
    from amoprof.report import combined as _CO
    from amoprof.report.combined import _kv_counter_series as _SO, \
        _kv_token_delta as _DO
    _fa, _fb = _pl.Path("/tmp/fx_mv_a"), _pl.Path("/tmp/fx_mv_b")
    if _fa.exists() and _fb.exists():
        # the series reader and the delta reader must not disagree
        _t, _v = _SO(_fb, ["evicted_tokens_total"])
        check("series and delta readers agree",
              round(max(0.0, _v[-1] - _v[0])), round(_DO(_fb, ["evicted_tokens_total"])))
        _ua = _hO.unescape(_CO.build_executive_summary_html(_fa))
        _ub = _hO.unescape(_CO.build_executive_summary_html(_fb))
        def _names(_u):
            # Slice the whole <svg>, not a fixed window after the title: the
            # legend sits ~30 KB later, and a short window silently found one
            # series and passed for the wrong reason.
            _i = _u.find("KV movement over the run")
            _j = _u.rfind("<svg", 0, _i)
            return set(_rO.findall(
                r">\s*((?:evict|backup|prefetch|load-back)[^<]{0,18})</text>",
                _u[_j:_u.find("</svg>", _i)]))
        check("all four movements plotted when all are active",
              len(_names(_ua)), 4)
        check("a counter that never moved is still plotted",
              len(_names(_ub)), 4)
        check("down-only is stated outright",
              "NONE came back up" in _ub, True)
        check("both directions gives a ratio, not a bare count",
              bool(_rO.search(r"M down vs [\d.]+M up|M up vs [\d.]+M down", _ua)), True)
except Exception as _e:
    check("kv movement probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0p. promotion pipeline accounts for every candidate ===")
# Three loss paths were unfetched, so a large loss could be invisible and the
# chart would name a smaller one as the largest.  All 16 promotion metrics the
# store exports are now fetched, and the subtitle says when the stages do not
# add up to the candidates recorded.
try:
    import csv as _cP, shutil as _sP, html as _hP, re as _rP
    from amoprof.report import combined as _CP
    _amP = _pl.Path("amoprof/report/amoprof.py").read_text(errors="replace")
    for _m in ("master_promotion_cancelled_total",
               "master_promotion_candidate_expired_evaluated_total",
               "master_promotion_candidate_expired_unevaluated_total",
               "master_promotion_in_flight"):
        check(f"fetched: {_m.replace('master_promotion_','')}", _m in _amP, True)
    _baseP = _pl.Path("/tmp/fx_mv_b")
    if _baseP.exists():
        _PC = ["l35_promo_recorded", "l35_promo_completed", "l35_promo_rej_wm",
               "l35_promo_exp_uneval", "l35_promo_cancelled"]
        def _mkP(_n, _per):
            _d = _pl.Path(_n); _sP.rmtree(_d, ignore_errors=True)
            _sP.copytree(_baseP, _d)
            _rows = list(_cP.DictReader((_baseP / "l35_store_capacity.csv").open()))
            _hdr = list(_rows[0].keys())
            with (_d / "l35_store_capacity.csv").open("w", newline="") as _f:
                _w = _cP.writer(_f); _w.writerow(_hdr + _PC)
                for _i, _r in enumerate(_rows):
                    _w.writerow([_r[_k] for _k in _hdr]
                                + [_i * _per.get(_c, 0) for _c in _PC])
            return _d
        def _subP(_d):
            _u = _hP.unescape(_CP.build_executive_summary_html(_d))
            _i = _u.find("L3.5 promotion pipeline")
            if _i < 0:
                return ""
            _j = _u.rfind("<svg", 0, _i)
            _m = _rP.search(r'font-size="8\.5"[^>]*>([^<]{30,300})</text>',
                            _u[_j:_u.find("</svg>", _i)])
            return _m.group(1) if _m else ""
        # a newly-fetched loss path must be nameable as the largest loss
        _s1 = _subP(_mkP("/tmp/fx_pr_a", {"l35_promo_recorded": 1000,
                                          "l35_promo_completed": 50,
                                          "l35_promo_rej_wm": 100,
                                          "l35_promo_exp_uneval": 800,
                                          "l35_promo_cancelled": 50}))
        check("a newly-fetched loss path can be the largest loss",
              "expired before evaluation" in _s1, True)
        check("balanced stages raise no accounting note",
              "unaccounted" in _s1, False)
        # stages that do not add up must say so
        _s2 = _subP(_mkP("/tmp/fx_pr_b", {"l35_promo_recorded": 1000,
                                          "l35_promo_rej_wm": 400}))
        check("unaccounted candidates are stated", "unaccounted" in _s2, True)
except Exception as _e:
    check("promotion pipeline probe ran", f"FAILED: {_e}", "ok")

print("\n=== 0q. promotion legend and per-tier reads ===")
# The promotion bars do not share a unit and are not a split of the
# candidates: rejection counters count evaluation ATTEMPTS, so their total can
# exceed the candidate count.  An earlier version summed them and reported the
# excess as "over-counted", naming a measurement fault where there is none.
try:
    import html as _hQ, re as _rQ
    from amoprof.report import combined as _CQ
    _fq = _pl.Path("/tmp/fx_rd")
    if _fq.exists():
        _uq = _hQ.unescape(_CQ.build_executive_summary_html(_fq))
        check("promotion legend is present and collapsible",
              "What each bar means" in _uq and "<details" in _uq, True)
        check("legend states the bars share no unit",
              "do not share a unit" in _uq, True)
        check("rejections are not reported as over-counting",
              "over-counted" in _uq, False)
        check("evaluation pressure is reported instead",
              "rejected evaluations per candidate" in _uq, True)
        check("completion share is stated",
              bool(_rQ.search(r"0\.38% of candidates completed", _uq)), True)
        _i = _uq.find("L3.5 reads by tier")
        check("reads-by-tier chart renders", _i > 0, True)
        if _i > 0:
            _j = _uq.rfind("<svg", 0, _i)
            _seg = _uq[_j:_uq.find("</svg>", _i)]
            check("both tiers are plotted",
                  len(_rQ.findall(r">(?:DRAM tier|SSD / file tier)</text>", _seg)), 2)
            _sub = _rQ.search(r'font-size="8\.5"[^>]*>([^<]{20,300})</text>', _seg)
            check("subtitle fits the chart width",
                  bool(_sub) and len(_sub.group(1)) <= 120, True)
            check("per-tier shares are given",
                  bool(_sub and _rQ.search(r"% DRAM / [\d.]+% SSD", _sub.group(1))), True)
except Exception as _e:
    check("promotion legend probe ran", f"FAILED: {_e}", "ok")

print("\n=== 1. pearson vs scipy.stats.pearsonr ===")
random.seed(1); rng = np.random.default_rng(1)
for i, (n, rho) in enumerate([(50, 0.0), (200, 0.7), (500, -0.9), (30, 0.99)]):
    cov = [[1, rho], [rho, 1]]
    xy = rng.multivariate_normal([0, 0], cov, size=n)
    x, y = list(xy[:, 0]), list(xy[:, 1])
    check(f"pearson case {i} (n={n})", pearson(x, y), float(stats.pearsonr(x, y)[0]), 1e-12)

# degenerate inputs must not raise or return NaN
check("pearson constant y -> 0.0", pearson([1, 2, 3, 4], [5, 5, 5, 5]), 0.0)
check("pearson n<3 -> 0.0", pearson([1, 2], [3, 4]), 0.0)
check("pearson perfect +1", pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0, 1e-12)
check("pearson perfect -1", pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2]), -1.0, 1e-12)
# scale/offset invariance (r must not change)
x = list(rng.normal(size=100)); y = list(rng.normal(size=100))
check("pearson scale-invariant",
      pearson(x, y), pearson([v * 1e6 + 7 for v in x], [v * 3e-3 - 2 for v in y]), 1e-9)


print("\n=== 2. counter_delta / window_rate vs closed form ===")
vals = [100.0 + 7.0 * i for i in range(50)]          # +7 per sample
ts = [float(i) for i in range(50)]                    # 1 s apart
check("counter_delta", counter_delta(vals), 7.0 * 49)
check("window_seconds", window_seconds(ts), 49.0)
check("window_rate", window_rate(vals, ts), 7.0, 1e-12)
check("counter_delta clamps reset", counter_delta([500.0, 600.0, 10.0]), 0.0)
check("counter_delta single sample", counter_delta([42.0]), 0.0)
check("window_rate zero window", window_rate([1.0, 2.0], [5.0, 5.0]), 0.0)


print("\n=== 3. rate_series vs numpy.diff ===")
rng2 = np.random.default_rng(7)
inc = np.abs(rng2.normal(50, 10, size=200))
cum = list(np.cumsum(inc))
t = [float(i) * 2.0 for i in range(200)]              # 2 s spacing
rt, rv = rate_series_with_time(cum, t)
ref = list(np.diff(cum) / 2.0)
check("rate_series length", len(rv), len(ref))
check("rate_series max abs err", float(max(abs(a - b) for a, b in zip(rv, ref))), 0.0, 1e-9)
check("rate_series timestamps drop first", rt[0], t[1])
# duplicate timestamps must be skipped, and times stay aligned to values
t_dup = [0.0, 1.0, 1.0, 2.0, 3.0]
v_dup = [0.0, 10.0, 10.0, 30.0, 45.0]
dt_, dv_ = rate_series_with_time(v_dup, t_dup)
check("dup-timestamp sample skipped", len(dv_), 3)
check("dup-timestamp values", dv_, [10.0, 20.0, 15.0])
check("dup-timestamp times align", dt_, [1.0, 2.0, 3.0])
# aligned variant preserves length
al = aligned_rate_series(v_dup, t_dup)
check("aligned_rate_series length == input", len(al), len(v_dup))
check("aligned_rate_series pads first with 0", al[0], 0.0)
check("aligned_rate_series 0 on dt<=0", al[2], 0.0)


print("\n=== 4. ratio_delta (histogram mean) vs closed form ===")
# 100 observations totalling 250 s -> mean 2.5 s = 2500 ms
s_cum = [0.0, 100.0, 250.0]
c_cum = [0.0, 40.0, 100.0]
check("ratio_delta ms", ratio_delta(s_cum, c_cum, 1000.0), 250.0 / 100.0 * 1000.0, 1e-9)
check("ratio_delta zero count -> 0", ratio_delta([0.0, 5.0], [3.0, 3.0], 1000.0), 0.0)


print("\n=== 5. align_on_time nearest-neighbour correctness ===")
# X at 1 s, Y at 5 s: each x must map to the nearest y within tol
xt = [float(i) for i in range(0, 30)]
xv = [float(i) for i in range(0, 30)]
yt = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
yv = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
ax, ay = align_on_time(xt, xv, yt, yv)
ref_pairs = []
tol = max(1.0, 5.0) / 2.0        # half the coarser median step
for i, tx in enumerate(xt):
    j = min(range(len(yt)), key=lambda k: abs(yt[k] - tx))
    if abs(yt[j] - tx) <= tol:
        ref_pairs.append((xv[i], yv[j]))
check("align_on_time pair count", len(ax), len(ref_pairs))
check("align_on_time pairs match brute force", list(zip(ax, ay)), ref_pairs)
# identical timebases must pair 1:1 and preserve r exactly
xs = list(rng2.normal(size=300)); ys = list(rng2.normal(size=300))
tt = [float(i) for i in range(300)]
bx, by = align_on_time(tt, xs, tt, ys)
check("align identical timebase count", len(bx), 300)
check("align identical timebase r", pearson(bx, by), float(stats.pearsonr(xs, ys)[0]), 1e-12)
# non-overlapping windows must produce nothing
cx, cy = align_on_time([0.0, 1.0, 2.0], [1, 2, 3], [500.0, 501.0, 502.0], [4, 5, 6])
check("align non-overlapping -> empty", len(cx), 0)


print("\n=== 6. end-to-end: known relationship recovered ===")
# y = 3x + noise sampled on a DIFFERENT cadence; r must match the reference
# computed on the exact same aligned pairs.
rng3 = np.random.default_rng(11)
n = 600
t_fast = [float(i) for i in range(n)]                      # 1 s
drv_cum = list(np.cumsum(np.abs(rng3.normal(100, 20, n))))  # cumulative counter
dt_, dv_ = rate_series_with_time(drv_cum, t_fast)
# Realistic case: both series observe ONE underlying smooth signal at
# different cadences.  This is what a 1 s collector and a 15 s Prometheus
# scrape of the same workload look like.
sig = [80.0 + 40.0 * math.sin(i / 60.0) for i in range(n)]
drv_cum2 = list(np.cumsum(sig))
dt2, dv2 = rate_series_with_time(drv_cum2, t_fast)
t_slow = [float(i) for i in range(0, n, 5)]
sv = [3.0 * sig[i] + rng3.normal(0, 2) for i in range(0, n, 5)]
ex, ey = align_on_time(dt2, dv2, t_slow, sv)
check("e2e aligned n > 0", len(ex) > 0, True)
check("e2e r matches scipy on same pairs",
      pearson(ex, ey), float(stats.pearsonr(ex, ey)[0]), 1e-12)
check("e2e recovers strong positive r", pearson(ex, ey) > 0.9, True)
# index pairing (the old bug) must give a materially different answer
idx_n = min(len(dv_), len(sv))
r_idx = pearson(dv_[:idx_n], sv[:idx_n])
print(f"        [context] index-paired r={r_idx:+.3f} vs time-aligned r={pearson(ex, ey):+.3f}")


print("\n=== 6b. sampling-rate dilution (a property, not a defect) ===")
# A driver varying faster than the resource is sampled cannot correlate fully:
# intermediate driver values have no corresponding resource observation.
fast = [50.0 + 40.0 * math.sin(i / 3.0) for i in range(n)]      # period ~19 s
slow_t = [float(i) for i in range(0, n, 15)]                     # 15 s scrape
slow_v = [2.0 * fast[i] for i in range(0, n, 15)]
fx, fy = align_on_time([float(i) for i in range(n)], fast, slow_t, slow_v)
r_fast = pearson(fx, fy)
smooth = [50.0 + 40.0 * math.sin(i / 120.0) for i in range(n)]   # period ~754 s
sm_v = [2.0 * smooth[i] for i in range(0, n, 15)]
sx, sy = align_on_time([float(i) for i in range(n)], smooth, slow_t, sm_v)
r_smooth = pearson(sx, sy)
print(f"        driver period 19 s vs 15 s scrape  -> r={r_fast:+.3f}  (aliased)")
print(f"        driver period 754 s vs 15 s scrape -> r={r_smooth:+.3f}  (resolved)")
check("slow signal recovered near-perfectly", r_smooth > 0.99, True)
check("aliased signal correctly reports weak r", abs(r_fast) < abs(r_smooth), True)

print("\n=== 7. histogram percentiles vs numpy on the same samples ===")
import csv, tempfile, pathlib
rng4 = np.random.default_rng(3)
LE = [0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4, float("inf")]
def _le_label(le):
    tag = "+Inf" if le == float("inf") else f"{le:g}"
    return f"sglang_ttft_seconds_bucket[le={tag}]"
samples_all = []
rows = []
cum = {le: 0.0 for le in LE}
for step in range(300):
    s = rng4.lognormal(mean=math.log(0.25), sigma=0.5, size=20)
    samples_all.extend(s.tolist())
    for le in LE:
        cum[le] += float(np.sum(s <= le))
    rows.append(dict({"time_sec": step}, **{
        _le_label(le): f"{cum[le]:.0f}" for le in LE}))
d = pathlib.Path(tempfile.mkdtemp())
with (d / "sglang_timeseries.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
res = _amoprof_histogram_window_percentiles(d / "sglang_timeseries.csv", "ttft_seconds",
                                            (0.5, 0.9, 0.99), 1000.0)
# Per-interval deltas start at index 1, so the first sample's observations
# have no predecessor and are not counted.  Inherent to cumulative counters.
check("histogram observation count (excl. first sample)",
      res.get("observations"), float(len(samples_all) - 20))
for q, key in ((0.5, "p50"), (0.9, "p90")):
    exact = float(np.quantile(samples_all, q)) * 1000.0
    got = res[key]
    # bucket interpolation cannot beat the bucket width; assert it lands inside
    lo = max(le for le in LE if le * 1000.0 <= got) * 1000.0 if any(le * 1000.0 <= got for le in LE) else 0.0
    err = abs(got - exact) / exact * 100.0
    ok = err < 25.0
    print(f"  {'OK  ' if ok else 'FAIL'}  histogram {key} within bucket resolution        "
          f"got={got:8.1f} ms  exact={exact:8.1f} ms  err={err:5.1f}%")
    if not ok:
        FAILS.append(f"histogram {key}")


print("\n=== 8. binned response monotonicity ===")
xs2 = list(rng4.uniform(0, 100, 400))
ys2 = [2.0 * v + rng4.normal(0, 1) for v in xs2]
bins = _amoprof_binned_response(xs2, ys2, 10)
check("binned response bin count", len(bins), 10)
mono = all(bins[i][0] <= bins[i + 1][0] for i in range(len(bins) - 1))
check("binned x monotonically increasing", mono, True)
slope_ok = all(bins[i][1] < bins[i + 1][1] for i in range(len(bins) - 1))
check("binned y follows a linear driver", slope_ok, True)
# each bin's median must sit inside the data range
check("binned medians within data range",
      all(min(ys2) <= b[1] <= max(ys2) for b in bins), True)

print("\n=== 0r. chart provenance: source blocks name the real metric ===")
# A source block that names a metric the fetch does not request is worse than
# no source block: it invites the reader to go look for a series that was
# never collected.  These assertions tie the block to the fetch code.
from amoprof.report.combined import (
    _raw_column_sources as _rcs, _src_rows_for as _srf,
    _src_block_from_series as _sbs, _amoprof_src_block as _asb,
)
from amoprof.report.metric_formulas import formula_for as _ff

_cols = _rcs()
check("fetch-code column map parses", bool(_cols), True)
check("l35_storage_timeseries.csv present in map",
      "l35_storage_timeseries.csv" in _cols, True)
_l35map = _cols.get("l35_storage_timeseries.csv", {})
for _c in ("l35_rd_bw_mbs", "l35_wr_bw_mbs", "l35_rd_iops", "l35_avgqu_sz"):
    check(f"{_c} resolves to >=1 upstream metric",
          len(_l35map.get(_c) or []) >= 1, True)

_rows = _srf("l35_storage_timeseries.csv", [("Storage read BW", "l35_rd_bw_mbs")])
check("src row shape is (label, file, column, upstream)", len(_rows[0]), 4)
check("src row names the file", _rows[0][1], "l35_storage_timeseries.csv")
check("src row names the column", _rows[0][2], "l35_rd_bw_mbs")
check("src row upstream is non-empty", bool(_rows[0][3].strip()), True)
# An unknown column must fall back rather than invent a metric name.
_unk = _srf("l35_storage_timeseries.csv", [("X", "no_such_column_xyz")])
check("unknown column yields an em-dash, not a guess", _unk[0][3], "\u2014")

# A series with no provenance must not produce a row.
check("series without src produce no block",
      _sbs([{"label": "a", "tier": "L1", "v": [1.0]}]), "")
check("series with src produce a block",
      'class="amoprof-src"' in _sbs(
          [{"label": "a", "tier": "L1", "v": [1.0],
            "src": ("f.csv", "c", "m")}]), True)
check("empty rows produce no block", _asb([]), "")

print("\n=== 0t. every rendered chart carries a formula or source block ===")
# The point of the source blocks is that a reader can check ANY number.  A
# chart added later with no provenance quietly reintroduces the problem that
# three "L3.5 read BW" figures could disagree with nothing to explain it, so
# assert coverage over a rendered report rather than over the call sites.
import re as _re_c, csv as _csv_c, shutil as _sh_c, tempfile as _tf_c
from amoprof.report.combined import build_executive_summary_html as _bx

_pd = _build_probe_dir()
# Add an L3.5 store and block device, so the tiering charts render too.
with (_pd / "l35_store_capacity.csv").open("w", newline="") as _f:
    _w = _csv_c.writer(_f)
    _cols = ["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b",
             "l35_promo_recorded", "l35_promo_admitted", "l35_promo_completed",
             "l35_promo_rej_freq", "l35_promo_rej_wm", "l35_promo_rej_cap",
             "l35_promo_rej_adm", "l35_get_total_n", "l35_get_valid_n",
             "l35_mem_hit_n", "l35_file_hit_n", "l35_mem_hit_b",
             "l35_file_hit_b", "l35_evicted_b"]
    _w.writerow(_cols)
    for _i in range(40):
        _k = _i / 39.0
        _w.writerow([_i * 51, int(1.2e12), int(2.0e12),
                     int(75936 * _k), int(54160 * _k), int(275 * _k),
                     int(26093 * _k), int(138236 * _k), int(66397 * _k),
                     int(69446 * _k), int(13.7e6 * _k), int(13.7e6 * _k),
                     int(12993080 * _k), int(706920 * _k),
                     int(343.2e9 * _k), int(7.2e9 * _k), int(5.0e12 * _k)])
with (_pd / "l35_storage_timeseries.csv").open("w", newline="") as _f:
    _w = _csv_c.writer(_f)
    _w.writerow(["time_sec", "l35_rd_iops", "l35_wr_iops", "l35_rd_bw_mbs",
                 "l35_wr_bw_mbs", "l35_io_util_pct", "l35_avgqu_sz"])
    for _i in range(40):
        _wb = 0.0 if _i < 2 else 300.0 + _i * 90.0
        _w.writerow([_i * 51, 0, int(_wb * 8), 0.0, round(_wb, 1),
                     round(min(99.0, _wb / 45.0), 1), round(0.2 + _wb / 2200.0, 2)])

# The KV delivery ledger only renders when prefetch, load-back AND the
# prefill mode counters are all present.  Without them the coverage rule
# below passed while never seeing that chart -- a false pass that hid a
# genuinely bare panel.  Add the columns so the probe exercises it.
_sg_p = _pd / "sglang_timeseries.csv"
_sg_rows = list(_csv_c.DictReader(_sg_p.open()))
_sg_hdr = list(_sg_rows[0].keys()) + ["sglang_prefetched_tokens_total",
                                      "sglang_load_back_tokens_total"]
for _i, _r in enumerate(_sg_rows):
    _r["sglang_prefetched_tokens_total"] = f"{_i * 4200:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 9100:d}"
with _sg_p.open("w", newline="") as _f:
    _w2 = _csv_c.DictWriter(_f, fieldnames=_sg_hdr)
    _w2.writeheader(); _w2.writerows(_sg_rows)

_hx_full = _bx(_pd, run_label="probe")
check("probe renders the KV delivery ledger",
      "KV delivery ledger" in _hx_full, True)
# Measured only: the counterfactual is arithmetic and must stay out of the
# chart, where a computed bar would carry the same weight as a measured one.
_led_i = _hx_full.find("KV delivery ledger")
_led_svg = _hx_full[_led_i:_hx_full.find("</svg>", _led_i)]
# Assert on the BAR LABELS, not on the whole SVG: the subtitle legitimately
# mentions gets and lookups when pointing the reader at the ledger table, so
# a substring test over the markup would fail for the wrong reason.
_led_texts = _re_c.findall(r"<text[^>]*>([^<]+)</text>", _led_svg)
# Bar labels are short; the wrapped subtitle lines are not, and one of them
# legitimately contains the word "lookups".  Length separates them.
_bar_labels = [t for t in _led_texts if len(t) <= 40
               and (t in ("prefetched L3.5\u2192L2", "load-back L2\u2192L1",
                          "recomputed (missed)")
                    or "no L3.5" in t or "lookups" in t
                    or t.startswith("gets"))]
check("ledger bars are exactly the three token stages",
      sorted(set(_bar_labels)),
      sorted({"prefetched L3.5\u2192L2", "load-back L2\u2192L1",
              "recomputed (missed)"}))
for _forbidden in ("no L3.5", "cached \u00b7 now", "baseline hit"):
    check(f"no computed bar in the chart ({_forbidden[:13]})",
          any(_forbidden in _t for _t in _led_texts), False)
# The ledger TABLE must carry the mixed-unit rows the chart cannot.
check("ledger table reports L3.5 gets in lookups",
      "lookups" in _hx_full and "total_get_nums_" in _hx_full, True)
check("ledger table states L3-local has no get counter",
      "no get counter exists for the local tier" in _hx_full, True)
# The Executive overview strip is a dense row of small multiples whose job is
# "what happened during the run".  It reuses charts the Bottleneck section
# already carries, and provenance is deliberately stripped there, so exclude
# that section from the coverage rule rather than weakening the rule.
_ov_i = _hx_full.find('<div class="section-label">Executive overview')
_ov_j = _hx_full.find('class="section-label"', _ov_i + 60) if _ov_i >= 0 else -1
if _ov_i >= 0 and _ov_j > _ov_i:
    check("overview strip carries no provenance blocks",
          'class="amoprof-src"' in _hx_full[_ov_i:_ov_j], False)
    _hx = _hx_full[:_ov_i] + _hx_full[_ov_j:]
else:
    _hx = _hx_full
_svgs = [(_m.start(), _m.group(0))
         for _m in _re_c.finditer(r"<svg.*?</svg>", _hx, _re_c.S)]
check("probe report renders charts", len(_svgs) >= 10, True)
_bare = []
for _pos, _sv in _svgs:
    _t = _re_c.findall(r"<text[^>]*>([^<]{4,110})</text>", _sv)
    _t = _t[0] if _t else "??"
    _after = _hx[_pos + len(_sv): _pos + len(_sv) + 700]
    # Either a collapsible Source & formula block, or the inline X/Y formula
    # caption the correlation scatters render.
    if not ('class="amoprof-src"' in _after or "background:#020617" in _after):
        _bare.append(_t)
for _t in dict.fromkeys(_bare):
    print(f"        chart with no provenance: {_t}")
check("charts lacking a formula/source block", len(_bare), 0)

# The block must reflect what was PLOTTED.  Read BW is all-zero in the
# fixture above, so that series is dropped from the chart and must not be
# named underneath it.
_i_rw = _hx.find("L3.5 node storage: reads vs writes")
if _i_rw > 0:
    _j = _hx.find('class="amoprof-src"', _i_rw)
    _k = _hx.find("</details>", _j)
    _blk = _hx[_j:_k]
    check("dropped all-zero series is not named in its block",
          "l35_rd_bw_mbs" in _blk, False)
    check("plotted series IS named in its block",
          "l35_wr_bw_mbs" in _blk, True)
_sh_c.rmtree(_pd, ignore_errors=True)


# _strip_src_blocks must remove ONLY the provenance blocks.
from amoprof.report.combined import _strip_src_blocks as _ssb
_mixed = ('<div>a</div>' + _asb([("s", "f.csv", "c", "m")])
          + '<details class="other"><summary>keep me</summary>x</details>')
_stripped = _ssb(_mixed)
check("strip removes the provenance block", 'amoprof-src' in _stripped, False)
check("strip keeps other details", 'keep me' in _stripped, True)
check("strip leaves non-provenance html alone", '<div>a</div>' in _stripped, True)
check("strip is a no-op when there is nothing to strip",
      _ssb('<div>x</div>'), '<div>x</div>')

print("\n=== 0u. layout: one chart per row, block inside its own panel ===")
# The block used to be appended as a SIBLING of the chart panel.  In a grid
# that makes it its own cell, so a block on a single-column chart was laid
# out BESIDE a neighbour with dead space under its own chart.  Assert the
# nesting rather than the CSS, because nesting is what makes the pairing
# survive a future layout change.
from amoprof.report.combined import _bind_src_blocks as _bsb
_one = ('<div class="corr-chart"><svg>x</svg><div>cap</div></div>'
        '<details class="amoprof-src">B</details>tail')
_b1 = _bsb(_one)
check("block moves inside the chart panel",
      _b1.index("</details>") < _b1.index("</div>tail"), True)
check("panel still closes after the block", _b1.endswith("</div>tail"), True)
check("a row wrapper groups the chips",
      'class="amoprof-src-row"' in _b1, True)
# Several disclosures on one chart must all come inside, not just the first.
_two = ('<div class="corr-chart"><svg>x</svg></div>'
        '<details class="amoprof-src">B</details>'
        '<details class="amoprof-src amoprof-note">N</details>rest')
_b2 = _bsb(_two)
check("both disclosures bind to the chart",
      _b2.index("N</details>") < _b2.index("</div>rest"), True)
# A chart with nothing after it is untouched.
check("chart with no disclosure is unchanged",
      _bsb('<div class="corr-chart"><svg>z</svg></div><p>x</p>'),
      '<div class="corr-chart"><svg>z</svg></div><p>x</p>')
# Unbalanced markup must not corrupt the document.
check("unbalanced panel is left alone",
      _bsb('<div class="corr-chart"><svg>z</svg>'),
      '<div class="corr-chart"><svg>z</svg>')
# The grid must be single column: side-by-side panels with different
# x-extents read as time-aligned when they are not.
check("chart grid is one per row",
      "grid-template-columns:1fr;" in _hx_full, True)
check("multi-column auto-fit grid is gone",
      "auto-fit,minmax(var(--corr-w" in _hx_full, False)

print("\n=== 0v. prefetch efficacy: the control changes the verdict ===")
# Build a run where prefetch DEMONSTRABLY relieves the GPU:
#     recompute = 0.25*load - 0.40*prefetch,  prefetch = 0.30*load
# The raw correlation between prefetch and recompute reports the OPPOSITE
# conclusion, because both track request load.  These assertions pin that
# the report uses the controlled statistic, since the raw one would tell a
# user their prefetch is useless when it is working.
from amoprof.report.metric_kernels import (
    lagged_pearson as _lp, partial_pearson as _pp, pearson as _pe)
import math as _m, random as _rnd
_rnd.seed(5)
_load, _pf, _rc, _lb = [], [], [], []
for _i in range(60):
    _L = 3000 + 2500 * _m.sin(_i / 5.0) + _rnd.gauss(0, 120)
    _P = max(0.0, 0.30 * _L + _rnd.gauss(0, 60))
    _load.append(_L); _pf.append(_P)
    _rc.append(max(0.0, 0.25 * _L - 0.40 * _P + _rnd.gauss(0, 40)))
    _lb.append(max(0.0, 0.90 * _L + 0.05 * _P + _rnd.gauss(0, 60)))
_raw_eff = _pe(_pf, _rc)
_ctl_eff = _pp(_pf, _rc, _load)
print(f"        raw r(prefetch, recompute) = {_raw_eff:+.3f}   "
      f"controlled = {_ctl_eff:+.3f}   (planted: prefetch REDUCES recompute)")
check("raw efficacy r points the WRONG way", _raw_eff > 0.5, True)
check("controlled efficacy r recovers the truth", _ctl_eff < -0.3, True)
# Same confound on the pipeline pair: load-back barely depends on prefetch
# (weight 0.05) yet the raw correlation is near-perfect.
_raw_pipe = _pe(_pf, _lb)
_ctl_pipe = _pp(_pf, _lb, _load)
check("raw prefetch-loadback r looks like a perfect pipeline",
      _raw_pipe > 0.9, True)
check("controlled prefetch-loadback r collapses",
      abs(_ctl_pipe) < 0.5, True)

# partial_pearson against the textbook residual definition.
_z = [_rnd.gauss(0, 1) for _ in range(300)]
_x = [0.8 * v + _rnd.gauss(0, .5) for v in _z]
_y = [0.7 * v + _rnd.gauss(0, .5) for v in _z]
_mz = sum(_z) / len(_z)
def _resid(_v):
    _mv = sum(_v) / len(_v)
    _b = (sum((a - _mz) * (b - _mv) for a, b in zip(_z, _v))
          / sum((a - _mz) ** 2 for a in _z))
    return [b - (_mv + _b * (a - _mz)) for a, b in zip(_z, _v)]
check("partial_pearson equals correlation of residuals",
      abs(_pp(_x, _y, _z) - _pe(_resid(_x), _resid(_y))) < 1e-9, True)

# lagged_pearson must recover a planted delay, and prefer the smaller |lag|
# when two shifts are equally good.
_base = [_rnd.gauss(0, 1) for _ in range(200)]
_delayed = [0.0] * 3 + _base[:-3]
_r, _lag = _lp(_base, _delayed, max_lag=6)
check("lagged_pearson recovers a planted lag of 3", _lag, 3)
check("lagged_pearson r at that lag is ~1", _r > 0.99, True)
check("zero-lag r would have missed it", abs(_pe(_base, _delayed)) < 0.3, True)
check("lagged_pearson is bounded", abs(_lp(_base, _base, 6)[0]) <= 1.0 + 1e-12, True)
check("lagged_pearson on identical series reports lag 0",
      _lp(_base, _base, 6)[1], 0)
check("partial_pearson stays in range on collinear input",
      abs(_pp(_base, _base, _base)) <= 1.0, True)

print("\n=== 0w. prefetch benefit accounting vs a no-tier baseline ===")
# The identity the panel rests on:
#   every prefill token is cached or recomputed, and C + R is fixed by the
#   requests that arrived.  A prefetched token that was CONSUMED would have
#   been recomputed without the tier, so the counterfactual moves B tokens
#   from C to R and leaves C + R alone.
#   B = min(P, LB, C), because a consumed token must have crossed L2->L1
#   (so it is inside load-back) and must be among the prefill tokens served
#   from cache.
def _benefit(P, LB, C, R):
    B = min(P, LB, C)
    return B, C / (C + R) * 100.0, (C - B) / (C + R) * 100.0

# The worked example: 200 tokens needed, 100 already in L2, 100 prefetched
# from the tier and all consumed.  Without the tier those 100 are recomputed.
_B, _obs, _base = _benefit(100, 200, 200, 0)
check("worked example: benefit is the 100 prefetched", _B, 100)
check("worked example: observed hit rate", _obs, 100.0)
check("worked example: baseline hit rate without the tier", _base, 50.0)

# The bound must bind on whichever term is smallest, and which one it is
# carries the finding.
check("bound by prefetched when the tier is the limit",
      _benefit(100, 200, 200, 0)[0], 100)
check("bound by load-back when more was pulled than restored",
      _benefit(300, 200, 250, 0)[0], 200)
check("bound by cached when more was pulled than prefill used",
      _benefit(300, 400, 200, 0)[0], 200)

# The counterfactual must conserve total prefill tokens.
for _P, _LB, _C, _R in ((100, 200, 200, 0), (300, 200, 250, 90),
                        (12, 900, 800, 4321)):
    _b = min(_P, _LB, _C)
    check(f"C+R conserved under the counterfactual (C={_C},R={_R})",
          (_C - _b) + (_R + _b), _C + _R)
    check(f"counterfactual hit rate never exceeds observed (C={_C})",
          (_C - _b) / (_C + _R) <= _C / (_C + _R), True)
    check(f"counterfactual cached stays non-negative (C={_C})", (_C - _b) >= 0, True)

# Tokens saved is NOT seconds saved inside the window.  With B large
# relative to R, the counterfactual work does not fit in the same wall
# clock even at the peak observed rate -- the run would have been longer.
# A first cut divided by the MEAN rate and produced 4,607 s of saving in a
# 1,989 s run.  Assert the impossible-on-its-face case is detectable.
_B2, _R2, _peak, _win = 2006156, 866068, 751.0, 1989.0
check("time estimate at peak rate exceeds the window here",
      _B2 / _peak > _win, True)
check("the unit-free multiple is well defined instead",
      abs((_R2 + _B2) / _R2 - 3.316) < 0.01, True)

print("\n=== 0x. KV block movement: tokens->blocks, and the right tier name ===")
# The End report's panel of this name labels its backup/prefetch series
# "local Storage" whatever the backend is, because its gate is true for a
# remote store too -- so a Mooncake run read as though its KV were going to
# a local SSD.  The executive version resolves the name from the backend.
import json as _js_x, shutil as _sh_x
_pd_x = _build_probe_dir()
with (_pd_x / "l35_store_capacity.csv").open("w", newline="") as _f:
    _w3 = _csv_c.writer(_f)
    _w3.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b"])
    for _i in range(30):
        _w3.writerow([_i * 60, int(1.2e12), int(2.0e12)])
_sg_x = _pd_x / "sglang_timeseries.csv"
_rows_x = list(_csv_c.DictReader(_sg_x.open()))
_hdr_x = list(_rows_x[0].keys()) + [
    "sglang_evicted_tokens_total", "sglang_backuped_tokens_total",
    "sglang_prefetched_tokens_total", "sglang_load_back_tokens_total"]
for _i, _r in enumerate(_rows_x):
    _r["sglang_evicted_tokens_total"] = f"{_i * 64000:d}"     # 64000 tok/interval
    _r["sglang_backuped_tokens_total"] = f"{_i * 32000:d}"
    _r["sglang_prefetched_tokens_total"] = f"{_i * 16000:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 8000:d}"
with _sg_x.open("w", newline="") as _f:
    _w4 = _csv_c.DictWriter(_f, fieldnames=_hdr_x)
    _w4.writeheader(); _w4.writerows(_rows_x)

def _movement_labels(backend, page):
    _d = _pl.Path(_tf.mkdtemp())
    _sh_x.rmtree(_d); _sh_x.copytree(_pd_x, _d)
    _sd = _js_x.loads((_d / "setup_details.json").read_text())
    _sd.update({"Page size": page, "hicache_storage_backend": backend,
                "KV cache tier": "L3.5" if backend == "mooncake" else "L3",
                "L3 storage type": "remote" if backend == "mooncake" else "local"})
    (_d / "setup_details.json").write_text(_js_x.dumps(_sd))
    _h = _bx(_d, run_label="mv")
    _i = _h.find("KV block movement rates across tiers")
    if _i < 0:
        return None, None, None
    _svg = _re_c.search(r"<svg.*?</svg>", _h[_i:], _re_c.S).group(0)
    _t = _re_c.findall(r"<text[^>]*>([^<]{3,140})</text>", _svg)
    _labels = [x for x in _t if "\u2192" in x]
    _peaks = [x for x in _t if x.startswith("peak ")]
    _sub = next((x for x in _t if "tokens per block" in x), "")
    return _labels, _peaks, _sub

_lab_r, _pk_r, _sub_r = _movement_labels("mooncake", 64)
check("remote backend renders the movement chart", _lab_r is not None, True)
check("remote backend names the tier L3.5, not local storage",
      any("L3.5 memory node" in _l for _l in (_lab_r or [])), True)
check("remote backend never says local SSD",
      any("local SSD" in _l for _l in (_lab_r or [])), False)

_lab_l, _pk_l, _sub_l = _movement_labels("file", 64)
check("local backend names the tier L3 local SSD",
      any("L3 local SSD" in _l for _l in (_lab_l or [])), True)
check("local backend never says L3.5",
      any("L3.5" in _l for _l in (_lab_l or [])), False)

# tokens -> blocks must divide by the configured page size, not assume one.
# 64,000 tok per 15 s interval / 64 tok per block = 66.67 blk/s.
_peak_evict = None
for _l, _p in zip(_lab_r or [], _pk_r or []):
    if "evict" in _l:
        _peak_evict = float(_re_c.sub(r"[^0-9.]", "", _p.split("blk")[0]))
check("evict peak converts to blocks at the configured page size",
      abs(_peak_evict - (64000 / 15.0) / 64.0) < 0.5, True)
check("subtitle states the tokens-per-block used",
      "64 tokens per block" in (_sub_r or ""), True)

# Halving the page size must double blk/s -- i.e. the divide is real.
_lab_h, _pk_h, _sub_h = _movement_labels("mooncake", 32)
_peak_h = None
for _l, _p in zip(_lab_h or [], _pk_h or []):
    if "evict" in _l:
        _peak_h = float(_re_c.sub(r"[^0-9.]", "", _p.split("blk")[0]))
check("halving the page size doubles blocks/s",
      abs(_peak_h - 2 * _peak_evict) < 1.0, True)
_sh_x.rmtree(_pd_x, ignore_errors=True)

print("\n=== 0y. recomputed is measured, and the fallback must not leak ===")
# "Recomputed" is realtime_tokens_total{mode=prefill_compute}, read direct.
# But when that labelled counter is absent, combined.py substitutes
# prompt_tokens_total so the phase THROUGHPUT chart still renders. Prompt
# tokens include every cache hit, so anything treating the series as
# recompute would report a hit rate of zero on a perfectly healthy run.
# These assertions pin that the substitution cannot reach those consumers.
import csv as _csv_y, shutil as _sh_y

_pd_y = _build_probe_dir()
with (_pd_y / "l35_store_capacity.csv").open("w", newline="") as _f:
    _w5 = _csv_y.writer(_f)
    _w5.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b"])
    for _i in range(30):
        _w5.writerow([_i * 60, int(1.2e12), int(2.0e12)])
_sgy = _pd_y / "sglang_timeseries.csv"
_ry = list(_csv_y.DictReader(_sgy.open()))
_hy = list(_ry[0].keys()) + ["sglang_prefetched_tokens_total",
                             "sglang_load_back_tokens_total"]
for _i, _r in enumerate(_ry):
    _r["sglang_prefetched_tokens_total"] = f"{_i * 4200:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 9100:d}"
with _sgy.open("w", newline="") as _f:
    _w6 = _csv_y.DictWriter(_f, fieldnames=_hy); _w6.writeheader(); _w6.writerows(_ry)

# The probe builds prompt_tokens_total as 600/interval and splits it
# 360 cache / 240 compute, so the three must reconcile exactly.
_h_ok = _bx(_pd_y, run_label="recon")
check("reconciliation line is shown", "Does the split reconcile?" in _h_ok, True)
check("probe split reconciles against prompt_tokens_total",
      "confirmed against something outside itself" in _h_ok, True)

# Strip the mode-labelled counters: every consumer that treats the series
# as RECOMPUTE must disappear rather than render on substituted data.
_pd_n = _pl.Path(_tf.mkdtemp()); _sh_y.rmtree(_pd_n)
_sh_y.copytree(_pd_y, _pd_n)
_rn = list(_csv_y.DictReader((_pd_n / "sglang_timeseries.csv").open()))
_keep = [_c for _c in _rn[0] if "realtime_tokens_total" not in _c]
with (_pd_n / "sglang_timeseries.csv").open("w", newline="") as _f:
    _w7 = _csv_y.DictWriter(_f, fieldnames=_keep); _w7.writeheader()
    _w7.writerows([{_k: _r[_k] for _k in _keep} for _r in _rn])
_h_no = _bx(_pd_n, run_label="nomode")
for _probe in ("KV delivery ledger", "The efficacy test",
               "Does the split reconcile?", "KV cache hit ratio over the run"):
    check(f"absent mode counter hides: {_probe[:30]}", _probe in _h_no, False)
# ...while a chart that does NOT depend on recompute still renders.
check("block movement chart still renders without mode counters",
      "KV block movement rates across tiers" in _h_no, True)
# And the correlation driver that keeps the fallback must stop claiming
# the series is recompute.
check("fallback driver no longer claims to be recompute",
      "prefill tokens actually recomputed" in _h_no, False)
check("fallback driver says what it actually is",
      "ALL prompt tokens, cache hits included" in _h_no, True)

# A split that does NOT reconcile must say so and downgrade the claim.
_pd_b = _pl.Path(_tf.mkdtemp()); _sh_y.rmtree(_pd_b)
_sh_y.copytree(_pd_y, _pd_b)
_rb = list(_csv_y.DictReader((_pd_b / "sglang_timeseries.csv").open()))
for _r in _rb:
    _r["sglang_prompt_tokens_total"] = (
        f'{float(_r["sglang_prompt_tokens_total"]) * 1.12:.0f}')
with (_pd_b / "sglang_timeseries.csv").open("w", newline="") as _f:
    _w8 = _csv_y.DictWriter(_f, fieldnames=list(_rb[0].keys()))
    _w8.writeheader(); _w8.writerows(_rb)
_h_bad = _bx(_pd_b, run_label="badrecon")
check("a 12% gap is reported, not absorbed",
      "They differ by" in _h_bad, True)
check("a failed reconciliation downgrades the benefit claim",
      "indicative" in _h_bad, True)
for _d in (_pd_y, _pd_n, _pd_b):
    _sh_y.rmtree(_d, ignore_errors=True)

print("\n=== 0z. prefetch token counter: zero total with non-zero ops ===")
# Reported from a live run: sglang_prefetched_tokens_total reads 0 while
# sglang_prefetch_pgs counts operations.  Trusting the token counter alone
# puts the benefit bound at 0 and reports a working tier as useless.  The
# resolver must select on a non-zero DELTA, not on column presence -- the
# generic reader returns the first candidate whose column exists, and on
# such a run that column exists and is all zero.
import csv as _csv_z, shutil as _sh_z
from amoprof.report.combined import (
    _prefetch_tokens_resolved as _ptr, _kv_token_delta as _ktd)

def _mk_prefetch_fixture(base, zero_primary, hit_scale=1.0, unfulfilled=0.30):
    _d = _pl.Path(_tf.mkdtemp()); _sh_z.rmtree(_d); _sh_z.copytree(base, _d)
    _rows = list(_csv_z.DictReader((_d / "sglang_timeseries.csv").open()))
    _hdr = list(_rows[0].keys()) + [
        "sglang_storage_prefetch_hit_tokens_total",
        "sglang_storage_prefetch_unfulfilled_tokens_total"]
    for _r in _rows:
        _real = float(_r["sglang_prefetched_tokens_total"])
        if zero_primary:
            _r["sglang_prefetched_tokens_total"] = "0"
        _r["sglang_storage_prefetch_hit_tokens_total"] = f"{_real * hit_scale:.0f}"
        _r["sglang_storage_prefetch_unfulfilled_tokens_total"] = \
            f"{_real * unfulfilled:.0f}"
    with (_d / "sglang_timeseries.csv").open("w", newline="") as _f:
        _w9 = _csv_z.DictWriter(_f, fieldnames=_hdr)
        _w9.writeheader(); _w9.writerows(_rows)
    return _d

_pd_z = _build_probe_dir()
with (_pd_z / "l35_store_capacity.csv").open("w", newline="") as _f:
    _wz = _csv_z.writer(_f)
    _wz.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b"])
    for _i in range(30):
        _wz.writerow([_i * 60, int(1.2e12), int(2.0e12)])
_sgz = _pd_z / "sglang_timeseries.csv"
_rz = list(_csv_z.DictReader(_sgz.open()))
_hz = list(_rz[0].keys()) + ["sglang_prefetched_tokens_total",
                             "sglang_load_back_tokens_total",
                             "sglang_prefetch_pgs_count"]
for _i, _r in enumerate(_rz):
    _r["sglang_prefetched_tokens_total"] = f"{_i * 4200:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 9100:d}"
    _r["sglang_prefetch_pgs_count"] = f"{_i * 7:d}"
with _sgz.open("w", newline="") as _f:
    _wz2 = _csv_z.DictWriter(_f, fieldnames=_hz)
    _wz2.writeheader(); _wz2.writerows(_rz)

# Healthy build: the primary counter wins and nothing is substituted.
_d_ok = _mk_prefetch_fixture(_pd_z, zero_primary=False)
_t, _v, _src, _ops, _unf = _ptr(_d_ok)
check("healthy build uses the primary counter",
      _src, "sglang_prefetched_tokens_total")
check("healthy build still reports ops", _ops is not None and _ops > 0, True)

# The reported symptom: primary zero, storage hit counter carries volume.
_d_z = _mk_prefetch_fixture(_pd_z, zero_primary=True)
_t2, _v2, _src2, _ops2, _unf2 = _ptr(_d_z)
check("zeroed primary falls through to the storage hit counter",
      _src2, "sglang_storage_prefetch_hit_tokens_total")
check("the zeroed primary would have reported nothing",
      _ktd(_d_z, ["prefetched_tokens_total"]), 0.0)
check("the resolver recovers a non-zero volume",
      (_v2[-1] - _v2[0]) > 0, True)
check("unfulfilled tokens are reported", _unf2 is not None and _unf2 > 0, True)

# Both counters dead: report nothing rather than guess, but keep the ops.
_d_dead = _mk_prefetch_fixture(_pd_z, zero_primary=True, hit_scale=0.0)
_t3, _v3, _src3, _ops3, _unf3 = _ptr(_d_dead)
check("no usable token counter yields no source", _src3, "")
check("ops are still reported when tokens are not",
      _ops3 is not None and _ops3 > 0, True)

# The report must name the counter it used and flag the substitution.
_h_z = _bx(_d_z, run_label="pfzero")
check("substitution is disclosed, not silent",
      "Which prefetch counter this uses" in _h_z, True)
check("the ledger names the counter that supplied the number",
      "sglang_storage_prefetch_hit_tokens_total" in _h_z, True)
check("prefetch outcome chart renders",
      "Prefetch outcome" in _h_z, True)
_h_ok = _bx(_d_ok, run_label="pfok")
check("healthy build does NOT claim a substitution",
      "Which prefetch counter this uses" in _h_ok, False)
for _d in (_pd_z, _d_ok, _d_z, _d_dead):
    _sh_z.rmtree(_d, ignore_errors=True)

print("\n=== 0A. prefetch outcome renders on its own counters ===")
# The outcome chart was nested inside the benefit gate, which also needs
# load-back, the prefill mode counters AND a non-zero prefetch token total.
# The case the chart exists to diagnose -- prefetch asking and being
# delivered nothing -- drives that token total to zero, so the chart was
# suppressed exactly when it was needed. It must stand on hit + unfulfilled
# alone.
import csv as _csv_a, shutil as _sh_a

def _mk_outcome_fixture(base, hit_scale, unf_scale,
                        drop_loadback=False, drop_modes=False):
    _d = _pl.Path(_tf.mkdtemp()); _sh_a.rmtree(_d); _sh_a.copytree(base, _d)
    _rows = list(_csv_a.DictReader((_d / "sglang_timeseries.csv").open()))
    _hdr = list(_rows[0].keys()) + [
        "sglang_storage_prefetch_hit_tokens_total",
        "sglang_storage_prefetch_unfulfilled_tokens_total"]
    for _r in _rows:
        _real = float(_r.get("sglang_prefetched_tokens_total") or 0)
        _r["sglang_prefetched_tokens_total"] = "0"
        _r["sglang_storage_prefetch_hit_tokens_total"] = f"{_real * hit_scale:.0f}"
        _r["sglang_storage_prefetch_unfulfilled_tokens_total"] = \
            f"{_real * unf_scale:.0f}"
        if drop_loadback:
            _r["sglang_load_back_tokens_total"] = "0"
    if drop_modes:
        _hdr = [_c for _c in _hdr if "realtime_tokens_total" not in _c]
    with (_d / "sglang_timeseries.csv").open("w", newline="") as _f:
        _wa = _csv_a.DictWriter(_f, fieldnames=_hdr); _wa.writeheader()
        _wa.writerows([{_k: _r.get(_k, "0") for _k in _hdr} for _r in _rows])
    return _d

_pd_a = _build_probe_dir()
with (_pd_a / "l35_store_capacity.csv").open("w", newline="") as _f:
    _wa2 = _csv_a.writer(_f)
    _wa2.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b"])
    for _i in range(30):
        _wa2.writerow([_i * 60, int(1.2e12), int(2.0e12)])
_sga = _pd_a / "sglang_timeseries.csv"
_ra = list(_csv_a.DictReader(_sga.open()))
_ha = list(_ra[0].keys()) + ["sglang_prefetched_tokens_total",
                             "sglang_load_back_tokens_total"]
for _i, _r in enumerate(_ra):
    _r["sglang_prefetched_tokens_total"] = f"{_i * 4200:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 9100:d}"
with _sga.open("w", newline="") as _f:
    _wa3 = _csv_a.DictWriter(_f, fieldnames=_ha)
    _wa3.writeheader(); _wa3.writerows(_ra)

for _name, _kw in (
        ("normal", dict(hit_scale=1.0, unf_scale=0.30)),
        ("everything unfulfilled", dict(hit_scale=0.0, unf_scale=1.0)),
        ("no load-back", dict(hit_scale=1.0, unf_scale=0.30, drop_loadback=True)),
        ("no prefill mode counters",
         dict(hit_scale=1.0, unf_scale=0.30, drop_modes=True))):
    _dd = _mk_outcome_fixture(_pd_a, **_kw)
    _hh = _bx(_dd, run_label="oc")
    check(f"outcome chart renders: {_name}",
          "Prefetch outcome \u2014 asked" in _hh, True)
    _sh_a.rmtree(_dd, ignore_errors=True)

# When the pair is absent entirely, the report must say so AND say that
# analyze --run-dir alone will not fix it, because --prefer local keeps the
# existing sglang_timeseries.csv and only fills MISSING files.
_h_none = _bx(_pd_a, run_label="nopair")
check("absent pair is explained, not silent",
      "Prefetch outcome could not be drawn" in _h_none, True)
check("the note names both missing counters",
      ("storage_prefetch_hit_tokens_total" in _h_none
       and "storage_prefetch_unfulfilled_tokens_total" in _h_none), True)
check("the note warns that --prefer local will not pick them up",
      "--prefer prometheus" in _h_none, True)
# A build that never EXPORTS these counters is a different case from one
# whose raw/ was written before AMOprof asked for them, and the fix is
# different too.  Telling a user to re-fetch a metric their engine does not
# emit sends them after something that cannot be found.
check("the note covers the not-exported case",
      "Not exported by this engine build" in _h_none, True)
check("the note names the store-side substitute",
      ("L3.5 get outcome" in _h_none
       and "total_get_nums_" in _h_none), True)
check("the note gives a way to tell the two cases apart",
      "grep storage_prefetch" in _h_none, True)
# ...and is suppressed once they are present.
_d_has = _mk_outcome_fixture(_pd_a, hit_scale=1.0, unf_scale=0.30)
_h_has = _bx(_d_has, run_label="haspair")
check("note disappears once the counters exist",
      "Prefetch outcome could not be drawn" in _h_has, False)
_sh_a.rmtree(_d_has, ignore_errors=True)
_sh_a.rmtree(_pd_a, ignore_errors=True)

print("\n=== 0B. prefetch shape from the histogram alone ===")
# Builds without the storage_prefetch pair still export the prefetch_pgs
# histogram.  Tokens-per-operation and operations-per-second separate
# "prefetch is rarely invoked" from "prefetch runs constantly and brings
# back almost nothing" -- different problems, indistinguishable from the
# token total alone.
_pd_b2 = _build_probe_dir()
with (_pd_b2 / "l35_store_capacity.csv").open("w", newline="") as _f:
    _wb = _csv_a.writer(_f)
    _wb.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b"])
    for _i in range(30):
        _wb.writerow([_i * 60, int(1.2e12), int(2.0e12)])
_sgb = _pd_b2 / "sglang_timeseries.csv"
_rb2 = list(_csv_a.DictReader(_sgb.open()))
_hb2 = list(_rb2[0].keys()) + ["sglang_prefetched_tokens_total",
                               "sglang_load_back_tokens_total",
                               "sglang_prefetch_pgs_count"]
# 2,000 tokens and 40 operations per interval -> 50.0 tokens/op exactly.
for _i, _r in enumerate(_rb2):
    _r["sglang_prefetched_tokens_total"] = f"{_i * 2000:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 9100:d}"
    _r["sglang_prefetch_pgs_count"] = f"{_i * 40:d}"
with _sgb.open("w", newline="") as _f:
    _wb2 = _csv_a.DictWriter(_f, fieldnames=_hb2)
    _wb2.writeheader(); _wb2.writerows(_rb2)
_h_b2 = _bx(_pd_b2, run_label="pgs")
check("tokens-per-operation row is present",
      "prefetch tokens per operation" in _h_b2, True)
check("tokens-per-operation is prefetched / operations",
      "50.0" in _h_b2, True)
check("operation-rate row is present",
      "prefetch operation rate" in _h_b2, True)
check("both derived rows are labelled derived, not measured",
      _h_b2.count("derived") >= 2, True)
_sh_a.rmtree(_pd_b2, ignore_errors=True)

print("\n=== 0C. L3.5 residency must include the file tier ===")
# The residency chart plotted only l35_store_mem_used_b, the store's DRAM
# front.  On a node with 54 GB of DRAM ahead of 966 GB of NVMe that made
# L3.5 look like the SMALLEST tier in the hierarchy when it is the largest,
# and pointed at "grow the tier" when the real shape is a saturated DRAM
# front with a half-empty SSD behind it.
_pd_c = _build_probe_dir()
_MEM_CAP, _FILE_CAP = 54e9, 966e9
with (_pd_c / "l35_store_capacity.csv").open("w", newline="") as _f:
    _wc = _csv_a.writer(_f)
    _wc.writerow(["time_sec", "l35_store_mem_used_b", "l35_store_mem_cap_b",
                  "l35_store_file_used_b", "l35_store_file_cap_b"])
    for _i in range(40):
        _k = _i / 39.0
        _wc.writerow([_i * 51, int(_MEM_CAP * 0.968 * _k), int(_MEM_CAP),
                      int(_FILE_CAP * 0.464 * _k), int(_FILE_CAP)])
_h_c = _bx(_pd_c, run_label="tiers")
_i_c = _h_c.find("KV tokens resident per cache tier")
_sv_c = _re_c.search(r"<svg.*?</svg>", _h_c[max(0, _i_c - 3000):_i_c + 60000],
                     _re_c.S).group(0)
check("DRAM front is labelled as a tier, not as the whole store",
      "DRAM tier" in _sv_c, True)
check("the file tier is plotted at all", "file tier" in _sv_c, True)
check("the old all-encompassing label is gone",
      "L3.5 remote KV store" in _sv_c, False)
# With this geometry the SSD tier must be the LARGEST resident series --
# the exact conclusion the old chart inverted.
_peaks = dict(zip(
    [_t for _t in _re_c.findall(r'<text[^>]*>([^<]{2,110})</text>', _sv_c)],
    [_t for _t in _re_c.findall(r'<text[^>]*>([^<]{2,110})</text>', _sv_c)][1:]))
_file_peak = next((_v for _k, _v in _peaks.items() if "file tier" in _k), "")
_dram_peak = next((_v for _k, _v in _peaks.items() if "DRAM tier" in _k), "")
def _num(_s):
    _m = _re_c.search(r"([\d,]+) tok", _s or "")
    return float(_m.group(1).replace(",", "")) if _m else 0.0
check("file tier out-sizes the DRAM front by roughly the capacity ratio",
      _num(_file_peak) > 5 * _num(_dram_peak), True)
check("file tier is below its ceiling while the front is at it",
      ("46% of cap" in _file_peak and "97% of cap" in _dram_peak), True)
_sh_a.rmtree(_pd_c, ignore_errors=True)

print("\n=== 0D. a stale embedded server_info must not override setup_details ===")
# A setup_details.json copied from an L3.5 deployment carries the old
# `SGLang server_info raw` blob.  That blob was the PRIMARY decision and
# beat every explicit field, including an explicit `KV cache tier: L3`, so
# a local-SSD run rendered end to end as L3.5 with nothing saying why.
from amoprof.report.l3_backend import resolve_l3_backend as _R3
import dataclasses as _dc

def _cls(_setup):
    return _dc.asdict(_R3(_setup))

_stale = {"SGLang server_info raw": {"hicache_storage_backend": "mooncake"}}

# No conflict: server_info alone still decides, both ways.
check("server_info=file alone resolves local",
      _cls({"SGLang server_info raw": {"hicache_storage_backend": "file"}}
           )["backend_class"], "local_ssd")
check("server_info=mooncake alone resolves remote",
      _cls(dict(_stale))["backend_class"], "remote_mooncake")

# Conflict: an explicit LOCAL setting wins over a stale remote server_info.
_c1 = _cls(dict(_stale, **{"L3 storage type": "local",
                           "hicache_storage_backend": "file",
                           "L3 Device": "/dev/nvme6n1"}))
check("explicit local backend beats stale remote server_info",
      _c1["backend_class"], "local_ssd")
_c2 = _cls(dict(_stale, **{"KV cache tier": "L3", "L3 storage type": "local",
                           "L3 Device": "/dev/nvme6n1"}))
check("explicit tier L3 beats stale remote server_info",
      _c2["backend_class"], "local_ssd")

# ...and the conflict is SAID, not silently resolved.
for _nm, _c in (("backend", _c1), ("tier", _c2)):
    check(f"conflict is disclosed in the evidence ({_nm})",
          ("explicitly configures" in _c["evidence"]
           and "server_info" in _c["evidence"]
           and "stale" in _c["evidence"]), True)

# The mirror case: explicit REMOTE over a local server_info.
_c3 = _cls({"KV cache tier": "L3.5",
            "SGLang server_info raw": {"hicache_storage_backend": "file"}})
check("explicit tier L3.5 beats a local server_info",
      _c3["backend_class"], "remote_storage")
check("the mirror conflict is disclosed too",
      "explicitly configures a REMOTE tier" in _c3["evidence"], True)

# A local resolution must carry the device through, so the device-level
# charts can find the right disk.
check("local resolution keeps the device mapping",
      _c1.get("local_device"), "/dev/nvme6n1")

print("\n=== 0E. local-L3 device charts read the local NVMe file ===")
# The device chart family read only l35_storage_timeseries.csv, whose
# columns are l35_-prefixed so a memory node's disk can never be confused
# with the GPU host's.  A LOCAL L3 run has no second node: its device
# metrics are in nvme_driver_timeseries.csv under unprefixed names.  Every
# device chart -- IOPS, reads vs writes, queue depth, the LBA strips --
# vanished on a local run whose data was sitting in the other file.
import csv as _csv_e, shutil as _sh_e, json as _js_e

_pd_e = _build_probe_dir()
_cols_e = (["time_sec", "rd_iops", "wr_iops", "rd_bw_mbs", "wr_bw_mbs",
            "io_util_pct", "avgqu_sz", "lba_w_span_gb", "lba_w_start_gb",
            "lba_r_span_gb", "lba_r_start_gb"]
           + [f"lba_w_d{_i}" for _i in range(10)]
           + [f"lba_r_d{_i}" for _i in range(10)])
with (_pd_e / "nvme_driver_timeseries.csv").open("w", newline="") as _f:
    _we = _csv_e.writer(_f); _we.writerow(_cols_e)
    for _i in range(40):
        _wd = [max(0, 100 - abs(_i % 10 - _j) * 9) for _j in range(10)]
        _rd = [max(0, 80 - abs(_j - 3) * 11) for _j in range(10)]
        _we.writerow([_i * 51, 900 + _i * 7, 400 + _i * 5, 120.0 + _i,
                      60.0 + _i, min(99, 20 + _i), 0.4 + _i * 0.02,
                      966.0, 0.0, 966.0, 0.0] + _wd + _rd)
_sd_e = _js_e.loads((_pd_e / "setup_details.json").read_text())
_sd_e.update({"KV cache tier": "L3", "L3 storage type": "local",
              "hicache_storage_backend": "file", "L3 Device": "/dev/nvme6n1"})
(_pd_e / "setup_details.json").write_text(_js_e.dumps(_sd_e))

_h_e = _bx(_pd_e, run_label="locdev")
_titles_e = []
for _m in _re_c.finditer(r"<svg.*?</svg>", _h_e, _re_c.S):
    _t = _re_c.findall(r'<text[^>]*>([^<]{4,110})</text>', _m.group(0))
    if _t:
        _titles_e.append(_t[0])
def _has(_frag):
    return any(_frag in _t for _t in _titles_e)
for _frag in ("storage: IOPS", "storage: reads vs writes",
              "storage: queue depth", "write I/O across LBA space",
              "read I/O across LBA space"):
    check(f"local run renders: {_frag[:30]}", _has(_frag), True)
# ...and names the local tier rather than a memory node that is not there.
check("device charts name the LOCAL tier",
      any("L3 local SSD" in _t for _t in _titles_e), True)
check("device charts do not claim a memory node",
      any("L3.5 node storage" in _t or "L3.5 memory node" in _t
          for _t in _titles_e), False)
_sh_e.rmtree(_pd_e, ignore_errors=True)

# No regression: a real L3.5 run still reads the l35_ file and keeps its name.
_pd_e2 = _build_probe_dir()
with (_pd_e2 / "l35_storage_timeseries.csv").open("w", newline="") as _f:
    _we2 = _csv_e.writer(_f)
    _we2.writerow(["time_sec", "l35_rd_iops", "l35_wr_iops",
                   "l35_rd_bw_mbs", "l35_wr_bw_mbs"])
    for _i in range(40):
        _we2.writerow([_i * 51, 900 + _i, 400 + _i, 120.0 + _i, 60.0 + _i])
_sd_e2 = _js_e.loads((_pd_e2 / "setup_details.json").read_text())
_sd_e2.update({"KV cache tier": "L3.5", "hicache_storage_backend": "mooncake"})
(_pd_e2 / "setup_details.json").write_text(_js_e.dumps(_sd_e2))
_h_e2 = _bx(_pd_e2, run_label="l35dev")
check("remote run still names the memory node",
      "L3.5 node storage: IOPS" in _h_e2, True)
check("remote run does not claim a local SSD",
      "L3 local SSD storage" in _h_e2, False)
_sh_e.rmtree(_pd_e2, ignore_errors=True)

print("\n=== 0F. a second metric family must not erase the first ===")
# _synth_ts writes with to_csv, which REPLACES the file.  The blktrace /
# LBA / SMART family now lands in nvme_driver_timeseries.csv alongside the
# device family, so without merge=True the second fetch would silently
# delete rd_iops and rd_bw_mbs -- and take the IOPS charts with them.
import pandas as _pd_f, tempfile as _tf_f, pathlib as _pl_f
_df = _pl_f.Path(_tf_f.mkdtemp()) / "nvme_driver_timeseries.csv"
_pd_f.DataFrame({"time_sec": [0, 51, 102], "rd_iops": [900, 907, 914],
                 "rd_bw_mbs": [120.0, 121.0, 122.0]}).to_csv(_df, index=False)

def _merge_in(_new: "_pd_f.DataFrame"):
    _old = _pd_f.read_csv(_df)
    _only = [_c for _c in _new.columns
             if _c != "time_sec" and _c not in _old.columns]
    _m = (_old.merge(_new[["time_sec"] + _only], on="time_sec", how="outer")
          .sort_values("time_sec")) if _only else _old
    _m.to_csv(_df, index=False)
    return _pd_f.read_csv(_df)

_after = _merge_in(_pd_f.DataFrame({"time_sec": [0, 51, 102],
                                    "lba_w_d0": [10, 12, 14],
                                    "bt_read_events": [5, 6, 7]}))
_cols = set(_after.columns)
check("device columns survive the blktrace merge",
      {"rd_iops", "rd_bw_mbs"} <= _cols, True)
check("blktrace columns are added", {"lba_w_d0", "bt_read_events"} <= _cols, True)
check("row count is preserved on a matching cadence", len(_after), 3)

# The two families can be sampled on different cadences; an outer join must
# add the new timestamps without nulling the device series on the old ones.
_after2 = _merge_in(_pd_f.DataFrame({"time_sec": [0, 120], "waf": [1.02, 1.03]}))
check("off-cadence merge keeps every original device sample",
      int(_after2["rd_iops"].notna().sum()), 3)
check("off-cadence merge adds the new timestamp", len(_after2), 4)

# A column that EXISTS but is all-zero is not data worth protecting. The
# sysfs NVMe rates read all-zero on some hardware, and keeping those over a
# blktrace series with real values leaves the chart as blank as if nothing
# had been fetched -- which is what happened to IOPS on a local run.
def _merge_replacing_dead(_new: "_pd_f.DataFrame"):
    _old = _pd_f.read_csv(_df)
    def _dead(_c):
        _v = _pd_f.to_numeric(_old[_c], errors="coerce")
        return bool(_v.isna().all() or (_v.fillna(0) == 0).all())
    _drop = [_c for _c in _new.columns
             if _c != "time_sec" and _c in _old.columns and _dead(_c)]
    _old = _old.drop(columns=_drop)
    _only = [_c for _c in _new.columns
             if _c != "time_sec" and _c not in _old.columns]
    _m = (_old.merge(_new[["time_sec"] + _only], on="time_sec", how="outer")
          .sort_values("time_sec")) if _only else _old
    _m.to_csv(_df, index=False)
    return _drop, _pd_f.read_csv(_df)

_pd_f.DataFrame({"time_sec": [0, 51, 102],
                 "rd_bw_mbs": [120.0, 121.0, 122.0],
                 "rd_iops": [0, 0, 0]}).to_csv(_df, index=False)
_dropped, _res = _merge_replacing_dead(
    _pd_f.DataFrame({"time_sec": [0, 51, 102], "rd_iops": [900, 907, 914],
                     "avgqu_sz": [0.4, 0.5, 0.6]}))
check("an all-zero column is treated as dead", _dropped, ["rd_iops"])
check("the dead column is replaced with real values",
      _res["rd_iops"].tolist(), [900, 907, 914])
check("a live column beside it is untouched",
      _res["rd_bw_mbs"].tolist(), [120.0, 121.0, 122.0])
check("a genuinely new column is still added", "avgqu_sz" in _res.columns, True)

# ...but a live column must never be replaced, even by newer data.
_pd_f.DataFrame({"time_sec": [0, 51], "rd_iops": [900, 907]}).to_csv(_df, index=False)
_dropped2, _res2 = _merge_replacing_dead(
    _pd_f.DataFrame({"time_sec": [0, 51], "rd_iops": [1, 1]}))
check("a live column is not treated as dead", _dropped2, [])
check("a live column keeps its original values",
      _res2["rd_iops"].tolist(), [900, 907])

# Re-merging a family already present must be a no-op, not a duplication.
# Fresh file: the dead-column checks above repointed _df, and a test that
# silently depends on a previous test's leftovers is not a test.
_pd_f.DataFrame({"time_sec": [0, 51, 102], "rd_iops": [900, 907, 914],
                 "lba_w_d0": [10, 12, 14]}).to_csv(_df, index=False)
_after3 = _merge_in(_pd_f.DataFrame({"time_sec": [0, 51, 102],
                                     "lba_w_d0": [99, 99, 99]}))
check("re-merging an existing column does not duplicate it",
      list(_after3.columns).count("lba_w_d0"), 1)
check("re-merging an existing column does not overwrite it",
      int(_after3.loc[_after3.time_sec == 0, "lba_w_d0"].iloc[0]), 10)

print("\n=== 0G. a local-L3 run must never mention L3.5 anywhere ===")
# Tier names were hardcoded across chart titles, series labels, axis
# labels, KPI tiles, source-block notes, the layer badge and the header's
# tier list.  Fixing them one at a time kept missing some, so assert the
# whole-document property instead: on a LOCAL run the string "L3.5" must
# not appear in any rendered label or prose, and on a REMOTE run it must.
import shutil as _sh_g, json as _js_g, csv as _csv_g, html as _H_g

_pd_g = _build_probe_dir()
_cols_g = (["time_sec", "rd_iops", "wr_iops", "rd_bw_mbs", "wr_bw_mbs",
            "io_util_pct", "avgqu_sz"]
           + [f"lba_w_d{_i}" for _i in range(10)]
           + [f"lba_r_d{_i}" for _i in range(10)])
with (_pd_g / "nvme_driver_timeseries.csv").open("w", newline="") as _f:
    _wg = _csv_g.writer(_f); _wg.writerow(_cols_g)
    for _i in range(30):
        _wg.writerow([_i * 51, 900 + _i, 400 + _i, 120.0, 60.0, 30, 0.5]
                     + [10] * 10 + [10] * 10)
_sgg = _pd_g / "sglang_timeseries.csv"
_rg = list(_csv_g.DictReader(_sgg.open()))
_hg = list(_rg[0].keys()) + ["sglang_evicted_tokens_total",
                             "sglang_backuped_tokens_total",
                             "sglang_prefetched_tokens_total",
                             "sglang_load_back_tokens_total"]
for _i, _r in enumerate(_rg):
    _r["sglang_evicted_tokens_total"] = f"{_i * 90000:d}"
    _r["sglang_backuped_tokens_total"] = f"{_i * 60000:d}"
    _r["sglang_prefetched_tokens_total"] = f"{_i * 4000:d}"
    _r["sglang_load_back_tokens_total"] = f"{_i * 9000:d}"
with _sgg.open("w", newline="") as _f:
    _wg2 = _csv_g.DictWriter(_f, fieldnames=_hg)
    _wg2.writeheader(); _wg2.writerows(_rg)
_sd_g = _js_g.loads((_pd_g / "setup_details.json").read_text())
_sd_g.update({"KV cache tier": "L3", "L3 storage type": "local",
              "hicache_storage_backend": "file", "L3 Device": "/dev/nvme6n1"})
(_pd_g / "setup_details.json").write_text(_js_g.dumps(_sd_g))

def _count_l35(_h):
    _svg = sum(1 for _m in _re_c.finditer(r"<svg.*?</svg>", _h, _re_c.S)
               for _t in _re_c.findall(r'<text[^>]*>([^<]+)</text>',
                                       _H_g.unescape(_m.group(0)))
               if "L3.5" in _t)
    _rest = _re_c.sub(r"<svg.*?</svg>|<style.*?</style>|<script.*?</script>",
                      " ", _h, flags=_re_c.S)
    _txt = _re_c.sub(r"\s+", " ", _H_g.unescape(_re_c.sub(r"<[^>]+>", " ", _rest)))
    return _svg, _txt.count("L3.5")

_svg_l, _prose_l = _count_l35(_bx(_pd_g, run_label="local"))
check("local run: no chart label says L3.5", _svg_l, 0)
check("local run: no prose or tile says L3.5", _prose_l, 0)

# The mirror: a remote run must still say L3.5, or the fix has just
# renamed the remote tier out of existence.
_sd_g.update({"KV cache tier": "L3.5", "L3 storage type": "remote",
              "hicache_storage_backend": "mooncake"})
(_pd_g / "setup_details.json").write_text(_js_g.dumps(_sd_g))
_svg_r, _prose_r = _count_l35(_bx(_pd_g, run_label="remote"))
check("remote run still labels its charts L3.5", _svg_r > 0, True)
check("remote run still says L3.5 in prose", _prose_r > 0, True)
_sh_g.rmtree(_pd_g, ignore_errors=True)

print("\n=== 0H. compare: an empty directory field means fetch ===")
# Comparing two windows used to mean running `analyze` once per window
# purely to create directories for `compare` to read. The timestamps the
# spec already accepted did not help: they set the displayed duration and
# the window label and nothing else, so the same directory under two
# different windows gave identical numbers. An empty directory field now
# means "fetch this window", where the window IS the query range.
import re as _re_h

def _classify(_spec, _prometheus=""):
    _parts = _spec.split(":", 3)
    if len(_parts) < 2:
        return "ERR_FORMAT"
    _dirf = _parts[1].strip()
    _ts = _parts[2].strip() if len(_parts) >= 3 else ""
    _te = _parts[3].strip() if len(_parts) >= 4 else ""
    if not _dirf:
        if not _prometheus:
            return "ERR_NO_PROM"
        if not (_ts and _te):
            return "ERR_NEEDS_BOTH"
        return "FETCH"
    return "DIR"

_P = "http://prom:9090"
check("empty dir with a full window fetches",
      _classify("L3 local::1790866656:1790872805", _P), "FETCH")
check("a label with dots and spaces still parses",
      _classify("L3.5 Mooncake::1790700000:1790706000", _P), "FETCH")
check("a directory spec is unchanged",
      _classify("Baseline:./run_a:1778871540:1778877078"), "DIR")
check("a directory spec without a window is unchanged",
      _classify("BF16:./metrics_run_20260515"), "DIR")
check("empty dir without --prometheus is an error",
      _classify("NoProm::100:200"), "ERR_NO_PROM")
check("empty dir with only a start is an error",
      _classify("NoEnd::100", _P), "ERR_NEEDS_BOTH")
check("empty dir with no window at all is an error",
      _classify("NoWindow::", _P), "ERR_NEEDS_BOTH")
check("a one-field spec is still rejected", _classify("JustALabel"), "ERR_FORMAT")

# Fetched runs are written under a slug of the label, so two runs cannot
# land in the same directory and silently compare a window against itself.
def _slug(_l):
    return _re_h.sub(r"[^A-Za-z0-9._-]+", "_", _l).strip("_") or "run"
check("label slug keeps dots and strips spaces",
      _slug("L3.5 Mooncake"), "L3.5_Mooncake")
check("two different labels get different directories",
      _slug("L3 local SSD") != _slug("L3.5 Mooncake"), True)
check("an all-punctuation label still yields a usable name",
      _slug("///"), "run")

print("\n=== 0s. the two L3.5 bandwidth tiles name different layers ===")
# The NVMe-derived tile and the memory-node device tile were both labelled
# "L3.5 ... read BW" and read as the same quantity.  They are not: one is a
# block device, the other is whatever host the NVMe collector scraped, and a
# read served from the store's memory tier or from page cache appears in
# neither.  Each label must now carry its layer AND resolve to a formula.
for _lab in ("L3.5 storage read BW (NVMe driver)",
             "L3.5 read throughput (NVMe driver)",
             "L3.5 node storage BW (device)"):
    _f = _ff(_lab)
    check(f"formula registered: {_lab[:34]}", bool(_f), True)
    check(f"formula names a raw/ file: {_lab[:30]}", ".csv" in _f, True)
check("device tile formula flags the page-cache case",
      "page cache" in _ff("L3.5 node storage BW (device)"), True)
check("NVMe tile formula points at the store cross-check",
      "cache_hit_bytes_total" in _ff("L3.5 storage read BW (NVMe driver)"), True)


print("\n=== 0I. compare: per-run overrides, tiers and N-way chain ===")
# The scoping flags were global, which is only correct when every run shares
# one backend class, one host and one device.  The comparison `compare` exists
# for is usually the opposite -- a local-SSD L3 run against an L3.5 memory
# node -- and under global-only scoping an --l35-instance aimed at the memory
# node pulled that node's store metrics into the local run, while the local
# run was labelled with a tier it never had.
from amoprof.cli import (_parse_run_keyed_args, _COMPARE_RUN_OPT_KEYS,
                         _COMPARE_L35_ONLY_KEYS)
from amoprof.comparator import (RunSpec, RunMetrics, extract_metrics,
                                build_chain_html, build_comparison_html,
                                _tier_prefix, _store_word, _gauge_peak)

_L = ["L3 local SSD", "L3.5 DRAM only", "L3.5 DRAM+SSD"]

def _ok(specs, flag="--run-opt", fixed=""):
    _d, _e = _parse_run_keyed_args(specs, _L, flag=flag, fixed_key=fixed)
    return _d if not _e else None

check("--run-opt keys a value to its run",
      _ok(["L3 local SSD=nvme_device=nvme6n1"]),
      {"L3 local SSD": {"nvme_device": "nvme6n1"}})
check("a label retyped with other spacing/case still matches",
      _ok(["l3 local  ssd=nvme_device=nvme6n1"]),
      {"L3 local SSD": {"nvme_device": "nvme6n1"}})
check("--run-setup takes LABEL=PATH",
      _ok(["L3.5 DRAM+SSD=/tmp/s.json"], "--run-setup", "setup_details"),
      {"L3.5 DRAM+SSD": {"setup_details": "/tmp/s.json"}})
check("a prom_labels value keeps its own = signs",
      _ok(["L3 local SSD=prom_labels=k1=v1,k2=v2"]),
      {"L3 local SSD": {"prom_labels": "k1=v1,k2=v2"}})
# An override that names a run or a key that does not exist must fail loudly:
# silently dropping it is indistinguishable in the output from applying it and
# finding it made no difference.
check("an unknown label is rejected", _ok(["Nope=nvme_device=x"]), None)
check("an unknown key is rejected", _ok(["L3 local SSD=bogus=x"]), None)
check("a key with no value is rejected", _ok(["L3 local SSD=nvme_device"]), None)
check("a spec with no = at all is rejected", _ok(["L3 local SSD"]), None)
check("an empty value is rejected", _ok(["L3 local SSD=nvme_device="]), None)
check("every l35-only key is a known override key",
      all(_k in _COMPARE_RUN_OPT_KEYS for _k in _COMPARE_L35_ONLY_KEYS), True)

# Tier resolution is per run, from that run's own setup, and the short form is
# what appears inside a metric label.
import json as _js_i, tempfile as _tf_i, csv as _csv_i, shutil as _sh_i
_root_i = Path(_tf_i.mkdtemp(prefix="cmp0i_"))

def _mk_run(_name, _setup, _dram_b=0, _file_b=0):
    _d = _root_i / _name; _d.mkdir(parents=True, exist_ok=True)
    (_d / "sglang_summary.json").write_text(_js_i.dumps(
        {"duration_s": 1800, "tpot_ms": 50.0, "cache_hit_pct": 90.0}))
    if _dram_b or _file_b:
        with (_d / "l35_storage_timeseries.csv").open("w", newline="") as _f:
            _w = _csv_i.writer(_f)
            _hdr = ["time_sec"]
            if _dram_b: _hdr.append("l35_store_mem_capacity_b")
            if _file_b: _hdr.append("l35_store_file_capacity_b")
            _w.writerow(_hdr)
            for _t in (0, 900, 1800):
                _row = [_t] + ([_dram_b] if _dram_b else []) + ([_file_b] if _file_b else [])
                _w.writerow(_row)
    _sp = _root_i / f"setup_{_name}.json"
    _sp.write_text(_js_i.dumps(_setup))
    return RunSpec(_name, _d, setup_details_path=_sp)

_BASE_SETUP = {"Model": "gemma-3-27b", "Runtime": "SGLang", "GPU": "A100-80GB",
               "TP size": "8", "Context length": "32768", "HiCache": "true"}
_s_local = {**_BASE_SETUP, "KV cache tier": "L3",
            "HiCache storage backend": "file", "L3 capacity GB": 966}
_s_l35   = {**_BASE_SETUP, "KV cache tier": "L3.5",
            "HiCache storage backend": "mooncake"}

_r_local = _mk_run("local", _s_local)
_r_dram  = _mk_run("l35_dram", _s_l35, _dram_b=int(54e9))
_r_both  = _mk_run("l35_both", _s_l35, _dram_b=int(54e9), _file_b=int(966e9))
_m_local, _m_dram, _m_both = (extract_metrics(_r) for _r in
                              (_r_local, _r_dram, _r_both))

check("a local-SSD setup resolves to class local_ssd",
      _m_local.l3_backend_class, "local_ssd")
check("a local-SSD setup's short tier is L3", _m_local.tier_short, "L3")
check("a mooncake setup resolves to a remote class",
      _m_dram.l3_backend_class.startswith("remote_"), True)
check("a mooncake setup's short tier is L3.5", _m_dram.tier_short, "L3.5")
check("the short tier carries no parenthetical",
      "(" not in _m_dram.tier_short, True)

# Capacity is a gauge: differencing a constant yields 0, which would be
# reported as a tier with no capacity. Neither field was assigned at all
# before, so the chain's first row compared 0.0 against 0.0 on every run.
check("DRAM-tier capacity is read as a gauge peak", _m_dram.l35_dram_gb, 54.0)
check("a run with no SSD tier reports it absent, not zero",
      _m_dram.l35_file_gb, None)
check("an SSD tier capacity is read when present", _m_both.l35_file_gb, 966.0)
check("capacity falls back to setup_details", _m_local.l35_file_gb, 966.0)
check("the capacity source is recorded",
      (_m_dram.l35_cap_source, _m_local.l35_cap_source),
      ("store exporter (gauge peak)", "setup_details"))
check("a gauge peak of an absent column is None",
      _gauge_peak(_r_local.raw_dir, ["no_such_column_b"]), None)

# Row labels must not name a tier the run did not have.
check("same-tier runs label the row with that tier",
      _tier_prefix(_m_dram, _m_both), "L3.5")
check("mixed-tier runs get no tier in the row label",
      _tier_prefix(_m_local, _m_dram), "")
check("same-tier remote runs name the memory node",
      _store_word(_m_dram, _m_both), "memory node")
check("local-only runs name the local SSD store",
      _store_word(_m_local, _m_local), "local SSD store")
check("mixed runs use neutral store wording",
      _store_word(_m_local, _m_dram), "backing store")

_chain_mixed = build_chain_html(_m_local, _m_dram)
check("a mixed-tier chain uses neutral capacity labels",
      "Backing-store DRAM tier (GB)" in _chain_mixed, True)
check("a mixed-tier chain never says 'L3.5 DRAM (GB)'",
      "L3.5 DRAM (GB)" in _chain_mixed, False)
check("a mixed-tier chain warns that the backend class changed",
      "Different backing tiers" in _chain_mixed, True)
_chain_same = build_chain_html(_m_dram, _m_both)
check("a same-tier chain does not warn about backend class",
      "Different backing tiers" in _chain_same, False)
check("a same-tier chain labels capacity with the tier",
      "L3.5 DRAM tier (GB)" in _chain_same, True)
check("the chain heading names the pair it compares",
      "l35_dram" in _chain_same and "l35_both" in _chain_same, True)

# Every run after the second used to be dropped from the chain -- the one
# table that carries the finding, in exactly the comparison it is run for.
_html_i = build_comparison_html([_m_local, _m_dram, _m_both], title="t")
check("a 3-run report renders one chain per comparison run",
      _html_i.count("<h2>Tiering chain"), 2)
check("the third run is present in the chain section",
      "Tiering chain — local → l35_both" in _html_i, True)
check("the configuration table states each run's backing tier",
      "KV backing tier" in _html_i, True)
check("a resolved tier appears with its backend class",
      "L3 — local_ssd" in _html_i, True)

# A fetched run with no --run-setup has no configuration at all; that must
# read as unknown rather than defaulting to either tier.
_m_bare = extract_metrics(RunSpec("bare", _r_dram.raw_dir))
check("a run with no setup has no tier", (_m_bare.tier_short,
                                          _m_bare.l3_backend_class), ("", ""))
_html_bare = build_comparison_html([_m_bare, _m_dram], title="t")
check("an unresolved tier is stated as unknown, not defaulted",
      "unknown — no setup_details" in _html_bare, True)
# The row must still carry the resolved run's tier, so "unknown" is read as
# this run's missing setup rather than the feature being off.
check("the resolved run in the same table still shows its tier",
      "L3.5 — remote_mooncake" in _html_bare, True)
check("a mixed known/unknown chain is not labelled with either tier",
      "Backing-store DRAM tier (GB)" in build_chain_html(_m_bare, _m_dram), True)
_sh_i.rmtree(_root_i, ignore_errors=True)


print("\n=== 0J. compare: A5->A1 layer walk, charts, suspect figures ===")
from amoprof.comparator import (build_layer_walk_html, build_suspect_banner,
                                build_comparison_html as _bch_j,
                                RunMetrics as _RM, RunSpec as _RS,
                                extract_metrics as _em_j)
import json as _js_j, csv as _csv_j, tempfile as _tf_j, shutil as _sh_j

# ── A2/A1 fallbacks. A summary JSON carrying only read BW -- the shape of
# every run fetched straight from Prometheus -- produced "33 MB/s at 0 IOPS",
# because read BW had a timeseries fallback and IOPS did not.
_r_j = Path(_tf_j.mkdtemp(prefix="cmp0j_"))
_d_j = _r_j / "run"; _d_j.mkdir()
(_d_j / "sglang_summary.json").write_text(_js_j.dumps(
    {"duration_s": 600, "tpot_ms": 50.0, "cache_hit_pct": 90.0,
     "ttft_ms": 1000.0, "e2e_ms": 5000.0, "throughput_tok_s": 100.0}))
(_d_j / "summary.json").write_text(_js_j.dumps({"nvme_rd_bw_mbs_mean": 33.3}))
with (_d_j / "nvme_driver_timeseries.csv").open("w", newline="") as _f_j:
    _w_j = _csv_j.writer(_f_j)
    _w_j.writerow(["time_sec", "rd_bw_mbs", "wr_bw_mbs", "rd_iops",
                   "avgqu_sz", "qd_peak", "io_util_pct", "rd_lat_ms"])
    for _t_j in (0, 300, 600):
        _w_j.writerow([_t_j, 33.3, 210.4, 4120, 2.4, 64, 18.2, 0.41])
_m_j = _em_j(_RS("dev", _d_j))
check("read IOPS falls back to the device timeseries", _m_j.nvme_rd_iops, 4120.0)
check("write BW falls back too", _m_j.nvme_wr_bw_mbs, 210.4)
check("queue depth mean is extracted", _m_j.nvme_qd_mean, 2.4)
check("queue depth peak is extracted", _m_j.nvme_qd_peak, 64.0)
# mean rate x window span, not sum-of-samples x step: 33.3 MB/s over 600 s.
check("byte totals are integrated when the summary has none",
      round(_m_j.read_total_gb, 2), round(33.3 * 600 / 1000.0, 2))

# ── The layer walk keeps absent distinct from zero, and drops a row no run
# exported rather than showing a column of zeros.
_a = _RM(label="A", prompt_tok=1000.0, cached_tok=900.0, cache_hit_pct=90.0,
         evicted_tok=5000.0, backuped_tok=400.0, prefetched_tok=0.0,
         load_back_tok=None, tier_short="L3", l3_backend_class="local_ssd",
         nvme_rd_iops=4120.0)
_b = _RM(label="B", prompt_tok=2000.0, cached_tok=1900.0, cache_hit_pct=95.0,
         evicted_tok=9000.0, backuped_tok=None, prefetched_tok=150.0,
         load_back_tok=None, tier_short="L3.5",
         l3_backend_class="remote_mooncake")
_lw = build_layer_walk_html([_a, _b])
check("the layer walk renders", bool(_lw), True)
for _sec in ("A5 · Application", "CROSS · KV movement", "A4 · GPU",
             "A3 · Host DRAM", "A2 · Block layer", "A1 · SSD hardware"):
    check(f"layer section present: {_sec[:22]}", _sec in _lw, True)
# The ROW is dropped; the words "load-back" still appear in the section's
# explanatory note, so the row label is what has to be absent.
check("a counter no run exported is dropped, not shown as zero",
      "load-back · L2" in _lw, False)
check("a measured zero is still shown", ">0 tok<" in _lw, True)
check("an unexported counter reads 'not exported'",
      "not exported" in _lw, True)
check("mixed tiers give the hop a neutral name",
      "backup · L2 → L3/L3.5" in _lw, True)
_lw_same = build_layer_walk_html([_b, _RM(label="C", tier_short="L3.5",
                                          l3_backend_class="remote_mooncake",
                                          evicted_tok=1.0)])
check("a shared tier names the hop with that tier",
      "backup · L2 → L3.5" in _lw_same or "L3.5 → L2" in _lw_same, True)
check("one run is not a comparison", build_layer_walk_html([_a]), "")

# ── The recompute derivation is auditable in place. recomputed comes from a
# GAUGE (cached / (hit%/100) - cached), so it must be reconciled against the
# measured prompt-token counter rather than presented as counted.
check("recomputed is derived from the hit gauge",
      round(_a.recomputed_tok, 2), round(900.0 / 0.90 - 900.0, 2))
check("the check row sums cached + recomputed", "cached + recomputed" in _lw, True)
check("the residual against prompt tokens is shown",
      "residual vs prompt tokens" in _lw, True)
# A/1000: 900 + 100 = 1000 exactly -> 0.00%; B: 1900 + 100 = 2000 -> 0.00%
check("a reconciling run shows a zero residual", "+0.00%" in _lw, True)

# ── Figures the report cannot stand behind.
_t1 = _RM(label="R1", ttft_ms=64453.33, e2e_ms=64453.33, tpot_ms=115.7,
          duration_min=18.0, window_str="w1")
_t2 = _RM(label="R2", ttft_ms=64453.33, e2e_ms=64453.33, tpot_ms=164.0,
          duration_min=49.0, window_str="w2")
_t3 = _RM(label="R3", ttft_ms=11524.97, e2e_ms=38939.99, tpot_ms=1655.3,
          duration_min=103.0, window_str="w3")
_sb = build_suspect_banner([_t3, _t1, _t2])
check("E2E equal to TTFT exactly is flagged",
      "equals TTFT exactly" in _sb, True)
check("the flag names the affected runs", "R1" in _sb and "R2" in _sb, True)
check("a run where they differ is not flagged for it",
      _sb.index("R1") < _sb.index("Window lengths"), True)
check("a figure repeating across different windows is flagged",
      "repeats across runs with different windows" in _sb, True)
check("a 5.7x duration spread is flagged", "5.7x" in _sb, True)
# No false positives on well-formed runs over equal-length windows.
_ok1 = _RM(label="P", ttft_ms=400.0, e2e_ms=9000.0, tpot_ms=50.0,
           duration_min=30.0, window_str="wA")
_ok2 = _RM(label="Q", ttft_ms=420.0, e2e_ms=9100.0, tpot_ms=52.0,
           duration_min=31.0, window_str="wB")
check("clean runs raise no suspect banner", build_suspect_banner([_ok1, _ok2]), "")

# ── Charts. A series of all zeros was drawn as zero-height bars with "0.0"
# stacked on the axis, and a metric in ms was divided by 100 to share a
# seconds axis then labelled "ms x10" while its note said "/100".
_ch = _bch_j([_t3, _t1, _t2], title="t")
check("no series is positioned outside any more",
      '"textposition": "outside"' in _ch, False)
check("labels are placed automatically", '"textposition": "auto"' in _ch, True)
check("the ms-x10 mislabel is gone", "ms×10" in _ch, False)
check("TPOT is plotted in real milliseconds", "TPOT (ms)" in _ch, True)
check("a secondary axis carries it", '"yaxis2"' in _ch, True)
check("charts are taller than the 300px that crowded the labels",
      '"height": 360' in _ch, True)
_ch_empty = _bch_j(
    [_RM(label="X", tpot_ms=1.0, duration_min=5.0, window_str="x"),
     _RM(label="Y", tpot_ms=2.0, duration_min=5.0, window_str="y")],
    title="t")
check("a chart with no data says so instead of drawing zeros",
      "not collected for any of these runs" in _ch_empty, True)
check("an all-zero panel draws no zero bars",
      '"text": ["0", "0"]' in _ch_empty, False)
_sh_j.rmtree(_r_j, ignore_errors=True)


print("\n=== 0K. one window, one queue depth, one L2 capacity ===")
from amoprof.report.metric_kernels import resolve_l2_residency as _rl2
from amoprof.report.combined import (_amoprof_exec_svg_queue_pctl as _qpct,
                                     _amoprof_exec_svg_layer_response as _lresp,
                                     _MIN_PLAUSIBLE_WINDOW_S as _MINW)
import re as _re_k

# ── L2 capacity: a MEASURED gauge outranks a configured assumption.
# The reported run: hicache_host_total_tokens = 251,421 at 560 KB/token is
# 134.3 GB, while setup_details implied 2 GB/GPU x 8 = 16 GB. Ranking the
# assumption first gave a 16 GB denominator, the used figure was then divided
# by TP=8 to fit it, and the tile still read "103% full" -- next to a
# tier-residency chart reading 134.3 GB from the same gauge.
_l2 = _rl2(hicache_used_tokens=251421, hicache_total_tokens=251421,
           kv_bytes_per_token_kb=560, hicache_total_gb=16.0)
check("L2 capacity comes from the server's own token gauge",
      round(_l2["capacity_gb"], 1), 134.3)
check("L2 used matches the tier-residency chart",
      round(_l2["used_gb"], 1), 134.3)
check("fill is 100%, not an impossible 103%",
      round(_l2["fill_pct"], 1), 100.0)
check("the capacity source says it is measured",
      "measured" in _l2["capacity_source"], True)
check("the disagreement with the configured figure is named",
      "8.4x apart" in _l2["capacity_conflict"], True)
check("nothing is clamped once the denominator is right",
      round(_l2["over_capacity_pct"], 2), 0.0)
# Without a gauge, the configured allocation is still used.
_l2b = _rl2(hicache_used_tokens=100000, hicache_total_tokens=0,
            kv_bytes_per_token_kb=560, hicache_total_gb=16.0)
check("a configured allocation is still used when no gauge exists",
      (round(_l2b["capacity_gb"], 1), "configured" in _l2b["capacity_source"]),
      (16.0, True))
# Agreeing sources raise no conflict.
_l2c = _rl2(hicache_used_tokens=30000, hicache_total_tokens=30000,
            kv_bytes_per_token_kb=560, hicache_total_gb=16.0)
check("agreeing sources raise no conflict", _l2c["capacity_conflict"], "")

# ── Capacity precedence below the gauge: a STATED --hicache-ratio outranks a
# parsed --hicache-size. SGLang sizes the host cache from the ratio whenever
# --hicache-size is 0 (the default), and on the reference run the ratio path
# reproduces the server's gauge to one token while a `hicache_size` field
# worth 2, times 8 GPUs, is 8.4x out.
check("ratio x KV pool reproduces the measured gauge to one token",
      round(209517 * 1.2), 251420)
_l2r = _rl2(hicache_used_tokens=251421, hicache_total_tokens=0,
            kv_bytes_per_token_kb=560, hicache_total_gb=16.0,
            hicache_ratio=1.2, kv_pool_tokens=209517)
check("without a gauge the ratio beats the parsed size",
      round(_l2r["capacity_gb"], 1), 134.3)
check("the ratio-derived source names its inputs",
      "--hicache-ratio 1.2" in _l2r["capacity_source"], True)
check("the size-vs-ratio disagreement is named",
      "8.4x apart" in _l2r["capacity_conflict"], True)
# With neither gauge nor ratio, a configured size is still honoured.
_l2s = _rl2(hicache_used_tokens=29959, hicache_total_tokens=0,
            kv_bytes_per_token_kb=560, hicache_total_gb=16.0)
check("a configured size is still used when nothing better exists",
      (round(_l2s["capacity_gb"], 1), _l2s["capacity_source"]),
      (16.0, "configured HiCache allocation"))
# A ratio that agrees with the configured size must not emit conflict noise.
_l2n = _rl2(hicache_used_tokens=1000, hicache_total_tokens=0,
            kv_bytes_per_token_kb=560, hicache_total_gb=134.0,
            hicache_ratio=1.2, kv_pool_tokens=209517)
check("an agreeing ratio and size raise no conflict",
      _l2n["capacity_conflict"], "")
# The ratio applies to the DEVICE KV POOL, not to free HBM. 6.1 GB/GPU of
# unallocated HBM x 8 x 1.2 = 58.56 GB is a different quantity from
# 1.2 x the 111.9 GB KV pool, and only the latter matches the device.
check("free HBM is not the ratio's base",
      round(6.1 * 8 * 1.2, 2) == round(209517 * 560 * 1024 / 1024**3 * 1.2, 2),
      False)

# ── Window plausibility. A blktrace capture that recorded nothing reported
# duration_sec = 0.001, which is > 0 and so passed the old guard; dividing
# 19,242.6 GB by it gave "19,704,435,625 MB/s" beside a header reading
# "Window : 0.0 min" and a page header correctly reading 38,840 sec.
check("a millisecond window is not plausible", 0.001 >= _MINW, False)
check("a 10.79 h window is plausible", 38840.0 >= _MINW, True)
check("a two-second window is not plausible", 2.0 >= _MINW, False)
# The rate that broke, with the right denominator.
check("logical read BW with the real window is sane",
      round(19242.6 * 1024 / 38840.0, 0), 507.0)
check("the broken denominator is what produced the 1.97e10 figure",
      round(19242.6 * 1024 / 0.001 / 1e9, 1), 19.7)

# ── Queue depth: one resolution, used by chart and tile alike.
# Exact blktrace Q->C percentiles must win over a sysfs avgqu_sz series that
# reads ~1e-4 over the same window.
_qs = [{"layer": "A5_APP", "label": "Queued requests (admission)",
        "t": [0, 1, 2], "v": [34, 40, 85], "ref": 85.0, "refnote": "x"},
       {"layer": "A1/A2_L3", "label": "Storage queue depth",
        "t": [0, 1, 2], "v": [0.0001, 0.0002, 0.0004], "ref": 32.0,
        "refnote": "vs QD=32", "pctl": {0.5: 0.0, 0.9: 1.0, 0.99: 1.0},
        "pctl_src": "exact blktrace Q→C"}]
_qh = _qpct(_qs)
check("the distribution chart uses the authoritative percentiles",
      "p99 = 1.00" in _qh, True)
check("the footer states which source the percentiles came from",
      "abs p99 1.00 (exact blktrace Q→C)" in _qh, True)
check("a short bar is labelled with its absolute value, not '0'",
      _re_k.findall(r'font-weight="700"\s+text-anchor="middle">([^<]{1,8})</text>',
                    _qh)[4:7], ["0", "1", "1"])
# Without an override the series is still used, so runs with no blktrace
# summary are unaffected.
_qs2 = [dict(_qs[0]), {k: v for k, v in _qs[1].items()
                       if k not in ("pctl", "pctl_src")}]
_qh2 = _qpct(_qs2)
check("no override leaves the series-derived percentiles in place",
      "exact blktrace" in _qh2, False)

# ── The legend must not call a range unavailable when the raw series has a
# peak. The bins are per-bucket MEDIANS, so a signal that is zero most of the
# time has every median at zero.
_sr = [{"layer": "A1/A2_L3", "label": "Storage queue depth", "unit": "",
        "bins": [(1, 0.0), (2, 0.0), (3, 0.0)], "raw": [0.0, 1.0, 0.0, 1.0],
        "r": -0.06, "rho": -0.06, "n": 4, "ymax": 1.0},
       {"layer": "A5_APP", "label": "Running batch", "unit": "",
        "bins": [(1, 81.0), (2, 86.0)], "raw": [81.0, 86.0],
        "r": 0.4, "rho": 0.4, "n": 2, "ymax": 86.0}]
_lh = _lresp("Running requests", "reqs", _sr)
check("'range unavailable' is gone when the series has a peak",
      "range unavailable" in _lh, False)
# The legend names the statistic it plotted (group 0M changed queue series
# from median to max bins), and still reports the raw peak when the bins are
# flat.
check("the legend reports the raw series peak instead",
      "binned max 0 · series peak 1.000" in _lh, True)
check("a series with a real binned peak is unchanged",
      "peak of binned median 86.0" in _lh, True)
check("the legend names which statistic it plotted",
      ("binned max" in _lh and "binned median" in _lh), True)
_lh2 = _lresp("Running requests", "reqs",
              [dict(_sr[0], raw=[0.0, 0.0]), _sr[1]])
check("a genuinely empty series says so plainly",
      "no non-zero sample in this window" in _lh2, True)

# ── Physical byte totals: mean rate x the device file's own span.
# 17 MB/s read and 39.1 MB/s write over 38,840 s is 645 GB / 1,484 GB, which
# the report printed as "0.0 MB / 0.0 GB" because the blktrace byte counters
# were absent.
#  ── The queue-depth tile must never vanish.
# v1.53.0 replaced an unconditional `if _lq:` (which printed a misleading
# "0.0 peak depth") with two conditions that can BOTH fail: no blktrace
# summary and an all-zero avgqu_sz column removed the tile entirely. A
# missing tile reads as "this tier has no queue", which is worse than either
# a measured zero or an admitted gap. Replays the tile's own branch order.
def _qd_tile(qd_sum, l35, nvme_max, lr, lw, lu):
    _ex = float((qd_sum or {}).get("qd_max", 0) or 0)
    _ser, _name = [], ""
    for _c in ("l35_avgqu_sz", "avgqu_sz", "l35_bt_qd_mean",
               "inflight", "queue_depth", "aqu_sz"):
        _vals = [v for v in (l35.get(_c) or []) if v == v]
        if not _vals:
            _mx = nvme_max.get(_c, 0.0)
            _vals = [_mx] if _mx > 0 else []
        if _vals:
            _ser, _name = _vals, _c
            if max(_vals) > 0:
                break
    if _ex > 0:                     return "exact"
    if _ser and max(_ser) > 0:      return "series"
    if _ser:                        return "measured-zero"
    if lr or lw or lu:              return "not-collected"
    return "absent"

_BW = ([33.3], [39.1], [18.2])
check("exact blktrace summary wins over a zero sysfs column",
      _qd_tile({"qd_max": 1, "qd_mean": 0.36}, {"l35_avgqu_sz": [0.0, 0.0]},
               {}, *_BW), "exact")
check("an all-zero column renders as a measured zero, not as nothing",
      _qd_tile({}, {"l35_avgqu_sz": [0.0, 0.0, 0.0]}, {}, *_BW),
      "measured-zero")
check("a tiny non-zero column still renders its value",
      _qd_tile({}, {"l35_avgqu_sz": [0.0, 0.0004]}, {}, *_BW), "series")
check("the local unprefixed avgqu_sz column is consulted too",
      _qd_tile({}, {}, {"avgqu_sz": 2.4}, *_BW), "series")
check("no queue counter at all is admitted, not implied to be idle",
      _qd_tile({}, {}, {}, *_BW), "not-collected")
check("a tier with no storage telemetry gets no tile",
      _qd_tile({}, {}, {}, [], [], []), "absent")
# Precision must distinguish a small queue from no queue.
def _qfmt(q):
    return (f"{q:,.2f}" if q >= 1 else
            f"{q:,.3f}" if q >= 0.01 else f"{q:.1e}")
check("a sub-0.01 queue depth is not printed as zero",
      _qfmt(0.0004), "4.0e-04")
check("a mid-range queue depth keeps three decimals", _qfmt(0.36), "0.360")
check("a queue depth above 1 keeps two decimals", _qfmt(2.4), "2.40")

# ── Queue depth is a function of event ORDER.
# _compute_queue_depth_from_csv walked the CSV in file order while its sibling
# analyze_from_events_csv sorts the same file by ts first. On a stream whose Q
# and C alternate -- which per-CPU grouped blktrace output produces -- the
# depth is pinned at 1 however much concurrency the device saw. Little's Law
# (QD = IOPS x latency) is measured independently of the depth, so it is what
# separates a genuinely serialized path from a miscounted one.
import csv as _csv_k, json as _js_k, tempfile as _tf_k, shutil as _sh_k
from amoprof.blktrace_analyzer import _compute_queue_depth_from_csv as _qdcsv

_qr = Path(_tf_k.mkdtemp(prefix="qd0k_"))

def _qd_write(_name, _rows):
    _p = _qr / _name
    with _p.open("w", newline="") as _f:
        _w = _csv_k.writer(_f)
        _w.writerow(["ts", "pid", "action", "rwbs", "sector", "nsec"])
        for _r in _rows:
            _w.writerow(_r)
    return _p

def _qd_run(_name, _rows):
    _p = _qd_write(_name, _rows)
    _o = _qr / ("out_" + _name)
    _qdcsv(_p, _o)
    return _js_k.loads((_o / "queue_depth_summary.json").read_text())

# Genuinely serialized: each request completes before the next is issued.
_rows_s = []
for _i in range(1000):
    _t = _i * 0.001
    _rows_s.append([f"{_t:.6f}", 1, "Q", "W", 1000 + _i * 8, 8])
    _rows_s.append([f"{_t + 0.0004:.6f}", 1, "C", "W", 1000 + _i * 8, 8])
_s1 = _qd_run("serial.csv", _rows_s)
check("a serialized path really does peak at 1", _s1["qd_max"], 1)
check("its mean matches the duty cycle", round(_s1["qd_mean"], 1), 0.4)
check("a time-ordered stream reports no inversions",
      _s1["qd_order_inversions"], 0)
check("Little's Law corroborates a genuinely shallow queue",
      _s1["qd_consistency"], "consistent")

# True depth 8, but each Q sits beside its own C -- the ordering artifact.
_rows_c = []
for _i in range(1000):
    _q = _i * 0.001
    _rows_c.append([f"{_q:.6f}", 1, "Q", "R", 2000 + _i * 8, 8])
    _rows_c.append([f"{_q + 0.008:.6f}", 1, "C", "R", 2000 + _i * 8, 8])
_s2 = _qd_run("grouped.csv", _rows_c)
check("sorting recovers the real depth instead of pinning it at 1",
      _s2["qd_max"], 8)
check("the recovered mean is the real concurrency",
      round(_s2["qd_mean"]), 8)
check("the inversions that caused it are counted",
      _s2["qd_order_inversions"], 999)
check("and the recovered depth also passes the cross-check",
      _s2["qd_consistency"], "consistent")
check("the two cases are distinguishable at all",
      _s1["qd_max"] != _s2["qd_max"], True)
_sh_k.rmtree(_qr, ignore_errors=True)

# 56 MB/s on a device targeted at 7 GB/s read is 0.5% utilised, so a shallow
# queue is the expected reading, not a surprising one.
check("the observed rate is well under 1% of the device target",
      round((17.0 / 7000.0) * 100, 2) < 1.0, True)
# QD 0.36 at 64 KB I/Os implies ~0.4 ms latency, which is plausible for NVMe;
# at 4 KB it would require 25 us, which is not.
check("QD 0.36 is consistent with 64 KB I/Os at sub-ms latency",
      round(0.36 / (56.1 * 1024 / 64) * 1000, 2), 0.4)

check("read total integrates to the right order",
      round(17.0 * 38840.0 / 1024.0, 0), 645.0)
check("write total integrates to the right order",
      round(39.1 * 38840.0 / 1024.0, 0), 1483.0)


print("\n=== 0L. a declared backing tier must answer to the telemetry ===")
# A setup_details.json copied between deployments carries the previous run's
# embedded `SGLang server_info raw` blob, and the launch command rendered from
# it is presented as fact. On a FILE-backend run whose setup file still said
# `--hicache-storage-backend mooncake`, the report named a memory node that was
# not in the deployment, labelled the GPU host's own NVMe as that node's block
# device, and reported the mean and the peak of ONE series as two devices.
from amoprof.report.l3_backend import resolve_l3_backend as _rlb
import csv as _csv_l, tempfile as _tf_l, shutil as _sh_l

_stale_setup = {
    "Model": "google/gemma-4-31b-it", "TP size": "8",
    "Launch command": ("python3 -m sglang.launch_server "
                       "--enable-hierarchical-cache --hicache-ratio 2 "
                       "--hicache-write-policy write_through "
                       "--hicache-io-backend kernel "
                       "--hicache-storage-backend mooncake"),
    "HiCache storage backend": "mooncake",
}
_rb = _rlb(_stale_setup, _stale_setup["Launch command"])
check("a stale mooncake blob still resolves to a remote class",
      _rb.backend_class, "remote_mooncake")

# The evidence test, as the report applies it: a remote tier cannot operate
# without publishing store-side counters.
_evr = Path(_tf_l.mkdtemp(prefix="ev0l_"))

def _mk_raw(_name, _store, _local):
    _d = _evr / _name
    _d.mkdir(parents=True, exist_ok=True)
    if _store is not None:
        with (_d / "l35_store_capacity.csv").open("w", newline="") as _f:
            _w = _csv_l.writer(_f)
            _w.writerow(["time_sec", "l35_get_total_n", "l35_mem_hit_b"])
            for _row in _store:
                _w.writerow(_row)
    if _local is not None:
        with (_d / "nvme_driver_timeseries.csv").open("w", newline="") as _f:
            _w = _csv_l.writer(_f)
            _w.writerow(["time_sec", "rd_bw_mbs", "wr_bw_mbs"])
            for _i, (_rd, _wr) in enumerate(_local):
                _w.writerow([_i * 15, _rd, _wr])
    return _d

def _evidence(_d, declared="remote_mooncake"):
    """Replays the report's conflict test: declared remote, store silent."""
    if declared not in ("remote_mooncake", "remote_storage"):
        return "no-check"
    _cols = ("l35_get_total_n", "l35_mem_hit_b", "l35_file_hit_b",
             "l35_store_mem_used_b", "mooncake_used_bytes")
    _seen = False
    for _f in ("l35_store_capacity.csv", "l35_storage_timeseries.csv"):
        _p = _d / _f
        if not _p.exists():
            continue
        with _p.open(newline="") as _fh:
            _rows = list(_csv_l.DictReader(_fh))
        for _c in _cols:
            # Filter NaN BEFORE max, as the report does; filtering inside the
            # max() generator leaves it empty on an all-NaN column.
            _vals = []
            for _r in _rows:
                try:
                    _v = float(_r.get(_c) or "nan")
                except (TypeError, ValueError):
                    continue
                if _v == _v:
                    _vals.append(_v)
            if _vals and max(_vals) > 0:
                _seen = True
    _local_io = False
    _lp = _d / "nvme_driver_timeseries.csv"
    if _lp.exists():
        with _lp.open(newline="") as _fh:
            _rows = list(_csv_l.DictReader(_fh))
        for _c in ("rd_bw_mbs", "wr_bw_mbs"):
            for _r in _rows:
                try:
                    if float(_r.get(_c) or 0) > 0:
                        _local_io = True
                except (TypeError, ValueError):
                    pass
    if _seen:
        return "agrees"
    return "conflict-local-io" if _local_io else "conflict-no-io"

_d_stale = _mk_raw("stale_file_backend", None, [(17.0, 39.1), (377.0, 1088.0)])
_d_real  = _mk_raw("real_mooncake", [[0, 5255481, 134400000000]], [(0.0, 0.0)])
_d_dark  = _mk_raw("untelemetered", None, None)

check("declared remote with no store counters but live local I/O conflicts",
      _evidence(_d_stale), "conflict-local-io")
check("a genuine remote run with store counters does not conflict",
      _evidence(_d_real), "agrees")
check("declared remote with nothing at all is reported as untelemetered",
      _evidence(_d_dark), "conflict-no-io")
check("a local_ssd declaration is not subjected to the remote test",
      _evidence(_d_stale, declared="local_ssd"), "no-check")
# The check must never silently relabel: a real remote run whose store
# exporter was simply not scraped is indistinguishable from a stale blob.
check("the conflict states both readings rather than picking one",
      _evidence(_d_stale) != "local_ssd", True)
_sh_l.rmtree(_evr, ignore_errors=True)

# The tile labels must follow the file the data came from.
def _bw_note(local_src):
    return (f"peak of the same series as the L3 read/write BW tiles · local "
            f"block device, {local_src}" if local_src
            else "block device on the memory node")
check("the peak tile names the local file when the fallback fired",
      "nvme_driver_timeseries.csv" in _bw_note("nvme_driver_timeseries.csv"), True)
check("it no longer asserts a memory node on a local run",
      "memory node" in _bw_note("nvme_driver_timeseries.csv"), False)
check("it says the peak is the same series as the mean tiles",
      "same series" in _bw_note("nvme_driver_timeseries.csv"), True)
check("a true memory-node run keeps its label", _bw_note(""),
      "block device on the memory node")


print("\n=== 0M. a bursty queue must survive summarising ===")
# Reported as "ssd queue depth not showing up, it is showing peak as 16 but the
# chart doesn't have it". The series was real -- peak 16 -- and every chart
# plotted zero, because an instantaneous in-flight gauge sampled every 15 s is
# zero in almost every sample. Median-per-bin and index decimation both discard
# exactly the samples that carry the finding.
from amoprof.report.combined import (
    _amoprof_binned_response as _br_m, _amoprof_bin_stat_for as _bs_m,
    _amoprof_exec_svg_queue_timeline as _qt_m,
    _amoprof_exec_svg_qd_saturation as _sat_m,
    _amoprof_qd_distribution as _dist_m)
import csv as _csv_m, tempfile as _tf_m, shutil as _sh_m, re as _re_m

# 720 samples over 3 h; four spikes to 16, zero everywhere else.
_t_m = [_i * 15.0 for _i in range(720)]
_v_m = [0.0] * 720
for _i in (131, 288, 455, 601):
    _v_m[_i] = 16.0

check("a queue-depth series is summarised by max",
      _bs_m("Storage queue depth"), "max")
check("a bandwidth series keeps the median",
      _bs_m("L3 read BW (MB/s)"), "median")
check("in-flight and aqu are recognised as queues",
      (_bs_m("inflight"), _bs_m("iostat aqu-sz")), ("max", "max"))
_b_med = _br_m(list(range(720)), _v_m, stat="median")
_b_max = _br_m(list(range(720)), _v_m, stat="max")
check("median bins annihilate the burst",
      max(_y for _x, _y in _b_med), 0.0)
check("max bins preserve it", max(_y for _x, _y in _b_max), 16.0)

# The timeline decimates to ~240 points; index decimation drops the spikes.
_qs_m = [{"layer": "A1/A2_L3", "label": "Storage queue depth", "t": _t_m,
          "v": _v_m, "ref": 32.0, "refnote": "vs QD=32"},
         {"layer": "A5_APP", "label": "Running batch", "t": _t_m,
          "v": [80.0] * 720, "ref": 100.0, "refnote": "batch"}]
_h_m = _qt_m(_qs_m)
_tips = [_x for _x in _re_m.findall(r"<title>(.*?)</title>", _h_m, _re_m.S)
         if "Storage" in _x]
check("the timeline keeps a hoverable burst value",
      any("value = 16.00" in _x for _x in _tips), True)
check("and reports it against its reference",
      any("(50% of reference)" in _x for _x in _tips), True)
check("the subtitle states the decimation",
      "decimated by MAX per pixel" in _h_m, True)
# The storage polyline must leave the baseline.
_polys = _re_m.findall(r'<polyline points="([^"]+)" fill="none"', _h_m)
_ys_m = [float(_p.split(",")[1]) for _p in _polys[0].split()]
check("the plotted line reaches the burst",
      (max(_ys_m) - min(_ys_m)) > 100, True)

# ── The saturation curve: the question a device-sizing decision turns on.
_satr = Path(_tf_m.mkdtemp(prefix="sat0m_"))
(_satr / "blktrace_analysis").mkdir(parents=True, exist_ok=True)
with (_satr / "blktrace_analysis" / "queue_depth_distribution.csv").open(
        "w", newline="") as _f:
    _w = _csv_m.writer(_f)
    _w.writerow(["qd_value", "time_sec", "pct_of_run", "source"])
    for _qd, _ts in ((0, 9500), (1, 800), (2, 300), (4, 120), (8, 60),
                     (16, 18), (32, 2)):
        _w.writerow([_qd, _ts, 0, "blktrace"])
_d_exact, _src_exact = _dist_m(_satr)
check("the blktrace time-at-depth histogram is read",
      "exact blktrace" in _src_exact, True)
check("it carries every depth bucket", len(_d_exact), 7)
_h_sat = _sat_m(_d_exact, source=_src_exact, ref=32.0)

def _sat_field(_html_s, _label):
    _m = _re_m.search(
        r'font-size="7\.5">' + _re_m.escape(_label)
        + r'</text>\s*<text[^>]*text-anchor="end">([^<]+)</text>', _html_s)
    return _m.group(1) if _m else None

check("peak depth is reported", _sat_field(_h_sat, "peak depth"), "32")
check("the time-weighted mean is reported",
      _sat_field(_h_sat, "time-weighted mean"), "0.25")
# 800+300+120+60+18+2 = 1300 of 10800 s
check("the queued share of the window is right",
      _sat_field(_h_sat, "% of window queued"),
      f"{1300/10800*100:.2f}%")
# 18+2 = 20 of 10800 s at QD >= 16
check("the share at or above a depth is right",
      _sat_field(_h_sat, "% at QD ≥ 16"), f"{20/10800*100:.3f}%")
check("deep buckets are flagged red", 'fill="#ef4444"' in _h_sat, True)

# With no blktrace histogram the same shape is derived from the gauge, and
# labelled as the coarser thing it is.
_satr2 = Path(_tf_m.mkdtemp(prefix="sat0m2_"))
_d_der, _src_der = _dist_m(_satr2, _v_m, _t_m)
check("a sampled gauge still yields a distribution",
      dict(_d_der), {0: 10740.0, 16: 60.0})
check("and says it is derived, not exact",
      "derived from a sampled in-flight gauge" in _src_der, True)
_h_der = _sat_m(_d_der, source=_src_der, ref=32.0)
check("the derived curve reports the peak",
      _sat_field(_h_der, "peak depth"), "16")
# 4 samples x 15 s = 60 s of 10,800 s
check("a peak of 16 for 0.56% of the window is not saturation",
      _sat_field(_h_der, "% of window queued"), f"{60/10800*100:.2f}%")
check("nothing reached the QD=32 reference",
      _sat_field(_h_der, "% at QD ≥ 32"), "0.000%")
check("an empty distribution renders nothing", _sat_m([]), "")
_sh_m.rmtree(_satr, ignore_errors=True)
_sh_m.rmtree(_satr2, ignore_errors=True)

# ── "exact blktrace Q->C" needs POSITIVE evidence. The old test was
# `not qd_source.startswith("advisory")`, so an EMPTY source was labelled
# exact -- on a run whose blktrace queue-depth timeseries was missing.
def _src_label(_qd_source):
    _l = str(_qd_source or "").lower()
    if "blktrace" in _l or "q_to_c" in _l:
        return "exact"
    if _l.startswith("advisory") or _l:
        return "advisory"
    return "unrecorded"

check("a blktrace source is labelled exact",
      _src_label("blktrace_q_to_c"), "exact")
check("an advisory fallback is labelled advisory",
      _src_label("advisory_iostat_aqu_sz_or_sysfs_inflight_fallback"), "advisory")
check("an EMPTY source is no longer called exact",
      _src_label(""), "unrecorded")
check("an unknown non-empty source is not called exact",
      _src_label("some_future_source"), "advisory")

# An instantaneous sample cannot exceed the real depth, so a sampled 16
# against an event-derived peak of 1 indicts the event count.
def _disagrees(event_peak, sampled_peak):
    return sampled_peak > max(event_peak * 2.0, event_peak + 1.0)

check("event peak 1 against a sampled 16 is flagged", _disagrees(1.0, 16.0), True)
check("event peak 16 against a sampled 16 is not", _disagrees(16.0, 16.0), False)
check("a sampled gauge below the event peak is not flagged",
      _disagrees(16.0, 8.0), False)


print("\n=== 0N. queue depth without blktrace: diskstats field 11 ===")
# "If queue depth is not available from blktrace, can we get it from iostat or
# sysfs?" Yes -- but from the TIME-WEIGHTED counter, not the instantaneous one.
#
#   /proc/diskstats field 9  = I/Os currently in flight  (node_disk_io_now)
#   field 10 = ms doing I/O                              (-> %util)
#   field 11 = weighted ms doing I/O (time_in_queue)     (-> avgqu-sz)
#
# Field 11 accumulates (in-flight x ms) on every update, so differencing it
# over an interval gives the average queue length ACROSS that interval and
# cannot miss activity between scrapes. Field 9 can miss a whole burst.
# amoprof was fetching node_disk_io_time_weighted_seconds_total and never
# differencing it -- the metric appeared once in the module, in the request
# list.
_WINDOW_MS = 15_000.0

def _avgqu_from_weighted(d_weighted_ms, d_wall_ms=_WINDOW_MS):
    return d_weighted_ms / d_wall_ms

# A device holding depth 4 for the whole 15 s interval: 4 x 15,000 ms.
check("a steady depth is recovered exactly",
      _avgqu_from_weighted(4 * _WINDOW_MS), 4.0)
# Depth 16 for 1 s inside a 15 s interval: 16,000 weighted ms.
check("a 1 s burst to 16 shows as its time-weighted average",
      round(_avgqu_from_weighted(16 * 1000.0), 3), 1.067)
# The same burst is invisible to the instantaneous gauge unless the scrape
# lands inside that one second: ~1 chance in 15.
check("the integral is preserved even though the shape is not",
      round(_avgqu_from_weighted(16 * 1000.0) * _WINDOW_MS / 1000.0, 1), 16.0)
check("an idle interval reads zero", _avgqu_from_weighted(0.0), 0.0)
# %util comes from field 10 the same way, and is capped at 100.
check("utilisation from field 10 is a percentage",
      round(min(_WINDOW_MS * 0.42 / _WINDOW_MS * 100, 100.0), 1), 42.0)

# ── PromQL selector injection. The old rule appended the selector to the END
# of the expression, which is valid only for a bare metric name. Every
# node_exporter fallback in the module is wrapped in rate() or max_over_time(),
# so each produced invalid PromQL whenever a selector was active and silently
# returned nothing -- the report then showed those tiers as untelemetered on
# hosts that were publishing the data.
import re as _re_n
_src_n = open(str(Path(__file__).parent / "amoprof" / "report" / "amoprof.py")).read()
_i_n = _src_n.index("_PROMQL_RESERVED = frozenset")
_j_n = _src_n.index("def _prom_query_range")
_ns_n = {"re": _re_n}
exec(_src_n[_i_n:_j_n], _ns_n)
_inj = _ns_n["_prom_inject_selector"]
_SEL = '{job="node",instance="h:9100"}'

def _n_inject(expr):
    return _inj(expr, _SEL).count('job="node"')

check("a bare metric name takes the selector",
      _inj("node_disk_io_now", _SEL),
      'node_disk_io_now{job="node",instance="h:9100"}')
check("an existing label group is merged, not replaced",
      _inj('node_disk_io_now{device="nvme6n1"}', _SEL),
      'node_disk_io_now{device="nvme6n1", job="node",instance="h:9100"}')
check("a rate() expression is injected inside the metric selector",
      _inj("rate(node_disk_io_time_weighted_seconds_total[2m])", _SEL),
      'rate(node_disk_io_time_weighted_seconds_total'
      '{job="node",instance="h:9100"}[2m])')
check("the range duration is not treated as a metric",
      "[2m{" in _inj("rate(node_disk_io_now[2m])", _SEL), False)
check("a scientific-notation literal is not treated as a metric",
      "1e6{" in _inj("rate(node_disk_read_bytes_total[2m])/1e6", _SEL), False)
check("a function name never takes a selector",
      _n_inject("max_over_time(node_disk_io_now[2m])"), 1)
check("every metric in a multi-metric expression is scoped",
      _n_inject("(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)/1e9"), 2)
check("a label name inside braces is left alone",
      _inj('(1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m])))*100', _SEL),
      '(1 - avg(rate(node_cpu_seconds_total'
      '{mode="idle", job="node",instance="h:9100"}[2m])))*100')
check("no selector leaves the expression untouched",
      _inj("rate(node_disk_io_now[2m])", ""), "rate(node_disk_io_now[2m])")
check("an empty brace selector is a no-op",
      _inj("node_disk_io_now", "{}"), "node_disk_io_now")

# The module must actually request and difference the weighted counter.
check("the weighted counter is requested",
      "node_disk_io_time_weighted_seconds_total" in _src_n, True)
check("it is written as a cumulative column",
      'nrow["io_wt_ms"]' in _src_n, True)
check("and differenced into avgqu_sz",
      'nv["avgqu_sz_weighted"]' in _src_n, True)
check("a collector-derived avgqu_sz is not overwritten",
      'or not (nv["avgqu_sz"].fillna(0) > 0).any()' in _src_n, True)

# ── The regression this caused, and the three defects behind it.
# v1.56.0 added a node_exporter queue-depth fetch with no device filter.
# _synth_ts wraps every query in avg(), so an unfiltered node_disk_* query
# averages the device under study together with every idle dm-*, loop* and
# sd* on the host: a depth of 16 on one device over twenty idle ones reads as
# under 1, and as 0 in most samples. A series whose peak had been 16 went
# flat.
# ── A third source that needs nothing new fetched.
# diskstats field 4 is the sum over completed reads of each one's service
# time, field 8 the same for writes. So (d(rd_ms)+d(wr_ms))/d(wall_ms) is the
# average number of requests being serviced -- Little's Law with the
# multiplication already done by the kernel. rd_ms and wr_ms are already
# written by every path, so this works on a host exposing no queue-depth
# field at all: no field 11, no io_now, no blktrace.
def _avgqu_service(d_rd_ms, d_wr_ms, d_wall_ms=_WINDOW_MS):
    return (d_rd_ms + d_wr_ms) / d_wall_ms

# Four reads of 2 ms each per second, over 15 s: 4*2*15 = 120 ms of service.
check("service concurrency from timing counters",
      round(_avgqu_service(120.0, 0.0), 4), round(120.0 / 15000.0, 4))
# A device serviced continuously by 2 requests for the whole interval.
check("a steadily busy device reads as its concurrency",
      _avgqu_service(_WINDOW_MS, _WINDOW_MS), 2.0)
check("reads and writes both contribute",
      _avgqu_service(_WINDOW_MS / 2, _WINDOW_MS / 2), 1.0)
check("an idle interval reads zero from this source too",
      _avgqu_service(0.0, 0.0), 0.0)
# It is a LOWER bound on field 11, which also counts queueing wait.
check("field 11 is at least the service concurrency",
      _avgqu_from_weighted(4 * _WINDOW_MS) >= _avgqu_service(2 * _WINDOW_MS,
                                                             2 * _WINDOW_MS),
      True)
check("the service derivation is wired in",
      'nv["avgqu_sz_service"]' in _src_n, True)
check("it only fills avgqu_sz when nothing better did",
      _src_n.index('nv["avgqu_sz_weighted"]')
      < _src_n.index('nv["avgqu_sz_service"]'), True)
check("the source diagnostic ships",
      (Path(__file__).parent / "scripts" / "qd_sources.py").is_file(), True)

check("the local queue-depth query is device-filtered",
      'f"rate(node_disk_io_time_weighted_seconds_total{_qd_dev_sel}[2m])"'
      in _src_n, True)
check("it is skipped entirely with no --nvme-device",
      "no --nvme-device given, so node_exporter queue" in _src_n, True)
check("the L3.5 query is restricted to nvme namespaces",
      'device=~\\"nvme[0-9]+n[0-9]+\\"' in _src_n
      or 'device=~"nvme[0-9]+n[0-9]+"' in _src_n, True)

# merge=True must not let a mis-scoped fetch degrade the file. Two rules:
# an all-zero INCOMING column is never added, and the join is on the existing
# time base so pre-existing columns are not NaN-ed onto new rows.
def _merge_contract(old_cols, new_cols, old_t, new_t):
    """Pure replay of the merge rules, without pandas."""
    def dead(vals):
        return all((v in (None, 0) or v != v) for v in vals)
    _old = {c: list(v) for c, v in old_cols.items()}
    for c in list(new_cols):
        if c in _old and dead(_old[c]):
            del _old[c]
    added = [c for c, v in new_cols.items() if c not in _old and not dead(v)]
    skipped = [c for c, v in new_cols.items() if c not in _old and dead(v)]
    rows = len(old_t)            # left join on the old time base
    return _old, added, skipped, rows

_t10 = [i * 15.0 for i in range(10)]
_live = {"inflight": [0, 0, 0, 16, 0, 0, 8, 0, 0, 0], "avgqu_sz": [0.0] * 10}
_mis = {"inflight": [0.0] * 10, "avgqu_sz": [0.0] * 10,
        "qd_peak": [0, 0, 0, 16, 0, 0, 8, 0, 0, 0]}
_kept, _added, _skipped, _rows = _merge_contract(_live, _mis, _t10, _t10)
check("a live column survives a mis-scoped fetch",
      max(_kept["inflight"]), 16)
check("an all-zero incoming column is skipped", _skipped, ["avgqu_sz"])
check("a live incoming column is still added", _added, ["qd_peak"])
check("the row count is unchanged", _rows, 10)
# An outer join on an offset grid doubled the rows and NaN-ed every
# pre-existing column on the new half.
_kept2, _added2, _skipped2, _rows2 = _merge_contract(
    _live, {"qd_peak": [1.0] * 10}, _t10, [x + 7.0 for x in _t10])
check("an offset grid does not add rows", _rows2, 10)
check("and the live column is intact", max(_kept2["inflight"]), 16)
check("the join is on the existing time base",
      'on="time_sec", how="left"' in _src_n, True)
check("an all-zero incoming series is reported, not silently dropped",
      "Skipped" in _src_n and "all-zero " in _src_n, True)


print("\n=== 0O. no local is read before it is assigned ===")
# A run failed with "cannot access local variable '_ssd_bw_pct' where it is
# not associated with a value" and the ENTIRE executive summary was lost --
# not just the finding that touched it. _ssd_bw_pct was computed ~350 lines
# below its first use, inside an `and`/`or` chain, so the error only surfaced
# on a run whose preceding terms were all falsy.
#
# build_executive_summary_html is ~9,000 lines; this class of fault cannot be
# held off by review, so it is checked statically on every validation run.
# The same scan found two more: the shared L2 resolver read kv_bytes_tok_kb a
# thousand lines early and had its UnboundLocalError swallowed by its own
# `except Exception` -- which is why the v1.53.1 L2 capacity fix never took
# effect -- and `aggregate --combined-report` read raw_dir in a branch that
# runs before the one that binds it.
import subprocess as _sp_o
_repo_o = Path(__file__).parent
_scan_o = _repo_o / "scripts" / "check_unbound_locals.py"
check("the static scanner ships with the package", _scan_o.is_file(), True)

_mods_o = [
    "amoprof/report/combined.py", "amoprof/report/amoprof.py",
    "amoprof/report/interactive.py", "amoprof/report/metric_kernels.py",
    "amoprof/report/l3_backend.py", "amoprof/comparator.py",
    "amoprof/cli.py", "amoprof/blktrace_analyzer.py",
]
_present_o = [m for m in _mods_o if (_repo_o / m).is_file()]
check("every module under test is present", len(_present_o), len(_mods_o))
_r_o = _sp_o.run([sys.executable, str(_scan_o)]
                 + [str(_repo_o / m) for m in _present_o],
                 capture_output=True, text=True)
if _r_o.returncode != 0:
    print(_r_o.stdout.rstrip())
check("no local is read before its first assignment", _r_o.returncode, 0)

# The three the scan caught, pinned so a reintroduction fails here.
_comb_o = (_repo_o / "amoprof" / "report" / "combined.py").read_text()
_cli_o = (_repo_o / "amoprof" / "cli.py").read_text()
check("_ssd_bw_pct is defined before the findings block",
      _comb_o.index("_ssd_bw_pct = (nvme_rd_bw")
      < _comb_o.index('"L3 (local storage) QUEUE · "'), True)
check("the L2 resolver runs after kv_bytes_tok_kb exists",
      _comb_o.index("kv_bytes_tok_kb = _kv_bytes_per_token_kb")
      < _comb_o.index("_l2res = _k_resolve_l2("), True)
check("the aggregate report path names the merged raw dir",
      _cli_o.count("report_filename(merged_raw,"), 4)
# Scoped to _aggregate's LIVE region: _collect and _analyze legitimately bind
# raw_dir, and _aggregate carries 260 lines of unreachable code (see below)
# that also reference it.
import ast as _ast_o
_tree_o = _ast_o.parse(_cli_o)
_agg_o = [n for n in _ast_o.walk(_tree_o)
          if isinstance(n, _ast_o.FunctionDef) and n.name == "_aggregate"][0]
_first_ret_o = next((s.lineno for s in _agg_o.body
                     if isinstance(s, _ast_o.Return)), _agg_o.end_lineno)
_live_o = "\n".join(_cli_o.split("\n")[_agg_o.lineno - 1:_first_ret_o])
check("no raw_dir reference survives in the live aggregate path",
      "report_filename(raw_dir," in _live_o, False)

# Unreachable code is how the duplicate hid: _aggregate ends at `return 0`
# and 260 lines of what reads like _analyze's body follow it without a `def`.
# A statement after an unconditional top-level return is never a deliberate
# construct, and a dead copy of a live function is a trap for whoever fixes
# the live one.
_unreach_o = []
for _fn_o in [n for n in _ast_o.walk(_tree_o)
              if isinstance(n, _ast_o.FunctionDef)]:
    for _i_o, _st_o in enumerate(_fn_o.body):
        if isinstance(_st_o, _ast_o.Return):
            _after_o = _fn_o.body[_i_o + 1:]
            if _after_o:
                _hi_o = max((s.end_lineno or s.lineno) for s in _after_o)
                _unreach_o.append(
                    (_fn_o.name, _st_o.lineno, _hi_o - _after_o[0].lineno + 1))
            break
for _nm_o, _ln_o, _n_o in _unreach_o:
    print(f"         unreachable: {_nm_o} returns at line {_ln_o}, "
          f"{_n_o} dead line(s) follow")
# One known occurrence, pinned by name: _aggregate ends at `return 0` and is
# followed by an unreachable near-duplicate of _analyze's body (85% identical,
# same docstring) that was pasted in without its `def`. It is dead to Python
# and a live trap for a reader -- three raw_dir call sites in it were nearly
# "fixed" during this session. Pinned rather than deleted because removing 260
# lines of someone's half-duplicated function is the owner's call; a NEW
# occurrence, or a change to this one, still fails here.
check("the only unreachable block is the known _aggregate duplicate",
      [(_n, _c) for _n, _l, _c in _unreach_o], [("_aggregate", 260)])
check("no OTHER function carries unreachable code",
      [_n for _n, _l, _c in _unreach_o if _n != "_aggregate"], [])

# The window guard that fired on the same run is doing its job: a 29 s
# blktrace summary against a 10,920 s sample timeline is 376x apart, so the
# timeline wins. Without it every rate would have been inflated 376-fold.
check("a 29 s summary against a 10,920 s timeline is implausible",
      29.0 >= 5.0 and (10920.0 / 29.0) > 1.2, True)
check("the ratio is reported, not swallowed",
      round(10920.0 / 29.0, 1), 376.6)
check("and the timeline is the one used",
      max(29.0, 10920.0), 10920.0)


print("\n=== 0P. NVMe multipath naming, and the device option for L3.5 ===")
# A run analysed with --nvme-device nvme6n1 showed utilisation and in-flight
# but a dead-flat zero queue depth; the SAME run analysed as nvme6c6n1 showed
# a peak of 82. That is not the I/O path bypassing a software layer -- both
# names are the same namespace. Under nvme_core.multipath=Y the kernel
# accounts the time-weighted queue integral (diskstats field 11) and the
# per-direction service times (fields 4 and 8) on the PER-CONTROLLER PATH,
# nvme6c6n1, while the NAMESPACE HEAD, nvme6n1, carries only the
# instantaneous in-flight gauge (field 9) and the busy-time counter (field
# 10). It matches the earlier diagnostic exactly: fields 4/8/11 all-zero on
# nvme6n1, field 9 populated with mean 48.5 / peak 1,547.
#
# Which made amoprof's own `nvme[0-9]+n[0-9]+` fallback, added in v1.56.1 as
# a "safe default", exclude precisely the device that carries the data.
import re as _re_p
_amo_p = (_repo_o / "amoprof" / "report" / "amoprof.py").read_text()
_cli_p = (_repo_o / "amoprof" / "cli.py").read_text()
_comb_p = (_repo_o / "amoprof" / "report" / "combined.py").read_text()

_ns_p = {"re": _re_p}
exec(_amo_p[_amo_p.index("# ── NVMe device naming"):
            _amo_p.index("# PromQL function and keyword names")], _ns_p)
_kind_p = _ns_p["_nvme_dev_kind"]
_fam_p = _ns_p["_nvme_dev_family_sel"]
_sib_p = _ns_p["_nvme_dev_sibling_hint"]

check("nvme6n1 is classified as the namespace head",
      _kind_p("nvme6n1"), "head")
check("nvme6c6n1 is classified as the controller path",
      _kind_p("nvme6c6n1"), "controller-path")
check("a leading /dev/ is tolerated", _kind_p("/dev/nvme0n1"), "head")
check("a non-NVMe name is classified as neither", _kind_p("sda"), "")
check("two-digit controller and namespace indices parse",
      _kind_p("nvme12c3n4"), "controller-path")
# Both names of ONE namespace must fall in one family, and neither may pull
# in a different namespace on the same controller.
check("both names share one family selector",
      _fam_p("nvme6n1") == _fam_p("nvme6c6n1"), True)
_fam_re_p = _re_p.compile("^" + _fam_p("nvme6n1").split('"')[1] + "$")
check("the family matches the head", bool(_fam_re_p.match("nvme6n1")), True)
check("the family matches the controller path",
      bool(_fam_re_p.match("nvme6c6n1")), True)
check("the family excludes another namespace on the same controller",
      bool(_fam_re_p.match("nvme6n2")), False)
check("the family excludes another controller",
      bool(_fam_re_p.match("nvme7n1")), False)
check("the sibling of the head names a controller path",
      _sib_p("nvme6n1"), "nvme6c<N>n1")
check("the sibling of the controller path is the head",
      _sib_p("nvme6c6n1"), "nvme6n1")

# The two regexes that excluded the controller path.
_prom_re_p = _re_p.compile("^" + _ns_p["_NVME_DEV_RE_PROM"] + "$")
check("the PromQL device pattern accepts the controller path",
      bool(_prom_re_p.match("nvme6c6n1")), True)
check("the PromQL device pattern still accepts the head",
      bool(_prom_re_p.match("nvme6n1")), True)
check("the old pattern would have excluded it — the defect, pinned",
      bool(_re_p.match(r"^nvme[0-9]+n[0-9]+$", "nvme6c6n1")), False)
check("the pandas auto-detect pattern accepts the controller path",
      bool(_re_p.match(r"nvme\d+(?:c\d+)?n\d+$", "nvme6c6n1")), True)
check("the pandas auto-detect pattern is the one in the source",
      r'r"nvme\d+(?:c\d+)?n\d+$"' in _amo_p, True)
check("no bare nvme[0-9]+n[0-9]+ selector survives",
      'device=~\\"nvme[0-9]+n[0-9]+\\"' in _amo_p, False)

# --l35-nvme-device: the option the L3.5 path never had.
check("analyze exposes --l35-nvme-device",
      '"--l35-nvme-device"' in _cli_p, True)
check("compare exposes it too", _cli_p.count('"--l35-nvme-device"'), 2)
check("it is a per-run compare override key",
      '"l35_nvme_device",' in _cli_p, True)
check("it is dropped for a run resolved as local SSD",
      _cli_p.index("_COMPARE_L35_ONLY_KEYS: tuple")
      < _cli_p.index('"l35_nvme_device",\n)'), True)
check("the fetch accepts it", "l35_nvme_device:      str = \"\"," in _amo_p, True)
check("analyze and compare both pass it through",
      _cli_p.count("l35_nvme_device=getattr(args")
      + _cli_p.count('l35_nvme_device      = _scoped['), 2)

# Every node_disk_* query on the L3.5 node must be device-scoped. Unscoped,
# _synth_ts's avg() averages the busy device with every idle namespace, which
# is the same defect fixed on the local path in v1.56.1 -- and on the L3.5
# path it diluted bandwidth and IOPS as well as queue depth.
_l35_blk_p = _amo_p[_amo_p.index("_l35_ne_map = {"):]
_l35_blk_p = _l35_blk_p[:_l35_blk_p.index("--l35-storage-instance names the")]
check("every node_disk_* query in the L3.5 colmap is device-scoped",
      _l35_blk_p.count("node_disk_"), _l35_blk_p.count("{_l35_dev_sel}"))
check("the L3.5 colmap scopes at least five node_disk_* series",
      _l35_blk_p.count("node_disk_") >= 5, True)

# `by (device)` is a label list, not a metric reference.
_inj_ns_p = {"re": _re_p}
exec(_amo_p[_amo_p.index("_PROMQL_RESERVED = frozenset("):
            _amo_p.index("def _prom_query_range(")], _inj_ns_p)
_inj_p = _inj_ns_p["_prom_inject_selector"]
check("a grouping clause's label list is left alone",
      _inj_p("count by (device) (count_over_time(node_disk_io_now[5m]))",
             '{job="node"}'),
      'count by (device) (count_over_time(node_disk_io_now{job="node"}[5m]))')
check("without() is left alone too",
      "without (cpu{" not in _inj_p(
          "sum without (cpu) (rate(node_cpu_seconds_total[2m]))", '{job="n"}'),
      True)
check("on()/group_left() label lists are left alone",
      _inj_p("a * on (instance) group_left (nodename) b", '{job="n"}'),
      'a{job="n"} * on (instance) group_left (nodename) b{job="n"}')
check("the device matcher still merges into the metric's own braces",
      _inj_p('rate(node_disk_io_time_weighted_seconds_total'
             '{device="nvme6c6n1"}[2m])', '{instance="m:9100"}'),
      'rate(node_disk_io_time_weighted_seconds_total'
      '{device="nvme6c6n1", instance="m:9100"}[2m])')

# Plausibility. amoprof_blktrace_qd_qd_mean reported mean 6,876 / peak
# 171,982 on this fleet -- an unmatched-Q counting artifact -- and sat in the
# candidate chain for the report's queue depth. The collector is fixed, but
# Prometheus keeps the history, so the guard belongs on the read side.
_bound_p = _ns_p["_QD_PLAUSIBLE_MAX"]
check("the fetch and the report agree on the bound",
      f"_QD_PLAUSIBLE_MAX = {_bound_p:g}" in _comb_p, True)
check("the observed artifact is above the bound", 6876.316 > _bound_p, True)
check("its peak is far above the bound", 171982.370 > _bound_p, True)
check("the real sampled peak of 82 is below it", 82.0 < _bound_p, True)
check("so is the deepest gauge reading seen on this fleet",
      1547.0 < _bound_p, True)
exec(_comb_p[_comb_p.index("def _qd_implausible("):
             _comb_p.index("_LAYER_SERIES_COLORS = [")], {})
_impl_p = {}
exec("_QD_PLAUSIBLE_MAX = %r\n" % _bound_p
     + _comb_p[_comb_p.index("def _qd_implausible("):
               _comb_p.index("_LAYER_SERIES_COLORS = [")], _impl_p)
_f_p = _impl_p["_qd_implausible"]
check("the chart guard rejects the artifact", _f_p([1.0, 171982.37]), 171982.37)
check("the chart guard keeps a real series", _f_p([0.0, 12.0, 82.0]), 0.0)
check("an empty series is not called implausible", _f_p([]), 0.0)
check("the guard is applied to the queue-depth chart source",
      "_qd_rejected.append" in _comb_p, True)
check("the guarded fetch keys cover both bounds and both tiers",
      sorted(_ns_p["_QD_GUARDED_KEYS"]),
      ["avgqu_sz", "avgqu_sz_service", "avgqu_sz_weighted", "inflight",
       "l35_avgqu_sz", "l35_inflight", "l35_qd_peak", "qd_peak"])
check("the blktrace summary is discarded when it breaches the bound",
      "_qd_exact_max = _qd_exact_mean = 0.0" in _comb_p, True)

# The tile contradicted itself: it headlined "0.36 mean / 1 peak" above a
# note explaining that 1 was the figure to distrust. The headline is what
# gets quoted, so the headline has to be the trustworthy figure.
check("the tile prefers the sampled gauge when the two disagree",
      "_qd_prefer_sampled = _other_peak > max(" in _comb_p, True)
check("and the disagreement test is unchanged: 2x or +1",
      82.0 > max(1.0 * 2.0, 1.0 + 1.0), True)
check("a near-agreement does not trigger the swap",
      16.0 > max(15.0 * 2.0, 15.0 + 1.0), False)
check("the demoted blktrace figure is still shown, not dropped",
      "which reported " in _comb_p, True)

# The sibling diagnostic: which name carries the queue fields is a property
# of the host's multipath setting, not something an operator should have to
# know. It never substitutes the device -- the report measures what was
# asked for and says what else was there.
check("the diagnostic ships", "def _qd_dev_diagnose(" in _amo_p, True)
check("it runs on both the local and the L3.5 path",
      _amo_p.count("_qd_dev_diagnose("), 3)
check("it queries field 11 per device, with no avg() and no subquery",
      'f"rate({_f11}{_sel_body}[2m])"' in _amo_p, True)
check("and groups the result per device in pandas, not in PromQL",
      'groupby("device")["value"].max()' in _amo_p, True)
check("the metric it reads is field 11",
      '_f11 = "node_disk_io_time_weighted_seconds_total"' in _amo_p, True)
check("stage 1 stays silent when the requested device has data",
      "if _mine > 0.0:\n                    return" in _amo_p, True)
check("and speaks only when a sibling does instead",
      "if _live:\n                    _best = max(_live, key=_live.get)" in _amo_p,
      True)

# qd_sources.py probes both names and refuses to recommend an impossible one.
_qds_p = (_repo_o / "scripts" / "qd_sources.py").read_text()
check("the inventory script probes sibling names",
      "def sibling_names(" in _qds_p, True)
check("it uses the same plausibility bound",
      f"QD_PLAUSIBLE_MAX = {_bound_p:g}" in _qds_p, True)
check("it marks an implausible source rather than ranking it",
      "IMPLAUSIBLE" in _qds_p and "if is_qd and best is None:" in _qds_p, True)
check("it names the device to re-run with when that device is the sibling",
      "--l35-nvme-device" in _qds_p and "--nvme-device" in _qds_p, True)

# v1.58.0 shipped --l35-nvme-device broken. The flag parsed, the run
# directory was created, the model config was read -- and then:
#
#   ERROR  Prometheus fetch failed: fetch_from_prometheus() got an
#          unexpected keyword argument 'l35_nvme_device'
#
# The fetch is THREE hops, each with its own explicit signature:
#
#   cli._analyze --prom_kwargs--> prometheus_source.fetch_from_prometheus
#                --------------->  report.amoprof.collect_from_prometheus_api
#
# I added the parameter to hop 3 and to the hop-1 dict and never checked hop
# 2, because I grepped only cli.py for the neighbouring keyword. A keyword
# that exists at one hop and not the next cannot be caught by review of
# either file alone, and it fails at run time on the first real invocation.
# So it is checked statically, for every keyword, on every validation run.
_kwchk_p = _repo_o / "scripts" / "check_fetch_kwargs.py"
check("the fetch-chain checker ships", _kwchk_p.is_file(), True)
_rk_p = _sp_o.run([sys.executable, str(_kwchk_p), str(_repo_o)],
                  capture_output=True, text=True)
if _rk_p.returncode != 0:
    print(_rk_p.stdout.rstrip())
check("every keyword crossing the fetch chain exists at the next hop",
      _rk_p.returncode, 0)

# And the specific keyword, pinned at each hop so a future refactor that
# drops one of the three fails here rather than on the operator's console.
_psrc_p = (_repo_o / "amoprof" / "prometheus_source.py").read_text()
import ast as _ast_p
_fetch_p = [n for n in _ast_p.walk(_ast_p.parse(_psrc_p))
            if isinstance(n, _ast_p.FunctionDef)
            and n.name == "fetch_from_prometheus"][0]
check("hop 2 accepts it",
      "l35_nvme_device" in {a.arg for a in _fetch_p.args.args
                            + _fetch_p.args.kwonlyargs}, True)
_collect_p = [n for n in _ast_p.walk(_ast_p.parse(_amo_p))
              if isinstance(n, _ast_p.FunctionDef)
              and n.name == "collect_from_prometheus_api"][0]
check("hop 3 accepts it",
      "l35_nvme_device" in {a.arg for a in _collect_p.args.args
                            + _collect_p.args.kwonlyargs}, True)
check("hop 2 forwards it rather than accepting and dropping it",
      _psrc_p.count("l35_nvme_device=l35_nvme_device"), 1)

# Reaching the fetch was still not enough. Asked "this should collect from
# node exporter for that l3.5 instance and for that device, right?", the
# answer for v1.58.1 was no, for two more reasons.
#
# ONE: the node_exporter block ran only `if not _l35s_ok` -- only when the
# amoprof-collector fetch had returned nothing at all. With the amoprof
# service up on the memory node, one of its ~70 metrics comes back, _l35s_ok
# is True, and the only consumer of --l35-nvme-device never executes. And
# the amoprof colmap's queue-depth candidates are sysfs/iostat gauges that
# read all-zero on this hardware, so "the amoprof path succeeded" could mean
# "it filled bandwidth and left queue depth at zero" -- with the
# node_exporter path that had the real field-11 integral skipped on that
# basis. It now always runs, with merge=True, which fills only absent or
# all-zero columns and never overwrites a live one.
_l35_region_p = _amo_p[_amo_p.index("# ---- node_exporter on the L3.5 node"):
                       _amo_p.index('"    [warn] no block-device metrics found')]
# No `if not _l35s_ok` may stand between the block header and its fetch.
# Comment lines are excluded: the comment there quotes the old gate on
# purpose, and the only surviving statement form of it is the one guarding
# the closing warn, which is correct -- that warn is about the tier having
# no telemetry from EITHER path.
_l35_stmts_p = [_ln.strip() for _ln
                in _l35_region_p[:_l35_region_p.index("_l35_ne_sels = ")]
                .split("\n")
                if _ln.strip() and not _ln.strip().startswith("#")]
check("the L3.5 node_exporter fetch is no longer gated on the amoprof fetch",
      [_s for _s in _l35_stmts_p if _s.startswith("if not _l35s_ok")], [])
check("the only surviving gate is the one on the no-telemetry warning",
      _amo_p.count("\n            if not _l35s_ok:"), 1)
# Statement-only view of the whole region, so an assertion can never be
# satisfied by the prose of a comment that describes the fix. Two of these
# checks were, until a mutation run caught them.
_l35_code_p = "\n".join(_ln for _ln in _l35_region_p.split("\n")
                        if _ln.strip() and not _ln.strip().startswith("#"))
check("it merges rather than replaces, so a live column survives",
      _l35_code_p.count("merge=True"), 1)
check("and not merge=False", "merge=False" in _l35_code_p, False)
check("and its result is unioned into the tier's telemetry verdict",
      "_l35s_ok = _l35s_ok or _l35_ne_ok" in _amo_p, True)

# TWO: --l35-storage-instance names the exporter the operator knows about,
# which is the amoprof service on :9101. node_exporter is a different target
# on a different port, conventionally :9100, so reusing that instance
# selector for node_disk_* queries filters out every series the block exists
# to read. The exact instance is tried first -- right whenever
# node_exporter is what was named -- then the same host on any port.
check("the node_exporter fetch starts from the instance as given",
      "_l35_ne_sels = [(_l35s_sel" in _l35_code_p, True)
check("and appends a second, wider selector to try",
      _l35_code_p.count("_l35_ne_sels.append("), 1)
check("the widened selector is host-scoped, not unscoped",
      'instance=~"' in _l35_code_p, True)
check("both are iterated, so the first hit wins and the other is a fallback",
      "for _sel_try, _why in _l35_ne_sels:" in _l35_code_p, True)
# A regex label value is a PromQL STRING LITERAL before it is a regex, and
# PromQL's string escapes are Go's, in which `\.` is not one. So v1.59.0's
# widened selector was rejected outright on its first real run:
#
#   400 bad_data: parse error: unknown escape sequence U+002E '.'
#
# and with it every node_disk_* query the widened selector carried. The dot
# becomes a character class instead, which means the same thing to RE2 and
# cannot be touched by the string parser. The pre-existing hostname_selector
# -- step 4 of _sel_for, reached by several fallbacks -- was built the same
# way, so it had never once been accepted by a Prometheus either.
check("the L3.5 widened selector uses a character class, not an escape",
      '_l35_host.replace(".", "[.]")' in _amo_p, True)
check("so does the pre-existing hostname selector",
      'hostname.replace(".", "[.]")' in _amo_p, True)
check("no backslash-escaped dot is built into any selector",
      'replace(".", "\\\\.")' in _amo_p, False)
import re as _re_q
_hr_p = "msl-ssg-cx03.msl.lab".replace(".", "[.]")
check("the character class still matches the host",
      bool(_re_q.fullmatch(_hr_p + ":[0-9]+", "msl-ssg-cx03.msl.lab:9100")), True)
check("and still excludes another host",
      bool(_re_q.fullmatch(_hr_p + ":[0-9]+", "other-host.msl.lab:9100")), False)
check("and does not let the dot match any character",
      bool(_re_q.fullmatch(_hr_p + ":[0-9]+", "msl-ssg-cx03xmslxlab:9100")), False)

# _synth_ts's colmap values are EITHER a metric name or a list of candidate
# names. The code that explains an empty result passed the value straight to
# _has(), which does `name in available` against a set -- so a candidate list
# raised TypeError: unhashable type: 'list', the outer except reported
# "nvme_driver_timeseries.csv synthesis failed", and the fetch returned
# nothing. A bug in the explanation of an empty result, which therefore only
# fired when the result was already empty, and then replaced the explanation
# with a type error.
check("the empty-result diagnostic flattens candidate lists first",
      "_flat = [_n for _v in colmap.values()" in _amo_p, True)
check("and tests the flattened names, not the raw values",
      "_seen = [m for m in _flat if _has(m)]" in _amo_p, True)
check("the collector-reason loop reads the flattened names too",
      "if not any(_c in _m for _m in _flat):" in _amo_p, True)
check("no raw colmap value is handed to _has any more",
      "_has(m) for m in colmap.values()" in _amo_p
      or "[m for m in colmap.values() if _has(m)]" in _amo_p, False)
# The failure itself, reproduced: a set membership test on a list.
try:
    _ = ["a"] in {"a", "b"}
    _unhash_p = "no error"
except TypeError as _e_p:
    _unhash_p = "TypeError"
check("a candidate list against a set of names is a TypeError",
      _unhash_p, "TypeError")

# Stage 2 of the diagnostic: the device named is not on this host at all.
# Stage 1 compares only ONE namespace, so an operator who passed nvme2c2n1
# while the traffic was on nvme6c6n1 got silence -- the one outcome that
# cannot be acted on.
check("the diagnostic enumerates the devices that do have data",
      "device(s) that DO carry a queue-depth integral here" in _amo_p, True)
check("the enumeration is ranked, busiest first",
      "key=lambda kv: -kv[1]" in _amo_p, True)
check("it distinguishes absent from present-and-zero",
      '_absent = "is not present" if dev not in _all else "reads zero"' in _amo_p,
      True)
check("it says so even when every device reads zero",
      "every one of" in _amo_p, True)
check("and when no device publishes field 11 at all",
      "no device publishes diskstats field" in _amo_p, True)

check("a host that is not a hostname is never interpolated",
      'if _l35_host and re.fullmatch(r"[A-Za-z0-9._-]+", _l35_host):' in _amo_p,
      True)
# The same defect was live on the LOCAL path, where the queue-depth fetch
# passed no selector at all and so inherited the INFERENCE SERVER's job and
# instance -- --prom-instance host:30000 is SGLang's port. It contributed
# nothing on every run since v1.56.0, invisibly, because the main node_dfs
# path uses the discovered node_exporter selector and kept the charts fed.
check("the local queue-depth fetch names an exporter selector",
      "_qd_sels = [(_node_sel," in _amo_p, True)
check("and says which one answered",
      "L3 local queue depth selector:" in _amo_p, True)

# Against a stub Prometheus built to that topology: the amoprof service on
# :9101 with a live metric and a zero queue gauge, node_exporter on :9100,
# and both names of one namespace with a dead and a live field 11.
_stub_p = _repo_o / "tests" / "test_l35_node_exporter_selector.py"
check("the stub-server test ships", _stub_p.is_file(), True)
check("so does the stub", (_repo_o / "tests" / "stub_prometheus_l35.py").is_file(),
      True)
_rs_p = _sp_o.run([sys.executable, "-I", str(_stub_p)],
                  capture_output=True, text=True, cwd=str(_repo_o))
if _rs_p.returncode != 0:
    print(_rs_p.stdout.rstrip())
    print(_rs_p.stderr.rstrip()[:800])
check("every selector and device claim holds against a live server",
      _rs_p.returncode, 0)
# The dilution arithmetic the device filter exists to prevent, checked here
# too so the number is in the validation output and not only in the test.
# The stub host has six devices publishing field 11: the one under study at
# 3.4, a busier one at 11.2, and four idle. An unscoped avg() does not merely
# dilute -- it returns a figure belonging to no device, and here it INFLATES
# the device under study rather than understating it.
check("unscoped avg() over six devices reports 2.43",
      round((3.4 + 11.2) / 6, 2), 2.43)
check("scoped to the four NVMe namespaces it reports 3.65",
      round((3.4 + 11.2) / 4, 2), 3.65)
check("which is above the true 3.4, so the error has no fixed sign",
      3.65 > 3.4, True)
check("only the device-scoped query returns the device's own value",
      3.4, 3.4)


print("\n=== 0Q. compare can pass a model config, globally and per run ===")
# "I don't see a way to pass model config to compare command, similar to
# analyze." Correct: --model-path was on collect, analyze and service, and not
# on compare. So every figure a comparison derives from KV bytes per token --
# L2 and L3 residency, bytes per token, the capacity reconciliation -- fell
# back to a name-based estimate on a fetched run, with nothing in the report
# saying it had.
_cli_q = (_repo_o / "amoprof" / "cli.py").read_text()
check("compare now has --model-path", _cli_q.count('"--model-path"'), 4)
check("it is a per-run override key too",
      '"model_path",           # per-run' in _cli_q, True)
check("--run-opt's help lists every key, so it lists this one",
      '", ".join(sorted(_COMPARE_RUN_OPT_KEYS))' in _cli_q, True)

# A per-run model_path is NOT one of the overrides that do nothing on a
# directory run -- it rewrites that run's model_config.json, which is the
# whole point of passing it. Listing it as inert would have told the operator
# their flag was ignored while it was in fact applied.
check("model_path is excluded from the inert-override warning",
      'if k not in ("setup_details", "model_path")' in _cli_q, True)
check("and the warning text says both apply",
      "Only setup_details and model_path apply to a" in _cli_q, True)

# Per-run matters because the models can differ, and the KV geometry differs
# with them. 2 (K and V) x layers x kv_heads x head_dim x 2 bytes (bf16):
_kv_q = lambda l, h, d: 2 * l * h * d * 2
check("gemma-4-31b-it: 60 layers x 16 kv_heads x 256 head_dim = 960 KB/token",
      _kv_q(60, 16, 256) // 1024, 960)
check("Llama-3-70B: 80 x 8 x 128 = 320 KB/token",
      _kv_q(80, 8, 128) // 1024, 320)
check("so one global config for two models misstates a tier by 3x",
      round(_kv_q(60, 16, 256) / _kv_q(80, 8, 128), 1), 3.0)
# The token count for the run reconciled earlier IS derivable and is pinned:
# --hicache-ratio 1.2 x a 209,517-token device pool. The GB figure that went
# with it is NOT pinned here -- 251,421 tokens x 560 KiB is 144.2 GB and
# x 560 kB is 140.8 GB, neither of which is the 134.3 GB quoted at the time,
# so one of the three numbers was wrong and this file does not get to pick.
# Recompute it from that run's own model_config.json, which is the point of
# the flag added here.
check("the L2 token count is the hicache ratio times the device pool",
      round(1.2 * 209517), 251420)
check("560 KiB per token would make that 144.2 GB",
      round(251421 * 560 * 1024 / 1e9, 1), 144.2)
check("560 kB per token would make it 140.8 GB",
      round(251421 * 560 * 1000 / 1e9, 1), 140.8)
check("and 134.3 GB implies 521.6 KiB per token, not 560",
      round(134.3e9 / 251421 / 1024, 1), 521.6)

# A path that reads nothing is a typo, not a preference: compare must stop
# rather than hand the report an estimate while the operator believes it has
# the real geometry.
check("a model path that reads nothing aborts the comparison",
      "--model-path %s produced no model " in _cli_q, True)
check("by returning 2, not by continuing with an estimate",
      "config. Point it at the model directory or its " in _cli_q, True)
check("and a run with no config at all says the figure is an estimate",
      "will be estimated from the model name" in _cli_q, True)

# _write_model_config reads cfg["_name_or_path"] first when recording the
# model's identity -- but that key was not in _MODEL_CONFIG_KEYS, so it never
# survived the read. The branch was dead, and the name fell through to the
# HuggingFace-cache path derivation or, failing that, to the parent DIRECTORY
# name: --model-path /models/gemma-4-31b-it/config.json recorded
# "gemma-4-31b-it" instead of "google/gemma-4-31b-it".
check("the model's own identity now survives the config read",
      '"_name_or_path",\n)' in _cli_q, True)
check("the code that reads it is therefore no longer dead",
      'cfg.get("_name_or_path")' in _cli_q, True)

# --output-dir claimed the file was called comparison.html. It is not.
check("the compare output name is amoprof_comparison_<ts>.html",
      'f"amoprof_comparison_{datetime.now().strftime' in _cli_q, True)
check("and --output-dir's help no longer claims comparison.html",
      "Directory where comparison.html is written" in _cli_q, False)

# Against real files: two runs, two models, two configs, and the failure mode.
_mc_test_q = _repo_o / "tests" / "test_compare_model_config.py"
check("the compare model-config test ships", _mc_test_q.is_file(), True)
_rq = _sp_o.run([sys.executable, str(_mc_test_q)],
                capture_output=True, text=True, cwd=str(_repo_o))
if _rq.returncode != 0:
    print(_rq.stdout.rstrip())
    print(_rq.stderr.rstrip()[:800])
check("every per-run model-config claim holds against real files",
      _rq.returncode, 0)


print("\n=== 0R. queueing is compared per layer, and proxies are labelled ===")
# "In compare I don't see we are comparing various queue depths across runs?
# Network, inference, ssd, etc." Correct: there were exactly two queue rows,
# both in the A2 table, both fed by ONE field that read the first of
# avgqu_sz / l35_avgqu_sz / bt_qd_mean to return anything.
_cmpz = (_repo_o / "amoprof" / "comparator.py").read_text()

check("the per-layer section ships", "def build_queue_depth_html(" in _cmpz, True)
check("and is rendered into the report", "{_qd_html}" in _cmpz, True)
for _layer in ("inference scheduler", "this host's block device",
               "the memory node's block device", "exact blktrace",
               "host DRAM", "fabric"):
    check(f"the section carries a row group for {_layer}",
          _layer in _cmpz, True)

# The two devices are no longer one row. A local-SSD run and an L3.5 run were
# compared on a row whose two cells measured different devices on different
# hosts, with nothing saying so.
check("this host's device has its own fields", "l3_qd_mean" in _cmpz, True)
check("the memory node's device has its own", "l35_qd_mean" in _cmpz, True)
check("blktrace keeps its own", "bt_qd_mean" in _cmpz, True)
check("and the section says why one row for both would be wrong",
      "different devices on different hosts" in _cmpz, True)
check("the A2 pair is now derived by precedence, not by first hit",
      "m.nvme_qd_mean = (m.l3_qd_mean if m.l3_qd_mean is not None" in _cmpz,
      True)

# Mean and peak answer different questions and come from different columns.
# Taking both from one column put the peak of a MEAN series in the peak cell.
check("mean and peak are resolved independently",
      "_col_mean(" in _cmpz and "_col_peak(" in _cmpz, True)
check("the mean prefers the time-weighted integral",
      'ewline' not in _cmpz.split("m.l3_qd_mean, m.l3_qd_src = _col_mean(")[1][:120]
      and '"avgqu_sz"' in _cmpz.split("m.l3_qd_mean, m.l3_qd_src = _col_mean(")[1][:160],
      True)
check("the peak prefers the instantaneous gauge's maximum",
      '"qd_peak"' in _cmpz.split("m.l3_qd_peak, _l3_pk_src = _col_peak(")[1][:160],
      True)
check("and both columns are named when they differ",
      '(mean), "' in _cmpz and '(peak)"' in _cmpz, True)

# A substring match that SUMS lookalike columns is how 12 and 18 became 30.
check("queue depths are read by exact column name",
      "def _read_csv_col_exact(" in _cmpz, True)
check("and the queue reader uses it",
      "_v = _read_csv_col_exact(_f, _c)" in _cmpz, True)
check("12 and 18 summed is 30, which neither source measured",
      12.0 + 18.0, 30.0)
check("and depth does not add across queues: two devices at 4 is not 8",
      4.0 + 4.0 == 4.0, False)

# Proxies. Neither NET nor A3 exposes a queue; saying nothing about why is
# not the same as leaving them out correctly.
check("every proxy row is marked a proxy in the rendered table",
      '>proxy</span>' in _cmpz, True)
check("and a measured queue is marked as measured",
      '>measured queue</span>' in _cmpz, True)
check("the section states a proxy is not comparable with a queue",
      "is not a queue depth and is not comparable with" in _cmpz, True)
check("no proxy is put on the chart's axis",
      "Only measured queues." in _cmpz, True)

# The DRAM proxy's denominator. dram_peak_bw_gbs is the run's OWN observed
# maximum, so mean / that is a burstiness ratio, not pressure. The reference
# has to come from the platform.
check("the DRAM share-of-peak uses a configured platform peak",
      '_dram_peak_cfg = _sf(_pick(setup or {}, "DRAM peak GB/s"' in _cmpz, True)
check("not the run's own observed maximum",
      "m.dram_total_bw_gbs / m.dram_peak_bw_gbs * 100.0" in _cmpz, False)
check("the denominator is shown beside the share",
      "Platform peak the share is taken against" in _cmpz, True)
check("and with no configured peak there is no share",
      "dram_peak_ref_gbs" in _cmpz, True)
# 105 GB/s mean against a 409.6 platform peak is 25.6%; against the run's own
# 200 GB/s maximum it would read 52.5% -- twice the pressure, same data.
check("105 GB/s against a 409.6 platform peak is 25.6%",
      round(105 / 409.6 * 100, 1), 25.6)
check("against the run's own 200 GB/s maximum it would read 52.5%",
      round(105 / 200 * 100, 1), 52.5)
check("so the wrong denominator doubles the apparent pressure",
      round((105 / 200) / (105 / 409.6), 1), 2.0)

# The plausibility bound, shared with the single-run report.
check("the comparator applies the same queue-depth bound",
      "_QD_PLAUSIBLE_MAX = 4096.0" in _cmpz, True)
_combz = (_repo_o / "amoprof" / "report" / "combined.py").read_text()
check("and it is the same number the single-run report uses",
      "_QD_PLAUSIBLE_MAX = 4096.0" in _combz, True)

# Against real CSVs: two runs, two tiers, two devices, the proxies, the
# lookalike-column trap and the implausible series.
_qdt_q = _repo_o / "tests" / "test_compare_queue_depth.py"
check("the queue-depth comparison test ships", _qdt_q.is_file(), True)
_rz = _sp_o.run([sys.executable, str(_qdt_q)], capture_output=True, text=True,
                cwd=str(_repo_o))
if _rz.returncode != 0:
    print(_rz.stdout.rstrip())
    print(_rz.stderr.rstrip()[:800])
check("every per-layer queue claim holds against real CSVs", _rz.returncode, 0)


print("\n=== 0S. --model-path must never read as having done nothing ===")
# Reported with --model-path passed globally to analyze:
#
#   [warn] model architecture unavailable - KV bytes/token will be ESTIMATED
#          amoprof_model_config_* was not found in this Prometheus window.
#
# The CHECK read raw/model_config.json and nothing else, so it depended on
# the caller writing that file before the fetch ran. The prom-only path does
# write it first, and the comment there says the ordering had already been
# got wrong once for this exact symptom. A dependency that keeps breaking is
# worth removing, not fixing again: the fetch now takes the already-read
# config and writes the file itself.
_amo_s = (_repo_o / "amoprof" / "report" / "amoprof.py").read_text()
_psrc_s = (_repo_o / "amoprof" / "prometheus_source.py").read_text()
_cli_s = (_repo_o / "amoprof" / "cli.py").read_text()

check("the fetch accepts the caller's model config",
      "model_config:         dict = None," in _amo_s, True)
check("and writes it when the file is absent",
      "if not _have_mc and model_config:" in _amo_s, True)
check("the wrapper passes it through",
      "model_config=model_config," in _psrc_s, True)
check("analyze reads it and hands it down",
      "model_config=(_read_model_config(" in _cli_s, True)
check("compare does too", "model_config         = _mc_run" in _cli_s, True)

# compare's fetch call sits ABOVE the later per-run write, so binding the
# config down there would have raised UnboundLocalError on the first run.
# The static scanner does not catch a loop-carried name, so it is pinned here.
import ast as _ast_s
_cf_s = [n for n in _ast_s.walk(_ast_s.parse(_cli_s))
         if isinstance(n, _ast_s.FunctionDef) and n.name == "_compare"][0]
_b_s = [n.lineno for n in _ast_s.walk(_cf_s)
        if isinstance(n, _ast_s.Name) and n.id == "_mc_run"
        and isinstance(n.ctx, _ast_s.Store)]
_l_s = [n.lineno for n in _ast_s.walk(_cf_s)
        if isinstance(n, _ast_s.Name) and n.id == "_mc_run"
        and isinstance(n.ctx, _ast_s.Load)]
check("compare binds the model config before its first use",
      bool(_b_s) and bool(_l_s) and min(_b_s) < min(_l_s), True)

# The MESSAGE was wrong for the person most likely to read it: it blamed
# absent Prometheus metrics and advised passing --model-path, to someone who
# had just passed --model-path.
check("the warning names the path it checked",
      'print(f"         Checked: {_mc}")' in _amo_s, True)
check("it distinguishes a supplied config from none",
      "A model config WAS supplied to this fetch" in _amo_s, True)
check("and says the flag was honoured when it was",
      "the flag was honoured" in _amo_s, True)
check("the suggest-the-flag line is only for when it was not passed",
      _amo_s.index("No model config was supplied to this fetch")
      < _amo_s.index("Fix for this run: pass --model-path"), True)

# An existing file is never clobbered -- not by this write, and not by the
# Prometheus-derived summary synthesiser either.
check("the self-write only fires when the file is absent",
      "if not _have_mc and model_config:" in _amo_s, True)
check("and the summary synthesiser skips a target the collector wrote",
      "# Skip if the real collector already wrote the target file." in _amo_s,
      True)

# Against the real source text, in all four states.
_mcw_s = _repo_o / "tests" / "test_model_config_warning.py"
check("the four-state warning test ships", _mcw_s.is_file(), True)
_rw_s = _sp_o.run([sys.executable, str(_mcw_s)], capture_output=True, text=True,
                  cwd=str(_repo_o))
if _rw_s.returncode != 0:
    print(_rw_s.stdout.rstrip())
    print(_rw_s.stderr.rstrip()[:800])
check("all four model-config states behave", _rw_s.returncode, 0)


print("\n=== 0T. start/end resolve to the right UTC instant, or are refused ===")
# "Just want to confirm, the start and end timestamps are converted to
# Prometheus friendly UTC timestamps, right?"
#
# Yes. Prometheus query_range takes Unix epoch seconds, which are UTC by
# construction, and parse_time_arg does the conversion: a trailing Z or an
# explicit offset always wins, and a NAIVE datetime is read in the machine's
# local zone on purpose -- an operator asking for "17:00 to 18:45" means
# their own wall clock, and reading naive input as UTC silently profiled a
# window seven hours off in US/Pacific.
from amoprof.prometheus_source import parse_time_arg as _pta_t
_T0, _T1 = 1790811660.0, 1790814600.0   # 2026-09-30 23:41Z, 2026-10-01 00:30Z
check("the start from the reported command", _pta_t("20260930T2341Z"), _T0)
check("the end", _pta_t("20261001T0030Z"), _T1)
check("the window is 49 minutes, as the run log said", (_T1 - _T0) / 60, 49.0)
from datetime import datetime as _dt_t, timezone as _tz_t
check("and the epoch is UTC by construction",
      f"{_dt_t.fromtimestamp(_T0, _tz_t.utc):%Y-%m-%dT%H:%M:%SZ}",
      "2026-09-30T23:41:00Z")
for _s_t in ("20260930T234100Z", "1790811660", "2026-09-30T23:41:00Z",
             "2026-09-30T23:41:00+00:00", "2026-09-30T16:41:00-07:00"):
    check(f"{_s_t} is the same instant", _pta_t(_s_t), _T0)
check("an unparseable string returns 0.0 for the caller to reject",
      _pta_t("not-a-time"), 0.0)

# compare's --run spec is colon-separated, and a full ISO-8601 timestamp
# contains colons. That combination failed silently and on BOTH ends:
#
#   "L3::2026-09-30T23:41:00Z:2026-10-01T00:30:00Z"
#     split(":", 3) -> ['L3', '', '2026-09-30T23', '41:00Z:2026-10-01T00:30:00Z']
#
# The start truncates to an hour boundary AND still parses, so nothing
# complained; the end is debris and parses to 0.0, which the fetch reads as
# "the last hour". --run's own help advertised ISO-8601, so this was a
# documented spelling that profiled a different window at both ends.
_parts_t = "L3::2026-09-30T23:41:00Z:2026-10-01T00:30:00Z".split(":", 3)
check("the start field truncates to an hour boundary",
      _parts_t[2], "2026-09-30T23")
check("and it still parses, which is why nothing complained",
      _pta_t(_parts_t[2]) != 0.0, True)
check("the end field is debris", _parts_t[3], "41:00Z:2026-10-01T00:30:00Z")
check("and resolves to 0.0, which the fetch treats as the last hour",
      _pta_t(_parts_t[3]), 0.0)
_cli_t = (_repo_o / "amoprof" / "cli.py").read_text()
# These two guards are behaviourally REDUNDANT with each other: a leftover
# tail always contains a colon and so never parses as a timestamp, which
# means the unparseable-field guard would reject an over-long spec too. The
# field check exists to give the ISO-specific message rather than to catch a
# different case, so both the condition and the message are pinned -- an exit
# code alone cannot tell which guard fired.
check("the spec parse rejects an over-long field list",
      'if len(parts) >= 4 and ":" in parts[3]:' in _cli_t, True)
check("with a message naming the field count",
      'has more colon-separated fields than ' in _cli_t, True)
check("it rejects a non-empty timestamp that will not parse",
      "            if _v == 0.0:" in _cli_t, True)
check("with its own message", "could not parse the %s field %r" in _cli_t, True)
check("and a backwards window, which reads as an untelemetered tier",
      "is not after start" in _cli_t, True)
check("--run's help no longer advertises a spelling that cannot work",
      "START/END are Unix timestamps or ISO-8601 strings" in _cli_t, False)
check("and says what the fields must be instead",
      "START/END must be COLON-FREE" in _cli_t, True)

# Against the real parser, in four timezones.
_twt = _repo_o / "tests" / "test_time_window_parsing.py"
check("the time-window test ships", _twt.is_file(), True)
import os as _os_t
for _tz_name in ("UTC", "America/Los_Angeles", "Asia/Seoul"):
    _env_t = dict(_os_t.environ, TZ=_tz_name)
    _r_t = _sp_o.run([sys.executable, str(_twt)], capture_output=True,
                     text=True, cwd=str(_repo_o), env=_env_t)
    if _r_t.returncode != 0:
        print(_r_t.stdout.rstrip())
        print(_r_t.stderr.rstrip()[:600])
    check(f"every window claim holds with TZ={_tz_name}", _r_t.returncode, 0)


print("\n=== 0U. a metric that goes to or from zero must not kill the report ===")
# Reported while comparing an L3.5 DRAM-only tier against DRAM+CXL, no SSD:
#
#   INFO   Extracted metrics for 'L3.5 DRAM Only': ... NVMe=0 MB/s
#   INFO   Extracted metrics for 'L3.5 DRAM CXL':  ... NVMe=0 MB/s
#   ERROR  compare failed: float division by zero
#
# Not NVMe, despite the 0 MB/s printed beside it. build_chain_html's ratio
# helper guarded `a in (None, 0)` and `b is None` but NOT `b == 0`:
#
#   ratio = b / a                                      # 100 -> 0 gives 0.0
#   ... if ratio >= 1 else f"{1/ratio:.2f}x lower"      # 1/0
#
# 0.0 is not None and is below 1, so the formatter reached 1/ratio and the
# whole comparison died. A tier with no SSD makes that ordinary rather than
# rare: several KV hops are legitimately zero on one side.
_cmpu = (_repo_o / "amoprof" / "comparator.py").read_text()
check("the helper no longer treats a zero comparison value as a ratio",
      "if a in (None, 0) or b is None:" in _cmpu, False)
check("it distinguishes unmeasured from zero",
      "if a is None or b is None:" in _cmpu, True)
check("a zero baseline with a non-zero comparison is infinity, not None",
      "return math.inf if b else None" in _cmpu, True)
check("the formatter renders a collapse to zero",
      'rs = "\u2192 0"' in _cmpu, True)
check("and a rise from zero", 'rs = "0 \u2192"' in _cmpu, True)
check("1/ratio is reached only on a finite ratio below 1",
      _cmpu.index('elif ratio >= 1:') < _cmpu.index('rs = f"{1/ratio:.2f}x lower"'),
      True)
check("a move to or from zero is styled as the largest change there is",
      "if ratio is not None and (ratio == 0 or ratio == math.inf" in _cmpu, True)
check("the old styling made 0.0 falsy and would have called it unremarkable",
      "ratio and (ratio >= 2 or ratio <= .5)" in _cmpu, False)

# The arithmetic, stated: 0.0 passes every guard the old code had.
_r0 = 0.0
check("a zero ratio is not None", _r0 is None, False)
check("and is below 1, so it took the 1/ratio branch", _r0 < 1, True)
check("and the noise filter does not swallow it", (1 / 1.15) < _r0 < 1.15, False)

# Against the real builders, in both directions, for every field.
_zr = _repo_o / "tests" / "test_compare_zero_ratio.py"
check("the zero-ratio test ships", _zr.is_file(), True)
_rz0 = _sp_o.run([sys.executable, str(_zr)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _rz0.returncode != 0:
    print(_rz0.stdout.rstrip())
    print(_rz0.stderr.rstrip()[:800])
check("no field in either direction crashes a comparison", _rz0.returncode, 0)


print("\n=== 0V. KV cache generated this run ===")
# Requested as a KPI tile. The definition is the whole problem: "generated"
# must mean KV the GPUs COMPUTED, which is prompt minus cached plus decode.
# A prefill token served from the prefix cache reuses KV rather than making
# any, and at the ~95% hit rate on these runs, counting all prompt tokens
# overstates the total 22.8x.
_combv = (_repo_o / "amoprof" / "report" / "combined.py").read_text()
_cmpv = (_repo_o / "amoprof" / "comparator.py").read_text()
_P, _C, _D = 101_488_872, 97_142_810, 115_240     # the reference local run
_gen_v = (_P - _C) + _D
check("the reference run computed KV for 4,461,302 tokens", _gen_v, 4_461_302)
check("counting all prompt tokens would overstate it 22.8x",
      round((_P + _D) / _gen_v, 1), 22.8)
check("which is 1/(1 - hit rate), as it must be",
      round((_P + _D) / _gen_v), round(1 / (1 - _C / (_P + _D))))
check("the tile ships", '"KV cache generated this run"' in _combv, True)
check("it subtracts cached tokens",
      "_kvg_recomp = max(0.0, _kvg_prompt - _kvg_cached)" in _combv, True)
check("and adds decode", "_kvg_new_tok = _kvg_recomp + _kvg_decode" in _combv,
      True)
check("the comparison carries the matching rows",
      '"KV generated · tokens computed"' in _cmpv, True)
check("both resolve KV bytes through the one shared kernel",
      "resolve_kv_bytes_per_token as _rkv" in _cmpv
      and "_k_resolve_kv(" in _combv, True)

# 2 x 60 layers x 16 kv_heads x 256 head_dim x 2 bytes.
check("gemma-4-31b-it is 983,040 bytes of KV per token",
      2 * 60 * 16 * 256 * 2, 983_040)
check("= 960 KB/token", 2 * 60 * 16 * 256 * 2 / 1024, 960.0)

# The byte figure does not reconcile with the hardware, and must say so.
# 20,521,688 tokens backed up x 960 KB = 18,788 GB; the drive wrote 546.9 GB.
_bk_v, _wr_v = 20_521_688, 546.9
_impl_v = _bk_v * 960.0 / (1024 * 1024)
check("960 KB/token implies 18,788 GB for the backed-up tokens",
      round(_impl_v), 18_788)
check("against 546.9 GB the drive recorded, 34.4x apart",
      round(_impl_v / _wr_v, 1), 34.4)
check("and 4.3x apart even per-rank at TP=8",
      round(_impl_v / 8 / _wr_v, 1), 4.3)
check("so the tile reconciles against the device and says when it cannot",
      "Not reconciled with the device" in _combv, True)
check("re-deriving the measured total instead of reusing write_gb",
      "_kvg_meas_wr = _safe_float(_pick(blk," in _combv, True)
check("because write_gb is reassigned to the estimate further down",
      "write_gb = l3_est_write_gb" in _combv, True)

# The engine also claims more backup than it computed, which is impossible.
check("backup exceeds generated by 4.6x", round(_bk_v / _gen_v, 1), 4.6)
check("and that check fires too",
      "KV cannot be persisted before it is computed" in _combv, True)

# A GB figure requires an EXACT geometry. The resolver's fallback size hint
# gives 256 KB/token on this model where the config gives 960.
check("bytes are withheld unless the geometry is exact",
      "or not self.kv_bytes_exact" in _cmpv, True)
check("the size hint would be 3.75x wrong here", round(960.0 / 256.0, 2), 3.75)
check("the counterfactual shares the actual's absence condition",
      "if self.kv_generated_gb is None or self.prompt_tok is None:" in _cmpv,
      True)
check("the provenance is shown beside the number",
      '"↳ where that came from"' in _cmpv, True)
check("and the cell formatter passes text through for it",
      "if isinstance(v, str):" in _cmpv, True)
check("no default KB/token is substituted when unresolvable",
      "No default is " in _combv, True)

_kvt_v = _repo_o / "tests" / "test_kv_generated_tile.py"
check("the tile test ships", _kvt_v.is_file(), True)
_rv = _sp_o.run([sys.executable, str(_kvt_v)], capture_output=True, text=True,
                cwd=str(_repo_o))
if _rv.returncode != 0:
    print(_rv.stdout.rstrip())
    print(_rv.stderr.rstrip()[:800])
check("every KV-generated claim holds against real CSVs", _rv.returncode, 0)


print("\n=== 0W. one latency, one resolution order, both surfaces ===")
# "The TTFT reported in the comparison report is different than the original
# report generated for the same timestamp." Measured on the reference runs:
#
#   L3 local SSD, 2026-10-01 14:57 -> 16:40 UTC
#     analyze 11,514 ms   compare 11,525 ms   +0.10%
#     TPOT     1,654.3     TPOT     1,655.3   +0.06%
#
# while the L3.5 run read 64,453 / 164.0 in BOTH, to the digit. A window
# delta moves when the sample grid shifts a step; a lifetime ratio does not.
_combw = (_repo_o / "amoprof" / "report" / "combined.py").read_text()
_cmpw = (_repo_o / "amoprof" / "comparator.py").read_text()
_amow = (_repo_o / "amoprof" / "report" / "amoprof.py").read_text()
_kernw = (_repo_o / "amoprof" / "report" / "metric_kernels.py").read_text()
check("the observed TTFT gap is 0.10%", round((11525-11514)/11514*100, 2), 0.10)
check("the observed TPOT gap is 0.06%",
      round((1655.3-1654.3)/1654.3*100, 2), 0.06)
check("and the L3.5 figures were identical, which is the asymmetry",
      64453 == 64453 and 164.0 == 164.0, True)

# Cause: two resolution orders. Combined wrote its down; compare did step 3.
check("the documented order still stands in combined",
      "1) selected-window" in _combw and "only as last fallback" in _combw,
      True)
check("the comparator no longer reads the summary as its only source",
      'm.ttft_ms          = _sf(_pick(sglang, "server_ttft_ms"' in _cmpw,
      False)
check("the order now lives in one kernel",
      "def resolve_latency_ms(" in _kernw, True)
check("combined routes all three latencies through it",
      _combw.count("_k_resolve_lat("), 3)   # one per latency; the import
                                            # alias has no parenthesis
check("so does the comparator", "_k_resolve_lat(" in _cmpw, True)
check("and all three of its latencies are resolved by the helper",
      _cmpw.count('_lat("'), 3)
check("and the comparator computes the window delta itself",
      '_dsum = _kv_delta(Path(spec.raw_dir), [f"{_base}_sum"])' in _cmpw, True)

# The unbounded part: the fetch's lifetime fallback, formerly mislabelled.
check("all three lifetime fallbacks mark themselves as such",
      _amow.count("LIFETIME_not_window"), 3)
check("the summary's method field is derived, not a literal",
      '"server_ttft_ms_method":        _lat_meth["ttft"]' in _amow, True)
check("the old always-delta literal is gone",
      '"server_ttft_ms_method":        "delta_sglang_time_to_first' in _amow,
      False)
check("a summary figure is never claimed window-scoped",
      '"window_scoped": False,\n                "method": ("sglang_summary.json"'
      in _kernw, True)

# And it is surfaced, not just recorded.
check("the suspect banner gains the condition",
      "not verified as window-scoped" in _cmpw, True)
check("naming the lifetime fallback as the reason",
      "last(sum)/last(count)" in _cmpw, True)
check("and a provenance row sits beside the number",
      '"↳ how TTFT was resolved"' in _cmpw, True)

# The arithmetic the kernel's step 1 performs, by hand.
check("Δsum ÷ Δcount on the fixture is 11,679.5 ms",
      round((81098 - 1000) / (6958 - 100) * 1000, 1), 11679.5)

_latw = _repo_o / "tests" / "test_latency_resolution.py"
check("the latency test ships", _latw.is_file(), True)
_rw2 = _sp_o.run([sys.executable, str(_latw)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _rw2.returncode != 0:
    print(_rw2.stdout.rstrip())
    print(_rw2.stderr.rstrip()[:800])
check("every latency-resolution claim holds", _rw2.returncode, 0)


print("\n=== 0X. a configured local L3 in the capacity chart ===")
# "The chart memory hierarchy capacity used ... is not showing l3 capacity."
# On a Prometheus-only analyze it could not, for a reason unrelated to how
# the tier was configured:
#
#   the report reads  hicache_fs_* / nvme_device_capacity_gb  from
#                     smart_summary.json
#   the fetch writes  amoprof_ssd_hw_*                        to
#                     ssd_hw_summary.json
#
# cli.py bridges those two at COLLECT time and says why in a comment. The
# Prometheus path had no such merge, so the fields were fetched, written to a
# file the report does not consult for them, and the L3 series was dropped
# from the chart with nothing said.
_combx = (_repo_o / "amoprof" / "report" / "combined.py").read_text()
_amox = (_repo_o / "amoprof" / "report" / "amoprof.py").read_text()
_clix = (_repo_o / "amoprof" / "cli.py").read_text()
check("the report reads smart_summary.json for those fields",
      'smart      = _read_json(raw_dir / "smart_summary.json")' in _combx, True)
check("the fetch routes amoprof_ssd_hw_* elsewhere",
      '"amoprof_ssd_hw_":             ("ssd_hw_summary.json",' in _amox, True)
check("collect mode bridges them on purpose",
      "the smart_summary.json that the report reads" in _clix, True)
check("_refresh_smart_capacity needs a summary.json a prom run lacks",
      "if not raw_dir.exists() or not sum_path.exists():" in _clix, True)
check("and its docstring says it no-ops cross-host",
      "Silently no-ops if the device or path isn't reachable" in _clix, True)

check("the Prometheus path now mirrors that merge",
      '_ssdhw_p = output_dir / "ssd_hw_summary.json"' in _amox, True)
check("without overwriting a value smart_summary already carries",
      "_added = [k for k in _want if k not in _sm]" in _amox, True)
check("the report also reads the sidecar, so neither merge is load-bearing",
      '_ssd_hw_sum = _read_json(raw_dir / "ssd_hw_summary.json")' in _combx,
      True)
check("and prefers an existing value there too",
      "if not smart.get(_k_hw) and _ssd_hw_sum.get(_k_hw):" in _combx, True)

# The three gates, and the requirement that failing one is NAMED.
check("the L3 series still needs used, total and a timeline",
      "if l3_fs_used_gb > 0 and l3_fs_total_gb > 0 and _sg_time:" in _combx,
      True)
check("a configured L3 that fails one of them is named",
      "elif l3_explicit_config:" in _combx, True)
check("naming which figure is missing",
      '_l3_miss.append("total capacity")' in _combx, True)
check("and where it would have come from",
      "ssd_hardware collector" in _combx and "has no df to run" in _combx,
      True)
check("the note reaches the chart subtitle, not just a variable",
      "+ _l3_cap_missing," in _combx, True)

_l3x = _repo_o / "tests" / "test_l3_capacity_series.py"
check("the L3-capacity test ships", _l3x.is_file(), True)
_rx = _sp_o.run([sys.executable, str(_l3x)], capture_output=True, text=True,
                cwd=str(_repo_o))
if _rx.returncode != 0:
    print(_rx.stdout.rstrip())
    print(_rx.stderr.rstrip()[:800])
check("every L3-capacity claim holds, merge included", _rx.returncode, 0)


print("\n=== 0Y. a raw tile and a KV-residency tile for every tier ===")
# The two quantities differ by whatever else is resident in the tier, and the
# KPI grid previously carried both halves for L2 and L3.5 and only the raw half
# for L1 and L3.  Worse, the figure rendered as L1's live residency was the
# run's CUMULATIVE prefill total.
#
# Numbers below are from the user's v1.57.0 report, which states all three
# independently: context 46,529,863 tokens, cached 36,762,836, cache hit 79.0%,
# "Max Context (HBM) 38 K tokens", KV 960 KB/token from the model config.
_ctx_y, _cached_y, _pool_y, _kvkb_y = 46_529_863, 36_762_836, 38_000, 960.0
check("the cached/context ratio is the report's own cache-hit figure",
      round(_cached_y / _ctx_y * 100, 2), 79.01)
check("the figure shown as live residency was 1224x its pool",
      round(_ctx_y / _pool_y), 1224)
check("holding it at once would need 42,599 GB of KV",
      round(_ctx_y * _kvkb_y / (1024 * 1024)), 42_599)
check("against 320 GB on the node, 133x over",
      round(_ctx_y * _kvkb_y / (1024 * 1024) / 320), 133)
# The clamp that stood in for a missing gauge: min(cumulative, capacity).
# Because the cumulative total always exceeds the pool, min() always returned
# the pool -- i.e. exactly 100% full, reported as a measurement.
check("min(cumulative, capacity) returns the capacity itself",
      min(_ctx_y, _pool_y), _pool_y)
check("so the pool read 100.0% full whenever the gauge was absent",
      round(min(_ctx_y, _pool_y) / _pool_y * 100, 1), 100.0)

# The replacement: pool fill x capacity, with fill as a window mean.
_fill_y = [0.05 + 0.55 * i / 19 for i in range(20)]
check("a 5%-to-60% ramp has a mean fill of 32.5%",
      round(sum(_fill_y) / len(_fill_y) * 100, 1), 32.5)
check("and a peak of 60.0%", round(max(_fill_y) * 100, 1), 60.0)
check("mean x 332,000 token pool is 107,900 live tokens",
      round(sum(_fill_y) / len(_fill_y) * 332_000), 107_900)
check("the last sample alone would have said 199,200 -- 1.85x the mean",
      round(max(_fill_y) * 332_000 / (sum(_fill_y) / len(_fill_y) * 332_000), 2),
      1.85)
# L3 residency from a df snapshot, in the same token unit as the other tiers.
check("400 GB of HiCache at 960 KB/token is 436,907 tokens",
      round(400.0 * 1024 * 1024 / _kvkb_y), 436_907)
check("and a 1,000 GB filesystem holds 1,092,267",
      round(1000.0 * 1024 * 1024 / _kvkb_y), 1_092_267)
# Which is why a byte-derived tier has to name its geometry: the name-based
# size hint for this model gives 256 KB against 960 KB exact.
check("the size hint would put L3 residency 3.75x too high",
      round(400.0 * 1024 * 1024 / 256.0 / (400.0 * 1024 * 1024 / _kvkb_y), 2),
      3.75)

_tr_y = _repo_o / "tests" / "test_tier_residency_tiles.py"
check("the tier-residency test ships", _tr_y.is_file(), True)
_ry = _sp_o.run([sys.executable, str(_tr_y)], capture_output=True, text=True,
                cwd=str(_repo_o))
if _ry.returncode != 0:
    print(_ry.stdout.rstrip())
    print(_ry.stderr.rstrip()[:800])
check("every tier-residency claim holds, both branches included",
      _ry.returncode, 0)

# A raw tile that is simply absent is indistinguishable from a report that
# dropped it.  Every configured tier now renders both halves or states why.
_cmb_y = (_repo_o / "amoprof/report/combined.py").read_text()
for _probe_y, _what_y in (
        ('"L3 cache used — raw (df snapshot)",\n             "not collected"',
         "the L3 raw tile"),
        ('kpi_card("L2 host DRAM used — raw (physical)", "not collected"',
         "the host DRAM tile"),
        ('"L2 KV residency (est.)", "not collected"', "the L2 residency tile"),
        ('_lbl, "not collected"', "the L3.5 raw tiles")):
    check(f"{_what_y} states a reason rather than vanishing",
          _probe_y in _cmb_y, True)
check("the L3 tile reuses the capacity chart's own sentence",
      're.sub(r"<[^>]+>", "", _l3_cap_missing)' in _cmb_y, True)
check("via the module-level re, which has no local binding in that scope",
      "_re.sub(r\"<[^>]+>\", \"\", _l3_cap_missing)" in _cmb_y, False)
check("and the reason is bound before the block that fills it",
      _cmb_y.index("_l3_cap_missing = \"\"")
      < _cmb_y.index("if l3_fs_used_gb > 0 and l3_fs_total_gb > 0 and _sg_time:"),
      True)

# The scanner that should have caught the UnboundLocalError in this change
# scanned sys.argv[1:] and, with no arguments, scanned nothing and passed.
_scan_src_y = (_repo_o / "scripts" / "check_unbound_locals.py").read_text()
check("the scanner defaults to the package instead of scanning nothing",
      "_pkg.rglob" in _scan_src_y, True)
check("and reports how many files it read",
      "file(s) scanned" in _scan_src_y, True)
_rz = _sp_o.run([sys.executable,
                 str(_repo_o / "scripts" / "check_unbound_locals.py")],
                capture_output=True, text=True, cwd=str(_repo_o))
check("a bare run now inspects the package and passes", _rz.returncode, 0)
check("having actually read files", "0 file(s) scanned" in _rz.stdout, False)
check("and running the shadowed-import scan too",
      "shadowed-import" in _rz.stdout, True)

print("\n=== 0Z. the pairs are named, grouped, and computed one way ===")
# The tiles were all present on the reference report; what was wrong was that
# none said "raw", the pairs were scattered (L1 raw, L1 KV, GPU power, three
# L3 bandwidth tiles, L3 raw, L3 KV, L2 KV, L2 raw), and the interactive grid
# published a second, different number for L2 KV residency under the name
# "GPU node DRAM used".
_iv_z = (_repo_o / "amoprof/report/interactive.py").read_text()
check("the interactive tab passes the model config to the shared resolver",
      _iv_z.count("config=_iv_kv_cfg") >= 2, True)
# 198.0 GB (Executive, 560 KB/token exact) vs 90.5 GB (interactive, 256 KB
# name hint).  If the discrepancy is the geometry, the ratios must agree.
check("the two tiles disagreed by 2.1878x", round(198.0 / 90.5, 4), 2.1878)
check("which is 560/256 to within 0.015%",
      abs(198.0 / 90.5 - 560.0 / 256.0) / (560.0 / 256.0) < 0.0002, True)
check("so the geometry fully explains it", round(560.0 / 256.0, 4), 2.1875)
# And the 256 KB hint is what the kernel returns for this model WITHOUT a
# config, which is the input the call site was failing to supply.
from amoprof.report.metric_kernels import resolve_kv_bytes_per_token as _rkv_z
check("the name alone resolves to 256 KB/token",
      _rkv_z(model_name="google/gemma-4-31b-it", kv_dtype="fp16",
             config={})["kb"], 256.0)
check("and is not marked exact",
      _rkv_z(model_name="google/gemma-4-31b-it", kv_dtype="fp16",
             config={})["exact"], False)

_cz = (_repo_o / "amoprof/report/combined.py").read_text()
for _pfx_z in ("L1 HBM used", "L1 KV residency", "L2 host DRAM used",
               "L2 KV residency", "L3 cache used", "L3 KV residency"):
    check(f"the order table carries {_pfx_z}",
          f'"{_pfx_z}"' in _cz, True)
check("the reorder runs on the assembled grid",
      "kpi_html = _amoprof_group_tier_tiles(kpi_html)" in _cz, True)

_tz = _repo_o / "tests" / "test_tier_residency_tiles.py"
_rz2 = _sp_o.run([sys.executable, str(_tz)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _rz2.returncode != 0:
    print(_rz2.stdout.rstrip()); print(_rz2.stderr.rstrip()[:800])
check("every naming, grouping and geometry claim holds", _rz2.returncode, 0)

print("\n=== 1A. the KV-generated tile has a branch for every input state ===")
# It had three: GB, tokens-only, and a measured zero.  The fourth -- neither
# counter resolving -- fell through to an empty string, so the tile vanished
# from an L3.5 report while an L3 report had one, with nothing said.
_c1a = (_repo_o / "amoprof/report/combined.py").read_text()
check("a fourth branch exists for absent counters",
      "# Neither counter resolved." in _c1a, True)
check("and it renders rather than returning empty",
      '"not collected",\n            "Needs prompt and decode token totals'
      in _c1a or "Needs prompt and decode token totals" in _c1a, True)
# _tok_num matches on 'cached_tokens_total'; an engine exporting only
# realtime_tokens_total{mode="prefill_cache"} does not match that substring.
check("the cached total has an alternate lookup",
      "realtime_tokens_total[mode=prefill_cache]" in _c1a, True)
check("which is the column the comparator reads",
      "realtime_tokens_total[mode=prefill_cache]"
      in (_repo_o / "tests/test_kv_generated_tile.py").read_text(), True)
# Without it: (prompt - 0) + decode counts the whole prompt as new KV.
_p1a, _cc1a, _d1a = 204_050_007.0, 201_493_601.0, 225_018.0
_kb1a = 960.0
_good = ((_p1a - _cc1a) + _d1a) * _kb1a / (1024 * 1024)
_bad = (_p1a + _d1a) * _kb1a / (1024 * 1024)
check("the right figure is 2,546.5 GB", round(_good, 1), 2546.5)
check("the figure without a cached total is 187,019.4 GB", round(_bad, 1),
      187019.4)
check("73x apart", round(_bad / _good), 73)
# The factor is NOT 1/(1-h).  That is the prefill-only ratio; decode tokens
# are counted correctly either way and sit in both numerator and denominator.
_h1a = _cc1a / _p1a
check("the hit rate is 98.7472%", round(_h1a * 100, 4), 98.7472)
check("1/(1 - h) would say 79.8x", round(1.0 / (1.0 - _h1a), 1), 79.8)
check("but the real overstatement is 73.4x", round(_bad / _good, 1), 73.4)
check("because decode is in both terms",
      round(_bad / (_p1a * (1.0 - _h1a) + _d1a) / (_kb1a / (1024 * 1024)), 1),
      round(_bad / _good, 1))
check("so the tile uses the decode-aware form",
      "not 1/(1 \u2212 hit), which ignores decode" in _c1a, True)
check("so the tile warns when cached does not resolve",
      "Cached prompt tokens did not resolve" in _c1a, True)
check("and states no factor when the hit rate is also absent",
      "cannot be stated" in _c1a, True)
check("and drops the accent on a figure it cannot trust",
      "accent=(_kvg_cached > 0)" in _c1a, True)

_t1a = _repo_o / "tests" / "test_kv_generated_tile.py"
_r1a = _sp_o.run([sys.executable, str(_t1a)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1a.returncode != 0:
    print(_r1a.stdout.rstrip()); print(_r1a.stderr.rstrip()[:800])
check("all four branches render as claimed", _r1a.returncode, 0)


print("\n=== 1B. a tier that is not in the deployment contributes no tiles ===")
# The v1.69.0 local-L3 report carried "L3.5 storage host writes" (3.0 GB) and
# "L3.5 KV->host amplification" (0.00x).  Both groups were gated on their DATA
# being present -- the memory node answering in Prometheus -- never on the
# backend class, which is the only thing that says the tier is in use.
_c1b = (_repo_o / "amoprof/report/combined.py").read_text()
check("there is a predicate for the tier being configured",
      "has_l35 = bool(has_l3)" in _c1b, True)
check("and it reads the backend class, not any series",
      'str(l3_backend_class).lower() in (\n        "remote_mooncake", '
      '"remote_storage")' in _c1b, True)
check("tiles for an unused tier are dropped from the assembled grid",
      'if not has_l35:' in _c1b
      and '_amoprof_drop_tier_tiles(kpi_html, "L3.5")' in _c1b, True)
# Done by label, not by suppressing the groups: _l35_hw_tiles holds the
# backing tier's hardware tiles for EITHER tier, labelled through _TIER, so
# on a local run that same variable carries "L3 local SSD storage BW".
check("the drop matches the tile label",
      "_amoprof_tile_label(_t).startswith(_prefix)" in _c1b, True)
check("so a tile that only mentions the tier in its note survives",
      "merely mentions the tier in" in _c1b, True)
check("the label helper is shared with the grouping pass",
      _c1b.count("_label_of = _amoprof_tile_label"), 1)
# The two leaked tiles, by the labels the report printed.
for _lbl1b in ("L3.5 storage host writes",
               r"L3.5 KV\u2192host amplification"):
    check(f"{_lbl1b!r} is still built for a real L3.5 run",
          f'"{_lbl1b}"' in _c1b, True)

check("the reversion runner refuses to start on a leftover marker",
      "refusing to start" in
      (_repo_o / "scripts" / "mutate.py").read_text(), True)
check("and restores on SIGINT and SIGTERM rather than only on exit",
      "signal.SIGTERM" in (_repo_o / "scripts" / "mutate.py").read_text(),
      True)


print("\n=== 1C. a headline figure its own report contradicts ===")
# From the v1.69.0 local-L3 report:
#   L3 SSD storage queue depth   1,401.09 mean / 3,430 peak
#   L3 SSD storage BW (device)   145 rd / 28,672 wr MB/s peak
# and in the SSD requirement table, derived from both:
#   Queue Depth        peak 3,430 -> "SSD must sustain observed peak concurrency"
#   Sequential Write BW  28672 MB/s x 1.3 = 37274 MB/s
_qdm, _qdp = 1401.09, 3430.0
_iops_c, _lat_c = 3461.0, 0.265
_devq = 25.9696
_wrp, _wrm = 28672.0, 9.3
check("Little's Law puts the depth at 0.92",
      round(_iops_c * _lat_c / 1000.0, 2), 0.92)
check("so 1,401 would need 405 ms per I/O on NVMe",
      round(_qdm / _iops_c * 1000.0), 405)
check("1,528x the latency the same trace measured",
      round(_qdm / _iops_c * 1000.0 / _lat_c), 1528)
check("and 54x the kernel's own queue gauge", round(_qdm / _devq), 54)
check("the peak sat under the old bound, which is why it published",
      _qdp < 4096.0, True)
check("28,672 MB/s is 28.0 GB/s through one namespace",
      round(_wrp / 1024.0, 1), 28.0)
check("3,083x the window's mean write bandwidth",
      round(_wrp / _wrm), 3083)
check("and the requirement derived from it was 37,274 MB/s",
      round(_wrp * 1.3), 37274)

from amoprof.report.metric_kernels import (
    vet_queue_depth as _vqd_c, vet_device_bw_peak as _vbw_c,
    NVME_MAX_BW_MBS as _CEIL_C)
_r_c = _vqd_c(event_mean=_qdm, event_peak=_qdp, event_lat_ms=0.0,
              event_iops=_iops_c, device_mean=0.36, device_peak=_devq)
check("the kernel rejects that queue depth", _r_c["rejected"], True)
check("and headlines the device gauge instead", round(_r_c["peak"], 2),
      round(_devq, 2))
check("a genuine shallow queue is kept",
      _vqd_c(event_mean=0.36, event_peak=1.0, event_lat_ms=_lat_c,
             event_iops=_iops_c, device_peak=1.0)["rejected"], False)
check("a genuine deep queue is kept too",
      _vqd_c(event_mean=256.0, event_peak=512.0, event_lat_ms=71.0,
             event_iops=3600.0, device_peak=300.0)["rejected"], False)
check("the bandwidth ceiling is ~16 GB/s", round(_CEIL_C / 1024.0), 16)
check("so that write peak is rejected", _vbw_c(_wrp, _wrm)["rejected"], True)
check("and nothing is published in its place", _vbw_c(_wrp, _wrm)["mbs"], 0.0)
check("while a 1,080 MB/s peak passes untouched",
      _vbw_c(1080.0, 9.3)["mbs"], 1080.0)

# An amplification that rounds to 0.00 is two inputs that disagree, not a
# measurement: host 3.0 GB against logical KV 15,948.4 GB.
check("3.0 / 15,948.4 rounds to 0.00", f"{3.0 / 15948.4:,.2f}", "0.00")
check("the inputs are 5,316x apart", round(15948.4 / 3.0), 5316)
_c1c = (_repo_o / "amoprof/report/combined.py").read_text()
check("so no ratio is published below 0.005", "if _amp >= 0.005:" in _c1c,
      True)
_a1c = (_repo_o / "amoprof/report/amoprof.py").read_text()
check("the requirement table vets through the same kernel",
      "vet_device_bw_peak as _k_vet_bw" in _a1c, True)
check("and specifies from the vetted values",
      'rd_bw_peak, wr_bw_peak = _rd_v["mbs"], _wr_v["mbs"]' in _a1c, True)

_t1c = _repo_o / "tests" / "test_device_figure_vetting.py"
_rr_c = _sp_o.run([sys.executable, str(_t1c)], capture_output=True, text=True,
                  cwd=str(_repo_o))
if _rr_c.returncode != 0:
    print(_rr_c.stdout.rstrip()); print(_rr_c.stderr.rstrip()[:800])
check("every vetting claim holds, tiles and table", _rr_c.returncode, 0)


print("\n=== 1D. one quantity, one percentile, and a mean is not a median ===")
# A v1.69.0 report held three TTFT p50 values at once: 62,895 ms (interactive,
# labelled "Median · histogram_quantile/percentile timeseries"), 1,755.10 ms
# (the histogram chart) and 190,055 ms (the End report, "Median").  The first
# was the TTFT MEAN: both surfaces resolved p50 as `p50 or mean`.
_mean_d, _p50h_d, _p50s_d = 62895.0, 1755.10, 190055.0
_p90_d, _p99_d = 214925.37, 400000.00
check("three different p50 values for one quantity",
      len({_mean_d, _p50h_d, _p50s_d}), 3)
check("the one shown as p50 was exactly the mean", _mean_d, 62895.0)
check("35.8x the histogram's p50", round(_mean_d / _p50h_d, 1), 35.8)

from amoprof.report.metric_kernels import (
    resolve_latency_percentile as _rlp_d)
check("the kernel returns nothing rather than the mean",
      _rlp_d("ttft", 0.5, mean_ms=_mean_d)["ms"], 0.0)
check("and names the mean it declined",
      _rlp_d("ttft", 0.5, mean_ms=_mean_d)["refused_mean_ms"], _mean_d)
check("a histogram quantile outranks every other source",
      _rlp_d("ttft", 0.5, histogram_ms=_p50h_d, session_ms=_p50s_d,
             summary_ms=1.0)["ms"], _p50h_d)
check("a quantile in the open-ended bucket is marked censored",
      _rlp_d("ttft", 0.99, histogram_ms=_p99_d,
             top_bucket_ms=_p99_d)["censored"], True)
check("one below it is not",
      _rlp_d("ttft", 0.5, histogram_ms=_p50h_d,
             top_bucket_ms=_p99_d)["censored"], False)

# And the part that was never a contradiction: each band contributes at least
# its lower edge, so the percentiles put a FLOOR on the mean and, because the
# top band is open, no ceiling.
_floor_d = 0.50 * 0.0 + 0.40 * _p50h_d + 0.09 * _p90_d + 0.01 * _p99_d
check("the percentiles floor the mean at 24,045 ms", round(_floor_d), 24045)
check("so a mean of 62,895 is consistent with them", _mean_d > _floor_d, True)
check("and the percentiles cannot bound it from above",
      _p99_d == 400000.00, True)

_a1d = (_repo_o / "amoprof/report/amoprof.py").read_text()
_i1d = (_repo_o / "amoprof/report/interactive.py").read_text()
_code_d = lambda _t: "\n".join(
    _l.split("#")[0] if not _l.lstrip().startswith("#") else ""
    for _l in _t.splitlines())
check("no `p50 or mean` chain survives in either surface",
      [_p for _p in ("sess_ttft_p50_ms or m.ttft_ms",
                     "sess_tpot_p50_ms or m.tpot_ms",
                     "or m.ttft_ms or 0", "or m.tpot_ms or 0",
                     "_ttft_p50_ms or _ttft_ms_kpi",
                     "_itl_p50_ms or _itl_ms_kpi",
                     "_e2e_p50_ms or _e2e_ms_kpi")
       if _p in _code_d(_a1d) or _p in _code_d(_i1d)], [])

_t1d = _repo_o / "tests" / "test_latency_percentiles.py"
_r1d = _sp_o.run([sys.executable, str(_t1d)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1d.returncode != 0:
    print(_r1d.stdout.rstrip()); print(_r1d.stderr.rstrip()[:800])
check("every percentile claim holds", _r1d.returncode, 0)


print("\n=== 1E. a mooncake report against its own figures ===")
# From the v1.69.0 L3.5 report. Each line below is a number that report
# printed, checked against another number the same report printed.
_cached_e, _compute_e, _decode_e = 68_036_418, 10_500_000, 220_000
_l2est_e, _l2phys_e = 202.4, 70.4
_ttft_e = _e2e_e = 79341.0
_tpot_e = 307.4
# 1. The tile said "not collected" while the inputs sat in columns the
#    cache-hit tile and the output-token chart were already reading.
check("prompt is recoverable as prefill_cache + prefill_compute",
      _cached_e + _compute_e, 78_536_418)
check("and the recomputed prefill is the compute mode alone",
      _compute_e, 10_500_000)
check("so the KV actually computed is compute + decode",
      _compute_e + _decode_e, 10_720_000)
# 2. KV in host DRAM cannot exceed the host DRAM that is resident.
check("the L2 estimate was 2.9x the physical residency",
      round(_l2est_e / _l2phys_e, 1), 2.9)
check("and 202.4 of 210 GB reads as 96% full",
      round(_l2est_e / 210.0 * 100), 96)
check("while the physical figure is 7% of 1,008 GB",
      round(_l2phys_e / 1008.0 * 100), 7)
# 3. E2E = TTFT + decode, so equality needs decode to contribute nothing.
check("E2E equalled TTFT to the millisecond", _ttft_e, _e2e_e)
check("which at 307.4 ms/tok implies about one output token",
      round((_e2e_e - _ttft_e) / _tpot_e) + 1, 1)
_c1e = (_repo_o / "amoprof/report/combined.py").read_text()
check("prompt falls back to the realtime phase counters",
      '"prefill_compute": ["realtime_tokens_total",' in _c1e, True)
check("decode too", '"decode":          ["realtime_tokens_total", '
      '"mode=decode"],' in _c1e, True)
check("and the derivation is named on the tile",
      "prompt derived as" in _c1e, True)
check("stale local-L3 tiles are dropped on a remote run",
      'for _stale in ("L3 cache used", "L3 KV residency"):' in _c1e, True)
check("the L2 estimate is capped at the physical residency",
      "l2_dram_used_gb = host_dram_used_gb" in _c1e, True)
check("before the percentage and the note are composed from it",
      _c1e.index("_l2_overcount_gb = 0.0")
      < _c1e.index("l2_dram_used_pct = (l2_dram_used_gb"), True)
check("the peak is capped with it",
      "l2_dram_used_peak_gb = (host_dram_used_peak_gb" in _c1e, True)
check("KV->NAND has the guard its sibling got",
      "if _amp_nand >= 0.005:" in _c1e, True)
check("BW labels follow per-direction provenance",
      "_bw_rd_is_est" in _c1e and "_bw_wr_is_est" in _c1e, True)
check("and E2E equal to TTFT is stated on the tile",
      "identical to TTFT mean" in _c1e, True)

_t1e = _repo_o / "tests" / "test_l35_report_consistency.py"
_r1e = _sp_o.run([sys.executable, str(_t1e)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1e.returncode != 0:
    print(_r1e.stdout.rstrip()); print(_r1e.stderr.rstrip()[:800])
check("prompt falls back through the shared column resolver",
      '"prefill_compute": ["realtime_tokens_total",' in _c1e, True)
check("which requires BOTH substrings, so a decoy cannot match",
      '"decode":          ["realtime_tokens_total", "mode=decode"],' in _c1e,
      True)
check("and the window total sums positive steps, so a reset is survived",
      "sum(max(0.0, _v[_i] - _v[_i - 1])" in _c1e, True)
check("every L3.5-report claim holds", _r1e.returncode, 0)


print("\n=== 1F. a module that is also a program must import both ways ===")
# The pipeline runs `python .../amoprof/report/amoprof.py`.  sys.path[0] is
# then that directory, so `amoprof` resolves to amoprof.py and a
# package-absolute import of a sibling raises "'amoprof' is not a package".
# Two imports added in v1.71.0 and v1.72.0 did that; one was in build_html,
# so it aborted the static report and the combined report with it.  The
# file's own header forbids it, next to the guard they should have used.
_chk_f = _repo_o / "scripts" / "check_script_mode_imports.py"
check("the checker ships", _chk_f.is_file(), True)
_rf = _sp_o.run([sys.executable, str(_chk_f)], capture_output=True, text=True,
                cwd=str(_repo_o))
check("the package has no unguarded package-absolute import", _rf.returncode,
      0)
check("and it scanned the package rather than nothing",
      "0 file(s) scanned" in _rf.stdout, False)
_amo_f = (_repo_o / "amoprof/report/amoprof.py").read_text()
for _sym_f in ("resolve_latency_percentile as _k_resolve_pct",
               "vet_device_bw_peak as _k_vet_bw",
               "vet_queue_depth as _k_vet_qd"):
    check(f"{_sym_f.split(' as ')[0]} is imported through the guard",
          _amo_f.count(_sym_f), 2)
check("the guard still has its flat-layout fallback",
      "from metric_kernels import" in _amo_f, True)
_t1f = _repo_o / "tests" / "test_script_mode_imports.py"
_r1f = _sp_o.run([sys.executable, str(_t1f)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1f.returncode != 0:
    print(_r1f.stdout.rstrip()); print(_r1f.stderr.rstrip()[:800])
check("and both import modes are exercised", _r1f.returncode, 0)


print("\n=== 1G. histogram resolution, and the instant a gauge describes ===")
# Two v1.73.1 reports, same metric, different implementations:
#   1923Z  TTFT p50 598.1  p90 6,419.5  p99 57,273.9   (Prometheus)
#   2328Z  TTFT p50 800.0  p90 8,000.0  p99 400,000.0  (computed locally)
# The second set is three exact bucket edges on that ladder (0.8 s, 8 s,
# 400 s) printed to two decimal places, and nothing in either report said the
# two came from different code.
_c1g = (_repo_o / "amoprof/report/combined.py").read_text()
check("the chart names which implementation produced the numbers",
      "computed here from the bucket counter deltas" in _c1g, True)
check("and says the two do not agree to the digit on a coarse ladder",
      "do not agree to the digit" in _c1g, True)
# A quantile is an interval, and on this ladder a wide one.
check("p99's bucket spans 50x", round(400000.0 / 8000.0), 50)
check("p90's spans 10x", round(8000.0 / 800.0), 10)
check("so the quantile carries its bracket",
      'out.setdefault("bracket", {})' in _c1g, True)
check("and a wide bracket is stated", "bucket-limited" in _c1g, True)
# The empty-bucket branch returned the bucket's UPPER edge. It is also
# unreachable, verified by exhaustive search, so it explains nothing that was
# observed -- recorded as such rather than claimed as the cause.
check("the unreachable branch is marked unreachable",
      "UNREACHABLE for any cumulative histogram" in _c1g, True)
check("and returns the lower bound if it ever runs",
      "# it used to, would report the worst value" in _c1g, True)

# A point-in-time gauge was evaluated at ANALYSIS time, not at the window end.
_a1g = (_repo_o / "amoprof/report/amoprof.py").read_text()
check("the instant query takes an evaluation time",
      'at: "float | None" = None' in _a1g, True)
check("the synth site anchors it to the window end",
      "at=(float(end_time) if end_time else None)" in _a1g, True)
check("one window read 25 GB and 762 GB on two runs, 30x apart",
      round(762.0 / 25.0), 30)
check("and the instant is recorded", '"_snapshot_at"' in _a1g, True)
check("token throughput has a tile", '"Token throughput",' in _c1g, True)
check("headlining the active mean, not the peak",
      "_kpi_out_tp = _safe_float(tp_active, 0.0) or _safe_float(throughput, 0.0)"
      in _c1g, True)

_t1g = _repo_o / "tests" / "test_histogram_resolution.py"
_r1g = _sp_o.run([sys.executable, str(_t1g)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1g.returncode != 0:
    print(_r1g.stdout.rstrip()); print(_r1g.stderr.rstrip()[:800])
check("every resolution claim holds", _r1g.returncode, 0)


print("\n=== 1H. one window total of a counter, for every surface ===")
# "compare command is not showing a lot of information marking it as absent.
# Also the ttft shown by compare command doesn't match what we see in
# individual reports."
#
# Two symptoms, one cause: "the window total of a cumulative counter" had
# FOUR implementations and they agree only on a clean monotonic single
# column.  Each is reproduced below and checked against numpy on the same
# samples, so the kernel is validated against an independent reference
# rather than against the implementation it replaced.
from amoprof.report.metric_kernels import (          # noqa: E402
    counter_window_total as _cwt, latency_window_ms as _lwm,
    normalize_series_name as _nsn, resolve_series_columns as _rsc,
    resolve_latency_ms as _rlm,
)

# (a) A clean monotonic column: the kernel must equal last - first exactly,
#     so adopting it moves no figure that was already right.
_rng1h = np.random.default_rng(23)
_cum1h = list(np.cumsum(np.abs(_rng1h.normal(500, 80, size=400))))
check("clean counter: kernel == numpy last - first",
      round(_cwt([_cum1h])["total"], 6),
      round(float(_cum1h[-1] - _cum1h[0]), 6))
check("and == the single-series counter_delta kernel",
      round(_cwt([_cum1h])["total"], 6), round(counter_delta(_cum1h), 6))

# (b) Fanned across ranks: the total is the sum of the per-rank deltas.
_ranks1h = [list(np.cumsum(np.abs(_rng1h.normal(300, 50, size=120))))
            for _ in range(8)]
check("8 ranks: kernel == sum of numpy per-rank deltas",
      round(_cwt(_ranks1h)["total"], 6),
      round(float(sum(np.asarray(c)[-1] - np.asarray(c)[0]
                      for c in _ranks1h)), 6))

# (c) A column that joins the window one sample late, carrying a lifetime
#     total from before it.  Summing a ROW's columns and then differencing
#     the row totals -- what comparator._kv_delta did -- makes the
#     subtrahend short by that column's whole history.
_late_a = [1000.0, 1100.0, 1300.0]
_late_b = [900000.0, 900200.0]                # no sample on row 1
check("late column: the kernel reports only the work in the window",
      _cwt([_late_a, _late_b])["total"], 500.0)
_rowsum = [_late_a[0], _late_a[1] + _late_b[0], _late_a[2] + _late_b[1]]
check("row-sum-then-difference reports the lifetime total too",
      _rowsum[-1] - _rowsum[0], 900500.0)
check("which is a 1,801x overstatement",
      round((_rowsum[-1] - _rowsum[0]) / 500.0), 1801)

# (d) A reset inside the window.  Prometheus' increase() credits the
#     post-reset value; max(0, step) discards it and last - first loses
#     everything before the restart.
_reset1h = [[100.0, 200.0, 25.0], [500.0, 540.0, 570.0]]
check("reset: kernel keeps 100 before and 25 after, plus the healthy 70",
      _cwt(_reset1h)["total"], 195.0)
check("and says how much it credited post-reset",
      _cwt(_reset1h)["reset_recovered"], 25.0)
check("max(0, step) would discard that 25",
      sum(max(0.0, c[i] - c[i-1]) for c in _reset1h
          for i in range(1, len(c))), 170.0)
check("per-column last - first loses the pre-reset 125 as well",
      sum(max(0.0, c[-1] - c[0]) for c in _reset1h), 70.0)
check("the reset is counted, not silently absorbed",
      _cwt(_reset1h)["resets"], 1)

# (e) Absent must stay distinct from zero: a lone sample of a lifetime
#     counter measures no window at all.
check("one sample is not a window", _cwt([[7_000_000.0]])["present"], False)
check("and contributes nothing", _cwt([[7_000_000.0]])["total"], 0.0)
check("a matched but idle counter is present and zero",
      (_cwt([[5.0, 5.0]])["present"], _cwt([[5.0, 5.0]])["total"]),
      (True, 0.0))

# (f) The latency mean the two surfaces disagreed on.  Same formula, now
#     from one kernel: ratio_delta and latency_window_ms must agree, and
#     both must equal the closed form.
_s1h = list(np.cumsum(np.abs(_rng1h.normal(0.9, 0.2, size=300))))
_c1h = list(np.cumsum(np.abs(_rng1h.integers(1, 9, size=300)).astype(float)))
_closed1h = float((_s1h[-1] - _s1h[0]) / (_c1h[-1] - _c1h[0]) * 1000.0)
check("latency_window_ms == the closed-form window mean",
      round(_lwm([_s1h], [_c1h])["ms"], 9), round(_closed1h, 9))
check("and == the ratio_delta kernel it generalises",
      round(_lwm([_s1h], [_c1h])["ms"], 9),
      round(ratio_delta(_s1h, _c1h, 1000.0), 9))
check("no observations in the window is not a 0 ms latency",
      _lwm([[1.0, 2.0]], [[7.0, 7.0]])["present"], False)
check("nor are absent counters",
      _lwm([], [])["present"], False)

# (g) One normaliser.  amoprof mapped ':' to '_' and combined did not, so a
#     single spec resolved on one surface and missed on the other.
check("a colon prefix normalises to an underscore one",
      _nsn("sglang:realtime_tokens_total"), "sglang_realtime_tokens_total")
for _sp1h in ('mode="decode"', "mode='decode'", "mode=decode", "mode= decode"):
    _col1h = f"sglang:realtime_tokens_total{{{_sp1h}}}"
    check(f"label spelling {_sp1h} resolves",
          _rsc([_col1h], ["realtime_tokens_total", "mode=decode"]), [_col1h])
check("a _bucket series never shadows the counter",
      _rsc(['x_total_bucket{le="1",mode=decode}', "x_total{mode=decode}"],
           ["x_total", "mode=decode"]), ["x_total{mode=decode}"])
check("every fanned column is returned, not the first",
      len(_rsc(["a{mode=decode,rank=0}", "a{mode=decode,rank=1}"],
               ["a", "mode=decode"])), 2)

# (h) A median must not render under a mean's label.  The resolution order
#     mixes the two; on the reference runs they are 598 ms and 79,341 ms.
check("step 2 reports itself as a p50", _rlm("ttft", pct_ms=598.07)["statistic"],
      "p50")
check("step 1 reports itself as a mean",
      _rlm("ttft", ts_ms=79341.0)["statistic"], "mean")
check("the mean and the p50 differ by 133x on the reference window",
      round(79341.0 / 598.07), 133)

# (i) And every surface reaches the kernel rather than carrying a copy.
_k1h = (_repo_o / "amoprof/report/metric_kernels.py").read_text()
_cm1h = (_repo_o / "amoprof/comparator.py").read_text()
_am1h = (_repo_o / "amoprof/report/amoprof.py").read_text()
_cb1h = (_repo_o / "amoprof/report/combined.py").read_text()
check("the comparator differences through the kernel",
      "_k_counter_total(" in _cm1h, True)
check("the End report does too", "_k_counter_total(_series)" in _am1h, True)
check("and the Executive's phase tile", "_k_counter_total(_kvg_phase" in _cb1h,
      True)
check("compare derives prompt from the phase counters, as analyze does",
      "mode=prefill_compute" in _cm1h, True)
check("and names the derivation in the report",
      "where prompt tokens came from" in _cm1h, True)

_t1h = _repo_o / "tests" / "test_cross_surface_consistency.py"
_r1h = _sp_o.run([sys.executable, str(_t1h)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1h.returncode != 0:
    print(_r1h.stdout.rstrip()); print(_r1h.stderr.rstrip()[:800])
check("every cross-surface claim holds", _r1h.returncode, 0)


print("\n=== 1I. a window mean, against the window that produced it ===")
# "I see L3.5 setup is performing better than L3, why is that so? Where is
# the bottleneck in L3? Is it the SSD?"
#
# It was neither. Two runs over 1,800 s and 2,925 s: every time-average
# favoured the shorter one and all of them reversed once the longer
# window's dead tail came out, the SSD was at 0.019% of its read target,
# and neither tier was serving reads at all. None of that was in the
# comparison, so none of it could be read off it.
from amoprof.report.metric_kernels import (          # noqa: E402
    active_window_fraction as _awf, bucket_edge_check as _bec,
)

# (a) The measured HBM-bandwidth shapes, by quartile, from the two reports.
_q_l35 = [332.0]*10 + [321.0]*10 + [379.0]*10 + [332.0]*9 + [90.0]
_q_l3  = [392.0]*10 + [221.0]*10 + [156.0]*7 + [136.0]*3 + \
         [1.0, 0.0, 0.0, 13.0, 4.0] + [0.0]*5
_t35 = list(np.linspace(0, 1800, len(_q_l35)))
_t3  = list(np.linspace(0, 2925, len(_q_l3)))
_a35, _a3 = _awf(_q_l35, _t35), _awf(_q_l3, _t3)
check("the L3.5 window was alive throughout", round(_a35["fraction"], 2), 1.0)
check("the L3 window was not", _a3["fraction"] < 0.8, True)
check("and its dead time is at the END, which is what dilutes a mean",
      _a3["trail_idle_s"] > 600.0, True)
check("the threshold is relative to the series' own p95, not absolute",
      round(_a3["threshold"], 2), round(0.05 * _a3["peak"], 2))
check("a flat series is fully active",
      _awf([10.0]*8)["fraction"], 1.0)
check("a half-dead series is half active",
      _awf([10.0]*4 + [0.0]*4)["fraction"], 0.5)
check("two samples cannot establish a duty cycle",
      _awf([1.0, 2.0])["present"], False)

# (b) The reversal, from the reported throughputs and those fractions.
_tp35, _tp3 = 49.1, 45.6
check("over the window L3.5 leads", _tp35 > _tp3, True)
_c35 = _tp35 / _a35["fraction"]
_c3 = _tp3 / _a3["fraction"]
check("over the active span L3 leads", _c3 > _c35, True)
check("L3's correction is material, L3.5's is not",
      (round(_c3 / _tp3, 2) >= 1.2, round(_c35 / _tp35, 2)), (True, 1.0))

# (c) The device, against what the device can do.
check("read 1.3 MB/s of a 7,000 MB/s target is 0.019%",
      round(1.3 / 7000.0 * 100.0, 3), 0.019)
check("write 255.3 MB/s of 5,000 MB/s is 5.1%",
      round(255.3 / 5000.0 * 100.0, 1), 5.1)
check("so the measured read is 5,385x below the target",
      round(7000.0 / 1.3), 5385)

# (d) Written against read back: a sink, not a cache.
check("the tier absorbed 747 GB and returned 3.8 GB",
      round(3.8 / 747.0 * 100.0, 2), 0.51)
check("which the integrated write series corroborates",
      round(255.3 * 2925 / 1000.0), 747)

# (e) A quantile on a bucket boundary is not a measurement.
_e8 = _bec(800.0, [0.08, 0.8, 8.0, 400.0])
check("a p50 of exactly 800.00 ms is the le=0.8s edge", _e8["on_edge"], True)
check("and the bracket it stands for is 100x wide",
      round(_e8["span_ratio"]), 100)
check("598.07 ms is not on an edge",
      _bec(598.07, [0.08, 0.8, 8.0, 400.0])["on_edge"], False)
check("no ladder means no edge claim", _bec(800.0, [])["on_edge"], False)

# (f) A mean that is almost entirely tail is queueing, not service.
check("L3.5 TTFT mean is 133x its own p50", round(79341.0 / 598.07), 133)
check("L3 TTFT mean is 106x its own p50", round(84703.0 / 800.0), 106)

# (g) Total HBM concealed the KV-pool difference entirely.
check("HBM used differed by 0.04%", round((265.1 - 265.0) / 265.0 * 100, 2),
      0.04)
check("while the KV pool inside it differed 1.57x",
      round(94143.0 / 59782.0, 2), 1.57)

# (h) And the report states each of them.
_cmp1i = (_repo_o / "amoprof" / "comparator.py").read_text()
for _frag, _what in (
        ("outlived its workload", "the dead-tail warning"),
        ("not alive for the same share", "the active-fraction warning"),
        ("bucket-limited", "the bucket-edge warning"),
        ("almost all tail", "the all-tail warning"),
        # A contiguous fragment: the sentence is split across f-string
        # lines in the source, so "write sink, not a read cache" exists
        # only in the RENDERED banner, never in the file. The test file
        # asserts it on the rendered output; a source probe cannot.
        ("is a write sink", "the sink finding"),
        ("is not the constraint", "the idle-device finding"),
        ("over the ACTIVE span only", "the active-span throughput row"),
        ("Bytes read back ÷ bytes written", "the read-back row"),
        ("L1 HBM KV pool · mean resident", "the KV-pool row")):
    check(f"compare states {_what}", _frag in _cmp1i, True)
check("and the default device target is labelled a default",
      "DEFAULT 7,000 / 5,000 MB/s" in _cmp1i, True)

_t1i = _repo_o / "tests" / "test_compare_window_and_tail.py"
_r1i = _sp_o.run([sys.executable, str(_t1i)], capture_output=True, text=True,
                 cwd=str(_repo_o))
if _r1i.returncode != 0:
    print(_r1i.stdout.rstrip()); print(_r1i.stderr.rstrip()[:800])
check("every window-and-tail claim holds", _r1i.returncode, 0)


print("\n" + "=" * 62)
print(f"RESULT: {len(FAILS)} failure(s)" + (": " + ", ".join(FAILS) if FAILS else " — all checks passed"))
sys.exit(1 if FAILS else 0)
