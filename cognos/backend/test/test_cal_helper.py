import pytest
import flask
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import mock_open, patch
import cognos.backend.helper as helper
from requests.models import Response

# get API version
backend_dir = Path(os.path.abspath(__file__)).parent.parent
CONFIGS = helper.fetch_cognos_configs(backend_dir, "config.json")
AGENT_ENDPOINT = CONFIGS["agent_endpoint"]
NODE_ENDPOINT = CONFIGS["node_endpoint"]
API_VERSION = helper.fetch_api_version(backend_dir)


def test_get_db_psswd(client):
    passwd = helper.get_db_passwd()
    assert passwd is not None
    assert len(passwd) > 1 and isinstance(passwd, str)


def construct_dummy_response(dummy_data):
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_data).encode("utf-8")
    return dummy_response


def test_failed_response(client):
    msg = "Dummy failed message"
    response = helper.failed_response(msg)
    response_payload = json.loads(response.data.decode("utf-8"))
    assert response_payload["status"] == 500


def test_prepare_response_with_body(client):
    paylaod = {"device_id": 392381231, "host": "HOST 1 LINK 0"}
    response = helper.prepare_response_with_body(paylaod)
    assert response is not None
    assert isinstance(response, flask.wrappers.Response)


def test_get_db_passwd(mocker):
    passwd = helper.get_db_passwd()
    assert str == type(passwd)
    assert passwd is not None
    mocker.patch("json.load", return_value=None)
    with pytest.raises(Exception):
        passwd = h.get_db_passwd()


def test_connect_to_mysql(mocker, mock_db):
    mocker.patch("cognos.backend.helper.get_db_passwd", return_value="xyz")
    db, cursor = helper.connect_to_mysql()
    assert db is not None
    assert cursor is not None


def test_get_param_from_request_params():
    dummy_request_params = (
        "cluster_id=CLUST1;command=AttachMemory;"
        "dev_id=549755813888;host_id=551903297536;mode=direct"
    ).split(";")
    expected_dev_id = "549755813888"
    expected_host_id = "551903297536"
    dev_id = helper.get_param_from_request_params(
        dummy_request_params, "dev_id"
    )
    host_id = helper.get_param_from_request_params(
        dummy_request_params, "host_id"
    )
    assert dev_id == expected_dev_id
    assert host_id == expected_host_id


def test_insert_hosts(mocker, mock_cursor, mock_connection):
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_connection, mock_cursor),
    )
    mock_data = [
        {
            "id": 3917231,
            "name": "Host 0 LINK 1",
            "mem_capacity": 473428423,
            "host_target_ports": [10],
        }
    ]
    fm_type = "FM_DIRECT_CMMD"
    helper.insert_hosts(mock_data, fm_type)


def test_update_metrics_host_filter_table(
    mocker, mock_cursor, mock_connection
):
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_connection, mock_cursor),
    )
    dummy_host = "test_host"
    helper.update_metrics_host_filter_table(dummy_host)


def test_get_metrics_host_filter(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = [["test_host"]]
    expected_response = ["test_host"]
    mock_cursor.fetchone.return_value = dummy_data
    result = helper.get_metrics_host_filter()
    assert result == expected_response
    # test empty DB table
    mock_cursor.fetchone.return_value = None
    assert "" == helper.get_metrics_host_filter()


def test_get_devices_from_db(mock_db):
    mock_connection, mock_cursor = mock_db

    dummy_data = [["dev02", 256, 32131212, 3, ""]]

    expected_response = [
        {
            "dev_name": "dev02",
            "dev_capacity": 256,
            "dev_id": 32131212,
            "dev_port": 3,
            "hosts_attached": "",
        }
    ]

    mock_cursor.fetchall.return_value = dummy_data
    result = helper.get_devices_from_db()
    assert result == expected_response


def test_insert_devices(mocker, mock_cursor, mock_connection):
    mock_data = [
        {
            "dev_id": 3213131,
            "dev_name": "CXL-DEV2",
            "dev_capacity": 9753826464,
            "dev_port": 11,
            "hosts_attached": "Host 1 Link 0",
            "status": "active",
            "type": "CMM-D",
            "mode": "direct",
        }
    ]
    mock_cursor.fetchall.return_value = mock_data
    mock_cursor.execute.return_value = mock_data
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_connection, mock_cursor),
    )

    helper.insert_devices(mock_data, {}, "FM_REMOTE_CMMD")


def test_insert_connection(mock_db):
    host_id = 948342
    host_name = "dummy-host"
    dev_id = 3219381281
    dev_name = "DUMMY_DEV1-256"
    helper.insert_connection(host_id, host_name, dev_id, dev_name)


def test_delete_connection(mock_db):
    dev_id = 23871273
    host_id = 3927311
    helper.delete_connection(dev_id, host_id)


def test_fetch_topology(mocker, mock_cursor, mock_connection):
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_connection, mock_cursor),
    )
    mock_data = ["Host 1 LINK 0", "DEV10,DEV11"]
    mock_cursor.fetchall.return_value = mock_data
    helper.fetch_topology()


def test_get_hosts_from_db(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = [["host1"]]
    mock_cursor.fetchall.return_value = dummy_data
    result = helper.get_hosts_from_db()
    assert result == [["host1"]]


def test_get_hostname_from_id(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = ("dummy_host", "")
    mock_cursor.fetchone.return_value = dummy_data
    response = helper.get_hostname_from_id(8371238)
    assert response == "dummy_host"


def test_get_devname_from_id(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = ("DUMMY_DEV1-256", "")
    mock_cursor.fetchone.return_value = dummy_data
    response = helper.get_devname_from_id(3827132)
    assert response == "DUMMY_DEV1-256"


def test_get_hostid_from_name(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = (123124, 0)
    mock_cursor.fetchone.return_value = dummy_data
    response = helper.get_hostid_from_name("dummy_host")
    assert response == 123124


def test_get_devid_from_name(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = (21311, 0)
    mock_cursor.fetchone.return_value = dummy_data
    response = helper.get_devid_from_name("DUMMY_DEV8-256")
    assert response == 21311


def test_get_deviceid_and_devicename_from_port(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = (231341, "DUMMY_DEV1-256")
    mock_cursor.fetchone.return_value = dummy_data
    response = helper.get_deviceid_and_devicename_from_port(5)
    assert response == dummy_data


def test_get_host_attached_devices(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = [["DUMMY_DEV2-256", "active", 5, "CMM-D", "direct", 256]]
    expected_response = [
        {
            "dev_name": "DUMMY_DEV2-256",
            "status": "active",
            "dev_port": 5,
            "type": "CMM-D",
            "mode": "direct",
            "dev_capacity": 256,
        }
    ]
    mock_cursor.fetchall.return_value = dummy_data
    result = helper.get_host_attached_devices("dummy_host")
    assert result == expected_response


def test_clear_all_tables(mock_db):
    helper.clear_all_tables()


def test_gen_svkcxlplugin_request_params():
    feature_params = "cluster_id=CLUST_ID_1;command=ListHosts"
    helper.gen_svkcxlplugin_request_params(feature_params)


def test_get_cognos_influx_functions():
    cognos_influx_fns = helper.get_cognos_influx_functions()
    assert cognos_influx_fns is not None


def test_gen_svkcxlplugin_request_params():
    # Input example
    feature_params = (
        "cluster_id=CL_ID_1;command=DetachMemory;dev_id=1401; "
        "host_id=1401;mode=direct"
    )
    # Call the function with valid input
    result = helper.gen_svkcxlplugin_request_params(feature_params)
    # Assert the structure and values
    assert result["cluster_id"] == "CL_ID_1"
    assert result["node_id"] == "localhost"
    assert result["feature_id"] == "3"
    assert result["feature_params"] == feature_params
    # Test with mock_request and mock_request_data
    mock_request_data = {
        "cluster_id": "MOCK_CLUSTER",
        "node_id": "MOCK_NODE",
        "feature_id": "99",
        "feature_params": "mock=params",
    }
    result_mock = helper.gen_svkcxlplugin_request_params(
        feature_params, mock_request=True, mock_request_data=mock_request_data
    )
    assert result_mock == mock_request_data
    # Test invalid input
    invalid_feature_params = "invalid_feature_param_without_equals"
    with pytest.raises(ValueError, match="Invalid feature parameter"):
        helper.gen_svkcxlplugin_request_params(invalid_feature_params)


def test_parse_svkcxlplugin_setup_response():
    # Mock response object
    response = MagicMock()
    response.text = json.dumps(
        {
            "nodeResponses": [
                {
                    "output": (
                        "[{'id': 1, 'type': 'FM_DIRECT'},"
                        "{'id': 2, 'type': 'FM_REMOTE'}]"
                    )
                }
            ]
        }
    )
    # Call the function
    result = helper.parse_svkcxlplugin_setup_response(response)
    # Assert the parsed response
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["type"] == "FM_DIRECT"
    assert result[1]["id"] == 2
    assert result[1]["type"] == "FM_REMOTE"


def test_is_hexadecimal():
    # Valid hexadecimal inputs
    assert helper.is_hexadecimal("0x1A3F") is True
    assert helper.is_hexadecimal("0xabcdef") is True
    assert helper.is_hexadecimal("0x123456") is True
    # Invalid hexadecimal inputs
    assert helper.is_hexadecimal("123456") is False
    assert helper.is_hexadecimal("0xGHIJKL") is False
    assert helper.is_hexadecimal("xyz") is False
    # Non-string inputs
    assert helper.is_hexadecimal(123456) is False
    assert helper.is_hexadecimal(None) is False
    assert helper.is_hexadecimal([]) is False


def test_fetch_cognos_configs():
    # Valid config file
    mock_config_data = (
        '{"agent_endpoint": "http://example.com",'
        '"node_endpoint": "http://node.com"}'
    )
    with patch("builtins.open", mock_open(read_data=mock_config_data)):
        result = helper.fetch_cognos_configs("/mock/parent_dir", "config.json")
        assert result["agent_endpoint"] == "http://example.com"
        assert result["node_endpoint"] == "http://node.com"
    # File not found
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(
            RuntimeError, match="Unable to retrieve cognos influx configs"
        ):
            helper.fetch_cognos_configs("/mock/parent_dir", "config.json")


def test_fetch_api_version():
    # Valid VERSION file
    with patch("builtins.open", mock_open(read_data="1.0.0")):
        result = helper.fetch_api_version("/mock/parent_dir")
        assert result == "1.0.0"
    # File not found
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(
            RuntimeError, match="Unable to retrieve API version"
        ):
            helper.fetch_api_version("/mock/parent_dir")


def test_mb_to_GB():
    assert helper.mb_to_GB(1024) == 1
    assert helper.mb_to_GB(2048) == 2
    assert helper.mb_to_GB(0) == 0


def test_bytes_to_MB():
    assert helper.bytes_to_MB(1048576) == 1
    assert helper.bytes_to_MB(2097152) == 2
    assert helper.bytes_to_MB(0) == 0


def test_bytes_to_GB():
    assert helper.bytes_to_GB(1073741824) == 1
    assert helper.bytes_to_GB(2147483648) == 2
    assert helper.bytes_to_GB(0) == 0


def test_get_devport_name_map():
    devices_payload = [
        {"dev_port": 1, "dev_name": "Device1"},
        {"dev_port": 2, "dev_name": "Device2"},
    ]
    result = helper.get_devport_name_map(devices_payload)
    assert result[1] == "Device1"
    assert result[2] == "Device2"
    assert len(result) == 2


def test_get_devport_hostname_map():
    hosts_payload = [
        {"endpoint": [{"target": 1}, {"target": 2}], "host_name": "Host1"},
        {"endpoint": [{"target": 3}], "host_name": "Host2"},
    ]
    result = helper.get_devport_hostname_map(hosts_payload)
    assert result[1] == "Host1"
    assert result[2] == "Host1"
    assert result[3] == "Host2"


@patch("socket.gethostbyname", return_value="127.0.0.1")
@patch("socket.gethostname", return_value="localhost")
def test_get_dummy_mb_info(mock_gethostname, mock_gethostbyname):
    result = helper.get_dummy_mb_info()
    assert result["mgmt_ip"] == "127.0.0.1"
    assert result["form_factor"] == "4U"
    assert result["manufacturer"] == "Samsung"
    assert result["memory_size"] == "1.5T"


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_get_available_devices_fromdb(
    mock_disconnect_mysql, mock_connect_to_mysql
):
    mock_cursor = MagicMock()
    mock_connect_to_mysql.return_value = (MagicMock(), mock_cursor)
    mock_cursor.fetchall.return_value = [("Device1",), ("Device2",)]
    result = helper.get_available_devices_fromdb()
    assert result == [("Device1",), ("Device2",)]
    mock_cursor.execute.assert_called_once_with(
        "SELECT dev_name FROM devices WHERE dev_name not in "
        "(SELECT dev_name FROM host_device_connections) and "
        "type='FM_REMOTE_CMMB';"
    )
    mock_disconnect_mysql.assert_called_once()


def test_process_membox_capacity_payload():
    devices_payload = [
        {"hosts_attached": "Host1"},
        {"hosts_attached": ""},
        {"hosts_attached": "Host2"},
    ]
    result = helper.process_membox_capacity_payload(devices_payload)
    assert len(result) == 1
    # 3 devices
    assert result[0]["total_capacity"] == 256 * 3
    # 2 devices attached to hosts
    assert result[0]["used_capacity"] == 256 * 2
    # 66% used
    assert result[0]["used_capacity_percentage"] == 66


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_remove_device_attached_host(
    mock_disconnect_mysql, mock_connect_to_mysql
):
    # Mock database and cursor
    mock_cursor = MagicMock()
    mock_connect_to_mysql.return_value = (MagicMock(), mock_cursor)
    # Case: Device has multiple hosts attached
    mock_cursor.fetchone.return_value = ["Host1,Host2"]
    helper.remove_device_attached_host(1234, "Host1")
    mock_cursor.execute.assert_called_with(
        "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;",
        ("Host2", 1234),
    )
    # Case: Device has only one host attached
    mock_cursor.fetchone.return_value = ["Host1"]
    helper.remove_device_attached_host(1234, "Host1")
    mock_cursor.execute.assert_called_with(
        "UPDATE devices SET hosts_attached = NULL WHERE dev_id = %s;",
        [1234],
    )
    # Case: No hosts attached
    mock_cursor.fetchone.return_value = None
    helper.remove_device_attached_host(1234, "Host1")
    mock_cursor.fetchone.return_value = ["Host2"]
    helper.remove_device_attached_host(1234, "Host1")
    # mock_cursor.execute.assert_not_called()
    mock_disconnect_mysql.assert_called()


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_update_device_attached_hosts(
    mock_disconnect_mysql, mock_connect_to_mysql
):
    # Mock database and cursor
    mock_cursor = MagicMock()
    mock_connect_to_mysql.return_value = (MagicMock(), mock_cursor)
    # Case: Device has no hosts attached
    mock_cursor.fetchone.return_value = [None]
    helper.update_device_attached_hosts(1234, "NewHost")
    mock_cursor.execute.assert_called_with(
        "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;",
        ("NewHost", 1234),
    )
    # Case: Device has existing hosts attached
    mock_cursor.fetchone.return_value = ["Host1"]
    helper.update_device_attached_hosts(1234, "NewHost")
    mock_cursor.execute.assert_called_with(
        "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;",
        ("Host1,NewHost", 1234),
    )
    mock_disconnect_mysql.assert_called()


def test_get_fm_host_info():
    hosts = [
        {
            "host_addr": "0x1A2B",
            "host_size": "0x40000000",
            "host_name": "Host1",
            "endpoint": [{"target": 1}, {"target": 2}],
        },
        {
            "host_addr": "5678",
            "host_size": "0x80000000",
            "host_name": "Host2",
            "endpoint": [{"target": 3}],
        },
    ]
    result = helper.get_fm_host_info(hosts)
    assert len(result) == 2
    assert result[0]["id"] == 0x1A2B
    assert result[0]["mem_capacity"] == 1  # 1 GiB
    assert result[0]["host_target_ports"] == [1, 2]
    assert result[1]["id"] == 5678
    assert result[1]["mem_capacity"] == 2  # 2 GiB
    assert result[1]["host_target_ports"] == [3]


def test_get_fm_devices_info():
    devices = [
        {
            "dev_addr": "0xABC",
            "dev_size": "0x40000000",
            "dev_port": 1,
            "dev_name": "Device1",
        },
        {"dev_addr": "1234", "dev_size": "0x80000000", "dev_port": 2},
    ]
    port_host_map = {1: "Host1", 2: "Host2"}
    result = helper.get_fm_devices_info(devices, port_host_map)
    assert len(result) == 2
    assert result[0]["dev_id"] == 0xABC
    assert result[0]["dev_capacity"] == 1  # 1 GiB
    assert result[0]["dev_port"] == 1
    assert result[0]["hosts_attached"] == ["Host1"]
    assert result[0]["dev_name"] == "Device1"
    assert result[1]["dev_id"] == 1234
    assert result[1]["dev_capacity"] == 2  # 2 GiB
    assert result[1]["dev_port"] == 2
    assert result[1]["hosts_attached"] == ["Host2"]
    assert result[1]["dev_name"] == "NA"


@patch("cognos.backend.helper.get_deviceid_and_devicename_from_port")
@patch("cognos.backend.helper.get_hostid_from_name")
@patch("cognos.backend.helper.insert_connection")
def test_init_connections_table(
    mock_insert_connection,
    mock_get_hostid_from_name,
    mock_get_deviceid_and_devicename_from_port,
):
    # Mock data
    devport_hostname_map = {1: "Host1", 2: "Host2"}
    mock_get_deviceid_and_devicename_from_port.side_effect = [
        (101, "Device1"),
        (102, "Device2"),
    ]
    mock_get_hostid_from_name.side_effect = [201, 202]
    # Call the function
    helper.init_connections_table(devport_hostname_map)
    # Assert that the helper functions were called correctly
    mock_get_deviceid_and_devicename_from_port.assert_any_call(1)
    mock_get_deviceid_and_devicename_from_port.assert_any_call(2)
    mock_get_hostid_from_name.assert_any_call("Host1")
    mock_get_hostid_from_name.assert_any_call("Host2")
    # Assert that `insert_connection` was called with the correct arguments
    mock_insert_connection.assert_any_call(201, "Host1", 101, "Device1")
    mock_insert_connection.assert_any_call(202, "Host2", 102, "Device2")
    # Ensure the exact number of calls
    assert mock_insert_connection.call_count == 2


@patch("cognos.backend.helper.insert_hosts")
def test_init_hosts_table(mock_insert_hosts):
    # Mock data
    hosts_payload = [
        {
            "id": 1,
            "name": "Host1",
            "mem_capacity": 1024,
            "host_target_ports": [1, 2],
        },
        {
            "id": 2,
            "name": "Host2",
            "mem_capacity": 2048,
            "host_target_ports": [3],
        },
    ]
    fm_type = "FM_DIRECT"
    # Call the function
    helper.init_hosts_table(hosts_payload, fm_type)
    # Assert that `insert_hosts` was called with the correct arguments
    mock_insert_hosts.assert_called_once_with(hosts_payload, fm_type)


@patch("cognos.backend.helper.insert_devices")
def test_init_devices_table(mock_insert_devices):
    # Mock data
    devices_payload = [
        {"dev_port": 1, "dev_size": 256},
        {"dev_port": 2, "dev_size": 512},
    ]
    dev_port_name_map = {1: "Device1", 2: "Device2"}
    devport_hostname_map = {1: "Host1", 2: "Host2"}
    fm_type = "FM_REMOTE"
    # Call the function
    helper.init_devices_table(
        devices_payload, dev_port_name_map, devport_hostname_map, fm_type
    )
    # Assert that `dev_name` was added to each device in `devices_payload`
    assert devices_payload[0]["dev_name"] == "Device1"
    assert devices_payload[1]["dev_name"] == "Device2"
    # Assert that `insert_devices` was called with the correct arguments
    mock_insert_devices.assert_called_once_with(
        devices_payload, devport_hostname_map, fm_type
    )


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_count_host_upstream_ports_success(mock_disconnect, mock_connect):
    # Mocking database connection
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [3]
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect.return_value = (mock_db, mock_cursor)
    # Call the method
    result = helper.count_host_upstream_ports()
    # Assertions
    assert result is not None, "Result should not be None"
    assert (
        result["num_upstream_ports"] == 3
    ), "Number of upstream ports should be 3"
    # Verify database methods were called
    mock_connect.assert_called_once()
    mock_disconnect.assert_called_once_with(mock_db)


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_count_host_upstream_ports_failure(mock_disconnect, mock_connect):
    # Simulate database connection failure
    mock_connect.return_value = (None, None)
    # Call the method
    result = helper.count_host_upstream_ports()
    # Assertions
    assert result is None, "Result should be None when connection fails"
    mock_connect.assert_called_once()


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_fetch_memory_capacity_success(mock_disconnect, mock_connect):
    # Mocking database connection
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [512, 1024, 50.0]
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect.return_value = (mock_db, mock_cursor)
    # Call the function
    result = helper.fetch_memory_capacity()
    # Assertions
    assert result is not None, "Result should not be None"
    assert result["used_capacity"] == 512, "Used capacity should be 512"
    assert result["total_capacity"] == 1024, "Total capacity should be 1024"
    assert result["used_percentage"] == 50.0, "Used percentage should be 50.0"
    # Verify that database methods were called
    mock_connect.assert_called_once()
    mock_disconnect.assert_called_once_with(mock_db)


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_count_attached_devices_success(mock_disconnect, mock_connect):
    # Mocking database connection
    mock_cursor = MagicMock()
    # Mocked database result
    mock_cursor.fetchall.return_value = [[5, 10]]
    mock_db = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mock_connect.return_value = (mock_db, mock_cursor)
    # Call the function
    result = helper.count_attached_devices()
    # Assertions
    assert result is not None, "Result should not be None"
    assert result["num_hosts"] == 5, "Number of hosts should be 5"
    assert (
        result["num_cxl_devices"] == 10
    ), "Number of CXL devices should be 10"
    # Verify that database methods were called
    mock_connect.assert_called_once()
    mock_disconnect.assert_called_once_with(mock_db)


@patch("cognos.backend.helper.connect_to_mysql")
@patch("cognos.backend.helper.disconnect_mysql")
def test_count_attached_devices_failure(mock_disconnect, mock_connect):
    # Simulate database connection failure
    mock_connect.return_value = (None, None)
    # Call the function
    result = helper.count_attached_devices()
    # Assertions
    assert result is None, "Result should be None when connection fails"
    # Verify that connect_to_mysql was called
    mock_connect.assert_called_once()


def test_get_clusters():
    result = helper.get_clusters()
    # Assertions
    assert result == ["CL_ID_1"], "Expected cluster names to be ['CL_ID_1']"
