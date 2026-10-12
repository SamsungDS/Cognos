# AMOprof 1.77.0

## compare — finds why one run finished first

The comparison report now leads with a diagnosis instead of window means.

- **Verdict card** per comparison run: which run served the workload faster
  and by how much (time to complete, or request throughput when the
  workloads differ), KPI tiles (baseline → comparison), an evidence table
  with ratios and short readings, flag chips for configuration problems, and
  a one-line *inferred* mechanism with the checks that would confirm it.
- **Diagnosis charts**: ratio to baseline for every key figure (log axis),
  where the time went (busy / stalled / idle / between batches), backing-tier
  delivery, GPU utilisation vs requests waiting, and a Pearson correlation
  heatmap per run across GPU util, waiting requests, decode batch, L1 KV fill,
  prefetch rate and backup rate.
- **Timeline** per run: GPU utilisation against waiting requests and decode
  batch, stall episodes shaded.
- **Stall detection** (`metric_kernels.admission_stalls`): idle time is split
  into *stalls* (GPUs idle while requests wait to enter prefill), idle with no
  work, and idle between batches. The "compare the active-span rows" advice is
  withdrawn when most idle time was stalls, since the active-span correction
  would excuse exactly the stall.
- New per-run figures: requests completed, time to complete, request rate,
  GPU-busy time, mean queue wait, prefetch/backup rates, tokens returned ÷
  absorbed, when prefetch went silent, HiCache page size, and the storage
  backend the engine ran against the one the launch command asks for.
- KPI table and Best-in-class gain time to complete, request throughput,
  queue wait, decode batch and prefetch rate.

### compare fixes

- The A5 scheduler-queue rows read `num_queue_reqs` / `num_running_reqs` by
  exact column name, which fetched CSVs never use; they were missing from
  every fetched comparison.
- GPU utilisation, HBM fill and DCGM activity read only `gpu_summary.json`;
  they now fall back to `gpu_timeseries.csv`, so the GPU chart and A4 table
  no longer say "not collected" when the data is there.
- Dual-axis bar charts drew the right-axis series over the left-axis ones
  (TPOT hid TTFT/E2E, read IOPS hid read BW).

## analyze — latency figures from multi-series histograms

A histogram that arrives as several labelled series (one per label set the
server or the scrape adds) is now read as one histogram, the way Prometheus'
`sum()` and `histogram_quantile(q, sum by (le) (...))` read it.

- **TTFT and E2E means could be identical.** The canonical KPI helper
  (`common_kpis`) and the Interactive tab took the *first* matching
  `_sum`/`_count` column, i.e. one series' share of the requests. When that
  series' TTFT equals its E2E (requests answered in one chunk record their
  first token at the end) every tab showed the same number for both. Means
  are now ΣΔsum ÷ ΣΔcount over every series, reset-safe.
- **Percentiles snapped to bucket edges** (800 / 8,000 / 400,000 ms). Each
  series' `le` was treated as its own bucket, so a quantile landing in the
  second of two same-`le` buckets interpolated between lo == hi and returned
  the edge, and only one series' observations were counted. A single reader
  (`_amoprof_bucket_series`) now sums every series per `le` with rows aligned
  on time, and feeds the whole-window percentiles, the per-interval
  percentile charts, and the bucket-occupancy chart. The per-interval path
  no longer returns a bucket's upper edge in its degenerate branch.
- **Executive Summary dropped** on runs with no L3.5 data and a missing
  token counter: an empty-series chart raised inside the correlation block,
  leaving `_l35s` unbound, and the KPI grid's NameError discarded the whole
  tab. The chart now returns nothing for empty input and the device-series
  dict is bound before the block.

## install.sh and packaging

- **Python floor read from `pyproject.toml`.** The preflight accepted 3.10+
  while the package requires 3.12 (`requires-python`), so on 3.10/3.11 it
  passed and pip then refused the install part-way. It now reads
  `requires-python` and stops before touching anything. `INSTALL.md`, the
  README dependency table and `report/requirements.txt` said 3.10 too.
- **`--with-dram-deps` no longer needs the execute bit.** The helper was
  required to be executable, and the 1.76.0 zip shipped every script
  without it, so the option always aborted. It is now run through `bash`,
  and the zip carries `+x` on `install.sh` and `scripts/*.sh`.
- **venv failures are clean.** On a Python without `ensurepip`
  (Debian/Ubuntu without `pythonX.Y-venv`) venv creation failed after making
  the directory, and the next run "reused" the half-built one. The partial
  directory is now removed with the exact package to install, and an
  existing directory without `bin/activate` is refused rather than reused.
- Help text: the `--with-pcm` options are listed under Options, and
  `--full` says what it adds over `--sglang`.

## Tests

- `tests/test_compare_stall_verdict.py` (74 checks)
- `tests/test_analyze_latency_series.py` (19 checks; 14 of them fail on 1.76.0)
