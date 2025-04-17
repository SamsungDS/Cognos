import pytest

from cognos.backend.cognos_northbound import Cognos


def test_cognos_init():
    cognos = Cognos()
    assert cognos.headers
    assert cognos.clusters == []


def test_populate_cluster_objects(mocker):
    dummy_cognos_topology = {
        'clusters':
            [
                {
                    'cluster_name': 'CL_ID_1',
                    'nodes': [
                        {
                            'node_name': 'node_1',
                            'devices': ['DEV14-256G', 'DEV15-256G'],
                            'fm_type': 'FM_DIRECT_CMMD'
                        },
                        {
                            'node_name': 'node_1',
                            'devices': ['DEV17-256G'],
                            'fm_type': 'FM_DIRECT_CMMH'
                        }
                    ]
                }
            ]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.build_cognos_topology',
        return_value=dummy_cognos_topology
    )
    dummy_list_nodes_response = {
        "node_info": [
            {
                "node_name": "node_1",
                "node_port": "9998",
                "node_ip": "1.2.3.0",
                "status": "online/offline",
            }
        ]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.list_nodes',
        return_value=dummy_list_nodes_response
    )
    cognos = Cognos()
    cognos.populate_cluster_objects()
    assert cognos.clusters


def test_fetch_cognos_topology_response(mocker, client, mock_app):
    dummy_cognos_topology = {
        'clusters':
            [
                {
                    'cluster_name': 'CL_ID_2',
                    'nodes': [
                        {
                            'node_name': 'node_3',
                            'devices': ['DEV14-256G', 'DEV15-256G'],
                            'fm_type': 'FM_DIRECT_CMMD'
                        },
                        {
                            'node_name': 'node_4',
                            'devices': ['DEV17-256G'],
                            'fm_type': 'FM_DIRECT_CMMH'
                        }
                    ]
                }
            ]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.build_cognos_topology',
        return_value=dummy_cognos_topology
    )
    cognos = Cognos()
    with mock_app.app_context():
        response = cognos.fetch_cognos_topology_response()
    assert response.status_code == 200
    assert response.json == dummy_cognos_topology


def test_build_cognos_topology(mocker):
    dummy_list_clusters_response = {
        "clusters": [
            {"cluster_name": "cluster_name_0"}
        ]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.list_clusters',
        return_value=dummy_list_clusters_response
    )

    dummy_legacy_topology_response = [
        {"host": "1.2.3.0", "fm_type": "FM_DIRECT_CMMD",
         "devices": ["DEV1", "DEV2"]},
        {"host": "3.4.5.0", "fm_type": "FM_DIRECT_CMMH", "devices": ["DEV3"]}
    ]
    mocker.patch(
        'cognos.backend.helper.fetch_topology',
        return_value=dummy_legacy_topology_response
    )

    dummy_list_nodes_response = {
        "node_info": [
            {
                "node_name": "xyz",
                "node_port": "9998",
                "node_ip": "1.2.3.0",
                "status": "online/offline",
            },
            {
                "node_name": "abc",
                "node_port": "9998",
                "node_ip": "3.4.5.0",
                "status": "online/offline",
            },
        ]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.list_nodes',
        return_value=dummy_list_nodes_response
    )

    dummy_list_cluster_nodes_response = {
        "clusters": [{
            "cluster_name": "cluster_name_0",
            "nodes": [
                {
                    "node_name": "xyz",
                    "status": "online/offline"
                },
                {
                    "node_name": "abc",
                    "status": "online/offline"
                }
            ]
        }]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.list_cluster_nodes',
        return_value=dummy_list_cluster_nodes_response
    )

    cognos = Cognos()
    cognos.build_cognos_topology()


def test_node_ip_to_name_mapping():
    dummy_node_info_input = [
        {
            "node_name": "cognos_node1",
            "node_port": "9998",
            "node_ip": "<IP addr>",
            "status": "online/offline",
        }
    ]
    cognos = Cognos()
    cognos.node_ip_to_name_mapping(dummy_node_info_input)


def test_get_cluster_nodes(mocker):
    dummy_list_cluster_nodes_response = {
        "clusters": [{
            "cluster_name": "cluster_name_0",
            "nodes": [
                {
                    "node_name": "abc",
                    "status": "online/offline"
                }
            ]
        }]
    }
    mocker.patch(
        'cognos.backend.cognos_northbound.Cognos.list_cluster_nodes',
        return_value=dummy_list_cluster_nodes_response
    )
    dummy_cluster_name = "cluster_name_0"
    cognos = Cognos()
    cognos.get_cluster_nodes(dummy_cluster_name)
