#!/usr/bin/env bash
# The SEL_* and RANGE_* globals are results read by the callers.
# shellcheck disable=SC2034
# Selection helpers: the parser for ci/selection.yml, path matching and the
# change range (base..head) shared by plan.sh and guards.sh. Sourced, never
# executed. SCM-neutral: the range comes from arguments or the SCM_* variables
# set by ci/scm/<scm>.sh (scm_env).

if [[ -n "${_COGNOS_CI_SELECTION_LOADED:-}" ]]; then
  return 0
fi
_COGNOS_CI_SELECTION_LOADED=1

# shellcheck source=ci/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# The 8 package components, in dependency order. A platform hit selects all
# of them. amo-prof and deploy are not package components.
SEL_PACKAGE_COMPONENTS=(core mgmt-fw cxl slat ras me node sapp)
# Every key ci/selection.yml must define, and no others.
SEL_REQUIRED_KEYS=(platform "${SEL_PACKAGE_COMPONENTS[@]}" amo-prof deploy)
SEL_ZERO_SHA_RE='^0+$'
# Results for callers (sel_key_matches, sel_resolve_range).
SEL_MATCH=""
RANGE_MODE="" RANGE_REASON="" RANGE_BASE="" RANGE_MERGE_BASE="" RANGE_HEAD=""

# Filled by sel_load: key -> newline-separated entries; keys in file order.
declare -gA SEL_ENTRIES=()
declare -ga SEL_KEYS=()
# The same entries pre-split for matching: all entries in file order, and per
# key the index of its first entry and the number of entries (a key's
# entries are contiguous).
declare -ga SEL_PATTERNS=()
declare -gA SEL_FIRST=() SEL_COUNT=()

# sel_load <file>: parse ci/selection.yml in its restricted format. Dies on
# any violation, naming the file, the line number and the offending line.
sel_load() {
  local file="$1" line n=0 key="" seen_root=0 entry k
  local -a lines
  [[ -r "${file}" ]] || die "selection file not readable: ${file}"
  mapfile -t lines < "${file}"
  SEL_ENTRIES=()
  SEL_KEYS=()
  SEL_PATTERNS=()
  SEL_FIRST=()
  SEL_COUNT=()
  for line in "${lines[@]}"; do
    n=$((n + 1))
    [[ "${line}" == *$'\r'* ]] && _sel_bad "${file}:${n}" "${line}" "CR line ending"
    [[ "${line}" == *$'\t'* ]] && _sel_bad "${file}:${n}" "${line}" "tab character"
    # Blank lines and full-line comments are allowed anywhere.
    [[ "${line}" =~ ^[[:space:]]*$ ]] && continue
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" =~ [[:space:]]$ ]] && _sel_bad "${file}:${n}" "${line}" "trailing whitespace"
    if [[ "${line}" == ".selection:" ]]; then
      [[ "${seen_root}" -eq 0 ]] || _sel_bad "${file}:${n}" "${line}" "duplicate top-level key"
      seen_root=1
      continue
    fi
    [[ "${seen_root}" -eq 1 ]] || _sel_bad "${file}:${n}" "${line}" "content before or outside the '.selection:' key"
    if [[ "${line}" =~ ^\ \ ([a-z0-9][a-z0-9-]*):$ ]]; then
      key="${BASH_REMATCH[1]}"
      [[ -z "${SEL_ENTRIES[${key}]+x}" ]] || _sel_bad "${file}:${n}" "${line}" "duplicate key '${key}'"
      SEL_ENTRIES["${key}"]=""
      SEL_KEYS+=("${key}")
      SEL_FIRST["${key}"]="${#SEL_PATTERNS[@]}"
      SEL_COUNT["${key}"]=0
      continue
    fi
    if [[ "${line}" =~ ^\ \ \ \ -\ (.+)$ ]]; then
      entry="${BASH_REMATCH[1]}"
      [[ -n "${key}" ]] || _sel_bad "${file}:${n}" "${line}" "list entry outside a key"
      _sel_valid_entry "${entry}" || _sel_bad "${file}:${n}" "${line}" "entry must be an exact path or '<dir>/**/*'"
      SEL_ENTRIES["${key}"]+="${entry}"$'\n'
      SEL_PATTERNS+=("${entry}")
      SEL_COUNT["${key}"]=$((SEL_COUNT["${key}"] + 1))
      continue
    fi
    _sel_bad "${file}:${n}" "${line}" "not in the restricted format (block lists under '.selection:' only)"
  done
  [[ "${seen_root}" -eq 1 ]] || die "${file}: missing top-level key '.selection:'"
  for k in "${SEL_KEYS[@]}"; do
    [[ -n "${SEL_ENTRIES[${k}]}" ]] || die "${file}: key '${k}' has no entries"
    _sel_in_list "${k}" "${SEL_REQUIRED_KEYS[@]}" || die "${file}: unknown key '${k}'"
  done
  for k in "${SEL_REQUIRED_KEYS[@]}"; do
    [[ -n "${SEL_ENTRIES[${k}]+x}" ]] || die "${file}: missing key '${k}'"
  done
}

# _sel_bad <file:line> <line> <message>: die on a format violation.
_sel_bad() {
  die "$1: $3: '$2'"
}

# _sel_valid_entry <entry>: exact path (no glob characters, no quotes, no
# leading or trailing slash, no '.' or '..' segments) or '<dir>/**/*'.
_sel_valid_entry() {
  local entry="$1" path="$1" seg
  if [[ "${entry}" == *"/**/*" ]]; then
    path="${entry%/\*\*/\*}"
  fi
  [[ -n "${path}" ]] || return 1
  [[ "${path}" =~ ^[A-Za-z0-9._+-][A-Za-z0-9._/+-]*$ ]] || return 1
  [[ "${path}" != */ && "${path}" != *//* ]] || return 1
  local -a segs
  IFS=/ read -r -a segs <<< "${path}"
  for seg in "${segs[@]}"; do
    [[ "${seg}" != "." && "${seg}" != ".." ]] || return 1
  done
  return 0
}

# _sel_in_list <needle> <item...>
_sel_in_list() {
  local needle="$1" item
  shift
  for item in "$@"; do
    [[ "${item}" == "${needle}" ]] && return 0
  done
  return 1
}

# sel_match <entry> <path>: true if path matches the entry. '<dir>/**/*'
# matches every path under '<dir>/' (GitLab fnmatch semantics for that form);
# anything else must be equal.
sel_match() {
  local entry="$1" path="$2"
  if [[ "${entry}" == *"/**/*" ]]; then
    [[ "${path}" == "${entry%\*\*/\*}"* ]]
  else
    [[ "${path}" == "${entry}" ]]
  fi
}

# sel_key_matches <key> <path>: true if an entry of key matches path; the
# matching entry is left in SEL_MATCH. Reads the pre-split SEL_PATTERNS
# without a subshell or here-string, so large diffs stay fast.
sel_key_matches() {
  local key="$1" path="$2" i end entry
  SEL_MATCH=""
  i="${SEL_FIRST[${key}]:-0}"
  end=$((i + ${SEL_COUNT[${key}]:-0}))
  for ((; i < end; i++)); do
    entry="${SEL_PATTERNS[i]}"
    sel_match "${entry}" "${path}" || continue
    SEL_MATCH="${entry}"
    return 0
  done
  return 1
}

# sel_resolve_range [<base>] [<head>]: decide the change range. Sets
#   RANGE_MODE        diff | all
#   RANGE_REASON      why (human readable)
#   RANGE_BASE        the requested base ('' if none)
#   RANGE_MERGE_BASE  merge-base of base and head (diff mode only)
#   RANGE_HEAD        the head commit sha
# Base precedence: argument, SCM_MR_DIFF_BASE_SHA, SCM_BEFORE_SHA. A missing,
# all-zero or unreachable base, or a schedule/tag/web event, gives 'all'.
sel_resolve_range() {
  local base="${1:-}" head="${2:-}" event="${SCM_EVENT:-}"
  RANGE_MODE="all"
  RANGE_REASON=""
  RANGE_MERGE_BASE=""
  head="${head:-${SCM_SHA:-HEAD}}"
  RANGE_HEAD="$(git rev-parse --verify --quiet "${head}^{commit}")" \
    || die "head '${head}' is not a commit in this repository"
  if [[ -z "${base}" ]]; then
    base="${SCM_MR_DIFF_BASE_SHA:-}"
  fi
  if [[ -z "${base}" ]]; then
    base="${SCM_BEFORE_SHA:-}"
  fi
  RANGE_BASE="${base}"
  case "${event}" in
    schedule | tag | web)
      RANGE_REASON="${event} pipeline: everything is selected"
      return 0
      ;;
  esac
  if [[ -z "${base}" ]]; then
    RANGE_REASON="no base commit: everything is selected"
    return 0
  fi
  if [[ "${base}" =~ ${SEL_ZERO_SHA_RE} ]]; then
    RANGE_REASON="base is all zeros: everything is selected"
    return 0
  fi
  local base_sha
  if ! base_sha="$(git rev-parse --verify --quiet "${base}^{commit}")"; then
    RANGE_REASON="base '${base}' is not reachable: everything is selected"
    return 0
  fi
  if ! RANGE_MERGE_BASE="$(git merge-base "${base_sha}" "${RANGE_HEAD}")"; then
    RANGE_MERGE_BASE=""
    RANGE_REASON="no merge base between '${base}' and '${head}': everything is selected"
    return 0
  fi
  RANGE_MODE="diff"
  RANGE_REASON="changes in ${RANGE_MERGE_BASE:0:12}..${RANGE_HEAD:0:12}"
}

# sel_changed_files: print the files changed in RANGE_MERGE_BASE..RANGE_HEAD,
# one per line, without rename collapsing. Requires RANGE_MODE=diff.
sel_changed_files() {
  [[ "${RANGE_MODE:-}" == diff ]] || die "sel_changed_files: no diff range"
  git -c core.quotePath=false diff --name-only --no-renames --no-ext-diff \
    "${RANGE_MERGE_BASE}..${RANGE_HEAD}" --
}
