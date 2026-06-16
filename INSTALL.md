AMOprof v1.90.0

# AMOprof — Installation Guide

## Recommended: Virtual Environment (avoids all system Python conflicts)

```bash
# 1. Create and activate a venv
python3 -m venv ~/aiwasp_venv
source ~/aiwasp_venv/bin/activate

# 2. Upgrade pip inside the venv
pip install --upgrade pip

# 3. Install base package
pip install ./aiwasp_pkg

# 4. Install optional extras based on your machine type
#    CPU machine (DRAM + SSD profiling only):
pip install "./aiwasp_pkg[cpu]"

#    GPU machine (DGX — HBM + full stack):
pip install "./aiwasp_pkg[gpu]"

#    Fine-tuning / checkpoint / WAF tests:
pip install "./aiwasp_pkg[training]"

#    Everything:
pip install "./aiwasp_pkg[all]"

# 5. Verify
amoprof --list-models
```

---

## Why the system pip fails

Debian/Ubuntu install some Python packages via `apt` (e.g. `typing_extensions`,
`urllib3`, `charset-normalizer`) without a pip RECORD file.  When a deep
dependency (torch, transformers) requires a newer version, pip tries to uninstall
the system copy and hits:

```
ERROR: Cannot uninstall typing_extensions 4.10.0, RECORD file not found.
Hint: The package was installed by debian.
```

A virtual environment sidesteps this entirely — it has its own clean site-packages.

---

## Workaround if you cannot use a venv

Add `--ignore-installed` to skip the broken uninstall step:

```bash
pip3 install --ignore-installed --break-system-packages "./aiwasp_pkg[gpu]"
```

> ⚠️  This overwrites the system `typing_extensions` in-place without
> uninstalling the old one first.  It works but is not clean.
> Use the venv approach on any machine you care about.

---

## Minimal install (no ML frameworks — for fio / iostat / SMART profiling only)

If you only want to run the fio baselines and SSD metric collectors without
downloading torch/transformers/vLLM:

```bash
source ~/aiwasp_venv/bin/activate
pip install ./aiwasp_pkg        # installs only psutil + rich
amoprof --model deepseek-v3 \
       --hbm-cap 80GB --dram-cap 512GB --nvme-cap 10TB \
       --ai-op weight-load --dry-run
```

The framework runners will raise a clear `ImportError` if you try to run a
workload that needs a missing framework, without crashing the whole harness.

---

## System tool dependencies (installed via apt, not pip)

```bash
sudo apt install -y \
    fio \
    nvme-cli \
    sysstat \
    linux-tools-common \
    linux-tools-$(uname -r) \
    bpfcc-tools \
    ipmitool
```


## Included wrapper

Use `./run_aiwasp_swebench_pro_sweeps.sh` for benchmark and sweep runs.

---

## SWE-agent and mini-swe-agent setup (for `sweagent` and `mini` backends)

Both agents are git submodules inside [scaleapi/SWE-bench_Pro-os](https://github.com/scaleapi/SWE-bench_Pro-os).

### 1. Clone the repo with submodules

```bash
git clone --recurse-submodules https://github.com/scaleapi/SWE-bench_Pro-os
export SWEAP_REPO_ROOT=/path/to/SWE-bench_Pro-os
```

Add `SWEAP_REPO_ROOT` to your shell profile so it persists.

### 2. Install SWE-agent submodule

```bash
cd $SWEAP_REPO_ROOT/SWE-agent
pip install -e ".[dev]"
```

### 3. Install mini-swe-agent submodule

```bash
cd $SWEAP_REPO_ROOT/mini-swe-agent
pip install -e ".[extra]"
```

The `[extra]` extra installs `mini-extra`, the CLI entry point used for
per-instance SWE-bench runs (`mini-extra swebench-single`).

### 4. Verify

```bash
sweagent --help       # should show SWE-agent v1.x options
mini-extra --help     # should show mini-swe-agent extra commands
```

### 5. Run with the correct backend

```bash
# SWE-agent (pinned submodule version)
SWEAP_REPO_ROOT=/path/to/SWE-bench_Pro-os \
AGENT_BACKEND=sweagent \
  ./run_aiwasp_swebench_pro_sweeps.sh concurrency

# mini-swe-agent (pinned submodule version)
SWEAP_REPO_ROOT=/path/to/SWE-bench_Pro-os \
AGENT_BACKEND=mini \
  ./run_aiwasp_swebench_pro_sweeps.sh concurrency
```

If `SWEAP_REPO_ROOT` is not set, AMOprof falls back to whatever
`sweagent` / `mini-extra` is on your system PATH (pip-installed version).

### How executable discovery works

AMOprof looks for the agent in this order:
1. `$SWEAP_REPO_ROOT/SWE-agent/.venv/bin/sweagent` (submodule venv)
2. `$SWEAP_REPO_ROOT/SWE-agent/venv/bin/sweagent`
3. `sweagent` on system PATH
4. `python -m sweagent` (module fallback)

Same pattern for `mini-extra` / `mini_extra` in the `mini-swe-agent/` submodule.



## AMD / Intel DRAM bandwidth dependencies

For `amoprof collect --enable-dram`, use the included OS-aware installer:

```bash
sudo ./scripts/install_dram_deps.sh --dram-tool auto
```

It detects `/etc/os-release`, the package manager (`apt`, `dnf`, `yum`, `zypper`, or `pacman`), and the CPU vendor from `/proc/cpuinfo`.

Typical paths:

```bash
# AMD host
sudo ./scripts/install_dram_deps.sh --dram-tool amduprof \
  --amduprof-installer ./AMDuProf_Linux_x64.deb

# Intel host
sudo ./scripts/install_dram_deps.sh --dram-tool intel-pcm

# Intel host with no distro PCM package
sudo ./scripts/install_dram_deps.sh --dram-tool intel-pcm --build-intel-pcm

# Install/check both backends
sudo ./scripts/install_dram_deps.sh --dram-tool all
```

The generic package installer can also call it:

```bash
sudo ./install.sh --with-dram-deps --dram-tool auto
```

Notes:
- Intel PCM is installed from the native `pcm` package where the distro provides it.
- AMD uProf is not silently downloaded because AMD distributes it separately; pass `--amduprof-installer` or `--amduprof-url` to install it.
- `perf-imc` fallback installs/checks `perf`, `msr-tools`, and kernel counter prerequisites.

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
