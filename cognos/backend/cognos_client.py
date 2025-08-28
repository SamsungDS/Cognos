import json
import math
import os
import requests
import socket
import sys
import time
from pathlib import Path
from typing import Callable, List, Dict
from cognos.backend.base_control_interface import BaseControlInterface

from flask import request

from cognos.backend.node import Node
from cognos.backend.cmmd import CMMD
from cognos.backend.cmmh import CMMH

from cognos.backend.constants import (
    COGNOS_NORTHBOUND_ENDPOINTS, COGNOS_ENDPOINT
)

from cognos.backend.sqlite_client import SqliteClient
from cognos.backend.direct_node_interface import DirectAttachedNodeInterface
from cognos.backend.remote_node_interface import RemoteAttachedNodeInterface
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient
import cognos.backend.helper as helper


class Cognos(BaseControlInterface):
    """
    Used to manage the entire Cognos System

    Perform operations such as fetching topology,
    retrieving metrics, performing attach/detach operations
    """
    def __init__(self, logger, mock=False):
        self.headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        self.logger = logger

        self.sql_client = SqliteClient(mock=mock, logger=self.logger)
        self.remote_node_client = RemoteAttachedNodeInterface()
        self.direct_node_client = DirectAttachedNodeInterface()

        self.influx_client = CognosInfluxDBClient(self.sql_client)
        self.cognos_metric_functions = {
            "dram_cxl_usage": (
                self.influx_client.get_recent_dram_cxl_usage_data
            ),
            "cpu_mem_usage": self.influx_client.get_cpu_mem_usage,
            "memserver_capacity": self.influx_client.get_memserver_capacity,
            "cmmb_usage": self.influx_client.get_membox_usage,
            "cmmb_capacity": self.influx_client.get_membox_capacity,
            "cmmb_bandwidth": self.influx_client.get_membox_bandwidth,
            "devices_count": self.influx_client.get_attached_devices_count
        }

        # used to help initialize underlying sql tables
        self.cognos_system = {}  # { cluster_name: {node_name: [device_id]} }
        self._initialize_cognos()
        self.logger.info("Successfully initialized Cognos..")

    def _remove_connection(self, cluster_name: str, node_name: str,
                           dev_id: int) -> None:
        """
        Removes a connection in underlying sqliteDB between a node and device
        """
        self.sql_client.exec_query(
            "DELETE FROM connections WHERE "
            "(cluster_name = ? AND node_name = ? AND device_id = ?)",
            (cluster_name, node_name, dev_id)
        )

    def _add_connection(self, cluster_name: str, node_name, dev_id) -> None:
        """
        Adds a new connection to underlying sqliteDB
        """
        self.sql_client.exec_query(
            "INSERT INTO connections VALUES "
            "(?, ?, ?)",
            (cluster_name, node_name, dev_id)
        )

    def _initialize_cognos(self) -> None:
        """
        - Creates SQLite schema and tables
        - Retrieves current state of Cognos System.
        - Defines attributes such as hostname and device_name
        - Populates SQLite DB and maps relationships / metadata

        Refer to dbschema.md for what type of information is stored
        """
        try:
            self._initialize_hosts_devices()
            self.logger.info(
                "Successfully retrieved all hosts / devices info.."
            )
        except Exception as e:
            self.logger.critical(
                f"Unable to retrieve hosts & devices info of system: {str(e)}"
            )
            sys.exit()

        try:
            self._initialize_connections()
            self.logger.info(
                "Successfully retrieved all device to host mappings.."
            )
        except Exception as e:
            self.logger.critical(
                f"Unable to get host to device mapping: {str(e)}"
            )
            sys.exit()

        self.logger.info("** Initialized Cognos DB Tables ***")
        self.sql_client.get_table_records("devices")
        self.sql_client.get_table_records("hosts")
        self.sql_client.get_table_records("connections")

    def _initialize_connections(self) -> None:
        """
        Creates mappings of clusters to nodes or
        clusters to nodes to devices in
        sqlite connections table

        Refer to dbschema.md for what type of information is stored
        """
        self.logger.info(f"COGNOS SYSTEM: {self.cognos_system}")
        # update connections table
        for cluster in self.cognos_system.keys():
            for node in self.cognos_system[cluster]:
                # add cluster node connection
                self.logger.info(f"Adding Cluster Node connection")
                self.logger.info(
                    f"cluster_name: {cluster} "
                    f"node_name: {node} "
                )
                self.sql_client.execute_query(
                    "INSERT INTO connections "
                    "(cluster_name, node_name) "
                    f"VALUES ('{cluster}', '{node}')"
                )
                for device in self.cognos_system[cluster][node]:
                    # check to see if current node is direct attached
                    direct_node = (
                        True
                        if self.direct_node_client.list_devices(node, cluster)
                        else False
                    )

                    if not direct_node:
                        # check if remote devices are attached or not
                        remote_devices = (
                            self.remote_node_client.list_devices(
                                node, cluster
                            )
                        )
                        attached_remote_device_ids = (
                            [
                                dev["dev_id"]
                                for dev in remote_devices
                                if dev["hosts_attached"]
                            ]
                        )
                        if device in attached_remote_device_ids:
                            self.logger.info(f"Adding remote dev connection")
                            self.logger.info(
                                f"cluster_name: {cluster} "
                                f"node_name: {node} "
                                f"device: {device}"
                            )
                            self.sql_client.execute_query(
                                "INSERT INTO connections "
                                "(cluster_name, node_name, device_id) "
                                f"VALUES ('{cluster}', '{node}', {device})"
                            )
                    else:
                        self.logger.info(f"Adding direct dev connection")
                        self.logger.info(
                            f"cluster_name: {cluster} "
                            f"node_name: {node} "
                            f"device: {device}"
                        )
                        # direct attached node, log connection
                        self.sql_client.execute_query(
                            "INSERT INTO connections "
                            "(cluster_name, node_name, device_id) "
                            f"VALUES ('{cluster}', '{node}', {device})"
                        )

    def _initialize_hosts_devices(self):
        """
        Populates both hosts and devices tables
        with metadata of all existing  hosts and devices
        in the cognos system.

        Refer to dbschema.md for what type of information is stored
        """
        clusters = self.list_clusters()

        # map node_name to ip_addr and hostname
        # {node_name: {"ip_addr": <ip_addr>, "hostname": <hostname>}}
        node_info_map = {}
        cognos_nodes = self.list_nodes()

        for n in cognos_nodes['node_info']:
            node_info_map[n['node_name']] = {}
            ip_addr = n['node_ip']
            node_info_map[n['node_name']]['ip_addr'] = ip_addr
            # TODO: update to strictly use node_name from node feature module
            # TODO: remove 'hostname' field
            hostname = n['node_name']
            node_info_map[n['node_name']]['hostname'] = hostname

        for cluster in clusters:
            self.cognos_system[cluster] = {}
            nodes = self.list_cluster_nodes(cluster)
            for node in nodes:
                #  get devices that belong to each node
                node_devices = []  # [device_id]
                # check to see if the current node is direct attached or not
                direct_attached_devices = self.direct_node_client.list_devices(
                    node, cluster
                )
                if direct_attached_devices:
                    for dev in direct_attached_devices:
                        # get additional info for each device
                        dev_info = self.direct_node_client.get_device_info(
                            node, cluster, dev["device_id"]
                        )
                        if dev['vendor_device_type'] == 'CMM-H':
                            cmmh = CMMH(dev_info, "direct")
                            self.sql_client.execute_query(
                                cmmh.serialize_device_to_insert_query()
                            )
                            node_devices.append(cmmh)
                        else:
                            cmmd = CMMD(dev_info, "direct")
                            self.sql_client.execute_query(
                                cmmd.serialize_device_to_insert_query()
                            )
                            node_devices.append(cmmd)
                else:
                    remote_attached_devices = (
                        self.remote_node_client.list_devices(node, cluster)
                    )
                    for dev in remote_attached_devices:
                        cmmd = CMMD(dev, "remote")
                        self.sql_client.execute_query(
                            cmmd.serialize_device_to_insert_query()
                        )
                        node_devices.append(cmmd)

                # add record for node in hosts table
                fm_type = ""
                mem_capacity = None
                target_ports = None
                ip_addr = ""
                hostname = ""
                remote_id = None

                if any(isinstance(dev, CMMH) for dev in node_devices):
                    fm_type = "FM_DIRECT_CMMH"
                elif any(
                        dev.attached_type == "remote" for dev in node_devices
                        ):
                    fm_type = "FM_REMOTE_CMMD"
                else:
                    fm_type = "FM_DIRECT_CMMD"

                if fm_type == "FM_REMOTE_CMMD":
                    host_data = (
                        self.remote_node_client.list_hosts(node, cluster)
                    )
                    for host in host_data:
                        if host["name"] == node:
                            mem_capacity = host['mem_capacity']
                            target_ports = str(host['host_target_ports'])
                            remote_id = host['id']
                else:
                    # dervied from attached devices for direct-attached hosts
                    mem_capacity = sum(dev.capacity for dev in node_devices)

                ip_addr = node_info_map[node]['ip_addr']
                hostname = node_info_map[node]['hostname']

                node_obj = Node(self.sql_client, node, fm_type, mem_capacity,
                                target_ports, ip_addr, hostname, remote_id)
                node_obj.insert_node_into_hosts_table()

                self.cognos_system[cluster][node] = (
                    [dev.device_id for dev in node_devices]
                )

    @property
    def cognos_endpoint(self):
        return COGNOS_ENDPOINT

    @property
    def scmc_version(self):
        payload = {}
        scmc_version_file = helper.get_scmc_version_file()
        if scmc_version_file:
            try:
                with open(scmc_version_file, "r") as v:
                    API_VERSION = v.read().strip()
                    payload = ({"version": API_VERSION})
            except Exception as error:
                raise RuntimeError(
                    f"Unable to retrieve API version: {str(error)}"
                )
        else:
            payload = ({"error": "version file not found"})
        return payload

    @property
    def cognos_commands(self):
        pass

    @property
    def feature_map(self):
        pass

    def fetch_topology(self) -> Dict[str, List]:
        """
        Returns: REST response containing a json-structure similar to

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
        payload = {'clusters': []}

        data = self.sql_client.exec_fetch_query(
            "SELECT c.cluster_name, c.node_name, c.device_id, h.fm_type "
            "FROM connections as c "
            "INNER JOIN hosts as h "
            "ON c.node_name = h.node_name",
            tuple()
        )

        clusters = list(set([row[0] for row in data]))
        nodes = list(set([row[1] for row in data]))
        cluster_node_map = {}  # {<cluster>: [<node>]}
        for row in data:
            if row[0] not in cluster_node_map:
                cluster_node_map[row[0]] = [row[1]]
            elif row[1] not in cluster_node_map[row[0]]:
                cluster_node_map[row[0]].append(row[1])

        # {<node>: {'fm_type': <fm_type>, 'devices': [<devices>]}}
        node_info = {}
        for node in nodes:
            if node not in node_info:
                node_info[node] = {'node_name': node}
            for row in data:
                if row[1] == node:
                    node_info[node]['fm_type'] = row[3]
                    if 'devices' not in node_info[node] and row[2]:
                        node_info[node]['devices'] = [row[2]]
                    elif row[2]:
                        node_info[node]['devices'].append(row[2])

        for cluster in clusters:
            cluster_info = {'cluster_name': cluster, 'nodes': []}
            for node in cluster_node_map[cluster]:
                cluster_info['nodes'].append(node_info[node])
            payload['clusters'].append(cluster_info)

        return payload

    def get_remote_hosts(self) -> Dict:
        """
        Retrieves all remote-attached hosts
        """
        remote_hosts = self.sql_client.exec_fetch_query(
            "SELECT DISTINCT hostname FROM hosts "
            "WHERE fm_type = 'FM_REMOTE_CMMD';",
            tuple()
        )
        payload = []
        for host in remote_hosts:
            host_selection = {
                "value": host[0],
                "label": host[0]
            }
            payload.append(host_selection)
        return payload

    def get_hosts(self) -> Dict:
        """
        Retrieves all hosts in Cognos System
        """
        hosts = self.sql_client.exec_fetch_query(
            "SELECT DISTINCT hostname FROM hosts;",
            tuple()
        )
        payload = []
        for host in hosts:
            host_selection = {
                "value": host[0],
                "label": host[0]
            }
            payload.append(host_selection)
        return payload

    def get_nodes(self) -> Dict:
        """
        Retrives all nodes in Cognos System
        """
        nodes = self.sql_client.exec_fetch_query(
            "SELECT DISTINCT node_name FROM hosts;",
            tuple()
        )
        payload = []
        for node in nodes:
            node_selection = {
                "value": node[0],
                "label": node[0]
            }
            payload.append(node_selection)
        return payload

    def get_remote_devices(self) -> List[Dict]:
        """
        Fetches remote devices (CMM-B) and corresponding metadata
        Returns:
        [
            {
                "dev_name": <dev_name>,
                "dev_capacity": <dev_capacity>,
                "dev_id": <dev_id>,
                "dev_port": <dev_port>,
                "hosts_attached": <hosts>
            },
            {
                ...
            }
        ]
        """

        devices = self.sql_client.exec_fetch_query(
            "SELECT d.id, d.mem_capacity, d.port, d.type, h.hostname, "
            "d.name FROM devices as d "
            "LEFT JOIN connections as c ON d.id = c.device_id "
            "LEFT JOIN hosts as h ON c.node_name = h.node_name "
            "WHERE d.mode = 'remote';",
            tuple()
        )

        payload = []
        for dev in devices:
            device_info = {
                "dev_name": dev[5],
                "dev_capacity": dev[1],
                "dev_id": dev[0],
                "dev_port": dev[2],
                "hosts_attached": dev[4]
            }
            payload.append(device_info)
        return payload

    def list_clusters(self) -> Dict[str, List]:
        """
        Retrieves all logical clusters in the Cognos System

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
        if response.ok:
            try:
                data = json.loads(response.json()['commandResponse'])
                return (
                    [
                        v for cluster in data["clusters"]
                        for v in cluster.values()
                    ]
                )
            except Exception as error:
                print(f"Failed to parse ListClusters response from controller")
                return []
        return []

    def list_nodes(self) -> Dict[str, List]:
        """
        Retrives all nodes in the Cognos System with metadata

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

    def list_cluster_nodes(self, cluster_name: str) -> Dict[str, List]:
        """
        Retrieves all nodes for the given cluster

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
        if response.ok:
            try:
                data = json.loads(response.json()['commandResponse'])
                nodes = []
                for c in data["clusters"]:
                    for n in c["nodes"]:
                        nodes.append(n["node_name"])
                return nodes
            except Exception as error:
                print(f"Failed to parse ListClusterNodes from controller")
                return []
        return []

    def get_host_devices_from_db(self, host):
        node_name = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT node_name FROM hosts WHERE hostname = ?",
            (host,)
        )

        host_devices = self.sql_client.exec_fetch_query(
            "SELECT * FROM devices WHERE id IN ("
            f"SELECT device_id FROM connections WHERE node_name = ?"
            ");",
            (node_name,)
        )

        if not host_devices:
            return []

        payload = []
        for dev in host_devices:
            device_info = {
                "dev_name": dev[5],
                "status": "active",
                "dev_port": dev[2],
                "type": dev[3],
                "mode": dev[4],
                "dev_capacity": round((dev[1] / 1000000000), 2)
            }
            payload.append(device_info)
        return payload

    def host_devices(self) -> List[Dict]:
        """
        Returns all attached devices, direct or remote, of a given host

        Input host is given directly as part of request args
        """
        request_data = request.get_json()
        host = request_data["host"]

        # check if default selection
        if host == 'Select Host':
            return []

        return self.get_host_devices_from_db(host)

    def create_cluster(self):
        pass

    def delete_cluster(self):
        pass

    def available_remote_devices(self) -> List[str]:
        """
        Returns all available CMMB devices (not currently attached)
        """
        payload = self.sql_client.exec_fetch_query(
            "SELECT name FROM devices WHERE mode = 'remote' and id NOT IN "
            "(SELECT device_id FROM connections WHERE device_id NOT NULL)",
            tuple()
        )
        return payload

    def get_remote_node_client_req_args(self, hostname, dev_name):
        node_name = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT node_name FROM hosts WHERE hostname = ?",
            (hostname,)
        )
        cluster_name = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT cluster_name FROM connections WHERE node_name = ?",
            (node_name,)
        )
        host_id = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT remote_id FROM hosts WHERE hostname = ?",
            (hostname,)
        )
        dev_id = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT id FROM devices WHERE name = ?",
            (dev_name,)
        )

        self.logger.info(
            f"node_name: {node_name}"
            f"cluster_name: {cluster_name}"
            f"host_id: {host_id}"
            f"dev_id: {dev_id}"
        )
        return node_name, cluster_name, host_id, dev_id

    def detach_remote_device(self) -> List[Dict]:
        """
        Performs Detach Operation and returns all associated
        devices with the host along with the device metadata
        """
        request_data = request.get_json()
        hostname = request_data["host_name"]
        dev_name = request_data["dev_name"]

        node_name, cluster_name, host_id, dev_id = (
            self.get_remote_node_client_req_args(hostname, dev_name)
        )

        # validate request args
        if any(
                arg is None for arg in
                [node_name, cluster_name, host_id, dev_id]
                ):
            self.logger.critical("Empty request args for detach operation")
            return self.get_host_devices_from_db(hostname)

        detached_success = self.remote_node_client.detach_device(
            node_name, cluster_name, host_id, dev_id
        )

        if detached_success:
            # detach successful, remove connection
            self._remove_connection(cluster_name, node_name, dev_id)
            # return updated attached host devices
            return self.get_host_devices_from_db(hostname)
        self.logger.critical("Detach operation failed")
        return self.get_host_devices_from_db(hostname)

    def attach_remote_device(self) -> List[Dict]:
        """
        Performs Detach Operation and returns all associated
        devices with the host along with the device metadata
        """
        request_data = request.get_json()
        hostname = request_data["host_name"]
        dev_name = request_data["dev_name"]

        node_name, cluster_name, host_id, dev_id = (
            self.get_remote_node_client_req_args(hostname, dev_name)
        )

        # validate request args
        if any(
                arg is None for arg in
                [node_name, cluster_name, host_id, dev_id]
                ):
            self.logger.critical("Empty request args for attach operation")
            return self.get_host_devices_from_db(hostname)

        attached_success = self.remote_node_client.attach_device(
            node_name, cluster_name, host_id, dev_id
        )

        if attached_success:
            # attach successful, add connection
            self._add_connection(cluster_name, node_name, dev_id)
            # return updated attached host devices
            return self.get_host_devices_from_db(hostname)
        self.logger.critical("Attach operation failed")
        return self.get_host_devices_from_db(hostname)

    def get_metrics(self) -> List:
        """
        Given the input host and metric request in the request arguments,
        returns several data points in the expected format for SCMC to
        render on a corresponding graph
        """
        metric_type = ""
        host = None
        try:
            request_data = request.get_json()
            metric_type = request_data["metric_type"]
            host = request_data.get("host", None)
        except Exception:
            print("Failed to get input request data")
        if host and host != "":
            self.influx_client.selected_host = host
            self.influx_client.filter = True

        payload = self.cognos_metric_functions.get(
            metric_type,
            helper.create_empty_response
        )()
        return payload
