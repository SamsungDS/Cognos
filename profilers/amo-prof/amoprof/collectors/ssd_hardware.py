"""SsdHardwareMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.ssd_hardware")


@register_collector
class SsdHardwareMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='ssd_hw',
        layer=AIStackLayer.A1_L3_SSD,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='Extended NVMe SMART + TBW/DWPD + HiCache filesystem df + device capacity',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device,
                   hicache_path=getattr(args, 'hicache_path', '/mnt/sglang_dv3'),
                   use_sudo=ctx.get('use_sudo', True))

    """
    Extended NVMe SMART metrics for A1 L3:SSD Hardware layer.

    Adds to NvmeSmartMonitor:
      - TBW (terabytes written, from data_units_written)
      - DWPD estimate (host_written / (TBW_rated * days))
      - P999 read latency (from nvme latency stats if available)
      - KV$ cold store size (du -sh of HiCache directory)
      - HiCache file count (number of KV$ block files)
    """

    def __init__(self, device: str, hicache_path: str = "/mnt/sglang_dv3",
                 rated_tbw: float = 7300.0, use_sudo: bool = True):
        self.device       = device
        self.use_sudo    = use_sudo
        self.hicache_path = hicache_path
        self.rated_tbw    = rated_tbw   # rated TBW for DWPD calc (Dell CM7 = ~7.3 PBW)
        self._start: dict = {}
        self.nvme_capacity_gb = self._read_device_capacity_gb()

    def _read_device_capacity_gb(self) -> float:
        """Read NVMe device capacity in GB from /sys/block/<dev>/size.

        Falls back to `nvme id-ctrl ... tnvmcap` if the /sys path is missing
        (e.g. partition device passed in — strip the pN suffix and retry).
        Returns 0.0 if neither source works, so the collector keeps running.
        """
        try:
            dev_name = os.path.basename(self.device)
            # /sys/block has whole-device entries only — strip pN suffix
            dev_base = re.sub(r"p\d+$", "", dev_name)
            size_path = f"/sys/block/{dev_base}/size"
            if os.path.exists(size_path):
                with open(size_path) as f:
                    sectors = int(f.read().strip())
                # /sys/block exposes 512-byte sector count regardless of the
                # device's physical sector size, so 512 is correct here.
                return round(sectors * 512 / (1024 ** 3), 2)
        except Exception:
            pass
        # Fallback: nvme id-ctrl tnvmcap (total NVM capacity in bytes)
        try:
            out = _sudo_check_output(
                ["nvme", "id-ctrl", self.device, "-o", "json"], self.use_sudo,
                stderr=subprocess.DEVNULL, timeout=10)
            j = json.loads(out)
            tn = j.get("tnvmcap", 0)
            if tn:
                return round(int(tn) / (1024 ** 3), 2)
        except Exception:
            pass
        return 0.0

    def _smart(self) -> dict:
        try:
            return json.loads(_sudo_check_output(
                ["nvme", "smart-log", self.device, "-o", "json"], self.use_sudo,
                stderr=subprocess.DEVNULL, timeout=10))
        except Exception:
            return {}

    def _latency_stats(self) -> dict:
        """nvme latency-stats — P999 read latency histogram."""
        try:
            raw = _sudo_check_output(
                ["nvme", "latency-stats", self.device], self.use_sudo,
                stderr=subprocess.DEVNULL, text=True, timeout=10)
            # Parse read latency buckets to estimate P999
            buckets = []
            in_read = False
            for line in raw.splitlines():
                if "Read" in line and "Latency" in line:
                    in_read = True
                if in_read and re.match(r"\s*\d+", line):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            lat_us = int(parts[0])
                            count  = int(parts[1])
                            buckets.extend([lat_us] * count)
                        except ValueError:
                            pass
            if buckets:
                buckets.sort()
                n = len(buckets)
                return {
                    "nvme_rd_lat_p50_us_fw":  buckets[int(n * 0.50)],
                    "nvme_rd_lat_p99_us_fw":  buckets[int(n * 0.99)],
                    "nvme_rd_lat_p999_us_fw": buckets[min(int(n * 0.999), n - 1)],
                }
        except Exception:
            pass
        return {}

    def _hicache_stats(self) -> dict:
        """Measure KV$ cold store occupancy on the SSD."""
        path = self.hicache_path
        out  = {}
        try:
            # File count
            fc = len(list(Path(path).iterdir())) if Path(path).exists() else 0
            out["hicache_file_count"] = fc
            # Directory size (bytes)
            result = subprocess.run(
                ["du", "-sb", path],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                size_bytes = int(result.stdout.split()[0])
                out["hicache_size_gb"] = round(size_bytes / (1024 ** 3), 3)
            else:
                out["hicache_size_gb"] = 0.0
        except Exception:
            out["hicache_file_count"] = -1
            out["hicache_size_gb"]    = 0.0
        return out

    def start(self):
        self._start = self._smart()

    def stop(self) -> dict:
        end = self._smart()
        if not self._start:
            return {}

        def gb(s, k):
            return s.get(k, 0) * 512 * 1024 / (1024 ** 3)

        host_written_gb = max(0.0, gb(end, "data_units_written") -
                                   gb(self._start, "data_units_written"))
        nand_written_gb = max(0.0, (end.get("nand_bytes_written", 0) -
                                    self._start.get("nand_bytes_written", 0)) / (1024 ** 3))
        waf = round(nand_written_gb / max(host_written_gb, 0.001), 3) if host_written_gb > 0.01 else 0.0

        # Cumulative TBW from SMART (total lifetime host writes)
        lifetime_host_tb = round(gb(end, "data_units_written") / 1024, 2)
        # DWPD estimate: (host_written_gb_this_run / run_hours) / (rated_tbw_tb * 1024 / 365)
        # Simplified: host_written_gb / rated_TBW_per_day_gb
        rated_gb_per_day = self.rated_tbw * 1024 / 365
        run_hours = 1.0   # approximation; real value needs wall-clock from caller
        dwpd_est  = round(host_written_gb / max(rated_gb_per_day / 24 * run_hours, 0.001), 4)

        temps = []
        for s in [self._start, end]:
            t = s.get("temperature", 0)
            temps.append(int(t - 273) if t > 200 else int(t))

        result = {
            # A1 SSD Hardware layer
            "ssd_host_written_gb":   round(host_written_gb, 3),
            "ssd_nand_written_gb":   round(nand_written_gb, 3),
            "ssd_waf":               waf,
            "ssd_lifetime_tbw":      lifetime_host_tb,
            "ssd_dwpd_est":          dwpd_est,
            "ssd_temp_start_c":      temps[0],
            "ssd_temp_end_c":        temps[1],
            "ssd_temp_peak_c":       max(temps),
            "ssd_power_cycles":      end.get("power_cycles", 0),
            "ssd_unsafe_shutdowns":  end.get("unsafe_shutdowns", 0),
            "ssd_media_errors":      end.get("media_errors", 0),
        }
        result.update(self._latency_stats())
        result.update(self._hicache_stats())
        # NVMe device total capacity
        if self.nvme_capacity_gb > 0:
            result["nvme_device_capacity_gb"] = self.nvme_capacity_gb
        # HiCache filesystem df stats
        try:
            _df = subprocess.run(
                ["df", "-B1", "--output=size,used,avail", self.hicache_path],
                capture_output=True, text=True, timeout=5)
            if _df.returncode == 0:
                _ln = []
                for _l in _df.stdout.strip().splitlines():
                    _ps = _l.split()
                    if _ps and _ps[0].isdigit():
                        _ln.append(_l)
                if _ln:
                    _p = _ln[0].split()
                    if len(_p) >= 3:
                        _G = 1024 ** 3
                        result["hicache_fs_total_gb"] = round(int(_p[0]) / _G, 2)
                        result["hicache_fs_used_gb"]  = round(int(_p[1]) / _G, 2)
                        result["hicache_fs_avail_gb"] = round(int(_p[2]) / _G, 2)
                        result["hicache_fs_used_pct"] = round(
                            int(_p[1]) / max(int(_p[0]), 1) * 100, 1)
        except Exception:
            pass
        return result
