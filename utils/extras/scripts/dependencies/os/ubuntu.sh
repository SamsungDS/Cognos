#! /usr/bin/env bash
set -e

GO_VERSION=1.22

# Build Dependencies
install_build_deps() {
    apt-get update
    BUILD_DEPS=(
        cmake
        debhelper
        devscripts
        g++
        git
        "golang-$GO_VERSION-go"
        libc-ares-dev
        libgoogle-glog-dev
        libssl-dev
        python3
        python3-venv
        sudo
        tar
        wget
        zlib1g-dev
    )
    package_manager
}

# Install from package mananger
package_manager() {
    local OPERATION=$1
    # Detect package manager tool
    local INSTALLER_BIN=''

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
}

install_build_deps
set_go_path
