#!/bin/bash

set -euo pipefail

: "${NEXUS_URL:?NEXUS_URL is not set — export it before running this script}"

declare -A PKG_NAME=(
    [slat]="cognos-slat"      [svk-me]="cognos-me"     [ras]="cognos-ras"
    [svk-node]="cognos-node"  [sapp]="cognos-app"       [core]="cognos-core"
    [mgmt-fw]="cognos-mgmt-fw" [cxl]="cognos-cxl"       [grpc]="cognos-grpc"
)
ALL_PROJECTS="slat svk-me ras svk-node sapp core mgmt-fw cxl grpc"

declare -A PINNED_VERSION
MOCK_MODE=false

die()  { echo "[ERROR] $*" >&2; exit 1; }
log()  { echo "[INFO]  $*"; }

usage() {
    echo "Usage: $0 --os ubuntu22|ubuntu24|ol9|ol10 [--mock] [project=version ...]"
    echo ""
    echo "  --os <target>       Required. One of: ubuntu22, ubuntu24, ol9, ol10"
    echo "  --mock              Also download cognos-cxl-mock package"
    echo "  project=version     Pin a specific version for a project, e.g. slat=1.1.0"
    echo ""
    echo "Projects: $ALL_PROJECTS"
    echo ""
    echo "Examples:"
    echo "  $0 --os ubuntu22"
    echo "  $0 --os ol10 --mock"
    echo "  $0 --os ol10 slat=1.1.0 core=1.0.9"
    exit 0
}

OS_TARGET=""

[[ $# -eq 0 ]] && usage

while [[ $# -gt 0 ]]; do
    case "$1" in
        --os)
            shift
            [[ $# -gt 0 ]] || die "--os requires an argument"
            OS_TARGET="$1"; shift ;;
        --os=*)
            OS_TARGET="${1#--os=}"; shift ;;
        --mock)
            MOCK_MODE=true; shift ;;
        -h|--help)
            usage ;;
        *=*)
            proj="${1%%=*}"
            ver="${1#*=}"
            [[ -v PKG_NAME[$proj] ]] \
                || die "Unknown project '$proj'. Valid projects: $ALL_PROJECTS"
            [[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
                || die "Invalid version '$ver' for '$proj'. Expected format: X.Y.Z"
            PINNED_VERSION[$proj]="$ver"
            log "Pinned: $proj=$ver"
            shift ;;
        *)
            die "Unknown argument: $1  Run $0 --help for usage." ;;
    esac
done

[[ -n "$OS_TARGET" ]] || die "--os is required. Valid targets: ubuntu22, ubuntu24, ol9, ol10"

case "$OS_TARGET" in
    ubuntu22) OS_FAMILY="debian"; NEXUS_REPO="svk_apt_ubuntu22" ;;
    ubuntu24) OS_FAMILY="debian"; NEXUS_REPO="svk_apt_ubuntu24" ;;
    ol9)      OS_FAMILY="rpm";    NEXUS_REPO="svk_yum_ol9"      ;;
    ol10)     OS_FAMILY="rpm";    NEXUS_REPO="svk_yum_ol10"     ;;
    *)        die "Unsupported OS target '$OS_TARGET'. Valid: ubuntu22, ubuntu24, ol9, ol10" ;;
esac

BASE_URL="${NEXUS_URL%/repository}"

log "OS target  : $OS_TARGET"
log "Nexus repo : $NEXUS_REPO"
log "NEXUS_URL  : $BASE_URL"

nexus_search() {
    local pkg="$1"
    local ver="${2:-}"
    local base_url="${BASE_URL}/service/rest/v1/search/assets?repository=${NEXUS_REPO}&name=${pkg}&sort=version&direction=desc"
    [[ -n "$ver" ]] && base_url+="&version=${ver}"

    local token="" response all_urls=""
    while true; do
        local search_url="$base_url"
        [[ -n "$token" ]] && search_url+="&continuationToken=${token}"

        response=$(curl --silent --max-time 30 \
            --header "Accept: application/json" \
            "$search_url" 2>/dev/null) || true

        [[ -n "$response" ]] \
            || die "$pkg: no response from Nexus at ${BASE_URL} — check NEXUS_URL and network"

        all_urls+=$(printf '%s' "$response" \
            | grep -oP '"downloadUrl"\s*:\s*"\K[^"]+')
        all_urls+=$'\n'

        token=$(printf '%s' "$response" \
            | grep -oP '"continuationToken"\s*:\s*"\K[^"]+' | head -1)
        [[ -n "$token" ]] || break
    done

    printf '%s' "$all_urls" | grep -v '^$' \
        | while IFS= read -r u; do
            v=$(basename "$u" | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            printf '%s %s\n' "${v:-0.0.0}" "$u"
          done \
        | sort -V -k1,1 \
        | awk '{print $2}' || true
}

pick_url_for_os() {
    local urls="$1"
    local match=""

    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        case "$OS_FAMILY" in
            debian) [[ "$url" == *"${NEXUS_REPO}"* && "$url" == *.deb ]] && match="$url" ;;
            rpm)    [[ "$url" == *"${NEXUS_REPO}"* && "$url" == *.rpm ]] && match="$url" ;;
        esac
    done <<< "$urls"

    echo "$match"
}

version_from_url() {
    basename "$1" | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

log ""
log "=== Resolving packages from Nexus ==="

declare -A RESOLVED_URL
declare -A RESOLVED_VERSION
LATEST_VER=""

for project in $ALL_PROJECTS; do
    pkg="${PKG_NAME[$project]}"

    if [[ -v PINNED_VERSION[$project] ]]; then
        ver="${PINNED_VERSION[$project]}"
        log "  $project ($pkg): looking up pinned version $ver..."

        urls=$(nexus_search "$pkg" "$ver")
        url=$(pick_url_for_os "$urls")

        [[ -n "$url" ]] \
            || die "$project: pinned version $ver of '$pkg' not found in Nexus repo '$NEXUS_REPO' for OS '$OS_TARGET'"

        RESOLVED_URL[$project]="$url"
        RESOLVED_VERSION[$project]="$ver"
        log "$project: $ver (pinned) → $(basename "$url")"
    else
        log "  $project ($pkg): querying Nexus for latest..."

        urls=$(nexus_search "$pkg")
        url=$(pick_url_for_os "$urls")

        [[ -n "$url" ]] \
            || die "$project: package '$pkg' not found in Nexus repo '$NEXUS_REPO' for OS '$OS_TARGET'"

        ver=$(version_from_url "$url")
        [[ -n "$ver" ]] \
            || die "$project: could not parse version from URL: $url"

        RESOLVED_URL[$project]="$url"
        RESOLVED_VERSION[$project]="$ver"
        log "$project: $ver (latest) → $(basename "$url")"

        if [[ -z "$LATEST_VER" ]] || \
           [[ "$(printf '%s\n%s' "$ver" "$LATEST_VER" | sort -V | tail -1)" == "$ver" ]]; then
            LATEST_VER="$ver"
        fi
    fi

    if [[ "$project" == "cxl" && "$MOCK_MODE" == true ]]; then
        log "  cxl-mock (cognos-cxl-mock): querying Nexus for latest..."
        urls=$(nexus_search "cognos-cxl-mock")
        url=$(pick_url_for_os "$urls")
        [[ -n "$url" ]] \
            || die "cxl-mock: package 'cognos-cxl-mock' not found in Nexus repo '$NEXUS_REPO' for OS '$OS_TARGET'"
        ver=$(version_from_url "$url")
        RESOLVED_URL[cxl-mock]="$url"
        RESOLVED_VERSION[cxl-mock]="$ver"
        log "cxl-mock: $ver (latest) → $(basename "$url")"
    fi
done

[[ -n "$LATEST_VER" ]] \
    || die "Could not determine latest version — were all packages pinned?"

TARBALL_VER="${LATEST_VER%.*}"   # strip patch: 1.1.1 → 1.1
TARBALL_NAME="cognos_runner_mvp_${TARBALL_VER}_${OS_TARGET}.tar.gz"

log ""
log "=== Version summary ==="
for project in $ALL_PROJECTS; do
    flag=""; [[ -v PINNED_VERSION[$project] ]] && flag=" (pinned)"
    log "  $project: ${RESOLVED_VERSION[$project]}${flag}  →  $(basename "${RESOLVED_URL[$project]}")"
    if [[ "$project" == "cxl" && "$MOCK_MODE" == true ]]; then
        log "  cxl-mock: ${RESOLVED_VERSION[cxl-mock]}  →  $(basename "${RESOLVED_URL[cxl-mock]}")"
    fi
done
log "  Tarball name: $TARBALL_NAME"

log ""
log "=== Downloading packages ==="

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

PKG_DIR="${WORK_DIR}/SVK"
mkdir -p "$PKG_DIR"

for project in $ALL_PROJECTS; do
    url="${RESOLVED_URL[$project]}"
    filename=$(basename "$url")
    dest="${PKG_DIR}/${filename}"

    log "  $project: downloading $filename"
    if ! wget --quiet --output-document="$dest" "$url" 2>/dev/null; then
        rm -f "$dest"
        die "$project: failed to download $filename from $url"
    fi
    log "$project: $filename"

    if [[ "$project" == "cxl" && "$MOCK_MODE" == true ]]; then
        url="${RESOLVED_URL[cxl-mock]}"
        filename=$(basename "$url")
        dest="${PKG_DIR}/${filename}"
        log "  cxl-mock: downloading $filename"
        if ! wget --quiet --output-document="$dest" "$url" 2>/dev/null; then
            rm -f "$dest"
            die "cxl-mock: failed to download $filename from $url"
        fi
        log "cxl-mock: $filename"
    fi
done

TARBALL_PATH="${PWD}/${TARBALL_NAME}"

log ""
log "=== Creating tarball: $TARBALL_NAME ==="

tar -czf "$TARBALL_PATH" -C "$WORK_DIR" SVK \
    || die "Failed to create tarball at $TARBALL_PATH"

ARTIFACTS_DIR="$(git rev-parse --show-toplevel)/artifacts"
mkdir -p "$ARTIFACTS_DIR"

log ""
log "=== Extracting tarball into $ARTIFACTS_DIR ==="
tar -xzf "$TARBALL_PATH" -C "$ARTIFACTS_DIR"

log ""
log "=== Done ==="
log "  Tarball  : $TARBALL_PATH"
log "  Artifacts: $ARTIFACTS_DIR/SVK"
log "  Contents :"
ls "$ARTIFACTS_DIR/SVK" | while IFS= read -r f; do log "    $f"; done
