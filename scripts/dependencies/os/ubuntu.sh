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
        python3-virtualenv
        tar
        unzip
        wget
        rapidjson-dev
        libnuma-dev
        libfmt-dev
        rasdaemon
        flex
        bison
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

# Install SVK APT Repo (Nexus)
configure_nexus() {
    NEXUS_BASE_URL=http://ssg-nexus.msl.lab:8081
    NEXUS_COMMON_URL="$NEXUS_BASE_URL/repository/svk_common"
    NEXUS_APT_URL="$NEXUS_BASE_URL/repository/svk_apt_$ID${VERSION_ID%%.*}"
    NEXUS_PUBKEY_PATH=/usr/share/keyrings/ssg-nexus.pgp

    wget --no-verbose --output-document $NEXUS_PUBKEY_PATH  $NEXUS_COMMON_URL/public.pgp
    echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=$NEXUS_PUBKEY_PATH] \
    $NEXUS_APT_URL $UBUNTU_CODENAME main" > /etc/apt/sources.list.d/ssg-nexus.list
    apt-get update

    # Install svk-core packages from Nexus
    BUILD_DEPS=(
        svk-core
        svk-core-dev
    )
    package_manager
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
configure_nexus
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
