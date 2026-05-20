"""
amoprof/report/enhancer.py — Post-process the bundled amoprof HTML report to:

  1. Apply a darker reading theme (slate-900 background, light text)
  2. Add hover tooltips with summary stats to each chart image
  3. Inject per-chart explanations describing the chart, what it measures,
     and its significance to KV cache and the overall AI inference stack

Designed to run AFTER amoprof.py has emitted its standard HTML report.
We do NOT modify the bundled amoprof.py — instead we read the produced
file and rewrite specific elements via parsing.

Public API:
    enhance_report(html_path: Path,
                   raw_dir: Path | None = None,
                   theme: str = "dark") -> Path

Theme options:
    "dark"   — slate-900 background, slate-50 text, kept color accents on charts
    "light"  — original amoprof palette (no-op)

The matplotlib chart palette is set inside amoprof.py at import time, so we
cannot retro-recolor the PNG plots. Instead we wrap each chart image in a
dark gradient frame that integrates the existing charts cleanly with the
darker page chrome — the matplotlib charts themselves remain readable on
their light-blue plot backgrounds.
"""
from __future__ import annotations

import csv
import json
import re
import logging
from pathlib import Path

log = logging.getLogger("amoprof.enhancer")


# ─── Chart explanations ──────────────────────────────────────────────────────
# Keyed by the H2 heading text (case-insensitive substring match).
# Each entry: (one-line summary, multi-paragraph significance).
CHART_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "ai operation phase": (
        "Decomposes time spent in prefill (TTFT) vs decode (TPOT) phases of inference.",
        "Why this matters for the AI stack: Prefill is compute-bound and dominated by "
        "matmul throughput on HBM; decode is memory-bandwidth bound and dominated by "
        "KV-cache reads. The relative durations tell you whether your bottleneck is "
        "HBM bandwidth (decode-heavy) or compute / KV-cache-load (prefill-heavy). "
        "For long contexts, prefill grows quadratically with sequence length; for long "
        "generations, decode dominates."
        "\n\nFor KV$: prefill writes new KV entries into the L1 (HBM) cache; decode "
        "reads them on every token. A high TTFT with low TPOT means the KV-cache load "
        "path is slow (likely L2/L3 misses); a high TPOT means the decode path is "
        "constrained by HBM bandwidth or KV eviction."
    ),
    "gpu utilisation": (
        "Per-GPU utilization, HBM occupancy, power draw, and temperature over time.",
        "Why this matters: For inference, sustained GPU util &lt; 60% indicates the "
        "model is starved — usually waiting for KV cache loads from L2/L3 (host DRAM "
        "or SSD). Sustained util &gt; 90% with stable HBM usage means HBM is the "
        "bottleneck; util &gt; 90% with rising HBM means you're approaching OOM and "
        "the runtime will start evicting KV entries.\n\nFor KV$: HBM occupancy is the "
        "L1 tier capacity. If it stays pinned near 100%, every new request triggers "
        "evictions to L2 (host DRAM), which surface as `load_back_tokens_total` "
        "increments in the SGLang metrics below."
    ),
    "sglang inference": (
        "Real-time inference throughput, latencies, and request queue depth.",
        "Why this matters: SGLang's Prometheus endpoint exposes the runtime view of "
        "your inference engine — TTFT, ITL (inter-token latency, ≈ TPOT), e2e request "
        "latency, generation throughput, queue depth, and per-mode token counters "
        "(decode / prefill_compute / prefill_cache).\n\nFor KV$: the most important "
        "metric here is `cache_hit_rate` — the fraction of prefill tokens served from "
        "the radix tree cache rather than recomputed. A drop in hit rate during a "
        "long run usually signals KV$ pressure: the cache is being evicted faster "
        "than it's being reused."
    ),
    "memory profile": (
        "Combined HBM (GPU), DRAM (host), and KV cache occupancy over time.",
        "Why this matters: The three memory tiers compete for the same data. HBM holds "
        "model weights + active KV; DRAM holds spilled KV (L2); SSD holds cold KV (L3). "
        "Tracking all three together shows whether the runtime is using its tiers "
        "efficiently or leaving capacity stranded.\n\nFor KV$: when HBM nears full, "
        "spillover to DRAM should be visible as rising `hicache_host_used_tokens`. "
        "If DRAM also fills, you'll see writes to NVMe (the §C/§D/§E charts)."
    ),
    "kv cache footprint": (
        "How KV cache consumes HBM capacity over the course of the run.",
        "Why this matters: KV cache grows linearly with the number of active requests "
        "× context length. For a 70B model with fp16 KV at 8192 context, each request "
        "needs ~5 GB of KV. On 40 GB A100s with the model itself taking ~140 GB across "
        "8 GPUs, only ~180 GB total is left for KV — that limits concurrent active "
        "requests.\n\nFor KV$: when this chart shows HBM saturating, the runtime "
        "starts trading: evicting older sessions' KV to DRAM to admit new requests, "
        "then loading them back when those sessions resume."
    ),
    "per cache tier": (
        "Cost per cache hit/miss broken down by tier (L1 HBM / L2 DRAM / L3 SSD).",
        "Why this matters: Each cache tier has wildly different access cost — HBM "
        "reads complete in ~1µs, DRAM in ~10µs, SSD in ~100µs. A KV cache that "
        "spills to L3 (SSD) adds 100× latency vs. an L1 hit. Knowing the access "
        "ratio per tier tells you whether your tier sizing matches your working set."
        "\n\nFor KV$: an L3 hit (SSD load-back) is much cheaper than a full prefill "
        "recompute, but only if the SSD can sustain enough bandwidth. The §C/§D "
        "charts later show whether your SSD is keeping up."
    ),
    "latency breakdown": (
        "How total request latency decomposes across queue / prefill / decode phases.",
        "Why this matters: A request's e2e latency = queue_time + TTFT + N*ITL. "
        "If queue_time dominates, you need more concurrent capacity or smaller "
        "models. If TTFT dominates, you need faster KV-cache loads (or prefill "
        "compute). If ITL dominates, you need more HBM bandwidth or smaller batches."
        "\n\nFor KV$: TTFT is the metric most affected by KV cache placement. A "
        "request whose prefill prefix is cached in L1 has near-zero TTFT; one that "
        "requires L3 (SSD) loads can have 100ms+ TTFT just for cache warmup."
    ),
    "storage i/o": (
        "Aggregate disk I/O activity plus OS page-fault rate.",
        "Why this matters: This is the &quot;health vitals&quot; view of the storage "
        "subsystem. Sustained writes &gt; 2 GB/s indicate active KV cache spilling. "
        "High major fault rate without disk I/O indicates DRAM exhaustion / swap.\n\n"
        "For KV$: when L1 (HBM) overflows to L2 (DRAM), there's no disk I/O. When "
        "L2 (DRAM) overflows to L3 (SSD), this chart should light up with steady "
        "write activity matching the SGLang `backuped_tokens_total` rate."
    ),
    "session / stream": (
        "Per-inference-session view: lifetime, KV footprint, BW consumed by each request.",
        "Why this matters: When 10 requests are in flight, this chart shows how each "
        "one is utilising memory and storage bandwidth. Outlier streams that consume "
        "10× more I/O than peers indicate either very long contexts, heavy cache "
        "thrashing, or pathological access patterns.\n\nFor KV$: each session is a "
        "stream in the bandwidth_per_stream.csv data. The shape of this distribution "
        "tells you whether your workload is uniform (good for cache sizing) or "
        "long-tailed (a few heavy requests dominate)."
    ),
    "kv cache block": (
        "Lifecycle events for individual KV cache blocks — load, evict, write-back, prefetch.",
        "Why this matters: Every KV block in the radix-tree cache has a lifecycle: "
        "created during prefill, hit on subsequent prefills (if prefix matches), "
        "evicted under memory pressure, backed up to L2/L3, and loaded back if the "
        "session resumes. The rate of each transition tells you whether the cache is "
        "thrashing.\n\nFor KV$: high `evicted` + high `load_back` = thrashing (the "
        "cache is too small for the working set). High `backuped` with low "
        "`load_back` = good tier policy (cold blocks are spilled, warm ones stay)."
    ),
    "nvme io workload": (
        "Aggregate NVMe IOPS, throughput, and queue depth — the SSD&#39;s view of the workload.",
        "Why this matters: This is the device-level view of all SSD activity, "
        "regardless of which process generated it. A sustained 80%+ utilization "
        "with rising queue depth means the SSD is saturated and adds latency to "
        "every request.\n\nFor KV$: when KV cache spills to L3 (SSD), you'll see "
        "this chart spike. The R/W ratio reveals workload character — KV loads "
        "are reads, KV write-backs are writes. A heavy-write phase corresponds "
        "to L2→L3 spillover; heavy-read corresponds to L3→L1 reactivation."
    ),
    "nvme io deep profiling": (
        "Per-request NVMe details: request size, alignment, sequential vs random, latency.",
        "Why this matters: Two workloads with identical aggregate IOPS can stress an "
        "SSD very differently. 4KB random reads have ~10× the per-byte overhead of "
        "1MB sequential reads. This chart shows the actual request shape, which is "
        "what determines whether the SSD will keep up.\n\nFor KV$: KV cache I/O has "
        "a characteristic signature — small (64KB-256KB) writes to sequential LBAs "
        "during spill, small random reads during reactivation. Deviation from that "
        "signature (e.g. lots of tiny 4KB I/O) usually indicates metadata thrashing."
    ),
    "ssd read workload": (
        "Read-only deep dive: read size distribution, read inter-arrival times, read alignment.",
        "Why this matters: SSDs deliver their advertised IOPS only on 4K-aligned, "
        "queue-depth-saturated workloads. Misaligned reads pay a read-modify-write "
        "penalty. Bursts faster than the SSD's GC interval will trigger latency "
        "spikes.\n\nFor KV$: every KV cache miss that reaches L3 generates a read "
        "here. If the read pattern is random and small, your SSD's random read "
        "spec dominates achievable throughput — and L3 access becomes a bottleneck "
        "for token generation."
    ),
    "ssd write workload": (
        "Write-only deep dive: write size distribution, write IAT, write alignment.",
        "Why this matters: SSD write performance degrades over time as cells fill up "
        "and GC kicks in. Large sequential writes (preferred) coexist peacefully "
        "with reads; small random writes (avoided) trigger background GC that "
        "stalls reads.\n\nFor KV$: KV write-backs from L2 (DRAM) to L3 (SSD) "
        "should be large sequential writes — the runtime batches them. If you "
        "see small random writes here, that's likely metadata or wandering free "
        "list allocation, which will hurt sustained throughput."
    ),
    "trim / discard": (
        "TRIM (discard) commands — how the OS tells the SSD which blocks are no longer needed.",
        "Why this matters: TRIM lets the SSD's GC reclaim space without copying "
        "stale data, dramatically improving sustained write performance. No TRIM = "
        "the SSD treats every block as &quot;live&quot;, slowly degrading to its "
        "factory-fresh-out-of-box state.\n\nFor KV$: when a KV cache session "
        "completes, the runtime should TRIM the blocks it occupied so the SSD "
        "can prepare them for reuse without read-modify-write. Absent TRIM, "
        "long runs will see write performance degrade as the SSD fills with "
        "stale KV data."
    ),
    "cross-layer correlation": (
        "Derived KPIs that span GPU + NVMe + SGLang — token cost in storage I/O.",
        "Why this matters: A single &quot;tokens per second&quot; number hides the "
        "cost structure. This section computes per-token SSD bandwidth (MB of disk "
        "I/O per generated token), per-token HBM bandwidth, and a throughput "
        "bottleneck estimate based on the most-loaded subsystem.\n\nFor KV$: when "
        "per-token SSD cost is high (&gt; 0.1 MB/tok), the KV cache is regularly "
        "hitting L3 — your model is paying SSD-tier latency on the critical path. "
        "When per-token HBM BW saturates the GPU's HBM peak, decode is "
        "HBM-bandwidth-bound and adding more GPUs won't help (each GPU is "
        "individually saturated)."
    ),
    "cross-layer kpi": (
        "Composite KPIs that span GPU, NVMe, and inference engine layers.",
        "Why this matters: Bottlenecks rarely live in one layer — they're usually "
        "the intersection of two. &quot;GPU is idle&quot; + &quot;SSD is busy&quot; = "
        "KV loads are the bottleneck. &quot;GPU is busy&quot; + &quot;SSD is "
        "idle&quot; = HBM bandwidth or compute is the bottleneck.\n\nFor KV$: this "
        "is where you spot tier-mismatched workloads — e.g., a small fast SSD "
        "wasted on a workload that fits in DRAM, or a workload that needs L3 "
        "running on storage that can't keep up."
    ),
    "lba hot/cold": (
        "Spatial distribution of disk accesses — which regions of the SSD address space are hot.",
        "Why this matters: Most workloads concentrate their accesses on a small "
        "subset of the disk — this is the working set. Quantifying it (via Gini "
        "coefficient or top-1% byte share) tells you how much storage you really "
        "need: a 10TB SSD where 99% of bytes touch the same 100GB is wasteful.\n\n"
        "For KV$: KV cache pages tend to be hot for the duration of a session and "
        "cold afterward. A high Gini means the runtime is correctly concentrating "
        "active sessions; a low Gini suggests scattered, ineffective caching."
    ),
    "per-stream bandwidth": (
        "How total disk bandwidth is divided across concurrent inference sessions.",
        "Why this matters: Under contention, fair-share splitting is rare — heavy "
        "streams often crowd out lighter ones (head-of-line blocking on the device "
        "queue). The shape of the per-stream BW distribution reveals fairness "
        "issues that aggregate stats miss.\n\nFor KV$: a single long-context "
        "request can monopolize the SSD's read queue, starving other sessions' "
        "KV loads and inflating their TTFTs. This chart is where you spot that."
    ),
    "ssd io workload characteristics": (
        "Comprehensive SSD I/O profile across read, write, and trim operations.",
        "Why this matters: This unified view lets you compare the three I/O types "
        "side-by-side on the same axes — bandwidth, IOPS, latency, queue behavior. "
        "Disproportions (e.g., huge write BW relative to read BW) reveal workload "
        "imbalance that aggregate-only views hide.\n\nFor KV$: a healthy KV "
        "workload should show roughly balanced read and write BW when the cache "
        "is in steady state, with a brief write-heavy phase at the start (cache "
        "fill) and a brief trim-heavy phase at the end (session cleanup)."
    ),
    "hbm (gpu) bandwidth": (
        "HBM (GPU memory) read/write bandwidth and transaction rate.",
        "Why this matters: A100 80GB HBM2e theoretical peak is ~2 TB/s. Sustained "
        "&gt; 1.5 TB/s during decode means you're memory-bandwidth bound — adding "
        "more compute won't help, only smaller models, quantization, or faster HBM "
        "will.\n\nFor KV$: every decode token reads the entire active KV cache "
        "from HBM. KV cache size × decode rate gives you the HBM read BW the "
        "model needs. If actual HBM BW is below that, the GPU is stalling on "
        "KV loads — which means the L1 tier is the bottleneck."
    ),
    "system dram": (
        "Host (CPU-side) DRAM bandwidth and transaction rate from AMDuProf PMU counters.",
        "Why this matters: Host DRAM is the L2 tier for KV cache. EPYC servers "
        "typically have 12-channel DDR5 at ~460 GB/s peak — much slower than HBM "
        "but much larger. If KV spillover saturates this number, your L2 tier "
        "becomes the bottleneck.\n\nFor KV$: the rate at which the runtime can "
        "spill HBM→DRAM and reload DRAM→HBM is gated by this bandwidth divided "
        "by your KV block size. High DRAM BW here during steady-state inference "
        "is the signature of an active L2 tier."
    ),
    "swap storm": (
        "Page swap and major-fault activity from /proc/vmstat.",
        "Why this matters: Swap activity during ML inference is almost always "
        "pathological — the kernel is pushing pages of model weights or KV cache "
        "to swap because pinned memory was misconfigured. A swap storm here "
        "correlates with massive latency spikes in TTFT/TPOT.\n\nFor KV$: if "
        "your L2 (DRAM) tier was sized larger than physical RAM, the kernel "
        "fills RAM and then swaps to disk. The SGLang runtime sees this as "
        "host memory pressure but the underlying cost is swap I/O — visible "
        "here as `pswpout`/`pswpin` rates."
    ),
    "bottleneck attribution": (
        "Cross-layer bottleneck analysis — which subsystem is limiting throughput.",
        "Why this matters: With dozens of metrics across compute, memory, storage, "
        "and the inference engine itself, attribution is non-trivial. This view "
        "applies heuristics (utilization, saturation, error correlation) to "
        "highlight which layer is the dominant constraint.\n\nFor KV$: the most "
        "common attribution result for KV-cache-heavy workloads is &quot;HBM "
        "capacity&quot; (causing eviction churn) or &quot;SSD random read&quot; "
        "(slowing L3 reactivation). Both have specific remedies — quantize the "
        "KV (HBM capacity) or batch L3 loads (SSD random read)."
    ),
    "metric derivations": (
        "Reference tables showing the formula behind every reported metric.",
        "Why this matters: Different tools compute &quot;throughput&quot; or "
        "&quot;latency&quot; differently. This section makes the math explicit so "
        "comparisons with other measurement frameworks are well-founded.\n\nFor "
        "KV$: pay particular attention to `cache_hit_rate_realtime_pct` and "
        "`hicache_host_fill_pct` definitions — those are the two metrics that "
        "drive most optimization decisions."
    ),
    "optimisation": (
        "Automatically-generated recommendations based on observed bottlenecks.",
        "Why this matters: The recommendations distill the cross-layer analysis "
        "into prioritized actions — change batch size, quantize KV, add a swap "
        "disable, enable TRIM, etc. They're guidance, not mandates: validate "
        "with controlled experiments.\n\nFor KV$: the most impactful KV-related "
        "recommendations are typically batch size (reduces concurrent KV "
        "footprint), KV quantization (FP8 halves HBM consumption), and tier "
        "policy (whether to spill to DRAM or recompute)."
    ),
}


def _match_explanation(heading: str) -> tuple[str, str] | None:
    h = heading.lower()
    for key, val in CHART_EXPLANATIONS.items():
        if key in h:
            return val
    return None


# ─── Stat extraction from raw/ for tooltips ──────────────────────────────────
def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_csv_summary(path: Path) -> dict:
    """Return basic min/mean/max for each numeric column."""
    if not path.exists() or path.stat().st_size == 0:
        return {}
    out: dict[str, dict[str, float]] = {}
    try:
        with open(path, encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []
            data: dict[str, list[float]] = {c: [] for c in cols}
            for row in r:
                for c in cols:
                    try:
                        data[c].append(float(row[c]))
                    except (ValueError, TypeError):
                        pass
        for c, vals in data.items():
            if vals:
                out[c] = {"min": min(vals), "mean": sum(vals)/len(vals),
                          "max": max(vals), "n": len(vals)}
    except Exception as e:
        log.debug("csv summary error %s: %s", path, e)
    return out


def _build_tooltip_data(raw_dir: Path) -> dict[str, str]:
    """Build a map of heading-keyword → tooltip HTML."""
    tt: dict[str, str] = {}

    sg = _read_json(raw_dir / "sglang_summary.json")
    if sg:
        tt["sglang inference"] = (
            f"<b>TTFT</b> {sg.get('server_ttft_ms', 0):.0f}ms · "
            f"<b>TPOT</b> {sg.get('server_itl_ms', 0):.1f}ms · "
            f"<b>E2E</b> {sg.get('server_e2e_ms', 0):.0f}ms<br>"
            f"<b>Throughput</b> {sg.get('ai_op_decode_tok_s', 0):.1f} tok/s · "
            f"<b>Cache hit</b> {sg.get('cache_hit_rate_realtime_pct', 0):.1f}%<br>"
            f"<b>Samples</b>: {sg.get('collection_samples', 0)} scrapes"
        )
        tt["ai operation phase"] = (
            f"<b>TTFT</b> {sg.get('server_ttft_ms', 0):.0f}ms "
            f"(prefill) · <b>TPOT</b> {sg.get('server_itl_ms', 0):.1f}ms (decode)<br>"
            f"Prefill compute / cache tokens: "
            f"{sg.get('rt_prefill_compute_tokens', 0):,} / "
            f"{sg.get('rt_prefill_cache_tokens', 0):,}"
        )
        tt["latency breakdown"] = (
            f"<b>TTFT</b> {sg.get('server_ttft_ms', 0):.0f}ms · "
            f"<b>TPOT</b> {sg.get('server_itl_ms', 0):.1f}ms · "
            f"<b>E2E</b> {sg.get('server_e2e_ms', 0):.0f}ms<br>"
            f"Decode tokens: {sg.get('rt_decode_tokens', 0):,}"
        )

    gpu = _read_json(raw_dir / "gpu_summary.json")
    if gpu:
        tt["gpu utilisation"] = (
            f"<b>{gpu.get('gpu_count', 0)} GPUs</b><br>"
            f"<b>Util</b> mean {gpu.get('gpu_util_mean', 0):.1f}%, "
            f"peak {gpu.get('gpu_util_peak', 0):.1f}%<br>"
            f"<b>HBM</b> {gpu.get('hbm_used_mb_mean', 0)/1024:.1f} GB / "
            f"{gpu.get('hbm_total_mb_per_gpu', 0)/1024:.0f} GB "
            f"({gpu.get('hbm_util_pct_mean', 0):.0f}%)<br>"
            f"<b>Power</b> peak {gpu.get('power_w_peak', 0):.0f} W/GPU"
        )
        tt["hbm (gpu) bandwidth"] = (
            f"<b>HBM util</b> {gpu.get('hbm_util_pct_mean', 0):.0f}% · "
            f"DCGM active {gpu.get('dcgm_hbm_bw_active_pct', 0):.0f}%<br>"
            f"<b>HBM used</b> {gpu.get('hbm_used_mb_mean', 0)/1024:.1f} GB mean"
        )

    smart = _read_json(raw_dir / "smart_summary.json")
    if smart:
        tt["nvme io"] = (
            f"<b>{smart.get('model', '?')}</b> {smart.get('capacity_gb', 0)} GB<br>"
            f"<b>Temp</b> {smart.get('temperature_c', 0)}°C · "
            f"<b>WAF</b> {smart.get('waf', 0):.2f}<br>"
            f"<b>Lifetime used</b> {smart.get('lifetime_pct_used', 0)}%"
        )

    bt = _read_json(raw_dir / "summary.json")
    if bt:
        tt["ssd read workload"] = (
            f"<b>{bt.get('read_events', 0):,}</b> read events<br>"
            f"<b>R BW</b> {bt.get('read_bw_mb_s_mean', 0):.1f} MB/s · "
            f"<b>R IOPS</b> {bt.get('read_iops_mean', 0):.0f}<br>"
            f"<b>Read bytes</b> {bt.get('read_bytes_total', 0)/1e9:.2f} GB"
        )
        tt["ssd write workload"] = (
            f"<b>{bt.get('write_events', 0):,}</b> write events<br>"
            f"<b>W BW</b> {bt.get('write_bw_mb_s_mean', 0):.1f} MB/s · "
            f"<b>W IOPS</b> {bt.get('write_iops_mean', 0):.0f}<br>"
            f"<b>Write bytes</b> {bt.get('write_bytes_total', 0)/1e9:.2f} GB"
        )
        tt["trim / discard"] = (
            f"<b>TRIM events</b>: {bt.get('trim_events', 0):,}<br>"
            f"<b>TRIM IOPS</b> {bt.get('trim_iops_mean', 0):.2f} mean<br>"
            f"<b>TRIM bytes</b> {bt.get('trim_bytes_total', 0)/1e9:.2f} GB"
        )
        tt["nvme io workload"] = (
            f"<b>{bt.get('total_events', 0):,}</b> total block IOs<br>"
            f"<b>R:W ratio</b> {bt.get('rw_ratio', 0):.2f}× · "
            f"R={bt.get('read_events', 0):,} W={bt.get('write_events', 0):,} "
            f"T={bt.get('trim_events', 0):,}<br>"
            f"<b>Duration</b> {bt.get('duration_sec', 0):.0f} sec"
        )

    nvm = _read_csv_summary(raw_dir / "nvme_driver_timeseries.csv")
    if nvm:
        rd = nvm.get("rd_iops", {})
        wr = nvm.get("wr_iops", {})
        util = nvm.get("io_util_pct", {})
        tt["nvme io deep profiling"] = (
            f"<b>R IOPS</b> mean {rd.get('mean', 0):.0f}, "
            f"peak {rd.get('max', 0):.0f}<br>"
            f"<b>W IOPS</b> mean {wr.get('mean', 0):.0f}, "
            f"peak {wr.get('max', 0):.0f}<br>"
            f"<b>Util</b> mean {util.get('mean', 0):.1f}%, "
            f"peak {util.get('max', 0):.1f}%"
        )

    vm = _read_csv_summary(raw_dir / "vmstat_timeseries.csv")
    if vm:
        pswpin = vm.get("pswpin", {})
        pswpout = vm.get("pswpout", {})
        pgmaj = vm.get("pgmajfault", {})
        tt["swap storm"] = (
            f"<b>Swap-in</b> peak {pswpin.get('max', 0):.0f} pages<br>"
            f"<b>Swap-out</b> peak {pswpout.get('max', 0):.0f} pages<br>"
            f"<b>Major faults</b> peak {pgmaj.get('max', 0):.0f}"
        )
        tt["storage i/o"] = tt.get("storage i/o", "") + (
            f"<b>Major faults</b> peak {pgmaj.get('max', 0):.0f}/sec"
        )

    return tt


def _match_tooltip(heading: str, tooltips: dict[str, str]) -> str:
    h = heading.lower()
    for key, val in tooltips.items():
        if key in h:
            return val
    return ""


# ─── HTML rewriting ──────────────────────────────────────────────────────────
DARK_THEME_CSS = """
<style id="amoprof-enhancer-theme">
  /* ── Dark theme overrides (post-processor injected) ───────────────────── */
  body {
    background: #0f172a !important;
    color: #e2e8f0 !important;
  }
  /* Card containers: dark gray panel with strong borders */
  .card, div[style*="background:#fff"], div[style*="background:white"],
  div[style*="background:#ffffff"] {
    background: #1e293b !important;
    border-color: #475569 !important;
    color: #e2e8f0 !important;
  }
  /* Headings */
  h1, h2, h3, h4 {
    color: #f1f5f9 !important;
  }
  /* Subheadings inside cards (originally dark slate) become light */
  div[style*="color:#0f172a"], div[style*="color: #0f172a"],
  div[style*="color:#334155"], div[style*="color: #334155"],
  div[style*="color:#1e293b"] {
    color: #cbd5e1 !important;
  }
  /* Inline code spans (data source citations) — dim but readable */
  code, span[style*="background:#eff6ff"], span[style*="background:#faf5ff"] {
    background: #334155 !important;
    color: #e0f2fe !important;
  }
  /* KPI cards — keep distinct from outer cards */
  div[style*="border:1px solid #e2e8f0"] {
    background: #0f172a !important;
    border-color: #475569 !important;
  }
  /* The labels (small uppercase) inside KPIs */
  div[style*="color:#64748b"] {
    color: #94a3b8 !important;
  }


  /* ── Dark theme contrast fixes for generated inline styles ───────────── */
  body > div:first-of-type span[style*="font-size:22px"][style*="font-weight:900"] {
    color: #f8fafc !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.35);
  }
  body > div:first-of-type span[style*="font-size:22px"][style*="color:#4f46e5"] {
    color: #a5b4fc !important;
  }
  .card:not(.setup-panel) span[style*="color:#0f172a"],
  .card:not(.setup-panel) span[style*="color: #0f172a"],
  .card:not(.setup-panel) span[style*="color:#334155"],
  .card:not(.setup-panel) span[style*="color: #334155"],
  .card:not(.setup-panel) span[style*="color:#1e293b"],
  .card:not(.setup-panel) td[style*="color:#0f172a"],
  .card:not(.setup-panel) td[style*="color: #0f172a"],
  .card:not(.setup-panel) td[style*="color:#334155"],
  .card:not(.setup-panel) td[style*="color: #334155"],
  .card:not(.setup-panel) td[style*="color:#1e293b"],
  .card:not(.setup-panel) b[style*="color:#0f172a"],
  .card:not(.setup-panel) b[style*="color: #0f172a"],
  .card:not(.setup-panel) div[style*="color:#0f172a"],
  .card:not(.setup-panel) div[style*="color: #0f172a"],
  .card:not(.setup-panel) div[style*="color:#334155"],
  .card:not(.setup-panel) div[style*="color: #334155"],
  .card:not(.setup-panel) div[style*="color:#1e293b"] {
    color: #cbd5e1 !important;
  }

  /* Keep setup/config section intentionally light even in dark theme. */
  .setup-panel {
    background: linear-gradient(135deg, #eef2ff 0%, #ffffff 55%, #f8fafc 100%) !important;
    border: 1px solid #a5b4fc !important;
    border-left: 6px solid #818cf8 !important;
    color: #0f172a !important;
    box-shadow: 0 6px 18px rgba(15,23,42,0.35) !important;
  }
  .setup-panel h2,
  .setup-panel .setup-info-title {
    color: #1e1b4b !important;
    text-shadow: none !important;
  }
  .setup-panel .setup-table,
  .setup-panel .setup-info-box,
  .setup-panel table {
    background: #ffffff !important;
    color: #0f172a !important;
  }
  .setup-panel th,
  .setup-panel td,
  .setup-panel .setup-key,
  .setup-panel .setup-value,
  .setup-panel p,
  .setup-panel div,
  .setup-panel span {
    color: #0f172a !important;
  }
  .setup-panel .setup-row-defaulted .setup-key,
  .setup-panel .setup-row-defaulted .setup-value {
    background: #fff7ed !important;
    color: #7c2d12 !important;
  }
  .setup-panel code {
    background: #eef2ff !important;
    color: #3730a3 !important;
  }

  /* Wrapper around each chart image — adds tooltip parent */
  figure.amoprof-chart {
    position: relative;
    margin: 0 0 8px 0;
    padding: 0;
    border-radius: 10px;
    overflow: hidden;
    background: #0f172a;
    border: 1px solid #475569;
    cursor: help;
  }
  figure.amoprof-chart img {
    width: 100%;
    display: block;
    border-radius: 9px;
    transition: transform 0.18s ease;
  }
  figure.amoprof-chart:hover img {
    transform: scale(1.005);
  }
  /* Tooltip — small badge in the top-right that reveals on hover */
  figure.amoprof-chart .amoprof-tt-badge {
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(15,23,42,0.85);
    color: #cbd5e1;
    border: 1px solid #475569;
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    backdrop-filter: blur(2px);
    pointer-events: none;
    opacity: 0.65;
    transition: opacity 0.15s;
  }
  figure.amoprof-chart:hover .amoprof-tt-badge {
    opacity: 1;
  }
  figure.amoprof-chart .amoprof-tt {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0.96);
    min-width: 280px;
    max-width: 480px;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #f1f5f9;
    border: 1px solid #64748b;
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 13px;
    line-height: 1.55;
    box-shadow: 0 8px 24px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.05) inset;
    opacity: 0;
    pointer-events: none;
    visibility: hidden;
    transition: opacity 0.18s, transform 0.18s, visibility 0.18s;
    z-index: 10;
  }
  figure.amoprof-chart:hover .amoprof-tt {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
    visibility: visible;
  }
  figure.amoprof-chart .amoprof-tt b {
    color: #fbbf24;
  }
  /* Per-chart explanation block — sits below the chart */
  .amoprof-explain {
    background: rgba(15, 23, 42, 0.6);
    border-left: 3px solid #22d3ee;
    margin: 10px 0 8px 0;
    padding: 10px 14px 12px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 12.5px;
    line-height: 1.6;
    color: #cbd5e1;
  }
  .amoprof-explain .amoprof-explain-summary {
    display: block;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.3px;
    color: #22d3ee;
    margin-bottom: 6px;
    text-transform: uppercase;
  }
  .amoprof-explain p {
    margin: 6px 0 0 0;
  }
  /* Existing <details> blocks (formula reveals) — readable on dark */
  details.fml {
    background: rgba(15, 23, 42, 0.7) !important;
    border-color: #475569 !important;
  }
  details.fml summary {
    color: #f1f5f9 !important;
    background: rgba(30, 41, 59, 0.6) !important;
  }
  details.fml .fml-body, details.fml code {
    color: #e2e8f0 !important;
    background: rgba(0, 0, 0, 0.25) !important;
  }
  details.fml .fml-note {
    color: #94a3b8 !important;
  }
  /* Scrollbars */
  ::-webkit-scrollbar { width: 12px; background: #0f172a; }
  ::-webkit-scrollbar-thumb { background: #475569; border-radius: 6px; }
  ::-webkit-scrollbar-thumb:hover { background: #64748b; }
</style>
"""


LIGHT_THEME_CSS = """
<style id="amoprof-enhancer-theme">
  /* ── Light theme: keep original amoprof colors, add tooltip+explanation styling ── */

  /* Wrapper around each chart image */
  figure.amoprof-chart {
    position: relative;
    margin: 0 0 8px 0;
    padding: 0;
    border-radius: 10px;
    overflow: hidden;
    cursor: help;
    border: 1px solid #cbd5e1;
  }
  figure.amoprof-chart img {
    width: 100%;
    display: block;
    border-radius: 9px;
    transition: transform 0.18s ease;
  }
  figure.amoprof-chart:hover img {
    transform: scale(1.003);
  }
  figure.amoprof-chart .amoprof-tt-badge {
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(255,255,255,0.92);
    color: #475569;
    border: 1px solid #cbd5e1;
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    pointer-events: none;
    opacity: 0.7;
    transition: opacity 0.15s;
  }
  figure.amoprof-chart:hover .amoprof-tt-badge {
    opacity: 1;
  }
  figure.amoprof-chart .amoprof-tt {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0.96);
    min-width: 280px;
    max-width: 480px;
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #f1f5f9;
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 13px;
    line-height: 1.55;
    box-shadow: 0 8px 24px rgba(15,23,42,0.4);
    opacity: 0;
    pointer-events: none;
    visibility: hidden;
    transition: opacity 0.18s, transform 0.18s, visibility 0.18s;
    z-index: 10;
  }
  figure.amoprof-chart:hover .amoprof-tt {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
    visibility: visible;
  }
  figure.amoprof-chart .amoprof-tt b {
    color: #fbbf24;
  }
  /* Per-chart explanation — light variant uses indigo accent on white */
  .amoprof-explain {
    background: linear-gradient(180deg, #f1f5f9 0%, #ffffff 100%);
    border-left: 3px solid #4f46e5;
    margin: 10px 0 14px 0;
    padding: 10px 14px 12px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 12.5px;
    line-height: 1.6;
    color: #1e293b;
    box-shadow: 0 1px 3px rgba(15,23,42,0.04);
  }
  .amoprof-explain .amoprof-explain-summary {
    display: block;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.3px;
    color: #4f46e5;
    margin-bottom: 6px;
    text-transform: uppercase;
  }
  .amoprof-explain p {
    margin: 6px 0 0 0;
  }
</style>
"""


def _wrap_chart_image(match: re.Match, heading: str,
                       tooltips: dict[str, str]) -> str:
    """Wrap an <img> tag in a <figure> with hover tooltip + badge."""
    img_tag = match.group(0)
    tt_html = _match_tooltip(heading, tooltips)
    badge = "📊 hover for stats" if tt_html else "📊 chart"
    tt_div = f'<div class="amoprof-tt">{tt_html}</div>' if tt_html else ""
    return (f'<figure class="amoprof-chart">'
            f'<span class="amoprof-tt-badge">{badge}</span>'
            f'{tt_div}'
            f'{img_tag}'
            f'</figure>')


def _inject_explanations_and_tooltips(html: str, raw_dir: Path | None) -> str:
    """Find each <h2> heading, then locate the chart-containing <img> after it
    and wrap it. Also inject explanation block after the heading.

    We process the HTML by splitting on <h2> tags to delimit sections.
    Charts inside a section get the section's tooltip + explanation.
    """
    tooltips: dict[str, str] = {}
    if raw_dir is not None:
        try:
            tooltips = _build_tooltip_data(raw_dir)
        except Exception as e:
            log.warning("tooltip build failed: %s", e)

    # Pattern: split HTML at <h2 ...>...</h2> boundaries while keeping the H2 text
    # We will walk through and rewrite each section in place.

    h2_re = re.compile(r'(<h2[^>]*>(.*?)</h2>)', re.IGNORECASE | re.DOTALL)
    img_re = re.compile(r'<img\s+src="data:image/png;base64,[^"]+"[^>]*/?>',
                         re.IGNORECASE | re.DOTALL)

    # Find all H2 positions
    sections = list(h2_re.finditer(html))
    if not sections:
        return html

    pieces: list[str] = []
    last_end = 0
    for idx, m in enumerate(sections):
        # Append everything up to and including the H2 tag
        pieces.append(html[last_end:m.end()])
        heading_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        # Insert explanation block right after the H2
        expl = _match_explanation(heading_text)
        if expl:
            summary, body = expl
            # Convert plain-text \n\n into <p> tags
            body_html = "".join(f"<p>{p.strip()}</p>" for p in body.split("\n\n") if p.strip())
            pieces.append(
                f'<div class="amoprof-explain">'
                f'<span class="amoprof-explain-summary">📖 What this chart shows</span>'
                f'{summary}{body_html}'
                f'</div>'
            )
        # Determine the end of this section (start of next H2, or EOF)
        section_end = sections[idx + 1].start() if idx + 1 < len(sections) else len(html)
        section_body = html[m.end():section_end]
        # Wrap each <img> inside this section
        def _wrap(mi):
            return _wrap_chart_image(mi, heading_text, tooltips)
        section_body = img_re.sub(_wrap, section_body)
        pieces.append(section_body)
        last_end = section_end

    # Append any tail content (unlikely, but safe)
    pieces.append(html[last_end:])
    return "".join(pieces)


def enhance_report(html_path: Path,
                   raw_dir: Path | None = None,
                   theme: str = "dark") -> Path:
    """Post-process an amoprof HTML report file in place.

    Idempotent — running this multiple times on the same file is a no-op for
    explanations and tooltips (detected by checking for the marker class
    `amoprof-explain` already present in the file). Theme CSS injection is
    also guarded by a unique <style> id.

    Returns the same path (file is overwritten).
    """
    html_path = Path(html_path)
    html = html_path.read_text(encoding="utf-8", errors="replace")

    already_enhanced = ('class="amoprof-explain"' in html
                        or 'class="amoprof-chart"' in html
                        or 'id="amoprof-enhancer-theme"' in html)

    # Inject theme CSS into <head> (right before </head>) — guarded by style id
    if theme in ("dark", "light"):
        if 'id="amoprof-enhancer-theme"' not in html:
            inject = DARK_THEME_CSS if theme == "dark" else LIGHT_THEME_CSS
            if "</head>" in html:
                html = html.replace("</head>", inject + "\n</head>", 1)
            else:
                html = inject + html

    # Inject per-chart tooltips and explanations — skip if already done
    if not already_enhanced:
        html = _inject_explanations_and_tooltips(html, raw_dir)
    else:
        log.info("amoprof enhancer: file already enhanced — only theme refreshed")

    html_path.write_text(html, encoding="utf-8")
    log.info("amoprof enhancer: wrote %s (%d KB, theme=%s)",
             html_path, len(html) // 1024, theme)
    return html_path
