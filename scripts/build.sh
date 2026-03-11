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
TESTS_DIR="$BUILD_DIR/tests"
REPORTS_DIR="$BUILD_DIR/reports"
VENV_DIR="/usr/local/svk/venv/me"

# Default build options
BUILD_RELEASE=false
BUILD_TESTING=false
WITH_COVERAGE=false
MAKE_INSTALL=false

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
  echo "-r | --release"
  echo "  Release build. Generates a tarball called svk-core-<version>.tgz by default."
  exit
}

parse_options()
{
  while [[ $# -gt 0 ]];
  do
  case $1 in
      -t|--build-tests)
      BUILD_TESTING=true
      CMAKE_OPTIONS+=("-DBUILD_TESTING=ON")
      CMAKE_OPTIONS+=("-DWITH_COVERAGE=ON")
      shift
      ;;
      -h|--help)
      help
      ;;
      -r|--release)
      BUILD_RELEASE=true
      shift
      ;;
      *)
      echo "Invalid option provided. Check the valid options"
      help
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
  GIT_VERSION=$("$SCRIPT_DIR/get_version.sh" -v)

  echo "Building SVK ME version: $GIT_VERSION"
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
    local SPECFILE='svk_me.spec'
    local RPMBUILD_DIR="$BUILD_DIR/rpmbuild"

    # Replace '-' with '_' in version string, in case current commit is not an exact tag
    local RPM_VERSION=${GIT_VERSION//-/_}
    # Exclude everything after '-' for Go version (must be semantic version with integers only)
    local RPM_SHORT_VERSION=${GIT_VERSION/-*}

    # Only build RPM on supported OS
    if [[ "$ID" == "rocky" || "$ID" == "ol" ]]; then
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

create_deb()
{
  # Debian Package vars
  local DEBIAN_DIR="$BUILD_DIR/debian"

  # Define a dynamic package name which reflects whether we are producting a release or simulation artifact
  # This name needs to match the .install file name in the debian directory
  local DEB_PACKAGE_NAME='cognos-me'

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
    # Define the package name - needed to differentiate "release" from "simulation" package
    sed -i -e "s@DEB_PACKAGE_NAME@$DEB_PACKAGE_NAME@g" "$DEBIAN_DIR/rules"
    sed -i -e "s@DEB_PACKAGE_NAME@$DEB_PACKAGE_NAME@g" "$DEBIAN_DIR/changelog"
    sed -i -e "s@DEB_PACKAGE_NAME@$DEB_PACKAGE_NAME@g" "$DEBIAN_DIR/control"
    pushd "$BUILD_DIR"
      echo "Building SVK Memory Engine Debian packages.."
      # Build Debian packages - generate binaries only, do not sign packages
      dpkg-buildpackage -b -us -uc --no-sign

      # Delete .bindinfo and .changes files, since we don't care about them and can't suppress them
      rm --verbose -f ../*.buildinfo ../*.changes

      # Move Debian Packages to artifacts dir
      move_artifacts "$PROJECT_ROOT" deb
    popd
  else
    echo "Skipping SVK Memory Engine Debian package build for OS: $ID"
  fi
}

parse_options "$@"
get_os_version
get_git_version
activate_venv

execute_tests() {

  pushd "$BUILD_DIR"
  echo "Running unit tests..."   
  mkdir -p "$BUILD_DIR/tests/movers"
  mkdir -p "$BUILD_DIR/tests/profilers"
  mkdir -p "/usr/local/svk/feature_modules/me/config/"
  cp "$BUILD_DIR/src/movers/numa_move_all/libnuma_move_all.so" "$BUILD_DIR/tests/movers/"
  cp "$BUILD_DIR/src/movers/mover_damo/libmover_damo.so" "$BUILD_DIR/tests/movers/"
  mkdir -p "$BUILD_DIR/tests/test_CmeDiscovery"
  mkdir -p "$BUILD_DIR/tests/test_CmeDiscovery_fail"
  cp "$BUILD_DIR/src/libsvkme.so" "$BUILD_DIR/tests/test_CmeDiscovery/"
  cp "$BUILD_DIR/tests/mock_failures/libregister_mover.so" "$BUILD_DIR/tests/test_CmeDiscovery_fail/"
  cp "$PROJECT_ROOT/tests/cme_config.json" "$BUILD_DIR/tests/"
  cp "$PROJECT_ROOT/src/movers/mover_damo/config/damo_config.json" "/usr/local/svk/feature_modules/me/config/"
  cp "$PROJECT_ROOT/src/movers/mover_damo/tools/tm_gen_config.py" "/usr/local/svk/feature_modules/me/config/"
  mkdir -p "$REPORTS_DIR"
  ctest --output-junit "$REPORTS_DIR/gitlab_junit.xml" --test-dir "$TESTS_DIR"
  rm -rf "/usr/local/svk/feature_modules/me"
  rm -rf "$BUILD_DIR/tests/test_CheckCmeDiscovery"
  rm -rf "$BUILD_DIR/tests/test_CmeDiscovery_fail"
  rm -rf "$BUILD_DIR/tests/test_CmeDiscovery/"

  echo "Generating coverage reports"
  # Using path to framework object files
  "${VENV_DIR}"/bin/gcovr \
    --xml "$REPORTS_DIR/gitlab_coverage.xml" \
    --sonarqube "$REPORTS_DIR/sonar_coverage.xml" \
    --txt \
    --root "$PROJECT_ROOT" \
    --exclude "$BUILD_DIR" \
    --exclude "$PROJECT_ROOT/tests" \
    --exclude-throw-branches \
    "$BUILD_DIR"
}

build_feature() {
    # Append INSTALL_PREFIX to CMAKE_OPTIONS if we are installing
    if $MAKE_INSTALL; then
        CMAKE_OPTIONS+=("-DCMAKE_INSTALL_PREFIX=me")
    fi

    # Display CMAKE_OPTIONS before building
    printf "CMake options: %s\n" "${CMAKE_OPTIONS[@]}"
    
    # Build SVK Feature
    mkdir --verbose --parents "$BUILD_DIR"
    pushd "$BUILD_DIR"
        # Build Commands below
        echo "Building $SVK_PROJECT_NAME"
        cmake "${CMAKE_OPTIONS[@]}" ..
        make "-j$(nproc)"
    popd

    # Optionally execute tests
    if $BUILD_TESTING; then
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

if $BUILD_RELEASE;then
  create_deb
  build_rpm
else
  build_feature
fi
