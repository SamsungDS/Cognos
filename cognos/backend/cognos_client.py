import json
import math
import os
import requests
import socket
import sys
import time
import threading
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

current_script_dir = os.path.dirname(os.path.abspath(__file__))
NUMA_CONFIGS = helper.fetch_cognos_configs(
    current_script_dir,
    "numa_config.json"
)

get_stats_workers = {}  # { pid: thread }


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
            "node_bandwidth": self.influx_client.get_node_bandwidth,
            "devices_count": self.influx_client.get_hostview_devices_count,
            "hostview_bandwidth": self.influx_client.get_hostview_bandwidth,
            "hostview_usage": self.influx_client.get_hostview_usage,
            "hostview_capacity": self.influx_client.get_hostview_capacity,
            "hostview_devices_count": (
                self.influx_client.get_hostview_devices_count
            )
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
                data = json.loads(response.json()['command_response'])
                return (
                    [
                        v for cluster in data["clusters"]
                        for v in cluster.values()
                    ]
                )
            except Exception as error:
                print(f"Failed to parse ListClusters from controller")
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
        return json.loads(data['command_response'])

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
                data = json.loads(response.json()['command_response'])
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
        cluster = ""
        try:
            request_data = request.get_json()
            metric_type = request_data["metric_type"]
            if "cluster" in request_data:
                cluster = request_data["cluster"]
            host = request_data.get("host", None)
        except Exception:
            print("Failed to get input request data")
        if host and host != "":
            self.influx_client.selected_host = host
            self.influx_client.filter = True

        metrics_fn = self.cognos_metric_functions.get(metric_type, None)
        payload = (
            metrics_fn(cluster=cluster)
            if metrics_fn
            else helper.create_empty_payload()
        )
        return payload

    def get_events(self):
        return self.influx_client.get_cognos_events_past(720)

    def get_device_stats(self) -> List:
        try:
            request_data = request.get_json()
            device_id = request_data["device_id"]
            stat_key = request_data["stat_key"]
            if not device_id or not stat_key:
                raise ValueError(
                    "Failed to get input request data "
                    "/device_stats"
                )
            return self.influx_client.get_cognos_device_stats(
                1,
                device_id,
                stat_key,
            )
        except Exception as error:
            print(f"Failure in processing/device_stats request: {str(error)}")

    def get_data_moved_percentage(self, app_pid, app_name):
        self.logger.info("GETTING CME STATS -------------")

        node_name = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT server_name FROM applications WHERE app_pid = ?",
            (app_pid,)
        )

        cluster_name = self.sql_client.exec_fetch_singlerecord_query(
            "SELECT cluster_name FROM connections "
            "WHERE node_name = ? AND device_id = NULL",
            (node_name,)
        )

        request_url = (
            COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_prefix"] +
            node_name +
            COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_suffix"]
        )

        command_params = json.dumps({
            "app": app_name,
            "app_pid": str(app_pid),
        })

        request_args = {
            "cluster_name": cluster_name,
            "command_name": "get_stats",
            "command_params": command_params
        }

        # add delay to reduce frequency of calling GET STATS
        time.sleep(15)

        response = requests.post(
            request_url,
            json=request_args,
            headers=self.headers
        )
        if response.ok:
            self.logger.info("GET STATS CALL SUCCESSFUL")
            self.logger.info(f"RESPONSE CODE: {response.status_code}")
        else:
            self.logger.info("GET STATS CALL FAILED")
            self.logger.info(f"RESPONSE CODE: {response.status_code}")
            self.logger.info(f"RESPONSE TEXT: {response.text}")

        response_data = response.json()
        self.logger.info(f"RESPONSE DATA: {response_data}")
        if (
            not response_data["response"]
            or response_data["response"] == ["-22"]
        ):
            self.logger.info("NO ACTIVE DATA MOVEMENT")
            return "0"
        else:
            self.logger.info("--------- DATA BEING MOVED! ----------")
            try:
                x = float(json.loads(
                    response_data["response"][0])['observations']['%_moved']
                )
                percent_moved = (round(x, 4))
                percent_moved_string = str(percent_moved)  # + '%'
                self.logger.info(f" % PERCENT MOVED {percent_moved_string}")

                if percent_moved_string:
                    self.sql_client.execute_query(
                        "UPDATE applications "
                        f"SET data_moved = '{percent_moved_string}' "
                        f"WHERE app_pid = {app_pid};"
                    )

                return percent_moved_string
            except Exception as error:
                self.logger.error(f"failed to parse get stats: {str(error)}")
                return None

    def get_applications(self):
        # Loop for all active applications
        running_apps = self.sql_client.exec_fetch_query(
            "SELECT app_pid, app_name FROM applications;",
            tuple()
        )

        # update the status and msg fields with latest event
        for app in running_apps:
            app_pid = app[0]
            app_name = app[1]

            app_event = (
                self.influx_client.get_latest_application_event(app_pid)
            )

            app_status = self.sql_client.exec_fetch_singlerecord_query(
                "SELECT status FROM applications WHERE app_pid = ?",
                (app_pid,)
            )

            app_message = self.sql_client.exec_fetch_singlerecord_query(
                "SELECT message FROM applications WHERE app_pid = ?",
                (app_pid,)
            )

            if app_status == "degraded" or app_status == "device_degraded":
                # create get stats thread
                task = get_stats_workers.get(app_pid)

                if (not task) or (not task.is_alive()):
                    thread = threading.Thread(
                        target=self.get_data_moved_percentage,
                        args=(app_pid, app_name,)
                    )
                    thread.daemon = True
                    get_stats_workers[app_pid] = thread
                    thread.start()

            if app_event:
                updated_status = (
                    'good' if app_event[0]['severity']
                    in ["good", "Normal", "normal"]
                    else app_event[0]['severity']
                )

                if updated_status == "degraded" and (
                    app_message and "sla"
                    in app_message.lower()
                ):
                    updated_status = "device_degraded"

                updated_msg = app_event[0]['msg']

                self.sql_client.execute_query(
                    "UPDATE applications "
                    f"SET status = '{updated_status}', "
                    f"message = '{updated_msg}' "
                    f"WHERE app_pid = {app_pid};"
                )

        # get apps from DB
        data = self.sql_client.exec_fetch_query(
            "SELECT app_name, app_pid, server_name, throughput_ops_per_sec, "
            "targetread_p99_latency, targetwrite_p99_latency, status, "
            "message, data_moved FROM applications ",
            tuple()
        )
        apps = []
        for x in data:
            app = helper.App(
                app_name=x[0],
                app_pid=x[1],
                server_name=x[2],
                throughput_ops_per_sec=x[3],
                targetread_p99_latency=x[4],
                targetwrite_p99_latency=x[5],
                status=x[6],
                message=x[7],
                data_moved=x[8]
            )
            apps.append(app.to_dict())

        return apps

    def insert_application(self, app):
        app_name = app["app_name"]
        app_pid = app["app_pid"]
        server_name = app["server_name"]
        throughput_ops_per_sec = app["throughput_ops_per_sec"]
        targetread_p99_latency = app["targetread_p99_latency"]
        targetwrite_p99_latency = app["targetwrite_p99_latency"]
        status = app["status"]
        message = app["message"]
        data_moved = app["data_moved"]

        self.sql_client.execute_query(
            "INSERT INTO applications "
            "(app_name, app_pid, server_name, throughput_ops_per_sec, "
            "targetread_p99_latency, targetwrite_p99_latency, status, "
            "message, data_moved) "
            f"VALUES ('{app_name}', {app_pid}, '{server_name}', "
            f"{throughput_ops_per_sec}, {targetread_p99_latency}, "
            f"{targetwrite_p99_latency}, '{status}', '{message}', "
            f"'{data_moved}')"
        )

    def set_app_sla(self):
        """
        {
            "app_name": <app_name>,
            "app_pid": <app_pid>,
            "server_name": <server_name>,
            "avg_latency_ns": <avg_latency_ns>,
            "throughput_ops_per_sec": <throughput_ops_per_sec>,
            "targetread_p99_latency": <targetread_p99_latency>,
            "targetwrite_p99_latency": <targetwrite_p99_latency>
        }
        """
        try:
            request_data = request.get_json()
            app_name = request_data["app_name"]
            app_pid = request_data["app_pid"]
            server_name = request_data["server_name"]
            avg_latency_ns = request_data["avg_latency_ns"]
            throughput_ops_per_sec = request_data["throughput_ops_per_sec"]
            targetread_p99_latency = request_data["targetread_p99_latency"]
            targetwrite_p99_latency = request_data["targetwrite_p99_latency"]

            # get cluster of node
            data = self.sql_client.exec_fetch_query(
                "SELECT node_name, cluster_name FROM connections ",
                tuple()
            )

            cluster_name = ""
            for pair in data:
                if server_name == pair[0]:
                    cluster_name = pair[1]
            # TODO: add check if cluster name is empty

            numa_nodes = NUMA_CONFIGS[server_name][str(app_pid)]

            device_numa_nodes = []
            for numa in numa_nodes:
                # TODO: make DRAM / CXL nodes as part of config or
                # dynamically determine through get_device_info call
                # or use py-libnuma

                # dram numa nodes
                if numa < 2:
                    device_numa_nodes.append({"device_numa": str(numa)})
                else:
                    device_numa_nodes.append(
                        {"device_numa": str(numa),
                         "device_allocated_capacity_mb": 600000}
                    )

            command_params = json.dumps({
                "app_name": app_name,
                "app_pid": app_pid,
                "app_desired_qos": {
                    "avg_latency_ns": avg_latency_ns
                },
                "devices": device_numa_nodes
            })
            request_args = {
                "command_name": "set_app_sla",
                "cluster_name": cluster_name,
                "node_name": server_name,
                "command_params": command_params
            }
            response = requests.post(
                COGNOS_NORTHBOUND_ENDPOINTS["sla"],
                json=request_args,
                headers=self.headers
            )
            if response.ok:
                # create record for application
                app = helper.App(
                    app_name=app_name,
                    app_pid=app_pid,
                    server_name=server_name,
                    throughput_ops_per_sec=throughput_ops_per_sec,
                    targetread_p99_latency=targetread_p99_latency,
                    targetwrite_p99_latency=targetwrite_p99_latency,
                    status="good",
                    message="",
                    data_moved="0"
                )

                self.insert_application(app.to_dict())

                # send payload back of all registered applications
                return self.get_applications()
            else:
                self.logger.error("SLA CALL FAILED")
                self.logger.error(f"SLA ERROR: {response.status_code}")
                self.logger.error(f"SLA TEXT: {response.text}")
        except Exception as error:
            self.logger.error(f"Failed to set app sla {str(error)}")

    def move(self):
        try:
            status = ""
            request_data = request.get_json()
            cluster = request_data["cluster"]
            node = request_data["node"]
            app = request_data["app"]
            app_pid = request_data["app_pid"]
            tm_attr = request_data["tm_attr"]
            slow_tier = request_data["slow_tier"]
            fast_tier = request_data["fast_tier"]

            if all([app, app_pid, tm_attr, slow_tier, fast_tier, cluster,
                    node]):
                request_url = (
                    COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_prefix"] +
                    node +
                    COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_suffix"]
                )

                command_params = json.dumps({
                    "app": app,
                    "app_pid": str(app_pid),
                    "tm_attr": tm_attr,
                    "slow_tier": slow_tier,
                    "fast_tier": fast_tier
                })

                request_args = {
                    "cluster_name": cluster,
                    "command_name": "move",
                    "command_params": command_params
                }

                response = requests.post(
                    request_url,
                    json=request_args,
                    headers=self.headers
                )
                if response.ok:
                    response_data = response.json()
                    status = "move successful" if response_data["response"] == ["0"] else "move failed"
                else:
                    status = "failed request"
                return {
                    "status": status
                }

        except Exception as error:
            self.logger.error(f"failed move request: {str(error)}")
            return {
                "status": "request error"
            }

    def move_all(self):
        try:
            status = ""
            request_data = request.get_json()
            cluster = request_data["cluster"]
            node = request_data["node"]
            app = request_data["app"]
            app_pid = request_data["app_pid"]
            tm_attr = request_data["tm_attr"]
            src = request_data["src"]
            dst = request_data["dst"]

            if all([app, app_pid, tm_attr, src, dst, cluster, node]):
                request_url = (
                    COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_prefix"] +
                    node +
                    COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_suffix"]
                )

                command_params = json.dumps({
                    "app": app,
                    "app_pid": str(app_pid),
                    "tm_attr": tm_attr,
                    "src": src,
                    "dst": dst
                })

                request_args = {
                    "cluster_name": cluster,
                    "command_name": "move_all",
                    "command_params": command_params
                }

                response = requests.post(
                    request_url,
                    json=request_args,
                    headers=self.headers
                )
                if response.ok:
                    response_data = response.json()
                    status = "move_all successful" if response_data["response"] == ["0"] else "move_all failed"
                else:
                    status = "failed request"
                return {
                    "status": status
                }

        except Exception as error:
            self.logger.error(f"failed move_all request: {str(error)}")
            return {
                "status": "request error"
            }

    def get_move_stats(self):
        try:
            status = ""
            request_data = request.get_json()
            cluster = request_data["cluster"]
            node = request_data["node"]
            app = request_data["app"]
            app_pid = request_data["app_pid"]

            if all([app, app_pid, cluster, node]):
                request_url = (
                    COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_prefix"] +
                    node +
                    COGNOS_NORTHBOUND_ENDPOINTS["get_cme_stats_suffix"]
                )

                command_params = json.dumps({
                    "app": app,
                    "app_pid": str(app_pid)
                })

                request_args = {
                    "cluster_name": cluster,
                    "command_name": "get_stats",
                    "command_params": command_params
                }

                response = requests.post(
                    request_url,
                    json=request_args,
                    headers=self.headers
                )
                if response.ok:
                    try:
                        response_data = response.json()
                        x = float(json.loads(
                            response_data["response"][0])
                            ['observations']['%_moved']
                        )
                        percent_moved = (round(x, 4))
                        percent_moved_string = str(percent_moved)
                        status = f"DATA MOVED: {percent_moved_string}%"
                    except Exception as error:
                        self.logger.error("FAILED TO PARSE GET STATS RESPONSE")
                else:
                    status = "failed request"
                return {
                    "status": status
                }

        except Exception as error:
            self.logger.error(f"failed get_move_stats request: {str(error)}")
            return {
                "status": "request error"
            }

    def valid_move_configs(self, op, configs):
        move_keys = (
            ["cluster", "node", "app", "app_pid", "tm_attr",
             "slow_tier", "fast_tier"]
        )
        move_all_keys = (
            ["cluster", "node", "app", "app_pid", "tm_attr", "src", "dst"]
        )
        get_stats_keys = (
            ["cluster", "node", "app", "app_pid"]
        )

        if op == "move":
            for k in move_keys:
                if k not in configs:
                    return False
        elif op == "move_all":
            for k in move_all_keys:
                if k not in configs:
                    return False
        elif op == "get_move_stats":
            for k in get_stats_keys:
                if k not in configs:
                    return False

        return True

    def valid_tm_attrs(self, op, attr):
        move_tm_attrs = [
            "MOVER_AGGRESSIVENESS_LOW",
            "MOVER_AGGRESSIVENESS_HIGH",
        ]
        move_all_tm_attrs = [
            "0"
        ]

        if op == "move" and attr in move_tm_attrs:
            return True
        elif op == "move_all" and attr in move_all_tm_attrs:
            return True
        else:
            return False
