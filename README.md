# AMOprof

AMOprof is a profiling and report-generation package for AI inference workloads. It correlates SGLang/HiCache metrics, GPU/HBM telemetry, host DRAM bandwidth, OS memory pressure, and local storage activity into Executive, Interactive, and End Report views.

It is designed for long-context and KV-cache tiering experiments where HBM, DRAM, and local SSD/NVMe behavior must be interpreted together without mixing logical cache counters with physical block-device telemetry.

---

## What AMOprof reports

AMOprof can generate a single combined HTML report with three tabs:

| Tab | Purpose |
|---|---|
| Executive | High-level KPIs, findings, source health, and cross-layer interpretation. |
| Interactive | Plotly-based exploratory timelines and drill-down charts. |
| End Report | Static deep-dive report with formulas, sectioned analysis, PNG charts, and per-chart takeaways. |

Core analysis areas include:

- SGLang request, latency, throughput, and cache-hit metrics.
- GPU utilization, GPU power, HBM usage, HBM bandwidth, and NVLink/PCIe signals when available.
- HiCache/KV tier analysis across L1/HBM, L2/DRAM, and L3/local storage.
- L3 local storage analysis from blktrace/iostat/sysfs, including bandwidth, IOPS, queue-depth evidence, request sizes, hot/cold LBA, TRIM/discard, and per-stream attribution when collected.
- DRAM bandwidth from AMD uProf, Intel PCM, or perf IMC fallback.
- OS page activity from vmstat, swap, NUMA, and page-fault counters.
- Formula/source documentation so report KPIs can be traced back to counters.

---

## Tier terminology

| Tier | Meaning | Typical source |
|---|---|---|
| L1 | GPU HBM and hot KV cache | DCGM / nvidia-smi / SGLang |
| L2 | Host DRAM / HiCache memory tier | SGLang host-cache counters, setup details, DRAM PMU |
| L3 local storage | Node-local SSD/NVMe or local file-backed HiCache storage | blktrace, iostat, sysfs, SMART, filesystem capacity |
| Remote/shared backing tier | Remote/shared AI memory node, object store, or unmapped backing tier | Logical SGLang movement only unless explicit physical mapping exists |

Important counter rules:

- `sglang_backuped_tokens_total` is logical offload/write movement.
- `sglang_prefetched_tokens_total` is logical prefetch/onboard movement.
- `sglang_load_back_tokens_total` is an L2→L1 restore diagnostic and is not counted as local SSD read bytes.
- Physical SSD/LBA charts are populated only from local block telemetry.
- If no L3 is configured and no L3 activity exists, L3-relevant sections stay present but collapsed with a “not configured / no activity” note.

---

## Package structure

```text
amoprof_1_39_90/
├── README.md                         # Overview, features, CLI reference, examples
├── INSTALL.md                        # Installation and dependency guide
├── install.sh                        # Main installer for Python + common system dependencies
├── pyproject.toml                    # Python package metadata and amoprof console entry point
├── setup.py                          # Editable-install compatibility
├── setup_details_sample.json         # Example setup metadata for reports
├── run_amoprof_swebench_pro_sweeps.sh# Example benchmark wrapper
├── scripts/
│   └── install_dram_deps.sh          # Architecture/vendor-aware DRAM PMU dependency installer
├── tests/
│   └── test_executive_symbol_regression.py
└── amoprof/
    ├── cli.py                        # CLI parser and command dispatch
    ├── collectors.py                 # Core GPU, DRAM, power, vmstat, iostat, SMART collectors
    ├── collectors_extra.py           # blktrace, biosnoop, discard, swap-storm collectors
    ├── prometheus_source.py          # Prometheus/SGLang/DCGM/node-exporter source handling
    ├── blktrace_analyzer.py          # Block-level L3/NVMe trace analysis
    ├── comparator.py                 # Multi-run comparison support
    ├── aggregator.py                 # Multi-run aggregation support
    ├── retime.py                     # Legacy timeseries alignment helper
    ├── bench_lc_results.py           # Long-context benchmark summary renderer
    ├── report/
    │   ├── amoprof.py                # Static End Report generation
    │   ├── interactive.py            # Interactive report generation
    │   ├── combined.py               # Combined tabbed report generation
    │   ├── common_kpis.py            # Shared KPI definitions
    │   ├── l3_backend.py             # L3 backend detection/resolution
    │   └── tier_terms.py             # Tier naming/terminology helpers
    └── dashboard/                    # Optional dashboard assets
```

---

## Quick installation

```bash
unzip amoprof_1_39_90.zip
cd amoprof_1_39_90
chmod +x install.sh scripts/install_dram_deps.sh
./install.sh
source ~/amoprof_venv/bin/activate
amoprof --version
```

For full tracing and DRAM PMU support on the target server:

```bash
sudo ./install.sh --with-dram-deps --dram-tool auto
```

`install.sh` detects the OS package manager, CPU architecture, CPU vendor, and available GPU tools. It installs common packages using the relevant package names for `apt`, `dnf`, `yum`, `zypper`, or `pacman` where available. `scripts/install_dram_deps.sh` selects AMD uProf, Intel PCM, or perf IMC support based on CPU vendor and architecture.

See [INSTALL.md](INSTALL.md) for detailed setup instructions.

---

## CLI commands

AMOprof exposes one console entry point, `amoprof`, with these subcommands:

| Command | Purpose | Typical output |
|---|---|---|
| `amoprof collect` | Collect local/remote runtime telemetry while a workload runs. | `metrics_run_*` directory with `raw/*.csv`, summaries, and optional reports. |
| `amoprof analyze` | Generate reports from an existing run directory, Prometheus, or both. | Static, Interactive, and/or Combined HTML report. |
| `amoprof retime` | Re-align legacy SGLang timeseries to the run start time. | Updated `raw/sglang_timeseries.csv` or dry-run offset report. |
| `amoprof aggregate` | Merge multiple run directories into one synthetic run and optionally enrich from Prometheus. | `merged_run_*` directory and optional reports. |
| `amoprof compare` | Compare multiple runs side by side. | Single comparison HTML with delta tables/charts. |
| `amoprof bench-lc` | Render a long-context benchmark JSON into an HTML benchmark summary. | Benchmark summary HTML. |
| `amoprof --version` | Print installed package version. | Version string. |

Backward-compatible shortcut: if no subcommand is provided, AMOprof treats the invocation as `collect`. For example, `amoprof --duration-s 60 ...` is equivalent to `amoprof collect --duration-s 60 ...`.

---

## Command examples

### 1. Collect metrics from a local SGLang run

```bash
sudo amoprof collect \
  --output-dir ./amoprof_results \
  --label dgx_lc_l3_nvme \
  --duration-s 900 \
  --interval-s 1 \
  --sglang-host 127.0.0.1 \
  --sglang-port 30000 \
  --model openai/gpt-oss-120b \
  --ssd-device /dev/nvme2n1 \
  --hicache-path /mnt/sglang_hicache \
  --enable-dram \
  --dram-tool auto \
  --enable-blktrace \
  --enable-biosnoop \
  --setup-details setup_details_sample.json \
  --combined-report \
  --strict-sanity
```

Use `sudo` for blktrace, biosnoop, perf, and DRAM PMU collectors. Use `--no-sudo` only when AMOprof itself already runs as root.

### 2. Collect until SGLang becomes idle

Useful when the benchmark duration is not known in advance:

```bash
sudo amoprof collect \
  --output-dir ./amoprof_results \
  --label lc_until_idle \
  --sglang-host 127.0.0.1 \
  --sglang-port 30000 \
  --until-idle \
  --idle-grace-s 20 \
  --max-duration-s 7200 \
  --enable-dram \
  --enable-blktrace \
  --combined-report
```

### 3. Analyze a collected run

```bash
amoprof analyze \
  --run-dir ./amoprof_results/metrics_run_YYYYMMDD_HHMMSS \
  --combined-report \
  --interactive-report \
  --amoprof-report \
  --prom-rate-window 5m
```

### 4. Analyze a collected run and fill missing data from Prometheus

```bash
amoprof analyze \
  --run-dir ./amoprof_results/metrics_run_YYYYMMDD_HHMMSS \
  --prometheus http://PROM_HOST:9090 \
  --start 2026-06-17T23:15:54Z \
  --end   2026-06-17T23:25:54Z \
  --prom-step 15 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --prefer local \
  --setup-details setup_details_sample.json \
  --combined-report
```

### 5. Generate a Prometheus-only report

```bash
amoprof analyze \
  --prometheus http://PROM_HOST:9090 \
  --start 2026-06-17T23:15:54Z \
  --end   2026-06-17T23:25:54Z \
  --prom-step 15 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --nvme-device nvme2n1 \
  --output-dir ./prom_reports \
  --setup-details setup_details_sample.json \
  --prefer prometheus \
  --combined-report
```

### 6. Discover Prometheus target labels

```bash
amoprof analyze \
  --prometheus http://PROM_HOST:9090 \
  --list-targets
```

Use the listed `{job, instance}` pairs with `--prom-instance`, `--prom-job`, and `--prom-labels`.

### 7. Analyze with a benchmark summary file

```bash
amoprof analyze \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --bench-summary ./perf_metrics_summary.json \
  --combined-report \
  --interactive-report
```

### 8. Re-align a legacy SGLang timeseries

Use `retime` only for old run directories where SGLang time starts at zero or is shifted relative to GPU/host telemetry:

```bash
amoprof retime \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --sglang-offset-s 75 \
  --dry-run
```

Apply the offset after confirming the dry run:

```bash
amoprof retime \
  --run-dir ./metrics_run_YYYYMMDD_HHMMSS \
  --sglang-offset-s 75
```

### 9. Aggregate multiple runs into one report

```bash
amoprof aggregate \
  --run-dirs ./run_c1 ./run_c4 ./run_c8 \
  --start 1778871540 \
  --end 1778877078 \
  --prometheus http://PROM_HOST:9090 \
  --output-dir ./aggregated \
  --run-label concurrency_sweep \
  --setup-details setup_details_sample.json \
  --combined-report
```

### 10. Compare multiple runs side by side

Each `--run` uses `LABEL:DIR[:START[:END]]`. The first run is the baseline.

```bash
amoprof compare \
  --run "Baseline:./run_c1:1778871540:1778877078" \
  --run "4-way concurrency:./run_c4:1778881540:1778887078" \
  --run "FP8 KV:./run_fp8:1778891540:1778897078" \
  --output-dir ./comparison \
  --title "SGLang KV Cache Tuning Comparison"
```

### 11. Render a long-context benchmark summary

```bash
amoprof bench-lc \
  --input ./lc_bm_results.json \
  --output ./lc_benchmark_report.html \
  --title "Long-Context Benchmark" \
  --run-label qwen3_235b_awq
```

---

## Common collector options

| Option | Use |
|---|---|
| `--sglang-host`, `--sglang-port` | Scrape SGLang `/metrics` and server info. |
| `--ssd-device /dev/nvmeXnY` | Resolve local L3 device for physical storage analysis. |
| `--hicache-path PATH` | Resolve local file-backed HiCache/L3 location and filesystem capacity. |
| `--enable-blktrace` | Capture block I/O completions for request-size, LBA, latency, and physical R/W charts. |
| `--enable-biosnoop` | Add per-PID/per-stream block I/O attribution. |
| `--enable-dram --dram-tool auto` | Collect host DRAM bandwidth from AMD uProf, Intel PCM, or perf fallback. |
| `--enable-nsys` | Capture Nsight Systems GPU traces when the tool is installed and supported. |
| `--setup-details FILE` | Add model, TP, HBM, DRAM, L3 capacity, and launch configuration context. |
| `--bench-summary FILE` | Attach benchmark-level summary/percentile validation to reports. |
| `--strict-sanity` | Fail early on missing/invalid critical run metadata. |

---

## Common analyze/report options

| Option | Use |
|---|---|
| `--combined-report` | Generate the tabbed Executive / Interactive / End Report HTML. |
| `--interactive-report` | Generate only the interactive Plotly report. |
| `--amoprof-report` | Generate only the static End Report. |
| `--report-theme dark|light|off` | Select report styling and explanatory tooltip behavior. |
| `--prefer local|prometheus` | Pick which source wins when local CSVs and Prometheus both provide the same metric. |
| `--prom-rate-window 5m` | Set Prometheus `rate()` window for percentile timeseries. |
| `--sglang-page-size N` | Override SGLang page size/KV block size when it cannot be auto-detected. |
| `--server-info-url URL` | Fetch SGLang server metadata from an explicit endpoint. |
| `--setup-details-override` | Allow manual setup details to replace server-info-derived metadata. |

---

## Dependency overview

| Area | Tools |
|---|---|
| Python package | Python 3.10+, pip, venv, pandas, numpy, matplotlib, scipy, requests |
| GPU/HBM | nvidia-smi and optionally DCGM/dcgmi |
| SGLang metrics | SGLang Prometheus `/metrics` endpoint |
| L3 local storage | nvme-cli, sysstat/iostat, blktrace/blkparse, sysfs |
| Per-stream attribution | bpfcc-tools / biosnoop-bpfcc |
| DRAM bandwidth | AMD uProf on AMD x86_64, Intel PCM on Intel x86_64, perf IMC fallback |
| Optional tracing | bpftrace, Nsight Systems |

---

## Report consistency expectations

AMOprof is designed to keep report sections stable across runs:

- L3-active reports show populated L3 storage and KV-cache tier sections.
- L2-only reports keep L3 sections collapsed instead of removing the section layout.
- Static End Report GPU/HBM timelines use the full report-window display scale.
- KV$B Event Traces appear immediately after KV Cache Footprint & HBM Capacity Analysis.
- Logical SGLang L3 movement and physical SSD/LBA telemetry are shown separately unless a concrete local mapping exists.

---

## Troubleshooting

### `blktrace` or `biosnoop` fails

Run collection with sudo or configure passwordless sudo for the tracing binaries. These tools need root privileges on most systems.

### DRAM bandwidth is missing

Run:

```bash
sudo scripts/install_dram_deps.sh --dram-tool auto
```

Then collect with:

```bash
amoprof collect --enable-dram --dram-tool auto ...
```

### SGLang counters are missing

Confirm the metrics endpoint is reachable:

```bash
curl http://127.0.0.1:30000/metrics | grep sglang_
```

### SMART data is missing

Install `nvme-cli` and run collection with permission to query the NVMe device:

```bash
sudo nvme smart-log /dev/nvme2n1
```

---

## Development checks

```bash
python -m compileall -q amoprof
pytest -q tests/test_executive_symbol_regression.py
```
