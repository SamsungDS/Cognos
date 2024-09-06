from base_datasource import DataSource
from collections import defaultdict, namedtuple
from flask import request, jsonify
import json
import math
import os
import requests
import socket

import app
import helper


CONFIGS = helper.fetch_cognos_configs(
    os.path.dirname(os.path.abspath(__file__)),
    'config.json'
)
NODE_ENDPOINT = CONFIGS['node_endpoint']
AGENT_ENDPOINT = CONFIGS['agent_endpoint']


class CXLPlugin(DataSource):
    def init(self):
        payload = self.get_setup_info()
        return jsonify(payload)

    def get_topology(self):
        payload = app.fetch_topology()
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
        num_devices = 0
        num_hosts = 0
        for dev in payload:
            num_devices += 1
            num_hosts += 1 if dev['hosts_attached'] else 0
        total_capacity = 256 * num_devices
        used_capacity = 256 * num_hosts
        payload = [{
            "total_capacity": total_capacity,
            "used_capacity": used_capacity,
            "used_capacity_percentage": (
                math.floor((used_capacity/total_capacity) * 100)
            )
        }]
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def host_devices(self):
        request_data = request.get_json()
        host = request_data["host"]
        payload = app.get_host_attached_devices(host)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def available_devices(self):
        db, cursor = app.connect_to_mysql()
        query = (
            "SELECT dev_name FROM devices WHERE dev_name not in "
            "(SELECT dev_name FROM host_device_connections);"
        )
        cursor.execute(query)
        result = cursor.fetchall()
        app.disconnect_mysql(db)
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def detach_device(self):
        request_data = request.get_json()
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]
        dev_id = app.get_devid_from_name(dev_name)
        host_id = app.get_hostid_from_name(host_name)
        svk_api_input_arg = (
            "cluster_id=CLUST1;command=DetachMemory;"
            f"dev_id={dev_id};host_id={host_id};mode=direct"
        )
        body = {
            "input": svk_api_input_arg
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(AGENT_ENDPOINT, json=body,
                                 headers=headers)
        payload = (
            json.loads(response.json()['output'])
            [NODE_ENDPOINT]
        )

        if response.ok:
            # Update DB after detach operation
            app.delete_connection(int(dev_id), int(host_id))

        # Return response for host/attached-devices table
        payload = app.get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def attach_device(self):
        request_data = request.get_json()
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]
        dev_id = app.get_devid_from_name(dev_name)
        host_id = app.get_hostid_from_name(host_name)
        svk_api_input_arg = (
            "cluster_id=CLUST1;command=AttachMemory;"
            f"dev_id={dev_id};host_id={host_id};mode=direct"
        )
        request_data = {
            "input": svk_api_input_arg
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(AGENT_ENDPOINT, json=request_data,
                                 headers=headers)
        payload = (
            json.loads(response.json()['output'])
            [NODE_ENDPOINT]
        )

        if response.ok:
            # Update DB with new connection
            db, cursor = app.connect_to_mysql()
            insert_query = (
                "INSERT INTO host_device_connections "
                "(host_id, host_name, dev_id, dev_name)"
                "VALUES (%s, %s, %s, %s)"
            )
            values = (host_id, host_name, dev_id, dev_name)
            cursor.execute(insert_query, values)
            db.commit()
            app.disconnect_mysql(db)

        # Return response for host/attached-devices table
        payload = app.get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_mb_info(self):
        TB = 1024 * 1024 * 1024 * 1024
        GB = 1024 * 1024 * 1024
        mb_mgmt_ip = socket.gethostbyname(socket.gethostname())
        mb_info = {
            'data_ports': 15,
            'mgmt_ports': 1,
            'mgmt_ip': f'{mb_mgmt_ip}',
            'mgmt_port': 5000,
            'mgmt_port_type': 'PCIe',
            'mgmt_netmask': '255.255.254.0',
            'form_factor': '4U',
            'manufacturer': 'Samsung',
            'memory_size': f'{((256 * GB) * 6) / TB}T',
            'power_state': 'ON',
            'health': 'OK',
            'protocol_version': 2.0
        }
        response = jsonify(mb_info)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_setup_info(self):
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

        # TODO: replace json field with json from incoming request
        # no current notion of cluster_id
        response = requests.post(
            AGENT_ENDPOINT,
            json={"input": "cluster_id=CLUST1;command=SetupInfo"},
            headers=headers
        )

        payload = (
            json.loads(response.json()['output'])
            [NODE_ENDPOINT]
        )

        # Find mappings between hosts and devices
        dev_ports = set()
        devices = {}
        device_match = namedtuple("Match", "device host port")
        matches = []

        if 'Devices' in payload:
            for device in payload['Devices']:
                dev_port = device["dev_port"]
                dev_name = device["dev_name"]
                dev_ports.add(dev_port)
                devices[dev_port] = dev_name

        if 'Hosts' in payload:
            for host in payload["Hosts"]:
                for endpt in host["endpoint"]:
                    target_port = endpt["target"]
                    host_name = host["host_name"]
                    if target_port in dev_ports:
                        matches.append(device_match(devices[target_port],
                                                    host_name, target_port))
        return payload

    def get_devices_info(self):
        headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
        svk_api_input_arg = (
            "cluster_id=CLUST1;command=ListDevices;"
            "FM_id=203;FM_endpoint=samsung.com"
        )
        response = requests.post(
            AGENT_ENDPOINT,
            json={"input": svk_api_input_arg},
            headers=headers
        )

        if response.ok:
            payload = (
                json.loads(response.json()['output'])
                [NODE_ENDPOINT]
                ["devices"]
            )
        else:
            return app.failed_response("Failed to fetch device info from SVK")

        # convert bytes into GB & add device names
        for i in range(len(payload)):
            payload[i]["dev_capacity"] = (
                math.trunc(payload[i]["dev_capacity"] / (1024*1024*1024))
            )
            dev_id = payload[i]["dev_id"]
            payload[i]["dev_name"] = (
                app.get_devname_from_id(payload[i]["dev_id"])
            )
        return payload

    def get_hosts_info(self):
        headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
        }
        response = requests.post(
            AGENT_ENDPOINT,
            json={"input": "cluster_id=CLUST1;command=ListHosts"},
            headers=headers
        )
        if response.ok:
            payload = (
                json.loads(response.json()['output'])
                [NODE_ENDPOINT]
                ['hosts']
            )
            return payload
        else:
            return failed_response("Failed to retrieve hosts info from SVK")

    def setup_tables(self):
        # get setup info
        init_payload = self.get_setup_info()
        dev_port_name_map = defaultdict()
        devport_hostname_map = defaultdict()

        for device in init_payload["Devices"]:
            dev_port_name_map[device["dev_port"]] = device["dev_name"]

        for host in init_payload["Hosts"]:
            for endpt in host["endpoint"]:
                devport_hostname_map[endpt["target"]] = host["host_name"]

        # get device info
        devices_payload = self.get_devices_info()
        for i in range(len(devices_payload)):
            dev_name = dev_port_name_map[devices_payload[i]["dev_port"]]
            devices_payload[i]["dev_name"] = dev_name
        app.insert_devices(devices_payload)

        # get hosts info
        hosts_payload = self.get_hosts_info()
        app.insert_hosts(hosts_payload)

        # store connections
        for dev_port, host_name in devport_hostname_map.items():
            dev_id, dev_name = (
                app.get_deviceid_and_devicename_from_port(dev_port)
            )
            host_id = app.get_hostid_from_name(host_name)
            app.insert_connection(host_id, host_name, dev_id, dev_name)
