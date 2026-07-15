"""GpuMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.gpu")


@register_collector
class GpuMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='gpu',
        layer=AIStackLayer.A4_GPU_HBM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='nvidia-smi/DCGM GPU utilization, HBM occupancy, temp',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0))

    """
    Polls nvidia-smi for per-GPU:
      utilisation (%), HBM used/total (MB), power draw (W), temperature (°C)
    Aggregates to mean/peak across all GPUs.
    """

    def __init__(self, interval_s: float = 1.0):
        self.interval = interval_s
        self.samples: list[dict] = []
        self._thread = None
        self._stop   = threading.Event()

    def _has_gpu(self) -> bool:
        try:
            subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def _gpu_count(self) -> int:
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                stderr=subprocess.DEVNULL, text=True)
            return len(out.strip().splitlines())
        except Exception:
            return 0

    def start(self):
        if not self._has_gpu():
            return
        self._stop.clear()
        self.samples.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,utilization.gpu,utilization.memory,"
            "memory.used,memory.total,power.draw,temperature.gpu",
            "--format=csv,noheader,nounits",
            f"--loop-ms={int(self.interval * 1000)}",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True)
            for line in proc.stdout:
                if self._stop.is_set():
                    proc.terminate()
                    break
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 7:
                    try:
                        self.samples.append({
                            "gpu_idx":   int(p[0]),
                            "gpu_util":  float(p[1]),
                            "mem_util":  float(p[2]),
                            "mem_used":  float(p[3]),
                            "mem_total": float(p[4]),
                            "power":     float(p[5]) if p[5] != "N/A" else 0.0,
                            "temp_c":    float(p[6]) if p[6] != "N/A" else 0.0,
                        })
                    except ValueError:
                        pass
        except FileNotFoundError:
            pass

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if not self.samples:
            return {"gpu_available": False}

        def m(k):  return round(statistics.mean(s[k] for s in self.samples), 2)
        def pk(k): return round(max(s[k] for s in self.samples), 2)

        gpu_indices = sorted(set(s["gpu_idx"] for s in self.samples))
        n_gpus      = len(gpu_indices)

        # Per-GPU peak HBM used (MB) and mean utilisation
        per_hbm_peak = []
        per_gpu_util = []
        for idx in gpu_indices:
            gs = [s for s in self.samples if s["gpu_idx"] == idx]
            if gs:
                per_hbm_peak.append(round(max(s["mem_used"] for s in gs), 0))
                per_gpu_util.append(round(statistics.mean(s["gpu_util"] for s in gs), 1))

        all_mem_used  = [s["mem_used"]  for s in self.samples]
        all_mem_total = [s["mem_total"] for s in self.samples]
        total_hbm_gb  = round(all_mem_total[0] / 1024 * n_gpus, 1) if all_mem_total else 0
        peak_hbm_used_all_gb = round(sum(per_hbm_peak) / 1024, 2) if per_hbm_peak else 0

        return {
            "gpu_available":          True,
            "gpu_count":              n_gpus,
            # Utilisation
            "gpu_util_mean":          m("gpu_util"),
            "gpu_util_peak":          pk("gpu_util"),
            "gpu_util_per_gpu":       per_gpu_util,
            # HBM (GPU memory)
            "hbm_util_mean":          m("mem_util"),
            "hbm_used_mb_mean":       m("mem_used"),
            "hbm_used_mb_peak":       pk("mem_used"),
            "hbm_used_gb_peak_all":   peak_hbm_used_all_gb,
            "hbm_total_mb_per_gpu":   round(statistics.mean(all_mem_total), 0) if all_mem_total else 0,
            "hbm_total_gb_all":       total_hbm_gb,
            "hbm_util_pct_mean":      round(m("mem_used") / max(statistics.mean(all_mem_total), 1) * 100, 1),
            "hbm_per_gpu_peak_mb":    per_hbm_peak,
            # Power
            "power_w_mean":           m("power"),
            "power_w_peak":           pk("power"),
            "power_all_gpus_w_mean":  round(m("power") * n_gpus, 1),
            # Temperature
            "gpu_temp_mean_c":        m("temp_c"),
            "gpu_temp_peak_c":        pk("temp_c"),
        }
