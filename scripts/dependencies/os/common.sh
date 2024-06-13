#! /usr/bin/env bash
set -e

GRPC_REPO_BRANCH="v1.59.2"

# Path variables
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REQUIREMENTS=$(realpath "$SCRIPT_DIR/../python/requirements.txt")

# Install python3 pip
python3 -m ensurepip --upgrade

# Install python modules from requirements.txt
PIP_ARGS=()
PIP_ARGS+=("-r")
PIP_ARGS+=("$REQUIREMENTS")

# Optimizations for Docker build
if [[ -f /.dockerenv ]]
then
    PIP_ARGS+=("--no-cache-dir")
fi

# Install python modules from requirements.txt via pip
INSTALL_STRING="python3 -m pip install ${PIP_ARGS[*]}"
echo "executing command: $INSTALL_STRING"
eval "$INSTALL_STRING"

# Download the grpc branch, compile the grpc and install to the default installation path /usr/local
if [[ -d /usr/local/include/grpcpp ]]; then
    echo "gRPC is already installed. Skipping ..."
else
    GRPC_DIR="grpc_$GRPC_REPO_BRANCH"
    if [[ ! -d "$GRPC_DIR" ]]; then
        git clone --branch "$GRPC_REPO_BRANCH" https://github.com/grpc/grpc --single-branch "$GRPC_DIR"
    fi
    pushd "$GRPC_DIR"
        git submodule update --init
        BUILD_DIR=cmake/build

        # Remove build dir if it exists
        if [[ -d cmake/build ]]; then
            rm -rf "$BUILD_DIR"
        fi
        mkdir "$BUILD_DIR"
        pushd "$BUILD_DIR"
            cmake ../..
            make "-j$(nproc)"
            make install
        popd
        # Install re2 if missing
        if [[ -d /usr/local/lib/pkgconfig/re2.pc ]]; then
            echo "re2 is already installed. Skipping ..."
        else
            pushd third_party/re2
                make install
                echo "/usr/local/lib" > /etc/ld.so.conf.d/grpc_re2.conf
            popd
        fi
    popd
fi

# Set git safe.directory globally if docker
if [[ -f /.dockerenv ]]
then
    git config --global --add safe.directory '*'
fi
