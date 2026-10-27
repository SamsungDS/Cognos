"""BpftraceCollector — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.bpftrace")


@register_collector
class BpftraceCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='bpf',
        layer=AIStackLayer.A4_GPU_HBM,
        is_ssd_scoped=False,
        is_pid_scoped=True,
        optional=True,
        enable_flag='pid',
        description='bpftrace uprobes on PID for syscall/latency traces',
    )
    @classmethod
    def for_pid(cls, pid: int, args, ctx: dict):
        return cls(pid, duration_s=max(int(ctx.get('duration_s', 60)), 1),
                   work_dir=ctx.get('raw_dir', '.'),
                   use_sudo=ctx.get('use_sudo', True))

    """
    Attaches bpftrace programs to the SGLang server PID and collects:

    bpf_available               bool
    bpf_page_faults_total       int    — minor + major page faults
    bpf_major_faults_total      int    — major faults (page not in RAM)
    bpf_mmap_calls              int    — mmap() call count
    bpf_mmap_bytes_gb           float  — total bytes requested via mmap (GB)
    bpf_malloc_calls            int    — malloc() call count (uprobe on libc)
    bpf_malloc_bytes_gb         float  — total bytes allocated (GB)
    bpf_read_lat_p99_us         float  — read() call latency p99 (µs)
    bpf_write_lat_p99_us        float  — write() call latency p99 (µs)
    bpf_duration_s              float  — actual monitoring window
    """

    # bpftrace program: page faults + mmap + read/write latency for target PID
    _BPF_PROG = """
BEGIN {{ printf("bpf_start\\n"); }}

/* page faults */
software:page-faults:{pid}
{{
    @pf_minor = count();
}}

software:major-faults:{pid}
{{
    @pf_major = count();
}}

/* mmap syscall */
tracepoint:syscalls:sys_enter_mmap
/ pid == {pid} /
{{
    @mmap_calls = count();
    @mmap_bytes = @mmap_bytes + args->len;
}}

/* malloc via uprobe (best-effort) */
uprobe:/lib/x86_64-linux-gnu/libc.so.6:malloc
/ pid == {pid} /
{{
    @malloc_calls = count();
    @malloc_bytes = @malloc_bytes + arg0;
}}

/* read/write latency */
tracepoint:syscalls:sys_enter_read  / pid == {pid} / {{ @rd_start[tid] = nsecs; }}
tracepoint:syscalls:sys_exit_read
/ pid == {pid} && @rd_start[tid] /
{{
    @rd_lat_us = hist((nsecs - @rd_start[tid]) / 1000);
    delete(@rd_start[tid]);
}}

tracepoint:syscalls:sys_enter_write / pid == {pid} / {{ @wr_start[tid] = nsecs; }}
tracepoint:syscalls:sys_exit_write
/ pid == {pid} && @wr_start[tid] /
{{
    @wr_lat_us = hist((nsecs - @wr_start[tid]) / 1000);
    delete(@wr_start[tid]);
}}

END
{{
    printf("bpf_pf_minor %d\\n",    @pf_minor);
    printf("bpf_pf_major %d\\n",    @pf_major);
    printf("bpf_mmap_calls %d\\n",  @mmap_calls);
    printf("bpf_mmap_bytes %d\\n",  @mmap_bytes);
    printf("bpf_malloc_calls %d\\n",@malloc_calls);
    printf("bpf_malloc_bytes %d\\n",@malloc_bytes);
    print(@rd_lat_us);
    print(@wr_lat_us);
}}
"""

    def __init__(self, server_pid: int, duration_s: int = 30,
                 work_dir: "Path | None" = None, use_sudo: bool = True):
        self.server_pid = server_pid
        self.use_sudo  = use_sudo
        self.duration   = duration_s
        self.work_dir   = work_dir
        self._proc      = None
        self._t0: float = 0.0
        self._result: dict = {}

    def _bpftrace_available(self) -> bool:
        try:
            subprocess.run(["bpftrace", "--version"],
                           capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def start(self):
        if not self._bpftrace_available():
            self._result = {"bpf_available": False,
                            "bpf_reason": "bpftrace not found"}
            return
        prog = self._BPF_PROG.replace("{pid}", str(self.server_pid))
        import tempfile
        td = self.work_dir or Path(tempfile.mkdtemp(prefix="amoprof_bpf_"))
        prog_file = td / "monitor.bt"
        prog_file.write_text(prog)

        cmd = ["bpftrace", "-e", prog,
               "--unsafe",           # allow uprobe on libc malloc
               "-c", f"sleep {self.duration}"]
        # Alternatively run with timeout via the prog's interval timer
        cmd = ["timeout", str(self.duration + 5),
               "bpftrace", str(prog_file)]
        try:
            self._proc = _sudo_popen(
                cmd, self.use_sudo, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True,
                cwd=str(td))
            self._t0 = time.time()
        except Exception as e:
            self._result = {"bpf_available": False, "bpf_reason": str(e)}

    def stop(self) -> dict:
        if self._result:
            return self._result
        if not self._proc:
            return {"bpf_available": False, "bpf_reason": "not started"}
        elapsed = round(time.time() - self._t0, 2)
        try:
            # Send SIGINT so bpftrace prints END block
            import signal
            self._proc.send_signal(signal.SIGINT)
            stdout, stderr = self._proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            stdout, stderr = self._proc.communicate()
        except Exception as e:
            return {"bpf_available": False, "bpf_reason": str(e)}

        return self._parse(stdout or "", stderr or "", elapsed)

    def _parse(self, stdout: str, stderr: str, elapsed_s: float) -> dict:
        if "permission denied" in stderr.lower() or "operation not permitted" in stderr.lower():
            return {"bpf_available": False,
                    "bpf_reason": "permission denied (need CAP_BPF or root)"}

        combined = stdout + "\n" + stderr

        def _int(key: str) -> int:
            m = re.search(rf"{key}\s+(\d+)", combined)
            return int(m.group(1)) if m else 0

        def _p99_from_hist(section_marker: str) -> float:
            """
            Extract p99 from bpftrace hist() output.  Format:
              [32K, 64K)    42 |@@@|
            We accumulate counts and find the bucket at 99th percentile.
            """
            in_section = False
            buckets: list[tuple[float, int]] = []
            for line in combined.splitlines():
                if section_marker in line:
                    in_section = True
                    continue
                if in_section:
                    if not line.strip():
                        break
                    # match "[lo, hi)  count"
                    m = re.match(r"\s*\[([^,]+),\s*([^\)]+)\)\s+(\d+)", line)
                    if m:
                        try:
                            lo = float(m.group(1).replace("K","e3").replace("M","e6"))
                            cnt = int(m.group(3))
                            buckets.append((lo, cnt))
                        except Exception:
                            pass
                    elif buckets:
                        break

            if not buckets:
                return 0.0
            total = sum(c for _, c in buckets)
            if total == 0:
                return 0.0
            target = total * 0.99
            cumul  = 0
            for lo, cnt in buckets:
                cumul += cnt
                if cumul >= target:
                    return round(lo, 2)
            return round(buckets[-1][0], 2)

        pf_minor     = _int("bpf_pf_minor")
        pf_major     = _int("bpf_pf_major")
        mmap_calls   = _int("bpf_mmap_calls")
        mmap_bytes   = _int("bpf_mmap_bytes")
        malloc_calls = _int("bpf_malloc_calls")
        malloc_bytes = _int("bpf_malloc_bytes")
        rd_p99       = _p99_from_hist("@rd_lat_us")
        wr_p99       = _p99_from_hist("@wr_lat_us")

        return {
            "bpf_available":         True,
            "bpf_page_faults_total": pf_minor + pf_major,
            "bpf_major_faults_total":pf_major,
            "bpf_mmap_calls":        mmap_calls,
            "bpf_mmap_bytes_gb":     round(mmap_bytes / 1e9, 4),
            "bpf_malloc_calls":      malloc_calls,
            "bpf_malloc_bytes_gb":   round(malloc_bytes / 1e9, 4),
            "bpf_read_lat_p99_us":   rd_p99,
            "bpf_write_lat_p99_us":  wr_p99,
            "bpf_duration_s":        elapsed_s,
            "bpf_raw_output":        combined[-4000:],
        }
