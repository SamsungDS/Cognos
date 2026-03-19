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


def test_get_events(test_client, mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos.get_events',
                 return_value={})
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/events",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/events"


def test_get_list_artifact(test_client):
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/list_artifact",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/list_artifact"


def test_get_download_artifact(test_client):
    with test_client.test_request_context(f"/api/{CAL_API_VERSION}/artifact/<int:artifact_id>/download_artifact",
                                          method='GET'):
        assert request.path == f"/api/{CAL_API_VERSION}/artifact/<int:artifact_id>/download_artifact"


def test_init_sqlite_db_file():
    app.init_sqlite_db_file()


def test_init_cognos_db():
    app.init_cognos_db(mock=True)


def test_clear_cognos_db():
    app.clear_cognos_db(mock=True)


def test_list_artifact_disabled(artifact_client, mocker):
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', False)
    response = artifact_client.get("/api/v2.0.1/list_artifact")
    assert response.status_code == 503
    assert response.get_json() == {"error": "Artifact download is not enabled"}


def test_list_artifact_empty(artifact_client, mocker):
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [])
    response = artifact_client.get("/api/v2.0.1/list_artifact")
    assert response.status_code == 200
    assert response.get_json() == {"artifacts": []}


def test_list_artifact_with_existing_file(artifact_client, mocker, tmp_path):
    artifact = {
        "id": 1,
        "name": "release-1.0.tar.gz",
        "ARTIFACT_DETAILS": {
            "release_name": "v1.0",
            "release_date": "2024-01-01",
            "feature_list": ["feature_a", "feature_b"],
            "release_notes": "Initial release"
        }
    }
    fake_file = tmp_path / "release-1.0.tar.gz"
    fake_file.write_bytes(b"fake tar content")
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [artifact])
    mocker.patch('cognos.backend.app.ARTIFACTS_DIR', str(tmp_path))
    response = artifact_client.get("/api/v2.0.1/list_artifact")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["id"] == 1
    assert data["artifacts"][0]["name"] == "release-1.0.tar.gz"
    assert data["artifacts"][0]["available"] is True
    assert data["artifacts"][0]["release_name"] == "v1.0"
    assert data["artifacts"][0]["release_date"] == "2024-01-01"
    assert data["artifacts"][0]["feature_list"] == ["feature_a", "feature_b"]
    assert data["artifacts"][0]["release_notes"] == "Initial release"


def test_list_artifact_with_missing_file(artifact_client, mocker, tmp_path):
    artifact = {
        "id": 2,
        "name": "release-2.0.tar.gz",
        "ARTIFACT_DETAILS": {
            "release_name": "v2.0",
            "release_date": "2024-06-01",
            "feature_list": [],
            "release_notes": None
        }
    }
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [artifact])
    mocker.patch('cognos.backend.app.ARTIFACTS_DIR', str(tmp_path))
    response = artifact_client.get("/api/v2.0.1/list_artifact")
    assert response.status_code == 200
    assert response.get_json()["artifacts"][0]["available"] is False


def test_list_artifact_missing_details_keys(artifact_client, mocker, tmp_path):
    artifact = {"id": 3, "name": "release-3.0.tar.gz"}
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [artifact])
    mocker.patch('cognos.backend.app.ARTIFACTS_DIR', str(tmp_path))
    response = artifact_client.get("/api/v2.0.1/list_artifact")
    assert response.status_code == 200
    result = response.get_json()["artifacts"][0]
    assert result["release_name"] is None
    assert result["release_date"] is None
    assert result["feature_list"] == []
    assert result["release_notes"] is None


def test_download_artifact_disabled(artifact_client, mocker):
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', False)
    response = artifact_client.get("/api/v2.0.1/artifact/1/download_artifact")
    assert response.status_code == 403
    assert response.get_json() == {"error": "Artifact download is not enabled."}


def test_download_artifact_not_found(artifact_client, mocker):
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [])
    response = artifact_client.get("/api/v2.0.1/artifact/99/download_artifact")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_download_artifact_file_missing_on_disk(artifact_client, mocker, tmp_path):
    artifact = {"id": 1, "name": "release-1.0.tar.gz"}
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [artifact])
    mocker.patch('cognos.backend.app.ARTIFACTS_DIR', str(tmp_path))
    response = artifact_client.get("/api/v2.0.1/artifact/1/download_artifact")
    assert response.status_code == 404
    assert "missing on system" in response.get_json()["error"]


def test_download_artifact_success(artifact_client, mocker, tmp_path):
    artifact = {"id": 1, "name": "release-1.0.tar.gz"}
    fake_file = tmp_path / "release-1.0.tar.gz"
    fake_file.write_bytes(b"fake tar content")
    mocker.patch('cognos.backend.app.DOWNLOAD_ARTIFACT_MODE', True)
    mocker.patch('cognos.backend.app.ARTIFACTS', [artifact])
    mocker.patch('cognos.backend.app.ARTIFACTS_DIR', str(tmp_path))
    response = artifact_client.get("/api/v2.0.1/artifact/1/download_artifact")
    assert response.status_code == 200
    assert response.mimetype == "application/x-tar"
    assert b"fake tar content" in response.data
    assert "attachment" in response.headers.get("Content-Disposition", "")
