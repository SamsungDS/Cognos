"""CpuMonitor — host CPU utilisation from /proc/stat.

The host CPU is not a bystander in an inference stack: it runs the scheduler,
the tokenizer, the HTTP layer, and every KV transfer that is not a direct
GPU-to-GPU copy.  A saturated host, or one stalled on iowait, shows up as
latency the GPU metrics cannot explain — which is exactly the gap this fills.

Metrics per interval, derived from jiffy deltas rather than instantaneous
values (a counter read alone tells you nothing about the window):

  cpu_util_pct        busy / total, excluding idle and iowait
  cpu_user_pct        user + nice
  cpu_system_pct      system + irq + softirq
  cpu_iowait_pct      blocked on I/O — the signal that storage is the constraint
  cpu_steal_pct       time stolen by the hypervisor; nonzero means the host is
                      oversubscribed and the measurement is not yours alone
  cpu_busiest_core_pct   the hottest single core
  cpu_cores_over_90_pct  how many cores are near saturation

Per-core figures matter because a single-threaded bottleneck pins one core
while the aggregate reads comfortable.
"""
from __future__ import annotations

import threading
import time

import logging

from ..base import (
    AIStackLayer,
    BaseCollector,
    CollectorSpec,
    register_collector,
)

log = logging.getLogger("amoprof.collectors.cpu")


@register_collector
class CpuMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='cpu',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='/proc/stat host CPU utilisation, iowait, steal, per-core',
    )

    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0))

    # /proc/stat cpu line fields, in order.
    _FIELDS = ("user", "nice", "system", "idle", "iowait",
               "irq", "softirq", "steal", "guest", "guest_nice")

    def __init__(self, interval_s: float = 1.0):
        self.interval = interval_s
        self._samples: list[dict] = []
        self._thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    def _read(self) -> dict:
        """One snapshot of aggregate and per-core jiffy counters."""
        out: dict = {"_cores": {}}
        try:
            with open("/proc/stat") as fh:
                for line in fh:
                    if not line.startswith("cpu"):
                        if out:
                            break
                        continue
                    parts = line.split()
                    name = parts[0]
                    try:
                        vals = [int(x) for x in parts[1:1 + len(self._FIELDS)]]
                    except ValueError:
                        continue
                    rec = dict(zip(self._FIELDS, vals))
                    if name == "cpu":
                        out.update(rec)
                    else:
                        out["_cores"][name] = rec
        except Exception:
            pass
        return out

    @staticmethod
    def _pcts(prev: dict, cur: dict) -> dict:
        """Percentages for one interval, from the delta between two snapshots."""
        d = {}
        for k in CpuMonitor._FIELDS:
            d[k] = max(0, int(cur.get(k, 0)) - int(prev.get(k, 0)))
        # guest time is already counted inside user/nice on Linux; adding it
        # again would push the total past 100%.
        total = sum(d[k] for k in
                    ("user", "nice", "system", "idle", "iowait",
                     "irq", "softirq", "steal"))
        if total <= 0:
            return {}
        p = lambda *keys: sum(d[k] for k in keys) / total * 100.0  # noqa: E731
        return {
            "cpu_util_pct":    100.0 - p("idle", "iowait"),
            "cpu_user_pct":    p("user", "nice"),
            "cpu_system_pct":  p("system", "irq", "softirq"),
            "cpu_iowait_pct":  p("iowait"),
            "cpu_steal_pct":   p("steal"),
            "cpu_idle_pct":    p("idle"),
        }

    # ------------------------------------------------------------------
    def start(self):
        self._stop.clear()
        self._samples.clear()
        s = self._read()
        s["_ts"] = time.time()
        self._samples.append(s)
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = self._read()
            s["_ts"] = time.time()
            self._samples.append(s)

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        s = self._read()
        s["_ts"] = time.time()
        self._samples.append(s)

        if len(self._samples) < 2:
            return {"cpu_available": False,
                    "cpu_reason": "fewer than two /proc/stat samples"}

        rows: list[dict] = []
        for prev, cur in zip(self._samples, self._samples[1:]):
            pcts = self._pcts(prev, cur)
            if not pcts:
                continue
            # Per-core, to catch a single-threaded bottleneck that the
            # aggregate hides.
            core_utils = []
            for name, cur_core in (cur.get("_cores") or {}).items():
                prev_core = (prev.get("_cores") or {}).get(name)
                if not prev_core:
                    continue
                cp = self._pcts(prev_core, cur_core)
                if cp:
                    core_utils.append(cp["cpu_util_pct"])
            if core_utils:
                pcts["cpu_busiest_core_pct"] = max(core_utils)
                pcts["cpu_cores_over_90_pct"] = float(
                    sum(1 for v in core_utils if v >= 90.0))
                pcts["cpu_core_count"] = float(len(core_utils))
            pcts["time_sec"] = cur["_ts"] - self._samples[0]["_ts"]
            rows.append(pcts)

        if not rows:
            return {"cpu_available": False,
                    "cpu_reason": "no usable /proc/stat deltas"}

        def _agg(key: str, how: str = "mean") -> float:
            vals = [r[key] for r in rows if key in r]
            if not vals:
                return 0.0
            if how == "peak":
                return round(max(vals), 2)
            return round(sum(vals) / len(vals), 2)

        out = {
            "cpu_available": True,
            "cpu_samples": len(rows),
            "cpu_util_pct_mean":   _agg("cpu_util_pct"),
            "cpu_util_pct_peak":   _agg("cpu_util_pct", "peak"),
            "cpu_user_pct_mean":   _agg("cpu_user_pct"),
            "cpu_system_pct_mean": _agg("cpu_system_pct"),
            "cpu_iowait_pct_mean": _agg("cpu_iowait_pct"),
            "cpu_iowait_pct_peak": _agg("cpu_iowait_pct", "peak"),
            "cpu_steal_pct_mean":  _agg("cpu_steal_pct"),
            "cpu_busiest_core_pct_mean": _agg("cpu_busiest_core_pct"),
            "cpu_busiest_core_pct_peak": _agg("cpu_busiest_core_pct", "peak"),
            "cpu_cores_over_90_peak":    _agg("cpu_cores_over_90_pct", "peak"),
            "cpu_core_count": _agg("cpu_core_count", "peak"),
        }
        out["_timeseries"] = rows
        return out
