import ipaddress
import json
import logging
import math
import re
import os
import sys
import ast
import socket
import re
from collections import defaultdict, namedtuple
from dataclasses import dataclass, asdict
from flask import Flask, jsonify, make_response, Response, request
from typing import Dict, List


project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)
sys.path.insert(0, project_root)
from cognos.backend.db_query_constants import DUMMYIP  # noqa: E402

COGNOS_TABLES = ["devices", "hosts", "mem_box", "host_device_connections"]
current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(current_script_dir, "config", "config.json")
CAL_LOGGER = logging.getLogger('svkapp-cal-logger')


@dataclass
class App:
    app_name: str
    app_pid: int
    server_name: str
    throughput_ops_per_sec: int
    targetread_p99_latency: int
    targetwrite_p99_latency: int
    status: str
    message: str
    data_moved: str

    def to_dict(self) -> dict:
        return asdict(self)


def get_request_metadata(request) -> Dict[str, str]:
    request_metadata = {}
    try:
        request_metadata["request_method"] = (
            request.environ.get('REQUEST_METHOD')
        )
        request_metadata["path_info"] = (
            request.environ.get('PATH_INFO')
        )
        request_metadata["http_version"] = (
            request.environ.get('SERVER_PROTOCOL')
        )
        request_metadata["server_name"] = (
            request.environ.get('SERVER_NAME')
        )
        request_metadata["server_environment"] = (
            request.environ.get('SERVER_ENVIRONMENT')
        )
        request_metadata["server_protocol"] = (
            request.environ.get('SERVER_PROTOCOL')
        )
        request_metadata["browser_info"] = (
            request.headers.get('User-Agent')
        )
        request_metadata["referer"] = (
            request.headers.get('Referer')
        )
        request_metadata["referer-policy"] = (
            request.headers.get('Referer-Policy')
        )
    except Exception as error:
        CAL_LOGGER.error(
            f"Failed to parse incoming request metadata: {str(error)}"
        )
    return request_metadata


def serialize_request_metadata(request_metadata: Dict[str, str]):
    return (
        f"Incoming Request: {request_metadata.get('request_method')} "
        f"{request_metadata.get('path_info')} |"
        f" HTTP VERSION {request_metadata.get('http_version')} |"
        f" BROWSER {request_metadata.get('browser_info')} |"
        f" SERVER NAME {request_metadata.get('server_name')} |"
        f" SERVER ENV {request_metadata.get('server_environment')} |"
        f" SERVER PROTOCOL {request_metadata.get('server_protocol')} |"
        f" REFERER {request_metadata.get('referer')} |"
        f" REFERER POLICY {request_metadata.get('referer-policy')} \n"
    )


def check_service_running(service_name):
    status = os.system(f'systemctl is-active --quiet {service_name}')
    return status == 0


def check_cognos_mgmt_services():
    mgmt_services = [
        "cognos-app",
        "cognos-ui",
        "cognos-subscriber",
        "svk-restserver",
        "svk-controller",
        "influxdb"
    ]
    failed_services = []
    for service in mgmt_services:
        if not check_service_running(service):
            failed_services.append(service)
    return failed_services


def check_cognos_application_services():
    application_services = [
        "svk-node",
        "svk-svc-mgr"
    ]
    failed_services = []
    for service in application_services:
        if not check_service_running(service):
            failed_services.append(service)
    return failed_services


def get_service_status(service_name):
    status = os.system(f'systemctl status {service_name}')
    return status


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


def create_empty_payload() -> Dict:
    return {}


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
    Returns the absolute path to the SCMC_VERSION file.
    The file is typically located at the project root or installed location.
    """
    cwd_path = os.path.join(os.getcwd(), 'SCMC_VERSION')
    if os.path.isfile(cwd_path):
        return cwd_path

    root_folder = (
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
    version_file = os.path.join(root_folder, 'SCMC_VERSION')
    if os.path.isfile(version_file):
        return version_file
    else:
        # Fallback to original logic (three levels up from this file)
        fallback_folder = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '../../..')
        )
        fallback_path = os.path.join(fallback_folder, 'SCMC_VERSION')
        return fallback_path if os.path.isfile(fallback_path) else None


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
        CAL_LOGGER.error(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
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
        CAL_LOGGER.error(f"Unable to retrieve API version: {str(error)}")
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
