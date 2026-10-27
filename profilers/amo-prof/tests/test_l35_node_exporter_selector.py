#!/usr/bin/env python3
"""Does --l35-nvme-device actually reach node_exporter on the L3.5 node?

Run: python3 tests/test_l35_node_exporter_selector.py

The question this answers came from a run whose flags were:

    --l35-storage-instance msl-ssg-cx03.msl.lab:9101 \
    --l35-nvme-device nvme2c2n1

and the answer, for v1.58.1, was NO -- for two independent reasons, both of
which this test pins:

1.  The node_exporter block ran only `if not _l35s_ok`, i.e. only when the
    amoprof-collector fetch had returned nothing at all. With the amoprof
    service up on the memory node, one of ~70 metrics comes back, _l35s_ok is
    True, and the only consumer of --l35-nvme-device never executes. The
    amoprof colmap's own queue-depth candidates are sysfs/iostat gauges that
    read all-zero on this hardware, so "the amoprof path succeeded" could
    mean "it filled bandwidth and left queue depth at zero" -- and the
    node_exporter path holding the real field-11 integral was skipped on
    that basis.

2.  --l35-storage-instance names the exporter the operator knows about, which
    is the amoprof service on :9101. node_exporter is a different target on a
    different port, conventionally :9100. Reusing that instance selector for
    node_disk_* queries filters out every series the block exists to read.

It runs against a stub Prometheus (tests/stub_prometheus_l35.py) built to the
same topology, including both names of one NVMe namespace -- nvme2n1 with a
dead field 11 and nvme2c2n1 with a live one -- and three idle devices whose
only job is to dilute an unscoped avg().

No pandas required, so it runs on the same interpreter as the package.
"""
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stub_prometheus_l35 as stub  # noqa: E402

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SRC = (_REPO / "amoprof" / "report" / "amoprof.py").read_text()

# The real helpers, lifted from the module so no pandas import is needed.
_NS = {"re": re}
exec(_SRC[_SRC.index("_PROMQL_RESERVED = frozenset("):
          _SRC.index("def _prom_query_range(")], _NS)
exec(_SRC[_SRC.index("# ── NVMe device naming"):
          _SRC.index("# PromQL function and keyword names")], _NS)
_inject = _NS["_prom_inject_selector"]
_NVME_RE = _NS["_NVME_DEV_RE_PROM"]
_family = _NS["_nvme_dev_family_sel"]

HOST = "msl-ssg-cx03.msl.lab"
AMO_SEL = '{instance="%s:9101"}' % HOST
# Built exactly as the module builds it: the dot as a character class.
HOST_SEL = '{instance=~"' + HOST.replace(".", "[.]") + ':[0-9]+"}'
# The form v1.59.0 shipped, kept as the defect it was.
HOST_SEL_BROKEN = '{instance=~"' + HOST.replace(".", "\\.") + ':[0-9]+"}'
F11 = 'rate(node_disk_io_time_weighted_seconds_total{device="%s"}[2m])'

_RESULTS = []


def _q(base, expr, selector, agg=""):
    e = _inject(expr, selector)
    if agg:
        e = f"{agg}({e})"
    url = base + "/api/v1/query_range?" + urllib.parse.urlencode(
        {"query": e, "start": "0", "end": "600", "step": "60"})
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.load(r)
    res = d["data"]["result"]
    vals = [float(v) for s in res for _t, v in s["values"]]
    return res, (max(vals) if vals else None)


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    srv, base = stub.serve()
    try:
        print("\nDefect 2 — the instance named is not node_exporter's")
        _r, mx = _q(base, F11 % "nvme2c2n1", AMO_SEL, "avg")
        _check("field 11 under the :9101 selector returns nothing", mx, None)
        _r, mx = _q(base, F11 % "nvme2c2n1", HOST_SEL, "avg")
        _check("the host-scoped selector finds it", mx, 3.4)
        _check("the hyphen is not escaped", "\\-" in HOST_SEL, False)
        _check("nor is the dot: it is a character class",
               "\\." in HOST_SEL, False)
        _check("the dot is still anchored, not a wildcard",
               "[.]" in HOST_SEL, True)

        print("\nDefect 3 — a regex label value is a PromQL string first")
        # v1.59.0 built the widened selector with a backslash-escaped dot.
        # PromQL parses a quoted label value as a string literal, with Go's
        # escape rules, and `\.` is not one of them -- so every query the
        # widened selector produced came back HTTP 400 and the whole L3.5
        # node_exporter fetch returned nothing. The stub rejects it the same
        # way a real Prometheus does.
        _err = None
        try:
            _q(base, F11 % "nvme2c2n1", HOST_SEL_BROKEN, "avg")
        except urllib.error.HTTPError as e:
            _err = json.load(e).get("error", "")
        _check("a backslash-escaped dot is rejected, as Prometheus rejects it",
               bool(_err and "unknown escape sequence" in _err), True)
        if _err:
            print(f"        {_err}")
        _r, mx = _q(base, F11 % "nvme2c2n1", HOST_SEL, "avg")
        _check("the character-class form is accepted and returns the data",
               mx, 3.4)
        _check("and it still matches only that host",
               bool(re.fullmatch(HOST_SEL.split('"')[1],
                                 "msl-ssg-cx03.msl.lab:9100"))
               and not re.fullmatch(HOST_SEL.split('"')[1],
                                    "other-host.msl.lab:9100"), True)

        print("\nDefect 4 — the named device is not on this host at all")
        # Stage 1 of the diagnostic compares only ONE namespace, so when the
        # operator named nvme2c2n1 while the traffic was on nvme6c6n1 it found
        # nothing and said nothing. Stage 2 enumerates what IS there.
        _r, absent = _q(base, F11 % "nvme9c9n9", HOST_SEL, "avg")
        _check("a device that does not exist returns nothing", absent, None)
        res, _mx = _q(base, 'rate(node_disk_io_time_weighted_seconds_total'
                            '{device=~"%s"}[2m])' % _NVME_RE, HOST_SEL)
        by = {s2["metric"]["device"]:
              max(float(v) for _t, v in s2["values"]) for s2 in res}
        live = sorted((k for k, v in by.items() if v > 0), key=lambda k: -by[k])
        _check("stage 2 can enumerate the devices that do have data",
               live, ["nvme6c6n1", "nvme2c2n1"])
        _check("and ranks the busiest first", by[live[0]], 11.2)

        print("\nDefect 1 — the amoprof path 'succeeding' is not an answer")
        _r, mx = _q(base, "amoprof_iostat_read_bw_mb_mean", AMO_SEL, "avg")
        _check("the amoprof service is up and has a live metric", mx, 410.0)
        _r, qd = _q(base, "amoprof_nvme_driver_nvme_inflight_mean",
                    AMO_SEL, "avg")
        _check("but its queue-depth gauge reads zero", qd, 0.0)
        _check("so gating node_exporter on that success loses the real depth",
               (mx or 0) > 0 and qd == 0.0, True)

        print("\nNamespace head vs controller path")
        _r, head = _q(base, F11 % "nvme2n1", HOST_SEL, "avg")
        _r, ctrl = _q(base, F11 % "nvme2c2n1", HOST_SEL, "avg")
        _check("nvme2n1 (head) field 11 is zero", head, 0.0)
        _check("nvme2c2n1 (controller path) field 11 is live", ctrl, 3.4)

        print("\nThe sibling diagnostic's query")
        res, _mx = _q(base, "rate(node_disk_io_time_weighted_seconds_total"
                            f"{_family('nvme2n1')}[2m])", HOST_SEL)
        by = {s["metric"]["device"]:
              max(float(v) for _t, v in s["values"]) for s in res}
        _check("it sees both names of the namespace and nothing else",
               sorted(by), ["nvme2c2n1", "nvme2n1"])
        _check("requested dead, sibling live, so it speaks",
               by["nvme2n1"] == 0.0 and by["nvme2c2n1"] > 0.0, True)

        print("\nWhy the device filter is not optional")
        # The host has six block devices publishing field 11: nvme2c2n1 at
        # 3.4, nvme6c6n1 at 11.2, and four idle ones. An unscoped avg() does
        # not merely dilute -- it reports a number that belongs to no device.
        _r, un = _q(base, "rate(node_disk_io_time_weighted_seconds_total[2m])",
                    HOST_SEL, "avg")
        _check("unscoped avg() over 6 devices reports 2.43, which is neither",
               round(un, 2), round((3.4 + 11.2) / 6, 2))
        _r, nvme_only = _q(
            base, 'rate(node_disk_io_time_weighted_seconds_total'
                  '{device=~"%s"}[2m])' % _NVME_RE, HOST_SEL, "avg")
        _check("scoping to NVMe namespaces alone reports 3.65 -- still neither",
               round(nvme_only, 2), round((3.4 + 11.2) / 4, 2))
        _check("and it INFLATES the device under study, not just dilutes it",
               round(nvme_only, 2) > 3.4, True)
        _check("only the named device reports its own value", ctrl, 3.4)
    finally:
        srv.shutdown()

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
