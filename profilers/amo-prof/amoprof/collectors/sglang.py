"""SGLangMetricsSampler — extracted from sglang_collector.py into its own module.

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

log = logging.getLogger("amoprof.collectors.sglang")

# Fallback only, for code that constructs the sampler directly rather than
# through for_host().  The metrics path no longer touches /get_server_info at
# all: it has its own fetcher and its own thread, so the two intervals cannot
# interfere.
_SERVER_INFO_MIN_S = float(os.environ.get("AMOPROF_SGLANG_SERVER_INFO_MIN_S", "300"))


def _fetch_metrics_once(port: int, debug: bool = False,
                        debug_path: str | None = None,
                        host: str = "127.0.0.1") -> dict:
    """
    Fetch one Prometheus snapshot from SGLang /metrics.

    Correctly parses:
      - Plain gauges:      sglang:gen_throughput 3.05
      - Labeled metrics:   sglang:cached_tokens_total{source="device"} 12345
      - Histogram sums:    sglang:eviction_duration_seconds_sum 0.042
      - Histogram counts:  sglang:eviction_duration_seconds_count 7

    Returns a flat dict where labeled metrics get key metric_name[label=value].
    Counter/histogram pairs are preserved for delta computation in the sampler.
    When debug is enabled, scrape diagnostics are added to the result and also
    appended to debug_path when provided.
    """
    result = {}
    url = f"http://{host}:{port}/metrics"
    scrape_bytes = 0
    metric_lines = 0
    matched_lines = 0
    ttft_lines = 0
    debug_lines: list[str] = []

    def _dbg(msg: str) -> None:
        if debug:
            debug_lines.append(msg)

    _dbg(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] fetch url={url}")
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            raw = r.read().decode("utf-8", errors="replace")
            scrape_bytes = len(raw.encode("utf-8", errors="replace"))
            lines = raw.splitlines()
            _dbg(f"scrape_success=1 scrape_bytes={scrape_bytes} total_lines={len(lines)}")
            for line in lines:
                if line.startswith("#") or not line.strip():
                    continue
                metric_lines += 1
                if "time_to_first_token" in line:
                    ttft_lines += 1
                    if ttft_lines <= 5:
                        _dbg(f"ttft_line={line}")
                # Parse: metric_name{k="v",...} value OR metric_name value.
                # Accept both SGLang styles: sglang:foo and sglang_foo.
                m = re.match(
                    r'^\s*((?:sglang[:_])\w+)(?:\{([^}]*)\})?\s+([\d.eE+\-]+)', line)
                if not m:
                    continue
                matched_lines += 1
                try:
                    name = m.group(1)
                    # Normalize to the colon style used by the rest of this module.
                    if name.startswith("sglang_"):
                        name = "sglang:" + name[len("sglang_"):]
                    labels = m.group(2) or ""
                    value = float(m.group(3))
                except ValueError:
                    continue

                _PRIORITY_LABELS = {"mode", "source", "type", "status",
                                    "backend", "direction", "phase"}
                if labels:
                    label_pairs = re.findall(r'(\w+)="([^"]+)"', labels)
                    label_dict = dict(label_pairs)
                    keyed = False
                    for _pl in _PRIORITY_LABELS:
                        if _pl in label_dict:
                            result[f'{name}[{_pl}={label_dict[_pl]}]'] = value
                            keyed = True
                            break
                    if not keyed and label_pairs:
                        result[f'{name}[{label_pairs[0][0]}={label_pairs[0][1]}]'] = value
                    result.setdefault(name, value)
                else:
                    result[name] = value

    except Exception as e:
        result["sglang:scrape_success"] = 0.0
        result["sglang:scrape_error"] = str(e)
        _dbg(f"scrape_success=0 error={e!r}")
    else:
        result["sglang:scrape_success"] = 1.0

    result["sglang:scrape_bytes"] = float(scrape_bytes)
    result["sglang:scrape_metric_lines"] = float(metric_lines)
    result["sglang:scrape_matched_lines"] = float(matched_lines)
    result["sglang:scrape_ttft_lines"] = float(ttft_lines)
    if debug:
        _dbg(f"parsed metric_lines={metric_lines} matched_lines={matched_lines} ttft_lines={ttft_lines}")
        for key in [
            "sglang:time_to_first_token_seconds_sum",
            "sglang:time_to_first_token_seconds_count",
            "sglang:e2e_request_latency_seconds_sum",
            "sglang:e2e_request_latency_seconds_count",
            "sglang:realtime_tokens_total[mode=decode]",
            "sglang:realtime_tokens_total[mode=prefill_compute]",
            "sglang:num_running_reqs",
            "sglang:num_queue_reqs",
        ]:
            if key in result:
                _dbg(f"parsed {key}={result[key]}")


    if debug and debug_path:
        try:
            with open(debug_path, "a", encoding="utf-8") as f:
                for msg in debug_lines:
                    f.write(msg + "\n")
                f.write("---\n")
        except Exception:
            pass

    return result


def _histogram_mean(samples: list[dict], prefix: str) -> float:
    """
    Compute mean from a Prometheus histogram _sum / _count pair.
    Returns 0.0 if data unavailable.
    """
    sum_key   = f"{prefix}_sum"
    count_key = f"{prefix}_count"
    first = samples[0]  if samples else {}
    last  = samples[-1] if samples else {}
    d_sum   = max(last.get(sum_key,   0.0) - first.get(sum_key,   0.0), 0.0)
    d_count = max(last.get(count_key, 0.0) - first.get(count_key, 0.0), 0.0)
    return round(d_sum / d_count, 6) if d_count > 0 else 0.0


@register_collector
class SGLangMetricsSampler(BaseCollector):
    """
    Polls SGLang /metrics every `interval_s` while a request is in flight.

    Collects ALL meaningful metrics from the /metrics endpoint as seen in
    a real SGLang 0.5.9 deployment, including:

    KV$ tier metrics (direct from SGLang):
      evicted_tokens_total    — tokens evicted GPU→CPU (L1→L2, cumulative counter)
      load_back_tokens_total  — tokens restored CPU→GPU (L2→L1, cumulative counter)
      cached_tokens[source=device]  — tokens in GPU KV cache (L1 occupancy)
      cached_tokens[source=host]    — tokens in CPU staging (L2 occupancy)
      cached_tokens[source=storage] — tokens on SSD (L3 occupancy)
      hicache_host_used_tokens      — host KV cache used tokens
      hicache_host_total_tokens     — host KV cache capacity

    HiCache latency:
      eviction_duration_seconds — mean time per HBM→CPU eviction event
      load_back_duration_seconds— mean time per CPU→HBM restore event

    AI op classification (using realtime_tokens_total{mode=...}):
      prefill_compute tokens  — tokens that needed actual prefill (new KV$ write)
      prefill_cache tokens    — tokens served from RadixAttention cache (KV$ hit)
      decode tokens           — decode phase tokens (KV$ read-all per step)

    Server-side latency histograms (ground truth, vs our stream measurements):
      time_to_first_token_seconds  — server-measured TTFT
      inter_token_latency_seconds  — server-measured ITL/TPOT
      e2e_request_latency_seconds  — server-measured E2E
      queue_time_seconds           — time spent queued before prefill

    Queue and throughput:
      num_running_reqs     — active requests (gauge)
      num_queue_reqs       — queued requests (gauge)
      decode_sum_seq_lens  — total decode context length (KV$ demand proxy)
      gen_throughput       — decode tokens/s (gauge)
      new_token_ratio      — fraction of tokens not served from cache
      utilization          — overall server utilisation

    Pool capacity:
      max_total_num_tokens — KV pool capacity in tokens
      num_used_tokens      — tokens currently in KV pool
      token_usage          — pool fill ratio (0..1)
    """

    SPEC = CollectorSpec(
        name="sglang",
        layer=AIStackLayer.A4_GPU_HBM,
        is_ssd_scoped=False,
        optional=True,
        enable_flag="sglang_port",
        description="SGLang Prometheus /metrics scrape (KV$ tiers, TTFT, throughput, latency)",
    )

    @classmethod
    def for_host(cls, args, ctx: dict):
        """Factory: build from argparse Namespace + ctx.

        cli/service call this when `args.sglang_port is not None`.
        """
        # --server-info-interval-s governs EVERY call to /get_server_info,
        # not just the config capture.  Two independent throttles on one
        # endpoint meant setting the flag to 600s still left this collector
        # polling it on its own schedule, which is exactly the confusion the
        # flag exists to remove.  --server-info-once means "fetch once", so
        # here it is an interval no run will reach.
        _si_iv = float(getattr(args, "server_info_interval_s", 300.0) or 0.0)
        if bool(getattr(args, "server_info_once", False)):
            _si_iv = float("inf")
        globals()["_SERVER_INFO_MIN_S"] = _si_iv

        return cls(
            port=int(getattr(args, "sglang_port", 0) or 0),
            interval_s=(float(getattr(args, "sglang_metrics_interval_s", 0) or 0)
                        or float(ctx.get("interval_s", 1.0))),
            server_info_interval_s=_si_iv,
            host=str(getattr(args, "sglang_host", "127.0.0.1") or "127.0.0.1"),
            debug=bool(getattr(args, "debug_sglang", False)),
            debug_path=str(ctx.get("raw_dir", ".")) + "/sglang_debug.log",
        )

    def __init__(self, port: int, interval_s: float = 1.0,
                 host: str = "127.0.0.1",
                 debug: bool = False, debug_path: str | None = None,
                 server_info_interval_s: float = 300.0):
        self.port     = port
        self.host     = host
        self.interval = interval_s
        # /get_server_info is NOT polled here.  SGLang exports both gauges we
        # wanted from it — sglang:cache_hit_rate and sglang:token_usage — on
        # /metrics, which this collector already scrapes and parses
        # generically.  Calling a heavy JSON endpoint that serialises the whole
        # server configuration to extract two floats we were fetching anyway
        # was pure overhead.  Retained only so the constructor signature stays
        # compatible with callers that pass it.
        self.si_interval = float(server_info_interval_s)
        self.debug    = bool(debug)
        self.debug_path = debug_path
        self._samples: list[dict] = []
        self._stop    = threading.Event()
        self._thread  = None
        self._t_start = 0.0
        self._t_end   = 0.0

    @property
    def prometheus_url(self) -> str:
        return f"http://{self.host}:{self.port}/metrics"

    @property
    def raw_samples(self) -> list[dict]:
        """All collected Prometheus scrape snapshots, in chronological order.
        Each snapshot is {metric_key: float, 'ts': epoch_seconds}.
        Used by amoprof.writer to emit sglang_timeseries.csv."""
        return list(self._samples)

    @property
    def elapsed_s(self) -> float:
        if self._t_end > 0 and self._t_start > 0:
            return self._t_end - self._t_start
        return 0.0

    def start(self):
        self._stop.clear()
        self._samples.clear()
        self._t_start = time.time()
        s = _fetch_metrics_once(self.port, self.debug, self.debug_path, host=self.host)
        if s:
            s = dict(s)
            s["ts"] = time.time()
            self._samples.append(s)
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self):
        while not self._stop.wait(self.interval):
            s = _fetch_metrics_once(self.port, self.debug, self.debug_path, host=self.host)
            if s:
                s = dict(s)
                s["ts"] = time.time()
                self._samples.append(s)

    def stop(self) -> dict:
        self._stop.set()
        s = _fetch_metrics_once(self.port, self.debug, self.debug_path, host=self.host)
        if s:
            s = dict(s)
            s["ts"] = time.time()
            self._samples.append(s)
        self._t_end = time.time()
        if self._thread:
            self._thread.join(timeout=3)

        if not self._samples:
            return self._empty()

        first  = self._samples[0]
        last   = self._samples[-1]
        n      = len(self._samples)

        def peak(k):
            return max((s.get(k, 0.0) for s in self._samples), default=0.0)
        def mn(k):
            vs = [s.get(k, 0.0) for s in self._samples]
            return round(sum(vs) / max(len(vs), 1), 4)
        def delta(k):
            return max(last.get(k, 0.0) - first.get(k, 0.0), 0.0)

        # ── KV$ tier occupancy ────────────────────────────────────────────────
        # Gauges — current state
        kv_pool_capacity_tokens  = peak("sglang:max_total_num_tokens")
        kv_used_tokens_peak      = peak("sglang:num_used_tokens")
        kv_token_usage_peak      = peak("sglang:token_usage")
        hicache_host_used        = peak("sglang:hicache_host_used_tokens")
        hicache_host_total       = peak("sglang:hicache_host_total_tokens")

        # Labeled cache tier occupancy (tokens per tier)
        kv_l1_device_tokens = peak("sglang:cached_tokens_total[source=device]")
        kv_l2_host_tokens   = peak("sglang:cached_tokens_total[source=host]")
        kv_l3_storage_tokens= peak("sglang:cached_tokens_total[source=storage]")

        # ── KV$ eviction / restore (counters — use deltas) ───────────────────
        evicted_delta   = delta("sglang:evicted_tokens_total")
        load_back_delta = delta("sglang:load_back_tokens_total")
        prefetched_delta= delta("sglang:prefetched_tokens_total")

        # ── HiCache latency histograms ────────────────────────────────────────
        eviction_mean_s  = _histogram_mean(self._samples,
                                           "sglang:eviction_duration_seconds")
        load_back_mean_s = _histogram_mean(self._samples,
                                           "sglang:load_back_duration_seconds")
        queue_time_mean_s= _histogram_mean(self._samples,
                                           "sglang:queue_time_seconds")

        # ── Server-side latency histograms ────────────────────────────────────
        ttft_mean_s   = _histogram_mean(self._samples,
                                        "sglang:time_to_first_token_seconds")
        itl_mean_s    = _histogram_mean(self._samples,
                                        "sglang:inter_token_latency_seconds")
        e2e_mean_s    = _histogram_mean(self._samples,
                                        "sglang:e2e_request_latency_seconds")

        # ── Realtime tokens by mode (counters) ───────────────────────────────
        # These are the ground-truth AI operation breakdown
        rt_prefill_compute = delta("sglang:realtime_tokens_total[mode=prefill_compute]")
        rt_prefill_cache   = delta("sglang:realtime_tokens_total[mode=prefill_cache]")
        rt_decode          = delta("sglang:realtime_tokens_total[mode=decode]")
        rt_total = rt_prefill_compute + rt_prefill_cache + rt_decode

        # Cache hit rate from realtime_tokens: cache_hit / (compute + cache)
        prefill_total = rt_prefill_compute + rt_prefill_cache
        cache_hit_rate_realtime = (
            round(rt_prefill_cache / prefill_total * 100, 1)
            if prefill_total > 0 else 0.0)

        # ── AI op classification (improved) ──────────────────────────────────
        # Use realtime_tokens_total as ground truth when available;
        # fall back to gen_throughput gauge for live classification.
        dc_peak  = peak("sglang:gen_throughput")
        n_run_pk = peak("sglang:num_running_reqs")
        n_run_mn = mn("sglang:num_running_reqs")
        new_tok_ratio = mn("sglang:new_token_ratio")   # 1.0 = no cache, 0.0 = all cached

        if rt_total > 0:
            # Ground-truth classification from token counters
            if rt_prefill_compute > rt_decode * 2:
                op = "prefill"
            elif rt_decode > 0 and dc_peak < 15:
                op = "reasoning"       # R1/QwQ: long decode at low tok/s
            elif rt_decode > rt_prefill_compute:
                op = "decode"
            else:
                op = "mixed"
        elif n_run_pk == 0:
            op = "idle"
        elif dc_peak > 0:
            op = "reasoning" if dc_peak < 15 else "decode"
        else:
            op = "prefill" if n_run_pk > 0 else "idle"

        # ── Throughput and queue ──────────────────────────────────────────────
        decode_sum_seq_lens = peak("sglang:decode_sum_seq_lens")
        n_queue_peak        = peak("sglang:num_queue_reqs")
        utilization         = mn("sglang:utilization")
        kv_cache_hit_rate   = last.get("sglang:cache_hit_rate",
                              last.get("sglang:cache_hit_rate[cache=0]", 0.0))

        return {
            # ── Current 5 fields (unchanged interface) ────────────────────────
            "ai_op_type":              op,
            "ai_op_prefill_tok_s":     round(rt_prefill_compute / max(n, 1), 2),
            "ai_op_decode_tok_s":      round(dc_peak, 2),
            "kv_cache_hit_rate_pct":   round(kv_cache_hit_rate * 100, 1),
            "num_running_req_mean":    round(n_run_mn, 2),

            # ── NEW: KV$ pool state ───────────────────────────────────────────
            "token_usage_peak":        round(kv_token_usage_peak * 100, 1),
            "kv_pool_capacity_tokens": int(kv_pool_capacity_tokens),
            "kv_used_tokens_peak":     int(kv_used_tokens_peak),

            # ── NEW: KV$ tier breakdown (L1/L2/L3 occupancy) ─────────────────
            "kv_l1_device_tokens":     int(kv_l1_device_tokens),
            "kv_l2_host_tokens":       int(kv_l2_host_tokens),
            "kv_l3_storage_tokens":    int(kv_l3_storage_tokens),
            "hicache_host_used_tokens":int(hicache_host_used),
            "hicache_host_total_tokens":int(hicache_host_total),
            "hicache_host_fill_pct":   round(hicache_host_used / max(hicache_host_total, 1) * 100, 1),

            # ── NEW: KV$ eviction / restore (token counts this instance) ─────
            "kv_evicted_tokens":       int(evicted_delta),
            "kv_restored_tokens":      int(load_back_delta),
            "kv_prefetched_tokens":    int(prefetched_delta),

            # ── NEW: HiCache operation latency ────────────────────────────────
            "hicache_eviction_ms":     round(eviction_mean_s  * 1000, 2),
            "hicache_load_back_ms":    round(load_back_mean_s * 1000, 2),
            "hicache_queue_time_ms":   round(queue_time_mean_s * 1000, 2),

            # ── NEW: AI op breakdown (token-level ground truth) ───────────────
            "rt_prefill_compute_tokens": int(rt_prefill_compute),  # new KV$ writes
            "rt_prefill_cache_tokens":   int(rt_prefill_cache),    # KV$ cache hits
            "rt_decode_tokens":          int(rt_decode),           # KV$ read-all ops
            "cache_hit_rate_realtime_pct": cache_hit_rate_realtime,
            "new_token_ratio_mean":      round(new_tok_ratio, 3),

            # ── NEW: Server-side latency histograms (ground truth) ────────────
            "server_ttft_ms":          round(ttft_mean_s  * 1000, 2),
            "server_itl_ms":           round(itl_mean_s   * 1000, 2),
            "server_e2e_ms":           round(e2e_mean_s   * 1000, 2),

            # ── NEW: Queue and throughput ──────────────────────────────────────
            "num_queue_reqs_peak":     int(n_queue_peak),
            "decode_sum_seq_lens":     int(decode_sum_seq_lens),
            "utilization_mean":        round(utilization * 100, 1),

            "num_samples":             n,
        }

    def _empty(self) -> dict:
        return {k: v for k, v in {
            "ai_op_type": "unknown", "ai_op_prefill_tok_s": 0.0,
            "ai_op_decode_tok_s": 0.0, "kv_cache_hit_rate_pct": 0.0,
            "num_running_req_mean": 0.0, "token_usage_peak": 0.0,
            "kv_pool_capacity_tokens": 0, "kv_used_tokens_peak": 0,
            "kv_l1_device_tokens": 0, "kv_l2_host_tokens": 0,
            "kv_l3_storage_tokens": 0, "hicache_host_used_tokens": 0,
            "hicache_host_total_tokens": 0, "hicache_host_fill_pct": 0.0,
            "kv_evicted_tokens": 0, "kv_restored_tokens": 0, "kv_prefetched_tokens": 0,
            "hicache_eviction_ms": 0.0, "hicache_load_back_ms": 0.0, "hicache_queue_time_ms": 0.0,
            "rt_prefill_compute_tokens": 0, "rt_prefill_cache_tokens": 0, "rt_decode_tokens": 0,
            "cache_hit_rate_realtime_pct": 0.0, "new_token_ratio_mean": 0.0,
            "server_ttft_ms": 0.0, "server_itl_ms": 0.0, "server_e2e_ms": 0.0,
            "num_queue_reqs_peak": 0, "decode_sum_seq_lens": 0, "utilization_mean": 0.0,
            "num_samples": 0,
        }.items()}
