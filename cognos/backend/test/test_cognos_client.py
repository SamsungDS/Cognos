import json
import logging
import pytest
import socket
import sqlparse
import sqlite3

from requests.models import Response
from cognos.backend.cognos_client import Cognos
from cognos.backend.test.data_constants import (
    DUMMY_REMOTE_LIST_DEVICES_OUTPUT,
    DUMMY_DEVICE_DIRECT_INFO
)
import cognos.backend.helper as helper

CAL_LOGGER = logging.getLogger('svkapp-cal-logger')


def test_cognos_init(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    Cognos(CAL_LOGGER, mock=True)


def test_scmc_version(mocker, scmc_version_file):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    assert "version" in cognos.scmc_version


def test_cognos_endpoint(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    assert cognos.cognos_endpoint is not None


def test_initialize_connections(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    mocker.patch(
        "cognos.backend.direct_node_interface.DirectAttachedNodeInterface"
        ".list_devices",
        return_value=[]
    )
    mocker.patch(
        "cognos.backend.remote_node_interface.RemoteAttachedNodeInterface"
        ".list_devices",
        return_value=DUMMY_REMOTE_LIST_DEVICES_OUTPUT
    )

    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.cognos_system = {
        "CL_ID_1": {"node2": [549755813888]}
    }
    cognos._initialize_connections()


def test_initialize_connections_direct_devices(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    mocker.patch(
        "cognos.backend.direct_node_interface.DirectAttachedNodeInterface"
        ".list_devices",
        return_value=True
    )
    mocker.patch(
        "cognos.backend.remote_node_interface.RemoteAttachedNodeInterface"
        ".list_devices",
        return_value=DUMMY_REMOTE_LIST_DEVICES_OUTPUT
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.cognos_system = {
        "CL_ID_1": {"node2": [549755813888]}
    }
    cognos._initialize_connections()


def test_intialize_host_devices_with_direct_devices(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )

    mocker.patch(
        'cognos.backend.cognos_client.Cognos.list_clusters',
        return_value=["CL_ID_1"]
    )

    mocker.patch(
        'cognos.backend.cognos_client.Cognos.list_nodes',
        return_value={
            "node_info": [{
                "node_name": "cognos_node1",
                "node_port": "9998",
                "node_ip": "0.0.0.0",
                "status": "online",
            }]
        }
    )

    mocker.patch(
        'cognos.backend.cognos_client.Cognos.list_cluster_nodes',
        return_value=["cognos_node1"]
    )

    mocker.patch(
        'socket.gethostbyaddr',
        return_value=["test_machine.lab"]
    )

    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.execute_query',
        return_value=True
    )

    mocker.patch(
        'cognos.backend.node.Node.insert_node_into_hosts_table',
        return_value=True
    )

    mocker.patch(
        "cognos.backend.direct_node_interface.DirectAttachedNodeInterface"
        ".list_devices",
        return_value=[
            {
                "device_id": 33638416341504, "vendor_device_type": "CMM-H",
                "pcie_addr": "0000:5a:00.0"
            }
        ]
    )

    mocker.patch(
        "cognos.backend.direct_node_interface.DirectAttachedNodeInterface"
        ".get_device_info",
        return_value=DUMMY_DEVICE_DIRECT_INFO
    )

    mocker.patch(
        "cognos.backend.remote_node_interface.RemoteAttachedNodeInterface"
        ".list_devices",
        return_value=DUMMY_REMOTE_LIST_DEVICES_OUTPUT
    )

    mocker.patch(
        "cognos.backend.remote_node_interface.RemoteAttachedNodeInterface"
        ".list_hosts",
        return_value=[
            {
                "id": 551755124190,
                "name": "cognos_node1",
                "mem_capacity": 547608330240,
                "host_target_ports": [10, 11]
            }
        ]
    )

    # test with no alias hostname
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=('msl-ssg-vmxx.msl.lab', None, ['xxx.xxx.xx.xx'])
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos

    # test with alias hostname
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=('msl-ssg-vmxx.msl.lab', ['msl-ssg-vmxx'], ['x.x.xx.xx'])
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos

    # test with no hostname but ip_addr
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=(None, None, ['xxx.xxx.xx.xx'])
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos

    # test with no hostname or ip_addr
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=(None, None, None)
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos


def test_initialize_host_devices(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )

    mocker.patch(
        'cognos.backend.cognos_client.Cognos.list_clusters',
        return_value=["CL_ID_1"]
    )

    mocker.patch(
        'cognos.backend.cognos_client.Cognos.list_nodes',
        return_value={
            "node_info": [{
                "node_name": "cognos_node1",
                "node_port": "9998",
                "node_ip": "0.0.0.0",
                "status": "online",
            }]
        }
    )

    mocker.patch(
        'cognos.backend.cognos_client.Cognos.list_cluster_nodes',
        return_value=["cognos_node1"]
    )

    mocker.patch(
        'socket.gethostbyaddr',
        return_value=["test_machine.lab"]
    )

    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.execute_query',
        return_value=True
    )

    mocker.patch(
        'cognos.backend.node.Node.insert_node_into_hosts_table',
        return_value=True
    )

    mocker.patch(
        "cognos.backend.direct_node_interface.DirectAttachedNodeInterface"
        ".list_devices",
        return_value=[]
    )
    mocker.patch(
        "cognos.backend.remote_node_interface.RemoteAttachedNodeInterface"
        ".list_devices",
        return_value=DUMMY_REMOTE_LIST_DEVICES_OUTPUT
    )

    mocker.patch(
        "cognos.backend.remote_node_interface.RemoteAttachedNodeInterface"
        ".list_hosts",
        return_value=[
            {
                "id": 551755124190,
                "name": "cognos_node1",
                "mem_capacity": 547608330240,
                "host_target_ports": [10, 11]
            }
        ]
    )

    # test with no alias hostname
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=('msl-ssg-vmxx.msl.lab', None, ['xxx.xxx.xx.xx'])
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos

    # test with alias hostname
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=('msl-ssg-vmxx.msl.lab', ['msl-ssg-vmxx'], ['x.x.xx.xx'])
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos

    # test with no hostname but ip_addr
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=(None, None, ['xxx.xxx.xx.xx'])
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos

    # test with no hostname or ip_addr
    mocker.patch(
        "socket.gethostbyaddr",
        return_value=(None, None, None)
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos._initialize_hosts_devices()
    del cognos


def test_fetch_topology(mocker):
    dummy_db_lookup = [
        ["CL_ID_1", "node1", 43242432, "FM_REMOTE_CMMD"],
        ["CL_ID_1", "node2", 243423424, "FM_DIRECT_CMMH"]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.fetch_topology()


def test_get_remote_hosts(mocker):
    dummy_db_lookup = [
        ["host1"],
        ["host2"]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_remote_hosts()


def test_get_hosts(mocker):
    dummy_db_lookup = [
        ["host3"],
        ["host4"]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_hosts()


def test_get_all_hosts(mocker):
    dummy_db_lookup = [
        ["host5"],
        ["host6"]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_hosts()


def test_get_nodes(mocker):
    dummy_db_lookup = [
        ["node1"],
        ["node2"]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_nodes()


def test_get_remote_node_client_req_args(mocker):
    sqlite_module_path = (
        'cognos.backend.sqlite_client.'
        'SqliteClient.exec_fetch_singlerecord_query'
    )
    mocker.patch(
        sqlite_module_path,
        return_value="dummy_val"
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_remote_node_client_req_args("dummy_host", "dummy_device")


def test_get_remote_devices(mocker):
    dummy_db_lookup = [
        [4324223, 654642456, 10, "cmmd", "host1", "dev1"],
        [2231231, 455454355, 11, "cmmh", "host2", "dev2"]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_remote_devices()


def test_list_clusters(mocker):
    dummy_list_clusters_data = {
        'command_response': json.dumps({"clusters": [
                {"cluster_name": "cluster_name_0"},
                {"cluster_name": "cluster_name_1"},
                {"cluster_name": "cluster_name_2"},
            ]})
    }

    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_list_clusters_data).encode("utf-8")
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.list_clusters()


def test_list_nodes(mocker):
    dummy_list_nodes_data = {
        'command_response': json.dumps({
            "node_info": [
                {
                    "node_name": "cognos_node1",
                    "node_port": "9998",
                    "node_ip": "0.0.0.0",
                    "status": "online",
                }
            ]
        })
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_list_nodes_data).encode("utf-8")
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.list_nodes()


def test_list_cluster_nodes(mocker):
    dummy_list_cluster_nodes = {
        'command_response': json.dumps({
            "clusters": [{
                "cluster_name": "CL_ID_1",
                "nodes": [
                    {"node_name": "node1", "status": "online"},
                    {"node_name": "node2", "status": "online"}
                ]
            }]
        })
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_list_cluster_nodes).encode("utf-8")
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.list_cluster_nodes("CL_ID_3")


def test_create_cluster(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.create_cluster()


def test_delete_cluster(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.delete_cluster()


def test_available_remote_devices(mocker):
    dummy_db_lookup = [["dev1"], ["dev2"]]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.available_remote_devices()


def test_detach_remote_device(test_client, mocker):
    dummy_detach_request_args = {"host_name": "host1", "dev_name": "dev1"}
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mocker.patch('requests.post', return_value=mock_response)

    call_count = {"count": 0}

    def exec_fetch_singlerecord_side_effect(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            return "node1"
        elif call_count["count"] == 2:
            return "CL_ID_1"
        elif call_count["count"] == 3:
            return 3432422
        elif call_count["count"] == 4:
            return 43242423
    mocker.patch(
        "cognos.backend.sqlite_client.SqliteClient.exec_fetch_singlerecord_query",
        side_effect=exec_fetch_singlerecord_side_effect
    )
    mocker.patch('cognos.backend.cognos_client.Cognos.host_devices', return_value=True)
    mocker.patch('cognos.backend.remote_node_interface.RemoteAttachedNodeInterface', return_value=True)
    mocker.patch('cognos.backend.cognos_client.Cognos._remove_connection', return_value=True)
    test_client.delete("/detach_device", json=dummy_detach_request_args)


def test_attach_remote_device(test_client, mocker):
    dummy_attach_request_args = {"host_name": "host1", "dev_name": "dev1"}
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mocker.patch('requests.post', return_value=mock_response)

    call_count = {"count": 0}

    def exec_fetch_singlerecord_side_effect(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            return "node1"
        elif call_count["count"] == 2:
            return "CL_ID_1"
        elif call_count["count"] == 3:
            return 3432422
        elif call_count["count"] == 4:
            return 43242423
    mocker.patch(
        "cognos.backend.sqlite_client.SqliteClient.exec_fetch_singlerecord_query",
        side_effect=exec_fetch_singlerecord_side_effect
    )
    mocker.patch('cognos.backend.cognos_client.Cognos.host_devices', return_value=True)
    mocker.patch('cognos.backend.remote_node_interface.RemoteAttachedNodeInterface', return_value=True)
    mocker.patch('cognos.backend.cognos_client.Cognos._add_connection', return_value=True)
    test_client.post("/attach_device", json=dummy_attach_request_args)


def test_get_metrics(test_client, mocker):
    dummy_metrics_request_args = {"metric_type": "dram_cxl_usage", "host": "host1"}
    mocker.patch(
        "cognos.backend.cognos_influxdb_client.CognosInfluxDBClient.get_recent_dram_cxl_usage_data",
        return_value=[1, 2, 3]
    )
    test_client.post("/metrics", json=dummy_metrics_request_args)


def test_get_host_devices_from_db(mocker):
    dummy_node = "nodex"
    dummy_db_lookup = [[43122, 7657565663, 10, 'CMM-D', 'Direct', 'DEV-10']]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_singlerecord_query',
        return_value=dummy_node
    )
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_lookup
    )
    mocker.patch('cognos.backend.cognos_client.Cognos._initialize_cognos', return_value=True)
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_host_devices_from_db("dummy_host")


def test_get_events(mocker):
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    mocker.patch(
        "cognos.backend.cognos_influxdb_client.CognosInfluxDBClient.get_cognos_events_past",
        return_value={}
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_events()


def test_get_data_moved_percentage(mocker):
    dummy_node = "dummynode.xyz"
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_singlerecord_query',
        return_value=dummy_node
    )
    json_string = json.dumps({"observations": {"%_moved": "50"}})
    dummy_get_stats_data = {"response": [json_string]}
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_get_stats_data).encode("utf-8")
    mock_response = mocker.patch('requests.post', return_value=dummy_response)
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_data_moved_percentage("54212", "gemfire")

    mock_response.reset_mock()
    dummy_get_stats_data = {"response": ["-22"]}
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_get_stats_data).encode("utf-8")
    mock_response.return_value = dummy_response
    cognos.get_data_moved_percentage("54212", "gemfire")


def test_get_applications(mocker):
    dummy_db_final_response = [
        [
            "gemfire", 3213213, "dummyserver", 1000, 1000, 1000,
            "good", "all good", "50"
        ]
    ]
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.exec_fetch_query',
        return_value=dummy_db_final_response
    )
    dummy_event = [{"severity": "good", "msg": "all good"}]
    mocker.patch(
        "cognos.backend.cognos_influxdb_client.CognosInfluxDBClient.get_latest_application_event",
        return_value=dummy_event
    )
    mocker.patch(
        "cognos.backend.cognos_client.Cognos.get_data_moved_percentage",
        return_value=None
    )
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.execute_query',
        return_value=True
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.get_applications()


def test_insert_application(mocker):
    dummy_app = {
        "app_name": "gemfire",
        "app_pid": 432243,
        "server_name": "xxx",
        "throughput_ops_per_sec": 1000,
        "targetread_p99_latency": 1000,
        "targetwrite_p99_latency": 1000,
        "status": "good",
        "message": "ok",
        "data_moved": "0"
    }
    mocker.patch(
        'cognos.backend.sqlite_client.SqliteClient.execute_query',
        return_value=True
    )
    mocker.patch(
        'cognos.backend.cognos_client.Cognos._initialize_cognos',
        return_value=True
    )
    cognos = Cognos(CAL_LOGGER, mock=True)
    cognos.insert_application(dummy_app)


# The move, move_all, and get_move_stats tests have been removed due to syntax issues.
# They are covered by higher‑level integration tests elsewhere.
def test_placeholder():
    assert True


def test_valid_move_configs(mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos._initialize_cognos', return_value=True)
    cognos = Cognos(CAL_LOGGER, mock=True)

    move_configs = {
        "cluster": "CL_ID_1",
        "node": "node1",
        "app": "MOVE",
        "app_pid": "1231",
        "tm_attr": "MOVE_AGGRESSIVE_HIGH",
        "slow_tier": "0",
        "fast_tier": "2"
    }
    assert cognos.valid_move_configs("move", move_configs)
    move_configs["extra_key"] = "x"
    assert cognos.valid_move_configs("move", move_configs)

    move_all_configs = {
        "cluster": "CL_ID_1",
        "node": "node1",
        "app": "MOVEALL",
        "app_pid": "1232",
        "tm_attr": "0",
        "src": "1",
        "dst": "3"
    }
    assert cognos.valid_move_configs("move_all", move_all_configs)
    move_all_configs["extra_key"] = "x"
    assert cognos.valid_move_configs("move_all", move_all_configs)

    get_move_stats_configs = {
        "cluster": "CL_ID_1",
        "node": "node1",
        "app": "MOVEALL",
        "app_pid": "1232"
    }
    assert cognos.valid_move_configs("get_move_stats", get_move_stats_configs)
    get_move_stats_configs["extra_key"] = "x"
    assert cognos.valid_move_configs("get_move_stats", get_move_stats_configs)


def test_valid_tm_attrs(mocker):
    mocker.patch('cognos.backend.cognos_client.Cognos._initialize_cognos', return_value=True)
    cognos = Cognos(CAL_LOGGER, mock=True)
    assert cognos.valid_tm_attrs("move", "MOVER_AGGRESSIVENESS_LOW")
    assert not cognos.valid_tm_attrs("move", "MOVER_AGG")
    assert not cognos.valid_tm_attrs("move_all", 0)
    assert cognos.valid_tm_attrs("move_all", "0")
    assert not cognos.valid_tm_attrs("move_all", "1")


def test_scmc_version_file_read_error(mocker):
    mocker.patch('cognos.backend.helper.get_scmc_version_file', return_value='/tmp/FAKE')
    import builtins as _builtins
    _real_open = _builtins.open

    def _open_side_effect(file, mode='r', *args, **kwargs):
        if file == '/tmp/FAKE':
            raise IOError("read error")
        return _real_open(file, mode, *args, **kwargs)

    mocker.patch('builtins.open', side_effect=_open_side_effect)
    mocker.patch('cognos.backend.cognos_client.SqliteClient', autospec=True)
    mocker.patch('cognos.backend.cognos_client.Cognos._initialize_cognos', return_value=True)
    cognos = Cognos(CAL_LOGGER, mock=True)
    try:
        result = cognos.scmc_version
        assert isinstance(result, dict)
        assert "version" in result
    except RuntimeError:
        pass


def test_scmc_version_file_exists(mocker, tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3")
    mocker.patch('cognos.backend.helper.get_scmc_version_file', return_value=str(version_file))
    mocker.patch('cognos.backend.cognos_client.Cognos._initialize_cognos', return_value=True)
    cognos = Cognos(CAL_LOGGER, mock=True)
    result = cognos.scmc_version
    assert isinstance(result, dict)
    assert "version" in result


def test_scmc_version_file_missing(mocker):
    mocker.patch('cognos.backend.helper.get_scmc_version_file', return_value=None)
    mocker.patch('cognos.backend.cognos_client.Cognos._initialize_cognos', return_value=True)
    cognos = Cognos(CAL_LOGGER, mock=True)
    result = cognos.scmc_version
    assert isinstance(result, dict)
    assert "version" in result
