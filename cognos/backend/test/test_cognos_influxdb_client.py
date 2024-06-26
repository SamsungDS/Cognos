import pytest
from unittest.mock import MagicMock

from cognos_influxdb_client import CognosInfluxDBClient
from mock_cognos_agent_metrics_populator import (
    mock_metrics, run_mock_populator
)


def test_create_client(cognos_influx_client):
    assert cognos_influx_client is not None


def test_create_client_from_config(cognos_influx_client_from_config):
    assert cognos_influx_client_from_config is not None


def test_write_records(cognos_influx_client, mocker):
    mocker.patch(
        'cognos_influxdb_client.CognosInfluxDBClient.write_cognos_event',
        return_value=True
    )
    for metric in mock_metrics:
        cognos_influx_client.write_cognos_event(metric)


def test_read_records(cognos_influx_client, mocker):
    mocker.patch(
        'cognos_influxdb_client.CognosInfluxDBClient.query_cognos_events',
        return_value=True
    )
    cognos_influx_client.query_cognos_events('10m')


def test_run_mock_populator(cognos_influx_client, mocker):
    mocker.patch(
        'cognos_influxdb_client.CognosInfluxDBClient.write_cognos_event',
        return_value=True
    )
    mocker.patch(
        'cognos_influxdb_client.CognosInfluxDBClient.query_cognos_events',
        return_value=True
    )
    run_mock_populator(cognos_influx_client, 10, '10m')
