"""NvmeSmartMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.nvme_smart")


@register_collector
class NvmeSmartMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='smart',
        layer=AIStackLayer.A1_L3_SSD,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='nvme-cli SMART: host writes, NAND writes, WAF, temperature',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device,
                   poll_s=max(int(ctx.get('interval_s', 1.0)), 1),
                   use_sudo=ctx.get('use_sudo', True))

    def __init__(self, device: str, poll_s: int = 15, use_sudo: bool = True):
        self.device = device; self.poll_s = poll_s; self.use_sudo = use_sudo
        self._start = {}; self._samples = []
        self._thread= None; self._stop = threading.Event()

    def _smart(self) -> dict:
        try:
            return json.loads(_sudo_check_output(
                ["nvme","smart-log",self.device,"-o","json"], self.use_sudo,
                stderr=subprocess.DEVNULL, timeout=10))
        except: return {}

    def _host_gb(self, s): return s.get("data_units_written",0)*512*1024/(1024**3)
    def _nand_gb(self, s): return (s["nand_bytes_written"]/(1024**3)
                                   if "nand_bytes_written" in s else self._host_gb(s))
    def _temp(self, s):    t=s.get("temperature",0); return int(t-273) if t>200 else int(t)

    def start(self):
        self._stop.clear(); self._start = self._smart()
        self._samples = [("start", time.time(), self._start)]
        self._thread  = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.poll_s):
            self._samples.append(("poll", time.time(), self._smart()))

    def stop(self) -> dict:
        self._stop.set()
        if self._thread: self._thread.join(timeout=5)
        end = self._smart(); self._samples.append(("end", time.time(), end))
        if not self._start: return {}
        host  = max(0.0, self._host_gb(end) - self._host_gb(self._start))
        nand  = max(0.0, self._nand_gb(end) - self._nand_gb(self._start))
        temps = [self._temp(s) for _,_,s in self._samples if s]
        return {
            "host_written_gb": round(host, 3),
            "nand_written_gb": round(nand, 3),
            "waf":             round(nand/host, 3) if host > 0.01 else 0.0,
            "temp_start_c":    self._temp(self._start),
            "temp_end_c":      self._temp(end),
            "temp_peak_c":     max(temps) if temps else 0,
        }
