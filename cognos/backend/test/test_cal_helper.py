import pytest
import json
import os
import socket
from pathlib import Path
from unittest.mock import mock_open, patch
import cognos.backend.helper as helper


# get API version
backend_dir = Path(os.path.abspath(__file__)).parent.parent
CONFIGS = helper.fetch_cognos_configs(backend_dir, "config.json")
AGENT_ENDPOINT = CONFIGS["agent_endpoint"]
NODE_ENDPOINT = CONFIGS["node_endpoint"]
API_VERSION = helper.fetch_cal_api_version(backend_dir)


def test_create_empty_response(client):
    response = helper.create_empty_response()
    response_payload = response.data.decode("utf-8")
    assert not response_payload
    assert response.status_code == 204


def test_create_response_from_payload(client):
    payload = {"dev_id": 8372161728, "host_id": 489123}
    response = helper.create_response_from_payload(payload)
    assert response.status_code == 200
    response_payload = json.loads(response.data.decode("utf-8"))
    assert response_payload["dev_id"] == payload["dev_id"]
    assert response_payload["host_id"] == payload["host_id"]


def test_create_notfound_response_from_payload(client):
    payload = {"error": "data not found"}
    response = helper.create_notfound_response_from_payload(payload)
    assert response.status_code == 404


def test_failed_response(client):
    msg = "Dummy failed message"
    response = helper.failed_response(msg)
    response_payload = json.loads(response.data.decode("utf-8"))
    assert response_payload["status"] == 500


def test_get_cognos_influx_functions():
    cognos_influx_fns = helper.get_cognos_influx_functions()
    assert cognos_influx_fns is not None
    assert type(cognos_influx_fns) is list


def test_is_hexadecimal():
    # Valid hexadecimal inputs
    assert helper.is_hexadecimal("0x1A3F") is True
    assert helper.is_hexadecimal("0xabcdef") is True
    assert helper.is_hexadecimal("0x123456") is True
    # Invalid hexadecimal inputs
    assert helper.is_hexadecimal("123456") is False
    assert helper.is_hexadecimal("0xGHIJKL") is False
    assert helper.is_hexadecimal("xyz") is False
    # Non-string inputs
    assert helper.is_hexadecimal(123456) is False
    assert helper.is_hexadecimal(None) is False
    assert helper.is_hexadecimal([]) is False


def test_is_endpoint_reachable(mocker):
    ip_addr = socket.gethostbyname(socket.gethostname())
    assert not helper.is_endpoint_reachable(ip_addr, 4005)
    mocker.patch(
        "socket.socket.connect",
        return_value=True
    )
    assert helper.is_endpoint_reachable(ip_addr, 4005)


def test_is_valid_ip_addr():
    ip_addr = socket.gethostbyname(socket.gethostname())
    assert helper.is_valid_ip_addr(ip_addr)
    invalid_ip = "321.12.12.1"
    assert not helper.is_valid_ip_addr(invalid_ip)


def test_is_valid_device_type():
    dummy_valid_type = 'CMM-H'
    dummy_invalid_type = 'CMMD'
    assert helper.is_valid_device_type(dummy_valid_type)
    assert not helper.is_valid_device_type(dummy_invalid_type)


def test_fetch_cognos_configs():
    # Valid config file
    mock_config_data = (
        '{"agent_endpoint": "http://example.com",'
        '"node_endpoint": "http://node.com"}'
    )
    with patch("builtins.open", mock_open(read_data=mock_config_data)):
        result = helper.fetch_cognos_configs("/mock/parent_dir", "config.json")
        assert result["agent_endpoint"] == "http://example.com"
        assert result["node_endpoint"] == "http://node.com"
    # File not found
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(
            RuntimeError, match="Unable to retrieve cognos influx configs"
        ):
            helper.fetch_cognos_configs("/mock/parent_dir", "config.json")


def test_fetch_cal_api_version():
    # Valid VERSION file
    with patch("builtins.open", mock_open(read_data="1.0.0")):
        result = helper.fetch_cal_api_version("/mock/parent_dir")
        assert result == "1.0.0"
    # File not found
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(
            RuntimeError, match="Unable to retrieve API version"
        ):
            helper.fetch_cal_api_version("/mock/parent_dir")


def test_get_scmc_version_file():
    scmc_version_file = helper.get_scmc_version_file()
    assert scmc_version_file
    assert scmc_version_file.split("/")[-1] == '.version'


def test_mb_to_GB():
    assert helper.mb_to_GB(1024) == 1
    assert helper.mb_to_GB(2048) == 2
    assert helper.mb_to_GB(0) == 0


def test_bytes_to_MB():
    assert helper.bytes_to_MB(1048576) == 1
    assert helper.bytes_to_MB(2097152) == 2
    assert helper.bytes_to_MB(0) == 0


def test_bytes_to_GB():
    assert helper.bytes_to_GB(1073741824) == 1
    assert helper.bytes_to_GB(2147483648) == 2
    assert helper.bytes_to_GB(0) == 0


@patch("socket.gethostbyname", return_value="127.0.0.1")
@patch("socket.gethostname", return_value="localhost")
def test_get_dummy_mb_info(mock_gethostname, mock_gethostbyname):
    result = helper.get_dummy_mb_info()
    assert result["mgmt_ip"] == "127.0.0.1"
    assert result["form_factor"] == "4U"
    assert result["manufacturer"] == "Samsung"
    assert result["memory_size"] == "1.5T"
