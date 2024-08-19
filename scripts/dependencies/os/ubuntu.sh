#! /usr/bin/env bash
set -e

GO_VERSION=1.21

# Build Dependencies
install_build_deps() {
    BUILD_DEPS=()
    package_manager 'update'
    BUILD_DEPS+=('cmake')
    BUILD_DEPS+=('dpkg-dev')
    BUILD_DEPS+=('g++')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=("golang-$GO_VERSION-go")
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

    # Install svk-core-dev, svk-extras packages from Nexus
    BUILD_DEPS=()
    BUILD_DEPS+=('svk-core-dev')
    BUILD_DEPS+=('svk-grpc')
    BUILD_DEPS+=('svk-go-modules')
    package_manager 'install'
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
configure_nexus
set_go_path
