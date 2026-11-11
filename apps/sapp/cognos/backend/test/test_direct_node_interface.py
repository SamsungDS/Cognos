import json
import pytest

from cognos.backend.direct_node_interface import DirectAttachedNodeInterface
from requests.models import Response


def test_init_directnode_interface():
    DirectAttachedNodeInterface()


def test_list_devices(mocker):
    dummy_raw_list_devices_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"devices\":[{\"device_id\":33638416341504,"
            "\"vendor_device_type\":\"CMM-H\",\"pcie_addr\":\"0000:5a:00.0\"}"
            ",{\"device_id\":33638416369152,\"vendor_device_type\":\"CMM-H\","
            "\"pcie_addr\":\"0000:c6:00.0\"}]}"
            ]
        }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_raw_list_devices_output).encode("utf-8")
    )
    mocker.patch(
        "requests.post",
        return_value=dummy_response
    )
    direct_client = DirectAttachedNodeInterface()
    direct_client.list_devices("node1", "CL_ID_1")


def test_mock_list_devices():
    direct_client = DirectAttachedNodeInterface(mock=True)
    assert direct_client.list_devices("host-srf01", "CL_ID_1")


def test_list_devices_w_exception(mocker):
    dummy_raw_list_devices_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"devices\":[{\"device_id\":33638416341504,"
            "\"vendor_device_type\":\"CMM-H\",\"pcie_addr\":\"0000:5a:00.0\"}"
            ",{\"device_id\":33638416369152,\"vendor_device_type\":\"CMM-H\","
            "\"pcie_addr\":\"0000:c6:00.0\"}]}"
            ]
        }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_raw_list_devices_output).encode("utf-8")
    )
    mocker.patch(
        "requests.post",
        return_value=dummy_response,
    )
    mocker.patch(
        'json.loads',
        side_effect=Exception("failed response parsing")
    )
    direct_client = DirectAttachedNodeInterface()
    direct_client.list_devices("node2", "CL_ID_2")


def test_get_device_info(mocker):
    dummy_raw_get_devices_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"api_version\":1.0,\"device_id\":33638416369152,"
            "\"manufacturer\":\"Samsung\",\"serial_number\":305419896,"
            "\"FW_revision\":\"1.0.0\",\"location\":\"0000:c6:00.0\","
            "\"total_capacity_MB\":516079,\"feature_supported\":\"basic\","
            "\"vendor_device_type\":\"CMM-H\",\"cxl_device_type\":\"Type3\","
            "\"protocol\":\"CXL 2.0\",\"port_type\":\"root\","
            "\"mode_discovered\":\"auto\",\"connection_type\":\"CXL.mem\","
            "\"domain_type\":\"PCIe\",\"domain_id\":0,\"link_speed\":32,"
            "\"link_width\":8,\"available_capacity_MB\":443507,\"status\""
            ":\"active\",\"aspm_active\":false,\"sris_active\":false,"
            "\"lock_active\":false,\"numa_attached\":1,\"capabilities\":"
            "{\"Power Management version\":1},\"advertised_qos\":"
            "{\"avg_latency\":120,\"p99_latency\":350,\"io_per_sec\":50000,"
            "\"BW_per_sec\":1000000,\"io_size\":4096,\"qd\":32}}"
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_raw_get_devices_output).encode("utf-8")
    )
    mocker.patch(
        "requests.post",
        return_value=dummy_response
    )
    direct_client = DirectAttachedNodeInterface()
    direct_client.get_device_info(
        "node2",
        "CL_ID_2",
        423424234
    )


def test_get_device_info_w_exception(mocker):
    dummy_raw_get_devices_output = {
        "error_id_or_string_if_any": "", "error_code": 0, "api_version": "0.1",
        "response": [
            "{\"api_version\":1.0,\"device_id\":33638416369152,"
            "\"manufacturer\":\"Samsung\",\"serial_number\":305419896,"
            "\"FW_revision\":\"1.0.0\",\"location\":\"0000:c6:00.0\","
            "\"total_capacity_MB\":516079,\"feature_supported\":\"basic\","
            "\"vendor_device_type\":\"CMM-H\",\"cxl_device_type\":\"Type3\","
            "\"protocol\":\"CXL 2.0\",\"port_type\":\"root\","
            "\"mode_discovered\":\"auto\",\"connection_type\":\"CXL.mem\","
            "\"domain_type\":\"PCIe\",\"domain_id\":0,\"link_speed\":32,"
            "\"link_width\":8,\"available_capacity_MB\":443507,\"status\""
            ":\"active\",\"aspm_active\":false,\"sris_active\":false,"
            "\"lock_active\":false,\"numa_attached\":1,\"capabilities\":"
            "{\"Power Management version\":1},\"advertised_qos\":"
            "{\"avg_latency\":120,\"p99_latency\":350,\"io_per_sec\":50000,"
            "\"BW_per_sec\":1000000,\"io_size\":4096,\"qd\":32}}"
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_raw_get_devices_output).encode("utf-8")
    )
    mocker.patch(
        "requests.post",
        return_value=dummy_response
    )
    mocker.patch(
        'json.loads',
        side_effect=Exception("failed response parsing")
    )
    direct_client = DirectAttachedNodeInterface()
    direct_client.get_device_info(
        "node2",
        "CL_ID_2",
        423424234
    )


def test_mock_get_device_info():
    direct_client = DirectAttachedNodeInterface(mock=True)
    assert direct_client.get_device_info("host-srf01", "CL_ID_1", 33638416328448)
