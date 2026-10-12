# Executive report — Bottleneck Analysis correlation changes

All edits are confined to `amoprof/report/combined.py`, inside
`build_executive_summary_html()` (the cross-layer correlation block) plus two
new module-level helpers. No other file in the tree is modified.

`bottleneck_correlation.patch` in this directory is the unified diff against
the previous `combined.py`; `git apply -R bottleneck_correlation.patch` reverts
just this work.

## New charts

**Token movement → configured tier signals.** One card per SGLang movement
counter that saw non-zero activity in the window:

| Driver | Source |
|---|---|
| Evict rate | `Δsglang_evicted_tokens_total ÷ Δt` |
| Load-back rate | `Δsglang_load_back_tokens_total ÷ Δt` |
| Prefetch rate | `Δsglang_prefetched_tokens_total ÷ Δt` |
| Backup rate | `Δsglang_backuped_tokens_total ÷ Δt` |

**Prefill / decode phase activity → configured tier signals.** One card per
phase driver:

| Driver | Source |
|---|---|
| Prefill compute rate | `Δrealtime_tokens_total{mode=prefill_compute} ÷ Δt` (falls back to `prompt_tokens_total`) |
| Prefill cache-hit rate | `Δrealtime_tokens_total{mode=prefill_cache} ÷ Δt` |
| Decode rate | `Δrealtime_tokens_total{mode=decode} ÷ Δt` (falls back to `generation_tokens_total`) |
| Running requests | `sglang_num_running_reqs` gauge |
| Queued requests | `sglang_num_queue_reqs` gauge |

Each card scatters its driver against every signal of every **configured**
tier, ranked by `|Pearson r|` descending:

* **L1** — GPU util (%), HBM used (GB)
* **L2** — DRAM total / read / write BW (GB/s)
* **L3** — read+write BW (MB/s), read+write IOPS, read+write latency (ms),
  queue depth

Tier gating goes through `_tier_signal_bundle(configured, prefix, entries)`.
An unconfigured tier contributes no axis and is omitted from the card title.

## Defect fixes in the existing charts

1. **NVMe bandwidth columns.** The block requested `read_bytes` / `write_bytes`,
   which `writer.write_nvme_driver_timeseries()` does not emit — its contract is
   `rd_bw_mbs` / `wr_bw_mbs` (already MB/s gauges). Both L3 bandwidth cards were
   therefore always empty. Now reads the gauge first and falls back to
   differencing cumulative byte counters when a Prometheus-sourced CSV has them.

2. **DRAM columns.** Requested only `dram_bw_gbps` / `read_bw_gbps` /
   `write_bw_gbps`; the AMDuProf/PCM collectors write `dram_total_gb_s` /
   `dram_read_gb_s` / `dram_write_gb_s`. Now scans the same alias set the KPI
   path uses, so the correlation axis and the DRAM tile read the same column.

3. **Time-based alignment.** `_align_xy()` joins two series on `time_sec` with a
   tolerance of half the coarser median step, replacing index pairing. Needed
   because AMDuProf PCM stays local at `--interval-s 1.0` even when the
   Prometheus-owned CSVs use the 15 s default step. Falls back to the original
   `_align_pair()` when either timebase is absent.

4. **Rate/timestamp desync.** `_rate_with_time()` returns surviving timestamps
   alongside rates. `_rate_from_counter()` skipped `Δt ≤ 0` samples, breaking the
   `len(rate) == len(raw) - 1` assumption index pairing relied on. Values are
   unchanged for existing callers.

5. **Dead IOPS fallback.** `_first_nonempty("rd_iops", "read_iops")` always won,
   so the cumulative-counter branch never ran and a counter could be plotted as a
   gauge. Now checks the gauge spelling alone first.

6. **Duplicate latency charts.** Read and write latency both fell back to the
   combined `await` column, rendering two identical charts. `await` is now used
   once, as a single `r+w lat (ms)` signal, and only when neither
   direction-specific column exists.

7. **Queue depth source.** Now prefers `queue_depth_sources_timeseries.csv`
   (`qd_best_effort → qd → weighted_qd → inflight`, which carries exact blktrace
   Q→C when present) so the correlation axis matches the QD KPI tile. Falls back
   to NVMe `inflight`. The axis label names the column used.

8. **Doubled label prefix.** `L3 · L3 read IOPS` → `L3 · read IOPS`.

## Behaviour changes worth reviewing

**L2 gate tightened.** `_l2_configured` previously fell back to total host DRAM
capacity, so it read true on any host with known DIMMs — including runs with no
hierarchical cache. It now requires positive HiCache evidence: an L2/HiCache
allocation, a truthy `HiCache` setup flag, or `--enable-hierarchical-cache` /
`--hicache-*` in the launch command. When none of those keys exist at all (older
runs with no such metadata) it falls back to the previous capacity test rather
than dropping the card.

**Size caps.** Two constants in the correlation block:

```python
_CORR_MAX_SCATTERS_PER_CARD = 6    # scatters drawn per card
_CORR_MAX_PLOT_POINTS       = 400  # circles plotted per scatter
```

Both are lossless for the reported statistics — `r` is always computed on the
full time-aligned series, decimation only thins plotted points, and every pair
below the cap still appears with its `r` in the card footer. Raise the first
constant to draw every pair again.

## Verification performed

Rendered across seven fixtures (L1+L2+L3, L1+L2, L1-only, and a mixed-cadence
1 s/5 s case). Outside the Bottleneck Analysis section the HTML is byte-identical
to the pre-change build in every case, and no card is lost — the only vanished
titles are renames.

Note: `__version__` in `amoprof/__init__.py` is left at `1.1.0`; bump it if your
release process expects it.

---

# Summary-tile formulas (all reports)

Every summary tile in every report now shows the formula that produced its
number, with exact metric / column names, in place of explanatory prose.

## Single registry — `amoprof/report/metric_formulas.py`

All formula strings live here and nowhere else. 114 tile labels are covered.
Lookup is by normalised label (case, punctuation, and the
`L3 (local storage)` / `L3` backend-name expansion are folded away), so a
tile is wired up by existing — there are no per-call-site formula strings to
drift.

`tile_note(label, existing_note)` returns the registry formula in place of
the old note. Measured values in the original note are preserved and
appended (`P90=1.4s`, `312 M txns/s`, `of 409 GB/s peak`); numeric *legends*
are not (`1.0=no degradation`, `0=uniform, 1=all one region`). A label with
no registry entry returns its note unchanged, so wiring this in is
non-breaking.

## Wire-up — 4 renderers, not 117 call sites

| Report | Renderer | File |
|---|---|---|
| Executive | `kpi_card()` | `report/combined.py` |
| End Report | `bw_card()`, `_kpi()` | `report/amoprof.py` |
| Interactive | `_kpi_tile()` | `report/interactive.py` |

Each calls `_tile_note(label, note)` on entry. Import is guarded so bundled
/ standalone execution falls back to the original note rather than failing.

## Duplication removed

Four separate copies of the same formula/explanation text existed:

1. `amoprof.py::_METRIC_FORMULAS` + `_METRIC_FORMULAS_EXTRA` — the
   §Metrics & Formulas table. Its formula column is now overridden from the
   registry wherever the label matches; the collector and interpretation
   columns still come from those tables.
2. `combined.py` Executive tiles — TTFT / TPOT / cache-hit formulas were
   hardcoded a second time and had already drifted from (1) (the table said
   `× 1000`, the tile did not).
3. `combined.py::_apply_latency_overrides_to_report_html` — passed
   "Canonical selected-window latency KPI" prose that overwrote tile notes
   during combined-report assembly. Those note arguments are now blank, so
   the registry-derived note survives.
4. `common_kpis.py::_note_for_key` — a fifth copy, applied during combined
   assembly. Now routed through `formula_for()`. The cache-hit tile keeps
   its resolved provenance variant appended, since that is a measured fact
   about the run rather than prose.

Items 3 and 4 are why the formulas reach the **combined** report and not
just the standalone tabs.

## Verification

* 114/114 tile labels across the three reports resolve to a formula.
* Combined report rebuilt: all three tabs present, formula strings present
  in each, and an audit for the previous prose strings ("Canonical common
  KPI", "time-weighted average", "max ever observed", "saturation
  indicator", "1.0=no degradation", …) returns zero hits.
* Bottleneck-analysis correlation cards unchanged across all three sample
  runs (13 / 11 / 7 cards).
* `compileall` passes on the package; all report modules import cleanly.

## Not yet covered

The formulas for blktrace-derived access-pattern statistics (`Rd Gini`,
`Skewness`, `Top-1% Share`, `Bursts`, `BW Degrad.`, `Seasonal Period`,
`R↔W Lag`) name the exact source column and give the standard definition of
the statistic. Where the upstream computation is in the analysis stage
rather than in `amoprof.py`, the registry states the source column instead
of reproducing arithmetic that was not verified. Those entries are marked by
their `· blktrace` suffix and are worth a review pass against the analysis
code.

---

# Correlation-chart layout + chart formulas

## Root cause of the clipped charts

`report/combined.py` stylesheet:

```css
.combo-wrap svg { width:100%; min-width:860px; height:auto; }
```

That rule exists for the wide time-series charts. The correlation scatters
reused the same `combo-wrap` class, so every 460px-viewBox scatter was forced
to a **860px minimum** inside a ~430px column, with `overflow-x:auto` on the
wrapper — which is why each chart appeared cut vertically down the middle.
`min-width` overrides the inline `width:100%`, so the inline style never had
a chance.

## Fixes

* Scatters now emit `class="corr-chart"` — a dedicated class with
  `min-width:0`, so the SVG scales to whatever column it lands in.
  `.combo-wrap` and its 860px floor are untouched for the time-series charts.
* Charts are laid out in `class="corr-strip"` — a single non-wrapping
  horizontal row with `overflow-x:auto`, so they sit side by side and the
  strip scrolls rather than wrapping into a narrow column. Chart width is
  `var(--corr-w, 430px)`; a `max-width:900px` media query drops it to 300px.
* In-chart font sizes reduced so chart text is proportional to page text:
  title 12→10, subtitle 10→8.5, Pearson badge 11→9, axis ticks 9→7.5,
  axis titles 10→8.5.

## Chart axis formulas

Each scatter now carries an X/Y formula caption under it, sourced from the
same registry as the tiles via the new
`metric_formulas.axis_formula()`. That helper strips the trailing
parenthesised unit an axis label carries but a tile label does not
(`"L3 · read BW (MB/s)"` → `l3 read bw`) and keeps the tier prefix, because
"read BW" is a different column at L2 than at L3.

Registry entries added for all correlation drivers (evict / load-back /
prefetch / backup, prefill-compute / prefill-cache / decode, running and
queued requests) and all tier signals (L1 util & HBM, L2 DRAM total/read/write,
L3 BW / IOPS / latency / queue depth).

Verified: 64 charts rendered on the full-tier sample, **0 missing an axis
formula**; combined report carries 16 strips / 67 charts / 84 formula
captions; tile coverage still 114/114.

---

# Fix: ModuleNotFoundError when amoprof.py runs as a script

`report/amoprof.py` is invoked two ways: imported as `amoprof.report.amoprof`,
and spawned directly as a script by `cli._run_amoprof()`
(`[sys.executable, ".../report/amoprof.py", "--raw", ...]`). In the second
case `amoprof` resolves to that module itself, not to the package, so
`from amoprof.report.metric_formulas import ...` raises

    ModuleNotFoundError: No module named 'amoprof.report'; 'amoprof' is not a package

The registry import at module top was already guarded for this, but the
formula-table wiring added a **second, unguarded** import inline inside
`build_html()`. That import ran on every static-report build, so the End
Report failed and the combined report was skipped.

Fix: `formula_for` (and `axis_formula`) moved into the existing module-level
guarded block, and the inline import removed. All registry imports across
`combined.py`, `interactive.py`, `common_kpis.py` and `amoprof.py` are now
inside try/except with a `from metric_formulas import ...` fallback (which
resolves in script mode, since `sys.path[0]` is the `report/` directory) and
a final no-op fallback.

Verified by reproducing the traceback against the previous package and then
running the real path:

* `cli._run_amoprof()` — exit 1 before, exit 0 after
* End Report built in script mode: 4.2 MB, registry formulas present, zero
  leftover prose
* Full chain static (subprocess) → interactive → combined: 10.2 MB, all
  three tabs, 16 correlation strips / 67 charts / 84 axis-formula captions,
  no clipped scatters

---

# E2E latency correlations + server/GPU config capture

## New card: Input / Output tokens vs E2E latency

Executive → Bottleneck Analysis now carries a tier-independent card scattering
per-interval mean E2E latency against prefill and decode token rate.

Latency series = `Δsglang_e2e_request_latency_seconds_sum ÷
Δsglang_e2e_request_latency_seconds_count × 1000` computed per sampling
interval — the same identity the E2E KPI tile uses. Intervals that completed no
requests (`Δcount == 0`) are dropped together with their timestamp, so the
series stays time-alignable via `_align_xy`.

Emitted regardless of configured tiers, since latency is a request property —
on an L1-only run it is the only cross-layer attribution available.

## Server info was silently never fetched

`cli.py::_fetch_sglang_server_info()` built its candidate URL list *only* from
`--server-info-url` or `--sglang-port`. With neither set the list was empty, the
function returned `{}`, and the warning was guarded on `if urls:` — so
`amoprof service` without `--sglang-port` produced no `setup_details.json` and
an empty Server Info panel, with nothing in the log.

Now: candidate ports are the explicit `--sglang-port`, any port recoverable from
a metrics/Prometheus URL already passed, then the SGLang defaults 30000 and
8000. The warning is unconditional and names the endpoints tried and the flag
that fixes it.

## New: raw/gpu_config.json from nvidia-smi

Nothing captured the static GPU inventory — the time-series collector polls
utilization/memory but never recorded device model, count or `memory.total`, so
reports inferred GPU identity and HBM capacity from `setup_details.json` (i.e.
from server_info). When server_info was missing, both were wrong.

`cli._write_gpu_config()` queries
`nvidia-smi --query-gpu=index,name,uuid,memory.total,compute_mode,pcie...` and
writes per-GPU entries plus `gpu_count`, `hbm_per_gpu_gb`, `hbm_total_gb`,
`driver_version`. It then reads `server_info.json` for TP/DP and records
`gpus_in_use = TP × DP` (clamped to the physical count) and
`hbm_capacity_gb = hbm_per_gpu_gb × gpus_in_use`.

Called after `_write_setup_details_from_server_info()` — so TP/DP are available —
at all three `_collect`/`_analyze` sites and once per `service` cycle
(`service.py`). Absent nvidia-smi it returns `{}` and writes nothing; the
previous inference path still applies.

## HBM capacity now hardware-derived

`report/combined.py` prefers `gpu_config.json` for GPU model, physical device
count and per-GPU HBM capacity, falling back to the old setup_details/regex
inference only when the file is absent. `active_gpu_count` still resolves to
TP × DP; `gpus_in_use` from gpu_config is used when TP is not otherwise known.

Verified: with an 8×A100-40GB / TP=8 `gpu_config.json`, the "HBM used (all
GPUs)" tile denominator resolves to 320 GB from nvidia-smi `memory.total`
rather than an inferred value.
