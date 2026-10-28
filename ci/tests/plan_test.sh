#!/usr/bin/env bash
# Tests of ci/scripts/plan.sh and the ci/selection.yml parser, table-driven
# over a fixture repository built in a temporary directory.
set -euo pipefail

# shellcheck source=ci/tests/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

PLAN=(bash "${COGNOS_CI_DIR}/scripts/plan.sh")
SELECTION="${COGNOS_CI_DIR}/selection.yml"
ALL8="core mgmt-fw cxl slat ras me node sapp"
ZEROS=0000000000000000000000000000000000000000

repo="${T_TMP}/repo"
t_repo "${repo}"
cd "${repo}"
for f in README.md docs/guide.md VERSION build.sh .gitmodules ci/x.sh gitlab/x.yml \
  components/core/a components/mgmt-fw/a components/cxl/a components/slat/a \
  components/ras/a components/me/a components/node/a apps/sapp/a \
  profilers/amo-prof/a deploy/a; do
  t_write "${f}" base
done
# cama is a gitlink; its empty directory stands for the unpopulated submodule.
mkdir -p cama
git update-index --add --cacheinfo "160000,1111111111111111111111111111111111111111,cama"
t_commit base
BASE="$(git rev-parse HEAD)"

# plan_json <args...>: plan.sh --format json in the fixture repository.
plan_json() {
  "${PLAN[@]}" --selection "${SELECTION}" --format json "$@"
}

# summary <json>: 'mode|components|amo_prof|ansible_lint'
summary() {
  jq -r '[.mode, (.components | join(" ")), (.flags.amo_prof | tostring),
    (.flags.ansible_lint | tostring)] | join("|")' <<< "$1"
}

# case_paths <name> <expected summary> <path...>: branch from BASE, change
# the paths, commit, and compare plan.sh's selection.
case_paths() {
  local name="$1" expected="$2" out
  shift 2
  git checkout -q -B "case" "${BASE}"
  local p
  for p in "$@"; do
    t_write "${p}"
  done
  t_commit "${name}"
  out="$(plan_json --base "${BASE}" --head HEAD)"
  t_eq "${name}" "${expected}" "$(summary "${out}")"
}

# Selection matrix (every case of the acceptance list).
case_paths "docs only -> none" "diff||false|false" docs/guide.md README.md docs/new.md
case_paths "components/cxl -> cxl" "diff|cxl|false|false" components/cxl/src/x.c
case_paths "components/core -> all 8, no amo-prof" "diff|${ALL8}|false|false" components/core/src/x.c
case_paths "components/mgmt-fw -> all 8" "diff|${ALL8}|false|false" components/mgmt-fw/x
case_paths "VERSION -> all 8" "diff|${ALL8}|false|false" VERSION
case_paths "build.sh -> all 8" "diff|${ALL8}|false|false" build.sh
case_paths "ci/ -> all 8" "diff|${ALL8}|false|false" ci/scripts/y.sh
case_paths "gitlab/ -> all 8" "diff|${ALL8}|false|false" gitlab/jobs/z.yml
case_paths ".github/ -> all 8" "diff|${ALL8}|false|false" .github/workflows/ci.yml
case_paths "apps/sapp -> sapp" "diff|sapp|false|false" apps/sapp/cognos/ui/x.js
case_paths "profilers/amo-prof -> amo-prof only" "diff||true|false" profilers/amo-prof/x.py
case_paths "core and amo-prof -> all 8 and amo-prof" "diff|${ALL8}|true|false" \
  components/core/x profilers/amo-prof/x
case_paths "deploy -> ansible-lint" "diff||false|true" deploy/roles/x.yml
case_paths ".gitmodules -> none" "diff||false|false" .gitmodules
case_paths "two leaves -> both, in stack order" "diff|cxl node|false|false" \
  components/node/x components/cxl/x
case_paths "prefix is a directory: components/cxlx -> none" "diff||false|false" \
  components/cxlx/a components/core.txt

# cama gitlink -> none.
git checkout -q -B "case" "${BASE}"
git update-index --cacheinfo "160000,2222222222222222222222222222222222222222,cama"
git commit -q --no-verify -m "bump cama"
t_eq "cama gitlink -> none" "diff||false|false" "$(summary "$(plan_json --base "${BASE}" --head HEAD)")"
t_eq "cama gitlink is the changed file" "cama" \
  "$(plan_json --base "${BASE}" --head HEAD | jq -r '.changed_files | join(" ")')"

# No rename collapsing: moving a file out of a component still selects it.
git checkout -q -B "case" "${BASE}"
git mv components/ras/a docs/ras-a
t_commit "move out of ras"
t_eq "rename out of a component selects it" "diff|ras|false|false" \
  "$(summary "$(plan_json --base "${BASE}" --head HEAD)")"

# Base handling: zeros, unreachable, none, events.
git checkout -q -B "case" "${BASE}"
t_write docs/guide.md
t_commit "docs"
ALLSEL="all|${ALL8}|true|true"
t_eq "base of zeros -> all" "${ALLSEL}" "$(summary "$(plan_json --base "${ZEROS}" --head HEAD)")"
t_eq "unreachable base -> all" "${ALLSEL}" \
  "$(summary "$(plan_json --base 3333333333333333333333333333333333333333 --head HEAD)")"
t_eq "unknown base ref -> all" "${ALLSEL}" "$(summary "$(plan_json --base no-such-ref --head HEAD)")"
t_eq "no base at all -> all" "${ALLSEL}" "$(summary "$(plan_json --head HEAD)")"
for ev in schedule web; do
  t_eq "event ${ev} -> all" "${ALLSEL}" \
    "$(summary "$(SCM_EVENT="${ev}" plan_json --base "${BASE}" --head HEAD)")"
done
tag_out="$(SCM_EVENT=tag plan_json --base "${BASE}" --head HEAD)"
t_eq "event tag -> all 8, no amo-prof, no ansible-lint" "all|${ALL8}|false|false" "$(summary "${tag_out}")"
t_eq "event tag says why amo-prof and ansible-lint are off" "amo_prof ansible_lint" \
  "$(jq -r '.not_selected | keys | map(sub("-"; "_")) | sort | join(" ")' <<< "${tag_out}")"
t_eq "not_selected is empty outside tag pipelines" "{}" \
  "$(SCM_EVENT=web plan_json --base "${BASE}" --head HEAD | jq -c .not_selected)"
t_eq "event mr with a base -> diff" "diff||false|false" \
  "$(summary "$(SCM_EVENT=mr plan_json --base "${BASE}" --head HEAD)")"
t_eq "zero base reason" "base is all zeros: everything is selected" \
  "$(plan_json --base "${ZEROS}" --head HEAD | jq -r .reason)"

# Default base and head from the neutral SCM variables.
docs_head="$(git rev-parse HEAD)"
git checkout -q -B "case" "${BASE}"
t_write components/slat/x
t_commit "slat"
slat_head="$(git rev-parse HEAD)"
git checkout -q "${docs_head}"
t_eq "SCM_MR_DIFF_BASE_SHA and SCM_SHA are the defaults" "diff|slat|false|false" \
  "$(summary "$(SCM_MR_DIFF_BASE_SHA="${BASE}" SCM_SHA="${slat_head}" plan_json)")"
t_eq "SCM_BEFORE_SHA is the fallback base" "diff|slat|false|false" \
  "$(summary "$(SCM_BEFORE_SHA="${BASE}" SCM_SHA="${slat_head}" plan_json)")"
t_eq "SCM_MR_DIFF_BASE_SHA wins over SCM_BEFORE_SHA" "all|${ALL8}|true|true" \
  "$(summary "$(SCM_MR_DIFF_BASE_SHA="${ZEROS}" SCM_BEFORE_SHA="${BASE}" SCM_SHA="${slat_head}" plan_json)")"

# Merge-base semantics: a core change on the base branch after the fork is
# not part of a cxl-only change.
git checkout -q -B fork "${BASE}"
t_write components/cxl/x
t_commit "cxl on the fork"
git checkout -q -B target "${BASE}"
t_write components/core/x
t_commit "core on the target"
t_eq "diff starts at the merge base" "diff|cxl|false|false" \
  "$(summary "$(plan_json --base target --head fork)")"

# Output formats.
git checkout -q fork
t_eq "github-matrix format" '{"include":[{"component":"cxl"}]}' \
  "$("${PLAN[@]}" --selection "${SELECTION}" --format github-matrix --base "${BASE}" --head HEAD)"
t_eq "json reason per selection" "cxl: components/cxl/x matches components/cxl/**/*" \
  "$(plan_json --base "${BASE}" --head HEAD | jq -r '.reasons.cxl')"
text_out="$("${PLAN[@]}" --selection "${SELECTION}" --base "${BASE}" --head HEAD)"
if grep -q '^components: *cxl$' <<< "${text_out}"; then
  t_ok "text format lists the components"
else
  t_fail "text format lists the components" "${text_out}"
fi
json_out="$(plan_json --base "${BASE}" --head HEAD --text-out "${T_TMP}/plan.txt")"
t_eq "--text-out writes the text output of the same run" "${text_out}" "$(cat "${T_TMP}/plan.txt")"
t_eq "--text-out keeps the json on stdout" "cxl" "$(jq -r '.components | join(" ")' <<< "${json_out}")"

# Usage errors exit 2.
rc=0
"${PLAN[@]}" --format yaml > /dev/null 2>&1 || rc=$?
t_eq "unknown format exits 2" 2 "${rc}"
rc=0
"${PLAN[@]}" --bogus > /dev/null 2>&1 || rc=$?
t_eq "unknown option exits 2" 2 "${rc}"

# dump_selection: '<key> <entry>' lines, as read by the bash parser.
dump_selection() (
  # shellcheck source=ci/lib/selection.sh
  source "${COGNOS_CI_DIR}/lib/selection.sh"
  sel_load "${SELECTION}"
  for k in "${SEL_KEYS[@]}"; do
    while IFS= read -r e; do
      if [[ -n "${e}" ]]; then
        printf '%s %s\n' "${k}" "${e}"
      fi
    done <<< "${SEL_ENTRIES[${k}]}"
  done
)

# The real selection file: valid YAML whose content equals what the bash
# parser reads.
if command -v python3 > /dev/null 2>&1 && python3 -c 'import yaml' 2> /dev/null; then
  yaml_dump="$(python3 -c '
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
assert list(d) == [".selection"], list(d)
for k, v in d[".selection"].items():
    assert isinstance(v, list), k
    for e in v:
        print(k, e)
' "${SELECTION}")"
  bash_dump="$(dump_selection)"
  t_eq "selection.yml is valid YAML and parses identically" "${yaml_dump}" "${bash_dump}"
else
  t_fail "selection.yml YAML check" "python3 with the yaml module is required"
fi

# Format violations are rejected loudly.
bad_selection() {
  local name="$1" content="$2" expect="$3" out rc=0
  printf '%s\n' "${content}" > "${T_TMP}/bad.yml"
  out="$("${PLAN[@]}" --selection "${T_TMP}/bad.yml" --base "${BASE}" --head HEAD 2>&1)" || rc=$?
  if [[ "${rc}" -eq 1 && "${out}" == *"${expect}"* ]]; then
    t_ok "rejects ${name}"
  else
    t_fail "rejects ${name}" "exit ${rc}" "${out}"
  fi
}
good="$(cat "${SELECTION}")"
bad_selection "flow-style lists" "${good/$'  deploy:\n    - deploy/**/*'/  deploy: [deploy/**/*]}" \
  "not in the restricted format"
bad_selection "other glob forms" "${good/deploy\/\*\*\/\*/deploy/*}" "exact path or"
bad_selection "a missing key" "${good/$'  deploy:\n    - deploy/**/*'/}" "missing key 'deploy'"
bad_selection "an unknown key" "${good}"$'\n  extra:\n    - x' "unknown key 'extra'"
bad_selection "a duplicate key" "${good}"$'\n  deploy:\n    - x' "duplicate key 'deploy'"
bad_selection "a second top-level key" "${good}"$'\nother:\n  - x' "not in the restricted format"
bad_selection "anchors" "${good/$'  core:\n'/$'  core: &core\n'}" "not in the restricted format"
bad_selection "parent segments" "${good/deploy\/\*\*\/\*/..\/deploy}" "exact path or"
bad_selection "tabs" "${good/$'    - VERSION'/$'    -\tVERSION'}" "tab character"
bad_selection "a missing root key" "${good/.selection:/selection:}" "content before or outside"

t_done
