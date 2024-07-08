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

die()
{
    echo "$*"
    exit 1
}

help()
{
    # Display Help
    echo "Build script for SVK Framework"
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
    echo "  Release build. Generates a tarball called svk-core-<version>.tgz by default."
    echo "-f | --filename"
    echo "  Filename prefix to use for release tarball. Only applicable when building with release flag."
    echo "-b | --build-rpms"
    echo "  Generate SVK core RPMs."
    echo "-i | --install-path"
    echo "  Path that RPMs should install core to (Default: /usr/local/svk/core). Only applicable when building with release flag."
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
        -b|--build-rpms)
        INSTALL_RPM=true
        shift
        ;;
        -i|--install-path)
        RPM_INSTALL_PATH="$2"
        shift
        shift
        ;;
        *)
        ;;
    esac
    done
}

generateRPMs()
{
    local rpmBuildDir=$1
    local installpath=$2

    GIT_VER="$(git describe --abbrev=0 --always --tags)" #Commit hash causing issues with rpmbuild
    export GIT_VER
    export CMAKE_INSTALL_PREFIX

    rpmbuild -bb --clean "$PROJECT_ROOT/svk_core.spec" --define "_topdir $rpmBuildDir" --define "installpath $installpath"
    ls "$RPMBUILD_DIR/RPMS/x86_64"
}

RELEASE=false
BUILD_TESTING=false
WITH_COVERAGE=false

parse_options "$@"

echo "Build tests: $BUILD_TESTING"
echo "Build with code coverage: $WITH_COVERAGE"
echo "CMake install prefix: $CMAKE_INSTALL_PREFIX"

mkdir -p "$BUILD_DIR"

CMAKE_OPTIONS=()

pushd "$BUILD_DIR"
    # If building release, don't build tests and code coverage
    if $RELEASE;then
        BUILD_TESTING=false
        WITH_COVERAGE=false
        if [ -z "$CMAKE_INSTALL_PREFIX" ];then
            CMAKE_INSTALL_PREFIX="svk-core" # Path is used for cmake install only
        fi
        if [ -z "$RELEASE_FILENAME_PREFIX" ];then
            RELEASE_FILENAME_PREFIX="svk-core"
        fi
        CMAKE_OPTIONS+=("-DWITH_RELEASE=ON")
        if [ -z "$RPM_INSTALL_PATH" ];then
            RPM_INSTALL_PATH="/usr/local/svk/core" # Location that rpm -ivh will install to
        fi
    fi
    
    if [ -n "$RPM_INSTALL_PATH" ];then
        CMAKE_OPTIONS+=("-DPKG_CONFIG_PREFIX=$RPM_INSTALL_PATH")
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

    printf "Cmake options: %s\n" "${CMAKE_OPTIONS[@]}"

    echo "Running cmake..."
    cmake "${CMAKE_OPTIONS[@]}" .. 

    echo "Building libraries..."

    if [ -n "$CMAKE_INSTALL_PREFIX" ];then
        echo "make install..."
        make install
    else
        echo "make..."
        make
    fi

    if $WITH_COVERAGE;then
        if $BUILD_TESTING;then
            pushd tests
                echo "Running unit tests..."
                mkdir -p "$REPORTS_DIR"
                ctest --output-junit "$REPORTS_DIR/gitlab_junit.xml"
            popd
        else
            die "Can't generate code coverage without building tests, not running gcovr"
        fi

        echo "Generating coverage reports"
        # Using path to framework object files
        gcovr \
            --xml "$REPORTS_DIR/gitlab_coverage.xml" \
            --sonarqube "$REPORTS_DIR/sonar_coverage.xml" \
            --txt \
            --root "$PROJECT_ROOT" \
            --exclude "$PROJECT_ROOT/build" \
            "$BUILD_DIR"
    elif $RELEASE;then
        echo "Generating release tarball..."
        GIT_VER=$(git describe --abbrev=4 --always --tags)
        tar -zcf "$RELEASE_FILENAME_PREFIX-$ID-$VERSION_ID-$GIT_VER.tgz" "$CMAKE_INSTALL_PREFIX"
        echo "$INSTALL_RPM"
        if [ -n "$INSTALL_RPM" ];then
            echo "Generating release/devel RPMs..."
            
            RPMBUILD_DIR="$BUILD_DIR/rpmbuild"
            mkdir -p rpmbuild/{BUILD,RPMS,SPECS}
            
            cp -rf "$CMAKE_INSTALL_PREFIX/" "$RPMBUILD_DIR/BUILD"

            generateRPMs "$RPMBUILD_DIR" "$RPM_INSTALL_PATH"
        fi

    fi

popd
