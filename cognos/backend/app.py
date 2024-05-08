# app.py
from collections import namedtuple
from flask import Flask, request, jsonify
import json
import mysql.connector
import os
import requests
import socket
from flask_cors import CORS


current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(current_script_dir, 'config', 'config.json')
CONFIGS = ''
try:
    with open(CONFIG_FILE_PATH, 'r') as config_file:
        CONFIGS = json.load(config_file)
except Exception as error:
    raise RuntimeError(
        f"Unable to retrieve abstraction layer configs: {error}"
    )
AGENT_ENDPOINT = CONFIGS['agent_endpoint']
# TODO: support multiple Node Servers / Agents at scale
global NODE_ENDPOINT
NODE_ENDPOINT = CONFIGS['node_endpoint']


def get_db_passwd():
    db_pass = ''
    try:
        with open(CONFIG_FILE_PATH, 'r') as config_file:
            db_pass = json.load(config_file)
            if not db_pass:
                raise RuntimeError(
                    f"Unable to retrieve mysql db password: {error}"
                )
    except Exception as error:
        raise RuntimeError(f"Unable to retrieve mysql db password: {error}")
    return db_pass['mysql_db_dev_passwd']


def prepare_response_with_body(payload):
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


def connect_to_mysql():
    db = mysql.connector.connect(
        host="localhost",
        user="dev",
        passwd=get_db_passwd(),
        database="cognos"
    )
    cursor = db.cursor()
    return db, cursor


def disconnect_mysql(db):
    db.close()


def get_param_from_request_params(request_params, arg):
    for param in request_params:
        if param.startswith(arg):
            return param.split("=")[1]
    return None


def insert_hosts(payload):
    db, cursor = connect_to_mysql()

    for host in payload:
        insert_query = (
            "INSERT INTO hosts "
            "(id, name, mem_capacity, host_target_ports)"
            "VALUES (%s, %s, %s, %s)"
        )

        values = (
            host['id'], host['name'], host['mem_capacity'],
            ','.join([str(x) for x in host['host_target_ports']])
        )
        cursor.execute(insert_query, values)

        db.commit()

    disconnect_mysql(db)


def insert_devices(payload):
    db, cursor = connect_to_mysql()

    for device in payload:
        insert_query = (
            "INSERT INTO devices "
            "(dev_id, dev_capacity, dev_port,"
            " hosts_attached, status, type, mode)"
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )

        # TODO: extract status, type, and mode info
        # currently not available in SVK CXL Plugin
        values = (
            device['dev_id'], device['dev_capacity'], device['dev_port'],
            ','.join(device['hosts_attached']),
            'active', 'cmm-d', 'direct'
        )
        cursor.execute(insert_query, values)
        db.commit()

    disconnect_mysql(db)


def delete_connection(dev_id, host_id):
    db, cursor = connect_to_mysql()
    delete_query = (
        "DELETE FROM connections "
        "WHERE (dev_id=%s AND host_id=%s)"
    )
    values = (dev_id, host_id)
    cursor.execute(delete_query, values)
    db.commit()
    disconnect_mysql(db)


def fetch_topology():
    payload = []

    db, cursor = connect_to_mysql()
    cursor.execute(
        "SELECT DISTINCT(host_id) as host, GROUP_CONCAT(dev_id) as devices "
        "FROM connections GROUP BY 1;"
    )
    rows = cursor.fetchall()

    for row in rows:
        obj = {
            "host": row[0],
            "devices": row[1].split(',')
        }
        payload.append(obj)

    disconnect_mysql(db)
    return payload


def create_app():
    """ Implements endpoints of Flask App """
    app = Flask(__name__)
    CORS(app)
    app.config['CORS_HEADERS'] = 'Content-Type'

    # TODO: Optimize connection finding by consuming dev/host ids from STG API
    # currently not available on setupInfo STG API call
    @app.get("/init")
    def init():
        """
        Derives initial configuration and connections between devices
        """

        request_data = request.get_json()
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

        # Find mappings between hosts and devices
        dev_ports = set()
        devices = {}
        device_match = namedtuple("Match", "device host port")
        matches = []

        for device in payload['Devices']:
            dev_port = device["dev_port"]
            dev_name = device["dev_name"]
            dev_ports.add(dev_port)
            devices[dev_port] = dev_name

        for host in payload["Hosts"]:
            for endpt in host["endpoint"]:
                target_port = endpt["target"]
                host_name = host["host_name"]
                if target_port in dev_ports:
                    matches.append(device_match(devices[target_port],
                                                host_name, target_port))

        # TODO: get dev_ids and host_ids of paired devices
        # currently there exists no mapping between host/dev name and id
        # TODO: once dev_ids and host_ids available update connections table

        return jsonify(payload)

    @app.get("/topology")
    def get_topology():
        """
        Prior implementation - Example layout
        [
            { host: 'Host1',
            devices: [
                'D1',
                'D3',
                'D6'
            ]
            },{
            host: 'Host2',
            devices: [
                'D4'
            ]
            },{
            host: 'Host3',
            devices: [
                'D5'
            ]
            }
        ]
        """
        payload = fetch_topology()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.get("/hosts")
    def get_hosts():
        request_data = request.get_json()
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(AGENT_ENDPOINT, json=request_data,
                                 headers=headers)
        payload = (
            json.loads(response.json()['output'])
            [NODE_ENDPOINT]
            ['hosts']
        )
        insert_hosts(payload)

        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.get("/device_status")
    def get_device_status():
        # TODO: currently not implemented on SVK CXL Plugin end
        return jsonify({'status': 200})

    @app.get("/devices")
    def get_devices():
        request_data = request.get_json()
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(AGENT_ENDPOINT, json=request_data,
                                 headers=headers)

        payload = (
            json.loads(response.json()['output'])
            [NODE_ENDPOINT]
            ["devices"]
        )

        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.get("/host_devices")
    def get_host_devices():
        # TODO: Populate connections table with dev/host ids from STG
        return jsonify({'status': 200})

    @app.delete("/detach_device")
    def detach_device():
        # TODO: Implement desired UI response
        request_data = request.get_json()
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

        # get dev, host ids from request params
        request_params = request_data["input"].split(";")
        dev_id = get_param_from_request_params(request_params, 'dev_id')
        host_id = get_param_from_request_params(request_params, 'host_id')

        # Update DB after detach operation
        delete_connection(int(dev_id), int(host_id))

        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.post("/attach_device")
    def attach_device():
        # TODO: Implement desired UI response
        request_data = request.get_json()
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

        # get dev, host ids from request params
        request_params = request_data["input"].split(";")
        dev_id = get_param_from_request_params(request_params, 'dev_id')
        host_id = get_param_from_request_params(request_params, 'host_id')

        # Update DB after attach operation
        db, cursor = connect_to_mysql()
        insert_query = (
            "INSERT INTO connections "
            "(membox_id, dev_id, host_id)"
            "VALUES (%s, %s, %s)"
        )
        default_membox_id = 1
        values = (default_membox_id, dev_id, host_id)
        cursor.execute(insert_query, values)
        db.commit()

        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        disconnect_mysql(db)
        return response

    @app.get("/api/v1/cxl/mb/info")
    def get_mb_info():
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
    return app
