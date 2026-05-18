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
        libfmt-dev
        libjansson-dev
	    libnuma-dev
        libpci-dev
	    libspdlog-dev
        libssl-dev
        libyaml-cpp-dev
        libzmq3-dev
        net-tools
        pkgconf
        python3.11
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
    BUILD_DEPS=()
    apt-get update

    # Install cognos-core, cognos-extras packages from Nexus
    BUILD_DEPS=(
        cognos-core
        cognos-core-dev
        cognos-mgmt-fw
        cognos-mgmt-fw-dev
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
