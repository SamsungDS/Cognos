#!/usr/bin/env python3
"""A metric that goes to or from exactly zero must not kill the comparison.

Run: python3 tests/test_compare_zero_ratio.py

Reported while comparing an L3.5 DRAM-only tier against DRAM+CXL, no SSD:

    INFO   Extracted metrics for 'L3.5 DRAM Only': TTFT=75.7s ... NVMe=0 MB/s
    INFO   Extracted metrics for 'L3.5 DRAM CXL':  TTFT=75.3s ... NVMe=0 MB/s
    ERROR  compare failed: float division by zero

Not NVMe, despite the 0 MB/s beside it. build_chain_html's ratio helper
guarded `a in (None, 0)` and `b is None` but NOT `b == 0`:

    ratio = b / a                       # 100 -> 0 gives 0.0
    ... if ratio >= 1 else f"{1/ratio:.2f}x lower"   # 1/0

0.0 is not None and is less than 1, so the formatter reached `1 / ratio` and
the whole report died. A tier with no SSD makes that ordinary rather than
rare: several KV hops are legitimately zero on one side of the comparison.

The opposite direction, 0 -> non-zero, returned None and rendered as "—",
silently losing a finding. A hop that went from nothing to something is
exactly as interesting as the reverse, and on a DRAM vs DRAM+CXL comparison
it is the whole point: promotion and prefetch are zero without CXL.

Needs no Prometheus.
"""
import copy
import dataclasses
import logging
import math
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.comparator import (  # noqa: E402
    RunMetrics, RunSpec, build_chain_html, build_comparison_html,
    extract_metrics,
)

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def _chain_cells(html):
    """[(link, metric, baseline, comparison, ratio_text)] from a chain table."""
    return [(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            for m in re.finditer(
                r'<td><b>([^<]+)</b></td><td>([^<]+)</td>'
                r'<td[^>]*>([^<]*)</td><td[^>]*>([^<]*)</td>'
                r'<td[^>]*>([^<]*)</td>', html)]


def main() -> int:
    print("\nBoth zero directions render, neither raises")
    a, b = RunMetrics(label="DRAM Only"), RunMetrics(label="DRAM CXL")
    a.evicted_gb, b.evicted_gb = 91.0, 0.0          # collapse to zero
    a.promoted_gb, b.promoted_gb = 0.0, 420.0       # rise from zero
    a.prefetched_tok, b.prefetched_tok = 1000.0, 500.0   # an ordinary ratio
    try:
        html = build_chain_html(a, b)
        _check("the chain table builds", bool(html), True)
    except ZeroDivisionError:
        _check("the chain table builds", "ZeroDivisionError", True)
        html = ""
    _cells = {c[1]: c for c in _chain_cells(html)}
    _check("a collapse to zero is shown as such",
           _cells.get("evicted (GB)", (None,) * 5)[4], "→ 0")
    _check("a rise from zero is shown as such",
           _cells.get("promoted (GB)", (None,) * 5)[4], "0 →")
    _check("and an ordinary ratio is unchanged",
           _cells.get("tokens prefetched", (None,) * 5)[4], "2.00x lower")
    _check("both values are still printed beside the ratio",
           (_cells.get("evicted (GB)", (None,) * 5)[2:4],
            _cells.get("promoted (GB)", (None,) * 5)[2:4]),
           (("91.0", "0.0"), ("0.0", "420.0")))
    _check("a move to or from zero is highlighted as the largest change",
           html.count("chain-hot") >= 2, True)
    # 0 -> 0 is not a change and has no ratio; it must not be highlighted.
    c, d = RunMetrics(label="x"), RunMetrics(label="y")
    c.evicted_gb = d.evicted_gb = 0.0
    _z = {x[1]: x for x in _chain_cells(build_chain_html(c, d))}
    _check("0 to 0 stays an em dash", _z.get("evicted (GB)", (None,) * 5)[4], "—")

    print("\nThe ratio helper's four outcomes are distinct")
    # Re-derived from the shipped source so the test cannot drift from it.
    _src = (pathlib.Path(__file__).resolve().parent.parent
            / "amoprof" / "comparator.py").read_text()
    _ns = {"math": math}
    _body = _src[_src.index("    def _r(a, b):"):_src.index("    _p   = _tier_prefix(")]
    exec("import math\n" + "\n".join(l[4:] for l in _body.split("\n")), _ns)
    _r = _ns["_r"]
    _check("unmeasured on either side is None", _r(None, 5.0), None)
    _check("unmeasured on the other side too", _r(5.0, None), None)
    _check("zero to zero is None", _r(0.0, 0.0), None)
    _check("non-zero to zero is 0.0", _r(100.0, 0.0), 0.0)
    _check("zero to non-zero is infinity", _r(0.0, 100.0), math.inf)
    _check("and an ordinary pair is the plain ratio", _r(100.0, 50.0), 0.5)

    print("\nNo field, in either direction, crashes a whole comparison")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="amoprof_zr_"))
    try:
        def _mk(name):
            raw = tmp / name / "raw"
            raw.mkdir(parents=True)
            (raw / "sglang_timeseries.csv").write_text(
                "time_sec,num_queue_reqs,num_running_reqs,gen_throughput_toks\n"
                "0,0,8,0\n900,2,96,120\n1800,6,128,140\n")
            return extract_metrics(RunSpec(label=name, raw_dir=raw))
        _A, _B = _mk("A"), _mk("B")
        _A.ttft_ms, _A.tpot_ms = 75700.0, 376.0
        _B.ttft_ms, _B.tpot_ms = 75300.0, 418.0
        _names = [f.name for f in dataclasses.fields(_A)]
        _crashers = []
        for _f in _names:
            for _av, _bv in ((100.0, 0.0), (0.0, 100.0)):
                _x, _y = copy.deepcopy(_A), copy.deepcopy(_B)
                try:
                    setattr(_x, _f, _av)
                    setattr(_y, _f, _bv)
                except Exception:
                    continue
                try:
                    build_comparison_html([_x, _y], title="t")
                except ZeroDivisionError:
                    _crashers.append(f"{_f} {_av}->{_bv}")
                except Exception:
                    pass
        _check(f"all {len(_names)} fields survive both directions",
               _crashers, [])
        # The six that did crash before the fix, pinned by name so a
        # reintroduction is named rather than merely counted.
        _check("the six known crashers are among the fields probed",
               sorted(set(_names) & {"tpot_ms", "evicted_gb", "promoted_gb",
                                     "prefetched_tok", "l35_dram_gb",
                                     "l35_file_gb"}),
               ["evicted_gb", "l35_dram_gb", "l35_file_gb", "prefetched_tok",
                "promoted_gb", "tpot_ms"])

        print("\nAnd a no-SSD DRAM vs DRAM+CXL comparison renders")
        import json as _json
        for _n, _dram, _promo in (("L3.5 DRAM Only", 512, 0),
                                  ("L3.5 DRAM CXL", 1536, 4.2e11)):
            _raw = tmp / _n / "raw"
            _raw.mkdir(parents=True, exist_ok=True)
            (_raw / "sglang_timeseries.csv").write_text(
                "time_sec,num_queue_reqs,num_running_reqs,gen_throughput_toks\n"
                "0,0,8,0\n900,2,96,120\n1800,6,128,140\n")
            (_raw / "l35_store_capacity.csv").write_text(
                "time_sec,l35_dram_gb,l35_file_gb,l35_promoted_b\n"
                f"0,{_dram},0,0\n1800,{_dram},0,{_promo}\n")
            (_raw / "setup_details.json").write_text(
                _json.dumps({"Model": "google/gemma-4-31b-it",
                             "L3 backend": "mooncake"}))
        _specs = [RunSpec(label=_n, raw_dir=tmp / _n / "raw")
                  for _n in ("L3.5 DRAM Only", "L3.5 DRAM CXL")]
        _ms = [extract_metrics(_s) for _s in _specs]
        _html = build_comparison_html(_ms, title="DRAM vs DRAM+CXL")
        _check("the report builds with no SSD data anywhere",
               bool(_html), True)
        _check("and the promotion hop reads as a rise from zero",
               "0 →" in _html, True)
        _check("the queue section is present even with no device queue",
               "Queueing across the stack" in _html, True)
        _check("and absent telemetry reads as absent, not as zero",
               "not exported" in _html, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
