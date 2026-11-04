#!/usr/bin/env bash
# Tests of the scripts the pipeline uses: file modes, shellcheck, the unit tests, and with --smoke the
# read-only smoke tests against this GitLab (CI only). Run from anywhere in the repository.
#
# Usage: gitlab/scripts/tests/run.sh [--smoke]
#
# Needs bash, git, python3, shellcheck and dpkg-deb. The unit tests need no network: they use a fake GitLab API,
# throwaway git repositories and stand-in commands (see helpers.py).
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$HERE/../../.." && pwd)
cd "$ROOT"

# The scripts the pipeline runs directly must be executable in git, not just on this disk.
EXECUTABLES=(build.sh ci/version.sh ci/image.sh ci/dev-set.py ci/compat-check.sh gitlab/scripts/api.py
    deploy/scripts/fetch-packages.py deploy/scripts/test-deploy.sh gitlab/scripts/tests/run.sh
    gitlab/scripts/tests/smoke.sh)

echo "== file modes"
bad=0
for f in "${EXECUTABLES[@]}"; do
    mode=$(git ls-files -s -- "$f" | cut -d' ' -f1)
    if [[ $mode != 100755 ]]; then
        echo "not executable in git (${mode:-not tracked}): $f"
        bad=1
    fi
done
[[ $bad -eq 0 ]] || exit 1

echo "== shellcheck"
shellcheck build.sh ci/*.sh gitlab/scripts/tests/*.sh deploy/scripts/test-deploy.sh

echo "== unit tests"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover --buffer \
    --start-directory "$HERE" --top-level-directory "$HERE" --pattern 'test_*.py'

if [[ ${1:-} == --smoke ]]; then
    echo "== smoke tests"
    "$HERE/smoke.sh"
fi
