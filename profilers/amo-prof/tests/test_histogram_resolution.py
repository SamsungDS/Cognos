#!/usr/bin/env python3
"""A histogram quantile is an interval, not a two-decimal measurement.

Run: python3 tests/test_histogram_resolution.py

A v1.73.1 report printed, from a TTFT histogram with 5,955 observations:

    TTFT p50:    800.00 ms
    TTFT p90:  8,000.00 ms
    TTFT p99: 400,000.00 ms

Three exact numbers, two decimal places each, and all three are SGLang bucket
edges on that deployment's ladder (0.8 s, 8 s, 400 s). The TPOT histogram in
the same report, with 108,874 observations over a finer ladder, read 32.40 /
919.16 / 1,970.24 -- interpolated, and plainly so.

Two defects, found together:

1. When the bucket a quantile landed in gained no observations in the window,
   the code returned that bucket's UPPER edge. On this ladder that turns a
   quantile whose observations all sit at or below 0.8 s into "8,000.00 ms".
   It reports the worst value a bucket can hold as though it were measured,
   and it rounds only one way: up. The lower edge is the bound the data
   supports.

2. Even when the interpolation is right, the output implied precision the
   histogram cannot have. p99 inside a bucket spanning 8 s to 400 s is an
   estimate in a range 50x wide. The quantile now carries its bracket, and a
   wide bracket is stated rather than rounded away.

Also here: the token-throughput tile, and the instant a point-in-time gauge
describes. `_prom_query_instant` sent no `time` parameter, so every scalar
synthesised from Prometheus -- df fullness, SMART counters, device capacity --
was evaluated at ANALYSIS time rather than at the window end. The same
30-minute window reported the HiCache filesystem at 25 GB on one run and 762
GB on a later one; both were just `df` at the moment the analysis ran.
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

# The deployment's ladder, in seconds, and that report's observation count.
LES = [0.08, 0.8, 8.0, 400.0, float("inf")]
N_OBS = 5955


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _hist(base, cum_fracs, les=LES, n=N_OBS):
    """A cumulative Prometheus histogram as the fetch writes it to CSV."""
    base.mkdir(parents=True, exist_ok=True)
    p = base / "sglang_timeseries.csv"
    cols = ["time_sec"] + [
        f'sglang_time_to_first_token_seconds_bucket'
        f'[le="{"+Inf" if le == float("inf") else le}"]' for le in les]
    rows = [",".join(["0.0"] + ["0"] * len(les))]
    for i in range(1, 12):
        f = i / 11.0
        rows.append(",".join([str(i * 150.0)]
                             + [str(int(c * n * f)) for c in cum_fracs]))
    p.write_text(",".join(cols) + "\n" + "\n".join(rows) + "\n")
    return p


def main() -> int:
    from amoprof.report.combined import (
        _amoprof_histogram_window_percentiles as _H_q)

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_hist_"))
    try:
        print("\nAn empty bucket no longer reports its upper edge")
        # Everything at or below 0.8 s; the buckets above it gain nothing.
        # p50/p90/p99 all fall in buckets with no observations, which is the
        # branch that used to return `hi`.
        _r = _H_q(_hist(tmp / "flat", [0.0, 1.0, 1.0, 1.0, 1.0]),
                  "time_to_first_token_seconds", (0.5, 0.9, 0.99), 1000.0)
        # Interpolated inside (80, 800] ms, which is where the observations
        # are: 80 + 720q for q = 0.5 / 0.9 / 0.99.
        _check("the quantiles interpolate inside the bucket holding the data",
               [round(_r["p50"], 1), round(_r["p90"], 1), round(_r["p99"], 1)],
               [440.0, 728.0, 792.8])
        _check("which is 80 + 720q, as linear interpolation requires",
               [round(80.0 + 720.0 * _q, 1) for _q in (0.5, 0.9, 0.99)],
               [440.0, 728.0, 792.8])
        _check("not at 8,000 ms, which the upper edge would have given",
               8000.0 in (_r["p50"], _r["p90"], _r["p99"]), False)
        _check("and all three are inside the bucket that holds the data",
               all(80.0 <= _r[k] <= 800.0 for k in ("p50", "p90", "p99")),
               True)

        print("\nEvery quantile carries the bucket it was interpolated in")
        _r2 = _H_q(_hist(tmp / "spread", [0.10, 0.52, 0.91, 0.995, 1.00]),
                   "time_to_first_token_seconds", (0.5, 0.9, 0.99), 1000.0)
        _brk = _r2.get("bracket") or {}
        _check("the bracket is reported", sorted(_brk), ["p50", "p90", "p99"])
        _check("p50's bucket is (80, 800] ms", _brk["p50"], (80.0, 800.0))
        _check("p90's is (800, 8000] ms", _brk["p90"], (800.0, 8000.0))
        _check("p99's is (8000, 400000] ms", _brk["p99"],
               (8000.0, 400000.0))
        _check("and each value lies inside its own bracket",
               all(_brk[k][0] <= _r2[k] <= _brk[k][1]
                   for k in ("p50", "p90", "p99")), True)
        # The width is the point: p99's bucket spans a factor of 50.
        _check("p99's bucket spans 50x", round(400000.0 / 8000.0), 50)
        _check("so two decimal places on it are not meaningful",
               _brk["p99"][1] / _brk["p99"][0] > 3.0, True)

        print("\nA tight bucket is not labelled bucket-limited")
        # The threshold has to discriminate, or every quantile carries the
        # caveat and the caveat stops meaning anything. A fine ladder where
        # each bucket is 25% wider than the last must come out clean.
        _fine = [round(0.5 * (1.25 ** _i), 6) for _i in range(12)] + [
            float("inf")]
        _fcum = [min(1.0, 0.02 + 0.09 * _i) for _i in range(12)] + [1.0]
        _hf = _hist(tmp / "fine", _fcum, les=_fine)
        _rf = _H_q(_hf, "time_to_first_token_seconds", (0.5, 0.9), 1000.0)
        _bf = (_rf.get("bracket") or {})
        _check("a fine ladder still reports brackets", len(_bf) >= 2, True)
        # `_bk` not `_b`: `_b` is this file's alias for
        # build_executive_summary_html, and a comprehension variable of the
        # same name shadowed it two lines later. The same shadowing shape that
        # bit amoprof.py three times, now in a test of it.
        _check("but each is under 3x wide, so none is called bucket-limited",
               all(_bk[1] / max(_bk[0], 1e-9) < 3.0
                   for _bk in _bf.values() if _bk[1] != float("inf")), True)

        print("\nThe open-ended bucket is still censoring, not bracketing")
        _r3 = _H_q(_hist(tmp / "inf", [0.0, 0.0, 0.0, 0.0, 1.0]),
                   "time_to_first_token_seconds", (0.99,), 1000.0)
        _check("a quantile past the last finite edge is censored",
               _r3.get("censored"), ["p99"])
        _check("reported at the floor, not the (infinite) ceiling",
               _r3["p99"], 400000.0)

        print("\nThe chart states a wide bracket instead of rounding it away")
        sys.path.insert(0, str(_ROOT / "tests"))
        from test_tier_residency_tiles import _make_run, _tiles
        from amoprof.report.combined import (
            build_executive_summary_html as _b)

        def _run(_dir, *, cum=(0.10, 0.52, 0.91, 0.995, 1.00),
                 gen_tp=41.2, prompt_tok=4_500_000, les=None, summary=None):
            _raw = _make_run(_dir)
            _les_r = list(les) if les else LES
            if summary:
                _raw.joinpath("sglang_summary.json").write_text(
                    json.dumps(summary))
            _cols = (["time_sec"]
                     + [f'sglang_time_to_first_token_seconds_bucket'
                        f'[le="{"+Inf" if l == float("inf") else l}"]'
                        for l in _les_r]
                     + ["sglang_time_to_first_token_seconds_sum",
                        "sglang_time_to_first_token_seconds_count",
                        "sglang_gen_throughput",
                        "sglang_prompt_tokens_total"])
            _rows = []
            for _i in range(12):
                _f = _i / 11.0
                _rows.append([_i * 150.0]
                             + [int(_c * N_OBS * _f) for _c in
                                (list(cum) if len(cum) == len(_les_r)
                                 else [min(1.0, 0.02 + 0.09 * _j)
                                       for _j in range(len(_les_r) - 1)]
                                     + [1.0])]
                             + [84.70 * N_OBS * _f, int(N_OBS * _f),
                                0.0 if _i % 4 == 3 else gen_tp,
                                int(prompt_tok * _f)])
            _raw.joinpath("sglang_timeseries.csv").write_text(
                ",".join(_cols) + "\n"
                + "\n".join(",".join(str(v) for v in _r) for _r in _rows)
                + "\n")
            return _raw

        _html = _H.unescape(_b(_run(tmp / "chart"), run_label="c"))
        _txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html))
        _row = re.search(r"TTFT p50 (.{0,900})", _txt)
        _check("the chart row renders", _row is not None, True)
        _rowtxt = _row.group(1) if _row else ""
        _check("p50 says which bucket it came from",
               "between 80 ms and 800 ms" in _rowtxt, True)
        _check("p90 too", "between 800 ms and 8000 ms" in _rowtxt, True)
        _check("and p99", "between 8000 ms and 400000 ms" in _rowtxt,
               True)
        _check("each calls itself an interpolation, not a measured value",
               _rowtxt.count("not a measured value"), 3)
        _check("and no quantile is printed as a bare bucket edge",
               re.search(r"p90 8,000\.0 ms ·", _rowtxt) is not None, False)

        print("\nThe caveat discriminates: a fine ladder gets none")
        _fine_txt = re.sub(r"\s+", " ", re.sub(
            r"<[^>]+>", " ", _H.unescape(
                _b(_run(tmp / "finechart", les=_fine), run_label="f"))))
        _fm = re.search(r"TTFT p50 (.{0,600})", _fine_txt)
        _check("the fine-ladder chart renders", _fm is not None, True)
        _check("and carries no bucket-limited caveat",
               "bucket-limited" in (_fm.group(1) if _fm else ""), False)
        _check("while the coarse ladder does",
               _rowtxt.count("bucket-limited"), 3)

        print("\nThe chart names which implementation produced the numbers")
        _check("the local path says so",
               "computed here from the bucket counter deltas" in _txt, True)
        _check("and that the two implementations differ on a coarse ladder",
               "do not agree to the digit" in _txt, True)
        # With the summary's own percentiles present, the override fires and
        # the subtitle must say Prometheus instead -- the difference between
        # the two reports that prompted this.
        _ovr = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _H.unescape(
            _b(_run(tmp / "override",
                    summary={"server_ttft_p50_ms": 598.1,
                             "server_ttft_p90_ms": 6419.5,
                             "server_ttft_p99_ms": 57273.9}),
              run_label="o"))))
        _check("the override path names Prometheus",
               "Prometheus histogram_quantile over the range" in _ovr, True)
        _check("and does not claim the local computation",
               "computed here from the bucket counter deltas" in _ovr, False)
        _check("its values are the summary's, not the local ones",
               "598 ms" in _ovr, True)

        print("\nThe token throughput tile")
        _tl = _tiles(_b(_run(tmp / "tp"), run_label="t"))
        _check("the tile exists", "Token throughput" in _tl, True)
        _check("showing both directions", _tl["Token throughput"][0],
               "41.2 out / 2,727 in tok/s")
        _check("the decode figure is the active mean, idle excluded",
               "active mean of sglang_gen_throughput (idle samples excluded)"
               in _tl["Token throughput"][1], True)
        # The fixture idles one sample in four, so the active mean is the
        # non-zero value and a plain mean would be a quarter lower. Headlining
        # the summary's peak-ish figure instead would also change this.
        _check("so the headline is the active value, not a windowed mean",
               _tl["Token throughput"][0].startswith("41.2 out"), True)
        _check("which a plain mean over all samples would understate",
               round(41.2 * 9 / 12, 1), 30.9)
        # And the summary's peak-ish figure must not be the headline. With
        # both present and different, preferring the wrong one is visible.
        _tlp = _tiles(_b(_run(tmp / "peak",
                              # gen_tp_peak is the first key `throughput`
                              # picks and is not in tp_active's list, so the
                              # two differ and the preference is observable.
                              summary={"gen_tp_active_mean": 41.2,
                                       "gen_tp_peak": 912.0}),
                         run_label="p"))
        _check("the active mean is headlined, not the peak",
               _tlp["Token throughput"][0].startswith("41.2 out"), True)
        _check("and the peak is shown beside it instead",
               "peak 912.0 tok/s" in _tlp["Token throughput"][1], True)
        _check("the p50 is beside it",
               "p50 41.2 tok/s" in _tl["Token throughput"][1], True)
        _check("the prefill method is named",
               "prefill delta_sglang_prompt_tokens_total" in
               _tl["Token throughput"][1], True)
        _check("and the ratio between the two directions is stated",
               "prompt tokens arrive per token generated"
               in _tl["Token throughput"][1], True)
        # A window with no throughput signal at all must say so, not show 0.
        _tl2 = _tiles(_b(_run(tmp / "notp", gen_tp=0.0, prompt_tok=0),
                         run_label="n"))
        _check("with neither signal it says not collected",
               _tl2["Token throughput"][0], "not collected")
        _check("naming both inputs it needs",
               "sglang_gen_throughput" in _tl2["Token throughput"][1]
               and "prompt_tokens_total" in _tl2["Token throughput"][1], True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nA point-in-time gauge is evaluated at the window end")
    a = (_ROOT / "amoprof" / "report" / "amoprof.py").read_text()
    _check("the instant query takes an evaluation time",
           'at: "float | None" = None' in a, True)
    _check("and passes it to Prometheus",
           '_params["time"] = f"{float(at):.3f}"' in a, True)
    _check("the service summaries aggregate the whole window instead",
           "_aggregate_service_cycles(" in a, True)
    c = (_ROOT / "amoprof" / "report" / "combined.py").read_text()
    _check("which the L3 tile states",
           'f" taken at {_l3_snap_at}"' in c, True)
    # The two readings of one window that prompted this.
    _check("25 GB and 762 GB for one window differ 30x",
           round(762.0 / 25.0), 30)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
