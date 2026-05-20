"""
blktrace_analyzer.py — Pre-aggregate raw blktrace events into the analysis
CSVs that the bundled AMOprof report reads.

amoprof's report engine knows how to render rich per-stream / per-region /
per-window NVMe charts when these files exist in raw/. Without them, it falls
back to flat "no data" panels.

This module produces (all written into the same `raw/` directory):
    summary.json
    bandwidth_per_stream.csv          one row per (op, stream) with bw/count/bytes
    bandwidth_per_stream_summary.csv  avg/max BW per op
    hot_regions_overall.csv           top LBA regions by bytes (per op)
    hot_regions_by_time_window.csv    same, per 10s window
    interarrival_distribution.csv     per-op IAT histogram bins
    request_size_distribution.csv     per-event size + access_area + alignment
    burst_temporal_windows.csv        windows where IOPS or BW exceeded a threshold
    temporal_read_write_trim_pattern.csv  10s-window R/W/T bytes & counts
    access_skew_summary.csv           Gini + top-1%/top-5% byte share per op
    bandwidth_degradation.csv         late-window BW / early-window BW ratio
    request_size_random_seq_correlation.csv  corr(size, is_random) per op

Input: a `blkparse_events.generated.csv` file (or path to a blktrace binary
directory which will be parsed first).

This is invoked automatically by `amoprof analyze` and `amoprof collect
--analyze` when blktrace data is present.
"""
from __future__ import annotations

import csv
import json
import logging
import math
from collections import Counter, defaultdict
from pathlib import Path

log = logging.getLogger("amoprof.blktrace_analyzer")

# Window size for burst / temporal pattern analysis (seconds)
WINDOW_S = 10.0
# Hot region bucket size (bytes) — LBA-space buckets for hot-region counting
LBA_BUCKET = 16 * 1024 * 1024   # 16 MB
# Burst detection threshold (multiple of mean IOPS)
BURST_X = 2.0


def _read_events(csv_path: Path) -> list[dict]:
    """Load blkparse_events.generated.csv into a list of dicts.

    Expected columns: ts, pid, action, rwbs, op, sector, nsectors,
                      size_bytes, comm, dev, cpu
    Only completion events (action='C') are used for size/throughput, but
    queue events (action='Q') are kept for IAT analysis.
    """
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ts = float(row["ts"])
                size = int(row.get("size_bytes") or
                           (int(row.get("nsectors", 0)) * 512))
                if size <= 0:
                    continue
                rows.append({
                    "ts":     ts,
                    "pid":    int(row.get("pid", 0) or 0),
                    "comm":   row.get("comm", "") or "",
                    "op":     row.get("op", row.get("rwbs", "?"))[:1].upper(),
                    "sector": int(row.get("sector", 0) or 0),
                    "size":   size,
                    "action": row.get("action", ""),
                })
            except (ValueError, KeyError):
                continue
    return rows


def _gini(values: list[float]) -> float:
    """Gini coefficient of a list of non-negative values."""
    if not values:
        return 0.0
    xs = sorted(float(v) for v in values if v > 0)
    n = len(xs)
    if n == 0:
        return 0.0
    cum = 0.0
    for i, v in enumerate(xs, 1):
        cum += i * v
    s = sum(xs)
    if s == 0:
        return 0.0
    return (2 * cum) / (n * s) - (n + 1) / n


def _topk_byte_share(values: list[int], pct: float) -> float:
    """Fraction of total bytes contributed by the top `pct`% of buckets."""
    if not values:
        return 0.0
    xs = sorted(values, reverse=True)
    total = sum(xs)
    if total <= 0:
        return 0.0
    k = max(1, int(len(xs) * pct / 100))
    return sum(xs[:k]) / total


def _per_event_iat_us(events: list[dict]) -> dict[str, list[float]]:
    """Inter-arrival times per operation, in microseconds."""
    by_op: dict[str, list[float]] = {}
    last_ts: dict[str, float] = {}
    for e in events:
        op = e["op"]
        if op in last_ts:
            iat_us = (e["ts"] - last_ts[op]) * 1e6
            if iat_us > 0:
                by_op.setdefault(op, []).append(iat_us)
        last_ts[op] = e["ts"]
    return by_op


def _histogram(values: list[float], bins: list[tuple[float, float, str]]) -> list[tuple[str, int]]:
    """Bucketize `values` into named bins. Returns (label, count)."""
    out = []
    for lo, hi, label in bins:
        c = sum(1 for v in values if lo <= v < hi)
        out.append((label, c))
    return out


IAT_BINS = [
    (0,       1,       "<1us"),
    (1,       10,      "1-10us"),
    (10,      100,     "10-100us"),
    (100,     1000,    "100us-1ms"),
    (1000,    10000,   "1-10ms"),
    (10000,   100000,  "10-100ms"),
    (100000,  1e9,     ">100ms"),
]

SIZE_BINS = [
    (0,        4096+1,        "≤4KB"),
    (4097,     16384+1,       "4-16KB"),
    (16385,    65536+1,       "16-64KB"),
    (65537,    262144+1,      "64-256KB"),
    (262145,   1048576+1,     "256KB-1MB"),
    (1048577,  1<<30,         ">1MB"),
]

OP_NAME = {"R": "read", "W": "write", "D": "trim"}


def _classify_access(prev_end_sector: int | None,
                      cur_sector: int,
                      cur_nsec: int) -> str:
    """Sequential vs random heuristic: if cur_sector == prev_end, sequential."""
    if prev_end_sector is None:
        return "random"
    # Allow small gap (≤8 sectors = 4KB) to still be "sequential"
    if 0 <= (cur_sector - prev_end_sector) <= 8:
        return "sequential"
    return "random"


def analyze(events_csv: Path, output_dir: Path) -> dict:
    """Compute all analysis CSVs from a blkparse events CSV.

    Returns a dict of filenames produced.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    log.info("blktrace_analyzer: reading %s", events_csv)
    events = _read_events(events_csv)
    if not events:
        log.warning("blktrace_analyzer: no events found in %s", events_csv)
        return {}

    events.sort(key=lambda e: e["ts"])
    t0 = events[0]["ts"]
    t1 = events[-1]["ts"]
    duration = max(t1 - t0, 1e-6)

    # Normalise timestamps to [0, duration]
    for e in events:
        e["ts"] -= t0

    written: dict[str, Path] = {}

    # ─── 1. summary.json ─────────────────────────────────────────────────────
    rd_evts = [e for e in events if e["op"] == "R"]
    wr_evts = [e for e in events if e["op"] == "W"]
    tr_evts = [e for e in events if e["op"] == "D"]
    summary = {
        "duration_sec":       round(duration, 3),
        "total_events":       len(events),
        "read_events":        len(rd_evts),
        "write_events":       len(wr_evts),
        "trim_events":        len(tr_evts),
        "read_bytes_total":   sum(e["size"] for e in rd_evts),
        "write_bytes_total":  sum(e["size"] for e in wr_evts),
        "trim_bytes_total":   sum(e["size"] for e in tr_evts),
        "rw_ratio":           (len(rd_evts) / max(len(wr_evts), 1)),
        "read_iops_mean":     round(len(rd_evts) / duration, 2),
        "write_iops_mean":    round(len(wr_evts) / duration, 2),
        "trim_iops_mean":     round(len(tr_evts) / duration, 4),
        "read_bw_mb_s_mean":  round(sum(e["size"] for e in rd_evts) / 1e6 / duration, 2),
        "write_bw_mb_s_mean": round(sum(e["size"] for e in wr_evts) / 1e6 / duration, 2),
        "trim_present":       len(tr_evts) > 0,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    written["summary.json"] = output_dir / "summary.json"

    # ─── 2. bandwidth_per_stream.csv ────────────────────────────────────────
    # Stream = (op, pid+comm). Compute per-stream bandwidth in MiB/s.
    stream_stats: dict[tuple, dict] = {}
    for e in events:
        key = (e["op"], e["pid"], e["comm"])
        s = stream_stats.setdefault(key, {"count": 0, "bytes": 0,
                                          "first_ts": e["ts"], "last_ts": e["ts"]})
        s["count"] += 1
        s["bytes"] += e["size"]
        s["first_ts"] = min(s["first_ts"], e["ts"])
        s["last_ts"] = max(s["last_ts"], e["ts"])
    with open(output_dir / "bandwidth_per_stream.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "stream", "pid", "comm", "count", "bytes",
                    "duration_sec", "bandwidth_mib_s"])
        for (op, pid, comm), s in stream_stats.items():
            dur = max(s["last_ts"] - s["first_ts"], 1e-3)
            bw  = s["bytes"] / 1048576.0 / dur
            stream_name = f"{comm}:{pid}"
            w.writerow([OP_NAME.get(op, op), stream_name, pid, comm,
                        s["count"], s["bytes"], round(dur, 3), round(bw, 3)])
    written["bandwidth_per_stream.csv"] = output_dir / "bandwidth_per_stream.csv"

    # bandwidth_per_stream_summary.csv
    with open(output_dir / "bandwidth_per_stream_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "n_streams", "bandwidth_mib_s_mean", "bandwidth_mib_s_max"])
        for op in ("R", "W", "D"):
            bws = []
            for (eo, _, _), s in stream_stats.items():
                if eo != op:
                    continue
                dur = max(s["last_ts"] - s["first_ts"], 1e-3)
                bws.append(s["bytes"] / 1048576.0 / dur)
            if bws:
                w.writerow([OP_NAME.get(op, op), len(bws),
                            round(sum(bws)/len(bws), 3), round(max(bws), 3)])
    written["bandwidth_per_stream_summary.csv"] = output_dir / "bandwidth_per_stream_summary.csv"

    # ─── 3. hot_regions_overall.csv ──────────────────────────────────────────
    region_bytes: dict[tuple, int] = defaultdict(int)
    region_count: dict[tuple, int] = defaultdict(int)
    for e in events:
        bucket = (e["sector"] * 512) // LBA_BUCKET
        region_bytes[(e["op"], bucket)] += e["size"]
        region_count[(e["op"], bucket)] += 1
    # Take top 50 per op
    with open(output_dir / "hot_regions_overall.csv", "w", newline="") as f:
        w = csv.writer(f)
        # 'region' is the bucket index, kept as a separate column for the
        # bundled amoprof chart engine which expects exactly that name.
        w.writerow(["op", "region", "lba_bucket_start", "lba_bucket_end",
                    "bytes", "count"])
        for op in ("R", "W", "D"):
            items = [(b, c, region_bytes[(op, b)])
                     for (eo, b), c in region_count.items() if eo == op]
            items.sort(key=lambda x: x[2], reverse=True)
            for bucket, count, b in items[:50]:
                w.writerow([OP_NAME.get(op, op), bucket,
                            bucket * LBA_BUCKET,
                            (bucket + 1) * LBA_BUCKET,
                            b, count])
    written["hot_regions_overall.csv"] = output_dir / "hot_regions_overall.csv"

    # ─── 4. hot_regions_by_time_window.csv ───────────────────────────────────
    with open(output_dir / "hot_regions_by_time_window.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["window_start_sec", "op", "lba_bucket_start",
                    "lba_bucket_end", "bytes"])
        n_windows = max(1, int(duration / WINDOW_S))
        for win in range(n_windows):
            t_lo, t_hi = win * WINDOW_S, (win + 1) * WINDOW_S
            win_bytes: dict[tuple, int] = defaultdict(int)
            for e in events:
                if t_lo <= e["ts"] < t_hi:
                    bucket = (e["sector"] * 512) // LBA_BUCKET
                    win_bytes[(e["op"], bucket)] += e["size"]
            # Top 10 per window
            items = sorted(win_bytes.items(), key=lambda x: x[1], reverse=True)[:10]
            for (op, bucket), b in items:
                w.writerow([round(t_lo, 1), OP_NAME.get(op, op),
                            bucket * LBA_BUCKET,
                            (bucket + 1) * LBA_BUCKET, b])
    written["hot_regions_by_time_window.csv"] = output_dir / "hot_regions_by_time_window.csv"

    # ─── 5. interarrival_distribution.csv ────────────────────────────────────
    iats = _per_event_iat_us(events)
    with open(output_dir / "interarrival_distribution.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "bin_label", "lower_us", "upper_us", "count",
                    "inter_arrival_us_mean"])
        for op, vals in iats.items():
            hist = _histogram(vals, IAT_BINS)
            mean_iat = sum(vals) / len(vals) if vals else 0
            for label, count in hist:
                lo, hi, _ = next(x for x in IAT_BINS if x[2] == label)
                w.writerow([OP_NAME.get(op, op), label, lo, hi, count,
                            round(mean_iat, 2)])
    written["interarrival_distribution.csv"] = output_dir / "interarrival_distribution.csv"

    # ─── 6. request_size_distribution.csv ───────────────────────────────────
    # Track sequential vs random per stream
    prev_end: dict[tuple, int] = {}
    with open(output_dir / "request_size_distribution.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "size_bytes", "size_bucket", "access_area",
                    "alignment_4k", "ts_sec"])
        for e in events:
            key = (e["op"], e["pid"])
            access_area = _classify_access(prev_end.get(key),
                                            e["sector"], e["size"] // 512)
            prev_end[key] = e["sector"] + (e["size"] // 512)
            # size bucket label
            sb = next((lab for lo, hi, lab in SIZE_BINS
                       if lo <= e["size"] < hi), ">1MB")
            aligned_4k = "yes" if (e["size"] % 4096 == 0
                                    and e["sector"] % 8 == 0) else "no"
            w.writerow([OP_NAME.get(e["op"], e["op"]), e["size"], sb,
                        access_area, aligned_4k, round(e["ts"], 6)])
    written["request_size_distribution.csv"] = output_dir / "request_size_distribution.csv"

    # ─── 7. temporal_read_write_trim_pattern.csv ────────────────────────────
    n_windows = max(1, int(math.ceil(duration / WINDOW_S)))
    win_data: list[dict] = []
    for win in range(n_windows):
        t_lo = win * WINDOW_S
        t_hi = (win + 1) * WINDOW_S
        rec = {"window_start_sec": round(t_lo, 1),
               "window_end_sec":   round(min(t_hi, duration), 1),
               "read":  0, "write": 0, "trim":  0,
               "read_count": 0, "write_count": 0, "trim_count": 0}
        for e in events:
            if not (t_lo <= e["ts"] < t_hi):
                continue
            if   e["op"] == "R": rec["read"]  += e["size"]; rec["read_count"]  += 1
            elif e["op"] == "W": rec["write"] += e["size"]; rec["write_count"] += 1
            elif e["op"] == "D": rec["trim"]  += e["size"]; rec["trim_count"]  += 1
        win_data.append(rec)
    with open(output_dir / "temporal_read_write_trim_pattern.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(win_data[0].keys()))
        w.writeheader()
        w.writerows(win_data)
    written["temporal_read_write_trim_pattern.csv"] = (
        output_dir / "temporal_read_write_trim_pattern.csv")

    # ─── 8. burst_temporal_windows.csv ──────────────────────────────────────
    bursts = []
    for op_key, op_name in [("read_count", "read"),
                             ("write_count", "write"),
                             ("trim_count", "trim")]:
        counts = [rec[op_key] for rec in win_data]
        if not counts or sum(counts) == 0:
            continue
        mean = sum(counts) / len(counts)
        threshold = mean * BURST_X
        for rec, c in zip(win_data, counts):
            if c > threshold and c > 10:
                bursts.append({
                    "op":              op_name,
                    "window_start_sec": rec["window_start_sec"],
                    "window_end_sec":   rec["window_end_sec"],
                    "events":           c,
                    "threshold":        round(threshold, 2),
                })
    with open(output_dir / "burst_temporal_windows.csv", "w", newline="") as f:
        if bursts:
            w = csv.DictWriter(f, fieldnames=list(bursts[0].keys()))
            w.writeheader()
            w.writerows(bursts)
        else:
            f.write("op,window_start_sec,window_end_sec,events,threshold\n")
    written["burst_temporal_windows.csv"] = output_dir / "burst_temporal_windows.csv"

    # ─── 9. access_skew_summary.csv ─────────────────────────────────────────
    with open(output_dir / "access_skew_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "gini_coefficient", "top1pct_byte_share",
                    "top5pct_byte_share", "unique_regions"])
        for op in ("R", "W", "D"):
            region_b = [region_bytes[(eo, b)]
                         for (eo, b) in region_bytes if eo == op]
            if not region_b:
                continue
            w.writerow([OP_NAME.get(op, op),
                        round(_gini(region_b), 4),
                        round(_topk_byte_share(region_b, 1) * 100, 2),
                        round(_topk_byte_share(region_b, 5) * 100, 2),
                        len(region_b)])
    written["access_skew_summary.csv"] = output_dir / "access_skew_summary.csv"

    # ─── 10. bandwidth_degradation.csv ──────────────────────────────────────
    # Compare last quartile of run to first quartile of run.
    with open(output_dir / "bandwidth_degradation.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "early_bw_mb_s", "late_bw_mb_s", "ratio_late_early"])
        for op, op_name in [("R", "read"), ("W", "write"), ("D", "trim")]:
            evs = [e for e in events if e["op"] == op]
            if not evs:
                continue
            q1 = duration / 4
            q3 = 3 * duration / 4
            early = [e for e in evs if e["ts"] <  q1]
            late  = [e for e in evs if e["ts"] >= q3]
            early_bw = sum(e["size"] for e in early) / 1e6 / max(q1, 1e-3)
            late_bw  = sum(e["size"] for e in late)  / 1e6 / max(duration - q3, 1e-3)
            ratio    = late_bw / early_bw if early_bw > 0 else 0
            w.writerow([op_name, round(early_bw, 3), round(late_bw, 3),
                        round(ratio, 4)])
    written["bandwidth_degradation.csv"] = output_dir / "bandwidth_degradation.csv"

    # ─── 11. request_size_random_seq_correlation.csv ────────────────────────
    # corr(size_bytes, is_random_int) per op
    with open(output_dir / "request_size_random_seq_correlation.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "size_rand_corr", "n_events",
                    "mean_size_random", "mean_size_sequential"])
        prev_end_corr: dict[tuple, int] = {}
        for op in ("R", "W", "D"):
            evs = [e for e in events if e["op"] == op]
            if len(evs) < 10:
                continue
            sizes, rnd_flags = [], []
            seq_sizes, rnd_sizes = [], []
            local_prev: dict[int, int] = {}
            for e in evs:
                area = _classify_access(local_prev.get(e["pid"]),
                                         e["sector"], e["size"] // 512)
                local_prev[e["pid"]] = e["sector"] + (e["size"] // 512)
                sizes.append(e["size"])
                is_rnd = 1.0 if area == "random" else 0.0
                rnd_flags.append(is_rnd)
                (rnd_sizes if is_rnd else seq_sizes).append(e["size"])
            n = len(sizes)
            mean_s = sum(sizes) / n
            mean_r = sum(rnd_flags) / n
            cov = sum((s - mean_s) * (r - mean_r)
                      for s, r in zip(sizes, rnd_flags)) / n
            var_s = sum((s - mean_s) ** 2 for s in sizes) / n
            var_r = sum((r - mean_r) ** 2 for r in rnd_flags) / n
            denom = math.sqrt(var_s * var_r) if var_s > 0 and var_r > 0 else 0
            corr = cov / denom if denom > 0 else 0
            mean_seq = sum(seq_sizes)/len(seq_sizes) if seq_sizes else 0
            mean_rnd = sum(rnd_sizes)/len(rnd_sizes) if rnd_sizes else 0
            w.writerow([OP_NAME.get(op, op), round(corr, 4), n,
                        round(mean_rnd, 1), round(mean_seq, 1)])
    written["request_size_random_seq_correlation.csv"] = (
        output_dir / "request_size_random_seq_correlation.csv")

    log.info("blktrace_analyzer: wrote %d files to %s", len(written), output_dir)
    return {name: str(path) for name, path in written.items()}

# ---------------------------------------------------------------------------
# v1.25: streaming analyzer override
# ---------------------------------------------------------------------------
def analyze(events_csv: Path, output_dir: Path) -> dict:  # type: ignore[override]
    """Streaming blktrace analyzer for very large blkparse CSV files.

    The original analyzer materialized every event in memory and then made
    multiple full passes over the list. That is fine for small traces, but a
    6.5GB blkparse_events.generated.csv can make report generation appear to
    hang. This implementation performs one streaming pass and writes compact
    aggregate CSVs that the report consumes.
    """
    import os
    import heapq

    events_csv = Path(events_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Keep request-size CSV bounded; charts only need a representative sample.
    sample_limit = int(os.environ.get("AMOPROF_BLKTRACE_EVENT_SAMPLE_LIMIT", "200000"))
    sample_every_env = int(os.environ.get("AMOPROF_BLKTRACE_SAMPLE_EVERY", "0"))

    log.info("blktrace_analyzer(streaming): reading %s", events_csv)

    t0 = None
    t1 = None
    total_events = 0
    counts = Counter()
    bytes_by_op = Counter()
    stream_stats: dict[tuple, dict] = {}
    region_bytes: dict[tuple, int] = defaultdict(int)
    region_count: dict[tuple, int] = defaultdict(int)
    win_data: dict[int, dict] = {}
    hot_win_bytes: dict[tuple, int] = defaultdict(int)
    last_ts_by_op: dict[str, float] = {}
    iat_hist: dict[str, Counter] = defaultdict(Counter)
    iat_sum: Counter = Counter()
    iat_count: Counter = Counter()
    prev_end_by_stream: dict[tuple, int] = {}
    prev_end_corr: dict[tuple, int] = {}
    corr_stats: dict[str, dict] = defaultdict(lambda: {"n":0,"sum_s":0.0,"sum_r":0.0,"sum_s2":0.0,"sum_r2":0.0,"sum_sr":0.0,"seq_sum":0,"seq_n":0,"rnd_sum":0,"rnd_n":0})
    early_bytes = Counter()
    late_bytes = Counter()
    early_cut = late_cut = None

    req_path = output_dir / "request_size_distribution.csv"
    req_f = open(req_path, "w", newline="")
    req_w = csv.writer(req_f)
    req_w.writerow(["op", "size_bytes", "size_bucket", "access_area", "alignment_4k", "ts_sec"])
    sample_written = 0

    def _ensure_win(win: int) -> dict:
        rec = win_data.get(win)
        if rec is None:
            t_lo = win * WINDOW_S
            rec = {"window_start_sec": round(t_lo, 1),
                   "window_end_sec": round(t_lo + WINDOW_S, 1),
                   "read": 0, "write": 0, "trim": 0,
                   "read_count": 0, "write_count": 0, "trim_count": 0}
            win_data[win] = rec
        return rec

    def _iat_bin(v: float) -> str:
        for lo, hi, label in IAT_BINS:
            if lo <= v < hi:
                return label
        return IAT_BINS[-1][2]

    def _size_bucket(sz: int) -> str:
        for lo, hi, label in SIZE_BINS:
            if lo <= sz < hi:
                return label
        return ">1MB"

    try:
        with open(events_csv, newline="", encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    ts_abs = float(row.get("ts") or row.get("time_sec") or row.get("timestamp") or 0)
                    size = int(row.get("size_bytes") or (int(row.get("nsectors", 0) or 0) * 512))
                    if size <= 0:
                        continue
                    op = (row.get("op") or row.get("rwbs") or row.get("type") or "?")[:1].upper()
                    if op not in ("R", "W", "D"):
                        continue
                    pid = int(float(row.get("pid", 0) or 0))
                    comm = row.get("comm", "") or ""
                    sector = int(float(row.get("sector", 0) or 0))
                except Exception:
                    continue

                if t0 is None:
                    t0 = ts_abs
                t1 = ts_abs
                ts = ts_abs - t0
                total_events += 1
                counts[op] += 1
                bytes_by_op[op] += size

                key = (op, pid, comm)
                ss = stream_stats.setdefault(key, {"count":0,"bytes":0,"first_ts":ts,"last_ts":ts})
                ss["count"] += 1; ss["bytes"] += size
                ss["last_ts"] = ts

                bucket = (sector * 512) // LBA_BUCKET
                region_bytes[(op, bucket)] += size
                region_count[(op, bucket)] += 1

                win = int(ts // WINDOW_S)
                rec = _ensure_win(win)
                if op == "R": rec["read"] += size; rec["read_count"] += 1
                elif op == "W": rec["write"] += size; rec["write_count"] += 1
                elif op == "D": rec["trim"] += size; rec["trim_count"] += 1
                hot_win_bytes[(win, op, bucket)] += size

                if op in last_ts_by_op:
                    iat_us = (ts - last_ts_by_op[op]) * 1e6
                    if iat_us > 0:
                        iat_hist[op][_iat_bin(iat_us)] += 1
                        iat_sum[op] += iat_us
                        iat_count[op] += 1
                last_ts_by_op[op] = ts

                # bounded request-size/event sample
                take_sample = False
                if sample_limit <= 0:
                    take_sample = False
                elif sample_every_env > 0:
                    take_sample = (total_events % sample_every_env == 0)
                else:
                    # deterministic early sample; avoids memory and is enough for charts.
                    take_sample = sample_written < sample_limit
                if take_sample:
                    k = (op, pid)
                    access_area = _classify_access(prev_end_by_stream.get(k), sector, size // 512)
                    prev_end_by_stream[k] = sector + (size // 512)
                    aligned_4k = "yes" if (size % 4096 == 0 and sector % 8 == 0) else "no"
                    req_w.writerow([OP_NAME.get(op, op), size, _size_bucket(size), access_area, aligned_4k, round(ts, 6)])
                    sample_written += 1

                # correlation stats use streaming moments
                ck = (op, pid)
                area = _classify_access(prev_end_corr.get(ck), sector, size // 512)
                prev_end_corr[ck] = sector + (size // 512)
                rnd = 1.0 if area == "random" else 0.0
                st = corr_stats[op]
                st["n"] += 1; st["sum_s"] += size; st["sum_r"] += rnd
                st["sum_s2"] += size * size; st["sum_r2"] += rnd * rnd; st["sum_sr"] += size * rnd
                if rnd: st["rnd_sum"] += size; st["rnd_n"] += 1
                else: st["seq_sum"] += size; st["seq_n"] += 1
    finally:
        req_f.close()

    if not total_events or t0 is None or t1 is None:
        log.warning("blktrace_analyzer(streaming): no events found in %s", events_csv)
        return {}

    duration = max(t1 - t0, 1e-6)
    q1 = duration / 4.0
    q3 = 3.0 * duration / 4.0

    # second lightweight pass only for early/late bytes; avoids storing events
    with open(events_csv, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ts = float(row.get("ts") or row.get("time_sec") or row.get("timestamp") or 0) - t0
                size = int(row.get("size_bytes") or (int(row.get("nsectors", 0) or 0) * 512))
                op = (row.get("op") or row.get("rwbs") or row.get("type") or "?")[:1].upper()
                if size <= 0 or op not in ("R", "W", "D"):
                    continue
            except Exception:
                continue
            if ts < q1:
                early_bytes[op] += size
            elif ts >= q3:
                late_bytes[op] += size

    written: dict[str, Path] = {"request_size_distribution.csv": req_path}

    summary = {
        "duration_sec": round(duration, 3),
        "total_events": int(total_events),
        "read_events": int(counts["R"]), "write_events": int(counts["W"]), "trim_events": int(counts["D"]),
        "read_bytes_total": int(bytes_by_op["R"]), "write_bytes_total": int(bytes_by_op["W"]), "trim_bytes_total": int(bytes_by_op["D"]),
        "rw_ratio": counts["R"] / max(counts["W"], 1),
        "read_iops_mean": round(counts["R"] / duration, 2),
        "write_iops_mean": round(counts["W"] / duration, 2),
        "trim_iops_mean": round(counts["D"] / duration, 4),
        "read_bw_mb_s_mean": round(bytes_by_op["R"] / 1e6 / duration, 2),
        "write_bw_mb_s_mean": round(bytes_by_op["W"] / 1e6 / duration, 2),
        "trim_present": counts["D"] > 0,
        "streaming_analyzer": True,
        "request_size_sampled_events": sample_written,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    written["summary.json"] = output_dir / "summary.json"

    with open(output_dir / "bandwidth_per_stream.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["op","stream","pid","comm","count","bytes","duration_sec","bandwidth_mib_s"])
        for (op, pid, comm), s in stream_stats.items():
            dur = max(s["last_ts"] - s["first_ts"], 1e-3)
            bw = s["bytes"] / 1048576.0 / dur
            w.writerow([OP_NAME.get(op, op), f"{comm}:{pid}", pid, comm, s["count"], s["bytes"], round(dur,3), round(bw,3)])
    written["bandwidth_per_stream.csv"] = output_dir / "bandwidth_per_stream.csv"

    with open(output_dir / "bandwidth_per_stream_summary.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["op","n_streams","bandwidth_mib_s_mean","bandwidth_mib_s_max"])
        for op in ("R","W","D"):
            bws=[]
            for (eo,_,_), s in stream_stats.items():
                if eo == op:
                    dur=max(s["last_ts"]-s["first_ts"],1e-3); bws.append(s["bytes"]/1048576.0/dur)
            if bws: w.writerow([OP_NAME.get(op,op), len(bws), round(sum(bws)/len(bws),3), round(max(bws),3)])
    written["bandwidth_per_stream_summary.csv"] = output_dir / "bandwidth_per_stream_summary.csv"

    with open(output_dir / "hot_regions_overall.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["op","region","lba_bucket_start","lba_bucket_end","bytes","count"])
        for op in ("R","W","D"):
            items=[(bucket, region_count[(op,bucket)], b) for (eo,bucket), b in region_bytes.items() if eo==op]
            for bucket,count,b in sorted(items, key=lambda x:x[2], reverse=True)[:50]:
                w.writerow([OP_NAME.get(op,op), bucket, bucket*LBA_BUCKET, (bucket+1)*LBA_BUCKET, b, count])
    written["hot_regions_overall.csv"] = output_dir / "hot_regions_overall.csv"

    with open(output_dir / "hot_regions_by_time_window.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["window_start_sec","op","lba_bucket_start","lba_bucket_end","bytes"])
        by_win=defaultdict(list)
        for (win,op,bucket), b in hot_win_bytes.items(): by_win[win].append((b,op,bucket))
        for win, items in by_win.items():
            for b,op,bucket in sorted(items, reverse=True)[:10]:
                w.writerow([round(win*WINDOW_S,1), OP_NAME.get(op,op), bucket*LBA_BUCKET, (bucket+1)*LBA_BUCKET, b])
    written["hot_regions_by_time_window.csv"] = output_dir / "hot_regions_by_time_window.csv"

    with open(output_dir / "interarrival_distribution.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["op","bin_label","lower_us","upper_us","count","inter_arrival_us_mean"])
        for op in ("R","W","D"):
            mean = (iat_sum[op] / iat_count[op]) if iat_count[op] else 0
            for lo,hi,label in IAT_BINS:
                w.writerow([OP_NAME.get(op,op), label, lo, hi, iat_hist[op][label], round(mean,2)])
    written["interarrival_distribution.csv"] = output_dir / "interarrival_distribution.csv"

    ordered_wins = [win_data[k] for k in sorted(win_data)]
    with open(output_dir / "temporal_read_write_trim_pattern.csv", "w", newline="") as f:
        fields=["window_start_sec","window_end_sec","read","write","trim","read_count","write_count","trim_count"]
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(ordered_wins)
    written["temporal_read_write_trim_pattern.csv"] = output_dir / "temporal_read_write_trim_pattern.csv"

    bursts=[]
    for key,op_name in [("read_count","read"),("write_count","write"),("trim_count","trim")]:
        vals=[rec[key] for rec in ordered_wins]
        if vals and sum(vals)>0:
            mean=sum(vals)/len(vals); threshold=mean*BURST_X
            for rec,c in zip(ordered_wins,vals):
                if c>threshold and c>10:
                    bursts.append({"op":op_name,"window_start_sec":rec["window_start_sec"],"window_end_sec":rec["window_end_sec"],"events":c,"threshold":round(threshold,2)})
    with open(output_dir / "burst_temporal_windows.csv", "w", newline="") as f:
        fields=["op","window_start_sec","window_end_sec","events","threshold"]
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(bursts)
    written["burst_temporal_windows.csv"] = output_dir / "burst_temporal_windows.csv"

    with open(output_dir / "access_skew_summary.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["op","gini_coefficient","top1pct_byte_share","top5pct_byte_share","unique_regions"])
        for op in ("R","W","D"):
            vals=[b for (eo,_), b in region_bytes.items() if eo==op]
            if vals: w.writerow([OP_NAME.get(op,op), round(_gini(vals),4), round(_topk_byte_share(vals,1)*100,2), round(_topk_byte_share(vals,5)*100,2), len(vals)])
    written["access_skew_summary.csv"] = output_dir / "access_skew_summary.csv"

    with open(output_dir / "bandwidth_degradation.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["op","early_bw_mb_s","late_bw_mb_s","ratio_late_early"])
        for op in ("R","W","D"):
            eb=early_bytes[op]/1e6/max(q1,1e-3); lb=late_bytes[op]/1e6/max(duration-q3,1e-3)
            if early_bytes[op] or late_bytes[op]: w.writerow([OP_NAME.get(op,op), round(eb,3), round(lb,3), round((lb/eb if eb>0 else 0),4)])
    written["bandwidth_degradation.csv"] = output_dir / "bandwidth_degradation.csv"

    with open(output_dir / "request_size_random_seq_correlation.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["op","size_rand_corr","n_events","mean_size_random","mean_size_sequential"])
        for op,st in corr_stats.items():
            n=st["n"]
            if n<10: continue
            ms=st["sum_s"]/n; mr=st["sum_r"]/n
            cov=st["sum_sr"]/n - ms*mr
            vs=st["sum_s2"]/n - ms*ms; vr=st["sum_r2"]/n - mr*mr
            denom=math.sqrt(max(vs,0)*max(vr,0))
            corr=cov/denom if denom>0 else 0
            mean_r=st["rnd_sum"]/st["rnd_n"] if st["rnd_n"] else 0
            mean_s=st["seq_sum"]/st["seq_n"] if st["seq_n"] else 0
            w.writerow([OP_NAME.get(op,op), round(corr,4), int(n), round(mean_r,1), round(mean_s,1)])
    written["request_size_random_seq_correlation.csv"] = output_dir / "request_size_random_seq_correlation.csv"

    log.info("blktrace_analyzer(streaming): wrote %d files to %s; events=%d sample=%d", len(written), output_dir, total_events, sample_written)
    return {name: str(path) for name, path in written.items()}
