from collections import defaultdict, namedtuple
from flask import request, jsonify
import json
import math
import os
import requests
import socket

from cognos.backend.base_datasource import DataSource
from cognos.backend.helper import (
    fetch_cognos_configs, process_membox_capacity_payload,
    get_available_devices_fromdb, get_dummy_mb_info, get_devport_name_map,
    get_devport_hostname_map, init_devices_table, init_hosts_table,
    init_connections_table, fetch_topology, get_host_attached_devices,
    get_devid_from_name, get_hostid_from_name, delete_connection,
    connect_to_mysql, disconnect_mysql, failed_response, get_devname_from_id,
    parse_svkcxlplugin_response, gen_svkcxlplugin_request_params,
    update_device_attached_hosts, remove_device_attached_host,
    update_metrics_host_filter_table
)


CONFIGS = fetch_cognos_configs(
    os.path.dirname(os.path.abspath(__file__)),
    'config.json'
)
NODE_ENDPOINT = CONFIGS['node_endpoint']
AGENT_ENDPOINT = CONFIGS['agent_endpoint']


class CXLPlugin(DataSource):
    def init(self):
        payload = self.get_setup_info()
        return jsonify(payload)

    def update_metrics_host_filter(self):
        request_data = request.get_json()
        host = request_data["host"]["value"]
        update_metrics_host_filter_table(host)
        print("update_metrics_host_filter host: ", host)
        payload = {'status': 200}
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_topology(self):
        payload = fetch_topology()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_hosts(self):
        payload = self.get_hosts_info()
        hosts = []
        for host in payload:
            data = {
                "value": host['name'],
                "label": host['name']
            }
            hosts.append(data)
        response = jsonify(hosts)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def post_devices(self):
        payload = self.get_devices_info()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def membox_capacity(self):
        payload = self.get_devices_info()
        response = jsonify(process_membox_capacity_payload(payload))
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def host_devices(self):
        request_data = request.get_json()
        host = request_data["host"]
        payload = get_host_attached_devices(host)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def available_devices(self):
        response = jsonify(get_available_devices_fromdb())
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def detach_device(self, mock_request=False, mock_request_data=None):
        request_data = {}
        if not mock_request:
            request_data = request.get_json()
        elif mock_request_data:
            request_data = mock_request_data
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]

        dev_id = get_devid_from_name(dev_name)
        host_id = get_hostid_from_name(host_name)
        feature_params = (
            "cluster_id=CL_ID_1;command=DetachMemory;"
            f"dev_id={dev_id};host_id={host_id};mode=direct"
        )
        body = gen_svkcxlplugin_request_params(feature_params)
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(AGENT_ENDPOINT, json=body,
                                 headers=headers)
        payload = parse_svkcxlplugin_response(response)

        if response.ok:
            # Update DB after detach operation
            delete_connection(int(dev_id), int(host_id))
            # remove attached host from device
            remove_device_attached_host(dev_id, host_name)

        # Return response for host/attached-devices table
        payload = get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def attach_device(self, mock_request=False, mock_request_data=None):
        request_data = {}
        if not mock_request:
            request_data = request.get_json()
        elif mock_request_data:
            request_data = mock_request_data
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]
        dev_id = get_devid_from_name(dev_name)
        host_id = get_hostid_from_name(host_name)
        feature_params = (
            "cluster_id=CL_ID_1;command=AttachMemory;"
            f"dev_id={dev_id};host_id={host_id};mode=direct"
        )
        body = gen_svkcxlplugin_request_params(feature_params)
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(AGENT_ENDPOINT, json=body,
                                 headers=headers)
        payload = parse_svkcxlplugin_response(response)

        if response.ok:
            # Update DB with new connection
            db, cursor = connect_to_mysql()
            insert_query = (
                "INSERT INTO host_device_connections "
                "(host_id, host_name, dev_id, dev_name)"
                "VALUES (%s, %s, %s, %s)"
            )
            values = (host_id, host_name, dev_id, dev_name)
            cursor.execute(insert_query, values)
            db.commit()
            disconnect_mysql(db)
            # add attached host to device
            update_device_attached_hosts(dev_id, host_name)

        # Return response for host/attached-devices table
        payload = get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_mb_info(self):
        response = jsonify(get_dummy_mb_info())
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_setup_info(self):
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

        # TODO: replace json field with json from incoming request
        # no current notion of cluster_id
        feature_params = "cluster_id=CL_ID_1;command=SetupInfo"
        body = gen_svkcxlplugin_request_params(feature_params)
        response = requests.post(
            AGENT_ENDPOINT,
            json=body,
            headers=headers
        )

        payload = parse_svkcxlplugin_response(response)
        return payload

    def get_devices_info(self):
        headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
        feature_params = (
            "cluster_id=CL_ID_1;command=ListDevices;"
            "FM_id=203;FM_endpoint=samsung.com"
        )
        body = gen_svkcxlplugin_request_params(feature_params)
        response = requests.post(
            AGENT_ENDPOINT,
            json=body,
            headers=headers
        )

        if response.ok:
            payload = parse_svkcxlplugin_response(response)["devices"]
        else:
            return failed_response("Failed to fetch device info from SVK")

        # convert bytes into GB & add device names
        for i in range(len(payload)):
            payload[i]["dev_capacity"] = (
                math.trunc(payload[i]["dev_capacity"] / (1024*1024*1024))
            )
            dev_id = payload[i]["dev_id"]
            payload[i]["dev_name"] = (
                get_devname_from_id(payload[i]["dev_id"])
            )
        return payload

    def get_hosts_info(self):
        headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
        }
        feature_params = "cluster_id=CL_ID_1;command=ListHosts"
        body = gen_svkcxlplugin_request_params(feature_params)
        response = requests.post(
            AGENT_ENDPOINT,
            json=body,
            headers=headers
        )
        if response.ok:
            payload = parse_svkcxlplugin_response(response)['hosts']
            return payload
        else:
            return failed_response(
                "Failed to retrieve hosts info from SVK"
            )

    def setup_tables(self):
        # get setup info
        init_payload = self.get_setup_info()
        dev_port_name_map = (
            get_devport_name_map(init_payload["Devices"])
        )
        devport_hostname_map = (
            get_devport_hostname_map(init_payload["Hosts"])
        )

        # get device info
        devices_payload = self.get_devices_info()
        init_devices_table(devices_payload, dev_port_name_map)

        # get hosts info
        hosts_payload = self.get_hosts_info()
        init_hosts_table(hosts_payload)

        # store connections
        init_connections_table(devport_hostname_map)
