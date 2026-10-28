#!/usr/bin/env bash
# Repository-wide build entry point for the Cognos stack.
#
# Usage:
#   ./build.sh [<component>... | all | amo-prof] [--os <os>|all] [--native]
#              [-t] [-c] [--mode local|ci]
#   ./build.sh --plan [--base <ref>] [--keys] [--format text|json|github-matrix]
#   ./build.sh -h | --help
#
# Components: core mgmt-fw cxl slat ras me node sapp (default: these 8), and
# amo-prof (only when named).
#
#   --plan          print what a change selects (ci/scripts/plan.sh), for the
#                   changes from the merge base of --base (default origin/main)
#                   to HEAD
#   --base <ref>    base of --plan
#   --format <fmt>  output of --plan: text (default), json or github-matrix
#   --keys          add each component/OS cache key to --plan (later phase)
#   --os <os>|all   target OS (later phase)
#   --native        build on this host instead of in the component image
#                   (later phase)
#   -t              build and run the unit tests (later phase)
#   -c              remove build/ (later phase)
#   --mode local|ci (later phase)
#
# Only --plan and --help work yet; every other mode prints 'not implemented
# yet (later phase)' and exits 2.
# Exit: 0 success, 1 failure, 2 usage error or not implemented yet.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ci/lib/selection.sh
source "${REPO_ROOT}/ci/lib/selection.sh"

KNOWN_COMPONENTS=("${SEL_PACKAGE_COMPONENTS[@]}" amo-prof)

usage() {
  sed -n '2,28s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
}

not_implemented() {
  log "$1: not implemented yet (later phase)"
  exit 2
}

plan=0
keys=0
base=origin/main
format=text
later=()
components=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --plan)
      plan=1
      shift
      ;;
    --base | --format | --os | --mode)
      [[ $# -ge 2 ]] || usage_error "$1 needs a value"
      case "$1" in
        --base) base="$2" ;;
        --format) format="$2" ;;
        *) later+=("$1 $2") ;;
      esac
      shift 2
      ;;
    --keys)
      keys=1
      shift
      ;;
    --native | -t | -c)
      later+=("$1")
      shift
      ;;
    -*) usage_error "unknown option '$1' (see --help)" ;;
    *)
      if [[ "$1" != all ]] && ! printf '%s\n' "${KNOWN_COMPONENTS[@]}" | grep -qxF -- "$1"; then
        usage_error "unknown component '$1' (known: ${KNOWN_COMPONENTS[*]} or all)"
      fi
      components+=("$1")
      shift
      ;;
  esac
done

if [[ "${plan}" -eq 1 ]]; then
  [[ "${#components[@]}" -eq 0 ]] || usage_error "--plan takes no components"
  [[ "${#later[@]}" -eq 0 ]] || usage_error "--plan cannot be combined with: ${later[*]}"
  [[ "${keys}" -eq 0 ]] || not_implemented "--keys"
  cd "${REPO_ROOT}"
  exec bash "${REPO_ROOT}/ci/scripts/plan.sh" --base "${base}" --head HEAD --format "${format}"
fi

if [[ "${keys}" -eq 1 ]]; then
  usage_error "--keys needs --plan"
fi
not_implemented "building components"
