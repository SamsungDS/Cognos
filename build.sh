#!/usr/bin/env bash
# Build Cognos component packages (deb on ubuntu24, rpm on ol10) with one
# version, and collect them in build/artifacts/<os>/. CI runs the same
# command with --native. See docs/ci.md.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Dependency order. cama and amo-prof are not built here.
ALL_COMPONENTS=(core mgmt-fw node ras slat me cxl sapp)

usage() {
    cat <<EOF
Usage: ./build.sh [--native] [--os ubuntu24|ol10] [--mock] [<component> ...]

Builds the release packages of the given components, or of all of them
(${ALL_COMPONENTS[*]}), in that order, and copies them to build/artifacts/<os>/.

  --native   Build on this machine or container. It must run the --os
             operating system and have the component's dependencies installed
             (its scripts/dependencies/install.sh, as in the component image).
             Without --native, each component is built in a Docker container
             from its scripts/docker/<os>.DOCKERFILE. Those Dockerfiles install
             packages from the internal Nexus, so Docker mode needs the lab
             network.
  --os       ubuntu24 (default) or ol10.
  --mock     Build the cxl mock variant (cognos-cxl-mock). Other components
             ignore it.
  -h         Show this help.

Version: COGNOS_VERSION if set, else the vX.Y.Z tag on HEAD, else
X.(Y+1).0~dev.0.local from VERSION.

Upstream packages: before building, the packages of core (and of mgmt-fw for
cxl and me) found in components/<upstream>/build/artifacts/<os>/ are installed
(logged as "pipeline"). Otherwise the ones already installed are used (logged
as "image").
EOF
}

die() {
    echo "build.sh: $*" >&2
    exit 1
}

component_dir() {
    if [[ $1 == sapp ]]; then echo "$ROOT/apps/sapp"; else echo "$ROOT/components/$1"; fi
}

# Upstream components whose packages a component builds against.
upstreams() {
    case $1 in
        core | sapp) ;;
        cxl | me) echo core mgmt-fw ;;
        *) echo core ;;
    esac
}

# The arguments of the component's own scripts/build.sh for a release build,
# as in its own CI.
component_build_args() {
    case $1 in
        cxl) echo --release -b ${MOCK:+--mock} ;;
        sapp) echo -r ;;
        *) echo --release ;;
    esac
}

set_version() {
    [[ -z ${COGNOS_VERSION:-} ]] || return 0
    local tag x y
    tag=$(git -C "$ROOT" tag --points-at HEAD | grep -Ex 'v[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 || true)
    if [[ -n $tag ]]; then
        COGNOS_VERSION=${tag#v}
    else
        IFS=. read -r x y < "$ROOT/VERSION"
        COGNOS_VERSION="$x.$((y + 1)).0~dev.0.local"
    fi
    export COGNOS_VERSION
}

# Prints "<name> <version>" of each package file given.
show_packages() {
    local f
    for f in "$@"; do
        if [[ $f == *.deb ]]; then
            echo "$(dpkg-deb -f "$f" Package) $(dpkg-deb -f "$f" Version)"
        else
            rpm -qp --qf '%{NAME} %{VERSION}-%{RELEASE}\n' "$f"
        fi
    done
}

install_upstream() {
    local up=$1 pkgs
    pkgs=("$(component_dir "$up")/build/artifacts/$OS"/*."$PKG_EXT")
    if [[ ${#pkgs[@]} -gt 0 ]]; then
        echo "upstream $up: pipeline $(show_packages "${pkgs[0]}" | cut -d' ' -f2)"
        if [[ $PKG_EXT == deb ]]; then
            $SUDO apt-get update
            DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --allow-downgrades "${pkgs[@]}"
        else
            $SUDO dnf install -y "${pkgs[@]}"
        fi
    elif [[ $PKG_EXT == deb ]]; then
        echo "upstream $up: image $(dpkg-query -W -f '${Version}' "cognos-$up" 2>/dev/null || echo 'not installed')"
    else
        echo "upstream $up: image $(rpm -q --qf '%{VERSION}-%{RELEASE}' "cognos-$up" 2>/dev/null || echo 'not installed')"
    fi
}

build_native() {
    local c=$1 dir pkgs up os_id
    # shellcheck disable=SC1091
    os_id=$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}")
    [[ $os_id == "$OS" ]] || die "--native --os $OS, but this machine runs $os_id"
    dir=$(component_dir "$c")
    echo "== build $c ($OS), version $COGNOS_VERSION"
    for up in $(upstreams "$c"); do
        install_upstream "$up"
    done
    # shellcheck disable=SC2046
    (cd "$dir" && ./scripts/build.sh $(component_build_args "$c"))
    pkgs=("$dir/build/artifacts/$OS"/*."$PKG_EXT")
    [[ ${#pkgs[@]} -gt 0 ]] || die "$c produced no .$PKG_EXT packages in $dir/build/artifacts/$OS"
    mkdir -p "$ROOT/build/artifacts/$OS"
    cp "${pkgs[@]}" "$ROOT/build/artifacts/$OS/"
    echo "Packages of $c:"
    show_packages "${pkgs[@]}"
}

# Docker mode: the container runs as root, so give the build directories back
# to the caller, also on failure and Ctrl-C.
restore_owner() {
    local dirs=() c
    [[ -n $LAST_IMAGE ]] || return 0
    [[ -d $ROOT/build ]] && dirs+=("$ROOT/build")
    for c in "${ALL_COMPONENTS[@]}"; do
        [[ -d $(component_dir "$c")/build ]] && dirs+=("$(component_dir "$c")/build")
    done
    # sapp's debian/rules runs npm in apps/sapp/cognos/ui.
    [[ -d $ROOT/apps/sapp/cognos/ui/node_modules ]] && dirs+=("$ROOT/apps/sapp/cognos/ui/node_modules")
    [[ -d $ROOT/apps/sapp/cognos/ui/build ]] && dirs+=("$ROOT/apps/sapp/cognos/ui/build")
    [[ ${#dirs[@]} -gt 0 ]] || return 0
    docker run --rm --init -v "$ROOT:$ROOT" --entrypoint chown "$LAST_IMAGE" -R "$(id -u):$(id -g)" "${dirs[@]}" || true
}

build_docker() {
    local c=$1 dir image mounts git_dir
    dir=$(component_dir "$c")
    image="cognos-$c:$OS"
    docker build -f "$dir/scripts/docker/$OS.DOCKERFILE" -t "$image" "$dir"
    LAST_IMAGE=$image
    mounts=(-v "$ROOT:$ROOT")
    # A git worktree keeps its repository outside the checkout.
    git_dir=$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)
    [[ $git_dir == "$ROOT"/* ]] || mounts+=(-v "$git_dir:$git_dir")
    # safe.directory: the checkout belongs to the caller, the container runs as root.
    # --init: so that Ctrl-C stops the build inside the container.
    docker run --rm --init "${mounts[@]}" -w "$ROOT" -e COGNOS_VERSION \
        -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e 'GIT_CONFIG_VALUE_0=*' \
        "$image" ./build.sh --native --os "$OS" ${MOCK:+--mock} "$c"
}

NATIVE=
OS=ubuntu24
MOCK=
REQUESTED=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --native) NATIVE=1 ;;
        --os)
            [[ $# -ge 2 ]] || die "--os needs a value"
            OS=$2
            shift
            ;;
        --mock) MOCK=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*) die "unknown option $1 (see -h)" ;;
        *) REQUESTED+=("$1") ;;
    esac
    shift
done

case $OS in
    ubuntu24) PKG_EXT=deb ;;
    ol10) PKG_EXT=rpm ;;
    *) die "--os must be ubuntu24 or ol10, not $OS" ;;
esac

for c in "${REQUESTED[@]}"; do
    [[ " ${ALL_COMPONENTS[*]} " == *" $c "* ]] || die "unknown component $c (one of: ${ALL_COMPONENTS[*]})"
done
COMPONENTS=()
for c in "${ALL_COMPONENTS[@]}"; do
    if [[ ${#REQUESTED[@]} -eq 0 || " ${REQUESTED[*]} " == *" $c "* ]]; then
        COMPONENTS+=("$c")
    fi
done

shopt -s nullglob
set_version
echo "Cognos version: $COGNOS_VERSION"

if [[ -n $NATIVE ]]; then
    SUDO=
    [[ $EUID -eq 0 ]] || SUDO=sudo
    for c in "${COMPONENTS[@]}"; do
        build_native "$c"
    done
else
    LAST_IMAGE=
    trap restore_owner EXIT
    trap 'exit 130' INT TERM
    for c in "${COMPONENTS[@]}"; do
        build_docker "$c"
    done
fi

echo "Packages in build/artifacts/$OS:"
ls -1 "$ROOT/build/artifacts/$OS"
