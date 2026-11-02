#!/usr/bin/env bash
# Prints the one Cognos version of a build. X.Y is the root VERSION file.
#
# Usage: ci/version.sh [--tag <tag>] [--mr <number>] [--branch <branch>] [--run <number>]
#
#   --tag vX.Y.Z                    X.Y.Z
#   --mr N --run R                  X.(Y+1).0~dev.0.mrN.R
#   --branch release/X.Y --run R    X.Y.(P+1)~rc.R, P = highest X.Y patch released so far (none: X.Y.0~rc.R)
#   --next-patch                    X.Y.(P+1): the next release tag of the VERSION line (without the v)
#   --run R                         X.(Y+1).0~dev.R (main, schedules, web runs)
#   no arguments (local build)      the vX.Y.Z tag on HEAD, else X.(Y+1).0~dev.0.local
#
# Empty values count as not given, so CI can pass its variables unconditionally.
# R is the CI run counter (GitLab: pipeline IID).
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

die() {
    echo "ci/version.sh: $*" >&2
    exit 1
}

TAG='' MR='' BRANCH='' RUN='' NEXT_PATCH=''
while [[ $# -gt 0 ]]; do
    if [[ $1 == --next-patch ]]; then
        NEXT_PATCH=1
        shift
        continue
    fi
    [[ $# -ge 2 ]] || die "$1 needs a value"
    case $1 in
        --tag) TAG=$2 ;;
        --mr) MR=$2 ;;
        --branch) BRANCH=$2 ;;
        --run) RUN=$2 ;;
        *) die "unknown option $1" ;;
    esac
    shift 2
done

IFS=. read -r X Y < "$ROOT/VERSION"
[[ $X =~ ^[0-9]+$ && $Y =~ ^[0-9]+$ ]] || die "VERSION must be MAJOR.MINOR"
NEXT="$X.$((Y + 1)).0"

# P + 1, where P is the highest X.Y patch released so far: this repository's
# vX.Y.P tags and the imported component tags (<component>/vX.Y.P), so that no
# version is ever reused. No release yet: 0.
# Fails (never guesses 0) when origin's tags cannot be read.
next_patch() {
    local tags p
    tags=$(git -C "$ROOT" ls-remote --tags origin "refs/tags/v$X.$Y.*" "refs/tags/*/v$X.$Y.*") \
        || die "cannot read the release tags from origin (git ls-remote failed)"
    p=$(sed -n "s|.*refs/tags/\([a-z0-9-]*/\)\{0,1\}v$X\.$Y\.\([0-9][0-9]*\)$|\2|p" <<< "$tags" | sort -n | tail -n 1)
    echo $((${p:--1} + 1))
}

if [[ -n $NEXT_PATCH ]]; then
    PATCH=$(next_patch)
    echo "$X.$Y.$PATCH"
    exit 0
fi

if [[ -n $TAG ]]; then
    [[ $TAG =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "tag $TAG is not vX.Y.Z"
    echo "${TAG#v}"
elif [[ -n $MR ]]; then
    echo "$NEXT~dev.0.mr$MR.${RUN:?--run is required with --mr}"
elif [[ $BRANCH == release/* ]]; then
    [[ ${BRANCH#release/} == "$X.$Y" ]] || die "branch $BRANCH, but VERSION is $X.$Y"
    PATCH=$(next_patch)
    echo "$X.$Y.$PATCH~rc.${RUN:?--run is required with --branch}"
elif [[ -n $RUN ]]; then
    echo "$NEXT~dev.$RUN"
else
    TAG=$(git -C "$ROOT" tag --points-at HEAD | grep -Ex 'v[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || true)
    if [[ -n $TAG ]]; then echo "${TAG#v}"; else echo "$NEXT~dev.0.local"; fi
fi
