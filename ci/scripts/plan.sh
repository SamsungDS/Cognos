#!/usr/bin/env bash
# Change-based selection: which components and jobs a change needs.
#
# Usage: plan.sh [--base <ref>] [--head <ref>] [--format text|json|github-matrix]
#                [--text-out <file>] [--selection <file>]
#
# Diffs 'git diff --name-only <merge-base>..<head>' (no rename collapsing) in
# the repository of the current directory and applies ci/selection.yml:
# - a platform hit selects all 8 package components;
# - a <component> hit selects that component;
# - an amo-prof hit selects the amo-prof jobs (never through platform);
# - a deploy hit selects ansible-lint;
# - anything else selects nothing.
# Base: --base, else SCM_MR_DIFF_BASE_SHA, else SCM_BEFORE_SHA. A missing,
# all-zero or unreachable base, or SCM_EVENT schedule/tag/web, selects
# everything, except that a tag pipeline never selects the amo-prof or
# ansible-lint jobs (they do not run on tags). Head: --head, else SCM_SHA,
# else HEAD.
#
# Output (stdout): text (default), json, or github-matrix (a JSON object
# {"include":[{"component":"<name>"},...]} for a GitHub Actions matrix; with
# no component selected it is {"include":[]}, which GitHub rejects as a
# matrix, so callers check for an empty selection first).
# --text-out <file> also writes the text output to <file>, so one run gives
# both the JSON and the text and the diff is classified once.
# Exit: 0 success, 1 failure, 2 usage error.
set -euo pipefail

# shellcheck source=ci/lib/selection.sh
source "$(dirname "${BASH_SOURCE[0]}")/../lib/selection.sh"

usage() {
  sed -n '2,27s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
}

base=""
head=""
format=text
text_out=""
selection="${COGNOS_CI_DIR}/selection.yml"
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
    --format)
      [[ $# -ge 2 ]] || usage_error "--format needs a value"
      format="$2"
      shift 2
      ;;
    --text-out)
      [[ $# -ge 2 ]] || usage_error "--text-out needs a value"
      text_out="$2"
      shift 2
      ;;
    --selection)
      [[ $# -ge 2 ]] || usage_error "--selection needs a value"
      selection="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) usage_error "unknown argument '$1' (see --help)" ;;
  esac
done
case "${format}" in
  text | json | github-matrix) ;;
  *) usage_error "unknown format '${format}' (text, json or github-matrix)" ;;
esac

require_cmd git jq
git rev-parse --git-dir > /dev/null 2>&1 || die "not inside a git repository: $(pwd)"
sel_load "${selection}"
sel_resolve_range "${base}" "${head}"

# selected[<name>] = reason; names are the package components plus the
# amo-prof and ansible_lint flags. not_selected[<name>] = why a flag that
# 'all' would set is off.
declare -A selected=() not_selected=()
changed=()

select_item() {
  local name="$1" reason="$2"
  if [[ -z "${selected[${name}]+x}" ]]; then
    selected["${name}"]="${reason}"
  fi
}

if [[ "${RANGE_MODE}" == all ]]; then
  for c in "${SEL_PACKAGE_COMPONENTS[@]}"; do
    select_item "${c}" "${RANGE_REASON}"
  done
  if [[ "${SCM_EVENT:-}" == tag ]]; then
    not_selected[amo-prof]="tag pipeline: the amo-prof jobs do not run on tags"
    not_selected[ansible_lint]="tag pipeline: ansible-lint does not run on tags"
  else
    select_item amo-prof "${RANGE_REASON}"
    select_item ansible_lint "${RANGE_REASON}"
  fi
else
  diff_out="$(sel_changed_files)" || die "git diff failed for ${RANGE_MERGE_BASE}..${RANGE_HEAD}"
  if [[ -n "${diff_out}" ]]; then
    mapfile -t changed <<< "${diff_out}"
  fi
  for path in "${changed[@]+"${changed[@]}"}"; do
    [[ -n "${path}" ]] || continue
    if sel_key_matches platform "${path}"; then
      for c in "${SEL_PACKAGE_COMPONENTS[@]}"; do
        select_item "${c}" "platform: ${path} matches ${SEL_MATCH}"
      done
    fi
    for c in "${SEL_PACKAGE_COMPONENTS[@]}"; do
      if sel_key_matches "${c}" "${path}"; then
        select_item "${c}" "${c}: ${path} matches ${SEL_MATCH}"
      fi
    done
    if sel_key_matches amo-prof "${path}"; then
      select_item amo-prof "amo-prof: ${path} matches ${SEL_MATCH}"
    fi
    if sel_key_matches deploy "${path}"; then
      select_item ansible_lint "deploy: ${path} matches ${SEL_MATCH}"
    fi
  done
fi

components=()
for c in "${SEL_PACKAGE_COMPONENTS[@]}"; do
  if [[ -n "${selected[${c}]+x}" ]]; then
    components+=("${c}")
  fi
done
amo_prof=false
[[ -n "${selected[amo-prof]+x}" ]] && amo_prof=true
ansible_lint=false
[[ -n "${selected[ansible_lint]+x}" ]] && ansible_lint=true

# map_json <assoc array name>: the array's amo-prof/ansible_lint and
# component entries as a JSON object.
map_json() {
  local -n map="$1"
  local name
  for name in "${components[@]+"${components[@]}"}" amo-prof ansible_lint; do
    if [[ -n "${map[${name}]+x}" ]]; then
      jq -n --arg k "${name}" --arg v "${map[${name}]}" '{($k): $v}'
    fi
  done | jq -s 'add // {}'
}

render_json() {
  jq -n \
    --arg mode "${RANGE_MODE}" \
    --arg reason "${RANGE_REASON}" \
    --arg base "${RANGE_BASE}" \
    --arg merge_base "${RANGE_MERGE_BASE}" \
    --arg head "${RANGE_HEAD}" \
    --arg event "${SCM_EVENT:-}" \
    --argjson amo_prof "${amo_prof}" \
    --argjson ansible_lint "${ansible_lint}" \
    --argjson components "$(printf '%s\n' "${components[@]+"${components[@]}"}" | jq -R . | jq -s 'map(select(length > 0))')" \
    --argjson changed "$(printf '%s\n' "${changed[@]+"${changed[@]}"}" | jq -R . | jq -s 'map(select(length > 0))')" \
    --argjson reasons "$(map_json selected)" \
    --argjson not_selected "$(map_json not_selected)" \
    '{schema: 1, mode: $mode, reason: $reason, event: $event, base: $base,
      merge_base: $merge_base, head: $head, components: $components,
      flags: {amo_prof: $amo_prof, ansible_lint: $ansible_lint},
      reasons: $reasons, not_selected: $not_selected, changed_files: $changed}'
}

render_matrix() {
  printf '%s\n' "${components[@]+"${components[@]}"}" | jq -R . \
    | jq -cs 'map(select(length > 0)) | {include: map({component: .})}'
}

render_text() {
  local name
  printf 'mode:          %s (%s)\n' "${RANGE_MODE}" "${RANGE_REASON}"
  printf 'base:          %s\n' "${RANGE_BASE:-<none>}"
  printf 'merge-base:    %s\n' "${RANGE_MERGE_BASE:-<none>}"
  printf 'head:          %s\n' "${RANGE_HEAD}"
  printf 'changed files: %s\n' "${#changed[@]}"
  if [[ "${#components[@]}" -gt 0 ]]; then
    printf 'components:    %s\n' "${components[*]}"
  else
    printf 'components:    none\n'
  fi
  printf 'amo-prof:      %s\n' "${amo_prof}"
  printf 'ansible-lint:  %s\n' "${ansible_lint}"
  if [[ "${#selected[@]}" -gt 0 ]]; then
    printf 'reasons:\n'
    for name in "${components[@]+"${components[@]}"}" amo-prof ansible_lint; do
      if [[ -n "${selected[${name}]+x}" ]]; then
        printf '  %-13s %s\n' "${name}" "${selected[${name}]}"
      fi
    done
  fi
  if [[ "${#not_selected[@]}" -gt 0 ]]; then
    printf 'not selected:\n'
    for name in amo-prof ansible_lint; do
      if [[ -n "${not_selected[${name}]+x}" ]]; then
        printf '  %-13s %s\n' "${name}" "${not_selected[${name}]}"
      fi
    done
  fi
}

case "${format}" in
  json) render_json ;;
  github-matrix) render_matrix ;;
  text) render_text ;;
esac
if [[ -n "${text_out}" ]]; then
  render_text > "${text_out}" || die "cannot write ${text_out}"
fi
