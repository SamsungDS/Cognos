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
        'cognos-core'
        'cognos-core-dev'
        'cognos-grpc'
        'cognos-go-modules'
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

install_build_deps
configure_nexus
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
