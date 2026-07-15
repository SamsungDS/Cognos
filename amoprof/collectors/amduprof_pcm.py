"""AMDuProfPcmMemoryCollector — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.amduprof_pcm")


@register_collector
class AMDuProfPcmMemoryCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='amduprof_pcm',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=True,
        enable_flag='enable_dram',
        description='AMD uProf PCM memory read/write bandwidth',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        return cls(
            duration_s=(getattr(args, 'amduprof_duration_s', None) or ctx.get('duration_s', 60)),
            interval_s=ctx.get('interval_s', 1.0),
            binary=getattr(args, 'amduprof_pcm_bin', '/opt/AMDuProf_5.2-606/bin/AMDuProfPcm'),
            output_csv=str(ctx.get('raw_dir', '.')) + '/amduprof_pcm_raw.csv',
            extra_args=getattr(args, 'amduprof_extra_arg', None) or [],
            use_sudo=ctx.get('use_sudo', True),
        )

    """Capture DRAM read/write bandwidth and transactions with AMD uProf PCM."""
    def __init__(self, duration_s: float = 10.0, interval_s: float = 1.0,
                 binary: str = "/opt/AMDuProf_5.2-606/bin/AMDuProfPcm",
                 output_csv: str | None = None, extra_args: list[str] | None = None,
                 use_sudo: bool = True):
        self.duration_s = max(float(duration_s), 1.0)
        self.interval_s = max(float(interval_s), 0.1)
        self.binary = binary
        self.output_csv = output_csv
        self.extra_args = extra_args or []
        self.use_sudo = use_sudo
        self.samples: list[dict] = []
        self._proc = None
        self._thread = None
        self._result: dict = {}
        self._raw_output = ""
        self._csv_path: str | None = None
        self._command: str = ""
        self._t0 = 0.0

    def start(self):
        self.samples.clear(); self._result = {}; self._raw_output = ""; self._t0 = time.time()
        if not (self.binary and Path(self.binary).exists() and os.access(self.binary, os.X_OK)):
            self._result = {"amduprof_pcm_available": False, "amduprof_pcm_reason": f"AMDuProfPcm not found or not executable: {self.binary}"}
            return
        out_csv = Path(self.output_csv) if self.output_csv else Path(f"/tmp/amoprof_amduprof_pcm_{int(self._t0)}.csv")
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        # AMDuProf 5.2-606 rejects -i (interval) in -m memory mode with
        # "Error: Failed to process args." It does accept -d (duration in
        # seconds) and auto-adjusts the sampling interval to its minimum
        # (~1200ms). Use -d so the binary self-terminates after our
        # collection window, matching the working command pattern:
        #     AMDuProfPcm -m memory -a -d <secs> -o <path> --msr
        # AMDuProf complains if the output file already exists, so unlink
        # first.
        try:
            out_csv.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        self._csv_path = str(out_csv)
        duration_secs = max(int(self.duration_s), 2)
        # Reset/clean AMDuProfPcm internal state before capture.  This avoids
        # stale counters/state from a previous run contaminating the DRAM-BW
        # timeseries.  Do not duplicate -r if the user already supplied it via
        # --amduprof-extra-arg.
        reset_args = [] if any(str(a) == "-r" for a in self.extra_args) else ["-r"]
        cmd = [self.binary] + reset_args + ["-m", "memory", "-a", "--msr",
               "-d", str(duration_secs), "-o", str(out_csv)] + self.extra_args
        # AMDuProfPcm normally needs MSR access.  If amoprof is not running as
        # root, run through sudo -n so collection either succeeds non-
        # interactively or fails clearly instead of hanging for a password.
        run_cmd = _sudo_cmd(cmd, self.use_sudo)
        self._command = " ".join(str(x) for x in run_cmd)
        try:
            self._proc = subprocess.Popen(run_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                          cwd=str(out_csv.parent))
            self._thread = threading.Thread(target=self._wait_and_parse, daemon=True); self._thread.start()
        except Exception as e:
            self._result = {"amduprof_pcm_available": False, "amduprof_pcm_reason": str(e), "amduprof_pcm_command": " ".join(str(x) for x in run_cmd)}

    @staticmethod
    def _f(v):
        try:
            t = str(v).strip().replace(",", "")
            if not t or t.upper() in {"NA", "N/A", "-"}: return None
            return float(t)
        except Exception: return None

    @staticmethod
    def _gb_s_scale(h: str) -> float:
        x = h.lower()
        if "/s" not in x and "bandwidth" not in x and "bw" not in x: return 1.0
        if "kb" in x: return 1.0/(1024*1024)
        if "mb" in x: return 1.0/1024
        if "gb" in x: return 1.0
        if "byte" in x or "b/s" in x: return 1.0/(1024**3)
        return 1.0

    def _wait_and_parse(self):
        if not self._proc: return
        try:
            # AMDuProfPcm is launched with ``-d <duration>`` and normally
            # self-terminates after flushing its CSV.  Do not kill it exactly
            # at duration_s; that can truncate the DF METRICS section and leave
            # AMOprof with an empty/all-zero DRAM result even though the same
            # command works manually.  Wait for natural completion, then use a
            # bounded terminate/kill sequence only as a final fallback.
            try:
                out, _ = self._proc.communicate(timeout=max(self.duration_s + 30.0, 35.0))
                self._raw_output = out or ""
            except subprocess.TimeoutExpired:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                try:
                    out, _ = self._proc.communicate(timeout=10)
                    self._raw_output = out or ""
                except subprocess.TimeoutExpired:
                    try:
                        self._proc.kill()
                        out, _ = self._proc.communicate(timeout=5)
                        self._raw_output = out or ""
                    except Exception:
                        pass
        except Exception as e:
            self._result = {"amduprof_pcm_available": False, "amduprof_pcm_reason": f"runtime failed: {e}"}
        try: self._parse_csv_file()
        except Exception as e:
            self._result = {"amduprof_pcm_available": False, "amduprof_pcm_reason": f"parse failed: {e}", "amduprof_pcm_raw_output": self._raw_output[-4000:]}

    def _parse_csv_file(self):
        import csv as _csv
        if not self._csv_path or not Path(self._csv_path).exists():
            self._result = {"amduprof_pcm_available": False, "amduprof_pcm_reason": "output CSV not found", "amduprof_pcm_raw_output": self._raw_output[-4000:]}; return
        text = Path(self._csv_path).read_text(errors="replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines: return
        header_idx = 0
        # AMDuProf PCM headers vary by platform/version. Common 5.2 memory mode
        # columns include compact names such as:
        #   Total Mem Bw (GB/s), Total Mem RdBw (GB/s), Total Mem WrBw (GB/s)
        # which do not contain the literal strings \"read\" or \"write\".
        for i, ln in enumerate(lines):
            low = ln.lower()
            has_delim = ("," in ln or ";" in ln)
            has_mem = any(x in low for x in ("memory", "dram", "ddr", "mem"))
            has_bw = any(x in low for x in ("bw", "bandwidth", "/s", "gb/s", "mb/s"))
            has_rw = any(x in low for x in ("read", "write", "rdbw", "wrbw", "rd bw", "wr bw", "rdb/s", "wrb/s"))
            if has_delim and has_mem and has_bw and has_rw:
                header_idx = i; break
        body = "\n".join(lines[header_idx:])
        try: dialect = _csv.Sniffer().sniff(body[:4096], delimiters=",;")
        except Exception: dialect = _csv.excel
        reader = _csv.DictReader(body.splitlines(), dialect=dialect)
        rows=[]; t0=self._t0 or time.time()

        def norm_name(name: str) -> str:
            return " ".join(str(name).strip().lower().replace("_", " " ).replace("-", " " ).split())

        for idx,row in enumerate(reader):
            sample={
                "ts": round(t0 + idx*self.interval_s, 6),
                "timestamp_epoch": round(t0 + idx*self.interval_s, 6),
                "time_sec": round(idx*self.interval_s, 6),
            }
            read=write=total=rtxn=wtxn=0.0
            saw_total=False
            for k,v in row.items():
                if not k: continue
                key=str(k).strip(); lk=norm_name(key); fv=self._f(v); sample[f"raw::{key}"]=v
                if fv is None: continue

                # Exact/common AMDuProf PCM aliases first. Your observed output uses:
                #   Total Mem Bw (GB/s), Total Mem RdBw (GB/s), Total Mem WrBw (GB/s)
                is_total_mem_read_bw = (
                    "total mem rdbw" in lk or "total mem rd bw" in lk or
                    "total memory rdbw" in lk or "total memory read" in lk or
                    "total mem read" in lk or "mem rdbw" in lk or "mem rd bw" in lk
                )
                is_total_mem_write_bw = (
                    "total mem wrbw" in lk or "total mem wr bw" in lk or
                    "total memory wrbw" in lk or "total memory write" in lk or
                    "total mem write" in lk or "mem wrbw" in lk or "mem wr bw" in lk
                )
                is_total_mem_bw = (
                    ("total mem bw" in lk or "total memory bw" in lk or "total mem bandwidth" in lk)
                    and not is_total_mem_read_bw and not is_total_mem_write_bw
                )

                if is_total_mem_read_bw:
                    read += fv*self._gb_s_scale(key); continue
                if is_total_mem_write_bw:
                    write += fv*self._gb_s_scale(key); continue
                if is_total_mem_bw:
                    total += fv*self._gb_s_scale(key); saw_total=True; continue

                is_mem=any(x in lk for x in ("dram","ddr","memory","mem","channel","socket"))
                is_read=("read" in lk or " rdbw" in lk or " rd bw" in lk or lk.endswith("rdbw"))
                is_write=("write" in lk or " wrbw" in lk or " wr bw" in lk or lk.endswith("wrbw"))
                is_bw=any(x in lk for x in ("/s","bw","bandwidth","bytes/s","mb/s","gb/s"))
                is_txn=any(x in lk for x in ("txn","trans","transaction","cas","count"))
                if is_mem and is_read and is_bw: read += fv*self._gb_s_scale(key)
                elif is_mem and is_write and is_bw: write += fv*self._gb_s_scale(key)
                elif is_mem and is_read and is_txn: rtxn += fv
                elif is_mem and is_write and is_txn: wtxn += fv

            total_bw = total if saw_total else (read + write)
            sample.update({
                "dram_read_gb_s": round(read,6),
                "dram_write_gb_s": round(write,6),
                "dram_total_gb_s": round(total_bw,6),
                "dram_read_transactions": round(rtxn,6),
                "dram_write_transactions": round(wtxn,6),
                "dram_total_transactions": round(rtxn+wtxn,6),
                "dram_read_gb_est": round(read*self.interval_s,6),
                "dram_write_gb_est": round(write*self.interval_s,6),
                "dram_total_gb_est": round(total_bw*self.interval_s,6),
                "amduprof_pcm_parse_schema": "amduprof_5_total_mem_bw_aliases",
                "dram_transactions_supported": bool(rtxn or wtxn),
            })
            rows.append(sample)
        self.samples=rows

    def stop(self) -> dict:
        _interrupted = bool(getattr(self, "_amoprof_interrupted", False))
        _timeout = float(getattr(self, "_amoprof_stop_timeout_s", 0.0) or (5.0 if _interrupted else self.duration_s + 35))
        if _interrupted and self._proc and self._proc.poll() is None:
            try: self._proc.terminate()
            except Exception: pass
        if self._thread: self._thread.join(timeout=_timeout)
        if self._result: return self._result
        if self._proc and self._proc.poll() is None:
            try: self._proc.terminate()
            except Exception: pass
            try: self._proc.wait(timeout=min(_timeout, 5.0))
            except Exception:
                try: self._proc.kill()
                except Exception: pass
        if not self.samples:
            return {"amduprof_pcm_available": False, "amduprof_pcm_reason": "no samples", "amduprof_pcm_csv_path": self._csv_path or "", "amduprof_pcm_command": self._command, "amduprof_pcm_raw_output": self._raw_output[-4000:]}
        reads=[float(s.get("dram_read_gb_s",0) or 0) for s in self.samples]
        writes=[float(s.get("dram_write_gb_s",0) or 0) for s in self.samples]
        totals=[float(s.get("dram_total_gb_s",0) or 0) for s in self.samples]
        rtxn=[float(s.get("dram_read_transactions",0) or 0) for s in self.samples]
        wtxn=[float(s.get("dram_write_transactions",0) or 0) for s in self.samples]
        def mn(xs): return round(statistics.mean(xs),6) if xs else 0.0
        def pk(xs): return round(max(xs),6) if xs else 0.0
        elapsed=max(time.time()-(self._t0 or time.time()),0.001)
        return {
            "amduprof_pcm_available": True,
            "amduprof_pcm_source": self.binary,
            "amduprof_pcm_csv_path": self._csv_path or "",
            "amduprof_pcm_command": self._command,
            "amduprof_pcm_samples": len(self.samples),
            "dram_read_gb_s_mean": mn(reads),
            "dram_write_gb_s_mean": mn(writes),
            "dram_total_gb_s_mean": mn(totals),
            "dram_read_gb_s_peak": pk(reads),
            "dram_write_gb_s_peak": pk(writes),
            "dram_total_gb_s_peak": pk(totals),
            "dram_read_transactions_total": round(sum(rtxn),6),
            "dram_write_transactions_total": round(sum(wtxn),6),
            "dram_total_transactions_total": round(sum(rtxn)+sum(wtxn),6),
            "dram_read_gb_est": round(sum(reads)*self.interval_s,6),
            "dram_write_gb_est": round(sum(writes)*self.interval_s,6),
            "dram_total_gb_est": round(sum(totals)*self.interval_s,6),
            "amduprof_pcm_duration_s": round(elapsed,3),
            "amduprof_pcm_raw_output": self._raw_output[-4000:],
        }
