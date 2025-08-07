#! /usr/bin/env bash
set -e

# Path variables
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PYTHON_REQUIREMENTS=$(realpath "$SCRIPT_DIR/../python/requirements.txt")

# Upgrade pip to the latest version
python3 -m pip install pip --upgrade

# Install python modules from requirements.txt
PIP_ARGS=()
PIP_ARGS+=("-r")
PIP_ARGS+=("$PYTHON_REQUIREMENTS")

# Optimizations for Docker build
if [[ -f /.dockerenv ]]
then
    PIP_ARGS+=("--no-cache-dir")
fi

# Install python modules from requirements.txt via pip
INSTALL_STRING="python3 -m pip install ${PIP_ARGS[*]}"
echo "executing command: $INSTALL_STRING"
eval "$INSTALL_STRING"

# Set git safe.directory globally if docker
if $DOCKER; then
    git config --global --add safe.directory '*'
fi
