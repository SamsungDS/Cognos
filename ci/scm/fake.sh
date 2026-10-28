#!/usr/bin/env bash
# File-backed fake SCM adapter for tests. Sourced, never executed. Implements
# the same functions as ci/scm/gitlab.sh.
#
# State: FAKE_SCM_STATE names a file of 'SCM_<NAME>=<value>' lines (blank
# lines and '#' comments allowed). Variables missing from the file are empty.

FAKE_SCM_VARS=(SCM_SHA SCM_BEFORE_SHA SCM_MR_DIFF_BASE_SHA SCM_SOURCE_BRANCH
  SCM_TARGET_BRANCH SCM_SOURCE_IS_FORK SCM_EVENT SCM_REF SCM_TAG SCM_PIPELINE_URL)

# scm_env: load and export the SCM_* variables from FAKE_SCM_STATE.
scm_env() {
  local file="${FAKE_SCM_STATE:-}" line name value v
  [[ -n "${file}" && -r "${file}" ]] || {
    printf 'scm_env (fake): FAKE_SCM_STATE is not a readable file\n' >&2
    return 1
  }
  for v in "${FAKE_SCM_VARS[@]}"; do
    printf -v "${v}" '%s' ""
  done
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    name="${line%%=*}"
    value="${line#*=}"
    case " ${FAKE_SCM_VARS[*]} " in
      *" ${name} "*) printf -v "${name}" '%s' "${value}" ;;
      *)
        printf 'scm_env (fake): unknown variable %s in %s\n' "${name}" "${file}" >&2
        return 1
        ;;
    esac
  done < "${file}"
  SCM_SOURCE_IS_FORK="${SCM_SOURCE_IS_FORK:-false}"
  case "${SCM_EVENT}" in
    mr | push | tag | schedule | web) ;;
    *)
      printf 'scm_env (fake): unsupported event %s\n' "'${SCM_EVENT}'" >&2
      return 1
      ;;
  esac
  export "${FAKE_SCM_VARS[@]}"
}
