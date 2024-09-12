import json
import pytest
from unittest.mock import MagicMock

from cognos.backend.mock_cognos_agent_metrics_populator import (
    mock_metrics, run_mock_populator
)
from requests.models import Response

cognos_backend_prefix = 'cognos.backend.'


def construct_dummy_response(dummy_data):
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_data).encode('utf-8')
    return dummy_response


def test_create_client(cognos_influx_client):
    assert cognos_influx_client is not None


def test_create_client_from_config(cognos_influx_client_from_config):
    assert cognos_influx_client_from_config is not None


def test_write_records(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix +
        'cognos_influxdb_client.CognosInfluxDBClient.write_cognos_event',
        return_value=True
    )
    for metric in mock_metrics:
        cognos_influx_client.write_cognos_event(metric)


def test_read_records(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix +
        'cognos_influxdb_client.CognosInfluxDBClient.query_cognos_events',
        return_value=True
    )
    cognos_influx_client.query_cognos_events('10m')


def test_run_mock_populator(cognos_influx_client, mocker):
    mocker.patch(
        cognos_backend_prefix +
        'cognos_influxdb_client.CognosInfluxDBClient.write_cognos_event',
        return_value=True
    )
    mocker.patch(
        cognos_backend_prefix +
        'cognos_influxdb_client.CognosInfluxDBClient.query_cognos_events',
        return_value=True
    )
    run_mock_populator(cognos_influx_client, 10, '10m')


def test_get_recent_dram_cxl_usage_data(cognos_influx_client, mocker):
    t = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t, "_field": "dram_usage_mb", "_value": 2321},
        {"_time": t, "_field": "dram_capacity_mb", "_value": 32111},
        {"_time": t, "_field": "cxl_usage_mb", "_value": 2134},
        {"_time": t, "_field": "cxl_capacity_mb", "_value": 150000}
    ]
    mocker.patch('influxdb_client.client.query_api.QueryApi.query',
                 return_value=MagicMock())
    mocker.patch(
        'json.loads', return_value=dummy_data
    )
    cognos_influx_client.get_recent_dram_cxl_usage_data()


def test_get_cpu_mem_usage(cognos_influx_client, mocker):
    t = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t, "_field": "cpu_usage", "_value": 71},
        {"_time": t, "_field": "dram_usage_mb", "_value": 2321},
        {"_time": t, "_field": "dram_capacity_mb", "_value": 32111},
        {"_time": t, "_field": "cxl_usage_mb", "_value": 2134},
        {"_time": t, "_field": "cxl_capacity_mb", "_value": 150000}
    ]
    mocker.patch('influxdb_client.client.query_api.QueryApi.query',
                 return_value=MagicMock())
    mocker.patch(
        'json.loads', return_value=dummy_data
    )
    cognos_influx_client.get_cpu_mem_usage()


def test_get_memserver_capacity(cognos_influx_client, mocker):
    t = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t, "_field": "dram_capacity_mb", "_value": 32111},
        {"_time": t, "_field": "cxl_capacity_mb", "_value": 150000}
    ]
    mocker.patch('influxdb_client.client.query_api.QueryApi.query',
                 return_value=MagicMock())
    mocker.patch(
        'json.loads', return_value=dummy_data
    )
    cognos_influx_client.get_memserver_capacity()


def test_get_membox_usage(cognos_influx_client, mocker):
    t1 = "2024-07-24T22:15:16.00"
    t2 = "2024-07-24T22:15:21.00"
    dummy_data = [
        {"_time": t1, "_field": "cxl_usage_mb", "_value": 3216211},
        {"_time": t2, "_field": "cxl_usage_mb", "_value": 150000}
    ]
    mocker.patch('influxdb_client.client.query_api.QueryApi.query',
                 return_value=MagicMock())
    mocker.patch(
        'json.loads', return_value=dummy_data
    )
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
                    "switch_mode": "direct"
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
                        "dev_width": 8
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
                        "dev_width": 8
                    }
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
                                "target": 11
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10
                            }
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
                        "host_width": 8
                    }
                ]
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch('json.loads', return_value=dummy_response.json()["output"])
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
                    "switch_mode": "direct"
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
                        "dev_width": 8
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
                        "dev_width": 8
                    }
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
                                "target": 11
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10
                            }
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
                        "host_width": 8
                    }
                ]
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch('json.loads', return_value=dummy_response.json()["output"])
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
                    "switch_mode": "direct"
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
                        "dev_width": 8
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
                        "dev_width": 8
                    }
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
                                "target": 11
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10
                            }
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
                        "host_width": 8
                    }
                ]
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch('json.loads', return_value=dummy_response.json()["output"])
    cognos_influx_client.get_membox_capacity()
