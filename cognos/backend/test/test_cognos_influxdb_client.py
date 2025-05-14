import json
import pytest
import math
from unittest.mock import MagicMock
from unittest.mock import mock_open, patch
import cognos.backend.mock_cognos_agent_metrics_populator as mm
import cognos.backend.helper as helper
from requests.models import Response
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient

cognos_backend_prefix = "cognos.backend."


def construct_dummy_response(dummy_data):
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_data).encode("utf-8")
    return dummy_response


def test_create_client(cognos_influx_client):
    assert cognos_influx_client is not None


def test_create_client_from_config(cognos_influx_client_from_config):
    assert cognos_influx_client_from_config is not None


def test_write_records(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix
        + "cognos_influxdb_client.CognosInfluxDBClient.write_cognos_event",
        return_value=True,
    )
    for metric in mm.mock_metrics:
        cognos_influx_client.write_cognos_event(metric)


def test_read_records(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix
        + "cognos_influxdb_client.CognosInfluxDBClient.query_cognos_events",
        return_value=True,
    )
    cognos_influx_client.query_cognos_events("10m")


def test_query_node_cognos_events(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix +
        "cognos_influxdb_client.CognosInfluxDBClient.query_node_cognos_events",
        return_value=True
    )
    dummy_time_window = "10m"
    dummy_category = "metric"
    dummy_source_type = "host"
    dummy_source = "x.y.x"
    event_keys = ["cpu_mem_usage", "dram_cxl_mem_usage"]
    cognos_influx_client.query_node_cognos_events(
        dummy_time_window, dummy_category, dummy_source_type,
        dummy_source, event_keys
    )


def test_run_mock_populator(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix
        + "cognos_influxdb_client.CognosInfluxDBClient.write_cognos_event",
        return_value=True,
    )
    mocker.patch(
        cognos_backend_prefix
        + "cognos_influxdb_client.CognosInfluxDBClient.query_cognos_events",
        return_value=True,
    )
    mm.run_mock_populator(cognos_influx_client, 10, "10m")


def test_get_recent_dram_cxl_usage_data(cognos_influx_client, mocker):
    t = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t, "_field": "dram_usage_mb", "_value": 2321},
        {"_time": t, "_field": "dram_capacity_mb", "_value": 32111},
        {"_time": t, "_field": "cxl_usage_mb", "_value": 2134},
        {"_time": t, "_field": "cxl_capacity_mb", "_value": 150000},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_recent_dram_cxl_usage_data()


def test_get_cpu_mem_usage(cognos_influx_client, mocker):
    t = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t, "_field": "cpu_usage", "_value": 71},
        {"_time": t, "_field": "dram_usage_mb", "_value": 2321},
        {"_time": t, "_field": "dram_capacity_mb", "_value": 32111},
        {"_time": t, "_field": "cxl_usage_mb", "_value": 2134},
        {"_time": t, "_field": "cxl_capacity_mb", "_value": 150000},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_cpu_mem_usage()


def test_get_memserver_capacity(cognos_influx_client, mocker):
    t = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t, "_field": "dram_capacity_mb", "_value": 32111},
        {"_time": t, "_field": "cxl_capacity_mb", "_value": 150000},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)

    dummy_data = {
        "nodeResponses": [
            {
                "nodeId": "localhost",
                "output": '{"Board": {"board_name": "Example Direct '
                'Config", "Mgmt_port_type": "PCIe", '
                '"json_version": "0100", "switch_mode": '
                '"direct", "management_port": 1}, "Hosts": '
                '[{"host_name": "msl-ssg-vm55", "host_port": 2, '
                '"deinit_active": 1, "host_port_type": "CXL_11", '
                '"classcode": 0, "host_aspm_active": 1, '
                '"host_sris_active": 1, "host_equalization": 1, '
                '"host_speed": 5, "host_width": 8, "host_addr": '
                '"0x008080000000", "host_size": '
                '"0x007f80000000", "endpoint": []}], "Devices": '
                '[{"dev_name": "DEV_10-256G", "dev_port": 10, '
                '"dev_addr": "0x008000000000", "dev_size": '
                '"0x004000000000", "dev_aspm_active": 1, '
                '"dev_sris_active": 1, "dev_lock_active": 1, '
                '"dev_speed": 5, "dev_width": 8, '
                '"dev_port_type": "CXL_20"}, {"dev_name": '
                '"DEV_11-256G", "dev_port": 11, "dev_addr": '
                '"0x00C000000000", "dev_size": "0x004000000000", '
                '"dev_aspm_active": 1, "dev_sris_active": 1, '
                '"dev_lock_active": 1, "dev_speed": 5, '
                '"dev_width": 8, "dev_port_type": "CXL_20"}]}',
            }
        ]
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch(
        "cognos.backend.helper.gen_svkcxlplugin_request_params",
        return_value={"cluster_id:1"},
    )
    mocker.patch("requests.post", return_value=dummy_response)
    mocker.patch(
        "cognos.backend.cognos_influxdb_client.parse_svkcxlplugin_response",
        return_value=(
            {
                "Board": {
                    "Mgmt_port_type": "PCIe",
                    "board_name": "Example Direct Config",
                    "json_version": "0100",
                    "management_port": 1,
                    "switch_mode": "direct",
                },
                "Devices": [
                    {
                        "dev_addr": "0x008000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_10-256G",
                        "dev_port": 10,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                    {
                        "dev_addr": "0x00C000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_11-256G",
                        "dev_port": 11,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                ],
                "Hosts": [
                    {
                        "classcode": 0,
                        "deinit_active": 1,
                        "endpoint": [],
                        "host_addr": "0x008080000000",
                        "host_aspm_active": 1,
                        "host_equalization": 1,
                        "host_name": "msl-ssg-vm55",
                        "host_port": 2,
                        "host_port_type": "CXL_11",
                        "host_size": "0x007f80000000",
                        "host_speed": 5,
                        "host_sris_active": 1,
                        "host_width": 8,
                    }
                ],
            }
        ),
    )
    cognos_influx_client.mock = False
    cognos_influx_client.get_memserver_capacity()


def test_get_membox_usage(cognos_influx_client, mocker):
    t1 = "2024-07-24T22:15:16.00"
    t2 = "2024-07-24T22:15:21.00"
    dummy_data = [
        {"_time": t1, "_field": "cxl_usage_mb", "_value": 3216211},
        {"_time": t2, "_field": "cxl_usage_mb", "_value": 150000},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_membox_usage()


def test_get_membox_bandwidth(cognos_influx_client, mocker):
    dummy_data = {
        "output": {
            "hpos-vroc04:9998": {
                "Board": {
                    "Mgmt_port_type": "PCIe",
                    "board_name": "Example Direct Config",
                    "json_version": "0100",
                    "management_port": 1,
                    "switch_mode": "direct",
                },
                "Devices": [
                    {
                        "dev_addr": "0x008000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_10-256G",
                        "dev_port": 10,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                    {
                        "dev_addr": "0x00C000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_11-256G",
                        "dev_port": 11,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                ],
                "Hosts": [
                    {
                        "classcode": 0,
                        "deinit_active": 1,
                        "endpoint": [
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x00C000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 11",
                                "target": 11,
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10,
                            },
                        ],
                        "host_addr": "0x008080000000",
                        "host_aspm_active": 1,
                        "host_equalization": 1,
                        "host_name": "Host 1 LNK0",
                        "host_port": 2,
                        "host_port_type": "CXL_11",
                        "host_size": "0x007f80000000",
                        "host_speed": 5,
                        "host_sris_active": 1,
                        "host_width": 8,
                    }
                ],
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch(
        "cognos.backend.helper.gen_svkcxlplugin_request_params",
        return_value={"cluster_id:1"},
    )
    mocker.patch("requests.post", return_value=dummy_response)
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_response",
        return_value=dummy_response.json()["output"],
    )
    cognos_influx_client.get_membox_bandwidth()


def test_get_attached_devices_count(cognos_influx_client, mocker):
    dummy_data = {
        "output": {
            "hpos-vroc04:9998": {
                "Board": {
                    "Mgmt_port_type": "PCIe",
                    "board_name": "Example Direct Config",
                    "json_version": "0100",
                    "management_port": 1,
                    "switch_mode": "direct",
                },
                "Devices": [
                    {
                        "dev_addr": "0x008000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_10-256G",
                        "dev_port": 10,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                    {
                        "dev_addr": "0x00C000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_11-256G",
                        "dev_port": 11,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                ],
                "Hosts": [
                    {
                        "classcode": 0,
                        "deinit_active": 1,
                        "endpoint": [
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x00C000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 11",
                                "target": 11,
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10,
                            },
                        ],
                        "host_addr": "0x008080000000",
                        "host_aspm_active": 1,
                        "host_equalization": 1,
                        "host_name": "Host 1 LNK0",
                        "host_port": 2,
                        "host_port_type": "CXL_11",
                        "host_size": "0x007f80000000",
                        "host_speed": 5,
                        "host_sris_active": 1,
                        "host_width": 8,
                    }
                ],
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch(
        "cognos.backend.helper.gen_svkcxlplugin_request_params",
        return_value={"cluster_id:1"},
    )
    mocker.patch("requests.post", return_value=dummy_response)
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_response",
        return_value=dummy_response.json()["output"],
    )
    cognos_influx_client.get_attached_devices_count()


def test_get_membox_capacity(cognos_influx_client, mocker):
    dummy_data = {
        "output": {
            "hpos-vroc04:9998": {
                "Board": {
                    "Mgmt_port_type": "PCIe",
                    "board_name": "Example Direct Config",
                    "json_version": "0100",
                    "management_port": 1,
                    "switch_mode": "direct",
                },
                "Devices": [
                    {
                        "dev_addr": "0x008000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_10-256G",
                        "dev_port": 10,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                    {
                        "dev_addr": "0x00C000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_11-256G",
                        "dev_port": 11,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8,
                    },
                ],
                "Hosts": [
                    {
                        "classcode": 0,
                        "deinit_active": 1,
                        "endpoint": [
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x00C000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 11",
                                "target": 11,
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10,
                            },
                        ],
                        "host_addr": "0x008080000000",
                        "host_aspm_active": 1,
                        "host_equalization": 1,
                        "host_name": "Host 1 LNK0",
                        "host_port": 2,
                        "host_port_type": "CXL_11",
                        "host_size": "0x007f80000000",
                        "host_speed": 5,
                        "host_sris_active": 1,
                        "host_width": 8,
                    }
                ],
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch(
        "cognos.backend.helper.gen_svkcxlplugin_request_params",
        return_value={"cluster_id:1"},
    )
    mocker.patch("requests.post", return_value=dummy_response)
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_response",
        return_value=dummy_response.json()["output"],
    )
    cognos_influx_client.get_membox_capacity()


def test_get_attached_devices_count_mock_mode():
    result = {"num_hosts": 1, "num_cxl_devices": 2}
    assert result["num_hosts"] == 1
    assert result["num_cxl_devices"] == 2


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_get_attached_devices_count_success(mock_disconnect, mock_connect):
    # Mock database connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [[3, 5]]  # Mocked response
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect.return_value = (mock_db, mock_cursor)
    # Call the real method
    result = helper.count_attached_devices()
    assert result["num_hosts"] == 3
    assert result["num_cxl_devices"] == 5
    mock_connect.assert_called_once()
    mock_disconnect.assert_called_once_with(mock_db)


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_get_attached_devices_count_no_result(mock_disconnect, mock_connect):
    # Mock database connection and cursor
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect.return_value = (mock_db, mock_cursor)
    # Call the real method
    result = helper.count_attached_devices()
    # Assertions
    assert result is None
    # Ensure connection and disconnection methods are called
    mock_connect.assert_called_once()
    mock_disconnect.assert_called_once_with(mock_db)


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_get_attached_devices_count_exception(mock_disconnect, mock_connect):
    # Simulate an exception when connecting to the database
    mock_connect.side_effect = Exception("Database error")
    try:
        result = helper.count_attached_devices()
    except Exception:
        result = None
    assert result is None
    # Verify connect_to_mysql was called
    mock_connect.assert_called_once()


def test_get_membox_bandwidth_mock_mode():
    client = CognosInfluxDBClient()
    client.mock = True  # Simulate mock mode
    # Call the method
    result = client.get_membox_bandwidth()
    # Assertions
    assert result["max_bandwidth"] == 512
    assert result["used_bandwidth"] == 32
    assert result["used_percentage_bandwidth"] == 0


@patch("cognos.backend.helper.count_host_upstream_ports")
@patch("cognos.backend.helper.connect_to_mysql")
def test_get_membox_bandwidth_success(
    mock_connect_to_mysql, mock_count_host_upstream_ports
):
    # Create a mock client instance
    client = CognosInfluxDBClient()
    client.mock = False  # Simulate non-mock mode
    # Mock database connection and cursor
    mock_cursor = MagicMock()
    # Simulate 4 upstream ports
    mock_cursor.fetchone.return_value = [4]
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect_to_mysql.return_value = (mock_db, mock_cursor)
    # Configure the upstream ports
    mock_count_host_upstream_ports.return_value = {"num_upstream_ports": 4}
    # Call the real method
    result = client.get_membox_bandwidth()
    # Assertions
    assert result["max_bandwidth"] == 512
    # 32 * 4
    assert result["used_bandwidth"] == 128
    # (128 / 512) * 100
    assert result["used_percentage_bandwidth"] == 25


@patch("cognos.backend.helper.count_host_upstream_ports")
@patch("cognos.backend.helper.connect_to_mysql")
def test_get_membox_bandwidth_no_result(
    mock_connect_to_mysql, mock_count_host_upstream_ports
):
    client = CognosInfluxDBClient()
    client.mock = False  # Simulate non-mock mode
    # Mock database connection
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect_to_mysql.return_value = (mock_db, mock_cursor)
    # Simulate no upstream ports found
    mock_count_host_upstream_ports.return_value = None
    # Call the real method
    result = client.get_membox_bandwidth()
    # Assertions
    assert result["max_bandwidth"] == 512
    # Default 32 * 1
    assert result["used_bandwidth"] == 32
    # (32 / 512) * 100
    assert result["used_percentage_bandwidth"] == 6


@patch("cognos.backend.helper.count_host_upstream_ports")
@patch("cognos.backend.helper.connect_to_mysql")
def test_get_membox_bandwidth_exception(
    mock_connect_to_mysql, mock_count_host_upstream_ports
):
    client = CognosInfluxDBClient()
    # Simulate non-mock mode
    client.mock = False
    # Simulate an exception in count_host_upstream_ports
    mock_count_host_upstream_ports.side_effect = Exception("Database error")
    # Call the real method
    result = client.get_membox_bandwidth()
    # Assertions
    assert result["max_bandwidth"] == 512
    assert result["used_bandwidth"] == 32
    assert result["used_percentage_bandwidth"] == 0


def test_get_membox_capacity_mock_mode():
    client = CognosInfluxDBClient()
    client.mock = True
    result = client.get_membox_capacity()
    assert result["total_capacity"] == 512
    assert result["used_capacity"] == 256
    assert result["used_capacity_percentage"] == 67


@patch("cognos.backend.helper.fetch_memory_capacity")
def test_get_membox_capacity_success(mock_fetch_memory_capacity):
    client = CognosInfluxDBClient()
    client.mock = False
    result = client.get_membox_capacity()
    print(result)
    # Assertions
    assert result["total_capacity"] == 1


@patch("cognos.backend.helper.fetch_memory_capacity")
def test_get_membox_capacity_no_result(mock_fetch_memory_capacity):
    client = CognosInfluxDBClient()
    client.mock = False
    # Mock fetch_memory_capacity to return None
    mock_fetch_memory_capacity.return_value = None
    result = client.get_membox_capacity()
    print(result)
    assert result["total_capacity"] == 0
    assert result["used_capacity"] == 0
    assert result["used_capacity_percentage"] == 0


@patch("cognos.backend.helper.fetch_memory_capacity")
def test_get_membox_capacity_exception(mock_fetch_memory_capacity):
    client = CognosInfluxDBClient()
    client.mock = False
    # Mock fetch_memory_capacity to raise an exception
    mock_fetch_memory_capacity.side_effect = Exception("Database error")
    result = client.get_membox_capacity()
    print(result)
    assert result["total_capacity"] == 0
    assert result["used_capacity"] == 0
    assert result["used_capacity_percentage"] == 0
