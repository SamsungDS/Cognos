import argparse
import distro
import json
import logging
import os
import platform
import psutil
import socket
import subprocess
import uuid

from numa import info as numactl_info
from numa import memory as memory_info

node_name = None
config_file = None

logger = None

def get_system_info():
    """
    Get details about the server the script is running on.
    
    Returns:
        dict: A dictionary containing server information.
    """
    hostname = platform.node()
    # Create set of IPs that are used for localhost and filter them from the IP list
    localhost_ips = set()
    for res in socket.getaddrinfo('localhost', 0):
        localhost_ips.add(res[4][0])
    server_info = {
        "hostname": hostname,
        "fqdn": socket.getfqdn(),
        "ip-address": next((ip for ip in socket.gethostbyname_ex(platform.node())[2] if ip not in localhost_ips), 
                           socket.gethostbyname(hostname)),
        "os-release": distro.name(pretty=True),
        "kernel-version": platform.uname().release if hasattr(platform, 'uname') else None,
    }
    
    return {'server-info': server_info}

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
            mtu_path = f"/sys/class/net/{adapter}/mtu"
            if os.path.exists(mtu_path):
                with open(mtu_path, "r") as f:
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
            logger.error(f"Error getting info for adapter {adapter}: {e}")
    
    for item in data:
        network_dev_name = item.get("logicalname")
        if not network_dev_name:
            continue
        pci_address_match = re.search(r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]{0,2})", item.get("businfo", ""))
        if pci_address_match is not None:
            network_adapters_info[network_dev_name]["pci-address"] = pci_address_match.group(1)
        if "vendor" in item:
            network_adapters_info[network_dev_name]["device-vendor"] = item["vendor"]
    
    return {'network-adapters-info': network_adapters_info}

def get_cpu_info():
    """
    Get information about CPU.
    
    Returns:
        dict: A dictionary containing CPU information.
    """
    #numa, cpu type
    # interval is being set, if not set it may return 0
    cpu_info = {
        "physical-cores": psutil.cpu_count(logical=False),
        "total-cores": psutil.cpu_count(logical=True),
        "current-frequency": psutil.cpu_freq().current,
        "max-frequency": psutil.cpu_freq().max,
        "min-frequency": psutil.cpu_freq().min,
        "cpu-percentage": psutil.cpu_percent(interval=0.5),
    }
    return {'cpu_info': cpu_info}

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
    return {'memory_info': memory_info}

def get_pci_info():
    pci_info = []
    dev_info_fields = {
        "Slot": "pci_address",
        "Vendor": "device_manufacturer",
        "NUMANode": "NUMA node",
    }
    try:
        # Use lspci command to get information about PCI devices
        lspci_output = (
            subprocess.check_output(["lspci", "-vmm"]).decode("utf-8").split("\n\n")
        )

        for device in lspci_output:
            if device:  # Check if device string is not empty
                device_info = {}
                lines = device.split("\n")

                for line in lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip()
                        if key == "Class":
                            if (
                                "Non-Volatile memory controller" in value
                                or "NVMe" in value
                            ):
                                device_info["device_type"] = "nvme"
                            elif "CXL" in value:
                                device_info["device_type"] = "cxl"
                            else:
                                continue  # Skip other device types
                        else:
                            try:
                                device_info[dev_info_fields[key]] = value
                            except Exception as e:
                                logger.debug(
                                    f"Device info not part of map, skipping this field: {e}"
                                )

                required_keys = ["pci_address", "device_type"]
                if all(key in device_info for key in required_keys):
                    pci_info.append(device_info)

    except Exception as e:
        logger.error(f"Error in getting pci info: {e}")

    return {'pci-info': pci_info}

def read_device_qos_data_from_config_file(config_file):

    if (os.path.exists(config_file) and os.path.isfile(config_file)) is False:
        logger.error(f"Config file {config_file} doesn't exist")
        return {}

    try:
        with open(config_file, 'r') as file:
            config_data = json.load(file)
            return config_data.get('device_qos', {})
    except Exception as e:
        logger.error(f"An error occurred in reading the config file for device QoS data: {e}")
    return {}

def get_device_info():
    """
    Get information of all the DRAM devices.

    Returns:
        dict: A dictionary containing DRAM device names.
    """
    device_info = dict()

    logger.info(f"Node name is {node_name}")
    if node_name is None:
        return {'device-info': device_info}

    node_name_str = node_name
    qos_data = read_device_qos_data_from_config_file(config_file)
    try:
        # Get the list of devices
        max_nodes = numactl_info.get_max_node()
        logger.debug(f"Max nodes is {max_nodes + 1}")
        for node in range(max_nodes + 1):
            cores = numactl_info.node_to_cpus(node)
            if len(cores) == 0:
                continue
            mem_obj = memory_info.node_memory_info(node)
            logger.debug(f"memory total, used for {node} is {mem_obj}")
            device = {
                'device_id': node,
                'serial_number': str(uuid.uuid3(uuid.NAMESPACE_DNS, node_name_str + "_" + str(node))),
                'numa_node': node,
                'total_capacity_MB': int(mem_obj[0]/(1024*1024)),
                'available_capacity_MB': int(mem_obj[1]/(1024*1024)),
                'vendor_device_type': "DRAM",
                'status': 'online',
                'advertised_qos': {
                    'avg_latency_ns': qos_data.get('avg_latency_ns', 100),
                    'p99_latency_ns': qos_data.get('p99_latency_ns', 100),
                    'io_per_sec': qos_data.get('io_per_sec', 1000000),
                    'BW_per_sec': qos_data.get('BW_per_sec', 1000),
                    'io_size_in_bytes': qos_data.get('io_size_in_bytes', 4096),
                    'qd': qos_data.get('qd', 32)
                }
            }
            device_info[device['serial_number']] = device
    except Exception as e:
        logger.error(f"Error in getting device info: {e}")

    logger.info(f"Device info is {device_info}")
    return {'device-info': device_info}

def get_node_stats():
    node_stats = dict()

    logger.info(f"Node name is {node_name}")

    try:
        node_stats["node_name"] = node_name

        node_stats["cpu"] = dict()
        node_stats["cpu"]["cores"] = psutil.cpu_count()
        node_stats["cpu"]["freq"] = psutil.cpu_freq().current
        node_stats["cpu"]["usage"] = psutil.cpu_percent()
        cpu_times_obj = psutil.cpu_times_percent()
        node_stats["cpu"]["user"] = cpu_times_obj.user
        node_stats["cpu"]["system"] = cpu_times_obj.system
        node_stats["cpu"]["idle"] = cpu_times_obj.idle
        node_stats["cpu"]["iowait"] = cpu_times_obj.iowait
        node_stats["cpu"]["nr_processes"] = len(psutil.pids())

        node_stats["memory"] = dict()
        virtual_memory_obj = psutil.virtual_memory()
        node_stats["memory"]["total_memory_mb"] = int(virtual_memory_obj.total/(1024*1024))
        node_stats["memory"]["available_memory_mb"] = int(virtual_memory_obj.available/(1024*1024))
        node_stats["memory"]["free_memory_mb"] = int(virtual_memory_obj.free/(1024*1024))
        swap_memory_obj = psutil.swap_memory()
        node_stats["memory"]["swap_total_mb"] = int(swap_memory_obj.total/(1024*1024))
        node_stats["memory"]["swap_free_mb"] = int(swap_memory_obj.free/(1024*1024))
    except Exception as e:
        logger.error(f"Error in getting node_stats: {e}")

    return {'node-stats': node_stats}

def get_all_info():
    """
    Get aggregated system information.
    
    Returns:
        dict: A dictionary containing aggregated system information.
    """
    func_list = [get_system_info, get_cpu_info, get_network_adapters_info,
                 get_memory_info, get_pci_info, get_device_info, get_node_stats]
    res = {k:v for func in func_list for k, v in func().items()}

    return res

def parse_args():

    parser = argparse.ArgumentParser(
        description="Python script to retrieve information about the node."
            "Currently only supporting 1 type of info at a time or all node info"
    )

    parser.add_argument(
        "-t",
        "--info-type",
        type=str,
        default="all",
        choices=["network", "memory", "cpu", "system", "pci", "device", "stats", "all"],
        help="Type of info to retrieve about the node. If no info type is provided, retrieve all info."
            "Types supported: network, memory, cpu, system, pci, device, all"
    )
    
    parser.add_argument("-l", "--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Log level for python logger."
                        "Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL")

    parser.add_argument(
        "-n",
        "--node-name",
        type=str,
        help="The node name used by the node server"
    )
    parser.add_argument(
        "-c",
        "--config-file",
        type=str,
        default="/usr/local/svk/feature_modules/node/config/node_mgmt_conf.json",
        help="Configuration file to read the defaults for the QoS Data (default: %(default)s)"
    )
    # Using hardcode default log file for now
    default_log_file = "/var/log/svk/find_node_info.log"
    args = parser.parse_args()

    return {'info_type': args.info_type, 'log_level': args.log_level, 'log_file_path': default_log_file,
            'node_name': args.node_name, 'config_file': args.config_file}

def init_logger(log_level: str, log_file_path: str):
    """Initialize the logger for find_node_info.py

    Args:
        log_level (str): Log level to set. Valid log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
        log_file_path (str): File path for the logger to print to

    Returns:
        Logger: A logger object for this python script with the given log level and file path set
    """
    global logger
    logger = logging.getLogger("find_node_info.py")
    logger.propagate = False
    
    log_levels_supported = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    if log_level in log_levels_supported:
        logger.setLevel(log_level)
    else:
        # Default log level
        logger.setLevel('INFO')

    formatter = logging.Formatter('[%(name)s]: %(asctime)s - %(levelname)s - %(message)s')

    try:
        dir_path = os.path.dirname(log_file_path)
        if dir_path and not os.path.exists(dir_path):
            raise FileNotFoundError(f"Directory '{dir_path}' does not exist.")
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(logger.level)
        
        
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    except Exception as e:
        print(f"Couldn't create log file: {e}")
        logger = None
        return
    logger.info("Logger is initialized")

def get_command(info_type: str):
    command_map = {'network': get_network_adapters_info, 'memory': get_memory_info, 'cpu': get_cpu_info,
                   'system': get_system_info, 'pci': get_pci_info, 'device': get_device_info, 
                   'stats':get_node_stats, 'all': get_all_info}
    return command_map[info_type]

def main():
    global node_name
    global config_file

    if platform.system() != "Linux":
        print("Platform not supported")
        return

    args = parse_args()

    init_logger(args["log_level"], args["log_file_path"])
    if logger is None:
        print("Logger not initialized, couldn't run find node info")
        return

    node_name = args["node_name"]
    config_file = args["config_file"]

    print(json.dumps(get_command(args['info_type'])(), indent=4))

if __name__ == "__main__":
    main()
