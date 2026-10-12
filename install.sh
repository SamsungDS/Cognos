#!/usr/bin/env bash
# =============================================================================
# AMOprof installer
#
# Default mode installs AMOprof for metrics collection/reporting only.
# Optional modes add SGLang dependencies.
# System dependencies are installed best-effort using the detected package manager,
# CPU architecture, CPU vendor, and available GPU tooling.
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
section() { echo -e "\n${BOLD}── $* ──${NC}"; }

MODE="metrics"                 # metrics | sglang | full
SKIP_SYS_PKGS=0
WITH_PCM=0                       # build Intel PCM from source (opt-in)
PCM_REF="${AMOPROF_PCM_REF:-}"   # tag/branch; empty = default branch
PCM_PREFIX="${AMOPROF_PCM_PREFIX:-/opt/intel-pcm}"
SKIP_VENV=0
VENV_DIR="${AMOPROF_VENV:-$HOME/amoprof_venv}"
TORCH_INDEX="${AMOPROF_TORCH_INDEX:-https://download.pytorch.org/whl/cu121}"
INSTALL_DRAM_DEPS=0
DRAM_DEPS_TOOL="${AMOPROF_DRAM_TOOL:-auto}"
BUILD_INTEL_PCM=0
AMDUPROF_INSTALLER=""
AMDUPROF_URL=""
ASSUME_YES=1
DRY_RUN=0

usage() {
cat <<'USAGE'
Usage: ./install.sh [OPTIONS]

Modes:
  default              Install AMOprof + metrics/reporting dependencies only.
  --sglang             Also install PyTorch/SGLang dependencies.
  --full               --sglang, plus SWE-agent from GitHub.

Options:
  --venv DIR           Virtualenv path. Default: ~/amoprof_venv
  --torch-index URL    PyTorch wheel index. Default: cu121 index.
  --skip-apt           Backward-compatible alias for --skip-system-packages.
  --skip-system-packages
                       Do not install OS packages.
  --skip-venv          Install into current Python environment.
  --with-dram-deps     Run scripts/install_dram_deps.sh after common deps.
  --dram-tool TOOL     auto | all | amduprof | intel-pcm | perf-imc | none
  --build-intel-pcm    Let the DRAM helper build Intel PCM if package is missing.
  --amduprof-installer PATH
                       Local AMD uProf installer for AMD systems.
  --amduprof-url URL   AMD uProf installer URL for the DRAM helper.
  --with-pcm           Build Intel PCM from source and use it for DRAM bandwidth.
                       Needed on CPUs newer than the installed PCM package
                       knows: PCM refuses a microarchitecture its build was not
                       compiled for, so every pcm-* binary is present and every
                       one exits with "unsupported processor". Skipped on AMD,
                       and when the installed PCM already supports this CPU.
  --pcm-ref REF        PCM git tag to build (default: repo default branch).
                       Xeon 6 / Granite Rapids needs 202409 or later.
  --pcm-prefix DIR     Install location (default: /opt/intel-pcm).
  --no                 Do not pass automatic yes flags to package manager.
  --dry-run            Print package-install commands without executing them.
  --help               Show this help.

Requires the Python version pyproject.toml declares (requires-python, 3.12+).

Examples:
  ./install.sh
  sudo ./install.sh --with-dram-deps --dram-tool auto
  ./install.sh --sglang --torch-index https://download.pytorch.org/whl/cu124

USAGE
exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sglang) MODE="sglang"; shift ;;
        --full) MODE="full"; shift ;;
        --venv) VENV_DIR="$2"; shift 2 ;;
        --torch-index) TORCH_INDEX="$2"; shift 2 ;;
        --skip-apt|--skip-system-packages) SKIP_SYS_PKGS=1; shift ;;
        --with-pcm)        WITH_PCM=1; shift ;;
        --pcm-ref)         PCM_REF="$2"; shift 2 ;;
        --pcm-prefix)      PCM_PREFIX="$2"; shift 2 ;;
        --skip-venv) SKIP_VENV=1; shift ;;
        --with-dram-deps) INSTALL_DRAM_DEPS=1; shift ;;
        --dram-tool) DRAM_DEPS_TOOL="$2"; shift 2 ;;
        --build-intel-pcm) BUILD_INTEL_PCM=1; shift ;;
        --amduprof-installer) AMDUPROF_INSTALLER="$2"; shift 2 ;;
        --amduprof-url) AMDUPROF_URL="$2"; shift 2 ;;
        --no) ASSUME_YES=0; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --help|-h) usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$SCRIPT_DIR"

SUDO=""
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    SUDO="sudo"
fi

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "+ $*"
    else
        "$@"
    fi
}

detect_arch() {
    local a
    a="$(uname -m 2>/dev/null || echo unknown)"
    case "$a" in
        x86_64|amd64) echo "x86_64" ;;
        aarch64|arm64) echo "aarch64" ;;
        ppc64le) echo "ppc64le" ;;
        *) echo "$a" ;;
    esac
}

detect_cpu_vendor() {
    local cpu
    cpu="$(tr '[:upper:]' '[:lower:]' < /proc/cpuinfo 2>/dev/null || true)"
    if grep -qi "authenticamd" <<<"$cpu"; then echo "amd"; return; fi
    if grep -qi "genuineintel" <<<"$cpu"; then echo "intel"; return; fi
    echo "unknown"
}

load_os_release() {
    OS_ID="unknown"; OS_LIKE=""; OS_VERSION_ID=""
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_LIKE="${ID_LIKE:-}"
        OS_VERSION_ID="${VERSION_ID:-}"
    fi
}

detect_pm() {
    if command -v apt-get >/dev/null 2>&1; then echo apt; return; fi
    if command -v dnf >/dev/null 2>&1; then echo dnf; return; fi
    if command -v yum >/dev/null 2>&1; then echo yum; return; fi
    if command -v zypper >/dev/null 2>&1; then echo zypper; return; fi
    if command -v pacman >/dev/null 2>&1; then echo pacman; return; fi
    echo unknown
}

pm_update_once=0
pm_install_group() {
    local packages=("$@")
    [[ "${#packages[@]}" -eq 0 ]] && return 0

    case "$PM" in
        apt)
            if [[ "$pm_update_once" -eq 0 ]]; then
                run $SUDO apt-get update -qq || true
                pm_update_once=1
            fi
            if [[ "$ASSUME_YES" -eq 1 ]]; then
                run $SUDO apt-get install -y --no-install-recommends "${packages[@]}"
            else
                run $SUDO apt-get install --no-install-recommends "${packages[@]}"
            fi
            ;;
        dnf)
            if [[ "$ASSUME_YES" -eq 1 ]]; then run $SUDO dnf install -y "${packages[@]}"; else run $SUDO dnf install "${packages[@]}"; fi
            ;;
        yum)
            if [[ "$ASSUME_YES" -eq 1 ]]; then run $SUDO yum install -y "${packages[@]}"; else run $SUDO yum install "${packages[@]}"; fi
            ;;
        zypper)
            if [[ "$ASSUME_YES" -eq 1 ]]; then run $SUDO zypper --non-interactive install "${packages[@]}"; else run $SUDO zypper install "${packages[@]}"; fi
            ;;
        pacman)
            if [[ "$ASSUME_YES" -eq 1 ]]; then run $SUDO pacman -Sy --needed --noconfirm "${packages[@]}"; else run $SUDO pacman -Sy --needed "${packages[@]}"; fi
            ;;
        *)
            warn "No supported package manager detected; install manually: ${packages[*]}"
            return 1
            ;;
    esac
}

pm_install_best_effort() {
    local p
    for p in "$@"; do
        info "Installing/checking OS package: $p"
        if ! pm_install_group "$p"; then
            warn "Could not install '$p' via $PM; continuing"
        fi
    done
}

install_system_packages() {
    section "System packages"

    if [[ "$SKIP_SYS_PKGS" -eq 1 ]]; then
        warn "Skipping OS package installation."
        return 0
    fi

    local pkgs=()
    local perf_pkgs=()
    local bpf_pkgs=()
    local build_pkgs=()

    case "$PM" in
        apt)
            pkgs=(python3-dev python3-venv python3-pip jq curl wget ca-certificates nvme-cli sysstat blktrace pciutils procps kmod numactl)
            build_pkgs=(build-essential pkg-config git)
            bpf_pkgs=(bpfcc-tools bpftrace)
            perf_pkgs=(linux-tools-"$(uname -r)" linux-tools-generic linux-perf)
            ;;
        dnf|yum)
            pkgs=(python3-devel python3-pip jq curl wget ca-certificates nvme-cli sysstat blktrace pciutils procps-ng kmod numactl)
            build_pkgs=(gcc gcc-c++ make pkgconf-pkg-config git)
            bpf_pkgs=(bcc-tools bpftrace)
            perf_pkgs=(perf kernel-tools)
            ;;
        zypper)
            pkgs=(python3-devel python3-pip jq curl wget ca-certificates nvme-cli sysstat blktrace pciutils procps kmod numactl)
            build_pkgs=(gcc gcc-c++ make pkg-config git)
            bpf_pkgs=(bcc-tools bpftrace)
            perf_pkgs=(perf)
            ;;
        pacman)
            pkgs=(python python-pip jq curl wget ca-certificates nvme-cli sysstat blktrace pciutils procps-ng kmod numactl)
            build_pkgs=(base-devel pkgconf git)
            bpf_pkgs=(bpftrace bcc)
            perf_pkgs=(linux-tools)
            ;;
        *)
            warn "Unsupported package manager. Install Python dev/venv, nvme-cli, sysstat, blktrace, bpf tools, perf, jq/curl/wget manually."
            return 0
            ;;
    esac

    pm_install_best_effort "${pkgs[@]}"
    pm_install_best_effort "${build_pkgs[@]}"

    # BPF packages are not consistently available on every architecture/release.
    # Install best-effort, but never fail the AMOprof Python install because BPF
    # tooling is optional and can be added later.
    if [[ "$ARCH" == "x86_64" || "$ARCH" == "aarch64" ]]; then
        pm_install_best_effort "${bpf_pkgs[@]}"
    else
        warn "Skipping automatic BPF packages on architecture '$ARCH'; install biosnoop/bpftrace manually if needed."
    fi

    # perf package names vary; install one by one best-effort.
    pm_install_best_effort "${perf_pkgs[@]}"

    if command -v nvidia-smi >/dev/null 2>&1; then
        ok "nvidia-smi found: $(command -v nvidia-smi)"
    else
        warn "nvidia-smi not found. GPU/HBM collection requires NVIDIA drivers/tools on the target node."
    fi
}

section "Preflight"
if [[ ! -f "$PACKAGE_DIR/pyproject.toml" ]]; then
    error "pyproject.toml not found in $PACKAGE_DIR. Run install.sh from the package root."
    exit 1
fi

load_os_release
PM="$(detect_pm)"
ARCH="$(detect_arch)"
CPU_VENDOR="$(detect_cpu_vendor)"

# The minimum is pyproject.toml's requires-python, read rather than repeated:
# this check said 3.10 while the package required 3.12, so on 3.10/3.11 the
# preflight passed and pip then refused the install half-way through.
REQ_PY="$(sed -n -E 's/^requires-python *= *"[^0-9]*([0-9]+\.[0-9]+).*/\1/p' \
          "$PACKAGE_DIR/pyproject.toml" | head -1)"
REQ_PY="${REQ_PY:-3.12}"
REQ_MAJOR="${REQ_PY%%.*}"; REQ_MINOR="${REQ_PY##*.}"

PY="$(command -v python3 || true)"
if [[ -z "$PY" ]]; then
    error "python3 not found. Install Python $REQ_PY+ first."
    exit 1
fi
PY_VER="$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER##*.}"
if [[ "$PY_MAJOR" -lt "$REQ_MAJOR" || ( "$PY_MAJOR" -eq "$REQ_MAJOR" && "$PY_MINOR" -lt "$REQ_MINOR" ) ]]; then
    error "Python $REQ_PY+ required (pyproject.toml requires-python), found $PY_VER"
    exit 1
fi

ok "Python $PY_VER"
echo "Architecture   : $ARCH"
echo "CPU vendor     : $CPU_VENDOR"
echo "OS             : $OS_ID $OS_VERSION_ID (like: $OS_LIKE)"
echo "Package manager: $PM"
echo "Install mode   : $MODE"

install_system_packages

if [[ "$INSTALL_DRAM_DEPS" -eq 1 ]]; then
    section "DRAM PMU dependencies"
    DRAM_SCRIPT="$PACKAGE_DIR/scripts/install_dram_deps.sh"
    if [[ ! -f "$DRAM_SCRIPT" ]]; then
        error "DRAM dependency installer not found: $DRAM_SCRIPT"
        exit 1
    fi
    DRAM_ARGS=(--dram-tool "$DRAM_DEPS_TOOL")
    [[ "$BUILD_INTEL_PCM" -eq 1 ]] && DRAM_ARGS+=(--build-intel-pcm)
    [[ -n "$AMDUPROF_INSTALLER" ]] && DRAM_ARGS+=(--amduprof-installer "$AMDUPROF_INSTALLER")
    [[ -n "$AMDUPROF_URL" ]] && DRAM_ARGS+=(--amduprof-url "$AMDUPROF_URL")
    [[ "$ASSUME_YES" -eq 0 ]] && DRAM_ARGS+=(--no)
    [[ "$DRY_RUN" -eq 1 ]] && DRAM_ARGS+=(--dry-run)
    [[ "${EUID:-$(id -u)}" -eq 0 ]] && DRAM_ARGS+=(--no-sudo)
    # Through bash, so a zip or Windows copy that dropped the execute bit
    # still runs it rather than aborting the install.
    bash "$DRAM_SCRIPT" "${DRAM_ARGS[@]}"
else
    warn "Skipping DRAM PMU dependency helper. Use --with-dram-deps for AMD uProf / Intel PCM / perf IMC dependencies."
fi

section "Python virtual environment"
if [[ "$SKIP_VENV" -eq 1 ]]; then
    warn "Installing into the current Python environment."
    PIP="pip3"
else
    if [[ ! -d "$VENV_DIR" ]]; then
        info "Creating venv at $VENV_DIR"
        # A Python without ensurepip (Debian/Ubuntu without pythonX.Y-venv)
        # fails here AFTER creating the directory, and the next run then took
        # the half-built directory for a venv to reuse.  Remove it and say
        # what is missing instead.
        if ! "$PY" -m venv "$VENV_DIR"; then
            rm -rf "$VENV_DIR"
            error "Could not create a virtualenv at $VENV_DIR: python$PY_VER has no venv/ensurepip support."
            error "Install it (Debian/Ubuntu: apt install python${PY_VER}-venv), drop --skip-system-packages so"
            error "this script installs it, or re-run with --skip-venv to use the current environment."
            exit 1
        fi
    elif [[ ! -f "$VENV_DIR/bin/activate" ]]; then
        error "$VENV_DIR exists but is not a usable virtualenv (no bin/activate) -- most likely left by an"
        error "earlier failed attempt. Remove it, or pass a different --venv, and re-run."
        exit 1
    else
        info "Reusing venv at $VENV_DIR"
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    PIP="pip"
    ok "venv active: $VENV_DIR"
fi

$PIP install --quiet --upgrade pip setuptools wheel

section "Core Python dependencies"
CORE_DEPS=(
    "psutil>=5.9"
    "PyYAML>=6.0"
    "rich>=13.0"
    "pandas>=1.5"
    "numpy>=1.24"
    "matplotlib>=3.7"
    "scipy>=1.10"
    "openpyxl>=3.1"
    "requests>=2.28"
    "Pillow>=9.4"
)
$PIP install --quiet "${CORE_DEPS[@]}"
ok "Core Python dependencies installed"

section "Installing AMOprof"
case "$MODE" in
    metrics)
        $PIP install --quiet -e "$PACKAGE_DIR"
        ;;
    sglang)
        $PIP install --quiet --extra-index-url "$TORCH_INDEX" -e "$PACKAGE_DIR[sglang]"
        ;;
    full)
        $PIP install --quiet --extra-index-url "$TORCH_INDEX" -e "$PACKAGE_DIR[sglang]"
        if ! python3 -c "import sweagent" 2>/dev/null; then
            info "Installing sweagent from GitHub"
            $PIP install --quiet "git+https://github.com/SWE-agent/SWE-agent.git"
        fi
        ;;
esac
ok "AMOprof installed"

section "Optional tool checks"
if command -v dcgmi >/dev/null 2>&1; then ok "dcgmi found: $(command -v dcgmi)"; else warn "dcgmi not found; GPU collection will use nvidia-smi when available."; fi
if command -v nsys >/dev/null 2>&1; then ok "nsys found: $(command -v nsys)"; else warn "nsys not found; Nsight Systems collector unavailable."; fi
if command -v blktrace >/dev/null 2>&1 && command -v blkparse >/dev/null 2>&1; then ok "blktrace + blkparse available"; else warn "blktrace/blkparse missing; request-level L3 storage charts will be empty."; fi
if command -v biosnoop-bpfcc >/dev/null 2>&1 || command -v biosnoop >/dev/null 2>&1; then ok "biosnoop available"; else warn "biosnoop missing; per-stream storage attribution will be empty."; fi
if command -v nvme >/dev/null 2>&1; then ok "nvme-cli available"; else warn "nvme-cli missing; SMART/endurance fields unavailable."; fi
if command -v AMDuProfPcm >/dev/null 2>&1 || compgen -G '/opt/AMDuProf*/bin/AMDuProfPcm' >/dev/null; then ok "AMDuProfPcm available"; else warn "AMDuProfPcm not found; use scripts/install_dram_deps.sh on AMD systems."; fi
if command -v pcm-memory >/dev/null 2>&1 || [[ -x /usr/local/bin/pcm-memory ]]; then ok "Intel pcm-memory available"; else warn "Intel pcm-memory not found; use scripts/install_dram_deps.sh on Intel systems."; fi

section "Privilege check"
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    ok "Running as root."
elif sudo -n true 2>/dev/null; then
    ok "Passwordless sudo available."
else
    warn "blktrace, biosnoop, perf, and DRAM PMU tools usually require root or passwordless sudo."
fi

section "Verification"
if python3 -c "import amoprof; print('amoprof', amoprof.__version__)"; then
    ok "amoprof import OK"
else
    error "amoprof import failed"
    exit 1
fi

if python3 -c "from amoprof.cli import main"; then
    ok "amoprof CLI import OK"
else
    error "amoprof.cli import failed"
    exit 1
fi

ENTRY="$(command -v amoprof 2>/dev/null || true)"
if [[ -n "$ENTRY" ]]; then
    ok "amoprof CLI: $ENTRY"
else
    warn "amoprof entry point is not on PATH. Activate the virtualenv before use."
fi

section "Intel PCM (DRAM bandwidth)"
# PCM only supports microarchitectures its build was compiled for.  On a newer
# Xeon every pcm-* binary installs and every one exits with "unsupported
# processor" — so the fix is a newer BUILD, not a newer package.  Opt-in,
# because building from source pulls a toolchain and takes a few minutes.
pcm_cpu_vendor() { awk -F: '/^vendor_id/{gsub(/ /,"",$2);print $2;exit}' /proc/cpuinfo 2>/dev/null; }
pcm_build_rejects_cpu() {
    # Any pcm-* utility shares the CPU-support table, so one refusal is
    # enough to know they all refuse.
    local probe
    for probe in pcm-raw pcm-core pcm-numa pcm; do
        if command -v "$probe" >/dev/null 2>&1; then
            "$probe" 2>&1 | grep -qi "unsupported processor" && return 0
            return 1
        fi
    done
    return 1   # nothing installed: not a rejection, just absent
}

if [[ "$WITH_PCM" -eq 1 ]]; then
    if [[ "$(pcm_cpu_vendor)" == "AuthenticAMD" ]]; then
        warn "AMD cpu detected — Intel PCM cannot read AMD memory controllers. Skipping."
        warn "Use --dram-tool amduprof with AMDuProf instead."
    elif command -v pcm-memory >/dev/null 2>&1 && ! pcm_build_rejects_cpu; then
        ok "pcm-memory already installed and supports this CPU: $(command -v pcm-memory)"
    else
        if pcm_build_rejects_cpu; then
            warn "Installed PCM does not support this CPU — building a current one."
        fi
        PCM_SRC="${PCM_PREFIX}/src"
        if [[ "$SKIP_SYS_PKGS" -eq 0 ]]; then
            case "$(detect_pm)" in
                apt) run $SUDO apt-get install -y --no-install-recommends \
                        git cmake g++ make ca-certificates ;;
                dnf|yum) run $SUDO "$(detect_pm)" install -y git cmake gcc-c++ make ;;
                zypper)  run $SUDO zypper --non-interactive install git cmake gcc-c++ make ;;
                pacman)  run $SUDO pacman -S --noconfirm git cmake gcc make ;;
                *)   warn "Unknown package manager; ensure git, cmake, g++ and make are present." ;;
            esac
        fi
        run $SUDO mkdir -p "$PCM_PREFIX"
        run $SUDO chown -R "$(id -u):$(id -g)" "$PCM_PREFIX" 2>/dev/null || true

        PCM_OK=1
        if [[ -d "$PCM_SRC/.git" ]]; then
            info "Updating existing PCM checkout in $PCM_SRC"
            (cd "$PCM_SRC" && git fetch --tags --quiet && git submodule update --init --recursive --quiet) || PCM_OK=0
        else
            # --recursive matters: PCM vendors simdjson as a submodule and the
            # build fails without it.
            info "Cloning intel/pcm into $PCM_SRC"
            git clone --recursive --quiet https://github.com/intel/pcm.git "$PCM_SRC" || PCM_OK=0
        fi
        if [[ "$PCM_OK" -eq 1 && -n "$PCM_REF" ]]; then
            (cd "$PCM_SRC" && git checkout --quiet "$PCM_REF" \
                && git submodule update --init --recursive --quiet) \
                || { warn "Could not check out PCM ref '$PCM_REF'; using default branch."; }
        fi

        if [[ "$PCM_OK" -eq 1 ]]; then
            info "Building PCM (this takes a few minutes)"
            if (cd "$PCM_SRC" && cmake -E make_directory build \
                    && cd build && cmake .. >/dev/null \
                    && cmake --build . --parallel "$(nproc 2>/dev/null || echo 4)" >/dev/null); then
                PCM_BIN="$PCM_SRC/build/bin/pcm-memory"
                if [[ -x "$PCM_BIN" ]]; then
                    ok "Built pcm-memory: $PCM_BIN"
                    if "$PCM_BIN" -h 2>&1 | grep -qi "unsupported processor"; then
                        error "The freshly built PCM still refuses this CPU."
                        warn  "Try a newer --pcm-ref, or use --dram-tool perf-imc."
                    else
                        ok "pcm-memory supports this CPU."
                        echo "AMOPROF_INTEL_PCM_MEMORY_BIN=$PCM_BIN" >> "$SCRIPT_DIR/.amoprof-pcm.env"
                        ok "Recorded path in $SCRIPT_DIR/.amoprof-pcm.env"
                        info "Add to your amoprof env file:"
                        info "  AMOPROF_EXTRA_ARGS=\"... --enable-dram --dram-tool intel-pcm --intel-pcm-memory-bin $PCM_BIN\""
                    fi
                else
                    error "Build finished but pcm-memory is missing from build/bin."
                fi
            else
                error "PCM build failed. Build it manually, or use --dram-tool perf-imc."
            fi
        else
            error "Could not fetch PCM sources (network or git unavailable)."
            warn  "Download a release from https://github.com/intel/pcm/releases and build it,"
            warn  "or use --dram-tool perf-imc which needs no external tool."
        fi
    fi
else
    if pcm_build_rejects_cpu; then
        warn "Installed Intel PCM does not support this CPU (every pcm-* tool refuses it)."
        warn "Re-run with --with-pcm to build a current one, or use --dram-tool perf-imc."
    fi
fi

section "Collector readiness"
# Presence of a binary is not readiness: Intel PCM installs fine and returns
# nothing without MSR access; iostat is on PATH but reports zeros for the
# wrong device.  Both look identical from Prometheus hours later — the gauges
# appear carrying only collection metadata and the charts are empty.  So run
# each collector here and report what actually came back.
if [[ -f "$SCRIPT_DIR/check_collectors.py" ]]; then
    if python3 "$SCRIPT_DIR/check_collectors.py" --seconds 2 \
            ${AMOPROF_SSD_DEVICE:+--ssd-device "$AMOPROF_SSD_DEVICE"}; then
        ok "All checked collectors produced data."
    else
        warn "Some collectors will produce no data on this host (see above)."
        warn "amoprof will still install and run; the affected charts will be empty."
        warn "Re-run any time with: python3 $SCRIPT_DIR/check_collectors.py"
    fi
else
    warn "check_collectors.py not found; skipping collector readiness checks."
fi

section "Installation complete"
if [[ "$SKIP_VENV" -eq 1 ]]; then
    VENV_SUMMARY="current Python environment"
else
    VENV_SUMMARY="$VENV_DIR"
fi

cat <<EOF_SUMMARY
Mode        : $MODE
Virtualenv  : $VENV_SUMMARY
Package dir : $PACKAGE_DIR
Architecture: $ARCH
CPU vendor  : $CPU_VENDOR
OS/PM       : $OS_ID $OS_VERSION_ID / $PM

Next steps:
  source $VENV_DIR/bin/activate
  amoprof --version

Example collect:
  sudo amoprof collect \\
    --sglang-host 127.0.0.1 --sglang-port 30000 \\
    --ssd-device /dev/nvme2n1 --hicache-path /mnt/sglang_hicache \\
    --duration-s 900 --interval-s 1 \\
    --enable-dram --dram-tool auto \\
    --enable-blktrace --enable-biosnoop \\
    --setup-details setup_details_sample.json \\
    --label my-run

Example analyze:
  amoprof analyze --run-dir ./amoprof_results/metrics_run_YYYYMMDD_HHMMSS \\
    --combined-report --interactive-report --prom-rate-window 5m
EOF_SUMMARY
