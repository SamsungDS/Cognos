"""IostatMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.iostat")


@register_collector
class IostatMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='iostat',
        layer=AIStackLayer.A2_NVME_DRIVER,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='iostat -x per-device bandwidth/IOPS/await/util',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device, ctx.get('interval_s', 1.0))

    def __init__(self, device: str, interval: float = 1.0):
        self.device   = os.path.basename(device)
        self.interval = interval
        self.samples: list[dict] = []
        self._proc  = None
        self._thread= None
        self._stop  = threading.Event()

    def start(self):
        self._stop.clear(); self.samples.clear()
        self._proc = subprocess.Popen(
            ["iostat", "-x", "-d", str(self.interval), self.device],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _f(self, s):
        try: return float(s.replace(",", "."))
        except: return 0.0

    def _read(self):
        hdrs = []
        for line in self._proc.stdout:
            if self._stop.is_set(): break
            line = line.strip()
            if not line: continue
            if line.startswith("Device"): hdrs = line.split(); continue
            if self.device not in line: continue
            parts = line.split()
            if len(parts) != len(hdrs): continue
            d = dict(zip(hdrs, parts))
            # iostat may report BW in either MB/s or kB/s depending on version /
            # locale. Detect which key is present (substring match against keys,
            # not against d itself — `"rMB" in d` checks key equality, not
            # substring) and convert kB→MB when needed.
            rMB_key = next((k for k in d if k.startswith("rMB")), None)
            rkB_key = next((k for k in d if k.startswith("rkB")), None)
            wMB_key = next((k for k in d if k.startswith("wMB")), None)
            wkB_key = next((k for k in d if k.startswith("wkB")), None)
            r_bw = self._f(d.get(rMB_key, "0")) if rMB_key else \
                   self._f(d.get(rkB_key, "0")) / 1024.0
            w_bw = self._f(d.get(wMB_key, "0")) if wMB_key else \
                   self._f(d.get(wkB_key, "0")) / 1024.0
            self.samples.append({
                "ts":    time.time(),
                "rMBs":  r_bw,
                "wMBs":  w_bw,
                "riops": self._f(d.get("r/s",    d.get("tps","0"))),
                "wiops": self._f(d.get("w/s",    "0")),
                "rawt":  self._f(d.get("r_await",d.get("await","0"))),
                "wawt":  self._f(d.get("w_await","0")),
                "avgqu": self._f(d.get("avgqu-sz",d.get("aqu-sz","0"))),
                "util":  self._f(d.get("%util","0")),
            })

    def stop(self):
        self._stop.set()
        _timeout = float(getattr(self, "_amoprof_stop_timeout_s", 0.0) or 5.0)
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=min(_timeout, 5.0))
            except Exception:
                try: self._proc.kill()
                except Exception: pass
        if self._thread: self._thread.join(timeout=min(_timeout, 3.0))

    def summarise(self) -> dict:
        if not self.samples: return {}
        def m(k):  return round(statistics.mean(s[k] for s in self.samples), 3)
        def pk(k): return round(max(s[k] for s in self.samples), 3)
        def p(k, pct):
            xs = sorted(s[k] for s in self.samples)
            return round(xs[int(len(xs)*pct/100)], 3) if xs else 0.0
        return {
            "read_bw_mb_mean":    m("rMBs"),  "read_bw_mb_peak":   pk("rMBs"),
            "write_bw_mb_mean":   m("wMBs"),  "write_bw_mb_peak":  pk("wMBs"),
            "read_iops_mean":     m("riops"), "read_iops_peak":    pk("riops"),
            "write_iops_mean":    m("wiops"), "write_iops_peak":   pk("wiops"),
            "r_await_ms_mean":    m("rawt"),
            "r_await_ms_p99":     p("rawt", 99),
            "r_await_ms_p999":    p("rawt", 99.9),
            "w_await_ms_mean":    m("wawt"),  "w_await_ms_p99":    p("wawt",99),
            "avgqu_sz_mean":      m("avgqu"), "avgqu_sz_p50":      p("avgqu", 50),
            "avgqu_sz_p95":       p("avgqu", 95), "avgqu_sz_p99":      p("avgqu", 99),
            "avgqu_sz_peak":      pk("avgqu"), "util_pct_mean":       m("util"),
            "util_pct_peak":      pk("util"),
            "queue_depth_source": "iostat_aqu_sz_or_avgqu_sz",
            "iostat_samples":     len(self.samples),
        }
