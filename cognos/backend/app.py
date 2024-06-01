# app.py
from collections import defaultdict, namedtuple
from flask import Flask, request, jsonify
import json
import math
import mysql.connector
import os
import requests
import socket
from flask_cors import CORS


current_script_dir = os.path.dirname(os.path.abspath(__file__))

# get API version
VERSION_FILE_PATH = os.path.join(current_script_dir, 'VERSION')
API_VERSION = ''
try:
    with open(VERSION_FILE_PATH, 'r') as version_file:
        API_VERSION = version_file.read().strip()
except Exception as error:
    raise RuntimeError(
        f"Unable to retrieve API version: {str(error)}"
    )

# get configs
CONFIG_FILE_PATH = os.path.join(current_script_dir, 'config', 'config.json')
CONFIGS = ''
try:
    with open(CONFIG_FILE_PATH, 'r') as config_file:
        CONFIGS = json.load(config_file)
except Exception as error:
    raise RuntimeError(
        f"Unable to retrieve abstraction layer configs: {str(error)}"
    )
AGENT_ENDPOINT = CONFIGS['agent_endpoint']
# TODO: support multiple Node Servers / Agents at scale
global NODE_ENDPOINT
NODE_ENDPOINT = CONFIGS['node_endpoint']

COGNOS_TABLES = [
    "connections",
    "devices",
    "host_device_ids",
    "hosts",
    "mem_box",
    "host_device_connections"
]


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


def failed_response(msg):
    payload = {'status': 500, 'error': msg}
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


def connect_to_mysql():
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="dev",
            passwd=get_db_passwd(),
            database="cognos"
        )
        cursor = db.cursor()
        return db, cursor
    except Exception as error:
        print(f"Failed to connect to Cognos Mysql DB.. {str(error)}")


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
        try:
            insert_query = (
                "REPLACE INTO hosts "
                "(id, name, mem_capacity, host_target_ports)"
                "VALUES (%s, %s, %s, %s)"
            )

            values = (
                host['id'], host['name'], host['mem_capacity'],
                ','.join([str(x) for x in host['host_target_ports']])
            )
            cursor.execute(insert_query, values)
            db.commit()
        except Exception as error:
            print(f"Failed to insert into hosts table.. {str(error)}")

    disconnect_mysql(db)


def get_devices_from_db():
    db, cursor = connect_to_mysql()
    try:
        query = (
            "SELECT dev_capacity, dev_id, dev_port, "
            "hosts_attached FROM devices"
        )
        cursor.execute(query)
        rows = cursor.fetchall()

        payload = []
        for row in rows:
            obj = {
                "dev_capacity": row[0],
                "dev_id": row[1],
                "dev_port": row[2],
                "hosts_attached": row[3]
            }
            payload.append(obj)
        disconnect_mysql(db)
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")
    return payload


def insert_devices(payload):
    db, cursor = connect_to_mysql()

    for device in payload:
        try:
            insert_query = (
                "INSERT INTO devices "
                "(dev_id, dev_name, dev_capacity, dev_port,"
                " hosts_attached, status, type, mode)"
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )

            # TODO: extract status, type, and mode info
            # currently not available in SVK CXL Plugin

            values = (
                device['dev_id'], device['dev_name'],
                device['dev_capacity'],
                device['dev_port'], ','.join(device['hosts_attached']),
                'active', 'CMM-D', 'direct'
            )
            cursor.execute(insert_query, values)
            db.commit()
        except Exception as error:
            print(f"Failed insert into devices table.. {str(error)}")

    disconnect_mysql(db)


def insert_connection(host_id, host_name, dev_id, dev_name):
    db, cursor = connect_to_mysql()
    try:
        insert_query = (
            "INSERT INTO host_device_connections "
            "(host_id, host_name, dev_id, dev_name) "
            "VALUES (%s, %s, %s, %s)"
        )
        values = (host_id, host_name, dev_id, dev_name)
        cursor.execute(insert_query, values)
        db.commit()
    except Exception as error:
        print(f"Failed to insert into connections table.. {str(error)}")
    disconnect_mysql(db)


def delete_connection(dev_id, host_id):
    db, cursor = connect_to_mysql()
    try:
        delete_query = (
            "DELETE FROM host_device_connections "
            "WHERE (dev_id=%s AND host_id=%s)"
        )
        values = (dev_id, host_id)
        cursor.execute(delete_query, values)
        db.commit()
    except Exception as e:
        print(f"Failed to delete from host_devices_connections.. {str(e)}")
    disconnect_mysql(db)


def fetch_topology():
    payload = []

    db, cursor = connect_to_mysql()
    try:
        cursor.execute(
            "SELECT DISTINCT(host_name) as host, GROUP_CONCAT(dev_name) "
            "as devices FROM host_device_connections GROUP BY 1;"
        )
        rows = cursor.fetchall()
    except Exception as error:
        print(f"Failed to fetch topology from devices table.. {str(error)}")

    for row in rows:
        obj = {
            "host": row[0],
            "devices": row[1].split(',')
        }
        payload.append(obj)

    disconnect_mysql(db)
    return payload


def get_hostname_from_id(host_id):
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT name FROM hosts WHERE id=%s"
        values = [host_id]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from hosts table.. {str(error)}")
    disconnect_mysql(db)
    if row:
        return row[0]
    else:
        return ''


def get_devname_from_id(dev_id):
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT dev_name FROM devices WHERE dev_id=%s LIMIT 1;"
        values = [dev_id]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")
    disconnect_mysql(db)
    if row:
        return row[0]
    else:
        return ''


def get_hostid_from_name(name):
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT id FROM hosts WHERE name=%s"
        values = [name]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from hosts table.. {str(error)}")
    disconnect_mysql(db)
    if row:
        return row[0]
    else:
        return ''


def get_devid_from_name(dev_name):
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT dev_id FROM devices WHERE dev_name=%s"
        values = [dev_name]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")
    disconnect_mysql(db)
    if row:
        return row[0]
    else:
        return ''


def get_deviceid_and_devicename_from_port(port):
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT dev_id, dev_name FROM devices WHERE dev_port=%s"
        values = [port]
        cursor.execute(query, values)
        row = cursor.fetchone()
        if not row:
            return (0, '')
        dev_id, dev_name = row[0], row[1]
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")
    disconnect_mysql(db)
    return dev_id, dev_name


def get_setup_info():
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


def get_devices_info():
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

        # convert bytes into GB & add device names
        for i in range(len(payload)):
            payload[i]["dev_capacity"] = (
                math.trunc(payload[i]["dev_capacity"] / (1024*1024*1024))
            )
            dev_id = payload[i]["dev_id"]
            payload[i]["dev_name"] = get_devname_from_id(payload[i]["dev_id"])

        return payload
    else:
        return failed_response("Failed to fetch device info from SVK")


def get_hosts_info():
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


def get_host_attached_devices(host):
    db, cursor = connect_to_mysql()
    try:
        query = (
            "SELECT dev_name, status, dev_port, type, mode, dev_capacity "
            "FROM devices WHERE dev_id IN "
            "(SELECT dev_id FROM host_device_connections "
            f"WHERE host_name='{host}')"
        )
        cursor.execute(query)
        results = cursor.fetchall()
    except Exception as e:
        print(f"Failed to fetch device data for a specific host.. {str(e)}")
    disconnect_mysql(db)
    payload = []
    row = {}
    for x in results:
        row = {
            'dev_name': x[0], 'status': x[1], 'dev_port': x[2],
            'type': x[3], 'mode': x[4],
            'dev_capacity': x[5]
        }
        payload.append(row)
        row = {}
    return payload


def clear_all_tables():
    db, cursor = connect_to_mysql()
    for table in COGNOS_TABLES:
        try:
            delete_query = f"DELETE FROM {table};"
            cursor.execute(delete_query)
            db.commit()
        except Exception as error:
            print(f"Failed to delete from {table}.. {str(error)}")
    disconnect_mysql(db)


def setup_tables():
    # get setup info
    init_payload = get_setup_info()
    dev_port_name_map = defaultdict()
    devport_hostname_map = defaultdict()

    for device in init_payload["Devices"]:
        dev_port_name_map[device["dev_port"]] = device["dev_name"]

    for host in init_payload["Hosts"]:
        for endpt in host["endpoint"]:
            devport_hostname_map[endpt["target"]] = host["host_name"]

    # get device info
    devices_payload = get_devices_info()
    for i in range(len(devices_payload)):
        dev_name = dev_port_name_map[devices_payload[i]["dev_port"]]
        devices_payload[i]["dev_name"] = dev_name
    insert_devices(devices_payload)

    # get hosts info
    hosts_payload = get_hosts_info()
    insert_hosts(hosts_payload)

    # store connections
    for dev_port, host_name in devport_hostname_map.items():
        dev_id, dev_name = get_deviceid_and_devicename_from_port(dev_port)
        host_id = get_hostid_from_name(host_name)
        insert_connection(host_id, host_name, dev_id, dev_name)


def create_app():
    """ Implements endpoints of Flask App """
    app = Flask(__name__)
    CORS(app)
    app.config['CORS_HEADERS'] = 'Content-Type'

    # clear out existing tables
    clear_all_tables()

    @app.get(f"/api/{API_VERSION}/init")
    def init():
        """
        Derives initial configuration and connections between devices
        """
        payload = get_setup_info()
        return jsonify(payload)

    @app.get(f"/api/{API_VERSION}/topology")
    def get_topology():
        """
        Expected UI topology format - Example layout
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

    @app.get(f"/api/{API_VERSION}/hosts")
    def get_hosts():
        payload = get_hosts_info()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.get(f"/api/{API_VERSION}/device_status")
    def get_device_status():
        # TODO: currently not implemented on SVK CXL Plugin end
        return jsonify({'status': 200})

    @app.post(f"/api/{API_VERSION}/devices")
    def post_devices():
        payload = get_devices_info()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.post(f"/api/{API_VERSION}/host_devices")
    def host_devices():
        request_data = request.get_json()
        host = request_data["host"]
        payload = get_host_attached_devices(host)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.get(f"/api/{API_VERSION}/available_devices")
    def available_devices():
        db, cursor = connect_to_mysql()
        query = (
            "SELECT dev_name FROM devices WHERE dev_name not in "
            "(SELECT dev_name FROM host_device_connections);"
        )
        cursor.execute(query)
        result = cursor.fetchall()
        disconnect_mysql(db)
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.delete(f"/api/{API_VERSION}/detach_device")
    def detach_device():
        request_data = request.get_json()
        print(f"**** REQUEST DATA: {request_data}")
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]
        dev_id = get_devid_from_name(dev_name)
        host_id = get_hostid_from_name(host_name)
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
            delete_connection(int(dev_id), int(host_id))

        # Return response for host/attached-devices table
        payload = get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.post(f"/api/{API_VERSION}/attach_device")
    def attach_device():
        request_data = request.get_json()

        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"]
        dev_id = get_devid_from_name(dev_name)
        host_id = get_hostid_from_name(host_name)
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

        # Return response for host/attached-devices table
        payload = get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    @app.get(f"/api/{API_VERSION}/cxl/mb/info")
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

    # setup database tables based on current state during initial boot
    setup_tables()
    return app
