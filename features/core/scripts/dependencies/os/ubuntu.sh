#! /usr/bin/env bash
set -e

if [[ -e /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
else
    VERSION_ID=unknown
fi

# Build Dependencies
install_packages() {
    apt-get update
    BUILD_DEPS=(
        build-essential
        clang-format
        cmake
        debhelper
        g++
        gcovr
        git
        libboost-dev
        libfmt-dev
        libspdlog-dev
        libzmq3-dev
        pkg-config
        python3-venv
        tar
        unzip
        wget
    )
    package_manager

    # On Ubuntu 24, the cppzmq-dev needs to be installed explicitly to overcome
    # the issue where this pkg is not installed with the default docker setup
    if [ "${VERSION_ID/22/}" == "$VERSION_ID" ]; then 
        apt-get update
        BUILD_DEPS=(
            cppzmq-dev
        )
        package_manager
    fi
}

# Install from package mananger
package_manager() {
    # Optimizations for Docker build - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
    if [[ $DOCKER ]]; then
        BUILD_DEPS+=('--no-install-recommends')
    fi

    INSTALL_STRING="DEBIAN_FRONTEND=noninteractive apt-get install -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

install_packages

# Post-install Docker optimizations
if [[ $DOCKER ]]; then
    apt-get clean
    rm -rf /var/lib/apt/lists/*
    rm -rf /tmp/*
    rm -rf /var/tmp/*
    rm -rf /usr/share/doc
    rm -rf /usr/share/man
    rm -rf /usr/share/locale
    rm -rf /usr/share/zoneinfo
fi
