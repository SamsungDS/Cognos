#! /usr/bin/env bash
set -e

# Build Dependencies
install_build_deps() {
    BUILD_DEPS=()
    BUILD_DEPS+=('epel-release')
    package_manager 'install'
    BUILD_DEPS=()
    BUILD_DEPS+=('boost-devel')
    BUILD_DEPS+=('cmake')
    BUILD_DEPS+=('gcc-c++')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('golang')
    BUILD_DEPS+=('net-tools')
    BUILD_DEPS+=('python3.11')
    BUILD_DEPS+=('python3-pip')
    BUILD_DEPS+=('spdlog-devel')
    BUILD_DEPS+=('tar')
    BUILD_DEPS+=('unzip')
    BUILD_DEPS+=('wget')
    BUILD_DEPS+=('zeromq')
    BUILD_DEPS+=('zeromq-devel')
    package_manager 'install'
}

# Install from package mananger
package_manager() {
    OPERATION=$1
    # Detect package manager tool
    INSTALLER_BIN=""

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

    # Optimizations for Docker build
    if [[ $DOCKER ]]
    then
        if [[ $INSTALLER_BIN != 'yum' ]]
        then
            BUILD_DEPS+=('--nodocs')
        fi
        BUILD_DEPS+=('--noplugins')
        BUILD_DEPS+=('--setopt=install_weak_deps=0')
    fi

    INSTALL_STRING="$INSTALLER_BIN $OPERATION -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

# Install SVK Yum Repo (Nexus)
configure_nexus() {
    NEXUS_YUM_REPO_FILE="http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$ID${VERSION_ID%%.*}.repo"
    wget --no-verbose --output-document /etc/yum.repos.d/ssg-nexus.repo "$NEXUS_YUM_REPO_FILE"

    # Install svk-core-devel package
    BUILD_DEPS=('svk-core-devel')
    package_manager 'install'
}

install_build_deps
configure_nexus

# Farther cleanup if Docker environment
if [[ $DOCKER ]]
then
    CLEANUP_STRING="$INSTALLER_BIN clean all"
    echo "executing command: $CLEANUP_STRING"
    eval "$CLEANUP_STRING"
    rm -rf "$GRPC_DIR"
    rm -rf /var/lib/dnf/history*
    rm -rf /var/lib/dnf/repos/*
    rm -rf /var/lib/rpm/__db*
    rm -rf /usr/share/man /usr/share/doc /usr/share/licenses /tmp/*
    rm -f /var/log/dnf*
fi
