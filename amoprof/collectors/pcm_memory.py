"""PcmMemoryCollector — extracted from collectors.py into its own module.

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

log = logging.getLogger("amoprof.collectors.pcm_memory")


@register_collector
class PcmMemoryCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='pcm',
        layer=AIStackLayer.A3_DRAM,
        is_ssd_scoped=False,
        is_pid_scoped=False,
        optional=True,
        enable_flag='enable_dram',
        description='Intel PCM pcm-memory or perf uncore_imc fallback',
    )
    @classmethod
    def for_host(cls, args, ctx: dict):
        dram_tool = ctx.get('dram_tool', 'auto') or 'auto'
        return cls(
            ctx.get('interval_s', 1.0),
            binary=(None if dram_tool == 'perf-imc' else getattr(args, 'intel_pcm_memory_bin', None)),
            force_perf_imc=(dram_tool == 'perf-imc'),
            use_sudo=ctx.get('use_sudo', True),
            work_dir=ctx.get('raw_dir', '.'),
        )

    """
    Tracks socket-level DRAM bandwidth using Intel PCM or IMC PMU counters.

    Metrics
    -------
    pcm_available               bool
    pcm_dram_read_gb_s          float  — mean DRAM read BW across all sockets (GB/s)
    pcm_dram_write_gb_s         float  — mean DRAM write BW across all sockets (GB/s)
    pcm_dram_total_gb_s         float  — read + write
    pcm_dram_read_gb_s_peak     float  — peak in window
    pcm_dram_write_gb_s_peak    float  — peak in window
    pcm_samples                 int
    pcm_source                  str    — "pcm-memory" | "imc_pmu" | "unavailable"
    """

    def __init__(self, interval_s: float = 1.0, binary: str | None = None,
                 force_perf_imc: bool = False, use_sudo: bool = True,
                 work_dir: "Path | str | None" = None):
        self.interval  = interval_s
        self.binary    = binary
        self.force_perf_imc = force_perf_imc
        self.use_sudo  = use_sudo
        self.work_dir  = Path(work_dir) if work_dir is not None else None
        if self.work_dir is not None:
            self.work_dir.mkdir(parents=True, exist_ok=True)
        self._samples: list[dict] = []
        self._proc      = None
        self._thread    = None
        self._stop      = threading.Event()
        self._source    = "unavailable"
        self._t0        = 0.0
        self._raw_path: "Path | None" = (self.work_dir / "pcm_memory_raw.csv" if self.work_dir is not None else None)
        self._raw_fh = None
        self._command = ""
        self._reason = ""

    # ── PCM binary path ───────────────────────────────────────────────────────

    def _pcm_path(self) -> "str | None":
        candidates = []
        if self.binary:
            candidates.append(self.binary)
        candidates += ["pcm-memory", "pcm-memory.x", "/usr/local/bin/pcm-memory",
                       "/usr/local/sbin/pcm-memory", "/opt/intel/pcm/bin/pcm-memory",
                       "/opt/intel/pcm/pcm-memory"]
        seen = set()
        for p in candidates:
            if not p or p in seen:
                continue
            seen.add(p)
            try:
                subprocess.run([p, "--help"], capture_output=True, timeout=3)
                return p
            except Exception:
                pass
        return None

    # ── IMC PMU fallback via perf ─────────────────────────────────────────────

    def _imc_perf_available(self) -> bool:
        """Check if perf can access uncore_imc events."""
        try:
            r = subprocess.run(
                ["perf", "list", "uncore_imc"],
                capture_output=True, text=True, timeout=5)
            return "cas_count" in r.stdout.lower() or "cas_count" in r.stderr.lower()
        except Exception:
            return False

    def start(self):
        self._stop.clear()
        self._samples.clear()
        self._t0 = time.time()
        pcm = None if self.force_perf_imc else self._pcm_path()
        if pcm:
            self._source = "intel-pcm/pcm-memory"
            self._start_pcm(pcm)
        elif self._imc_perf_available():
            self._source = "imc_pmu"
            self._thread = threading.Thread(
                target=self._poll_imc_pmu, daemon=True)
            self._thread.start()
        else:
            self._source = "unavailable"

    def _start_pcm(self, pcm_bin: str):
        """Launch Intel pcm-memory in CSV mode and parse its streaming output."""
        cmd = [pcm_bin, str(self.interval), "-csv"]
        self._command = " ".join(str(x) for x in _sudo_cmd(cmd, self.use_sudo))
        try:
            self._proc = _sudo_popen(
                cmd, use_sudo=self.use_sudo, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True,
                cwd=str(self.work_dir) if self.work_dir is not None else None)
            self._thread = threading.Thread(
                target=self._read_pcm, daemon=True)
            self._thread.start()
        except Exception as e:
            self._source = "unavailable"
            self._reason = f"failed to launch pcm-memory: {e}"

    @staticmethod
    def _num(v):
        try:
            t = str(v).strip().strip('"').replace(",", "")
            if not t or t.upper() in {"NA", "N/A", "-", "--"}:
                return None
            return float(t)
        except Exception:
            return None

    @staticmethod
    def _bw_scale_from_header(h: str) -> float:
        x = str(h).lower()
        if "kb/s" in x or "kbytes/s" in x or "kbyte/s" in x:
            return 1.0 / (1024 * 1024)
        if "mb/s" in x or "mbytes/s" in x or "mbyte/s" in x:
            return 1.0 / 1024
        if "gb/s" in x or "gbytes/s" in x or "gbyte/s" in x:
            return 1.0
        # Intel pcm-memory CSV emits MB/s for the unqualified System Read/Write/Memory
        # columns in common two-row-header output.  Older AMOprof treated these
        # unqualified columns as GB/s or lost them entirely; default to MB/s here
        # unless a unit is explicitly present.
        return 1.0 / 1024

    @staticmethod
    def _csv_split(line: str, delim: str) -> list[str]:
        try:
            return [x.strip().strip('"') for x in next(csv.reader([line], delimiter=delim, skipinitialspace=True))]
        except Exception:
            return [x.strip().strip('"') for x in str(line).split(delim)]

    @staticmethod
    def _unique_headers(cols: list[str]) -> list[str]:
        seen = {}
        out = []
        for c in cols:
            base = (str(c).strip() or "col")
            n = seen.get(base, 0)
            seen[base] = n + 1
            out.append(base if n == 0 else f"{base}.{n+1}")
        return out

    @classmethod
    def _combine_pcm_headers(cls, group_line: str | None, header_line: str, delim: str) -> list[str]:
        names = cls._csv_split(header_line, delim)
        groups = cls._csv_split(group_line, delim) if group_line else []
        if len(groups) != len(names):
            return cls._unique_headers(names)
        out = []
        for g, h in zip(groups, names):
            g = str(g or '').strip()
            h = str(h or '').strip()
            # pcm-memory often has a first row like: ,,SKT0,...,SKT1,...,System,System,System
            # and a second row like: Date,Time,Ch0Read,...,Read,Write,Memory.
            # Preserve both levels so System Read/Write can be selected and duplicate
            # per-socket column names do not overwrite each other.
            if g and h and h.lower() not in {"date", "time"}:
                out.append(f"{g} {h}")
            else:
                out.append(h or g)
        return cls._unique_headers(out)

    @classmethod
    def parse_pcm_memory_raw_csv(cls, path: "str | Path", *, source: str = "intel-pcm/pcm-memory",
                                 start_ts: float | None = None) -> list[dict]:
        """Parse Intel pcm-memory CSV, including two-row SKT/System headers.

        Returns AMOprof-normalized samples in GB/s.  This is used both by the
        live collector and by the analyzer to repair older raw directories where
        pcm_timeseries.csv was written as zeros even though pcm_memory_raw.csv
        contains real System Read/Write/Memory values.
        """
        try:
            lines = Path(path).read_text(errors="replace").splitlines()
        except Exception:
            return []
        prev = None
        header = None
        delim = ","
        out: list[dict] = []
        t0 = start_ts or time.time()
        for line in lines:
            if not str(line).strip():
                continue
            d = ";" if line.count(";") >= line.count(",") else ","
            if header is None:
                if cls._looks_like_pcm_header(line, d):
                    delim = d
                    header = cls._combine_pcm_headers(prev, line, delim)
                else:
                    prev = line
                continue
            parts = cls._csv_split(line, delim)
            if len(parts) < len(header):
                continue
            if len(parts) > len(header):
                parts = parts[:len(header)]
            row = dict(zip(header, parts))
            dummy = cls()
            read_gb_s, write_gb_s, total_gb_s, schema = dummy._extract_pcm_bw(row)
            if total_gb_s <= 0:
                continue
            ts = time.time()
            # Prefer PCM Date/Time when present for stable offline analysis.
            try:
                import datetime as _dt
                date = row.get("Date") or row.get("date")
                tm = row.get("Time") or row.get("time")
                if date and tm:
                    dt = _dt.datetime.fromisoformat(str(date).strip() + "T" + str(tm).strip())
                    ts = dt.replace(tzinfo=_dt.timezone.utc).timestamp()
            except Exception:
                pass
            out.append({
                "ts": round(float(ts), 6),
                "timestamp_epoch": round(float(ts), 6),
                "timestamp_utc": cls._utc(float(ts)),
                "time_sec": round(max(float(ts) - float(t0), 0.0), 6),
                "read": round(read_gb_s, 6),
                "write": round(write_gb_s, 6),
                "dram_read_gb_s": round(read_gb_s, 6),
                "dram_write_gb_s": round(write_gb_s, 6),
                "dram_total_gb_s": round(total_gb_s, 6),
                "pcm_dram_read_gb_s": round(read_gb_s, 6),
                "pcm_dram_write_gb_s": round(write_gb_s, 6),
                "pcm_dram_total_gb_s": round(total_gb_s, 6),
                "dram_source": source,
                "pcm_parse_schema": schema,
            })
        if out:
            base = float(out[0].get("timestamp_epoch", out[0].get("ts", 0)) or 0)
            for i, r in enumerate(out):
                r["iteration"] = i
                te = float(r.get("timestamp_epoch", r.get("ts", base)) or base)
                r["time_sec"] = round(max(te - base, 0.0), 6)
        return out

    @staticmethod
    def _utc(ts: float) -> str:
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return ""

    @staticmethod
    def _looks_like_pcm_header(line: str, delim: str) -> bool:
        low = line.lower()
        if delim not in line:
            return False
        # Intel PCM often prints banner / socket topology lines before the CSV
        # header. The real memory CSV header contains at least read/write BW
        # terms and usually System/Socket/SKT columns.
        has_read = any(x in low for x in ("read", "rdbw", "read bw", "mem read"))
        has_write = any(x in low for x in ("write", "wrbw", "write bw", "mem write"))
        has_mem = any(x in low for x in ("memory", "mem", "dram", "socket", "skt", "system"))
        return has_read and has_write and has_mem

    def _extract_pcm_bw(self, row: dict[str, str]) -> tuple[float, float, float, str]:
        """Return read/write/total GB/s from one Intel PCM row.

        Prefer System/Total memory columns when present.  If only per-socket
        columns exist, sum those.  This avoids double-counting rows that expose
        both per-socket and already-aggregated System columns.
        """
        entries = []
        for k, v in row.items():
            lk = str(k).strip().strip('"').lower().replace("_", " ").replace("-", " ")
            fv = self._num(v)
            if fv is None:
                continue
            if not any(x in lk for x in ("read", "write", "rdbw", "wrbw", "memory", "mem", "dram")):
                continue
            if not any(x in lk for x in ("read", "write", "rdbw", "wrbw")):
                continue
            direction = "read" if ("read" in lk or "rdbw" in lk or "rd bw" in lk) else "write"
            scale = self._bw_scale_from_header(k)
            is_system = any(x in lk for x in ("system", "total", "all sockets", "aggregate"))
            is_socket = any(x in lk for x in ("socket", "skt", "package", "node", "channel", "imc"))
            entries.append((direction, fv * scale, is_system, is_socket, lk))

        # Prefer aggregate System/Total columns if available.
        use = [e for e in entries if e[2]] or [e for e in entries if e[3]] or entries
        read = sum(e[1] for e in use if e[0] == "read")
        write = sum(e[1] for e in use if e[0] == "write")
        total = read + write
        source = "system_total_columns" if any(e[2] for e in use) else ("per_socket_sum" if any(e[3] for e in use) else "best_effort_columns")
        return read, write, total, source

    def _read_pcm(self):
        """Parse Intel pcm-memory CSV robustly across PCM versions."""
        if not self._proc:
            return
        if self._raw_path is not None:
            try:
                self._raw_fh = open(self._raw_path, "w", encoding="utf-8", buffering=1)
            except Exception:
                self._raw_fh = None
        header = None
        prev_header_line = None
        try:
            iterator = self._proc.stdout or []
            for line in iterator:
                if self._raw_fh:
                    try:
                        self._raw_fh.write(line)
                    except Exception:
                        pass
                if self._stop.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                delim = ";" if line.count(";") >= line.count(",") else ","
                if header is None:
                    if not self._looks_like_pcm_header(line, delim):
                        prev_header_line = line
                        continue
                    self._pcm_delim = delim
                    header = self._combine_pcm_headers(prev_header_line, line, delim)
                    continue
                delim = getattr(self, "_pcm_delim", ";")
                parts = self._csv_split(line, delim)
                if len(parts) < len(header):
                    continue
                if len(parts) > len(header):
                    parts = parts[:len(header)]
                row = dict(zip(header, parts))
                try:
                    read_gb_s, write_gb_s, total_gb_s, schema = self._extract_pcm_bw(row)
                    if total_gb_s <= 0:
                        continue
                    ts = time.time()
                    self._samples.append({
                        "ts": round(ts, 6),
                        "timestamp_epoch": round(ts, 6),
                        "timestamp_utc": self._utc(ts),
                        "time_sec": round(ts - (self._t0 or ts), 6),
                        "read": round(read_gb_s, 6), "write": round(write_gb_s, 6),
                        "dram_read_gb_s": round(read_gb_s, 6),
                        "dram_write_gb_s": round(write_gb_s, 6),
                        "dram_total_gb_s": round(total_gb_s, 6),
                        "pcm_dram_read_gb_s": round(read_gb_s, 6),
                        "pcm_dram_write_gb_s": round(write_gb_s, 6),
                        "pcm_dram_total_gb_s": round(total_gb_s, 6),
                        "dram_source": self._source,
                        "pcm_parse_schema": schema,
                    })
                except Exception as e:
                    self._reason = f"pcm row parse failed: {e}"
                    pass
        finally:
            if self._raw_fh:
                try:
                    self._raw_fh.close()
                except Exception:
                    pass
                self._raw_fh = None

    def _poll_imc_pmu(self):
        """
        Poll IMC CAS counters via perf stat --all-sockets every interval_s.
        CAS_COUNT_RD * 64 bytes / interval → GB/s.
        """
        cmd = [
            "perf", "stat", "-a",
            "-e", "uncore_imc/cas_count_read/,uncore_imc/cas_count_write/",
            "-I", str(int(self.interval * 1000)),
            "--field-separator", ",",
            "sleep", "86400",
        ]
        try:
            proc = _sudo_popen(
                cmd, use_sudo=self.use_sudo, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True,
                cwd=str(self.work_dir) if self.work_dir is not None else None)
            for line in proc.stderr:
                if self._stop.is_set():
                    proc.terminate()
                    break
                # format: timestamp,count,unit,event,duration,...
                parts = line.strip().split(",")
                if len(parts) < 4:
                    continue
                try:
                    count = int(parts[1].replace(",","").strip())
                    event = parts[3].strip().lower()
                    dt    = self.interval
                    bw    = count * 64 / 1e9 / max(dt, 0.001)
                    ts = time.time()
                    base = {
                        "ts": round(ts, 6),
                        "timestamp_epoch": round(ts, 6),
                        "timestamp_utc": self._utc(ts),
                        "time_sec": round(ts - (self._t0 or ts), 6),
                        "dram_source": self._source,
                        "pcm_parse_schema": "perf_uncore_imc_cas_count",
                    }
                    if "read" in event:
                        self._samples.append({**base, "read": round(bw,6), "write": 0,
                                              "dram_read_gb_s": round(bw,6), "dram_write_gb_s": 0,
                                              "dram_total_gb_s": round(bw,6),
                                              "pcm_dram_read_gb_s": round(bw,6), "pcm_dram_write_gb_s": 0,
                                              "pcm_dram_total_gb_s": round(bw,6)})
                    elif "write" in event:
                        if self._samples:
                            self._samples[-1]["write"] = round(bw,6)
                            self._samples[-1]["dram_write_gb_s"] = round(bw,6)
                            self._samples[-1]["pcm_dram_write_gb_s"] = round(bw,6)
                            total = self._samples[-1].get("dram_read_gb_s", 0) + bw
                            self._samples[-1]["dram_total_gb_s"] = round(total,6)
                            self._samples[-1]["pcm_dram_total_gb_s"] = round(total,6)
                        else:
                            self._samples.append({**base, "read": 0, "write": round(bw,6),
                                                  "dram_read_gb_s": 0, "dram_write_gb_s": round(bw,6),
                                                  "dram_total_gb_s": round(bw,6),
                                                  "pcm_dram_read_gb_s": 0, "pcm_dram_write_gb_s": round(bw,6),
                                                  "pcm_dram_total_gb_s": round(bw,6)})
                except Exception:
                    pass
        except Exception as e:
            self._reason = f"perf imc polling failed: {e}"

    def stop(self) -> dict:
        self._stop.set()
        if self._proc:
            self._proc.terminate()
            try: self._proc.wait(timeout=5)
            except Exception: pass
        if self._thread:
            self._thread.join(timeout=5)

        if self._source == "unavailable" or not self._samples:
            return {"pcm_available":  False,
                    "pcm_source":     self._source,
                    "pcm_reason":     getattr(self, "_reason", "no Intel PCM/perf IMC samples"),
                    "pcm_samples":    0,
                    "pcm_raw_path":   str(self._raw_path) if self._raw_path is not None else ""}

        reads  = [float(s.get("dram_read_gb_s", s.get("read", 0)) or 0) for s in self._samples]
        writes = [float(s.get("dram_write_gb_s", s.get("write", 0)) or 0) for s in self._samples]
        totals = [float(s.get("dram_total_gb_s", r + w) or 0) for s, r, w in zip(self._samples, reads, writes)]

        def mn(xs): return round(statistics.mean(xs), 6) if xs else 0.0
        def pk(xs): return round(max(xs), 6) if xs else 0.0
        nonzero = sum(1 for x in totals if abs(float(x or 0)) > 0)
        elapsed = max(time.time() - (self._t0 or time.time()), 0.001)

        return {
            "pcm_available":            bool(nonzero),
            "pcm_source":               self._source,
            "dram_collector":           self._source,
            "pcm_dram_read_gb_s":       mn(reads),
            "pcm_dram_write_gb_s":      mn(writes),
            "pcm_dram_total_gb_s":      mn(totals),
            "dram_read_gb_s_mean":      mn(reads),
            "dram_write_gb_s_mean":     mn(writes),
            "dram_total_gb_s_mean":     mn(totals),
            "pcm_dram_read_gb_s_peak":  pk(reads),
            "pcm_dram_write_gb_s_peak": pk(writes),
            "pcm_dram_total_gb_s_peak": pk(totals),
            "dram_read_gb_s_peak":      pk(reads),
            "dram_write_gb_s_peak":     pk(writes),
            "dram_total_gb_s_peak":     pk(totals),
            "pcm_samples":              len(self._samples),
            "pcm_nonzero_samples":      nonzero,
            "pcm_duration_s":           round(elapsed, 3),
            "pcm_raw_path":             str(self._raw_path) if self._raw_path is not None else "",
            "pcm_reason":               "" if nonzero else getattr(self, "_reason", "all Intel PCM samples were zero"),
        }
