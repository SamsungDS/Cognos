import pytest
import flask
import json
import os
from pathlib import Path


from cognos.backend.helper import (
    get_db_passwd, get_param_from_request_params, insert_hosts,
    insert_devices, prepare_response_with_body,
    get_db_passwd, fetch_topology, failed_response,
    get_devices_from_db, insert_connection, delete_connection,
    get_hostname_from_id, get_devname_from_id, get_hostid_from_name,
    get_devid_from_name, get_deviceid_and_devicename_from_port,
    get_host_attached_devices, clear_all_tables, connect_to_mysql,
    get_hosts_from_db, fetch_cognos_configs, fetch_api_version,
    gen_svkcxlplugin_request_params, get_cognos_influx_functions
)
from requests.models import Response


# get API version
backend_dir = Path(os.path.abspath(__file__)).parent.parent
CONFIGS = fetch_cognos_configs(backend_dir, 'config.json')
AGENT_ENDPOINT = CONFIGS['agent_endpoint']
NODE_ENDPOINT = CONFIGS['node_endpoint']
API_VERSION = fetch_api_version(backend_dir)


def test_get_db_psswd(client):
    passwd = get_db_passwd()
    assert passwd is not None
    assert len(passwd) > 1 and isinstance(passwd, str)


def construct_dummy_response(dummy_data):
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_data).encode('utf-8')
    return dummy_response


def test_failed_response(client):
    msg = "Dummy failed message"
    response = failed_response(msg)
    response_payload = json.loads(response.data.decode('utf-8'))
    assert response_payload["status"] == 500


def test_prepare_response_with_body(client):
    paylaod = {
        "device_id": 392381231,
        "host": "HOST 1 LINK 0"
    }
    response = prepare_response_with_body(paylaod)
    assert response is not None
    assert isinstance(response, flask.wrappers.Response)


def test_get_db_passwd(mocker):
    passwd = get_db_passwd()
    assert str == type(passwd)
    assert passwd is not None
    mocker.patch('json.load', return_value=None)
    with pytest.raises(Exception):
        passwd = get_db_passwd()


def test_connect_to_mysql(mocker, mock_db):
    mocker.patch('app.get_db_passwd', return_value="xyz")
    db, cursor = connect_to_mysql()
    assert db is not None
    assert cursor is not None


def test_get_param_from_request_params():
    dummy_request_params = (
        "cluster_id=CLUST1;command=AttachMemory;"
        "dev_id=549755813888;host_id=551903297536;mode=direct"
    ).split(";")
    expected_dev_id = "549755813888"
    expected_host_id = "551903297536"
    dev_id = get_param_from_request_params(dummy_request_params, 'dev_id')
    host_id = get_param_from_request_params(dummy_request_params, 'host_id')
    assert dev_id == expected_dev_id
    assert host_id == expected_host_id


def test_insert_hosts(mocker, mock_cursor, mock_connection):
    mocker.patch('app.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mock_data = [{
        "id": 3917231,
        "name": "Host 0 LINK 1",
        "mem_capacity": 473428423,
        "host_target_ports": [10]
    }]
    insert_hosts(mock_data)


def test_get_devices_from_db(mock_db):
    mock_connection, mock_cursor = mock_db

    dummy_data = [[
        "dev02", 256, 32131212, 3, ''
    ]]

    expected_response = [
        {
            "dev_name": "dev02",
            "dev_capacity": 256,
            "dev_id": 32131212,
            "dev_port": 3,
            "hosts_attached": ''
        }
    ]

    mock_cursor.fetchall.return_value = dummy_data
    result = get_devices_from_db()
    assert result == expected_response


def test_insert_devices(mocker, mock_cursor, mock_connection):
    mock_data = [{
        "dev_id": 3213131,
        "dev_name": "CXL-DEV2",
        "dev_capacity": 9753826464,
        "dev_port": 11,
        "hosts_attached": "Host 1 Link 0",
        "status": "active",
        "type": "CMM-D",
        "mode": "direct"
    }]
    mock_cursor.fetchall.return_value = mock_data
    mock_cursor.execute.return_value = mock_data
    mocker.patch('app.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))

    insert_devices(mock_data)


def test_insert_connection(mock_db):
    host_id = 948342
    host_name = "dummy-host"
    dev_id = 3219381281
    dev_name = "DUMMY_DEV1-256"
    insert_connection(host_id, host_name, dev_id, dev_name)


def test_delete_connection(mock_db):
    dev_id = 23871273
    host_id = 3927311
    delete_connection(dev_id, host_id)


def test_fetch_topology(mocker, mock_cursor, mock_connection):
    mocker.patch('app.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mock_data = [
        "Host 1 LINK 0",
        "DEV10,DEV11"
    ]
    mock_cursor.fetchall.return_value = mock_data
    fetch_topology()


def test_get_hosts_from_db(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = [[
        'host1'
    ]]
    mock_cursor.fetchall.return_value = dummy_data
    result = get_hosts_from_db()
    assert result == [['host1']]


def test_get_hostname_from_id(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = ('dummy_host', '')
    mock_cursor.fetchone.return_value = dummy_data
    response = get_hostname_from_id(8371238)
    assert response == 'dummy_host'


def test_get_devname_from_id(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = ('DUMMY_DEV1-256', '')
    mock_cursor.fetchone.return_value = dummy_data
    response = get_devname_from_id(3827132)
    assert response == 'DUMMY_DEV1-256'


def test_get_hostid_from_name(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = (123124, 0)
    mock_cursor.fetchone.return_value = dummy_data
    response = get_hostid_from_name('dummy_host')
    assert response == 123124


def test_get_devid_from_name(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = (21311, 0)
    mock_cursor.fetchone.return_value = dummy_data
    response = get_devid_from_name('DUMMY_DEV8-256')
    assert response == 21311


def test_get_deviceid_and_devicename_from_port(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = (231341, 'DUMMY_DEV1-256')
    mock_cursor.fetchone.return_value = dummy_data
    response = get_deviceid_and_devicename_from_port(5)
    assert response == dummy_data


def test_get_host_attached_devices(mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = [[
        'DUMMY_DEV2-256', 'active', 5,
        'CMM-D', 'direct', 256
    ]]
    expected_response = [
        {
            'dev_name': 'DUMMY_DEV2-256',
            'status': 'active',
            'dev_port': 5,
            'type': 'CMM-D',
            'mode': 'direct',
            'dev_capacity': 256
        }
    ]
    mock_cursor.fetchall.return_value = dummy_data
    result = get_host_attached_devices('dummy_host')
    assert result == expected_response


def test_clear_all_tables(mock_db):
    clear_all_tables()


def test_gen_svkcxlplugin_request_params():
    feature_params = "cluster_id=CLUST_ID_1;command=ListHosts;"
    gen_svkcxlplugin_request_params(feature_params)


def test_get_cognos_influx_functions():
    cognos_influx_fns = get_cognos_influx_functions()
    assert cognos_influx_fns is not None
