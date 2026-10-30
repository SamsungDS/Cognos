#!/usr/bin/env bash
# Puts the Cognos packages for one OS into deploy/artifacts/SVK/, where
# playbooks/deploy_cognos.yml installs them from.
#
# Usage: deploy/scripts/fetch-packages.sh --os ubuntu24|ol10 [--mock] <source>
#
# <source> is one of:
#   --set latest          the newest dev set (built on main)
#   --set <pipeline id>   the dev set of that main pipeline (kept for 10 days)
#   --pipeline <id>       the packages built by that pipeline, for example a
#                         merge request's; components it did not build come
#                         from the newest dev set
#   --local               the packages of your own ./build.sh, from
#                         build/artifacts/<os>/
#
#   --mock                cognos-cxl-mock instead of cognos-cxl
#
# Only runtime packages are copied: no -dev/-devel packages, and one cxl
# variant. Existing cognos-* packages in deploy/artifacts/SVK/ are removed
# first, so the playbooks install exactly this set. ol10 also needs
# cognos-grpc, which is not built in this repository; it is downloaded from
# Nexus at GRPC_VERSION.
#
# Environment (defaults in brackets):
#   COGNOS_GITLAB_URL   [https://cxl-gitlab.ssi.samsung.com]
#   COGNOS_PROJECT      [dfs/svk/cognos]
#   GITLAB_TOKEN        only needed if the project or its pipelines are not public
#   NEXUS_URL           [http://ssg-nexus.msl.lab:8081]
#   ARTIFACTS_DIR       [deploy/artifacts/SVK]
#
# Needs bash, curl and python3 (already on an ansible controller).
set -euo pipefail

GRPC_VERSION=1.59.2

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
GITLAB_URL=${COGNOS_GITLAB_URL:-https://cxl-gitlab.ssi.samsung.com}
PROJECT=${COGNOS_PROJECT:-dfs/svk/cognos}
NEXUS_URL=${NEXUS_URL:-http://ssg-nexus.msl.lab:8081}
ARTIFACTS_DIR=${ARTIFACTS_DIR:-$ROOT/deploy/artifacts/SVK}
API="$GITLAB_URL/api/v4/projects/${PROJECT//\//%2F}"

die() {
    echo "fetch-packages.sh: $*" >&2
    exit 1
}

usage() {
    sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
    exit "${1:-0}"
}

OS='' MOCK='' SOURCE='' SOURCE_ARG=''
while [[ $# -gt 0 ]]; do
    case $1 in
        --os | --set | --pipeline)
            [[ $# -ge 2 ]] || die "$1 needs a value"
            if [[ $1 == --os ]]; then OS=$2; else SOURCE=${1#--} SOURCE_ARG=$2; fi
            shift
            ;;
        --local) SOURCE=local ;;
        --mock) MOCK=1 ;;
        -h | --help) usage 0 ;;
        *) die "unknown option $1 (see -h)" ;;
    esac
    shift
done
case $OS in
    ubuntu24) EXT=deb ;;
    ol10) EXT=rpm ;;
    *) die "--os must be ubuntu24 or ol10" ;;
esac
[[ -n $SOURCE ]] || die "give a source: --set, --pipeline or --local (see -h)"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# GitLab API GET; the token is only sent when one is given.
gitlab() {
    local auth=()
    [[ -z ${GITLAB_TOKEN:-} ]] || auth=(--header "PRIVATE-TOKEN: $GITLAB_TOKEN")
    curl --fail --silent --show-error --location --globoff "${auth[@]}" "$@"
}

# Prints the id of the successful job named $2 in pipeline $1.
job_id() {
    gitlab "$API/pipelines/$1/jobs?per_page=100&scope[]=success" \
        | python3 -c 'import json,sys; print(next((str(j["id"]) for j in json.load(sys.stdin) if j["name"] == sys.argv[1]), ""))' "$2"
}

# Downloads the artifacts of job $1 (or of a URL) and extracts them into $2.
extract_artifacts() {
    local url=$1 dir=$2
    [[ $url == http* ]] || url="$API/jobs/$1/artifacts"
    gitlab --output "$WORK/artifacts.zip" "$url"
    python3 -m zipfile -e "$WORK/artifacts.zip" "$dir"
    rm -f "$WORK/artifacts.zip"
}

# Downloads a dev set into $WORK/set and checks every file against set.json.
fetch_set() {
    local which=$1 url
    if [[ $which == latest ]]; then
        url="$API/jobs/artifacts/main/download?job=publish%20dev%20set"
    else
        url=$(job_id "$which" "publish dev set")
        [[ -n $url ]] || die "pipeline $which has no successful \"publish dev set\" job (dev sets are kept for 10 days)"
    fi
    extract_artifacts "$url" "$WORK/set"
    python3 - "$WORK/set/dev-set" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
s = json.loads((root / "set.json").read_text())
for p in s["packages"]:
    if hashlib.sha256((root / p["file"]).read_bytes()).hexdigest() != p["sha256"]:
        sys.exit(f"checksum mismatch: {p['file']}")
print(f"Dev set {s['version']} (pipeline {s['pipeline']}, {s['created']}): checksums OK")
PY
    cp "$WORK/set/dev-set/$OS"/*."$EXT" "$WORK/packages/"
}

# Downloads the packages of pipeline $1's build jobs for $OS into $WORK/pipeline.
fetch_pipeline() {
    local jobs id
    jobs=$(gitlab "$API/pipelines/$1/jobs?per_page=100&scope[]=success" \
        | python3 -c '
import json, sys
os_name, variant = sys.argv[1], sys.argv[2]
for j in json.load(sys.stdin):
    name = j["name"]
    if name.startswith("build ") and " image" not in name and name.endswith("]") and (
            name.endswith(f"[{os_name}]") or name.endswith(f"[{os_name}, {variant}]")):
        print(j["id"], name)' "$OS" "$([[ -n $MOCK ]] && echo mock || echo release)")
    [[ -n $jobs ]] || die "pipeline $1 has no successful build jobs for $OS"
    while read -r id name; do
        echo "  pipeline $1: $name"
        extract_artifacts "$id" "$WORK/pipeline/$id"
    done <<< "$jobs"
}

# $WORK/packages: the base packages; $WORK/overlay: packages that replace base
# packages of the same name (a pipeline's builds over the dev set).
mkdir -p "$WORK/packages" "$WORK/overlay"
case $SOURCE in
    set) fetch_set "$SOURCE_ARG" ;;
    local)
        compgen -G "$ROOT/build/artifacts/$OS/*.$EXT" > /dev/null || die "no packages in build/artifacts/$OS; run ./build.sh --os $OS first"
        cp "$ROOT/build/artifacts/$OS"/*."$EXT" "$WORK/packages/"
        ;;
    pipeline)
        [[ $SOURCE_ARG =~ ^[0-9]+$ ]] || die "--pipeline needs a pipeline id"
        echo "Components not built in pipeline $SOURCE_ARG come from the newest dev set."
        (fetch_set latest) || echo "WARNING: no dev set available; only the pipeline's packages are used."
        fetch_pipeline "$SOURCE_ARG"
        find "$WORK/pipeline" -name "*.$EXT" -exec cp {} "$WORK/overlay/" \;
        ;;
esac

# The runtime packages of one cxl variant, one file per package name; an
# overlay package wins over a base package of the same name.
python3 - "$EXT" "${MOCK:+mock}" "$WORK/packages" "$WORK/overlay" > "$WORK/selected" <<'PY'
import os, re, sys
ext, mock, directories = sys.argv[1], sys.argv[2] == "mock", sys.argv[3:]
chosen = {}
for directory in directories:
    for f in sorted(os.listdir(directory)):
        m = re.match(r"^([a-z0-9-]+?)(_|-[0-9])", f)
        if not m or not f.endswith("." + ext):
            continue
        name = m.group(1)
        if name.endswith(("-dev", "-devel")):
            continue
        if name in ("cognos-cxl", "cognos-cxl-mock") and (name == "cognos-cxl-mock") != mock:
            continue
        chosen[name] = os.path.join(directory, f)
for name in sorted(chosen):
    print(chosen[name])
PY
[[ -s $WORK/selected ]] || die "no $OS packages found"

mkdir -p "$ARTIFACTS_DIR"
find "$ARTIFACTS_DIR" -maxdepth 1 -name "cognos-*.$EXT" -print -delete | sed 's/^/  removed old /'
while read -r f; do
    cp "$f" "$ARTIFACTS_DIR/"
done < "$WORK/selected"

if [[ $OS == ol10 ]]; then
    echo "cognos-grpc $GRPC_VERSION from Nexus"
    url=$(curl --fail --silent --show-error --max-time 30 \
        "$NEXUS_URL/service/rest/v1/search/assets?repository=svk_yum_ol10&name=cognos-grpc&version=$GRPC_VERSION" \
        | python3 -c 'import json,sys; print(next((a["downloadUrl"] for a in json.load(sys.stdin)["items"] if a["downloadUrl"].endswith(".rpm")), ""))')
    [[ -n $url ]] || die "cognos-grpc $GRPC_VERSION not found in Nexus (svk_yum_ol10)"
    curl --fail --silent --show-error --output "$ARTIFACTS_DIR/${url##*/}" "$url"
fi

echo "Packages in $ARTIFACTS_DIR:"
find "$ARTIFACTS_DIR" -maxdepth 1 -name "*.$EXT" -printf '  %f\n' | sort
