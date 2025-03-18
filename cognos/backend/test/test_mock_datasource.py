from unittest.mock import mock_open, MagicMock
import mock_datasource


def test_mock_init(get_mock_datasource, client):
    get_mock_datasource.init()


def test_mock_get_scmc_version(get_mock_datasource, client, mocker):
    response = get_mock_datasource.get_scmc_version()
    # should fail as version file is non-existent
    assert response.json == {"error": "version file not found"}

    # test with mocked version file
    mock_file = mock_open(read_data="0.5.0 \n")
    mocker.patch("cognos.backend.mock_datasource.open", mock_file)
    mocker.patch("cognos.backend.mock_datasource.get_scmc_version_file",
                 return_value=mock_file)
    response = get_mock_datasource.get_scmc_version()
    assert response.json == {"version": "0.5.0"}


def test_mock_get_topology(get_mock_datasource, client):
    get_mock_datasource.get_topology()


def test_mock_get_hosts(get_mock_datasource, client):
    get_mock_datasource.get_hosts()


def test_mock_post_devices(mocker, get_mock_datasource, client):
    mocker.patch(
        "cognos.backend.mock_datasource.Mock.get_devices_info",
        return_value={"dev": "dev1"},
    )
    get_mock_datasource.post_devices()


def test_mock_membox_capacity(get_mock_datasource, client):
    get_mock_datasource.membox_capacity()


def test_mock_host_devices(get_mock_datasource, client):
    data = client.get("/host_devices", json={"host": "host1"})
    get_mock_datasource.host_devices()


def test_mock_available_devices(
    mocker, get_mock_datasource, client, mock_connection, mock_cursor
):
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_connection, mock_cursor),
    )
    dummy_data = [["DUMMY_DEV5-256"]]
    mock_cursor.execute.return_value = True
    mock_cursor.fetchall.return_value = dummy_data
    get_mock_datasource.available_devices()


def test_mock_detach_device(mocker, get_mock_datasource, client):
    data = client.post(
        "/detach_device", json={"host_name": ["host1"], "dev_name": "dev1"}
    )
    mocker.patch(
        "cognos.backend.helper.get_devid_from_name", return_value=3215
    )
    mocker.patch(
        "cognos.backend.helper.get_hostid_from_name", return_value=4314
    )
    mocker.patch("cognos.backend.helper.delete_connection", return_value=True)
    mocker.patch(
        "cognos.backend.helper.get_host_attached_devices",
        return_value={"dev": "dev1"},
    )
    get_mock_datasource.detach_device()


def test_mock_attach_device(mocker, get_mock_datasource, client, mock_db):
    data = client.post(
        "/attach_device", json={"host_name": ["host2"], "dev_name": "dev2"}
    )
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_db[0], mock_db[1]),
    )
    mocker.patch("cognos.backend.helper.disconnect_mysql", return_value=True)
    mocker.patch(
        "cognos.backend.helper.get_devid_from_name", return_value=7653
    )
    mocker.patch(
        "cognos.backend.helper.get_hostid_from_name", return_value=437314
    )
    mocker.patch("cognos.backend.helper.delete_connection", return_value=True)
    mocker.patch(
        "cognos.backend.helper.get_host_attached_devices",
        return_value={"dev": "dev2"},
    )
    # Here we simulate the value for 'hosts_attached' being a string
    mock_db[1].fetchone.return_value = ("host1",)
    get_mock_datasource.attach_device()


def test_mock_getmbinfo(get_mock_datasource, client):
    get_mock_datasource.get_mb_info()


def test_mock_setupinfo(get_mock_datasource, client):
    get_mock_datasource.get_setup_info()


def test_mock_getdevicesinfo(get_mock_datasource, client):
    get_mock_datasource.get_devices_info()


def test_mock_gethostsinfo(get_mock_datasource, client):
    get_mock_datasource.get_hosts_info()


def test_update_metrics_host_filter(
    get_mock_datasource, client, mocker, mock_db
):
    data = client.post(
        "/update_metrics_host_filter", json={"host": {"value": "test_host"}}
    )
    get_mock_datasource.update_metrics_host_filter()
