"""BlockQueueDepthCollector — extracted from collectors.py into its own module.

Part of the amoprof.collectors package.  Registers itself via
@register_collector at import time (populates CollectorRegistry).
"""
from __future__ import annotations

import csv
# Some call sites in this module reference `_csv`; alias it so a
# NameError cannot surface at runtime inside a try/except and be
# reported as a parse failure rather than a missing import.
_csv = csv
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

log = logging.getLogger("amoprof.collectors.queue_depth")


@register_collector
class BlockQueueDepthCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='queue_depth_sysfs',
        layer=AIStackLayer.A2_NVME_DRIVER,
        is_ssd_scoped=True,
        optional=False,
        enable_flag='',
        description='multi-source sampled queue-depth: sysfs stat inflight + weighted delta',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(device,
                   ctx.get('interval_s', 1.0),
                   work_dir=ctx.get('raw_dir', '.'),
                   filename_suffix=ctx.get('filename_suffix', ''))

    """
    Capture queue-depth related metrics from every cheap local kernel source.

    Sources sampled every interval:
      • /sys/block/<dev>/stat field 9  -> instantaneous in-flight I/O
      • /sys/block/<dev>/stat field 10 -> cumulative device busy ticks
      • /sys/block/<dev>/stat field 11 -> cumulative weighted time in queue
      • /sys/block/<dev>/inflight      -> read/write in-flight split
      • /sys/block/<dev>/queue/*       -> queue limits/config
      • /proc/diskstats                -> same kernel counters via proc fallback

    Exact event-level queue depth still comes from blktrace Q→C analysis when
    --enable-blktrace is used. This collector provides always-on sampled
    advisory sampled queue pressure so the report has data even when exact blktrace Q/C parsing is
    missing or intentionally disabled. Cumulative sysfs fields are used only as run-window deltas, never as absolute point values.
    """

    def __init__(self, device: str, interval_s: float = 1.0, work_dir: "Path | str" = ".",
                 filename_suffix: str = ""):
        self.device = device
        self.dev = os.path.basename(device)
        # If the user passes a partition, queue stats live under the parent disk.
        self.base_dev = re.sub(r"p\d+$", "", self.dev)
        self.interval = max(float(interval_s or 1.0), 0.1)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._samples: list[dict] = []
        self._derived: list[dict] = []
        self._thread = None
        self._stop = threading.Event()
        _sfx = ("_" + filename_suffix) if filename_suffix else ""
        self._csv_path = self.work_dir / ("queue_depth_sources_timeseries" + _sfx + ".csv")

    def _read_queue_params(self) -> dict:
        out = {}
        qdir = Path(f"/sys/block/{self.base_dev}/queue")
        for name in (
            "nr_requests", "scheduler", "nomerges", "rq_affinity",
            "rotational", "max_sectors_kb", "max_hw_sectors_kb",
            "logical_block_size", "physical_block_size", "minimum_io_size",
            "optimal_io_size", "io_poll", "io_poll_delay",
        ):
            p = qdir / name
            try:
                v = p.read_text().strip()
                out[f"queue_{name}"] = int(v) if re.fullmatch(r"-?\d+", v or "") else v
            except Exception:
                pass
        return out

    def _nr_hw_queues(self) -> int:
        try:
            mq = Path(f"/sys/block/{self.base_dev}/mq")
            return len([p for p in mq.iterdir() if p.is_dir()]) if mq.exists() else 1
        except Exception:
            return 1

    def _fallback_qd_plausibility_limit(self, row: dict | None = None) -> float:
        """Conservative sanity bound for sampled/fallback queue-depth values.

        This is not a saturation threshold. It only prevents cumulative sysfs
        counter/unit mistakes from being promoted into QD values.  Exact
        blktrace Q->C analysis does not use this helper.
        """
        row = row or {}
        try:
            nr_req = float(row.get("queue_nr_requests", 0) or 0)
        except Exception:
            nr_req = 0.0
        nr_hwq = float(row.get("nr_hw_queues", 0) or self._nr_hw_queues() or 1)
        # Many NVMe drivers expose nr_requests per hardware queue. Allow headroom
        # for transient samples but reject values orders-of-magnitude above the
        # configured queueing capacity.
        base = nr_req * max(nr_hwq, 1.0) if nr_req > 0 else 4096.0
        return max(128.0, min(base * 4.0, 262144.0))

    def _read_inflight(self) -> dict:
        out = {}
        for dev in (self.dev, self.base_dev):
            p = Path(f"/sys/block/{dev}/inflight")
            if p.exists():
                try:
                    vals = p.read_text().split()
                    if len(vals) >= 2:
                        out["sysfs_inflight_reads"] = int(vals[0])
                        out["sysfs_inflight_writes"] = int(vals[1])
                        out["sysfs_inflight_total_split"] = int(vals[0]) + int(vals[1])
                        out["sysfs_inflight_source_dev"] = dev
                        return out
                except Exception:
                    pass
        return out

    def _read_stat_file(self) -> dict:
        for dev in (self.dev, self.base_dev):
            p = Path(f"/sys/block/{dev}/stat")
            if p.exists():
                try:
                    raw = p.read_text().split()
                    if len(raw) >= 11:
                        return {
                            "stat_source": f"/sys/block/{dev}/stat",
                            "rd_ios": int(raw[0]),
                            "rd_merges": int(raw[1]),
                            "rd_sectors": int(raw[2]),
                            "rd_ms": int(raw[3]),
                            "wr_ios": int(raw[4]),
                            "wr_merges": int(raw[5]),
                            "wr_sectors": int(raw[6]),
                            "wr_ms": int(raw[7]),
                            "stat_inflight": int(raw[8]),
                            "io_ticks_ms": int(raw[9]),
                            "weighted_io_ms": int(raw[10]),
                            "discard_ios": int(raw[11]) if len(raw) > 11 else 0,
                            "discard_sectors": int(raw[13]) if len(raw) > 13 else 0,
                            "discard_ms": int(raw[14]) if len(raw) > 14 else 0,
                        }
                except Exception:
                    pass
        return {}

    def _read_proc_diskstats(self) -> dict:
        try:
            with open("/proc/diskstats") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 14 and parts[2] in {self.dev, self.base_dev}:
                        return {
                            "proc_diskstats_dev": parts[2],
                            "proc_rd_ios": int(parts[3]),
                            "proc_rd_sectors": int(parts[5]),
                            "proc_rd_ms": int(parts[6]),
                            "proc_wr_ios": int(parts[7]),
                            "proc_wr_sectors": int(parts[9]),
                            "proc_wr_ms": int(parts[10]),
                            "proc_inflight": int(parts[11]) if len(parts) > 11 else 0,
                            "proc_io_ticks_ms": int(parts[12]) if len(parts) > 12 else 0,
                            "proc_weighted_io_ms": int(parts[13]) if len(parts) > 13 else 0,
                        }
        except Exception:
            pass
        return {}

    def _read(self) -> dict:
        row = {"ts": time.time(), "device": self.device, "dev": self.dev, "base_dev": self.base_dev}
        row.update(self._read_stat_file())
        row.update(self._read_inflight())
        row.update(self._read_proc_diskstats())
        row.update(self._read_queue_params())
        return row

    def start(self):
        self._stop.clear()
        self._samples.clear()
        self._derived.clear()
        self._samples.append(self._read())
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            self._samples.append(self._read())

    def _derive_rows(self) -> list[dict]:
        rows: list[dict] = []
        for i in range(1, len(self._samples)):
            a, b = self._samples[i-1], self._samples[i]
            dt = max(float(b.get("ts", 0)) - float(a.get("ts", 0)), 1e-6)
            wall_ms = dt * 1000.0
            d_io_ms = max(float(b.get("io_ticks_ms", b.get("proc_io_ticks_ms", 0))) -
                          float(a.get("io_ticks_ms", a.get("proc_io_ticks_ms", 0))), 0.0)
            d_weighted_ms = max(float(b.get("weighted_io_ms", b.get("proc_weighted_io_ms", 0))) -
                                float(a.get("weighted_io_ms", a.get("proc_weighted_io_ms", 0))), 0.0)
            d_rd_ios = max(float(b.get("rd_ios", b.get("proc_rd_ios", 0))) -
                           float(a.get("rd_ios", a.get("proc_rd_ios", 0))), 0.0)
            d_wr_ios = max(float(b.get("wr_ios", b.get("proc_wr_ios", 0))) -
                           float(a.get("wr_ios", a.get("proc_wr_ios", 0))), 0.0)
            d_rd_sec = max(float(b.get("rd_sectors", b.get("proc_rd_sectors", 0))) -
                           float(a.get("rd_sectors", a.get("proc_rd_sectors", 0))), 0.0)
            d_wr_sec = max(float(b.get("wr_sectors", b.get("proc_wr_sectors", 0))) -
                           float(a.get("wr_sectors", a.get("proc_wr_sectors", 0))), 0.0)
            d_rd_ms = max(float(b.get("rd_ms", b.get("proc_rd_ms", 0))) -
                          float(a.get("rd_ms", a.get("proc_rd_ms", 0))), 0.0)
            d_wr_ms = max(float(b.get("wr_ms", b.get("proc_wr_ms", 0))) -
                          float(a.get("wr_ms", a.get("proc_wr_ms", 0))), 0.0)
            sysfs_inflight = float(b.get("stat_inflight", b.get("proc_inflight", 0)) or 0)
            weighted_qd_raw = d_weighted_ms / max(wall_ms, 1e-6)
            row = {
                "ts": b.get("ts", 0),
                "device": self.device,
                "dev": self.dev,
                "base_dev": self.base_dev,
                "source": "sysfs_run_delta_advisory",
                "sysfs_inflight": sysfs_inflight,
                "sysfs_inflight_reads": float(b.get("sysfs_inflight_reads", 0) or 0),
                "sysfs_inflight_writes": float(b.get("sysfs_inflight_writes", 0) or 0),
                # Keep raw weighted QD for audit only. It is a per-run delta:
                # delta(weighted_io_ms) / delta(wall_ms). Never use the
                # cumulative weighted_io_ms absolute value as QD.
                "weighted_qd_raw": round(weighted_qd_raw, 4),
                "weighted_qd": round(weighted_qd_raw, 4),
                "d_weighted_io_ms": round(d_weighted_ms, 3),
                "d_io_ticks_ms": round(d_io_ms, 3),
                "wall_ms": round(wall_ms, 3),
                "io_util_pct": round(min(d_io_ms / max(wall_ms, 1e-6) * 100.0, 100.0), 3),
                "rd_iops": round(d_rd_ios / dt, 3),
                "wr_iops": round(d_wr_ios / dt, 3),
                "rd_bw_mbs": round(d_rd_sec * 512.0 / 1024.0 / 1024.0 / dt, 6),
                "wr_bw_mbs": round(d_wr_sec * 512.0 / 1024.0 / 1024.0 / dt, 6),
                "rd_lat_ms": round(d_rd_ms / max(d_rd_ios, 1.0), 4) if d_rd_ios > 0 else 0.0,
                "wr_lat_ms": round(d_wr_ms / max(d_wr_ios, 1.0), 4) if d_wr_ios > 0 else 0.0,
                "queue_nr_requests": b.get("queue_nr_requests", 0),
                "nr_hw_queues": b.get("nr_hw_queues", 1),
                "queue_scheduler": b.get("queue_scheduler", ""),
                "queue_nomerges": b.get("queue_nomerges", ""),
                "queue_max_sectors_kb": b.get("queue_max_sectors_kb", 0),
                "stat_start_weighted_io_ms": a.get("weighted_io_ms", a.get("proc_weighted_io_ms", 0)),
                "stat_end_weighted_io_ms": b.get("weighted_io_ms", b.get("proc_weighted_io_ms", 0)),
                "stat_start_io_ticks_ms": a.get("io_ticks_ms", a.get("proc_io_ticks_ms", 0)),
                "stat_end_io_ticks_ms": b.get("io_ticks_ms", b.get("proc_io_ticks_ms", 0)),
            }
            plaus_limit = self._fallback_qd_plausibility_limit(row)
            weighted_valid = 0.0 <= weighted_qd_raw <= plaus_limit
            inflight_valid = 0.0 <= sysfs_inflight <= plaus_limit
            row["fallback_qd_plausibility_limit"] = round(plaus_limit, 3)
            row["weighted_qd_valid"] = int(bool(weighted_valid))
            row["sysfs_inflight_valid"] = int(bool(inflight_valid))
            # Conservative best-effort QD for fallback reports:
            #   1. prefer instantaneous in-flight from /sys/block/<dev>/stat
            #      because it is not cumulative and cannot include previous runs;
            #   2. use weighted_qd only when it is a plausible run-window delta.
            # Fallback QD remains advisory and must not by itself prove saturation.
            if inflight_valid:
                row["qd_best_effort"] = round(sysfs_inflight, 4)
                row["qd_best_effort_source"] = "sysfs_stat_inflight_instantaneous"
                row["qd_valid"] = 1
            elif weighted_valid:
                row["qd_best_effort"] = round(weighted_qd_raw, 4)
                row["qd_best_effort_source"] = "sysfs_weighted_io_ms_run_delta_advisory"
                row["qd_valid"] = 1
            else:
                row["qd_best_effort"] = 0.0
                row["qd_best_effort_source"] = "invalid_sysfs_counter_delta_rejected"
                row["qd_valid"] = 0
            rows.append(row)
        return rows

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._samples.append(self._read())
        self._derived = self._derive_rows()

        # Write a canonical, multi-source queue-depth timeseries immediately so
        # analyze/report can consume it without needing to know collector internals.
        if self._derived:
            import csv as _csv
            fields = sorted({k for row in self._derived for k in row.keys()})
            with open(self._csv_path, "w", encoding="utf-8", newline="") as fp:
                w = _csv.DictWriter(fp, fieldnames=fields)
                w.writeheader()
                for row in self._derived:
                    w.writerow(row)

        valid_rows = [r for r in self._derived if int(float(r.get("qd_valid", 0) or 0)) == 1]
        qd_vals = [float(r.get("qd_best_effort", 0)) for r in valid_rows]
        weighted_vals = [float(r.get("weighted_qd", 0)) for r in self._derived
                         if int(float(r.get("weighted_qd_valid", 0) or 0)) == 1]
        inflight_vals = [float(r.get("sysfs_inflight", 0)) for r in self._derived
                         if int(float(r.get("sysfs_inflight_valid", 0) or 0)) == 1]
        util_vals = [float(r.get("io_util_pct", 0)) for r in self._derived]
        invalid_qd_rows = max(len(self._derived) - len(valid_rows), 0)
        def _mean(vals):
            return round(statistics.mean(vals), 4) if vals else 0.0
        def _pct(vals, pct):
            if not vals: return 0.0
            xs = sorted(vals)
            idx = min(max(int(len(xs) * pct / 100.0), 0), len(xs)-1)
            return round(xs[idx], 4)
        def _peak(vals):
            return round(max(vals), 4) if vals else 0.0

        return {
            "queue_depth_available": bool(qd_vals),
            "queue_depth_csv": str(self._csv_path) if self._derived else "",
            "queue_depth_samples": len(qd_vals),
            "queue_depth_rows_total": len(self._derived),
            "queue_depth_invalid_rows": invalid_qd_rows,
            "queue_depth_sources": "advisory_sysfs_run_delta_and_inflight",
            "queue_depth_validity": "run_window_delta_only_not_accumulated; fallback_advisory_not_saturation_proof",
            "queue_depth_mean": _mean(qd_vals),
            "queue_depth_p50": _pct(qd_vals, 50),
            "queue_depth_p95": _pct(qd_vals, 95),
            "queue_depth_p99": _pct(qd_vals, 99),
            "queue_depth_peak": _peak(qd_vals),
            "weighted_qd_mean": _mean(weighted_vals),
            "weighted_qd_peak": _peak(weighted_vals),
            "inflight_mean": _mean(inflight_vals),
            "inflight_peak": _peak(inflight_vals),
            "io_util_pct_mean": _mean(util_vals),
            "io_util_pct_peak": _peak(util_vals),
        }
