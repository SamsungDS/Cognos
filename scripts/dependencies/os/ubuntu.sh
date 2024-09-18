#! /usr/bin/env bash
set -e 

# Build Dependencies
install_build_deps() {
    apt-get update

    BUILD_DEPS=(
        build-essential
        curl
        debhelper
        dpkg-dev
        findutils
        git
        gnupg
        pip
        python3.11
        unzip
        wget
    )
    package_manager
    
    # Install NodeJS 21
    curl -fsSL https://deb.nodesource.com/setup_21.x | bash -
    BUILD_DEPS=(nodejs)
    package_manager

    # Install chrome
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
    sh -c 'echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
    apt-get update
    BUILD_DEPS=(google-chrome-stable)
    package_manager
}

# Install from package mananger
package_manager() {
    # Optimizations for Docker build - see scripts/docker/*.DOCKERFILE for $DOCKER var invocation
    if $DOCKER; then
        BUILD_DEPS+=(--no-install-recommends)
    fi

    INSTALL_STRING="apt-get install -y ${BUILD_DEPS[*]}"
    echo "executing command: $INSTALL_STRING"
    eval "$INSTALL_STRING"
}

# Configure google chrome for selenium tests
configure_chrome() {
    wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip
    unzip /tmp/chromedriver.zip
    rm -rf /tmp/chromedriver.zip
    chmod +x chromedriver
}

install_build_deps
# Commenting this out because it is not being used and it is not idempotent
# To be addressed in a future MR
# configure_chrome

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
