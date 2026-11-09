#!/usr/bin/env bash
# Determine the version from git tags and output a version string
# This script serves as a central location to define the git command for scripts, cmake, etc.
set -eu

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
GIT_DIR=$(realpath "$SCRIPT_DIR/..")

# Default variables
NO_V=false
SHORT=false

help()
{
    # Exit with 0 by default - otherwise used passed value
    local EXIT_CODE="${1-0}"

    # Display Help
    echo "Determine the version from git tags and output a version string"
    echo
    echo "Syntax: get_version.sh [-v|s|g|h]"
    echo "options:"
    echo "-v | --no-v"
    echo "  Return version string without the preceding 'v' character."
    echo "-s | --short"
    echo "  Return short version string, just <MAJOR.MINOR.PATCH>."
    echo "-g | --git-dir"
    echo "  Specify the path to the git dir."
    echo "  By default: $GIT_DIR"
    echo "-h | --help"
    echo "  Print this help."
    exit "$EXIT_CODE"
}

parse_options()
{
    while [[ $# -gt 0 ]];
    do
    case $1 in
        -v|--no-v)
        NO_V=true
        shift
        ;;
        -s|--short)
        SHORT=true
        shift
        ;;
        -g|--git-dir)
        if [[ $# -lt 2 ]]; then
            echo "Error: Missing argument for --git-dir" >&2
            exit 1
        fi
        GIT_DIR="$2"
        shift 2
        ;;
        -h|--help)
        help
        ;;
        *)
        echo "Invalid option provided. See usage details below:"
        help 1
        ;;
    esac
    done
}

parse_options "$@"

# Get the version from COGNOS_VERSION if set, else from git tag
GIT_VERSION=${COGNOS_VERSION:+v$COGNOS_VERSION}
[[ -n $GIT_VERSION ]] || GIT_VERSION=$(git -C "$GIT_DIR" describe --abbrev=4 --always --tags)

if [[ $NO_V == true || $SHORT == true ]]; then
    # strip the 'v'
    GIT_VERSION="${GIT_VERSION/v/}"
fi
if [[ $SHORT == true ]]; then
    # strip everything after patch integer
    GIT_VERSION="${GIT_VERSION/-*/}"
    GIT_VERSION="${GIT_VERSION%%\~*}"
fi

echo "$GIT_VERSION"
