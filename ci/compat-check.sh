#!/usr/bin/env bash
# Proposes the next release as major or minor, by comparing with the last release.
#
# Usage: ci/compat-check.sh --base <tag> --old <dir> --new <dir> --report <file>
#   --base     the last release (a tag, e.g. v1.6.3); its protos are read from git
#   --old      that release's ubuntu24 packages (.deb)
#   --new      the packages to release (.deb), e.g. the newest dev set
#   --report   where to write the findings (Markdown)
#
# Prints "major" if a public interface broke, else "minor":
#   - mgmt-fw's gRPC API (features/mgmt-fw/proto/framework): buf breaking against --base;
#   - every shared library in the packages: abidiff, old against new (an incompatible ABI change).
# A check that cannot run is reported and counts as no break: the reviewer of the release merge request decides.
#
# Run from anywhere in the repository. Needs git (with the --base tag), buf, abidiff (abigail-tools) and dpkg-deb.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PROTO_DIR=features/mgmt-fw/proto
# The framework protos import google/api and protoc-gen-openapiv2 from third_party/.
BUF_CONFIG='{"version":"v2","modules":[{"path":"framework"},{"path":"third_party"}],"breaking":{"use":["FILE"]}}'

die() {
    echo "ci/compat-check.sh: $*" >&2
    exit 1
}

BASE='' OLD='' NEW='' REPORT=''
while [[ $# -gt 0 ]]; do
    [[ $# -ge 2 ]] || die "$1 needs a value"
    case $1 in
        --base) BASE=$2 ;;
        --old) OLD=$2 ;;
        --new) NEW=$2 ;;
        --report) REPORT=$2 ;;
        *) die "unknown option $1" ;;
    esac
    shift 2
done
[[ -n $BASE && -d $OLD && -d $NEW && -n $REPORT ]] || die "usage: --base <tag> --old <dir> --new <dir> --report <file>"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
BREAK=''
{
    echo "Compared with \`$BASE\`."
    echo
    echo "### gRPC API (\`$PROTO_DIR/framework\`)"
    echo
    rc=0
    # The release's protos, unpacked: both sides are then plain directories with the same layout.
    mkdir -p "$WORK/base"
    if git -C "$ROOT" archive "$BASE" "$PROTO_DIR" | tar -x -C "$WORK/base" 2> "$WORK/buf.txt"; then
        (cd "$ROOT/$PROTO_DIR" && buf breaking . --config "$BUF_CONFIG" --against "$WORK/base/$PROTO_DIR" \
            --against-config "$BUF_CONFIG") >> "$WORK/buf.txt" 2>&1 || rc=$?
    else
        rc=1
    fi
    if [[ $rc -eq 0 ]]; then
        echo "No breaking changes."
    elif [[ $rc -eq 100 ]]; then
        BREAK=1
        echo "**Breaking changes:**"
        echo
        echo '```'
        cat "$WORK/buf.txt"
        echo '```'
    else
        echo "Could not check (buf exit $rc):"
        echo
        echo '```'
        tail -n 20 "$WORK/buf.txt"
        echo '```'
    fi
    echo
    echo "### Shared libraries (abidiff)"
    echo
    for side in old new; do
        dir=$OLD
        [[ $side == old ]] || dir=$NEW
        mkdir -p "$WORK/$side"
        for deb in "$dir"/*.deb; do
            [[ -e $deb ]] && dpkg-deb -x "$deb" "$WORK/$side"
        done
    done
    found=''
    while IFS= read -r old_lib; do
        key=$(basename "$old_lib" | sed 's/\.so.*$/.so/')
        new_lib=$(find "$WORK/new" -type f -name "${key}*" | head -n 1)
        found=1
        if [[ -z $new_lib ]]; then
            BREAK=1
            echo "- \`$key\`: **removed**"
            continue
        fi
        rc=0
        abidiff --no-show-locs "$old_lib" "$new_lib" > "$WORK/abi.txt" 2>&1 || rc=$?
        if ((rc & 8)); then
            BREAK=1
            echo "- \`$key\`: **incompatible change**"
            echo
            echo '  ```'
            head -n 40 "$WORK/abi.txt" | sed 's/^/  /'
            echo '  ```'
        elif ((rc & 3)); then
            echo "- \`$key\`: could not compare (abidiff exit $rc): $(tail -n 1 "$WORK/abi.txt")"
        elif ((rc & 4)); then
            echo "- \`$key\`: compatible changes"
        else
            echo "- \`$key\`: unchanged"
        fi
    done < <(find "$WORK/old" -type f -name '*.so*' | sort)
    [[ -n $found ]] || echo "No shared libraries found in $OLD."
    echo
    if [[ -n $BREAK ]]; then
        echo "**Proposed: major** (a public interface broke)."
    else
        echo "**Proposed: minor** (no break found)."
    fi
} > "$REPORT"

cat "$REPORT" >&2
if [[ -n $BREAK ]]; then echo major; else echo minor; fi
