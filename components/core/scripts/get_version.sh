#!/usr/bin/env bash
# Determine the version from git tags and output a version string
# This script serves as a central location to define the git command for scripts, cmake, etc.
set -eu

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")

# Get the version from git tag, this works from anywhere since we point to PROJECT_ROOT
GIT_VERSION=$(git -C "$PROJECT_ROOT" describe --abbrev=4 --always --tags)

# Output the version
echo "$GIT_VERSION"
