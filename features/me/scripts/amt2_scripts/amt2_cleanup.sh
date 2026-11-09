#!/bin/bash
SCRIPT_DIR="$(dirname "$0")"

echo "[+] Cleaning up amt2 runtime artifacts in $SCRIPT_DIR..."

# Remove report directories
for d in "$SCRIPT_DIR"/report_*/; do
    if [ -d "$d" ]; then
        rm -rf "$d"
        echo "[+] Removed $d"
    fi
done

echo "[+] Cleanup complete."
