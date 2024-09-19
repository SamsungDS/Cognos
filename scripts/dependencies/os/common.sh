#! /usr/bin/env bash
set -e

# Path variables
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
REQUIREMENTS=$(realpath "$SCRIPT_DIR/../python/requirements.txt")
JANSSON_VERSION=2.13


# Install python3 pip
python3 -m pip install --upgrade pip

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

# Set git safe.directory globally if docker
if [[ -f /.dockerenv ]]
then
    git config --global --add safe.directory '*'
fi


# Install Jansson if it is not already installed
if [ -f "/usr/local/include/jansson.h" ]; then
    echo "Jansson is installed. Skipping..."
else
    echo "Downloading Jansson"
    wget http://digip.org/jansson/releases/jansson-$JANSSON_VERSION.tar.gz
    tar -xf jansson-$JANSSON_VERSION.tar.gz
	
    echo "Building Jansson"
    pushd jansson-$JANSSON_VERSION
        ./configure
        make
        make install
    popd

    echo "Removing Jansson source code files"
    rm -rf jansson-*
fi
