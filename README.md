# AMOprof — AI Memory & I/O Profiler

AMOprof is a profiling and reporting toolkit for AI inference stacks that use GPU HBM, host DRAM, and NVMe SSD tiers for KV-cache movement. It collects or imports SGLang, GPU, NVMe, blktrace, biosnoop, vmstat, power, and optional AMDuProf/NSight data, then produces static and interactive HTML reports that correlate model-serving behavior with hardware bottlenecks.

This package version includes the cache-hit, percentile, blktrace, biosnoop, large-trace, pandas-compatibility, and static/interactive SSD chart fixes discussed during the v1.22 → v1.27 iterations.

---

## 1. What AMOprof answers

AMOprof is designed to answer questions such as:

- Is TTFT high because prefill compute is expensive, because KV cache is missing, or because the server is queued?
- Is decode slow because GPU/HBM is saturated, or because KV blocks are being loaded from host DRAM/NVMe?
- Are L3 SSD reads bursty, random, misaligned, or concentrated in hot LBA regions?
- Are write-back / backup / eviction paths stressing SSD endurance?
- Is SGLang cache-hit rate consistent between benchmark output, Prometheus gauges, and report KPIs?
- Are p50/p90/p99 latency tails correlated with GPU, HBM, NVMe, or system memory behavior?

The tool is most useful for SGLang deployments using hierarchical cache / KV-cache offload, but many GPU, Prometheus, NVMe, and block I/O sections also work for other inference stacks.

---

## 2. Package layout

```text
amoprof/
├── cli.py                         # main CLI: collect/analyze/retime
├── collectors.py                  # live collectors: GPU, iostat, vmstat, blktrace, biosnoop, etc.
├── collectors_extra.py            # optional collectors and helpers
├── prometheus_source.py           # Prometheus discovery/query/range fetch logic
├── percentiles.py                 # histogram_quantile() fetch/merge support
├── blktrace_analyzer.py           # streaming large-blktrace analyzer
├── bench_summary.py               # bench_serving/perf summary parser
├── report/
│   ├── amoprof.py                 # static HTML report generator
│   ├── interactive.py             # Plotly interactive report generator
│   ├── enhancer.py                # post-processing/theme/highlight enhancer
│   └── ai_metrics_dict.py         # metric glossary/purpose descriptions
├── analysis.py                    # analysis helpers
├── writer.py                      # output writer helpers
├── retime.py                      # time-axis repair for legacy run dirs
├── preflight.py                   # collector preflight checks
├── benchmark.py                   # benchmark helpers
├── bench_sglang.py                # SGLang benchmark wrapper
├── bench_swebench.py              # SWE-bench benchmark wrapper
├── dashboard/                     # optional dashboard assets
├── setup.py
├── pyproject.toml
└── README.md
```

---

## 3. Installation

### 3.1 Python environment

```bash
python3 -m venv ~/amoprof-venv
source ~/amoprof-venv/bin/activate
pip install --upgrade pip
pip install -e .
```

For report generation, install the Python dependencies if they are not already pulled in:

```bash
pip install pandas numpy matplotlib plotly requests python-dateutil
```

### 3.2 System packages

Install only the tools you plan to use. Missing tools are skipped, but the corresponding report panels will be empty or marked as unavailable.

#### Ubuntu / Debian example

```bash
sudo apt-get update
sudo apt-get install -y \
  sysstat blktrace bpfcc-tools linux-tools-common linux-tools-generic \
  jq curl tar gzip zstd
```

#### RHEL / CentOS / Fedora example

```bash
sudo dnf install -y \
  sysstat blktrace bcc-tools kernel-tools jq curl tar gzip zstd
```

### 3.3 Optional GPU and platform tools

| Tool | Purpose | Notes |
|---|---|---|
| `nvidia-smi` | GPU utilization, memory, power, temperature | Installed with NVIDIA driver |
| DCGM / dcgm-exporter | GPU/HBM metrics via Prometheus | Recommended for long runs |
| `iostat` | NVMe IOPS/BW/latency | From `sysstat` |
| `blktrace` + `blkparse` | Per-request block I/O events | Requires root |
| `biosnoop-bpfcc` | Per-PID I/O attribution | Requires BCC/eBPF + root |
| `AMDuProfPcm` | AMD EPYC DRAM bandwidth | Optional; parser accepts raw PCM output |
| `nsys` | CUDA trace | Optional |
| Prometheus | SGLang/DCGM/node exporter metrics | Strongly recommended |

---

## 4. Quick start

### 4.1 Analyze a previous run directory with Prometheus merge

This is the most common flow when local storage data is in a run directory but SGLang/GPU metrics are fetched from Prometheus.

```bash
amoprof analyze \
  --run-dir /path/to/metrics_run_YYYYMMDD_HHMMSS \
  --prometheus http://PROMETHEUS:9090 \
  --prom-step 30 \
  --start 1778871540 \
  --end 1778877078 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --output-dir ./results \
  --bench-summary ./perf_metrics_summary.txt \
  --sglang-page-size 1 \
  --amoprof-report \
  --interactive-report
```

Expected outputs:

```text
metrics_run_YYYYMMDD_HHMMSS/
├── amoprof_report.html
├── amoprof_interactive.html
└── raw/
    ├── sglang_timeseries.csv
    ├── sglang_summary.json
    ├── sglang_percentiles_timeseries.json
    ├── gpu_timeseries.csv
    ├── gpu_summary.json
    ├── nvme_driver_timeseries.csv
    ├── vmstat_timeseries.csv
    ├── blkparse_events.generated.csv
    ├── request_size_distribution.csv
    ├── interarrival_distribution.csv
    ├── temporal_read_write_trim_pattern.csv
    ├── hot_regions_overall.csv
    ├── hot_regions_by_time_window.csv
    └── summary.json
```

### 4.2 Prometheus-only analysis

```bash
amoprof analyze \
  --prometheus http://PROMETHEUS:9090 \
  --start "2026-05-15T18:59:00Z" \
  --end   "2026-05-15T20:31:18Z" \
  --prom-step 30 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --output-dir ./results \
  --sglang-page-size 1 \
  --amoprof-report \
  --interactive-report
```

### 4.3 Live collection

```bash
sudo amoprof collect \
  --duration-s 300 \
  --sglang-port 30000 \
  --ssd-device /dev/nvme0n1 \
  --enable-all \
  --sglang-page-size 1 \
  --amoprof-report \
  --interactive-report
```

For live blktrace/biosnoop collection, run as root or with enough privileges for block tracing and eBPF.

---

## 5. Main CLI commands

| Command | Purpose |
|---|---|
| `amoprof collect` | Capture a live profiling run from local tools |
| `amoprof analyze` | Generate reports from a run dir, Prometheus, or merged sources |
| `amoprof retime` | Repair legacy time-axis offsets in existing run dirs |

### 5.1 `analyze` source modes

#### Local-only

```bash
amoprof analyze \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --amoprof-report \
  --interactive-report
```

#### Prometheus-only

```bash
amoprof analyze \
  --prometheus http://PROMETHEUS:9090 \
  --start "2026-05-15T18:59:00Z" \
  --end "2026-05-15T20:31:18Z" \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --output-dir ./results \
  --amoprof-report \
  --interactive-report
```

#### Merge local storage traces with Prometheus server metrics

```bash
amoprof analyze \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --prometheus http://PROMETHEUS:9090 \
  --start 1778871540 \
  --end 1778877078 \
  --prom-step 30 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --prefer local \
  --amoprof-report \
  --interactive-report
```

In recent versions, SGLang Prometheus files are refreshed for the requested `--start/--end/--prom-instance` window, while local-only storage files such as blktrace and biosnoop are kept from the run directory.

---

## 6. Cache-hit rate methodology

AMOprof reports multiple cache-hit values because SGLang exposes both counters and gauges, and these answer different questions.

### 6.1 Script-compatible active gauge average

This matches the standalone script that averages `sglang_cache_hit_rate` samples after filtering idle zeros:

```text
active_gauge_avg = avg(sglang_cache_hit_rate samples where value > 0) × 100
```

This is useful when you want the report to match a Prometheus script like:

```python
hit_rates = [float(sample[1]) for sample in raw_samples]
active_samples = [rate for rate in hit_rates if rate > 0]
active_avg = sum(active_samples) / len(active_samples) * 100
```

Example interpretation:

```text
Gauge active average:   59.43%
Gauge timeline average:  6.43%
Gauge peak:             99.62%
Active windows:         20 / 185
```

The timeline average is lower because it includes idle scrape intervals where the gauge is zero.

### 6.2 Token-weighted / benchmark-style cache hit

This uses token deltas over the selected window:

```text
token_weighted = Δprefill_cache_tokens / (Δprefill_cache_tokens + Δprefill_compute_tokens) × 100
```

Depending on which SGLang metrics are available, AMOprof may derive this from:

```text
sglang:realtime_tokens_total{mode="prefill_cache"}
sglang:realtime_tokens_total{mode="prefill_compute"}
```

or from compatible counter alternatives such as cached/prompt token counters.

### 6.3 What the main KPI uses

Current behavior:

1. If `sglang_cache_hit_rate` gauge samples are available, the top KPI uses the **script-compatible active gauge average**.
2. The Cache Hit Methodology section still shows token-weighted, active-gauge, timeline-gauge, and peak-gauge values side by side.
3. `sglang_summary.json` records `cache_hit_calc_method` so you can see which path was used.

This makes it clear why benchmark output, token-weighted counters, and active gauge averages can differ.

---

## 7. Percentile metrics

When Prometheus is supplied, AMOprof fetches percentile time series using `histogram_quantile()` for metrics that expose Prometheus histogram buckets.

Typical percentile panels:

| Panel | Source |
|---|---|
| Server TTFT P50/P90/P99 | `sglang_time_to_first_token_seconds_bucket` |
| Server ITL/TPOT P50/P90/P99 | SGLang inter-token latency histogram bucket, if exposed |
| Server E2E P50/P90/P99 | SGLang request/e2e latency histogram bucket |
| Prompt/output token percentiles | Benchmark summary or Prometheus histograms, if available |
| SSD request-size percentiles | blktrace compact analysis |

The generated files include:

```text
raw/sglang_percentiles_timeseries.json
raw/sglang_summary.json
```

The static report includes a P50/P90/P99 summary chart. The interactive report includes time-series percentile charts where the data is available.

---

## 8. Blktrace and biosnoop data flow

### 8.1 Why blktrace can become huge

A busy NVMe device can generate tens or hundreds of millions of block events. A parsed `blkparse_events.generated.csv` can easily reach several GB. Loading that directly into pandas for HTML report generation is slow and memory-heavy.

Recent package versions avoid this by treating the raw event CSV as evidence and producing compact aggregate analysis files.

### 8.2 Large blktrace behavior

Default behavior:

```text
If blkparse_events.generated.csv > 256 MB:
  skip raw --blktrace load
  use compact blktrace-analysis CSVs instead
```

Log example:

```text
blkparse_events.generated.csv is 6644 MB; skipping raw --blktrace load and using pre-aggregated blktrace analysis files instead
[blktrace-analysis] Loading directory: .../raw
Skipping raw events CSV load (6644 MB); using compact blktrace-analysis CSVs only
```

Override threshold:

```bash
export AMOPROF_MAX_RAW_BLKTRACE_CSV_MB=1024
```

Disable/adjust sampled request-size events:

```bash
export AMOPROF_BLKTRACE_EVENT_SAMPLE_LIMIT=200000
# or disable event sampling:
export AMOPROF_BLKTRACE_EVENT_SAMPLE_LIMIT=0
```

### 8.3 Compact blktrace analysis files

The streaming analyzer writes files such as:

| File | Purpose |
|---|---|
| `summary.json` | Read/write/trim totals, event counts, mean BW, alignment, random/sequential stats |
| `bandwidth_per_stream.csv` | Per-stream or per-window bandwidth |
| `bandwidth_per_stream_summary.csv` | Stream-level rollup |
| `request_size_distribution.csv` | Request-size histogram/sample for read/write/trim |
| `interarrival_distribution.csv` | I/O inter-arrival distribution |
| `temporal_read_write_trim_pattern.csv` | Time-windowed read/write/trim pattern |
| `burst_temporal_windows.csv` | Burst detection windows |
| `hot_regions_overall.csv` | Global hot LBA regions |
| `hot_regions_by_time_window.csv` | Hot regions over time |
| `access_skew_summary.csv` | LBA access skew metrics |
| `bandwidth_degradation.csv` | Long-run bandwidth trend/degradation |
| `request_size_random_seq_correlation.csv` | Request-size vs sequential/random correlation |

The static report and interactive report should use these compact files when the raw CSV is too large.

### 8.4 Static §C/§D/§E SSD charts

The `KV$ SSD I/O Workload Characteristics — C Read / D Write / E Trim` section depends on blktrace-derived fields. It should populate from compact analysis even when raw events are skipped.

If this section says `blktrace not loaded`, check:

```bash
ls -lh raw/summary.json \
       raw/request_size_distribution.csv \
       raw/interarrival_distribution.csv \
       raw/temporal_read_write_trim_pattern.csv
```

Also check the report log for:

```text
[blktrace-analysis] Loading directory: .../raw
Analysis keys: scalar=['summary'] dataframes=[...]
[blktrace analysis] Rd=<non-zero>GB Wr=<non-zero>GB ...
```

If only `Analysis keys: ['summary']` appears, the report may not be discovering the compact CSVs, or the files may be empty / named differently.

### 8.5 Biosnoop normalization

Biosnoop is used for per-PID/per-command I/O attribution. AMOprof normalizes common biosnoop outputs into canonical fields:

```text
time_sec, type/op, sector, size_bytes, offset_bytes, lat_ms, pid, comm, disk
```

Supported file names include:

```text
biosnoop.csv
biosnoop_events.csv
biosnoop_timeseries.csv
```

If biosnoop charts are empty, verify:

```bash
head -5 raw/biosnoop.csv
head -5 raw/biosnoop_events.csv
head -5 raw/biosnoop_timeseries.csv
```

The file must contain actual rows, not only a header or collector window markers.

---

## 9. AMDuProf PCM notes

AMDuProf PCM output can be CSV-like but not always valid rectangular CSV. If you see:

```text
amduprof_pcm_raw.csv: Error tokenizing data. C error: Expected 2 fields in line 16, saw 4
```

then the raw PCM file is not parseable by the current strict CSV path. Workarounds:

1. Preserve the raw text file for manual inspection.
2. Export AMDuProf PCM in a stable CSV mode if available.
3. Use the report without DRAM-bandwidth charts until the parser is hardened for that specific PCM output format.

This warning does not affect SGLang, GPU, NVMe driver, blktrace, or biosnoop sections.

---

## 10. Interactive report behavior

The interactive report is generated as:

```text
amoprof_interactive.html
```

It uses Plotly and supports:

- Hover for exact values
- Click legend traces to hide/show
- Drag to zoom
- Double-click to reset

Some charts may be empty for legitimate reasons:

| Empty chart | Common reason |
|---|---|
| KV Cache Tier Occupancy | SGLang does not expose tier-labelled `cached_tokens_total{source=...}` |
| L3 SSD KV movement | SGLang does not expose backup/load-back/prefetch/evict counters, or labels differ |
| Swap storm | vmstat swap/page counters absent or all zero |
| DRAM bandwidth | AMDuProf PCM parse failed |
| Biosnoop PID I/O | biosnoop output has no rows or only window markers |
| Blktrace LBA/hot-region | compact blktrace analysis files missing or empty |

Recent versions include fallback logic so the interactive KV-cache tier chart can use derived L3 movement/residency signals from backup/prefetch/load-back/eviction counters when tier-labelled occupancy metrics are absent.

---

## 11. Common commands and validation checks

### 11.1 Confirm cache-hit samples were ingested

```bash
grep -i "cache_hit" raw/sglang_summary.json
```

Expected useful fields include:

```json
{
  "cache_hit_pct": 59.43,
  "cache_hit_calc_method": "gauge_active_average_script_compatible",
  "cache_hit_gauge_active_avg_pct": 59.43,
  "cache_hit_gauge_timeline_avg_pct": 6.43,
  "cache_hit_gauge_peak_pct": 99.62,
  "cache_hit_gauge_active_samples": 20,
  "cache_hit_gauge_total_samples": 185
}
```

### 11.2 Validate Prometheus gauge manually

```bash
curl -G 'http://PROMETHEUS:9090/api/v1/query_range' \
  --data-urlencode 'query=sglang_cache_hit_rate{instance="msl-ssg-dgx1.msl.lab:30000"}' \
  --data-urlencode 'start=2026-05-15T18:59:00Z' \
  --data-urlencode 'end=2026-05-15T20:31:18Z' \
  --data-urlencode 'step=30s' | jq '.data.result[0].values | length'
```

### 11.3 Confirm blktrace compact analysis exists

```bash
ls -lh raw/summary.json \
       raw/request_size_distribution.csv \
       raw/interarrival_distribution.csv \
       raw/temporal_read_write_trim_pattern.csv \
       raw/hot_regions_overall.csv \
       raw/hot_regions_by_time_window.csv
```

### 11.4 Check blktrace summary values

```bash
jq . raw/summary.json | head -80
```

Look for non-zero values like:

```json
{
  "read_events": 101476895,
  "write_events": 130255,
  "trim_events": 0,
  "read_bytes_total": 123456789,
  "write_bytes_total": 123456
}
```

### 11.5 Confirm report did not load the giant raw event CSV

Expected log:

```text
Skipping raw events CSV load (6644 MB); using compact blktrace-analysis CSVs only
```

If the report is slow or memory-heavy, check whether raw CSV loading was accidentally enabled:

```bash
echo $AMOPROF_MAX_RAW_BLKTRACE_CSV_MB
```

---

## 12. Troubleshooting

### 12.1 Report generation is very slow after blktrace parsing

Cause: `blkparse_events.generated.csv` is huge and is being loaded directly.

Fix:

```bash
export AMOPROF_MAX_RAW_BLKTRACE_CSV_MB=256
export AMOPROF_BLKTRACE_EVENT_SAMPLE_LIMIT=200000
```

Then rerun `amoprof analyze`.

### 12.2 `blkparse output ... regex matched 0 events`

Cause: `blkparse` output format changed or a summary-only output mode was used.

Fix in recent package: normal parsing avoids `blkparse -O` for per-event output.

Manual check:

```bash
blkparse -i raw/blktrace_data/trace | head -50
```

You should see per-event lines with read/write/trim operations.

### 12.3 Static SSD §C/§D/§E charts are empty but interactive report shows Block IOs

Cause: report wiring issue or compact analysis files not discovered.

Check log:

```text
[blktrace-analysis] Loading directory: .../raw
Analysis keys: scalar=['summary'] dataframes=[...]
```

If it says only `summary`, verify that the compact CSVs exist and have rows.

### 12.4 Cache hit is not matching standalone script

Check whether the report ingested `sglang_cache_hit_rate` gauge samples:

```bash
grep -i "cache_hit_gauge" raw/sglang_summary.json
```

If active samples are `0 / 0`, the Prometheus gauge series was not fetched or not merged into the report input.

Possible causes:

- Wrong `--prom-instance`
- Wrong `--start/--end`
- Local stale `sglang_summary.json` overriding Prometheus data
- Metric name differs in this SGLang version

Use:

```bash
amoprof analyze --prometheus http://PROMETHEUS:9090 --list-targets
```

and then query the exact instance.

### 12.5 `--bench-summary file not found`

Pass an absolute path or a path relative to the current working directory:

```bash
--bench-summary /root/mandar/.../perf_metrics_summary.txt
```

If the benchmark file is missing, report generation still works, but benchmark-specific comparison and some percentile annotations may be absent.

### 12.6 Timestamps show 1970 in the interactive report

Cause: the data was plotted using relative seconds as Unix epoch timestamps.

This is cosmetic if relative time is intended, but if absolute wall-clock time is required, ensure the run metadata contains `t0_epoch` and that the interactive report applies it when converting `time_sec` to datetime.

### 12.7 `NDFrame.fillna() got an unexpected keyword argument 'method'`

Cause: pandas compatibility issue around `fillna(method="ffill")`.

Fixed in v1.27 by using:

```python
.ffill().fillna(...)
```

---

## 13. Report sections and data dependencies

| Report section | Primary files/metrics | Empty if |
|---|---|---|
| Header KPIs | `sglang_summary.json`, `gpu_summary.json`, `summary.json` | source summaries absent |
| Cache Hit Methodology | `sglang_cache_hit_rate`, SGLang token counters | gauge/counter metrics absent |
| P50/P90/P99 Summary | `sglang_percentiles_timeseries.json`, benchmark summary | histogram buckets absent |
| GPU Utilization / HBM / Power | `gpu_timeseries.csv`, DCGM | GPU/DCGM data absent |
| AI Operation Phase | SGLang summary/timeseries | SGLang scrape absent |
| KV Cache Tiering | SGLang cache/tier metrics | tier counters absent |
| NVMe Driver Timeline | `nvme_driver_timeseries.csv`, node exporter | iostat/node data absent |
| KV$ SSD I/O Workload §C/§D/§E | compact blktrace analysis CSVs | blktrace missing or empty |
| Per-PID I/O | biosnoop files | biosnoop missing or empty |
| DRAM Bandwidth | AMDuProf PCM output | PCM missing/unparseable |
| Swap Storm | vmstat files | counters missing or zero |
| Interactive Report | same source files | individual charts depend on source availability |

---

## 14. Recommended full workflow

```bash
# 1. Activate environment
source ~/amoprof-venv/bin/activate

# 2. Keep huge blktrace raw CSV out of report memory path
export AMOPROF_MAX_RAW_BLKTRACE_CSV_MB=256
export AMOPROF_BLKTRACE_EVENT_SAMPLE_LIMIT=200000

# 3. Generate reports from existing run + Prometheus window
amoprof analyze \
  --run-dir /root/mandar/amo_prof/amoprof_1_17/amoprof_results/metrics_run_20260515_115803 \
  --prometheus http://105.128.44.21:9090 \
  --prom-step 30 \
  --start 1778871540 \
  --end 1778877078 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --output-dir ./results \
  --bench-summary /absolute/path/to/perf_metrics_summary.txt \
  --sglang-page-size 1 \
  --amoprof-report \
  --interactive-report

# 4. Validate cache hit and blktrace ingestion
grep -i "cache_hit" /root/mandar/amo_prof/amoprof_1_17/amoprof_results/metrics_run_20260515_115803/raw/sglang_summary.json
ls -lh /root/mandar/amo_prof/amoprof_1_17/amoprof_results/metrics_run_20260515_115803/raw/request_size_distribution.csv
jq . /root/mandar/amo_prof/amoprof_1_17/amoprof_results/metrics_run_20260515_115803/raw/summary.json | head -80
```

---

## 15. Version notes for this package

This package includes fixes made across the recent iterations:

- Added Cache Hit Methodology section.
- Added script-compatible `sglang_cache_hit_rate` active-average KPI.
- Preserved token-weighted cache-hit as a separate methodology value.
- Added P50/P90/P99 summary and percentile time-series support.
- Refreshed SGLang Prometheus data for the selected time window during merge.
- Fixed blktrace parsing by avoiding summary-only `blkparse -O` output for per-event parsing.
- Added biosnoop normalization into canonical I/O fields.
- Added streaming large-blktrace analysis and compact aggregate CSV generation.
- Skipped raw multi-GB `blkparse_events.generated.csv` during report generation by default.
- Wired static §C/§D/§E SSD charts to compact blktrace analysis files.
- Added interactive fallback behavior for KV-cache tier charts where tier-labelled metrics are absent.
- Fixed pandas compatibility issue caused by `fillna(method="ffill")`.
- Fixed flat vs nested `summary.json` handling for blktrace aggregate totals.

---

## 16. Safety and overhead notes

- `blktrace` can create very large files quickly on busy NVMe devices. Monitor disk space.
- `biosnoop` and BCC tools may require kernel headers and root privileges.
- `AMDuProfPcm` may require MSR access and platform-specific permissions.
- Prometheus-only analysis is safest for production systems because it does not attach additional local tracers.
- For long storage runs, prefer compact blktrace analysis over raw per-event report loading.

---

## 17. Minimal bug report template

When reporting an AMOprof issue, include:

```text
AMOprof version/package:
Command used:
Run directory path:
Prometheus URL/instance/start/end/step:
Relevant log excerpt:
Files present under raw/:
  ls -lh raw | head -100
Cache hit summary:
  grep -i cache_hit raw/sglang_summary.json
Blktrace summary:
  jq . raw/summary.json | head -80
Whether amoprof_report.html and amoprof_interactive.html were generated:
Screenshots or section names that look wrong:
```

This makes it much easier to distinguish missing data from report wiring bugs.
