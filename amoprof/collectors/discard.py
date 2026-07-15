"""DiscardStatsMonitor — extracted from collectors_extra.py into its own module.

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

log = logging.getLogger("amoprof.collectors.discard")


@register_collector
class DiscardStatsMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='discard',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='TRIM/discard time-series from /proc/diskstats (per-device)',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device,
                   ctx.get('interval_s', 1.0),
                   work_dir=ctx.get('raw_dir', '.'),
                   filename_suffix=ctx.get('filename_suffix', ''))

    """
    Time-series of TRIM/discard activity from /proc/diskstats.

    /proc/diskstats columns (Linux ≥4.18, fields 14-17 are discard fields):
        major minor name
        14: discards completed
        15: discards merged
        16: sectors discarded
        17: time spent discarding (ms)

    Plus we mirror the read/write columns (4-13) so we can compute the
    read/write/discard ratio in one place.

    Output: <work_dir>/discard_timeseries.csv per-sample row.
    Summary: discard_iops, discard_bw_mb_s, discard_present (bool).
    """

    def __init__(self, device: str, interval_s: float = 1.0,
                 work_dir: "Path | str" = ".", filename_suffix: str = ""):
        self.device_name = os.path.basename(device)
        self.interval = max(float(interval_s), 0.1)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()
        self._thread = None
        self._samples: list[dict] = []
        _sfx = ("_" + filename_suffix) if filename_suffix else ""
        self._csv_path = self.work_dir / ("discard_timeseries" + _sfx + ".csv")

    def _read_diskstats(self) -> dict | None:
        try:
            with open("/proc/diskstats") as f:
                for line in f:
                    p = line.split()
                    if len(p) < 14:
                        continue
                    if p[2] != self.device_name:
                        continue
                    # Reads:  p[3]=completed, p[5]=sectors, p[6]=ms
                    # Writes: p[7]=completed, p[9]=sectors, p[10]=ms
                    # Discards: p[14]=completed, p[15]=merged, p[16]=sectors, p[17]=ms
                    rec = {
                        "ts":              time.time(),
                        "rd_completed":    int(p[3]),
                        "rd_sectors":      int(p[5]),
                        "rd_ms":           int(p[6]),
                        "wr_completed":    int(p[7]),
                        "wr_sectors":      int(p[9]),
                        "wr_ms":           int(p[10]),
                    }
                    if len(p) >= 18:
                        rec["disc_completed"] = int(p[14])
                        rec["disc_merged"]    = int(p[15])
                        rec["disc_sectors"]   = int(p[16])
                        rec["disc_ms"]        = int(p[17])
                    else:
                        rec["disc_completed"] = 0
                        rec["disc_merged"]    = 0
                        rec["disc_sectors"]   = 0
                        rec["disc_ms"]        = 0
                    return rec
        except Exception as e:
            log.debug("DiscardStatsMonitor: %s", e)
        return None

    def start(self):
        self._stop.clear()
        self._samples.clear()
        s = self._read_diskstats()
        if s is not None:
            self._samples.append(s)
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = self._read_diskstats()
            if s is not None:
                self._samples.append(s)

    def stop(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        s = self._read_diskstats()
        if s is not None:
            self._samples.append(s)

        if len(self._samples) < 2:
            return {"discard_available": False,
                    "discard_reason": f"no diskstats samples for {self.device_name}"}

        # Write per-interval rate CSV
        rates = []
        with open(self._csv_path, "w", encoding="utf-8", newline="") as fp:
            w = _csv.writer(fp)
            w.writerow([
                "ts", "rd_iops", "rd_mb_s",
                       "wr_iops", "wr_mb_s",
                       "discard_iops", "discard_mb_s", "discard_avg_ms",
            ])
            for i in range(1, len(self._samples)):
                a, b = self._samples[i-1], self._samples[i]
                dt = max(b["ts"] - a["ts"], 1e-6)
                rd_iops = max(b["rd_completed"]   - a["rd_completed"],   0) / dt
                wr_iops = max(b["wr_completed"]   - a["wr_completed"],   0) / dt
                dc_iops = max(b["disc_completed"] - a["disc_completed"], 0) / dt
                rd_mb_s = max(b["rd_sectors"]     - a["rd_sectors"],     0) * 512 / 1024 / 1024 / dt
                wr_mb_s = max(b["wr_sectors"]     - a["wr_sectors"],     0) * 512 / 1024 / 1024 / dt
                dc_mb_s = max(b["disc_sectors"]   - a["disc_sectors"],   0) * 512 / 1024 / 1024 / dt
                dc_dms  = max(b["disc_ms"]        - a["disc_ms"],        0)
                dc_avg  = (dc_dms / max(b["disc_completed"] - a["disc_completed"], 1)
                           if (b["disc_completed"] - a["disc_completed"]) > 0 else 0.0)
                rates.append({
                    "rd_iops": rd_iops, "wr_iops": wr_iops, "dc_iops": dc_iops,
                    "rd_mb_s": rd_mb_s, "wr_mb_s": wr_mb_s, "dc_mb_s": dc_mb_s,
                })
                w.writerow([round(b["ts"], 3),
                            round(rd_iops, 2), round(rd_mb_s, 3),
                            round(wr_iops, 2), round(wr_mb_s, 3),
                            round(dc_iops, 2), round(dc_mb_s, 3),
                            round(dc_avg, 3)])

        def _mean(key):
            vals = [r[key] for r in rates]
            return sum(vals) / max(len(vals), 1) if vals else 0.0

        def _peak(key):
            vals = [r[key] for r in rates]
            return max(vals) if vals else 0.0

        # Total discards (sectors → bytes)
        total_disc_sectors = max(self._samples[-1]["disc_sectors"]
                                 - self._samples[0]["disc_sectors"], 0)
        total_disc_bytes = total_disc_sectors * 512
        total_disc_ops = max(self._samples[-1]["disc_completed"]
                             - self._samples[0]["disc_completed"], 0)
        discard_present = total_disc_ops > 0

        return {
            "discard_available":   True,
            "discard_present":     discard_present,
            "discard_csv":         str(self._csv_path),
            "discard_total_ops":   total_disc_ops,
            "discard_total_bytes": total_disc_bytes,
            "discard_iops_mean":   round(_mean("dc_iops"), 2),
            "discard_iops_peak":   round(_peak("dc_iops"), 2),
            "discard_bw_mb_s_mean": round(_mean("dc_mb_s"), 3),
            "discard_bw_mb_s_peak": round(_peak("dc_mb_s"), 3),
            # rd/wr summaries for completeness — analysis layer may use either
            # these or iostat's; here we expose them as discard collector by-product.
            "diskstats_rd_iops_mean": round(_mean("rd_iops"), 2),
            "diskstats_wr_iops_mean": round(_mean("wr_iops"), 2),
            "diskstats_rd_mb_s_mean": round(_mean("rd_mb_s"), 3),
            "diskstats_wr_mb_s_mean": round(_mean("wr_mb_s"), 3),
        }
