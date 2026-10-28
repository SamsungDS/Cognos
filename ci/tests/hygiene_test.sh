#!/usr/bin/env bash
# Hygiene of the CI files: LF line endings, executable scripts with strict
# mode, no shell tracing. (shellcheck runs separately in the hygiene job.)
set -euo pipefail

# shellcheck source=ci/tests/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

cd "${COGNOS_REPO_ROOT}"

text_files=()
while IFS= read -r -d '' f; do
  text_files+=("${f#./}")
done < <(find ci gitlab -type f -print0 | sort -z)
# Only the files that trigger the hygiene job (gitlab/jobs/hygiene.yml), so a
# docs-only change never needs it.
for f in build.sh VERSION; do
  [[ -f "${f}" ]] && text_files+=("${f}")
done

crlf="$(grep -lI $'\r' "${text_files[@]}" || true)"
t_eq "no CR line endings in ci/, gitlab/, build.sh, VERSION" "" "${crlf}"

scripts=(build.sh)
while IFS= read -r -d '' f; do
  scripts+=("${f#./}")
done < <(find ci -type f -name '*.sh' -print0 | sort -z)

# Scripts are committed with mode 100755. Checked on the git index, not the
# disk, so the check also holds on checkouts that ignore file modes. A script
# that is not in the index fails: its mode would only be decided at commit.
not_exec=()
no_strict=()
for f in "${scripts[@]}"; do
  mode="$(git ls-files -s -- "${f}" | cut -d' ' -f1)"
  if [[ -z "${mode}" ]]; then
    not_exec+=("${f} (not added to git; stage it with git add --chmod=+x)")
  elif [[ "${mode}" != 100755 ]]; then
    not_exec+=("${f} (${mode}; stage it with git add --chmod=+x)")
  fi
  # Executed scripts (not the sourced libraries and adapters) use strict mode.
  case "${f}" in
    ci/lib/* | ci/scm/* | ci/tests/lib.sh) ;;
    *) grep -qx 'set -euo pipefail' "${f}" || no_strict+=("${f}") ;;
  esac
done
t_eq "every script is in git with mode 100755" "" "${not_exec[*]}"
t_eq "every executed script sets -euo pipefail" "" "${no_strict[*]}"

tracing="$(grep -nE '^[[:space:]]*set[[:space:]]+-[a-wyz]*x' "${scripts[@]}" || true)"
t_eq "no set -x" "" "${tracing}"

t_done
