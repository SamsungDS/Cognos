#!/usr/bin/env bash
# Prints the one Cognos version of a build. X.Y is the root VERSION file.
#
# Usage: ci/version.sh [--tag <tag>] [--mr <number>] [--branch <branch>] [--run <number>]
#
#   --tag vX.Y.Z                    X.Y.Z
#   --mr N --run R                  X.(Y+1).0~dev.0.mrN.R
#   --branch release/X.Y --run R    X.Y.(P+1)~rc.R, P = highest vX.Y.P tag on origin (none: X.Y.0~rc.R)
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

TAG='' MR='' BRANCH='' RUN=''
while [[ $# -gt 0 ]]; do
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

if [[ -n $TAG ]]; then
    [[ $TAG =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "tag $TAG is not vX.Y.Z"
    echo "${TAG#v}"
elif [[ -n $MR ]]; then
    echo "$NEXT~dev.0.mr$MR.${RUN:?--run is required with --mr}"
elif [[ $BRANCH == release/* ]]; then
    [[ ${BRANCH#release/} == "$X.$Y" ]] || die "branch $BRANCH, but VERSION is $X.$Y"
    P=$(git -C "$ROOT" ls-remote --tags origin "refs/tags/v$X.$Y.*" \
        | sed -n "s|.*refs/tags/v$X\.$Y\.\([0-9][0-9]*\)$|\1|p" | sort -n | tail -n 1)
    echo "$X.$Y.$((${P:--1} + 1))~rc.${RUN:?--run is required with --branch}"
elif [[ -n $RUN ]]; then
    echo "$NEXT~dev.$RUN"
else
    TAG=$(git -C "$ROOT" tag --points-at HEAD | grep -Ex 'v[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || true)
    if [[ -n $TAG ]]; then echo "${TAG#v}"; else echo "$NEXT~dev.0.local"; fi
fi
