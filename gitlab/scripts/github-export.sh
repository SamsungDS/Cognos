#!/usr/bin/env bash
# Makes the history that goes to GitHub from this repository's: the same commits, authors, dates and files, except
#   - files larger than 100 MB, which GitHub refuses, are removed from every commit (a commit left with no change
#     goes);
#   - e-mail addresses are removed from the commit messages: "Signed-off-by: Name <address>" keeps the name, any
#     other address becomes "[e-mail removed]".
# The same input always gives the same commits, so an export of a newer <branch> adds commits on top of the last one
# and pushes to GitHub as a fast-forward.
#
# Usage: gitlab/scripts/github-export.sh <repository> <branch> <out>
#   <repository>  a path or URL to clone from, e.g. . (this checkout)
#   <branch>      the branch to export, e.g. main; only that branch, no tags
#   <out>         a new directory: the exported repository (bare), with <branch> only
#
# Needs git and git-filter-repo (FILTER_REPO, default git-filter-repo on PATH). MAX_FILE_SIZE (default 100M) is for
# the tests. After the export it checks the result and fails if a large file or an e-mail address is left.
set -euo pipefail

die() {
    echo "github-export.sh: $*" >&2
    exit 1
}

[[ $# -eq 3 ]] || die "usage: github-export.sh <repository> <branch> <out>"
SRC=$1 BRANCH=$2 OUT=$3
FILTER_REPO=${FILTER_REPO:-git-filter-repo}
MAX_FILE_SIZE=${MAX_FILE_SIZE:-100M}
command -v "$FILTER_REPO" > /dev/null || die "git-filter-repo not found (set FILTER_REPO)"
[[ ! -e $OUT ]] || die "$OUT exists already"

case $MAX_FILE_SIZE in
    *K) MAX_BYTES=$((${MAX_FILE_SIZE%K} * 1024)) ;;
    *M) MAX_BYTES=$((${MAX_FILE_SIZE%M} * 1024 * 1024)) ;;
    *) MAX_BYTES=$MAX_FILE_SIZE ;;
esac
# An address: local part, @, a domain with at least one dot.
EMAIL='[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+'

git clone --quiet --bare --no-local --single-branch --branch "$BRANCH" --no-tags "$SRC" "$OUT"
cd "$OUT"
before=$(git rev-list --count "$BRANCH")

RULES=$(mktemp)
trap 'rm -f "$RULES"' EXIT
cat > "$RULES" << EOF
regex:[ \t]*<${EMAIL}>==>
regex:${EMAIL}==>[e-mail removed]
EOF
"$FILTER_REPO" --quiet --strip-blobs-bigger-than "$MAX_FILE_SIZE" --replace-message "$RULES"

after=$(git rev-list --count "$BRANCH")
echo "$BRANCH: $before commits, $after exported ($((before - after)) left with no change)"

# The checks: nothing larger than the limit, no address in any message.
large=$(git rev-list --objects "$BRANCH" | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' |
    awk -v max="$MAX_BYTES" '$1 == "blob" && $2 > max {print "  " $2 " bytes: " $3}')
[[ -z $large ]] || die "files larger than $MAX_FILE_SIZE are left:"$'\n'"$large"
addresses=$(git log "$BRANCH" --format=%B | grep -cE "$EMAIL" || true)
[[ $addresses -eq 0 ]] || die "$addresses e-mail addresses are left in commit messages"
echo "checked: no file larger than $MAX_FILE_SIZE, no e-mail address in the commit messages"
