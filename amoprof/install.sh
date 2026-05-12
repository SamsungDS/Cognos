#!/usr/bin/env bash
# =============================================================================
# AMOprof — AI Memory & IO Profiler
# Dependency installer
# =============================================================================
# Usage:
#   chmod +x install.sh && ./install.sh          # auto-detect Python
#   ./install.sh --python python3.11             # specific interpreter
#   ./install.sh --venv                          # install into a virtualenv
#   ./install.sh --venv --venv-dir /opt/amoprof  # custom venv location
#   ./install.sh --user                          # pip install --user
#   ./install.sh --check                         # check only, no install
# =============================================================================

set -euo pipefail

# ── defaults ─────────────────────────────────────────────────────────────────
PYTHON=""
USE_VENV=0
VENV_DIR="./amoprof_env"
USER_INSTALL=0
CHECK_ONLY=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)     PYTHON="$2";            shift 2 ;;
        --venv)       USE_VENV=1;             shift   ;;
        --venv-dir)   VENV_DIR="$2"; USE_VENV=1; shift 2 ;;
        --user)       USER_INSTALL=1;         shift   ;;
        --check)      CHECK_ONLY=1;           shift   ;;
        -h|--help)
            sed -n '3,12p' "$0" | sed 's/^# //'
            exit 0 ;;
        *) error "Unknown option: $1"; exit 1 ;;
    esac
done

header "========================================"
header " AMOprof — Dependency Installer"
header "========================================"

# ── find Python ──────────────────────────────────────────────────────────────
if [[ -z "$PYTHON" ]]; then
    for candidate in python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" &>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON" ]]; then
    error "No Python interpreter found. Install Python >= 3.10 first."
    exit 1
fi

PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_FULL=$("$PYTHON" --version 2>&1)
info "Python: $PYTHON_FULL  ($PYTHON)"

# Check minimum version
MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
if [[ "$MAJOR" -lt 3 ]] || { [[ "$MAJOR" -eq 3 ]] && [[ "$MINOR" -lt 10 ]]; }; then
    error "Python >= 3.10 required (found $PYTHON_VERSION)"
    exit 1
fi
ok "Python version $PYTHON_VERSION OK"

# ── check requirements file ───────────────────────────────────────────────────
if [[ ! -f "$REQ_FILE" ]]; then
    error "requirements.txt not found at: $REQ_FILE"
    exit 1
fi
info "Requirements: $REQ_FILE"

# ── check-only mode ──────────────────────────────────────────────────────────
if [[ "$CHECK_ONLY" -eq 1 ]]; then
    header "── Checking installed packages ──────────────────"
    MISSING=()
    while IFS= read -r line; do
        [[ "$line" =~ ^#|^$ ]] && continue
        PKG=$(echo "$line" | sed 's/[>=<!=].*//' | tr -d ' ')
        if "$PYTHON" -c "import importlib; importlib.import_module('$PKG')" 2>/dev/null; then
            VER=$("$PYTHON" -c "import importlib.metadata; print(importlib.metadata.version('$PKG'))" 2>/dev/null || echo "?")
            ok "$PKG  (installed: $VER)"
        else
            # Handle import name ≠ package name
            IMPORT_NAME="$PKG"
            case "$PKG" in
                Pillow)    IMPORT_NAME="PIL"      ;;
                scikit-learn) IMPORT_NAME="sklearn" ;;
            esac
            if "$PYTHON" -c "import $IMPORT_NAME" 2>/dev/null; then
                VER=$("$PYTHON" -c "import importlib.metadata; print(importlib.metadata.version('$PKG'))" 2>/dev/null || echo "?")
                ok "$PKG  (installed: $VER)"
            else
                warn "$PKG  MISSING"
                MISSING+=("$PKG")
            fi
        fi
    done < "$REQ_FILE"
    if [[ ${#MISSING[@]} -gt 0 ]]; then
        echo ""
        warn "${#MISSING[@]} package(s) missing: ${MISSING[*]}"
        echo "Run ./install.sh to install them."
        exit 1
    else
        echo ""
        ok "All dependencies satisfied."
    fi
    exit 0
fi

# ── set up virtualenv (optional) ─────────────────────────────────────────────
PIP_CMD=("$PYTHON" -m pip)

if [[ "$USE_VENV" -eq 1 ]]; then
    header "── Creating virtualenv: $VENV_DIR ──────────────────"
    if [[ ! -d "$VENV_DIR" ]]; then
        "$PYTHON" -m venv "$VENV_DIR"
        ok "Created virtualenv at $VENV_DIR"
    else
        info "Virtualenv already exists at $VENV_DIR"
    fi
    # Activate
    if [[ -f "$VENV_DIR/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
        PYTHON="python"
        PIP_CMD=("python" -m pip)
        ok "Virtualenv activated"
    elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
        source "$VENV_DIR/Scripts/activate"
        PYTHON="python"
        PIP_CMD=("python" -m pip)
        ok "Virtualenv activated (Windows/MINGW)"
    fi
fi

# ── upgrade pip ──────────────────────────────────────────────────────────────
header "── Upgrading pip ────────────────────────────────────"
"${PIP_CMD[@]}" install --quiet --upgrade pip
ok "pip upgraded"

# ── install dependencies ──────────────────────────────────────────────────────
header "── Installing AMOprof dependencies ──────────────────"

PIP_ARGS=(install --quiet)
[[ "$USER_INSTALL" -eq 1 ]] && PIP_ARGS+=(--user)

# Check for DGX / restricted environment (no internet access)
if ! "${PIP_CMD[@]}" install --quiet --dry-run --ignore-installed requests &>/dev/null; then
    warn "Network install may not be available. Trying with --break-system-packages fallback..."
    PIP_ARGS+=(--break-system-packages)
fi

"${PIP_CMD[@]}" "${PIP_ARGS[@]}" -r "$REQ_FILE"
ok "All dependencies installed"

# ── verify imports ────────────────────────────────────────────────────────────
header "── Verifying imports ────────────────────────────────"
VERIFY_SCRIPT=$(cat << 'PYEOF'
import sys
results = []
checks = [
    ("matplotlib",  "matplotlib",         "plt"),
    ("numpy",       "numpy",              "np"),
    ("pandas",      "pandas",             "pd"),
    ("openpyxl",    "openpyxl",           "Workbook"),
    ("requests",    "requests",           "get"),
    ("scipy",       "scipy.stats",        "pearsonr"),
    ("Pillow",      "PIL.Image",          "open"),
]
for pkg, mod, attr in checks:
    try:
        m = __import__(mod, fromlist=[attr])
        ver = getattr(m, '__version__', None)
        if ver is None:
            import importlib.metadata
            ver = importlib.metadata.version(pkg)
        results.append((True,  pkg, ver))
    except Exception as e:
        results.append((False, pkg, str(e)))

ok_count = sum(1 for r in results if r[0])
for ok, pkg, info in results:
    mark = "✅" if ok else "❌"
    print(f"  {mark}  {pkg:<15} {info}")

print(f"\n  {ok_count}/{len(results)} imports OK")
if ok_count < len(results):
    sys.exit(1)
PYEOF
)
"$PYTHON" -c "$VERIFY_SCRIPT"

# ── done ──────────────────────────────────────────────────────────────────────
header "========================================"
ok "AMOprof is ready to use!"
header "========================================"
echo ""
echo "  Run the profiler:"
if [[ "$USE_VENV" -eq 1 ]]; then
    echo "    source $VENV_DIR/bin/activate"
fi
echo "    python3 amoprof.py --help"
echo ""
echo "  Example:"
echo "    python3 amoprof.py \\"
echo "      --raw metrics_run_*/raw \\"
echo "      --blktrace-analysis-dir kvssd_bltrace_analysis_2/ \\"
echo "      --iostat iostat_xm_1.txt \\"
echo "      --output report.html --excel"
echo ""
