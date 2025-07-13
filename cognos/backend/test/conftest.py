import os
from pathlib import Path
import pytest
import sys
from unittest.mock import MagicMock

sys.path.append(
    os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), "../../..")
    )
)  # noqa: E402
from cognos.backend.base_control_interface import BaseControlInterface
from cognos.backend.cognos_client import Cognos
from cognos.backend.helper import fetch_cognos_configs
from cognos.backend.app import create_app
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient
from cognos.backend.sqlite_client import SqliteClient


@pytest.fixture
def get_cognos_configs():
    backend_dir = Path(os.path.abspath(__file__)).parent.parent
    configs = fetch_cognos_configs(backend_dir, "config.json")
    return configs


@pytest.fixture
def cognos_influx_client(mock_sqlite_client):
    url = "http://localhost:8086"
    token = "token"
    org = "test-org"
    bucket = "test-bucket"
    return CognosInfluxDBClient(
        mock_sqlite_client, url=url, token=token, org=org,
        bucket=bucket, mock=True
    )


@pytest.fixture
def cognos_influx_client_from_config(mock_sqlite_client):
    return CognosInfluxDBClient(mock_sqlite_client)


@pytest.fixture
def get_cognos_client():
    return Cognos()


@pytest.fixture
def mock_sqlite_connection(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch(
        "sqlite3.connect",
        return_value=mock_conn
    )


@pytest.fixture
def mock_sqlite_client(mock_sqlite_connection):
    return SqliteClient(svk_data_path=os.getcwd())


@pytest.fixture
def override_sqlite_client_instantiation(mocker):
    mock_client = MagicMock()
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient',
        return_value=mock_client
    )


@pytest.fixture
def mock_initialize_cognos(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )


@pytest.fixture
def client(mocker, override_sqlite_client_instantiation,
           mock_initialize_cognos):
    app = create_app(mock=True)
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture
def test_client(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    app = create_app(mock=True)
    return app


@pytest.fixture
def scmc_version_file():
    root_dir = os.getcwd()
    scmc_version_path = os.path.join(root_dir, 'SCMC_VERSION')
    with open(scmc_version_path, 'w') as f:
        pass  # Create the file
    yield scmc_version_path
    os.remove(scmc_version_path)
