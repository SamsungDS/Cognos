#!/bin/sh
set -eu

PATH=/usr/sbin:/usr/bin:/sbin:/bin

SOURCE_CONTEXT="/usr/local/svk/svk-app/cognos/rbac"
TAG="rbac-container:latest"


# load OS info
# shellcheck source=/etc/os-release
# shellcheck disable=SC1091
. /etc/os-release


case "${ID:-}" in
	ubuntu)
		DOCKERFILE="${SOURCE_CONTEXT}/ubuntu_Dockerfile"
		;;
	ol|oracle)
		DOCKERFILE="${SOURCE_CONTEXT}/oel_Dockerfile"
		echo "Oracle Linux detected - preparing CA bundle.."
		rm -f tls-ca-bundle.pem
		cp /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem .
		chmod u+w tls-ca-bundle.pem
		;;
	*)
		echo "ERROR: Unsupported OS ID='${ID:-}'"
		exit 1
		;;
esac

echo "BUILDING ${TAG} using ${DOCKERFILE} (os=${ID})"

docker buildx build \
	-t "${TAG}" \
	-f "${DOCKERFILE}" \
	"${SOURCE_CONTEXT}"
