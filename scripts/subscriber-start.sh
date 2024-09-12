#!/usr/bin/env bash
# shellcheck source=scripts/subscriber-start.sh

echo "Running subscriber start script"

set -e
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SAPP_DIR="$(dirname "$SCRIPT_DIR")"

# Get cognos top level bash configs
pushd "$SAPP_DIR"/scripts/ || exit
    source "$SCRIPT_DIR"/cognos.config
popd || exit

# Enter Cognos Directory
pushd "$SAPP_DIR"/cognos/ || exit

    # Run Subscriber
    if [ "$MODE" = "mock" ]; then
        echo "Running Subscriber in mock mode.."
        python3 subscriber/sub_client.py --mock subscriber/mock_publisher_events.output &
    else
        echo "Running Subscriber in real mode currently not supported.."
    fi

# Exit Cognos Directory
popd || exit

wait
