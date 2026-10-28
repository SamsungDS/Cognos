#!/usr/bin/env bash
# Shared helpers for every script under ci/. Sourced, never executed.
#
# SCM-neutral: nothing here may reference a particular SCM or CI system.
# SCM specifics live in ci/scm/<scm>.sh.

if [[ -n "${_COGNOS_CI_COMMON_LOADED:-}" ]]; then
  return 0
fi
_COGNOS_CI_COMMON_LOADED=1

# Root of the ci/ tree and of the repository that contains it.
COGNOS_CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COGNOS_REPO_ROOT="$(cd "${COGNOS_CI_DIR}/.." && pwd)"
export COGNOS_CI_DIR COGNOS_REPO_ROOT

# log <message...>: one line on stderr, prefixed with the calling script name.
log() {
  printf '[%s] %s\n' "$(basename "${0}")" "$*" >&2
}

# warn <message...>: like log, marked as a warning.
warn() {
  log "WARNING: $*"
}

# die <message...>: log an error and exit 1.
die() {
  log "ERROR: $*"
  exit 1
}

# usage_error <message...>: log a usage error and exit 2.
usage_error() {
  log "usage error: $*"
  exit 2
}

# require_cmd <cmd...>: die unless every command is on PATH.
require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "${cmd}" > /dev/null 2>&1 || die "required command not found: ${cmd}"
  done
}

# retry <attempts> <delay seconds> <cmd...>: run cmd until it succeeds, at most
# <attempts> times, sleeping <delay> seconds between attempts. Returns the last
# exit status on failure.
retry() {
  local attempts="$1" delay="$2" n=1 rc=0
  shift 2
  [[ "${attempts}" =~ ^[1-9][0-9]*$ ]] || die "retry: invalid attempt count '${attempts}'"
  [[ "${delay}" =~ ^[0-9]+$ ]] || die "retry: invalid delay '${delay}'"
  while true; do
    rc=0
    "$@" || rc=$?
    if [[ "${rc}" -eq 0 ]]; then
      return 0
    fi
    if [[ "${n}" -ge "${attempts}" ]]; then
      log "command failed after ${n} attempt(s) (exit ${rc}): $1"
      return "${rc}"
    fi
    log "attempt ${n}/${attempts} failed (exit ${rc}), retrying in ${delay}s: $1"
    n=$((n + 1))
    sleep "${delay}"
  done
}

# os_detect [os-release file]: print the Cognos OS name of this host
# (ubuntu22, ubuntu24, rocky9, ol9, ol10, ...). Dies on an unknown OS.
os_detect() {
  local file="${1:-/etc/os-release}" id="" version_id="" major
  [[ -r "${file}" ]] || die "cannot read ${file}"
  id="$(sed -n 's/^ID=//p' "${file}" | tr -d '"' | head -n 1)"
  version_id="$(sed -n 's/^VERSION_ID=//p' "${file}" | tr -d '"' | head -n 1)"
  major="${version_id%%.*}"
  case "${id}" in
    ubuntu) printf 'ubuntu%s\n' "${major}" ;;
    rocky) printf 'rocky%s\n' "${major}" ;;
    ol) printf 'ol%s\n' "${major}" ;;
    *) die "unsupported OS '${id}' (VERSION_ID '${version_id}') in ${file}" ;;
  esac
}
