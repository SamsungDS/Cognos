# app.py
from collections import defaultdict
from flask import Flask, request, jsonify
from decimal import Decimal
import json
import mysql.connector
import os
import socket
from flask_cors import CORS

from db_query_constants import (
    get_all_devices_query,
    get_device_host_connections_query,
    update_lmd_status_query
)

app = Flask(__name__)
CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(current_script_dir, 'config', 'config.json')

hosts_table = [
    {"host": "host1", "dram": 56.3, "cxl_dram": 141.1, "cxl_pmem": 48.1,
     "units": "GB"},
    {"host": "host2", "dram": 124, "cxl_dram": 322, "cxl_pmem": 201,
     "units": "GB"},
    {"host": "host3", "dram": 64, "cxl_dram": 221, "cxl_pmem": 120,
     "units": "GB"},
    {"host": "host4", "dram": 14, "cxl_dram": 32, "cxl_pmem": 10.2,
     "units": "GB"},
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
    return db_pass


def prepare_response_with_body(payload):
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


def get_host_devices_query(host):
    return (
        "SELECT lmd, pool, mem_type, mem_mode, capacity, capacity_units, "
        "used_capacity, used_capacity_units FROM logical_memory_device "
        "WHERE lmd in "
        f"(SELECT lmd from connections WHERE host = '{host}');"
    )


def get_host_devices_table(host):
    db, cursor = connect_to_mysql()
    query = get_host_devices_query(host)
    cursor.execute(query)
    results = cursor.fetchall()
    payload = []
    row = {}
    for x in results:
        row = {
            'lmd': x[0], 'pool': x[1], 'mem_type': x[2], 'mem_mode': x[3],
            'capacity': float(x[4]), 'capacity_units': x[5],
            'used_capacity': float(x[6]), 'used_capacity_units': x[7]
        }
        payload.append(row)
        row = {}
    disconnect_mysql(db)
    return payload


def get_latest_devices_table():
    db, cursor = connect_to_mysql()
    cursor.execute(get_all_devices_query)
    result = cursor.fetchall()
    host_mapping_query = cursor.execute(
        get_device_host_connections_query
    )
    cursor.execute(host_mapping_query)
    host_mapping = cursor.fetchall()
    lmd_to_memory_servers = defaultdict(None)
    for y in host_mapping:
        lmd_to_memory_servers[y[0]] = y[1]  # {<lmd>: host1,host2,..}
    payload = []
    row = {}
    for x in result:
        row = {
            'status': x[0], 'lmd': x[1], 'pool': x[2],
            'mem_type': x[3], 'mem_mode': x[4], 'capacity': float(x[5]),
            'capacity_units': x[6], 'used_capacity': float(x[7]),
            'used_capacity_units': x[8], 'device_type': x[9],
            'memory_servers': lmd_to_memory_servers.get(x[1], '')
        }
        payload.append(row)
        row = {}
    disconnect_mysql(db)
    return payload


def connect_to_mysql():
    db = mysql.connector.connect(
        host="localhost",
        user="dev",
        passwd=get_db_passwd(),
        database="scfm"
    )
    cursor = db.cursor()
    return db, cursor


def disconnect_mysql(db):
    db.close()


@app.get("/hosts")
def get_hosts():
    db, cursor = connect_to_mysql()
    cursor.execute("SELECT * FROM hosts;")
    result = cursor.fetchall()

    payload = []
    row = {}

    for x in result:
        row = {'host': x[0], 'dram': float(x[1]), 'cxl_dram': float(x[2]),
               'cxl_pmem': float(x[3]), 'units': x[4]}
        payload.append(row)
        row = {}
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    disconnect_mysql(db)
    return response


@app.get("/lmds")
def get_partitions():
    payload = get_latest_devices_table()
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.post("/membox_lmds")
def get_membox_lmds():
    data = json.loads(request.data)
    mem_box = data['mem_box']
    db, cursor = connect_to_mysql()

    query = (
        "SELECT status, lmd, device_type, mem_mode, pool, capacity, "
        "capacity_units FROM logical_memory_device "
        f"WHERE mem_box = '{mem_box}';"
    )
    cursor.execute(query)
    lmd_metadata = cursor.fetchall()

    host_mapping_query = cursor.execute(
        get_device_host_connections_query
    )
    cursor.execute(host_mapping_query)
    host_mapping = cursor.fetchall()
    lmd_to_memory_servers = defaultdict(None)
    for y in host_mapping:
        lmd_to_memory_servers[y[0]] = y[1]  # {<lmd>: host1,host2,..}

    payload = []
    row = {}
    for x in lmd_metadata:
        row = {
            'status': x[0], 'lmd': x[1], 'mem_box': mem_box,
            'device_type': x[2], 'mem_mode': x[3], 'pool': x[4],
            'capacity': x[5], 'capacity_units': x[6],
            'memory_servers': lmd_to_memory_servers.get(x[1], '')
        }
        payload.append(row)
        row = {}

    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    disconnect_mysql(db)
    return response


@app.post("/host_lmds")
def host_lmds():
    data = json.loads(request.data)
    host = data['host']
    payload = get_host_devices_table(host)
    return prepare_response_with_body(payload)


@app.get("/attached_hosts")
def attached_hosts():
    db, cursor = connect_to_mysql()
    cursor.execute(get_device_host_connections_query)
    results = cursor.fetchall()

    lmd_to_memory_servers = defaultdict(None)

    for x in results:
        lmd_to_memory_servers[x[0]] = x[1]

    response = jsonify(lmd_to_memory_servers)
    response.headers.add('Access-Control-Allow-Origin', '*')
    disconnect_mysql(db)
    return response


@app.post("/attach_lmd")
def attach_lmd():
    # add row to connection table
    # select all records from connection table for the host
    data = json.loads(request.data)

    db, cursor = connect_to_mysql()
    insert_query = (
        "INSERT INTO connections "
        "(host, host_memory_address, lmd, mem_box, cxl_device)"
        "VALUES (%s, %s, %s, %s, %s)"
    )

    values = (
        data['host'], data.get('host_memory_address', ''),
        data['lmd'], 'mb-1', 'cxl-device-1'
    )

    cursor.execute(insert_query, values)
    db.commit()

    # Update the status of the LMD
    update_query = (
        update_lmd_status_query
    )
    update_values = ('loading', data['lmd'])
    cursor.execute(update_query, update_values)
    db.commit()

    disconnect_mysql(db)

    # get the latest state of the table after attach and return as a response
    host = data['host']
    payload = get_host_devices_table(host)
    return prepare_response_with_body(payload)


@app.delete("/detach_lmd")
def detach_lmd():
    data = json.loads(request.data)

    host = data['host']
    db, cursor = connect_to_mysql()
    delete_query = ("DELETE FROM connections WHERE host = %s AND lmd = %s;")
    values = (data['host'], data['lmd'])
    cursor.execute(delete_query, values)
    db.commit()

    # Set state of LMD to ready after detach
    update_query = (
        update_lmd_status_query
    )
    update_values = ('ready', data['lmd'])
    cursor.execute(update_query, update_values)
    db.commit()

    disconnect_mysql(db)

    # get the latest state of the table after detach and return as a response
    payload = get_host_devices_table(host)
    return prepare_response_with_body(payload)


@app.post("/activate_device")
def update_device_status():
    data = json.loads(request.data)
    host, lmd, status = data['host'], data['lmd'], 'active'
    db, cursor = connect_to_mysql()

    update_query = (
        update_lmd_status_query
    )
    update_values = (status, lmd)

    cursor.execute(update_query, update_values)
    db.commit()
    disconnect_mysql(db)

    # Get the latest state of the table and return as a response
    payload = get_latest_devices_table()
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.post("/create_lmd")
def create_lmd():
    data = json.loads(request.data)

    pool_name = ""
    if data["isPoolFlag"]:
        pool_name = data['logicalMemoryDevice']
    else:
        pool_name = '' if data['pool'] == 'Default Pool' else data['pool']

    db, cursor = connect_to_mysql()
    insert_query = (
        "INSERT INTO logical_memory_device "
        "(status, lmd, pool, mem_type, mem_mode, capacity, capacity_units, "
        "used_capacity, used_capacity_units, device_type) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    values = (
        'loading', data['logicalMemoryDevice'],
        pool_name,
        data['memoryType'], data['memoryMode'], data['memoryAllocation'],
        "GB", 0, "GB", 'SLD'
    )

    cursor.execute(insert_query, values)
    db.commit()
    disconnect_mysql(db)

    # get latest state of table and return as response
    payload = get_latest_devices_table()
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.get("/available_lmds")
def available_lmds():
    db, cursor = connect_to_mysql()
    query = "SELECT lmd FROM logical_memory_device;"
    cursor.execute(query)
    result = cursor.fetchall()

    response = jsonify(result)
    response.headers.add('Access-Control-Allow-Origin', '*')
    disconnect_mysql(db)
    return response


@app.delete("/free_lmd")
def free_lmd():
    lmd = json.loads(request.data)

    db, cursor = connect_to_mysql()
    delete_query = "DELETE FROM logical_memory_device WHERE lmd = %s;"
    delete_params = [lmd]
    cursor.execute(delete_query, delete_params)
    db.commit()
    disconnect_mysql(db)

    # get latest state of table and return as response
    payload = get_latest_devices_table()
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@app.get("/connections")
def get_connections():
    db, cursor = connect_to_mysql()
    cursor.execute("SELECT * FROM connections;")
    result = cursor.fetchall()

    payload = []
    row = {}
    for x in result:
        row = {
            'host': x[0], 'lmd': x[1], 'mem_box': x[2],
            'cxl_device': x[3]
        }
        payload.append(row)
        row = {}
    response = jsonify(payload)
    response.headers.add('Access-Control-Allow-Origin', '*')
    disconnect_mysql(db)
    return response


@app.get("/host_device_map")
def get_host_device_map():
    """
    Example layout
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
    payload = []

    db, cursor = connect_to_mysql()
    cursor.execute(
        "SELECT DISTINCT(host), GROUP_CONCAT(lmd) as devices "
        "FROM connections GROUP BY host;"
    )
    rows = cursor.fetchall()
    for row in rows:
        obj = {
            "host": row[0].replace(' ', ''),
            "devices": row[1].split(',')
        }
        payload.append(obj)

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
