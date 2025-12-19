#!/usr/bin/env bash
set -eu

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/..")
BUILD_DIR="$PROJECT_ROOT/build"
ARTIFACTS_DIR="$BUILD_DIR/artifacts"
REPORTS_DIR="$BUILD_DIR/reports"
TESTS_DIR="$BUILD_DIR/tests"
VENV_DIR=/usr/local/svk/mgmt/venv

# Default build options
CMAKE_OPTIONS=()
BUILD_RELEASE=false
RUN_TESTS=false
MAKE_INSTALL=false

# I don't know if this is needed
set +u
export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig:/usr/lib/pkgconfig
set -u

help()
{
    # Exit with 0 by default - otherwise used passed value
    local EXIT_CODE="${1-0}"

    # Display Help
    echo "Build script for SVK Framework"
    echo
    echo "Syntax: build.sh [-r|t|p|h]"
    echo "options:"
    echo "-r | --release"
    echo "  Release build. Generates RPMs on Rockylinux or Debian Packages on Ubuntu."
    echo "  If selected, all other build options are ignored."
    echo "-t | --run-tests"
    echo "  Execute unit tests for SVK Framework and generate code coverage reports."
    echo "-p | --install-prefix"
    echo "  Performs 'make install' to the specified path."
    echo "  Path is relative to $BUILD_DIR unless you provide an absolute path."
    echo "-h | --help"
    echo "  Print this help."
    exit "$EXIT_CODE"
}

parse_options()
{
    while [[ $# -gt 0 ]];
    do
    case $1 in
        -r|--release)
        BUILD_RELEASE=true
        shift
        ;;
        -t|--run-tests)
        RUN_TESTS=true
        CMAKE_OPTIONS+=("-DBUILD_TESTING=ON")
        CMAKE_OPTIONS+=("-DWITH_COVERAGE=ON")
        shift
        ;;
        -p|--install-prefix)
        MAKE_INSTALL=true
        INSTALL_PREFIX="$2"
        shift
        shift
        ;;
        -h|--help)
        help
        ;;
        *)
        echo "Invalid option provided. See usage details below:"
        help 1
        ;;
    esac
    done
}

activate_venv() {
    if [[ ! -d $VENV_DIR ]]; then
        echo "Python virtual environment does not exist!"
        echo "Execute dependency install script and try again: ./scripts/dependencies/install.sh"
        exit 1
    else
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    fi
}

get_os_version() {
    # Determine OS ID from /etc/os-release
    if [[ -e /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source "/etc/os-release"
    else
        echo "ERROR: Unknown build OS"
        exit 1
    fi
    echo "Build OS is: $ID ${VERSION_ID%%.*}"
}

get_git_version() {
    # Get Git version from tag
    echo "Determining version from git tag"
    GIT_VERSION=$("$SCRIPT_DIR/get_version.sh" -v)

    echo "Building SVK Management Framework version: $GIT_VERSION"
}

set_go_paths() {
    # Set PATH to include Go on Ubuntu
    if [ -f /etc/profile.d/go-1.22.sh ]; then
        # shellcheck disable=SC1091
        source /etc/profile.d/go-1.22.sh
    fi

    # Set GOPATH for SVK Go Modules and append to PATH
    export GOPATH=/usr/local/svk/go_dir
    export PATH=$PATH:$GOPATH/bin
}

build_mgmt_fw() {
    # Append INSTALL_PREFIX to CMAKE_OPTIONS if we are installing
    if $MAKE_INSTALL; then
        CMAKE_OPTIONS+=("-DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX")
        CMAKE_OPTIONS+=("-DPKG_CONFIG_PREFIX=$INSTALL_PREFIX")
    fi

    # Display CMAKE_OPTIONS before building
    printf "CMake options: %s\n" "${CMAKE_OPTIONS[@]}"
    
    # Build SVK Management Framework
    mkdir --verbose --parents "$BUILD_DIR"
    pushd "$BUILD_DIR"
        cmake "${CMAKE_OPTIONS[@]}" ..
        make "-j$(nproc)"
    popd

    # Optionally execute tests
    if $RUN_TESTS; then
        execute_tests
    else
        echo "Skipping test execution"
    fi

    # Optionally install
    if $MAKE_INSTALL; then
        pushd "$BUILD_DIR"
            make install
        popd
    else
        echo "Skipping make install"
    fi
}

execute_tests() {
    # Execute unit tests
    echo "Running unit tests..."
    mkdir --verbose --parent "$REPORTS_DIR"
    ctest --output-junit "$REPORTS_DIR/gitlab_junit.xml" --test-dir "$TESTS_DIR"

    # Run go code coverage tests as well for REST API server
    cp "$PROJECT_ROOT/config/mgmt_fw_config.json" /usr/local/svk/conf.json
    go mod tidy -C "$BUILD_DIR/rest_api/tests"
    go test -C "$BUILD_DIR/rest_api/tests/cmd/app" -coverprofile="$REPORTS_DIR/go_coverage.out" -v
    
    # Generate coverage reports and display results with summary to terminal
    echo "Generating coverage reports"
    gcovr \
        --xml "$REPORTS_DIR/gitlab_coverage.xml" \
        --sonarqube "$REPORTS_DIR/sonar_coverage.xml" \
        --txt-metric line --txt \
        --print-summary \
        --root "$PROJECT_ROOT" \
        --exclude "$PROJECT_ROOT/build" \
        --exclude "$PROJECT_ROOT/tests" \
        "$BUILD_DIR"
}

move_artifacts() {
    # Paths to move artifacts from
    local MOVE_ARTIFACTS_DIR=$1
    local MOVE_ARTIFACTS_SUFFIX=$2

    # Path to move artifacts to
    local OS_ARTIFACTS_DIR="$ARTIFACTS_DIR/$ID${VERSION_ID%%.*}"

    # Create artifacts dir and move artifacts
    mkdir --verbose --parents "$OS_ARTIFACTS_DIR"
    mv --verbose "$MOVE_ARTIFACTS_DIR"/*."$MOVE_ARTIFACTS_SUFFIX" "$OS_ARTIFACTS_DIR"
}

build_rpm() {
    # RPM vars
    local SPECFILE='mgmt_fw.spec'
    local RPMBUILD_DIR="$BUILD_DIR/rpmbuild"

    # Replace '-' with '_' in version string, in case current commit is not an exact tag
    local RPM_VERSION=${GIT_VERSION//-/_}
    # Exclude everything after '-' for Go version (must be semantic version with integers only)
    local RPM_SHORT_VERSION=${GIT_VERSION/-*}

    # Only build RPM on supported OS
    if [[ "$ID" == "rocky" ]]; then
        # Prepare RPMBUILD directories - inside our build directory
        rm -rf "$BUILD_DIR"
        mkdir --verbose --parents "$RPMBUILD_DIR"/{BUILD,RPMS,SPECS}

        # Build RPM
        echo "Building $SPECFILE RPM..."
        rpmbuild -bb --clean "$SCRIPT_DIR"/packaging/rpm/"$SPECFILE" \
            --define "_topdir $RPMBUILD_DIR" \
            --define "svk_rpm_version $RPM_VERSION" \
            --define "svk_short_version $RPM_SHORT_VERSION" \
            --define "svk_os_version $ID$VERSION_ID"

        # Move RPMs to artifacts dir
        move_artifacts "$RPMBUILD_DIR/RPMS/$(rpm --eval '%{_arch}')" rpm
    else
        echo "Skipping $SPECFILE RPM build for OS: $ID"
    fi
}

build_deb() {
    # Debian Package vars
    local DEBIAN_DIR="$BUILD_DIR/debian"

    # Only build Debian Package on supported OS
    if [[ "$ID" == "ubuntu" ]]; then
        # Prepare Debian package files
        rm -rf "$BUILD_DIR"
        mkdir --verbose --parent "$BUILD_DIR"
        cp --verbose -r "$PROJECT_ROOT"/scripts/packaging/debian "$BUILD_DIR/"

        echo "Updating $DEBIAN_DIR/changelog for this build"
        # Append git commit history to changelog
        sed -i -e "/.*DEB_CHANGELOG.*$/r /dev/stdin" -e "s/.*DEB_CHANGELOG.*$//" "$DEBIAN_DIR/changelog" <<< "$(git -C "$PROJECT_ROOT" log --pretty=format:'  * %aD %an - %s' --no-merges)"
        # Update changelog version string
        sed -i "s/DEB_VERSION/$GIT_VERSION-$ID$VERSION_ID/g" "$DEBIAN_DIR/changelog"
        # Update changelog timestamp
        sed -i "s/DEB_TIMESTAMP/$(date -R)/g" "$DEBIAN_DIR/changelog"
        # Update changelog OS version
        sed -i "s/DEB_OSVER/$ID$VERSION_ID/g" "$DEBIAN_DIR/changelog"

        pushd "$BUILD_DIR"
            echo "Building SVK Management Framework Debian packages..."
            # Build Debian packages - generate binaries only, do not sign packages
            dpkg-buildpackage -b -us -uc --no-sign

            # Delete .bindinfo and .changes files, since we don't care about them and can't suppress them
            rm --verbose -f ../*.buildinfo ../*.changes

            # Move Debian Packages to artifacts dir
            move_artifacts "$PROJECT_ROOT" deb
        popd
    else
        echo "Skipping SVK Management Framework Debian package build for OS: $ID"
    fi
}

parse_options "$@"
get_os_version
get_git_version
activate_venv
set_go_paths

if $BUILD_RELEASE; then
    build_deb
    build_rpm
else
    build_mgmt_fw
fi
