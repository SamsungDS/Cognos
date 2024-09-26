#! /usr/bin/env bash
set -e

# Build Dependencies
install_packages() {
    BUILD_DEPS=(
        dnf
        epel-release
    )
    package_manager

    # Enable CodeReady Builder (CRB) repository
    BUILD_DEPS=("'dnf-command(config-manager)'")
    package_manager
    /usr/bin/crb enable

    BUILD_DEPS=(
        boost-devel
        cmake
        gcc-c++
        git
        python3-virtualenv
        rpmdevtools
        spdlog-devel
        tar
        unzip
        wget
    )
    package_manager
}

# Install from package mananger
package_manager() {
    # Optimizations for Docker build  - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
    if [[ $DOCKER ]]; then
        BUILD_DEPS+=(
            --nodocs
            --noplugins
            --setopt=install_weak_deps=0
        )
    fi

    # Detect package installer
    INSTALLER_BIN=""

    if [[ -f '/usr/bin/dnf' ]]; then
        echo "using dnf"
        INSTALLER_BIN='dnf'
    elif [[ -f '/usr/bin/microdnf' ]]; then
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

install_packages

# Farther cleanup if Docker environment
if [[ $DOCKER ]]; then
    CLEANUP_STRING="$INSTALLER_BIN clean all"
    echo "executing command: $CLEANUP_STRING"
    eval "$CLEANUP_STRING"
    rm -rf /var/lib/dnf/history*
    rm -rf /var/lib/dnf/repos/*
    rm -rf /var/lib/rpm/__db*
    rm -rf /usr/share/man
    rm -rf /usr/share/doc
    rm -rf /usr/share/licenses
    rm -rf /tmp/*
    rm -f /var/log/dnf*
fi
