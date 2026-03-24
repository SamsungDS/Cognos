import json
import pytest

from cognos.backend.remote_node_interface import RemoteAttachedNodeInterface
from requests.models import Response


def test_init_remoteattached_node_interface():
    RemoteAttachedNodeInterface()


def test_list_devices(mocker):
    dummy_remote_list_devices_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"devices\": [{\"dev_id\": 549755813888, "
            "\"dev_capacity\": 274877906944, \"dev_port\": 10, "
            "\"hosts_attached\": [\"node2\"]}, {\"dev_id\": 824633720832, "
            "\"dev_capacity\": 274877906944, \"dev_port\": 11, "
            "\"hosts_attached\": [\"node2\"]}]}"
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_remote_list_devices_output).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    remote_client = RemoteAttachedNodeInterface()
    remote_client.list_devices("node1", "CL_ID_2")


def test_list_hosts(mocker):
    dummy_remote_list_hosts_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"hosts\": [{\"id\": 551903297536, \"name\": \"node2\", "
            "\"mem_capacity\": 547608330240, \"host_target_ports\": "
            "[10, 11]}]}"
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_remote_list_hosts_output).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    remote_client = RemoteAttachedNodeInterface()
    remote_client.list_hosts("node1", "CL_ID_1")


def test_setup_info(mocker):
    dummy_remote_setup_info_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"Board\": {\"board_name\": \"Example Direct Config\", "
            "\"Mgmt_port_type\": \"PCIe\", \"json_version\": \"0100\", "
            "\"switch_mode\": \"direct\", \"management_port\": 1}, "
            "\"Hosts\": [{\"host_name\": \"node2\", \"host_port\": 2, "
            "\"deinit_active\": 1, \"host_port_type\": \"CXL_11\", "
            "\"classcode\": 0, \"host_aspm_active\": 1, "
            "\"host_sris_active\": 1, \"host_equalization\": 1, "
            "\"host_speed\": 5, \"host_width\": 8, \"host_addr\": "
            "\"0x008080000000\", \"host_size\": \"0x007f80000000\", "
            "\"endpoint\": [{\"memdev\": \"mem- 10\", \"target\": 10, "
            "\"mem_addr\": \"0x008080000000\", \"mem_size\": "
            "\"0x003f80000000\", \"dev_offset\": \"0\"}, {\"memdev\": "
            "\"mem- 11\", \"target\": 11, \"mem_addr\": \"0x00C000000000\", "
            "\"mem_size\": \"0x004000000000\", \"dev_offset\": \"0\"}]}], "
            "\"Devices\": [{\"dev_name\": \"DEV_10-256G\", \"dev_port\": 10, "
            "\"dev_addr\": \"0x008000000000\", \"dev_size\": "
            "\"0x004000000000\", \"dev_aspm_active\": 1, "
            "\"dev_sris_active\": 1, \"dev_lock_active\": 1, "
            "\"dev_speed\": 5, \"dev_width\": 8, \"dev_port_type\": "
            "\"CXL_20\"}, {\"dev_name\": \"DEV_11-256G\", \"dev_port\": 11, "
            "\"dev_addr\": \"0x00C000000000\", \"dev_size\": "
            "\"0x004000000000\", \"dev_aspm_active\": 1, "
            "\"dev_sris_active\": 1, \"dev_lock_active\": 1, "
            "\"dev_speed\": 5, \"dev_width\": 8, \"dev_port_type\": "
            "\"CXL_20\"}]}"
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_remote_setup_info_output).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    remote_client = RemoteAttachedNodeInterface()
    remote_client.setup_info("node3", "CL_ID_2")


def test_attach_device(mocker):
    dummy_attach_response = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": ["{\"rc\": 0}"]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_attach_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    remote_client = RemoteAttachedNodeInterface()
    remote_client.attach_device("node1", "CL_ID_1", 2343234, 43242434)


def test_detach_device(mocker):
    dummy_detach_response = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": ["{\"rc\": 0}"]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_detach_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    remote_client = RemoteAttachedNodeInterface()
    remote_client.detach_device("node2", "CL_ID_2", 3434243224, 434242)
