from click.testing import CliRunner
from flask import request
import pytest
import cognos.backend.app as app
from cognos.backend.app import main, get_ssl_context, validate_ssl_enabled


CAL_API_VERSION = "2.0.1"
runner = CliRunner()


def test_run_flask_server(mocker, client):
    mocker.patch('flask.Flask.run', return_value=True)
    mock_mode = True
    host = "127.0.0.1"
    port = "4000"
    ssl = True
    runner.invoke(main, ["--host", host, "--port", port, "--ssl"])


def test_get_ssl_context():
    ssl_cert, ssl_key = get_ssl_context()
    assert ssl_cert and ssl_key
    assert isinstance(ssl_cert, str)
    assert isinstance(ssl_key, str)


def test_validate_ssl_enabled():
    assert not validate_ssl_enabled()


def test_scmc_version_endpoint(test_client):
    api_path = f"/api/{CAL_API_VERSION}/scmc_version"
    with test_client.test_request_context(api_path, method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/scmc_version"


def test_get_topology_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.fetch_topology',
                 return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/topology",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/topology"


def test_get_hosts_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_remote_hosts',
                 return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/hosts",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/hosts"


def test_get_nodes_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_nodes',
                 return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/nodes",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/nodes"


def test_get_devices_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_remote_devices',
                 return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/devices",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/devices"


def test_init_sqlite_db_file():
    app.init_sqlite_db_file()


def test_init_cognos_db():
    app.init_cognos_db(mock=True)


def test_clear_cognos_db():
    app.clear_cognos_db(mock=True)
