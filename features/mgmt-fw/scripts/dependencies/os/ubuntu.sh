#! /usr/bin/env bash
set -e

GO_VERSION=1.22

# Build Dependencies
install_build_deps() {
    apt-get update
    BUILD_DEPS=(
        'build-essential'
        'cmake'
        'debhelper'
        'dpkg-dev'
        'g++'
        'git'
        "golang-$GO_VERSION-go"
        'libboost-dev'
        'libfmt-dev'
        'libspdlog-dev'
        'libssl-dev'
        'libzmq3-dev'
        'net-tools'
        'pkgconf'
        'python3'
        'python3-pip'
        'python3-venv'
        'libsystemd-dev'
        'tar'
        'unzip'
        'wget'
    )

    # Packages specific for Ubuntu 24
    if [ "${VERSION_ID%%.*}" == "24" ]; then
        BUILD_DEPS+=(
            'cppzmq-dev'
        )
    fi
    package_manager
}

# Install from package mananger
package_manager() {
    # Optimizations for Docker build - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
    if $DOCKER; then
        BUILD_DEPS+=('--no-install-recommends')
    fi

    INSTALL_STRING="apt-get install -y ${BUILD_DEPS[*]}"
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

install_build_deps
set_go_path

# Post-install Docker optimizations
if $DOCKER; then
    apt-get clean
    rm -rf /var/lib/apt/lists/*
    rm -rf /tmp/*
    rm -rf /var/tmp/*
    rm -rf /usr/share/doc
    rm -rf /usr/share/man
    rm -rf /usr/share/locale
    rm -rf /usr/share/zoneinfo
fi
