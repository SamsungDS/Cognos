#!/usr/bin/env bash
# Run every test the repository ships, the way each one is written.
#
# tests/ holds two kinds of file: pytest modules (they define test_*
# functions) and standalone scripts (they print PASS/FAIL and exit non-zero
# on failure). `pytest tests/` collects nothing from the scripts and reports
# success without running them, so each kind is run its own way here.
# validate_math.py runs last.
#
#   scripts/run_tests.sh              # exit 0 only if everything passed
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$PWD"

# Failing on main before 1.78.0 and unchanged by it; listed here so they are
# visible, and deselected so they do not mask new failures. Remove an entry
# once its test is fixed.
KNOWN_FAILURES=()

fail=0
pytest_files=()
script_files=()
for f in tests/test_*.py; do
  if grep -q -E '^def test_' "$f"; then pytest_files+=("$f"); else script_files+=("$f"); fi
done

echo "== pytest: ${#pytest_files[@]} files + amoprof/tests (${#KNOWN_FAILURES[@]} known failures deselected)"
deselect=()
for k in ${KNOWN_FAILURES[@]+"${KNOWN_FAILURES[@]}"}; do deselect+=(--deselect "$k"); done
"$PY" -m pytest -q "${pytest_files[@]}" amoprof/tests ${deselect[@]+"${deselect[@]}"} || fail=1

echo "== script tests: ${#script_files[@]} files"
log=$(mktemp)
for f in "${script_files[@]}"; do
  if "$PY" "$f" >"$log" 2>&1; then
    echo "  ok    $f  ($(tail -1 "$log"))"
  else
    echo "  FAIL  $f"; tail -15 "$log" | sed 's/^/        /'; fail=1
  fi
done

echo "== validate_math.py"
if "$PY" validate_math.py >"$log" 2>&1; then
  echo "  ok    $(tail -1 "$log")"
else
  grep -E '^\s+FAIL|Traceback' "$log" | head -20 | sed 's/^/        /'
  tail -1 "$log"; fail=1
fi
rm -f "$log"
find . -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

[ "$fail" = 0 ] && echo "ALL TESTS PASSED" || echo "TESTS FAILED"
exit "$fail"
