from collections import defaultdict, namedtuple
from flask import request, jsonify
from db_query_constants import APPLICATION_JSON
import json
import math
import os
import requests
import socket
from typing import Callable, List, Dict
from cognos.backend.base_datasource import DataSource
import cognos.backend.helper as helper


CONFIGS = helper.fetch_cognos_configs(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)
NODE_ENDPOINT = CONFIGS["node_endpoint"]
AGENT_ENDPOINT = CONFIGS["agent_endpoint"]
LIST_CLUSTER_EP = CONFIGS["list_cluster_ep"]


class CXLPlugin(DataSource):

    def init(self):
        super().__init__()
        payload = self.get_setup_info()
        return jsonify(payload)

    def get_scmc_version(self):
        scmc_version_file = helper.get_scmc_version_file()
        if scmc_version_file:
            try:
                with open(scmc_version_file, "r") as v:
                    API_VERSION = v.read().strip()
                    response = jsonify({"version": API_VERSION})
                    response.status_code = 200
                    return response
            except Exception as error:
                raise RuntimeError(
                    f"Unable to retrieve API version: {str(error)}"
                )
        else:
            response = jsonify({"error": "version file not found"})
            response.status_code = 404
            return response

    def update_metrics_host_filter(self):
        request_data = request.get_json()
        host = request_data["host"]["value"]
        helper.update_metrics_host_filter_table(host)
        payload = {"status": 200}
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_topology(self):
        payload = helper.fetch_topology()
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_hosts(self):
        payload = self.aggregate_info(self.get_hosts_info, "id")
        hosts = []
        for host in payload:
            data = {"value": host["name"], "label": host["name"]}
            hosts.append(data)
        response = jsonify(hosts)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def post_devices(self):
        payload = self.aggregate_info(self.get_devices_info, "dev_id")
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def membox_capacity(self):
        payload = self.get_devices_info("", "")
        response = jsonify(helper.process_membox_capacity_payload(payload))
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def host_devices(self):
        request_data = request.get_json()
        host = request_data["host"]
        payload = helper.get_host_attached_devices(host)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def available_devices(self):
        response = jsonify(helper.get_available_devices_fromdb())
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def detach_device(
        self, mock_request=False, mock_request_data=None, fp=None
    ):
        request_data = {}
        if not mock_request:
            request_data = request.get_json()
        elif mock_request_data:
            request_data = mock_request_data

        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]

        dev_id = helper.get_devid_from_name(dev_name)
        host_id = helper.get_hostid_from_name(host_name)

        feature_params = (
            "cluster_id=CL_ID_1;command=DetachMemory;"
            f"dev_id={dev_id};host_id={host_id};mode=direct"
        )

        body = helper.gen_svkcxlplugin_request_params(
            feature_params, mock_request, fp
        )

        headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }

        clust_nodes = self.get_node_info()
        dropped = False
        for _, node_id in clust_nodes:
            body["node_id"] = node_id
            response = requests.post(
                AGENT_ENDPOINT, json=body, headers=headers
            )
            payload = helper.parse_svkcxlplugin_response(response)

            if response.ok and not dropped:
                # Update DB after detach operation
                helper.delete_connection(int(dev_id), int(host_id))
                # remove attached host from device
                helper.remove_device_attached_host(dev_id, host_name)
                dropped = True

        # Return response for host/attached-devices table
        payload = helper.get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def attach_device(self, mock_request=False, mock_request_data=None):
        request_data = {}
        if not mock_request:
            request_data = request.get_json()
        elif mock_request_data:
            request_data = mock_request_data
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]
        dev_id = helper.get_devid_from_name(dev_name)
        host_id = helper.get_hostid_from_name(host_name)
        feature_params = (
            "cluster_id=CL_ID_1;command=AttachMemory;"
            f"dev_id={dev_id};host_id={host_id};mode=direct"
        )
        body = helper.gen_svkcxlplugin_request_params(feature_params)
        headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }

        clust_nodes = self.get_node_info()
        for _, node_id in clust_nodes:
            body["node_id"] = node_id
            response = requests.post(
                AGENT_ENDPOINT, json=body, headers=headers
            )
            payload = helper.parse_svkcxlplugin_response(response)

            if response.ok and not mock_request:
                # Update DB with new connection
                db, cursor = helper.connect_to_mysql()
                insert_query = (
                    "INSERT IGNORE INTO host_device_connections "
                    "(host_id, host_name, dev_id, dev_name)"
                    "VALUES (%s, %s, %s, %s)"
                )
                values = (host_id, host_name, dev_id, dev_name)
                cursor.execute(insert_query, values)
                db.commit()
                helper.disconnect_mysql(db)
                # add attached host to device
                helper.update_device_attached_hosts(dev_id, host_name)

        # Return response for host/attached-devices table
        payload = helper.get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_mb_info(self):
        response = jsonify(helper.get_dummy_mb_info())
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_setup_info(self, cluster_id=None, node_id=None):
        headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }
        if cluster_id and node_id:
            feature_params = (
                f"cluster_id={cluster_id};node_id={node_id};command=SetupInfo"
            )
        else:
            feature_params = (
                "cluster_id=CL_ID_1;node_id=localhost;" "command=SetupInfo"
            )
        body = helper.gen_svkcxlplugin_request_params(feature_params)
        response = requests.post(AGENT_ENDPOINT, json=body, headers=headers)
        payload = helper.parse_svkcxlplugin_setup_response(response)
        return payload

    def get_devices_info(self, cluster_id, node_id):
        headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }
        if cluster_id and node_id:
            feature_params = f"cluster_id={cluster_id};node_id={node_id};"
        else:
            feature_params = "cluster_id=CL_ID_1;node_id=localhost"
        feature_params += (
            "command=ListDevices;FM_id=203;FM_endpoint=samsung.com"
        )
        # Generate request body and send the request
        body = helper.gen_svkcxlplugin_request_params(feature_params)
        response = requests.post(AGENT_ENDPOINT, json=body, headers=headers)
        # Check response status and handle errors
        if response.ok:
            payload = helper.parse_svkcxlplugin_response(response).get(
                "devices", []
            )
        else:
            # pragma: no cover
            return helper.failed_response(
                "Failed to fetch device info from SVK"
            )

        # Process device data by converting bytes to GB and adding device names
        for device in payload:
            # Convert capacity from bytes to GB
            device["dev_capacity"] = math.trunc(
                device["dev_capacity"] / (1024 * 1024 * 1024)
            )
            # Add device name based on device ID
            device["dev_name"] = helper.get_devname_from_id(device["dev_id"])

        return payload

    def get_hosts_info(self, cluster_id, node_id):
        headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }

        if cluster_id and node_id:
            feature_params = f"cluster_id={cluster_id};node_id={node_id};"
        else:
            feature_params = "cluster_id=CL_ID_1;node_id=localhost"
        feature_params += "command=ListHosts"

        body = helper.gen_svkcxlplugin_request_params(feature_params)
        response = requests.post(AGENT_ENDPOINT, json=body, headers=headers)
        if response.ok:
            payload = helper.parse_svkcxlplugin_response(response)["hosts"]
            return payload
        else:
            # pragma: no cover
            return helper.failed_response(
                "Failed to retrieve hosts info from SVK"
            )

    def setup_tables(self):
        for cluster_id in helper.get_clusters():
            node_info = self.get_cluster_nodes(cluster_id)[cluster_id]
            for node in node_info:
                node_id = node["nodeId"]
                print(f"node_id : {node_id}")
                # get setup info for the specific cluster and node
                payload = self.get_setup_info(cluster_id, node_id)
                for fm in payload:
                    dev_port_name_map = helper.get_devport_name_map(
                        fm["Devices"]
                    )
                    devport_hostname_map = helper.get_devport_hostname_map(
                        fm["Hosts"]
                    )

                    # get device info
                    devices_payload = helper.get_fm_devices_info(
                        fm["Devices"], devport_hostname_map
                    )
                    helper.init_devices_table(
                        devices_payload,
                        dev_port_name_map,
                        devport_hostname_map,
                        fm["type"],
                    )

                    # get hosts info
                    hosts_payload = helper.get_fm_host_info(fm["Hosts"])
                    helper.init_hosts_table(hosts_payload, fm["type"])
                    # store connections
                    helper.init_connections_table(devport_hostname_map)

    def get_cluster_nodes(self, cluster_id):
        headers = {
            "accept": APPLICATION_JSON,
            "Content-Type": APPLICATION_JSON,
        }

        feature_params = f"cluster_id={cluster_id};command=list_cluster_nodes"

        body = helper.gen_list_cluster_req_params(feature_params)
        response = requests.post(LIST_CLUSTER_EP, json=body, headers=headers)
        # Parse the response and extract cluster info for all clusters
        payload = response.json()
        all_node_info = self.parse_cluster_info(payload)

        return all_node_info

    def parse_cluster_info(self, payload, cluster_id=None):
        """
        Parses the cluster info from the response payload for the
        given cluster ID.
        Args:
            payload (dict): The JSON response payload.
            cluster_id (str, optional): The ID of the cluster to search for.
            If None, returns nodeInfo for all clusters.
        Returns:
            dict: A dictionary with cluster IDs as keys and node
                  information as values.If a specific cluster_id is
                  provided, returns the nodeInfo for that cluster only.
                  Returns an empty dict if no clusters match.
        """
        cluster_info = payload.get("clusterInfo", [])
        result = {}
        for cluster in cluster_info:
            current_cluster_id = cluster.get("clusterId")
            if cluster_id is None or current_cluster_id == cluster_id:
                result[current_cluster_id] = cluster.get("nodeInfo", [])
        # If a specific cluster_id was provided, return only its nodeInfo
        if cluster_id:
            return result.get(cluster_id, [])
        return result

    def get_node_info(self):
        nodes = []
        # @to-do Replace with a dynamic cluster ID list via API
        for cluster_id in helper.get_clusters():
            node_info = self.get_cluster_nodes(cluster_id).get(cluster_id, [])
            for node in node_info:
                node_id = node["nodeId"]
                nodes.append((cluster_id, node_id))
        return nodes

    def aggregate_info(
        self, function_name: Callable[[str, str], List[Dict]], key: str
    ) -> List[Dict]:
        result_d = {}
        nodes = self.get_node_info()
        for cluster_id, node_id in nodes:
            try:
                payload = function_name(cluster_id, node_id)
                for _dict in payload:
                    _id = _dict.get(key)
                    if not _id:
                        raise ValueError(
                            f"Missing key '{key}' in JSON object: {_dict}"
                        )
                    if _id not in result_d:
                        result_d[_id] = _dict
            except Exception as e:
                print(f"Error with cluster {cluster_id},node:{node_id}:{e}")
                continue
        return list(result_d.values())

    def get_all_hosts_info(self):

        try:
            # Call the helper function to get host information
            result = helper.get_all_hosts()
            if result is None:
                formatted_result = []
            else:
                formatted_result = [
                    {"value": host, "label": host}
                    for host in result["hostnames"]
                ]
            response = jsonify(formatted_result)
            response.status_code = 200
            response.headers.add("Access-Control-Allow-Origin", "*")
            return response
        except Exception as e:
            print(f"An error occurred in get_all_hosts_info: {e}")
            response = jsonify(
                {"error": "Failed to retrieve host information"}
            )
            response.status_code = 500
            return response
