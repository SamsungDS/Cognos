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
        libboost-thread-dev
        pkg-config
        python3-venv
        tar
        unzip
        wget
        rapidjson-dev
        libnuma-dev
        libpci-dev
        libfmt-dev
        flex
        bison
        libsqlite3-dev
        libtraceevent-dev
        autoconf
        automake
    )
    package_manager
}

# Install from package mananger
package_manager() {
    # Optimizations for Docker build - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
    if [[ $DOCKER ]]; then
        BUILD_DEPS+=(--no-install-recommends)
    fi

    INSTALL_STRING="DEBIAN_FRONTEND=noninteractive apt-get install -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

# Set PATH to include go bin dir
set_go_path() {
    local GO_PROFILE="/etc/profile.d/go-$GO_VERSION.sh"
    echo "export PATH=\$PATH:/usr/lib/go-$GO_VERSION/bin" > "$GO_PROFILE"
    chmod +x "$GO_PROFILE"
    # shellcheck disable=SC1090
    source "$GO_PROFILE"
}

install_packages
set_go_path

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
