#!/usr/bin/env bash
# Repository guards, run by the plan job. Every guard that fails prints its
# reason and the offending paths; the script exits 1 if any guard failed.
#
# Usage: guards.sh [--base <ref>] [--head <ref>]
#
# (a) Transition guard (merge requests): while the individual repositories
#     still own the components, a merge request may not change components/**,
#     apps/sapp/** or profilers/amo-prof/**. Exempt: source branches sync/*
#     and backport/* of this project (not of a fork). Lifted by
#     MONOREPO_OWNS_COMPONENTS=true.
# (b) VERSION and CHANGELOG.md guard (merge requests): into main, only
#     release-bot/next of this project (not of a fork) may change them; into
#     release/*, nobody may change VERSION.
# (c) release-bot/next guard (merge requests from release-bot/next): only
#     VERSION and CHANGELOG.md may change, and the new VERSION (X.Y) must be
#     greater than the latest release line (highest vX.Y.Z tag, or VERSION at
#     the merge base).
# (d) Conflict-marker guard (any diff): no added line may start with a git
#     conflict marker ('<<<<<<<' or '>>>>>>>' followed by a space, a carriage
#     return or the end of the line).
#
# The exemptions trust the branch name; the project must protect those
# branches (see docs/ci.md, 'Project settings this CI relies on').
#
# Inputs: SCM_EVENT, SCM_SOURCE_BRANCH, SCM_TARGET_BRANCH, SCM_SOURCE_IS_FORK,
# the range variables of ci/lib/selection.sh (see plan.sh) and
# MONOREPO_OWNS_COMPONENTS.
# Exit: 0 all guards pass, 1 a guard failed, 2 usage error.
set -euo pipefail

# shellcheck source=ci/lib/selection.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/selection.sh"

usage() {
  sed -n '2,31s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
}

base=""
head=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      [[ $# -ge 2 ]] || usage_error "--base needs a value"
      base="$2"
      shift 2
      ;;
    --head)
      [[ $# -ge 2 ]] || usage_error "--head needs a value"
      head="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) usage_error "unknown argument '$1' (see --help)" ;;
  esac
done

require_cmd git
git rev-parse --git-dir > /dev/null 2>&1 || die "not inside a git repository: $(pwd)"

TRANSITION_PREFIXES=(components/ apps/sapp/ profilers/amo-prof/)
RELEASE_BOT_BRANCH=release-bot/next
VERSION_RE='^[0-9]+\.[0-9]+$'
# A carriage return is allowed after the marker, for files with CRLF endings.
CONFLICT_RE='^\+(<{7}|>{7})( |'$'\r''|$)'

event="${SCM_EVENT:-}"
source_branch="${SCM_SOURCE_BRANCH:-}"
target_branch="${SCM_TARGET_BRANCH:-}"
# Branch-name exemptions hold only for branches of this project; a fork can
# name its branch anything.
trusted_branch="${source_branch}"
if [[ "${SCM_SOURCE_IS_FORK:-false}" == true ]]; then
  trusted_branch=""
fi
failures=0

fail() {
  local guard="$1" reason="$2"
  shift 2
  failures=$((failures + 1))
  log "GUARD FAILED (${guard}): ${reason}"
  local p
  for p in "$@"; do
    printf '    %s\n' "${p}" >&2
  done
}

pass() {
  log "guard ${1}: ok${2:+ (${2})}"
}

# The event's range. Guards (a) to (c) only make sense on a real merge
# request diff, so an MR whose range cannot be resolved fails loudly.
sel_resolve_range "${base}" "${head}"
changed=()
if [[ "${RANGE_MODE}" == diff ]]; then
  diff_out="$(sel_changed_files)" || die "git diff failed for ${RANGE_MERGE_BASE}..${RANGE_HEAD}"
  if [[ -n "${diff_out}" ]]; then
    mapfile -t changed <<< "${diff_out}"
  fi
elif [[ "${event}" == mr ]]; then
  die "cannot evaluate the merge-request guards: ${RANGE_REASON}"
fi
log "event '${event:-local}', source '${source_branch}'$([[ "${SCM_SOURCE_IS_FORK:-false}" == true ]] && printf ' (fork)'), target '${target_branch}', ${RANGE_REASON}"

has_changed() {
  local want="$1" p
  for p in "${changed[@]+"${changed[@]}"}"; do
    [[ "${p}" == "${want}" ]] && return 0
  done
  return 1
}

# (a) Transition guard.
guard_transition() {
  local p prefix hits=()
  if [[ "${event}" != mr ]]; then
    pass a "not a merge request"
    return 0
  fi
  if [[ "${MONOREPO_OWNS_COMPONENTS:-}" == true ]]; then
    pass a "lifted: MONOREPO_OWNS_COMPONENTS=true"
    return 0
  fi
  case "${trusted_branch}" in
    sync/* | backport/*)
      pass a "exempt source branch ${source_branch}"
      return 0
      ;;
  esac
  for p in "${changed[@]+"${changed[@]}"}"; do
    for prefix in "${TRANSITION_PREFIXES[@]}"; do
      if [[ "${p}" == "${prefix}"* ]]; then
        hits+=("${p}")
        break
      fi
    done
  done
  if [[ "${#hits[@]}" -gt 0 ]]; then
    fail a "components are still owned by their own repositories. Change them there; they reach this repository through the sync/* merge requests. Set MONOREPO_OWNS_COMPONENTS=true only at cut-over. Paths:" "${hits[@]}"
    return 0
  fi
  pass a
}

# (b) VERSION and CHANGELOG.md guard.
guard_version() {
  local hits=() f
  if [[ "${event}" != mr ]]; then
    pass b "not a merge request"
    return 0
  fi
  case "${target_branch}" in
    release/*)
      if has_changed VERSION; then
        fail b "VERSION may not change in a merge request into ${target_branch}. Paths:" VERSION
        return 0
      fi
      ;;
    main)
      if [[ "${trusted_branch}" != "${RELEASE_BOT_BRANCH}" ]]; then
        for f in VERSION CHANGELOG.md; do
          has_changed "${f}" && hits+=("${f}")
        done
        if [[ "${#hits[@]}" -gt 0 ]]; then
          fail b "only the release bot (${RELEASE_BOT_BRANCH}) may change VERSION and CHANGELOG.md in main. Paths:" "${hits[@]}"
          return 0
        fi
      fi
      ;;
  esac
  pass b
}

# latest_release_line: set LATEST_LINE to the highest X.Y among tags vX.Y.Z,
# else to VERSION at the merge base ('' if neither exists), and LATEST_SOURCE
# to where it came from, for the log.
latest_release_line() {
  local tag version
  tag="$(git tag --list 'v[0-9]*' \
    | sed -n 's/^v\([0-9][0-9]*\)\.\([0-9][0-9]*\)\.\([0-9][0-9]*\)$/\1.\2.\3 &/p' \
    | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1 | cut -d' ' -f2)"
  if [[ -n "${tag}" ]]; then
    version="${tag#v}"
    LATEST_LINE="${version%.*}"
    LATEST_SOURCE="tag ${tag}"
  else
    LATEST_LINE="$(git show "${RANGE_MERGE_BASE}:VERSION" 2> /dev/null | tr -d '[:space:]' || true)"
    LATEST_SOURCE="VERSION at ${RANGE_MERGE_BASE:0:12}"
  fi
}

# version_gt <a> <b>: true if X.Y a > X.Y b.
version_gt() {
  local a_major="${1%%.*}" a_minor="${1#*.}" b_major="${2%%.*}" b_minor="${2#*.}"
  ((10#${a_major} > 10#${b_major})) && return 0
  ((10#${a_major} == 10#${b_major} && 10#${a_minor} > 10#${b_minor}))
}

# (c) release-bot/next content guard.
guard_release_bot() {
  local p others=() new latest before="${failures}"
  if [[ "${event}" != mr || "${source_branch}" != "${RELEASE_BOT_BRANCH}" ]]; then
    pass c "not a ${RELEASE_BOT_BRANCH} merge request"
    return 0
  fi
  for p in "${changed[@]+"${changed[@]}"}"; do
    [[ "${p}" == VERSION || "${p}" == CHANGELOG.md ]] || others+=("${p}")
  done
  if [[ "${#others[@]}" -gt 0 ]]; then
    fail c "a ${RELEASE_BOT_BRANCH} merge request may change only VERSION and CHANGELOG.md. Paths:" "${others[@]}"
  fi
  if has_changed VERSION; then
    new="$(git show "${RANGE_HEAD}:VERSION" 2> /dev/null | tr -d '[:space:]' || true)"
    latest_release_line
    latest="${LATEST_LINE}"
    log "latest release line '${latest}' from ${LATEST_SOURCE}"
    if [[ ! "${new}" =~ ${VERSION_RE} ]]; then
      fail c "VERSION must be X.Y, found '${new}'. Paths:" VERSION
    elif [[ -n "${latest}" && ! "${latest}" =~ ${VERSION_RE} ]]; then
      fail c "cannot read the latest release line, found '${latest}'. Paths:" VERSION
    elif [[ -n "${latest}" ]] && ! version_gt "${new}" "${latest}"; then
      fail c "the new VERSION ${new} must be greater than the latest release line ${latest}. Paths:" VERSION
    fi
  fi
  [[ "${failures}" -eq "${before}" ]] && pass c
  return 0
}

# (d) Conflict-marker guard.
guard_conflict_markers() {
  local file="" line hits=() in_header=0 diff_text
  if [[ "${RANGE_MODE}" != diff ]]; then
    pass d "no diff range"
    return 0
  fi
  # The prefixes are forced so that the user's diff.noprefix or
  # diff.mnemonicPrefix cannot hide the file names.
  diff_text="$(git -c core.quotePath=false -c diff.noprefix=false -c diff.mnemonicPrefix=false \
    diff --src-prefix=a/ --dst-prefix=b/ --no-renames --no-ext-diff --no-color -U0 \
    "${RANGE_MERGE_BASE}..${RANGE_HEAD}" --)" \
    || die "git diff failed for ${RANGE_MERGE_BASE}..${RANGE_HEAD}"
  # Header lines run from 'diff --git' to the first hunk ('@@'); only added
  # lines inside hunks are checked. Binary files have no hunks. A marker whose
  # file name could not be read is still reported, never dropped.
  while IFS= read -r line; do
    if [[ "${line}" == "diff --git "* ]]; then
      in_header=1
      file=""
      continue
    fi
    if [[ "${in_header}" -eq 1 ]]; then
      case "${line}" in
        "+++ b/"*) file="${line#+++ b/}" ;;
        "+++ \"b/"*)
          file="${line#+++ \"b/}"
          file="${file%\"}"
          ;;
        "@@"*) in_header=0 ;;
      esac
      continue
    fi
    if [[ "${line}" =~ ${CONFLICT_RE} ]]; then
      [[ -n "${file}" ]] || file="<unknown file>"
      if [[ "${#hits[@]}" -eq 0 || "${hits[-1]}" != "${file}" ]]; then
        hits+=("${file}")
      fi
    fi
  done <<< "${diff_text}"
  if [[ "${#hits[@]}" -gt 0 ]]; then
    fail d "unresolved conflict markers were added. Resolve the conflict and remove the markers. Paths:" "${hits[@]}"
    return 0
  fi
  pass d
}

guard_transition
guard_version
guard_release_bot
guard_conflict_markers

if [[ "${failures}" -gt 0 ]]; then
  die "${failures} guard(s) failed"
fi
log "all guards passed"
