#! /usr/bin/env bash
set -e

# Build Dependencies
define_build_deps() {
    BUILD_DEPS=()
    BUILD_DEPS+=('cmake')
    BUILD_DEPS+=('g++')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('libboost-dev')
    BUILD_DEPS+=('libfmt8')
    BUILD_DEPS+=('libfmt-dev')
    BUILD_DEPS+=('libspdlog-dev')
    BUILD_DEPS+=('libssl-dev')
    BUILD_DEPS+=('net-tools')
    BUILD_DEPS+=('pkgconf')
    BUILD_DEPS+=('python3.11')
    BUILD_DEPS+=('python3-pip')
    BUILD_DEPS+=('tar')
    BUILD_DEPS+=('unzip')
    BUILD_DEPS+=('wget')
    install_packages
}

# Install from package mananger
install_packages() {
    INSTALLER_BIN="apt-get"
    # Run apt-get update to update the package repo cache
    INSTALL_STRING="$INSTALLER_BIN update"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"

    INSTALL_STRING="$INSTALLER_BIN install -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"

    GO_PKG="go1.21.7.linux-amd64.tar.gz"

    if [ ! -f "$GO_PKG" ]; then
        wget "https://go.dev/dl/$GO_PKG"
    fi
    tar -zxvf go1.21.7.linux-amd64.tar.gz  -C /usr/local
}

define_build_deps

# Farther cleanup if Docker environment
if [[ -f /.dockerenv ]]
then
    CLEANUP_STRING="$INSTALLER_BIN clean all"
    echo "executing command: $CLEANUP_STRING"
    eval "$CLEANUP_STRING"
fi
