AMOprof v1.95.0

# AMOprof

Version: v1.88.0 v1.35 — AI Memory & I/O Profiler

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
 │ A1 L1 HBM HW     │ A1 L2 DRAM HW    │ A1 local Storage / AI memory node HW (NAND)       │
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
  "HiCache": "enabled; L2 DRAM + L3",
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


## Benchmark summary alignment

For Prometheus-only analysis, pass the SGLang `bench_serving` summary with `--bench-summary ./bench_summary.json` or `.txt`. When present, AMOprof uses benchmark `cache_hit_rate` as the main cache-hit KPI, fills the P50/P90/P99 summary from benchmark latency/token percentiles, and uses benchmark output/request throughput when `sglang_gen_throughput` is missing or zero. Prometheus `sglang_cache_hit_rate` gauge active/timeline/peak values are still displayed separately in the Cache Hit Methodology section.

SGLang 0.5.x exposes metrics with underscore names such as `sglang_cache_hit_rate` and `sglang_realtime_tokens_total`; the report code matches underscore names and legacy colon-style labels where present.

### v1.53 local Storage / AI memory node activity semantics

For Prometheus-only reports, local Storage / AI memory node activity is now derived from SGLang hierarchical-cache counters when blktrace is absent. Any non-zero delta in `backuped_tokens_total`, `load_back_tokens_total`, `prefetched_tokens_total`, or `evicted_tokens_total` is treated as evidence of L3/cache-tier activity. Directional read/write byte estimates are only computed where the counter direction is clear: `backuped_tokens_total` contributes to estimated local Storage / AI memory node writes, while `load_back_tokens_total` and `prefetched_tokens_total` contribute to estimated local Storage / AI memory node reads. `evicted_tokens_total` is reported as cache-tier pressure/activity but is not converted to disk bytes by itself. If neither blktrace nor these SGLang counters are present, local Storage / AI memory node activity is reported as unavailable/none instead of inferred.

### Formula and metric-name convention

Reports now display formulas using the SGLang 0.5.10 Prometheus metric names exported with underscores, for example `sglang_gen_throughput`, `sglang_cache_hit_rate`, `sglang_realtime_tokens_total`, `sglang_cached_tokens_total`, `sglang_backuped_tokens_total`, `sglang_evicted_tokens_total`, and `sglang_load_back_tokens_total`. Older colon-style aliases may still be normalized internally when reading legacy CSVs, but user-facing formulas in Executive, Interactive, and End Report tabs use the underscore metric names consistently.

Primary Prometheus-only cache-hit KPI:

```text
effective_cache_hit_pct =
  (Δsglang_cached_tokens_total + Δsglang_realtime_tokens_total{mode="prefill_cache"})
  /
  (Δsglang_cached_tokens_total + Δsglang_realtime_tokens_total{mode="prefill_cache"} + Δsglang_realtime_tokens_total{mode="prefill_compute"})
  × 100
```

local Storage / AI memory node activity is inferred from SGLang hierarchical-cache counters when blktrace is unavailable: `sglang_backuped_tokens_total`, `sglang_load_back_tokens_total`, `sglang_prefetched_tokens_total`, and `sglang_evicted_tokens_total`.


## v1.67 Version metadata bump

- Bumped package metadata to `1.67.0` so `amoprof --version`, the generated combined-report tab bar, and pip/package metadata are consistent.
- Includes all prior fixes through the local Storage / AI memory node busy consistency update.

## v1.55 Storage I/O / OS Page Activity semantics

The **Storage I/O & OS Page Activity** section now treats block-device counters as host OS block I/O by default. A small amount of write IOPS from `nvme_driver_timeseries.csv`, node-exporter, or `/sys/block/*/stat` is not automatically interpreted as local Storage / AI memory node cache traffic. The report only labels it as local Storage / AI memory node I/O when `setup_details.json` explicitly maps the collected block device to the local Storage / AI memory node backend, for example with `L3 Device`, `local Storage / AI memory node Type`, `HiCache storage backend`, or `HiCache storage path`.

The section now includes a formula subsection documenting the exact parameters used:

```text
Read IOPS            = rate(read_ios_total)
Write IOPS           = rate(write_ios_total)
Discard / TRIM IOPS  = rate(discard_ios_total)
Read bandwidth       = rate(read_bytes_total) / 1024^2
Write bandwidth      = rate(write_bytes_total) / 1024^2
Device busy          = rate(io_ms_total) / 1000 * 100
Page faults/sec      = rate(vmstat_pgfault)
Major faults/sec     = rate(vmstat_pgmajfault)
Swap-in pages/sec    = rate(vmstat_pswpin)
Swap-out pages/sec   = rate(vmstat_pswpout)
```

This avoids misleading reports such as “NVMe I/O write activity” when no NVMe-backed local Storage / AI memory node tier was configured.

## v1.56 metric methodology updates

- Prometheus-only reports use Prometheus/SGLang metrics as the source of truth; benchmark summaries are validation references only.
- The primary cache-hit KPI is the active-window average of `sglang_cache_hit_rate` (`value > 0`). Counter-based token ratios are shown as diagnostics because they can diverge from benchmark cache-hit semantics.
- Mean TTFT, ITL/TPOT, and E2E latency are derived from `_sum/_count` counter deltas:
  - `Δsglang_time_to_first_token_seconds_sum / Δsglang_time_to_first_token_seconds_count`
  - `Δsglang_inter_token_latency_seconds_sum / Δsglang_inter_token_latency_seconds_count`
  - `Δsglang_e2e_request_latency_seconds_sum / Δsglang_e2e_request_latency_seconds_count`
- Percentile charts use `histogram_quantile()` over SGLang histogram buckets and are displayed separately from mean KPI tiles.
- local Storage / AI memory node activity is inferred from SGLang hierarchy movement counters (`sglang_backuped_tokens_total`, `sglang_load_back_tokens_total`, `sglang_prefetched_tokens_total`, `sglang_evicted_tokens_total`) or direct blktrace data if present.
- Host block I/O and OS page activity sections document node-exporter/iostat/vmstat metric sources and are not labeled as L3 unless the setup explicitly maps the block device to local Storage / AI memory node.
- Major report sections now include a Formula & Metrics Used subsection so that each displayed value has an auditable source.


## AMDuProfPcm reset/sudo behavior

When `--enable-amduprof-pcm` is used, AMOprof runs AMDuProfPcm with `-r` to reset/clean existing PCM state before capture. If AMOprof itself is not running as root, the collector runs `sudo -n AMDuProfPcm ...` so MSR access succeeds non-interactively or fails clearly without a password prompt.


### v1.69 system collector sudo behavior

AMOprof now runs root-required system collectors through non-interactive sudo when it is not already running as root. This applies to NVMe SMART/admin commands, BCC/eBPF tools, blktrace, biosnoop, biolatency, AMDuProfPcm, perf PID attach, bpftrace, and IPMI power polling. The command prefix is `sudo -n`, so AMOprof will not hang waiting for a password prompt. If passwordless sudo is not configured, the affected collector is skipped or marked unavailable with its error reason. Use `--no-sudo` to force direct execution.


## v1.70 reporting fixes

- Executive cache tier hides backend/vendor names in the top hero line and uses generic local Storage / AI memory node terminology.
- DRAM BW tile includes host DRAM capacity context: used/total when available, or total capacity when used capacity is unavailable.
- DRAM static chart output is rendered in a compact image path to avoid combined-report iframe/srcdoc rendering failures.
- Bottleneck scores are clamped to 0-100 and KV/cache-hit mapping includes active cache hit vs input/prefill-token weighted diagnostic details.

### v1.72 HBM active-capacity calculation

HBM capacity in Executive / Interactive report tiles is now computed from the active inference parallelism in `setup_details.json`:

```text
active_hbm_total_gb = TP size × DP size × GPU Memory per Device GB
active_hbm_used_gb  = per_gpu_hbm_used_gb × TP size × DP size
```

If `TP size` is missing, AMOprof falls back to `GPU Count` / parsed GPU description.



### v1.88.0 notes

- Fixes the End Report P50/P90/P99 Summary token-percentile panel so Prompt / Output Token Percentiles are populated from SGLang token histogram aliases when available.
- Supports both `sglang_prompt_tokens_histogram_bucket` / `sglang_generation_tokens_histogram_bucket` and `sglang_prompt_tokens_bucket` / `sglang_generation_tokens_bucket`.
- Falls back to Prometheus-derived per-request token counter deltas when token histogram buckets are not exported, instead of leaving the panel blank.
- Keeps local Storage / AI memory node gating from v1.78: eviction remains cache pressure and is not mislabeled as storage activity.

### v1.78.0 notes

- Fixed End Report zero-data collapsing for the **Trim / Discard Events & Temporal Patterns** section.
- The section now collapses by default when explicit TRIM indicators show no activity, even if read/write temporal reference values or placeholder chart content are present.
- This keeps §E behavior consistent with the other no-data / zero-data sections.

### v1.74.0 notes

- Fixed L2 DRAM cache used/capacity reporting so SGLang HiCache host-used token counters are converted with TP-sharded KV bytes when the full-model conversion would exceed the configured HiCache allocation. The report no longer shows impossible values such as 186 GB used out of 100 GB configured.


### v1.88.0
- Fixed Session / Stream Analysis rendering from Prometheus aggregate counters when raw per-request traces are absent.


### v1.88.0 selected-window KPI consistency

- TTFT/TPOT/E2E KPIs in Executive, Interactive, and End Report now use selected-window SGLang counter deltas first, selected-window percentile timeseries second, and `sglang_summary.json` only as last fallback.
- This prevents L2-only and L3-active reports from showing identical latency KPIs when their run-local charts/counters differ.
- GPU utilization remains active-window based and is not averaged over inactive/idle-only samples where active samples exist.


### v1.95.0
- DRAM/L2 used capacity in Executive and Interactive reports now uses the selected-window active mean of SGLang HiCache host-used token gauges instead of a stale last sample or setup fallback. This makes L2-only and L3-active reports differ when their L2 residency differs, and labels the source in the tile note.



### v1.39.20
- Added a shared L3 backend resolver used by report logic before interpreting SGLang HiCache movement counters. `sglang_backuped_tokens_total` is now labeled as local-SSD L3 write only when the resolved backend is `local_ssd`; Mooncake/remote backends are labeled as remote logical L3 movement, and unknown backends remain generic logical HiCache backup.
- Tightened Executive and End Report L3 I/O reconciliation: physical SSD bytes from blktrace/iostat remain separate from SGLang logical L3 estimates, with explicit provenance and backend class.
- End Report Storage I/O overlays SGLang logical estimates only for resolved local SSD backends; remote/Mooncake movement is no longer forced onto local block-device charts.
- Improved blktrace analyzer coverage diagnostics so zero captured writes/reads with positive `/sys/block` deltas now raises a coverage warning instead of silently looking like no I/O.
- Added read-side coverage ratio diagnostics alongside existing write-side capture validation to catch wrong-device, dropped-event, RAID/multi-device, and delayed-write anomalies.

### v1.99.0
- Fixed End Report **Storage I/O & OS Page Activity** chart to use the same authoritative SSD/L3 stream as Interactive (`nvme_io_ts`) when it contains non-zero read/write activity.
- Prevents regressions where Interactive/Executive show local SSD L3 reads+writes while the End Report storage chart appears empty because `nvme_ts` was empty/stale.
- Added fallback derivation from bandwidth to approximate IOPS when only `rd_bw_mbs` / `wr_bw_mbs` are available.
- Chart title now shows source (`nvme_io_ts` vs `nvme_ts`) and both read/write max IOPS.

### v1.96.0
- Fixed End Report KV$ L3 per-stream bandwidth and temporal-pattern chart clipping by using an auto-sized canvas, safer image padding, and explicit IAT/temporal subplots.
- Chart images now use responsive `height:auto`/`object-fit:contain` styling to avoid truncated combined-report rendering.

### v1.39.20 — KV$B vs Host Block I/O Consistency Guard
- Keeps SGLang KV$B block movement as the authoritative logical L3/backing-tier direction.
- Labels host block I/O charts as host/OS telemetry unless setup_details resolves a concrete local SSD L3 device/path.
- Prevents physical host read/write bars from visually contradicting logical L3 backup/load-back counters.
- Adds explicit chart notes in End Report and Interactive tabs explaining when block telemetry is, and is not, L3 SSD evidence.


### v1.39.20 — Cross-vendor DRAM bandwidth collection

- Added `--enable-dram` to the `collect` command.
- `--enable-dram --dram-tool auto` detects CPU vendor from `/proc/cpuinfo`:
  - AMD systems use AMD uProf PCM (`AMDuProfPcm`).
  - Intel systems use Intel Performance Counter Monitor (`pcm-memory`) with a Linux `perf uncore_imc` fallback.
- Added explicit overrides: `--dram-tool amduprof`, `--dram-tool intel-pcm`, `--dram-tool perf-imc`, and `--dram-tool none`.
- Added `--intel-pcm-memory-bin` for custom Intel PCM installations.
- Kept legacy `--enable-amduprof-pcm` as an alias for `--enable-dram --dram-tool amduprof`.
- Updated report labels from AMD-only wording to generic CPU PMU/DRAM wording.

Example:

```bash
amoprof collect --enable-dram --dram-tool auto --duration-s 300 ...
```

For Intel machines, install Intel PCM and make sure `pcm-memory` is in PATH, or pass:

```bash
amoprof collect --enable-dram --dram-tool intel-pcm --intel-pcm-memory-bin /path/to/pcm-memory ...
```



### Cache-hit-rate methodology

AMOprof no longer treats `sglang_cache_hit_rate` as the primary cache-hit KPI.
That metric is an instantaneous gauge and can be overwritten frequently by SGLang,
so production reports now show all selected-window cache-hit derivations:

```text
Token weighted   = Δsglang_cached_tokens_total / Δsglang_prompt_tokens_total × 100
Time weighted    = avg_over_time(sglang_cache_hit_rate[report_window]) × 100
Request weighted = Δsglang_request_cache_hit_total / Δsglang_request_total × 100
```

The primary Executive KPI prefers token-weighted, then request-weighted, then
time-weighted when the required counters are available. Evictions/offloads/backups
are reported separately as tier-capacity/movement pressure and do not by themselves
mean cache-hit rate must be low.

### DRAM PMU dependency installer — AMD + Intel

AMOprof now includes a distro-aware dependency installer for `collect --enable-dram`:

```bash
# Auto-detect CPU vendor and install the matching DRAM backend dependencies
sudo ./scripts/install_dram_deps.sh --dram-tool auto

# Install/check both AMD and Intel DRAM backends where possible
sudo ./scripts/install_dram_deps.sh --dram-tool all

# Intel systems: install Intel PCM pcm-memory from native packages
sudo ./scripts/install_dram_deps.sh --dram-tool intel-pcm

# Intel systems: if the distro package is unavailable, build Intel PCM from source
sudo ./scripts/install_dram_deps.sh --dram-tool intel-pcm --build-intel-pcm

# AMD systems: install prerequisites and install AMD uProf from a local installer
sudo ./scripts/install_dram_deps.sh --dram-tool amduprof \
  --amduprof-installer ./AMDuProf_Linux_x64.deb
```

The main installer can invoke the same dependency path:

```bash
sudo ./install.sh --with-dram-deps --dram-tool auto
```

Backend behavior:

| CPU / option | Tool used by `amoprof collect --enable-dram --dram-tool auto` | Installer behavior |
|---|---|---|
| AMD | `AMDuProfPcm` | Installs kernel/MSR prerequisites; installs AMD uProf only when a local installer or URL is provided |
| Intel | Intel PCM `pcm-memory` | Installs distro package `pcm` where available; optional `--build-intel-pcm` source build fallback |
| Unknown / virtualized | `perf-imc` fallback | Installs `perf`, `msr-tools`, `numactl`, and kernel counter prerequisites |

The installer checks for existing binaries first and does not reinstall tools that are already present.

### v1.39.20 L3 read-byte semantics

AMOprof no longer counts `sglang_load_back_tokens_total` as local SSD/L3 read bytes. The Executive and report L3 read estimate uses `sglang_prefetched_tokens_total × KV_bytes_per_token`; write uses `sglang_backuped_tokens_total × KV_bytes_per_token`. `load_back_tokens_total` is displayed as a hierarchy-restore diagnostic/upper bound only because it can include L2 DRAM/page-cache/HBM reload paths and can greatly exceed physical SSD footprint or blktrace bytes.

blktrace collection now defaults to larger buffers (`-b 16384 -n 4`) and exposes `--blktrace-buffer-kb` / `--blktrace-num-buffers` for high-I/O runs.


### SGLang L3 logical read/write formulas

AMOprof treats SGLang HiCache counters as logical KV movement. The production formulas are:

```text
L3 logical write/offload bytes =
  Δsglang_backuped_tokens_total × KV_bytes_per_token

L3 logical read/onboard bytes =
  Δsglang_prefetched_tokens_total × KV_bytes_per_token
```

Diagnostic-only counters:

```text
Load-back diagnostic upper bound =
  Δsglang_load_back_tokens_total × KV_bytes_per_token

Eviction pressure diagnostic =
  Δsglang_evicted_tokens_total × KV_bytes_per_token
```

`sglang_load_back_tokens_total` is intentionally not counted as local-SSD read bytes because it can represent hierarchy restore/reload pressure and may include L2 DRAM, page cache, HBM reload, or repeated logical reconstruction. Physical SSD bytes come only from blktrace/iostat on the resolved L3 block device.


### v1.39.20 chart legend and host block activity fallback

Interactive and Executive Plotly charts now normalize legends before render so labels remain readable in iframe/card layouts. Legends are placed below the x-axis with reserved bottom margin, fixed entry widths, and extra height for charts with many traces.

The Host/OS block I/O latency/utilization chart no longer renders an empty canvas when read/write activity exists but latency/busy counters are missing. If `rd_lat_ms`, `wr_lat_ms`, and `io_util_pct` are unavailable or all zero while `rd_bw_mbs`, `wr_bw_mbs`, `rd_iops`, or `wr_iops` have activity, AMOprof renders an activity fallback chart showing available BW/IOPS and explicitly labels latency/utilization as unavailable. Read/write activity alone does not imply latency/utilization counters were collected; those require `rd_ms/wr_ms/io_ms`, iostat `await/%util`, or blktrace latency derivation.


### v1.39.20 — P50 summary tiles

Summary tiles in Executive, Interactive, and End Report now show p50/median next to existing mean latency and throughput KPIs:

```text
TTFT mean = Δsglang_time_to_first_token_seconds_sum / Δsglang_time_to_first_token_seconds_count × 1000
TTFT p50  = histogram_quantile(0.50, rate(sglang_time_to_first_token_seconds_bucket[window])) × 1000

TPOT/ITL mean = Δsglang_inter_token_latency_seconds_sum / Δsglang_inter_token_latency_seconds_count × 1000
TPOT/ITL p50  = histogram_quantile(0.50, rate(sglang_inter_token_latency_seconds_bucket[window])) × 1000

Throughput mean = active_mean(sglang_gen_throughput)
Throughput p50  = median(nonzero_samples(sglang_gen_throughput))
```

Mean remains useful for overall run cost/capacity planning. P50 gives the typical request/token path for executive and engineering readers.


### v1.39.20 — collect `--output-dir` hardening

`amoprof collect --output-dir <DIR>` now resolves all collect-time paths at startup and writes a `collection_output_manifest.json` into the created `metrics_run_*` directory. The manifest lists generated artifacts and warns if any collector-reported artifact path is outside the requested output tree.

Collector hardening in this release:

- Exposes `AMOPROF_OUTPUT_DIR`, `AMOPROF_RUN_DIR`, and `AMOPROF_RAW_DIR` to child tools.
- Passes canonical `raw/` working directories to Intel PCM / perf IMC, AMD uProf PCM, BPF trace, and related external profiler launches.
- Mirrors Intel PCM raw CSV output into `raw/pcm_memory_raw.csv` when available.
- Fixes PID/BPF collection duration when `--duration-s` is omitted but a stop condition or `--max-duration-s` is used.
- Adds an output-scope validation step after report generation.


### v1.39.20 — Queue-depth population fixes

The SSD Queue Depth / AI Stack Layer Pressure section now has a three-tier data path:

1. Preferred: exact blktrace Q→C event walk from raw `trace.blktrace.*` binaries.
2. Fallback: `blkparse_events.generated.csv` when it contains both `Q` and `C` events.
3. Coarse fallback: `nvme_driver_timeseries.csv` `inflight` / iostat `aqu-sz` / sysfs inflight.

This prevents the queue-depth section from rendering empty when read/write activity exists but the exact blktrace Q→C summary file was not produced. Exact blktrace queue depth remains the source of truth when available; fallback values are clearly labeled as sampled/coarse pressure indicators.


### Queue-depth collection sources

`amoprof collect` now captures queue-depth / device-pressure information from all cheap local sources by default, and uses exact event-level queue depth when blktrace is enabled:

| Source | File / metric | Purpose |
|---|---|---|
| blktrace Q→C | `raw/blktrace_analysis/queue_depth_timeseries.csv`, `queue_depth_summary.json` | Exact event-level queue depth when `--enable-blktrace` is used |
| iostat | `raw/iostat_timeseries.csv`, `aqu-sz` / `avgqu-sz` | Kernel averaged queue size fallback |
| sysfs stat | `/sys/block/<dev>/stat` field 8 | Instantaneous in-flight I/O |
| sysfs weighted queue time | `/sys/block/<dev>/stat` field 10 | Time-weighted average queue depth over each sample interval |
| sysfs inflight split | `/sys/block/<dev>/inflight` | Read/write in-flight split |
| proc diskstats | `/proc/diskstats` | Fallback copy of kernel block stats |
| sysfs queue config | `/sys/block/<dev>/queue/*` | Queue limits/config such as `nr_requests`, scheduler, merge settings |

The unified collector writes `raw/queue_depth_sources_timeseries.csv` and `raw/queue_depth_sysfs_summary.json`. Reports prefer exact blktrace Q→C, then the unified multi-source queue-depth file, then legacy `nvme_driver_timeseries.csv` / `iostat_timeseries.csv` fallback.


### blktrace collection diagnostics

When `--enable-blktrace` is passed, AMOprof now writes launch diagnostics under the run raw directory:

```text
raw/blktrace_command.txt
raw/blktrace_launch_stderr.txt
raw/blktrace_summary.json
```

If `--strict-sanity` is enabled and blktrace produces no binary files or no parseable events, collection returns non-zero after writing diagnostics. Common causes are:
- the whole command was not run with `sudo` and `sudo -n` cannot acquire privileges;
- debugfs/tracefs is not mounted;
- another blktrace is already active on the same device;
- CAP_SYS_ADMIN is unavailable in the container/session;
- blktrace/blkparse binaries are missing or incompatible.

Recommended local SSD command form:

```bash
sudo amoprof collect \
  --output-dir ./amoprof_results \
  --ssd-device /dev/nvme7n1 \
  --enable-blktrace \
  --blktrace-buffer-kb 32768 \
  --blktrace-num-buffers 8 \
  --strict-sanity
```


### Blktrace event cap behavior

By default, AMOprof now uses **all available blktrace events** captured during the collection/analyze window. There is no implicit 5M or 10M event cap.

Use an event cap only when you explicitly want to bound memory/runtime on very large traces:

```bash
amoprof collect --enable-blktrace --blktrace-max-events 5000000 ...
```

When the cap is omitted, both collect-time `blkparse_events.generated.csv` and binary re-analysis from `raw/blktrace_data/trace.blktrace.*` consume all parseable events. When the cap is provided, AMOprof applies uniform 1-in-N sampling and records `event_cap` / `event_cap_applied` in the blktrace analysis summary.


### Blktrace start diagnostics

AMOprof no longer warns if `blktrace` is running but no `trace.blktrace.*` files are visible immediately after launch. That early state is diagnostic only; some systems do not expose or flush trace files until later in the run or at stop time.

For each run, AMOprof writes:

```text
raw/blktrace_start_status.json
raw/blktrace_command.txt
raw/blktrace_launch_stderr.txt
raw/blktrace_summary.json
```

Only the stop-time summary determines failure. With `--strict-sanity`, missing usable blktrace data at stop still returns a non-zero status.


### Biosnoop collection behavior

AMOprof controls biosnoop duration itself. BCC `biosnoop` uses `-t` for timestamps; it is **not** a duration argument. AMOprof now runs biosnoop as:

```bash
biosnoop-bpfcc -t
```

and stops it at collection stop time with SIGINT.

For diagnostics, AMOprof writes:

```text
raw/biosnoop_command.txt
raw/biosnoop_stderr.txt
raw/biosnoop_raw.log
raw/biosnoop_summary.json
raw/biosnoop_events_all.csv
raw/biosnoop_events.csv
```

`biosnoop_events_all.csv` contains all devices seen by biosnoop. `biosnoop_events.csv` is filtered to the requested `--ssd-device` and matching partitions such as `nvme7n1p1`. If the filtered CSV is empty but the all-device CSV has rows, check the `DISK` values in `biosnoop_events_all.csv` and verify whether the workload is hitting the expected device.


### Biosnoop preflight: header vs event verification

The biosnoop preflight now distinguishes two levels:

```text
attach/header OK
```

means the BCC tool started and emitted its header. This proves attach/startup, but not data capture.

When `--strict-sanity` is used, AMOprof now performs a tiny read-only direct read from `--ssd-device` while biosnoop is running and requires at least one matching biosnoop event for that disk or partition. This catches the case where biosnoop prints a header but emits no real block I/O events.


### End Report queue-depth charts

The static End Report now renders a PNG chart for **SSD Queue Depth — AI Stack Layer Pressure** whenever queue-depth data exists. Chart source priority is:

```text
blktrace_analysis/queue_depth_timeseries.csv + queue_depth_distribution.csv
→ raw/queue_depth_sources_timeseries.csv
→ raw/queue_depth_sysfs_timeseries.csv
→ nvme/iostat inflight or aqu-sz fallback
```

The chart includes queue depth over time, distribution, saturation threshold percentages, and mean/p50/p95/p99/peak summary bars.
