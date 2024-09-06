import pytest
import flask
import json
import os
from pathlib import Path

import helper
from app import (
    get_db_passwd,
    get_param_from_request_params, insert_hosts,
    insert_devices, prepare_response_with_body,
    get_db_passwd, fetch_topology, failed_response,
    get_devices_from_db, insert_connection, delete_connection,
    get_hostname_from_id, get_devname_from_id, get_hostid_from_name,
    get_devid_from_name, get_deviceid_and_devicename_from_port,
    get_host_attached_devices, clear_all_tables, setup_tables,
    get_devices_info
)
from requests.models import Response


# get API version
backend_dir = Path(os.path.abspath(__file__)).parent.parent
CONFIGS = helper.fetch_cognos_configs(backend_dir, 'config.json')
AGENT_ENDPOINT = CONFIGS['agent_endpoint']
NODE_ENDPOINT = CONFIGS['node_endpoint']
API_VERSION = helper.fetch_api_version(backend_dir)


# VERSION_FILE_PATH = os.path.join(backend_dir, 'VERSION')
# API_VERSION = ''
# try:
#     with open(VERSION_FILE_PATH, 'r') as version_file:
#         API_VERSION = version_file.read().strip()
# except Exception as error:
#     raise RuntimeError(
#         f"Unable to retrieve API version: {str(error)}"
#     )


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


def test_get_db_passwd(mocker):
    passwd = get_db_passwd()
    assert str == type(passwd)
    assert passwd is not None
    mocker.patch('json.load', return_value=None)
    with pytest.raises(Exception):
        passwd = get_db_passwd()


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


# def test_get_devices_info(mock_db, mocker):
#     mock_connection, mock_cursor = mock_db

#     dummy_data = {
#         "output": {
#             NODE_ENDPOINT: {
#                 "devices": [
#                     {
#                         "dev_capacity": 274877906944,
#                         "dev_id": 549755813888,
#                         "dev_port": 10,
#                         "hosts_attached": ["Host 1 LNK0"]
#                     },
#                     {
#                         "dev_capacity": 274877906944,
#                         "dev_id": 824633720832,
#                         "dev_port": 11,
#                         "hosts_attached": ["Host 1 LNK0"]
#                     }
#                 ]
#             }
#         }
#     }
#     dummy_response = construct_dummy_response(dummy_data)
#     mocker.patch('requests.post', return_value=dummy_response)
#     payload_output = dummy_data["output"]
#     mocker.patch('json.loads', return_value=payload_output)
#     get_devices_info()


def test_get_devices_from_db(mock_db):
    mock_connection, mock_cursor = mock_db

    dummy_data = [[
        256, 32131212, 3, ''
    ]]

    expected_response = [
        {
            "dev_capacity": 256,
            "dev_id": 32131212,
            "dev_port": 3,
            "hosts_attached": ''
        }
    ]

    mock_cursor.fetchall.return_value = dummy_data
    result = get_devices_from_db()
    assert result == expected_response


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


def test_available_devices(client, mock_db):
    mock_connection, mock_cursor = mock_db
    dummy_data = [[
        'DUMMY_DEV1-256'
    ]]
    mock_cursor.fetchall.return_value = dummy_data
    response = client.get(
        f"/api/{API_VERSION}/available_devices",
        headers={
            "Access-Control-Allow-Origin": "*",
            "accept": "application/json",
            "content-type": "application/json"
        }
    )
    assert response.status_code == 200


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


# def test_setup_tables(mocker, mock_db):
#     dummy_hosts_data = [
#         {
#             "host_target_ports": [11, 10],
#             "id": 551903297536,
#             "mem_capacity": 547608330240,
#             "name": "Host 1 LNK0"
#         }
#     ]
#     mocker.patch('app.get_hosts_info', return_value=dummy_hosts_data)

#     dummy_devices_data = [
#         {
#             "dev_capacity": 274877906944,
#             "dev_id": 549755813888,
#             "dev_port": 10,
#             "hosts_attached": ["Host 1 LNK0"]
#         },
#         {
#             "dev_capacity": 274877906944,
#             "dev_id": 824633720832,
#             "dev_port": 11,
#             "hosts_attached": ["Host 1 LNK0"]
#         }
#     ]
#     mocker.patch('app.get_devices_info', return_value=dummy_devices_data)

#     dummy_init_data = {
#         "Board": {
#             "Mgmt_port_type": "PCIe",
#             "board_name": "Example Direct Config",
#             "json_version": "0100",
#             "management_port": 1,
#             "switch_mode": "direct"
#         },
#         "Devices": [
#             {
#                 "dev_addr": "0x008000000000",
#                 "dev_aspm_active": 1,
#                 "dev_lock_active": 1,
#                 "dev_name": "DEV_10-256G",
#                 "dev_port": 10,
#                 "dev_port_type": "CXL_20",
#                 "dev_size": "0x004000000000",
#                 "dev_speed": 5,
#                 "dev_sris_active": 1,
#                 "dev_width": 8
#             },
#             {
#                 "dev_addr": "0x00C000000000",
#                 "dev_aspm_active": 1,
#                 "dev_lock_active": 1,
#                 "dev_name": "DEV_11-256G",
#                 "dev_port": 11,
#                 "dev_port_type": "CXL_20",
#                 "dev_size": "0x004000000000",
#                 "dev_speed": 5,
#                 "dev_sris_active": 1,
#                 "dev_width": 8
#             }
#         ],
#         "Hosts": [
#             {
#                 "classcode": 0,
#                 "deinit_active": 1,
#                 "endpoint": [
#                     {
#                         "dev_offset": "0",
#                         "mem_addr": "0x00C000000000",
#                         "mem_size": "0x004000000000",
#                         "memdev": "mem- 11",
#                         "target": 11
#                     },
#                     {
#                         "dev_offset": "0",
#                         "mem_addr": "0x008000000000",
#                         "mem_size": "0x004000000000",
#                         "memdev": "mem- 10",
#                         "target": 10
#                     }
#                 ],
#                 "host_addr": "0x008080000000",
#                 "host_aspm_active": 1,
#                 "host_equalization": 1,
#                 "host_name": "Host 1 LNK0",
#                 "host_port": 2,
#                 "host_port_type": "CXL_11",
#                 "host_size": "0x007f80000000",
#                 "host_speed": 5,
#                 "host_sris_active": 1,
#                 "host_width": 8
#             }
#         ]
#     }
#     mocker.patch('app.get_setup_info', return_value=dummy_init_data)
#     mocker.patch('app.insert_devices', return_value=True)
#     mocker.patch('app.insert_hosts', return_value=True)
#     mocker.patch('app.insert_connection', return_value=True)
#     setup_tables()


def test_get_hosts(mocker, client, mock_db_connect_disconnect):
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
    # dummy_response = construct_dummy_response(dummy_data)
    payload_output = dummy_data["output"][NODE_ENDPOINT]["hosts"]
    mocker.patch('app.get_hosts_info', return_value=payload_output)
    response = client.get(
        f"/api/{API_VERSION}/hosts",
        headers={
            "Access-Control-Allow-Origin": "*",
            "accept": "application/json",
            "content-type": "application/json"
        }
    )
    assert response.status_code == 200


# def test_get_devices(mocker, client):
#     mocker.patch('app.insert_devices', return_value=True)
#     dummy_data = {
#         "output": {
#             NODE_ENDPOINT: {
#                 "devices": [
#                     {
#                         "dev_capacity": 274877906944,
#                         "dev_id": 549755813888,
#                         "dev_port": 10,
#                         "hosts_attached": ["Host 1 LNK0"]
#                     },
#                     {
#                         "dev_capacity": 274877906944,
#                         "dev_id": 824633720832,
#                         "dev_port": 11,
#                         "hosts_attached": ["Host 1 LNK0"]
#                     }
#                 ]
#             }
#         }
#     }
#     # dummy_response = construct_dummy_response(dummy_data)
#     payload_output = dummy_data["output"]
#     mocker.patch('app.get_devices_info', return_value=payload_output)
#     response = client.post(
#         f"/api/{API_VERSION}/devices",
#         headers={
#             "Access-Control-Allow-Origin": "*",
#             "accept": "application/json",
#             "content-type": "application/json"
#         }
#     )
#     assert response.status_code == 200


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
    # dummy_response = construct_dummy_response(dummy_data)
    payload_output = dummy_data["output"]
    mocker.patch('app.get_setup_info', return_value=payload_output)

    response = client.get(
        f"/api/{API_VERSION}/init",
        headers={
            "Access-Control-Allow-Origin": "*",
            "accept": "application/json",
            "content-type": "application/json"
        }
    )
    assert response.status_code == 200


def test_get_device_status(client):
    response = client.get(f"/api/{API_VERSION}/device_status")
    assert response.status_code == 200


@pytest.mark.skip(reason="fix me")
def test_detach_device(client, mock_db, mocker):
    dummy_dev_name = 'DUMMY_DEV1-256'
    dummy_host_name = 'dummy_host'
    dummy_detach_response = {
        'rc': 0
    }

    mocker.patch('app.get_devid_from_name', return_value=12321)
    mocker.patch('app.get_hostid_from_name', return_value=389123)
    mocker.patch('requests.post', return_value=dummy_detach_response)
    mocker.patch('app.get_host_attached_devices', return_value={})
    mocker.patch('json.loads', return_value={})
    mocker.patch('app.request_data', {
        "dev_name": dummy_dev_name, "host_name": dummy_host_name})

    response = client.delete(
        f"/api/{API_VERSION}/detach_device",
        headers={
            "Access-Control-Allow-Origin": "*",
            "accept": "application/json",
            "Content-Type": "application/json"
        },
        json={
            "dev_name": dummy_dev_name,
            "host_name": dummy_host_name
        }
    )
    assert response.status_code == 200


def test_host_devices(mocker, client):
    dummy_payload = [
        {
            "dev_name": "CXL_DEV5-256GB",
            "status": "active",
            "dev_port": 6,
            "type": "CMM-D",
            "mode": "direct",
            "dev_capacity": 256
        }
    ]
    mocker.patch('app.get_host_attached_devices', return_value=dummy_payload)
    response = client.post(
        f"/api/{API_VERSION}/host_devices",
        json={
            "host": "dummyhost"
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "accept": "application/json",
            "content-type": "application/json"
        }
    )
    assert response.status_code == 200


def test_get_mb_info(client):
    response = client.get(f"/api/{API_VERSION}/cxl/mb/info")
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
    response = client.get(
        f"/api/{API_VERSION}/topology",
        headers={
            "Access-Control-Allow-Origin": "*",
            "accept": "application/json",
            "content-type": "application/json"
        }
    )
    assert response.status_code == 200


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
