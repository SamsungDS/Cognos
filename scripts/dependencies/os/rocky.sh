#! /usr/bin/env bash
set -e

# Build Dependencies
define_build_deps() {
    BUILD_DEPS=()
    BUILD_DEPS=('epel-release')
    install_packages
    BUILD_DEPS=()
    BUILD_DEPS+=('boost-devel')
    BUILD_DEPS+=('cmake')
    BUILD_DEPS+=('gcc-c++')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('golang')
    BUILD_DEPS+=('net-tools')
    BUILD_DEPS+=('python3.11')
    BUILD_DEPS+=('python3-pip')
    BUILD_DEPS+=('spdlog-devel')
    BUILD_DEPS+=('tar')
    BUILD_DEPS+=('unzip')
    BUILD_DEPS+=('wget')
    install_packages
}

# Install from package mananger
install_packages() {
    # Optimizations for Docker build
    if [[ -f /.dockerenv ]]
    then
        BUILD_DEPS+=('--nodocs')
        BUILD_DEPS+=('--noplugins')
        BUILD_DEPS+=('--setopt=install_weak_deps=0')
    fi

    # Detect package installer
    INSTALLER_BIN=""

    if [[ -f '/usr/bin/dnf' ]]
    then
        echo "using dnf"
        INSTALLER_BIN='dnf'
    elif [[ -f '/usr/bin/microdnf' ]]
    then
        echo "using microdnf"
        INSTALLER_BIN='microdnf'
    else
        # Can't find an appropriate installer
        echo "can't find a valid installer"
        exit 1
    fi

    INSTALL_STRING="$INSTALLER_BIN install -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

define_build_deps

# Farther cleanup if Docker environment
if [[ -f /.dockerenv ]]
then
    CLEANUP_STRING="$INSTALLER_BIN clean all"
    echo "executing command: $CLEANUP_STRING"
    eval "$CLEANUP_STRING"
    rm -rf "$GRPC_DIR"
    rm -rf /var/lib/dnf/history*
    rm -rf /var/lib/dnf/repos/*
    rm -rf /var/lib/rpm/__db*
    rm -rf /usr/share/man /usr/share/doc /usr/share/licenses /tmp/*
    rm -f /var/log/dnf*
fi
