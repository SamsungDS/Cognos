#!/usr/bin/env bash
# shellcheck source=/dev/null

set -e

if [[ -e /etc/os-release ]]; then
	source "/etc/os-release"
else
	ID=unknown
fi

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../")
BUILD_DIR="$PROJECT_ROOT/build"
REPORTS_DIR="$BUILD_DIR/reports"

export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig:/usr/lib/pkgconfig

die()
{
    echo "$*"
    exit 1
}

help()
{
    # Display Help
    echo "Build script for SVK Management Framework"
    echo
    echo "Syntax: build.sh [-t|c|h|p|r|f]"
    echo "options:"
    echo "-t | --build-tests"
    echo "  Build the unit tests for SVK Framework."
    echo "-c | --with-coverage"
    echo "  Build with code coverage report. Must build unit tests for this."
    echo "-h | --help"
    echo "  Print this help."
    echo "-p | --install-prefix"
    echo "  Install libraries and related files to specified dir."
    echo "-r | --release"
    echo "  Release build. Generates a tarball called svk-mgmt-fw-<version>.tgz by default."
    echo "-f | --filename"
    echo "  Filename prefix to use for release tarball. Only applicable when building with release flag."
    echo "-b | --build-package"
    echo "  Generate SVK Mgmt FW RPMs/DEB packages."
    echo "-i | --install-path"
    echo "  Path that RPMs/DEBs should install mgmt-fw to (Default: /usr/local/svk/mgmt-fw). Only applicable when building with release flag."
    exit
}

parse_options()
{
    while [[ $# -gt 0 ]];
    do
    case $1 in
        -t|--build-tests)
        BUILD_TESTING=true
        shift
        ;;
        -c|--with-coverage)
        WITH_COVERAGE=true
        shift
        ;;
        -h|--help)
        help
        ;;
        -p|--install-prefix)
        CMAKE_INSTALL_PREFIX="$2"
        shift
        shift
        ;;
        -r|--release)
        RELEASE=true
        shift
        ;;
        -f|--filename)
        RELEASE_FILENAME_PREFIX="$2"
        shift
        shift
        ;;
        -b|--build-package)
        GENERATE_PACKAGE=true
        shift
        ;;
        -i|--install-path)
        PACKAGE_INSTALL_PATH="$2"
        shift
        shift
        ;;
        *)
        echo "Invalid option provided. Check the valid options"
        help
        ;;
    esac
    done
}

GIT_VER=$(git describe --abbrev=4 --always --tags) #Commit hash causing issues with rpmbuild

generateRPMs()
{
    local rpmBuildDir=$1
    local installpath=$2

    GIT_VER_FOR_RPM=$(git describe --abbrev=4 --always --tags|sed 's/-/_/g'|sed 's/v//g')

    export GIT_VER_FOR_RPM
    export CMAKE_INSTALL_PREFIX

    rpmbuild -bb --clean "$PROJECT_ROOT/svk_mgmt_fw.spec" --define "_topdir $rpmBuildDir" --define "installpath $installpath"
    cp "$RPMBUILD_DIR/RPMS/x86_64"/svk-mgmt-fw-*.rpm "$PROJECT_ROOT/build"
}

generateDebPackage()
{
    installpath=$1

    export CMAKE_INSTALL_PREFIX
    # Debian package control file expects the version to be starting with integer
    local GIT_VER_IN_NUM
    GIT_VER_IN_NUM=$(git describe --abbrev=4 --always --tags|sed 's/v//g')

    # Generate SVK mgmt-fw DEB package
    rm -rf packaging/
    mkdir -p "packaging/$installpath"
    cp -rf "$CMAKE_INSTALL_PREFIX"/bin "packaging/$installpath/"
    cp -rf "$CMAKE_INSTALL_PREFIX"/etc "packaging/"
    cp -rf "$CMAKE_INSTALL_PREFIX"/lib "packaging/$installpath/"
    cp -rf "$CMAKE_INSTALL_PREFIX"/lib64 "packaging/$installpath/"
    cp -rf "$CMAKE_INSTALL_PREFIX"/rest_api "packaging/$installpath/"
    cp -rf "$PROJECT_ROOT/DEBIAN.svk-mgmt-fw/" "packaging/DEBIAN"
    sed -i "s/Version: GIT_VERSION/Version: $GIT_VER_IN_NUM/g" packaging/DEBIAN/control

    dpkg -b packaging
    dpkg-name packaging.deb

    # Generate SVK mgmt-fw-dev DEB package
    rm -rf packaging/
    mkdir -p "packaging/$installpath"
    cp -rf "$CMAKE_INSTALL_PREFIX"/include "packaging/$installpath/"
    cp -rf "$PROJECT_ROOT/DEBIAN.svk-mgmt-fw-dev/" "packaging/DEBIAN"
    sed -i "s/Version: GIT_VERSION/Version: $GIT_VER_IN_NUM/g" packaging/DEBIAN/control

    dpkg -b packaging
    dpkg-name packaging.deb
}

RELEASE=false
BUILD_TESTING=false
WITH_COVERAGE=false

parse_options "$@"

echo "Build tests: $BUILD_TESTING"
echo "Build with code coverage: $WITH_COVERAGE"
echo "CMake install prefix: $CMAKE_INSTALL_PREFIX"

mkdir -p "$BUILD_DIR"
if [ "$ID" == "ubuntu" ]; then
    source /etc/profile
fi

mkdir -p "$PROJECT_ROOT/build"

CMAKE_OPTIONS=()

pushd "$BUILD_DIR"
    # If building release, don't build tests and code coverage
    if $RELEASE;then
        BUILD_TESTING=false
        WITH_COVERAGE=false
        if [ -z "$CMAKE_INSTALL_PREFIX" ];then
            CMAKE_INSTALL_PREFIX="svk-mgmt-fw" # Path is used for cmake install only
        fi
        if [ -z "$RELEASE_FILENAME_PREFIX" ];then
            RELEASE_FILENAME_PREFIX="svk-mgmt-fw"
        fi
        CMAKE_OPTIONS+=("-DWITH_RELEASE=ON")
        if [ -z "$PACKAGE_INSTALL_PATH" ];then
            PACKAGE_INSTALL_PATH="/usr/local/svk/mgmt-fw" # Location that rpm -ivh will install to
        fi
    fi

    if [ -n "$PACKAGE_INSTALL_PATH" ];then
        CMAKE_OPTIONS+=("-DPKG_CONFIG_PREFIX=$PACKAGE_INSTALL_PATH")
    else
        CMAKE_OPTIONS+=("-DPKG_CONFIG_PREFIX=$CMAKE_INSTALL_PREFIX")
    fi

    # Add unit test option
    if $BUILD_TESTING;then
        CMAKE_OPTIONS+=("-DBUILD_TESTING=ON")
    fi

    # Add code coverage option
    if $WITH_COVERAGE;then
        CMAKE_OPTIONS+=("-DWITH_COVERAGE=ON")
    fi

    # Add cmake install prefix option
    if [ -n "$CMAKE_INSTALL_PREFIX" ];then
        CMAKE_OPTIONS+=("-DCMAKE_INSTALL_PREFIX=$CMAKE_INSTALL_PREFIX")
    fi

    export GOPATH=/usr/local/svk/go_dir
    export PATH=$PATH:$GOPATH/bin

    printf "Cmake options: %s\n" "${CMAKE_OPTIONS[@]}"

    echo "Running cmake..."
    cmake "${CMAKE_OPTIONS[@]}" ../

    echo "Building libraries..."

    if [ -n "$CMAKE_INSTALL_PREFIX" ];then
        echo "make install..."
        make install "-j$(nproc)"
    else
        echo "make..."
        make "-j$(nproc)"
    fi

    if $WITH_COVERAGE;then
        if $BUILD_TESTING;then
            pushd tests
                echo "Running unit tests..."
                mkdir -p "$REPORTS_DIR"
                ctest --output-junit "$REPORTS_DIR/gitlab_junit.xml"
            popd

            # Run go code coverage tests as well for REST API server
            pushd rest_api/tests
                cp "$PROJECT_ROOT/config/config.json.example" /usr/local/svk/conf.json
                GO111MODULE=on go mod tidy
                pushd cmd/app
                    GO111MODULE=on go test -coverprofile="$REPORTS_DIR/go_coverage.out"
                popd
            popd
        else
            die "Can't generate code coverage without building tests, not running gcovr"
        fi

        echo "Generating coverage reports"
        # Using path to framework object files
        gcovr \
            --xml "$REPORTS_DIR/gitlab_coverage.xml" \
            --html-details "$REPORTS_DIR/gitlab_coverage.html"\
            --sonarqube "$REPORTS_DIR/sonar_coverage.xml" \
            --txt \
            --root "$PROJECT_ROOT" \
            --exclude "$PROJECT_ROOT/build" \
            --exclude "$PROJECT_ROOT/tests" \
            --exclude "/usr/include/" \
            "$BUILD_DIR"

    elif $RELEASE;then
        echo "Generating release tarball..."
        GIT_VER=$(git describe --abbrev=4 --always --tags)
        GIT_SHORT_VER=$(git describe --abbrev=0 --always --tags|sed 's/v//g')
        # Run go tidy and go build commands inside the rest_api
        mkdir -p "$CMAKE_INSTALL_PREFIX/rest_api"
        pushd "$PROJECT_ROOT/build/rest_api/tests"
            GO111MODULE=on go mod tidy
            pushd cmd/app
                if [ -n "$CMAKE_INSTALL_PREFIX" ]; then
                    if [[ "$CMAKE_INSTALL_PREFIX" == /* ]]; then
                        GO111MODULE=on go build -o "$CMAKE_INSTALL_PREFIX/rest_api/svk_rest_server-$GIT_SHORT_VER"
                        pushd "$CMAKE_INSTALL_PREFIX/rest_api/"
                            if [ -f svk_rest_server ]; then
                                rm -f svk_rest_server
                            fi
                            ln -s "svk_rest_server-$GIT_SHORT_VER" svk_rest_server
                        popd
                    else
                        GO111MODULE=on go build -o "$PROJECT_ROOT/build/$CMAKE_INSTALL_PREFIX/rest_api/svk_rest_server-$GIT_SHORT_VER"
                        pushd "$PROJECT_ROOT/build/$CMAKE_INSTALL_PREFIX/rest_api/"
                            if [ -f svk_rest_server ]; then
                                rm -f svk_rest_server
                            fi
                            ln -s "svk_rest_server-$GIT_SHORT_VER" svk_rest_server
                        popd
                    fi
                fi
            popd
        popd

        mkdir -p "$CMAKE_INSTALL_PREFIX/lib"
        mkdir -p "$CMAKE_INSTALL_PREFIX/lib64"
        tar -zcf "$RELEASE_FILENAME_PREFIX-$ID-$VERSION_ID-$GIT_VER.tgz" "$CMAKE_INSTALL_PREFIX"
        echo "$GENERATE_PACKAGE"
        if [ -n "$GENERATE_PACKAGE" ];then
            if [ "$ID" == "ubuntu" ]; then
                echo "Generating Ubuntu package"
                generateDebPackage "$PACKAGE_INSTALL_PATH"
            else
                echo "Generating release/devel RPMs..."

                RPMBUILD_DIR="$BUILD_DIR/rpmbuild"
                mkdir -p rpmbuild/{BUILD,RPMS,SPECS}
                cp -rf "$CMAKE_INSTALL_PREFIX/" "$RPMBUILD_DIR/BUILD"

                generateRPMs "$RPMBUILD_DIR" "$PACKAGE_INSTALL_PATH"
            fi
        fi
    fi

popd
