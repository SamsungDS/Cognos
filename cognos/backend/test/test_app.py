import pytest
import flask
import json

from app import (
    create_app, NODE_ENDPOINT, get_db_passwd,
    get_param_from_request_params, insert_hosts,
    insert_devices, prepare_response_with_body,
    get_db_passwd, fetch_topology
)
from requests.models import Response


@pytest.fixture
def client():
    app = create_app()
    with app.test_client() as client:
        with app.app_context():
            yield client


def construct_dummy_response(dummy_data):
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_data).encode('utf-8')
    return dummy_response


def test_get_db_passwd():
    passwd = get_db_passwd()
    assert str == type(passwd)
    assert passwd is not None


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


def test_get_hosts(mocker, client):
    mocker.patch('app.insert_hosts', return_value=True)
    dummy_data = {
        "output": {
            NODE_ENDPOINT: {
                "hosts": [
                    {
                        "host_target_ports": [11, 10],
                        "id": 551903297536,
                        "mem_capacity": 547608330240,
                        "name": "Host 1 LNK0"
                    }
                ]
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    payload_output = dummy_data["output"]
    mocker.patch('json.loads', return_value=payload_output)
    response = client.get(
        '/hosts',
        json={"input": "cluster_id=CLUST1;command=ListHosts"},
        headers={'accept': 'application/json',
                 'Content-Type': 'application/json'}
    )

    assert response.status_code == 200


def test_get_devices(mocker, client):
    mocker.patch('app.insert_devices', return_value=True)
    dummy_data = {
        "output": {
            NODE_ENDPOINT: {
                "devices": [
                    {
                        "dev_capacity": 274877906944,
                        "dev_id": 549755813888,
                        "dev_port": 10,
                        "hosts_attached": ["Host 1 LNK0"]
                    },
                    {
                        "dev_capacity": 274877906944,
                        "dev_id": 824633720832,
                        "dev_port": 11,
                        "hosts_attached": ["Host 1 LNK0"]
                    }
                ]
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    payload_output = dummy_data["output"]
    mocker.patch('json.loads', return_value=payload_output)

    args = (
        "cluster_id=CLUST1;command=ListDevices;"
        "FM_id=203;FM_endpoint=samsung.com"
    )
    response = client.get(
        '/devices',
        json={
            "input": args},
        headers={'accept': 'application/json',
                 'Content-Type': 'application/json'}
    )

    assert response.status_code == 200


def test_init(mocker, client):
    dummy_data = {
        "output": {
            NODE_ENDPOINT: {
                "Board": {
                    "Mgmt_port_type": "PCIe",
                    "board_name": "Example Direct Config",
                    "json_version": "0100",
                    "management_port": 1,
                    "switch_mode": "direct"
                },
                "Devices": [
                    {
                        "dev_addr": "0x008000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_10-256G",
                        "dev_port": 10,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8
                    },
                    {
                        "dev_addr": "0x00C000000000",
                        "dev_aspm_active": 1,
                        "dev_lock_active": 1,
                        "dev_name": "DEV_11-256G",
                        "dev_port": 11,
                        "dev_port_type": "CXL_20",
                        "dev_size": "0x004000000000",
                        "dev_speed": 5,
                        "dev_sris_active": 1,
                        "dev_width": 8
                    }
                ],
                "Hosts": [
                    {
                        "classcode": 0,
                        "deinit_active": 1,
                        "endpoint": [
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x00C000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 11",
                                "target": 11
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10
                            }
                        ],
                        "host_addr": "0x008080000000",
                        "host_aspm_active": 1,
                        "host_equalization": 1,
                        "host_name": "Host 1 LNK0",
                        "host_port": 2,
                        "host_port_type": "CXL_11",
                        "host_size": "0x007f80000000",
                        "host_speed": 5,
                        "host_sris_active": 1,
                        "host_width": 8
                    }
                ]
            }
        }
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    payload_output = dummy_data["output"]
    mocker.patch('json.loads', return_value=payload_output)

    response = client.get(
        '/init',
        json={"input": "cluster_id=CLUST1;command=SetupInfo"},
        headers={'accept': 'application/json',
                 'Content-Type': 'application/json'}
    )

    assert response.status_code == 200


def test_get_device_status(client):
    response = client.get('/device_status')
    assert response.status_code == 200


def test_host_devices(client):
    response = client.get('/host_devices')
    assert response.status_code == 200


def test_get_mb_info(client):
    response = client.get("/api/v1/cxl/mb/info")
    assert response.status_code == 200
    payload = response.json
    expected_fields = ['mgmt_ip', 'mgmt_port']
    # validate expected fileds in response
    assert all([field in payload for field in expected_fields])


def test_get_topology(mocker, client):
    mocker.patch(
        'app.fetch_topology',
        return_value=(
            [
                {
                    "devices": ["549755813888"],
                    "host": 551903297536
                }
            ]
        )
    )
    response = client.get('/topology')
    assert response.status_code == 200


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


# TODO: Make unit test more comprehensive
def test_insert_devices(mocker, mock_cursor, mock_connection):
    mocker.patch('app.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mock_data = [{
        "dev_id": 3213131,
        "dev_capacity": 9753826464,
        "dev_port": 11,
        "hosts_attached": "Host 1 Link 0",
        "status": "active",
        "type": "CMM-D",
        "mode": "direct"
    }]
    mock_cursor.fetchall.return_value = mock_data
    insert_devices(mock_data)


# TODO: Make unit test more comprehensive
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


def test_fetch_topology(mocker, mock_cursor, mock_connection):
    mocker.patch('app.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mock_data = [
        "Host 1 LINK 0",
        "DEV10,DEV11"
    ]
    mock_cursor.fetchall.return_value = mock_data
    fetch_topology()


def test_prepare_response_with_body(client):
    paylaod = {
        "device_id": 392381231,
        "host": "HOST 1 LINK 0"
    }
    response = prepare_response_with_body(paylaod)
    assert response is not None
    assert isinstance(response, flask.wrappers.Response)


def test_get_db_psswd(client):
    passwd = get_db_passwd()
    assert passwd is not None
    assert len(passwd) > 1 and isinstance(passwd, str)
