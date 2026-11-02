#!/usr/bin/env bash
# Read-only smoke tests against this GitLab, run by the "test ci" job (gitlab/scripts/tests/run.sh --smoke).
# They check what the unit tests cannot: that this pipeline's environment reaches GitLab with the CI CA setup, with
# git (release tags), Python (the API) and downloads (the dev set). They change nothing.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"
: "${CI_API_V4_URL:?smoke tests run in CI only}"

fail() {
    echo "SMOKE TEST FAILED: $*" >&2
    exit 1
}

echo "-- git reads origin's tags"
tags=$(git ls-remote --tags origin) || fail "git ls-remote origin failed (the internal CA for git?)"
[[ -n $tags ]] || fail "origin has no tags"

echo "-- ci/version.sh --next-patch follows the highest released patch of the VERSION line"
next=$(ci/version.sh --next-patch) || fail "ci/version.sh --next-patch failed"
x_y=$(cat VERSION)
highest=-1
while read -r _ ref; do
    patch=${ref##*/v"$x_y".}
    [[ $ref == */v"$x_y".* && $patch =~ ^[0-9]+$ ]] || continue
    ((patch > highest)) && highest=$patch
done <<< "$tags"
[[ $next == "$x_y.$((highest + 1))" ]] || fail "next patch is $next, expected $x_y.$((highest + 1))"
echo "   $next"

echo "-- gitlab/scripts/api.py reads this pipeline's jobs"
gitlab/scripts/api.py job-results --pipeline "$CI_PIPELINE_ID" > /dev/null || fail "api.py job-results failed"

echo "-- the newest dev set downloads and its checksums match"
dest=$(mktemp -d)
trap 'rm -rf "$dest"' EXIT
if ARTIFACTS_DIR=$dest COGNOS_GITLAB_URL=$CI_SERVER_URL COGNOS_PROJECT=$CI_PROJECT_PATH \
    deploy/scripts/fetch-packages.py --os ubuntu24 --set latest --only core > "$dest.log" 2>&1; then
    grep -q "checksums OK" "$dest.log" || fail "no checksum confirmation: $(cat "$dest.log")"
    compgen -G "$dest/cognos-core_*.deb" > /dev/null || fail "no cognos-core package downloaded"
elif grep -q "no dev set available" "$dest.log"; then
    echo "   no dev set yet: skipped"
else
    fail "fetch-packages.py: $(tail -n 3 "$dest.log")"
fi
rm -f "$dest.log"
echo "smoke tests passed"
