"""NetworkMonitor — host network transactions and bandwidth.

Part of the amoprof.collectors package.  Registers itself via
@register_collector at import time (populates CollectorRegistry).

Why this exists
---------------
For disaggregated / multi-node inference the fabric is a first-class tier:
KV transfer between prefill and decode workers, remote-storage L3 backends
(Mooncake, 3FS, NFS/RDMA), and tensor-parallel collectives all move bytes
over the NIC.  Without NIC telemetry a fabric stall is indistinguishable
from a slow storage tier — both look like "tokens waiting".

Sources, in order of preference per interface
  * /proc/net/dev            — rx/tx bytes, packets, errors, drops (always)
  * /sys/class/net/<if>/speed — link speed, for utilisation %
  * /sys/class/infiniband/*  — IB/RoCE port_rcv_data / port_xmit_data,
                               which /proc/net/dev does not see for
                               kernel-bypass (verbs) traffic
  * /proc/net/snmp + netstat — TCP retransmits, a direct congestion signal

Everything is read from sysfs/procfs, so there is no external binary
dependency and no elevated privilege requirement.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

# One call site references `_csv`; alias it so a NameError cannot surface
# at runtime inside a try/except and be reported as a parse failure.
import csv as _csv

from ..base import (
    AIStackLayer,
    BaseCollector,
    CollectorSpec,
    register_collector,
)

log = logging.getLogger("amoprof.collectors.network")

# Interfaces that never carry inference traffic and only add noise.
_SKIP_PREFIXES = ("lo", "docker", "veth", "br-", "virbr", "cni", "flannel",
                  "kube-", "tunl", "gre", "sit", "dummy")


def _is_interesting(name: str) -> bool:
    return not any(name.startswith(p) for p in _SKIP_PREFIXES)


def _read_proc_net_dev() -> dict[str, dict[str, float]]:
    """Parse /proc/net/dev into {iface: {counter: value}} (cumulative)."""
    out: dict[str, dict[str, float]] = {}
    try:
        lines = Path("/proc/net/dev").read_text().splitlines()
    except Exception:
        return out
    for line in lines[2:]:
        if ":" not in line:
            continue
        name, _, rest = line.partition(":")
        name = name.strip()
        if not _is_interesting(name):
            continue
        f = rest.split()
        if len(f) < 16:
            continue
        try:
            out[name] = {
                "rx_bytes": float(f[0]), "rx_packets": float(f[1]),
                "rx_errs": float(f[2]),  "rx_drop": float(f[3]),
                "tx_bytes": float(f[8]), "tx_packets": float(f[9]),
                "tx_errs": float(f[10]), "tx_drop": float(f[11]),
            }
        except (ValueError, IndexError):
            continue
    return out


def _read_ethtool_phy(ifaces: "list[str]") -> dict[str, dict[str, float]]:
    """PHY-layer byte counters from `ethtool -S`, per interface.

    /proc/net/dev reports what the KERNEL saw.  On a Mellanox NIC carrying
    RoCE/RDMA — which is how KV blocks reach a remote memory node — the
    transfers bypass the kernel network stack entirely, so /proc/net/dev shows
    almost nothing while the link is saturated.  It also excludes Ethernet
    framing, preamble and CRC, so even for plain TCP it under-reports the wire
    rate by a few percent.

    `rx_bytes_phy` / `tx_bytes_phy` are the NIC's own hardware counters and see
    every byte on the wire, which is what `mlnx_perf` and `ethtool -S` report
    and what an operator comparing against those tools expects to match.

    Falls back silently when ethtool is missing or the counters are not
    exposed; the caller then uses /proc/net/dev.
    """
    out: dict[str, dict[str, float]] = {}
    if not shutil.which("ethtool"):
        return out
    for iface in ifaces:
        if not iface or iface == "lo":
            continue
        try:
            txt = subprocess.run(["ethtool", "-S", iface],
                                 capture_output=True, text=True,
                                 timeout=5).stdout or ""
        except Exception:
            continue
        vals: dict[str, float] = {}
        for line in txt.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip()
            if k in ("rx_bytes_phy", "tx_bytes_phy",
                     "rx_packets_phy", "tx_packets_phy"):
                try:
                    vals[k.replace("_phy", "")] = float(v.strip().split()[0])
                except (ValueError, IndexError):
                    pass
        if "rx_bytes" in vals and "tx_bytes" in vals:
            vals.setdefault("rx_packets", 0.0)
            vals.setdefault("tx_packets", 0.0)
            for _z in ("rx_errs", "tx_errs", "rx_drop", "tx_drop"):
                vals.setdefault(_z, 0.0)
            out[iface] = vals
    return out


def _read_ib_counters() -> dict[str, dict[str, float]]:
    """IB/RoCE port counters. port_*_data is in 32-bit words -> x4 for bytes."""
    out: dict[str, dict[str, float]] = {}
    base = Path("/sys/class/infiniband")
    if not base.exists():
        return out
    try:
        for dev in sorted(base.iterdir()):
            for port in sorted((dev / "ports").iterdir()) if (dev / "ports").exists() else []:
                c = port / "counters"
                if not c.exists():
                    continue

                def _rd(fn: str) -> float:
                    try:
                        return float((c / fn).read_text().strip())
                    except Exception:
                        return 0.0
                rcv, xmit = _rd("port_rcv_data"), _rd("port_xmit_data")
                if rcv <= 0 and xmit <= 0:
                    continue
                out[f"{dev.name}:{port.name}"] = {
                    "rx_bytes": rcv * 4.0,
                    "tx_bytes": xmit * 4.0,
                    "rx_packets": _rd("port_rcv_packets"),
                    "tx_packets": _rd("port_xmit_packets"),
                    "rx_errs": _rd("port_rcv_errors"),
                    "tx_errs": _rd("port_xmit_discards"),
                    "rx_drop": _rd("port_rcv_remote_physical_errors"),
                    "tx_drop": 0.0,
                }
    except Exception:
        pass
    return out


def _read_tcp_retrans() -> float:
    """Cumulative TCP retransmitted segments from /proc/net/snmp."""
    try:
        lines = Path("/proc/net/snmp").read_text().splitlines()
    except Exception:
        return 0.0
    for i, line in enumerate(lines):
        if line.startswith("Tcp:") and "RetransSegs" in line:
            hdr = line.split()
            try:
                vals = lines[i + 1].split()
                return float(vals[hdr.index("RetransSegs")])
            except Exception:
                return 0.0
    return 0.0


def _link_speed_mbits(iface: str) -> float:
    for p in (Path(f"/sys/class/net/{iface}/speed"),):
        try:
            v = float(p.read_text().strip())
            return v if v > 0 else 0.0
        except Exception:
            continue
    return 0.0


@register_collector
class NetworkMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='network',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='NIC/IB transactions, bandwidth, errors and TCP retransmits',
    )

    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0),
                   ifaces=str(getattr(args, "net_iface", "") or ""))

    def __init__(self, interval: float = 1.0, ifaces: str = ""):
        # Which interfaces count toward the totals.  Without this every NIC on
        # the box is summed — management, loopback aliases, unused ports — so
        # the "network bandwidth" figure is not the fabric carrying KV traffic
        # and the link-utilisation percentage is meaningless.  Naming the
        # interface makes the number specific to the path being measured.
        self.ifaces = [x.strip() for x in ifaces.split(",") if x.strip()]
        # Which interfaces are being read at PHY level, so the report can say
        # so rather than leaving the reader to wonder why amoprof and
        # `ethtool -S` agree (or, previously, did not).
        self._phy_ifaces: set[str] = set()
        self.interval = max(0.1, float(interval or 1.0))
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = 0.0

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        self.samples.clear()
        self._stop.clear()
        self._t0 = time.time()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        prev = None
        prev_t = None
        prev_retr = _read_tcp_retrans()
        while not self._stop.is_set():
            now = time.time()
            cur = _read_proc_net_dev()
            # PHY counters override the kernel's view for any interface that
            # exposes them.  Same key, so downstream aggregation is unchanged;
            # only the source improves.  Restricted to the interfaces actually
            # being measured, since ethtool is a syscall per interface.
            _phy_targets = self.ifaces or [k for k in cur if k != "lo"]
            for _if, _v in _read_ethtool_phy(_phy_targets).items():
                cur[_if] = _v
                self._phy_ifaces.add(_if)
            cur.update(_read_ib_counters())
            retr = _read_tcp_retrans()
            if prev is not None and prev_t is not None:
                dt = now - prev_t
                if dt > 0:
                    agg = {k: 0.0 for k in ("rx_bytes", "tx_bytes", "rx_packets",
                                            "tx_packets", "rx_errs", "tx_errs",
                                            "rx_drop", "tx_drop")}
                    for iface, c in cur.items():
                        # Only the named interfaces, when the operator named
                        # any.  Matching is exact, so a typo yields zeros
                        # rather than silently falling back to "everything" —
                        # a wrong-but-plausible total is worse than an obvious
                        # absence.
                        if self.ifaces and iface not in self.ifaces:
                            continue
                        p = prev.get(iface)
                        if not p:
                            continue
                        d = {k: max(0.0, c.get(k, 0.0) - p.get(k, 0.0)) for k in agg}
                        speed = _link_speed_mbits(iface)
                        self.samples.append({
                            "time_sec": round(now - self._t0, 3),
                            "iface": iface,
                            "rx_mbs": d["rx_bytes"] / dt / 1e6,
                            "tx_mbs": d["tx_bytes"] / dt / 1e6,
                            "rx_pps": d["rx_packets"] / dt,
                            "tx_pps": d["tx_packets"] / dt,
                            "rx_errs_ps": d["rx_errs"] / dt,
                            "tx_errs_ps": d["tx_errs"] / dt,
                            "rx_drop_ps": d["rx_drop"] / dt,
                            "tx_drop_ps": d["tx_drop"] / dt,
                            "link_speed_mbits": speed,
                            "link_util_pct": (((d["rx_bytes"] + d["tx_bytes"]) * 8.0 / dt)
                                              / (speed * 1e6) * 100.0) if speed > 0 else 0.0,
                        })
                        for k in agg:
                            agg[k] += d[k]
                    self.samples.append({
                        "time_sec": round(now - self._t0, 3),
                        "iface": "_total",
                        "rx_mbs": agg["rx_bytes"] / dt / 1e6,
                        "tx_mbs": agg["tx_bytes"] / dt / 1e6,
                        "total_mbs": (agg["rx_bytes"] + agg["tx_bytes"]) / dt / 1e6,
                        "rx_pps": agg["rx_packets"] / dt,
                        "tx_pps": agg["tx_packets"] / dt,
                        "total_pps": (agg["rx_packets"] + agg["tx_packets"]) / dt,
                        "rx_errs_ps": agg["rx_errs"] / dt,
                        "tx_errs_ps": agg["tx_errs"] / dt,
                        "rx_drop_ps": agg["rx_drop"] / dt,
                        "tx_drop_ps": agg["tx_drop"] / dt,
                        "tcp_retrans_ps": max(0.0, retr - prev_retr) / dt,
                        "link_speed_mbits": 0.0,
                        "link_util_pct": 0.0,
                    })
            prev, prev_t, prev_retr = cur, now, retr
            self._stop.wait(self.interval)

    def stop(self, *args, **kwargs) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 3)
        tot = [s for s in self.samples if s.get("iface") == "_total"]
        if not tot:
            return {"network_available": False}

        def _mean(k): return sum(s.get(k, 0.0) for s in tot) / len(tot)
        def _peak(k): return max((s.get(k, 0.0) for s in tot), default=0.0)
        per_if: dict[str, dict] = {}
        for s in self.samples:
            n = s.get("iface")
            if n == "_total":
                continue
            e = per_if.setdefault(n, {"rx_mbs_sum": 0.0, "tx_mbs_sum": 0.0, "n": 0,
                                      "link_speed_mbits": s.get("link_speed_mbits", 0.0),
                                      "link_util_pct_peak": 0.0})
            e["rx_mbs_sum"] += s.get("rx_mbs", 0.0)
            e["tx_mbs_sum"] += s.get("tx_mbs", 0.0)
            e["link_util_pct_peak"] = max(e["link_util_pct_peak"], s.get("link_util_pct", 0.0))
            e["n"] += 1
        interfaces = {
            n: {"rx_mbs_mean": round(e["rx_mbs_sum"] / max(e["n"], 1), 3),
                "tx_mbs_mean": round(e["tx_mbs_sum"] / max(e["n"], 1), 3),
                "link_speed_mbits": e["link_speed_mbits"],
                "link_util_pct_peak": round(e["link_util_pct_peak"], 2)}
            for n, e in per_if.items()
        }
        # The Prometheus exporter in service.py emits one gauge per *scalar*
        # summary key (amoprof_network_<key>) and skips nested structures, so
        # flatten per-interface figures into scalar keys as well — otherwise
        # only the host aggregate would ever be scrapeable and a single
        # saturated NIC in a bonded pair would be invisible.
        flat: dict = {}
        for _n, _e in interfaces.items():
            _safe = re.sub(r"[^A-Za-z0-9_]", "_", _n)
            flat[f"iface_{_safe}_rx_mbs_mean"] = _e["rx_mbs_mean"]
            flat[f"iface_{_safe}_tx_mbs_mean"] = _e["tx_mbs_mean"]
            flat[f"iface_{_safe}_link_speed_mbits"] = _e["link_speed_mbits"]
            flat[f"iface_{_safe}_link_util_pct_peak"] = _e["link_util_pct_peak"]

        return {
            "network_available": True,
            "samples": len(tot),
            "interface_count": len(interfaces),
            "interfaces": interfaces,
            # Which layer the bytes came from.  PHY matches `ethtool -S` and
            # `mlnx_perf`; the kernel view does not, and under-reports badly
            # when RDMA/RoCE bypasses the stack.  Stated so a mismatch against
            # those tools is explainable rather than mysterious.
            "net_counter_source": ("phy_ethtool" if self._phy_ifaces
                                   else "kernel_proc_net_dev"),
            "net_phy_interfaces": ",".join(sorted(self._phy_ifaces)),
            **flat,
            "net_rx_mbs_mean": round(_mean("rx_mbs"), 3),
            "net_tx_mbs_mean": round(_mean("tx_mbs"), 3),
            "net_total_mbs_mean": round(_mean("total_mbs"), 3),
            "net_rx_mbs_peak": round(_peak("rx_mbs"), 3),
            "net_tx_mbs_peak": round(_peak("tx_mbs"), 3),
            "net_total_mbs_peak": round(_peak("total_mbs"), 3),
            "net_total_pps_mean": round(_mean("total_pps"), 1),
            "net_total_pps_peak": round(_peak("total_pps"), 1),
            "net_rx_errs_ps_mean": round(_mean("rx_errs_ps"), 4),
            "net_tx_errs_ps_mean": round(_mean("tx_errs_ps"), 4),
            "net_rx_drop_ps_mean": round(_mean("rx_drop_ps"), 4),
            "net_tcp_retrans_ps_mean": round(_mean("tcp_retrans_ps"), 4),
            "net_tcp_retrans_ps_peak": round(_peak("tcp_retrans_ps"), 4),
            "net_link_util_pct_peak": round(
                max((v["link_util_pct_peak"] for v in interfaces.values()), default=0.0), 2),
        }

    # -- CSV ---------------------------------------------------------------
    NETWORK_TIMESERIES_COLUMNS = [
        "time_sec", "iface", "rx_mbs", "tx_mbs", "total_mbs",
        "rx_pps", "tx_pps", "total_pps",
        "rx_errs_ps", "tx_errs_ps", "rx_drop_ps", "tx_drop_ps",
        "tcp_retrans_ps", "link_speed_mbits", "link_util_pct",
    ]

    def write_timeseries(self, raw_dir: Path) -> Path | None:
        """Write network_timeseries.csv (aggregate rows plus per-interface)."""
        import csv as _csv
        if not self.samples:
            return None
        out = Path(raw_dir) / "network_timeseries.csv"
        try:
            with out.open("w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=self.NETWORK_TIMESERIES_COLUMNS,
                                    extrasaction="ignore")
                w.writeheader()
                for s in self.samples:
                    row = {k: s.get(k, "") for k in self.NETWORK_TIMESERIES_COLUMNS}
                    if row.get("total_mbs") == "":
                        row["total_mbs"] = (s.get("rx_mbs", 0.0) or 0.0) + (s.get("tx_mbs", 0.0) or 0.0)
                    if row.get("total_pps") == "":
                        row["total_pps"] = (s.get("rx_pps", 0.0) or 0.0) + (s.get("tx_pps", 0.0) or 0.0)
                    w.writerow(row)
            return out
        except Exception as e:
            log.warning("failed to write network_timeseries.csv: %s", e)
            return None
