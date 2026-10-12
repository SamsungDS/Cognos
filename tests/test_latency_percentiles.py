#!/usr/bin/env python3
"""One quantity, one percentile. And a mean is never a median.

Run: python3 tests/test_latency_percentiles.py

A v1.69.0 report carried three different TTFT p50 values at once:

    62,895 ms   interactive grid, labelled "Median · histogram_quantile/
                percentile timeseries"
     1,755 ms   the TTFT p50/p90/p99 chart (Prometheus histogram)
   190,055 ms   the End report, labelled "Median"

The first was not a percentile at all. Both surfaces resolved it as
``_ttft_p50_ms or _ttft_ms`` and ``m.sess_ttft_p50_ms or m.ttft_ms``: with no
percentile available they showed the MEAN and kept the percentile label.
62,895 ms is exactly what the TTFT mean tile read, and E2E p50 was likewise
exactly the E2E mean. A tile that says p50 and shows a mean is worse than an
empty one, because beside the mean tile it reads as corroboration.

Two further things the same report got wrong about percentiles:

  * TTFT p99 read "400,000.00 ms" and TPOT p90 and p99 both read "8,000.0" --
    bucket boundaries, not latencies. A Prometheus histogram's top bucket is
    open-ended, so a quantile landing in it is reported as that bucket's
    floor: a lower bound. The chart said so in a general footnote while
    printing the figures as plain values.
  * the mean-beside-p50 comparison, which exists precisely to explain a gap
    like 62,895 against 1,755, silently vanished: it read the mean from
    sglang_summary.json keys that a Prometheus-only run does not have.

And the part that is NOT a bug, pinned here so it is not "fixed" later: a mean
of 62,895 ms is consistent with that percentile set. The percentiles put a
floor of about 24,045 ms on the mean and no ceiling at all, because the top
band is open. The tiles and the charts never contradicted each other; the
report simply never showed the two together.
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

# Every figure from that report.
TTFT_MEAN, TTFT_P50_HIST, TTFT_P50_SESS = 62895.0, 1755.10, 190055.0
TTFT_P90, TTFT_P99 = 214925.37, 400000.00
TPOT_MEAN, TPOT_P50_HIST = 3667.1, 133.0
TPOT_P90, TPOT_P99 = 8000.0, 8000.0
E2E_MEAN, E2E_P50_SHOWN = 129140.0, 129140.0


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    from amoprof.report.metric_kernels import (
        resolve_latency_percentile as _rlp)

    print("\nThe p50 that was the mean")
    _check("the interactive p50 equalled the mean exactly",
           TTFT_MEAN == 62895.0 and E2E_P50_SHOWN == E2E_MEAN, True)
    _check("while the histogram put p50 at 1,755.10", TTFT_P50_HIST, 1755.10)
    _check("which is 35.8x lower than the figure shown as p50",
           round(TTFT_MEAN / TTFT_P50_HIST, 1), 35.8)
    _check("and a third surface said 190,055", TTFT_P50_SESS, 190055.0)
    _check("so one report held three TTFT p50 values",
           len({TTFT_MEAN, TTFT_P50_HIST, TTFT_P50_SESS}), 3)

    print("\nThe kernel refuses to substitute a mean for a percentile")
    r = _rlp("ttft", 0.5, mean_ms=TTFT_MEAN)
    _check("no figure is returned", r["ms"], 0.0)
    _check("the step records that nothing resolved", r["step"], 0)
    _check("the mean it declined is named",
           r["refused_mean_ms"], TTFT_MEAN)
    _check("and the method says so in words",
           "is not substituted for it here" in r["method"], True)
    _check("with the mean's value, so a reader sees what was rejected",
           "62,895" in r["method"], True)

    print("\nResolution order, highest-quality source first")
    _check("a histogram quantile wins",
           _rlp("ttft", 0.5, histogram_ms=1755.1, session_ms=190055.0,
                pct_ts_ms=1.0, summary_ms=2.0)["step"], 1)
    _check("then per-request session stats",
           _rlp("ttft", 0.5, session_ms=190055.0, pct_ts_ms=1.0,
                summary_ms=2.0)["step"], 2)
    _check("then the percentile timeseries",
           _rlp("ttft", 0.5, pct_ts_ms=1.0, summary_ms=2.0)["step"], 3)
    _check("then the summary, marked unverified",
           _rlp("ttft", 0.5, summary_ms=2.0)["step"], 4)
    _check("and the summary says it is not verified window-scoped",
           "NOT verified as window-scoped"
           in _rlp("ttft", 0.5, summary_ms=2.0)["method"], True)
    _check("the method names the metric and the quantile",
           "histogram_quantile(0.5" in
           _rlp("ttft", 0.5, histogram_ms=1.0)["method"], True)
    _check("and the quantile label follows the request",
           "p99" in _rlp("ttft", 0.99, session_ms=5.0)["method"], True)

    print("\nA censored reading is flagged, not published as a value")
    c = _rlp("ttft", 0.99, histogram_ms=TTFT_P99, top_bucket_ms=TTFT_P99)
    _check("p99 at the open bucket's floor is censored", c["censored"], True)
    _check("a quantile below it is not",
           _rlp("ttft", 0.5, histogram_ms=TTFT_P50_HIST,
                top_bucket_ms=TTFT_P99)["censored"], False)
    _check("TPOT p90 and p99 were the same bucket boundary",
           TPOT_P90 == TPOT_P99 == 8000.0, True)
    _check("with no top bucket given, nothing is called censored",
           _rlp("ttft", 0.99, histogram_ms=TTFT_P99)["censored"], False)

    print("\nNeither surface substitutes a mean any more")
    def _code_only(_path):
        """Statements only. A comment quoting the pattern it removed satisfies
        a plain substring probe -- which is how the first version of this test
        passed while three substitution sites were still live."""
        return "\n".join(
            _l.split("#")[0] if not _l.lstrip().startswith("#") else ""
            for _l in (_ROOT / "amoprof" / "report" / _path).read_text()
            .splitlines())

    iv = _code_only("interactive.py")
    a = _code_only("amoprof.py")
    _check("interactive.py drops the `p50 or mean` chain",
           "_ttft_p50_ms or _ttft_ms_kpi" in iv, False)
    _check("for TPOT too", "_itl_p50_ms or _itl_ms_kpi" in iv, False)
    _check("and E2E", "_e2e_p50_ms or _e2e_ms_kpi" in iv, False)
    _check("resolving through the kernel instead",
           "_k_resolve_pct(" in iv, True)
    _check("and showing an em dash when there is no percentile",
           '_kpi_tile(_label, "\\u2014", "", _r["method"])' in iv
           or '"—", "", _r["method"]' in iv, True)
    _check("amoprof.py drops `sess_ttft_p50_ms or m.ttft_ms`",
           "m.sess_ttft_p50_ms or m.ttft_ms" in a, False)
    _check("and `sess_tpot_p50_ms or m.tpot_ms`",
           "m.sess_tpot_p50_ms or m.tpot_ms" in a, False)
    # The symbol, not the spelling: pinning an inline package-absolute
    # import is what kept one in place until it broke script mode.
    _check("using the same kernel",
           "resolve_latency_percentile as _k_resolve_pct" in a, True)
    _check("through the module-level guard, not inline",
           a.count("resolve_latency_percentile as _k_resolve_pct"), 2)
    _check("and labelling the card Median only when it is one",
           '_p50_ttft["method"] if _p50_ttft["ms"] <= 0 else "Median"' in a,
           True)
    # Four sites held the same substitution; a probe that found two of them
    # and a comment quoting the pattern reported the job done.
    _check("no `p50 or mean` chain survives anywhere in either file",
           [_pat for _pat in ("sess_ttft_p50_ms or m.ttft_ms",
                              "sess_tpot_p50_ms or m.tpot_ms",
                              "or m.ttft_ms or 0", "or m.tpot_ms or 0",
                              "_ttft_p50_ms or _ttft_ms_kpi",
                              "_itl_p50_ms or _itl_ms_kpi",
                              "_e2e_p50_ms or _e2e_ms_kpi")
            if _pat in a or _pat in iv], [])
    _check("the synthesised E2E percentiles require their own inputs",
           "_have_all_pct" in a, True)
    # The guard has to be USED, not merely defined. amoprof.py imports
    # matplotlib, absent here, so this is a source probe: without it, a run
    # with a TTFT p90 but no TPOT p90 writes a p90 whose decode term is zero.
    _check("and the guard gates the synthesis",
           "if _e2e_flat and _have_all_pct:" in a, True)
    _check("including the output-token percentiles they multiply by",
           "sess_output_tok_p99" in a, True)
    _check("and the prose rows no longer print a mean under a p50 heading",
           a.count("the mean is not substituted") >= 2, True)

    print("\nThe mean and the percentiles are shown together")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_pct_"))
    try:
        sys.path.insert(0, str(_ROOT / "tests"))
        from test_tier_residency_tiles import _make_run
        from amoprof.report.combined import build_executive_summary_html as _b

        # A TTFT histogram shaped like the report's: most requests fast, a
        # long tail, and 1% past the last finite bucket.
        _les = [0.5, 1, 2, 5, 10, 30, 60, 120, 200, 300, 400, float("inf")]
        _cum = [0.02, 0.20, 0.52, 0.60, 0.64, 0.70, 0.76, 0.82, 0.86, 0.89,
                0.99, 1.00]
        _n_obs = 2060

        def _mk(_dir):
            _raw = _make_run(_dir)
            _cols = (["time_sec"]
                     + [f"sglang_time_to_first_token_seconds_bucket[le={le}]"
                        for le in _les]
                     + ["sglang_time_to_first_token_seconds_sum",
                        "sglang_time_to_first_token_seconds_count"])
            _rows = []
            for _i in range(12):
                _f = _i / 11.0
                _rows.append([_i * 300.0]
                             + [int(_c * _n_obs * _f) for _c in _cum]
                             + [TTFT_MEAN / 1000.0 * _n_obs * _f,
                                int(_n_obs * _f)])
            _raw.joinpath("sglang_timeseries.csv").write_text(
                ",".join(_cols) + "\n"
                + "\n".join(",".join(str(v) for v in _r) for _r in _rows)
                + "\n")
            return _raw

        _txt = re.sub(r"\s+", " ", re.sub(
            r"<[^>]+>", " ", _H.unescape(_b(_mk(tmp / "run"),
                                           run_label="p"))))
        _row = re.search(r"TTFT p50 ([^·]+)· p90 ([^·]+)· p99 (.{0,220})",
                         _txt)
        _check("the percentile row renders", _row is not None, True)
        _check("with the mean beside it, on a run with no summary keys",
               "mean 62,895.0 ms" in _txt, True)
        _check("and the ratio that explains the gap",
               re.search(r"x p50 —", _txt) is not None, True)
        _check("the censored quantile is marked",
               "censored" in _row.group(3), True)
        _check("as a lower bound rather than a measurement",
               "not a measurement" in _txt, True)
        _check("naming the bucket it fell above",
               "open-ended bucket above" in _txt, True)
        # p50 is nowhere near the top bucket and must stay unmarked.
        _check("a measured quantile is not marked",
               "censored" in _row.group(1), False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nThe helper reports WHICH quantiles it censored")
    from amoprof.report.combined import (
        _amoprof_histogram_window_percentiles as _hwp)
    _check("it records them by name",
           'out.setdefault("censored", []).append' in
           (_ROOT / "amoprof" / "report" / "combined.py").read_text(), True)
    # Exactness matters: a quantile can land exactly ON the last finite
    # boundary without being censored, and a threshold test would call that a
    # lower bound. The fixture's p90 does precisely this.
    _check("so a quantile sitting on the boundary is not called censored",
           'if _q in _cens_qs:' in
           (_ROOT / "amoprof" / "report" / "combined.py").read_text(), True)

    print("\nAnd the mean never contradicted the percentiles")
    # Each band contributes at least its lower edge. The top band is open, so
    # there is a floor on the mean and no ceiling: the percentiles cannot
    # contradict a mean above the floor.
    _floor = (0.50 * 0.0 + 0.40 * TTFT_P50_HIST
              + 0.09 * TTFT_P90 + 0.01 * TTFT_P99)
    _check("the percentiles put the mean at 24,045 ms or above",
           round(_floor), 24045)
    _check("and 62,895 is above it", TTFT_MEAN > _floor, True)
    _check("so the two are consistent, not contradictory",
           TTFT_MEAN >= _floor, True)
    _check("the same holds for TPOT",
           TPOT_MEAN >= (0.40 * TPOT_P50_HIST + 0.09 * TPOT_P90
                         + 0.01 * TPOT_P99), True)
    # And a mean BELOW the floor would be a real contradiction, worth saying.
    _check("a mean below the floor would be impossible",
           1000.0 < _floor, True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
