from cognos.backend.base_node_interface import BaseNodeInterface
from cognos.backend.db_query_constants import APPLICATION_JSON
import cognos.backend.mock_constants as mock_response
import cognos.backend.helper as helper
import json
import os
import requests
from typing import Dict


CONFIGS = helper.fetch_cognos_configs(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)
COGNOS_ENDPOINT = (
    CONFIGS["cognos_endpoint"]
    if CONFIGS["cognos_endpoint"].endswith("/")
    else CONFIGS["cognos_endpoint"] + "/"
)


class DirectAttachedNodeInterface(BaseNodeInterface):
    """
    Interface for all CXL API for application servers that
    deal with direct-attached devices
    """
    def __init__(self, mock=False):
        self.request_headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }
        self.mock = mock

    @property
    def node_type(self):
        return "direct"

    def list_devices(self, node_name: str, cluster_name: str) -> Dict:
        """
        Returns all direct-attached devices and their metadata
        """
        if self.mock:
            return mock_response.MOCK_DEVICES[node_name]

        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "list_devices",
            "command_params": json.dumps({"device_id": []})
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
                print(f"Failed to parse list_devices response for direct node")
                return None
        return None

    def get_device_info(self, node_name: str, cluster_name: str,
                        device_id: int) -> Dict:
        """
        Returns more detailed information for a given devices such as
        link speed, domain type, serial number, etc..
        """
        if self.mock:
            return mock_response.MOCK_DEVICE_INFO[node_name][device_id]

        request_url = f"{COGNOS_ENDPOINT}nodes/{node_name}/features/cxl"
        request_body = {
            "cluster_name": cluster_name,
            "command_name": "get_device_info",
            "command_params": json.dumps(
                {"domain": "", "device_id": device_id}
            )
        }
        response = requests.post(
            request_url, json=request_body, headers=self.request_headers
        )
        if response.ok:
            try:
                device = json.loads(
                    response.json()['response'][0]
                )
                return device
            except Exception as error:
                print(f"Failed to parse GetDeviceInfo for direct node")
                return None
        return None
