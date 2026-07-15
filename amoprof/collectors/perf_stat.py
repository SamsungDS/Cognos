"""PerfStatCollector — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.perf_stat")


@register_collector
class PerfStatCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='perf',
        layer=AIStackLayer.A4_GPU_HBM,
        is_ssd_scoped=False,
        is_pid_scoped=True,
        optional=True,
        enable_flag='pid',
        description='perf stat -p PID: cycles, IPC, cache misses, page faults',
    )
    @classmethod
    def for_pid(cls, pid: int, args, ctx: dict):
        return cls(pid, use_sudo=ctx.get('use_sudo', True))

    """
    Attaches ``perf stat`` to the running SGLang server PID and captures
    L3 miss rate and total memory load instruction counts for the window.

    Metrics
    -------
    perf_available              bool
    perf_l3_miss_count          int    — L3 miss events in window
    perf_all_loads_count        int    — total memory load instructions
    perf_l3_miss_rate_pct       float  — l3_miss / all_loads × 100
    perf_l3_miss_per_s          float  — L3 misses/second
    perf_duration_s             float  — measurement window duration
    perf_raw_output             str    — raw perf stat stderr text
    """

    _EVENTS = "mem_load_retired.l3_miss,mem_inst_retired.all_loads"

    def __init__(self, server_pid: int, use_sudo: bool = True):
        self.server_pid = server_pid
        self.use_sudo  = use_sudo
        self._proc      = None
        self._t0: float = 0.0
        self._result: dict = {}

    def _perf_available(self) -> bool:
        try:
            r = subprocess.run(["perf", "stat", "--help"],
                               capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def start(self):
        if not self._perf_available():
            self._result = {"perf_available": False,
                            "perf_reason": "perf not found"}
            return
        cmd = [
            "perf", "stat",
            "-e",  self._EVENTS,
            "-p",  str(self.server_pid),
            "--field-separator", ",",
        ]
        try:
            # perf stat writes metrics to stderr when interrupted
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, cwd=str(td))
            self._t0 = time.time()
        except Exception as e:
            self._result = {"perf_available": False, "perf_reason": str(e)}

    def stop(self) -> dict:
        if self._result:
            return self._result
        if not self._proc:
            return {"perf_available": False, "perf_reason": "not started"}
        elapsed = max(time.time() - self._t0, 0.001)
        try:
            self._proc.send_signal(__import__("signal").SIGINT)
            _, stderr = self._proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            _, stderr = self._proc.communicate()
        except Exception as e:
            return {"perf_available": False, "perf_reason": str(e)}

        return self._parse(stderr or "", elapsed)

    def _parse(self, raw: str, elapsed_s: float) -> dict:
        """
        Parse CSV perf stat output.  The --field-separator , format is:
          value,unit,event,run_time_ns,pct_running,...
        """
        l3_miss = all_loads = 0
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Also handle the plain human-readable format as fallback
            if "mem_load_retired.l3_miss" in line:
                m = re.search(r"([\d,]+)\s+mem_load_retired\.l3_miss", line)
                if m:
                    try: l3_miss = int(m.group(1).replace(",", ""))
                    except: pass
                # CSV path: first field is value
                parts = line.split(",")
                if parts:
                    try: l3_miss = int(parts[0].replace(",","").strip())
                    except: pass
            if "mem_inst_retired.all_loads" in line:
                m = re.search(r"([\d,]+)\s+mem_inst_retired\.all_loads", line)
                if m:
                    try: all_loads = int(m.group(1).replace(",", ""))
                    except: pass
                parts = line.split(",")
                if parts:
                    try: all_loads = int(parts[0].replace(",","").strip())
                    except: pass

        if l3_miss == 0 and all_loads == 0 and "not supported" in raw.lower():
            return {"perf_available": False,
                    "perf_reason": "PMU events not supported on this CPU"}

        miss_rate = round(l3_miss / max(all_loads, 1) * 100, 4)
        return {
            "perf_available":        True,
            "perf_l3_miss_count":    l3_miss,
            "perf_all_loads_count":  all_loads,
            "perf_l3_miss_rate_pct": miss_rate,
            "perf_l3_miss_per_s":    round(l3_miss / max(elapsed_s, 0.001), 1),
            "perf_duration_s":       round(elapsed_s, 3),
            "perf_raw_output":       raw[-2000:],
        }
