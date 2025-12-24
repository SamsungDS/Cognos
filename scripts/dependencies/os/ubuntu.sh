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

install_packages
configure_nexus

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
