#! /usr/bin/env bash
set -e

MAJOR_VER=${VERSION_ID%%.*}

# Build Dependencies
install_build_deps() {
    BUILD_DEPS=(
        dnf
        oracle-epel-release-el"${MAJOR_VER}"
    )
    package_manager 'install'

    # Enable CodeReady Builder (CRB) repository
    BUILD_DEPS=("'dnf-command(config-manager)'")
    package_manager 'install'
    dnf config-manager --set-enabled "ol${MAJOR_VER}_codeready_builder"

    BUILD_DEPS=()
    BUILD_DEPS+=('cmake')
    BUILD_DEPS+=('c-ares-devel')
    BUILD_DEPS+=('gcc-c++')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('golang')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('kmod-devel')
    # BUILD_DEPS+=('re2-devel')
    BUILD_DEPS+=('rpmdevtools')
    BUILD_DEPS+=('tar')
    BUILD_DEPS+=('zlib-devel')
    package_manager 'install'
}

# Install from package mananger
package_manager() {
    local OPERATION=$1
    # Detect package manager tool
    local INSTALLER_BIN=''

    if [[ -f '/usr/bin/dnf' ]]
    then
        echo "using dnf"
        INSTALLER_BIN='dnf'
    elif [[ -f '/usr/bin/yum' ]]
    then
        echo "using yum"
        INSTALLER_BIN='yum'
    elif [[ -f '/usr/bin/microdnf' ]]
    then
        echo "using microdnf"
        INSTALLER_BIN='microdnf'
    else
        # Can't find an appropriate installer
        echo "can't find a valid installer"
        exit 1
    fi

    INSTALL_STRING="$INSTALLER_BIN $OPERATION -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

install_build_deps
