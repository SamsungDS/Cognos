#!/usr/bin/env bash

set -e

# set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

# :help: run sapp tests
PROG=${0##*/}

# Path variables
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../")
BUILD_DIR="$PROJECT_ROOT/build"
ARTIFACTS_DIR="$BUILD_DIR/artifacts"
REPORTS_DIR="$BUILD_DIR/reports"

# Default build options
RELEASE=false
MOCK=false
BUILD_TESTING=false
WITH_COVERAGE=false
WITH_FMAPI=false

export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/lib64/pkgconfig:/usr/local/lib/pkgconfig:/usr/lib/pkgconfig

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
  echo "-b | --build-package"
  echo "  Generate SVK CXL FW RPMs/DEB packages."
  echo "-i | --install-path"
  echo "  Path that RPMs should install svk cxl to (Default: /usr/local/svk/cxl). Only applicable when building with release flag."
  echo "--mock"
  echo "  use simulated fmapi library for cxl build, Usage ex: scripts/build.sh --mock --with-fmapi <FMAPI_LIB_PATH> <FMAPI_INCLUDE_PATH>" 
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
      -b|--build-package)
      GENERATE_PACKAGE=true
      shift
      ;;
      -i|--install-path)
      PACKAGE_INSTALL_PATH="$2"
      shift
      shift
      ;;
      --mock)
      MOCK=true
      shift 
      ;;
      *)
      echo "Invalid option provided. Check the valid options"
      help
      ;;
  esac
  done
}

get_os_version() {
  # Determine OS ID from /etc/os-release
  if [[ -e "/etc/os-release" ]]; then
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
  GIT_VERSION=$("$SCRIPT_DIR/get_version.sh")

  # Strip 'v' character from version string
  GIT_VERSION=${GIT_VERSION/v/}
  echo "Building SVK Core version: $GIT_VERSION"
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

create_rpm()
{
  local rpmBuildDir=$1
  local installpath=$2
  local mock_flag=$3

  # Replace '-' with '_' in version string, in case current commit is not an exact tag
  local RPM_VERSION=${GIT_VERSION//-/_}

  export GIT_VERSION
  export CMAKE_INSTALL_PREFIX

  rpmbuild -bb --clean "$PROJECT_ROOT/scripts/packaging/rpm/svk_cxl.spec" \
    --define "_topdir $rpmBuildDir" \
    --define "installpath $installpath" \
    --define "_fmapilibpath $FMAPI_LIB_PATH" \
    --define "_fmapiincpath $FMAPI_INCLUDE_PATH" \
    --define "svk_cxl_version $RPM_VERSION" \
    --define "svk_os_version $ID$VERSION_ID" \
    --define "mock_flag ${mock_flag:-}"

  # Move RPMs to artifacts dir
  move_artifacts "$RPMBUILD_DIR/RPMS/$(rpm --eval '%{_arch}')" rpm

}

create_deb()
{
  # Debian Package vars
  local DEBIAN_DIR="$BUILD_DIR/debian"
  # We're passing $PACKAGE_INSTALL_PATH as $1 below but not capturing it? - Someone please fix this! - Matt

  # Define a dynamic package name which reflects whether we are producting a release or simulation artifact
  local DEB_PACKAGE_NAME='svk-cxl'
  if [[ $MOCK == true ]]; then
    DEB_PACKAGE_NAME="$DEB_PACKAGE_NAME-mock"
  fi

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
    # Update FM_API build and include dirs
    sed -i -e "s@FMAPI_INCLUDE_VAL@$FMAPI_INCLUDE_PATH@g" "$DEBIAN_DIR/rules"
    sed -i -e "s@FMAPI_LIB_VAL@$FMAPI_LIB_PATH@g" "$DEBIAN_DIR/rules"
    sed -i -e "s@MOCK_VAL@$MOCK@g" "$DEBIAN_DIR/rules"
    # Define the package name - needed to differentiate "release" from "simulation" package
    sed -i -e "s@DEB_PACKAGE_NAME@$DEB_PACKAGE_NAME@g" "$DEBIAN_DIR/rules"
    sed -i -e "s@DEB_PACKAGE_NAME@$DEB_PACKAGE_NAME@g" "$DEBIAN_DIR/changelog"
    sed -i -e "s@DEB_PACKAGE_NAME@$DEB_PACKAGE_NAME@g" "$DEBIAN_DIR/control"
    if [[ $MOCK == true ]]; then
      # Rename the .install packages if MOCK - to refelect above renamed package in rules / changelog / control
      mv -v "$DEBIAN_DIR/svk-cxl.install" "$DEBIAN_DIR/$DEB_PACKAGE_NAME.install"
      mv -v "$DEBIAN_DIR/svk-cxl-dev.install" "$DEBIAN_DIR/$DEB_PACKAGE_NAME-dev.install"
    fi

    sed -i -e "s@ZMQ_CONF_VAL@$PROJECT_ROOT@g" "$DEBIAN_DIR/rules"
    sed -i -e "s@CXL_CONF_VAL@$PROJECT_ROOT@g" "$DEBIAN_DIR/rules"

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

if [[ -e /etc/os-release ]]; then
  # shellcheck source=/dev/null
  source /etc/os-release
else
  ID=unknown
fi

parse_options "$@"
get_os_version
get_git_version

echo "Build tests: $BUILD_TESTING"
echo "Build with code coverage: $WITH_COVERAGE"
echo "CMake install prefix: $CMAKE_INSTALL_PREFIX"

mkdir -p "$BUILD_DIR"

pushd "$BUILD_DIR"
  # If building release, don't build tests and code coverage
if $RELEASE;then
  BUILD_TESTING=false
  WITH_COVERAGE=false
  if [ -z "$CMAKE_INSTALL_PREFIX" ];then
    CMAKE_INSTALL_PREFIX="svk-cxl" # Need to use this path to generate release tarball properly
  fi
  if [ -z "$RELEASE_FILENAME_PREFIX" ];then
    RELEASE_FILENAME_PREFIX="svk-cxl"
  fi
  CMAKE_OPTIONS+=("-DWITH_RELEASE=ON")
  if [ -z "$PACKAGE_INSTALL_PATH" ];then
    PACKAGE_INSTALL_PATH="/usr/local/svk/cxl" # Location that rpm -ivh will install to
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

if $WITH_FMAPI;then
  if [ ! -f "$FMAPI_LIB_PATH" ];then
    die "$FMAPI_LIB_PATH does not exists"
  fi

  #if ! file "FMAPI_LIB_PATH" | grep -q "ELF 64-bit LSB shared object"; then
    #die "$FMAPI_LIB_PATH not a library or shared object"
  #fi

  if [ ! -d "$FMAPI_INCLUDE_PATH" ];then
    die "$FMAPI_INCLUDE_PATH does not exist"
  fi
  CMAKE_OPTIONS+=("-DWITH_FMAPI=ON")
  CMAKE_OPTIONS+=("-DFMAPI_INCLUDE_PATH=$FMAPI_INCLUDE_PATH")
  CMAKE_OPTIONS+=("-DFMAPI_LIBRARY_PATH=$FMAPI_LIB_PATH")

  cp "$FMAPI_INCLUDE_PATH/sample_json/input.json" "$PROJECT_ROOT/tests"
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

    cp "$PROJECT_ROOT/tests/input.json" "$BUILD_DIR/tests"
    cp "$PROJECT_ROOT/config/zmq_config.json" "$BUILD_DIR/tests/"
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
    --exclude "$BUILD_DIR" \
    --exclude "$PROJECT_ROOT/tests" \
    --exclude-throw-branches \
      "$BUILD_DIR"

  #rm -rf "$PROJECT_ROOT/tests/usr/"

elif $RELEASE;then
  echo "Generating release tarball..."
  mkdir -p "$BUILD_DIR/$CMAKE_INSTALL_PREFIX/lib"
  mkdir -p "$BUILD_DIR/$CMAKE_INSTALL_PREFIX/lib64"
  cp "$PROJECT_ROOT/config/zmq_config.json" "$BUILD_DIR/$CMAKE_INSTALL_PREFIX/"
  cp "$PROJECT_ROOT/cxl.conf" "$BUILD_DIR/$CMAKE_INSTALL_PREFIX/"
  if $MOCK; then
    tar -zcf "$RELEASE_FILENAME_PREFIX-mock-$ID-$GIT_VERSION.tgz" "$CMAKE_INSTALL_PREFIX"
  else
    tar -zcf "$RELEASE_FILENAME_PREFIX-$ID-$GIT_VERSION.tgz" "$CMAKE_INSTALL_PREFIX"
  fi
  echo "$GENERATE_PACKAGE"
  if [ -n "$GENERATE_PACKAGE" ];then
    if [ "$ID" == "ubuntu" ]; then
      echo "Generating Ubuntu package"
      create_deb "$PACKAGE_INSTALL_PATH"
    else
      echo "Generating release RPM..."
      RPMBUILD_DIR="$BUILD_DIR/rpmbuild"
      mkdir -p rpmbuild/{BUILD,RPMS,SPECS}
      cp -rf "$CMAKE_INSTALL_PREFIX/" "$RPMBUILD_DIR/BUILD"
      create_rpm "$RPMBUILD_DIR" "$PACKAGE_INSTALL_PATH" $MOCK
    fi
  fi
fi

popd
