#! /usr/bin/env bash
set -e

# Build Dependencies
<<<<<<< HEAD
install_packages() {
    apt-get update
    BUILD_DEPS=(
        build-essential
        cmake
        debhelper
        diffutils
        dpkg-dev
        dstat
	file
        g++
        git
        libboost-dev
        libfmt-dev
        libjansson-dev
	libnuma-dev
	libspdlog-dev
        libssl-dev
        libzmq3-dev
        net-tools
        pkgconf
        python3.11
        python3-pip
        tar
        unzip
        wget
    )
    package_manager
=======
install_build_deps() {
  BUILD_DEPS=()
  package_manager 'update'
  BUILD_DEPS+=('cmake')
  BUILD_DEPS+=('dpkg-dev')
  BUILD_DEPS+=('debhelper')
  BUILD_DEPS+=('diffutils')
  BUILD_DEPS+=('dstat')
  BUILD_DEPS+=('file')
  BUILD_DEPS+=('g++')
  BUILD_DEPS+=('git')
  BUILD_DEPS+=('libboost-dev')
  BUILD_DEPS+=('libjansson-dev')
  BUILD_DEPS+=('libjansson4')
  BUILD_DEPS+=('libjansson-doc')
  BUILD_DEPS+=('libfmt8')
  BUILD_DEPS+=('libfmt-dev')
  BUILD_DEPS+=('libnuma-dev')
  BUILD_DEPS+=('libspdlog-dev')
  BUILD_DEPS+=('libssl-dev')
  BUILD_DEPS+=('libzmq3-dev')
  BUILD_DEPS+=('net-tools')
  BUILD_DEPS+=('pkgconf')
  BUILD_DEPS+=('python3.11')
  BUILD_DEPS+=('python3-pip')
  BUILD_DEPS+=('tar')
  BUILD_DEPS+=('unzip')
  BUILD_DEPS+=('wget')
  package_manager 'install'
>>>>>>> 46a4331 (FAM-1432: Host metrics collection implementation and support.)
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

    # Install svk-core, svk-extras packages from Nexus
    BUILD_DEPS=(
        svk-core
        svk-core-dev
        svk-mgmt-fw
        svk-mgmt-fw-dev
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
