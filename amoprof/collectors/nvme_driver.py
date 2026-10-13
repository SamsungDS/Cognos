"""NvmeDriverMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.nvme_driver")


@register_collector
class NvmeDriverMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='nvme_driver',
        layer=AIStackLayer.A2_NVME_DRIVER,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='sysfs NVMe driver counters: IOPS, inflight, weighted QD, latency',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device, ctx.get('interval_s', 1.0))

    """
    Reads NVMe driver-level metrics from sysfs (A2 io_uring/NVMe Driver layer).

    /sys/block/nvme0n1/stat:
      field 0  = reads completed
      field 3  = read ms total
      field 4  = writes completed
      field 7  = write ms total
      field 8  = I/Os currently in flight (queue depth)
      field 9  = ms spent doing I/Os (utilisation)
      field 10 = weighted ms spent doing I/Os (time_in_queue; avg QD source)

    Also reads queue parameters:
      /sys/block/<dev>/queue/nr_requests  — queue depth limit
      /sys/block/<dev>/queue/scheduler    — current I/O scheduler
      /sys/block/<dev>/inflight           — reads/writes in flight
    """

    def __init__(self, device: str, interval_s: float = 1.0):
        self.dev      = os.path.basename(device)
        self.interval = interval_s
        self._samples: list[dict] = []
        self._thread  = None
        self._stop    = threading.Event()

    def _read_stat(self) -> dict:
        try:
            raw = open(f"/sys/block/{self.dev}/stat").read().split()
            if len(raw) < 11:
                return {}
            # Fields 2 and 6 are sectors read / written, always in 512-byte
            # units whatever the device's block size (Documentation/block/
            # stat.rst).  They were skipped, so this collector published IOPS,
            # latency and queue depth but never bytes, and a run whose only
            # device collector was this one had no device bandwidth at all.
            return {
                "_ts":        time.time(),
                "rd_ios":     int(raw[0]),
                "rd_sectors": int(raw[2]),
                "rd_ms":      int(raw[3]),
                "wr_ios":     int(raw[4]),
                "wr_sectors": int(raw[6]),
                "wr_ms":      int(raw[7]),
                "inflight":       int(raw[8]),
                "io_ms":          int(raw[9]),
                "weighted_io_ms": int(raw[10]) if len(raw) > 10 else 0,
            }
        except Exception:
            return {}

    def _read_queue_params(self) -> dict:
        out = {}
        base = f"/sys/block/{self.dev}/queue"
        for f, key in [("nr_requests", "nr_requests"),
                       ("scheduler",   "scheduler"),
                       ("rotational",  "rotational"),
                       ("physical_block_size", "physical_block_size_b"),
                       ("logical_block_size",  "logical_block_size_b")]:
            try:
                val = open(f"{base}/{f}").read().strip()
                out[key] = int(val) if val.isdigit() else val
            except Exception:
                pass
        # Inflight (reads in-flight, writes in-flight)
        try:
            parts = open(f"/sys/block/{self.dev}/inflight").read().split()
            if len(parts) >= 2:
                out["inflight_reads"]  = int(parts[0])
                out["inflight_writes"] = int(parts[1])
        except Exception:
            pass
        return out

    def start(self):
        self._stop.clear()
        self._samples.clear()
        s = self._read_stat()
        if s:
            self._samples.append(s)
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = self._read_stat()
            if s:
                self._samples.append(s)

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        s = self._read_stat()
        if s:
            self._samples.append(s)

        qp = self._read_queue_params()

        if len(self._samples) < 2:
            return {"nvme_driver_available": False, **qp}

        first, last = self._samples[0], self._samples[-1]
        dt = max(last["_ts"] - first["_ts"], 0.001)

        rd_ios_delta = max(last["rd_ios"] - first["rd_ios"], 0)
        wr_ios_delta = max(last["wr_ios"] - first["wr_ios"], 0)
        rd_ms_delta  = max(last["rd_ms"]  - first["rd_ms"],  0)
        wr_ms_delta  = max(last["wr_ms"]  - first["wr_ms"],  0)
        io_ms_delta  = max(last["io_ms"]  - first["io_ms"],  0)

        # Average completion latency from sysfs (ms per IO)
        rd_lat_ms = round(rd_ms_delta / max(rd_ios_delta, 1), 2)
        wr_lat_ms = round(wr_ms_delta / max(wr_ios_delta, 1), 2)

        # IOPS from sysfs (crosscheck with iostat)
        rd_iops_sysfs = round(rd_ios_delta / dt, 1)
        wr_iops_sysfs = round(wr_ios_delta / dt, 1)

        # Bandwidth from the sector counters, in MB/s of 2^20 bytes -- the
        # unit the other block-layer series in amoprof use (queue_depth,
        # writer's per-sample rates).
        rd_sec_delta = max(last.get("rd_sectors", 0) - first.get("rd_sectors", 0), 0)
        wr_sec_delta = max(last.get("wr_sectors", 0) - first.get("wr_sectors", 0), 0)
        rd_bw_mbs_sysfs = round(rd_sec_delta * 512 / dt / 1048576, 3)
        wr_bw_mbs_sysfs = round(wr_sec_delta * 512 / dt / 1048576, 3)

        # Device utilisation % from sysfs (ms spent / wall ms)
        util_pct = round(min(io_ms_delta / (dt * 10), 100), 1)

        # Mean inflight queue depth
        inflight_vals = [s["inflight"] for s in self._samples if "inflight" in s]
        inflight_mean = round(statistics.mean(inflight_vals), 2) if inflight_vals else 0.0
        inflight_peak = max(inflight_vals) if inflight_vals else 0
        inflight_sorted = sorted(inflight_vals)
        def _pct(vals, pct):
            if not vals:
                return 0.0
            idx = min(max(int(len(vals) * pct / 100.0), 0), len(vals)-1)
            return round(vals[idx], 2)

        # /sys/block/<dev>/stat column 10 is a time-weighted queue depth source:
        # avg_qd = Δweighted_io_ms / Δwall_ms.
        weighted_delta_ms = max(float(last.get("weighted_io_ms", 0)) - float(first.get("weighted_io_ms", 0)), 0.0)
        weighted_qd_mean = round(weighted_delta_ms / max(dt * 1000.0, 1e-6), 3)

        return {
            "nvme_driver_available":  True,
            # A2 io_uring/NVMe Driver metrics
            "nvme_rd_iops_sysfs":     rd_iops_sysfs,
            "nvme_wr_iops_sysfs":     wr_iops_sysfs,
            "nvme_rd_bw_mbs_sysfs":   rd_bw_mbs_sysfs,
            "nvme_wr_bw_mbs_sysfs":   wr_bw_mbs_sysfs,
            "nvme_rd_bytes_total":    rd_sec_delta * 512,
            "nvme_wr_bytes_total":    wr_sec_delta * 512,
            "nvme_rd_lat_ms_mean":    rd_lat_ms,
            "nvme_wr_lat_ms_mean":    wr_lat_ms,
            "nvme_inflight_mean":     inflight_mean,
            "nvme_inflight_p50":      _pct(inflight_sorted, 50),
            "nvme_inflight_p95":      _pct(inflight_sorted, 95),
            "nvme_inflight_p99":      _pct(inflight_sorted, 99),
            "nvme_inflight_peak":     inflight_peak,
            "nvme_weighted_qd_mean":  weighted_qd_mean,
            "nvme_util_pct_sysfs":    util_pct,
            "queue_depth_sources":    "sysfs_stat_inflight,sysfs_stat_weighted_io_ms,sysfs_inflight,sysfs_queue",
            # Queue parameters (A2 layer config)
            "nvme_nr_requests":       qp.get("nr_requests", 0),
            "nvme_scheduler":         qp.get("scheduler", "unknown"),
            "nvme_physical_block_b":  qp.get("physical_block_size_b", 0),
            "nvme_logical_block_b":   qp.get("logical_block_size_b", 0),
            "nvme_inflight_reads":    qp.get("inflight_reads", 0),
            "nvme_inflight_writes":   qp.get("inflight_writes", 0),
        }
