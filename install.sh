#!/usr/bin/env bash
# =============================================================================
# AMOprof — Dependency Installation Script
# Tested on: Ubuntu 22.04 / DGX A100 (CUDA 12.x, Python 3.10+)
#
# Usage:
#   chmod +x install.sh
#   ./install.sh              # metrics-only mode (default, no torch/sglang)
#   ./install.sh --sglang     # + SGLang inference server deps
#   ./install.sh --full       # + SGLang + SWE-bench agent deps
#   ./install.sh --help
# =============================================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
section() { echo -e "\n${BOLD}── $* ──${NC}"; }

# ── Argument parsing ──────────────────────────────────────────────────────────
MODE="metrics"   # metrics | sglang | full
SKIP_APT=0
SKIP_VENV=0
VENV_DIR="${AMOPROF_VENV:-$HOME/amoprof_venv}"
TORCH_INDEX="https://download.pytorch.org/whl/cu121"  # override for other CUDA

usage() {
cat <<EOF
Usage: $0 [OPTIONS]

Modes (mutually exclusive):
  (default)     Install AMOprof + Python deps for metrics collection only.
                No torch, no sglang. Suitable for a separate monitoring node.
  --sglang      Also install SGLang and PyTorch (GPU required).
  --full        --sglang + SWE-bench + sweagent deps.

Options:
  --venv DIR          Path for virtualenv  (default: ~/amoprof_venv)
  --torch-index URL   PyTorch wheel index  (default: cu121)
  --skip-apt          Skip apt system package installation (requires root/sudo)
  --skip-venv         Install into current Python environment (not recommended)
  --help              Show this message
EOF
exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sglang)       MODE="sglang"; shift ;;
        --full)         MODE="full";   shift ;;
        --venv)         VENV_DIR="$2"; shift 2 ;;
        --torch-index)  TORCH_INDEX="$2"; shift 2 ;;
        --skip-apt)     SKIP_APT=1; shift ;;
        --skip-venv)    SKIP_VENV=1; shift ;;
        --help|-h)      usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
done

# ── Preflight ────────────────────────────────────────────────────────────────
section "Preflight checks"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$SCRIPT_DIR"

if [[ ! -f "$PACKAGE_DIR/pyproject.toml" ]]; then
    error "pyproject.toml not found in $PACKAGE_DIR. Run this script from the package root."
    exit 1
fi

PY=$(command -v python3 || true)
if [[ -z "$PY" ]]; then
    error "python3 not found. Install Python 3.10+ first."
    exit 1
fi

PY_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=${PY_VER%%.*}
PY_MINOR=${PY_VER##*.}
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]]; then
    error "Python 3.10+ required, found $PY_VER"
    exit 1
fi
ok "Python $PY_VER"

if [[ "$MODE" != "metrics" ]]; then
    if ! command -v nvidia-smi &>/dev/null; then
        warn "nvidia-smi not found — GPU mode selected but no GPU detected. Continuing anyway."
    else
        GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1 || true)
        ok "GPU: $GPU_INFO"
    fi
fi

# ── System packages (apt) ────────────────────────────────────────────────────
section "System packages"

APT_CORE=(
    # Python build deps
    python3-dev python3-venv python3-pip

    # NVMe / block device tools
    nvme-cli          # nvme smart-log, nvme latency-stats → NvmeSmartMonitor, NvmeDriverMonitor

    # I/O profiling
    sysstat           # iostat → IostatMonitor
    linux-tools-common linux-tools-generic  # perf stat → PerfStatCollector

    # BPF / tracing — needed for biolatency (always) and biosnoop (opt-in --enable-biosnoop)
    bpfcc-tools       # biolatency-bpfcc, biosnoop-bpfcc → BiolatencyCollector, BiosnoopCollector
    bpftrace          # bpftrace → BpftraceCollector

    # Per-request block I/O tracing (opt-in --enable-blktrace; required for §C/§D/§E/§H/§I charts)
    blktrace          # blktrace, blkparse → BlktraceCollector

    # Misc
    jq curl wget build-essential
)

if [[ "$SKIP_APT" -eq 1 ]]; then
    warn "Skipping apt install (--skip-apt). Ensure the following are installed:"
    printf '  %s\n' "${APT_CORE[@]}"
else
    if ! command -v apt-get &>/dev/null; then
        warn "apt-get not found — skipping system package install (non-Debian system)."
    else
        info "Updating apt cache..."
        sudo apt-get update -qq
        info "Installing system packages..."
        sudo apt-get install -y --no-install-recommends "${APT_CORE[@]}"
        ok "System packages installed"
    fi
fi

# ── Virtualenv ───────────────────────────────────────────────────────────────
section "Python virtual environment"

if [[ "$SKIP_VENV" -eq 1 ]]; then
    warn "--skip-venv: installing into current Python environment."
    PIP="pip3"
else
    if [[ ! -d "$VENV_DIR" ]]; then
        info "Creating venv at $VENV_DIR ..."
        "$PY" -m venv "$VENV_DIR"
    else
        info "Reusing existing venv at $VENV_DIR"
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    PIP="pip"
    ok "venv active: $VENV_DIR"
fi

$PIP install --quiet --upgrade pip setuptools wheel

# ── Core Python deps ─────────────────────────────────────────────────────────
section "Core Python dependencies"

# Direct runtime deps (always required)
CORE_DEPS=(
    "psutil>=5.9"    # PID detection, net_connections
    "PyYAML>=6.0"    # YAML config parsing
    "rich>=13.0"     # CLI output formatting
    # amoprof analyzer deps (always installed — amoprof is bundled with the package)
    "pandas>=1.5"
    "numpy>=1.24"
    "matplotlib>=3.7"
    "scipy>=1.10"
    "openpyxl>=3.1"
    "requests>=2.28"
    "Pillow>=9.4"
)

info "Installing core deps: ${CORE_DEPS[*]}"
$PIP install --quiet "${CORE_DEPS[@]}"
ok "Core deps installed"

# ── AMOprof package ───────────────────────────────────────────────────────────
section "Installing AMOprof"

case "$MODE" in
    metrics)
        info "Installing amoprof (metrics-only, no torch/sglang)..."
        $PIP install --quiet -e "$PACKAGE_DIR"
        ;;
    sglang)
        info "Installing amoprof[sglang] ..."
        $PIP install --quiet \
            --extra-index-url "$TORCH_INDEX" \
            -e "$PACKAGE_DIR[sglang]"
        ;;
    full)
        info "Installing amoprof[sglang,swebench] ..."
        $PIP install --quiet \
            --extra-index-url "$TORCH_INDEX" \
            -e "$PACKAGE_DIR[sglang,swebench]"

        # sweagent is not on PyPI in all versions — install from GitHub if needed
        if ! python3 -c "import sweagent" 2>/dev/null; then
            info "Installing sweagent from GitHub..."
            $PIP install --quiet "git+https://github.com/SWE-agent/SWE-agent.git"
        else
            ok "sweagent already available"
        fi
        ;;
esac
ok "AMOprof installed"

# ── Optional: DCGM (DGX-specific) ────────────────────────────────────────────
section "DCGM / dcgmi (optional, DGX only)"

if command -v dcgmi &>/dev/null; then
    ok "dcgmi found: $(dcgmi version 2>/dev/null | head -1 || echo 'version unknown')"
    ok "GpuMonitor will use dcgmi dmon for CUDA kernel-level counters."
else
    warn "dcgmi not found — GpuMonitor will fall back to nvidia-smi dmon."
    warn "To install DCGM on DGX:"
    echo "    wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb"
    echo "    sudo dpkg -i cuda-keyring_1.1-1_all.deb"
    echo "    sudo apt-get update && sudo apt-get install -y datacenter-gpu-manager"
    echo "    sudo systemctl enable --now nvidia-dcgm"
fi

# ── Optional: Nsight Systems ──────────────────────────────────────────────────
section "Nsight Systems / nsys (optional)"

if command -v nsys &>/dev/null; then
    ok "nsys found: $(nsys --version 2>/dev/null | head -1 || echo 'version unknown')"
else
    warn "nsys not found — NsysGpuTraceCollector will be unavailable."
    warn "Install from: https://developer.nvidia.com/nsight-systems"
fi

# ── Optional: AMD uProf (optional) ───────────────────────────────────────────
section "AMD uProf PCM (optional)"

AMDUPROF_DEFAULT="/opt/AMDuProf_5.2-606/bin/AMDuProfPcm"
if [[ -x "$AMDUPROF_DEFAULT" ]]; then
    ok "AMDuProfPcm found at $AMDUPROF_DEFAULT"
elif command -v AMDuProfPcm &>/dev/null; then
    ok "AMDuProfPcm found in PATH"
else
    warn "AMDuProfPcm not found — AMDuProfPcmMemoryCollector will be unavailable."
    warn "Download from: https://www.amd.com/en/developer/uprof.html"
fi

# ── Optional: Intel PCM ───────────────────────────────────────────────────────
section "Intel PCM (optional)"

if command -v pcm-memory &>/dev/null || [[ -x "/usr/local/bin/pcm-memory" ]]; then
    ok "pcm-memory found"
else
    warn "pcm-memory not found — PcmMemoryCollector will be unavailable."
    warn "Install: sudo apt-get install -y intel-pcm  (or build from https://github.com/intel/pcm)"
fi

# ── blktrace + blkparse (per-request NVMe events) ─────────────────────────────
section "blktrace (per-request NVMe events, §C/§D/§E/§H charts)"

if command -v blktrace &>/dev/null && command -v blkparse &>/dev/null; then
    BLKT_VER=$(blktrace -v 2>&1 | head -1 || echo unknown)
    ok "blktrace + blkparse found: $BLKT_VER"
    ok "Enable with: amoprof collect --enable-blktrace ..."
else
    warn "blktrace/blkparse not found. The §C/§D/§E/§H request-level NVMe charts"
    warn "will be empty without it. Install: sudo apt-get install -y blktrace"
fi

# ── BCC biosnoop (per-IO PID attribution) ─────────────────────────────────────
section "biosnoop (per-IO PID attribution, §I per-stream chart)"

BIOSNOOP_FOUND=""
for candidate in biosnoop-bpfcc biosnoop /usr/sbin/biosnoop-bpfcc /usr/share/bcc/tools/biosnoop; do
    if command -v "$candidate" &>/dev/null || [[ -x "$candidate" ]]; then
        BIOSNOOP_FOUND="$candidate"; break
    fi
done
if [[ -n "$BIOSNOOP_FOUND" ]]; then
    ok "biosnoop found at: $BIOSNOOP_FOUND"
    ok "Enable with: amoprof collect --enable-biosnoop ..."
else
    warn "biosnoop not found. The §I per-stream bandwidth chart will be empty."
    warn "Install: sudo apt-get install -y bpfcc-tools"
fi

# ── sudo / capability check for tracing tools ────────────────────────────────
section "Privilege check for tracing tools"

if [[ "$EUID" -eq 0 ]]; then
    ok "Running as root — blktrace/biosnoop will work directly."
elif sudo -n true 2>/dev/null; then
    ok "Passwordless sudo available — blktrace/biosnoop will work via sudo -n."
else
    warn "blktrace and biosnoop require root or passwordless sudo."
    warn "Either:"
    warn "  (a) Run AMOprof itself with 'sudo': sudo amoprof collect ..."
    warn "  (b) Configure sudoers for the current user (recommended for automated runs):"
    warn "      sudo visudo  → add line:"
    warn "      $USER ALL=(root) NOPASSWD: /usr/sbin/blktrace, /usr/bin/blkparse, /usr/sbin/biosnoop-bpfcc"
    warn "  (c) Add CAP_SYS_ADMIN + CAP_BPF capabilities (advanced)."
fi

# ── Verify installation ───────────────────────────────────────────────────────
section "Verification"

if python3 -c "import amoprof; print('amoprof', amoprof.__version__)" 2>/dev/null; then
    ok "amoprof import OK"
else
    error "amoprof import failed — check errors above."
    exit 1
fi

if python3 -c "from amoprof.cli import main" 2>/dev/null; then
    ok "amoprof.cli import OK"
else
    error "amoprof.cli import failed."
    exit 1
fi

ENTRY=$(command -v amoprof 2>/dev/null || true)
if [[ -n "$ENTRY" ]]; then
    ok "amoprof CLI entrypoint: $ENTRY"
else
    warn "amoprof entrypoint not in PATH. Either activate the venv or add it:"
    [[ "$SKIP_VENV" -eq 0 ]] && echo "    source $VENV_DIR/bin/activate"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
section "Installation complete"

cat <<EOF

  Mode       : $MODE
  Venv       : ${SKIP_VENV:-0 == 0 && echo "$VENV_DIR" || echo "(none — system Python)"}
  Package    : $PACKAGE_DIR

  Collectors always-on (no flag required):
    IostatMonitor         iostat (sysstat)
    NvmeSmartMonitor      nvme-cli
    BiolatencyCollector   biolatency-bpfcc (bpfcc-tools)
    VmstatMonitor         /proc/vmstat
    SwapStormMonitor      /proc/vmstat per-sample swap timeseries        [NEW]
    DiscardStatsMonitor   /proc/diskstats TRIM/discard timeseries        [NEW]
    NvmeDriverMonitor     nvme-cli latency-stats
    GpuMonitor            nvidia-smi / dcgmi dmon
    DramMonitor           /proc/meminfo
    PowerMonitor          nvidia-smi
    NvlinkPcieMonitor     nvidia-smi + dcgmi dmon
    PcmMemoryCollector    pcm-memory (Intel PCM, optional binary)

  Collectors requiring explicit flags (need sudo/root):
    BlktraceCollector     --enable-blktrace      blktrace + blkparse     [NEW]
                          Populates §C/§D/§E/§H request-level NVMe charts
                          (read/write/trim size, IAT, LBA hot/cold)

    BiosnoopCollector     --enable-biosnoop      biosnoop-bpfcc          [NEW]
                          Populates §I per-stream bandwidth chart
                          (per-IO PID + comm attribution)

    AMDuProfPcmMemoryCollector  --enable-amduprof-pcm  AMDuProfPcm
                          Populates §F DRAM (CPU-side) bandwidth chart

  Collectors that require running on the SGLang node (PID attach):
    PerfStatCollector     perf stat (linux-tools-generic)
    BpftraceCollector     bpftrace
    NsysGpuTraceCollector --enable-nsys (Nsight Systems)

  Collectors requiring --sglang-port / --sglang-host:
    SGLangMetricsSampler  Prometheus /metrics scrape

  Example run (full report, local DGX node):
    sudo amoprof collect \\
      --sglang-port 30000 \\
      --ssd-device /dev/nvme2n1 \\
      --duration-s 300 \\
      --enable-blktrace \\
      --enable-biosnoop \\
      --enable-amduprof-pcm \\
      --enable-nsys \\
      --label my-run --analyze -v

  Example run (remote SGLang, AMOprof runs locally on storage node):
    sudo amoprof collect \\
      --sglang-host 10.0.1.5 --sglang-port 30000 \\
      --ssd-device /dev/nvme2n1 \\
      --duration-s 300 \\
      --enable-blktrace --enable-biosnoop \\
      --label my-run --analyze

  Activate venv before each session:
    source $VENV_DIR/bin/activate
EOF
