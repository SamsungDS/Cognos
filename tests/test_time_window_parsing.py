#!/usr/bin/env python3
"""Start/end arguments resolve to the right UTC instant, or are refused.

Run: python3 tests/test_time_window_parsing.py

Prometheus query_range takes Unix epoch seconds, which are UTC by
construction, so the only question is whether the string the operator typed
resolves to the instant they meant. Two separate mechanisms decide that, and
both are checked here.

parse_time_arg handles the conversion. A trailing Z or an explicit offset
always wins; a NAIVE datetime is deliberately read in the machine's local
zone, because an operator asking for "17:00 to 18:45" means their own wall
clock. Reading naive input as UTC silently profiled a window seven hours off
in US/Pacific, and the mistake is invisible because the query succeeds and
returns real data for the wrong hours. AMOPROF_NAIVE_TZ=utc restores the old
behaviour for anyone who wants it.

compare's --run spec is the second mechanism, and it had a worse failure. The
spec is colon-separated and a full ISO-8601 timestamp contains colons, so

    "L3::2026-09-30T23:41:00Z:2026-10-01T00:30:00Z"

split into start='2026-09-30T23' (parsed as 23:00 LOCAL -- 7h41m off) and
end='41:00Z:2026-10-01T00:30:00Z' (unparseable, so 0.0, which the fetch reads
as "the last hour"). --run's own help advertised ISO-8601, so this was a
documented spelling that silently profiled a different window on both ends.
"""
import logging
import os
import pathlib
import shlex
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.CRITICAL)

from amoprof.prometheus_source import parse_time_arg  # noqa: E402
import amoprof.cli as cli  # noqa: E402

# 2026-09-30 23:41:00 UTC and 2026-10-01 00:30:00 UTC.
T0, T1 = 1790811660.0, 1790814600.0

_RESULTS = []


def _check(name, got, want):
    ok = got == want
    _RESULTS.append((ok, name))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        got  {got!r}\n        want {want!r}")


def main() -> int:
    print("\nEvery colon-free spelling of one instant resolves to that instant")
    for s in ("20260930T2341Z", "20260930T234100Z", "1790811660"):
        _check(f"{s} is 2026-09-30 23:41:00 UTC", parse_time_arg(s), T0)
    print("\nAnd so does every spelling that carries its own zone")
    for s in ("2026-09-30T23:41:00Z", "2026-09-30T23:41:00+00:00",
              "2026-09-30T16:41:00-07:00", "2026-09-30 23:41:00+00:00"):
        _check(f"{s} is the same instant", parse_time_arg(s), T0)

    print("\nThe window from the reported command is 49 minutes")
    _check("start", parse_time_arg("20260930T2341Z"), T0)
    _check("end", parse_time_arg("20261001T0030Z"), T1)
    _check("span", (parse_time_arg("20261001T0030Z")
                    - parse_time_arg("20260930T2341Z")) / 60, 49.0)
    _check("and the epoch values are UTC by construction",
           f"{datetime.fromtimestamp(T0, timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
           "2026-09-30T23:41:00Z")

    print("\nA naive datetime is the operator's wall clock, not UTC")
    _naive = parse_time_arg("2026-09-30T23:41:00")
    _off = datetime.now().astimezone().utcoffset().total_seconds()
    _check("it is offset from the Z form by this machine's UTC offset",
           _naive - T0, -_off)
    _check("which is 0 only when the machine itself runs UTC",
           (_naive == T0) == (_off == 0.0), True)

    print("\nAnd AMOPROF_NAIVE_TZ=utc restores reading naive input as UTC")
    os.environ["AMOPROF_NAIVE_TZ"] = "utc"
    try:
        import importlib
        import amoprof.prometheus_source as _ps
        importlib.reload(_ps)
        _check("naive input then matches the Z form",
               _ps.parse_time_arg("2026-09-30T23:41:00"), T0)
        _check("an explicit Z is unaffected by the override",
               _ps.parse_time_arg("20260930T2341Z"), T0)
    finally:
        del os.environ["AMOPROF_NAIVE_TZ"]
        importlib.reload(_ps)

    print("\nUnparseable input returns 0.0 for the caller to reject")
    for s in ("not-a-time", "2026-13-45", "yesterday"):
        _check(f"{s} does not resolve", parse_time_arg(s), 0.0)
    _check("an empty string is 'no value given', not an error",
           parse_time_arg(""), 0.0)

    print("\ncompare's --run spec: colon-free forms are accepted")
    _P = cli._build_parser()
    _GOOD_B = "B::1790811660:1790814600"

    def _spec_rc(spec):
        a = _P.parse_args(shlex.split(
            f'compare --prometheus http://127.0.0.1:1 '
            f'--run "{spec}" --run "{_GOOD_B}"'))
        return cli._compare(a)

    for name, spec in (("compact ISO", "A::20260930T2341Z:20261001T0030Z"),
                       ("unix epochs", "A::1790811660:1790814600"),
                       ("relative offsets", "A::49m:now")):
        # Anything past the spec parse fails later (no reachable Prometheus),
        # so the assertion is only that the SPEC itself was not rejected.
        _check(f"{name} passes the spec parse", _spec_rc(spec) != 2, True)

    print("\nAnd the forms that would silently misread are refused")
    # Exit code alone is not enough here. An over-long spec is also caught by
    # the unparseable-field guard, because the leftover tail never parses as
    # a timestamp -- so the two guards are behaviourally redundant and the
    # field check exists to give the ISO-SPECIFIC message rather than to
    # catch a different case. Assert the message, or a mutation that removes
    # the check passes on the strength of its neighbour.
    import io
    import logging as _lg

    def _spec_err(spec):
        _buf = io.StringIO()
        _h = _lg.StreamHandler(_buf)
        _log = _lg.getLogger("amoprof")
        _lvl, _dis, _prop = _log.level, _log.disabled, _log.propagate
        _log.addHandler(_h)
        _log.setLevel(_lg.ERROR)
        _log.disabled = False
        # Keep the captured errors out of this suite's own output: they are
        # the expected result of a deliberately bad spec, and printing them
        # makes a passing run look like a failing one.
        _log.propagate = False
        try:
            _spec_rc(spec)
        finally:
            _log.removeHandler(_h)
            _log.setLevel(_lvl)
            _log.disabled = _dis
            _log.propagate = _prop
        return _buf.getvalue()

    _e = _spec_err("A::2026-09-30T23:41:00Z:2026-10-01T00:30:00Z")
    _check("the ISO case is named as a field-count problem",
           "more colon-separated fields" in _e, True)
    _check("and the leftover text is quoted back",
           "41:00Z:2026-10-01T00:30:00Z" in _e, True)
    _check("and the colon-free alternatives are offered",
           "20260930T2341Z" in _e, True)
    _e2 = _spec_err("A::20260930T2341Z:not-a-time")
    _check("a plain typo gets the parse message, not the ISO one",
           "could not parse the end field" in _e2
           and "more colon-separated fields" not in _e2, True)
    _e3 = _spec_err("A::20261001T0030Z:20260930T2341Z")
    _check("a backwards window gets its own message",
           "is not after start" in _e3, True)
    _check("a full ISO timestamp is rejected, not split",
           _spec_rc("A::2026-09-30T23:41:00Z:2026-10-01T00:30:00Z"), 2)
    _check("a typo in the end field is rejected, not read as 'last hour'",
           _spec_rc("A::20260930T2341Z:not-a-time"), 2)
    _check("a typo in the start field too",
           _spec_rc("A::not-a-time:20261001T0030Z"), 2)
    _check("a backwards window is rejected",
           _spec_rc("A::20261001T0030Z:20260930T2341Z"), 2)
    # Pre-existing guard, pinned so the new validation did not displace it.
    _check("a fetched run with no window at all is still rejected",
           _spec_rc("A::"), 2)

    print("\nThe silent misreading this prevents, spelled out")
    # What the old code produced for the documented ISO spelling.
    _parts = "A::2026-09-30T23:41:00Z:2026-10-01T00:30:00Z".split(":", 3)
    _check("the start field was truncated to an hour boundary",
           _parts[2], "2026-09-30T23")
    _check("and the end field was left as unparseable debris",
           _parts[3], "41:00Z:2026-10-01T00:30:00Z")
    _check("the truncated start does parse, which is why it was silent",
           parse_time_arg(_parts[2]) != 0.0, True)
    _check("the debris does not, and 0.0 is what the fetch calls 'last hour'",
           parse_time_arg(_parts[3]), 0.0)
    _bad = parse_time_arg(_parts[2])
    _check("so the start was wrong by the 41 minutes plus the UTC offset",
           round((T0 - _bad) / 60), round((41 * 60 + _off) / 60))

    print("\nThe help no longer advertises a spelling that cannot work")
    _cli_src = (pathlib.Path(__file__).resolve().parent.parent
                / "amoprof" / "cli.py").read_text()
    _check("--run's help says the fields must be colon-free",
           "START/END must be COLON-FREE" in _cli_src, True)
    _check("and no longer claims ISO-8601 strings work there",
           "START/END are Unix timestamps or ISO-8601 strings" in _cli_src,
           False)

    bad = [n for ok, n in _RESULTS if not ok]
    print(f"\n{len(_RESULTS) - len(bad)}/{len(_RESULTS)} passed"
          + (f" — FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
