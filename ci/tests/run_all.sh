#!/usr/bin/env bash
# Run every ci/tests/*_test.sh. Offline; needs bash, git, jq and python3 (with
# the yaml module). Exit 1 if any test file fails.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failed=()
for t in "${TESTS_DIR}"/*_test.sh; do
  printf '=== %s\n' "$(basename "${t}")"
  if ! bash "${t}"; then
    failed+=("$(basename "${t}")")
  fi
done
if [[ "${#failed[@]}" -gt 0 ]]; then
  printf 'FAILED: %s\n' "${failed[*]}" >&2
  exit 1
fi
printf 'all ci tests passed\n'
