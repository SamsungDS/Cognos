import json
import math
import os
import socket
from collections import defaultdict, namedtuple

import app


def fetch_cognos_configs(parent_dir, file_name):
    config_file_path = os.path.join(parent_dir, 'config', file_name)
    configs = ''
    try:
        with open(config_file_path, 'r') as config_file:
            configs = json.load(config_file)
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
    return configs


def fetch_api_version(parent_dir):
    try:
        with open(os.path.join(parent_dir, 'VERSION'), 'r') as v:
            API_VERSION = v.read().strip()
            return API_VERSION
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve API version: {str(error)}"
        )


def get_devport_name_map(devices_payload):
    dev_port_name_map = defaultdict()
    for device in devices_payload:
        dev_port_name_map[device["dev_port"]] = device["dev_name"]
    return dev_port_name_map


def get_devport_hostname_map(hosts_payload):
    devport_hostname_map = defaultdict()
    for host in hosts_payload:
        for endpt in host["endpoint"]:
            devport_hostname_map[endpt["target"]] = host["host_name"]
    return devport_hostname_map


def init_devices_table(devices_payload, dev_port_name_map):
    for i in range(len(devices_payload)):
        dev_name = dev_port_name_map[devices_payload[i]["dev_port"]]
        devices_payload[i]["dev_name"] = dev_name
    app.insert_devices(devices_payload)


def init_hosts_table(hosts_payload):
    app.insert_hosts(hosts_payload)


def init_connections_table(devport_hostname_map):
    for dev_port, host_name in devport_hostname_map.items():
        dev_id, dev_name = (
            app.get_deviceid_and_devicename_from_port(dev_port)
        )
        host_id = app.get_hostid_from_name(host_name)
        app.insert_connection(host_id, host_name, dev_id, dev_name)


def get_dummy_mb_info():
    TB = 1024 * 1024 * 1024 * 1024
    GB = 1024 * 1024 * 1024
    mb_mgmt_ip = socket.gethostbyname(socket.gethostname())
    mb_info = {
        'data_ports': 15,
        'mgmt_ports': 1,
        'mgmt_ip': f'{mb_mgmt_ip}',
        'mgmt_port': 5000,
        'mgmt_port_type': 'PCIe',
        'mgmt_netmask': '255.255.254.0',
        'form_factor': '4U',
        'manufacturer': 'Samsung',
        'memory_size': f'{((256 * GB) * 6) / TB}T',
        'power_state': 'ON',
        'health': 'OK',
        'protocol_version': 2.0
    }
    return mb_info


def get_available_devices_fromdb():
    db, cursor = app.connect_to_mysql()
    query = (
        "SELECT dev_name FROM devices WHERE dev_name not in "
        "(SELECT dev_name FROM host_device_connections);"
    )
    cursor.execute(query)
    result = cursor.fetchall()
    app.disconnect_mysql(db)
    return result


def process_membox_capacity_payload(devices_payload):
    num_devices = 0
    num_hosts = 0
    for dev in devices_payload:
        num_devices += 1
        num_hosts += 1 if dev['hosts_attached'] else 0
    total_capacity = 256 * num_devices
    used_capacity = 256 * num_hosts
    devices_payload = [{
        "total_capacity": total_capacity,
        "used_capacity": used_capacity,
        "used_capacity_percentage": (
            math.floor((used_capacity/total_capacity) * 100)
        )
    }]
    return devices_payload
