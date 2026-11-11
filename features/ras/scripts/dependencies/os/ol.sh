#! /usr/bin/env bash
set -e

# shellcheck disable=SC1091
source "$SCRIPT_DIR"/os/rpm_common.sh

MAJOR_VER=${VERSION_ID%%.*}

# Build Dependencies
install_packages() {
    # Pre-install dependencies
    BUILD_DEPS=(
        dnf
        oracle-epel-release-el"${MAJOR_VER}"
    )
    package_manager

    BUILD_DEPS=("'dnf-command(config-manager)'")
    package_manager
    dnf config-manager --set-enabled "ol${MAJOR_VER}_codeready_builder"

    # Project build dependencies
    # shellcheck disable=SC2034
    BUILD_DEPS=(
        boost-devel
        cmake
        gcc-c++
        git
        python3
        rpmdevtools
        tar
        unzip
        wget
        rapidjson-devel
        numactl-devel
        pciutils-devel
        flex
        bison
        autoconf
        automake
        sqlite-devel
        libtraceevent-devel
    )
    package_manager
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
