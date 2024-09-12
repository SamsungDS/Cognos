#!/usr/bin/env bash
# shellcheck source=scripts/cal-start.sh

echo "Running CAL start script"

set -e
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SAPP_DIR="$(dirname "$SCRIPT_DIR")"

# Get cognos top level bash configs
pushd "$SAPP_DIR"/scripts/ || exit
    source "$SCRIPT_DIR"/cognos.config
popd || exit

# Enter Cognos Directory
pushd "$SAPP_DIR"/cognos/ || exit

    # Run CAL
    if [ "$MODE" = "mock" ]; then
        echo "Running CAL in mock mode.."
        python3 backend/app.py --host "$CAL_IP" --port "$CAL_PORT" --mock &
    else
        echo "RUNNING CAL.."
        python3 backend/app.py --host "$CAL_IP" --port "$CAL_PORT" &
    fi

# Exit Cognos Directory
popd || exit

wait
