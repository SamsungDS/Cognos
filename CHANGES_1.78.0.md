# AMOprof 1.78.0

1.77.0 (see `CHANGES_1.77.0.md`) merged with `main`. This release is what the
repository holds after that merge: everything in 1.77.0, nsarras's three
`main` commits that the package line never had, and the decisions taken where
the two overlapped.

## From main

- **KV utilization per tier** (236fe69): one tile per memory tier — fill %,
  peak, used/capacity tokens, provenance, and a stated reason when a tier
  reports nothing.
- **Duplicate TPOT graph removed** (b57e5ee).
- **Report accuracy and consistency fixes** (c62290f):
  - `amoprof_*` service summaries are built from every cycle in the analysed
    window, so reruns of a window are reproducible.
  - KV tokens are counted once across TP/PP ranks (they had been summed, 8x
    on TP=8) — now decided from the data, see below.
  - End Report run duration from the window span; sub-second durations no
    longer inflate KV movement rates.
  - `--setup-details` is merged into the existing setup file.
  - Histogram label sets summed per bucket; whole-window p50 in every tab;
    whole-run percentiles drawn on the over-the-run charts.
  - In-use KV no longer double-counted in the HBM composition.
  - Token_Reuse_Density; legends moved off plots; timelines span the run.
  - Executive latencies print like the KPI tiles (6730 ms, no comma).

## Where both lines changed the same thing

- Histograms with several label sets: main's `_amoprof_bucket_series` (it
  back-fills a series' leading gap, so a label set first seen mid-window does
  not count its lifetime total as new requests).
- Service summaries: main's aggregation over all cycles in the window.
- KPI grid: main's KV utilization tiles replace the package's per-tier KV
  residency tiles; each sits beside its tier's raw usage tile. The L2
  estimate keeps the label **L2 KV residency (est.)**.
- Run window: the package's plausible-window resolution, which also reports
  conflicting window lengths.

## New: KV-counter ranks combined by what the data shows

KV-movement token counters are exported once per rank. TP, PP and EP-over-TP
ranks count the same tokens (max); ranks serving different requests — e.g.
DP-attention on a build that labels them `tp_rank` only — must be summed.

- `metric_kernels.rank_combine_rule` compares the ranks' window deltas:
  within 1% they are replicas (max), otherwise shards (sum). `dp_rank` and
  other label sets are still summed.
- The Prometheus fetch queries these counters per rank and combines them by
  that rule, still writing one column per counter; the rule used is recorded
  in `sglang_summary.json` (`kv_rank_rules`) and stated on the KV movement
  chart.
- `compare` counts KV-movement tokens with the same reader (it summed every
  column, TP x on local runs with per-rank columns).

## Tests

- `tests/test_rank_rule.py` (new): TP, PP, EP over TP, DP with and without a
  `dp_rank` label, scrape noise, the fetch combiner, and compare.
- Package tests updated for the merge decisions (tile-style latency text, the
  L2 label, `test_tier_residency_tiles.py` retargeted to the utilization
  tiles, service-summary aggregation).
- Known failures, unchanged from `main`:
  `test_kv_token_accounting.py::test_phase_analysis_shows_token_reuse_density`
  and `test_executive_symbol_regression.py::test_ssd_bw_pct_initializer_before_first_use`.
