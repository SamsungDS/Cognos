"""SwapStormMonitor — extracted from collectors_extra.py into its own module.

Part of the amoprof.collectors package.  Registers itself via
@register_collector at import time (populates CollectorRegistry).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import signal  # noqa: F401  (used by some collectors' subprocess handling)
import statistics
import subprocess
import threading
import time
import urllib.request  # noqa: F401  (needed by http-based collectors)
from dataclasses import dataclass  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path

from ..base import (
    AIStackLayer,
    BaseCollector,
    CollectorSpec,
    register_collector,
)

log = logging.getLogger("amoprof.collectors.swap_storm")


@register_collector
class SwapStormMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='swap_storm',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='Per-sample pswpin/pswpout rates for swap-storm chart',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0), work_dir=ctx.get('raw_dir', '.'))

    """
    Sample /proc/vmstat at fixed interval and emit a time-series CSV of
    swap-related metrics. VmstatMonitor reports aggregates (first→last delta);
    this collector adds the per-sample rates needed to plot a swap storm chart.

    Output: <work_dir>/swap_timeseries.csv with columns:
        ts, pswpin_per_s, pswpout_per_s, pgmajfault_per_s,
            pgpgin_per_s,  pgpgout_per_s, oom_kills_cum
    """

    KEYS = ("pswpin", "pswpout", "pgmajfault", "pgpgin", "pgpgout", "oom_kill")

    def __init__(self, interval_s: float = 1.0,
                 work_dir: "Path | str" = "."):
        self.interval = max(float(interval_s), 0.1)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()
        self._thread = None
        self._samples: list[dict] = []
        self._csv_path = self.work_dir / "swap_timeseries.csv"

    def _read(self) -> dict:
        out: dict = {"ts": time.time()}
        try:
            with open("/proc/vmstat") as f:
                for line in f:
                    p = line.split()
                    if len(p) == 2 and p[0] in self.KEYS:
                        out[p[0]] = int(p[1])
        except Exception as e:
            log.debug("SwapStormMonitor read: %s", e)
        return out

    def start(self):
        self._stop.clear()
        self._samples.clear()
        self._samples.append(self._read())
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            self._samples.append(self._read())

    def stop(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._samples.append(self._read())

        if len(self._samples) < 2:
            return {"swap_storm_available": False,
                    "swap_storm_reason": "no vmstat samples"}

        rates = []
        with open(self._csv_path, "w", encoding="utf-8", newline="") as fp:
            w = _csv.writer(fp)
            w.writerow(["ts", "pswpin_per_s", "pswpout_per_s",
                        "pgmajfault_per_s", "pgpgin_per_s", "pgpgout_per_s",
                        "oom_kills_cum"])
            base_oom = self._samples[0].get("oom_kill", 0)
            for i in range(1, len(self._samples)):
                a, b = self._samples[i-1], self._samples[i]
                dt = max(b["ts"] - a["ts"], 1e-6)
                def _r(k):
                    return max(b.get(k, 0) - a.get(k, 0), 0) / dt
                row = {
                    "pswpin": _r("pswpin"),
                    "pswpout": _r("pswpout"),
                    "pgmajfault": _r("pgmajfault"),
                    "pgpgin": _r("pgpgin"),
                    "pgpgout": _r("pgpgout"),
                }
                rates.append(row)
                w.writerow([round(b["ts"], 3),
                            round(row["pswpin"], 2),
                            round(row["pswpout"], 2),
                            round(row["pgmajfault"], 2),
                            round(row["pgpgin"], 2),
                            round(row["pgpgout"], 2),
                            max(b.get("oom_kill", 0) - base_oom, 0)])

        def _mean(k): return sum(r[k] for r in rates) / max(len(rates), 1)
        def _peak(k): return max((r[k] for r in rates), default=0.0)

        # Swap storm is detected when peak pswpout exceeds a threshold.
        # We expose the raw rates and let analysis decide; default threshold
        # for "storm present" is 100 pages/s (= 400 KB/s of swap activity).
        STORM_THRESHOLD = 100.0
        swap_storm = (_peak("pswpout") > STORM_THRESHOLD
                      or _peak("pswpin") > STORM_THRESHOLD)

        return {
            "swap_storm_available":  True,
            "swap_storm_present":    bool(swap_storm),
            "swap_storm_csv":        str(self._csv_path),
            "swap_in_per_s_mean":    round(_mean("pswpin"), 2),
            "swap_in_per_s_peak":    round(_peak("pswpin"), 2),
            "swap_out_per_s_mean":   round(_mean("pswpout"), 2),
            "swap_out_per_s_peak":   round(_peak("pswpout"), 2),
            "major_faults_per_s_peak": round(_peak("pgmajfault"), 2),
        }
