"""VmstatMonitor — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.vmstat")


@register_collector
class VmstatMonitor(BaseCollector):
    SPEC = CollectorSpec(
        name='vmstat',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=False,
        enable_flag='',
        description='/proc/vmstat swap in/out, page faults, alloc stats',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(ctx.get('interval_s', 1.0))

    """
    Polls /proc/vmstat for OS/Memory Manager metrics (A3 L2=DRAM layer).

    Captures per-interval deltas for:
      pgfault          — minor page faults (KV$ mmap accesses)
      pgmajfault       — major page faults (page not in RAM → disk fetch)
      pswpin/pswpout   — swap in/out pages (KV$ overflow to swap)
      pgpgin/pgpgout   — page cache reads/writes (filesystem I/O through cache)
      numa_pages_migrated — NUMA page migrations (cross-socket KV$ movement)
      nr_tlb_remote_cache_miss — TLB misses (indirect measure of KV$ scatter)
    """

    KEYS = [
        "pgfault", "pgmajfault",
        "pswpin",  "pswpout",
        "pgpgin",  "pgpgout",
        "numa_pages_migrated", "numa_hint_faults",
        "nr_tlb_remote_cache_miss",
        "oom_kill",
    ]

    def __init__(self, interval_s: float = 1.0):
        self.interval = interval_s
        self._samples: list[dict] = []
        self._thread  = None
        self._stop    = threading.Event()

    def _read(self) -> dict:
        out = {}
        try:
            for line in open("/proc/vmstat").read().splitlines():
                p = line.split()
                if len(p) == 2 and p[0] in self.KEYS:
                    out[p[0]] = int(p[1])
        except Exception:
            pass
        return out

    def start(self):
        self._stop.clear()
        self._samples.clear()
        s = self._read()
        s["_ts"] = time.time()   # always record timestamp
        self._samples.append(s)
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = self._read()
            s["_ts"] = time.time()
            self._samples.append(s)

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        s = self._read()
        s["_ts"] = time.time()
        self._samples.append(s)

        if len(self._samples) < 2 or not any(
                k in self._samples[0] for k in ("pgfault", "pswpin")):
            return {"vmstat_available": False}

        first, last = self._samples[0], self._samples[-1]
        dt = max(last["_ts"] - first["_ts"], 0.001)

        def rate(k):
            delta = last.get(k, 0) - first.get(k, 0)
            return round(max(delta, 0) / dt, 2)

        def total(k):
            return max(last.get(k, 0) - first.get(k, 0), 0)

        # Huge pages from /proc/meminfo
        huge_total = huge_free = huge_size_kb = 0
        try:
            for line in open("/proc/meminfo").read().splitlines():
                p = line.split()
                if p[0] == "HugePages_Total:":  huge_total  = int(p[1])
                if p[0] == "HugePages_Free:":   huge_free   = int(p[1])
                if p[0] == "Hugepagesize:":      huge_size_kb = int(p[1])
        except Exception:
            pass

        return {
            "vmstat_available":          True,
            # A3 OS/Memory Manager — page fault metrics
            "page_faults_per_s":         rate("pgfault"),
            "major_faults_per_s":        rate("pgmajfault"),
            "page_faults_total":         total("pgfault"),
            "major_faults_total":        total("pgmajfault"),
            # Swap (KV$ swap rate proxy)
            "swap_in_per_s":             rate("pswpin"),
            "swap_out_per_s":            rate("pswpout"),
            "swap_pages_total":          total("pswpin") + total("pswpout"),
            # Page cache I/O
            "page_cache_reads_per_s":    rate("pgpgin"),
            "page_cache_writes_per_s":   rate("pgpgout"),
            # NUMA
            "numa_migrations_per_s":     rate("numa_pages_migrated"),
            "numa_hint_faults_per_s":    rate("numa_hint_faults"),
            # TLB
            "tlb_remote_miss_per_s":     rate("nr_tlb_remote_cache_miss"),
            # OOM
            "oom_kills":                 total("oom_kill"),
            # Huge pages (static snapshot)
            "hugepages_total":           huge_total,
            "hugepages_free":            huge_free,
            "hugepages_used":            huge_total - huge_free,
            "hugepage_size_kb":          huge_size_kb,
        }
