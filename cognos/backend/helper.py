import ipaddress
import json
import math
import re
import os
import sys
import ast
import socket
from collections import defaultdict, namedtuple
from flask import Flask, jsonify, make_response, Response
from typing import Dict, List

project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)
sys.path.insert(0, project_root)
from cognos.backend.db_query_constants import DUMMYIP  # noqa: E402

COGNOS_TABLES = ["devices", "hosts", "mem_box", "host_device_connections"]
current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(current_script_dir, "config", "config.json")


def is_hexadecimal(value: str) -> bool:
    """
    Checks if a given value is hexadecimal
    """
    # use re to check if the string matches hexadecimal format
    if isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]+", value):
        return True
    return False


def is_valid_ip_addr(ip: str) -> bool:
    """
    Validates if an ip addr is valid
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_endpoint_reachable(ip_address, port, timeout=1) -> bool:
    """
    Validates if an endpoint is reachable
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip_address, port))
        return True
    except (socket.timeout, ConnectionRefusedError):
        return False
    finally:
        s.close()


def is_valid_device_type(type: str):
    """
    Checks if device is a valid Cognos Device Type
    """
    if type not in ['CMM-D', 'CMM-H']:
        return False
    else:
        return True


def create_empty_response() -> Response:
    """
    Creates a valid flask resopnse with empty data
    """
    return make_response('', 204)


def create_response_from_payload(payload) -> Response:
    """
    Creates a successful flask response wrapped around
    a given payload
    """
    response = jsonify(payload)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


def create_notfound_response_from_payload(payload) -> Response:
    """
    Creates a not-found '404' flask response
    with a given payload
    """
    response = jsonify(payload)
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.status_code = 404
    return response


def failed_response(msg: str) -> Response:
    """
    Creates a failed flask server response with message
    """
    payload = {"status": 500, "error": msg}
    response = jsonify(payload)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


def get_scmc_version_file() -> str:
    """
    Returns: Filepath of VERSION file containing svk-app version
             VERSION file will always be located in the root of
             the install location or the development repository
    """
    root_folder = (
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
    return (
        os.path.join(root_folder, 'SCMC_VERSION')
        if os.path.exists(root_folder + os.sep + 'SCMC_VERSION')
        else None
    )


def fetch_cognos_configs(parent_dir: str, file_name: str) -> Dict:
    """
    Fetches cognos configs from a single config file. Paramaterized
    to enable user to choose which config file to load from
    """
    config_file_path = os.path.join(parent_dir, "config", file_name)
    configs = ""
    try:
        with open(config_file_path, "r") as config_file:
            configs = json.load(config_file)
    # pragma: no cover
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
    return configs


def fetch_cal_api_version(parent_dir: str) -> str:
    """
    Gets CAL flask server API Version #.
    This # is used as part of the url route when making requests
    to CAL
    """
    try:
        with open(os.path.join(parent_dir, "VERSION"), "r") as v:
            API_VERSION = v.read().strip()
            return API_VERSION
    # pragma: no cover
    except Exception as error:
        raise RuntimeError(f"Unable to retrieve API version: {str(error)}")


def mb_to_GB(val: int) -> int:
    return val // 1024


def bytes_to_MB(val: int) -> int:
    return val / (1024 * 1024)


def bytes_to_GB(val: int) -> int:
    return val / (1024**3)


def get_cognos_influx_functions() -> List[str]:
    """
    Returns a list of valid string
    representations of current Cognos Events fns
    """
    return [
        "get_recent_dram_cxl_usage_data",
        "get_cpu_mem_usage",
        "get_memserver_capacity",
        "get_membox_usage",
        "get_membox_capacity",
        "get_membox_bandwidth",
        "get_attached_devices_count",
    ]


def get_dummy_mb_info() -> Dict:
    """
    Returns mocked memory box metadata
    """
    TB = 1024 * 1024 * 1024 * 1024
    GB = 1024 * 1024 * 1024
    mb_mgmt_ip = socket.gethostbyname(socket.gethostname())
    mb_info = {
        "data_ports": 15,
        "mgmt_ports": 1,
        "mgmt_ip": f"{mb_mgmt_ip}",
        "mgmt_port": 5000,
        "mgmt_port_type": "PCIe",
        "mgmt_netmask": DUMMYIP,
        "form_factor": "4U",
        "manufacturer": "Samsung",
        "memory_size": f"{((256 * GB) * 6) / TB}T",
        "power_state": "ON",
        "health": "OK",
        "protocol_version": 2.0,
    }
    return mb_info
