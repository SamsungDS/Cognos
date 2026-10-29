#!/bin/sh
# Makes sure the build image of one component exists for this commit.
#
# Usage: ci/image.sh <component dir> <os> <image repository> <commit>
#
# An image depends only on scripts/docker/<os>.DOCKERFILE and scripts/dependencies/
# of its component, so it is tagged by those: <os>-deps-<hash>.
#   - That tag exists: nothing is built; it is also tagged <os>-<commit>.
#   - It does not: the image is built and pushed as <os>-deps-<hash> and <os>-<commit>.
# Build and test jobs use <os>-<commit>.
#
# Needs git, and docker with buildx, logged in to the registry.
set -eu

[ $# -eq 4 ] || { echo "usage: ci/image.sh <component dir> <os> <image repository> <commit>" >&2; exit 1; }
dir=$1 os=$2 repo=$3 commit=$4
dockerfile=$dir/scripts/docker/$os.DOCKERFILE

# The git object ids of the two inputs, hashed together.
hash=$(git rev-parse "HEAD:$dockerfile" "HEAD:$dir/scripts/dependencies" | git hash-object --stdin | cut -c1-12)
content_tag=$repo:$os-deps-$hash
commit_tag=$repo:$os-$commit

if docker buildx imagetools inspect "$content_tag" > /dev/null 2>&1; then
    echo "Reusing $content_tag: $dockerfile and $dir/scripts/dependencies are unchanged."
    docker buildx imagetools create --tag "$commit_tag" "$content_tag"
else
    echo "Building $content_tag: no image yet for this $dockerfile and $dir/scripts/dependencies."
    docker buildx build --file "$dockerfile" --tag "$content_tag" --tag "$commit_tag" \
        --push --provenance false "$dir"
fi
echo "Image for this commit: $commit_tag"
