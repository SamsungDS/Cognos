#!/usr/bin/env python3
"""
kvssd_trace_tool.py v4-correct

Capture/analyze NVMe SSD I/O characteristics for KV$ / hierarchical KV cache workloads.

Backends:
  blktrace  - low-level block trace; best for LBA locality/alignment/random-vs-seq
  biosnoop  - BCC/eBPF based; best for process attribution + latency
  both      - runs both collectors

Examples:

  sudo ./kvssd_trace_tool.py capture --backend both --dev /dev/nvme1n1 \
    --seconds 600 --interval-sec 5 --capture-sec 1 --max-trace-size-gb 10 \
    --biosnoop-queue-time --out kvssd_both_run

  ./kvssd_trace_tool.py analyze --trace-dir kvssd_both_run --out kvssd_blktrace_analysis

  ./kvssd_trace_tool.py analyze --biosnoop-file kvssd_both_run/biosnoop.txt \
    --actions '' --out kvssd_biosnoop_analysis
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

SECTOR_BYTES = 512


@dataclass
class CaptureMeta:
    device: str
    backend: str
    seconds: int
    interval_sec: Optional[float]
    capture_sec: Optional[float]
    max_trace_size_gb: Optional[float]
    started_epoch: float
    ended_epoch: float
    hostname: str
    windows_attempted: int
    windows_completed: int
    stopped_reason: str
    cmd: str


def run(cmd: List[str], *, check: bool = True, stdout=None, stderr=None) -> subprocess.CompletedProcess:
    print("+ " + " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=check, stdout=stdout, stderr=stderr, text=True)


def require_bin(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required command: {name}. Install it first.")


def find_biosnoop() -> Optional[str]:
    candidates = [
        "biosnoop",
        "biosnoop-bpfcc",
        "/usr/share/bcc/tools/biosnoop",
        "/usr/share/bpfcc-tools/biosnoop",
        "/usr/sbin/biosnoop",
        "/sbin/biosnoop",
    ]
    for c in candidates:
        p = shutil.which(c) if not c.startswith("/") else c
        if p and Path(p).exists():
            return p
    return None


def dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def start_sidecars(args, out: Path):
    sidecars = []
    if shutil.which("iostat"):
        f = open(out / "iostat_xm_1.txt", "w")
        sidecars.append(subprocess.Popen(
            ["iostat", "-xm", str(max(1, int(args.sidecar_interval_sec))), args.dev],
            stdout=f, stderr=subprocess.STDOUT, text=True
        ))

    if shutil.which("nvme"):
        sidecars.append(subprocess.Popen([sys.executable, "-c",
            "import time,subprocess,json\n"
            f"dev={args.dev!r}; seconds={args.seconds!r}; interval={max(1, int(args.sidecar_interval_sec))!r}; path={str(out/'nvme_smartlog.jsonl')!r}\n"
            "f=open(path,'w')\n"
            "end=time.time()+seconds\n"
            "while time.time()<end:\n"
            "  try:\n"
            "    cp=subprocess.run(['nvme','smart-log',dev,'-o','json'],capture_output=True,text=True,timeout=5)\n"
            "    f.write(json.dumps({'epoch':time.time(),'rc':cp.returncode,'stdout':cp.stdout,'stderr':cp.stderr})+'\\n'); f.flush()\n"
            "  except Exception as e:\n"
            "    f.write(json.dumps({'epoch':time.time(),'error':str(e)})+'\\n'); f.flush()\n"
            "  time.sleep(interval)\n"
        ]))
    return sidecars


def stop_sidecars(sidecars):
    for p in sidecars:
        try:
            p.terminate()
        except Exception:
            pass


def discover_trace_prefixes(trace_dir: Path) -> List[Path]:
    prefixes = set()
    for p in trace_dir.glob("*.blktrace.*"):
        marker = ".blktrace."
        if marker in p.name:
            prefixes.add(trace_dir / p.name.split(marker)[0])
    return sorted(prefixes, key=lambda x: str(x))


def blkparse_to_machine_csv(prefixes: List[Path], out_csv: Path) -> None:
    require_bin("blkparse")
    fmt = "%T.%t,%p,%a,%d,%S,%n,%c,%M,%C,%s\n"

    with open(out_csv, "w") as f:
        f.write("ts,pid,action,rwbs,sector,nsectors,comm,dev,cpu,seq,trace_prefix\n")
        for prefix in prefixes:
            cp = subprocess.run(
                ["blkparse", "-q", "-i", str(prefix), "-f", fmt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if cp.returncode != 0:
                raise SystemExit(f"blkparse conversion failed for {prefix}:\n{cp.stderr}")
            for line in cp.stdout.splitlines():
                if line.strip():
                    f.write(line.rstrip("\n") + "," + str(prefix) + "\n")


def capture_biosnoop_window(args, out_file: Path, seconds: float) -> None:
    biosnoop = find_biosnoop()
    if not biosnoop:
        raise SystemExit(
            "biosnoop not found. Install BCC tools first.\n"
            "RHEL/Fedora: sudo dnf install -y bcc-tools bpftrace\n"
            "Ubuntu/Debian: sudo apt-get install -y bpfcc-tools bpftrace"
        )

    disk_name = Path(args.dev).name
    cmd = [biosnoop]

    if args.biosnoop_queue_time:
        cmd.append("-Q")
    if not args.biosnoop_no_disk_filter:
        cmd += ["-d", disk_name]

    print("+ timeout --preserve-status " + str(seconds) + " " + " ".join(cmd), flush=True)

    with open(out_file, "a", buffering=1) as f:
        f.write(f"# BIOSNOOP_WINDOW_START epoch={time.time()} seconds={seconds} cmd={' '.join(cmd)}\n")
        subprocess.run(
            ["timeout", "--preserve-status", f"{seconds:.3f}"] + cmd,
            stdout=f,
            stderr=subprocess.STDOUT,
            text=True,
        )
        f.write(f"# BIOSNOOP_WINDOW_END epoch={time.time()}\n")


def validate_capture_args(args):
    if args.backend in ("blktrace", "both"):
        require_bin("blktrace")
        require_bin("blkparse")
    if args.backend in ("biosnoop", "both") and not find_biosnoop():
        raise SystemExit(
            "biosnoop not found. Install BCC tools first.\n"
            "RHEL/Fedora: sudo dnf install -y bcc-tools bpftrace\n"
            "Ubuntu/Debian: sudo apt-get install -y bpfcc-tools bpftrace"
        )
    if (args.interval_sec is None) != (args.capture_sec is None):
        raise SystemExit("Use both --interval-sec and --capture-sec together.")
    if args.interval_sec is not None:
        if args.interval_sec <= 0 or args.capture_sec <= 0:
            raise SystemExit("--interval-sec and --capture-sec must be positive.")
        if args.capture_sec > args.interval_sec:
            raise SystemExit("--capture-sec must be <= --interval-sec.")


def capture(args) -> None:
    validate_capture_args(args)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    started = time.time()
    hostname = subprocess.check_output(["hostname"], text=True).strip()
    sidecars = start_sidecars(args, out)

    windows_attempted = 0
    windows_completed = 0
    stopped_reason = "completed"
    max_bytes = int(args.max_trace_size_gb * (1024 ** 3)) if args.max_trace_size_gb else None

    try:
        if args.interval_sec is None:
            windows_attempted = 1
            if args.backend in ("blktrace", "both"):
                run(["blktrace", "-d", args.dev, "-w", str(args.seconds), "-o", str(out / "trace")])
            if args.backend in ("biosnoop", "both"):
                capture_biosnoop_window(args, out / "biosnoop.txt", float(args.seconds))
            windows_completed = 1
        else:
            print(f"[INFO] interval capture: capture {args.capture_sec}s every {args.interval_sec}s for {args.seconds}s total")
            end_time = time.time() + args.seconds
            idx = 0

            while time.time() < end_time:
                if max_bytes is not None and dir_size_bytes(out) >= max_bytes:
                    stopped_reason = f"max trace size reached: {args.max_trace_size_gb} GiB"
                    print(f"[WARN] {stopped_reason}")
                    break

                remaining = end_time - time.time()
                capture_for = min(float(args.capture_sec), max(0.0, remaining))
                if capture_for <= 0:
                    break

                windows_attempted += 1
                print(f"[INFO] capture window {idx}: {capture_for:.3f}s")

                if args.backend in ("blktrace", "both"):
                    run(["blktrace", "-d", args.dev, "-w", f"{capture_for:.3f}", "-o", str(out / f"trace_window_{idx}")])
                if args.backend in ("biosnoop", "both"):
                    capture_biosnoop_window(args, out / "biosnoop.txt", capture_for)

                windows_completed += 1

                if max_bytes is not None and dir_size_bytes(out) >= max_bytes:
                    stopped_reason = f"max trace size reached: {args.max_trace_size_gb} GiB"
                    print(f"[WARN] {stopped_reason}")
                    break

                idx += 1
                sleep_for = min(float(args.interval_sec - args.capture_sec), max(0.0, end_time - time.time()))
                if sleep_for > 0:
                    time.sleep(sleep_for)
    finally:
        stop_sidecars(sidecars)

    if args.backend in ("blktrace", "both") and not args.no_machine_csv:
        prefixes = discover_trace_prefixes(out)
        if not prefixes and (out / "trace.blktrace.0").exists():
            prefixes = [out / "trace"]
        if prefixes:
            blkparse_to_machine_csv(prefixes, out / "blkparse_events.csv")

    ended = time.time()
    meta = CaptureMeta(
        device=args.dev,
        backend=args.backend,
        seconds=args.seconds,
        interval_sec=args.interval_sec,
        capture_sec=args.capture_sec,
        max_trace_size_gb=args.max_trace_size_gb,
        started_epoch=started,
        ended_epoch=ended,
        hostname=hostname,
        windows_attempted=windows_attempted,
        windows_completed=windows_completed,
        stopped_reason=stopped_reason,
        cmd=" ".join(sys.argv),
    )
    (out / "capture_meta.json").write_text(json.dumps(asdict(meta), indent=2))

    print(f"\nCapture complete: {out}")
    if args.backend in ("blktrace", "both"):
        print(f"Analyze blktrace: {sys.argv[0]} analyze --trace-dir {out} --out {out}_blktrace_analysis")
    if args.backend in ("biosnoop", "both"):
        print(f"Analyze biosnoop: {sys.argv[0]} analyze --biosnoop-file {out/'biosnoop.txt'} --actions '' --out {out}_biosnoop_analysis")


def clean_blk_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["ts", "pid", "sector", "nsectors", "cpu", "seq"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["ts", "pid", "sector", "nsectors"]).copy()
    df["pid"] = df["pid"].astype(np.int64)
    df["sector"] = df["sector"].astype(np.int64)
    df["nsectors"] = df["nsectors"].astype(np.int64)
    df["cpu"] = pd.to_numeric(df.get("cpu", -1), errors="coerce").fillna(-1).astype(np.int64)
    df["seq"] = pd.to_numeric(df.get("seq", -1), errors="coerce").fillna(-1).astype(np.int64)
    df["comm"] = df["comm"].fillna("").astype(str)
    df["rwbs"] = df["rwbs"].fillna("").astype(str)
    df["action"] = df["action"].fillna("").astype(str)
    if "trace_prefix" not in df.columns:
        df["trace_prefix"] = ""
    df["trace_prefix"] = df["trace_prefix"].fillna("").astype(str)

    rwbs = df["rwbs"].str.upper()
    df["op"] = np.select(
        [
            rwbs.str.contains("R", regex=False),
            rwbs.str.contains("W", regex=False),
            rwbs.str.contains("D", regex=False) | rwbs.str.contains("DISCARD", regex=False),
        ],
        ["read", "write", "trim"],
        default="other",
    )
    df["stream"] = df["comm"] + ":" + df["pid"].astype(str)
    df["offset"] = df["sector"] * SECTOR_BYTES
    df["size_bytes"] = df["nsectors"] * SECTOR_BYTES
    df["end_sector"] = df["sector"] + df["nsectors"]
    df["latency_ms"] = np.nan
    df["queue_ms"] = np.nan
    return df


def read_machine_csv(path: Path, chunksize: Optional[int] = None) -> pd.DataFrame:
    usecols = ["ts", "pid", "action", "rwbs", "sector", "nsectors", "comm", "dev", "cpu", "seq", "trace_prefix"]
    if chunksize:
        parts = []
        for chunk in pd.read_csv(path, usecols=lambda c: c in usecols, chunksize=chunksize, on_bad_lines="skip"):
            parts.append(clean_blk_df(chunk))
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return clean_blk_df(pd.read_csv(path, usecols=lambda c: c in usecols, on_bad_lines="skip"))


def parse_biosnoop_file(path: Path) -> pd.DataFrame:
    rows = []
    header = None

    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "TIME" in line and "COMM" in line and "PID" in line:
                header = re.split(r"\s+", line)
                continue

            if header is None:
                continue

            parts = re.split(r"\s+", line)
            if len(parts) < len(header):
                continue

            d = dict(zip(header, parts[:len(header)]))

            def get_any(*names):
                for n in names:
                    if n in d:
                        return d[n]
                return None

            try:
                ts = float(get_any("TIME(s)", "TIME") or 0.0)
                pid = int(get_any("PID") or 0)
                comm = str(get_any("COMM") or "")
                disk = str(get_any("DISK") or "")
                typ = str(get_any("T", "TYPE") or "").upper()
                sector = int(float(get_any("SECTOR", "BLK") or 0))
                bytes_ = int(float(get_any("BYTES", "SIZE") or 0))
                latency_ms = float(get_any("LAT(ms)", "LAT", "LATENCY", "LATENCY(ms)") or "nan")
                queue_ms = float(get_any("QUE(ms)", "QUE", "QUEUE(ms)") or "nan")
            except Exception:
                continue

            if typ.startswith("R"):
                op, rwbs = "read", "R"
            elif typ.startswith("W"):
                op, rwbs = "write", "W"
            elif typ.startswith("D") or "DISCARD" in typ or "TRIM" in typ:
                op, rwbs = "trim", "D"
            else:
                op, rwbs = "other", typ

            nsectors = max(1, int(math.ceil(bytes_ / SECTOR_BYTES))) if bytes_ > 0 else 0
            rows.append({
                "ts": ts,
                "pid": pid,
                "action": "BIO",
                "rwbs": rwbs,
                "sector": sector,
                "nsectors": nsectors,
                "comm": comm,
                "dev": disk,
                "cpu": -1,
                "seq": len(rows),
                "trace_prefix": str(path),
                "op": op,
                "stream": f"{comm}:{pid}",
                "offset": sector * SECTOR_BYTES,
                "size_bytes": bytes_,
                "end_sector": sector + nsectors,
                "latency_ms": latency_ms,
                "queue_ms": queue_ms,
            })

    if not rows:
        raise SystemExit(f"No parseable biosnoop rows found in {path}. Check with: head -30 {path}")
    return pd.DataFrame(rows)


def load_events(args, out: Path) -> pd.DataFrame:
    if args.biosnoop_file:
        return parse_biosnoop_file(Path(args.biosnoop_file))
    if args.trace_dir:
        prefixes = discover_trace_prefixes(Path(args.trace_dir))
        if not prefixes:
            raise SystemExit(f"No trace prefixes found in {args.trace_dir}")
        machine = out / "blkparse_events.generated.csv"
        blkparse_to_machine_csv(prefixes, machine)
        return read_machine_csv(machine, chunksize=args.chunksize)
    if args.trace_prefix:
        prefixes = [Path(x) for x in args.trace_prefix]
        machine = out / "blkparse_events.generated.csv"
        blkparse_to_machine_csv(prefixes, machine)
        return read_machine_csv(machine, chunksize=args.chunksize)
    return read_machine_csv(Path(args.events), chunksize=args.chunksize)


def gini(values: np.ndarray) -> float:
    values = values.astype(float)
    values = values[values >= 0]
    if values.size == 0 or np.all(values == 0):
        return 0.0
    values = np.sort(values)
    n = values.size
    return float((2 * np.arange(1, n + 1) @ values) / (n * values.sum()) - (n + 1) / n)


def skewness(values: np.ndarray) -> float:
    values = values.astype(float)
    if values.size < 3:
        return 0.0
    std = values.std()
    if std == 0:
        return 0.0
    return float(np.mean(((values - values.mean()) / std) ** 3))


def classify_seq_random(df: pd.DataFrame, gap_sectors: int) -> pd.DataFrame:
    df = df.sort_values(["stream", "op", "ts", "seq"]).copy()
    df["prev_end_sector"] = df.groupby(["stream", "op"])["end_sector"].shift(1)
    df["lba_gap_sectors"] = (df["sector"] - df["prev_end_sector"]).abs()
    df["is_sequential"] = df["prev_end_sector"].notna() & (df["lba_gap_sectors"] <= gap_sectors)
    df["access_area"] = np.where(df["is_sequential"], "sequential", "random")
    return df.sort_values(["ts", "seq"]).reset_index(drop=True)


def make_plots(out: Path, window_df: pd.DataFrame, hot_df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    for op in ["read", "write", "trim"]:
        sdf = window_df[window_df["op"] == op]
        if not sdf.empty:
            plt.figure()
            plt.plot(sdf["window_start_sec"], sdf["bytes"] / (1024 * 1024))
            plt.xlabel("time since trace start (sec)")
            plt.ylabel("MiB per window")
            plt.title(f"{op} burst/bandwidth temporal shape")
            plt.tight_layout()
            plt.savefig(out / f"{op}_burst_shape.png", dpi=150)
            plt.close()

        hdf = hot_df[hot_df["op"] == op].head(30)
        if not hdf.empty:
            plt.figure()
            plt.bar(range(len(hdf)), hdf["bytes"] / (1024 * 1024))
            plt.xlabel("top regions")
            plt.ylabel("MiB")
            plt.title(f"{op} hot-region skew, top 30")
            plt.tight_layout()
            plt.savefig(out / f"{op}_hot_regions.png", dpi=150)
            plt.close()


def analyze(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    df = load_events(args, out)

    if args.sample_rate is not None:
        if not (0 < args.sample_rate <= 1):
            raise SystemExit("--sample-rate must be > 0 and <= 1")
        if args.sample_rate < 1:
            df = df.sample(frac=args.sample_rate, random_state=args.sample_seed).sort_values(["ts", "seq"]).reset_index(drop=True)

    if args.actions is not None and args.actions != "":
        df = df[df["action"].isin(list(args.actions))].copy()

    df = df[df["op"].isin(["read", "write", "trim"])].copy()
    if df.empty:
        raise SystemExit("No read/write/trim events after filtering. For biosnoop use --actions ''.")

    df["ts_rel"] = df["ts"] - df["ts"].min()
    duration = max(float(df["ts"].max() - df["ts"].min()), 1e-9)

    df = classify_seq_random(df, gap_sectors=max(0, int(args.sequential_gap_bytes // SECTOR_BYTES)))
    df["kv_aligned"] = (df["offset"] % args.kv_block_size == 0) & (df["size_bytes"] % args.kv_block_size == 0)
    df["page_aligned"] = (df["offset"] % args.page_size == 0) & (df["size_bytes"] % args.page_size == 0)

    if args.write_events_csv:
        df.to_csv(out / "events_enriched.csv", index=False)

    stream = (
        df.groupby(["op", "stream"], dropna=False)
          .agg(count=("size_bytes", "size"), bytes=("size_bytes", "sum"),
               first_ts=("ts", "min"), last_ts=("ts", "max"),
               latency_ms_avg=("latency_ms", "mean"))
          .reset_index()
    )
    stream["duration_sec"] = (stream["last_ts"] - stream["first_ts"]).clip(lower=1e-9)
    stream["bandwidth_mib_s"] = stream["bytes"] / stream["duration_sec"] / (1024 * 1024)
    stream.to_csv(out / "bandwidth_per_stream.csv", index=False)

    stream.groupby("op").agg(
        avg_stream_bandwidth_mib_s=("bandwidth_mib_s", "mean"),
        max_stream_bandwidth_mib_s=("bandwidth_mib_s", "max"),
        streams=("stream", "nunique"),
    ).reset_index().to_csv(out / "bandwidth_per_stream_summary.csv", index=False)

    inter_rows = []
    for op, odf in df.groupby("op"):
        for x in odf.sort_values("ts")["ts"].diff().dropna():
            inter_rows.append({"op": op, "inter_arrival_sec": float(x)})
    pd.DataFrame(inter_rows).to_csv(out / "interarrival_distribution.csv", index=False)

    df[["op", "size_bytes", "access_area", "kv_aligned", "page_aligned", "latency_ms"]].to_csv(
        out / "request_size_distribution.csv", index=False
    )

    if df["latency_ms"].notna().any():
        lat = df.groupby("op")["latency_ms"].agg(["count", "mean", "min", "max"]).reset_index()
        q = df.groupby("op")["latency_ms"].quantile([0.5, 0.9, 0.99]).unstack().reset_index()
        q.columns = ["op", "p50", "p90", "p99"]
        lat.merge(q, on="op", how="left").to_csv(out / "latency_summary_biosnoop.csv", index=False)

    df["window"] = np.floor(df["ts_rel"] / args.window_sec).astype(int)
    window_df = df.groupby(["op", "window"]).agg(
        count=("size_bytes", "size"),
        bytes=("size_bytes", "sum"),
        avg_req_size=("size_bytes", "mean"),
        avg_latency_ms=("latency_ms", "mean"),
    ).reset_index()
    window_df["window_start_sec"] = window_df["window"] * args.window_sec
    window_df["bandwidth_mib_s"] = window_df["bytes"] / args.window_sec / (1024 * 1024)
    window_df.to_csv(out / "burst_temporal_windows.csv", index=False)

    region_bytes = args.region_mib * 1024 * 1024
    df["region"] = (df["offset"] // region_bytes).astype(np.int64)
    hot_df = df.groupby(["op", "region"]).agg(bytes=("size_bytes", "sum"), count=("size_bytes", "size")).reset_index()
    hot_df = hot_df.sort_values(["op", "bytes"], ascending=[True, False])
    hot_df["region_start_byte"] = hot_df["region"] * region_bytes
    hot_df["region_end_byte"] = (hot_df["region"] + 1) * region_bytes - 1
    hot_df.to_csv(out / "hot_regions_overall.csv", index=False)

    skew_rows = []
    for op, odf in hot_df.groupby("op"):
        v = odf["bytes"].to_numpy()
        skew_rows.append({
            "op": op,
            "regions": int(len(v)),
            "gini_bytes": gini(v),
            "skewness_bytes": skewness(v),
            "top_1pct_byte_share": float(odf.head(max(1, math.ceil(len(odf) * 0.01)))["bytes"].sum() / max(odf["bytes"].sum(), 1)),
            "top_10_region_byte_share": float(odf.head(10)["bytes"].sum() / max(odf["bytes"].sum(), 1)),
        })
    pd.DataFrame(skew_rows).to_csv(out / "access_skew_summary.csv", index=False)

    hot_time = df.groupby(["op", "window", "region"]).agg(bytes=("size_bytes", "sum"), count=("size_bytes", "size")).reset_index()
    hot_time["rank_in_window"] = hot_time.groupby(["op", "window"])["bytes"].rank(method="first", ascending=False)
    hot_time_top = hot_time[hot_time["rank_in_window"] <= args.top_regions_per_window].copy()
    hot_time_top["window_start_sec"] = hot_time_top["window"] * args.window_sec
    hot_time_top.to_csv(out / "hot_regions_by_time_window.csv", index=False)

    corr_rows = []
    for op, odf in df.groupby("op"):
        corr = None
        if len(odf) > 1 and odf["is_sequential"].nunique() > 1:
            corr = float(np.corrcoef(odf["size_bytes"], odf["is_sequential"].astype(int))[0, 1])
        corr_rows.append({
            "op": op,
            "request_size_vs_is_sequential_corr": corr,
            "avg_size_random": float(odf.loc[odf["access_area"] == "random", "size_bytes"].mean()) if (odf["access_area"] == "random").any() else None,
            "avg_size_sequential": float(odf.loc[odf["access_area"] == "sequential", "size_bytes"].mean()) if (odf["access_area"] == "sequential").any() else None,
        })
    pd.DataFrame(corr_rows).to_csv(out / "request_size_random_seq_correlation.csv", index=False)

    early_end = duration * args.degradation_fraction
    late_start = duration * (1 - args.degradation_fraction)
    degrade_rows = []
    for op, odf in df.groupby("op"):
        early = odf[odf["ts_rel"] <= early_end]
        late = odf[odf["ts_rel"] >= late_start]
        early_bw = early["size_bytes"].sum() / max(early_end, 1e-9) / (1024 * 1024)
        late_bw = late["size_bytes"].sum() / max(duration - late_start, 1e-9) / (1024 * 1024)
        degrade_rows.append({
            "op": op,
            "early_fraction": args.degradation_fraction,
            "early_bandwidth_mib_s": float(early_bw),
            "late_bandwidth_mib_s": float(late_bw),
            "degradation_ratio_late_over_early": float(late_bw / early_bw) if early_bw > 0 else None,
            "degradation_pct": float((1 - late_bw / early_bw) * 100) if early_bw > 0 else None,
        })
    pd.DataFrame(degrade_rows).to_csv(out / "bandwidth_degradation.csv", index=False)

    seasonal = window_df.pivot_table(index="window_start_sec", columns="op", values="bytes", fill_value=0, aggfunc="sum").reset_index()
    for op in ["read", "write", "trim"]:
        if op not in seasonal.columns:
            seasonal[op] = 0
    seasonal["total"] = seasonal["read"] + seasonal["write"] + seasonal["trim"]
    for op in ["read", "write", "trim"]:
        seasonal[f"{op}_share"] = np.where(seasonal["total"] > 0, seasonal[op] / seasonal["total"], 0)
    seasonal.to_csv(out / "temporal_read_write_trim_pattern.csv", index=False)

    summary = {}
    for op in ["read", "write", "trim"]:
        odf = df[df["op"] == op]
        if odf.empty:
            summary[op] = {"count": 0}
            continue
        inter = odf["ts"].diff().dropna()
        size = odf["size_bytes"]
        total_bytes = int(size.sum())
        summary[op] = {
            "count": int(len(odf)),
            "total_bytes": total_bytes,
            "estimated_bytes_per_day": float(total_bytes / duration * 86400),
            "bandwidth_mib_s_avg_over_trace": float(total_bytes / duration / (1024 * 1024)),
            "request_size_bytes_avg": float(size.mean()),
            "request_size_bytes_min": int(size.min()),
            "request_size_bytes_p50": float(size.quantile(0.50)),
            "request_size_bytes_p90": float(size.quantile(0.90)),
            "request_size_bytes_p99": float(size.quantile(0.99)),
            "request_size_bytes_max": int(size.max()),
            "inter_arrival_sec_avg": float(inter.mean()) if len(inter) else None,
            "inter_arrival_sec_min": float(inter.min()) if len(inter) else None,
            "inter_arrival_sec_p50": float(inter.quantile(0.50)) if len(inter) else None,
            "inter_arrival_sec_p90": float(inter.quantile(0.90)) if len(inter) else None,
            "inter_arrival_sec_p99": float(inter.quantile(0.99)) if len(inter) else None,
            "inter_arrival_sec_max": float(inter.max()) if len(inter) else None,
            "latency_ms_avg": float(odf["latency_ms"].mean()) if odf["latency_ms"].notna().any() else None,
            "latency_ms_p99": float(odf["latency_ms"].quantile(0.99)) if odf["latency_ms"].notna().any() else None,
            "not_kv_block_aligned_count": int((~odf["kv_aligned"]).sum()),
            "not_page_aligned_count": int((~odf["page_aligned"]).sum()),
            "random_count": int((odf["access_area"] == "random").sum()),
            "sequential_count": int((odf["access_area"] == "sequential").sum()),
            "random_bytes": int(odf.loc[odf["access_area"] == "random", "size_bytes"].sum()),
            "sequential_bytes": int(odf.loc[odf["access_area"] == "sequential", "size_bytes"].sum()),
        }

    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "# KV$ SSD I/O Workload Analysis\n",
        f"Trace duration represented: {duration:.3f} sec",
        f"Events analyzed: {len(df):,}",
        f"KV block size: {args.kv_block_size} bytes; page size: {args.page_size} bytes",
        f"Sequential threshold gap: <= {args.sequential_gap_bytes} bytes\n",
    ]
    if args.biosnoop_file:
        lines.append("Source: biosnoop\n")
    for op, s in summary.items():
        lines.append(f"## {op.upper()}")
        if s.get("count", 0) == 0:
            lines.append("No events.\n")
            continue
        lines += [
            f"- requests: {s['count']:,}",
            f"- total bytes: {s['total_bytes']:,}",
            f"- estimated bytes/day: {s['estimated_bytes_per_day']:,.0f}",
            f"- avg bandwidth: {s['bandwidth_mib_s_avg_over_trace']:.2f} MiB/s",
            f"- request size avg/min/p50/p90/p99/max bytes: {s['request_size_bytes_avg']:.1f}/{s['request_size_bytes_min']}/{s['request_size_bytes_p50']:.1f}/{s['request_size_bytes_p90']:.1f}/{s['request_size_bytes_p99']:.1f}/{s['request_size_bytes_max']}",
            f"- latency avg/p99 ms: {s['latency_ms_avg']}/{s['latency_ms_p99']}",
            f"- not KV-block aligned: {s['not_kv_block_aligned_count']:,}",
            f"- not page aligned: {s['not_page_aligned_count']:,}",
            f"- random/sequential requests: {s['random_count']:,}/{s['sequential_count']:,}",
            "",
        ]
    (out / "report.md").write_text("\n".join(lines))

    if not args.no_plots:
        make_plots(out, window_df, hot_df)

    print(f"Analysis complete: {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="KV$ NVMe SSD I/O capture/analyzer using blktrace and biosnoop")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="capture IO traces")
    c.add_argument("--backend", choices=["blktrace", "biosnoop", "both"], default="blktrace",
                   help="capture backend")
    c.add_argument("--dev", required=True, help="block device, e.g. /dev/nvme1n1")
    c.add_argument("--seconds", type=int, default=300, help="total wall-clock runtime")
    c.add_argument("--out", required=True)
    c.add_argument("--interval-sec", type=float, default=None, help="interval between capture starts")
    c.add_argument("--capture-sec", type=float, default=None, help="capture duration per interval")
    c.add_argument("--max-trace-size-gb", type=float, default=None, help="stop after output dir reaches this size")
    c.add_argument("--sidecar-interval-sec", type=float, default=1)
    c.add_argument("--no-machine-csv", action="store_true", help="skip blkparse_events.csv generation")
    c.add_argument("--biosnoop-queue-time", action="store_true", help="pass -Q to biosnoop")
    c.add_argument("--biosnoop-no-disk-filter", action="store_true", help="do not pass -d <disk> to biosnoop")
    c.set_defaults(func=capture)

    a = sub.add_parser("analyze", help="analyze traces")
    src = a.add_mutually_exclusive_group(required=True)
    src.add_argument("--events", help="machine CSV blkparse_events.csv")
    src.add_argument("--trace-prefix", action="append", help="raw blktrace prefix; may be repeated")
    src.add_argument("--trace-dir", help="directory containing trace*.blktrace.* files")
    src.add_argument("--biosnoop-file", help="biosnoop.txt output")
    a.add_argument("--out", required=True)
    a.add_argument("--kv-block-size", type=int, default=4096)
    a.add_argument("--page-size", type=int, default=4096)
    a.add_argument("--window-sec", type=float, default=1.0)
    a.add_argument("--region-mib", type=int, default=64)
    a.add_argument("--sequential-gap-bytes", type=int, default=0)
    a.add_argument("--top-regions-per-window", type=int, default=10)
    a.add_argument("--degradation-fraction", type=float, default=0.10)
    a.add_argument("--actions", default="D", help="blkparse action letters; for biosnoop use --actions ''")
    a.add_argument("--sample-rate", type=float, default=None)
    a.add_argument("--sample-seed", type=int, default=42)
    a.add_argument("--chunksize", type=int, default=None)
    a.add_argument("--write-events-csv", action="store_true")
    a.add_argument("--no-plots", action="store_true")
    a.set_defaults(func=analyze)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
