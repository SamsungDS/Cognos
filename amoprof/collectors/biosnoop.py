"""BiosnoopCollector — extracted from collectors_extra.py into its own module.

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

log = logging.getLogger("amoprof.collectors.biosnoop")


@register_collector
class BiosnoopCollector(BaseCollector):
    SPEC = CollectorSpec(
        name='biosnoop',
        layer=AIStackLayer.A2_NVME_DRIVER,
        is_ssd_scoped=True,
        optional=True,
        enable_flag='enable_biosnoop',
        description='biosnoop-bpfcc per-I/O events with PID/command attribution',
    )
    @classmethod
    def for_device(cls, device: str, args, ctx: dict):
        return cls(duration_s=max(int(ctx.get('duration_s', 60)), 1),
                   work_dir=ctx.get('raw_dir', '.'),
                   device=device,
                   binary=getattr(args, 'biosnoop_bin', 'biosnoop-bpfcc'),
                   use_sudo=ctx.get('use_sudo', True),
                   filename_suffix=ctx.get('filename_suffix', ''))

    """
    Run BCC biosnoop to capture per-I/O events with PID + command attribution.

    Important behavior:
      • biosnoop's -t means "print timestamps"; it is NOT a duration option.
        AMOprof controls duration by starting biosnoop at collect start and
        stopping it at collect stop.
      • stdout is captured both as a raw log and parsed CSV.
      • stderr/command/summary are persisted so empty CSVs are diagnosable.
      • all-device biosnoop output is retained in biosnoop_events_all.csv, while
        biosnoop_events.csv contains the target-device/partition-filtered view.
    """

    def __init__(self, duration_s: int = 60,
                 work_dir: "Path | str" = ".",
                 device: str | None = None,
                 binary: str = "biosnoop-bpfcc",
                 use_sudo: bool = True,
                 filename_suffix: str = ""):
        self.duration_s = max(int(duration_s), 1)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.device_name = os.path.basename(device) if device else None
        self.binary = binary
        self.use_sudo = use_sudo

        self._proc = None
        self._reader = None
        self._stderr_reader = None
        _sfx = ("_" + filename_suffix) if filename_suffix else ""
        self._csv_path = self.work_dir / ("biosnoop_events" + _sfx + ".csv")
        self._csv_all_path = self.work_dir / ("biosnoop_events_all" + _sfx + ".csv")
        self._raw_path = self.work_dir / ("biosnoop_raw" + _sfx + ".log")
        self._stderr_path = self.work_dir / ("biosnoop_stderr" + _sfx + ".txt")
        self._cmd_path = self.work_dir / ("biosnoop_command" + _sfx + ".txt")
        self._summary_path = self.work_dir / ("biosnoop_summary" + _sfx + ".json")

        self._csv_fp = None
        self._csv_all_fp = None
        self._raw_fp = None
        self._stderr_fp = None
        self._csv_w = None
        self._csv_all_w = None
        self._events = 0
        self._events_all = 0
        self._lines_seen = 0
        self._lines_unparsed = 0
        self._headers_seen = 0
        self._reason = ""
        self._t0 = 0.0
        self._found = None
        self._cmd = []
        self._header_cols = None

    def _which(self, name: str) -> bool:
        try:
            subprocess.check_output(["which", name], stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def _biosnoop_supports_t(self, binary: str) -> bool:
        """Return True only when this biosnoop build supports -t.

        Some bpfcc-tools builds already print TIME(s) by default and expose only
        [-h] [-Q]. Passing -t to those builds makes biosnoop exit with
        "unrecognized arguments: -t". AMOprof must auto-detect.
        """
        try:
            r = subprocess.run([binary, "-h"], capture_output=True, text=True, timeout=5)
            help_txt = (r.stdout or "") + "\n" + (r.stderr or "")
        except Exception:
            try:
                r = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=5)
                help_txt = (r.stdout or "") + "\n" + (r.stderr or "")
            except Exception:
                return False
        return bool(re.search(r"(^|[\s,\[])-t([\s,\],]|$)", help_txt))

    def _build_biosnoop_cmd(self, binary: str) -> list[str]:
        cmd = [binary]
        if self._biosnoop_supports_t(binary):
            cmd.append("-t")
        return cmd

    @staticmethod
    def _norm_col(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(x).lower())

    def _device_matches(self, disk: str) -> bool:
        """Accept whole-device and partition names.

        Examples:
          device nvme7n1 matches nvme7n1 and nvme7n1p1
          device sda     matches sda and sda1
        """
        if not self.device_name:
            return True
        d = str(disk or "")
        base = self.device_name
        if d == base:
            return True
        if base.startswith("nvme") and d.startswith(base + "p"):
            return True
        if re.match(r"^[a-z]+[a-z]$", base) and d.startswith(base) and d[len(base):].isdigit():
            return True
        return False

    def _open_outputs(self):
        header = ["ts", "comm", "pid", "disk", "op", "sector", "size_bytes", "latency_ms"]
        self._csv_fp = open(self._csv_path, "w", encoding="utf-8", newline="")
        self._csv_all_fp = open(self._csv_all_path, "w", encoding="utf-8", newline="")
        self._raw_fp = open(self._raw_path, "w", encoding="utf-8")
        self._stderr_fp = open(self._stderr_path, "w", encoding="utf-8")
        self._csv_w = _csv.writer(self._csv_fp)
        self._csv_all_w = _csv.writer(self._csv_all_fp)
        self._csv_w.writerow(header)
        self._csv_all_w.writerow(header)

    def _write_summary(self, extra: dict | None = None):
        data = {
            "biosnoop_available": bool(self._events > 0),
            "biosnoop_events": int(self._events),
            "biosnoop_events_all_devices": int(self._events_all),
            "biosnoop_lines_seen": int(self._lines_seen),
            "biosnoop_lines_unparsed": int(self._lines_unparsed),
            "biosnoop_headers_seen": int(self._headers_seen),
            "biosnoop_csv": str(self._csv_path),
            "biosnoop_all_devices_csv": str(self._csv_all_path),
            "biosnoop_raw_log": str(self._raw_path),
            "biosnoop_stderr": str(self._stderr_path),
            "biosnoop_command": str(self._cmd_path),
            "biosnoop_duration_s": round(time.time() - self._t0, 2) if self._t0 else 0,
            "biosnoop_filter_disk": self.device_name or "(all)",
            "biosnoop_reason": self._reason,
            "biosnoop_binary": self._found,
            "biosnoop_cmd": self._cmd,
            "note": (
                "biosnoop_events.csv is filtered to the requested SSD/device and matching partitions; "
                "biosnoop_events_all.csv keeps the unfiltered all-device stream."
            ),
        }
        if extra:
            data.update(extra)
        try:
            self._summary_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
        return data

    def start(self):
        self._events = 0
        self._events_all = 0
        self._lines_seen = 0
        self._lines_unparsed = 0
        self._headers_seen = 0
        self._reason = ""

        candidates = [self.binary, "biosnoop", "biosnoop-bpfcc",
                      "/usr/sbin/biosnoop-bpfcc", "/usr/share/bcc/tools/biosnoop"]
        found = None
        for c in candidates:
            if Path(c).exists() and os.access(c, os.X_OK):
                found = c
                break
            if self._which(c):
                found = c
                break
        self._found = found
        if not found:
            self._reason = "biosnoop not installed (apt: bpfcc-tools)"
            log.warning("BiosnoopCollector: %s", self._reason)
            self._write_summary({"biosnoop_available": False})
            return

        # Biosnoop variants differ: some accept -t, while others print TIME(s)
        # by default and reject -t. Auto-detect and never pass a duration arg.
        cmd = self._build_biosnoop_cmd(found)
        if self.use_sudo and os.geteuid() != 0:
            cmd = ["sudo", "-n", "-E"] + cmd
        self._cmd = cmd
        try:
            self._cmd_path.write_text(" ".join(cmd) + "\n", encoding="utf-8")
        except Exception:
            pass

        self._open_outputs()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,
            )
        except FileNotFoundError as e:
            self._reason = f"failed to launch biosnoop: {e}"
            log.warning("BiosnoopCollector: %s", self._reason)
            self._write_summary({"biosnoop_available": False})
            return
        except Exception as e:
            self._reason = f"failed to launch biosnoop: {e}"
            log.warning("BiosnoopCollector: %s", self._reason)
            self._write_summary({"biosnoop_available": False})
            return

        self._t0 = time.time()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_reader.start()
        self._write_summary({"biosnoop_started": True, "biosnoop_pid": getattr(self._proc, "pid", None)})

    def _stderr_loop(self):
        if self._proc is None or self._proc.stderr is None:
            return
        for raw in self._proc.stderr:
            try:
                if self._stderr_fp:
                    self._stderr_fp.write(raw)
                    self._stderr_fp.flush()
            except Exception:
                pass

    def _parse_with_header(self, cols: list[str]):
        hdr = self._header_cols or []
        idx = {self._norm_col(h): i for i, h in enumerate(hdr)}
        def pick(names, default=None):
            for n in names:
                j = idx.get(self._norm_col(n))
                if j is not None and j < len(cols):
                    return cols[j]
            return default
        return [
            pick(["TIME(s)", "TIME", "TS"], cols[0] if cols else ""),
            pick(["COMM", "CMD", "PROCESS"], ""),
            pick(["PID"], ""),
            pick(["DISK", "DEV", "DEVICE"], ""),
            pick(["T", "TYPE", "OP", "RWBS"], ""),
            pick(["SECTOR", "LBA"], ""),
            pick(["BYTES", "SIZE"], ""),
            pick(["LAT(ms)", "LAT", "LATENCY", "LATENCY(ms)"], ""),
        ]

    def _parse_line(self, line: str):
        cols = line.split()
        if not cols:
            return None

        # Header variants commonly contain PID/DISK/SECTOR/BYTES/LAT.
        joined_norm = " ".join(cols).lower()
        if ("pid" in joined_norm and "disk" in joined_norm and
            ("sector" in joined_norm or "bytes" in joined_norm)):
            self._header_cols = cols
            self._headers_seen += 1
            return "header"

        if len(cols) < 7:
            self._lines_unparsed += 1
            return None

        # Header-driven path first.
        if self._header_cols:
            row = self._parse_with_header(cols)
            if row[2] and row[3] and row[6]:
                return row

        # Fallback for BCC biosnoop -t:
        # TIME(s) COMM PID DISK T SECTOR BYTES LAT(ms)
        if len(cols) >= 8:
            return [cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]]

        # Fallback for no timestamp:
        # COMM PID DISK T SECTOR BYTES LAT(ms)
        if len(cols) >= 7:
            return ["", cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6]]

        self._lines_unparsed += 1
        return None

    def _read_loop(self):
        if self._proc is None or self._proc.stdout is None:
            return
        for raw in self._proc.stdout:
            line = raw.rstrip("\n")
            if self._raw_fp:
                try:
                    self._raw_fp.write(raw)
                    self._raw_fp.flush()
                except Exception:
                    pass
            if not line:
                continue
            self._lines_seen += 1
            parsed = self._parse_line(line)
            if parsed is None or parsed == "header":
                continue
            try:
                ts, comm, pid, disk, op, sect, size, lat = parsed
                self._csv_all_w.writerow([ts, comm, pid, disk, op, sect, size, lat])
                self._events_all += 1
                if self._device_matches(disk):
                    self._csv_w.writerow([ts, comm, pid, disk, op, sect, size, lat])
                    self._events += 1
                if self._events_all % 1000 == 0:
                    try:
                        self._csv_all_fp.flush()
                        self._csv_fp.flush()
                    except Exception:
                        pass
            except Exception:
                self._lines_unparsed += 1

    def stop(self) -> dict:
        if self._proc is not None and self._proc.poll() is None:
            # SIGINT is friendlier to BCC Python tools than SIGTERM and gives
            # them a chance to unwind probes and flush stdout/stderr.
            try:
                self._proc.send_signal(signal.SIGINT)
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

        if self._reader is not None:
            self._reader.join(timeout=10)
        if self._stderr_reader is not None:
            self._stderr_reader.join(timeout=5)

        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

        for fp in (self._csv_fp, self._csv_all_fp, self._raw_fp, self._stderr_fp):
            if fp is not None:
                try:
                    fp.flush()
                    fp.close()
                except Exception:
                    pass

        rc = None
        if self._proc is not None:
            try:
                rc = self._proc.poll()
            except Exception:
                rc = None

        if self._events == 0:
            if self._events_all > 0:
                self._reason = (
                    f"biosnoop captured {self._events_all} events on other disks/devices, "
                    f"but none matched requested device filter {self.device_name!r}; "
                    f"inspect {self._csv_all_path.name} and check DISK names/partitions."
                )
            else:
                stderr_tail = ""
                try:
                    stderr_tail = self._stderr_path.read_text(encoding="utf-8", errors="ignore")[-1200:]
                except Exception:
                    pass
                self._reason = self._reason or (
                    "no biosnoop events captured; possible causes: no block I/O during window, "
                    "BCC/kernel probe attach failure, unsupported biosnoop binary, or permissions/CAP_BPF/CAP_SYS_ADMIN. "
                    f"stderr_tail={stderr_tail!r}"
                )

        summary = self._write_summary({
            "biosnoop_available": bool(self._events > 0),
            "biosnoop_returncode": rc,
        })

        if self._events == 0:
            log.warning("BiosnoopCollector: %s", self._reason)
            return {
                "biosnoop_available": False,
                "biosnoop_reason": self._reason,
                "biosnoop_events": 0,
                "biosnoop_events_all_devices": self._events_all,
                "biosnoop_summary": str(self._summary_path),
                "biosnoop_stderr": str(self._stderr_path),
                "biosnoop_raw_log": str(self._raw_path),
            }

        return {
            "biosnoop_available": True,
            "biosnoop_events": self._events,
            "biosnoop_events_all_devices": self._events_all,
            "biosnoop_csv": str(self._csv_path),
            "biosnoop_all_devices_csv": str(self._csv_all_path),
            "biosnoop_summary": str(self._summary_path),
            "biosnoop_duration_s": round(time.time() - self._t0, 2),
            "biosnoop_filter_disk": self.device_name or "(all)",
        }
