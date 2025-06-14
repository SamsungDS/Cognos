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


def test_get_attached_devices_count(cognos_influx_client):
    cognos_influx_client.get_attached_devices_count()


def test_get_attached_devices_count_mock_mode():
    result = {"num_hosts": 1, "num_cxl_devices": 2}
    assert result["num_hosts"] == 1
    assert result["num_cxl_devices"] == 2


def test_get_membox_bandwidth_mock_mode(cognos_influx_client):
    cognos_influx_client.mock = True  # Simulate mock mode
    # Call the method
    result = cognos_influx_client.get_membox_bandwidth()
    # Assertions
    assert result["max_bandwidth"] == 512
    assert result["used_bandwidth"] == 32
    assert result["used_percentage_bandwidth"] == 0


def test_get_membox_capacity_mock_mode(cognos_influx_client):
    cognos_influx_client.mock = True
    result = cognos_influx_client.get_membox_capacity()
    assert result["total_capacity"] == 512
    assert result["used_capacity"] == 256
    assert result["used_capacity_percentage"] == 50
