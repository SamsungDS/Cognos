#! /usr/bin/env bash
set -e

MAJOR_VER=${VERSION_ID%%.*}

# Build Dependencies
install_packages() {
    BUILD_DEPS=(
        dnf
        oracle-epel-release-el"${MAJOR_VER}"
    )
    package_manager

    # Add NodeJS 21 repo
    curl -fsSL https://rpm.nodesource.com/setup_22.x | bash

    # Enable CodeReady Builder (CRB) repository
    BUILD_DEPS=("'dnf-command(config-manager)'")
    package_manager
    dnf config-manager --enable ol"${MAJOR_VER}"_codeready_builder

    BUILD_DEPS=(
        chromedriver
        chromium
        findutils
        git
        nodejs
        python3
        python3-pip
        python3
        rpmdevtools
    )
    package_manager
}

# Install from package mananger
package_manager() {
    # Optimizations for Docker build  - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
    if $DOCKER; then
        BUILD_DEPS+=(
            --nodocs
            --noplugins
            --setopt=install_weak_deps=0
        )
    fi

    # Detect package installer
    INSTALLER_BIN=""

    if [[ -f '/usr/bin/dnf' ]]; then
        INSTALLER_BIN='dnf'
    elif [[ -f '/usr/bin/microdnf' ]]; then
        INSTALLER_BIN='microdnf'
    else
        # Can't find an appropriate installer
        echo "can't find a valid installer"
        exit 1
    fi

    echo "using $INSTALLER_BIN"

    INSTALL_STRING="$INSTALLER_BIN install -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

install_packages

# Farther cleanup if Docker environment
if $DOCKER; then
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
