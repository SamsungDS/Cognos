#!/usr/bin/env bash
# The logic under ci/ is SCM-neutral: only the SCM adapter (ci/scm/gitlab.sh)
# and the registry adapters (ci/registry/**) may reference GitLab predefined
# variables, the GitLab API or its token header. Everything else under ci/,
# and the root build.sh, uses the SCM_* variables and adapter functions.
# GitLab YAML lives under gitlab/.
set -euo pipefail

# shellcheck source=ci/tests/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# The patterns are assembled so that this file does not match itself.
PATTERNS=(
  '(^|[^A-Za-z0-9_])C''I_[A-Za-z0-9_]'
  'GIT''LAB'
  '/api''/v4'
  'PRIVATE''-TOKEN'
)
ALLOWED_RE='^ci/(scm/gitlab\.sh|registry/.*)$'

cd "${COGNOS_REPO_ROOT}"
files=()
while IFS= read -r -d '' f; do
  f="${f#./}"
  [[ "${f}" =~ ${ALLOWED_RE} ]] && continue
  files+=("${f}")
done < <(find ci -type f -print0 | sort -z)
files+=(build.sh)

if [[ "${#files[@]}" -eq 0 ]]; then
  t_fail "files to scan" "no files found under ci/"
else
  t_ok "scanning ${#files[@]} files under ci/ and build.sh"
fi

for pattern in "${PATTERNS[@]}"; do
  hits="$(grep -nIE -- "${pattern}" "${files[@]}" || true)"
  if [[ -z "${hits}" ]]; then
    t_ok "no match for /${pattern}/ outside the adapters"
  else
    t_fail "no match for /${pattern}/ outside the adapters" "${hits}"
  fi
done

# The fixture check itself must work: a planted reference is found.
mkdir -p "${T_TMP}/ci/lib"
# shellcheck disable=SC2016
printf 'x="${C%sI_COMMIT_SHA}"\n' "" > "${T_TMP}/ci/lib/planted.sh"
if grep -qIE -- "${PATTERNS[0]}" "${T_TMP}/ci/lib/planted.sh"; then
  t_ok "a planted reference is detected"
else
  t_fail "a planted reference is detected"
fi

t_done
