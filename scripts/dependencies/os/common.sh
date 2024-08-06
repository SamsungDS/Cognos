#! /usr/bin/env bash
set -e

# Path variables
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REQUIREMENTS=$(realpath "$SCRIPT_DIR/../python/requirements.txt")

# Install python3 pip
python3 -m pip install --upgrade pip

# Install python modules from requirements.txt
PIP_ARGS=()
PIP_ARGS+=("-r")
PIP_ARGS+=("$REQUIREMENTS")

# Optimizations for Docker build
if [[ $DOCKER ]]
then
    PIP_ARGS+=("--no-cache-dir")
fi

# Install python modules from requirements.txt via pip
INSTALL_STRING="python3 -m pip install ${PIP_ARGS[*]}"
echo "executing command: $INSTALL_STRING"
eval "$INSTALL_STRING"

# Download grpc tarball from Nexus and install to /usr/local
if [[ -d /usr/local/include/grpcpp ]]; then
    echo "gRPC is already installed. Skipping ..."
else
    GRPC_VERSION="1.59.2"
    GRPC_TARBALL="grpc-${GRPC_VERSION}_$ID${VERSION_ID%%.*}.tar.gz"
    GRPC_TARBALL_URL="http://ssg-nexus.msl.lab:8081/repository/svk_common/$GRPC_TARBALL"
    GRPC_INSTALL_DIR=/
    wget --no-verbose "$GRPC_TARBALL_URL"
    echo "Extracting $GRPC_TARBALL to $GRPC_INSTALL_DIR"
    tar xzf "$GRPC_TARBALL" --directory="$GRPC_INSTALL_DIR"
    rm -rfv "$GRPC_TARBALL"
    ldconfig
fi

# Set git safe.directory globally if docker
if [[ $DOCKER ]]
then
    git config --global --add safe.directory '*'
fi
