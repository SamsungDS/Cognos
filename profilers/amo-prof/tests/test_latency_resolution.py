#!/usr/bin/env python3
"""analyze and compare must resolve a latency the same way.

Run: python3 tests/test_latency_resolution.py

Reported: the TTFT in a comparison report differs from the TTFT in the
combined report for the same window. Measured on the reference runs:

    L3 local SSD, 2026-10-01 14:57 -> 16:40 UTC
      analyze  11,514 ms    compare  11,525 ms    +0.10%
      TPOT      1,654.3      TPOT      1,655.3    +0.06%

while the L3.5 run read 64,453 / 164.0 in BOTH, identical to the digit. That
asymmetry is the tell: a window delta moves when the sample grid shifts by a
step, a lifetime ratio does not.

The cause is two different resolution orders. The Combined report writes its
down:

    #   1) selected-window Δsum/Δcount counters
    #   2) selected-window percentile-timeseries p50 active mean
    #   3) sglang_summary.json only as last fallback
    # This avoids different runs reusing the same stale summary TTFT/TPOT.

and the comparator did step 3 only -- one `_pick` out of the summary.

0.1% on these runs, but the gap is not bounded at 0.1%. The fetch that
writes the summary falls back to last(sum)/last(count) when the window delta
is zero -- the server's LIFETIME mean -- and labelled the result
"delta_..._sum_over_count" either way, because that method string was a
literal in the dict. So the summary could hold a lifetime average wearing a
window label, invisibly, and a surface that trusts the summary inherits it.
"""
import json
import logging
import pathlib
import re
import shutil
import sys
import tempfile
import html as H

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.report.metric_kernels import resolve_latency_ms  # noqa: E402
from amoprof.comparator import (  # noqa: E402
    RunSpec, build_layer_walk_html, build_suspect_banner, extract_metrics,
)

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    print("\nThe kernel applies one order, and says which step answered")
    r1 = resolve_latency_ms("ttft", ts_ms=11514.0, pct_ms=11000.0,
                            summary_ms=11525.0)
    _check("the window delta wins over everything", r1["ms"], 11514.0)
    _check("step 1", r1["step"], 1)
    _check("and is window-scoped", r1["window_scoped"], True)
    r2 = resolve_latency_ms("ttft", pct_ms=11000.0, summary_ms=11525.0)
    _check("the percentile series is step 2", (r2["ms"], r2["step"]),
           (11000.0, 2))
    _check("also window-scoped", r2["window_scoped"], True)
    r3 = resolve_latency_ms("ttft", summary_ms=11525.0)
    _check("the summary is last", (r3["ms"], r3["step"]), (11525.0, 3))
    _check("and is NOT claimed to be window-scoped",
           r3["window_scoped"], False)
    _check("its method says so", "NOT verified as window-scoped"
           in r3["method"], True)
    _check("even when the summary claims a delta method",
           resolve_latency_ms(
               "ttft", summary_ms=11525.0,
               summary_method="delta_sglang_time_to_first_token_seconds_"
                              "sum_over_count")["window_scoped"], False)
    r0 = resolve_latency_ms("ttft")
    _check("nothing available gives zero, not a guess", r0["ms"], 0.0)
    _check("and step 0", r0["step"], 0)

    print("\nBoth surfaces import that one kernel")
    import amoprof.report.combined as _C
    import amoprof.report.metric_kernels as _K
    _check("combined uses it", _C._k_resolve_lat is _K.resolve_latency_ms,
           True)
    _cmp_src = (pathlib.Path(__file__).resolve().parent.parent / "amoprof"
                / "comparator.py").read_text()
    _check("the comparator does too",
           "resolve_latency_ms as _k_resolve_lat" in _cmp_src, True)
    _check("and no longer reads the summary as its only source",
           'm.ttft_ms          = _sf(_pick(sglang, "server_ttft_ms"'
           in _cmp_src, False)

    print("\nThe comparator now computes the window delta itself")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_lat_"))
    try:
        def _mk(n, counters):
            raw = tmp / n / "raw"
            raw.mkdir(parents=True)
            if counters:
                raw.joinpath("sglang_timeseries.csv").write_text(
                    "time_sec,time_to_first_token_seconds_sum,"
                    "time_to_first_token_seconds_count\n"
                    "0,1000,100\n6180,81098,6958\n")
            raw.joinpath("sglang_summary.json").write_text(json.dumps({
                "server_ttft_ms": 64453.0, "server_e2e_ms": 64453.0,
                "server_itl_ms": 164.0}))
            return extract_metrics(RunSpec(label=n, raw_dir=raw))

        a = _mk("with counters", True)
        b = _mk("summary only", False)
        _expect = (81098 - 1000) / (6958 - 100) * 1000
        _check("it ignores the summary when the delta is computable",
               round(a.ttft_ms, 1), round(_expect, 1))
        _check("which is Δsum ÷ Δcount by hand",
               round(_expect, 1), 11679.5)
        _check("and marks it window-scoped",
               a.latency_window_scoped["ttft"], True)
        _check("a run with no counters falls back to the summary",
               b.ttft_ms, 64453.0)
        _check("and is marked NOT window-scoped",
               b.latency_window_scoped["ttft"], False)

        print("\nAnd it is visible in the report, not just in a field")
        ban = H.unescape(re.sub(r"<[^>]+>", " ", build_suspect_banner([a, b])))
        _check("the banner names the condition",
               "not verified as window-scoped" in ban, True)
        _check("it names the run", "summary only" in ban, True)
        _check("and explains the lifetime fallback",
               "last(sum)/last(count)" in ban and "lifetime mean" in ban, True)
        h = build_layer_walk_html([a, b])
        _row = None
        for m in re.finditer(r"<tr class='chain-row'><td>(.*?)</td>(.*?)</tr>",
                             h, re.S):
            if "how TTFT was resolved" in H.unescape(
                    re.sub(r"<[^>]+>", "", m.group(1))):
                _row = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip()
                        for x in re.findall(r"<td class='num'>(.*?)</td>",
                                            m.group(2), re.S)]
        _check("a provenance row sits beside the number", bool(_row), True)
        _check("naming the delta for the first run",
               _row[0].startswith("Δtime_to_first_token_seconds_sum"), True)
        _check("and the summary for the second",
               "NOT verified as window-scoped" in _row[1], True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nThe fetch records the method it actually used")
    _amo_src = (pathlib.Path(__file__).resolve().parent.parent / "amoprof"
                / "report" / "amoprof.py").read_text()
    _check("the lifetime fallback marks itself",
           "LIFETIME_not_window" in _amo_src, True)
    _check("and the summary's method field is no longer a literal",
           '"server_ttft_ms_method":        _lat_meth["ttft"]' in _amo_src,
           True)
    _check("the old literal is gone",
           '"server_ttft_ms_method":        "delta_sglang_time_to_first'
           in _amo_src, False)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
