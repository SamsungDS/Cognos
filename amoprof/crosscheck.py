"""Independent cross-validation of AMOprof measurements against node_exporter.

AMOprof's own collectors and node_exporter observe several of the same
quantities by different routes — iostat parses a text stream, node_exporter
reads /sys and /proc directly.  When the two disagree by more than sampling
jitter, one of them is wrong, and which one matters: a silent measurement
error propagates into every chart and conclusion downstream.

This module answers "are the numbers right", not "which layer is the
bottleneck".  It is a consistency check, not ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Agreement within this fraction is attributed to sampling jitter rather than
# to a measurement fault.  Two instruments sampling the same counter at
# different phases will not match exactly.
TOLERANCE = 0.10


@dataclass
class CrossCheck:
    quantity: str
    amoprof_value: Optional[float]
    node_value: Optional[float]
    unit: str
    note: str = ""
    # Some pairs are expected to differ: AMOprof reads NIC PHY counters while
    # node_exporter reads /proc/net/dev, and RDMA traffic bypasses the kernel
    # stack entirely.  Flagging that as a fault would train the reader to
    # ignore the check, so it is reported as an expected gap instead.
    expect_gap: bool = False

    @property
    def ratio(self) -> Optional[float]:
        if not self.amoprof_value or self.node_value is None:
            return None
        if self.amoprof_value == 0:
            return None
        return self.node_value / self.amoprof_value

    @property
    def status(self) -> str:
        """agree | DISAGREE | amoprof-only | node-only | absent."""
        a, n = self.amoprof_value, self.node_value
        if a is None and n is None:
            return "absent"
        if a is None:
            return "node-only"
        if n is None:
            return "amoprof-only"
        r = self.ratio
        if r is None:
            if a == 0 and n == 0:
                return "agree"
            return "expected-gap" if self.expect_gap else "DISAGREE"
        if (1 - TOLERANCE) <= r <= (1 + TOLERANCE):
            return "agree"
        return "expected-gap" if self.expect_gap else "DISAGREE"

    def render(self) -> str:
        def _f(v):
            return "absent" if v is None else f"{v:,.2f}"
        r = self.ratio
        rs = "—" if r is None else f"{r:.2f}x"
        return (f"{self.quantity:<34s} amoprof {_f(self.amoprof_value):>14s}  "
                f"node {_f(self.node_value):>14s} {self.unit:<6s} "
                f"{rs:>7s}  {self.status}")


def compare_sources(amoprof: dict, node: dict) -> "list[CrossCheck]":
    """Pair AMOprof's own measurements with node_exporter's for the same quantity.

    Only quantities both instruments genuinely observe are paired.  Pairing a
    derived estimate against a direct reading would manufacture a disagreement
    that says nothing about either instrument.
    """
    pairs = [
        ("disk bytes written", "write_total_gb", "node_disk_written_gb", "GB",
         "iostat stream vs /sys/block counters", False),
        ("disk bytes read", "read_total_gb", "node_disk_read_gb", "GB",
         "iostat stream vs /sys/block counters", False),
        ("host DRAM used", "dram_used_gb", "node_mem_used_gb", "GB",
         "collector /proc/meminfo vs node_exporter /proc/meminfo", False),
        ("network rx", "net_rx_gb", "node_net_rx_gb", "GB",
         "PHY counters vs /proc/net/dev — a gap here is RDMA bypassing the "
         "kernel stack, which is information, not an error", True),
        ("network tx", "net_tx_gb", "node_net_tx_gb", "GB",
         "PHY counters vs /proc/net/dev — see rx", True),
        ("major page faults", "major_faults", "node_vmstat_pgmajfault", "",
         "vmstat collector vs node_exporter", False),
    ]
    out = []
    for label, a_key, n_key, unit, note, gap in pairs:
        out.append(CrossCheck(label, amoprof.get(a_key), node.get(n_key),
                              unit, note, gap))
    return out


def render_report(checks: "list[CrossCheck]") -> str:
    """Plain-text summary, for the analyze log and for --self-check."""
    lines = ["Cross-check against node_exporter "
             f"(agreement within {int(TOLERANCE*100)}%):", ""]
    for c in checks:
        lines.append("  " + c.render())
    bad = [c for c in checks if c.status == "DISAGREE"]
    gaps = [c for c in checks if c.status == "expected-gap"]
    lines.append("")
    for c in gaps:
        lines.append(f"  note  {c.quantity}: {c.note}")
    if gaps:
        lines.append("")
    if not bad:
        lines.append("  No unexpected disagreement.")
    else:
        lines.append(f"  {len(bad)} quantity/quantities disagree beyond tolerance:")
        for c in bad:
            lines.append(f"    - {c.quantity}: {c.note}")
        lines.append("  A disagreement means one instrument is wrong. Resolve "
                     "before trusting charts derived from it.")
    return "\n".join(lines)
