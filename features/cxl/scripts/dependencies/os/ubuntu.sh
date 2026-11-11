#! /usr/bin/env bash
set -e

# Build Dependencies
install_packages() {
    apt-get update
    BUILD_DEPS=(
        build-essential
        cmake
        cgroup-tools
        curl
        debhelper
        diffutils
        dpkg-dev
        file
        g++
        git
        libboost-dev
        libcxl-dev
        libdaxctl-dev
        libfmt-dev
        libjansson-dev
        libndctl-dev
        libnuma-dev
        libpci-dev
        libspdlog-dev
        libssl-dev
        libyaml-cpp-dev
        libzmq3-dev
        net-tools
        pkgconf
        python3
        python3-venv
        pybind11-dev
        python3-dev
        python3-pip
        python3-pybind11
        sudo
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
