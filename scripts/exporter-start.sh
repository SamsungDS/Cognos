#!/usr/bin/env bash
# shellcheck source=scripts/exporter-start.sh

echo "Running exporter start script"

set -e
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SAPP_DIR="$(dirname "$SCRIPT_DIR")"

# Get cognos top level bash configs
pushd "$SAPP_DIR"/scripts/ || exit
    source "$SCRIPT_DIR"/cognos.config
popd || exit

# Enter Cognos Directory
pushd "$SAPP_DIR"/cognos/ || exit

    # Run Exporter
    if [ "$MODE" = "mock" ]; then
        echo "Running Exporter in mock mode.."
        python3 exporter/exporter.py --mock &
    else
        echo "Running Exporter.."
        python3 exporter/exporter.py &
    fi

# Exit Cognos Directory
popd || exit

wait
