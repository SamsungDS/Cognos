import json
from requests.models import Response

from cognos.backend.test.test_cal_helper import construct_dummy_response


def test_cxlplugin_init(mocker, client, get_cognos_configs,
                        get_cxlplugin_datasource):
    dummy_data = {
        "output": {
            get_cognos_configs["node_endpoint"]: {
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
    payload_output = dummy_data["output"]
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_setup_info',
        return_value=payload_output
    )
    get_cxlplugin_datasource.init()


def test_cxlplugin_get_topology(mocker, client, get_cxlplugin_datasource):
    mock_data = [
        "Host 1 LINK 0",
        "DEV10,DEV11"
    ]
    mocker.patch(
        'cognos.backend.helper.fetch_topology',
        return_value=mock_data
    )
    get_cxlplugin_datasource.get_topology()


def test_cxlplugin_get_hosts(mocker, client, get_cxlplugin_datasource):
    mock_hosts = [
        {'name': 'host1'},
        {'name': 'host2'}
    ]
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_hosts_info',
        return_value=mock_hosts
    )
    get_cxlplugin_datasource.get_hosts()


def test_cxlplugin_post_devices(mocker, client, get_cxlplugin_datasource,
                                mock_devices_info):
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_devices_info',
        return_value=mock_devices_info
    )
    get_cxlplugin_datasource.post_devices()


def test_cxlplugin_membox_capacity(mocker, client, get_cxlplugin_datasource,
                                   mock_devices_info):
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_devices_info',
        return_value=mock_devices_info
    )
    get_cxlplugin_datasource.membox_capacity()


def test_host_devices(mocker, get_cxlplugin_datasource, mock_db, client):
    data = client.get('/host_devices', json={"host": "host1"})

    mock_connection, mock_cursor = mock_db
    mock_device = [[
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
    mock_cursor.fetchall.return_value = mock_device
    get_cxlplugin_datasource.host_devices()


def test_cxlplugin_available_devices(mocker, get_cxlplugin_datasource,
                                     client, mock_connection, mock_cursor):
    mocker.patch('cognos.backend.helper.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    dummy_data = [[
        'DUMMY_DEV1-256'
    ]]
    mock_cursor.execute.return_value = True
    mock_cursor.fetchall.return_value = dummy_data
    get_cxlplugin_datasource.available_devices()


def test_cxlplugin_detach_device(mocker, get_cxlplugin_datasource,
                                 get_cognos_configs, mock_app, app_context,
                                 mock_connection, mock_cursor):
    with mock_app.test_request_context('/detach_device', method='POST'):
        dummy_detach_response = {
            "nodeResponses": [
                {
                    "nodeId": "localhost",
                    "output": """{"rc": 0}"""
                }
            ]
        }
        dummy_response = Response()
        dummy_response.status_code = 200
        dummy_response._content = (
            json.dumps(dummy_detach_response, indent=2).encode('utf-8')
        )
        dummy_response.headers['Content-Type'] = 'application/json'
        mocker.patch('requests.post', return_value=dummy_response)
        mocker.patch(
            'cognos.backend.helper.parse_svkcxlplugin_response',
            return_value={get_cognos_configs["node_endpoint"]: {'rc': 0}}
        )
        mocker.patch(
            'cognos.backend.helper.get_db_passwd',
            return_value="CXL123mem!"
        )
        mocker.patch(
            'cognos.backend.helper.delete_connection',
            return_value=True
        )
        get_cxlplugin_datasource.detach_device(
            mock_request=True,
            mock_request_data={"dev_name": "dev1", "host_name": "host1"}
        )


def test_cxlplugin_attach_device(mocker, get_cxlplugin_datasource,
                                 get_cognos_configs, mock_app,
                                 app_context):
    with mock_app.test_request_context('/attach_device', method='POST'):
        dummy_attach_response = {
            "nodeResponses": [
                {
                    "nodeId": "localhost",
                    "output": """{"rc": 0}"""
                }
            ]
        }

        dummy_response = Response()
        dummy_response.status_code = 200
        dummy_response._content = (
            json.dumps(dummy_attach_response, indent=2).encode('utf-8')
        )
        dummy_response.headers['Content-Type'] = 'application/json'
        mocker.patch('requests.post', return_value=dummy_response)
        mocker.patch(
            'cognos.backend.helper.parse_svkcxlplugin_response',
            return_value={get_cognos_configs["node_endpoint"]: {'rc': 0}}
        )
        mock_connection = mocker.MagicMock()
        mock_cursor = mocker.MagicMock()
        mocker.patch('mysql.connector.connect', return_value=mock_connection)
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.execute.return_value = True
        mocker.patch(
            'cognos.backend.helper.get_db_passwd',
            return_value="CXL123mem!"
        )
        mocker.patch(
            'cognos.backend.helper.connect_to_mysql',
            return_value=(mock_connection, mock_cursor)
        )
        mocker.patch(
            'cognos.backend.helper.disconnect_mysql',
            return_value=True
        )
        # Return a dummy value for `fetchone` to avoid `MagicMock`
        mock_cursor.fetchone.return_value = ('host1',)

        # mock_cursor.execute.return_value = True
        mocker.patch('cognos.backend.helper.get_host_attached_devices',
                     return_value={"device": "dev1"})
        get_cxlplugin_datasource.attach_device(
            mock_request=True,
            mock_request_data={"dev_name": "dev2", "host_name": "host2"}
        )


def test_cxlplugin_get_mb_info(client, get_cxlplugin_datasource):
    get_cxlplugin_datasource.get_mb_info()


def test_cxlplugin_setup_info(mocker, client,
                              get_cxlplugin_datasource, get_cognos_configs):
    dummy_init_data = {
        "nodeResponses": [
            {
                "nodeId": "localhost",
                "output": """{
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
                }"""
            }
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_init_data, indent=2).encode('utf-8')
    )
    dummy_response.headers['Content-Type'] = 'application/json'
    mocker.patch('requests.post', return_value=dummy_response)
    mocker.patch(
        'cognos.backend.helper.parse_svkcxlplugin_response',
        return_value=dummy_init_data["nodeResponses"][0]["output"]
    )
    get_cxlplugin_datasource.get_setup_info()


def test_cxlplugin_get_devices_info(mock_db, mocker,
                                    get_cxlplugin_datasource,
                                    get_cognos_configs):
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
                }"""
            }
        ]
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    payload_output = json.loads(dummy_data["nodeResponses"][0]["output"])
    mocker.patch(
        'cognos.backend.helper.parse_svkcxlplugin_response',
        return_value=payload_output
    )
    get_cxlplugin_datasource.get_devices_info()


def test_cxlplugin_get_hosts_info(mock_db, mocker,
                                  get_cxlplugin_datasource,
                                  get_cognos_configs):
    mock_connection, mock_cursor = mock_db

    dummy_data = {
        "nodeResponses": [
            {
                "nodeId": "localhost",
                "output": """{
                    "hosts": [
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
                }"""

            }

        ]
    }
    dummy_response = construct_dummy_response(dummy_data)
    mocker.patch('requests.post', return_value=dummy_response)
    payload_output = dummy_data["nodeResponses"][0]["output"]
    mocker.patch(
        'cognos.backend.helper.parse_svkcxlplugin_response',
        return_value=payload_output
    )
    get_cxlplugin_datasource.get_hosts_info()


def test_cxlplugin_setup_tables(mocker, mock_db, client,
                                get_cxlplugin_datasource,
                                get_cognos_configs):

    dummy_hosts_data = [
        {
            "host_target_ports": [11, 10],
            "id": 551903297536,
            "mem_capacity": 547608330240,
            "name": "Host 1 LNK0"
        }
    ]
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_hosts_info',
        return_value=dummy_hosts_data
    )

    dummy_devices_data = [
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
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_devices_info',
        return_value=dummy_devices_data
    )

    dummy_init_data = {
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
    mocker.patch(
        'cognos.backend.cxlplugin_datasource.CXLPlugin.get_setup_info',
        return_value=dummy_init_data
    )
    mocker.patch(
        'cognos.backend.helper.insert_devices',
        return_value=True
    )
    mocker.patch(
        'cognos.backend.helper.insert_hosts',
        return_value=True
    )
    mocker.patch(
        'cognos.backend.helper.insert_connection',
        return_value=True
    )
    get_cxlplugin_datasource.setup_tables()


def test_update_metrics_host_filter(get_cxlplugin_datasource, mocker, client,
                                    mock_db):
    data = client.post(
        '/update_metrics_host_filter',
        json={"host": {"value": "test_host"}}
    )
    get_cxlplugin_datasource.update_metrics_host_filter()
