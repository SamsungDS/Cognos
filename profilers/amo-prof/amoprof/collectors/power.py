"""PowerMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.power")


@register_collector
class PowerMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='power',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='System power via nvidia-smi/dcgmi + RAPL + IPMI',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0), use_sudo=ctx.get('use_sudo', True))

    """
    Records system power consumption from every available source during a
    workload run and returns a unified power summary.

    Sources probed (in priority order per domain):

    GPU power
      • nvidia-smi  per-GPU power.draw + power.limit  (primary)
      • dcgmi dmon  per-GPU power counters            (DGX fallback)

    CPU / package power  (RAPL — Running Average Power Limit)
      • /sys/class/powercap/intel-rapl/*/energy_uj    (Intel, read directly)
      • /sys/class/powercap/intel-rapl-mmio/*/energy_uj (alternate path)
      • perf stat -e power/energy-pkg/               (fallback)

    DRAM power  (RAPL)
      • /sys/class/powercap/intel-rapl/*/intel-rapl:*/energy_uj  (sub-domain)

    System / PSU power
      • ipmitool dcmi power reading                  (BMC, most accurate)
      • ipmitool sdr type "Power Supply"             (PSU rails fallback)

    Metrics reported
    ─────────────────────────────────────────────────────────────────────
    gpu_power_w_mean / _peak / _total_wh             per-GPU average / peak / energy
    gpu_power_all_w_mean                             sum across all GPUs
    cpu_package_power_w_mean / _total_wh             CPU package (RAPL)
    dram_power_w_mean / _total_wh                    DRAM subsystem (RAPL)
    system_power_w_mean / _peak / _total_wh          BMC/IPMI total chassis
    total_system_power_w_mean                        gpu + cpu + dram combined estimate
    power_efficiency_tok_per_wh                      tokens / watt-hour (if tok count known)
    power_sources                                    comma list of active sources
    """

    _RAPL_BASE = "/sys/class/powercap"

    def __init__(self, interval_s: float = 1.0, use_sudo: bool = True):
        self.interval    = interval_s
        self.use_sudo   = use_sudo
        self.samples: list[dict] = []
        self._t_start    = 0.0
        self._t_end      = 0.0
        self._rapl_start: dict[str, int] = {}
        self._rapl_end:   dict[str, int] = {}
        self._thread     = None
        self._stop       = threading.Event()
        self._sources: list[str] = []

    # ── Source detection ──────────────────────────────────────────────────────

    def _has_nvidia(self) -> bool:
        try:
            subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def _has_dcgmi(self) -> bool:
        try:
            subprocess.check_output(["dcgmi", "version"], stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def _has_ipmi(self) -> bool:
        try:
            _sudo_check_output(
                ["ipmitool", "dcmi", "power", "reading"], self.use_sudo,
                stderr=subprocess.DEVNULL, timeout=5)
            return True
        except Exception:
            return False

    def _rapl_paths(self) -> dict[str, str]:
        """Return {domain_label: energy_uj_path} for all readable RAPL domains."""
        paths: dict[str, str] = {}
        for base in [self._RAPL_BASE + "/intel-rapl",
                     self._RAPL_BASE + "/intel-rapl-mmio"]:
            base_p = Path(base)
            if not base_p.exists():
                continue
            for zone in sorted(base_p.iterdir()):
                ename = zone / "name"
                epath = zone / "energy_uj"
                if not epath.exists():
                    continue
                try:
                    label = ename.read_text().strip() if ename.exists() else zone.name
                    paths[label] = str(epath)
                except Exception:
                    pass
                # sub-domains (DRAM, uncore, etc.)
                for sub in zone.iterdir():
                    sub_e = sub / "energy_uj"
                    sub_n = sub / "name"
                    if sub_e.exists():
                        try:
                            slabel = (sub_n.read_text().strip()
                                      if sub_n.exists() else sub.name)
                            paths[f"{label}/{slabel}"] = str(sub_e)
                        except Exception:
                            pass
        return paths

    def _read_rapl_uj(self, paths: dict[str, str]) -> dict[str, int]:
        out = {}
        for label, path in paths.items():
            try:
                out[label] = int(Path(path).read_text().strip())
            except Exception:
                out[label] = 0
        return out

    def _rapl_to_watts(self, start: dict[str, int], end: dict[str, int],
                       elapsed_s: float) -> dict[str, float]:
        """Convert RAPL energy delta (µJ) to average power (W)."""
        watts: dict[str, float] = {}
        if elapsed_s <= 0:
            return watts
        for k in start:
            if k in end:
                delta_uj = end[k] - start[k]
                # Handle counter wrap (max ~2^32 µJ on older CPUs)
                if delta_uj < 0:
                    try:
                        max_uj = int(Path(str(Path(self._rapl_paths().get(k,""))
                                            .parent / "max_energy_range_uj")
                                         ).read_text().strip())
                        delta_uj += max_uj
                    except Exception:
                        delta_uj = abs(delta_uj)
                watts[k] = round(delta_uj / 1e6 / elapsed_s, 2)
        return watts

    # ── nvidia-smi polling (background thread) ────────────────────────────────

    def _poll_nvidia(self):
        """Poll all GPUs: index,power.draw,power.limit per sample."""
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,power.draw,power.limit,temperature.gpu",
            "--format=csv,noheader,nounits",
            f"--loop-ms={int(self.interval * 1000)}",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            for line in proc.stdout:
                if self._stop.is_set():
                    proc.terminate()
                    break
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    try:
                        self.samples.append({
                            "ts":         time.time(),
                            "source":     "nvidia-smi",
                            "gpu_index":  int(parts[0]),
                            "gpu_power":  float(parts[1]) if parts[1] != "N/A" else 0.0,
                            "gpu_limit":  float(parts[2]) if parts[2] != "N/A" else 0.0,
                            "gpu_temp_c": float(parts[3]) if len(parts) > 3 and parts[3] != "N/A" else 0.0,
                        })
                    except ValueError:
                        pass
        except FileNotFoundError:
            pass

    def _poll_ipmi(self):
        """Poll IPMI system power every ~5 seconds (slow command)."""
        while not self._stop.wait(5.0):
            try:
                out = _sudo_check_output(
                    ["ipmitool", "dcmi", "power", "reading"], self.use_sudo,
                    stderr=subprocess.DEVNULL, timeout=8, text=True)
                for line in out.splitlines():
                    # "Instantaneous power reading:                   450 Watts"
                    if "Instantaneous" in line and "Watts" in line:
                        w = float(re.search(r"([\d.]+)\s+Watts", line).group(1))
                        self.samples.append({
                            "ts": time.time(), "source": "ipmi", "system_power": w})
                        break
            except Exception:
                break   # stop polling if IPMI becomes unavailable

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self):
        self._stop.clear()
        self.samples.clear()
        self._sources.clear()
        self._t_start = time.time()

        # Snapshot RAPL energy counters before workload
        self._rapl_paths_map = self._rapl_paths()
        if self._rapl_paths_map:
            self._rapl_start = self._read_rapl_uj(self._rapl_paths_map)
            self._sources.append("rapl")

        threads = []

        if self._has_nvidia():
            self._sources.append("nvidia-smi")
            t = threading.Thread(target=self._poll_nvidia, daemon=True)
            t.start(); threads.append(t)

        if self._has_ipmi():
            self._sources.append("ipmi")
            t = threading.Thread(target=self._poll_ipmi, daemon=True)
            t.start(); threads.append(t)

        self._threads = threads

    def stop(self, tokens_generated: int = 0) -> dict:
        self._stop.set()
        for t in getattr(self, "_threads", []):
            t.join(timeout=10)

        self._t_end = time.time()
        elapsed_s = max(self._t_end - self._t_start, 0.001)

        result: dict = {
            "power_sources":            ",".join(self._sources) or "none",
            "power_elapsed_s":          round(elapsed_s, 2),
        }

        # ── GPU power (nvidia-smi) ────────────────────────────────────────
        gpu_samples = [s for s in self.samples if s.get("source") == "nvidia-smi"]
        if gpu_samples:
            # Group by GPU index
            gpu_indices = sorted(set(s["gpu_index"] for s in gpu_samples))
            per_gpu_mean = []
            per_gpu_peak = []
            per_gpu_limit = []
            per_gpu_temp  = []
            for idx in gpu_indices:
                gs = [s["gpu_power"] for s in gpu_samples if s["gpu_index"] == idx]
                ts = [s["gpu_temp_c"] for s in gpu_samples if s["gpu_index"] == idx]
                ls = [s["gpu_limit"]  for s in gpu_samples if s["gpu_index"] == idx]
                if gs:
                    per_gpu_mean.append(round(statistics.mean(gs), 2))
                    per_gpu_peak.append(round(max(gs), 2))
                    per_gpu_limit.append(round(statistics.mean(ls), 2))
                    per_gpu_temp.append(round(max(ts), 1) if ts else 0.0)

            all_gpu_power = [s["gpu_power"] for s in gpu_samples]
            gpu_all_mean  = round(sum(
                statistics.mean(s["gpu_power"] for s in gpu_samples
                                if s["gpu_index"] == idx)
                for idx in gpu_indices), 2)

            result.update({
                "gpu_count":                  len(gpu_indices),
                "gpu_power_w_mean":           round(statistics.mean(all_gpu_power), 2),
                "gpu_power_w_peak":           round(max(all_gpu_power), 2),
                "gpu_power_all_w_mean":       gpu_all_mean,
                "gpu_power_limit_w":          round(statistics.mean(per_gpu_limit), 2) if per_gpu_limit else 0.0,
                "gpu_utilisation_pct":        round(gpu_all_mean / max(sum(per_gpu_limit), 1) * 100, 1),
                "gpu_temp_peak_c":            max(per_gpu_temp) if per_gpu_temp else 0.0,
                # Energy = mean_power_W × duration_h
                "gpu_energy_wh":              round(gpu_all_mean * elapsed_s / 3600, 4),
                "gpu_power_per_gpu_mean_w":   per_gpu_mean,
                "gpu_power_per_gpu_peak_w":   per_gpu_peak,
            })

        # ── CPU + DRAM power (RAPL) ───────────────────────────────────────
        if self._rapl_paths_map:
            self._rapl_end = self._read_rapl_uj(self._rapl_paths_map)
            rapl_w = self._rapl_to_watts(self._rapl_start, self._rapl_end, elapsed_s)

            # Aggregate: "package-N" → CPU, "dram" → DRAM
            cpu_watts  = [w for k, w in rapl_w.items()
                          if "package" in k.lower() and "dram" not in k.lower()]
            dram_watts = [w for k, w in rapl_w.items() if "dram" in k.lower()]

            cpu_total  = round(sum(cpu_watts),  2)
            dram_total = round(sum(dram_watts), 2)

            result.update({
                "cpu_package_power_w_mean":   cpu_total,
                "cpu_package_energy_wh":      round(cpu_total * elapsed_s / 3600, 4),
                "dram_power_w_mean":          dram_total,
                "dram_energy_wh":             round(dram_total * elapsed_s / 3600, 4),
                "rapl_domains":               list(rapl_w.keys()),
                "rapl_power_w":               {k: v for k, v in rapl_w.items()},
            })

        # ── System power (IPMI) ───────────────────────────────────────────
        ipmi_samples = [s["system_power"] for s in self.samples
                        if s.get("source") == "ipmi"]
        if ipmi_samples:
            sys_mean = round(statistics.mean(ipmi_samples), 2)
            sys_peak = round(max(ipmi_samples), 2)
            result.update({
                "system_power_w_mean":        sys_mean,
                "system_power_w_peak":        sys_peak,
                "system_energy_wh":           round(sys_mean * elapsed_s / 3600, 4),
            })

        # ── Combined total estimate ───────────────────────────────────────
        # Prefer IPMI (measures everything). Fallback: GPU + CPU + DRAM.
        if ipmi_samples:
            total_w = result.get("system_power_w_mean", 0.0)
        else:
            total_w = round(
                result.get("gpu_power_all_w_mean", 0.0) +
                result.get("cpu_package_power_w_mean", 0.0) +
                result.get("dram_power_w_mean", 0.0), 2)

        result["total_system_power_w_mean"] = total_w
        result["total_system_energy_wh"]    = round(total_w * elapsed_s / 3600, 4)

        # ── Power efficiency: tokens per watt-hour ────────────────────────
        if tokens_generated > 0 and total_w > 0:
            energy_wh = total_w * elapsed_s / 3600
            result["power_efficiency_tok_per_wh"] = (
                round(tokens_generated / energy_wh, 2) if energy_wh > 0 else 0.0)
        else:
            result["power_efficiency_tok_per_wh"] = 0.0

        return result
