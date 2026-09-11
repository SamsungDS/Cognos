"""Single source of truth for KPI-tile formulas.

Every summary tile in every report (Executive · End Report · Interactive)
shows the formula that produced its number, with the exact metric / column
names it was computed from.  Those formula strings live here and nowhere
else, so a metric's definition cannot drift between reports.

Consumers
---------
* ``report/combined.py``   — Executive ``kpi_card()``
* ``report/amoprof.py``    — End Report ``bw_card()`` / ``_kpi()``, and the
  §Metrics & Formulas table, which is generated from this registry rather
  than carrying its own copy of the same strings
* ``report/interactive.py`` — Interactive ``_kpi_tile()``

How the renderers use it
------------------------
Each renderer calls :func:`tile_note` with the tile's label and whatever
note it was going to show.  ``tile_note`` returns the registry formula in
place of that text.  Explanatory prose ("time-weighted average", "max ever
observed") is replaced outright; any measured value in the original note
(anything containing a digit, e.g. ``P90=1.4s``, ``312 M txns/s``) is kept
and appended after the formula, since deleting it would remove data the
tile is the only place to see.

Lookup is by normalised label, so a tile is wired up simply by existing —
no per-call-site edit.  A label with no registry entry keeps its original
note unchanged, which is what keeps this non-breaking.

Formula conventions
-------------------
``Δx``      counter delta across the selected window
``Δt``      elapsed wall-clock seconds across that window
``x[i,t]``  per-device i, per-sample t
``{...}``   Prometheus label selector, reproduced exactly as exported
Source file / column names are given verbatim so a number can be
recomputed from ``raw/`` by hand.
"""

from __future__ import annotations

import re
from typing import Dict

__all__ = ["FORMULAS", "VARIANTS", "formula_for", "axis_formula", "tile_note",
           "metric_formula_rows", "normalise_label"]


def normalise_label(label: str) -> str:
    """Fold a tile label to its lookup key.

    Tolerates the cosmetic differences between the three reports — case,
    punctuation, the ``L3 (local storage)`` / ``L3`` backend-name expansion,
    en/em dashes, and trailing units in parentheses.
    """
    s = str(label or "").strip().lower()
    s = s.replace("\u2192", "->").replace("\u2194", "<->")
    s = s.replace("\u2265", ">=").replace("\u2264", "<=")
    s = re.sub(r"\((?:local storage|remote storage|local ssd|cxl|network)\)", "", s)
    s = s.replace("\u2014", " ").replace("\u2013", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9%>=<+/ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# --------------------------------------------------------------------------
# Registry.  key = normalise_label(tile label) -> formula string.
# --------------------------------------------------------------------------
_RAW: Dict[str, str] = {

    # ── Latency (SGLang Prometheus histograms) ────────────────────────────
    "ttft": "Δsglang_time_to_first_token_seconds_sum ÷ "
            "Δsglang_time_to_first_token_seconds_count × 1000  [ms]",
    "ttft mean": "Δsglang_time_to_first_token_seconds_sum ÷ "
                 "Δsglang_time_to_first_token_seconds_count × 1000  [ms]",
    "ttft p50": "histogram_quantile(0.50, rate("
                "sglang_time_to_first_token_seconds_bucket[W])) × 1000  [ms]",
    "server ttft prom": "Δsglang_time_to_first_token_seconds_sum ÷ "
                        "Δsglang_time_to_first_token_seconds_count × 1000  [ms]",
    "tpot": "Δsglang_inter_token_latency_seconds_sum ÷ "
            "Δsglang_inter_token_latency_seconds_count × 1000  [ms/tok]  "
            "(alt: (E2E − TTFT) ÷ output_tokens)",
    "tpot / itl mean": "Δsglang_inter_token_latency_seconds_sum ÷ "
                       "Δsglang_inter_token_latency_seconds_count × 1000  [ms/tok]",
    # Alias so tiles labelled just "TPOT mean" (as of v1.20.2) find the same formula.
    "tpot mean": "Δsglang_inter_token_latency_seconds_sum ÷ "
                "Δsglang_inter_token_latency_seconds_count × 1000  [ms/tok]",
    "tpot / itl p50": "histogram_quantile(0.50, rate("
                      "sglang_inter_token_latency_seconds_bucket[W])) × 1000  [ms]",
    "server itl prom": "Δsglang_inter_token_latency_seconds_sum ÷ "
                       "Δsglang_inter_token_latency_seconds_count × 1000  [ms]",
    "e2e mean": "Δsglang_e2e_request_latency_seconds_sum ÷ "
                "Δsglang_e2e_request_latency_seconds_count × 1000  [ms]",
    "e2e p50": "histogram_quantile(0.50, rate("
               "sglang_e2e_request_latency_seconds_bucket[W])) × 1000  [ms]",
    "server e2e prom": "Δsglang_e2e_request_latency_seconds_sum ÷ "
                       "Δsglang_e2e_request_latency_seconds_count × 1000  [ms]",
    "queue time": "sess_queue_mean_ms = mean(request.queue_ms) over "
                  "session request log  [ms]",

    # ── Throughput ────────────────────────────────────────────────────────
    "input throughput": "Δsglang_prompt_tokens_total ÷ Δtime_sec over the WHOLE "
                        "selected window  [tok/s] — a run average that includes idle "
                        "time, so it reads lower than the per-interval rate charted "
                        "in Bottleneck Analysis",
    "output throughput": "Δsglang_generation_tokens_total ÷ Δtime_sec over the WHOLE "
                         "selected window  [tok/s] — run average including idle time",
    "throughput mean": "mean(sglang_gen_throughput) over samples with "
                       "sglang_num_running_reqs > 0  [tok/s]",
    "throughput p50": "median(sglang_gen_throughput) over samples with "
                      "sglang_num_running_reqs > 0  [tok/s]",
    "peak throughput": "max(sglang_gen_throughput)  [tok/s]  "
                       "(fallback: Δsglang_generation_tokens_total ÷ Δtime_sec)",
    "input tps": "bench prompt_tokens ÷ bench elapsed_s  [tok/s]",
    "output tps": "bench output_tokens ÷ bench elapsed_s  [tok/s]",

    # ── Cache ─────────────────────────────────────────────────────────────
    # The caption previously claimed Δsglang_cached_tokens_total was in the
    # numerator.  The code never added it — it computes prefill_cache ÷
    # (prefill_cache + prefill_compute).  A caption that describes a different
    # expression than the one computed is worse than no caption: it sends the
    # reader looking for a discrepancy that does not exist, and hides one that
    # might.  This text is now the expression actually evaluated, and matches
    # the equivalent PromQL sum(increase(...)) form.
    "cache hit": "Δsglang_realtime_tokens_total{mode=\"prefill_cache\"} ÷ "
                 "(Δ…{mode=\"prefill_cache\"} + Δ…{mode=\"prefill_compute\"}) "
                 "× 100  [%] · token-weighted over the analysed window · "
                 "equals sum(increase(…prefill_cache)) ÷ "
                 "(sum(increase(…prefill_cache)) + sum(increase(…prefill_compute)))",
    "cache hit %": "Δsglang_realtime_tokens_total{mode=\"prefill_cache\"} ÷ "
                   "(Δ…{mode=\"prefill_cache\"} + Δ…{mode=\"prefill_compute\"}) "
                   "× 100  [%] · token-weighted over the analysed window",
    "bench cache hit": "bench cached_tokens ÷ bench prompt_tokens × 100  [%]",
    "hicache fill %": "sglang_hicache_host_used_tokens ÷ "
                      "sglang_hicache_host_total_tokens × 100  [%]",

    # ── L1 · GPU / HBM ────────────────────────────────────────────────────
    "gpu util": "mean(gpu_util[i,t]) over all GPUs i and samples t · "
                "gpu_timeseries.csv ← nvidia-smi utilization.gpu  [%]",
    "gpu util mean %": "mean(gpu_util[i,t]) over all GPUs i and samples t · "
                       "gpu_timeseries.csv ← nvidia-smi utilization.gpu  [%]",
    "hbm used all gpus": "Σ mean(mem_used[i,t]) over GPUs i ÷ 1024  [GB]  · "
                         "gpu_timeseries.csv ← nvidia-smi memory.used",
    "hbm used gb/gpu": "mean(mem_used[i,t]) ÷ 1024  [GB/GPU]  · "
                       "gpu_timeseries.csv ← nvidia-smi memory.used",
    "hbm util %": "mean(mem_used[i,t] ÷ mem_total[i]) × 100  [%]  · "
                  "gpu_timeseries.csv ← nvidia-smi memory.used/total",
    "gpu power": "max(power_w[i,t])  [W]  · "
                 "gpu_timeseries.csv ← nvidia-smi power.draw",
    "hbm read bw": "model_bytes_per_GPU ÷ TPOT_s = "
                   "(params × 2 bytes ÷ n_gpus) ÷ (tpot_ms ÷ 1000)  [GB/s]  "
                   "(derived — nsys HBM counters inactive)",
    "hbm write bw": "HBM_read_BW × 0.12  [GB/s]  "
                    "(empirical write:read ratio for attention workloads)",
    "hbm bw util": "HBM_read_BW ÷ hbm_peak_bw_gbs × 100  [%]",
    "hbm peak bw": "device HBM2e theoretical peak from GPU model lookup  [GB/s]",
    "hbm read txns/s": "HBM_read_BW × 10⁹ ÷ 64  [txn/s]  "
                       "(64 B = HBM2e cache line)",
    "hbm write txns/s": "HBM_write_BW × 10⁹ ÷ 64  [txn/s]  "
                        "(64 B = HBM2e cache line)",

    # ── L2 · host DRAM ────────────────────────────────────────────────────
    "dram used": "(MemTotal − MemFree − Buffers − Cached) ÷ 1024³  [GB]  · "
                 "/proc/meminfo",
    "dram residency": "resident L2 KV bytes ÷ configured HiCache size  [GB / GB]",
    "dram bw": "dram_total_gb_s from amduprof_pcm_timeseries.csv  [GB/s]  "
               "(= dram_read_gb_s + dram_write_gb_s)",
    "dram read bw": "dram_read_gb_s · amduprof_pcm_timeseries.csv ← AMD DF PMU "
                    "\"Total Mem RdBw\" = read txns × 64 B ÷ interval ÷ 10⁹  [GB/s]",
    "dram write bw": "dram_write_gb_s · amduprof_pcm_timeseries.csv ← AMD DF PMU "
                     "\"Total Mem WrBw\"  [GB/s]",
    "dram total bw": "dram_read_gb_s + dram_write_gb_s  [GB/s]  · "
                     "amduprof_pcm_timeseries.csv",
    "dram bw util": "dram_total_gb_s ÷ dram_peak_theoretical_gbs × 100  [%]",
    "dram read txns/s": "dram_read_gb_s × 10⁹ ÷ 64  [txn/s]  "
                        "(64 B = DDR cache line)",
    "dram used gb": "(MemTotal − MemFree − Buffers − Cached) ÷ 1024³  [GB]  · "
                    "/proc/meminfo",

    # ── L3 · storage bandwidth / IOPS / latency / queue ───────────────────
    "l3 read bw": "mean(rd_bw_mbs) · nvme_driver_timeseries.csv  [MB/s]",
    "l3 write bw": "mean(wr_bw_mbs) · nvme_driver_timeseries.csv  [MB/s]",
    "rd bw mean": "mean(rd_bw_mbs) · nvme_driver_timeseries.csv  [MB/s]  "
                  "(blktrace: Σ read size_bytes ÷ run_duration_s ÷ 10⁶)",
    "wr bw mean": "mean(wr_bw_mbs) · nvme_driver_timeseries.csv  [MB/s]  "
                  "(blktrace: Σ write size_bytes ÷ run_duration_s ÷ 10⁶)",
    "rd bw total": "Σ read size_bytes ÷ run_duration_s ÷ 10⁶  [MB/s]  · blktrace",
    "wr bw total": "Σ write size_bytes ÷ run_duration_s ÷ 10⁶  [MB/s]  · blktrace",
    "wr iops mean": "mean(wr_iops) · nvme_driver_timeseries.csv  [IO/s]",
    "wr latency": "mean(wr_lat_ms) · nvme_driver_timeseries.csv  [ms]  "
                  "(blktrace: mean(C−Q) per write)",
    "rd size mean": "mean(size_bytes) over read events ÷ 1024  [KB]  · blktrace",
    "wr size mean": "mean(size_bytes) over write events ÷ 1024  [KB]  · blktrace",
    "bytes written": "Σ write size_bytes over run  [B]  · blktrace "
                     "(cross-check: Δdata_units_written × 512000 from SMART)",
    "drive wear": "Δpercentage_used from nvme smart-log over run  [%]",
    "host wr cmds": "Δhost_write_commands from nvme smart-log  [commands]",
    "block ios": "count(blktrace Q events)  [IOs]",
    "avg dispatched i/o": "mean(inflight) · nvme_driver_timeseries.csv  "
                          "(canonical: qd_best_effort · "
                          "queue_depth_sources_timeseries.csv)",

    # ── Queue depth (canonical merged source) ─────────────────────────────
    "qd mean": "time-weighted mean(qd) over samples with qd > 0 · "
               "queue_depth_sources_timeseries.csv "
               "(qd_best_effort → qd → weighted_qd → inflight)",
    "qd p50": "quantile(qd, 0.50) over qd > 0 · queue_depth_sources_timeseries.csv",
    "qd p95": "quantile(qd, 0.95) over qd > 0 · queue_depth_sources_timeseries.csv",
    "qd p99": "quantile(qd, 0.99) over qd > 0 · queue_depth_sources_timeseries.csv",
    "qd peak": "max(qd) · queue_depth_sources_timeseries.csv",
    "time at qd>=32": "count(qd ≥ 32) ÷ count(qd samples) × 100  [%]",

    # ── Session / request log ─────────────────────────────────────────────
    "total requests": "count(requests in session log)  "
                      "(rate = count ÷ run_duration_s  [req/s])",
    "max concurrent": "max(concurrent in-flight requests) from session "
                      "arrival/completion timestamps",
    "input tokens": "mean(request.prompt_tokens) over session log  [tok]",
    "output tokens": "mean(request.output_tokens) over session log  [tok]",

    # ── KV block accounting ───────────────────────────────────────────────
    "block size": "page_size × n_layers × 2 (K,V) × n_kv_heads × head_dim × "
                  "dtype_bytes  [B]",
    "l1 kv pool active": "sglang_token_usage × 100  [%]  "
                         "(live KV blocks ÷ HBM KV pool capacity)",
    "l2 kv pool active": "sglang_hicache_host_used_tokens ÷ "
                         "sglang_hicache_host_total_tokens × 100  [%]",
    "l1->l2 offload": "Δsglang_evicted_tokens_total × kv_bytes_per_token  [B]",
    "l2->l3 backup": "Δsglang_backuped_tokens_total × kv_bytes_per_token  [B]",
    "l3 onboard": "Δsglang_prefetched_tokens_total × kv_bytes_per_token  [B]",
    "l3 peak resident": "max(resident_tokens) ÷ block_size_tokens  [blocks]",
    "logical kv movement l3": "(Δbackuped + Δprefetched) tokens × "
                              "kv_bytes_per_token  [B]",
    "physical l3 block r / w total": "Σ blktrace read size_bytes / "
                                     "Σ blktrace write size_bytes  [B]",
    "l3 cache used": "resident L3 KV bytes ÷ configured L3 capacity  [GB / GB]",
    "l3 used": "used ÷ total from statvfs on the L3 mount path  [GB]",
    "l3 tok ceiling": "L3 capacity_bytes ÷ kv_bytes_per_token  [tok]",
    "l3": "backend from --hicache-storage-backend · setup_details.json; "
          "\"none\" when no L3 storage movement was observed in "
          "sglang_backuped_tokens_total / sglang_prefetched_tokens_total",
    # ── Correlation-chart axes (Bottleneck Analysis) ──────────────────────
    # Drivers
    "input tok/s": "Δsglang_prompt_tokens_total ÷ Δt PER SAMPLING INTERVAL  [tok/s] — instantaneous rate, not the run average shown in the KPI tiles",
    "output tok/s": "Δsglang_generation_tokens_total ÷ Δt PER SAMPLING INTERVAL  [tok/s] — instantaneous rate, not the run average shown in the KPI tiles",
    "evict rate": "Δsglang_evicted_tokens_total ÷ Δt  [tok/s]",
    "load back rate": "Δsglang_load_back_tokens_total ÷ Δt  [tok/s]",
    "prefetch rate": "Δsglang_prefetched_tokens_total ÷ Δt  [tok/s]",
    "backup rate": "Δsglang_backuped_tokens_total ÷ Δt  [tok/s]",
    "prefill compute rate": "Δsglang_realtime_tokens_total"
                            "{mode=\"prefill_compute\"} ÷ Δt  [tok/s]",
    "prefill cache hit rate": "Δsglang_realtime_tokens_total"
                              "{mode=\"prefill_cache\"} ÷ Δt  [tok/s]",
    "decode rate": "Δsglang_realtime_tokens_total{mode=\"decode\"} ÷ Δt  [tok/s]",
    "running requests": "sglang_num_running_reqs  [reqs]",
    "queued requests": "sglang_num_queue_reqs  [reqs]",
    # Tier signals — keyed with the tier so the same word means one thing
    "e2e request latency": "\u0394sglang_e2e_request_latency_seconds_bucket \u2014 whole-window histogram quantile  [ms]",
    "itl inter token latency": "\u0394sglang_inter_token_latency_seconds_bucket \u2014 whole-window histogram quantile  [ms/tok]",
    "tpot time per output token": "\u0394sglang_time_per_output_token_seconds_bucket (or inter_token_latency) \u2014 whole-window histogram quantile  [ms/tok]",
    "input tokens / request": "\u0394sglang_prompt_tokens_histogram_bucket \u2014 whole-window histogram quantile  [tokens]",
    "output tokens / request": "\u0394sglang_generation_tokens_histogram_bucket \u2014 whole-window histogram quantile  [tokens]",
    "queue depth distribution": "per-layer queue vs its saturation reference  [%]",
    "queue occupancy across layers": "each layer queue \u00f7 its saturation reference  [%]",
    "hbm composition per gpu": "measured HBM split into weights / KV pool / occupied KV / residual  [GB per GPU]",
    "e2e latency": "Δsglang_e2e_request_latency_seconds_sum ÷ "
                   "Δsglang_e2e_request_latency_seconds_count × 1000  [ms]  "
                   "(per sampling interval; intervals with Δcount = 0 dropped)",
    "net total bw": "(rx_bytes + tx_bytes) \u00f7 \u0394t \u00f7 1e6 · network_timeseries.csv (iface=_total) \u2190 /proc/net/dev + IB port counters  [MB/s]",
    "net rx bw": "\u0394rx_bytes \u00f7 \u0394t \u00f7 1e6 · network_timeseries.csv  [MB/s]",
    "net tx bw": "\u0394tx_bytes \u00f7 \u0394t \u00f7 1e6 · network_timeseries.csv  [MB/s]",
    "net packets/s": "(\u0394rx_packets + \u0394tx_packets) \u00f7 \u0394t · network_timeseries.csv  [pkt/s]",
    "net link util": "(rx+tx bits \u00f7 \u0394t) \u00f7 (/sys/class/net/<if>/speed \u00d7 1e6) \u00d7 100  [%]",
    "net tcp retrans/s": "\u0394Tcp.RetransSegs \u00f7 \u0394t · /proc/net/snmp  [seg/s]",
    "net rx+tx drops/s": "(\u0394rx_drop + \u0394tx_drop) \u00f7 \u0394t · /proc/net/dev  [pkt/s]",
    "l1 gpu util": "gpu_util · gpu_timeseries.csv ← nvidia-smi utilization.gpu  [%]",
    "hbm bw util": "DCGM_FI_PROF_DRAM_ACTIVE \u00d7 100 (or nvidia-smi "
                   "utilization.memory) · gpu_timeseries.csv — percent of the "
                   "interval the HBM interface was active  [%]",
    "l1 hbm bw util": "DCGM_FI_PROF_DRAM_ACTIVE \u00d7 100 (or nvidia-smi "
                      "utilization.memory) · gpu_timeseries.csv  [%]",
    "hbm bw": "HBM active fraction \u00d7 device HBM peak GB/s  [GB/s]  "
              "(activity from DCGM_FI_PROF_DRAM_ACTIVE, else "
              "DCGM_FI_DEV_MEM_COPY_UTIL, else nvidia-smi utilization.memory; "
              "peak from GPU model — axis stays in % if the model is unknown)",
    "l1 hbm bw": "HBM active fraction \u00d7 device HBM peak GB/s  [GB/s]",
    "l1 hbm used": "Σ mem_used[i] ÷ 1024 · gpu_timeseries.csv  [GB]",
    "l2 dram bw": "dram_total_gb_s · amduprof_pcm_timeseries.csv  [GB/s]",
    "l2 dram bw (kv movement est.)": "estimated L2 DRAM traffic derived from KV movement counters when a DRAM PMU counter is not available  [GB/s]",
    "l2 dram read bw": "dram_read_gb_s · amduprof_pcm_timeseries.csv  [GB/s]",
    "l2 dram write bw": "dram_write_gb_s · amduprof_pcm_timeseries.csv  [GB/s]",
    # This tile is derived from SGLang HiCache token counters, NOT from
    # /proc/meminfo.  Prior text implied a raw physical measurement, which
    # is what the sibling "L2 DRAM used (raw)" tile actually is; the two
    # numbers can and do diverge substantially when KV bytes/token is
    # over-estimated (sliding-window attention models, TP-sharding).
    "l2 dram used": "sglang_hicache_host_used_tokens × KV_bytes_per_token ÷ 1024³  [GB]  · sglang_timeseries.csv · token-derived residency — an ESTIMATE, not a physical /proc/meminfo measurement",
    "l2 kv residency (est )": "sglang_hicache_host_used_tokens × KV_bytes_per_token ÷ 1024³  [GB]  · sglang_timeseries.csv · token-derived residency — an ESTIMATE bounded above by raw physical DRAM (see 'Host DRAM used (physical)')",
    "host dram used (physical)": "(MemTotal − MemFree − Buffers − Cached) ÷ 1024³  [GB]  · /proc/meminfo · dram_summary.json + dram_timeseries.csv · whole-node residency (weights + page cache + KV + everything else)",
    "l2 dram used (raw)": "(MemTotal − MemFree − Buffers − Cached) ÷ 1024³  [GB]  · /proc/meminfo · dram_summary.json + dram_timeseries.csv · whole-node residency (weights + page cache + KV + everything else)",
    "l2 dram residency": "resident L2 KV bytes ÷ configured HiCache size  [GB / GB]",
    # ---- L3.5 (Mooncake / remote KV store) ----
    # normalise_label() strips the dot, so "L3.5 · x" becomes "l3 5 x";
    # keys below must use that form or they can never match.
    #
    # The Mooncake *master* exporter is a metadata service: capacity,
    # occupancy, request rates.  It has NO byte-throughput counters -- data
    # moves client<->store over RDMA and never reaches the master -- so
    # read/write bandwidth needs a store/transfer-engine exporter as well.
    # ---- L2 derived from SGLang hicache counters (no PMU required) ----
    "l2 hicache used": "sglang_hicache_host_used_tokens × KV bytes/token ÷ 1024²  [GB] — measured L2 occupancy, independent of any DRAM PMU",
    "l2 hicache fill": "sglang_hicache_host_used_tokens ÷ sglang_hicache_host_total_tokens × 100  [%]",
    "l2 l1->l2 evict bw": "Δsglang_evicted_tokens_total ÷ Δt × KV bytes/token ÷ 1024  [MB/s] — DERIVED from token movement, not a DRAM controller counter",
    "l2 l2->l1 restore bw": "Δsglang_load_back_tokens_total ÷ Δt × KV bytes/token ÷ 1024  [MB/s] — DERIVED from token movement",
    # Per-interval rate, NOT the run average the End Report tiles show.
    # Both are correct and they differ by the duty cycle: on a window that is
    # mostly idle the run average reads far lower, because idle intervals are
    # averaged in.  Correlation needs the per-interval rate — a run average
    # is a single number and cannot be plotted against anything.
    "input throughput tok/s per interval":
        "Δsglang_prompt_tokens_total ÷ Δt per sampling interval  [tok/s] · the End Report tile is Δtokens ÷ Δt over the WHOLE window, which includes idle time and reads lower",
    "output throughput tok/s per interval":
        "Δsglang_generation_tokens_total ÷ Δt per sampling interval  [tok/s] · the End Report tile averages over the whole window instead",
    # ---- Per-tier KV utilization tiles (Executive) ----
    # One tile per tier, all as "% of that tier's own ceiling". The four are NOT
    # equally direct and the formulas say so: L1/L2 are SGLang's own counters,
    # L3 is a df snapshot or a movement-derived estimate, L3.5 is store bytes.
    "l1 kv utilization":
        "sglang_kv_used_tokens (else sglang_token_usage × pool size) ÷ "
        "sglang_max_total_num_tokens × 100  [%] — mean over active samples",
    "l2 kv utilization":
        "sglang_hicache_host_used_tokens ÷ sglang_hicache_host_total_tokens "
        "× 100  [%] — mean over active samples",
    "l3 kv utilization":
        "hicache_fs_used_gb ÷ hicache_fs_total_gb × 100  [%] (df snapshot, "
        "measured) — else DERIVED (Δbackuped − Δprefetched tokens) ÷ "
        "(l3_fs_total_gb ÷ KV bytes/token) × 100; the tile note states which",
    "l3 5 store used": "master_allocated_bytes ÷ 1e9  [GB]",
    "l3 5 fill ratio": "master_allocated_bytes ÷ master_total_capacity_bytes × 100  [%]",
    # The tile resolves the denominator in priority order, so the formula names
    # every candidate: the store's own ratio first, then aggregate, segment
    # (DRAM pool) and file (flash) byte pairs. kv_l35_fill_source in
    # common_kpis.json records which one actually produced the number — without
    # it the percentage cannot be interpreted, since the four denominators mean
    # different things. Mean excludes idle samples; an all-sample mean over a
    # run that starts with an empty store reads near zero for a half-full tier.
    "l3 5 kv utilization":
        "mooncake_fill_ratio, else mooncake_used_bytes ÷ mooncake_capacity_bytes, "
        "else segment_, else file_ pair × 100  [%] — mean over active samples · "
        "see kv_l35_fill_source in common_kpis.json for the denominator used",
    "l3 5 put ops/s": "Δmaster_put_end_requests_total ÷ Δt  [ops/s]",
    "l3 5 read bw (mb/s)": "Δ(mem_cache_hit_bytes_total + file_cache_hit_bytes_total) ÷ Δt ÷ 1e6  [MB/s]",
    "l3 5 errors/s": "Δ(master_put_end_failures_total + master_get_replica_list_failures_total) ÷ Δt  [ops/s]",
    "l3 5 keys stored": "master_key_count  [keys]",
    "l3 5 active clients": "master_active_clients  [clients]",
    "l3 5 read bw": "Δmooncake_read_bytes_total ÷ Δt ÷ 1e6  [MB/s] (store exporter)",
    "l3 5 write bw": "Δmooncake_write_bytes_total ÷ Δt ÷ 1e6  [MB/s] (store exporter)",
    "l3 5 get lat": "Δmooncake_get_duration_seconds_sum ÷ Δ..._count × 1000  [ms]",
    "l3 5 put lat": "Δmooncake_put_duration_seconds_sum ÷ Δ..._count × 1000  [ms]",
    "l3 read bw": "rd_bw_mbs · nvme_driver_timeseries.csv  [MB/s]",
    "l3 write bw": "wr_bw_mbs · nvme_driver_timeseries.csv  [MB/s]",
    "l3 read iops": "rd_iops · nvme_driver_timeseries.csv  [IO/s]",
    "l3 write iops": "wr_iops · nvme_driver_timeseries.csv  [IO/s]",
    "l3 read lat": "rd_lat_ms · nvme_driver_timeseries.csv  [ms]",
    "l3 write lat": "wr_lat_ms · nvme_driver_timeseries.csv  [ms]",
    "l3 r+w lat": "await · nvme_driver_timeseries.csv  [ms]",
    "l3 queue depth": "qd_best_effort · queue_depth_sources_timeseries.csv "
                      "(→ qd → weighted_qd → inflight)",

    # Bare axis labels used by the per-tier throughput cards, where the tier
    # is already stated in the card title rather than in the axis label.
    "hbm used": "Σ mem_used[i] ÷ 1024 · gpu_timeseries.csv  [GB]",
    "read bw": "rd_bw_mbs · nvme_driver_timeseries.csv  [MB/s]",
    "write bw": "wr_bw_mbs · nvme_driver_timeseries.csv  [MB/s]",

    "block lifetime": "mean(evict_time − admit_time) per KV block  [s]",
    "rd b/output tok": "Σ blktrace read size_bytes ÷ "
                       "Δsglang_generation_tokens_total  [B/tok]",
    "wr b/input tok": "Σ blktrace write size_bytes ÷ "
                      "Δsglang_prompt_tokens_total  [B/tok]",
    "l3 rd/output tok": "Σ blktrace read size_bytes ÷ "
                        "Δsglang_generation_tokens_total  [B/tok]",
    "l3 wr/input tok": "Σ blktrace write size_bytes ÷ "
                       "Δsglang_prompt_tokens_total  [B/tok]",

    # ── Access pattern / blktrace statistics ──────────────────────────────
    "sequential / random": "count(LBA[i] == LBA[i−1] + size[i−1]) ÷ count(IOs) "
                           "× 100  [% sequential]  · blktrace",
    "skewness": "skewness_bytes from access_skew · blktrace "
                "(3rd standardised moment of per-LBA-region byte counts)",
    "rd gini": "gini_bytes from access_skew · blktrace  "
               "= Σᵢⱼ|xᵢ−xⱼ| ÷ (2n²x̄) over per-region read byte counts "
               "(0 = uniform, 1 = single region)",
    "rd top 1% share": "top_1pct_byte_share from access_skew · blktrace  "
                       "= bytes in hottest 1% of LBA regions ÷ total read bytes "
                       "× 100  [%]",
    "wr top 1% share": "top_1pct_byte_share (write) from access_skew · blktrace "
                       "× 100  [%]",
    "rd hot regions": "count(LBA regions with byte share above hot threshold) "
                      "· blktrace",
    "wr hot regions": "count(LBA regions with byte share above hot threshold) "
                      "· blktrace",
    "bursts": "count of runs where inter-arrival gap < burst threshold; "
              "mean = Σ size_bytes in run ÷ burst_count  · blktrace",
    "bw degrad.": "bw_degradation = mean(BW over last third of run) ÷ "
                  "mean(BW over first third)  [×]  (1.0 = no degradation)",
    "rd degrad.": "mean(read BW, last third) ÷ mean(read BW, first third)  [×]",
    "wr degrad.": "mean(write BW, last third) ÷ mean(write BW, first third)  [×]",
    "rd streams": "count(distinct sequential LBA streams) · blktrace",
    "wr streams": "count(distinct sequential LBA streams) · blktrace",
    "rd period": "dominant period of read BW series via autocorrelation  [s]",
    "wr period": "dominant period of write BW series via autocorrelation  [s]",
    "seasonal period": "argmax(autocorrelation(read BW series)) × "
                       "mean sample interval  [s]",
    "r<->w lag": "argmax(cross-correlation(read BW, write BW)) × "
                 "mean sample interval  [s]",
    "r/w ratio": "Σ read size_bytes ÷ Σ write size_bytes  · blktrace",
    "r/w corr": "Pearson r(read BW series, write BW series)",
    "offload<->wr corr": "Pearson r(Δsglang_evicted_tokens_total ÷ Δt, "
                         "wr_bw_mbs)",
    "onboard<->rd corr": "Pearson r(Δsglang_prefetched_tokens_total ÷ Δt, "
                         "rd_bw_mbs)",
    "trim present": "any(blktrace action == discard)",
    "trim iops": "count(discard events) ÷ run_duration_s  [IO/s]",
    "trim bw": "Σ discard size_bytes ÷ run_duration_s ÷ 10⁶  [MB/s]",

    # ── Setup / capacity context (no arithmetic — name the source) ────────
    "model": "Model / Model path · setup_details.json",
    "l3 device": "L3 Device · setup_details.json (← --hicache-storage-backend "
                 "mount resolution)",
    "capacity context": "L3 capacity from statvfs(mount) · "
                        "L2 from HiCache size per GPU × GPU count",
    "bench requests": "count(requests) · benchmark result JSON",
    "avg prompt": "mean(prompt_tokens) · benchmark result JSON  [tok]",
    "avg output": "mean(output_tokens) · benchmark result JSON  [tok]",
    "bench ttft": "mean(ttft_ms) · benchmark result JSON  [ms]",
    "bench itl": "mean(itl_ms) · benchmark result JSON  [ms]",
}

FORMULAS: Dict[str, str] = {normalise_label(k): v for k, v in _RAW.items()}


# Run-dependent variants.  A tile whose provenance changes with what the run
# actually exported (e.g. TTFT from Δsum/Δcount vs histogram vs summary JSON)
# passes the resolved variant name; the strings still live only here.
VARIANTS: Dict[str, Dict[str, str]] = {
    "ttft": {
        "delta": FORMULAS["ttft"],
        "histogram": "histogram_quantile(0.50, rate("
                     "sglang_time_to_first_token_seconds_bucket[W])) × 1000  [ms] "
                     "· P50 fallback when Δsum/Δcount unavailable",
        "summary": "server_ttft_ms · sglang_summary.json",
    },
    "tpot": {
        "delta": FORMULAS["tpot"],
        "histogram": "histogram_quantile(0.50, rate("
                     "sglang_inter_token_latency_seconds_bucket[W])) × 1000  [ms] "
                     "· P50 ITL fallback",
        "summary": "server_itl_ms · sglang_summary.json (mean over run)",
    },
}


def formula_for(label: str, variant: str = "") -> str:
    """Return the registry formula for a tile label, or "" if unknown."""
    key = normalise_label(label)
    if variant and key in VARIANTS:
        return VARIANTS[key].get(variant, FORMULAS.get(key, ""))
    return FORMULAS.get(key, "")


_VALUE_RE = re.compile(r"\d")


_STAT_RE = re.compile(
    r"\b(p\d{1,2}|min|max|mean|median|avg|peak|total|count|hit|full|ratio)\b", re.I)
_UNIT_RE = re.compile(
    r"\d\s*[kmgtµu]?\s*(?:[kmgtp]?i?b(?:/s)?|[munp]?s\b|ms\b|%|tok|txns?|iops?|w\b|×|x\b|"
    r"gb/s|mb/s|kb/s|req/s|gpu)", re.I)


def _is_measured_value(fragment: str) -> bool:
    """True when a note fragment carries a measurement worth keeping.

    Distinguishes "P90=1.4s", "312 M txns/s" and "of 409 GB/s peak" (keep —
    the tile is the only place those appear) from numeric *legends* like
    "1.0=no degradation" or "0=uniform, 1=all one region", which are
    explanatory text that the formula replaces even though they contain
    digits.
    """
    if not _VALUE_RE.search(fragment):
        return False
    return bool(_STAT_RE.search(fragment) or _UNIT_RE.search(fragment))


def tile_note(label: str, existing_note: str = "", variant: str = "") -> str:
    """Formula text for a tile, replacing explanatory prose in `existing_note`.

    Measured values in the original note are preserved: any `·`-separated
    fragment that looks like a measurement is kept and appended after the
    formula, so e.g. "P90=1.4s  Max=3.2s" survives while "time-weighted
    average" and "1.0=no degradation" do not.  Labels absent from the
    registry return `existing_note` unchanged, which is what makes wiring
    this in non-breaking.
    """
    formula = formula_for(label, variant)
    if not formula:
        return existing_note
    kept = [frag.strip() for frag in re.split(r"\s*·\s*", str(existing_note or ""))
            if frag.strip() and _is_measured_value(frag)]
    return formula + ("  ·  " + "  ·  ".join(kept) if kept else "")


_AXIS_UNIT_RE = re.compile(r"\s*\([^)]*\)\s*$")


def axis_formula(axis_label: str) -> str:
    """Formula for a correlation-chart axis label.

    Chart axes carry a trailing unit or qualifier in parentheses that tile
    labels do not — ``"L3 · read BW (MB/s)"``, ``"Evict rate (tok/s)"``,
    ``"Queued requests (prefill backlog)"``.  Strip that suffix, then use the
    normal registry lookup.  The tier prefix is deliberately kept, because
    "read BW" means a different column at L2 than at L3.
    """
    # Try the FULL label first.  Stripping the parenthesised suffix reduces
    # "Input throughput (tok/s, per-interval)" to "input throughput", which
    # matches the run-average entry — the opposite statistic, and exactly the
    # mismatch that made the chart caption contradict its own axis.  A
    # qualifier inside the parentheses is meaning, not decoration.
    _full = formula_for(axis_label)
    if _full:
        return _full
    label = _AXIS_UNIT_RE.sub("", str(axis_label or ""))
    return formula_for(label)


def metric_formula_rows() -> list[tuple[str, str]]:
    """(label, formula) pairs for the End Report §Metrics & Formulas table.

    Generated from the registry so that table and the tiles cannot disagree.
    """
    seen: set[str] = set()
    rows: list[tuple[str, str]] = []
    for label, formula in _RAW.items():
        if formula in seen:
            continue
        seen.add(formula)
        rows.append((label, formula))
    return rows


# ---------------------------------------------------------------------------
# Collapsible formula rendering
# ---------------------------------------------------------------------------

FORMULA_CSS = """
.fx{display:inline-block;margin-top:3px;max-width:100%}
.fx>summary{cursor:pointer;list-style:none;display:inline-flex;align-items:center;
  gap:4px;font-size:9px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;
  color:#64748b;border:1px solid currentColor;border-radius:999px;padding:0 6px;
  line-height:14px;opacity:.75;user-select:none}
.fx>summary::-webkit-details-marker{display:none}
.fx>summary:hover{opacity:1}
.fx[open]>summary{opacity:1;margin-bottom:3px}
.fx .fx-body{font-size:10px;line-height:1.5;color:#94a3b8;white-space:normal;
  overflow-wrap:anywhere;word-break:break-word;border-left:2px solid #334155;
  padding-left:6px;margin-top:2px}
"""

# The End Report renders on a light background; the same class needs a
# readable colour there rather than the dark-theme slate.
FORMULA_CSS_LIGHT = """
.fx>summary{color:#64748b}
.fx .fx-body{color:#475569;border-left-color:#cbd5e1}
"""


def formula_details(body: str, label: str = "formula", open_: bool = False) -> str:
    """Wrap a formula/provenance string in a collapsed disclosure.

    Formulas are what make a number auditable, but printed in full under every
    tile and chart they crowd out the value itself.  Collapsed by default,
    one click to read, and still present in the DOM so Ctrl-F and the report
    validators continue to find them.
    """
    body = (body or "").strip()
    if not body:
        return ""
    import html as _h
    return (f'<details class="fx"{" open" if open_ else ""}>'
            f'<summary>{_h.escape(label)}</summary>'
            f'<div class="fx-body">{body}</div></details>')
