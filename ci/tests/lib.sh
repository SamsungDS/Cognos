#!/usr/bin/env bash
# Helpers for the ci/ tests. Sourced, never executed.
#
# Tests build their fixture repositories in a temporary directory at run time
# and never touch the repository under test. Git runs isolated from the
# user's and the system's git configuration.

# shellcheck source=ci/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

T_PASS=0
T_FAIL=0
T_TMP="$(mktemp -d)"
trap 'rm -rf "${T_TMP}"' EXIT

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME=ci-test GIT_AUTHOR_EMAIL=ci-test@example.invalid
export GIT_COMMITTER_NAME=ci-test GIT_COMMITTER_EMAIL=ci-test@example.invalid
# Tests must not inherit a real pipeline's SCM state.
unset SCM_SHA SCM_BEFORE_SHA SCM_MR_DIFF_BASE_SHA SCM_SOURCE_BRANCH \
  SCM_TARGET_BRANCH SCM_SOURCE_IS_FORK SCM_EVENT SCM_REF SCM_TAG SCM_PIPELINE_URL \
  MONOREPO_OWNS_COMPONENTS

# t_ok <name> / t_fail <name> <details...>: record a result.
t_ok() {
  T_PASS=$((T_PASS + 1))
  printf 'ok    %s\n' "$1"
}

t_fail() {
  local name="$1"
  shift
  T_FAIL=$((T_FAIL + 1))
  printf 'FAIL  %s\n' "${name}"
  local d
  for d in "$@"; do
    printf '      %s\n' "${d}"
  done
}

# t_eq <name> <expected> <actual>
t_eq() {
  if [[ "$2" == "$3" ]]; then
    t_ok "$1"
  else
    t_fail "$1" "expected: $2" "actual:   $3"
  fi
}

# t_done: print the summary; exit 1 if anything failed.
t_done() {
  printf '%s: %d passed, %d failed\n' "$(basename "$0")" "${T_PASS}" "${T_FAIL}"
  [[ "${T_FAIL}" -eq 0 ]]
}

# t_repo <dir>: create an empty repository with branch main.
t_repo() {
  mkdir -p "$1"
  git -c init.defaultBranch=main -C "$1" init -q
}

# t_write <path> [content]: create or change a file (parents created).
t_write() {
  mkdir -p "$(dirname "$1")"
  printf '%s\n' "${2:-change $RANDOM}" >> "$1"
}

# t_commit <message>: commit everything in the current repository.
t_commit() {
  git add -A
  git commit -q --no-verify -m "$1"
}
