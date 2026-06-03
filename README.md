# AMOprof v1.35 — AI Memory & I/O Profiler

AMOprof profiles every layer of an AI inference stack — from user-visible request latency down to NAND flash IOPS — on a shared timeline. It collects metrics from SGLang, GPU (DCGM / nvidia-smi), NVMe (iostat / blktrace / biosnoop), host DRAM (AMDuProf PMU), vmstat, and power monitors, then produces three correlated HTML reports that map each metric onto the **AI Stack Cake** diagram (A5 Application → A4 Runtime → A3 OS/Kernel → A2 Drivers → A1 Hardware).

---

## Table of contents

1. [What AMOprof answers](#1-what-amoprof-answers)
2. [The AI Stack Cake — layered profiling model](#2-the-ai-stack-cake)
3. [Package layout](#3-package-layout)
4. [Installation](#4-installation)
5. [Quick start](#5-quick-start)
6. [Report types](#6-report-types)
7. [CLI reference — `analyze`](#7-cli-reference--analyze)
8. [CLI reference — `collect`](#8-cli-reference--collect)
9. [CLI reference — `retime`](#9-cli-reference--retime)
10. [Output files](#10-output-files)
11. [Stop conditions for `collect` (remote benchmark support)](#11-stop-conditions-for-collect)
12. [Output directory behaviour](#12-output-directory-behaviour)
13. [Data sources and how metrics are derived](#13-data-sources-and-how-metrics-are-derived)
14. [Pre-flight checks](#14-pre-flight-checks)
15. [Setup details override](#15-setup-details-override)
16. [Known data gaps and how to fill them](#16-known-data-gaps-and-how-to-fill-them)
17. [Version history](#17-version-history)
18. [Safety and overhead notes](#18-safety-and-overhead-notes)
19. [Bug report template](#19-bug-report-template)

---

## 1. What AMOprof answers

- Is TTFT high because prefill compute is expensive, the KV cache is cold, or the server is queued?
- Is decode slow because HBM is saturated, or because KV blocks are being loaded from DRAM or NVMe?
- Are NVMe reads bursty, random, misaligned, or concentrated in a small hot LBA region?
- Is the write-back / eviction / backup path stressing SSD endurance?
- Is the SGLang cache-hit rate consistent between the benchmark output, Prometheus gauges, and report KPIs?
- Are P50/P90/P99 latency tails correlated with GPU, HBM, NVMe, or system memory behaviour?
- Which subsystem (compute, HBM, DRAM, NVMe, queue) is the binding bottleneck at the current throughput?

---

## 2. The AI Stack Cake

Every chart in AMOprof is tagged with a **layer badge** (`[A2 · L3]`) that places it on the stack. The cake has five layers and three tier columns:

```
 ┌─────────────────────────────────────────────────────────────────┐
 │ A5 · APPLICATION LAYER                                          │
 │     Tokens/s · TTFT · TPOT · P99 Request Latency · E2E         │
 ├─────────────────────────────────────────────────────────────────┤
 │ A4 · INFERENCE RUNTIME  (SGLang / vLLM / TRT-LLM)              │
 │     Prefill · Decode · KV$ eviction · KV$ swap · Cache hit      │
 ├──────────────────┬──────────────────┬────────────────────────────┤
 │ A3 CUDA / Kernel │ A3 OS / Memory   │ A3 OS / Block Layer        │
 │ SM occupancy     │ Page fault rate  │ blktrace · biolatency      │
 ├──────────────────┼──────────────────┼────────────────────────────┤
 │ A2 GPU Driver    │ A2 CPU Driver    │ A2 io_uring / NVMe Driver  │
 │ dcgmi · CUDA     │ perf sched · IRQ │ SQ/CQ · IOPS vs QD        │
 ├──────────────────┼──────────────────┼────────────────────────────┤
 │ A1 L1 HBM HW     │ A1 L2 DRAM HW    │ A1 L3 SSD HW (NAND)       │
 │ ~3.35 TB/s       │ ~300 GB/s DDR5   │ Seq BW · P99 · WAF        │
 └──────────────────┴──────────────────┴────────────────────────────┘
   L1 = HBM (GPU)     L2 = Host DRAM     L3 = NVMe SSD
```

Charts in each report are ordered top-down (A5 → A4 → A3 → A2 → A1) with labelled layer banners between groups.

---

## 3. Package layout

```text
amoprof/
├── cli.py                    # collect / analyze / retime subcommands
├── collectors.py             # live collectors: GPU, iostat, vmstat, power, …
├── collectors_extra.py       # blktrace, biosnoop, discard, swap-storm monitors
├── prometheus_source.py      # Prometheus range query + histogram_quantile()
├── percentiles.py            # P50/P90/P99 derivation from histogram buckets
├── blktrace_analyzer.py      # large-trace streaming parser (§C/§D/§E/§G)
├── bench_summary.py          # bench_serving output parser
├── preflight.py              # per-tool smoke tests before long captures
├── retime.py                 # time-axis repair for legacy run dirs
├── analysis.py               # cross-collector bottleneck scoring
├── writer.py                 # CSV/JSON output helpers
├── plan.py                   # execution plan builder
├── models.py                 # KV-cache architecture DB (n_layers, n_heads, …)
├── runner.py                 # parallel collector orchestration
├── report/
│   ├── amoprof.py            # static HTML report (matplotlib PNGs, ~5 MB)
│   ├── interactive.py        # Plotly interactive report (~300 KB)
│   ├── combined.py           # tabbed merger: static + interactive → one file
│   ├── enhancer.py           # post-processor: dark theme, tooltips, layer badges
│   └── ai_metrics_dict.py    # metric glossary
├── dashboard/
│   └── concurrency_sweep.*   # concurrency-sweep dashboard assets
├── pyproject.toml
├── setup.py
└── README.md
```

---

## 4. Installation

### 4.1 Python environment

```bash
python3 -m venv ~/amoprof-venv
source ~/amoprof-venv/bin/activate
pip install --upgrade pip
pip install -e .
# Additional report dependencies if not pulled in automatically:
pip install pandas numpy matplotlib plotly requests python-dateutil
```

### 4.2 System packages

Only install the tools you plan to use — missing tools are skipped and their report panels show a placeholder.

**Ubuntu / Debian:**
```bash
sudo apt-get install -y \
  sysstat blktrace bpfcc-tools linux-tools-common linux-tools-generic \
  nvme-cli jq curl tar gzip zstd
```

**RHEL / CentOS / Fedora:**
```bash
sudo dnf install -y sysstat blktrace bcc-tools kernel-tools nvme-cli jq curl tar gzip zstd
```

### 4.3 Optional tools by layer

| Tool | Layer | What it adds | Install |
|---|---|---|---|
| `nvidia-smi` / DCGM | A2 → A1 | GPU util, HBM used, power, temperature | NVIDIA driver / datacenter-gpu-manager |
| `dcgmi dmon` | A2 | Continuous HBM-Active %, Tensor active | datacenter-gpu-manager |
| `iostat` (sysstat) | A2 | NVMe IOPS, BW, queue depth, latency | `apt install sysstat` |
| `blktrace` + `blkparse` | A2 | Per-request block events (§C/§D/§E) | `apt install blktrace` |
| `biosnoop-bpfcc` | A2/A3 | Per-PID I/O attribution | `apt install bpfcc-tools` |
| `AMDuProfPcm` | A1 | Host DRAM bandwidth (AMD Data Fabric PMU) | AMD uProf installer |
| `nvme-cli` | A1 | SMART log: WAF, temperature, lifetime | `apt install nvme-cli` |
| Prometheus + node_exporter | all | Remote metric pull, histogram_quantile | prometheus.io |
| `nsys` | A2/A3 | CUDA kernel trace | NVIDIA Nsight Systems |

---

## 5. Quick start

### 5.1 Analyze a previous run — combined single-file report

The most common flow: re-analyze a local run directory, pulling SGLang/GPU metrics from Prometheus, and produce one self-contained HTML file with both reports in two tabs.

```bash
amoprof analyze \
  --run-dir /path/to/metrics_run_20260515_115803 \
  --prometheus http://PROMETHEUS_HOST:9090 \
  --prom-step 30 \
  --start 1778871540 \
  --end   1778877078 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --output-dir ./results \
  --sglang-page-size 1 \
  --setup-details ./setup_details.json \
  --combined-report
```

Outputs in `./results/`:
```
amoprof_report.html        # static report  (~5 MB, matplotlib PNGs)
amoprof_interactive.html   # interactive    (~300 KB, Plotly)
amoprof_combined.html      # ★ tabbed merger of both  (~5.3 MB)
```

Open `amoprof_combined.html` in any modern browser. The **⚡ Interactive** tab loads by default; click **📊 Static** to switch. Use `Alt+1` / `Alt+2` as keyboard shortcuts. The last-used tab is remembered across page opens.

### 5.2 Live collection with combined report

```bash
sudo amoprof collect \
  --sglang-port 30000 \
  --ssd-device /dev/nvme0n1 \
  --enable-all \
  --sglang-page-size 1 \
  --combined-report \
  --output-dir ./results
```

### 5.3 Prometheus-only (no local run dir)

```bash
amoprof analyze \
  --prometheus http://PROMETHEUS_HOST:9090 \
  --start "2026-05-15T18:59:00Z" \
  --end   "2026-05-15T20:31:18Z" \
  --prom-step 30 \
  --prom-instance msl-ssg-dgx1.msl.lab:30000 \
  --output-dir ./results \
  --combined-report
```

---

## 6. Report types

AMOprof produces three report files from a single analysis run:

### 6.1 Static report — `amoprof_report.html`

Generated by `amoprof/report/amoprof.py` using matplotlib. Self-contained — all chart PNGs are embedded as base64. Size ~5 MB.

Features:
- Full bottleneck scoring table with per-layer scores (0–100), severity badges, and source attribution
- KPI cards at the top: TTFT, TPOT, E2E, Throughput, Cache Hit %, HBM fill %, GPU util, power, NVMe R/W
- 25+ chart sections ordered A5 → A4 → A3 → A2 → A1 with layer banners
- Per-chart **layer badge** (`[A2 · L3]`) and **"📖 What this chart shows"** explanation
- Metric Derivations & Formulas table with exact formulas, source paths, and notes
- Auto-generated Optimisation Recommendations ranked by impact and effort
- Dark theme with hover tooltips showing per-chart stats (applied by `enhancer.py`)

### 6.2 Interactive report — `amoprof_interactive.html`

Generated by `amoprof/report/interactive.py` using Plotly (CDN-loaded). Size ~300 KB.

Features:
- Hover for exact values, drag to zoom, click legend to isolate traces
- Sections in same A5 → A4 → A3 → A2 → A1 order as static report
- Layer banners with KPI lists and tool references
- All NVMe rate columns derived correctly from cumulative Prometheus counters (IOPS, BW, latency, utilisation)
- SGLang, GPU, swap, DRAM, and NVMe charts all populated from the same `raw/` CSV files as the static report

### 6.3 Combined report — `amoprof_combined.html`

Generated by `amoprof/report/combined.py`. Merges both reports into a single file with two tabs.

```
┌─────────────────────────────────────────────────────────────┐
│ 📊 AMOprof  │ ⚡ Interactive  [PLOTLY] │ 📊 Static  [PNG]  │
└─────────────────────────────────────────────────────────────┘
```

- **⚡ Interactive** tab active by default
- Sticky tab bar at the top — never scrolls away
- CSS is scoped per-pane to prevent style conflicts
- Plotly CDN script de-duplicated (one tag regardless of how many times it appears)
- Plotly charts re-layout on tab switch (correct width after being hidden)
- URL hash (`#interactive` or `#static`) preserved — shareable links land on the right tab
- Last-used tab remembered in `localStorage`
- `Alt+1` / `Alt+2` keyboard shortcuts

**Produce `--combined-report` instead of `--amoprof-report --interactive-report`** — it implies both and runs all three in one pass.

---

## 7. CLI reference — `analyze`

### Core flags

| Flag | Default | Description |
|---|---|---|
| `--run-dir PATH` | — | Source run directory containing `raw/` |
| `--prometheus URL` | — | Prometheus server to pull SGLang/DCGM/node_exporter metrics from |
| `--prom-instance HOST:PORT` | — | `instance` label to filter (e.g. `dgx1.lab:30000`) |
| `--start TIME` | — | Window start: Unix timestamp, ISO-8601, or `=-1h` (relative) |
| `--end TIME` | — | Window end: Unix timestamp, ISO-8601, or `=now` |
| `--prom-step SECS` | 30 | Prometheus query resolution in seconds |
| `--output-dir DIR` | `""` (run-dir) | Where report files are written. When `--run-dir` is also given, raw data stays in the run-dir but all HTML output goes here. |
| `--prefer local\|prometheus` | `local` | Merge policy when both local files and Prometheus have data for the same metric |

### Report flags

| Flag | Description |
|---|---|
| `--amoprof-report` | Generate `amoprof_report.html` (static, matplotlib) |
| `--interactive-report` | Generate `amoprof_interactive.html` (Plotly) |
| `--combined-report` | **★ Recommended.** Generate `amoprof_combined.html` (tabbed). Implies both above. |
| `--report-theme dark\|light\|off` | Theme applied to the static report. `dark` = slate-900 background (default). `off` skips post-processing. |

### Tuning flags

| Flag | Default | Description |
|---|---|---|
| `--sglang-page-size N` | 0 (auto) | SGLang KV block size in tokens. Used to estimate per-IO byte sizes when byte counters are unavailable. |
| `--bench-summary FILE` | — | Path to `bench_serving.py` output for the A5 bench-summary charts |
| `--setup-details FILE` | — | JSON file with server/model configuration (see §15) |
| `--verbose` | — | Extra diagnostic logging |

### Time syntax

All of `--start` / `--end` accept:
- Unix epoch seconds: `1778871540`
- ISO 8601 UTC: `"2026-05-15T18:59:00Z"`
- Relative (use `=` prefix): `=-1h`, `=-30m`, `=-2d`, `=now`

The `=` prefix is required for relative offsets so argparse does not misparse leading `-` as a flag.

---

## 8. CLI reference — `collect`

Live collection from a running SGLang server plus local system tools.

```bash
sudo amoprof collect \
  --sglang-port 30000 \
  --ssd-device /dev/nvme0n1 \
  --sglang-page-size 1 \
  --enable-all \
  --combined-report \
  --output-dir ./results
```

### Duration / stop flags

By default, collection runs for 300 seconds. Use stop conditions to tie collection lifetime to the benchmark without specifying `--duration-s` explicitly — especially useful when the benchmark starts from a **remote node**.

| Flag | Default | Description |
|---|---|---|
| `--duration-s SECS` | None (300 if no stop condition) | Fixed collection duration |
| `--max-duration-s SECS` | 7200 | Hard ceiling when a stop condition is used. Prevents runaway collection if the benchmark hangs. |
| `--until-idle` | off | Stop when SGLang `num_running_reqs == 0` and `num_queue_reqs == 0` for `--idle-grace-s` consecutive seconds. Zero coordination with the remote node needed — AMOprof watches the `/metrics` endpoint it already polls. |
| `--idle-grace-s SECS` | 15 | Grace period for `--until-idle`. Protects against momentary queue drains between request batches. |
| `--stop-file PATH` | — | Stop when this file appears on disk. The benchmark node creates it (e.g. via NFS mount or `ssh dgx1 "touch /tmp/bench_done"`). |
| `--stop-url URL` | — | Stop when this URL returns HTTP 200. The benchmark node exposes a minimal HTTP server that flips to 200 when the run completes. |
| `--stop-poll-s SECS` | 5 | Polling interval for `--stop-file` and `--stop-url` checks. |

**Example — stop when benchmark finishes on remote node:**

```bash
# On the DGX (collection node):
sudo amoprof collect \
  --sglang-port 30000 --ssd-device /dev/nvme0n1 \
  --until-idle --idle-grace-s 20 \
  --max-duration-s 7200 \
  --combined-report --output-dir ./results

# On the remote benchmark node (no coordination needed):
python3 -m sglang.bench_serving --host dgx1 --port 30000 \
  --dataset-name sharegpt --num-prompts 1000
# AMOprof detects drain automatically when the queue empties.
```

**Or with a sentinel file (more explicit):**
```bash
# Benchmark node:
run_my_benchmark ...
ssh dgx1 "touch /tmp/bench_done.sentinel"  # signal AMOprof to stop

# DGX:
sudo amoprof collect ... --stop-file /tmp/bench_done.sentinel
```

### Other `collect` flags

| Flag | Default | Description |
|---|---|---|
| `--sglang-port PORT` | 30000 | SGLang HTTP metrics port |
| `--sglang-host HOST` | localhost | SGLang server hostname |
| `--ssd-device DEV` | /dev/nvme0n1 | Block device for NVMe collectors |
| `--interval-s SECS` | 1.0 | Polling interval for time-series collectors |
| `--enable-all` | off | Enable every optional collector |
| `--enable-blktrace` | off | Enable blktrace (requires root) |
| `--enable-biosnoop` | off | Enable biosnoop eBPF (requires BCC + root) |
| `--enable-amduprof-pcm` | off | Enable AMD uProf DRAM BW collector |
| `--combined-report` | off | ★ Generate combined tabbed report (implies `--amoprof-report` + `--interactive-report`) |
| `--amoprof-report` | off | Generate static report only |
| `--interactive-report` | off | Generate interactive report only |
| `--report-theme` | dark | Theme for the static report (`dark`/`light`/`off`) |
| `--setup-details FILE` | — | Server config JSON (see §15) |
| `--bench-summary FILE` | — | bench_serving output file |
| `--output-dir DIR` | `./amoprof_results` | Parent directory; a `metrics_run_<ts>/` subdir is created inside it |

---

## 9. CLI reference — `retime`

Repair the SGLang time-axis offset that appears in run dirs created before v1.12. The bug anchored `sglang_timeseries.csv` to SGLang's first scrape instead of the run-wide t0, shifting the SGLang chart 5–15 s relative to all other charts.

```bash
amoprof retime --run-dir ./metrics_run_20260515_115803           # auto-detect
amoprof retime --run-dir ./metrics_run_20260515_115803 --sglang-offset-s 12  # manual
amoprof retime --run-dir ./metrics_run_20260515_115803 --dry-run  # preview only
```

The original CSV is backed up to `sglang_timeseries.csv.preretime` before modification. v1.12+ runs are unaffected.

---

## 10. Output files

```
./results/
├── amoprof_combined.html          # ★ tabbed report (both in one file)
├── amoprof_report.html            # static report  (if --amoprof-report)
├── amoprof_interactive.html       # interactive    (if --interactive-report)
└── metrics_run_<ts>/              # (for collect) or the original --run-dir
    ├── summary.json               # run metadata + KPI summary
    └── raw/
        ├── sglang_timeseries.csv           # SGLang /metrics 1-sec scrape
        ├── sglang_summary.json             # SGLang aggregates + percentiles
        ├── sglang_percentiles_timeseries.json  # P50/P90/P99 over time
        ├── gpu_timeseries.csv              # per-GPU per-tick (DCGM/nvidia-smi)
        ├── gpu_summary.json
        ├── nvme_driver_timeseries.csv      # iostat / Prometheus node_disk_*
        ├── vmstat_timeseries.csv           # /proc/vmstat per-tick
        ├── power_timeseries.csv
        ├── amduprof_pcm_raw.csv            # AMD DRAM PMU (if collected)
        ├── biosnoop.csv                    # per-IO with PID (if blktrace on)
        ├── blkparse_events.generated.csv
        ├── request_size_distribution.csv   # §C/§D size histograms
        ├── interarrival_distribution.csv   # §C/§D IAT histograms
        ├── temporal_read_write_trim_pattern.csv
        ├── bandwidth_per_stream.csv        # per-(pid,comm) BW
        ├── hot_regions_overall.csv         # LBA hot/cold map
        ├── smart_summary.json             # nvme-cli SMART
        └── setup_details.json             # server config (if supplied)
```

When `--output-dir` is specified together with `--run-dir`, all three HTML files go to `--output-dir` while the `raw/` data stays in the original run-dir.

---

## 11. Stop conditions for `collect`

When the benchmark runs on a **different machine** from the collection node you cannot use a local process sentinel. AMOprof provides three strategies:

### `--until-idle` (recommended — zero coordination)

AMOprof already polls SGLang's `/metrics` endpoint every second. When `num_running_reqs == 0` and `num_queue_reqs == 0` for `--idle-grace-s` consecutive seconds (default 15), the benchmark has drained and collection stops. No changes to the benchmark script needed.

Limitation: if SGLang stays up serving other traffic after the benchmark ends, the queue never fully drains and this signal never fires. Use `--stop-file` or `--stop-url` in that case.

### `--stop-file PATH` (simplest for shared filesystems)

AMOprof polls for a file. The benchmark node creates it when done.

```bash
# Benchmark node (add to end of benchmark script):
ssh collection-node "touch /tmp/bench_done.sentinel"
# OR via shared NFS:
touch /mnt/nfs/shared/bench_done.sentinel

# Collection node:
amoprof collect ... --stop-file /tmp/bench_done.sentinel
```

### `--stop-url URL` (no shared filesystem needed)

AMOprof polls an HTTP endpoint every `--stop-poll-s` seconds. HTTP 200 = done; anything else = still running.

```bash
# Benchmark node (add to end of benchmark script):
python3 -c "
import http.server, socketserver
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
with socketserver.TCPServer(('', 9999), H) as s:
    s.handle_request()
" &

# Collection node:
amoprof collect ... --stop-url http://bench-node:9999/done
```

### Combining strategies

Strategies can be combined — first to fire wins:
```bash
amoprof collect \
  --until-idle --idle-grace-s 30 \
  --stop-file /tmp/bench_done \
  --max-duration-s 7200
```

---

## 12. Output directory behaviour

| Flags passed | Raw data goes to | HTML reports go to |
|---|---|---|
| `--run-dir` only | (existing run-dir) | same run-dir |
| `--run-dir` + `--output-dir` | (existing run-dir, unchanged) | `--output-dir` ★ |
| `--output-dir` only (Prometheus mode) | `--output-dir/prom_run_<ts>/` | same new dir |
| neither | `./prom_run_<ts>/` | same new dir |
| `collect --output-dir` | `--output-dir/metrics_run_<ts>/` | same new dir |

★ This is the typical pattern for re-analyzing an existing run into a clean results directory.

---

## 13. Data sources and how metrics are derived

### Cache hit rate — four methods

AMOprof computes cache hit rate four ways and shows all of them in the "Cache Hit Methodology" chart:

| Method | Formula | Notes |
|---|---|---|
| **Token-weighted** | `Δcached_tokens / (Δcached + Δcompute) × 100` | Matches `bench_serving.py` output exactly |
| **Gauge active avg** | Mean of non-zero `sglang_cache_hit_rate` samples | Filters idle ticks |
| **Gauge timeline avg** | Mean over all samples including idle | Almost always misleadingly low |
| **Gauge peak** | Max instantaneous gauge value | Upper bound |

The report KPI card uses **token-weighted** (most accurate). The tooltip uses `gen_tp_peak` as the throughput fallback when the rolling gauge has decayed to zero after the benchmark ends.

### NVMe write BW in the bottleneck table

Priority order for the write BW used in the bottleneck scoring:

1. **blktrace §D scalar** (`ssd_wr_bw_mbs_mean`) — most accurate, requires `--enable-blktrace`
2. **node_exporter byte counters** — `Δnode_disk_written_bytes_total / Δtime / 2²⁰` — accurate from Prometheus; requires the byte counter columns to exist in `nvme_driver_timeseries.csv`
3. **IOPS × block size estimate** — least accurate, used only as last resort

### NVMe rate columns in the interactive report

The interactive report reads `nvme_driver_timeseries.csv` directly. The Prometheus loader writes cumulative counters (`rd_ios`, `wr_ios`, `rd_bytes`, `wr_bytes`, `rd_ms`, `wr_ms`, `io_ms`) — not rates. The `_derive_nvme_columns()` function in `interactive.py` diffs these to produce `rd_iops`, `wr_iops`, `rd_bw_mbs`, `wr_bw_mbs`, `rd_lat_ms`, `wr_lat_ms`, `io_util_pct` before passing to the chart functions. This matches the derivation done by the static report inside `extract_metrics()`.

### DRAM BW — file extension fallback

The DRAM BW chart looks for `amduprof_pcm_raw.txt` first, then `amduprof_pcm_raw.csv`. Both extensions are accepted from any AMDuProf version. The header detection accepts both `"Total Mem RdBw"` (CSV) and `"RdBw"` (txt) column variants.

### HBM pie chart clamping

`hbm_util_pct` is clamped to `[0, 100]` at both the `extract_metrics()` assignment and inside `chart_memory()` before being passed to `ax.pie()`. This prevents the `ValueError: Wedge sizes 'x' must be non negative values` crash that occurred when DCGM reported `-1` sentinel values or when `mem_total` was briefly 0 at startup.

---

## 14. Pre-flight checks

`collect` runs real smoke tests on every enabled collector for 1–3 seconds before the long capture begins:

| Tool | Test |
|---|---|
| `blktrace` | 1-sec real capture, verify trace binaries written |
| `biosnoop` | Spawn and wait ≤8 s for header (BCC needs first-run compile) |
| `AMDuProfPcm` | 3-sec capture, verify `Total Mem Bw + Total Mem RdBw` in output |
| `nvidia-smi` | Query GPUs, confirm ≥1 visible |
| `dcgmi` | `dcgmi discovery -l` confirms daemon (optional) |
| SGLang `/metrics` | HTTP GET, verify `sglang_*` metrics in response body |

Required-baseline failures (no GPU, SGLang unreachable, SSD missing) abort with exit 4. Optional-collector failures disable that collector and proceed. Pass `--strict-sanity` to abort on optional failures too. Pass `--skip-sanity-check` to bypass entirely (not recommended).

---

## 15. Setup details override

Both reports include a **Setup / Server Configuration** panel. AMOprof fills it from:

1. `sglang_summary.json` fields (model, TP size, dtype, page size, …)
2. Prometheus label columns from SGLang time-series
3. Optional manual override via `--setup-details <file>`
4. Built-in SGLang DeepSeek-R1-70B HiCache reference profile for any fields still missing

Pass `--setup-details` to override or supplement auto-detected values:

```bash
amoprof analyze --run-dir ./metrics_run_xxx --setup-details ./setup_details.json --combined-report
```

Example `setup_details.json`:
```json
{
  "Model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
  "Runtime": "SGLang 0.5.2",
  "Instance": "msl-ssg-dgx1.msl.lab:30000",
  "GPU": "8x A100 40GB",
  "TP size": "8",
  "dtype": "bfloat16",
  "KV dtype": "fp8_e4m3",
  "Context length": "131072",
  "Page size": "1",
  "HiCache": "enabled; L2 DRAM + L3 NVMe",
  "Attention backend": "triton",
  "Schedule policy": "lpm"
}
```

The file is copied to `raw/setup_details.json` and kept in the run directory. Manual keys override matching auto-detected fields.

> **Note on defaulted values:** fields filled from the built-in reference profile are assumptions, not observed values. They are labelled "Default profile" in the report. Always supply `--setup-details` for the most accurate Setup panel.

---

## 16. Known data gaps and how to fill them

| Symptom in report | Likely cause | Fix |
|---|---|---|
| SMART shows `?`, WAF=1.0 | nvme-cli SMART collection failed | Run `nvme smart-log /dev/nvme0 -o json` as root; check `nvme id-ctrl` |
| TRIM events = 0 | Filesystem not issuing TRIM | Mount hicache with `-o discard`, or schedule `fstrim` hourly |
| §C/§D deep-profiling panels (alignment, IAT histogram) empty | blktrace not enabled | Re-collect with `--enable-blktrace` |
| Bench Summary (4 charts) empty | No bench output file | Pass `--bench-summary bench_output.txt` |
| Interactive DRAM BW empty | File extension mismatch | Fixed in v1.35.5 — tries both `.txt` and `.csv` automatically |
| Interactive NVMe charts all-zero | Missing derived rate columns | Fixed in v1.35.5 — `_derive_nvme_columns()` runs on load |
| `gen_throughput 0.0 tok/s` in tooltip | Gauge decayed post-benchmark | Fixed in v1.35.3 — falls back to `gen_tp_peak` |
| Bottleneck table: `Write 0 MB/s` | BW source fallback not wired | Fixed in v1.35.3 — falls back to node_exporter BW |
| `ValueError: Wedge sizes 'x' must be non negative values` | DCGM sentinel or startup glitch | Fixed in v1.35.1 — HBM pct clamped to [0,100] |
| `ModuleNotFoundError: No module named 'amoprof.collectors'` | Patch-only zip dropped into empty dir | Use the `_COMPLETE.zip` which includes all modules |

---

## 17. Version history

### v1.35 (current)

**v1.35.8**
- Fixed `--combined-report` not generating the tabbed report from `amoprof collect` (the flag was only wired into `analyze`; the `collect` code path used a separate, older report-generation block that was never updated).
- Restored `--report-theme` argument that was accidentally dropped from the `collect` parser.
- Both `collect` and `analyze` now use identical report-generation logic.

**v1.35.7**
- Fixed `name '_chart_sglang_throughput' is not defined` in the interactive report — the function was accidentally deleted when `_derive_nvme_columns` was inserted in v1.35.5.
- Fixed unreadable text in the Metric Derivations & Formulas table in dark theme: `td` text colors `#64748b`, `#475569`, and `#334155` were not covered by the dark-theme CSS override selectors; added them. Fixed `<code>` blocks in the formula column (dark navy `#1e3a5f`) to render as light blue in dark mode.

**v1.35.6**
- Added `amoprof/report/combined.py` — merges the static and interactive reports into a single `amoprof_combined.html` with two tabs (⚡ Interactive | 📊 Static).
- New `--combined-report` flag in both `collect` and `analyze` — implies `--amoprof-report` + `--interactive-report` and runs all three in one pass.
- Tab bar: sticky top, Alt+1/Alt+2 shortcuts, URL hash persistence, localStorage tab memory.
- CSS scoping prevents `.card`, `.kpi-tile`, `h2` etc. from conflicting across panes.
- Plotly CDN `<script>` tag de-duplicated.
- Plotly charts re-layout on tab switch (fix for zero-width charts hidden by `display:none`).

**v1.35.5**
- Fixed interactive report NVMe charts (IOPS, BW, latency) showing all-zero when run is from Prometheus: added `_derive_nvme_columns()` which diffs the raw cumulative counters (`rd_ios`, `wr_ios`, `rd_bytes`, `wr_bytes`, `rd_ms`, `io_ms`) to produce rate columns matching what the static report derives inside `extract_metrics()`.
- Fixed interactive System DRAM Bandwidth chart empty: builder now tries both `amduprof_pcm_raw.txt` and `amduprof_pcm_raw.csv`.
- Fixed interactive Swap Storm chart missing when swap was zero: chart now renders with a green confirmation annotation instead of being hidden.

**v1.35.4**
- Fixed `--output-dir` ignored when `--run-dir` is also specified in `analyze`. Reports now go to `--output-dir`; raw data stays in `--run-dir`.
- Updated `--output-dir` help text to document all four directory-routing modes.

**v1.35.3**
- Fixed `Write 0 MB/s` in bottleneck table when blktrace not enabled: `wr_bw_for_score` now falls back to `nvme_wr_bw_mbs_mean` (node_exporter) when the blktrace scalar is zero.
- Fixed bottleneck NVMe score of 22/100 despite 83% utilisation: `peak_nvme_iops` now takes the max across all four IOPS sources (timeseries read max, timeseries write max, sysfs read, sysfs write); IOPS denominator changed from `/10` to `/150` for proportional scoring.
- Fixed `Throughput 0.0 tok/s` in SGLang chart hover tooltip: falls back to `gen_tp_peak` when `ai_op_decode_tok_s` is zero post-benchmark.
- Added adaptive BW display format: sub-10 MB/s values show one decimal place (`0.5 MB/s` instead of `0 MB/s`).
- Added `re_enhance_report()` function in `enhancer.py` to strip old explanation blocks and re-inject fresh ones after a package upgrade.

**v1.35.2**
- Fixed Prometheus path: `rd_bytes` / `wr_bytes` from `node_disk_read/written_bytes_total` were fetched but never written into the `nvme_rows` dict, so `wr_bw_mbs` could not be derived from them. Now both byte-counter columns are included in every Prometheus-sourced `nvme_driver_timeseries.csv` row.
- Added byte-counter differencing step in `extract_metrics()` BW derivation (runs before the IOPS × block-size fallback).

**v1.35.1**
- Fixed `ValueError: Wedge sizes 'x' must be non negative values` in `chart_memory()`. `hbm_util_pct` clamped at `extract_metrics()` assignment and again inside the chart function with explicit NaN check.

**v1.35.0**
- Complete package (all 26 modules) replacing previous patch-only zips.
- Comprehensive CHART_EXPLANATIONS rewrite (29 entries) with run-specific data, 5-part structure, and "For KV$" tier analysis.
- Layer reordering and banners in static report (A5 → A4 → A3 → A2 → A1).
- Three consistency bugs fixed (NVMe write BW, throughput tooltip, bottleneck score).

### v1.34 and earlier

See the legacy notes in the package for v1.28 (layer reordering), v1.29 (`--setup-details`), v1.30 (default profile), v1.33 (dark theme), and v1.34 (contrast fixes).

---

## 18. Safety and overhead notes

- `blktrace` creates large binary files quickly on busy NVMe devices. Monitor disk space; use `--max-duration-s` as a ceiling.
- `biosnoop` and BCC tools require kernel headers and root. On production kernels without debug symbols, the BCC compile step can take 20–30 seconds (pre-flight detects this).
- `AMDuProfPcm` requires MSR device access (`sudo modprobe msr`).
- For production systems, **Prometheus-only analysis** (`amoprof analyze --prometheus ...`) is safest because it attaches no local tracers to the host at analysis time.
- The combined report is ~5.3 MB and self-contained. All chart PNGs are base64-embedded; no network access needed after initial load (Plotly is CDN-loaded for the interactive tab).

---

## 19. Bug report template

```text
AMOprof version:      (amoprof --version)
Command used:         (full command line)
Run directory:        (path to metrics_run_xxx/)
Prometheus URL/instance/start/end/step:
Relevant log excerpt: (lines with WARNING or ERROR)

Files under raw/:
  ls -lh /path/to/raw/

Cache hit summary:
  grep -i cache_hit raw/sglang_summary.json

Bottleneck table NVMe row from report:
  (the "Write X MB/s, Read Y MB/s" line)

Reports generated (yes/no):
  amoprof_report.html:
  amoprof_interactive.html:
  amoprof_combined.html:

Symptom:
  (which section, which chart, what looks wrong)
```

## Combined Report Executive Summary Tab

When `--combined-report` is used, AMOprof now generates `amoprof_combined.html` with three tabs:

1. **Executive** — default landing tab with quick findings, setup snapshot, data-source health, top KPIs, and layer-by-layer stack status.
2. **Interactive** — Plotly time-series charts with hover values.
3. **Static** — full static PNG report, formulas, bottleneck tables, and detailed explanations.

Keyboard shortcuts:

```text
Alt+1  Executive
Alt+2  Interactive
Alt+3  Static
```

The Executive tab is generated from the run `raw/` directory and uses the same `setup_details.json`, `sglang_summary.json`, GPU/NVMe/DRAM summaries, and compact blktrace analysis files used elsewhere in the report. It does not require loading the large raw blktrace event CSV.
