set -e 

# Build Dependencies
install_build_deps() {
    BUILD_DEPS=()
    package_manager 'update'
    BUILD_DEPS+=('curl')
    package_manager 'install'
    curl -fsSL https://deb.nodesource.com/setup_21.x | bash -
    BUILD_DEPS+=('nodejs')
    BUILD_DEPS+=('findutils')
    BUILD_DEPS+=('git')
    BUILD_DEPS+=('python3.11')
    BUILD_DEPS+=('pip')
    BUILD_DEPS+=('unzip')
    BUILD_DEPS+=('gnupg')
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

# Configure google chrome for selenium tests
configure_chrome() {
    
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
    sh -c 'echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
    wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip
    unzip /tmp/chromedriver.zip
    rm -rf /tmp/chromedriver.zip
    chmod +x chromedriver
    BUILD_DEPS=()
    package_manager 'update'

    # Install chrome stable
    BUILD_DEPS=(google-chrome-stable)
    package_manager 'install'
}

install_build_deps
configure_chrome
