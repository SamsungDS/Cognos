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

### v1.39.11 L3 read-byte semantics

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


### v1.39.11 chart legend and host block activity fallback

Interactive and Executive Plotly charts now normalize legends before render so labels remain readable in iframe/card layouts. Legends are placed below the x-axis with reserved bottom margin, fixed entry widths, and extra height for charts with many traces.

The Host/OS block I/O latency/utilization chart no longer renders an empty canvas when read/write activity exists but latency/busy counters are missing. If `rd_lat_ms`, `wr_lat_ms`, and `io_util_pct` are unavailable or all zero while `rd_bw_mbs`, `wr_bw_mbs`, `rd_iops`, or `wr_iops` have activity, AMOprof renders an activity fallback chart showing available BW/IOPS and explicitly labels latency/utilization as unavailable. Read/write activity alone does not imply latency/utilization counters were collected; those require `rd_ms/wr_ms/io_ms`, iostat `await/%util`, or blktrace latency derivation.


### v1.39.11 — P50 summary tiles

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
