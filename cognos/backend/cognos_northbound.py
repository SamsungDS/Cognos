import json
import os
import requests
import socket

from cognos.backend.base_control_interface import BaseControlInterface
from cognos.backend.helper import fetch_topology
from flask import request, jsonify

from cognos.backend.cluster import Cluster
from cognos.backend.node import Node
from cognos.backend.cmmd import CMMD
from cognos.backend.cmmh import CMMH

from cognos.backend.constants import (
    COGNOS_NORTHBOUND_ENDPOINTS, COGNOS_ENDPOINT
)


class Cognos(BaseControlInterface):
    def __init__(self):
        self.headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }

        self.clusters = []  # list[Cluster]

    @property
    def cognos_endpoint(self):
        return COGNOS_ENDPOINT

    @property
    def api_version(self):
        pass

    @property
    def cognos_commands(self):
        pass

    @property
    def feature_map(self):
        pass

    def populate_cluster_objects(self):
        list_nodes_data = self.list_nodes()
        cognos_topology = self.build_cognos_topology()
        node_name_to_ip_map = (
            self.node_name_to_ip_mapping(list_nodes_data["node_info"])
        )
        for c in cognos_topology['clusters']:
            nodes = []
            for n in c['nodes']:
                devices = []
                for d in n['devices']:
                    # TODO: expand logic to support more device types
                    device = (
                        CMMD(d)
                        if n['fm_type'] == 'FM_DIRECT_CMMD' else CMMH(d)
                    )
                    devices.append(device)
                node_ip = node_name_to_ip_map[n['node_name']]
                node = Node(n['node_name'], node_ip, n['fm_type'],
                            "default_node_type", devices=devices,
                            cluster_name=c['cluster_name'])
                nodes.append(node)
            cluster = Cluster(c['cluster_name'], nodes=nodes)
            self.clusters.append(cluster)

    def fetch_cognos_topology_response(self):
        payload = self.build_cognos_topology()
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def build_cognos_topology(self):
        """
        TODO: generate cognos_topology directly from in-mem objects once the
              necessary northbound API are ready

        Returns: REST response containing a data-structure similar to

        { 'clusters':
            [
                {'cluster_name': 'CL_ID_1',
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
        """

        cognos_topology = {}
        cluster_data = self.list_clusters()
        # TODO: translation using legacy API approach until new API is ready
        node_level_topology = fetch_topology()

        list_nodes_data = self.list_nodes()
        node_map = self.node_ip_to_name_mapping(list_nodes_data["node_info"])

        clusters = []
        for cluster in cluster_data["clusters"]:
            cluster_info = {}
            cluster_info["cluster_name"] = cluster["cluster_name"]
            cluster_nodes = self.get_cluster_nodes(cluster["cluster_name"])
            cluster_info["nodes"] = []
            for node in node_level_topology:
                node_info = {}
                node_ip = socket.gethostbyname(node['host'])
                node_name = node_map[node_ip]
                if node_name in cluster_nodes:
                    node_info["node_name"] = node_name
                    node_info["devices"] = node['devices']
                    node_info['fm_type'] = node['fm_type']
                    cluster_info["nodes"].append(node_info)
            clusters.append(cluster_info)
        cognos_topology["clusters"] = clusters
        return cognos_topology

    def list_clusters(self):
        """
        Returns:
        {"clusters":[
            {
            "cluster_name": "cluster_name_0",
            },
            {
            "cluster_name": "cluster_name_1",
            },
            {
            "cluster_name": "cluster_name_2",
            }
        ]}
        """
        request_args = {"command_name": "list_clusters"}
        response = requests.post(
            COGNOS_NORTHBOUND_ENDPOINTS["list_clusters"],
            json=request_args,
            headers=self.headers
        )
        data = response.json()
        return json.loads(data['commandResponse'])

    def list_nodes(self):
        """
        Returns:
        {"node_info":[
            {
                "node_name":"cognos_node1",
                "node_port":"9998",
                "node_ip": "<IP addr>",
                "status": "online/offline",
            }
        ]}
        """
        request_args = {"command_name": "list_nodes"}
        response = requests.post(
            COGNOS_NORTHBOUND_ENDPOINTS["list_nodes"],
            json=request_args,
            headers=self.headers
        )
        data = response.json()
        return json.loads(data['commandResponse'])

    def list_cluster_nodes(self, cluster_name):
        """
        Returns:
        {"clusters":[{
            "cluster_name": "name",
            "nodes":[
                {
                    "node_name": "node1",
                    "status": "online/offline"
                },
                {
                    "node_name": "node2",
                    "status": "online/offline"
                }
            ]
        }]}
        """
        request_args = {"command_name": "list_nodes_in_cluster"}
        response = requests.post(
            COGNOS_NORTHBOUND_ENDPOINTS["list_cluster_nodes"] + cluster_name,
            json=request_args,
            headers=self.headers
        )
        data = response.json()
        return json.loads(data['commandResponse'])

    def list_devices(self):
        pass

    def list_applications(self):
        pass

    def create_cluster(self):
        pass

    def delete_cluster(self):
        pass

    def node_name_to_ip_mapping(self, node_info):
        node_map = {}
        for node in node_info:
            if node['node_name'] not in node_map:
                node_map[node['node_name']] = node['node_ip']
        return node_map

    def node_ip_to_name_mapping(self, node_info):
        node_map = {}
        for node in node_info:
            if node['node_ip'] not in node_map:
                node_map[node['node_ip']] = node['node_name']
        return node_map

    def get_cluster_nodes(self, cluster_name):
        cluster_nodes_response = self.list_cluster_nodes(cluster_name)
        for cluster in cluster_nodes_response["clusters"]:
            if cluster["cluster_name"] == cluster_name:
                nodes = []
                for node in cluster["nodes"]:
                    nodes.append(node["node_name"])
                return nodes
        return None
