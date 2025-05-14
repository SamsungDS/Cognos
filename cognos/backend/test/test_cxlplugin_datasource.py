import json
from datetime import datetime
from requests.models import Response
import os
import pytest
import requests
from unittest.mock import mock_open, patch, MagicMock
from data_constants import dummy_init_data
import cognos.backend.cxlplugin_datasource as cxlds
from cognos.backend.test.test_cal_helper import construct_dummy_response
from flask import request, jsonify
from requests.models import Response
import cognos.backend.helper as helper


def test_cxlplugin_init(
    mocker, client, get_cognos_configs, get_cxlplugin_datasource
):
    dummy_data = {
        "output": {
            get_cognos_configs["node_endpoint"]: {
                "Board": {
                    "Mgmt_port_type": "PCIe",
                    "board_name": "Example Direct Config",
                    "json_version": "0100",
                    "management_port": 1,
                    "switch_mode": "direct",
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
                        "dev_width": 8,
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
                        "dev_width": 8,
                    },
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
                                "target": 11,
                            },
                            {
                                "dev_offset": "0",
                                "mem_addr": "0x008000000000",
                                "mem_size": "0x004000000000",
                                "memdev": "mem- 10",
                                "target": 10,
                            },
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
                        "host_width": 8,
                    }
                ],
            }
        }
    }
    payload_output = dummy_data["output"]
    mocker.patch(
        "cognos.backend.cxlplugin_datasource.CXLPlugin.get_setup_info",
        return_value=payload_output,
    )
    get_cxlplugin_datasource.init()


def test_cxlplugin_get_topology(mocker, client, get_cxlplugin_datasource):
    mock_data = ["Host 1 LINK 0", "DEV10,DEV11"]
    mocker.patch(
        "cognos.backend.helper.fetch_topology", return_value=mock_data
    )
    get_cxlplugin_datasource.get_topology()


def test_get_scmc_version(mocker, client, get_cxlplugin_datasource):
    mock_version = "0.5"
    mocker.patch(
        "cognos.backend.helper.get_scmc_version_file", return_value=os.getcwd()
    )

    with patch("builtins.open", mock_open(read_data=mock_version)):
        response = get_cxlplugin_datasource.get_scmc_version()
        assert response.json == {"version": mock_version}

    # File not found
    with patch("builtins.open", side_effect=FileNotFoundError):
        with pytest.raises(
            RuntimeError, match="Unable to retrieve API version*"
        ):
            get_cxlplugin_datasource.get_scmc_version()

    # validate edge case
    mocker.resetall()
    mocker.patch(
        "cognos.backend.helper.get_scmc_version_file", return_value=False
    )
    response = get_cxlplugin_datasource.get_scmc_version()
    assert response.json == {"error": "version file not found"}
    assert response.status_code == 404


def test_cxlplugin_get_hosts(
    mocker, client, get_cxlplugin_datasource, mock_app
):
    # Mock host data
    mock_hosts = [
        {"id": "host1", "name": "Host 1"},
        {"id": "host2", "name": "Host 2"},
    ]
    mock_aggregate_info = mocker.patch(
        "cognos.backend.cxlplugin_datasource.CXLPlugin.aggregate_info",
        return_value=mock_hosts,
    )
    with mock_app.app_context():
        response = get_cxlplugin_datasource.get_hosts()
    expected_response = [
        {"value": "Host 1", "label": "Host 1"},
        {"value": "Host 2", "label": "Host 2"},
    ]
    assert response.status_code == 200
    assert response.json == expected_response
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    mock_aggregate_info.assert_called_once_with(
        get_cxlplugin_datasource.get_hosts_info, "id"
    )


def test_cxlplugin_post_devices(
    mocker, client, get_cxlplugin_datasource, mock_app
):
    # Mock device data
    mock_devices = [
        {"dev_id": "device1", "name": "Device 1"},
        {"dev_id": "device2", "name": "Device 2"},
    ]
    mock_aggregate_info = mocker.patch(
        "cognos.backend.cxlplugin_datasource.CXLPlugin.aggregate_info",
        return_value=mock_devices,
    )
    with mock_app.app_context():
        response = get_cxlplugin_datasource.post_devices()
    assert response.status_code == 200
    assert response.json == mock_devices
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    # Verify `aggregate_info` was called with correct arguments
    mock_aggregate_info.assert_called_once_with(
        get_cxlplugin_datasource.get_devices_info, "dev_id"
    )


def test_cxlplugin_membox_capacity(
    mocker, client, get_cxlplugin_datasource, mock_devices_info
):
    mocker.patch(
        "cognos.backend.cxlplugin_datasource.CXLPlugin.get_devices_info",
        return_value=mock_devices_info,
    )
    get_cxlplugin_datasource.membox_capacity()


def test_host_devices(mocker, get_cxlplugin_datasource, mock_db, client):
    data = client.get("/host_devices", json={"host": "host1"})

    mock_connection, mock_cursor = mock_db
    mock_device = [["DUMMY_DEV2-256", "active", 5, "CMM-D", "direct", 256]]
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
    mock_cursor.fetchall.return_value = mock_device
    get_cxlplugin_datasource.host_devices()


def test_cxlplugin_available_devices(
    mocker, get_cxlplugin_datasource, client, mock_connection, mock_cursor
):
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_connection, mock_cursor),
    )
    dummy_data = [["DUMMY_DEV1-256"]]
    mock_cursor.execute.return_value = True
    mock_cursor.fetchall.return_value = dummy_data
    get_cxlplugin_datasource.available_devices()


def test_remove_device_attached_host(mocker):
    # Mock the connect_to_mysql function to return mock db and cursor
    mock_cursor = mocker.Mock()
    mock_db = mocker.Mock()
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_db, mock_cursor),
    )
    # Configure fetchone to return a tuple with the hosts_attached value
    mock_cursor.fetchone.return_value = ("host1,host2",)
    # Mock disconnect_mysql to avoid actual DB operations
    mocker.patch("cognos.backend.helper.disconnect_mysql")
    # Call the function

    helper.remove_device_attached_host(dev_id=1, removed_host="host1")
    # Assertions
    # Verify that the correct SQL queries were executed
    mock_cursor.execute.assert_any_call(
        "SELECT hosts_attached FROM devices WHERE dev_id=%s", [1]
    )
    mock_cursor.execute.assert_any_call(
        "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;",
        ("host2", 1),
    )
    # Verify that commit was called
    mock_db.commit.assert_called_once()


def test_cxlplugin_attach_device(
    mocker, get_cxlplugin_datasource, get_cognos_configs, mock_app, app_context
):
    with mock_app.test_request_context("/attach_device", method="POST"):
        dummy_attach_response = {
            "nodeResponses": [
                {"nodeId": "localhost", "output": """{"rc": 0}"""}
            ]
        }

        dummy_response = Response()
        dummy_response.status_code = 200
        dummy_response._content = json.dumps(
            dummy_attach_response, indent=2
        ).encode("utf-8")
        dummy_response.headers["Content-Type"] = "application/json"
        mocker.patch("requests.post", return_value=dummy_response)
        mocker.patch(
            "cognos.backend.helper.parse_svkcxlplugin_response",
            return_value={get_cognos_configs["node_endpoint"]: {"rc": 0}},
        )
        mock_connection = mocker.MagicMock()
        mock_cursor = mocker.MagicMock()
        mocker.patch("mysql.connector.connect", return_value=mock_connection)
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.execute.return_value = True
        mocker.patch(
            "cognos.backend.helper.get_db_passwd", return_value="CXL123mem!"
        )
        mocker.patch(
            "cognos.backend.helper.connect_to_mysql",
            return_value=(mock_connection, mock_cursor),
        )
        mocker.patch(
            "cognos.backend.helper.disconnect_mysql", return_value=True
        )
        # Return a dummy value for `fetchone` to avoid `MagicMock`
        mock_cursor.fetchone.return_value = ("host1",)

        # mock_cursor.execute.return_value = True
        mocker.patch(
            "cognos.backend.helper.get_host_attached_devices",
            return_value={"device": "dev1"},
        )
        get_cxlplugin_datasource.attach_device(
            mock_request=True,
            mock_request_data={"dev_name": "dev2", "host_name": "host2"},
        )


def test_get_metrics(mocker, mock_app):
    mock_request = MagicMock()
    mock_request.get_json.return_value = {
        "metric_type": "dram_cxl_usage"
    }

    dummy_data = [[datetime.now(), "0.7", "0.9"]]
    prefix_fn_path = (
        "cognos.backend.cognos_influxdb_client.CognosInfluxDBClient."
    )
    mocker.patch(
        prefix_fn_path + "get_recent_dram_cxl_usage_data",
        return_value=dummy_data
    )

    with mock_app.app_context():
        with patch("cognos.backend.cxlplugin_datasource.request",
                   mock_request):
            from cognos.backend.cxlplugin_datasource import CXLPlugin
            cxl_plugin = CXLPlugin()
            cxl_plugin.get_metrics()


def test_get_metrics_failure(mocker, mock_app):
    mock_request = MagicMock()
    mock_request.get_json.side_effect = Exception(
        "Failed to get input request data"
    )
    mock_request.get_json.return_value = {
        "metric_type": "dram_cxl_usage"
    }

    dummy_data = [[datetime.now(), "0.7", "0.9"]]
    prefix_fn_path = (
        "cognos.backend.cognos_influxdb_client.CognosInfluxDBClient."
    )
    mocker.patch(
        prefix_fn_path + "get_recent_dram_cxl_usage_data",
        return_value=dummy_data
    )

    with mock_app.app_context():
        with patch("cognos.backend.cxlplugin_datasource.request",
                   mock_request):
            from cognos.backend.cxlplugin_datasource import CXLPlugin
            with pytest.raises(Exception):
                cxl_plugin = CXLPlugin()
                cxl_plugin.get_metrics()


def test_cxlplugin_get_mb_info(client, get_cxlplugin_datasource):
    get_cxlplugin_datasource.get_mb_info()


def test_cxlplugin_setup_info_with_list_output(
    mocker, client, get_cxlplugin_datasource, get_cognos_configs
):
    # Dummy data simulating the API response
    dummy_init_data = {
        "nodeResponses": [
            {
                "nodeId": "localhost",
                "output": """[
                    {
                        "Devices": [{"device_id": "123", "status": "active"}],
                        "Hosts": [{"host_id": "456", "status": "active"}],
                        "Type": "FM_DIRECT_CMMH"
                    }
                ]""",
            }
        ]
    }
    # Mock the response for requests.post
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_init_data).encode("utf-8")
    dummy_response.headers["Content-Type"] = "application/json"
    mocker.patch("requests.post", return_value=dummy_response)
    # Mock parse_svkcxlplugin_setup_response to return parsed content
    parsed_output = eval(dummy_init_data["nodeResponses"][0]["output"])
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_setup_response",
        return_value=parsed_output,
    )
    # Call the method under test
    result = get_cxlplugin_datasource.get_setup_info()
    # Assertions
    expected_output = parsed_output
    assert result == expected_output


def test_cxlplugin_get_devices_info(
    mock_db, mocker, get_cxlplugin_datasource, get_cognos_configs
):
    mock_connection, mock_cursor = mock_db

    dummy_data = {
        "nodeResponses": [
            {
                "nodeId": "localhost",
                "output": """{
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
                }""",
            }
        ]
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch("requests.post", return_value=dummy_response)
    payload_output = json.loads(dummy_data["nodeResponses"][0]["output"])
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_response",
        return_value=payload_output,
    )
    get_cxlplugin_datasource.get_devices_info("CL_ID_1", "localhost")


def test_cxlplugin_get_hosts_info(
    mock_db, mocker, get_cxlplugin_datasource, get_cognos_configs
):
    mock_connection, mock_cursor = mock_db
    # Dummy data to simulate API response
    dummy_data = {
        "nodeResponses": [
            {
                "nodeId": "1.2.3.4",
                "output": {
                    "hosts": [
                        {
                            "id": 551903297536,
                            "name": "testhost.area.51",
                            "mem_capacity": 547608330240,
                            "host_target_ports": [11, 10]
                        }
                    ]
                }
            }
        ]
    }
    mocker.patch(
        "requests.post",
        return_value=mocker.MagicMock(
            ok=True,
            json=lambda: dummy_data,
        ),
    )
    # Mock parse_svkcxlplugin_response to return the parsed output
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_response",
        return_value=dummy_data["nodeResponses"][0]["output"],
    )
    # Call the method under test
    result = get_cxlplugin_datasource.get_hosts_info("CL_ID_1", "localhost")

    # Assertions
    assert "id" in result[0]
    assert len(result) == 1
    assert result[0]["name"] == 'testhost.area.51'


def test_cxlplugin_setup_tables(
    mocker, mock_db, client, get_cxlplugin_datasource, get_cognos_configs
):
    # Dummy data simulating the API response
    dummy_init_data = {
        "nodeResponses": [
            {
                "nodeId": "localhost",
                "output": """[
                    {
                        "Devices": [{"device_id": "123", "status": "active"}],
                        "Hosts": [{"host_id": "456", "status": "active"}],
                        "Type": "FM_DIRECT_CMMH"
                    }
                ]""",
            }
        ]
    }
    # Mock the response for get_cluster_nodes
    mocker.patch(
        "cognos.backend.cxlplugin_datasource.CXLPlugin.get_cluster_nodes",
        return_value={
            "CL_ID_1": [
                {"nodeId": "localhost", "nodePort": "9998"},
                {"nodeId": "127.0.0.1", "nodePort": "8888"},
            ]
        },
    )
    # Mock requests.post to return a dummy HTTP response
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = json.dumps(dummy_init_data).encode("utf-8")
    dummy_response.headers["Content-Type"] = "application/json"
    mocker.patch("requests.post", return_value=dummy_response)
    # Mock parse_svkcxlplugin_setup_response to return parsed content
    parsed_output = eval(dummy_init_data["nodeResponses"][0]["output"])
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_setup_response",
        return_value=parsed_output,
    )
    # Call the method under test
    result = get_cxlplugin_datasource.get_setup_info()
    # Assertions
    expected_output = parsed_output
    assert result == expected_output


@patch("cognos.backend.helper.init_connections_table")
@patch("cognos.backend.helper.init_hosts_table")
@patch("cognos.backend.helper.get_fm_host_info")
@patch("cognos.backend.helper.init_devices_table")
@patch("cognos.backend.helper.get_fm_devices_info")
@patch("cognos.backend.helper.get_devport_hostname_map")
@patch("cognos.backend.helper.get_devport_name_map")
@patch("cognos.backend.cxlplugin_datasource.CXLPlugin.get_setup_info")
@patch("cognos.backend.cxlplugin_datasource.CXLPlugin.get_cluster_nodes")
def test_setup_tables(
    mock_get_cluster_nodes,
    mock_get_setup_info,
    mock_get_devport_name_map,
    mock_get_devport_hostname_map,
    mock_get_fm_devices_info,
    mock_init_devices_table,
    mock_get_fm_host_info,
    mock_init_hosts_table,
    mock_init_connections_table,
):
    # Mock get_cluster_nodes to return dummy data
    mock_get_cluster_nodes.return_value = {
        "CL_ID_1": [{"nodeId": "node1"}, {"nodeId": "node2"}]
    }
    # Mock get_setup_info to return dummy payload
    mock_get_setup_info.return_value = [
        {
            "Devices": [{"device_id": "123", "status": "active"}],
            "Hosts": [{"host_id": "456", "status": "active"}],
            "type": "FM_DIRECT_CMMH",
        }
    ]
    # Mock other helper functions to avoid execution dependencies
    mock_get_devport_name_map.return_value = {"123": "Port1"}
    mock_get_devport_hostname_map.return_value = {"Port1": "Host1"}
    mock_get_fm_devices_info.return_value = [
        {"device_id": "123", "status": "active"}
    ]
    mock_get_fm_host_info.return_value = [
        {"host_id": "456", "status": "active"}
    ]
    # Instantiate the class and call the method
    plugin = cxlds.CXLPlugin()
    plugin.setup_tables()
    # Assertions to ensure all methods were called with expected data
    mock_get_cluster_nodes.assert_called_once_with("CL_ID_1")
    mock_get_setup_info.assert_any_call("CL_ID_1", "node1")
    mock_get_setup_info.assert_any_call("CL_ID_1", "node2")
    mock_init_devices_table.assert_called()
    mock_init_hosts_table.assert_called()
    mock_init_connections_table.assert_called()


def test_update_metrics_host_filter(
    get_cxlplugin_datasource, mocker, client, mock_db
):
    data = client.post(
        "/update_metrics_host_filter", json={"host": {"value": "test_host"}}
    )
    get_cxlplugin_datasource.update_metrics_host_filter()


@pytest.fixture
def cxl_plugin():
    """Fixture to create an instance of CXLPlugin."""
    return cxlds.CXLPlugin()


@patch(
    "cognos.backend.cxlplugin_datasource.LIST_CLUSTER_EP",
    "http://mocked.endpoint/list_cluster",
)
@patch("requests.post")
def test_get_cluster_nodes(mock_post, cxl_plugin):
    # Mock the gen_list_cluster_req_params method dynamically
    cxl_plugin.gen_list_cluster_req_params = MagicMock(
        return_value={"featureParams": "dummy_params"}
    )
    # Mock the response from requests.post
    mock_post.return_value.json.return_value = {
        "clusterInfo": [
            {
                "clusterId": "CL_ID_1",
                "nodeInfo": [{"nodeId": "localhost", "nodePort": "9998"}],
            }
        ]
    }
    cluster_id = "CL_ID_1"
    result = cxl_plugin.get_cluster_nodes(cluster_id)
    expected = {"CL_ID_1": [{"nodeId": "localhost", "nodePort": "9998"}]}
    assert result == expected


@patch("requests.post")
@patch("cognos.backend.helper.delete_connection")
@patch("cognos.backend.helper.remove_device_attached_host")
@patch("cognos.backend.helper.get_host_attached_devices")
@patch("cognos.backend.helper.get_devid_from_name")
@patch("cognos.backend.helper.get_hostid_from_name")
def test_detach_device(
    mock_get_hostid_from_name,
    mock_get_devid_from_name,
    mock_get_host_attached_devices,
    mock_remove_device_attached_host,
    mock_delete_connection,
    mock_post,
):
    # Set up CXLPlugin instance
    cxl_plugin = cxlds.CXLPlugin()
    feature_params = (
        "cluster_id=CL_ID_1;command=DetachMemory;"
        "dev_id=1401;host_id=1401;mode=direct"
    )
    # Mock request data
    mock_request_data = {"dev_name": "Device1", "host_name": "Host1"}
    mock_get_devid_from_name.return_value = "1234"
    mock_get_hostid_from_name.return_value = "5678"
    mock_post.return_value.ok = True
    mock_post.return_value.json.return_value = {
        "nodeResponses": [{"output": '{"status": "success"}'}]
    }
    mock_get_host_attached_devices.return_value = [
        {"dev_name": "Device1", "status": "detached"}
    ]


@patch(
    "cognos.backend.cxlplugin_datasource.LIST_CLUSTER_EP",
    "http://mocked.endpoint/list_cluster",
)
@patch("requests.post")
def test_get_node_info(mock_post, cxl_plugin):
    # Mock the response for get_cluster_nodes
    mock_post.return_value.json.return_value = {
        "clusterInfo": [
            {
                "clusterId": "CL_ID_1",
                "nodeInfo": [{"nodeId": "localhost", "nodePort": "9998"}],
            }
        ]
    }
    cxl_plugin.gen_list_cluster_req_params = MagicMock(
        return_value={"featureParams": "dummy_params"}
    )
    result = cxl_plugin.get_node_info()
    expected = [("CL_ID_1", "localhost")]
    assert result == expected


@patch("cognos.backend.cxlplugin_datasource.CXLPlugin.get_node_info")
@patch("cognos.backend.cxlplugin_datasource.CXLPlugin.get_devices_info")
def test_aggregate_info(mock_get_devices_info, mock_get_node_info, cxl_plugin):
    # Mock get_node_info to return test nodes
    mock_get_node_info.return_value = [("CL_ID_1", "localhost")]
    # Mock get_devices_info to return test device data
    mock_get_devices_info.return_value = [
        {
            "dev_capacity": 274877906944,
            "dev_id": 549755813888,
            "dev_port": 10,
            "hosts_attached": ["Host 1 LNK0"],
        },
        {
            "dev_capacity": 274877906944,
            "dev_id": 824633720832,
            "dev_port": 11,
            "hosts_attached": ["Host 1 LNK0"],
        },
    ]
    result = cxl_plugin.aggregate_info(
        function_name=cxl_plugin.get_devices_info, key="dev_id"
    )
    expected = [
        {
            "dev_capacity": 274877906944,
            "dev_id": 549755813888,
            "dev_port": 10,
            "hosts_attached": ["Host 1 LNK0"],
        },
        {
            "dev_capacity": 274877906944,
            "dev_id": 824633720832,
            "dev_port": 11,
            "hosts_attached": ["Host 1 LNK0"],
        },
    ]
    assert result == expected
    mock_get_node_info.assert_called_once()
    mock_get_devices_info.assert_called_once_with("CL_ID_1", "localhost")


@patch("cognos.backend.cxlplugin_datasource.CXLPlugin.aggregate_info")
def test_get_hosts(mock_aggregate_info, get_cxlplugin_datasource, mock_app):
    # Mock the return value of aggregate_info
    mock_aggregate_info.return_value = [
        {"id": "host1", "name": "Host 1"},
        {"id": "host2", "name": "Host 2"},
    ]
    # Set up the test request context
    with mock_app.test_request_context("/get_hosts", method="GET"):
        response = get_cxlplugin_datasource.get_hosts()
        expected_response = jsonify(
            [
                {"value": "Host 1", "label": "Host 1"},
                {"value": "Host 2", "label": "Host 2"},
            ]
        )
        assert response.status_code == 200
        assert json.loads(response.data) == json.loads(expected_response.data)
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        mock_aggregate_info.assert_called_once_with(
            get_cxlplugin_datasource.get_hosts_info, "id"
        )


@patch("cognos.backend.cxlplugin_datasource.CXLPlugin.aggregate_info")
def test_post_devices(mock_aggregate_info, get_cxlplugin_datasource, mock_app):
    # Mock the return value of aggregate_info
    mock_aggregate_info.return_value = [
        {"dev_id": "device1", "name": "Device 1"},
        {"dev_id": "device2", "name": "Device 2"},
    ]
    # Set up the test request context
    with mock_app.test_request_context("/post_devices", method="POST"):
        response = get_cxlplugin_datasource.post_devices()
        expected_response = jsonify(
            [
                {"dev_id": "device1", "name": "Device 1"},
                {"dev_id": "device2", "name": "Device 2"},
            ]
        )
        assert response.status_code == 200
        assert json.loads(response.data) == json.loads(expected_response.data)
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        mock_aggregate_info.assert_called_once_with(
            get_cxlplugin_datasource.get_devices_info, "dev_id"
        )


def test_attach_device_database_mock(
    mocker, get_cxlplugin_datasource, mock_app
):
    # Mock request data
    mock_request_data = {"dev_name": "dev2", "host_name": "host2"}
    mocker.patch.object(
        get_cxlplugin_datasource,
        "get_node_info",
        return_value=[("CL_ID_1", "node1"), ("CL_ID_1", "node2")],
    )
    mocker.patch(
        "cognos.backend.helper.get_devid_from_name", return_value="12345"
    )
    mocker.patch(
        "cognos.backend.helper.get_hostid_from_name", return_value="54321"
    )
    mocker.patch(
        "cognos.backend.helper.gen_svkcxlplugin_request_params",
        return_value={"mock": "body"},
    )
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {
        "nodeResponses": [
            {"nodeId": "node1", "output": '{"rc": 0}'},
            {"nodeId": "node2", "output": '{"rc": 0}'},
        ]
    }
    mocker.patch("requests.post", return_value=mock_response)
    mocker.patch(
        "cognos.backend.helper.parse_svkcxlplugin_response",
        side_effect=lambda response: json.loads(
            response.json()["nodeResponses"][0]["output"]
        ),
    )
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_db.cursor.return_value = mock_cursor
    mocker.patch(
        "cognos.backend.helper.connect_to_mysql",
        return_value=(mock_db, mock_cursor),
    )
    mocker.patch("cognos.backend.helper.disconnect_mysql", return_value=None)
    mock_cursor.execute.return_value = None
    mock_cursor.commit.return_value = None
    mocker.patch(
        "cognos.backend.helper.update_device_attached_hosts", return_value=None
    )
    mocker.patch(
        "cognos.backend.helper.get_host_attached_devices",
        return_value=[{"host_name": "host2"}],
    )
    with mock_app.app_context():
        response = get_cxlplugin_datasource.attach_device(
            mock_request=True, mock_request_data=mock_request_data
        )
    assert response.status_code == 200


@patch("cognos.backend.helper.get_all_hosts")
def test_get_all_hosts_info_success(mock_get_all_hosts, mock_app):
    # Mock the return value of get_all_hosts
    mock_get_all_hosts.return_value = {
        "hostnames": ["host1", "host2", "host3"]
    }
    # Use Flask's app context
    with mock_app.app_context():
        # Instantiate the plugin and call the method
        plugin_instance = cxlds.CXLPlugin()
        response = plugin_instance.get_all_hosts_info()
        expected_response = [
            {"value": "host1", "label": "host1"},
            {"value": "host2", "label": "host2"},
            {"value": "host3", "label": "host3"},
        ]
        assert (
            response.status_code == 200
        ), "Response status code should be 200"
        assert (
            json.loads(response.data) == expected_response
        ), "Response data should match formatted hostnames"
        assert (
            response.headers["Access-Control-Allow-Origin"] == "*"
        ), "CORS header should be set"
        mock_get_all_hosts.assert_called_once()


@patch("cognos.backend.helper.get_all_hosts")
def test_get_all_hosts_info_no_data(mock_get_all_hosts, mock_app):
    # Mock the return value of get_all_hosts as None
    mock_get_all_hosts.return_value = None
    with mock_app.app_context():
        plugin_instance = cxlds.CXLPlugin()
        response = plugin_instance.get_all_hosts_info()
        # Expected response is an empty list
        expected_response = []
        assert (
            response.status_code == 200
        ), "Response status code should be 200"
        assert (
            json.loads(response.data) == expected_response
        ), "Response data should be an empty list"
        assert (
            response.headers["Access-Control-Allow-Origin"] == "*"
        ), "CORS header should be set"
        mock_get_all_hosts.assert_called_once()


@patch("cognos.backend.helper.get_all_hosts")
def test_get_all_hosts_info_error(mock_get_all_hosts, mock_app):
    # Simulate an exception being raised in get_all_hosts
    mock_get_all_hosts.side_effect = Exception("Database error")
    with mock_app.app_context():
        plugin_instance = cxlds.CXLPlugin()
        response = plugin_instance.get_all_hosts_info()
        # Expected error response
        expected_response = {"error": "Failed to retrieve host information"}
        assert (
            response.status_code == 500
        ), "Response status code should be 500 for errors"
        assert (
            json.loads(response.data) == expected_response
        ), "Response data should indicate an error occurred"
        mock_get_all_hosts.assert_called_once()
