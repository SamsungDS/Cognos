import logging
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
from cognos.backend.app import create_app, GunicornServer
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
    return mock_conn


@pytest.fixture
def mock_sqlite_connection_bad_commit(mocker):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch(
        "sqlite3.connect",
        return_value=mock_conn
    )
    mock_conn.commit.side_effect = Exception("General Exception")
    return mock_conn


@pytest.fixture
def mock_sqlite_client(mock_sqlite_connection, mock_logger):
    return SqliteClient(svk_data_path=os.getcwd(), logger=mock_logger)


@pytest.fixture
def mock_sqlite_db():
    svk_data_path = "/var/lib/svk"
    db_file = svk_data_path + os.sep + 'cognos.db'
    db_file_path = Path(db_file)

    if not os.path.exists(svk_data_path):
        # create data directory
        os.makedirs(svk_data_path)

    if not os.path.exists(db_file):
        db_file_path.touch(exist_ok=True)


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


@pytest.fixture
def mock_logger(mocker):
    mock_logger = mocker.patch('logging.getLogger')
    return mock_logger


class DummyCfg:
    def __init__(self):
        self.settings = {
            "bind": object(),
            "workers": object(),
            "timeout": object()
        }
        self.set_calls = []

    def set(self, key, value):
        self.set_calls.append((key, value))


@pytest.fixture
def dummy_app():
    return object()


@pytest.fixture
def gunicorn_app(dummy_app, monkeypatch):
    def fake_base_init(self):
        self.cfg = DummyCfg()
    monkeypatch.setattr(
        "cognos.backend.app.BaseApplication.__init__",
        fake_base_init
    )
    options = {
        "bind": "127.0.0.1:8000",
        "workers": 2,
        "timeout": None,
        "invalid_key": "test"
    }

    return GunicornServer(dummy_app, options)


# ----------------------------------------------------------------------
# New shared fixtures for inner‑function tests
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def disable_sys_exit(monkeypatch):
    """Prevent sys.exit from terminating the test suite."""
    monkeypatch.setattr("sys.exit", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def mock_scmc_version(mocker):
    """Make Cognos report a sane version string."""
    mocker.patch.object(
        Cognos,
        "scmc_version",
        {"version": "test-version"},
        create=True,
    )


@pytest.fixture
def flask_app(mock_initialize_cognos, mocker):
    """Create a single Flask app instance (mock mode) for inner‑function tests."""
    # Mock Cognos methods that would otherwise hit the SQLite DB
    mocker.patch(
        'cognos.backend.cognos_client.Cognos.fetch_topology',
        return_value={}
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos.get_remote_hosts',
        return_value={}
    )
    app = create_app(mock=True)
    return app


# ----------------------------------------------------------------------
# Autouse fixtures to mock Cognos methods that hit the SQLite DB
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_fetch_topology(mocker):
    """Mock Cognos.fetch_topology to avoid DB access in inner‑function tests."""
    mocker.patch(
        'cognos.backend.cognos_client.Cognos.fetch_topology',
        return_value={}
    )


@pytest.fixture(autouse=True)
def mock_get_remote_hosts(mocker):
    """Mock Cognos.get_remote_hosts to avoid DB access in inner‑function tests."""
    mocker.patch(
        'cognos.backend.cognos_client.Cognos.get_remote_hosts',
        return_value={}
    )


@pytest.fixture
def artifact_client(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    app = create_app(mock=True)
    app.config["TESTING"] = True
    with app.test_client() as client:
        with app.app_context():
            yield client
