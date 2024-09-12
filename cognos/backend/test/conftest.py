import os
from pathlib import Path
import pytest
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(  # noqa: E402
    os.path.join(os.path.dirname(__file__), '../../..')))  # noqa: E402
from cognos.backend.cxlplugin_datasource import CXLPlugin
from cognos.backend.helper import (
    fetch_cognos_configs
)
from cognos.backend.mock_datasource import Mock
from cognos.backend.app import create_app
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient


@pytest.fixture
def get_cognos_configs():
    backend_dir = Path(os.path.abspath(__file__)).parent.parent
    configs = fetch_cognos_configs(backend_dir, 'config.json')
    return configs


@pytest.fixture
def cognos_influx_client():
    url = 'http://localhost:8086'
    token = 'token'
    org = 'test-org'
    bucket = 'test-bucket'
    return CognosInfluxDBClient(url=url, token=token, org=org, bucket=bucket,
                                mock=True)


@pytest.fixture
def cognos_influx_client_from_config():
    return CognosInfluxDBClient()


@pytest.fixture
def get_cxlplugin_datasource():
    return CXLPlugin()


@pytest.fixture
def get_mock_datasource():
    return Mock()


@pytest.fixture
def mock_db_connect_disconnect(mocker):
    mocker.patch('cognos.backend.helper.connect_to_mysql', return_value=True)
    mocker.patch('cognos.backend.helper.disconnect_mysql', return_value=True)


@pytest.fixture
def mock_clear_setup_tables(mocker):
    mocker.patch('cognos.backend.helper.clear_all_tables', return_value=True)


@pytest.fixture
def mock_mysql_connection(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mocker.patch(
        'cognos.backend.helper.connect_to_mysql',
        return_value=(mock_conn, mock_cursor)
    )
    mocker.patch('cognos.backend.helper.disconnect_mysql', return_value=True)


@pytest.fixture
def client(mock_mysql_connection, mock_clear_setup_tables, mocker):
    app = create_app(mock=True)
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture(autouse=True)
def mock_app(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mocker.patch(
        'cognos.backend.helper.connect_to_mysql',
        return_value=(mock_conn, mock_cursor)
    )
    mocker.patch('cognos.backend.helper.disconnect_mysql', return_value=True)
    mocker.patch('cognos.backend.helper.clear_all_tables', return_value=True)
    APP = create_app(mock=True)
    return APP


@pytest.fixture
def app_context(mock_app):
    with mock_app.app_context():
        yield


@pytest.fixture
def request_context(mock_app):
    with mock_app.test_request_context('/data', method='POST'):
        yield


@pytest.fixture
def mock_db(mocker):
    mock_connection = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()

    mocker.patch('mysql.connector.connect', return_value=mock_connection)
    mock_connection.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = True

    mocker.patch('cognos.backend.helper.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mocker.patch('cognos.backend.helper.disconnect_mysql', return_value=True)

    return mock_connection, mock_cursor


@pytest.fixture
def mock_cursor(mocker):
    cursor = mocker.MagicMock()
    cursor.fetchall.return_value = [{
        "id": 3917231,
        "name": "Host 0 LINK 1",
        "mem_capacity": 473428423,
        "host_target_ports": [10]
    }]
    cursor.execute.return_value = [{
        "id": 3917231,
        "name": "Host 0 LINK 1",
        "mem_capacity": 473428423,
        "host_target_ports": [10]
    }]
    return cursor


@pytest.fixture
def mock_connection(mocker, mock_cursor):
    conn = mocker.MagicMock()
    conn.cursor.return_value = mock_cursor
    conn.commit.return_value = True
    return conn


@pytest.fixture
def mock_devices_info():
    return [
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
            "hosts_attached": "host1"
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
            "hosts_attached": "host2"
        }
    ]
