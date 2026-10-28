#!/usr/bin/env bash
# Tests of ci/scripts/guards.sh over a fixture repository, with the SCM state
# supplied through ci/scm/fake.sh.
set -euo pipefail

# shellcheck source=ci/tests/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GUARDS=(bash "${COGNOS_CI_DIR}/scripts/guards.sh")
FAKE_SCM="${COGNOS_CI_DIR}/scm/fake.sh"
# Conflict markers are built at run time so this file never contains one.
M_OPEN="$(printf '<%.0s' 1 2 3 4 5 6 7)"
M_MID="$(printf '=%.0s' 1 2 3 4 5 6 7)"
M_CLOSE="$(printf '>%.0s' 1 2 3 4 5 6 7)"

repo="${T_TMP}/repo"
t_repo "${repo}"
cd "${repo}"
for f in README.md VERSION components/cxl/a apps/sapp/a profilers/amo-prof/a deploy/a docs/a.md; do
  t_write "${f}" base
done
printf '1.6\n' > VERSION
t_commit base
BASE="$(git rev-parse HEAD)"

# change <branch> <path=content>...: branch from BASE and commit the files
# (content replaces the file; an empty content appends a line).
change() {
  local branch="$1" spec path content
  shift
  git checkout -q -B "${branch}" "${BASE}"
  for spec in "$@"; do
    path="${spec%%=*}"
    content="${spec#*=}"
    if [[ "${spec}" == *=* ]]; then
      mkdir -p "$(dirname "${path}")"
      printf '%s\n' "${content}" > "${path}"
    else
      t_write "${path}"
    fi
  done
  t_commit "change on ${branch}"
}

# run_guards <event> <source> <target>: run guards.sh with fake SCM state
# for BASE..HEAD (FORK=true: the source branch is in a fork). Prints the
# output; returns the exit status.
run_guards() {
  local state="${T_TMP}/scm.state"
  {
    printf 'SCM_EVENT=%s\n' "$1"
    printf 'SCM_SOURCE_BRANCH=%s\n' "$2"
    printf 'SCM_TARGET_BRANCH=%s\n' "$3"
    printf 'SCM_SOURCE_IS_FORK=%s\n' "${FORK:-false}"
    printf 'SCM_SHA=%s\n' "$(git rev-parse HEAD)"
    if [[ "$1" == mr ]]; then
      printf 'SCM_MR_DIFF_BASE_SHA=%s\n' "${BASE}"
    else
      printf 'SCM_BEFORE_SHA=%s\n' "${BASE}"
    fi
  } > "${state}"
  (
    # shellcheck source=ci/scm/fake.sh
    source "${FAKE_SCM}"
    FAKE_SCM_STATE="${state}" scm_env
    "${GUARDS[@]}" 2>&1
  )
}

# expect <name> pass|fail [<text in output>] -- <event> <source> <target>
expect() {
  local name="$1" want="$2" text="" out rc=0
  shift 2
  if [[ "$1" != "--" ]]; then
    text="$1"
    shift
  fi
  shift
  out="$(run_guards "$@")" || rc=$?
  if [[ "${want}" == pass && "${rc}" -eq 0 ]] \
    || [[ "${want}" == fail && "${rc}" -eq 1 && "${out}" == *"${text}"* ]]; then
    t_ok "${name}"
  else
    # shellcheck disable=SC2016
    t_fail "${name}" "wanted ${want}${text:+ with '${text}'}, got exit ${rc}" "${out//$'\n'/$'\n      '}"
  fi
}

# (a) Transition guard.
change feat-cxl components/cxl/b
expect "a: feature MR touching components/ fails" fail "GUARD FAILED (a)" -- mr feature/x main
expect "a: offending path is listed" fail "components/cxl/b" -- mr feature/x main
expect "a: sync/* is exempt" pass -- mr sync/cxl-1234abcd main
expect "a: backport/* is exempt" pass -- mr backport/1.7/mr-12 main
expect "a: push is not checked" pass -- push main ""
FORK=true expect "a: sync/* of a fork is not exempt" fail "GUARD FAILED (a)" -- mr sync/cxl-1234abcd main
FORK=true expect "a: backport/* of a fork is not exempt" fail "GUARD FAILED (a)" -- mr backport/1.7/mr-12 main
MONOREPO_OWNS_COMPONENTS=true expect "a: lifted by MONOREPO_OWNS_COMPONENTS=true" pass -- mr feature/x main
MONOREPO_OWNS_COMPONENTS=false expect "a: MONOREPO_OWNS_COMPONENTS=false keeps it" fail "GUARD FAILED (a)" -- mr feature/x main
change feat-sapp apps/sapp/b
expect "a: apps/sapp fails" fail "apps/sapp/b" -- mr feature/x main
change feat-amo profilers/amo-prof/b
expect "a: profilers/amo-prof fails" fail "profilers/amo-prof/b" -- mr feature/x main
change feat-ok docs/b.md deploy/b README.md
expect "a: docs and deploy pass" pass -- mr feature/x main

# (b) VERSION and CHANGELOG.md guard.
change feat-version VERSION=1.7
expect "b: feature MR changing VERSION fails" fail "GUARD FAILED (b)" -- mr feature/x main
expect "b: sync/* is not exempt" fail "GUARD FAILED (b)" -- mr sync/cxl-1 main
expect "b: backport/* is not exempt" fail "GUARD FAILED (b)" -- mr backport/1.7/mr-1 release/1.7
expect "b: VERSION into release/* fails even from the bot" fail "into release/1.7" -- mr release-bot/next release/1.7
expect "b: release-bot/next may change VERSION in main" pass -- mr release-bot/next main
FORK=true expect "b: release-bot/next of a fork may not" fail "GUARD FAILED (b)" -- mr release-bot/next main
change feat-changelog CHANGELOG.md
expect "b: feature MR changing CHANGELOG.md fails" fail "CHANGELOG.md" -- mr feature/x main
expect "b: CHANGELOG.md into release/* is allowed" pass -- mr backport/1.7/mr-2 release/1.7

# (c) release-bot/next content.
change bot-extra VERSION=1.7 CHANGELOG.md README.md
expect "c: other files fail" fail "GUARD FAILED (c)" -- mr release-bot/next main
expect "c: the extra path is listed" fail "README.md" -- mr release-bot/next main
# Same X.Y with a trailing blank line, so that VERSION is part of the diff.
change bot-same "VERSION=1.6
"
expect "c: VERSION equal to the release line fails" fail "must be greater" -- mr release-bot/next main
change bot-lower VERSION=1.5 CHANGELOG.md
expect "c: lower VERSION fails" fail "must be greater than the latest release line 1.6" -- mr release-bot/next main
expect "c: the release line source is logged (VERSION)" fail "latest release line '1.6' from VERSION at" -- mr release-bot/next main
change bot-bad VERSION=1.7.0
expect "c: VERSION must be X.Y" fail "VERSION must be X.Y" -- mr release-bot/next main
change bot-ok VERSION=2.0 CHANGELOG.md
expect "c: a major bump passes" pass -- mr release-bot/next main
git tag -a v2.0.0 -m "Release 2.0.0" "${BASE}"
change bot-tagged VERSION=2.0 CHANGELOG.md
expect "c: VERSION not above the highest v tag fails" fail "latest release line 2.0" -- mr release-bot/next main
expect "c: the release line source is logged (tag)" fail "latest release line '2.0' from tag v2.0.0" -- mr release-bot/next main
git tag core/v9.9.9 "${BASE}"
change bot-tagged-ok VERSION=2.1 CHANGELOG.md
expect "c: prefixed tags are ignored" pass -- mr release-bot/next main
git tag -d v2.0.0 core/v9.9.9 > /dev/null

# (d) Conflict markers.
change conflict "docs/c.md=intro
${M_OPEN} HEAD
ours
${M_MID}
theirs
${M_CLOSE} backport"
expect "d: added markers fail" fail "GUARD FAILED (d)" -- mr backport/1.7/mr-3 release/1.7
expect "d: the file is listed" fail "docs/c.md" -- mr backport/1.7/mr-3 release/1.7
expect "d: checked on pushes too" fail "GUARD FAILED (d)" -- push release/1.7 ""
# The user's diff configuration must not hide the file names.
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=diff.noprefix GIT_CONFIG_VALUE_0=true \
  expect "d: diff.noprefix=true still fails" fail "docs/c.md" -- mr backport/1.7/mr-3 release/1.7
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=diff.mnemonicPrefix GIT_CONFIG_VALUE_0=true \
  expect "d: diff.mnemonicPrefix=true still fails" fail "docs/c.md" -- mr backport/1.7/mr-3 release/1.7
change quoted "docs/q \"x\".md=intro
${M_CLOSE}"
expect "d: a quoted path still fails" fail "GUARD FAILED (d)" -- mr feature/x main
# A file with CRLF endings: the marker is followed by a carriage return.
git checkout -q -B crlf "${BASE}"
printf 'intro\r\n%s\r\n' "${M_CLOSE}" > docs/crlf.md
t_commit "crlf marker"
expect "d: a marker followed by CR (CRLF file) fails" fail "docs/crlf.md" -- mr feature/x main
change heading "docs/h.md=Title
${M_MID}
text with ${M_OPEN} inside a line"
expect "d: setext headings and inline text pass" pass -- mr feature/x main
# A change that removes a marker (from a base that has one) passes.
change marked "docs/c.md=intro
${M_OPEN} HEAD"
BASE_SAVE="${BASE}"
BASE="$(git rev-parse HEAD)"
printf 'intro\n' > docs/c.md
t_commit "remove the marker"
expect "d: removing a marker passes" pass -- mr feature/x main
BASE="${BASE_SAVE}"

# Merged-results pipelines build a merge commit of the MR onto the current
# target head. If the target gained a components/ commit (a sync merge)
# after the MR forked, the fork point as base pulls that commit into the
# range; the target head as base gives exactly the MR's change. This is why
# ci/scm/gitlab.sh uses the target head as base in those pipelines.
change mr-docs docs/m.md
mr_head="$(git rev-parse HEAD)"
git checkout -q -B main-later "${BASE}"
t_write components/cxl/synced
t_commit "sync merge on main"
target_head="$(git rev-parse HEAD)"
git merge -q --no-ff --no-edit "${mr_head}"
merge_commit="$(git rev-parse HEAD)"
merged() {
  SCM_EVENT=mr SCM_SOURCE_BRANCH=feature/x SCM_TARGET_BRANCH=main SCM_SHA="${merge_commit}" \
    "${GUARDS[@]}" --base "$1" --head "${merge_commit}" 2>&1
}
rc=0
out="$(merged "${BASE}")" || rc=$?
if [[ "${rc}" -eq 1 && "${out}" == *"GUARD FAILED (a)"* && "${out}" == *"components/cxl/synced"* ]]; then
  t_ok "merged result: the fork point as base wrongly fails (a)"
else
  t_fail "merged result: the fork point as base wrongly fails (a)" "exit ${rc}" "${out}"
fi
rc=0
out="$(merged "${target_head}")" || rc=$?
if [[ "${rc}" -eq 0 ]]; then
  t_ok "merged result: the target head as base passes"
else
  t_fail "merged result: the target head as base passes" "exit ${rc}" "${out}"
fi

# All guards report together.
change multi VERSION=1.9 components/cxl/c
out="$(run_guards mr feature/x main)" || true
if [[ "${out}" == *"GUARD FAILED (a)"* && "${out}" == *"GUARD FAILED (b)"* && "${out}" == *"2 guard(s) failed"* ]]; then
  t_ok "every failing guard is reported"
else
  t_fail "every failing guard is reported" "${out}"
fi

# Usage error.
rc=0
"${GUARDS[@]}" --nope > /dev/null 2>&1 || rc=$?
t_eq "unknown option exits 2" 2 "${rc}"

# An MR whose range cannot be resolved fails loudly.
rc=0
out="$(SCM_EVENT=mr SCM_MR_DIFF_BASE_SHA=0000000000000000000000000000000000000000 "${GUARDS[@]}" 2>&1)" || rc=$?
if [[ "${rc}" -eq 1 && "${out}" == *"cannot evaluate the merge-request guards"* ]]; then
  t_ok "MR without a usable base fails"
else
  t_fail "MR without a usable base fails" "exit ${rc}" "${out}"
fi

t_done
