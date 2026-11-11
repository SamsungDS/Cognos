#! /usr/bin/env bash
set -e


# Build Dependencies
install_packages() {
    apt-get update
    BUILD_DEPS=(
        build-essential
        clang-format
        cmake
        debhelper
        g++
        git
        libboost-dev
        libboost-filesystem-dev
        libboost-program-options-dev
        libfmt-dev
        libspdlog-dev
        pkgconf
        python3-venv
        tar
        unzip
        wget
    )
    package_manager

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
