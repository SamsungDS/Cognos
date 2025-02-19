#! /usr/bin/env bash
set -e

# Path variables
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REQUIREMENTS=$(realpath "$SCRIPT_DIR/../python/requirements.txt")
VENV_DIR=/usr/local/svk/ras/venv

# Create python venv if it does not exist
if [[ ! -d $VENV_DIR ]]; then
    echo "Creating Python virtual environment at $VENV_DIR"
    virtualenv $VENV_DIR
else
    echo "Python virtual environment already exists at $VENV_DIR"
fi

# Activate Python virtual environment
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# Ensure pip is latest
python3 -m pip install --upgrade pip

# Install python modules from requirements.txt
PIP_ARGS=(
    -r
    "$REQUIREMENTS"
)

# Optimizations for Docker build - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
if [[ $DOCKER ]]; then
    PIP_ARGS+=(--no-cache-dir)
fi

# Install python modules from requirements.txt via pip
INSTALL_STRING="python3 -m pip install ${PIP_ARGS[*]}"
echo "executing command: $INSTALL_STRING"
eval "$INSTALL_STRING"

# Set git safe.directory globally if docker
if [[ $DOCKER ]]; then
    git config --global --add safe.directory '*'
fi
