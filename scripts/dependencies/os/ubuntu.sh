#! /usr/bin/env bash
set -e

# Build Dependencies
install_build_deps() {
    BUILD_DEPS=()
    package_manager 'update'
    BUILD_DEPS+=('cmake')
    BUILD_DEPS+=('dpkg-dev')
    BUILD_DEPS+=('g++')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('libboost-dev')
    BUILD_DEPS+=('libfmt8')
    BUILD_DEPS+=('libfmt-dev')
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
}

# Install from package mananger
package_manager() {
    OPERATION=$1
    # Detect package manager tool
    INSTALLER_BIN=""

    if [[ -f '/usr/bin/apt-get' ]]
    then
        echo "using apt-get"
        INSTALLER_BIN='apt-get'
    else
        # Can't find an appropriate installer
        echo "can't find a valid installer"
        exit 1
    fi

    INSTALL_STRING="$INSTALLER_BIN $OPERATION -y ${BUILD_DEPS[*]}"
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
    package_manager 'update'

    # Install svk-core-dev package
    BUILD_DEPS=('svk-core-dev')
    package_manager 'install'
}

# Install Go
install_go() {
    GO_PKG="go1.21.7.linux-amd64.tar.gz"

    if [[ ! -f /usr/local/go/bin/go ]]; then
        wget --no-verbose "https://go.dev/dl/$GO_PKG"
        tar -zxvf $GO_PKG --directory=/usr/local
    fi
    rm -fv $GO_PKG
}

install_build_deps
configure_nexus
install_go
