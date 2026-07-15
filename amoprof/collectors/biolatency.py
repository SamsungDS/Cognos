"""BiolatencyCollector — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.biolatency")


@register_collector
class BiolatencyCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='biolatency',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='biolatency-bpfcc read-latency histogram (P50/P99/P999)',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device,
                   duration_s=max(int(ctx.get('duration_s', 60)), 1),
                   use_sudo=ctx.get('use_sudo', True))

    def __init__(self, device: str, duration_s: int = 60, use_sudo: bool = True):
        self.device=os.path.basename(device); self.duration_s=duration_s; self.use_sudo=use_sudo
        self._proc=None; self._out=""; self._done=threading.Event()

    def start(self):
        self._done.clear(); self._out=""
        try:
            self._proc = _sudo_popen(
                ["biolatency-bpfcc","-d",self.device,str(self.duration_s)], self.use_sudo,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            threading.Thread(target=self._read, daemon=True).start()
        except FileNotFoundError:
            self._done.set()

    def _read(self):
        if self._proc: self._out,_=self._proc.communicate()
        self._done.set()

    def stop(self) -> dict:
        _interrupted = bool(getattr(self, "_amoprof_interrupted", False))
        _timeout = float(getattr(self, "_amoprof_stop_timeout_s", 0.0) or (3.0 if _interrupted else self.duration_s + 5))
        if self._proc and self._proc.poll() is None:
            try: self._proc.terminate()
            except Exception: pass
        self._done.wait(timeout=_timeout)
        if self._proc and self._proc.poll() is None:
            try: self._proc.kill()
            except Exception: pass
        buckets=[]
        for line in self._out.splitlines():
            m=re.match(r"\s*(\d+)\s*->\s*(\d+)\s*:\s*(\d+)",line)
            if m:
                lo,hi,cnt=int(m.group(1)),int(m.group(2)),int(m.group(3))
                buckets.extend([(lo+hi)/2]*cnt)
        if not buckets: return {"biolatency_available":False}
        buckets.sort(); n=len(buckets)
        return {"biolatency_available":True,
                "read_lat_p50_us":  round(buckets[int(n*0.50)],1),
                "read_lat_p99_us":  round(buckets[int(n*0.99)],1),
                "read_lat_p999_us": round(buckets[min(int(n*0.999),n-1)],1),
                "read_lat_samples": n}
