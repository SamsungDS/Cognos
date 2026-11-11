#!/usr/bin/env bash
# shellcheck disable=SC1091
set -eu

# Path vars
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../")
ARTIFACT_DIR="$PROJECT_ROOT/build/artifacts"   # as every Cognos component

# The versions of the cognos-grpc and cognos-go-modules packages, the same as the internal packages:
# gRPC 1.59.2, and the Go modules package of the extras repository's last release (v0.0.25).
GRPC_VERSION="1.59.2"
GO_MODULES_VERSION="0.0.25"

help() {
    # Exit with 0 by default - otherwise used passed value
    EXIT_CODE="${1-0}"
    # Display Help
    echo "Build script for SVK Extras"
    echo
    echo "Syntax: build.sh [-b|g|v|h]"
    echo "options:"
    echo "-b | --build-grpc"
    echo "  Build gRPC for SVK"
    echo "-v | --grpc-version"
    echo "  Specify a gRPC version to build."
    echo "  Default gRPC version: $GRPC_VERSION"
    echo "-g | --build-go-package"
    echo "  Build SVK package for gRPC and protobuf go modules."
    echo "-h | --help"
    echo "  Print this help message."
    exit "$EXIT_CODE"
}

parse_options() {
    # Default options if no arguments passed
    if [[ $# -eq 0 ]]; then
        BUILD_GRPC=true
        BUILD_GO_PACKAGE=true
    else
        BUILD_GRPC=false
        BUILD_GO_PACKAGE=false
    fi

    # Parse options
    while [[ $# -gt 0 ]];
    do
    case $1 in
        -b|--build-grpc)
        BUILD_GRPC=true
        shift
        ;;
        -v|--grpc-version)
        GRPC_VERSION="$2"
        shift
        shift
        ;;
        -g|--build-go-package)
        BUILD_GO_PACKAGE=true
        shift
        ;;
        -h|--help)
        help
        ;;
        *)
        echo "ERROR: Invalid build option"
        help 1
        ;;
    esac
    done
}

get_os_version() {
    # Determine OS ID from /etc/os-release
    if [[ -e /etc/os-release ]]; then
        source "/etc/os-release"
    else
        echo "ERROR: Unknown build OS"
        exit 1
    fi
    echo "Build OS is: $ID ${VERSION_ID%%.*}"
}

remove_directory() {
    # Utility function to delete a directory and its contents if it exists
    local DIR_TO_REMOVE="$1"

    if [[ -d "$DIR_TO_REMOVE" ]]; then
        echo "Deleting $DIR_TO_REMOVE"
        rm -rf "$DIR_TO_REMOVE"
    fi
}

clone_grpc() {
    # Clone gRPC path vars
    GRPC_REPO_BRANCH="v$GRPC_VERSION"
    GRPC_DIR="$PROJECT_ROOT/grpc_$GRPC_REPO_BRANCH"

    # Clone grpc and its submodules
    if [[ ! -d "$GRPC_DIR" ]]; then
        git clone --branch "$GRPC_REPO_BRANCH" https://github.com/grpc/grpc --single-branch "$GRPC_DIR"
    fi
    pushd "$GRPC_DIR"
        git submodule update --init
    popd
}

build_grpc() {
    # Build gRPC path vars
    GRPC_BUILD_DIR="$GRPC_DIR/cmake/build"
    GRPC_STAGING_DIR="$PROJECT_ROOT/svk-grpc"
    RE2_DIR="$GRPC_DIR/third_party/re2"

    # Cleanup build dirs if they exist
    remove_directory "$GRPC_BUILD_DIR"
    remove_directory "$GRPC_STAGING_DIR"

    # Build grpc
    mkdir --verbose --parents "$GRPC_STAGING_DIR"
    mkdir --verbose --parents "$GRPC_BUILD_DIR"
    pushd "$GRPC_BUILD_DIR"
        # Use package version of cares, SSL, and zlib, otherwise they will conflict with our package.
        # The distro-version of ABSL cannot be used, because it is too old to build gRPC in Rocky.
        # Therefore, we must mark the absl package as conflicting in specfile/deb control.
        # I couldn't find packages to satisfy the other deps (protobuf, re2) so we shouldn't conflict.

	# For Ubuntu, Rocky9, OL9, the dependencies are built as the module which is part of the grpc repo
	# For OL10, it is built as package (external re2+abseil devel rpms needs to be installed)
	dep_pkg_type="module"

	# Disabling this for now as we couldn't figure out the exact root cause of stability issues
        # if [[ "$ID" == "ol" && "$MAJOR_VER" == "10" ]]; then
	#     dep_pkg_type="package"
	# fi

        cmake ../.. --install-prefix=/usr 	\
              -DCMAKE_BUILD_TYPE=Release       	\
              -DgRPC_ABSL_PROVIDER="${dep_pkg_type}"\
              -DgRPC_CARES_PROVIDER=package    	\
              -DgRPC_PROTOBUF_PROVIDER=module 	\
              -DgRPC_RE2_PROVIDER="${dep_pkg_type}"\
              -DgRPC_SSL_PROVIDER=package      	\
              -DgRPC_ZLIB_PROVIDER=package
        make "-j$(nproc)"
        make "-j$(nproc)" install DESTDIR="$GRPC_STAGING_DIR"
    popd

    # For Ubuntu, Rocky9, OL9, ship the re2 as part of the rpm
    # if [[ "$ID" == "ubuntu" || "$ID" == "rocky" || "$MAJOR_VER" == "9" ]]; then
    # Build re2
    pushd "$RE2_DIR"
        make "-j$(nproc)" install DESTDIR="$GRPC_STAGING_DIR" prefix=/usr
    popd
    # fi
}

get_go_modules() {
    # Path Vars
    GO_TMP_DIR="$PROJECT_ROOT/go_tmp"
    GO_STAGING_DIR="$PROJECT_ROOT/svk-go-modules"

    # Cleanup build dirs if they exist
    remove_directory "$GO_STAGING_DIR"

    # Ensure go is in path by sourcing /etc/profile - Ubuntu Only
    if [ "$ID" == "ubuntu" ]; then
        source /etc/profile
    fi

    # Install Go packages
    export GOPATH="$GO_STAGING_DIR/usr/local/svk/go_dir"
    export PATH=$PATH:$GOPATH/bin
    
    # Create GO_TMP_DIR and use as cwd - this is a hack because otherwise go will find .go files in the grpc_v* dir and try to install them
    mkdir --verbose --parents "$GO_STAGING_DIR"
    pushd "$GO_STAGING_DIR"
        export GO111MODULE=on
        go mod init rest_api
        cat > dependencies.go << EOF
package tools

import (
    _ "github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-grpc-gateway"
    _ "github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-openapiv2"
    _ "google.golang.org/grpc/cmd/protoc-gen-go-grpc"
    _ "google.golang.org/protobuf/cmd/protoc-gen-go"
)
EOF
        # go mod tidy
        # `go get` calls update the go.mod file
        go get github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-grpc-gateway@v2.25.1
        go get github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-openapiv2@v2.25.1
        go get google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
        go get google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.0
        # `go install` downloads the binary files associated
        go install github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-grpc-gateway@v2.25.1
        go install github.com/grpc-ecosystem/grpc-gateway/v2/protoc-gen-openapiv2@v2.25.1
        go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
        go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.0

        unlink dependencies.go
        mkdir "$GOPATH/go_files_dir"
        mv go.mod "$GOPATH/go_files_dir"
        mv go.sum "$GOPATH/go_files_dir"
    popd
}

generate_rpm() {
    # RPM vars
    local SPECFILE=$1
    local RPM_VERSION="$2"
    local RPMBUILD_DIR="$PROJECT_ROOT/rpmbuild"
    local STAGING_DIR="$PROJECT_ROOT/$SPECFILE"

    # Only build RPM on supported OS
    if [[ "$ID" == "rocky" || "$ID" == "ol" ]]; then
        # Prepare RPMBUILD directories
        mkdir --verbose --parents "$RPMBUILD_DIR"/{BUILD,RPMS,SPECS}

        # Replace '-' character with '_' in version string
        RPM_VERSION=${RPM_VERSION//-/_}

        # Export env vars used in SPECFILEs
        export RPM_VERSION
        export STAGING_DIR

        # Build RPM
        echo "Building $SPECFILE RPM..."
        rpmbuild -bb --clean "$PROJECT_ROOT"/scripts/packaging/rpm/"$SPECFILE".spec --define "_topdir $RPMBUILD_DIR"

        # Move RPM to artifact dir
        local OS_ARTIFACT_DIR="$ARTIFACT_DIR/$ID${VERSION_ID%%.*}"
        mkdir --verbose --parents "$OS_ARTIFACT_DIR"
        mv --verbose "$RPMBUILD_DIR/RPMS/x86_64"/*.rpm "$OS_ARTIFACT_DIR"
    else
        echo "Skipping $SPECFILE RPM build for OS: $ID"
    fi
}

generate_deb() {
    # Debian Package vars
    # $1 = output package name (used for staging dir + dch)
    # $2 = version string
    # $3 = (optional) source-template dir under scripts/packaging/debian/
    # $4 = (optional) build profile to pass via DEB_BUILD_PROFILES
    local DEB_NAME="$1"
    local DEB_VERSION="$2"
    local DEB_TEMPLATE="${3:-$DEB_NAME}"
    local DEB_BUILD_PROFILE="${4:-}"
    local DEB_STAGING_DIR="$PROJECT_ROOT/$DEB_NAME"
    local DEBIAN_DIR="$DEB_STAGING_DIR/debian"

    # Only build Debian Package on supported OS
    if [ "$ID" == "ubuntu" ]; then
        # Prepare Debian package files
        remove_directory "$DEBIAN_DIR"
        mkdir --verbose --parent "$DEBIAN_DIR"
        cp --verbose "$PROJECT_ROOT"/scripts/packaging/debian/"$DEB_TEMPLATE"/* "$DEBIAN_DIR/"
        cp --verbose -r "$PROJECT_ROOT"/scripts/packaging/debian/common/* "$DEBIAN_DIR"
        # Insert version string in control file
        sed -i "s/Version: DEB_VERSION/Version: $DEB_VERSION/g" "$DEBIAN_DIR/control"

        pushd "$DEB_STAGING_DIR"
            # Create changelog from git history
            export DEBEMAIL='karthik1.k@samsung.com'
            export DEBFULLNAME='Karthik Krishna'
            export DEB_VERSION
            # Parse Source: from the copied control file so the changelog's
            # source-package name matches what dpkg-source will validate.
            local DEB_SOURCE
            DEB_SOURCE=$(awk '/^Source:[[:space:]]*/ {print $2; exit}' "$DEBIAN_DIR/control")
            if [[ -z "$DEB_SOURCE" ]]; then
                echo "ERROR: could not parse Source: from $DEBIAN_DIR/control"
                exit 1
            fi
            # Create initial changelog
            dch --create --package "$DEB_SOURCE" --newversion "$DEB_VERSION" --distribution unstable --urgency=low "CHANGELOG"
            pushd "$PROJECT_ROOT"
                # Update changelog with git log history
                sed -i -e "/.*CHANGELOG.*$/r /dev/stdin" -e "s/.*CHANGELOG.*$//" "$DEBIAN_DIR/changelog" <<< "$(git log --pretty=format:'  * %aD %an - %s' --no-merges -- .)"
                # git log --pretty=format:'%h - %d: %s' --decorate=short --no-merges | sed -e 's/refs\/tags\///' -e 's/,.*//' >> "$DEBIAN_DIR/changelog"
            popd
            
            # Build package
            echo "Building $DEB_NAME Debian package..."
            if [[ -n "$DEB_BUILD_PROFILE" ]]; then
                DEB_BUILD_PROFILES="$DEB_BUILD_PROFILE" \
                    dpkg-buildpackage -b -us -uc --no-sign \
                        --build-profiles="$DEB_BUILD_PROFILE"
            else
                dpkg-buildpackage -b -us -uc --no-sign
            fi

            # Delete .bindinfo and .changes files, since we don't care about them and can't suppress them
            rm --verbose -f ../*.buildinfo ../*.changes

            # Move Debian Package to artifact dir
            local OS_ARTIFACT_DIR="$ARTIFACT_DIR/$ID${VERSION_ID%%.*}"
            mkdir --verbose --parents "$OS_ARTIFACT_DIR"
            mv --verbose ../*.deb "$OS_ARTIFACT_DIR"
        popd
    else
        echo "Skipping $DEB_NAME Debian package build for OS: $ID"
    fi
}

parse_options "$@"
get_os_version

MAJOR_VER=${VERSION_ID%%.*}

# Build gRPC
if $BUILD_GRPC; then
    clone_grpc
    build_grpc
    generate_rpm 'svk-grpc' "$GRPC_VERSION"
    generate_deb 'svk-grpc' "$GRPC_VERSION"
fi

# Build package for SVK go modules
if $BUILD_GO_PACKAGE; then
    get_go_modules
    generate_rpm 'svk-go-modules' "$GO_MODULES_VERSION"
    generate_deb 'svk-go-modules' "$GO_MODULES_VERSION"
fi

