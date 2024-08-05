import os
import json
import pytest
import uuid
from unittest.mock import patch, mock_open
from cognos.ssdp.helper import (
    load_config,
    get_or_generate_sku,
    generate_ssdp_response,
    get_ssdp_response
)

CONFIG_CONTENT = json.dumps({
    "device_type": "TestDevice",
    "manufacturer": "TestManufacturer",
    "mgmt_endpoint": "http://192.168.1.1:5000",
    "api_endpoint": "http://192.168.1.1:5000/api/v2.0/devices",
    "cxl_version": "1.1",
    "pcie_version": "gen6",
    "upstream_ports": "2",
    "downstream_ports": "4",
    "MCAST_GRP": "239.255.255.250",
    "MCAST_PORT": "1900",
    "capacity": "10"
})

SKU_FILE_PATH = 'sku.txt'


@pytest.fixture
def mock_config_file():
    with patch('builtins.open', mock_open(read_data=CONFIG_CONTENT)):
        yield


@pytest.fixture
def mock_os_path_exists():
    with patch('os.path.exists') as mock_exists:
        yield mock_exists


@pytest.fixture
def mock_file_open():
    with patch('builtins.open', mock_open()) as mock_file:
        yield mock_file


def test_load_config(mock_config_file):
    config = load_config()
    assert config['device_type'] == 'TestDevice'
    assert config['manufacturer'] == 'TestManufacturer'
    assert config['mgmt_endpoint'] == 'http://192.168.1.1:5000'


def test_get_or_generate_sku(mock_os_path_exists, mock_file_open):
    # Test SKU generation when file does not exist
    mock_os_path_exists.return_value = False
    sku = get_or_generate_sku()
    assert len(sku) == 7
    assert sku.isalnum()

    # Test SKU generation when file already exists
    mock_os_path_exists.return_value = True
    mock_file_open().read.return_value = 'ABC1234'
    assert get_or_generate_sku() == 'ABC1234'


def test_generate_ssdp_response(mock_config_file):
    with patch('cognos.ssdp.helper.get_or_generate_sku',
               return_value='ABC1234'):
        response = generate_ssdp_response()
        response_dict = json.loads(response)
        assert response_dict['device_type'] == 'TestDevice'
        assert response_dict['manufacturer'] == 'TestManufacturer'
        assert response_dict['mgmt_ip'] == '192.168.1.1'
        assert response_dict['mgmt_port'] == '5000'
        assert response_dict['capacity'] == '10'
        assert response_dict['cxl_version'] == '1.1'
        assert response_dict['pcie_version'] == 'gen6'
        assert response_dict['upstream_ports'] == '2'
        assert response_dict['downstream_ports'] == '4'
        assert response_dict['sku'] == 'ABC1234'


def test_get_ssdp_response(mock_config_file):
    with patch('cognos.ssdp.helper.uuid.uuid4',
               return_value=uuid.UUID('12345678123456781234567812345678')), \
         patch('cognos.ssdp.helper.generate_ssdp_response',
               return_value='{"key": "value"}'):
        response = get_ssdp_response()
        assert '12345678-1234-5678-1234-567812345678' in response
        assert 'EXTRA_FIELDS: {"key": "value"}' in response
