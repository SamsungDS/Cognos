import argparse
import distro
import json
import logging
import os
import platform
import psutil
import socket
import subprocess

logging.basicConfig(filename='find_node_info.log', level=logging.ERROR,
                    format='[find_node_info.py]: %(asctime)s - %(levelname)s - %(message)s')

def get_system_info():
    """
    Get details about the server the script is running on.
    
    Returns:
        dict: A dictionary containing server information.
    """
    server_info = {
        "hostname": platform.node(),
        "fqdn": socket.getfqdn(),
        "ip-address": socket.gethostbyname(platform.node()),
        "os-release": distro.name(pretty=True),
        "kernel-version": platform.uname().release if hasattr(platform, 'uname') else None,
    }
    
    return server_info

def get_network_adapters_info():
    """
    Get information about network adapters.
    
    Returns:
        dict: A dictionary containing network adapters information.
    """
    # speed, duplex, link detected, pci, device vendor, dns
    network_adapters_info = {}
    
    
    # Get PCI address using lshw
    output = subprocess.check_output(["lshw", "-C", "network", "-json"]).decode("utf-8")
    import json, re
    data = json.loads(output)
    for adapter, info in psutil.net_if_addrs().items():
        try:
            if adapter == "lo":
                continue
            
            # Get IPs, netmask
            network_adapters_info[adapter] = {
                "ip-address": next((addr.address for addr in info if addr.family == socket.AF_INET), ""),
                "ipv6-address": next((addr.address for addr in info if addr.family == socket.AF_INET6), ""),
                "netmask": getattr(info[0], 'netmask', ""),
            }
            

            # Get MTU
            with open(f"/sys/class/net/{adapter}/mtu", "r") as f:
                mtu = f.read().strip()
                if mtu == None:
                    mtu = ""
                network_adapters_info[adapter]["mtu"] = mtu

            # Get adapter speed, duplex setting, link detected, pci address of the adapter, and device vendor
            operstate_path = f"/sys/class/net/{adapter}/operstate"
            if os.path.exists(operstate_path):
                with open(operstate_path, "r") as f:
                    operstate = f.read().strip()
                    if operstate == None:
                        operstate = ""
                    network_adapters_info[adapter]["operational-state"] = operstate

            link_detected_path = f"/sys/class/net/{adapter}/carrier"
            if os.path.exists(link_detected_path):
                with open(link_detected_path, "r") as f:
                    link_detected = f.read().strip()
                    network_adapters_info[adapter]["link-detected"] = link_detected == "1"
            # These 2 may not be valid for all net devices, put them last
            speed_path = f"/sys/class/net/{adapter}/speed"
            if os.path.exists(speed_path):
                with open(speed_path, "r") as f:
                    speed = f.read().strip()
                    network_adapters_info[adapter]["speed"] = speed

            duplex_path = f"/sys/class/net/{adapter}/duplex"
            if os.path.exists(duplex_path):
                with open(duplex_path, "r") as f:
                    duplex = f.read().strip()
                    network_adapters_info[adapter]["duplex"] = duplex
            
        except Exception as e:
            print(f"Error getting info for adapter {adapter}: {e}")
            logging.error(f"Error getting info for adapter {adapter}: {e}")
    
    for item in data:
        network_dev_name = item.get("logicalname")
        if not network_dev_name:
            continue
        pci_address_match = re.search(r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}.[0-9a-fA-F]{0,2})", item.get("businfo", ""))
        network_adapters_info[network_dev_name]["pci-address"] = pci_address_match.group(1)
        network_adapters_info[network_dev_name]["device-vendor"] = item["vendor"]
    
    return network_adapters_info

def get_cpu_info():
    """
    Get information about CPU.
    
    Returns:
        dict: A dictionary containing CPU information.
    """
    #numa, cpu type
    cpu_info = {
        "physical-cores": psutil.cpu_count(logical=False),
        "total-cores": psutil.cpu_count(logical=True),
        "current-frequency": psutil.cpu_freq().current,
        "max-frequency": psutil.cpu_freq().max,
        "min-frequency": psutil.cpu_freq().min,
        "cpu-percentage": psutil.cpu_percent(),
    }
    return cpu_info

def get_memory_info():
    """
    Get information about memory.
    
    Returns:
        dict: A dictionary containing memory information in bytes.
    """
    svmem = psutil.virtual_memory()
    memory_info = {
        "total": svmem.total,
        "available": svmem.available,
        "used": svmem.used,
        "percentage": svmem.percent,
        "active": svmem.active,
        "inactive": svmem.inactive,
        "buffers": svmem.buffers,
        "cached": svmem.cached,
    }
    return memory_info

def get_storage_devices_info():
    devices_info = []

    try:
        # Use lspci command to get information about PCI devices
        lspci_output = subprocess.check_output(['lspci', '-vmm']).decode('utf-8').split('\n\n')

        for device in lspci_output:
            if device:  # Check if device string is not empty
                device_info = {}
                lines = device.split('\n')

                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()

                        if key == 'Slot':
                            device_info['pci_address'] = value
                        elif key == 'Class':
                            if 'Non-Volatile memory controller' in value or 'NVMe' in value:
                                device_info['device_type'] = 'nvme'
                            elif 'CXL' in value:
                                device_info['device_type'] = 'cxl'
                            else:
                                continue  # Skip other device types
                        elif key == 'Vendor':
                            device_info['device_manufacturer'] = value
                        elif key == 'NUMANode':
                            device_info['NUMA node'] = value
                # Check if required information is available
                required_keys = ['pci_address', 'device_type']
                if all(key in device_info for key in required_keys):
                    devices_info.append(device_info)

    except Exception as e:
        print(f"An error occurred: {e}")

    return devices_info


def get_all_info():
    """
    Get aggregated system information.
    
    Returns:
        dict: A dictionary containing aggregated system information.
    """
    system_info = {
        "system-info": get_system_info(),
        "network-adapters-info": get_network_adapters_info(),
        "cpu-info": get_cpu_info(),
        "memory-info": get_memory_info(),
        "device-info": get_storage_devices_info()
    }
    return system_info

def main():
    if platform.system() != 'Linux':
        print("Platform not supported")
        return
    parser = argparse.ArgumentParser(description="Python script to retrieve information about the node. Currently only supporting 1 type of info at a time or all node info")
    subparsers = parser.add_subparsers(dest="command", prog=parser.prog)

    subparsers.add_parser("network", help="Get network adapter info")
    subparsers.add_parser("memory", help="Get memory info in bytes")
    subparsers.add_parser("cpu", help="Get CPU info")
    subparsers.add_parser("system", help="Get info about the current server")
    subparsers.add_parser("devices", help="Get info about storage devices")

    args = parser.parse_args()
    if args.command == "network":
        network_info = {
            "newtork-adapters-info": get_network_adapters_info()
        }
        print(json.dumps(network_info, indent=4))
    elif args.command == "memory":
        memory_info = {
            "memory-info": get_memory_info()
        }
        print(json.dumps(memory_info, indent=4))
    elif args.command == "cpu":
        cpu_info = {
            "cpu-info": get_cpu_info()
        }
        print(json.dumps(cpu_info, indent=4))
    elif args.command == "system":
        system_info = {
            "system-info": get_system_info()
        }
        print(json.dumps(system_info, indent=4))
    elif args.command == "devices":
        device_info = {
            "device-info": get_storage_devices_info()
        }
        print(json.dumps(device_info, indent=4))
    else:
        system_info = get_all_info()
        print(json.dumps(system_info, indent=4))

if __name__ == "__main__":
    main()