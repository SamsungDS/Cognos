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

