from click.testing import CliRunner
import pytest
import cognos.backend.app as app
from cognos.backend.app import main, get_ssl_context, validate_ssl_enabled


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
