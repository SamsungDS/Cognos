import logging
from click.testing import CliRunner
import pytest
from flask import request
import cognos.backend.app as app

CAL_API_VERSION = "2.0.1"
runner = CliRunner()


# ----------------------------------------------------------------------
# Basic sanity checks – unchanged from the original suite
# ----------------------------------------------------------------------
def test_run_flask_server(mocker, client):
    mocker.patch('flask.Flask.run', return_value=True)
    host = "127.0.0.1"
    port = "4000"
    runner.invoke(app.main, ["--host", host, "--port", port, "--ssl"])


def test_get_ssl_context():
    ssl_cert, ssl_key = app.get_ssl_context()
    assert isinstance(ssl_cert, str)
    assert isinstance(ssl_key, str)


def test_validate_ssl_enabled():
    assert not app.validate_ssl_enabled()


def test_scmc_version_endpoint(test_client):
    api_path = f"/api/{CAL_API_VERSION}/scmc_version"
    with test_client.test_request_context(api_path, method='GET'):
        assert request.path == api_path


def test_get_topology_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.fetch_topology', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/topology", method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/topology"


def test_get_hosts_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_remote_hosts', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/hosts", method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/hosts"


def test_get_nodes_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_nodes', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/nodes", method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/nodes"


def test_get_devices_endpoint(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_remote_devices', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/devices", method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/devices"


def test_get_events(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_events', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/events", method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/events"


def test_move(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.move', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/move", method='POST'):
        assert request.path == f"/api/{CAL_API_VERSION}/move"


def test_move_all(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.move_all', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/move_all", method='POST'):
        assert request.path == f"/api/{CAL_API_VERSION}/move_all"


def test_get_move_stats(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_move_stats', return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/get_move_stats", method='POST'):
        assert request.path == f"/api/{CAL_API_VERSION}/get_move_stats"


# ----------------------------------------------------------------------
# Artifact‑related tests – unchanged
# ----------------------------------------------------------------------
def test_get_list_artifact(test_client):
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/list_artifact", method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/list_artifact"


def test_get_download_artifact(test_client):
    with test_client.test_request_context(
        f"/api/{CAL_API_VERSION}/artifact/<int:artifact_id>/download_artifact",
        method='GET'
    ):
        assert request.path == (
            f"/api/{CAL_API_VERSION}/artifact/<int:artifact_id>/download_artifact"
        )


def test_init_sqlite_db_file():
    app.init_sqlite_db_file()


def test_init_cognos_db():
    app.init_cognos_db(mock=True)


def test_clear_cognos_db():
    app.clear_cognos_db(mock=True)


def test_init_sets_app_and_options(gunicorn_app, dummy_app):
    gunicorn_app.load_config()
    assert ("bind", "127.0.0.1:8000") in gunicorn_app.cfg.set_calls
    assert ("workers", 2) in gunicorn_app.cfg.set_calls
    assert ("timeout", None) not in gunicorn_app.cfg.set_calls
    assert not any(key == "invalid_key" for key, _ in gunicorn_app.cfg.set_calls)


def test_load_returns_application(gunicorn_app, dummy_app):
    assert gunicorn_app.load() is dummy_app


# ----------------------------------------------------------------------
# Inner‑function tests – now using the shared flask_app fixture
# ----------------------------------------------------------------------
def test_inner_get_version_function(flask_app):
    get_version_func = flask_app.view_functions["get_version"]
    with flask_app.test_request_context(f"/api/{app.CAL_API_VERSION}/scmc_version", method="GET"):
        response = get_version_func()
        from flask import Response
        assert isinstance(response, Response)
        assert response.status_code == 200


def test_inner_get_topology_function(flask_app):
    get_topology_func = flask_app.view_functions["get_topology"]
    with flask_app.test_request_context(f"/api/{app.CAL_API_VERSION}/topology", method="GET"):
        response = get_topology_func()
        from flask import Response
        assert isinstance(response, Response)
        assert response.status_code == 200


def test_inner_get_hosts_function(flask_app):
    get_hosts_func = flask_app.view_functions["get_hosts"]
    with flask_app.test_request_context(f"/api/{app.CAL_API_VERSION}/hosts", method="GET"):
        response = get_hosts_func()
        from flask import Response
        assert isinstance(response, Response)
        assert response.status_code == 200


def test_inner_move_function(mocker, flask_app):
    mocker.patch('cognos.backend.cognos_client.Cognos.move', return_value={})
    move_func = flask_app.view_functions["move"]
    with flask_app.test_request_context(f"/api/{app.CAL_API_VERSION}/move", method="POST"):
        response = move_func()
        from flask import Response
        assert isinstance(response, Response)
        assert response.status_code == 200


def test_inner_move_all_function(mocker, flask_app):
    mocker.patch('cognos.backend.cognos_client.Cognos.move_all', return_value={})
    move_all_func = flask_app.view_functions["move_all"]
    with flask_app.test_request_context(f"/api/{app.CAL_API_VERSION}/move_all", method="POST"):
        response = move_all_func()
        from flask import Response
        assert isinstance(response, Response)
        assert response.status_code == 200


def test_inner_get_move_stats_function(mocker, flask_app):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_move_stats', return_value={})
    get_move_stats_func = flask_app.view_functions["get_move_stats"]
    with flask_app.test_request_context(f"/api/{app.CAL_API_VERSION}/get_move_stats", method="POST"):
        response = get_move_stats_func()
        from flask import Response
        assert isinstance(response, Response)
        assert response.status_code == 200
