"""DramMonitor — extracted from collectors.py into its own module.

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
from ._sudo import _sudo_cmd, _sudo_check_output, _sudo_popen, _sudo_run  # noqa: F401

log = logging.getLogger("amoprof.collectors.dram")


@register_collector
class DramMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='dram',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='Host DRAM used/available/pressure from /proc/meminfo',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0))

    """
    Polls host DRAM usage from /proc/meminfo every interval_s seconds.
    Reports:
      dram_used_gb_mean / peak   — average and peak used DRAM
      dram_free_gb_mean          — average free DRAM
      dram_util_pct_mean         — used / total %
      dram_available_gb_mean     — MemAvailable (excludes cache/buffers)
    """

    def __init__(self, interval_s: float = 1.0):
        self.interval = interval_s
        self.samples: list[dict] = []
        self._thread = None
        self._stop   = threading.Event()
        self._t0     = 0.0

    def _read_meminfo(self) -> dict:
        try:
            info = {}
            for line in open("/proc/meminfo").read().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    val = int(parts[1]) / 1024 / 1024   # kB → GB
                    info[key] = round(val, 3)
            total     = info.get("MemTotal",     0)
            free      = info.get("MemFree",      0)
            available = info.get("MemAvailable", free)
            buffers   = info.get("Buffers",      0)
            cached    = info.get("Cached",       0)
            used      = total - free - buffers - cached
            return {
                "total_gb":     round(total, 2),
                "used_gb":      round(max(used, 0), 2),
                "free_gb":      round(free, 2),
                "available_gb": round(available, 2),
                "util_pct":     round(max(used, 0) / max(total, 1) * 100, 1),
            }
        except Exception:
            return {}

    def _stamp_sample(self, sample: dict) -> dict:
        """Attach absolute and run-relative timestamps to one DRAM sample."""
        ts = time.time()
        sample = dict(sample)
        sample["ts"] = round(ts, 6)
        sample["timestamp_epoch"] = round(ts, 6)
        sample["time_sec"] = round(ts - (self._t0 or ts), 6)
        return sample

    def start(self):
        self._stop.clear()
        self.samples.clear()
        self._t0 = time.time()
        # Capture baseline
        s = self._read_meminfo()
        if s:
            self.samples.append(self._stamp_sample(s))
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = self._read_meminfo()
            if s:
                self.samples.append(self._stamp_sample(s))

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if not self.samples:
            return {"dram_available": False}
        def m(k):  return round(statistics.mean(s[k] for s in self.samples if k in s), 2)
        def pk(k): return round(max(s[k] for s in self.samples if k in s), 2)
        first = self.samples[0]
        last  = self.samples[-1]
        return {
            "dram_available":        True,
            "dram_total_gb":         first.get("total_gb", 0),
            "dram_used_gb_mean":     m("used_gb"),
            "dram_used_gb_peak":     pk("used_gb"),
            "dram_free_gb_mean":     m("free_gb"),
            "dram_available_gb_mean":m("available_gb"),
            "dram_util_pct_mean":    m("util_pct"),
            "dram_util_pct_peak":    pk("util_pct"),
            "dram_delta_gb":         round(last.get("used_gb", 0) -
                                          first.get("used_gb", 0), 2),
            "dram_samples":          len(self.samples),
        }
