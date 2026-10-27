#!/usr/bin/env python3
"""A latency histogram that arrives as several series is one histogram.

Run: python3 tests/test_analyze_latency_series.py

Two analyze reports of the reference L3 / L3.5 pair printed

    TTFT mean 84,703 ms    E2E mean 84,703 ms     (L3)
    TTFT mean 79,341 ms    E2E mean 79,341 ms     (L3.5)
    TTFT p50 800.00 · p90 8,000.00 · p99 400,000.00 ms   (every one a bucket edge)

while the comparison report, reading the same windows, had TTFT 10,080 and
E2E 14,818 ms. Both came from one cause: the fetched CSV carries more than
one series per histogram -- one per label set -- and analyze read them as if
there were one.

* The mean helpers took the FIRST matching _sum / _count column. That is one
  series' share of the requests; on these runs it was a series whose TTFT
  equals its E2E (requests answered in one chunk record their first token at
  the end), so the two tiles were identical on every tab.
* The percentile helpers took every bucket column as its own bucket. Two
  series with the same `le` became two adjacent buckets with the same bound,
  so a quantile landing in the second interpolated between lo == hi and came
  back exactly on the edge -- and only one series' observations were counted.

Prometheus answers both with sum(): ΣΔsum ÷ ΣΔcount, and
histogram_quantile(q, sum by (le) (...)). This file builds a run whose two
series differ, with the first one shaped like the reference's, and requires
every surface to agree with the truth.

Also covered: a run with no L3.5 data and no input-token counters used to
lose its whole Executive Summary to a NameError on `_l35s`.

Needs pandas (analyze does); no Prometheus.
"""
import csv
import json
import logging
import math
import pathlib
import random
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.report import common_kpis, interactive  # noqa: E402
from amoprof.report.combined import (  # noqa: E402
    _amoprof_exec_svg_tier_occupancy, _amoprof_histogram_percentiles,
    _amoprof_histogram_window_percentiles, build_executive_summary_html,
)

_RESULTS = []
LES = [0.1, 0.2, 0.4, 0.6, 0.8, 1, 2, 4, 6, 8, 10, 20, 40, 60, 80, 100, 200,
       400, float("inf")]
SERIES = ("stream=false", "stream=true")


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _within(name, got, want, rel):
    ok = got is not None and abs(got - want) <= rel * want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r} (±{rel:.0%})")


def _bracket(v_ms):
    """The bucket a value falls in, in ms: (lower edge, upper edge)."""
    v = v_ms / 1000.0
    lo = 0.0
    for le in LES:
        if v <= le:
            return lo * 1000.0, le * 1000.0
        lo = le
    return lo * 1000.0, float("inf")


def _make(raw: pathlib.Path) -> dict:
    """Two series per histogram; the FIRST one has TTFT == E2E."""
    random.seed(11)
    le_s = lambda le: "+Inf" if le == float("inf") else f"{le:g}"
    hdr = ["time_sec"]
    for base in ("time_to_first_token_seconds", "e2e_request_latency_seconds"):
        for s in SERIES:
            hdr += [f"sglang_{base}_bucket[le={le_s(le)},model_name=m,{s}]"
                    for le in LES]
            hdr += [f"sglang_{base}_sum[model_name=m,{s}]",
                    f"sglang_{base}_count[model_name=m,{s}]"]
    hdr += ["sglang_inter_token_latency_seconds_sum[model_name=m]",
            "sglang_inter_token_latency_seconds_count[model_name=m]"]
    st = {(b, s): {"cum": [0] * len(LES), "sum": 0.0, "cnt": 0}
          for b in ("ttft", "e2e") for s in SERIES}
    allv = {"ttft": [], "e2e": []}
    rows, dec = [], 0
    for i in range(160):
        if i:
            for s in SERIES:
                for _ in range(15):
                    t = random.lognormvariate(math.log(0.7), 1.6)
                    e = t + random.uniform(1.0, 9.0)
                    if s == "stream=false":
                        t = e
                    for b, v in (("ttft", t), ("e2e", e)):
                        allv[b].append(v)
                        d = st[(b, s)]
                        d["sum"] += v
                        d["cnt"] += 1
                        for k, le in enumerate(LES):
                            if v <= le:
                                d["cum"][k] += 1
            dec += 50
        r = [i * 15]
        for b in ("ttft", "e2e"):
            for s in SERIES:
                d = st[(b, s)]
                r += d["cum"] + [d["sum"], d["cnt"]]
        r += [dec * 0.03, dec]
        rows.append(r)
    raw.mkdir(parents=True)
    with (raw / "sglang_timeseries.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(hdr)
        w.writerows(rows)
    with (raw / "gpu_timeseries.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_sec", "gpu_idx", "gpu_util", "mem_used",
                    "mem_total", "power", "temp_c"])
        for i in range(160):
            for g in range(8):
                w.writerow([i * 15, g, 80, 33900, 40960, 300, 60])
    (raw / "setup_details.json").write_text(json.dumps(
        {"Model": "google/gemma-4-31b-it", "TP size": "8"}), encoding="utf-8")

    def q(xs, p):
        s = sorted(xs)
        return s[min(len(s) - 1, int(p * len(s)))] * 1000.0
    return {k: {"mean": sum(v) / len(v) * 1000.0, "n": len(v),
                "p50": q(v, .5), "p90": q(v, .9), "p99": q(v, .99)}
            for k, v in allv.items()}


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof-latser-"))
    try:
        raw = tmp / "raw"
        truth = _make(raw)
        sg = raw / "sglang_timeseries.csv"
        with sg.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))

        print("\n1 · means are summed over every series")
        k = common_kpis.compute_common_kpis(raw)
        _within("canonical TTFT mean is the true mean", k["ttft_ms"],
                truth["ttft"]["mean"], 1e-6)
        _within("canonical E2E mean is the true mean", k["e2e_ms"],
                truth["e2e"]["mean"], 1e-6)
        _check("and the two are not the same number",
               abs(k["ttft_ms"] - k["e2e_ms"]) > 1000.0, True)
        _within("the Interactive tab's own TTFT agrees",
                interactive._ratio_delta_ms_from_rows(
                    rows, "time_to_first_token_seconds_sum",
                    "time_to_first_token_seconds_count"),
                truth["ttft"]["mean"], 1e-6)
        _within("and its E2E", interactive._ratio_delta_ms_from_rows(
                    rows, "e2e_request_latency_seconds_sum",
                    "e2e_request_latency_seconds_count"),
                truth["e2e"]["mean"], 1e-6)

        print("\n2 · whole-window percentiles are sum by (le)")
        for kind, base in (("ttft", "time_to_first_token_seconds"),
                           ("e2e", "e2e_request_latency_seconds")):
            pw = _amoprof_histogram_window_percentiles(
                sg, base, (0.5, 0.9, 0.99), 1000.0)
            _check(f"{kind}: every observation is counted",
                   round(pw.get("observations", 0)), truth[kind]["n"])
            for qn in ("p50", "p90", "p99"):
                lo, hi = _bracket(truth[kind][qn])
                v = pw.get(qn, 0.0)
                _check(f"{kind} {qn} lands in the true value's bucket "
                       f"({lo:,.0f}–{hi:,.0f} ms)", lo <= v <= hi, True)
            _edges = {le * 1000.0 for le in LES if le != float("inf")}
            _check(f"{kind}: no percentile is exactly a bucket edge",
                   any(abs(pw.get(q, 0) - e) < 1e-6 for q in ("p50", "p90")
                       for e in _edges), False)

        print("\n3 · per-interval percentiles see the same histogram")
        _t, _pq = _amoprof_histogram_percentiles(
            sg, "time_to_first_token_seconds", (0.5,), 1000.0)
        _vals = [v for v in _pq.get(0.5, []) if v == v]
        _mid = sorted(_vals)[len(_vals) // 2] if _vals else 0.0
        _lo, _hi = _bracket(truth["ttft"]["p50"])
        _check("the median of the per-interval p50s is in the true p50's "
               "bucket", _lo <= _mid <= _hi, True)

        print("\n4 · an empty chart is skipped, not raised")
        _check("occupancy chart with no samples returns nothing",
               _amoprof_exec_svg_tier_occupancy(
                   [{"t": [], "v": [], "label": "x", "color": "#fff"}],
                   window=None), "")

        print("\n5 · the Executive Summary survives a run with no L3.5 data")
        try:
            _html = build_executive_summary_html(tmp)
            _err = ""
        except Exception as e:  # pragma: no cover - the failure being tested
            _html, _err = "", repr(e)
        _check("it builds", _err, "")
        _check("and carries the TTFT mean tile", "TTFT mean" in _html, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
