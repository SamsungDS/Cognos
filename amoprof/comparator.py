"""
amoprof/comparator.py — Compare metrics across multiple run directories.

Each run can have:
  • Its own local raw/ directory
  • Its own Prometheus time window (start/end)
  • A short human-readable label

The comparison report is a single self-contained HTML file with:
  1. Summary table    — all KPIs side-by-side, delta % vs the baseline
  2. Bar charts       — Plotly grouped bars for every metric family
  3. Radar chart      — normalised 0-100 score per metric for each run
  4. Bottleneck table — per-layer score for each run
  5. Recommendations  — which run is "better" per metric and why

Usage (module):
    from amoprof.comparator import compare_runs
    compare_runs(runs=[...], out_html=Path("comparison.html"))

Usage (CLI):
    amoprof compare \
      --run "Baseline:./run_c1:1778871540:1778877078" \
      --run "Optimised:./run_c4:1778881540:1778887078" \
      --output-dir ./comparison
"""
from __future__ import annotations

import csv
import html as _html
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("amoprof.comparator")


# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class RunSpec:
    """Specification for one run to compare."""
    label: str
    raw_dir: Path
    t_start: float = 0.0
    t_end:   float = 0.0
    # Explicit setup_details.json for this run, overriding whatever sits in
    # raw_dir.  A run fetched straight from Prometheus has no setup file of
    # its own, and two runs being compared usually have different ones, so the
    # setup cannot be taken from the directory alone.
    setup_details_path: "Path | None" = None


@dataclass
class RunMetrics:
    """Key scalar metrics extracted from one run."""
    label: str
    # Latency / throughput
    ttft_ms:          float = 0.0
    tpot_ms:          float = 0.0
    e2e_ms:           float = 0.0
    throughput_tok_s: float = 0.0
    cache_hit_pct:    float = 0.0
    cache_hit_tw_pct: float = 0.0
    # GPU / HBM
    gpu_util_pct:     float = 0.0
    gpu_util_peak:    float = 0.0
    hbm_used_gb:      float = 0.0
    hbm_pct:          float = 0.0
    gpu_power_w:      float = 0.0
    dcgm_active_pct:  float = 0.0
    # NVMe
    nvme_rd_bw_mbs:   float = 0.0
    nvme_wr_bw_mbs:   float = 0.0
    nvme_rd_iops:     float = 0.0
    nvme_util_pct:    float = 0.0
    nvme_rd_lat_ms:   float = 0.0
    nvme_wr_lat_ms:   float = 0.0
    read_total_gb:    float = 0.0
    write_total_gb:   float = 0.0
    # DRAM
    dram_total_bw_gbs: float = 0.0
    dram_rd_bw_gbs:    float = 0.0
    dram_wr_bw_gbs:    float = 0.0
    dram_peak_bw_gbs:  float = 0.0
    # Context info
    model:    str = ""
    runtime:  str = ""
    gpu_desc: str = ""
    tp_size:  str = ""
    context:  str = ""
    hicache:  str = ""
    duration_min: float = 0.0
    window_str: str = ""
    # Raw sources available
    has_blktrace: bool = False
    has_dram:     bool = False
    has_gpu:      bool = False
    raw_dir:      str  = ""   # for display in the comparison table
    # ── KV movement inside the AI memory node ────────────────────────────
    # These carry the tiering story: a tier that evicts far more than it
    # serves is thrashing, and one that never promotes is a sink rather than
    # a cache.  None means the counter was absent; 0.0 means it was present
    # and never incremented — a different finding, rendered differently.
    evicted_gb:       "float | None" = None
    promoted_gb:      "float | None" = None
    mem_hit_gb:       "float | None" = None
    file_hit_gb:      "float | None" = None
    prefetched_tok:   "float | None" = None
    cached_tok:       "float | None" = None
    # Capacity of each tier of the backing store, in GB.  None means no
    # capacity was found for that tier: the chain omits the row rather than
    # printing 0.0, which reads as a measured zero-capacity tier.
    l35_dram_gb:      "float | None" = None
    l35_file_gb:      "float | None" = None
    l35_cap_source:   str = ""
    window_s:         float = 0.0
    # ── Backing tier identity ────────────────────────────────────────────
    # Resolved per run from that run's own setup, so a local-SSD L3 run and
    # an L3.5 memory-node run can appear in one comparison without either
    # being described as the other.  "" means no setup was available: the
    # tier is then stated as unknown rather than defaulted to either value.
    l3_backend_class: str = ""
    tier_name:        str = ""     # full display name, e.g. "L3.5 (AI Memory Node …)"
    tier_short:       str = ""     # "L3" | "L3.5" | "" — for row labels
    tier_evidence:    str = ""
    # ── A5 · application / inference engine token activity ───────────────
    prompt_tok:       "float | None" = None
    gen_tok:          "float | None" = None
    # ── KV movement through the hierarchy (engine-side counters) ─────────
    # One hop per field, named by the hop rather than by the counter, so a
    # reader can follow a token down the stack:
    #   evict    L1 -> L2      backup    L2 -> L3/L3.5
    #   prefetch L3/L3.5 -> L2 load_back L2 -> L1
    evicted_tok:      "float | None" = None
    backuped_tok:     "float | None" = None
    load_back_tok:    "float | None" = None
    # ── store-side request counts (the backing store's own view) ─────────
    store_get_n:      "float | None" = None
    store_mem_hit_n:  "float | None" = None
    store_file_hit_n: "float | None" = None
    # ── KV geometry, for turning token counts into bytes ─────────────────
    # From this run's own raw/model_config.json, which --model-path writes.
    # None when the architecture could not be resolved: a KV total is the
    # denominator of every per-token byte figure, so a default would be worse
    # than an absence.
    # How each latency was resolved, and whether it is window-scoped. A
    # figure from the summary may be a lifetime average, and a delta between
    # two lifetime averages is not a comparison of two windows.
    latency_method:   dict = field(default_factory=dict)
    latency_window_scoped: dict = field(default_factory=dict)
    # Which statistic the resolved figure actually IS. The resolution order
    # mixes means (steps 1 and 3) with a median (step 2), so a column headed
    # "mean" is only a mean while step 1 or 3 answered; on these runs the two
    # differ by two orders of magnitude.
    latency_statistic: dict = field(default_factory=dict)
    # The column and file each latency was differenced from, and how many
    # observations completed in the window — a mean over four requests is not
    # comparable to one over six thousand, and nothing else on the row says so.
    latency_source:   dict = field(default_factory=dict)
    latency_obs:      dict = field(default_factory=dict)
    # Where a token counter came from when the named total was not exported
    # and the realtime phase counters answered instead.
    token_src:        dict = field(default_factory=dict)

    # ── How much of the window was alive ─────────────────────────────────
    # A window mean is a property of the system only when the window is a
    # property of the workload. Two runs compared over 1,800 s and 2,925 s
    # had every time-average favour the shorter one, and all of them
    # reversed once the longer window's dead tail was removed.
    active_frac:      "float | None" = None
    active_span_s:    "float | None" = None
    lead_idle_s:      "float | None" = None
    trail_idle_s:     "float | None" = None
    active_src:       str = ""
    active_method:    str = ""

    # ── Latency percentiles, so a mean can be read against its own median ─
    lat_pct_ms:       dict = field(default_factory=dict)   # (kind, q) -> ms
    lat_pct_src:      dict = field(default_factory=dict)
    lat_bucket_note:  dict = field(default_factory=dict)   # kind -> caveat

    # ── L1 HBM KV pool, which total HBM used conceals ────────────────────
    # The weights dominate HBM, so "HBM used" was 265.0 against 265.1 GB on
    # two runs whose KV pools differed by 1.57x. The pool is its own figure.
    l1_kv_tok_mean:   "float | None" = None
    l1_kv_tok_peak:   "float | None" = None
    l1_kv_cap_tok:    "float | None" = None
    l1_kv_src:        str = ""

    # ── Device load against what the device can do ───────────────────────
    dev_rd_target_mbs: "float | None" = None
    dev_wr_target_mbs: "float | None" = None
    dev_target_src:   str = ""

    kv_bytes_tok_kb:  "float | None" = None
    kv_bytes_src:     str = ""
    kv_bytes_exact:   bool = False
    tp_size_n:        "float | None" = None

    # ── Queue depth and pressure, per layer ──────────────────────────────
    #
    # One field per LAYER, and never one field standing in for several.
    # nvme_qd_mean/peak below read the first of avgqu_sz / l35_avgqu_sz /
    # bt_qd_mean that returned anything, so a local-SSD run and an L3.5 run
    # were compared on one row whose two cells measured different devices on
    # different hosts. Nothing in the row said so.
    #
    # Split by where the queue IS, and record which column each came from, so
    # a cell can be attributed:
    sg_queue_reqs_mean: "float | None" = None   # A5 scheduler waiting queue
    sg_queue_reqs_peak: "float | None" = None
    sg_running_reqs_mean: "float | None" = None  # A5 concurrent decode batch
    sg_running_reqs_peak: "float | None" = None
    l3_qd_mean:       "float | None" = None     # this host's block device
    l3_qd_peak:       "float | None" = None
    l3_qd_src:        str = ""
    l35_qd_mean:      "float | None" = None     # the memory node's device
    l35_qd_peak:      "float | None" = None
    l35_qd_src:       str = ""
    bt_qd_mean:       "float | None" = None     # exact blktrace Q→C
    bt_qd_peak:       "float | None" = None
    bt_qd_source:     str = ""
    # NO queue is exposed for these two layers. They are PROXIES and are
    # labelled as such wherever they are rendered; calling a %-of-peak a
    # queue depth is the error this split exists to prevent.
    net_retrans_ps_mean: "float | None" = None
    net_retrans_ps_peak: "float | None" = None
    net_rx_drop_ps_mean: "float | None" = None
    net_link_util_pct_mean: "float | None" = None
    net_link_util_pct_peak: "float | None" = None
    dram_bw_pct_of_peak: "float | None" = None
    dram_peak_ref_gbs: "float | None" = None   # the PLATFORM peak, from setup

    # ── A2 · block / driver ──────────────────────────────────────────────
    nvme_qd_mean:     "float | None" = None
    nvme_qd_peak:     "float | None" = None
    # ── A1 · device ──────────────────────────────────────────────────────
    nand_written_gb:  "float | None" = None
    host_written_gb:  "float | None" = None

    # ── The workload, and how long it took to serve ──────────────────────
    # Two runs of the same request set are compared fairly by how long each
    # took to finish it. Window means cannot say that: on the reference pair
    # the same ~5,900 requests took 50 min on one tier and 30 on the other,
    # and the active-span throughput still ranked the slower run first.
    requests_n: "float | None" = None
    requests_src: str = ""
    queue_wait_ms: "float | None" = None

    # ── Idle with work waiting, against idle with nothing to do ──────────
    # From metric_kernels.admission_stalls over GPU utilisation, the
    # scheduler's waiting queue, the decode batch and the L1 KV fill. With
    # stall_present False the series to classify the idle time were not
    # there, which is a different statement from "no stall".
    stall_present: bool = False
    busy_s: "float | None" = None
    stall_s: "float | None" = None
    no_work_s: "float | None" = None
    other_idle_s: "float | None" = None
    stall_episodes: list = field(default_factory=list)
    stall_method: str = ""
    stall_src: str = ""
    # Mean GPU utilisation x the GPU series' span: GPU-time actually spent.
    # Two runs that needed the same GPU-time but took different wall time
    # lost the difference to idling, not to compute.
    gpu_busy_equiv_s: "float | None" = None
    # When the backing tier last delivered anything, and how long it was
    # silent after that. A tier that stops serving reads part-way through a
    # run leaves every later miss to recompute or to wait.
    prefetch_last_move_s: "float | None" = None
    prefetch_quiet_tail_s: "float | None" = None
    # Aligned, downsampled series for the timeline chart:
    # {"t": [...], "gpu": [...], "waiting": [...], "running": [...]}
    timeline: dict = field(default_factory=dict)
    # Pearson r between the aligned timelines: {"names": [...], "r": [[...]]},
    # None in a cell whose pair is undefined (a constant series).
    corr: dict = field(default_factory=dict)

    # ── HiCache configuration that changes what a tier costs ─────────────
    page_size: "float | None" = None
    page_size_src: str = ""
    storage_backend: str = ""   # what the engine reported running
    launch_backend: str = ""    # what the recorded launch command asks for

    # ── derived ──────────────────────────────────────────────────────────
    @property
    def total_hit_gb(self) -> float:
        return (self.mem_hit_gb or 0.0) + (self.file_hit_gb or 0.0)

    @property
    def read_back_pct(self) -> "float | None":
        """Bytes read back from the tier as a share of bytes written to it.

        The question "is this tier a cache or a sink". On the reference runs
        the local-SSD tier absorbed 747 GB and returned 3.8 GB -- 0.51% --
        and the remote tier was the same shape. A tier that is not serving
        reads cannot be where read latency is being saved, whatever its
        media, and nothing else in this report says so: the read and write
        totals sat in separate rows and the ratio was left to the reader.
        """
        if not self.write_total_gb or self.read_total_gb is None:
            return None
        return self.read_total_gb / self.write_total_gb * 100.0

    @property
    def rd_headroom_pct(self) -> "float | None":
        """Measured read bandwidth as a share of the device's read target."""
        if not self.dev_rd_target_mbs or not self.nvme_rd_bw_mbs:
            return None
        return self.nvme_rd_bw_mbs / self.dev_rd_target_mbs * 100.0

    @property
    def wr_headroom_pct(self) -> "float | None":
        if not self.dev_wr_target_mbs or not self.nvme_wr_bw_mbs:
            return None
        return self.nvme_wr_bw_mbs / self.dev_wr_target_mbs * 100.0

    @property
    def active_output_tok_s(self) -> "float | None":
        """Output throughput over the ACTIVE span rather than the window.

        The window average is what the engine sustained including dead time;
        this is what it sustained while working. Both are reported, because
        which one answers the question depends on whether the window was
        bounded by the workload -- and when they differ the reader needs to
        see that they do.
        """
        if not self.throughput_tok_s or not self.active_frac:
            return None
        if self.active_frac <= 0 or self.active_frac > 1.0:
            return None
        return self.throughput_tok_s / self.active_frac

    def tail_ratio_for(self, kind: str) -> "float | None":
        """Mean ÷ its own p50. A mean far above it is queue wait, not service."""
        _mean = {"ttft": self.ttft_ms, "tpot": self.tpot_ms,
                 "e2e": self.e2e_ms}.get(kind) or 0.0
        _p50 = (self.lat_pct_ms or {}).get((kind, 0.5)) or 0.0
        if _mean <= 0 or _p50 <= 0:
            return None
        return _mean / _p50

    @property
    def evict_read_ratio(self) -> "float | None":
        """Evicted bytes per byte served. >1.0 means the tier is thrashing."""
        t = self.total_hit_gb
        if self.evicted_gb is None or t <= 0:
            return None
        return self.evicted_gb / t

    @property
    def file_read_share_pct(self) -> "float | None":
        t = self.total_hit_gb
        if self.file_hit_gb is None or t <= 0:
            return None
        return self.file_hit_gb / t * 100.0

    @property
    def recomputed_tok(self) -> "float | None":
        """Prefill tokens the GPU had to regenerate because they were not cached."""
        if self.cached_tok is None or self.cache_hit_pct <= 0:
            return None
        total = self.cached_tok / (self.cache_hit_pct / 100.0)
        return max(0.0, total - self.cached_tok)

    @property
    def kv_generated_tok(self) -> "float | None":
        """Tokens whose KV the GPUs actually computed in this window.

        prompt - cached + decode. A prefill token served from the prefix
        cache reuses KV that already existed; it does not generate any. With
        hit rates around 95% on these runs, counting all prompt tokens
        instead would overstate the total roughly twentyfold.

        Both terms are measured counters, so this does not inherit the
        hit-rate gauge's error the way recomputed_tok does -- the check row
        in the layer table shows how far the two routes disagree.
        """
        if self.prompt_tok is None or self.cached_tok is None:
            return None
        _dec = self.gen_tok or 0.0
        return max(0.0, self.prompt_tok - self.cached_tok) + _dec

    @property
    def kv_generated_gb(self) -> "float | None":
        """The same quantity in bytes, full-model across all ranks.

        Requires an EXACT geometry. The resolver falls back to a size hint
        from the model name, and on this model that hint gives 256 KB/token
        where the config gives 960 -- a 3.75x error. The byte figure is
        already an upper bound rather than bytes on a bus; built on a wrong
        constant it would be neither. Tokens are measured and always shown.
        """
        t = self.kv_generated_tok
        if t is None or not self.kv_bytes_tok_kb or not self.kv_bytes_exact:
            return None
        return t * self.kv_bytes_tok_kb / (1024 * 1024)

    @property
    def kv_demand_gb(self) -> "float | None":
        """What the run would have computed with no cache at all.

        Gated on kv_generated_gb, not just on prompt_tok: a counterfactual
        printed beside an actual that reads "not exported" offers a saving
        against nothing, which is how this row first rendered.
        """
        if self.kv_generated_gb is None or self.prompt_tok is None:
            return None
        t = self.prompt_tok + (self.gen_tok or 0.0)
        return t * self.kv_bytes_tok_kb / (1024 * 1024)

    @property
    def kv_avoided_gb(self) -> "float | None":
        """What the hierarchy saved: demand minus generated."""
        d, g = self.kv_demand_gb, self.kv_generated_gb
        return None if (d is None or g is None) else max(0.0, d - g)

    @property
    def recompute_rate_tok_s(self) -> "float | None":
        r = self.recomputed_tok
        if r is None or self.window_s <= 0:
            return None
        return r / self.window_s

    @property
    def evict_rate_gbs(self) -> "float | None":
        if self.evicted_gb is None or self.window_s <= 0:
            return None
        return self.evicted_gb / self.window_s

    @property
    def completion_s(self) -> "float | None":
        """How long the workload took: first to last busy sample.

        Lead and trailing idle are the window's, not the workload's, so they
        are excluded. Idle time BETWEEN busy samples is kept: when requests
        were waiting through it, it is the system's time, and a run that
        finished later finished later.
        """
        if self.active_span_s:
            return self.active_span_s
        if self.window_s > 0:
            return self.window_s
        return (self.duration_min * 60.0) or None

    @property
    def req_per_s(self) -> "float | None":
        c = self.completion_s
        if not self.requests_n or not c:
            return None
        return self.requests_n / c

    @property
    def recompute_measured_tok(self) -> "float | None":
        """Prefill tokens computed: prompt - cached, both measured counters.

        recomputed_tok derives the same quantity from the hit-rate gauge; this
        one inherits no gauge error, which matters when the point is that two
        runs did the same amount of prefill work.
        """
        if self.prompt_tok is None or self.cached_tok is None:
            return None
        return max(0.0, self.prompt_tok - self.cached_tok)

    @property
    def prefetch_rate_tok_s(self) -> "float | None":
        if self.prefetched_tok is None or self.window_s <= 0:
            return None
        return self.prefetched_tok / self.window_s

    @property
    def backup_rate_tok_s(self) -> "float | None":
        if self.backuped_tok is None or self.window_s <= 0:
            return None
        return self.backuped_tok / self.window_s

    @property
    def engine_read_back_pct(self) -> "float | None":
        """Tokens the tier gave back as a share of tokens it absorbed.

        The engine-side twin of read_back_pct, which needs a local block
        device. For a memory node this host's device is not the KV path, so
        only the engine's own counters can say whether the tier served reads.
        """
        if not self.backuped_tok or self.prefetched_tok is None:
            return None
        return self.prefetched_tok / self.backuped_tok * 100.0

    @property
    def idle_s(self) -> "float | None":
        if not self.stall_present:
            return None
        return ((self.stall_s or 0.0) + (self.no_work_s or 0.0)
                + (self.other_idle_s or 0.0))

    # KPI-table accessors: the table multiplies by a scale and drops rows that
    # are zero everywhere, so an absent figure is 0.0 there and nowhere else.
    @property
    def kpi_requests(self) -> float:
        return float(self.requests_n or 0.0)

    @property
    def kpi_completion_min(self) -> float:
        return (self.completion_s or 0.0) / 60.0

    @property
    def kpi_req_per_s(self) -> float:
        return float(self.req_per_s or 0.0)

    @property
    def kpi_running_mean(self) -> float:
        return float(self.sg_running_reqs_mean or 0.0)

    @property
    def kpi_prefetch_rate(self) -> float:
        return float(self.prefetch_rate_tok_s or 0.0)

    @property
    def kpi_queue_wait_s(self) -> float:
        return (self.queue_wait_ms or 0.0) / 1000.0



# Largest value that can be a real NVMe queue depth, the same bound the
# single-run report applies (amoprof/report/combined.py:_QD_PLAUSIBLE_MAX).
# A figure in the thousands is an unmatched-Q counting artifact, and a
# comparison that puts one in a cell invites a conclusion about a queue that
# was never that deep.
_QD_PLAUSIBLE_MAX = 4096.0


try:
    from .report.metric_kernels import (
        resolve_latency_ms as _k_resolve_lat,
        resolve_series_columns as _k_resolve_cols,
        counter_window_total as _k_counter_total,
        latency_window_ms as _k_latency_ms,
        active_window_fraction as _k_active_frac,
        bucket_edge_check as _k_bucket_edge,
        tail_ratio as _k_tail_ratio,
        align_on_time as _k_align,
        admission_stalls as _k_admission_stalls,
        pearson as _k_pearson,
    )
except Exception:  # pragma: no cover - the kernel ships with the package
    def _k_resolve_lat(kind, ts_ms=0.0, pct_ms=0.0, summary_ms=0.0,
                       summary_method=""):
        _v = ts_ms or pct_ms or summary_ms or 0.0
        return {"ms": float(_v), "step": 0, "window_scoped": bool(ts_ms),
                "method": "kernel unavailable"}

    def _k_resolve_cols(fieldnames, parts, exclude_buckets=True):
        _w = [str(p).lower() for p in (parts or [])]
        return [c for c in (fieldnames or [])
                if c and all(w in str(c).lower() for w in _w)]

    def _k_counter_total(series):
        return {"total": 0.0, "present": False, "columns": 0,
                "usable_columns": 0, "resets": 0, "samples": 0,
                "method": "kernel unavailable"}

    def _k_latency_ms(sum_series, count_series):
        return {"ms": 0.0, "d_sum": 0.0, "d_count": 0.0, "present": False,
                "method": "kernel unavailable"}

    def _k_active_frac(values, times=None, threshold=None, rel=0.05):
        return {"fraction": 0.0, "active_samples": 0, "samples": 0,
                "threshold": 0.0, "peak": 0.0, "active_span_s": 0.0,
                "lead_idle_s": 0.0, "trail_idle_s": 0.0, "present": False,
                "method": "kernel unavailable"}

    def _k_bucket_edge(value_ms, bucket_les_s, rel_tol=1e-6):
        return {"on_edge": False, "le_s": 0.0, "lower_s": 0.0,
                "span_ratio": 0.0, "note": ""}

    def _k_tail_ratio(mean_value, p50_value):
        return {"ratio": 0.0, "available": False, "note": ""}

    def _k_align(x_t, x_v, y_t, y_v, tolerance=0.0):
        return [], []

    def _k_pearson(xs, ys):
        return 0.0

    def _k_admission_stalls(times, busy, waiting, running=None,
                            kv_fill_pct=None, busy_threshold=None, rel=0.10,
                            min_samples=2):
        return {"present": False, "episodes": [], "longest": None,
                "method": "kernel unavailable"}


# The three CSVs a run's counters can live in, in the order they are tried —
# the order _kv_delta and _gauge_peak already used, kept rather than tidied so
# that naming it changes no run's answer. Named once so the latency path, the
# token path and the capacity path cannot search different files for the same
# run.
_COUNTER_CSVS = ("l35_store_capacity.csv", "l35_storage_timeseries.csv",
                 "sglang_timeseries.csv")


# One parse per file per process, keyed by identity AND freshness.
#
# extract_metrics asks for roughly 150 different counters, each over up to
# three candidate files, and sglang_timeseries.csv on a long run is tens of
# megabytes. Re-parsing it per counter is what the previous reader did too
# (once per file per _kv_delta call), and it is the one thing the move to a
# per-stem reader would have made worse. The mtime and size are part of the
# key so a re-collected directory is never served from the cache.
_CSV_CACHE: "dict[tuple, tuple[list, list[dict]]]" = {}


def _csv_rows(path: "Path") -> "tuple[list, list[dict]]":
    """(fieldnames, rows) for a CSV, parsed once and remembered."""
    try:
        st = path.stat()
    except OSError:
        return [], []
    key = (str(path), st.st_mtime_ns, st.st_size)
    hit = _CSV_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            r = csv.DictReader(fh)
            out = (list(r.fieldnames or []), list(r))
    except Exception:
        out = ([], [])
    _CSV_CACHE[key] = out
    return out


def _read_series(raw: "Path", parts: "list[str]",
                 files: "tuple[str, ...]" = _COUNTER_CSVS,
                 ) -> "tuple[list[list[float]], str]":
    """Samples of EVERY column matching all of `parts`, with its source.

    One reader for every counter this module differences, so the comparison
    and the single-run report resolve a labelled series the same way. Returns
    ([], "") when no file carried a matching column, which the callers keep
    distinct from a column that matched and never moved.
    """
    for name in files:
        f = Path(raw) / name
        if not f.exists():
            continue
        fieldnames, rows = _csv_rows(f)
        cols = _k_resolve_cols(fieldnames, parts)
        if not cols:
            continue
        series: "list[list[float]]" = [[] for _ in cols]
        for row in rows:
            for _i, _c in enumerate(cols):
                try:
                    v = float(str(row.get(_c, "")).replace(",", ""))
                except (TypeError, ValueError):
                    continue
                if v == v:
                    series[_i].append(v)
        if any(series):
            return series, f"{', '.join(str(c) for c in cols)} in {name}"
    return [], ""


def _sf(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _pick(d: Dict, *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", "unknown"):
            return d[k]
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if str(k).lower() in low and low[str(k).lower()] not in (None, "", "unknown"):
            return low[str(k).lower()]
    return None


def _read_json(path: Path) -> Dict:
    try:
        if path.exists() and path.stat().st_size > 0:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    return {}


def _read_csv_col_all(path: Path, col: str) -> List[float]:
    """Return ALL finite values of `col`, zeros included.

    _read_csv_col drops zeros, which is right for "what was it doing while
    it was busy" and wrong for two things that depend on every sample:

    * a time column, where dropping t=0 shortens the measured span (it
      halved an integrated byte total);
    * a window mean, where dropping idle samples reports the rate while
      active and labels it as the rate over the window.
    """
    if not path.exists():
        return []
    import csv as _c
    out: List[float] = []
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(_c.DictReader(fh))
    except Exception:
        return []
    if not rows:
        return []
    cols = [c for c in rows[0] if c and col in c]
    if not cols:
        return []
    for r in rows:
        tot, seen = 0.0, False
        for c in cols:
            try:
                v = float(r.get(c) or "nan")
            except (TypeError, ValueError):
                continue
            if v == v:
                tot += v; seen = True
        if seen:
            out.append(tot)
    return out


def _read_csv_col_exact(path: Path, col: str) -> List[float]:
    """Values of EXACTLY this column, never summed with a lookalike.

    _read_csv_col_all matches by substring and SUMS every column that
    contains the name. That is right for bandwidth fanned out per device --
    two devices at 300 MB/s really do move 600 -- and wrong twice over for a
    queue depth:

    * the substring match crosses sources. Asking for `qd_peak` in a file
      that also carries `bt_qd_peak` summed the sysfs gauge with the
      blktrace count: 12 and 18 became 30, a depth neither source measured.
    * summing is wrong even across real devices. Two devices each at depth 4
      is not one device at depth 8; depth does not add across queues.

    So queue depths are read exactly, and a column that is not there is
    absent rather than approximated by one whose name merely contains it.
    """
    if not path.exists():
        return []
    import csv as _c
    out: List[float] = []
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(_c.DictReader(fh))
    except Exception:
        return []
    if not rows or col not in rows[0]:
        return []
    for r in rows:
        try:
            v = float(r.get(col) or "nan")
        except (TypeError, ValueError):
            continue
        if v == v:
            out.append(v)
    return out


def _read_csv_col(path: Path, col: str) -> List[float]:
    """Return all non-zero finite values of `col` from a CSV."""
    if not path.exists():
        return []
    out = []
    try:
        with open(path, encoding="utf-8", newline="", errors="replace") as f:
            for row in csv.DictReader(f):
                v = _sf(row.get(col))
                if v > 0:
                    out.append(v)
    except Exception:
        pass
    return out


# ─── Metric extraction ───────────────────────────────────────────────────────


def _scale(v: "float | None", d: float) -> "float | None":
    return None if v is None else v / d


def _kv_delta(raw: "Path", stems: "list[str]") -> "float | None":
    """Window total of a cumulative counter, by the shared kernel's rule.

    Returns None when no column matches any stem — the counter was absent —
    and 0.0 when a column matched but never moved.  Those are different
    findings: absent means unmeasured, zero means measured and idle, and the
    comparison renders them differently.

    The arithmetic is metric_kernels.counter_window_total, which is also what
    the single-run report now differences with. What this function used to do
    was summing each ROW's columns and then differencing the row totals, and
    the two are not the same number: a series whose first sample lands on row
    2 — a scrape target that came up a tick late — is missing from the first
    row total, so the subtrahend was short by that column's entire lifetime
    value. The kernel differences each column over its own samples, which is
    also why a reset in one column no longer drags the others to zero.
    """
    for stem in stems:
        _series, _src = _read_series(raw, [stem])
        if not _series:
            continue
        _t = _k_counter_total(_series)
        if not _t["present"]:
            # Matched, but no column carried two samples: nothing to
            # difference. Still a measurement of "no movement observed",
            # which is what 0.0 says here.
            return 0.0
        return float(_t["total"])
    return None


def _gauge_peak(raw: "Path", stems: "list[str]") -> "float | None":
    """Peak of a GAUGE across the run, from the same CSV set as _kv_delta.

    Capacity is a gauge, not a counter, so it is read as a maximum rather than
    an end-minus-start delta: differencing a constant capacity yields 0, which
    would be reported as a tier with no capacity.

    Returns None when no column matches, so the caller can omit the row
    instead of printing a zero it did not measure.
    """
    import csv as _c
    for name in ("l35_store_capacity.csv", "l35_storage_timeseries.csv",
                 "sglang_timeseries.csv"):
        f = raw / name
        if not f.exists():
            continue
        try:
            with f.open(encoding="utf-8", errors="replace", newline="") as fh:
                rows = list(_c.DictReader(fh))
        except Exception:
            continue
        if not rows:
            continue
        for stem in stems:
            cols = [c for c in rows[0] if c and stem in c]
            if not cols:
                continue
            peak, seen = 0.0, False
            for r in rows:
                tot, row_seen = 0.0, False
                for c in cols:
                    try:
                        v = float(r.get(c) or "nan")
                    except (TypeError, ValueError):
                        continue
                    if v == v:
                        tot += v; row_seen = True
                if row_seen:
                    seen = True
                    peak = max(peak, tot)
            if seen:
                return peak
    return None


def _window_seconds(raw: "Path") -> float:
    import csv as _c
    for name in ("sglang_timeseries.csv", "l35_storage_timeseries.csv"):
        f = raw / name
        if not f.exists():
            continue
        try:
            with f.open(encoding="utf-8", errors="replace", newline="") as fh:
                ts = [float(r["time_sec"]) for r in _c.DictReader(fh)
                      if r.get("time_sec")]
        except Exception:
            continue
        if len(ts) >= 2:
            return max(ts) - min(ts)
    return 0.0

def extract_metrics(spec: RunSpec) -> RunMetrics:
    """Extract all comparable scalar metrics from a run's raw/ directory."""
    raw = spec.raw_dir
    m   = RunMetrics(label=spec.label, raw_dir=str(raw))

    # An explicit per-run setup wins over whatever is in the directory: for a
    # fetched run there is nothing in the directory, and for a directory run
    # the file there may be the stale copy that made every run render as one
    # tier.  Reading it does not modify the user's analyze output.
    setup = None
    if spec.setup_details_path:
        setup = _read_json(Path(spec.setup_details_path))
        if not setup:
            log.warning("compare: run %r: setup_details_path %s could not be "
                        "read as JSON; falling back to the run directory",
                        spec.label, spec.setup_details_path)
    if not setup:
        setup = _read_json(raw / "setup_details.json") or _read_json(raw / "setup.json")
    sglang = _read_json(raw / "sglang_summary.json")
    gpu    = _read_json(raw / "gpu_summary.json")
    smart  = _read_json(raw / "smart_summary.json")
    blk    = _read_json(raw / "summary.json")

    # Context
    m.model    = str(_pick(setup, "Model", "model", "model_name") or
                     _pick(sglang, "model_name", "model") or "unknown")
    m.runtime  = str(_pick(setup, "Runtime", "runtime") or "SGLang")
    m.gpu_desc = str(_pick(setup, "GPU", "gpu") or "unknown")
    m.tp_size  = str(_pick(setup, "TP size", "tp_size") or "?")
    m.context  = str(_pick(setup, "Context length", "context_length", "max_model_len") or "?")
    m.hicache  = str(_pick(setup, "HiCache", "enable_hierarchical_cache") or "?")

    # ── Backing tier, resolved from this run's own setup ──────────────────
    # The same resolver the Executive report uses, on the same file, so the
    # comparison cannot name a tier the single-run report would contradict.
    if setup:
        try:
            from .report.l3_backend import resolve_l3_backend
            _res = resolve_l3_backend(setup)
            m.l3_backend_class = str(_res.backend_class or "")
            m.tier_name        = str(_res.display_name or "")
            m.tier_evidence    = str(_res.evidence or "")
            # The display name carries a parenthetical ("L3.5 (AI Memory Node /
            # remote storage)"), which is right for a configuration row and far
            # too long inside a metric label, so keep a short form too.
            m.tier_short = ("L3" if m.l3_backend_class == "local_ssd"
                            else "L3.5" if m.l3_backend_class in
                            ("remote_mooncake", "remote_storage")
                            else "")
        except Exception as _te:
            log.warning("compare: run %r: backing tier unresolved: %s",
                        spec.label, _te)

    dur_s = _sf(_pick(blk, "duration_s", "run_duration_s")) or \
            _sf(_pick(sglang, "duration_s"))
    if spec.t_start > 0 and spec.t_end > 0:
        dur_s = spec.t_end - spec.t_start
    m.duration_min = dur_s / 60.0

    if spec.t_start > 1_000_000_000:
        from datetime import datetime, timezone, timedelta
        t0 = datetime.fromtimestamp(spec.t_start, tz=timezone.utc)
        t1 = datetime.fromtimestamp(spec.t_end,   tz=timezone.utc) if spec.t_end else None
        m.window_str = t0.strftime("%Y-%m-%d %H:%M UTC")
        if t1:
            m.window_str += f" → {t1.strftime('%H:%M UTC')}"

    # Latency / throughput
    # ---- latency, by the SAME resolution order the single-run report uses --
    #
    # These three lines used to read sglang_summary.json and nothing else --
    # step 3 of a three-step order whose own comment says step 3 "avoids
    # different runs reusing the same stale summary TTFT/TPOT". So the two
    # surfaces could disagree for one window, and on a reference run they
    # did: Combined 11,514 ms, compare 11,525 ms.
    #
    # 0.1% there, but not bounded at 0.1%: the fetch falls back to
    # last(sum)/last(count) -- the LIFETIME mean -- when the window delta is
    # zero, and labels it as a delta regardless, because that method string
    # is a literal. A surface that trusts the summary inherits a lifetime
    # average wearing a window label.
    #
    # The window delta is computable here from the same counters, so it is,
    # and the summary is the last resort it is meant to be.
    # Step 2 of that order — the per-interval p50 series — is read from the
    # same file the single-run report reads it from. Leaving it out meant
    # compare skipped step 2 and fell straight to the summary whenever the
    # counters were missing, so the two surfaces diverged on exactly the runs
    # where the fallback decides the number.
    _pct_ts = _read_json(raw / "sglang_percentiles_timeseries.json")

    def _pct_ts_ms(_key: str) -> float:
        _vals = ((_pct_ts or {}).get(_key) or {}).get("p50") or []
        _ok = [float(v) for v in _vals
               if isinstance(v, (int, float)) and float(v) == float(v)
               and float(v) > 0]
        return (sum(_ok) / len(_ok)) if _ok else 0.0

    def _lat(_kind: str, _base: str, _pct_key: str, *_sum_keys: str) -> None:
        # Δsum and Δcount through the shared kernel, in one resolution pass,
        # so the ratio cannot be formed from two different column sets. The
        # kernel also reports whether the counters were there at all, which
        # is what keeps "no observation completed" from rendering as 0 ms.
        _sum_s, _sum_src = _read_series(raw, [f"{_base}_sum"])
        _cnt_s, _ = _read_series(raw, [f"{_base}_count"])
        _w = _k_latency_ms(_sum_s, _cnt_s)
        _r = _k_resolve_lat(_kind,
                            ts_ms=(_w["ms"] if _w["present"] else 0.0),
                            pct_ms=_pct_ts_ms(_pct_key),
                            summary_ms=_sf(_pick(sglang, *_sum_keys)),
                            summary_method=str(_pick(
                                sglang, f"server_{_kind}_ms_method",
                                f"server_itl_ms_method") or ""))
        setattr(m, f"{_kind if _kind != 'tpot' else 'tpot'}_ms", _r["ms"])
        m.latency_method[_kind] = _r["method"]
        m.latency_window_scoped[_kind] = bool(_r["window_scoped"])
        m.latency_statistic[_kind] = str(_r.get("statistic") or "")
        m.latency_source[_kind] = _sum_src if _w["present"] else ""
        m.latency_obs[_kind] = (_w["d_count"] if _w["present"] else 0.0)

    m.latency_method = {}
    m.latency_window_scoped = {}
    m.latency_statistic = {}
    m.latency_source = {}
    m.latency_obs = {}
    _lat("ttft", "time_to_first_token_seconds", "ttft",
         "server_ttft_ms", "ttft_ms", "mean_ttft_ms")
    _lat("tpot", "inter_token_latency_seconds", "itl",
         "server_itl_ms", "tpot_ms", "itl_ms", "mean_tpot_ms")
    _lat("e2e", "e2e_request_latency_seconds", "e2e",
         "server_e2e_ms", "e2e_ms", "mean_e2e_ms")
    m.cache_hit_pct    = _sf(_pick(sglang, "cache_hit_pct", "cache_hit_active_avg_pct",
                                    "cache_hit_rate_pct", "cache_hit_rate_realtime_pct"))
    m.cache_hit_tw_pct = _sf(_pick(sglang, "cache_hit_token_weighted_pct",
                                    "token_weighted_cache_hit_pct"))
    m.throughput_tok_s = _sf(_pick(sglang, "gen_tp_peak", "gen_tp_active_mean",
                                    "throughput_tok_s", "ai_op_decode_tok_s"))

    # GPU
    m.gpu_util_pct   = _sf(_pick(gpu, "gpu_util_mean", "gpu_util_pct_mean", "util_mean"))
    m.gpu_util_peak  = _sf(_pick(gpu, "gpu_util_peak", "gpu_util_pct_peak"))
    m.hbm_used_gb    = _sf(_pick(gpu, "hbm_used_gb_mean", "hbm_gb", "mem_used_gb_mean"))
    if m.hbm_used_gb > 1000:
        m.hbm_used_gb /= 1024.0
    m.hbm_pct        = _sf(_pick(gpu, "hbm_util_pct_mean", "hbm_pct", "mem_util_pct_mean"))
    m.gpu_power_w    = _sf(_pick(gpu, "power_peak_w", "gpu_power_peak_w"))
    m.dcgm_active_pct = _sf(_pick(gpu, "dcgm_hbm_bw_active_pct", "dcgm_active_pct"))
    m.has_gpu        = bool(gpu)

    # Fallback from the GPU timeseries.
    #
    # Every A4 figure above reads gpu_summary.json and nothing else, so a run
    # with gpu_timeseries.csv and no summary -- a fetched run, or one whose
    # summary was never written -- rendered GPU utilisation, HBM fill and
    # DCGM activity as zeros, and the "GPU utilisation & HBM" chart said the
    # data was not collected while the stall timeline beside it plotted it.
    # Window means over every sample, idle ones included, like the summary.
    _g_p = raw / "gpu_timeseries.csv"
    if _g_p.exists() and (m.gpu_util_pct == 0 or m.hbm_pct == 0
                          or m.dcgm_active_pct == 0):
        _g_fn, _g_rows = _csv_rows(_g_p)
        _g_t, _g_u = _gpu_util_by_time(raw)
        if m.gpu_util_pct == 0 and _g_u:
            m.gpu_util_pct = sum(_g_u) / len(_g_u)
            m.gpu_util_peak = m.gpu_util_peak or max(_g_u)
        # HBM: per-sample sums across GPUs, so used and total are the node's.
        _used: "dict[float, float]" = {}
        _tot: "dict[float, float]" = {}
        _bw: "list[float]" = []
        for _r in _g_rows:
            try:
                _t = float(str(_r.get("time_sec", "")).replace(",", ""))
            except (TypeError, ValueError):
                continue
            _mu = _sf(_r.get("mem_used"), float("nan"))
            _mt = _sf(_r.get("mem_total"), float("nan"))
            if _mu == _mu and _mt == _mt and _mt > 0:
                _used[_t] = _used.get(_t, 0.0) + _mu
                _tot[_t] = _tot.get(_t, 0.0) + _mt
            _hb = _sf(_r.get("hbm_bw_pct"), float("nan"))
            if _hb == _hb:
                _bw.append(_hb)
        if _used:
            _fills = [_used[t] / _tot[t] * 100.0 for t in _used if _tot[t] > 0]
            if m.hbm_pct == 0 and _fills:
                m.hbm_pct = sum(_fills) / len(_fills)
            if m.hbm_used_gb == 0:
                # nvidia-smi reports MiB.
                m.hbm_used_gb = (sum(_used.values()) / len(_used)) / 1024.0
        if m.dcgm_active_pct == 0 and _bw:
            m.dcgm_active_pct = sum(_bw) / len(_bw)
        m.has_gpu = m.has_gpu or bool(_g_u)

    # NVMe
    m.nvme_rd_bw_mbs = _sf(_pick(blk, "nvme_rd_bw_mbs_mean", "read_bw_mb_s_mean"))
    m.nvme_wr_bw_mbs = _sf(_pick(blk, "nvme_wr_bw_mbs_mean", "write_bw_mb_s_mean"))
    m.nvme_rd_iops   = _sf(_pick(blk, "nvme_rd_iops_mean", "read_iops_mean"))
    m.nvme_util_pct  = _sf(_pick(blk, "nvme_io_util_pct", "nvme_util_pct"))
    m.nvme_rd_lat_ms = _sf(_pick(blk, "nvme_rd_lat_ms_mean", "read_lat_ms_mean"))
    m.nvme_wr_lat_ms = _sf(_pick(blk, "nvme_wr_lat_ms_mean", "write_lat_ms_mean"))
    m.read_total_gb  = _sf(_pick(blk, "nvme_read_total_gb", "read_gb_total", "read_GB_total"))
    m.write_total_gb = _sf(_pick(blk, "nvme_write_total_gb", "write_gb_total"))

    # Fallback from the device timeseries.
    #
    # Only read BW, util and read latency had a fallback here, so on a run
    # whose summary JSON carries none of these -- which is every run fetched
    # straight from Prometheus -- read BW appeared and IOPS, write BW and the
    # byte totals rendered as a measured 0.0 beside it. A device doing
    # 33 MB/s at 0 IOPS is not a finding, it is a missing fallback.
    #
    # Queue depth was not extracted at all, though the local-device fetch has
    # collected avgqu_sz and qd_peak since v1.49.5.
    _nvme_files = [raw / "nvme_driver_timeseries.csv",
                   raw / "l35_storage_timeseries.csv"]

    # Window means, over every sample including idle ones: a device that was
    # busy for a tenth of the window did not sustain its busy rate for the
    # whole of it. _read_csv_col_all is used rather than _read_csv_col for
    # exactly that reason.
    def _ts_mean(cols: "list[str]") -> "float | None":
        for _f in _nvme_files:
            for _c in cols:
                _v = _read_csv_col_all(_f, _c)
                if _v:
                    return sum(_v) / len(_v)
        return None

    def _ts_peak(cols: "list[str]") -> "float | None":
        for _f in _nvme_files:
            for _c in cols:
                _v = _read_csv_col_all(_f, _c)
                if _v:
                    return max(_v)
        return None

    if m.nvme_rd_bw_mbs == 0:
        m.nvme_rd_bw_mbs = _ts_mean(["rd_bw_mbs", "l35_rd_bw_mbs"]) or 0.0
    if m.nvme_wr_bw_mbs == 0:
        m.nvme_wr_bw_mbs = _ts_mean(["wr_bw_mbs", "l35_wr_bw_mbs"]) or 0.0
    if m.nvme_rd_iops == 0:
        m.nvme_rd_iops = _ts_mean(["rd_iops", "l35_rd_iops"]) or 0.0
    if m.nvme_util_pct == 0:
        m.nvme_util_pct = _ts_mean(["io_util_pct", "l35_io_util_pct"]) or 0.0
    if m.nvme_rd_lat_ms == 0:
        m.nvme_rd_lat_ms = _ts_mean(["rd_lat_ms", "l35_rd_lat_ms"]) or 0.0
    if m.nvme_wr_lat_ms == 0:
        m.nvme_wr_lat_ms = _ts_mean(["wr_lat_ms", "l35_wr_lat_ms"]) or 0.0
    # ── Queue depth and pressure, per layer ───────────────────────────────
    #
    # Resolved per LAYER and per HOST, with the column that answered recorded
    # so a cell can be attributed. The previous two lines read the first of
    # avgqu_sz / l35_avgqu_sz / bt_qd_mean that returned anything into ONE
    # pair of fields, so comparing a local-SSD run against an L3.5 run put
    # two different devices on two different hosts in the same row, with
    # nothing saying so.
    def _col_series(files: "list[Path]", cols: "list[str]",
                    ) -> "tuple[list[float], str]":
        """Samples of the first column that has any, with 'column in file'.

        A series whose maximum breaches the plausible queue-depth bound is
        skipped, not clamped: the single-run report applies the same bound,
        and a comparison that puts an unmatched-Q counting artifact in a cell
        invites a conclusion about a queue that was never that deep.
        """
        for _f in files:
            for _c in cols:
                _v = _read_csv_col_exact(_f, _c)
                if not _v:
                    continue
                if max(_v) > _QD_PLAUSIBLE_MAX:
                    continue
                return _v, f"{_c} in {_f.name}"
        return [], ""

    def _col_mean(files, cols) -> "tuple[float | None, str]":
        """Mean over EVERY sample, idle ones included.

        A device queued for a tenth of the window did not sustain that depth
        for the whole of it, which is why _read_csv_col_all is used rather
        than _read_csv_col -- the latter drops zeros.
        """
        _v, _src = _col_series(files, cols)
        return ((sum(_v) / len(_v)) if _v else None), _src

    def _col_peak(files, cols) -> "tuple[float | None, str]":
        _v, _src = _col_series(files, cols)
        return (max(_v) if _v else None), _src

    def _col_stats(files, cols) -> "tuple[float | None, float | None, str]":
        """Mean and peak of ONE series, for a column that carries samples."""
        _v, _src = _col_series(files, cols)
        if not _v:
            return None, None, ""
        return sum(_v) / len(_v), max(_v), _src

    _local_f = [raw / "nvme_driver_timeseries.csv"]
    _l35_f = [raw / "l35_storage_timeseries.csv"]
    _sg_f = [raw / "sglang_timeseries.csv"]
    _net_f = [raw / "network_timeseries.csv"]

    # A5 · the inference scheduler's own queue. A real count of requests
    # waiting to enter prefill, and the concurrent decode batch beside it --
    # the two together say whether a run was admission-bound or batch-bound.
    (m.sg_queue_reqs_mean, m.sg_queue_reqs_peak,
     _) = _col_stats(_sg_f, ["num_queue_reqs", "sglang_num_queue_reqs",
                             "queue_reqs"])
    (m.sg_running_reqs_mean, m.sg_running_reqs_peak,
     _) = _col_stats(_sg_f, ["num_running_reqs", "sglang_num_running_reqs",
                             "running_reqs"])

    # A2/A1 · the block layer, once per host.
    #
    # Mean and peak are resolved INDEPENDENTLY, each from the column that
    # means it. Taking both from one column put the peak of a mean series in
    # the peak cell: with bt_qd_mean and bt_qd_peak both present, the peak
    # read 2.4 (the largest per-sample MEAN) where bt_qd_peak said 18. Same
    # error on the device rows, where avgqu_sz is the time-weighted average
    # and qd_peak is max_over_time of the in-flight gauge -- the peak of the
    # average is not the peak.
    #
    #   mean  <- the time-weighted integral (diskstats field 11), which
    #            cannot miss a burst but averages it
    #   peak  <- the instantaneous gauge's maximum (field 9), which can miss
    #            a burst but, when it catches one, counts real coexistence
    #
    # Each keeps its own source string, so a mean and a peak drawn from
    # different columns cannot be read as one measurement.
    m.l3_qd_mean, m.l3_qd_src = _col_mean(
        _local_f, ["avgqu_sz", "avgqu_sz_weighted", "avgqu_sz_service",
                   "inflight"])
    m.l3_qd_peak, _l3_pk_src = _col_peak(
        _local_f, ["qd_peak", "inflight", "avgqu_sz", "avgqu_sz_weighted"])
    m.l35_qd_mean, m.l35_qd_src = _col_mean(
        _l35_f, ["l35_avgqu_sz", "l35_inflight"])
    m.l35_qd_peak, _l35_pk_src = _col_peak(
        _l35_f, ["l35_qd_peak", "l35_inflight", "l35_avgqu_sz"])
    # Exact blktrace Q→C, from whichever file carries it.
    m.bt_qd_mean, m.bt_qd_source = _col_mean(
        _local_f + _l35_f, ["bt_qd_mean", "l35_bt_qd_mean"])
    m.bt_qd_peak, _bt_pk_src = _col_peak(
        _local_f + _l35_f, ["bt_qd_peak", "l35_bt_qd_peak",
                            "bt_qd_mean", "l35_bt_qd_mean"])
    # Name the peak's own column whenever it differs from the mean's, so the
    # report can attribute each half of a mean/peak pair separately.
    for _attr, _pk_src in (("l3_qd_src", _l3_pk_src),
                           ("l35_qd_src", _l35_pk_src),
                           ("bt_qd_source", _bt_pk_src)):
        _mean_src = getattr(m, _attr, "")
        if _pk_src and _pk_src != _mean_src:
            setattr(m, _attr,
                    f"{_mean_src or 'no mean series'} (mean), "
                    f"{_pk_src} (peak)" if _mean_src else f"{_pk_src} (peak)")

    # NET and A3 · no queue is exposed at either layer. These are proxies and
    # are labelled as such wherever they are rendered.
    (m.net_retrans_ps_mean, m.net_retrans_ps_peak,
     _) = _col_stats(_net_f, ["tcp_retrans_ps", "net_tcp_retrans_ps"])
    m.net_rx_drop_ps_mean, _, _ = _col_stats(
        _net_f, ["rx_drop_ps", "net_rx_drop_ps"])
    (m.net_link_util_pct_mean, m.net_link_util_pct_peak,
     _) = _col_stats(_net_f, ["link_util_pct", "net_link_util_pct"])

    # The A2 table keeps its single pair, now derived from the split fields
    # rather than from a blind first-hit scan, preferring THIS host's device
    # and falling back to the memory node's, then to blktrace.
    m.nvme_qd_mean = (m.l3_qd_mean if m.l3_qd_mean is not None
                      else m.l35_qd_mean if m.l35_qd_mean is not None
                      else m.bt_qd_mean)
    m.nvme_qd_peak = (m.l3_qd_peak if m.l3_qd_peak is not None
                      else m.l35_qd_peak if m.l35_qd_peak is not None
                      else m.bt_qd_peak)
    # Byte totals: integrate the BW series when the summary has no total, so
    # the A1 volume row is not a zero standing in for "not in this JSON".
    #
    # mean rate x window, taking the span from the SAME file's own time
    # column. Summing samples and multiplying by a step counts N samples
    # over (N-1) intervals -- a 50% overcount on a three-sample series -- and
    # deriving the span from elsewhere gives up entirely on a run whose only
    # device file is this one.
    if m.read_total_gb == 0 or m.write_total_gb == 0:
        for _f in _nvme_files:
            _rd = (_read_csv_col_all(_f, "rd_bw_mbs")
                   or _read_csv_col_all(_f, "l35_rd_bw_mbs"))
            _wr = (_read_csv_col_all(_f, "wr_bw_mbs")
                   or _read_csv_col_all(_f, "l35_wr_bw_mbs"))
            if not (_rd or _wr):
                continue
            _ts = _read_csv_col_all(_f, "time_sec")
            _span = (max(_ts) - min(_ts)) if len(_ts) >= 2 else 0.0
            if _span <= 0:
                _span = _window_seconds(raw)
            if _span <= 0:
                continue
            if m.read_total_gb == 0 and _rd:
                m.read_total_gb = (sum(_rd) / len(_rd)) * _span / 1000.0
            if m.write_total_gb == 0 and _wr:
                m.write_total_gb = (sum(_wr) / len(_wr)) * _span / 1000.0
            break

    m.has_blktrace = any((raw / f).exists() for f in (
        "request_size_distribution.csv", "hot_regions_overall.csv"))

    # DRAM
    for dram_file in ("amduprof_pcm_timeseries.csv", "pcm_timeseries.csv"):
        dp = raw / dram_file
        if dp.exists():
            for total_col in ("dram_total_gb_s", "total_bw_gbps", "total_gb_s"):
                vals = _read_csv_col(dp, total_col)
                if vals:
                    m.dram_total_bw_gbs = sum(vals) / len(vals)
                    m.dram_peak_bw_gbs  = max(vals)
                    m.has_dram = True
                    break
            if m.has_dram:
                for rd_col in ("dram_read_gb_s", "read_bw_gbps", "read_gb_s"):
                    v = _read_csv_col(dp, rd_col)
                    if v: m.dram_rd_bw_gbs = sum(v) / len(v); break
                for wr_col in ("dram_write_gb_s", "write_bw_gbps", "write_gb_s"):
                    v = _read_csv_col(dp, wr_col)
                    if v: m.dram_wr_bw_gbs = sum(v) / len(v); break
                break

    # Clamp all float fields to >= 0 to prevent negative values
    # (e.g. -1 sentinel values in DCGM, or misconfigured Prometheus metrics)
    # reaching bar charts or delta cells.
    for _attr in ("ttft_ms", "tpot_ms", "e2e_ms", "throughput_tok_s",
                  "cache_hit_pct", "cache_hit_tw_pct", "gpu_util_pct",
                  "gpu_util_peak", "hbm_used_gb", "hbm_pct", "gpu_power_w",
                  "dcgm_active_pct", "nvme_rd_bw_mbs", "nvme_wr_bw_mbs",
                  "nvme_rd_iops", "nvme_util_pct", "nvme_rd_lat_ms",
                  "nvme_wr_lat_ms", "read_total_gb", "write_total_gb",
                  "dram_total_bw_gbs", "dram_rd_bw_gbs", "dram_wr_bw_gbs",
                  "dram_peak_bw_gbs"):
        v = getattr(m, _attr, 0.0)
        if v < 0:
            setattr(m, _attr, 0.0)

    # A3 has no controller queue to read, so the only pressure signal is how
    # close the measured bandwidth came to the platform's peak. Computed
    # after the clamp so a negative reading cannot produce a negative
    # percentage, and left as None when either side is missing rather than
    # dividing by a default that would read as a measurement.
    # dram_peak_bw_gbs is the run's OWN observed maximum (max of the series
    # a few lines up), not the platform's capability. Dividing the mean by it
    # gives a burstiness ratio -- how peaky the run was -- which is not a
    # pressure signal and must not be labelled as one. The reference has to
    # come from the platform, which only the setup details carry.
    _dram_peak_cfg = _sf(_pick(setup or {}, "DRAM peak GB/s", "dram_peak_gbs",
                               "dram_peak_bw_gbs", "DRAM peak bandwidth GB/s"),
                         0.0)
    if m.dram_total_bw_gbs > 0 and _dram_peak_cfg > 0:
        m.dram_bw_pct_of_peak = m.dram_total_bw_gbs / _dram_peak_cfg * 100.0
        m.dram_peak_ref_gbs = _dram_peak_cfg
    # No platform peak configured means no share-of-peak. A default stand-in
    # would make the cell look measured; left as None it reads as the gap it
    # is, and the row says which setup key would fill it.

    log.info("Extracted metrics for '%s': TTFT=%.1fs TPOT=%.0fms "
             "NVMe=%.0f MB/s GPU=%.1f%%",
             m.label, m.ttft_ms / 1000, m.tpot_ms,
             m.nvme_rd_bw_mbs, m.gpu_util_pct)

    # ── KV movement inside the AI memory node ────────────────────────────
    _raw = Path(spec.raw_dir)
    m.window_s      = _window_seconds(_raw)
    # Column names as the L3.5 synthesis writes them, with the raw exporter
    # names as fallbacks for run directories produced before that mapping.
    m.evicted_gb    = _scale(_kv_delta(_raw, ["l35_evicted_b",
                                              "evicted_size_bytes",
                                              "mooncake_evicted_bytes"]), 1e9)
    m.promoted_gb   = _scale(_kv_delta(_raw, ["l35_promoted_b",
                                              "promotion_completed_bytes",
                                              "mooncake_promoted_bytes"]), 1e9)
    m.mem_hit_gb    = _scale(_kv_delta(_raw, ["l35_mem_hit_b",
                                              "mem_cache_hit_bytes",
                                              "mooncake_read_bytes_mem"]), 1e9)
    m.file_hit_gb   = _scale(_kv_delta(_raw, ["l35_file_hit_b",
                                              "file_cache_hit_bytes",
                                              "mooncake_read_bytes_file"]), 1e9)
    m.prefetched_tok = _kv_delta(_raw, ["prefetched_tokens_total"])

    # ── Token activity and the KV hops, for the A5 -> A1 walk ─────────────
    # One counter per hop. These are lifetime counters, so they are
    # differenced over the window like the rest; None means the counter was
    # never exported, which is a different finding from a counter that
    # stayed at zero and is rendered differently.
    m.prompt_tok     = _kv_delta(_raw, ["prompt_tokens_total"])
    m.gen_tok        = _kv_delta(_raw, ["generation_tokens_total"])

    # ── The realtime phase counters, when the totals are not exported ─────
    #
    # Several deployments export only realtime_tokens_total{mode=...} and
    # none of prompt_tokens_total / generation_tokens_total / a cached total.
    # The single-run report grew this fallback in v1.73.0; compare did not,
    # so on exactly those runs every figure downstream of these three — the
    # layer walk, recomputed tokens, KV generated, demand and avoided bytes,
    # the recompute rate — rendered "not exported" in the comparison while
    # the per-run report beside it printed all of them. That is the whole of
    # the "compare marks a lot of information absent" complaint: the counters
    # were there, under the names only the other surface looked for.
    #
    #   prompt = prefill_cache + prefill_compute   (the cache-hit denominator)
    #   decode = decode mode
    #
    # cached_tok was the same bug in its sharpest form: its first stem,
    # "realtime_tokens_total[mode=prefill_cache]", is a literal with brackets
    # that no exporter writes, so it never matched; its second, the bare
    # "prefill_cache", matched the first column carrying that substring
    # whatever metric it belonged to. Both are replaced by the two-part
    # resolution, which requires the metric name AND the label and so cannot
    # do either.
    def _phase_tok(_mode: str) -> "float | None":
        _s, _ = _read_series(_raw, ["realtime_tokens_total", f"mode={_mode}"])
        if not _s:
            return None
        _t = _k_counter_total(_s)
        return float(_t["total"]) if _t["present"] else 0.0

    _ph_cache   = _phase_tok("prefill_cache")
    _ph_compute = _phase_tok("prefill_compute")
    _ph_decode  = _phase_tok("decode")

    m.cached_tok = _kv_delta(_raw, ["cached_tokens_total"])
    if not m.cached_tok and _ph_cache:
        m.cached_tok = _ph_cache
        m.token_src["cached"] = (
            "Δrealtime_tokens_total{mode=prefill_cache} — no cached total "
            "is exported here")
    if not m.prompt_tok and _ph_cache and _ph_compute:
        m.prompt_tok = _ph_cache + _ph_compute
        m.token_src["prompt"] = (
            f"Δrealtime_tokens_total{{mode=prefill_cache}} + "
            f"{{mode=prefill_compute}} ({_ph_cache:,.0f} + "
            f"{_ph_compute:,.0f}) — sglang_prompt_tokens_total is not "
            f"exported here")
    elif not m.prompt_tok and _ph_compute:
        # Compute alone IS the recomputed prefill, which is the term the
        # walk needs. Taken with cached at zero so prompt - cached is that
        # figure and not an inflated one.
        m.prompt_tok = _ph_compute
        m.cached_tok = 0.0
        m.token_src["prompt"] = (
            f"recomputed prefill taken directly from "
            f"Δrealtime_tokens_total{{mode=prefill_compute}} "
            f"({_ph_compute:,.0f}) — neither prompt_tokens_total nor a "
            f"cached total is exported here")
    if not m.gen_tok and _ph_decode:
        m.gen_tok = _ph_decode
        m.token_src["gen"] = (
            f"Δrealtime_tokens_total{{mode=decode}} ({_ph_decode:,.0f}) — "
            f"sglang_generation_tokens_total is not exported here")

    # ── How much of the window was alive ──────────────────────────────────
    #
    # Resolved from the first activity series the run exported, in order of
    # how directly it says "the GPUs were working":
    #
    #   hbm_bw_gbs / gpu_util   the GPUs themselves (gpu_timeseries.csv)
    #   gen_throughput          the engine's own decode rate
    #   num_running_reqs        the decode batch
    #
    # Each is a gauge, so the test is a duty cycle, not a counter delta. The
    # threshold is relative to the series' own robust peak -- these have
    # different units -- and is reported with the fraction, since a duty
    # cycle without its threshold is not checkable.
    for _af_file, _af_cols, _af_label in (
            ("gpu_timeseries.csv", ["hbm_bw_gbs"], "HBM bandwidth"),
            ("gpu_timeseries.csv", ["gpu_util"], "GPU utilisation"),
            ("sglang_timeseries.csv", ["gen_throughput"],
             "engine decode throughput"),
            ("sglang_timeseries.csv", ["num_running_reqs"],
             "decode batch size")):
        _af_p = raw / _af_file
        if not _af_p.exists():
            continue
        _af_fn, _af_rows = _csv_rows(_af_p)
        _af_c = _k_resolve_cols(_af_fn, _af_cols)
        if not _af_c:
            continue
        _af_v, _af_t = [], []
        for _r in _af_rows:
            try:
                _x = float(str(_r.get(_af_c[0], "")).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if _x != _x:
                continue
            _af_v.append(_x)
            try:
                _af_t.append(float(str(_r.get("time_sec", "")).replace(",", "")))
            except (TypeError, ValueError):
                _af_t.append(float("nan"))
        _af = _k_active_frac(_af_v, _af_t if len(_af_t) == len(_af_v) else None)
        if not _af["present"]:
            continue
        m.active_frac = float(_af["fraction"])
        m.active_span_s = float(_af["active_span_s"]) or None
        m.lead_idle_s = float(_af["lead_idle_s"])
        m.trail_idle_s = float(_af["trail_idle_s"])
        m.active_src = f"{_af_c[0]} in {_af_file} ({_af_label})"
        m.active_method = str(_af["method"])
        break

    # ── Latency percentiles ───────────────────────────────────────────────
    #
    # The whole-window quantiles the single-run report treats as
    # authoritative -- Prometheus histogram_quantile over the window, which
    # sglang_summary.json carries as server_*_p50/p90/p99_ms -- then the
    # per-interval p50 series as a fallback, which is the same order
    # analyze's _win_p50 applies.
    #
    # Each is checked against the metric's own bucket ladder, because a
    # quantile that lands on a boundary is bucket-limited: a reported p50 of
    # exactly 800.00 ms on the 0.08 / 0.8 / 8 / 400 s ladder is the 0.8 s
    # edge, and the span it stands for is 100x wide. Comparing it against
    # another run's 598 ms as though both were measurements is the error
    # this row exists to prevent.
    def _bucket_les(_base: str) -> "list[float]":
        for _name in _COUNTER_CSVS:
            _p = raw / _name
            if not _p.exists():
                continue
            _fn, _ = _csv_rows(_p)
            _les = []
            for _c in _k_resolve_cols(_fn, [f"{_base}_bucket"],
                                      exclude_buckets=False):
                _mm = re.search(r'le\s*=\s*["\']?([0-9.eE+infInf]+)',
                                str(_c))
                if not _mm:
                    continue
                try:
                    _les.append(float(_mm.group(1)))
                except ValueError:
                    pass
            if _les:
                return sorted(set(_les))
        return []

    for _pk, _pbase, _ppct_key in (("ttft", "time_to_first_token_seconds", "ttft"),
                                   ("tpot", "inter_token_latency_seconds", "itl"),
                                   ("e2e", "e2e_request_latency_seconds", "e2e")):
        _les = _bucket_les(_pbase)
        _sumkey = {"ttft": "ttft", "tpot": "itl", "e2e": "e2e"}[_pk]
        for _q, _qn in ((0.5, "p50"), (0.9, "p90"), (0.99, "p99")):
            _v = _sf(_pick(sglang, f"server_{_sumkey}_{_qn}_ms",
                           f"{_sumkey}_{_qn}_ms", f"{_pk}_{_qn}_ms"))
            _src = "whole-window histogram_quantile (sglang_summary.json)"
            if _v <= 0 and _q == 0.5:
                _v = _pct_ts_ms(_ppct_key)
                _src = ("per-interval p50, mean over active intervals "
                        "— FALLBACK")
            if _v <= 0:
                continue
            m.lat_pct_ms[(_pk, _q)] = _v
            m.lat_pct_src[(_pk, _q)] = _src
            _be = _k_bucket_edge(_v, _les)
            if _be["on_edge"]:
                m.lat_bucket_note[(_pk, _q)] = str(_be["note"])

    # ── L1 HBM KV pool, by the names the single-run report's chart uses ───
    for _l1_cols, _l1_kind in ((["num_used_tokens"], "tokens"),
                               (["kv_used_tokens"], "tokens"),
                               (["token_usage"], "fraction"),
                               (["full_token_usage"], "fraction")):
        _l1_s, _l1_src = _read_series(_raw, _l1_cols,
                                      ("sglang_timeseries.csv",))
        if not _l1_s or not _l1_s[0]:
            continue
        _l1_v = [x for x in _l1_s[0] if x == x]
        if not _l1_v:
            continue
        _cap_s, _ = _read_series(_raw, ["max_total_num_tokens"],
                                 ("sglang_timeseries.csv",))
        _cap = max((max(c) for c in _cap_s if c), default=0.0) or \
            _sf(_pick(sglang, "max_total_num_tokens",
                      "sglang_max_total_num_tokens")) or \
            _sf(_pick(setup or {}, "max_total_num_tokens"))
        if _l1_kind == "fraction":
            if _cap <= 0:
                continue
            _sc = 0.01 if max(_l1_v) > 1.5 else 1.0
            _l1_v = [x * _sc * _cap for x in _l1_v]
            _l1_src += " x max_total_num_tokens"
        m.l1_kv_tok_mean = sum(_l1_v) / len(_l1_v)
        m.l1_kv_tok_peak = max(_l1_v)
        m.l1_kv_cap_tok = _cap or None
        m.l1_kv_src = _l1_src
        break

    # ── What the device is rated for, so load can be read against it ──────
    # The single-run report's requirement summary measures against these
    # same two setup keys and falls back to 7,000 / 5,000 MB/s. That
    # fallback is a PLACEHOLDER, not a measurement of this drive, so when it
    # is what answered, the source string says so and the row is labelled a
    # default rather than a spec.
    _rt = _sf(_pick(setup or {}, "L3 (local storage) read BW target MB/s",
                    "nvme_rd_bw_target_mbs"))
    _wt = _sf(_pick(setup or {}, "L3 (local storage) write BW target MB/s",
                    "nvme_wr_bw_target_mbs"))
    if _rt > 0 or _wt > 0:
        m.dev_rd_target_mbs = _rt or None
        m.dev_wr_target_mbs = _wt or None
        m.dev_target_src = "setup_details"
    else:
        m.dev_rd_target_mbs, m.dev_wr_target_mbs = 7000.0, 5000.0
        m.dev_target_src = ("DEFAULT 7,000 / 5,000 MB/s — not this drive's "
                            "rating; set 'L3 (local storage) read/write BW "
                            "target MB/s' in setup_details to measure "
                            "against the real one")

    # ── Cache hit and throughput, from those same counters ────────────────
    #
    # Both read sglang_summary.json and nothing else, so on a run fetched
    # straight from Prometheus -- where there is no summary JSON at all --
    # the two headline KPIs of the comparison rendered as 0.0. A 0% cache hit
    # beside a tiering study is not an absence, it is a finding, and it was
    # the wrong one. The counters needed to compute both were in the same
    # file the layer walk reads.
    if m.cache_hit_pct <= 0 and _ph_cache and _ph_compute:
        # Token-weighted over the window, through the kernel the Executive
        # report's own cache-hit tile uses, so the two cannot disagree. A
        # mean of per-sample gauge readings is a different number: at a 2.5%
        # duty cycle the idle zeros drag a real 30% to 0.5%.
        try:
            from .report.metric_kernels import prefill_cache_hit_ratio as _rch
            _ch = _rch(_ph_cache, _ph_compute)
            if _sf(_ch.get("pct")) > 0:
                m.cache_hit_pct = float(_ch["pct"])
                m.cache_hit_tw_pct = m.cache_hit_tw_pct or float(_ch["pct"])
                m.token_src["cache_hit"] = (
                    "token-weighted Δrealtime_tokens_total{mode=prefill_cache} "
                    "÷ (prefill_cache + prefill_compute) — no cache-hit "
                    "figure is in sglang_summary.json")
        except Exception:
            pass
    if m.throughput_tok_s <= 0 and m.gen_tok and m.window_s > 0:
        # Decode tokens over the window, which is the whole-window average
        # and so includes idle time. Deliberately not the active-only rate:
        # the summary's gen_tp_peak is a peak and gen_tp_active_mean excludes
        # idle, and a comparison row has to mean one thing on every run.
        m.throughput_tok_s = float(m.gen_tok) / float(m.window_s)
        m.token_src["throughput"] = (
            f"Δdecode tokens ÷ window ({m.gen_tok:,.0f} ÷ "
            f"{m.window_s:,.0f} s) — whole-window average, idle time "
            f"included; no throughput figure is in sglang_summary.json")

    # ---- KV geometry, so token counts can become bytes -------------------
    #
    # From this run's own raw/model_config.json, which --model-path writes
    # (and which the fetch now writes itself). Resolved through the SAME
    # kernel the single-run report uses, so the two surfaces cannot report
    # different KV bytes per token for one model -- which they did once, 320
    # and 88 KB/token in one report, before that kernel existed.
    try:
        from .report.metric_kernels import resolve_kv_bytes_per_token as _rkv
    except Exception:
        _rkv = None
    if _rkv is not None:
        _mc_raw = _read_json(raw / "model_config.json")
        _kv_cfg = {str(k).strip().lower(): v for k, v in (_mc_raw or {}).items()
                   if not str(k).startswith("_")}
        # The engine's own kv_cache_dtype, when the setup passthrough has it:
        # a KV cache in fp8 is half the bytes of one in bf16, and nothing
        # else in the config says so.
        _kv_dt = str(_pick(setup or {}, "kv_cache_dtype", "KV cache dtype")
                     or _kv_cfg.get("kv_cache_dtype") or "") or ""
        try:
            _kvr = _rkv(model_name=m.model, kv_dtype=_kv_dt, config=_kv_cfg)
        except Exception:
            _kvr = {}
        _kb = _sf(_kvr.get("kb"), 0.0)
        if _kb > 0:
            m.kv_bytes_tok_kb = _kb
            m.kv_bytes_src = str(_kvr.get("source") or "")
            m.kv_bytes_exact = bool(_kvr.get("exact"))
    try:
        m.tp_size_n = float(str(m.tp_size).strip()) if m.tp_size not in ("", "?") else None
    except (TypeError, ValueError):
        m.tp_size_n = None
    m.evicted_tok    = _kv_delta(_raw, ["evicted_tokens_total"])
    m.backuped_tok   = _kv_delta(_raw, ["backuped_tokens_total"])
    m.load_back_tok  = _kv_delta(_raw, ["load_back_tokens_total"])
    m.store_get_n     = _kv_delta(_raw, ["l35_get_total_n", "get_total_n"])
    m.store_mem_hit_n = _kv_delta(_raw, ["l35_mem_hit_n", "mem_hit_n"])
    m.store_file_hit_n = _kv_delta(_raw, ["l35_file_hit_n", "file_hit_n"])

    # ── A1 device write amplification inputs (gauges, read as peaks) ──────
    m.nand_written_gb = _gauge_peak(_raw, ["l35_nand_written_gb", "nand_written_gb"])
    m.host_written_gb = _gauge_peak(_raw, ["l35_host_written_gb", "host_written_gb"])

    # ── Capacity of each tier of the backing store ────────────────────────
    # The chain's first row is a configuration row: the capacity the tier was
    # given, not how full it got.  Previously neither field was assigned
    # anywhere, so that row compared 0.0 against 0.0 on every run -- a
    # configuration difference between "DRAM only" and "DRAM + SSD" was
    # invisible in the one table meant to show it.
    #
    # Read as a gauge peak from the exporter when present, else from an
    # explicit capacity in setup_details. A capacity is never inferred from
    # how much of the tier was used.
    m.l35_dram_gb = _scale(_gauge_peak(_raw, [
        "l35_store_mem_capacity_b", "mooncake_segment_capacity_bytes",
        "mooncake_capacity_bytes", "mem_cache_capacity_bytes"]), 1e9)
    m.l35_file_gb = _scale(_gauge_peak(_raw, [
        "l35_store_file_capacity_b", "file_cache_capacity_bytes",
        "mooncake_file_capacity_bytes"]), 1e9)
    if m.l35_dram_gb is not None or m.l35_file_gb is not None:
        m.l35_cap_source = "store exporter (gauge peak)"
    if m.l35_dram_gb is None:
        _v = _sf(_pick(setup, "L3.5 DRAM capacity GB", "l35_dram_capacity_gb",
                       "L3.5 memory capacity GB", "AI memory node DRAM GB"))
        if _v > 0:
            m.l35_dram_gb, m.l35_cap_source = _v, "setup_details"
    if m.l35_file_gb is None:
        _v = _sf(_pick(setup, "L3.5 SSD capacity GB", "l35_file_capacity_gb",
                       "L3.5 storage capacity GB", "L3 capacity GB",
                       "L3 capacity"))
        if _v > 0:
            m.l35_file_gb = _v
            m.l35_cap_source = m.l35_cap_source or "setup_details"

    _extract_diagnosis(m, _raw, setup or {})
    return m


# ─── Where the time went: stalls, time to complete, tier delivery ───────────
#
# The figures above are window totals and window means. They say how much
# each run did, not why one took longer to do it. These read the timelines
# underneath them -- GPU utilisation, the scheduler's waiting queue, the
# decode batch, the L1 KV pool and the tier counters -- on one time base.


def _rows_by_time(path: "Path", parts: "list[str]",
                  exclude: "tuple[str, ...]" = (), agg: str = "max",
                  ) -> "tuple[list[float], list[float], str]":
    """(times, values, source) of one series, one value per CSV row.

    Every column matching all of `parts` contributes, minus any whose name
    contains an `exclude` fragment. `agg` decides how several columns become
    one value: "sum" for a counter fanned out per rank (each rank's share is
    part of the total), "max" for a gauge every rank reports alike (summing
    eight copies of one waiting queue would invent seven queues).
    """
    if not path.exists():
        return [], [], ""
    fieldnames, rows = _csv_rows(path)
    if "time_sec" not in fieldnames:
        return [], [], ""
    cols = [c for c in _k_resolve_cols(fieldnames, parts)
            if not any(x in str(c).lower() for x in exclude)]
    if not cols:
        return [], [], ""
    pts: "list[tuple[float, float]]" = []
    for r in rows:
        try:
            t = float(str(r.get("time_sec", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        vals = []
        for c in cols:
            try:
                v = float(str(r.get(c, "")).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if v == v:
                vals.append(v)
        if t == t and vals:
            pts.append((t, max(vals) if agg == "max" else sum(vals)))
    pts.sort()
    return ([t for t, _ in pts], [v for _, v in pts],
            f"{', '.join(str(c) for c in cols)} in {path.name}")


def _gpu_util_by_time(raw: "Path") -> "tuple[list[float], list[float]]":
    """Mean GPU utilisation per timestamp, across every GPU row at that time.

    gpu_timeseries.csv carries one row per GPU per sample, so reading the
    column top to bottom interleaves the GPUs; grouping on time_sec is what
    turns it back into one series.
    """
    p = raw / "gpu_timeseries.csv"
    if not p.exists():
        return [], []
    fieldnames, rows = _csv_rows(p)
    cols = _k_resolve_cols(fieldnames, ["gpu_util"])
    if not cols or "time_sec" not in fieldnames:
        return [], []
    col = "gpu_util" if "gpu_util" in cols else cols[0]
    acc: "dict[float, list[float]]" = {}
    for r in rows:
        try:
            t = float(str(r.get("time_sec", "")).replace(",", ""))
            v = float(str(r.get(col, "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if t == t and v == v:
            acc.setdefault(t, []).append(v)
    ts = sorted(acc)
    vals = [sum(acc[t]) / len(acc[t]) for t in ts]
    # A fraction rather than a percentage on some exporters.
    if vals and max(vals) <= 1.0:
        vals = [v * 100.0 for v in vals]
    return ts, vals


def _increase_between(ts: "list[float]", vs: "list[float]",
                      t0: float, t1: float) -> float:
    """Counter increase over the samples in (t0, t1], reset-safe."""
    tot = 0.0
    for i in range(1, len(ts)):
        if t0 < ts[i] <= t1:
            d = vs[i] - vs[i - 1]
            tot += d if d >= 0 else max(0.0, vs[i])
    return tot


_LAUNCH_BACKEND_RE = re.compile(r"--hicache-storage-backend[=\s]+([\w.-]+)")
_LAUNCH_PAGE_RE = re.compile(r"--page-size[=\s]+(\d+)")


def _extract_diagnosis(m: "RunMetrics", raw: "Path", setup: dict) -> None:
    """Fill the stall, completion-time, tier-delivery and config fields."""
    # ── How many requests the window served ───────────────────────────────
    for _k, _base in (("e2e", "e2e_request_latency_seconds"),
                      ("ttft", "time_to_first_token_seconds")):
        _n = (m.latency_obs or {}).get(_k)
        if _n:
            m.requests_n = float(_n)
            m.requests_src = f"Δ{_base}_count over the window"
            break

    # ── Time spent queued before prefill, window mean ─────────────────────
    _qs, _ = _read_series(raw, ["queue_time_seconds_sum"])
    _qc, _ = _read_series(raw, ["queue_time_seconds_count"])
    _qw = _k_latency_ms(_qs, _qc)
    if _qw["present"]:
        m.queue_wait_ms = float(_qw["ms"])

    # ── The timelines, on the scheduler's time base ───────────────────────
    sg = raw / "sglang_timeseries.csv"
    w_t, w_v, w_src = _rows_by_time(
        sg, ["num_queue_reqs"], exclude=("grammar", "offline", "prealloc",
                                         "transfer", "inflight"))
    r_t, r_v, _ = _rows_by_time(sg, ["num_running_reqs"],
                                exclude=("offline",))
    k_t, k_v, _ = _rows_by_time(sg, ["num_used_tokens"])
    g_t, g_v = _gpu_util_by_time(raw)

    # The A5 queue rows read these by exact column name, which the fetched
    # CSVs never use (they write `sglang:num_queue_reqs...`), so the
    # scheduler's queue -- the one plain count of waiting work in the stack
    # -- was missing from every fetched comparison. Fill them from the same
    # series the stall test reads.
    if m.sg_queue_reqs_mean is None and w_v:
        m.sg_queue_reqs_mean = sum(w_v) / len(w_v)
        m.sg_queue_reqs_peak = max(w_v)
    if m.sg_running_reqs_mean is None and r_v:
        m.sg_running_reqs_mean = sum(r_v) / len(r_v)
        m.sg_running_reqs_peak = max(r_v)

    if len(g_t) >= 2:
        _span = g_t[-1] - g_t[0]
        if _span > 0:
            m.gpu_busy_equiv_s = (sum(g_v) / len(g_v)) / 100.0 * _span

    p_t, p_v, _ = _rows_by_time(sg, ["prefetched_tokens_total"], agg="sum")
    b_t, b_v, _ = _rows_by_time(sg, ["backuped_tokens_total"], agg="sum")

    def _rate_at(ts, vs):
        """Per-interval rate of a counter, keyed by the interval's end."""
        out = {}
        for i in range(1, len(ts)):
            dt = ts[i] - ts[i - 1]
            if dt > 0:
                d = vs[i] - vs[i - 1]
                out[ts[i]] = (d if d >= 0 else max(0.0, vs[i])) / dt
        return out

    if w_t and g_t:
        # Pairing the scheduler's own timestamps with the nearest GPU sample
        # returns those timestamps as the X values, so the waiting, running
        # and KV series can be looked up at exactly the instants kept.
        _ts, _busy = _k_align(w_t, w_t, g_t, g_v)
        _w_at = dict(zip(w_t, w_v))
        _r_at = dict(zip(r_t, r_v))
        _cap = m.l1_kv_cap_tok or 0.0
        _k_at = ({t: v / _cap * 100.0 for t, v in zip(k_t, k_v)}
                 if _cap > 0 else {})
        _wait = [_w_at.get(t, 0.0) for t in _ts]
        _run = [_r_at.get(t, 0.0) for t in _ts] if _r_at else None
        _kv = [_k_at.get(t, float("nan")) for t in _ts] if _k_at else None
        _st = _k_admission_stalls(_ts, _busy, _wait, _run, _kv)
        if _st.get("present"):
            m.stall_present = True
            m.busy_s = float(_st["busy_s"])
            m.stall_s = float(_st["stall_s"])
            m.no_work_s = float(_st["no_work_s"])
            m.other_idle_s = float(_st["other_idle_s"])
            m.stall_method = str(_st["method"])
            m.stall_src = (f"gpu_util in gpu_timeseries.csv (mean across "
                           f"GPUs) against {w_src}")
            m.stall_episodes = [dict(e) for e in _st["episodes"]]
            # Downsampled for the chart: a 1 Hz local run has thousands of
            # points, and the chart is read for shape.
            _pr_at, _br_at = _rate_at(p_t, p_v), _rate_at(b_t, b_v)
            _pr = [_pr_at.get(t, float("nan")) for t in _ts] if _pr_at else None
            _br = [_br_at.get(t, float("nan")) for t in _ts] if _br_at else None
            _stride = max(1, len(_ts) // 400)
            m.timeline = {"t": _ts[::_stride], "gpu": _busy[::_stride],
                          "waiting": _wait[::_stride],
                          "running": (_run[::_stride] if _run else [])}
            # Which signals moved together over the run. Pairs are filtered
            # to samples where both sides are finite before the kernel sees
            # them, and a pair with a constant side is None rather than 0:
            # an r of 0 reads as "independent", which a flat line is not.
            _named = [(n, v) for n, v in (
                ("GPU util", _busy), ("waiting reqs", _wait),
                ("decode batch", _run), ("L1 KV fill", _kv),
                ("prefetch rate", _pr), ("backup rate", _br)) if v]
            _names = [n for n, _ in _named]
            _mat: "list[list[float | None]]" = []
            for _, xa in _named:
                _row = []
                for _, xb in _named:
                    _pairs = [(a, b) for a, b in zip(xa, xb)
                              if a == a and b == b]
                    _xs = [a for a, _ in _pairs]
                    _ys = [b for _, b in _pairs]
                    if (len(_pairs) < 3 or max(_xs) == min(_xs)
                            or max(_ys) == min(_ys)):
                        _row.append(None)
                    else:
                        _row.append(round(_k_pearson(_xs, _ys), 3))
                _mat.append(_row)
            if len(_names) >= 2:
                m.corr = {"names": _names, "r": _mat}

    # ── When the backing tier last delivered ──────────────────────────────
    if len(p_t) >= 2:
        _last = None
        for i in range(1, len(p_t)):
            if p_v[i] > p_v[i - 1]:
                _last = p_t[i]
        if _last is not None:
            m.prefetch_last_move_s = _last
            m.prefetch_quiet_tail_s = max(0.0, p_t[-1] - _last)
        else:
            m.prefetch_quiet_tail_s = p_t[-1] - p_t[0]
    # What each tier counter did DURING each stall: a tier that delivered
    # nothing while requests waited is a different finding from one that was
    # busy delivering.
    for e in m.stall_episodes:
        _t0 = e["t_end"] - e["dur_s"]
        e["prefetch_tok"] = (_increase_between(p_t, p_v, _t0, e["t_end"])
                             if len(p_t) >= 2 else None)
        e["backup_tok"] = (_increase_between(b_t, b_v, _t0, e["t_end"])
                           if len(b_t) >= 2 else None)

    # ── HiCache configuration ─────────────────────────────────────────────
    _si: dict = {}
    try:
        from .report.l3_backend import (_get_server_info_raw,
                                        _hicache_backend_from_server_info)
        _si = dict(_get_server_info_raw(setup) or {})
        m.storage_backend = _hicache_backend_from_server_info(setup) or ""
    except Exception:
        pass
    _launch = str(_pick(setup, "Launch command", "launch_command",
                        "SGLang launch command", "sglang_launch_command",
                        "Reference launch command") or "")
    _lb = _LAUNCH_BACKEND_RE.search(_launch)
    m.launch_backend = _lb.group(1).lower() if _lb else ""
    for _src, _val in (
            ("SGLang server_info page_size", _si.get("page_size")),
            ("setup_details", _pick(setup, "Page size", "page_size",
                                    "HiCache page size"))):
        _ps = _sf(str(_val).split()[0], 0.0) if str(_val or "").strip() \
            else 0.0
        if _ps > 0:
            m.page_size, m.page_size_src = _ps, _src
            break
    if m.page_size is None:
        _, _pv, _psrc = _rows_by_time(sg, ["page_size"])
        if _pv and max(_pv) > 0:
            m.page_size, m.page_size_src = max(_pv), _psrc
        elif sg.exists():
            for _c in _csv_rows(sg)[0]:
                _mm = re.search(r"page_size\s*=\s*[\"']?(\d+)", str(_c))
                if _mm:
                    m.page_size = float(_mm.group(1))
                    m.page_size_src = f"page_size label on {_c} in {sg.name}"
                    break
    if m.page_size is None:
        _lp = _LAUNCH_PAGE_RE.search(_launch)
        if _lp:
            m.page_size = float(_lp.group(1))
            m.page_size_src = "--page-size in the launch command"


# ─── HTML report builder ──────────────────────────────────────────────────────

def _delta_cell(base: float, cur: float, lower_is_better: bool = False,
                fmt: str = ".1f", unit: str = "") -> str:
    """Return a <td> with delta % colouring relative to base."""
    # Treat zero current as N/A (missing data, not genuinely zero performance)
    if cur == 0:
        return "<td class='neutral'><span style='color:#475569'>N/A</span></td>"
    if base == 0:
        return f"<td class='neutral'>{cur:{fmt}}{unit}</td>"
    delta = (cur - base) / abs(base) * 100
    # Suppress tiny deltas (< 1%) as noise
    good = (delta < -1) if lower_is_better else (delta > 1)
    bad  = (delta >  1) if lower_is_better else (delta < -1)
    cls  = "good" if good else ("bad" if bad else "neutral")
    sign = "+" if delta >= 0 else ""
    return (f"<td class='{cls}'>{cur:{fmt}}{unit} "
            f"<span class='delta'>({sign}{delta:.1f}%)</span></td>")



def _esc(x: object) -> str:
    import html as _h
    return _h.escape(str(x))

# ---------------------------------------------------------------------------
# Tiering chain
# ---------------------------------------------------------------------------

_NOISE = 1.15          # ratios closer to 1 than this are not shown


def _tier_prefix(*runs: "RunMetrics") -> str:
    """The tier name these runs share, or "" when it is not shared or not known.

    A comparison whose whole point is L3 against L3.5 must not label a shared
    row with either name, so the caller falls back to neutral wording.

    One unknown tier is enough to force the neutral form: a run with no
    setup_details has no established tier, and borrowing the other run's name
    for a shared row would assert of that run something nothing measured.
    """
    names = [getattr(r, "tier_short", "") for r in runs]
    if not names or not all(names):
        return ""
    return names[0] if len(set(names)) == 1 else ""


def _store_word(*runs: "RunMetrics") -> str:
    """What to call the layer that measured a store-side row.

    Neutral unless every run's backend class is known and they agree, for the
    same reason as _tier_prefix.
    """
    classes = [getattr(r, "l3_backend_class", "") for r in runs]
    if not classes or not all(classes):
        return "backing store"
    uniq = set(classes)
    if uniq == {"local_ssd"}:
        return "local SSD store"
    if "local_ssd" not in uniq:
        return "memory node"
    return "backing store"


def build_chain_html(base: "RunMetrics", cmp_: "RunMetrics") -> str:
    """Ordered causal chain from tier sizing to end-user latency.

    Rows follow the stack, not the size of the change, because the point is
    that a configuration decision propagates through the store and the engine
    before it reaches latency.  Each row names the layer that measured it —
    the finding needs several subsystems on one timeline, and the table should
    show that rather than assert it.

    A row is omitted when the two runs agree within _NOISE, so the chain shows
    only links that actually moved.
    """
    def _r(a, b):
        """Ratio b/a, or a sentinel when the ratio is undefined.

        Four outcomes, because collapsing them is what crashed this report:

          None      at least one side was never measured, or both were zero
          math.inf  the baseline was zero and the comparison run was not
          0.0       the comparison run was zero and the baseline was not
          b / a     both measured and non-zero

        The previous version guarded `a in (None, 0)` and `b is None` but
        NOT `b == 0`, so a metric that was non-zero in the baseline and
        exactly zero in the comparison run returned 0.0 -- which is not
        None, and is less than 1, so the formatter below reached
        `1 / ratio` and the whole comparison died with "float division by
        zero". A tier with no SSD makes that ordinary rather than rare:
        several KV hops are legitimately zero on one side.

        The 0 -> non-zero direction returned None, which rendered as "—"
        and silently lost a finding: a hop that went from nothing to
        something is exactly as interesting as the reverse.
        """
        if a is None or b is None:
            return None
        if a == 0:
            # 0 -> 0 has no ratio either, and is not a change.
            return math.inf if b else None
        return b / a

    _p   = _tier_prefix(base, cmp_)
    _dram_label = f"{_p} DRAM tier (GB)" if _p else "Backing-store DRAM tier (GB)"
    _store = _store_word(base, cmp_)

    _file_label = (f"{_p} file tier / SSD (GB)" if _p
                   else "Backing-store file tier / SSD (GB)")

    rows = [
        # Both capacity rows are always shown when either run has a capacity.
        # They are the configuration the rest of the chain is a consequence
        # of, and a capacity held CONSTANT is the control: suppressing it as
        # an unchanged link leaves a reader unable to see that, say, the DRAM
        # front was identical and only the SSD tier behind it was added.
        ("Tier capacity", _dram_label, base.l35_dram_gb, cmp_.l35_dram_gb,
         "configuration", True),
        ("Tier capacity", _file_label, base.l35_file_gb, cmp_.l35_file_gb,
         "configuration", True),
        ("Fit", "evict : read ratio", base.evict_read_ratio,
         cmp_.evict_read_ratio, _store, False),
        ("Eviction", "evicted (GB)", base.evicted_gb, cmp_.evicted_gb,
         _store, False),
        ("Promotion", "promoted (GB)", base.promoted_gb, cmp_.promoted_gb,
         _store, True),
        ("Prefetch", "tokens prefetched", base.prefetched_tok,
         cmp_.prefetched_tok, "inference engine", False),
        ("Recompute", "tokens recomputed", base.recomputed_tok,
         cmp_.recomputed_tok, "inference engine", False),
        ("Latency", "TPOT (ms)", base.tpot_ms, cmp_.tpot_ms, "inference engine",
         False),
    ]

    out = []
    for link, metric, a, b, layer, always in rows:
        if a is None and b is None:
            continue
        ratio = _r(a, b)
        # A promotion row of 0 -> 0 is itself the finding, so it is kept even
        # though the ratio is undefined.
        if not always and ratio is not None and (1/_NOISE) < ratio < _NOISE:
            continue
        # Every undefined ratio gets its own rendering. "—" used to stand for
        # three different things, and one of them crashed before it could be
        # rendered at all.
        if ratio is None:
            rs = "—"
        elif ratio == 0:
            rs = "→ 0"
        elif ratio == math.inf:
            rs = "0 →"
        elif ratio >= 1:
            rs = f"{ratio:.2f}x"
        else:
            rs = f"{1/ratio:.2f}x lower"
        fa = "absent" if a is None else f"{a:,.1f}"
        fb = "absent" if b is None else f"{b:,.1f}"
        # A move to or from exactly zero is the largest change there is, so it
        # is highlighted. `ratio and ...` made 0.0 falsy and would have
        # styled a collapse to zero as an unremarkable row.
        cls = ("chain-hot"
               if ratio is not None and (ratio == 0 or ratio == math.inf
                                         or ratio >= 2 or ratio <= .5)
               else "chain-row")
        out.append(
            f'<tr class="{cls}"><td><b>{link}</b></td><td>{metric}</td>'
            f'<td class="num">{fa}</td><td class="num">{fb}</td>'
            f'<td class="num">{rs}</td><td class="layer">{layer}</td></tr>')

    if not out:
        return (f'<h2>Tiering chain — {_esc(base.label)} → {_esc(cmp_.label)}</h2>'
                '<p class="note">No link in the tiering chain differed by more '
                f'than {int((_NOISE-1)*100)}% between these two runs.</p>')

    # When the two runs are not the same kind of backing tier, the rows are
    # still measured the same way but they no longer isolate one variable:
    # the backend changed too. Say that above the table rather than letting a
    # ratio imply a controlled comparison.
    _mixed = ""
    _tiers = {r.label: (r.tier_name or "unknown") for r in (base, cmp_)}
    if len({v for v in _tiers.values()}) > 1:
        _mixed = ('<p class="note"><b>Different backing tiers:</b> '
                  + "; ".join(f"{_esc(k)} = {_esc(v)}" for k, v in _tiers.items())
                  + '. Ratios below span a change of backend class, so they are '
                    'not attributable to any single setting.</p>')

    return (
        # The pair is named in the heading because there is one chain per
        # comparison run, and two identically titled tables would be read as
        # one table repeated.
        f'<h2>Tiering chain — {_esc(base.label)} → {_esc(cmp_.label)}</h2>'
        '<p class="note">From configuration to latency. Rows follow the stack. '
        'Each is measured by a different layer; links within '
        f'{int((_NOISE-1)*100)}% are omitted.</p>'
        + _mixed +
        '<table class="chain"><thead><tr>'
        f'<th>Link</th><th>Measurement</th><th>{_esc(base.label)}</th>'
        f'<th>{_esc(cmp_.label)}</th><th>Ratio</th><th>Measured by</th>'
        '</tr></thead><tbody>' + "".join(out) + '</tbody></table>')


def _fmt_layer_val(v: "float | None", unit: str = "", fmt: str = ",.0f") -> str:
    """Render one layer-walk cell, keeping absent distinct from zero.

    A counter that was never exported and a counter that stayed at zero are
    different findings. Collapsing both to "0" is what made a device appear
    to move 33 MB/s at 0 IOPS.
    """
    if v is None:
        return '<span style="color:#475569">not exported</span>'
    # A provenance row carries text, not a number: "model config (exact)"
    # belongs beside the KB/token it produced, and a format spec for floats
    # would raise on it.
    if isinstance(v, str):
        return _esc(v)
    return f"{v:{fmt}}{unit}"


def build_layer_walk_html(metrics: "list[RunMetrics]") -> str:
    """Compare the runs layer by layer, A5 down to A1.

    The chain table answers "what changed"; this answers "where in the stack
    is it visible". Rows follow one token down the stack: the engine's own
    token activity, then each KV hop between tiers, then the GPU, host DRAM,
    block layer and device that carry those hops.

    Every row names the layer that measured it and keeps absent distinct from
    zero, so a row of "not exported" reads as a gap in telemetry rather than
    as an idle subsystem.
    """
    if len(metrics) < 2:
        return ""

    labels = [_esc(m.label) for m in metrics]
    _p  = _tier_prefix(*metrics)
    _T  = _p or "L3/L3.5"
    _sw = _store_word(*metrics)

    # (section title, what measured it, [(row label, accessor, unit, fmt)])
    _G = "float | None"
    sections: "list[tuple[str, str, str, list]]" = [
        ("A5 · Application and inference engine",
         "SGLang request and token counters",
         "Token activity as the engine reports it. Prompt tokens are the "
         "prefill demand; cached and recomputed are how that demand was met. "
         "Rows marked derived are computed from a gauge rather than counted, "
         "and the check rows reconcile them against the measured counter — a "
         "residual above a per cent or two means the hit-rate gauge and the "
         "token counters disagree, and anything derived from the gauge "
         "inherits that. KV generated is the KV the GPUs actually computed "
         "\u2014 prompt minus cached, plus decode \u2014 since a prefill "
         "token served from cache reuses KV rather than generating it. Its "
         "byte figure is full-model across all ranks and requires an EXACT "
         "architecture from the model config, so it is absent unless "
         "--model-path was given: the resolver's fallback size hint gives "
         "256 KB/token on this model where the config gives 960, and a "
         "3.75x-wrong constant under a figure that is already an upper "
         "bound would be worth nothing. The row below it names the source.",
         [("Prompt tokens (prefill demand) · measured",
           lambda m: m.prompt_tok, "", ",.0f"),
          # Several deployments export only realtime_tokens_total{mode=...}
          # and none of the named totals, in which case each of these three
          # is summed from the phase counters the way the single-run report
          # sums them. A figure that was derived says so in its own row
          # rather than passing as a counter read straight off the exporter.
          ("↳ where prompt tokens came from",
           lambda m: (m.token_src or {}).get("prompt") or None, "", ""),
          ("Generated tokens · measured",    lambda m: m.gen_tok, "", ",.0f"),
          ("↳ where generated tokens came from",
           lambda m: (m.token_src or {}).get("gen") or None, "", ""),
          ("Prefill tokens served from cache · measured",
           lambda m: m.cached_tok, "", ",.0f"),
          ("↳ where cached tokens came from",
           lambda m: (m.token_src or {}).get("cached") or None, "", ""),
          # Recomputed is DERIVED from the hit-rate gauge, not counted:
          #   total = cached / (hit% / 100);  recomputed = total - cached
          # so it inherits whatever the gauge is averaging over.
          ("Prefill tokens recomputed · derived from hit %",
           lambda m: m.recomputed_tok, "", ",.0f"),
          # The audit of that derivation: cached + recomputed should equal
          # the measured prompt-token counter. A residual means the gauge and
          # the counters disagree, and every figure derived from the gauge --
          # recomputed, the counterfactual, the GPU-time floor -- carries
          # that disagreement. Showing it beside its inputs is the only way
          # the reader can check the arithmetic.
          ("↳ cached + recomputed · check",
           lambda m: ((m.cached_tok + m.recomputed_tok)
                      if (m.cached_tok is not None
                          and m.recomputed_tok is not None) else None),
           "", ",.0f"),
          ("↳ residual vs prompt tokens · check",
           lambda m: ((m.cached_tok + m.recomputed_tok - m.prompt_tok)
                      / m.prompt_tok * 100.0
                      if (m.cached_tok is not None
                          and m.recomputed_tok is not None
                          and m.prompt_tok) else None),
           "%", "+,.2f"),
          # KV actually COMPUTED, which is what the hierarchy exists to
          # avoid. prompt - cached + decode: a prefill token served from the
          # prefix cache reuses KV rather than generating any, so counting
          # all prompt tokens would overstate this by the hit rate -- about
          # twentyfold on these runs. Both terms are measured counters, so
          # unlike the recomputed row above this does not inherit the
          # hit-rate gauge's error; the check rows show how far apart the two
          # routes are.
          ("KV generated · tokens computed",
           lambda m: m.kv_generated_tok, "", ",.0f"),
          ("KV generated · bytes",
           lambda m: m.kv_generated_gb, " GB", ",.1f"),
          ("↳ KV bytes per token used",
           lambda m: m.kv_bytes_tok_kb, " KB", ",.0f"),
          # The resolver's own source string already says ESTIMATE for a
          # size hint, so only an inexact source that does NOT say so gets
          # the suffix -- otherwise the cell read "... (ESTIMATE ...) —
          # ESTIMATE".
          # "↳ where that came from" until the token rows above gained their
          # own provenance rows and "that" stopped having one referent.
          ("↳ where the KV geometry came from",
           lambda m: ((m.kv_bytes_src
                       + ("" if (m.kv_bytes_exact
                                 or "estimate" in m.kv_bytes_src.lower())
                          else " — ESTIMATE"))
                      if m.kv_bytes_src else None), "", ""),
          ("↳ with no cache at all · counterfactual",
           lambda m: m.kv_demand_gb, " GB", ",.1f"),
          ("↳ avoided by the hierarchy",
           lambda m: m.kv_avoided_gb, " GB", ",.1f"),
          ("Cache hit % (gauge)",            lambda m: m.cache_hit_pct or None, "%", ",.2f"),
          ("↳ where the cache hit % came from",
           lambda m: (m.token_src or {}).get("cache_hit") or None, "", ""),
          # The statistic travels with the figure. The resolution order mixes
          # means (the counter delta, the summary) with a MEDIAN (the
          # per-interval p50 fallback), and on these runs the two differ by
          # two orders of magnitude -- 79,341 ms against 598 ms on one
          # 30-minute window. A row headed "TTFT" is only comparable across
          # runs when both runs resolved the same statistic, which is what
          # this row lets the reader check.
          ("TTFT",                           lambda m: m.ttft_ms or None, " ms", ",.0f"),
          ("↳ which statistic that is",
           lambda m: (m.latency_statistic or {}).get("ttft") or None, "", ""),
          # The percentiles beside the mean, so the mean can be read against
          # its own distribution rather than against the other run's mean.
          # A mean an order of magnitude above its own p50 is queue wait.
          ("↳ TTFT p50",
           lambda m: (m.lat_pct_ms or {}).get(("ttft", 0.5)), " ms", ",.0f"),
          ("↳ TTFT p90",
           lambda m: (m.lat_pct_ms or {}).get(("ttft", 0.9)), " ms", ",.0f"),
          ("↳ TTFT p99",
           lambda m: (m.lat_pct_ms or {}).get(("ttft", 0.99)), " ms", ",.0f"),
          ("↳ mean ÷ its own p50 · tail",
           lambda m: m.tail_ratio_for("ttft"), "x", ",.1f"),
          ("↳ bucket-limited?",
           lambda m: ("yes — " + (m.lat_bucket_note or {}).get(("ttft", 0.5), ""))
                     if (m.lat_bucket_note or {}).get(("ttft", 0.5)) else None,
           "", ""),
          ("↳ how TTFT was resolved",
           lambda m: (m.latency_method or {}).get("ttft") or None, "", ""),
          # A mean over four requests and one over six thousand are not
          # comparable, and nothing else on the row says which this is.
          ("↳ observations in the window",
           lambda m: (m.latency_obs or {}).get("ttft") or None, "", ",.0f"),
          ("TPOT",                           lambda m: m.tpot_ms or None, " ms", ",.1f"),
          ("↳ which statistic that is",
           lambda m: (m.latency_statistic or {}).get("tpot") or None, "", ""),
          ("End-to-end latency",             lambda m: m.e2e_ms or None, " ms", ",.0f"),
          ("↳ which statistic that is",
           lambda m: (m.latency_statistic or {}).get("e2e") or None, "", ""),
          ("Throughput",                     lambda m: m.throughput_tok_s or None, " tok/s", ",.1f"),
          ("↳ where throughput came from",
           lambda m: (m.token_src or {}).get("throughput") or None, "", ""),
          # The window mean above and the active-span mean here. When the
          # window was bounded by the workload these agree; when they do
          # not, the gap IS the dead time, and the row above is comparing
          # how long each window was left running.
          ("↳ over the ACTIVE span only",
           lambda m: m.active_output_tok_s, " tok/s", ",.1f"),
          ("↳ window the workload was alive for",
           lambda m: (m.active_frac * 100.0) if m.active_frac is not None
                     else None, "%", ",.0f"),
          ("↳ idle at the end of the window",
           lambda m: (m.trail_idle_s / 60.0) if m.trail_idle_s else None,
           " min", ",.1f"),
          ("↳ how that was measured",
           lambda m: m.active_src or None, "", ""),
          # Total HBM is dominated by the weights -- it read 265.0 against
          # 265.1 GB on two runs whose KV pools differed 1.57x -- so the
          # pool gets its own rows.
          ("L1 HBM KV pool · mean resident",
           lambda m: m.l1_kv_tok_mean, " tok", ",.0f"),
          ("↳ peak resident",
           lambda m: m.l1_kv_tok_peak, " tok", ",.0f"),
          ("↳ pool capacity",
           lambda m: m.l1_kv_cap_tok, " tok", ",.0f"),
          ("↳ mean fill",
           lambda m: (m.l1_kv_tok_mean / m.l1_kv_cap_tok * 100.0)
                     if (m.l1_kv_tok_mean and m.l1_kv_cap_tok) else None,
           "%", ",.1f"),
          ]),
        ("CROSS · KV movement between tiers",
         "engine-side hop counters",
         f"One row per hop, top of the hierarchy downwards and back. "
         f"Down-moves are eviction and backup; up-moves are prefetch and "
         f"load-back. A hierarchy that moves far more down than up is a "
         f"sink rather than a cache.",
         [("evict · L1 (HBM) → L2 (host DRAM)", lambda m: m.evicted_tok, " tok", ",.0f"),
          (f"backup · L2 → {_T}",               lambda m: m.backuped_tok, " tok", ",.0f"),
          (f"prefetch · {_T} → L2",             lambda m: m.prefetched_tok, " tok", ",.0f"),
          ("load-back · L2 → L1 (HBM)",         lambda m: m.load_back_tok, " tok", ",.0f"),
          ]),
        (f"CROSS · {_T} store, its own view",
         f"{_sw} counters",
         "What the backing store itself recorded, independent of the "
         "engine's counters. Gets that hit in the store's DRAM tier never "
         "reach its SSD, so they appear in no device counter.",
         [("Gets (requests served)",      lambda m: m.store_get_n, "", ",.0f"),
          ("Hits in the DRAM tier",       lambda m: m.store_mem_hit_n, "", ",.0f"),
          ("Hits in the file tier (SSD)", lambda m: m.store_file_hit_n, "", ",.0f"),
          ("Bytes served from DRAM tier", lambda m: m.mem_hit_gb, " GB", ",.1f"),
          ("Bytes served from file tier", lambda m: m.file_hit_gb, " GB", ",.1f"),
          ("Evicted from the store",      lambda m: m.evicted_gb, " GB", ",.1f"),
          ("Promoted SSD → DRAM tier",    lambda m: m.promoted_gb, " GB", ",.1f"),
          ("DRAM-tier capacity",          lambda m: m.l35_dram_gb, " GB", ",.1f"),
          ("File-tier capacity",          lambda m: m.l35_file_gb, " GB", ",.1f"),
          ]),
        ("A4 · GPU and HBM",
         "DCGM / nvidia-smi",
         "Where the recompute that a cache miss causes is actually paid for.",
         [("GPU utilisation",      lambda m: m.gpu_util_pct or None, "%", ",.1f"),
          ("GPU utilisation peak", lambda m: m.gpu_util_peak or None, "%", ",.1f"),
          ("DCGM HBM BW active",   lambda m: m.dcgm_active_pct or None, "%", ",.1f"),
          ("HBM used",             lambda m: m.hbm_used_gb or None, " GB", ",.1f"),
          ("HBM fill",             lambda m: m.hbm_pct or None, "%", ",.1f"),
          ("GPU power",            lambda m: m.gpu_power_w or None, " W", ",.0f"),
          ]),
        ("A3 · Host DRAM",
         "AMDuProf / Intel PCM memory counters",
         "The physical layer L2 HiCache occupies. Evict and load-back traffic "
         "crosses it, as does every byte the store's DRAM tier serves when "
         "the store runs on this host.",
         [("Total bandwidth", lambda m: m.dram_total_bw_gbs or None, " GB/s", ",.2f"),
          ("Read bandwidth",  lambda m: m.dram_rd_bw_gbs or None, " GB/s", ",.2f"),
          ("Write bandwidth", lambda m: m.dram_wr_bw_gbs or None, " GB/s", ",.2f"),
          ("Peak bandwidth",  lambda m: m.dram_peak_bw_gbs or None, " GB/s", ",.2f"),
          ]),
        ("A2 · Block layer and NVMe driver",
         "sysfs / blktrace / biosnoop",
         "The requests the kernel actually issued. Backup and prefetch "
         "bytes should be visible here when the tier is a local SSD; for a "
         "memory node they appear on that node's device, not this host's.",
         [("Read bandwidth",   lambda m: m.nvme_rd_bw_mbs or None, " MB/s", ",.1f"),
          # A bandwidth figure on its own says nothing about whether the
          # device was the constraint. 1.3 MB/s reads as a small number and
          # 255 MB/s as a large one; against a 7,000 / 5,000 MB/s device
          # they are 0.019% and 5.1%, and neither is a bottleneck.
          ("↳ % of the device's read target",
           lambda m: m.rd_headroom_pct, "%", ",.3f"),
          ("Write bandwidth",  lambda m: m.nvme_wr_bw_mbs or None, " MB/s", ",.1f"),
          ("↳ % of the device's write target",
           lambda m: m.wr_headroom_pct, "%", ",.2f"),
          ("↳ where those targets came from",
           lambda m: m.dev_target_src or None, "", ""),
          ("Read IOPS",        lambda m: m.nvme_rd_iops or None, "", ",.0f"),
          ("Queue depth mean", lambda m: m.nvme_qd_mean, "", ",.2f"),
          ("Queue depth peak", lambda m: m.nvme_qd_peak, "", ",.0f"),
          ("Read latency",     lambda m: m.nvme_rd_lat_ms or None, " ms", ",.3f"),
          ("Write latency",    lambda m: m.nvme_wr_lat_ms or None, " ms", ",.3f"),
          ("Device utilisation", lambda m: m.nvme_util_pct or None, "%", ",.1f"),
          # The question "is this tier a cache or a sink", which the two
          # byte totals answered only if the reader divided them. On the
          # reference runs it was 0.51%: the tier absorbed 747 GB and gave
          # back 3.8 GB, so nothing about its media could be saving read
          # latency, because it was barely serving reads.
          ("Bytes read back ÷ bytes written",
           lambda m: m.read_back_pct, "%", ",.2f"),
          ]),
        ("A1 · SSD hardware",
         "NVMe SMART / device counters",
         "The bottom of the stack. Host-written against NAND-written gives "
         "write amplification, which is what KV backup traffic costs the "
         "device in endurance.",
         [("Bytes read",      lambda m: m.read_total_gb or None, " GB", ",.1f"),
          ("Bytes written",   lambda m: m.write_total_gb or None, " GB", ",.1f"),
          ("Host written",    lambda m: m.host_written_gb, " GB", ",.1f"),
          ("NAND written",    lambda m: m.nand_written_gb, " GB", ",.1f"),
          ("Write amplification",
           lambda m: ((m.nand_written_gb / m.host_written_gb)
                      if (m.nand_written_gb and m.host_written_gb) else None),
           "x", ",.2f"),
          ]),
    ]

    out = []
    for title, measured_by, note, rows in sections:
        body = ""
        for row_label, acc, unit, fmt in rows:
            vals = [acc(m) for m in metrics]
            # A row where no run exported the counter says nothing; drop it.
            if all(v is None for v in vals):
                continue
            cells = "".join(
                f"<td class='num'>{_fmt_layer_val(v, unit, fmt)}</td>"
                for v in vals)
            body += (f"<tr class='chain-row'><td>{_esc(row_label)}</td>"
                     f"{cells}</tr>")
        if not body:
            out.append(
                f'<h3 class="layer-h">{_esc(title)}</h3>'
                f'<p class="note">Nothing at this layer was exported by any '
                f'of these runs, so it cannot be compared. '
                f'Measured by: {_esc(measured_by)}.</p>')
            continue
        header = ("<tr><th>Measurement</th>"
                  + "".join(f"<th>{l}</th>" for l in labels) + "</tr>")
        out.append(
            f'<h3 class="layer-h">{_esc(title)}'
            f'<span class="layer-by">{_esc(measured_by)}</span></h3>'
            f'<p class="note">{_esc(note)}</p>'
            f'<table class="chain"><thead>{header}</thead>'
            f'<tbody>{body}</tbody></table>')

    return ('<h2>Layer-by-layer comparison — A5 down to A1</h2>'
            '<p class="note">The same run, read at each layer of the stack. '
            'A figure shown as <i>not exported</i> was never published by '
            'that run\'s collectors — it is a gap in telemetry, not an idle '
            'subsystem.</p>' + "".join(out))


def build_queue_depth_html(metrics: "list[RunMetrics]") -> str:
    """Compare queueing at every layer that exposes it, and say where none is.

    The comparison carried exactly two queue rows, both in the A2 table, both
    fed by one field that read the first of avgqu_sz / l35_avgqu_sz /
    bt_qd_mean to return anything. Three problems followed from that:

    * A local-SSD run and an L3.5 run were compared on one row whose cells
      measured different devices on different hosts, with nothing saying so.
    * The inference scheduler's own queue -- the only queue in the stack that
      is a plain count of waiting work, and the one that decides whether a
      run was admission-bound -- was not compared at all.
    * Network and DRAM were absent, which is defensible only if the report
      says WHY: neither layer exposes a queue depth to read.

    So each layer gets its own rows, each row names the column and file it
    came from, and a layer with no queue to read is listed with the proxy
    that stands in for one and marked as a proxy. A per-cent-of-peak is not a
    queue depth, and labelling one as such is the error this section exists
    to prevent.
    """
    if len(metrics) < 2:
        return ""

    labels = [_esc(m.label) for m in metrics]

    # (layer, row label, accessor, unit, fmt, kind, what measured it)
    #   kind "queue" -> a real count of coexisting or waiting work
    #   kind "proxy" -> the layer exposes no queue; this stands in for one
    rows: "list[tuple[str, str, Any, str, str, str, str]]" = [
        ("A5 · inference scheduler",
         "Requests waiting to enter prefill · mean",
         lambda m: m.sg_queue_reqs_mean, "", ",.2f", "queue",
         "sglang num_queue_reqs"),
        ("A5 · inference scheduler",
         "Requests waiting to enter prefill · peak",
         lambda m: m.sg_queue_reqs_peak, "", ",.0f", "queue",
         "sglang num_queue_reqs"),
        ("A5 · inference scheduler",
         "Concurrent decode batch · mean",
         lambda m: m.sg_running_reqs_mean, "", ",.2f", "queue",
         "sglang num_running_reqs"),
        ("A5 · inference scheduler",
         "Concurrent decode batch · peak",
         lambda m: m.sg_running_reqs_peak, "", ",.0f", "queue",
         "sglang num_running_reqs"),
        ("A3 · host DRAM",
         "Bandwidth used, share of configured platform peak · <b>proxy</b>",
         lambda m: m.dram_bw_pct_of_peak, "%", ",.1f", "proxy",
         "no memory-controller queue is exposed; needs 'DRAM peak GB/s' in "
         "setup details, and is NOT the run's own observed maximum"),
        ("A3 · host DRAM",
         "Platform peak the share is taken against",
         lambda m: m.dram_peak_ref_gbs, " GB/s", ",.1f", "proxy",
         "from setup details, so the denominator is visible"),
        ("A2/A1 · this host's block device",
         "Queue depth · mean",
         lambda m: m.l3_qd_mean, "", ",.3f", "queue",
         "diskstats field 11 / in-flight"),
        ("A2/A1 · this host's block device",
         "Queue depth · peak",
         lambda m: m.l3_qd_peak, "", ",.0f", "queue",
         "diskstats field 11 / in-flight"),
        ("A2/A1 · the memory node's block device",
         "Queue depth · mean",
         lambda m: m.l35_qd_mean, "", ",.3f", "queue",
         "diskstats field 11 on the L3.5 node"),
        ("A2/A1 · the memory node's block device",
         "Queue depth · peak",
         lambda m: m.l35_qd_peak, "", ",.0f", "queue",
         "diskstats field 11 on the L3.5 node"),
        ("A2/A1 · exact blktrace Q→C",
         "Queue depth · mean", lambda m: m.bt_qd_mean, "", ",.3f", "queue",
         "per-I/O queue and completion events"),
        ("A2/A1 · exact blktrace Q→C",
         "Queue depth · peak", lambda m: m.bt_qd_peak, "", ",.0f", "queue",
         "per-I/O queue and completion events"),
        ("NET · fabric",
         "TCP retransmits per second · <b>proxy</b>",
         lambda m: m.net_retrans_ps_mean, "/s", ",.2f", "proxy",
         "no NIC queue is exposed; a retransmit implies one overflowed"),
        ("NET · fabric",
         "Receive drops per second · <b>proxy</b>",
         lambda m: m.net_rx_drop_ps_mean, "/s", ",.2f", "proxy",
         "no NIC queue is exposed; a drop implies one overflowed"),
        ("NET · fabric",
         "Link utilisation · <b>proxy</b>",
         lambda m: m.net_link_util_pct_mean, "%", ",.1f", "proxy",
         "no NIC queue is exposed — share of link speed"),
    ]

    # Group in declaration order, keeping only layers some run measured.
    groups: "list[tuple[str, list]]" = []
    for layer, label, acc, unit, fmt, kind, by in rows:
        vals = [acc(m) for m in metrics]
        if all(v is None for v in vals):
            continue
        if not groups or groups[-1][0] != layer:
            groups.append((layer, []))
        groups[-1][1].append((label, vals, unit, fmt, kind, by))

    # Which source each run's device rows came from, named once per run so a
    # cell can be traced to a column in a file rather than taken on trust.
    _srcs = []
    for m in metrics:
        _bits = [f"{_esc(m.label)}: "
                 + ", ".join(
                     x for x in (
                         f"this host from <code>{_esc(m.l3_qd_src)}</code>"
                         if m.l3_qd_src else "",
                         f"memory node from <code>{_esc(m.l35_qd_src)}</code>"
                         if m.l35_qd_src else "",
                         f"blktrace from <code>{_esc(m.bt_qd_source)}</code>"
                         if m.bt_qd_source else "",
                     ) if x) or "no device queue series"]
        _srcs.append("".join(_bits))

    if not groups:
        return ('<h2>Queueing across the stack</h2>'
                '<p class="note">No run in this comparison exported a queue '
                'depth or a pressure proxy at any layer. Queue depth needs '
                'node_exporter with <code>--collector.diskstats</code>, an '
                'amoprof <code>nvme_driver</code> or <code>iostat</code> '
                'collector, or blktrace; on a multipath NVMe namespace it is '
                'the per-controller path name (nvmeXcYnZ) that carries the '
                'field, not the namespace head.</p>')

    out = []
    for layer, items in groups:
        body = ""
        for label, vals, unit, fmt, kind, by in items:
            cells = "".join(
                f"<td class='num'>{_fmt_layer_val(v, unit, fmt)}</td>"
                for v in vals)
            # A proxy row is tinted and carries its own reason, so it cannot
            # be read as a queue depth by someone skimming the column.
            _k = ('<span style="color:#b45309">proxy</span>' if kind == "proxy"
                  else '<span style="color:#15803d">measured queue</span>')
            body += (f"<tr class='chain-row'><td>{label}"
                     f"<br><span class='layer-by' style='margin:0'>{_k} · "
                     f"{by}</span></td>{cells}</tr>")
        header = ("<tr><th>Measurement</th>"
                  + "".join(f"<th>{l}</th>" for l in labels) + "</tr>")
        out.append(
            f'<h3 class="layer-h">{_esc(layer)}</h3>'
            f'<table class="chain"><thead>{header}</thead>'
            f'<tbody>{body}</tbody></table>')

    return ('<h2>Queueing across the stack</h2>'
            '<p class="note">Where work waited, at each layer that exposes a '
            'queue — and, for the layers that expose none, the proxy that '
            'stands in for one, marked as a proxy. A share-of-peak or a '
            'retransmit rate is not a queue depth and is not comparable with '
            'one; only rows marked <span style="color:#15803d">measured '
            'queue</span> count coexisting or waiting work. '
            'This host\'s device and the memory node\'s are separate rows: '
            'they are different devices on different hosts, and one row for '
            'both would compare two unlike things.</p>'
            '<p class="note">Sources — ' + " · ".join(_srcs) + '</p>'
            + "".join(out))


def build_suspect_banner(runs: "list[RunMetrics]") -> str:
    """Name figures this report cannot stand behind, before they are read.

    Three conditions have each produced a confident wrong reading:

    * End-to-end latency exactly equal to TTFT within a run. One of the two
      gauges is almost certainly standing in for the other, and the KPI table
      then reports a delta on both as if they were independent measurements.

    * A figure byte-identical across runs whose windows differ. Two separate
      windows do not agree to seven significant figures; a lifetime average
      scraped as a window value does.

    * Durations differing by more than 2x. Any rate or mean is then taken
      over very different spans, so the comparison is between differently
      smoothed quantities.

    The banner states the condition and which runs it affects, and does not
    guess the cause.
    """
    msgs: "list[str]" = []

    # 1. E2E == TTFT exactly.
    _same = [r for r in runs
             if r.e2e_ms and r.ttft_ms and abs(r.e2e_ms - r.ttft_ms) < 1e-6]
    if _same:
        msgs.append(
            "<b>End-to-end latency equals TTFT exactly</b> for "
            + ", ".join(_esc(r.label) for r in _same)
            + ". One of the two gauges is standing in for the other, so "
              "neither that figure nor any delta computed from it is "
              "evidence here.")

    # 2. A figure identical across runs with different windows.
    def _win(r):
        # RunMetrics carries the window as the rendered string plus its
        # length; that pair identifies it for this purpose.
        return (r.window_str or "", round(r.duration_min, 3))
    _distinct_windows = len({_win(r) for r in runs}) > 1
    if _distinct_windows:
        _dup: "list[str]" = []
        for _lab, _attr in (("TTFT", "ttft_ms"), ("TPOT", "tpot_ms"),
                            ("end-to-end latency", "e2e_ms"),
                            ("throughput", "throughput_tok_s"),
                            ("cache hit %", "cache_hit_pct")):
            _vals = [getattr(r, _attr, 0.0) or 0.0 for r in runs]
            _nz = [v for v in _vals if v]
            if len(_nz) < 2:
                continue
            # Identical to 1e-9 relative across at least two runs whose
            # windows differ.
            for _i in range(len(_vals)):
                for _j in range(_i + 1, len(_vals)):
                    _a, _b = _vals[_i], _vals[_j]
                    if not (_a and _b):
                        continue
                    if _win(runs[_i]) == _win(runs[_j]):
                        continue
                    if abs(_a - _b) <= abs(_a) * 1e-9:
                        _dup.append(
                            f"{_lab} is identical for "
                            f"{_esc(runs[_i].label)} and "
                            f"{_esc(runs[_j].label)} ({_a:,.5f})")
        if _dup:
            msgs.append(
                "<b>A figure repeats across runs with different windows:</b> "
                + "; ".join(sorted(set(_dup)))
                + ". Separate windows do not agree to this precision, so "
                  "that figure is not window-scoped and must be re-derived "
                  "before it is compared.")

    # 3b. A latency that is not window-scoped.
    #
    # When neither the window counters nor the percentile series are
    # available, the figure comes from sglang_summary.json -- which the fetch
    # may have filled from last(sum)/last(count), the server's LIFETIME mean.
    # A delta between two lifetime means is not a comparison of two windows,
    # and nothing in the number itself says which it is.
    _unscoped: "list[str]" = []
    for r in runs:
        _bad = sorted(k for k, v in (getattr(r, "latency_window_scoped", {})
                                     or {}).items() if v is False
                      and getattr(r, {"ttft": "ttft_ms", "tpot": "tpot_ms",
                                      "e2e": "e2e_ms"}[k], 0.0))
        if _bad:
            _unscoped.append(f"{_esc(r.label)} ({', '.join(_bad).upper()})")
    if _unscoped:
        msgs.append(
            "<b>A latency here is not verified as window-scoped:</b> "
            + "; ".join(_unscoped)
            + ". Those came from sglang_summary.json because neither the "
              "window counters nor the percentile series were available, and "
              "the fetch fills that field from last(sum)/last(count) when the "
              "window delta is zero — the server's lifetime mean, not this "
              "window's. Any delta computed from one is not a comparison of "
              "two windows.")

    # 3. Duration spread.
    _durs = [r.duration_min for r in runs if r.duration_min > 0]
    if len(_durs) >= 2 and max(_durs) > 2 * min(_durs):
        msgs.append(
            f"<b>Window lengths differ by {max(_durs)/min(_durs):.1f}x</b> "
            f"({min(_durs):.0f} min to {max(_durs):.0f} min). Means and "
            f"rates are taken over very different spans, so a difference "
            f"between them may be a difference in smoothing.")

    # 4. A window that outlived its workload.
    #
    # This is the condition the 2x duration guard above does not catch and
    # that cost the most: two runs over 1,800 s and 2,925 s -- 1.63x, so the
    # guard stayed silent -- where the longer window was 35% dead because
    # its workload had finished inside it. Output throughput, GPU
    # utilisation and HBM bandwidth all favoured the shorter window, and all
    # three reversed once the dead time was taken out.
    _dead = [r for r in runs
             if r.trail_idle_s and r.duration_min > 0
             and r.trail_idle_s > 0.10 * r.duration_min * 60.0]
    for r in _dead:
        _frac = (r.active_frac or 0.0) * 100.0
        _corr = r.active_output_tok_s
        msgs.append(
            f"<b>{_esc(r.label)}'s window outlived its workload:</b> "
            f"{r.trail_idle_s/60.0:,.0f} min of its "
            f"{r.duration_min:,.0f}-min window were idle at the end, and it "
            f"was active for {_frac:,.0f}% of the window"
            + (f" ({_esc(r.active_src)})" if r.active_src else "")
            + ". Every time-average for this run is diluted by that dead "
              "time"
            + (f" — output throughput is {r.throughput_tok_s:,.1f} tok/s "
               f"over the window and {_corr:,.1f} tok/s over the active "
               f"span" if _corr and r.throughput_tok_s else "")
            + ". Re-run the analysis with the window bounded by the "
              "benchmark's own start and end before comparing rates.")

    # 5. Active fractions that differ, which makes the time-averages
    #    incomparable even when both windows look reasonable on their own.
    _afs = [(r.label, r.active_frac) for r in runs if r.active_frac is not None]
    if len(_afs) >= 2:
        _lo = min(_afs, key=lambda x: x[1])
        _hi = max(_afs, key=lambda x: x[1])
        if _hi[1] - _lo[1] > 0.15 and _hi[0] != _lo[0]:
            # The active-span correction assumes the idle time was the
            # workload's. When most of it was a stall -- requests waiting,
            # GPUs idle -- it was the system's, and dividing it out credits
            # the slower run with time it spent not serving its queue. That
            # is how a run that finished 1.66x later read as the faster one.
            _lo_run = next((r for r in runs if r.label == _lo[0]), None)
            _idle = _lo_run.idle_s if _lo_run is not None else None
            _stalled = (_lo_run is not None and _lo_run.stall_present
                        and _idle and (_lo_run.stall_s or 0) >= 0.5 * _idle)
            if _stalled:
                msgs.append(
                    f"<b>These runs were not alive for the same share of "
                    f"their windows:</b> {_esc(_hi[0])} {_hi[1]*100:,.0f}% "
                    f"against {_esc(_lo[0])} {_lo[1]*100:,.0f}%. But "
                    f"{_lo_run.stall_s/60.0:,.1f} of {_esc(_lo[0])}'s "
                    f"{_idle/60.0:,.1f} idle minutes were stalls — requests "
                    f"waiting while the GPUs sat idle — so that idle time "
                    f"belongs to the system, not to the workload. Do not "
                    f"correct it away: the active-span rows below excuse "
                    f"exactly the stall. Compare time to complete and request "
                    f"throughput in the Verdict and Workload sections.")
            else:
                msgs.append(
                    f"<b>These runs were not alive for the same share of "
                    f"their windows:</b> {_esc(_hi[0])} {_hi[1]*100:,.0f}% "
                    f"against {_esc(_lo[0])} {_lo[1]*100:,.0f}%. A window "
                    f"mean is a property of the system only when the window "
                    f"is a property of the workload, so compare the "
                    f"active-span rows below, not the window means.")

    # 6. A percentile that is a bucket boundary rather than a measurement.
    _edge: "list[str]" = []
    for r in runs:
        for (_k, _q), _note in sorted((r.lat_bucket_note or {}).items()):
            _v = (r.lat_pct_ms or {}).get((_k, _q))
            _edge.append(f"{_esc(r.label)} {_k.upper()} p{int(_q*100)} "
                         f"= {_v:,.2f} ms {_note}")
    if _edge:
        msgs.append(
            "<b>A percentile here is bucket-limited:</b> "
            + "; ".join(_edge)
            + ". Comparing it against another run's figure treats a bucket "
              "boundary as a measurement. Add histogram buckets around that "
              "range before reading a difference.")

    # 7. A mean that is almost entirely tail, which is queueing and not
    #    service time -- so a delta on it is a delta on admission, and the
    #    storage tier is not what moves it.
    _tails: "list[str]" = []
    for r in runs:
        for _k in ("ttft", "tpot", "e2e"):
            _tr = r.tail_ratio_for(_k)
            if _tr and _tr >= 10.0:
                _p50 = (r.lat_pct_ms or {}).get((_k, 0.5))
                _mean = {"ttft": r.ttft_ms, "tpot": r.tpot_ms,
                         "e2e": r.e2e_ms}[_k]
                _tails.append(
                    f"{_esc(r.label)} {_k.upper()} mean {_mean:,.0f} ms is "
                    f"{_tr:,.0f}x its own p50 of {_p50:,.0f} ms")
    if _tails:
        msgs.append(
            "<b>A mean here is almost all tail:</b> " + "; ".join(_tails)
            + ". A mean that far above its own median is queue wait rather "
              "than service time, so a difference between two such means is "
              "a difference in admission, not in the tier being compared.")

    if not msgs:
        return ""
    return ('<div class="banner warn"><b>Figures this report cannot stand '
            'behind.</b><ul style="margin:6px 0 0;padding-left:20px">'
            + "".join(f"<li>{m}</li>" for m in msgs)
            + "</ul></div>")


def build_ruled_out_banner(runs: "list[RunMetrics]") -> str:
    """State what the telemetry positively rules out, not just what to doubt.

    The suspect banner says which figures cannot be trusted. This one says
    which explanations the measurements have already eliminated, which is
    the more useful half and the half a reader otherwise has to assemble by
    hand from rows several sections apart.

    Two conditions, both of which held on the reference runs and neither of
    which the report stated:

    * The tier is a write sink. It absorbed 747 GB and returned 3.8 GB --
      0.51%. A tier that is not serving reads cannot be where read latency
      is saved, so no difference in its media explains a latency
      difference. That is the question "L3.5 has DRAM, is that why it is
      faster?", and the read-back ratio answers it before any latency row
      is read.

    * The device is nowhere near its own limits. Read bandwidth was 1.3
      MB/s against a 7,000 MB/s target -- 0.019% -- at a queue depth of 5.
      A device at two hundredths of one percent of its read bandwidth is
      not the constraint, whatever the latency figures do.
    """
    msgs: "list[str]" = []

    _sinks = [r for r in runs
              if r.read_back_pct is not None and r.read_back_pct < 5.0
              and (r.write_total_gb or 0) > 1.0]
    for r in _sinks:
        msgs.append(
            f"<b>{_esc(r.label)}'s backing tier is a write sink, not a read "
            f"cache:</b> {r.write_total_gb:,.0f} GB written, "
            f"{r.read_total_gb:,.1f} GB read back "
            f"({r.read_back_pct:.2f}%). It served almost no reads, so no "
            f"property of its media — DRAM, SSD or anything else — can "
            f"explain a read-latency difference here. Look at the write and "
            f"eviction path instead.")

    _idle_dev = [r for r in runs
                 if r.rd_headroom_pct is not None and r.rd_headroom_pct < 5.0
                 and (r.nvme_rd_bw_mbs or 0) >= 0]
    for r in _idle_dev:
        _qd = r.nvme_qd_mean
        msgs.append(
            f"<b>{_esc(r.label)}'s device is not the constraint:</b> read "
            f"bandwidth {r.nvme_rd_bw_mbs:,.1f} MB/s is "
            f"{r.rd_headroom_pct:.3f}% of its {r.dev_rd_target_mbs:,.0f} "
            f"MB/s read target"
            + (f", write {r.nvme_wr_bw_mbs:,.1f} MB/s is "
               f"{r.wr_headroom_pct:.1f}% of {r.dev_wr_target_mbs:,.0f} MB/s"
               if r.wr_headroom_pct is not None else "")
            + (f", at a mean queue depth of {_qd:,.1f}"
               if _qd is not None else "")
            + ". Whatever is limiting this run, the device has not been "
              "asked for it."
            + (f" (Target: {_esc(r.dev_target_src)}.)"
               if "DEFAULT" in (r.dev_target_src or "") else ""))

    if not msgs:
        return ""
    return ('<div class="banner ok"><b>What the telemetry rules out.</b>'
            '<ul style="margin:6px 0 0;padding-left:20px">'
            + "".join(f"<li>{m}</li>" for m in msgs)
            + "</ul></div>")


def build_variance_banner(runs: "list[RunMetrics]") -> str:
    """Refuse to imply causation from one run per configuration.

    On the reference data two identically configured runs differed by 38.5
    percentage points on cache hit and 48% on TPOT.  A two-run comparison
    produced a confident conclusion that a third run reversed, so the tool
    must not present single-run deltas as attributable.
    """
    from collections import Counter
    n = Counter(r.label for r in runs)
    singles = [l for l, c in n.items() if c < 3]
    if not singles:
        return ('<div class="banner ok"><b>Repeated runs:</b> every '
                'configuration has 3 or more runs; deltas below compare '
                'distributions.</div>')
    return ('<div class="banner warn"><b>Indicative only — not attributable.</b> '
            + ", ".join(_esc(x) for x in singles) +
            " has fewer than 3 runs, so a difference here cannot be separated "
            "from ordinary run-to-run variation. Differences smaller than the "
            "spread between same-label runs are not evidence of a "
            "configuration effect.</div>")

# ---------------------------------------------------------------------------
# Verdict, workload and timeline
# ---------------------------------------------------------------------------

_WORKLOAD_TOL = 0.05   # requests and prompt tokens within 5% = same workload


def _same_workload(a: "RunMetrics", b: "RunMetrics",
                   tol: float = _WORKLOAD_TOL) -> "tuple[bool | None, str]":
    """Did two runs serve the same work? (verdict, the evidence for it).

    None when neither a request count nor a prompt-token counter is there on
    both sides: the question is then unanswered, not answered "no".
    """
    checks = []
    for name, va, vb in (("requests", a.requests_n, b.requests_n),
                         ("prompt tokens", a.prompt_tok, b.prompt_tok)):
        if va and vb:
            checks.append((name, va, vb, abs(va - vb) / max(va, vb)))
    if not checks:
        return None, "no request or prompt-token counters on both runs"
    desc = "; ".join(f"{n} {va:,.0f} vs {vb:,.0f} ({d*100:.1f}% apart)"
                     for n, va, vb, d in checks)
    return all(c[3] <= tol for c in checks), desc


def _min(sec: "float | None") -> str:
    return "?" if sec is None else f"{sec/60.0:,.1f} min"


def _ratio_txt(a: "float | None", b: "float | None") -> str:
    if a is None or b is None:
        return "—"
    if a == 0:
        return "0 →" if b else "—"
    if b == 0:
        return "→ 0"
    return f"{b / a:,.2f}x"


def build_verdict_html(base: "RunMetrics", cmp_: "RunMetrics") -> str:
    """Which run served the workload faster, shown as numbers.

    A headline, a row of tiles for the figures that decide it, and an
    evidence table -- baseline, comparison, ratio, and a two-word reading --
    for everything behind them. The one statement no counter measures, the
    likely mechanism, is a single line marked as an inference.
    """
    same, same_desc = _same_workload(base, cmp_)
    ca, cb = base.completion_s, cmp_.completion_s
    if same and ca and cb:
        fast, slow = (base, cmp_) if ca <= cb else (cmp_, base)
        speed = slow.completion_s / fast.completion_s
        basis = "time to complete"
    elif base.req_per_s and cmp_.req_per_s:
        fast, slow = ((base, cmp_) if base.req_per_s >= cmp_.req_per_s
                      else (cmp_, base))
        speed = fast.req_per_s / slow.req_per_s
        basis = "request throughput"
    else:
        return ""
    B, C = _esc(base.label), _esc(cmp_.label)
    F = _esc(fast.label)
    _title = f'<h2>🧭 Verdict — {B} vs {C}</h2>'
    if speed < 1.05:
        return (_title + f'<p class="headline">No material difference: '
                f'{basis} within {(speed - 1) * 100:.1f}%.</p>')
    head = (f"{F} served the {'same ' if same else ''}workload "
            f"{speed:.2f}x faster ({basis}).")

    def _mn(v):
        return None if v is None else v / 60.0

    def _lg(m):
        return (max(e["dur_s"] for e in m.stall_episodes) / 60.0
                if m.stall_episodes else (0.0 if m.stall_present else None))

    def _kvst(m):
        _k = [e["kv_fill_mean"] for e in (m.stall_episodes or [])
              if e.get("kv_fill_mean") is not None]
        return (sum(_k) / len(_k)) if _k else None

    def _dram(m):
        return ((m.store_mem_hit_n / m.store_get_n * 100.0)
                if (m.store_get_n and m.store_mem_hit_n is not None) else None)

    def _within(a, b, tol):
        return (a is not None and b is not None and max(a, b) > 0
                and abs(a - b) / max(a, b) <= tol)

    # (label, accessor, unit, fmt, lower_is_better or None, reading rule)
    rows = [
        ("Requests completed", lambda m: m.requests_n, "", ",.0f", None,
         lambda a, b: "same" if _within(a, b, _WORKLOAD_TOL) else ""),
        ("Prompt tokens", lambda m: m.prompt_tok, "", ",.0f", None,
         lambda a, b: "same" if _within(a, b, _WORKLOAD_TOL) else ""),
        ("Prefill tokens computed", lambda m: m.recompute_measured_tok, "",
         ",.0f", None,
         lambda a, b: "same" if _within(a, b, 0.10) else ""),
        ("GPU-busy time", lambda m: _mn(m.gpu_busy_equiv_s), " min", ",.1f",
         None, lambda a, b: "same GPU work" if _within(a, b, 0.15) else ""),
        ("Time to complete", lambda m: _mn(m.completion_s), " min", ",.1f",
         True, None),
        ("Request throughput", lambda m: m.req_per_s, " req/s", ",.2f",
         False, None),
        ("Stalled (GPU idle, reqs waiting)", lambda m: _mn(m.stall_s),
         " min", ",.1f", True, None),
        ("↳ episodes", lambda m: (float(len(m.stall_episodes))
                                  if m.stall_present else None),
         "", ",.0f", True, None),
        ("↳ longest", _lg, " min", ",.1f", True, None),
        ("↳ L1 KV fill during stalls", _kvst, "%", ",.0f", None,
         lambda a, b: "HBM had room" if (a is not None and a < 50) or
         (b is not None and b < 50) else ""),
        ("Idle, nothing queued", lambda m: _mn(m.no_work_s), " min", ",.1f",
         None, None),
        ("Mean queue wait", lambda m: (m.queue_wait_ms / 1000.0)
         if m.queue_wait_ms else None, " s", ",.1f", True, None),
        ("Prefetch from tier", lambda m: m.prefetch_rate_tok_s, " tok/s",
         ",.0f", False, None),
        ("↳ silent for the last", lambda m: _mn(m.prefetch_quiet_tail_s),
         " min", ",.1f", True, None),
        ("↳ returned ÷ absorbed", lambda m: m.engine_read_back_pct, "%",
         ",.1f", False, None),
        ("↳ store lookups from DRAM", _dram, "%", ",.1f", False, None),
        ("Backup to tier", lambda m: m.backup_rate_tok_s, " tok/s", ",.0f",
         None, None),
        ("Mean decode batch", lambda m: m.sg_running_reqs_mean, " reqs",
         ",.1f", None, None),
        ("TPOT", lambda m: m.tpot_ms or None, " ms", ",.0f", True,
         lambda a, b: ("cost of the larger batch"
                       if (a and b and (cmp_.sg_running_reqs_mean or 0)
                           and (base.sg_running_reqs_mean or 0)
                           and ((b > a) == (cmp_.sg_running_reqs_mean
                                            > base.sg_running_reqs_mean)))
                       else "")),
    ]

    def _cls(a, b, lib):
        if lib is None or a is None or b is None or a == b:
            return ""
        if a == 0:
            return "bad" if lib else "good"
        d = (b - a) / abs(a)
        if abs(d) < 0.05:
            return ""
        return "good" if (d < 0) == lib else "bad"

    body = ""
    for lab, acc, unit, fmt, lib, rd in rows:
        a, b = acc(base), acc(cmp_)
        if a is None and b is None:
            continue
        _c = _cls(a, b, lib)
        _rd = rd(a, b) if rd else ""
        body += (f"<tr class='chain-row'><td>{_esc(lab)}</td>"
                 f"<td class='num'>{_fmt_layer_val(a, unit, fmt)}</td>"
                 f"<td class='num {_c}'>{_fmt_layer_val(b, unit, fmt)}</td>"
                 f"<td class='num {_c}'>{_ratio_txt(a, b)}</td>"
                 f"<td class='layer'>{_esc(_rd)}</td></tr>")

    # Tiles: the four or five figures that decide the verdict.
    tiles = ""
    for lab, acc, unit, fmt, lib, _ in rows:
        if lab not in ("Time to complete", "Request throughput",
                       "Stalled (GPU idle, reqs waiting)", "GPU-busy time",
                       "Prefetch from tier", "TPOT"):
            continue
        a, b = acc(base), acc(cmp_)
        if a is None or b is None:
            continue
        tiles += (f'<div class="tile"><div class="t-lab">{_esc(lab)}</div>'
                  f'<div class="t-val">{a:{fmt}} → '
                  f'<span class="{_cls(a, b, lib)}">{b:{fmt}}</span>'
                  f'<span class="t-unit">{_esc(unit)}</span></div>'
                  f'<div class="t-ratio">{_ratio_txt(a, b)}</div></div>')

    flags = []
    for r in (base, cmp_):
        if r.page_size == 1 and r.l3_backend_class == "local_ssd":
            flags.append(f"{_esc(r.label)}: file tier at page_size 1 "
                         f"(one key/file per token per rank)")
        if (r.launch_backend and r.storage_backend
                and r.launch_backend != r.storage_backend):
            flags.append(f"{_esc(r.label)}: launch command is stale — says "
                         f"{_esc(r.launch_backend)}, engine ran "
                         f"{_esc(r.storage_backend)}")
    if same is False:
        flags.append(f"workloads differ — {_esc(same_desc)}")
    flags_html = ("".join(f'<span class="chip">⚑ {f}</span>' for f in flags)
                  if flags else "")

    infer = ""
    _pa, _pb = slow.prefetch_rate_tok_s, fast.prefetch_rate_tok_s
    if (slow.l3_backend_class == "local_ssd" and slow.stall_present
            and (slow.stall_s or 0) >= 60.0 and _pa is not None
            and _pb is not None and _pa < 0.2 * max(_pb, 1e-9)):
        infer = (f'<div class="infer"><b>Likely mechanism (inferred, not '
                 f'measured):</b> {_esc(slow.label)}\'s local file tier was '
                 f'too slow to prefetch'
                 + (" at page_size 1" if slow.page_size == 1 else "")
                 + ', so requests were held while the GPUs idled. '
                 '<b>To confirm:</b> prefetch timeouts in the SGLang log · '
                 'storage_prefetch_unfulfilled_tokens_total over the stalls · '
                 're-run with --page-size 64.</div>')

    header = (f"<tr><th>Measurement</th><th>{B}</th><th>{C}</th>"
              f"<th>{C} ÷ {B}</th><th>Reading</th></tr>")
    return (_title + f'<p class="headline">{head}</p>'
            f'<div class="tiles">{tiles}</div>'
            + (f'<div class="chips">{flags_html}</div>' if flags_html else "")
            + infer
            + f'<table class="chain"><thead>{header}</thead>'
              f'<tbody>{body}</tbody></table>')


def build_diagnosis_charts_html(metrics: "list[RunMetrics]",
                                colours: "list[str]") -> str:
    """The verdict's figures as charts, plus how the signals co-moved."""
    if len(metrics) < 2:
        return ""
    base = metrics[0]
    _lay = {"paper_bgcolor": "#1e293b", "plot_bgcolor": "#1e293b",
            "font": {"color": "#e2e8f0", "size": 11},
            "margin": {"l": 60, "r": 30, "t": 44, "b": 60}, "height": 360,
            "legend": {"orientation": "h", "y": -0.22}}
    charts: "list[tuple[str, dict, str]]" = []

    def _t(text):
        return {"text": text, "font": {"size": 13, "color": "#f1f5f9"}}

    # 1. Every key figure as a ratio to the baseline, on a log axis.
    _spec = [  # (label, accessor, lower_is_better or None)
        ("Requests", lambda m: m.requests_n, None),
        ("Prompt tokens", lambda m: m.prompt_tok, None),
        ("Prefill computed", lambda m: m.recompute_measured_tok, None),
        ("GPU-busy time", lambda m: m.gpu_busy_equiv_s, None),
        ("Time to complete", lambda m: m.completion_s, True),
        ("Request throughput", lambda m: m.req_per_s, False),
        ("Stall time", lambda m: m.stall_s, True),
        ("Queue wait", lambda m: m.queue_wait_ms, True),
        ("Prefetch rate", lambda m: m.prefetch_rate_tok_s, False),
        ("Backup rate", lambda m: m.backup_rate_tok_s, None),
        ("Decode batch", lambda m: m.sg_running_reqs_mean, None),
        ("TPOT", lambda m: m.tpot_ms or None, True),
    ]
    _tr = []
    for j, m in enumerate(metrics[1:], start=1):
        ys, xs, cols, txt = [], [], [], []
        for lab, acc, lib in _spec:
            a, b = acc(base), acc(m)
            if not a or b is None:
                continue
            r = max(b / a, 1e-2)
            ys.append(lab)
            xs.append(r)
            txt.append("→0" if b == 0 else f"{b / a:,.2f}x")
            cols.append("#64748b" if lib is None or abs(r - 1) < 0.05 else
                        ("#4ade80" if (r < 1) == lib else "#f87171"))
        if ys:
            _tr.append({"type": "bar", "orientation": "h", "y": ys, "x": xs,
                        "name": m.label, "text": txt, "textposition": "auto",
                        "marker": {"color": cols if len(metrics) == 2
                                   else colours[j % len(colours)]}})
    if _tr:
        charts.append(("diag-ratio", {
            "data": _tr, "layout": {**_lay, "title": _t(
                f"Ratio to baseline ({base.label})"),
                "height": 420, "barmode": "group",
                "xaxis": {"type": "log", "title": "× baseline (log)",
                          "gridcolor": "#334155"},
                "yaxis": {"autorange": "reversed", "automargin": True},
                "shapes": [{"type": "line", "x0": 1, "x1": 1, "yref": "paper",
                            "y0": 0, "y1": 1,
                            "line": {"color": "#e2e8f0", "dash": "dot"}}],
                "showlegend": len(metrics) > 2}},
            "Grey = workload or neutral; green / red = better / worse than "
            "baseline. 1.0 = no change."))

    # 2. Where each run's time went.
    _runs = [m for m in metrics if m.stall_present]
    if _runs:
        _parts = (("GPUs busy", "busy_s", "#22c55e"),
                  ("Stalled — reqs waiting", "stall_s", "#ef4444"),
                  ("Idle — nothing queued", "no_work_s", "#64748b"),
                  ("Idle — between batches", "other_idle_s", "#f59e0b"))
        charts.append(("diag-time", {
            "data": [{"type": "bar", "orientation": "h", "name": n,
                      "y": [m.label for m in _runs],
                      "x": [(getattr(m, a) or 0) / 60.0 for m in _runs],
                      "marker": {"color": c},
                      "text": [f"{(getattr(m, a) or 0) / 60.0:,.1f}"
                               for m in _runs], "textposition": "inside"}
                     for n, a, c in _parts],
            "layout": {**_lay, "title": _t("Where the time went (min)"),
                       "barmode": "stack", "height": 230 + 60 * len(_runs),
                       "margin": {"l": 60, "r": 30, "t": 44, "b": 110},
                       "legend": {"orientation": "h", "y": -0.5},
                       "xaxis": {"title": "minutes", "gridcolor": "#334155"},
                       "yaxis": {"automargin": True}}},
            ""))

    # 3. Backing-tier delivery.
    if any(m.prefetch_rate_tok_s is not None for m in metrics):
        charts.append(("diag-tier", {
            "data": [{"type": "bar", "name": n, "x": [m.label for m in metrics],
                      "y": [f(m) for m in metrics], "marker": {"color": c},
                      "text": [("n/a" if f(m) is None else f"{f(m):,.0f}")
                               for m in metrics], "textposition": "auto"}
                     for n, f, c in (
                         ("prefetch tok/s", lambda m: m.prefetch_rate_tok_s,
                          "#38bdf8"),
                         ("backup tok/s", lambda m: m.backup_rate_tok_s,
                          "#a78bfa"))],
            "layout": {**_lay, "title": _t("Backing-tier delivery"),
                       "barmode": "group",
                       "yaxis": {"type": "log", "title": "tokens / s (log)",
                                 "gridcolor": "#334155"}}},
            "Returned ÷ absorbed: " + " · ".join(
                f"{m.label} {m.engine_read_back_pct:,.1f}%"
                for m in metrics if m.engine_read_back_pct is not None)))

    # 4. GPU utilisation against waiting requests, one point per sample.
    _sc = [{"type": "scatter", "mode": "markers", "name": m.label,
            "x": m.timeline["waiting"], "y": m.timeline["gpu"],
            "marker": {"color": colours[i % len(colours)], "size": 6,
                       "opacity": 0.6}}
           for i, m in enumerate(metrics) if (m.timeline or {}).get("t")]
    if _sc:
        charts.append(("diag-scatter", {
            "data": _sc, "layout": {**_lay, "title": _t(
                "GPU utilisation vs requests waiting"),
                "xaxis": {"title": "requests waiting", "gridcolor": "#334155"},
                "yaxis": {"title": "GPU util %", "range": [-3, 105],
                          "gridcolor": "#334155"}}},
            "Bottom-right = stall: work waiting, GPUs idle."))

    # 5. Correlation between the signals, per run.
    for i, m in enumerate(metrics):
        c = m.corr or {}
        if not c.get("names"):
            continue
        z = c["r"]
        charts.append((f"diag-corr-{i}", {
            "data": [{"type": "heatmap", "x": c["names"], "y": c["names"],
                      "z": z, "zmin": -1, "zmax": 1, "colorscale": "RdBu",
                      "reversescale": True,
                      "text": [["" if v is None else f"{v:+.2f}" for v in row]
                               for row in z],
                      "texttemplate": "%{text}", "hoverongaps": False}],
            "layout": {**_lay, "title": _t(f"Correlation (Pearson r) — "
                                           f"{m.label}"),
                       "height": 380, "yaxis": {"autorange": "reversed",
                                                "automargin": True},
                       "xaxis": {"automargin": True}}},
            "Blank = undefined (a constant series)."))

    if not charts:
        return ""
    out = []
    for cid, fig, note in charts:
        dj = json.dumps(fig)
        out.append(f'<div class="chart-wrap"><div id="{cid}"></div>'
                   + (f'<div class="chart-note">{_esc(note)}</div>'
                      if note else "")
                   + f'</div><script>Plotly.newPlot("{cid}",{dj}.data,'
                     f'{dj}.layout,{{"responsive":true,'
                     f'"displayModeBar":false}});</script>')
    return ('<h2>📊 Diagnosis charts</h2><div class="charts-grid">'
            + "".join(out) + '</div>')


def build_workload_html(metrics: "list[RunMetrics]") -> str:
    """The workload each run served, how long it took, and where it waited."""
    if len(metrics) < 2:
        return ""
    labels = [_esc(m.label) for m in metrics]

    def _ep_longest(m):
        if not m.stall_episodes:
            return None if not m.stall_present else "none"
        e = max(m.stall_episodes, key=lambda x: x["dur_s"])
        return (f"{e['dur_s']/60.0:,.1f} min from t={e['t_end']-e['dur_s']:,.0f}"
                f" s, ≤{e['waiting_peak']:,.0f} waiting"
                + (f", KV {e['kv_fill_mean']:,.0f}% full"
                   if e.get("kv_fill_mean") is not None else ""))

    def _mn(v):
        return None if v is None else v / 60.0

    rows = [
        ("Requests completed · measured", lambda m: m.requests_n, "", ",.0f"),
        ("↳ counted as", lambda m: m.requests_src or None, "", ""),
        ("Prompt tokens", lambda m: m.prompt_tok, "", ",.0f"),
        ("↳ per request",
         lambda m: (m.prompt_tok / m.requests_n)
         if (m.prompt_tok and m.requests_n) else None, " tok", ",.0f"),
        ("Prefill tokens computed (prompt − cached)",
         lambda m: m.recompute_measured_tok, "", ",.0f"),
        ("Time to complete · first to last busy sample",
         lambda m: _mn(m.completion_s), " min", ",.1f"),
        ("↳ analysis window", lambda m: _mn(m.window_s or None), " min", ",.1f"),
        ("Request throughput · over time to complete",
         lambda m: m.req_per_s, " req/s", ",.2f"),
        ("GPU-busy time · mean util × span",
         lambda m: _mn(m.gpu_busy_equiv_s), " min", ",.1f"),
        ("GPUs busy", lambda m: _mn(m.busy_s), " min", ",.1f"),
        ("Stalled · GPUs idle, requests waiting",
         lambda m: _mn(m.stall_s), " min", ",.1f"),
        ("↳ episodes", lambda m: (float(len(m.stall_episodes))
                                  if m.stall_present else None), "", ",.0f"),
        ("↳ longest", _ep_longest, "", ""),
        ("Idle · nothing queued or running",
         lambda m: _mn(m.no_work_s), " min", ",.1f"),
        ("Idle · between batches", lambda m: _mn(m.other_idle_s), " min", ",.1f"),
        ("↳ how idle time was classified",
         lambda m: m.stall_method or None, "", ""),
        ("Waiting requests · mean", lambda m: m.sg_queue_reqs_mean, "", ",.1f"),
        ("↳ peak", lambda m: m.sg_queue_reqs_peak, "", ",.0f"),
        ("Decode batch · mean", lambda m: m.sg_running_reqs_mean, "", ",.1f"),
        ("↳ peak", lambda m: m.sg_running_reqs_peak, "", ",.0f"),
        ("Queue wait before prefill · mean",
         lambda m: (m.queue_wait_ms / 1000.0) if m.queue_wait_ms else None,
         " s", ",.1f"),
        ("Prefetch from the backing tier",
         lambda m: m.prefetch_rate_tok_s, " tok/s", ",.0f"),
        ("Backup to the backing tier",
         lambda m: m.backup_rate_tok_s, " tok/s", ",.0f"),
        ("↳ tokens returned ÷ tokens absorbed",
         lambda m: m.engine_read_back_pct, "%", ",.2f"),
        ("↳ prefetch silent for the last",
         lambda m: _mn(m.prefetch_quiet_tail_s), " min", ",.1f"),
        ("Store lookups answered from its DRAM tier",
         lambda m: (m.store_mem_hit_n / m.store_get_n * 100.0)
         if (m.store_get_n and m.store_mem_hit_n is not None) else None,
         "%", ",.2f"),
        ("HiCache page size", lambda m: m.page_size, " tok/page", ",.0f"),
        ("↳ from", lambda m: m.page_size_src or None, "", ""),
        ("Storage backend the engine ran",
         lambda m: m.storage_backend or None, "", ""),
        ("↳ launch command asks for",
         lambda m: m.launch_backend or None, "", ""),
    ]
    # With two runs the verdict's evidence table already carries the headline
    # figures; repeat them only when there are more runs than it shows.
    _in_verdict = {
        "Requests completed · measured", "Prompt tokens",
        "Prefill tokens computed (prompt − cached)",
        "Time to complete · first to last busy sample",
        "Request throughput · over time to complete",
        "GPU-busy time · mean util × span",
        "Stalled · GPUs idle, requests waiting", "↳ episodes",
        "Idle · nothing queued or running", "Decode batch · mean",
        "Queue wait before prefill · mean", "Prefetch from the backing tier",
        "Backup to the backing tier", "↳ tokens returned ÷ tokens absorbed",
        "↳ prefetch silent for the last",
        "Store lookups answered from its DRAM tier"}
    body = ""
    for row_label, acc, unit, fmt in rows:
        if len(metrics) == 2 and row_label in _in_verdict:
            continue
        vals = [acc(m) for m in metrics]
        if all(v is None for v in vals):
            continue
        body += (f"<tr class='chain-row'><td>{_esc(row_label)}</td>"
                 + "".join(f"<td class='num'>{_fmt_layer_val(v, unit, fmt)}"
                           f"</td>" for v in vals) + "</tr>")
    if not body:
        return ""
    _notes = []
    for _m in metrics[1:]:
        _same, _desc = _same_workload(metrics[0], _m)
        _notes.append(f"{_esc(metrics[0].label)} vs {_esc(_m.label)}: "
                      + ("same workload — " if _same else
                         "workloads differ — " if _same is False else "")
                      + _esc(_desc))
    header = ("<tr><th>Measurement</th>"
              + "".join(f"<th>{l}</th>" for l in labels) + "</tr>")
    return ('<h2>⏱️ Workload and time to complete — detail</h2>'
            '<p class="note">Stall = GPUs idle while requests waited. '
            + " · ".join(_notes) + '</p>'
            f'<table class="chain"><thead>{header}</thead>'
            f'<tbody>{body}</tbody></table>')


def build_timeline_html(metrics: "list[RunMetrics]",
                        colours: "list[str]") -> str:
    """GPU utilisation against waiting requests over each run's window.

    One panel per run, on minutes since the window start, with every stall
    episode shaded. The window means compress this to one number each; the
    timeline is where a 6-minute stall and a slow tier look different.
    """
    panels = []
    for i, m in enumerate(metrics):
        tl = m.timeline or {}
        if not tl.get("t"):
            continue
        x = [t / 60.0 for t in tl["t"]]
        traces = [
            {"type": "scatter", "mode": "lines", "name": "GPU util %",
             "x": x, "y": tl["gpu"],
             "line": {"color": colours[i % len(colours)], "width": 1.6}},
            {"type": "scatter", "mode": "lines", "name": "waiting requests",
             "x": x, "y": tl["waiting"], "yaxis": "y2",
             "line": {"color": "#f87171", "width": 1.4}},
        ]
        if tl.get("running"):
            traces.append({"type": "scatter", "mode": "lines",
                           "name": "decode batch", "x": x,
                           "y": tl["running"], "yaxis": "y2",
                           "line": {"color": "#94a3b8", "width": 1,
                                    "dash": "dot"}})
        shapes = [{"type": "rect", "xref": "x", "yref": "paper",
                   "x0": (e["t_end"] - e["dur_s"]) / 60.0,
                   "x1": e["t_end"] / 60.0, "y0": 0, "y1": 1,
                   "fillcolor": "rgba(248,113,113,0.18)", "line": {"width": 0}}
                  for e in (m.stall_episodes or [])]
        layout = {
            "title": {"text": f"{m.label} — "
                              + (f"{len(m.stall_episodes)} stall episode(s), "
                                 f"{(m.stall_s or 0)/60:,.1f} min"
                                 if m.stall_present else "stalls not classified"),
                      "font": {"size": 13, "color": "#f1f5f9"}},
            "paper_bgcolor": "#1e293b", "plot_bgcolor": "#1e293b",
            "font": {"color": "#e2e8f0", "size": 11},
            "xaxis": {"title": "minutes since window start",
                      "gridcolor": "#334155"},
            "yaxis": {"title": "GPU util %", "range": [0, 105],
                      "gridcolor": "#334155"},
            "yaxis2": {"title": "requests", "overlaying": "y", "side": "right",
                       "gridcolor": "rgba(0,0,0,0)", "rangemode": "tozero"},
            "legend": {"orientation": "h", "y": -0.3},
            "margin": {"l": 55, "r": 55, "t": 40, "b": 70}, "height": 320,
            "shapes": shapes,
        }
        cid = f"timeline-{i}"
        dj = json.dumps({"data": traces, "layout": layout})
        panels.append(f'<div class="chart-wrap"><div id="{cid}"></div></div>'
                      f'<script>Plotly.newPlot("{cid}",{dj}.data,{dj}.layout,'
                      f'{{"responsive":true,"displayModeBar":false}});</script>')
    if not panels:
        return ""
    return ('<h2>📉 Timeline — where the time went</h2>'
            '<p class="note">GPU utilisation (left) against requests waiting '
            'to enter prefill and the decode batch (right). Shaded spans are '
            'stalls: the GPUs idle while requests waited.</p>'
            '<div class="charts-grid">' + "".join(panels) + '</div>')


def build_comparison_html(
    metrics: List[RunMetrics],
    title: str = "AMOprof Comparison Report",
) -> str:
    """Return a self-contained comparison HTML from a list of RunMetrics."""

    if len(metrics) < 2:
        raise ValueError("Need at least 2 runs to compare")

    baseline = metrics[0]
    n        = len(metrics)
    labels   = [_html.escape(m.label) for m in metrics]
    colours  = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444",
                "#a78bfa", "#34d399", "#fbbf24", "#f87171"]

    # ── Plotly chart helper ────────────────────────────────────────────────
    def bar_chart(chart_id: str, title_str: str,
                  series: List[tuple[str, List[float]]],
                  y_label: str = "", note: str = "",
                  y2_label: str = "", y2_series: int = -1,
                  log_y: bool = False) -> str:
        """Grouped bars, one group per run.

        A series whose every value is zero is DROPPED rather than drawn as a
        row of zero-height bars with "0.0" labels stacked on the axis. Those
        bars were unreadable and, worse, a measured zero and an unexported
        metric looked the same -- the NVMe panel drew ten zero bars for runs
        whose device counters were simply never collected.

        *y2_series* puts one series on a secondary axis. Without it, a metric
        in milliseconds beside one in seconds had to be divided by a constant
        to share the axis, and the divided series was both mislabelled and
        too short to see.
        """
        _kept = [(i, name, vals) for i, (name, vals) in enumerate(series)
                 if any(v for v in vals if v is not None)]
        if not _kept:
            # Every series empty: say so instead of drawing an empty frame.
            return (f'<div class="chart-wrap"><div class="chart-note">'
                    f'<b>{_html.escape(title_str)}</b> — not collected for '
                    f'any of these runs, so there is nothing to compare.'
                    f'</div></div>')
        _dropped = [series[i][0] for i in range(len(series))
                    if i not in {k[0] for k in _kept}]

        traces = []
        for _slot, (i, name, vals) in enumerate(_kept):
            _t = {
                "type": "bar", "name": name,
                "x": labels, "y": vals,
                "marker": {"color": colours[i % len(colours)]},
                # Zero within a kept series is a real measurement; show it,
                # but let Plotly place the label inside or outside by room.
                # None is a gap, not a zero: Plotly draws no bar for null,
                # which is what "never exported" should look like. A real
                # measured zero still gets a labelled zero-height bar.
                "text": ["n/a" if v is None else
                         (f"{v:,.2f}".rstrip("0").rstrip(".") if v else "0")
                         for v in vals],
                "textposition": "auto",
                "textfont": {"size": 10},
                "cliponaxis": False,
            }
            if i == y2_series:
                _t["yaxis"] = "y2"
                _t["name"] = f"{name} (right axis)"
            # Bars on two overlaying axes are grouped per axis, so without
            # an offsetgroup each the right-axis series is drawn in the same
            # slot as the first left-axis one and hides it -- TPOT covered
            # TTFT and E2E, read IOPS covered read bandwidth.
            _t["offsetgroup"] = str(_slot)
            traces.append(_t)

        layout = {
            "title": {"text": title_str, "font": {"size": 14, "color": "#f1f5f9"}},
            "paper_bgcolor": "#1e293b", "plot_bgcolor": "#1e293b",
            "font": {"color": "#e2e8f0", "size": 12},
            "barmode": "group",
            "bargap": 0.25, "bargroupgap": 0.08,
            "yaxis": {"title": y_label, "gridcolor": "#334155",
                      "color": "#e2e8f0", "zerolinecolor": "#475569",
                      "automargin": True},
            "xaxis": {"color": "#e2e8f0", "gridcolor": "#334155",
                      "automargin": True},
            "legend": {"orientation": "h", "y": -0.28,
                       "font": {"color": "#e2e8f0", "size": 10.5}},
            "margin": {"l": 60, "r": 60, "t": 46, "b": 78},
            # Taller than 300: nine bars with outside labels in 300px was
            # what pushed the numbers on top of each other.
            "height": 360,
            "uniformtext": {"mode": "hide", "minsize": 8},
        }
        if log_y:
            # A log axis cannot render a zero bar, so the label carries the
            # zero and the bar is simply absent -- which is honest: on a log
            # scale there is no height that means "none".
            layout["yaxis"]["type"] = "log"
        if y2_series >= 0 and any(i == y2_series for i, _n, _v in _kept):
            layout["yaxis2"] = {
                "title": y2_label, "overlaying": "y", "side": "right",
                "gridcolor": "rgba(0,0,0,0)", "color": "#e2e8f0",
                "zerolinecolor": "#475569", "automargin": True,
            }

        _note = note
        if _dropped:
            _note = ((note + " " if note else "")
                     + "Not collected for these runs, so omitted: "
                     + ", ".join(_dropped) + ".")
        data_json = json.dumps({"data": traces, "layout": layout})
        note_html = (f'<div class="chart-note">{_html.escape(_note)}</div>'
                     if _note else "")
        return (f'<div class="chart-wrap">'
                f'<div id="{chart_id}"></div>{note_html}</div>'
                f'<script>Plotly.newPlot("{chart_id}",'
                f'{data_json}.data, {data_json}.layout,'
                f'{{"responsive":true,"displayModeBar":false}});</script>')

    def radar_chart() -> str:
        """Radar chart: normalised 0–100 score for each run on 8 axes."""
        # Higher = better for all axes (some are inverted)
        theta = ["Throughput", "Cache Hit", "GPU Util",
                 "HBM Headroom", "NVMe Latency\n(inv)", "DRAM Util\n(inv headroom)",
                 "TTFT\n(inv)", "TPOT\n(inv)"]
        traces = []
        for i, m in enumerate(metrics):
            # Normalise each dimension to 0-100 relative to max across all runs
            def norm_hi(vals: List[float]) -> float:
                mx = max(vals) if vals and max(vals) > 0 else 1
                return (m_vals / mx * 100) if (m_vals := vals[i]) else 0

            all_tp  = [x.throughput_tok_s for x in metrics]
            all_ch  = [x.cache_hit_pct for x in metrics]
            all_gu  = [x.gpu_util_pct for x in metrics]
            all_hbm = [max(100 - x.hbm_pct, 0) for x in metrics]   # headroom (clipped)
            all_nll = [1 / max(x.nvme_rd_lat_ms, 0.001) * 100 for x in metrics]  # inv latency
            all_dram= [100 - min(x.dram_total_bw_gbs / 204.8 * 100, 100) for x in metrics]  # headroom
            all_ttft= [1 / max(x.ttft_ms, 1) * 1e6 for x in metrics]   # inv
            all_tpot= [1 / max(x.tpot_ms, 1) * 1e6 for x in metrics]   # inv

            def _norm(vals: List[float], idx: int) -> float:
                mx = max(vals) if vals and max(vals) > 0 else 1
                return round(vals[idx] / mx * 100, 1)

            r = [
                _norm(all_tp,   i), _norm(all_ch,   i), _norm(all_gu,  i),
                _norm(all_hbm,  i), _norm(all_nll,  i), _norm(all_dram, i),
                _norm(all_ttft, i), _norm(all_tpot,  i),
            ]
            r.append(r[0])  # close loop
            traces.append({
                "type": "scatterpolar",
                "r": r, "theta": theta + [theta[0]],
                "name": m.label,
                "fill": "toself",
                "line": {"color": colours[i % len(colours)], "width": 2},
                "fillcolor": colours[i % len(colours)].replace("#", "rgba(") + ",0.15)",
            })
        layout = {
            "polar": {
                "radialaxis": {"visible": True, "range": [0, 105],
                               "color": "#475569", "gridcolor": "#334155"},
                "angularaxis": {"color": "#e2e8f0", "gridcolor": "#334155"},
                "bgcolor": "#1e293b",
            },
            "paper_bgcolor": "#1e293b",
            "font": {"color": "#e2e8f0", "size": 11},
            "legend": {"orientation": "h", "y": -0.15,
                       "font": {"color": "#e2e8f0"}},
            "margin": {"l": 40, "r": 40, "t": 10, "b": 60},
            "height": 380,
            "title": {"text": "Normalised performance profile (higher = better)",
                      "font": {"size": 13, "color": "#94a3b8"}},
        }
        data_json = json.dumps({"data": traces, "layout": layout})
        return (f'<div id="radar-chart"></div>'
                f'<script>Plotly.newPlot("radar-chart",'
                f'{data_json}.data, {data_json}.layout,'
                f'{{"responsive":true,"displayModeBar":false}});</script>')

    # ── KPI comparison table ───────────────────────────────────────────────
    def kpi_rows() -> str:
        rows_data = [
            # (label, attr, unit, lower_is_better, fmt)
            ("TTFT (s)",         "ttft_ms",          "s",    True,  ".1f", 1/1000),
            ("TPOT (ms/tok)",    "tpot_ms",          " ms",  True,  ".0f", 1.0),
            ("E2E latency (s)",  "e2e_ms",           "s",    True,  ".1f", 1/1000),
            ("Throughput (tok/s)","throughput_tok_s","tok/s", False, ".1f", 1.0),
            ("Cache hit % (gauge)","cache_hit_pct",  "%",    False, ".1f", 1.0),
            ("Cache hit % (token-wt)","cache_hit_tw_pct","%",False, ".1f", 1.0),
            ("GPU util %",       "gpu_util_pct",     "%",    False, ".1f", 1.0),
            ("HBM used (GB)",    "hbm_used_gb",      " GB",  True,  ".1f", 1.0),
            ("HBM fill %",       "hbm_pct",          "%",    True,  ".1f", 1.0),
            ("GPU power (W)",    "gpu_power_w",      " W",   True,  ".0f", 1.0),
            ("L3 (local storage) read throughput (MB/s)","nvme_rd_bw_mbs", " MB/s",False, ".0f", 1.0),
            ("NVMe read IOPS",   "nvme_rd_iops",     " IOPS",False, ".0f", 1.0),
            ("NVMe read lat (ms)","nvme_rd_lat_ms",  " ms",  True,  ".2f", 1.0),
            ("NVMe device util%","nvme_util_pct",    "%",    True,  ".1f", 1.0),
            ("SSD reads total (GB)","read_total_gb", " GB",  False, ".0f", 1.0),
            ("DRAM total BW (GB/s)","dram_total_bw_gbs"," GB/s",False,".1f",1.0),
            # Time to serve the workload, which is what a same-workload
            # comparison is about; the window means above dilute it.
            ("Time to complete (min)","kpi_completion_min"," min",True,".1f",1.0),
            ("Request throughput (req/s)","kpi_req_per_s"," req/s",False,".2f",1.0),
            ("Mean queue wait (s)","kpi_queue_wait_s","s",  True,  ".1f", 1.0),
            ("Mean decode batch (reqs)","kpi_running_mean","", False, ".1f", 1.0),
            ("Prefetch from tier (tok/s)","kpi_prefetch_rate"," tok/s",False,",.0f",1.0),
        ]
        header = "<tr><th>Metric</th>" + "".join(
            f"<th>{l}</th>" for l in labels) + "</tr>"
        body = ""
        for row_label, attr, unit, lib, fmt, scale in rows_data:
            vals = [getattr(m, attr) * scale for m in metrics]
            if all(v == 0 for v in vals):
                continue
            cells = ""
            for j, v in enumerate(vals):
                if j == 0:
                    cells += f"<td class='baseline'>{v:{fmt}}{unit}</td>"
                else:
                    cells += _delta_cell(vals[0] / scale * scale,
                                          v, lib, fmt, unit)
            body += f"<tr><td class='metric-name'>{_html.escape(row_label)}</td>{cells}</tr>"
        return f"<table class='kpi-table'><thead>{header}</thead><tbody>{body}</tbody></table>"

    # ── Configuration table ────────────────────────────────────────────────
    def config_table() -> str:
        fields = [
            ("Model",    [m.model for m in metrics]),
            ("Runtime",  [m.runtime for m in metrics]),
            ("GPU",      [m.gpu_desc for m in metrics]),
            ("TP size",  [m.tp_size for m in metrics]),
            ("Context",  [m.context for m in metrics]),
            ("HiCache",  [m.hicache for m in metrics]),
            # The tier each run actually used, resolved from that run's own
            # setup. With three runs over two backend classes this is the row
            # that says which comparison is being made, so it sits with the
            # configuration rather than being inferred from the run label.
            # Short tier plus the resolver's class, which is the value that
            # explains the label. The full display name is too long for a
            # table cell and repeats what the class already says.
            ("KV backing tier",
             [(f"{m.tier_short or '?'} — {m.l3_backend_class}" if m.l3_backend_class
               else "unknown — no setup_details") for m in metrics]),
            ("Duration", [f"{m.duration_min:.0f} min" if m.duration_min else "?" for m in metrics]),
            ("Window",   [m.window_str or "—" for m in metrics]),
        ]
        header = "<tr><th>Parameter</th>" + "".join(f"<th>{l}</th>" for l in labels) + "</tr>"
        rows = ""
        for fname, fvals in fields:
            # Highlight differences
            cells = ""
            all_same = len(set(str(v) for v in fvals)) == 1
            for v in fvals:
                cls = "" if all_same else " class='diff'"
                cells += f"<td{cls}>{_html.escape(str(v))}</td>"
            rows += f"<tr><td class='metric-name'>{_html.escape(fname)}</td>{cells}</tr>"
        return f"<table class='kpi-table'><thead>{header}</thead><tbody>{rows}</tbody></table>"

    # ── Winner badges ──────────────────────────────────────────────────────
    def winner_summary() -> str:
        categories = [
            ("Lowest TTFT",       "ttft_ms",          True),
            ("Lowest TPOT",       "tpot_ms",          True),
            ("Best throughput",   "throughput_tok_s",  False),
            ("Best cache hit",    "cache_hit_pct",     False),
            ("Lowest HBM fill",   "hbm_pct",           True),
            ("Highest NVMe BW",   "nvme_rd_bw_mbs",    False),
            ("Lowest NVMe lat",   "nvme_rd_lat_ms",    True),
            ("Lowest DRAM BW",    "dram_total_bw_gbs", True),  # lower = less L2 pressure
            ("Fastest to finish", "kpi_completion_min", True),
            ("Highest request rate", "kpi_req_per_s",  False),
        ]
        html_out = '<div class="winner-grid">'
        for cat, attr, lower_is_better in categories:
            vals = [(getattr(m, attr), m.label) for m in metrics if getattr(m, attr) > 0]
            if not vals:
                continue
            best_val, best_label = min(vals) if lower_is_better else max(vals)
            esc_label = _html.escape(best_label)
            esc_cat   = _html.escape(cat)
            esc_val   = _html.escape(f"{best_val:.1f}")
            html_out += (
                f'<div class="winner-card">'
                f'<div class="winner-cat">{esc_cat}</div>'
                f'<div class="winner-label">🏆 {esc_label}</div>'
                f'<div class="winner-val">{esc_val}</div>'
                f'</div>')
        return html_out + '</div>'

    # ── Build chart blocks ─────────────────────────────────────────────────
    charts_html = ""
    # TPOT goes on its own axis in real milliseconds. It used to be divided
    # by 100 so it could share the seconds axis, labelled "ms×10" (which is
    # a third scale again) while the note said "÷100" -- and at 1/100 scale
    # the bar was a sliver with its label on the axis line.
    charts_html += bar_chart("ch-latency", "Latency comparison",
        [("TTFT (s)",   [m.ttft_ms / 1000 for m in metrics]),
         ("E2E (s)",    [m.e2e_ms  / 1000 for m in metrics]),
         ("TPOT (ms)",  [max(m.tpot_ms, 0) for m in metrics])],
        y_label="seconds", y2_label="ms / token", y2_series=2,
        note="Lower is better. TPOT is per output token, in milliseconds on "
             "the right axis; TTFT and E2E are per request, in seconds on "
             "the left.")

    charts_html += bar_chart("ch-throughput", "Throughput & cache hit",
        [("Cache hit % (gauge)", [m.cache_hit_pct    for m in metrics]),
         ("Cache hit % (token-weighted)", [m.cache_hit_tw_pct for m in metrics]),
         ("Throughput (tok/s)", [m.throughput_tok_s  for m in metrics])],
        y_label="%", y2_label="tokens / s", y2_series=2,
        note="Higher is better. Throughput is on the right axis; the two "
             "cache-hit percentages share the left.")

    charts_html += bar_chart("ch-gpu", "GPU utilisation & HBM",
        [("GPU util %",  [m.gpu_util_pct  for m in metrics]),
         ("HBM fill %",  [m.hbm_pct       for m in metrics]),
         ("DCGM active%",[m.dcgm_active_pct for m in metrics])],
        y_label="%",
        note="GPU util higher is better; HBM fill lower is better.")

    # KV movement by hop, log-scaled: the hops routinely differ by three
    # orders of magnitude (millions of tokens evicted against thousands
    # prefetched), and on a linear axis every hop but the largest is a
    # sliver.
    _T_c = _tier_prefix(*metrics) or "L3/L3.5"
    _hop_series = [
        ("evict L1→L2",            [m.evicted_tok    for m in metrics]),
        (f"backup L2→{_T_c}",      [m.backuped_tok   for m in metrics]),
        (f"prefetch {_T_c}→L2",    [m.prefetched_tok for m in metrics]),
        ("load-back L2→L1",        [m.load_back_tok  for m in metrics]),
    ]
    if any(any(v for v in vals if v is not None) for _n, vals in _hop_series):
        charts_html += bar_chart("ch-kv-hops", "KV movement by hop",
            _hop_series, y_label="tokens (log scale)",
            note="Tokens moved across each boundary over the window. Log "
                 "axis: the hops differ by orders of magnitude. Down-moves "
                 "are evict and backup, up-moves prefetch and load-back. "
                 "A bar marked n/a means that run never exported the "
                 "counter, which is not the same as a hop that moved "
                 "nothing.",
            log_y=True)

    # Bandwidth and IOPS only, with IOPS on its own axis. This panel used to
    # put MB/s, IOPS, per cent and milliseconds on one linear axis, where
    # anything other than IOPS was invisible; latency and utilisation are in
    # the A2 table, each with its own unit.
    charts_html += bar_chart("ch-nvme", "Local NVMe: bandwidth and IOPS",
        [("Read BW (MB/s)",  [m.nvme_rd_bw_mbs or None for m in metrics]),
         ("Write BW (MB/s)", [m.nvme_wr_bw_mbs or None for m in metrics]),
         ("Read IOPS",       [m.nvme_rd_iops   or None for m in metrics])],
        y_label="MB/s", y2_label="IOPS", y2_series=2,
        note="Read bandwidth and IOPS higher = more KV load-back from the "
             "local device. For a run backed by a memory node this host's "
             "device is not the KV path, so these are expected to be absent. "
             "Latency, queue depth and utilisation are in the A2 table, "
             "each in its own unit.")

    if any(m.dram_total_bw_gbs > 0 for m in metrics):
        charts_html += bar_chart("ch-dram", "System DRAM bandwidth",
            [("Total BW (GB/s)", [m.dram_total_bw_gbs for m in metrics]),
             ("Read BW (GB/s)",  [m.dram_rd_bw_gbs    for m in metrics]),
             ("Write BW (GB/s)", [m.dram_wr_bw_gbs    for m in metrics])],
            y_label="GB/s",
            note="AMD EPYC PMU. Lower total = less L2 DRAM pressure.")

    charts_html += bar_chart("ch-ssd-total", "SSD I/O volume",
        [("Reads (GB)",  [m.read_total_gb  or None for m in metrics]),
         ("Writes (GB)", [m.write_total_gb or None for m in metrics]),
         ("Host written (GB)", [m.host_written_gb for m in metrics]),
         ("NAND written (GB)", [m.nand_written_gb for m in metrics])],
        y_label="GB",
        note="Bytes moved to and from the local NVMe over the window. Host "
             "against NAND written is write amplification.")

    # ── Full HTML ──────────────────────────────────────────────────────────
    run_rows_html = "".join(
        f"<tr><td>{i}</td><td><b>{_html.escape(m.label)}</b></td>"
        f"<td>{_html.escape(str(m.raw_dir))}</td>"
        f"<td>{_html.escape(m.window_str or '—')}</td>"
        f"<td>{m.duration_min:.0f} min</td></tr>"
        for i, m in enumerate(metrics)
    )

    # Chain and variance guard, rendered before the existing tables because
    # the chain is the finding and the guard qualifies everything below it.
    _variance_html = build_variance_banner(metrics)
    _chain_html = ""
    if len(metrics) >= 2:
        # One chain per comparison run, each against the baseline. Rendering
        # only metrics[1] dropped every run after the second from the one
        # table that carries the finding, which is exactly the table a
        # three-way comparison is run for.
        _chains = [build_chain_html(baseline, _m) for _m in metrics[1:]]
        _chain_html = "".join(f'<div class="card">{_c}</div>' for _c in _chains)
    _layer_inner = build_layer_walk_html(metrics)
    _layer_html = f'<div class="card">{_layer_inner}</div>' if _layer_inner else ""

    # Queueing, per layer. The chart carries ONLY the rows that are counts of
    # coexisting or waiting work -- no proxy goes on it. A share-of-peak and
    # a retransmit rate share no axis with a request count, and putting them
    # on one would invite exactly the comparison the table is careful to
    # forbid. Log scale, because a scheduler queue in the hundreds and a
    # device queue below one are both real and both worth seeing.
    _qd_inner = build_queue_depth_html(metrics)
    _qd_chart = ""
    _qd_series = [
        ("Waiting requests (A5, peak)", [m.sg_queue_reqs_peak for m in metrics]),
        ("Decode batch (A5, peak)", [m.sg_running_reqs_peak for m in metrics]),
        ("This host's device (peak)", [m.l3_qd_peak for m in metrics]),
        ("Memory node's device (peak)", [m.l35_qd_peak for m in metrics]),
        ("blktrace Q\u2192C (peak)", [m.bt_qd_peak for m in metrics]),
    ]
    _qd_series = [(_n, [0.0 if v is None else float(v) for v in _vs])
                  for _n, _vs in _qd_series
                  if any(v is not None and v > 0 for v in _vs)]
    if _qd_series:
        _qd_chart = bar_chart(
            "qd_layers", "Peak queue depth by layer", _qd_series,
            y_label="requests / IOs in flight",
            note="Only measured queues. DRAM share-of-peak and the network "
                 "retransmit and drop rates are pressure PROXIES, not queue "
                 "depths, so they are in the table and not on this axis. "
                 "Log scale: a scheduler queue in the hundreds and a device "
                 "queue below one are both real.",
            log_y=True)
    _qd_html = (f'<div class="card">{_qd_inner}{_qd_chart}</div>'
                if _qd_inner else "")
    _suspect_html = build_suspect_banner(metrics)
    # Stated after the caveats and before the tables: the caveats say
    # which figures to doubt, this says which explanations are already out.
    _ruled_out_html = build_ruled_out_banner(metrics)
    # The finding first: one verdict per comparison run, then the workload
    # and time-to-complete table and the timeline that back it.
    _verdict_html = "".join(
        f'<div class="card verdict">{_v}</div>'
        for _v in (build_verdict_html(baseline, _m) for _m in metrics[1:])
        if _v)
    _wl_inner = build_workload_html(metrics)
    _workload_html = f'<div class="card">{_wl_inner}</div>' if _wl_inner else ""
    _dg_inner = build_diagnosis_charts_html(metrics, colours)
    _diag_html = f'<div class="card">{_dg_inner}</div>' if _dg_inner else ""
    _tl_inner = build_timeline_html(metrics, colours)
    _timeline_html = f'<div class="card">{_tl_inner}</div>' if _tl_inner else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_html.escape(title)}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  *{{box-sizing:border-box;}}
  body{{margin:0;padding:20px 24px 40px;background:#0f172a;color:#e2e8f0;
       font-family:Inter,system-ui,sans-serif;line-height:1.6;font-size:13px;}}
  .wrap{{max-width:1400px;margin:0 auto;}}
  h1{{font-size:22px;margin:0 0 4px;color:#f8fafc;letter-spacing:-.4px;}}
  .subtitle{{color:#94a3b8;font-size:13px;margin-bottom:18px;}}
  .card{{background:#1e293b;border:1px solid #334155;border-radius:12px;
          padding:16px 18px;margin:12px 0;}}
  .banner{{border-radius:10px;padding:12px 16px;margin:12px 0;font-size:12.5px;}}
  .banner.warn{{background:#422006;border:1px solid #a16207;color:#fde68a;}}
  .banner.ok{{background:#052e16;border:1px solid #15803d;color:#bbf7d0;}}
  table.chain{{width:100%;border-collapse:collapse;font-size:12.5px;}}
  table.chain th{{background:#0f172a;color:#cbd5e1;text-align:left;
       padding:7px 10px;border-bottom:1px solid #334155;}}
  table.chain td{{padding:7px 10px;border-bottom:1px solid #243247;}}
  table.chain td.num{{text-align:right;font-variant-numeric:tabular-nums;}}
  table.chain td.layer{{color:#94a3b8;font-style:italic;}}
  tr.chain-hot td{{background:#2a1215;}}
  tr.chain-hot td.num:nth-child(5){{color:#f87171;font-weight:700;}}
  p.note{{color:#94a3b8;font-size:12px;margin:4px 0 10px;}}
  .card h2{{font-size:14px;margin:0 0 12px;color:#f1f5f9;display:flex;
             align-items:center;gap:8px;}}
  .tag{{font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;
         background:#312e81;color:#a5b4fc;}}
  .kpi-table{{width:100%;border-collapse:collapse;font-size:12px;}}
  .kpi-table th{{background:#0f172a;color:#94a3b8;text-align:left;
                  padding:8px 10px;border-bottom:1px solid #334155;
                  font-size:11px;text-transform:uppercase;letter-spacing:.4px;}}
  .kpi-table td{{padding:8px 10px;border-bottom:1px solid #1e3a5b;
                  vertical-align:middle;}}
  .kpi-table tr:last-child td{{border-bottom:none;}}
  .kpi-table tr:hover td{{background:rgba(99,102,241,0.06);}}
  .metric-name{{color:#94a3b8;white-space:nowrap;font-size:12px;}}
  .baseline{{color:#a5b4fc;font-weight:700;}}
  .good{{color:#4ade80;font-weight:700;}}
  .bad {{color:#f87171;font-weight:700;}}
  .neutral{{color:#e2e8f0;}}
  .diff{{color:#fbbf24;}}
  .delta{{font-size:10px;font-weight:600;opacity:0.85;}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
  @media(max-width:900px){{.two-col{{grid-template-columns:1fr;}}}}
  .chart-wrap{{background:#1e293b;border:1px solid #334155;border-radius:10px;
                padding:12px;margin:6px 0;}}
  .chart-note{{font-size:11px;color:#475569;margin-top:6px;font-style:italic;}}
  .charts-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
  @media(max-width:1000px){{.charts-grid{{grid-template-columns:1fr;}}}}
  .winner-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;}}
  .winner-card{{background:#111827;border:1px solid #334155;border-radius:10px;
                 padding:12px;text-align:center;}}
  .winner-cat{{color:#94a3b8;font-size:10.5px;text-transform:uppercase;
                letter-spacing:.5px;font-weight:700;}}
  .winner-label{{color:#f1f5f9;font-size:13px;font-weight:800;margin:5px 0 3px;}}
  .winner-val{{color:#64748b;font-size:11px;}}
  table.runs{{width:100%;border-collapse:collapse;font-size:12px;}}
  table.runs th{{background:#0f172a;color:#64748b;text-align:left;
                  padding:7px 10px;border-bottom:1px solid #334155;
                  font-size:11px;text-transform:uppercase;}}
  table.runs td{{padding:7px 10px;border-bottom:1px solid #1e3a5b;color:#e2e8f0;}}
  .legend-note{{font-size:11px;color:#475569;margin-top:8px;}}
  h3.layer-h{{font-size:12.5px;margin:18px 0 2px;color:#f1f5f9;
       text-transform:uppercase;letter-spacing:.5px;
       border-left:3px solid #6366f1;padding-left:9px;
       display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;}}
  h3.layer-h:first-of-type{{margin-top:4px;}}
  .layer-by{{font-size:10.5px;color:#64748b;text-transform:none;
       letter-spacing:0;font-weight:400;font-style:italic;}}
.verdict .headline{{font-size:15px;color:#f8fafc;font-weight:700;margin:2px 0 10px;}}
.verdict ul{{margin:4px 0 8px;padding-left:20px;}}
.verdict li{{margin:5px 0;}}
.infer{{background:#111827;border-left:3px solid #f59e0b;border-radius:6px;
  padding:9px 13px;margin:10px 0;color:#e2e8f0;}}
.infer h4{{margin:0 0 4px;font-size:12.5px;color:#fbbf24;}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:10px;margin:8px 0 12px;}}
.tile{{background:#111827;border:1px solid #334155;border-radius:10px;
  padding:10px 12px;}}
.t-lab{{color:#94a3b8;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.4px;font-weight:700;}}
.t-val{{font-size:17px;font-weight:800;color:#f1f5f9;margin:4px 0 2px;
  font-variant-numeric:tabular-nums;}}
.t-unit{{font-size:11px;color:#94a3b8;font-weight:400;margin-left:3px;}}
.t-ratio{{font-size:11px;color:#64748b;}}
.chips{{margin:4px 0 10px;}}
.chip{{display:inline-block;background:#422006;border:1px solid #a16207;
  color:#fde68a;border-radius:12px;padding:2px 10px;margin:2px 6px 2px 0;
  font-size:11.5px;}}
td.good{{color:#4ade80;font-weight:700;}}
td.bad{{color:#f87171;font-weight:700;}}
</style></head>
<body><div class="wrap">

<h1>📊 AMOprof Comparison Report</h1>
<div class="subtitle">{n} runs compared · baseline: <b>{_html.escape(baseline.label)}</b>
 · delta % relative to baseline · <span style="color:#4ade80">green = improvement</span>,
 <span style="color:#f87171">red = regression</span></div>

{_suspect_html}

{_ruled_out_html}

{_variance_html}

{_verdict_html}

{_diag_html}

{_workload_html}

{_timeline_html}

{_chain_html}

{_layer_html}
{_qd_html}

<div class="card">
  <h2>🏃 Runs compared</h2>
  <table class="runs">
    <thead><tr><th>#</th><th>Label</th><th>Raw directory</th>
               <th>Window</th><th>Duration</th></tr></thead>
    <tbody>{run_rows_html}</tbody>
  </table>
  <div class="legend-note">
    Delta % is relative to run 0 ({_html.escape(baseline.label)}).
    Green = improvement over baseline; Red = regression.
  </div>
</div>

<div class="card">
  <h2>🏆 Best in class</h2>
  {winner_summary()}
</div>

<div class="card">
  <h2>⚙️ Configuration</h2>
  {config_table()}
</div>

<div class="card">
  <h2>📐 KPI comparison <span class="tag">DELTA vs BASELINE</span></h2>
  {kpi_rows()}
</div>

<div class="card">
  <h2>🕸️ Performance radar</h2>
  {radar_chart()}
</div>

<div class="card">
  <h2>📈 Charts</h2>
  <div class="charts-grid">
    {charts_html}
  </div>
</div>

</div></body></html>"""


# ─── Entry point ─────────────────────────────────────────────────────────────

def compare_runs(
    runs: List[RunSpec],
    out_html: Path,
    title: str = "",
) -> Path:
    """Extract metrics from all run specs and write a comparison HTML report."""
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    all_metrics = [extract_metrics(spec) for spec in runs]
    html = build_comparison_html(
        all_metrics,
        title=title or f"AMOprof Comparison — {len(runs)} runs",
    )
    out_html.write_text(html, encoding="utf-8")
    log.info("Wrote comparison report: %s (%d KB)", out_html, len(html) // 1024)
    return out_html
