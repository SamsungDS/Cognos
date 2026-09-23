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
    def _ocp_log(self) -> dict:
        """OCP 2.0 SMART Cloud Attributes — the real NAND counters.

        Standard SMART has no NAND-writes field, which is why WAF was
        previously fabricated from host writes.  `nvme ocp smart-add-log`
        exposes "Physical media units written", the actual bytes committed to
        NAND, plus wear indicators the standard page omits.

        The 128-bit counters print as two space-separated words (high low);
        the low word is the value for any realistic drive.
        """
        out: dict = {}
        try:
            # _sudo_check_output returns BYTES.  Treating it as str raised
            # inside _ocp_log, and because that runs from start(), the
            # exception took down the ENTIRE smart collector — no WAF, no NAND,
            # and no host_written_gb either.  Decode explicitly.
            _raw = _sudo_check_output(
                ["nvme", "ocp", "smart-add-log", self.device], self.use_sudo,
                stderr=subprocess.DEVNULL, timeout=10) or b""
            txt = (_raw.decode("utf-8", "replace")
                   if isinstance(_raw, (bytes, bytearray)) else str(_raw))
        except Exception:
            return out
        _map = {
            "physical media units written": "nand_bytes_written",
            "physical media units read":    "nand_bytes_read",
            "percent free blocks":          "pct_free_blocks",
            "max user data erase counts":   "max_erase_count",
            "min user data erase counts":   "min_erase_count",
            "endurance estimate":           "endurance_estimate",
            "bad user nand blocks - raw":   "bad_user_nand_blocks",
            "soft ecc error count":         "soft_ecc_errors",
        }
        for line in txt.splitlines():
            # Some rows use "name - value", others just "name   value" —
            # match on the key rather than requiring a separator.
            if not line.strip():
                continue
            low = line.strip().lower()
            for _k, _name in _map.items():
                if low.startswith(_k):
                    nums = [t for t in line.replace("-", " ").split()
                            if t.replace(".", "", 1).isdigit()]
                    if nums:
                        try:
                            out[_name] = float(nums[-1])
                        except ValueError:
                            pass
                    break
        return out

    def _nand_gb(self, s):
        """NAND bytes written, or None when the drive does not report it.

        This used to fall back to the HOST figure, which made WAF exactly 1.0
        by construction — an unmeasured value presented as a measurement, and
        the most misleading possible answer for an endurance study, since 1.0
        means "no amplification" rather than "not known".
        """
        return (s["nand_bytes_written"] / (1024 ** 3)
                if "nand_bytes_written" in s else None)
    def _temp(self, s):    t=s.get("temperature",0); return int(t-273) if t>200 else int(t)

    def _smart_plus(self) -> dict:
        """Standard SMART plus the OCP cloud attributes.

        The OCP read is best-effort: a drive without that log page, or any
        parsing fault, must not cost us the standard SMART fields.
        """
        d = self._smart() or {}
        try:
            d.update(self._ocp_log())
        except Exception:
            pass
        return d

    def start(self):
        self._stop.clear(); self._start = self._smart_plus()
        self._samples = [("start", time.time(), self._start)]
        self._thread  = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.poll_s):
            self._samples.append(("poll", time.time(), self._smart_plus()))

    def stop(self) -> dict:
        self._stop.set()
        if self._thread: self._thread.join(timeout=5)
        end = self._smart_plus(); self._samples.append(("end", time.time(), end))
        if not self._start: return {}
        host  = max(0.0, self._host_gb(end) - self._host_gb(self._start))
        _n_end, _n_start = self._nand_gb(end), self._nand_gb(self._start)
        _nand_known = _n_end is not None and _n_start is not None
        nand = max(0.0, _n_end - _n_start) if _nand_known else 0.0
        temps = [self._temp(s) for _,_,s in self._samples if s]
        return {
            "host_written_gb": round(host, 3),
            # Only publish NAND and WAF when the drive actually reports NAND.
            # Omitting them is honest; 1.0 is not.
            **({"nand_written_gb": round(nand, 3),
                "waf": round(nand / host, 3) if host > 0.01 else 0.0}
               if _nand_known else {}),
            "nand_reported_by_drive": 1 if _nand_known else 0,
            "temp_start_c":    self._temp(self._start),
            "temp_end_c":      self._temp(end),
            "temp_peak_c":     max(temps) if temps else 0,
        }
