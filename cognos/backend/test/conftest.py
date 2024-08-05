import pytest
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

from cognos_influxdb_client import CognosInfluxDBClient

from app import create_app


@pytest.fixture
def cognos_influx_client():
    url = 'http://localhost:8086'
    token = 'token'
    org = 'test-org'
    bucket = 'test-bucket'
    return CognosInfluxDBClient(url=url, token=token, org=org, bucket=bucket)


@pytest.fixture
def cognos_influx_client_from_config():
    return CognosInfluxDBClient()


@pytest.fixture
def mock_db_connect_disconnect(mocker):
    mocker.patch('app.connect_to_mysql', return_value=True)
    mocker.patch('app.disconnect_mysql', return_value=True)


@pytest.fixture
def mock_clear_setup_tables(mocker):
    mocker.patch('app.clear_all_tables', return_value=True)
    mocker.patch('app.setup_tables', return_value=True)


@pytest.fixture
def client(mock_db_connect_disconnect, mock_clear_setup_tables):
    app = create_app()
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def mock_db(mocker):
    mock_connection = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()

    mocker.patch('mysql.connector.connect', return_value=mock_connection)
    mock_connection.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = True

    mocker.patch('app.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mocker.patch('app.disconnect_mysql', return_value=True)

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
    return cursor


@pytest.fixture
def mock_connection(mocker, mock_cursor):
    conn = mocker.MagicMock()
    conn.cursor.return_value = mock_cursor
    return conn
