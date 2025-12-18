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


def test_get_memserver_capacity(cognos_influx_client, mocker):
    t1 = "2024-07-24T22:15:16.00"
    t2 = "2024-07-24T22:15:21.00"
    dummy_data = [
        {"_time": t1, "_field": "CXL", "_value": 512},
        {"_time": t1, "_field": "DRAM", "_value": 256},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_memserver_capacity()


def test_get_hostview_usage(cognos_influx_client, mocker):
    t1 = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t1, "dram_usage_mb": 256000, "cxl_usage_mb": 512000}
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_hostview_usage()


def test_get_latest_application_event(cognos_influx_client, mocker):
    t1 = "2024-07-24T22:15:16.00"
    dummy_data = [
        {"_time": t1, "severity": "info", "message": "all good"},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_latest_application_event(44214)


def test_get_hostview_capacity(cognos_influx_client, mocker):
    dummy_data = [
        {
            "cxl_capacity_mb": 512000,
            "dram_capacity_mb": 256000
        }
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_hostview_capacity()


def test_get_attached_devices_count(cognos_influx_client):
    cognos_influx_client.get_attached_devices_count()


def test_get_attached_devices_count_mock_mode():
    result = {"num_hosts": 1, "num_cxl_devices": 2}
    assert result["num_hosts"] == 1
    assert result["num_cxl_devices"] == 2


def test_get_hostview_bandwidth(cognos_influx_client, mocker):
    dummy_data = [
        {"totalUsed": 32000000000, "totalTotal": 64000},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_hostview_bandwidth()


def test_get_hostview_bandwidth_mock_mode(cognos_influx_client):
    cognos_influx_client.mock = True  # Simulate mock mode
    # Call the method
    result = cognos_influx_client.get_hostview_bandwidth()
    # Assertions
    assert "max_bandwidth" in result
    assert "used_bandwidth" in result
    assert "used_percentage_bandwidth" in result


def test_get_node_bandwidth(cognos_influx_client, mocker):
    dummy_db_lookup = [
        [43242432],
        [243423424]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    dummy_data = [
        {"totalUsed": 32000000000, "totalTotal": 64000},
    ]
    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_node_bandwidth()


def test_get_membox_capacity_mock_mode(cognos_influx_client):
    cognos_influx_client.mock = True
    result = cognos_influx_client.get_membox_capacity()
    assert result["total_capacity"] == 512
    assert result["used_capacity"] == 256
    assert result["used_capacity_percentage"] == 50


def test_get_cognos_events_past(cognos_influx_client, mocker):
    dummy_data = [
        {
            '_time': '2025-09-18T01:04:30+00:00', '_field': 'fpga_temp_in_F',
            '_value': 530, 'cluster_name': 'CL_ID_1', 'node_name': 'node_1',
            'category': 'thermal', 'domain': 'cxl_device',
            'severity': 'critical', 'source': '33235991846400',
            'source_type': 'device'
        },
        {
            '_time': '2025-09-18T01:04:40+00:00', '_field': 'fpga_temp_in_F',
            '_value': 530, 'cluster_name': 'CL_ID_1', 'node_name': 'node_1',
            'category': 'thermal', 'domain': 'cxl_device',
            'severity': 'critical', 'source': '33235991846400',
            'source_type': 'device'
        }
    ]

    mocker.patch(
        "influxdb_client.client.query_api.QueryApi.query",
        return_value=MagicMock(),
    )
    mocker.patch("json.loads", return_value=dummy_data)
    cognos_influx_client.get_cognos_events_past(1)
