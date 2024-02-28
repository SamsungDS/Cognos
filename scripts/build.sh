#!/usr/bin/env bash

set -e

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../")

die()
{
    echo "$*"
    exit 1
}

help()
{
    # Display Help
    echo "Build script for SVK gRPC Framework"
    echo
    echo "Syntax: build.sh [-t|c|h|p|r]"
    echo "options:"
    echo "-t | --build-tests"
    echo "  Build the unit tests for SVK Framework."
    echo "-c | --with-coverage"
    echo "  Build with code coverage report. Must build unit tests for this."
    echo "-h | --help"
    echo "  Print this help."
    echo "-p=* | --install-prefix=*"
    echo "  Install libraries and related files to specified dir."
    echo "-r | --release"
    echo "  Release build."
    exit
}

parse_options()
{
    for i in "$@"
    do
    case $i in
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
        -p=*|--install-prefix=*)
        CMAKE_INSTALL_PREFIX="${i#*=}"
        shift
        ;;
        -r|--release)
        RELEASE=true
        shift
        ;;
        *)
        ;;
    esac
    done
}

RELEASE=false
BUILD_TESTING=false
WITH_COVERAGE=false

parse_options "$@"

echo "Build tests: $BUILD_TESTING"
echo "Build with code coverage: $WITH_COVERAGE"
echo "CMake install prefix: $CMAKE_INSTALL_PREFIX"

rm -rf "$PROJECT_ROOT/build"
mkdir -p "$PROJECT_ROOT/build"

CMAKE_OPTIONS=()

pushd "$PROJECT_ROOT/build"
    # If building release, don't build tests and code coverage
    if $RELEASE;then
        BUILD_TESTING=false
        WITH_COVERAGE=false
        CMAKE_OPTIONS+=("-DWITH_RELEASE=ON")
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
                ctest
            popd
        else
            die "Can't generate code coverage without building tests, not running gcovr"
        fi

        echo "Generating coverage reports"
        mkdir -p reports
        # Using path to framework object files
        gcovr --sonarqube reports/sonar_coverage.xml -r ../framework framework/CMakeFiles/svkframework.dir/src/
        gcovr --xml reports/gitlab_coverage.xml -r ../framework framework/CMakeFiles/svkframework.dir/src/
    fi

popd
