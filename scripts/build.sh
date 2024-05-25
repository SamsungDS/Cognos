#!/usr/bin/env bash

set -e

# set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

# :help: run sapp tests
PROG=${0##*/}

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../")
REPORTS_DIR="$PROJECT_ROOT/build/reports"

die() {
    echo "$PROG: $*" >&2
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
    echo "--with-fmapi <FMAPI_LIB_PATH> <FMAPI_INCLUDE_PATH>"
    echo "  Builds with fmapi. Requires fmapi library and source paths."
    echo "e.g. scripts/build.sh --with-fmapi /cxl_memory_box/mbox_a1/build/libmbox_a1_shared.so /cxl_memory_box/mbox_a1"
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
        --with-fmapi)
	WITH_FMAPI=true
	if [ -z "$2" ] || [ -z "$3" ]; then
	    echo "Missing FM library or include path."
	    help
	fi
	FMAPI_LIB_PATH="$2"
	FMAPI_INCLUDE_PATH="$3"
	shift
	shift
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
WITH_FMAPI=false

parse_options "$@"

echo "Build tests: $BUILD_TESTING"
echo "Build with code coverage: $WITH_COVERAGE"
echo "CMake install prefix: $CMAKE_INSTALL_PREFIX"

mkdir -p "$PROJECT_ROOT/build"

CMAKE_OPTIONS=()

pushd "$PROJECT_ROOT/build"
    # If building release, don't build tests and code coverage
    if $RELEASE;then
        BUILD_TESTING=false
        WITH_COVERAGE=false
        if [ -z "$CMAKE_INSTALL_PREFIX" ];then
            CMAKE_INSTALL_PREFIX="usr/local/svk" # Need to use this path to generate release tarball properly
        fi
        if [ -z "$RELEASE_FILENAME_PREFIX" ];then
            RELEASE_FILENAME_PREFIX="svk-cxl"
        fi
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

    if $WITH_FMAPI;then
	if [ ! -f "$FMAPI_LIB_PATH" ];then
		die "$FMAPI_LIB_PATH does not exists"
	fi

	if ! file "$FMAPI_LIB_PATH" | grep -q "ELF 64-bit LSB shared object"; then
		die "$FMAPI_LIB_PATH not a library or shared object"
	fi

	if [ ! -d "$FMAPI_INCLUDE_PATH" ];then
		die "$FMAPI_INCLUDE_PATH does not exist"
	fi
	CMAKE_OPTIONS+=("-DWITH_FMAPI=ON")
	CMAKE_OPTIONS+=("-DCMAKE_INCLUDE_PATH=$FMAPI_INCLUDE_PATH")
	CMAKE_OPTIONS+=("-DCMAKE_LIBRARY_PATH=$FMAPI_LIB_PATH")
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
            --exclude "$PROJECT_ROOT/tests" \
            "$PROJECT_ROOT/build"
    elif $RELEASE;then
        echo "Generating release tarball..."
        GIT_VER=$(git describe --abbrev=4 --always --tags)
        tar -zcf "$RELEASE_FILENAME_PREFIX-$GIT_VER.tgz" "$CMAKE_INSTALL_PREFIX"
    fi

popd

