#! /usr/bin/env bash
set -e

# Path variables
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REQUIREMENTS=$(realpath "$SCRIPT_DIR/../python/requirements.txt")

# Install python3 pip
UBUNTU_VER=${VERSION_ID%%.*}
if [ "$UBUNTU_VER" == "24" ]; then
    # PEP 668 - workaround
    # This is not required for the Ubuntu 24 as the pip is installed as the deb package
    # python3 -m pip install --break-system-packages --upgrade pip
    echo ""
else
    python3 -m pip install --upgrade pip
fi

# Install python modules from requirements.txt
PIP_ARGS=(
    '-r'
    "$REQUIREMENTS"
)

# Optimizations for Docker build
if [[ $DOCKER ]]
then
    PIP_ARGS+=("--no-cache-dir")
fi

if [ "$UBUNTU_VER" == "24" ]; then
    PIP_ARGS+=("--break-system-packages")
fi

# Install python modules from requirements.txt via pip
INSTALL_STRING="python3 -m pip install ${PIP_ARGS[*]}"
echo "executing command: $INSTALL_STRING"
eval "$INSTALL_STRING"

# Set git safe.directory globally if docker
if [[ $DOCKER ]]
then
    git config --global --add safe.directory '*'
fi
