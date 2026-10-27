#!/usr/bin/env bash
# Build the amoprof wheel into dist/ (or $1) and check what went into it.
#
#   scripts/build_wheel.sh            # -> dist/amoprof-<version>-py3-none-any.whl
#   pip install dist/amoprof-*.whl    # then: amoprof --version
#
# Uses pip's PEP 517 build (isolated, from pyproject.toml), so nothing beyond
# pip is needed. install.sh remains the way to install from a source tree;
# both install the same package and the same dependencies.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-dist}"
PY="${PYTHON:-python3}"

rm -rf build "$OUT" ./*.egg-info
"$PY" -m pip wheel --no-deps --wheel-dir "$OUT" . >/dev/null
WHL=$(ls "$OUT"/amoprof-*.whl)
echo "built: $WHL"

# A wheel that builds but is missing a module, the report data, the console
# script or the right version installs cleanly and fails later on the
# target host. Check it here instead.
"$PY" - "$WHL" <<'PY'
import re, sys, zipfile
whl = sys.argv[1]
names = set(zipfile.ZipFile(whl).namelist())
src_ver = re.search(r"__version__\s*=\s*'([^']+)'", open("amoprof/__init__.py").read()).group(1)
must = ["amoprof/__init__.py", "amoprof/cli.py", "amoprof/comparator.py",
        "amoprof/service.py", "amoprof/server_metrics.py",
        "amoprof/collectors/__init__.py", "amoprof/layers/__init__.py",
        "amoprof/report/combined.py", "amoprof/report/amoprof.py",
        "amoprof/report/metric_kernels.py", "amoprof/report/requirements.txt",
        "amoprof/dashboard/concurrency_sweep.html"]
missing = [m for m in must if m not in names]
dist = next(n.split("/")[0] for n in names if n.endswith(".dist-info/METADATA"))
meta = zipfile.ZipFile(whl).read(f"{dist}/METADATA").decode()
eps = zipfile.ZipFile(whl).read(f"{dist}/entry_points.txt").decode()
errs = []
if missing:
    errs.append(f"missing from the wheel: {missing}")
if f"Version: {src_ver}" not in meta:
    errs.append(f"wheel version does not match amoprof/__init__.py ({src_ver})")
if "amoprof = amoprof.cli:main" not in eps:
    errs.append("console script 'amoprof' is not declared")
if any(n.startswith(("tests/", "amoprof/tests/")) for n in names):
    errs.append("test files were packaged")
if errs:
    sys.exit("wheel check FAILED:\n  " + "\n  ".join(errs))
print(f"wheel check OK: version {src_ver}, {len(names)} files, console script amoprof")
PY
