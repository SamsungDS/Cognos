#!/usr/bin/env bash
set -euo pipefail

echo "=== KVSSD Trace Tool Dependency Installer ==="

OS="unknown"
if [ -f /etc/redhat-release ]; then
    OS="rhel"
elif [ -f /etc/debian_version ]; then
    OS="debian"
fi

if [ "$OS" = "rhel" ]; then
    sudo dnf install -y blktrace sysstat nvme-cli util-linux python3-pip
    sudo dnf install -y bcc-tools bpftrace || true
elif [ "$OS" = "debian" ]; then
    sudo apt-get update
    sudo apt-get install -y blktrace sysstat nvme-cli util-linux python3-pip
    sudo apt-get install -y bpfcc-tools bpftrace || true
else
    echo "Unsupported OS auto-detection."
    echo "Install manually: blktrace sysstat nvme-cli util-linux python3-pip bcc-tools/bpfcc-tools bpftrace"
fi

python3 -m pip install --upgrade pip
python3 -m pip install pandas numpy matplotlib

echo "Verifying..."
for cmd in blktrace blkparse iostat nvme; do
    command -v "$cmd" >/dev/null 2>&1 && echo "OK: $cmd" || echo "MISSING: $cmd"
done

if command -v biosnoop >/dev/null 2>&1; then
    echo "OK: biosnoop"
elif command -v biosnoop-bpfcc >/dev/null 2>&1; then
    echo "OK: biosnoop-bpfcc"
elif [ -x /usr/share/bcc/tools/biosnoop ]; then
    echo "OK: /usr/share/bcc/tools/biosnoop"
elif [ -x /usr/share/bpfcc-tools/biosnoop ]; then
    echo "OK: /usr/share/bpfcc-tools/biosnoop"
else
    echo "WARN: biosnoop not found"
fi

python3 - <<'PY'
for mod in ["pandas", "numpy", "matplotlib"]:
    __import__(mod)
    print(f"OK: python module {mod}")
PY

echo "Done."
