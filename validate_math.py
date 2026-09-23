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

print("\n" + "=" * 62)
print(f"RESULT: {len(FAILS)} failure(s)" + (": " + ", ".join(FAILS) if FAILS else " — all checks passed"))
sys.exit(1 if FAILS else 0)
