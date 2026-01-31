#!/usr/bin/env python3

import json
import subprocess
import re
import sys
import os
import argparse

# Default variables
DEFAULT_CONFIG_PATH = "/usr/local/svk/feature_modules/cxl/config/cxl_dev_id_map.json"
DEFAULT_PROTOCOL = "CXL 2.0"

"""
DEFAULT_CONFIG_PATH can be changed dynamically by,
using the "--config-path" flag and specify the absolute path

"""

# Hardware ID Mapping
DEVICE_TYPES = {
    ("1e98", "0ddb"): "CMM-H",
    ("1b00", "c001"): "CMM-D"
}

def run_command(cmd):
    """Executes a shell command and returns the output string."""
    try:
        result = subprocess.run(
            cmd, shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error executing command '{cmd}': {e}", file=sys.stderr)
        return None

# lsmem output to obtain device range
def get_numa_map_from_lsmem():
    output = run_command("lsmem --output-all")
    range_to_node_map = {}
    if not output:
        return {}

    lines = output.splitlines()
    for line in lines:
        if "RANGE" in line or not line.strip():
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        clean_range = parts[0].replace("0x", "").lower()
        node_numa = parts[5]
        if node_numa.isdigit():
            range_to_node_map[clean_range] = int(node_numa)

    return range_to_node_map

# Map the lsmem output to obtain numa node
def get_numa_node_for_device(bdf, lsmem_map):
    cmd = f"lspci -vvv -s {bdf} | grep 'Range1'"
    output = run_command(cmd)
    if not output:
        return 0
    match = re.search(r"([0-9a-fA-F]+-[0-9a-fA-F]+)", output)

    if match:
        device_range = match.group(1).lower()
        if device_range in lsmem_map:
            return lsmem_map[device_range]
        for mem_range, node in lsmem_map.items():
            if device_range == mem_range:
                return node
    return 0

# Populate the protocol
def get_protocol(bdf):
    output = run_command(f"lspci -vvv -s {bdf}")
    if not output:
        return DEFAULT_PROTOCOL
    for version in ["CXL 1.1", "CXL 2.0", "CXL 3.0"]:
        if version in output:
            return version

    return DEFAULT_PROTOCOL

# Obtain the device serial number if available, else use default
def get_serial_number(bdf):
    output = run_command(f"lspci -vvv -s {bdf} | grep 'Device Serial Number'")
    if output:
        parts = output.split('Number')
        if len(parts) > 1:
            return f"0x{parts[1].strip().replace('-', '')}"
    return None

# Discover the CXL devices and pattern match using regex
def discover_cxl_devices():
    devices = []
    lsmem_map = get_numa_map_from_lsmem()
    raw_list = run_command("lspci -nn | grep -i cxl")
    if not raw_list:
        return []
    pattern = re.compile(r"^([0-9a-f:.]+) .* \[([0-9a-f]{4}):([0-9a-f]{4})\]")
    for line in raw_list.splitlines():
        match = pattern.search(line)
        if match:
            bdf_short = match.group(1)
            vendor, device_id = match.group(2).lower(), match.group(3).lower()
            dev_type = DEVICE_TYPES.get((vendor, device_id))
            if dev_type:
                full_bdf = bdf_short if len(bdf_short.split(':')) == 3 else f"0000:{bdf_short}"
                print(f"Discovered {dev_type}: {full_bdf} [{vendor}:{device_id}]")
                devices.append({
                    "device_type": dev_type,
                    "vendor_id": vendor,
                    "device_id": device_id,
                    "location": full_bdf,
                    "protocol": get_protocol(full_bdf),
                    "numa_node": get_numa_node_for_device(full_bdf, lsmem_map),
                    "serial_number": get_serial_number(full_bdf)
                })
    return devices

# Add the map information in the cxl_dev_id_map.json file
def update_json(config_path, discovered_devices):
    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found at {config_path}")
        sys.exit(1)
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        sys.exit(1)

    if not data.get("device_map"):
        print("Error: No 'device_map' found in JSON to use as template.")
        sys.exit(1)
    template_obj = data["device_map"][0].copy()
    data["device_map"] = []

    for dev in discovered_devices:
        new_entry = json.loads(json.dumps(template_obj))
        new_entry.update({
            "mock_disable": True,
            "device_type": dev["device_type"],
            "vendor_id": dev["vendor_id"],
            "device_id": dev["device_id"],
            "location": dev["location"],
            "protocol": dev["protocol"],
            "numa_node": dev["numa_node"]
        })

        if dev["serial_number"]:
            new_entry["serial_number"] = dev["serial_number"]

        data["device_map"].append(new_entry)

    with open(config_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Successfully updated {len(discovered_devices)} devices in {config_path}")

def main():
    parser = argparse.ArgumentParser(description="Update CXL device JSON configuration.")
    parser.add_argument(
        "--config-path",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to the cxl.json file (default: {DEFAULT_CONFIG_PATH})"
    )
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Note: Running without root may result in incomplete lspci/lsmem data.")
    found_devices = discover_cxl_devices()
    if found_devices:
        update_json(args.config_path, found_devices)
    else:
        print("No CXL devices matching known CMM-H/CMM-D profiles were found.")

if __name__ == "__main__":
    main()
