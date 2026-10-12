#!/usr/bin/env python3
"""One window, one number: `compare` must agree with `analyze`.

Run: python3.12 tests/test_cross_surface_consistency.py

Reported:

    compare command is not showing a lot of information marking it as
    absent. Also the ttft shown by compare command doesn't match what we
    see in individual reports.

Two symptoms, one cause, and this is the fourth time in this class:

    v1.64.0  latency means     compare read sglang_summary.json only
    v1.68.0  KV bytes/token    interactive called the resolver without config
    v1.72.0  percentiles       a mean was published under a p50 label
    v1.75.0  this              compare never learned the phase counters

Each was the same failure in a different field, so the fix is not another
field. "The window total of a cumulative counter" had FOUR implementations:

    metric_kernels.counter_delta   max(0, last - first), one series
    amoprof._delta_sum_metric      sum_col max(0, last_col - first_col)
    combined._kvg_counter_delta    sum_steps max(0, step), ONE column
    comparator._kv_delta           max(0, (sum_col last) - (sum_col first))

They agree only on a clean monotonic single column, and real runs are not
that. This file pins the three fixtures where they disagree, checks the
kernel against hand arithmetic on each, and then checks that each surface
reaches the kernel rather than carrying its own copy.

The three fixtures, and which implementation each one catches:

  late-joining column   a scrape target whose first sample lands on row 2 --
                        routine after a restart or a rank coming up. Summing
                        a row's columns and then differencing the row totals
                        makes the subtrahend short by that column's entire
                        lifetime value. Catches comparator._kv_delta.

  reset in one column   a server restart inside the window. Clamping the
                        AGGREGATE at zero drags healthy columns down with
                        the one that reset; clamping last - first per column
                        loses every observation before the restart.
                        Catches comparator._kv_delta and _delta_sum_metric.

  fanned counter        one series per rank. Taking the first column reports
                        one rank's share as the total.
                        Catches combined's phase reader.

Needs no Prometheus and no pandas: the kernel is pure and the comparator
imports without either, so both run here. report/amoprof.py cannot be
imported in this sandbox (no numpy/pandas for 3.12), so its half is pinned
by comment-stripped source probes -- a comment satisfying a probe has
happened three times in this project, so the probes read code only.
"""
import logging
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.comparator import (  # noqa: E402
    RunSpec, _kv_delta, _read_series, extract_metrics,
)
from amoprof.report.metric_kernels import (  # noqa: E402
    counter_window_total, latency_window_ms, normalize_series_name,
    resolve_latency_ms, resolve_series_columns,
)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _close(name, got, want, tol=1e-6):
    ok = got is not None and abs(float(got) - float(want)) <= tol
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r} (+/-{tol})")


def _code_only(path):
    """The source with comments and docstrings blanked, layout preserved.

    Three times in this project a source probe was satisfied by a comment
    that described the thing instead of code that did it, so the probes here
    never see prose. The spans are blanked IN PLACE rather than re-joined
    from tokens: the first version of this helper joined tokens with newlines
    and `_k_counter_total(` stopped appearing as a substring anywhere, so six
    probes failed on code that was in fact correct. Blanking keeps every
    other character at its original offset.
    """
    import io
    import tokenize
    src = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines(keepends=True)
    # Offset of the first character of each 1-based line.
    starts, _acc = [0, 0], 0
    for _ln in lines:
        _acc += len(_ln)
        starts.append(_acc)
    buf = list(src)

    def _blank(a_row, a_col, b_row, b_col):
        a = starts[a_row] + a_col
        b = starts[b_row] + b_col
        for i in range(max(0, a), min(len(buf), b)):
            if buf[i] != "\n":
                buf[i] = " "

    try:
        prev = None
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                _blank(tok.start[0], tok.start[1], tok.end[0], tok.end[1])
            elif tok.type == tokenize.STRING and prev in (
                    tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, None):
                _blank(tok.start[0], tok.start[1], tok.end[0], tok.end[1])
            if tok.type != tokenize.NL:
                prev = tok.type
    except Exception:
        return src
    return "".join(buf)


def _func_src(code, name):
    """The body of `def name(` up to the next top-or-nested-level def."""
    i = code.find(f"def {name}(")
    if i < 0:
        return ""
    j = code.find("def ", i + 4)
    return code[i:j if j > 0 else len(code)]


# ── The old implementations, kept verbatim so the fixtures can discriminate ──

def _old_comparator_delta(rows, cols):
    """Sum each row's columns, then difference the row totals."""
    vals = []
    for r in rows:
        tot, seen = 0.0, False
        for c in cols:
            v = r.get(c)
            if v is not None and v == v:
                tot += v
                seen = True
        if seen:
            vals.append(tot)
    if len(vals) < 2:
        return None
    d = vals[-1] - vals[0]
    return d if d >= 0 else 0.0


def _old_amoprof_delta(series):
    """Per column, max(0, last - first); then sum."""
    total = 0.0
    for col in series:
        v = [x for x in col if x == x]
        if len(v) >= 2:
            d = v[-1] - v[0]
            if d > 0:
                total += d
    return total


def _write_csv(path, header, rows):
    """Write a fixture through csv.writer, not by joining on commas.

    A Prometheus column name carries its label set -- `{mode="decode",
    rank="0"}` -- so it contains both a comma and a quote. Joining the header
    on commas split one column into two and every probe downstream resolved
    nothing, which looked exactly like the bug under test.
    """
    import csv as _c
    with pathlib.Path(path).open("w", encoding="utf-8", newline="") as fh:
        w = _c.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if x is None else x for x in r])


def main() -> int:
    _P = "sglang:realtime_tokens_total"

    print("\nFixture 1 — a column that joins the window on row 2")
    # Rank 0 is scraped from the start; rank 1's exporter comes up one tick
    # late, carrying a lifetime total of 900,000 tokens from before the
    # window. Real work in the window: rank 0 moves 300, rank 1 moves 200.
    _cols = [f'{_P}{{mode="decode",rank="0"}}', f'{_P}{{mode="decode",rank="1"}}']
    _rows = [{_cols[0]: 1000.0, _cols[1]: None},
             {_cols[0]: 1100.0, _cols[1]: 900000.0},
             {_cols[0]: 1300.0, _cols[1]: 900200.0}]
    _series = [[1000.0, 1100.0, 1300.0], [900000.0, 900200.0]]
    _close("the kernel reports the 500 tokens actually moved",
           counter_window_total(_series)["total"], 500.0)
    _close("row-sum-then-difference reports rank 1's whole history too",
           _old_comparator_delta(_rows, _cols), 900500.0)
    _check("which is the 1,801x error the two surfaces disagreed by",
           round(_old_comparator_delta(_rows, _cols) /
                 counter_window_total(_series)["total"]), 1801)

    print("\n  and end-to-end, through the comparator's own reader")
    _tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof-xsurf-"))
    try:
        _raw = _tmp / "r1"
        _raw.mkdir()
        _write_csv(_raw / "sglang_timeseries.csv",
                   ["time_sec"] + _cols,
                   [[0.0, 1000.0, None], [10.0, 1100.0, 900000.0],
                    [20.0, 1300.0, 900200.0]])
        _close("_kv_delta no longer inflates by the late column's history",
               _kv_delta(_raw, ["realtime_tokens_total"]), 500.0)
        _s, _src = _read_series(_raw, ["realtime_tokens_total", "mode=decode"])
        _check("and it resolved BOTH fanned columns, not the first",
               len(_s), 2)
        _check("naming the file it read them from",
               "sglang_timeseries.csv" in _src, True)

        print("\n  the one-parse-per-file cache must not serve a stale run")
        # The reader is called roughly 150 times per run and
        # sglang_timeseries.csv is tens of megabytes on a long one, so the
        # parse is remembered. The key carries mtime and size, because a
        # re-collected directory at the same path is a different run.
        import time as _time
        _write_csv(_raw / "sglang_timeseries.csv",
                   ["time_sec", f'{_P}{{mode="decode"}}'],
                   [[0.0, 100.0], [10.0, 200.0]])
        _close("the first read differences the file on disk",
               _kv_delta(_raw, ["realtime_tokens_total"]), 100.0)
        _time.sleep(0.01)
        _write_csv(_raw / "sglang_timeseries.csv",
                   ["time_sec", f'{_P}{{mode="decode"}}'],
                   [[0.0, 100.0], [10.0, 500.0]])
        _close("and a rewritten file is re-parsed, not served from cache",
               _kv_delta(_raw, ["realtime_tokens_total"]), 400.0)

        print("\nFixture 2 — a server restart inside the window")
        # One column resets; the other is healthy throughout. 40 + 60 = 100
        # tokens moved before the reset, 25 after, and the healthy column
        # moved 70.
        _rc = [f'{_P}{{mode="decode",rank="0"}}', f'{_P}{{mode="decode",rank="1"}}']
        _raw2 = _tmp / "r2"
        _raw2.mkdir()
        _write_csv(_raw2 / "sglang_timeseries.csv",
                   ["time_sec"] + _rc,
                   [[0.0, 100.0, 500.0], [10.0, 200.0, 540.0],
                    [20.0, 25.0, 570.0]])
        _reset_series = [[100.0, 200.0, 25.0], [500.0, 540.0, 570.0]]
        _close("the kernel keeps the 100 before the reset and the 25 after",
               counter_window_total(_reset_series)["total"], 195.0)
        _check("and records that a reset was spanned",
               counter_window_total(_reset_series)["resets"], 1)
        _close("naming how much of the total the reset accounts for",
               counter_window_total(_reset_series)["reset_recovered"], 25.0)
        _close("discarding the step instead would lose that 25",
               sum(max(0.0, c[i] - c[i - 1]) for c in _reset_series
                   for i in range(1, len(c))), 170.0)
        _close("per-column last-minus-first loses the pre-reset 125",
               _old_amoprof_delta(_reset_series), 70.0)
        _close("row-sum-then-difference loses all of it, clamping to zero",
               _old_comparator_delta(
                   [{_rc[0]: 100.0, _rc[1]: 500.0},
                    {_rc[0]: 200.0, _rc[1]: 540.0},
                    {_rc[0]: 25.0, _rc[1]: 570.0}], _rc), 0.0)
        _close("and _kv_delta now gives the kernel's answer",
               _kv_delta(_raw2, ["realtime_tokens_total"]), 195.0)

        print("\nFixture 3 — one sample is not a window")
        _raw3 = _tmp / "r3"
        _raw3.mkdir()
        _write_csv(_raw3 / "sglang_timeseries.csv",
                   ["time_sec", f'{_P}{{mode="decode"}}'], [[0.0, 7_000_000.0]])
        _check("a lone sample of a lifetime counter measures no window",
               counter_window_total([[7_000_000.0]])["present"], False)
        _close("so the window total is zero, not the lifetime total",
               _kv_delta(_raw3, ["realtime_tokens_total"]), 0.0)
        _check("a counter with no column at all stays absent, not zero",
               _kv_delta(_raw3, ["prompt_tokens_total"]), None)

        print("\nThe absent information: realtime phase counters only")
        # This deployment exports realtime_tokens_total{mode=...} and none of
        # prompt_tokens_total / generation_tokens_total / a cached total.
        # analyze derives all three from the phase counters (v1.73.0);
        # compare rendered them "not exported".
        _raw4 = _tmp / "r4"
        _raw4.mkdir()
        _hdr = ["time_sec",
                f'{_P}{{mode="prefill_cache"}}',
                f'{_P}{{mode="prefill_compute"}}',
                f'{_P}{{mode="decode"}}',
                "sglang:time_to_first_token_seconds_sum",
                "sglang:time_to_first_token_seconds_count",
                'sglang:time_to_first_token_seconds_bucket{le="0.8"}']
        _write_csv(_raw4 / "sglang_timeseries.csv", _hdr, [
            [0.0,  1_000_000.0,   10_000.0,  40_000.0,  100.0,  200.0, 7.0],
            [10.0, 1_400_000.0,   22_000.0,  70_000.0,  520.0,  260.0, 9.0],
            [20.0, 1_800_000.0,   30_000.0, 100_000.0, 1000.0,  300.0, 11.0],
        ])
        _m = extract_metrics(RunSpec(label="phase only", raw_dir=_raw4))
        _close("cached comes from mode=prefill_cache", _m.cached_tok, 800_000.0)
        _close("prompt is cache + compute, as analyze derives it",
               _m.prompt_tok, 820_000.0)
        _close("generated comes from mode=decode", _m.gen_tok, 60_000.0)
        _check("and each says where it came from, not just that it exists",
               sorted(_m.token_src),
               ["cache_hit", "cached", "gen", "prompt", "throughput"])
        _check("the prompt note names the two series it was summed from",
               ("prefill_cache" in _m.token_src["prompt"]
                and "prefill_compute" in _m.token_src["prompt"]), True)
        _check("so KV generated is no longer absent",
               _m.kv_generated_tok is not None, True)
        _close("and equals (prompt - cached) + decode, the counter route",
               _m.kv_generated_tok, 80_000.0)
        print("\n  the two headline KPIs stop reading 0 on a fetched run")
        # Both read sglang_summary.json and nothing else, so a run fetched
        # from Prometheus -- which has no summary JSON -- rendered a 0% cache
        # hit beside a tiering study. That is a finding, and the wrong one.
        _close("cache hit is token-weighted over the window",
               _m.cache_hit_pct, 800_000.0 / 820_000.0 * 100.0, tol=1e-9)
        _close("throughput is decode tokens over the window",
               _m.throughput_tok_s, 60_000.0 / 20.0)
        _check("both name the counters they were derived from",
               ("prefill_cache" in _m.token_src["cache_hit"]
                and "decode" in _m.token_src["throughput"]), True)
        _close("and the hit-rate route now agrees with the counter route",
               _m.recomputed_tok, 20_000.0, tol=1e-6)

        print("\n  TTFT: the same formula analyze uses, on the same columns")
        # analyze (report/amoprof.py): Δsum ÷ Δcount × 1000, over every
        # matching series. Here 900 s over 100 observations = 9,000 ms.
        _want_ms = (1000.0 - 100.0) / (300.0 - 200.0) * 1000.0
        _close("compare's TTFT is the window Δsum ÷ Δcount",
               _m.ttft_ms, _want_ms)
        _close("which the kernel reaches from the raw series too",
               latency_window_ms([[100.0, 520.0, 1000.0]],
                                 [[200.0, 260.0, 300.0]])["ms"], _want_ms)
        _check("it is window-scoped, so a delta between runs is meaningful",
               _m.latency_window_scoped.get("ttft"), True)
        _check("and it is a mean, which is what the column is headed",
               _m.latency_statistic.get("ttft"), "mean")
        _close("the observation count travels with it",
               _m.latency_obs.get("ttft"), 100.0)
        _check("the bucket series did not shadow the _sum/_count pair",
               "_bucket" not in (_m.latency_source.get("ttft") or ""), True)

        print("\n  step 2: the per-interval p50 series, which compare skipped")
        # analyze's resolution order is counters, then the per-interval p50
        # series, then the summary. compare went straight from counters to
        # the summary, so on a run with no counters the two surfaces reported
        # DIFFERENT figures from the same directory -- and the summary's is
        # the one that may be a lifetime average wearing a window label.
        _raw6 = _tmp / "r6"
        _raw6.mkdir()
        (_raw6 / "sglang_percentiles_timeseries.json").write_text(
            '{"ttft": {"p50": [500.0, 700.0, 0.0, 600.0]},'
            ' "itl": {"p50": [40.0, 60.0]}}', encoding="utf-8")
        (_raw6 / "sglang_summary.json").write_text(
            '{"server_ttft_ms": 79341.0, "server_itl_ms": 120.0}',
            encoding="utf-8")
        _m6 = extract_metrics(RunSpec(label="pct ts", raw_dir=_raw6))
        _close("the p50 series wins over the summary, as it does in analyze",
               _m6.ttft_ms, (500.0 + 700.0 + 600.0) / 3.0)
        _check("and it is labelled a p50, not a mean",
               _m6.latency_statistic.get("ttft"), "p50")
        _check("the summary's 79,341 ms mean is not what was published",
               round(_m6.ttft_ms) != 79341, True)
        _check("TPOT takes the same route",
               _m6.latency_statistic.get("tpot"), "p50")
        _close("over its own active intervals", _m6.tpot_ms, 50.0)

        print("\n  a summary-only run is marked NOT window-scoped")
        _raw5 = _tmp / "r5"
        _raw5.mkdir()
        (_raw5 / "sglang_summary.json").write_text(
            '{"server_ttft_ms": 11525.0, '
            '"server_ttft_ms_method": "last_sum_over_count"}', encoding="utf-8")
        _m5 = extract_metrics(RunSpec(label="summary only", raw_dir=_raw5))
        _close("the summary figure is used as the last resort", _m5.ttft_ms,
               11525.0)
        _check("but not claimed as window-scoped",
               _m5.latency_window_scoped.get("ttft"), False)
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)

    print("\nA median must not render under a mean's label")
    _r2 = resolve_latency_ms("ttft", pct_ms=598.07)
    _check("the per-interval p50 fallback reports itself as a p50",
           _r2["statistic"], "p50")
    _check("while the counter delta reports itself as a mean",
           resolve_latency_ms("ttft", ts_ms=79341.0)["statistic"], "mean")
    _check("and the summary figure is a mean as well",
           resolve_latency_ms("ttft", summary_ms=11525.0)["statistic"], "mean")
    _check("an unresolved latency claims no statistic at all",
           resolve_latency_ms("ttft")["statistic"], "")

    print("\nOne normaliser, so one spec cannot get two answers")
    _check("a colon metric prefix normalises like an underscore one",
           normalize_series_name("sglang:realtime_tokens_total"),
           "sglang_realtime_tokens_total")
    for _spelling in ('mode="decode"', "mode='decode'", "mode=decode",
                      "mode= decode"):
        _col = f"sglang:realtime_tokens_total{{{_spelling}}}"
        _check(f"  {_spelling} resolves",
               resolve_series_columns([_col],
                                      ["realtime_tokens_total", "mode=decode"]),
               [_col])
    _check("a _bucket series never shadows the counter",
           resolve_series_columns(
               ["x_total_bucket{le=\"1\",mode=decode}", "x_total{mode=decode}"],
               ["x_total", "mode=decode"]),
           ["x_total{mode=decode}"])
    _check("every fanned column is returned, not the first",
           len(resolve_series_columns(
               ["a{mode=decode,rank=0}", "a{mode=decode,rank=1}"],
               ["a", "mode=decode"])), 2)

    print("\nEach surface reaches the kernel instead of carrying a copy")
    _cmp = _code_only(_ROOT / "amoprof" / "comparator.py")
    _amo = _code_only(_ROOT / "amoprof" / "report" / "amoprof.py")
    _comb = _code_only(_ROOT / "amoprof" / "report" / "combined.py")

    _kvd = _func_src(_cmp, "_kv_delta")
    _check("comparator._kv_delta calls the kernel",
           "_k_counter_total(" in _kvd, True)
    _check("and no longer sums a row's columns before differencing",
           ("vals[-1] - vals[0]" in _kvd or "tot += v" in _kvd), False)

    _dsm = _func_src(_amo, "_delta_sum_metric")
    _check("amoprof._delta_sum_metric calls the kernel",
           "_k_counter_total(" in _dsm, True)
    _check("and no longer does its own last-minus-first",
           "iloc[-1] - " in _dsm, False)

    _kcd = _func_src(_comb, "_kvg_counter_delta")
    _check("combined._kvg_counter_delta calls the kernel",
           "_k_counter_total(" in _kcd, True)
    _check("and no longer loops the per-step differences itself",
           "range(1, len(" in _kcd, False)

    _check("combined's phase site reads EVERY matching column",
           "_amoprof_read_series_substr(_kvg_sg_path" in _comb, True)
    _srd = _func_src(_comb, "_amoprof_read_columns_substr")
    _check("combined's substring reader uses the shared resolver",
           "_k_resolve_cols(" in _srd, True)
    _check("and not its own narrower quote-strip",
           'replace(\'"\', "")' in _srd, False)

    _lat = _func_src(_cmp, "_lat")
    _check("compare's latency goes through the kernel's window ratio",
           "_k_latency_ms(" in _lat, True)
    # No probe for the step-2 fallback. "pct_ms=" in the source was satisfied
    # by `pct_ms=0.0`, so a reversion that passed a hard zero escaped the
    # suite; the fixture above asserts the behaviour instead.
    _check("step 2 is wired to the reader, not to a constant",
           "pct_ms=_pct_ts_ms(" in _lat, True)
    _check("the brackets literal no exporter writes is gone",
           "realtime_tokens_total[mode=prefill_cache]" in _cmp, False)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
