from cognos.backend.base_node_interface import BaseNodeInterface
from cognos.backend.db_query_constants import APPLICATION_JSON
import json
import os
import requests
import cognos.backend.helper as helper
from typing import Dict, List


CONFIGS = helper.fetch_cognos_configs(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)
COGNOS_ENDPOINT = (
    CONFIGS["cognos_endpoint"]
    if CONFIGS["cognos_endpoint"].endswith("/")
    else CONFIGS["cognos_endpoint"] + "/"
)


class RemoteAttachedNodeInterface(BaseNodeInterface):
    """
    Interface for all CXL API for application servers that
    deal with remote-attached devices
    """
    def __init__(self):
        self.request_headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }

    @property
    def node_type(self):
        return "remote"

    def list_devices(self, node_name: str, cluster_name: str) -> List[Dict]:
        """
        Returns all remote-devices with metadata for a given node
        """
        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        cxl_command_params = json.dumps({
            "command": "ListDevices",
            "cluster_id": cluster_name,
            "FM_id": "203",
            "FM_endpoint": "samsung.com"
        })
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "ListDevices",
            "command_params": cxl_command_params
        }
        response = requests.post(
            request_url, json=request_body, headers=self.request_headers
        )
        if response.ok:
            try:
                devices = (
                    json.loads(response.json()['response'][0])['devices']
                )
                return devices
            except Exception as error:
                print(f"Failed to parse ListDevices response for remote node")
                return None
        return None

    def list_hosts(self, node_name: str, cluster_name: str) -> List[Dict]:
        """
        Returns: List of hosts info
        Return_Type: List[{host_info}]
        """
        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "ListHosts",
            "command_params": "{}"
        }
        response = requests.post(
            request_url, json=request_body, headers=self.request_headers
        )
        if response.ok:
            try:
                hosts = json.loads(response.json()['response'][0])['hosts']
                return hosts
            except Exception as error:
                print(f"Failed to parse ListHosts response for remote node")
                return None
        return None

    def setup_info(self, node_name: str, cluster_name: str) -> List[Dict]:
        """
        Returns initial state / configuration of CMM-B and corresponding
        hosts and devices
        """
        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "SetupInfo",
            "command_params": "{}"
        }
        response = requests.post(
            request_url, json=request_body, headers=self.request_headers
        )
        if response.ok:
            try:
                setup = json.loads(response.json()['response'][0])
            except Exception as error:
                print(f"Failed to parse SetupInfo response for remote node")
                return None
        return None

    def attach_device(self, node_name: str, cluster_name: str,
                      host_id: int, dev_id: int) -> bool:
        """
        Performs attach operation for a remote device and node

        Returns:
          True: if op successful
          False: if op failed
        """
        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        cxl_command_params = json.dumps({
            "command": "AttachMemory",
            "cluster_id": cluster_name,
            "dev_id": dev_id,
            "host_id": host_id,
            "mode": "direct"
        })
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "AttachMemory",
            "command_params": cxl_command_params
        }

        response = requests.post(
            request_url, json=request_body, headers=self.request_headers
        )
        if response.ok:
            try:
                rc = (
                    json.loads(response.json()['response'][0])['rc']
                )
                return rc == 0
            except Exception as error:
                print(f"Failed to parse AttachDevice response for remote node")
                return None
        return None

    def detach_device(self, node_name: str, cluster_name: str,
                      host_id: int, dev_id: int) -> bool:
        """
        Performs detach operation for a remote device and node

        Returns:
          True: if op successful
          False: if op failed
        """
        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        cxl_command_params = json.dumps({
            "command": "DetachMemory",
            "cluster_id": cluster_name,
            "dev_id": dev_id,
            "host_id": host_id,
            "mode": "direct"
        })
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "DetachMemory",
            "command_params": cxl_command_params
        }

        response = requests.post(
            request_url, json=request_body, headers=self.request_headers
        )
        if response.ok:
            try:
                rc = (
                    json.loads(response.json()['response'][0])['rc']
                )
                return rc == 0
            except Exception as error:
                print(f"Failed to parse DetachDevice response for remote node")
                return None
        return None
