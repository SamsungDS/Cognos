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
                # Only count completion events (action='C').
                # The blkparse CSV contains all event types (Q, G, I, D, C, …);
                # counting every type would 3–5× overcount bytes per I/O.
                action = row.get("action", "C")
                if action and action.upper() != "C":
                    continue
                ts = float(row["ts"])
                size = int(row.get("size_bytes") or
                           (int(row.get("nsectors", 0)) * 512))
                if size <= 0:
                    continue
                # Derive direction from normalized op/rwbs.  Do not infer
                # read from a completion with missing direction: that silently
                # turns write-heavy HiCache offload into a read-heavy SSD chart.
                # Unknown completions are skipped below.
                op = _normalise_block_op(row)
                if op not in ("R", "W", "D"):
                    continue
                rows.append({
                    "ts":     ts,
                    "pid":    int(row.get("pid", 0) or 0),
                    "comm":   row.get("comm", "") or "",
                    "op":     op,
                    "sector": int(row.get("sector", 0) or 0),
                    "size":   size,
                    "action": action,
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


def _normalise_block_op(row: dict) -> str:
    """Return R/W/D for one blkparse CSV row, or '?' if unknown.

    AMOprof's blkparse CSV contains both a normalized ``op`` column and the
    original blkparse ``rwbs`` flags.  Completion rows are the only rows that
    represent device bytes.  Prefer the normalized op, but derive from rwbs as
    a fallback.  Importantly, do **not** use the blkparse action letter ``D``
    (dispatch) as a discard/trim signal; discard must come from rwbs/op.
    """
    op_raw = (row.get("op") or "").strip().upper()
    if op_raw[:1] in ("R", "W", "D"):
        return op_raw[:1]
    rwbs = (row.get("rwbs") or row.get("type") or "").strip().upper()
    if "D" in rwbs:
        return "D"
    if "W" in rwbs:
        return "W"
    if "R" in rwbs:
        return "R"
    return "?"


def _is_completion_row(row: dict) -> bool:
    """True when a blkparse CSV row represents completed device I/O.

    Bytes must be counted only once per I/O. blkparse emits multiple lifecycle
    actions (Q/G/I/D/C). Counting all of them inflates and distorts SSD/L3
    distributions, especially in the streaming analyzer used for large traces.
    """
    action = (row.get("action") or "C").strip().upper()
    return action == "C"


def _merge_collector_diagnostics_into_summary(summary: dict, bt_sum_path: Path) -> None:
    """Pull collector-side /sys/block deltas + dropped-event info into the
    analyzer summary, and emit a coverage_warning string when blktrace's
    captured bytes are far below the kernel counter.

    This handles two related signals the reader needs to interpret op counts:

      1. captured_vs_kernel_ratio — if blktrace bytes << kernel sectors_written,
         events were dropped or the wrong device was traced (real measurement gap).
      2. sys_block_*_merge_ratio — fraction of submitted BIOs that got coalesced
         by the block layer before dispatch. HIGH merge ratios mean the kernel
         issued fewer, larger I/Os to the device than the FS submitted — this is
         healthy behaviour, not data loss. XFS extent-based allocation triggers
         this much more than ext4 block-based allocation.

    Without these two together, a reader seeing "fewer ops on XFS than ext4"
    cannot tell whether they lost data or whether the FS just did its job better.
    """
    try:
        if not bt_sum_path.exists():
            return
        import json as _json
        bts = _json.loads(bt_sum_path.read_text(encoding="utf-8"))
    except Exception as _e:
        log.debug("could not read blktrace collector summary: %s", _e)
        return

    kernel_wr_gb   = float(bts.get("sys_block_wr_gb_delta") or 0)
    kernel_rd_gb   = float(bts.get("sys_block_rd_gb_delta") or 0)
    captured_wr_gb = summary.get("write_bytes_total", 0) / 1e9
    captured_rd_gb = summary.get("read_bytes_total", 0) / 1e9
    if kernel_wr_gb > 0:
        ratio = captured_wr_gb / kernel_wr_gb if kernel_wr_gb > 0 else 0.0
        summary["kernel_wr_gb_delta"]       = round(kernel_wr_gb, 2)
        summary["captured_vs_kernel_ratio"] = round(ratio, 3)
        summary["blktrace_device"]          = bts.get("blktrace_device", "")
        if ratio < 0.5:
            summary["coverage_warning"] = (
                f"⚠ blktrace captured only {captured_wr_gb:.3f} GB of writes "
                f"but the kernel's /sys/block/<dev>/stat write counter "
                f"advanced by {kernel_wr_gb:.3f} GB during the trace window "
                f"({ratio*100:.1f}% capture). "
                f"Likely causes: (1) blktrace ring buffer overran (check "
                f"blktrace_summary.json :: blktrace_dropped_events and "
                f"blktrace_per_cpu_dropped — raise blktrace -b to 16384+); "
                f"(2) wrong device traced (collected {bts.get('blktrace_device','?')} "
                f"but writes hit a different namespace); "
                f"(3) cache striped across multiple NVMes (trace each); "
                f"(4) writes are buffered/delayed outside the selected SGLang window."
            )
    if kernel_rd_gb > 0:
        rratio = captured_rd_gb / kernel_rd_gb if kernel_rd_gb > 0 else 0.0
        summary["kernel_rd_gb_delta"] = round(kernel_rd_gb, 2)
        summary["captured_vs_kernel_read_ratio"] = round(rratio, 3)
        if rratio < 0.5:
            prev = summary.get("coverage_warning", "")
            msg = (
                f"⚠ blktrace captured only {captured_rd_gb:.3f} GB of reads while "
                f"kernel read counter advanced by {kernel_rd_gb:.3f} GB ({rratio*100:.1f}% capture). "
                f"Check traced device, dropped events, and multi-device/RAID/cache mapping."
            )
            summary["coverage_warning"] = (prev + " " + msg).strip()

    # Propagate the collector's own dropped-events warning if present
    if bts.get("blktrace_coverage_warning"):
        summary["blktrace_collector_warning"] = bts["blktrace_coverage_warning"]
    if bts.get("blktrace_dropped_events", 0) > 0:
        summary["blktrace_dropped_events"]  = bts["blktrace_dropped_events"]
        summary["blktrace_per_cpu_dropped"] = bts.get("blktrace_per_cpu_dropped", {})

    # ── Block-layer merge diagnostics ────────────────────────────────────────
    # These let the report distinguish "captured ops dropped because of XFS
    # merging" from "captured ops dropped because of trace loss". Both can
    # produce the same superficial symptom (fewer events than expected).
    for k in ("sys_block_rd_ios_delta",     "sys_block_wr_ios_delta",
              "sys_block_rd_merges_delta",  "sys_block_wr_merges_delta",
              "sys_block_rd_merge_ratio",   "sys_block_wr_merge_ratio",
              "sys_block_avg_rd_io_kb",     "sys_block_avg_wr_io_kb",
              "sys_block_rd_gb_delta"):
        if k in bts:
            summary[k] = bts[k]

    # ── Emit a positive (informational) finding when block-layer merging is
    # significant. Without this, a user comparing op counts before/after a
    # filesystem swap (ext4→XFS) would see "fewer ops" and assume data loss.
    wr_merge_ratio = float(bts.get("sys_block_wr_merge_ratio") or 0)
    rd_merge_ratio = float(bts.get("sys_block_rd_merge_ratio") or 0)
    avg_wr_io_kb   = float(bts.get("sys_block_avg_wr_io_kb")   or 0)
    if wr_merge_ratio >= 0.3 or rd_merge_ratio >= 0.3:
        summary["block_layer_merge_note"] = (
            f"Block layer coalesced "
            f"{wr_merge_ratio*100:.0f}% of write BIOs and "
            f"{rd_merge_ratio*100:.0f}% of read BIOs before dispatching to the "
            f"device. Average dispatched I/O size: {avg_wr_io_kb:.1f} KB write. "
            f"Fewer captured ops on this FS than ext4 is expected and not a "
            f"measurement gap — the filesystem merged adjacent operations into "
            f"larger BIOs."
        )


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



def _write_queue_depth_outputs(output_dir: Path,
                               qd_samples: list[tuple[float, int, int, int]],
                               time_at_qd: dict[int, float],
                               qd_max: int,
                               bucket_s: float,
                               source: str,
                               q_events: int = 0,
                               c_events: int = 0,
                               order_inversions: int = 0,
                               mean_lat_s: float = 0.0) -> dict:
    """Write queue-depth CSVs/summary from already computed QD samples."""
    if not qd_samples or not time_at_qd:
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)

    ts_csv = output_dir / "queue_depth_timeseries.csv"
    with ts_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_sec", "qd_total", "qd_read", "qd_write", "source"])
        for t_rel, qd, qr, qw in qd_samples:
            w.writerow([f"{t_rel:.3f}", qd, qr, qw, source])

    total_time = sum(time_at_qd.values())
    hist_csv = output_dir / "queue_depth_distribution.csv"
    with hist_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qd_value", "time_sec", "pct_of_run", "source"])
        for qd in sorted(time_at_qd):
            t = time_at_qd[qd]
            w.writerow([qd, f"{t:.3f}", f"{(t/total_time*100):.2f}" if total_time > 0 else "0", source])

    def _time_weighted_percentile(p: float) -> float:
        cum = 0.0
        target = p * total_time
        for qd in sorted(time_at_qd):
            cum += time_at_qd[qd]
            if cum >= target:
                return float(qd)
        return float(max(time_at_qd) if time_at_qd else 0)

    qd_mean = (sum(qd * t for qd, t in time_at_qd.items()) / total_time
               if total_time > 0 else 0)
    sat_pcts = {}
    for cap_candidate in (32, 64, 128, 256, 1024):
        t_at_or_above = sum(t for qd, t in time_at_qd.items() if qd >= cap_candidate)
        sat_pcts[f"pct_at_qd_ge_{cap_candidate}"] = round(
            t_at_or_above / total_time * 100, 2) if total_time > 0 else 0

    summary = {
        "qd_mean": round(qd_mean, 2),
        "qd_p50": round(_time_weighted_percentile(0.50), 1),
        "qd_p95": round(_time_weighted_percentile(0.95), 1),
        "qd_p99": round(_time_weighted_percentile(0.99), 1),
        "qd_max": qd_max,
        "qd_samples_count": len(qd_samples),
        "qd_bucket_s": bucket_s,
        "qd_total_time_s": round(total_time, 3),
        "qd_source": source,
        "q_events_seen": int(q_events),
        "c_events_seen": int(c_events),
        # Ordering hygiene. Queue depth is a function of event order, so a
        # non-zero count here means the stream needed sorting before Q/C were
        # counted -- and that any earlier run of this analyser, which did not
        # sort, produced a depth derived from the wrong sequence.
        "qd_order_inversions": int(order_inversions),
        **sat_pcts,
    }

    # Little's Law cross-check: QD = throughput x latency.
    #
    # A measured qd_max of 1 has two very different explanations -- an I/O
    # path that issues one request and waits, or an event sequence whose Q and
    # C alternate for a reason that has nothing to do with the device -- and
    # they are indistinguishable from the depth alone. IOPS and mean latency
    # are measured independently of the depth, so their product is an
    # independent estimate of it. Agreement corroborates a serialized path;
    # disagreement says the depth is not measuring what it claims.
    _iops = (q_events / total_time) if total_time > 0 else 0.0
    summary["qd_iops_from_q_events"] = round(_iops, 1)
    if _iops > 0 and mean_lat_s > 0:
        _expected = _iops * mean_lat_s
        summary["qd_mean_lat_ms"] = round(mean_lat_s * 1e3, 4)
        summary["qd_expected_littles_law"] = round(_expected, 3)
        _ratio = (max(_expected, qd_mean) / max(min(_expected, qd_mean), 1e-9)
                  if qd_mean > 0 else 0.0)
        summary["qd_littles_law_ratio"] = round(_ratio, 2)
        summary["qd_consistency"] = (
            "consistent" if (qd_mean > 0 and _ratio <= 2.0) else
            "measured depth disagrees with IOPS x latency by "
            f"{_ratio:.1f}x — treat the depth as unverified")
    else:
        summary["qd_consistency"] = "not cross-checkable (no latency sample)"
    (output_dir / "queue_depth_summary.json").write_text(json.dumps(summary, indent=2))
    log.info("queue depth[%s]: mean=%.1f, p95=%.0f, max=%d (%d samples over %.1fs)",
             source, qd_mean, _time_weighted_percentile(0.95), qd_max,
             len(qd_samples), total_time)
    return {"queue_depth_timeseries.csv": ts_csv,
            "queue_depth_distribution.csv": hist_csv,
            "queue_depth_summary.json": output_dir / "queue_depth_summary.json"}


# ─── Q→C latency histogram (log-scale, memory-safe) ─────────────────────────
# We stream millions of Q/C pairs so a flat array of dwell times is too big.
# Instead, per direction we keep a log-scale histogram (~30 buckets) which
# gives sub-percent accuracy on p50/p95/p99 with fixed memory.
_LAT_BUCKET_EDGES_US = [
    1, 2, 4, 8, 16, 32, 64, 128, 256, 512,
    1_024, 2_048, 4_096, 8_192, 16_384, 32_768, 65_536,
    131_072, 262_144, 524_288, 1_048_576, 2_097_152, 4_194_304,
    8_388_608, 16_777_216,   # 16 s
]


def _lat_bucket_index(us: float) -> int:
    """Return the index of the log-scale bucket that contains `us`."""
    if us <= 0:
        return 0
    for i, edge in enumerate(_LAT_BUCKET_EDGES_US):
        if us <= edge:
            return i
    return len(_LAT_BUCKET_EDGES_US) - 1


def _bucket_percentile_us(buckets: list[int], p: float) -> float:
    """Estimate a percentile from a log-scale bucketed histogram.

    Uses linear interpolation within the winning bucket, in log space,
    between its lower and upper edges. Good enough for report tiles;
    NOT a substitute for streaming exact percentiles when caller needs
    <1% error.
    """
    total = sum(buckets)
    if total <= 0:
        return 0.0
    target = p * total
    cum = 0
    for i, cnt in enumerate(buckets):
        cum += cnt
        if cum >= target:
            lo = _LAT_BUCKET_EDGES_US[i - 1] if i > 0 else 0
            hi = _LAT_BUCKET_EDGES_US[i]
            # Linear interp within the bucket (in log space) using the
            # position of `target` inside the bucket's cumulative range.
            if cnt <= 0:
                return float(hi)
            frac = (target - (cum - cnt)) / cnt
            return lo + (hi - lo) * frac
    return float(_LAT_BUCKET_EDGES_US[-1])


def _write_latency_outputs(output_dir: Path,
                           read_buckets: list[int],
                           write_buckets: list[int],
                           source: str = "blktrace_q_to_c") -> dict:
    """Write Q→C latency histogram + summary derived from `read_buckets`
    and `write_buckets` (one count per _LAT_BUCKET_EDGES_US slot).

    Emits:
      • blktrace_latency_histogram.csv  (bucket_edge_us, read_count, write_count, source)
      • blktrace_latency_summary.json   (per-direction p50/p95/p99 + sample counts)
    """
    if not any(read_buckets) and not any(write_buckets):
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)

    hist_csv = output_dir / "blktrace_latency_histogram.csv"
    with hist_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bucket_upper_us", "read_count", "write_count", "source"])
        for i, edge in enumerate(_LAT_BUCKET_EDGES_US):
            w.writerow([edge, read_buckets[i], write_buckets[i], source])

    def _stats(bkts: list[int]) -> dict:
        n = sum(bkts)
        if n <= 0:
            return {"samples": 0, "p50_us": 0.0, "p95_us": 0.0, "p99_us": 0.0}
        return {
            "samples": int(n),
            "p50_us":  round(_bucket_percentile_us(bkts, 0.50), 1),
            "p95_us":  round(_bucket_percentile_us(bkts, 0.95), 1),
            "p99_us":  round(_bucket_percentile_us(bkts, 0.99), 1),
        }

    summary = {
        "lat_source": source,
        "read":  _stats(read_buckets),
        "write": _stats(write_buckets),
    }
    (output_dir / "blktrace_latency_summary.json").write_text(
        json.dumps(summary, indent=2))
    log.info("blktrace latency[%s]: read p99=%.0fus (n=%d), write p99=%.0fus (n=%d)",
             source, summary["read"]["p99_us"], summary["read"]["samples"],
             summary["write"]["p99_us"], summary["write"]["samples"])
    return {"blktrace_latency_histogram.csv": hist_csv,
            "blktrace_latency_summary.json": output_dir / "blktrace_latency_summary.json"}


def _compute_queue_depth_from_csv(events_csv: Path, output_dir: Path,
                                  bucket_s: float = 1.0,
                                  source: str = "blkparse_events_csv_q_to_c") -> dict:
    """Fallback QD pass from blkparse_events.generated.csv.

    Requires rows containing both action=Q and action=C. If the CSV was capped to
    completions only, this returns {} so the report can fall back to iostat/sysfs.
    """
    if not events_csv.exists():
        return {}
    qd_total = qd_read = qd_write = 0
    qd_samples: list[tuple[float, int, int, int]] = []
    time_at_qd: dict[int, float] = {}
    last_event_t = None
    qd_max = 0
    t0 = None
    q_events = c_events = 0
    # Value is (op, q_t_rel); q_t_rel lets us compute per-request Q→C dwell
    # time when the matching C event arrives. Keys are only removed on C, so
    # the dict grows unbounded when C events arrive without a matching Q
    # (already a pre-existing behavior); we do NOT change that.
    pending_op: dict[tuple[str, str, str], tuple[str, float]] = {}
    # Log-scale latency histograms — one bucket count per _LAT_BUCKET_EDGES_US
    # slot per direction. Sized once for constant memory.
    read_lat_buckets  = [0] * len(_LAT_BUCKET_EDGES_US)
    write_lat_buckets = [0] * len(_LAT_BUCKET_EDGES_US)

    # Queue depth is a function of event ORDER, so the stream must be in time
    # order before Q/C are counted.
    #
    # This pass walked the CSV in file order while its sibling,
    # analyze_from_events_csv, sorts the same file by ts before doing anything
    # with it. Any inversion therefore produced a different queue depth here
    # than everywhere else: a Q that arrives after its own C decrements before
    # it increments, and a stream whose Q and C alternate pins qd_max at 1 no
    # matter how much concurrency the device actually saw. Reading the rows
    # first and sorting them costs one pass and removes the whole class.
    _order_inversions = 0
    try:
        with open(events_csv, newline="", encoding="utf-8", errors="replace") as f:
            _rows_in = [_r for _r in csv.DictReader(f)
                        if (_r.get("action") or "").strip().upper() in ("Q", "C")]
    except Exception:
        _rows_in = []

    def _row_ts(_r):
        try:
            return float(_r.get("ts") or _r.get("time_sec")
                         or _r.get("timestamp") or 0)
        except Exception:
            return 0.0

    _prev_ts = None
    for _r in _rows_in:
        _ts = _row_ts(_r)
        if _prev_ts is not None and _ts < _prev_ts:
            _order_inversions += 1
        _prev_ts = _ts
    if _order_inversions:
        log.warning("queue depth: %d out-of-order event(s) in %s — sorting by "
                    "timestamp before Q/C accounting", _order_inversions,
                    events_csv.name)
        _rows_in.sort(key=_row_ts)

    try:
        for row in _rows_in:
            action = (row.get("action") or "").strip().upper()
            if action not in ("Q", "C"):
                continue
            try:
                t_abs = float(row.get("ts") or row.get("time_sec") or row.get("timestamp") or 0)
            except Exception:
                continue
            if t0 is None:
                t0 = t_abs
            t_rel = t_abs - t0
            op = _normalise_block_op(row)
            nsec = str(row.get("nsectors") or row.get("nsec") or "0")
            req_key = (str(row.get("pid") or "0"), str(row.get("sector") or "0"), nsec)
            if action == "Q":
                q_events += 1
            else:
                c_events += 1

            if last_event_t is not None:
                dt = t_rel - last_event_t
                if dt > 0:
                    time_at_qd[qd_total] = time_at_qd.get(qd_total, 0.0) + dt
            last_event_t = t_rel

            if action == "Q":
                if op in ("R", "W", "D"):
                    pending_op[req_key] = (op, t_rel)
                qd_total += 1
                if op == "R": qd_read += 1
                elif op == "W": qd_write += 1
                qd_max = max(qd_max, qd_total)
            else:
                # On C, always consume pending_op so the dict stays bounded
                # AND we can compute latency. Fall back to the C row's own
                # op letter when no Q was ever seen for this key.
                _pending = pending_op.pop(req_key, None)
                if _pending is not None:
                    _op_q, _t_q = _pending
                    dt_us = max((t_rel - _t_q) * 1e6, 0.0)
                    _op_for_lat = _op_q if _op_q in ("R", "W") else (op if op in ("R", "W") else "")
                    if _op_for_lat == "R":
                        read_lat_buckets[_lat_bucket_index(dt_us)] += 1
                    elif _op_for_lat == "W":
                        write_lat_buckets[_lat_bucket_index(dt_us)] += 1
                    if op not in ("R", "W", "D"):
                        op = _op_q
                qd_total = max(qd_total - 1, 0)
                if op == "R": qd_read = max(qd_read - 1, 0)
                elif op == "W": qd_write = max(qd_write - 1, 0)

            if qd_samples and (t_rel - qd_samples[-1][0]) < bucket_s:
                last = qd_samples[-1]
                qd_samples[-1] = (last[0], max(last[1], qd_total),
                                   max(last[2], qd_read), max(last[3], qd_write))
            else:
                qd_samples.append((t_rel, qd_total, qd_read, qd_write))
    except Exception as e:
        log.warning("queue depth CSV fallback failed: %s", e)
        return {}

    if q_events <= 0:
        log.warning("queue depth CSV fallback skipped: %s has %d C events but no Q events", events_csv, c_events)
        return {}

    # Latency emission is best-effort; QD outputs are the primary result and
    # must not be affected by a latency-write failure.
    try:
        _write_latency_outputs(output_dir, read_lat_buckets, write_lat_buckets,
                               source="blktrace_q_to_c")
    except Exception as _e:
        log.warning("latency emission failed (QD outputs still written): %s", _e)

    # Mean Q->C latency from the histograms this pass already filled, as the
    # geometric midpoint of each log-scale bucket. Only needed to the nearest
    # factor of two, since it feeds a consistency check rather than a reported
    # latency figure.
    _mean_lat_s = 0.0
    try:
        _n_lat = sum(read_lat_buckets) + sum(write_lat_buckets)
        if _n_lat > 0:
            _acc_us = 0.0
            for _bi, _edge in enumerate(_LAT_BUCKET_EDGES_US):
                _cnt = read_lat_buckets[_bi] + write_lat_buckets[_bi]
                if not _cnt:
                    continue
                _lo = _LAT_BUCKET_EDGES_US[_bi - 1] if _bi else 0.0
                _mid = ((_lo * _edge) ** 0.5) if _lo > 0 else (_edge / 2.0)
                _acc_us += _mid * _cnt
            _mean_lat_s = (_acc_us / _n_lat) / 1e6
    except Exception:
        _mean_lat_s = 0.0

    return _write_queue_depth_outputs(output_dir, qd_samples, time_at_qd, qd_max,
                                      bucket_s, source, q_events, c_events,
                                      order_inversions=_order_inversions,
                                      mean_lat_s=_mean_lat_s)


def _compute_queue_depth_timeseries(bin_dir: Path, output_dir: Path,
                                     blkparse_bin: str = "blkparse",
                                     bucket_s: float = 1.0) -> dict:
    """Compute true SSD queue-depth time series + distribution from blktrace.

    Uses the raw blktrace binaries and walks Q (queued) → C (completed) events.
    This path intentionally uses blkparse's default text output plus robust
    parsers for modern and legacy formats. Older builds used a custom `-f`
    formatter that fails on some blkparse versions, which made the SSD Queue
    Depth section appear empty even though blktrace data was collected.
    """
    import subprocess as _sp
    import re as _re

    if not bin_dir.exists():
        return {}
    bins = sorted(bin_dir.glob("trace.blktrace.*"))
    if not bins:
        return {}

    prefix = bin_dir / "trace"
    cmd = [blkparse_bin, "-i", str(prefix)]

    _LINE_RE = _re.compile(
        r"^\s*(?P<major>\d+),(?P<minor>\d+)\s+(?P<cpu>\d+)\s+\d+\s+"
        r"(?P<ts>[\d.]+)\s+(?P<pid>\d+)\s+"
        r"(?P<action>[A-Z])\s+(?P<rwbs>[A-Z]*)\s*"
        r"(?P<sector>\d+)\s+\+\s+(?P<nsec>\d+)"
        r"(?:\s+\[(?P<comm>[^\]]+)\])?"
    )
    _LINE_RE_OLD = _re.compile(
        r"^\s*(?P<ts>[\d.]+)\s+(?P<pid>\d+)\s+"
        r"(?P<action>[A-Z])\s+(?P<rwbs>[A-Z]*)\s+"
        r"(?P<major>\d+),(?P<minor>\d+)\s+"
        r"(?P<sector>\d+)\s+\+\s+(?P<nsec>\d+)"
        r"(?:\s+\[(?P<comm>[^\]]+)\])?"
    )

    qd_total = qd_read = qd_write = 0
    qd_samples: list[tuple[float, int, int, int]] = []
    time_at_qd: dict[int, float] = {}
    last_event_t = None
    qd_max = 0
    t0 = None
    q_events = c_events = 0
    # (op, q_t_rel) — the timestamp lets us compute per-request latency at C.
    pending_op: dict[tuple[str, str, str], tuple[str, float]] = {}
    read_lat_buckets  = [0] * len(_LAT_BUCKET_EDGES_US)
    write_lat_buckets = [0] * len(_LAT_BUCKET_EDGES_US)
    unmatched_sample: list[str] = []

    try:
        with _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.PIPE, text=True) as proc:
            if proc.stdout is None:
                return {}
            for raw in proc.stdout:
                m = _LINE_RE.match(raw) or _LINE_RE_OLD.match(raw)
                if not m:
                    if len(unmatched_sample) < 3 and raw.strip():
                        st = raw.strip()
                        if not (st.startswith("CPU") or st.startswith("Input") or st.startswith("Total") or st.startswith("Events")):
                            unmatched_sample.append(st[:160])
                    continue
                d = m.groupdict()
                action = d.get("action") or ""
                if action not in ("Q", "C"):
                    continue
                try:
                    t_abs = float(d.get("ts") or 0.0)
                except Exception:
                    continue
                if t0 is None:
                    t0 = t_abs
                t_rel = t_abs - t0
                rwbs = d.get("rwbs") or ""
                if "D" in rwbs: op = "D"
                elif "W" in rwbs: op = "W"
                elif "R" in rwbs: op = "R"
                else: op = "?"
                nsec = str(d.get("nsec") or "0")
                req_key = (d.get("pid") or "0", d.get("sector") or "0", nsec)
                if action == "Q": q_events += 1
                else: c_events += 1

                if last_event_t is not None:
                    dt = t_rel - last_event_t
                    if dt > 0:
                        time_at_qd[qd_total] = time_at_qd.get(qd_total, 0.0) + dt
                last_event_t = t_rel

                if action == "Q":
                    if op in ("R", "W", "D"):
                        pending_op[req_key] = (op, t_rel)
                    qd_total += 1
                    if op == "R": qd_read += 1
                    elif op == "W": qd_write += 1
                    qd_max = max(qd_max, qd_total)
                else:
                    _pending = pending_op.pop(req_key, None)
                    if _pending is not None:
                        _op_q, _t_q = _pending
                        dt_us = max((t_rel - _t_q) * 1e6, 0.0)
                        _op_for_lat = _op_q if _op_q in ("R", "W") else (op if op in ("R", "W") else "")
                        if _op_for_lat == "R":
                            read_lat_buckets[_lat_bucket_index(dt_us)] += 1
                        elif _op_for_lat == "W":
                            write_lat_buckets[_lat_bucket_index(dt_us)] += 1
                        if op not in ("R", "W", "D"):
                            op = _op_q
                    qd_total = max(qd_total - 1, 0)
                    if op == "R": qd_read = max(qd_read - 1, 0)
                    elif op == "W": qd_write = max(qd_write - 1, 0)

                if qd_samples and (t_rel - qd_samples[-1][0]) < bucket_s:
                    last = qd_samples[-1]
                    qd_samples[-1] = (last[0], max(last[1], qd_total),
                                       max(last[2], qd_read), max(last[3], qd_write))
                else:
                    qd_samples.append((t_rel, qd_total, qd_read, qd_write))
            try:
                proc.wait(timeout=max(60, min(sum(p.stat().st_size for p in bins) // (1024 * 1024), 600)))
            except _sp.TimeoutExpired:
                proc.kill(); proc.wait(timeout=5)
    except FileNotFoundError:
        log.warning("queue depth: %s not found", blkparse_bin)
        return {}
    except Exception as e:
        log.warning("queue depth pass failed: %s", e)
        return {}

    if q_events <= 0:
        log.warning("queue depth pass found %d C events but no Q events; sample unmatched=%s", c_events, unmatched_sample)
        return {}
    try:
        _write_latency_outputs(output_dir, read_lat_buckets, write_lat_buckets,
                               source="blktrace_q_to_c")
    except Exception as _e:
        log.warning("latency emission failed (QD outputs still written): %s", _e)
    return _write_queue_depth_outputs(output_dir, qd_samples, time_at_qd, qd_max,
                                      bucket_s, "blktrace_q_to_c", q_events, c_events)


def _scale_sampled_analysis_outputs(output_dir: Path, ratio: int) -> None:
    """Scale aggregate CSVs produced from a 1-in-N completion sample.

    The sampled binary path is used only when raw blkparse CSVs are too large
    or absent.  Summary totals were already scaled in older builds, but the
    LBA/hot-region/temporal visual CSVs remained sampled, which made reports
    internally inconsistent.  This keeps every aggregate visualization on the
    same estimated full-population basis while leaving per-event sample files
    (request_size_distribution.csv) untouched.
    """
    if ratio <= 1:
        return
    import csv as _csv

    def _scale_csv(name: str, numeric_cols: set[str]) -> None:
        path = output_dir / name
        if not path.exists():
            return
        try:
            with path.open(newline="", encoding="utf-8") as f:
                rows = list(_csv.DictReader(f))
                fields = rows[0].keys() if rows else []
            if not rows:
                return
            for row in rows:
                for col in numeric_cols:
                    if col in row and str(row[col]).strip() not in ("", "nan", "None"):
                        try:
                            val = float(row[col]) * ratio
                            row[col] = str(int(round(val))) if abs(val - round(val)) < 1e-9 else f"{val:.6g}"
                        except Exception:
                            pass
            with path.open("w", newline="", encoding="utf-8") as f:
                w = _csv.DictWriter(f, fieldnames=list(fields))
                w.writeheader(); w.writerows(rows)
        except Exception as e:
            log.warning("could not scale sampled blktrace aggregate %s by %s: %s", name, ratio, e)

    _scale_csv("hot_regions_overall.csv", {"bytes", "count"})
    _scale_csv("lba_distribution_full.csv", {"bytes", "count"})
    _scale_csv("hot_regions_by_time_window.csv", {"bytes"})
    _scale_csv("temporal_read_write_trim_pattern.csv", {"read", "write", "trim", "read_count", "write_count", "trim_count"})
    _scale_csv("bandwidth_per_stream.csv", {"count", "bytes", "bandwidth_mib_s"})
    _scale_csv("bandwidth_per_stream_summary.csv", {"bandwidth_mib_s_mean", "bandwidth_mib_s_max"})
    _scale_csv("interarrival_distribution.csv", {"count"})
    _scale_csv("burst_temporal_windows.csv", {"events", "threshold"})

def _streaming_lba_keys(lo: dict, hi: dict, hist: dict) -> dict:
    """Decile histogram of bytes across the observed LBA span, per op.

    The streaming analyzer has its own summary dict, separate from the
    in-memory one, so a decile export added only to the latter never reached a
    deployed service.  Ten buckets keeps cardinality fixed while still
    answering "is access concentrated or spread", which is what drives garbage
    collection and therefore write amplification.
    """
    out: dict = {}
    try:
        for op, tag in (("R", "read"), ("W", "write")):
            if op not in lo or op not in hi:
                continue
            span = (hi[op] - lo[op]) or 1
            dec = [0] * 10
            for (o, bucket), nbytes in hist.items():
                if o != op:
                    continue
                sector = bucket * (LBA_BUCKET // 512)
                i = int((sector - lo[op]) * 10 // span)
                dec[min(9, max(0, i))] += nbytes
            tot = sum(dec)
            if tot <= 0:
                continue
            for i, b in enumerate(dec):
                out[f"lba_{tag}_decile{i}_pct"] = round(b / tot * 100.0, 3)
            out[f"lba_{tag}_deciles_touched"] = sum(1 for b in dec if b > 0)
            out[f"lba_{tag}_span_gb"] = round(span * 512 / 1e9, 3)
            out[f"lba_{tag}_start_gb"] = round(lo[op] * 512 / 1e9, 3)
    except Exception:
        return {}
    return out


def analyze_from_binaries(bin_dir: Path, output_dir: Path,
                           blkparse_bin: str = "blkparse",
                           max_events: int | None = None) -> dict:
    """Run blktrace analysis by streaming directly from binary trace files.

    This is the preferred path when blkparse_events.generated.csv is missing
    or was capped.  It spawns blkparse, pipes its output through the event
    parser, and feeds a temporary CSV to analyze().

    The temporary CSV contains only completion events (action='C'), which is
    the subset the analyzer actually uses.  This reduces the in-memory footprint
    by ~4× compared to keeping Q/M/G events.

    Args:
        bin_dir:      Directory containing trace.blktrace.* binary files.
        output_dir:   Where to write analysis CSVs (same as analyze()).
        blkparse_bin: Path to the blkparse binary.
        max_events:   Optional cap on completion events written to the temporary CSV.
                      When omitted/None, all completion events from the blktrace
                      binaries are used. When provided, the cap is applied
                      uniformly as 1-in-N sampling so the full time range is
                      represented.

    Returns the same dict as analyze().
    """
    import subprocess as _sp
    import tempfile
    import os as _os

    bins = sorted(bin_dir.glob("trace.blktrace.*"))
    if not bins:
        log.warning("analyze_from_binaries: no trace.blktrace.* files in %s", bin_dir)
        return {}

    log.info("analyze_from_binaries: streaming %d binaries (%d MB) from %s",
             len(bins),
             sum(p.stat().st_size for p in bins) // (1024 * 1024),
             bin_dir)

    # Line regex (same as BlktraceCollector)
    import re as _re
    _LINE_RE = _re.compile(
        r"^\s*(?P<major>\d+),(?P<minor>\d+)\s+(?P<cpu>\d+)\s+\d+\s+"
        r"(?P<ts>[\d.]+)\s+(?P<pid>\d+)\s+"
        r"(?P<action>[A-Z])\s+(?P<rwbs>[A-Z]*)\s*"
        r"(?P<sector>\d+)\s+\+\s+(?P<nsec>\d+)"
        r"(?:\s+\[(?P<comm>[^\]]+)])?"
    )

    prefix = bin_dir / "trace"
    cmd = [blkparse_bin, "-i", str(prefix)]

    # ── Optional first pass only when user requested an event cap ──────────
    # Default behavior is to use all available blktrace completion events.
    # If --blktrace-max-events is provided, count first so we can apply
    # uniform 1-in-N sampling across the full time range.
    total_c_events = 0
    keep_ratio = 1
    if max_events not in (None, "", 0, "0"):
        max_events = int(max_events)
        log.info("analyze_from_binaries: counting events for optional cap=%d (pass 1/2)...", max_events)
        try:
            with _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True) as proc:
                for raw in proc.stdout:
                    m = _LINE_RE.match(raw)
                    if m and m.group("action") == "C":
                        total_c_events += 1
                try:
                    proc.wait(timeout=max(60, len(bins) * 2))
                except _sp.TimeoutExpired:
                    proc.kill(); proc.wait(timeout=5)
        except Exception as e:
            log.warning("analyze_from_binaries: count pass failed: %s", e)
            total_c_events = 0
        if total_c_events > max_events:
            keep_ratio = (total_c_events + max_events - 1) // max_events
            log.info("analyze_from_binaries: %d completion events; optional cap keeps 1-in-%d (~%d events)",
                     total_c_events, keep_ratio, total_c_events // keep_ratio)
        else:
            log.info("analyze_from_binaries: %d completion events <= cap — keeping all", total_c_events)
    else:
        max_events = None
        log.info("analyze_from_binaries: no event cap set — using all available blktrace completion events")

    # ── Write full or optionally sampled CSV ──────────────────────────────
    log.info("analyze_from_binaries: writing %s CSV...",
             "sampled" if keep_ratio > 1 else "full")
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_csv = output_dir / "_blkparse_sampled.csv"
    written_events = 0
    seq = 0   # event counter for 1-in-N selection

    try:
        with _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True) as proc,              open(tmp_csv, "w", encoding="utf-8", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(["ts", "pid", "action", "rwbs", "op",
                         "sector", "nsectors", "size_bytes", "comm", "dev", "cpu"])
            pending_op: dict[tuple[str, str, str], str] = {}
            for raw in proc.stdout:
                m = _LINE_RE.match(raw)
                if not m:
                    continue
                d = m.groupdict()
                rwbs = d.get("rwbs") or ""
                nsec = int(d["nsec"])
                if "D" in rwbs:
                    op = "D"
                elif "W" in rwbs:
                    op = "W"
                elif "R" in rwbs:
                    op = "R"
                else:
                    op = "?"
                req_key = (d.get("pid") or "0", d.get("sector") or "0", str(nsec))
                action = d.get("action") or ""
                if action != "C":
                    if op in ("R", "W", "D"):
                        pending_op[req_key] = op
                    continue          # completions only
                if op not in ("R", "W", "D"):
                    op = pending_op.pop(req_key, "?")
                if op not in ("R", "W", "D"):
                    continue
                seq += 1
                if (seq % keep_ratio) != 0:
                    continue          # skip non-sampled events
                w.writerow([d["ts"], d["pid"], action, rwbs, op,
                             d["sector"], nsec, nsec * 512,
                             d.get("comm") or "",
                             f"{d['major']},{d['minor']}",
                             d.get("cpu") or "0"])
                written_events += 1
            # Drain any remaining output so blkparse can exit
            try:
                proc.stdout.read()
            except Exception:
                pass
            _wait_s = max(60, min(sum(p.stat().st_size for p in bins) // (1024 * 1024), 600))
            try:
                proc.wait(timeout=_wait_s)
            except _sp.TimeoutExpired:
                log.warning("analyze_from_binaries: blkparse still running after %ds — killing",
                            _wait_s)
                try:
                    proc.kill(); proc.wait(timeout=5)
                except Exception:
                    pass
    except Exception as e:
        log.error("analyze_from_binaries: write pass failed: %s", e)
        return {}

    log.info("analyze_from_binaries: wrote %d events to %s", written_events, tmp_csv)

    if written_events == 0:
        log.warning("analyze_from_binaries: no events written — check blkparse output")
        try:
            tmp_csv.unlink(missing_ok=True)
        except Exception:
            pass
        return {}

    # ── Run the standard analyzer on the sampled CSV ───────────────────────
    result = analyze(tmp_csv, output_dir)
    if keep_ratio > 1:
        _scale_sampled_analysis_outputs(output_dir, keep_ratio)

    # ── Run the queue-depth pass (separate from analyze() because it needs
    # both 'Q' and 'C' events, not just completions). Best-effort: if blkparse
    # fails or there's no useful QD data, just skip — main analysis is intact.
    try:
        qd_outputs = _compute_queue_depth_timeseries(bin_dir, output_dir,
                                                      blkparse_bin=blkparse_bin)
        if not qd_outputs:
            qd_outputs = _compute_queue_depth_from_csv(tmp_csv, output_dir,
                                                       source="sampled_csv_q_to_c")
        result.update(qd_outputs)
    except Exception as e:
        log.warning("queue depth analysis skipped: %s", e)

    # Store the sampling ratio in the summary so downstream consumers know
    if (output_dir / "summary.json").exists():
        try:
            import json as _json
            s = _json.loads((output_dir / "summary.json").read_text())
            s["sampling_ratio"]        = keep_ratio
            s["sampled_events"]        = written_events
            s["total_c_events_raw"]    = total_c_events if total_c_events else written_events
            s["source"]                = "blktrace_binaries"
            s["event_cap"]             = max_events
            s["event_cap_applied"]     = bool(keep_ratio > 1)
            # Scale totals back to full population when sampled
            if keep_ratio > 1:
                for key in ("read_events", "write_events", "trim_events", "total_events"):
                    if key in s:
                        s[key] = s[key] * keep_ratio
                for key in ("read_bytes_total", "write_bytes_total", "trim_bytes_total"):
                    if key in s:
                        s[key] = s[key] * keep_ratio
                # Rates are computed from duration, not event count — leave as-is
            (output_dir / "summary.json").write_text(
                _json.dumps(s, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("analyze_from_binaries: could not annotate summary.json: %s", e)

    # Clean up the temporary CSV (the compact analysis outputs remain)
    try:
        tmp_csv.unlink(missing_ok=True)
    except Exception:
        pass

    return result

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
    # LBA distribution as bounded gauges.  The full hot-region table goes to
    # hot_regions_overall.csv, which a Prometheus-fetched run never sees — so
    # a remote node had locality scalars and no distribution at all.  Ten
    # deciles across the observed LBA span answer "is access concentrated or
    # spread" with fixed cardinality, which the top-50 table could not.
    _lba_keys = {}
    try:
        for _op, _tag in (("R", "read"), ("W", "write")):
            _ev = [e for e in events if e.get("op") == _op]
            if not _ev:
                continue
            _sect = [e["sector"] for e in _ev]
            _lo, _hi = min(_sect), max(_sect)
            _span = (_hi - _lo) or 1
            _dec = [0] * 10
            for _e in _ev:
                _i = int((_e["sector"] - _lo) * 10 // _span)
                _dec[min(9, max(0, _i))] += _e["size"]
            _tot = sum(_dec) or 1
            for _i, _b in enumerate(_dec):
                _lba_keys[f"lba_{_tag}_decile{_i}_pct"] = round(_b / _tot * 100.0, 3)
            _lba_keys[f"lba_{_tag}_span_gb"] = round(_span * 512 / 1e9, 3)
            _lba_keys[f"lba_{_tag}_start_gb"] = round(_lo * 512 / 1e9, 3)
            # Deciles carrying any traffic: 1 means every write hit one tenth
            # of the span, 10 means it was spread evenly.
            _lba_keys[f"lba_{_tag}_deciles_touched"] = sum(1 for _b in _dec if _b > 0)
    except Exception:
        _lba_keys = {}

    summary = {
        **_lba_keys,
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
    # ── Cross-check captured bytes against kernel-side ground truth ─────────
    # Read /sys/block/<dev>/stat delta that the collector recorded in
    # blktrace_summary.json (BlktraceCollector.stop). If blktrace bytes are
    # significantly less than the kernel's write counter, events were dropped
    # or the trace ran on the wrong device. Surfaces the discrepancy directly
    # in the summary so the reader doesn't have to dig.
    # Cross-check captured bytes vs kernel /sys/block delta + merge stats.
    # See _merge_collector_diagnostics_into_summary for what gets propagated
    # and why it matters when explaining FS-driven op-count changes.
    _merge_collector_diagnostics_into_summary(
        summary, output_dir.parent / "blktrace_summary.json")
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
    # The LBA distribution is written to CSV for the local reports, but a run
    # analysed over Prometheus never sees that file — which is why the L3.5
    # node has locality SCALARS (gini, topNpct) and no distribution.  Export
    # the shape as gauges too: a coarse decile histogram is enough to answer
    # "is access concentrated or spread", and unlike the top-50 CSV it has
    # bounded cardinality, so it is safe to publish every cycle.
    region_bytes: dict[tuple, int] = defaultdict(int)
    region_count: dict[tuple, int] = defaultdict(int)
    _lba_lo: dict = {}
    _lba_hi: dict = {}
    _lba_hist: dict = defaultdict(int)
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

    # ─── 3b. lba_distribution_full.csv ────────────────────────────────────────
    # Complete per-bucket I/O distribution across the device — required to
    # understand SSD usage (the hot regions CSV only keeps the top 50 buckets,
    # which on this workload represents ~15% of total bytes). Each row is one
    # 16 MB LBA bucket; columns: op, lba_bucket_start, bytes, count. Buckets
    # with zero traffic are omitted to keep file size sane (5,000-50,000 rows
    # typical vs ~250,000 for a 4 TB device with all buckets emitted).
    with open(output_dir / "lba_distribution_full.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "lba_bucket_start", "lba_bucket_end", "bytes", "count"])
        # Group by op for predictable file ordering, sort by LBA within each op.
        for op in ("R", "W", "D"):
            buckets = sorted(b for (eo, b) in region_bytes if eo == op)
            for bucket in buckets:
                w.writerow([
                    OP_NAME.get(op, op),
                    bucket * LBA_BUCKET,
                    (bucket + 1) * LBA_BUCKET,
                    region_bytes[(op, bucket)],
                    region_count[(op, bucket)],
                ])
    written["lba_distribution_full.csv"] = output_dir / "lba_distribution_full.csv"

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
    _lba_lo: dict = {}
    _lba_hi: dict = {}
    _lba_hist: dict = defaultdict(int)
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
                    # Count only completed I/O.  blkparse emits Q/G/I/D/C
                    # lifecycle events for the same request; only C contributes
                    # one physical device I/O.  This keeps the interactive SSD
                    # I/O distribution aligned with the blktrace summary and
                    # with SGLang logical L3 read/write direction.
                    if not _is_completion_row(row):
                        continue
                    ts_abs = float(row.get("ts") or row.get("time_sec") or row.get("timestamp") or 0)
                    size = int(row.get("size_bytes") or (int(row.get("nsectors", 0) or 0) * 512))
                    if size <= 0:
                        continue
                    op = _normalise_block_op(row)
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
                # LBA span and per-bucket bytes, for the decile export below.
                # This is the STREAMING path — the deployed one — and it has
                # its own summary dict, so the decile code added to the
                # non-streaming analyzer never ran here.
                _lba_lo[op] = sector if op not in _lba_lo else min(_lba_lo[op], sector)
                _lba_hi[op] = sector if op not in _lba_hi else max(_lba_hi[op], sector)
                _lba_hist[(op, bucket)] += size

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
                if not _is_completion_row(row):
                    continue
                ts = float(row.get("ts") or row.get("time_sec") or row.get("timestamp") or 0) - t0
                size = int(row.get("size_bytes") or (int(row.get("nsectors", 0) or 0) * 512))
                op = _normalise_block_op(row)
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
        **{_k: _v for _k, _v in _streaming_lba_keys(
            _lba_lo, _lba_hi, _lba_hist).items()},
        "completion_events_only": True,
        "request_size_sampled_events": sample_written,
    }
    # Cross-check captured bytes vs kernel /sys/block delta + merge stats.
    # See _merge_collector_diagnostics_into_summary for what gets propagated.
    _merge_collector_diagnostics_into_summary(
        summary, output_dir.parent / "blktrace_summary.json")
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

    # Complete per-bucket distribution for the SSD-usage chart. The hot
    # regions CSV only keeps the top 50 per op (~15% of bytes on this
    # workload); the chart needs the full distribution to show how I/O
    # really spreads across the device's LBA range.
    with open(output_dir / "lba_distribution_full.csv", "w", newline="") as f:
        w=csv.writer(f); w.writerow(["op","lba_bucket_start","lba_bucket_end","bytes","count"])
        for op in ("R","W","D"):
            buckets = sorted(b for (eo, b) in region_bytes if eo == op)
            for bucket in buckets:
                w.writerow([OP_NAME.get(op, op),
                            bucket * LBA_BUCKET, (bucket+1) * LBA_BUCKET,
                            region_bytes[(op, bucket)],
                            region_count[(op, bucket)]])
    written["lba_distribution_full.csv"] = output_dir / "lba_distribution_full.csv"

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

    # Queue-depth fallback for CSVs that contain Q and C events. If this CSV is
    # completion-only, the helper returns {} and the report falls back to
    # iostat/sysfs inflight instead of rendering an empty section.
    try:
        qd_outputs = _compute_queue_depth_from_csv(events_csv, output_dir)
        written.update({k: Path(v) for k, v in qd_outputs.items()})
    except Exception as e:
        log.warning("queue depth CSV fallback skipped: %s", e)

    log.info("blktrace_analyzer(streaming): wrote %d files to %s; events=%d sample=%d", len(written), output_dir, total_events, sample_written)
    return {name: str(path) for name, path in written.items()}
