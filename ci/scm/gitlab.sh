#!/usr/bin/env bash
# GitLab adapter. Sourced, never executed. This file and gitlab/** are the
# only places that know GitLab: everything else under ci/ reads the neutral
# SCM_* variables set by scm_env.
#
# Phase 1 provides scm_env only. ci/scm/fake.sh implements the same functions
# for tests.

# scm_env: map the GitLab predefined CI_* variables to the neutral SCM_*
# variables and export them.
#   SCM_SHA               commit being built
#   SCM_BEFORE_SHA        previous branch head of a push ('' if none)
#   SCM_MR_DIFF_BASE_SHA  merge-request diff base ('' outside merge requests)
#   SCM_SOURCE_BRANCH     merge-request source branch, else the pushed branch
#   SCM_TARGET_BRANCH     merge-request target branch ('' outside merge requests)
#   SCM_SOURCE_IS_FORK    true if the merge request comes from another
#                         project (a fork), else false
#   SCM_EVENT             mr | push | tag | schedule | web
#   SCM_REF               branch or tag name
#   SCM_TAG               tag name ('' unless a tag pipeline)
#   SCM_PIPELINE_URL      URL of this pipeline
scm_env() {
  local source="${CI_PIPELINE_SOURCE:-}"
  SCM_SHA="${CI_COMMIT_SHA:-}"
  SCM_BEFORE_SHA="${CI_COMMIT_BEFORE_SHA:-}"
  SCM_MR_DIFF_BASE_SHA="${CI_MERGE_REQUEST_DIFF_BASE_SHA:-}"
  # Merged-results and merge-train pipelines build a temporary merge commit
  # onto the target head; diffing it against the fork point would pull in
  # everything merged into the target since. The target head is the right base.
  case "${CI_MERGE_REQUEST_EVENT_TYPE:-}" in
    merged_result | merge_train)
      if [[ -n "${CI_MERGE_REQUEST_TARGET_BRANCH_SHA:-}" ]]; then
        SCM_MR_DIFF_BASE_SHA="${CI_MERGE_REQUEST_TARGET_BRANCH_SHA}"
      fi
      ;;
  esac
  SCM_SOURCE_BRANCH="${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-${CI_COMMIT_BRANCH:-}}"
  SCM_TARGET_BRANCH="${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-}"
  SCM_SOURCE_IS_FORK=false
  if [[ -n "${CI_MERGE_REQUEST_SOURCE_PROJECT_ID:-}" \
    && "${CI_MERGE_REQUEST_SOURCE_PROJECT_ID}" != "${CI_PROJECT_ID:-}" ]]; then
    SCM_SOURCE_IS_FORK=true
  fi
  SCM_REF="${CI_COMMIT_REF_NAME:-}"
  SCM_TAG="${CI_COMMIT_TAG:-}"
  SCM_PIPELINE_URL="${CI_PIPELINE_URL:-}"
  # A tag pipeline is a tag pipeline whatever started it (push, API, trigger).
  if [[ -n "${SCM_TAG}" ]]; then
    source=tag
  fi
  case "${source}" in
    merge_request_event) SCM_EVENT=mr ;;
    tag) SCM_EVENT=tag ;;
    push) SCM_EVENT=push ;;
    schedule) SCM_EVENT=schedule ;;
    web) SCM_EVENT=web ;;
    *)
      printf 'scm_env: unsupported pipeline source %s\n' "'${source}'" >&2
      return 1
      ;;
  esac
  # A merge-request pipeline has no 'before' commit; GitLab reports zeros.
  if [[ "${SCM_EVENT}" == mr ]]; then
    SCM_BEFORE_SHA=""
  fi
  [[ -n "${SCM_SHA}" ]] || {
    printf 'scm_env: commit sha is not set\n' >&2
    return 1
  }
  export SCM_SHA SCM_BEFORE_SHA SCM_MR_DIFF_BASE_SHA SCM_SOURCE_BRANCH \
    SCM_TARGET_BRANCH SCM_SOURCE_IS_FORK SCM_EVENT SCM_REF SCM_TAG SCM_PIPELINE_URL
}
