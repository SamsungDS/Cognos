#!/usr/bin/env python3
"""Report which queue-depth sources a Prometheus actually has, and what each gives.

Queue depth has several possible sources with very different properties. This
asks the server which ones exist for a device and window, so a run is planned
against what is there rather than what was hoped for.

    python3 scripts/qd_sources.py http://PROM:9090 nvme6n1 [START] [END]

START/END are Unix seconds; they default to the last hour.

Two things this script learned the hard way, both of which it now checks for
you:

1.  An NVMe namespace appears in /proc/diskstats under TWO names when native
    multipath is on: the namespace head (nvme6n1) and the per-controller path
    (nvme6c6n1). The kernel accounts the time-weighted queue integral (field
    11) and the per-direction service times (fields 4 and 8) on the CONTROLLER
    PATH; the head carries only the instantaneous in-flight gauge (field 9)
    and the busy-time counter (field 10). Asking about the head alone
    therefore shows utilisation and in-flight but a dead-flat zero for queue
    depth, with nothing to say why. Every device-scoped source below is
    probed against both names and reported side by side.

2.  A queue depth in the thousands is not a deep queue. The block layer caps
    in-flight requests at nr_requests per hardware queue, and this fleet's
    drives measure in the tens to low hundreds. A larger figure is a counting
    artifact -- most often a Q→C pass over an event stream that was not sorted
    by timestamp, which leaves Q events unmatched and lets the running count
    climb for the whole capture. amoprof_blktrace_qd_qd_mean published mean
    6,876 / peak 171,982 on this fleet for exactly that reason. Such a source
    is marked implausible and is never offered as "best available".
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

# Largest value that can be a real NVMe queue depth. Same bound the report
# uses (amoprof/report/combined.py:_QD_PLAUSIBLE_MAX).
QD_PLAUSIBLE_MAX = 4096.0

_DEV_RE = re.compile(r"^nvme(\d+)(?:c(\d+))?n(\d+)$")

# (label, promql template, what it gives, caveat, is_queue_depth)
SOURCES = [
    ("blktrace Q→C (exact)",
     'amoprof_blktrace_qd_qd_mean',
     "per-I/O: true peak, p99 and time-at-depth",
     "needs blktrace running for the WHOLE window", True),
    ("blktrace peak",
     'amoprof_blktrace_qd_qd_peak',
     "the real maximum coexistence count", "", True),
    ("diskstats field 11 — node_exporter",
     'rate(node_disk_io_time_weighted_seconds_total{{device="{dev}"}}[5m])',
     "time-weighted average incl. queueing wait (= iostat aqu-sz)",
     "averages bursts; cannot miss activity", True),
    ("diskstats field 11 — amoprof collector",
     'amoprof_nvme_driver_nvme_weighted_qd_mean',
     "same quantity, at the collector's finer interval", "", True),
    ("diskstats field 9 — node_exporter",
     'node_disk_io_now{{device="{dev}"}}',
     "instantaneous in-flight; a catch is a REAL coexistence count",
     "misses most bursts between scrapes", True),
    ("diskstats field 9 — amoprof collector",
     'amoprof_nvme_driver_nvme_inflight_peak',
     "the collector's own sampled peak", "", True),
    ("iostat aqu-sz",
     'amoprof_iostat_avgqu_sz_mean',
     "field 11 as iostat computes it", "", True),
    ("Little's Law from service time",
     '(rate(node_disk_read_time_seconds_total{{device="{dev}"}}[5m]) '
     '+ rate(node_disk_write_time_seconds_total{{device="{dev}"}}[5m]))',
     "avg concurrency from throughput x latency",
     "LOWER bound: service time only, no queueing wait", True),
    ("device utilisation (context)",
     'rate(node_disk_io_time_seconds_total{{device="{dev}"}}[5m])*100',
     "%util — saturates early, not a capacity measure", "", False),
]


def q(base, expr, start, end):
    url = (base.rstrip("/") + "/api/v1/query_range?"
           + urllib.parse.urlencode({"query": expr, "start": f"{start:.0f}",
                                     "end": f"{end:.0f}", "step": "60"}))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)
    except Exception as e:
        return None, f"query failed: {e}"
    if d.get("status") != "success":
        return None, str(d.get("error", "error"))[:70]
    res = d.get("data", {}).get("result", [])
    vals = []
    for s in res:
        for _t, v in s.get("values", []):
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f:
                vals.append(f)
    return vals, ""


def sibling_names(base, dev, start, end):
    """Every /proc/diskstats name this Prometheus has for `dev`'s namespace.

    Returns the requested name first, then any other accounting path for the
    same namespace that the server actually carries series for.
    """
    m = _DEV_RE.match(dev)
    if not m:
        return [dev]
    ctrl, _path, ns = m.group(1), m.group(2), m.group(3)
    expr = (f'count by (device) (count_over_time('
            f'node_disk_io_time_seconds_total'
            f'{{device=~"nvme{ctrl}(c[0-9]+)?n{ns}"}}[5m]))')
    url = (base.rstrip("/") + "/api/v1/query_range?"
           + urllib.parse.urlencode({"query": expr, "start": f"{start:.0f}",
                                     "end": f"{end:.0f}", "step": "300"}))
    found = []
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)
        for s in d.get("data", {}).get("result", []):
            name = s.get("metric", {}).get("device", "")
            if name and name not in found:
                found.append(name)
    except Exception:
        pass
    out = [dev] + [n for n in sorted(found) if n != dev]
    return out


def kind(dev):
    m = _DEV_RE.match(dev)
    if not m:
        return "unrecognised name"
    return "controller path" if m.group(2) else "namespace head"


def probe(base, dev, start, end, best):
    """Print every source for one device name. Returns the updated `best`."""
    print(f"── {dev}  ({kind(dev)}) " + "─" * max(0, 52 - len(dev)))
    for label, tmpl, gives, caveat, is_qd in SOURCES:
        expr = tmpl.format(dev=dev)
        # A metric with no {dev} placeholder is a collector gauge that is
        # already device-scoped at the collector; probing it once per name
        # would print the same answer twice.
        if "{dev}" not in tmpl and dev != _FIRST["name"]:
            continue
        vals, err = q(base, expr, start, end)
        if err:
            print(f"  ✗  {label}\n       {err}")
            continue
        if not vals:
            print(f"  ✗  {label}\n       no samples in this window")
            continue
        mx, mean = max(vals), sum(vals) / len(vals)
        if mx <= 0:
            print(f"  ○  {label}\n       present but all zero "
                  f"({len(vals)} samples) — collector running, device idle, "
                  f"or wrong device")
            continue
        if is_qd and mx > QD_PLAUSIBLE_MAX:
            print(f"  ⚠  {label}\n       mean {mean:,.3f}  peak {mx:,.3f}  "
                  f"({len(vals)} samples)\n"
                  f"       IMPLAUSIBLE: a queue depth cannot exceed "
                  f"{QD_PLAUSIBLE_MAX:,.0f}. This is an unmatched Q→C "
                  f"counting artifact, not a queue. Not usable.")
            continue
        print(f"  ✓  {label}\n       mean {mean:,.3f}  peak {mx:,.3f}  "
              f"({len(vals)} samples)\n       {gives}")
        if caveat:
            print(f"       caveat: {caveat}")
        if is_qd and best is None:
            best = (label, dev, mean, mx)
    print()
    return best


_FIRST = {"name": ""}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base, dev = sys.argv[1], sys.argv[2]
    end = float(sys.argv[4]) if len(sys.argv) > 4 else time.time()
    start = float(sys.argv[3]) if len(sys.argv) > 3 else end - 3600
    names = sibling_names(base, dev, start, end)
    _FIRST["name"] = names[0]
    print(f"Prometheus : {base}")
    print(f"Device     : {dev}  ({kind(dev)})")
    if len(names) > 1:
        print(f"Siblings   : {', '.join(names[1:])} — the same namespace seen "
              f"through another accounting path; probed below")
    print(f"Window     : {start:.0f} → {end:.0f}  ({(end-start)/3600:.2f} h)\n")

    best = None
    for name in names:
        best = probe(base, name, start, end, best)

    if best:
        _lbl, _dev, _mean, _mx = best
        print(f"Best available: {_lbl}  on {_dev}  "
              f"(mean {_mean:,.3f}, peak {_mx:,.3f})")
        print("A peak and a mean answer different questions. Use the exact or "
              "field-9 peak for 'how deep did it get', and field 11 or "
              "Little's Law for 'how deep was it on average'.")
        if _dev != dev:
            print(f"\nNote: the usable source is on {_dev}, not the {dev} you "
                  f"asked about. Pass --nvme-device {_dev} (or "
                  f"--l35-nvme-device {_dev} for a memory node) so the report "
                  f"measures the name that carries the data.")
    else:
        print("No plausible queue-depth source has data for this device and "
              "window.")
        print("Turn one on:")
        print("  node_exporter  --collector.diskstats           (fields 9, 10, 11)")
        print("  amoprof        service --collectors nvme_driver,iostat "
              "--ssd-device " + dev)
        print("  blktrace       for exact Q→C, for the WHOLE window")
        if len(names) > 1:
            print(f"  …and try {names[1]}: under NVMe native multipath the "
                  f"queue fields land on the controller path, not the head.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
