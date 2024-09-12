#!/usr/bin/env bash
# shellcheck source=scripts/cognos-start.sh

echo "Running cognos start script"

set -e
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SAPP_DIR="$(dirname "$SCRIPT_DIR")"

# Get cognos top level bash configs
pushd "$SAPP_DIR"/scripts/ || exit
    source "$SCRIPT_DIR"/cognos.config
popd || exit

# Enter Cognos UI Directory
pushd "$SAPP_DIR"/cognos/ui/ || exit

# Run UI
npm start &

# Exit Cognos UI Directory
popd || exit

wait
