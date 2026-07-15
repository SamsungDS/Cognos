"""NvlinkPcieMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.nvlink_pcie")


@register_collector
class NvlinkPcieMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='nvlink_pcie',
        layer=AIStackLayer.A4_GPU_HBM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='NVLink + PCIe TX/RX bandwidth from nvidia-smi',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(max(ctx.get('interval_s', 1.0), 1.0))

    """
    Samples NVLink bandwidth and PCIe host↔device transfer rates.

    NVLink BW:  nvidia-smi nvlink --query-nvlink=nvlink.tx.bytes,nvlink.rx.bytes
    PCIe BW:    nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current
                or dcgmi dmon -e 1009,1010 (PCIe TX/RX bytes)

    Populates A2 GPU Driver layer of the stack-cake.
    """

    def __init__(self, interval_s: float = 2.0):
        self.interval = interval_s
        self._samples: list[dict] = []
        self._thread  = None
        self._stop    = threading.Event()
        self._has_nvlink = None

    def _check_nvlink(self) -> bool:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "nvlink", "--status", "-i", "0"],
                stderr=subprocess.DEVNULL, text=True, timeout=5)
            return "Active" in out or "Inactive" in out
        except Exception:
            return False

    def _sample_nvlink(self) -> dict:
        """Query NVLink TX/RX bytes per GPU via nvidia-smi."""
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "nvlink",
                 "--query-nvlink=nvlink.tx.bytes,nvlink.rx.bytes",
                 "--format=csv,noheader,nounits", "-i", "0"],
                stderr=subprocess.DEVNULL, text=True, timeout=5)
            tx_total = rx_total = 0
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 2:
                    try:
                        tx_total += int(parts[0])
                        rx_total += int(parts[1])
                    except ValueError:
                        pass
            return {"nvlink_tx_bytes": tx_total, "nvlink_rx_bytes": rx_total,
                    "_ts": time.time()}
        except Exception:
            return {}

    def _sample_pcie(self) -> dict:
        """Query PCIe TX/RX via dcgmi dmon, fallback to nvidia-smi."""
        # Try dcgmi first (field IDs 1009=PCIe TX bytes, 1010=PCIe RX bytes)
        try:
            out = subprocess.check_output(
                ["dcgmi", "dmon", "-e", "1009,1010", "-c", "1"],
                stderr=subprocess.DEVNULL, text=True, timeout=5)
            tx = rx = 0
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    try:
                        tx += int(parts[1])
                        rx += int(parts[2])
                    except (ValueError, IndexError):
                        pass
            if tx > 0 or rx > 0:
                return {"pcie_tx_bytes_per_s": tx, "pcie_rx_bytes_per_s": rx}
        except Exception:
            pass
        # Fallback: nvidia-smi pcie link info (static, not per-interval BW)
        try:
            out = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=pcie.link.gen.current,pcie.link.width.current",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, text=True, timeout=5)
            gens = widths = []
            for line in out.strip().splitlines():
                p = [x.strip() for x in line.split(",")]
                if len(p) == 2:
                    try:
                        gens.append(int(p[0]))
                        widths.append(int(p[1]))
                    except ValueError:
                        pass
            if gens:
                # Theoretical BW: Gen5 x16 = 64 GB/s, Gen4 x16 = 32 GB/s
                gen_bw = {1: 4, 2: 8, 3: 16, 4: 32, 5: 64}
                bw_per_gpu = [gen_bw.get(g, 0) * w / 16 for g, w in zip(gens, widths)]
                return {
                    "pcie_link_gen":       gens[0] if gens else 0,
                    "pcie_link_width":     widths[0] if widths else 0,
                    "pcie_theoretical_gbps": round(sum(bw_per_gpu) / max(len(bw_per_gpu), 1), 1),
                }
        except Exception:
            pass
        return {}

    def start(self):
        self._has_nvlink = self._check_nvlink()
        self._stop.clear()
        self._samples.clear()
        s = {}
        if self._has_nvlink:
            s.update(self._sample_nvlink())
        s.update(self._sample_pcie())
        s["_ts"] = time.time()
        self._samples.append(s)
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = {}
            if self._has_nvlink:
                s.update(self._sample_nvlink())
            s.update(self._sample_pcie())
            s["_ts"] = time.time()
            self._samples.append(s)

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

        if len(self._samples) < 2:
            return {"nvlink_available": self._has_nvlink or False}

        first, last = self._samples[0], self._samples[-1]
        dt = max(last["_ts"] - first["_ts"], 0.001)

        result = {"nvlink_available": bool(self._has_nvlink)}

        if self._has_nvlink and "nvlink_tx_bytes" in last:
            tx_delta = last.get("nvlink_tx_bytes", 0) - first.get("nvlink_tx_bytes", 0)
            rx_delta = last.get("nvlink_rx_bytes", 0) - first.get("nvlink_rx_bytes", 0)
            result["nvlink_tx_gb_s"] = round(max(tx_delta, 0) / dt / 1e9, 2)
            result["nvlink_rx_gb_s"] = round(max(rx_delta, 0) / dt / 1e9, 2)
            result["nvlink_total_bw_gb_s"] = round(result["nvlink_tx_gb_s"] +
                                                    result["nvlink_rx_gb_s"], 2)

        # PCIe
        if "pcie_tx_bytes_per_s" in last:
            result["pcie_tx_gb_s"] = round(last.get("pcie_tx_bytes_per_s", 0) / 1e9, 3)
            result["pcie_rx_gb_s"] = round(last.get("pcie_rx_bytes_per_s", 0) / 1e9, 3)
        if "pcie_link_gen" in last:
            result["pcie_link_gen"]           = last["pcie_link_gen"]
            result["pcie_link_width"]         = last["pcie_link_width"]
            result["pcie_theoretical_gbps"]   = last.get("pcie_theoretical_gbps", 0)

        return result
