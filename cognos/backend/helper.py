import json
import math
import mysql.connector
import os
import sys
import socket
from collections import defaultdict, namedtuple
from flask import Flask, jsonify

project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)
sys.path.insert(0, project_root)
from cognos.backend.db_query_constants import DUMMYIP  # noqa: E402


current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(current_script_dir, 'config', 'config.json')

COGNOS_TABLES = [
    "devices",
    "hosts",
    "mem_box",
    "host_device_connections"
]


def parse_svkcxlplugin_response(response):
    """
    Should parse REST response and return a payload similar to the
    output of FM API
    """
    return json.loads(response.json()["nodeResponses"][0]["output"])


def gen_svkcxlplugin_request_params(feature_params):
    return {
        "cluster_id": "CL_ID_1",
        "node_id": "localhost",
        "feature_id": "3",
        "feature_params": feature_params
    }


def fetch_cognos_configs(parent_dir, file_name):
    config_file_path = os.path.join(parent_dir, 'config', file_name)
    configs = ''
    try:
        with open(config_file_path, 'r') as config_file:
            configs = json.load(config_file)
    # pragma: no cover
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
    return configs


def fetch_api_version(parent_dir):
    try:
        with open(os.path.join(parent_dir, 'VERSION'), 'r') as v:
            API_VERSION = v.read().strip()
            return API_VERSION
    # pragma: no cover
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve API version: {str(error)}"
        )


def mb_to_GiB(val):
    return val // 1024


def bytes_to_MB(val):
    return val / (1024 * 1024)


def bytes_to_GB(val):
    return val / (1024 ** 3)


def get_cognos_influx_functions():
    return [
        'get_recent_dram_cxl_usage_data',
        'get_cpu_mem_usage',
        'get_memserver_capacity',
        'get_membox_usage',
        'get_membox_capacity',
        'get_membox_bandwidth',
        'get_attached_devices_count'
    ]


def get_devport_name_map(devices_payload):
    dev_port_name_map = defaultdict()
    for device in devices_payload:
        dev_port_name_map[device["dev_port"]] = device["dev_name"]
    return dev_port_name_map


def get_devport_hostname_map(hosts_payload):
    devport_hostname_map = defaultdict()
    for host in hosts_payload:
        for endpt in host["endpoint"]:
            devport_hostname_map[endpt["target"]] = host["host_name"]
    return devport_hostname_map


def get_dummy_mb_info():
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
    return mb_info


def get_available_devices_fromdb():
    db, cursor = connect_to_mysql()
    query = (
        "SELECT dev_name FROM devices WHERE dev_name not in "
        "(SELECT dev_name FROM host_device_connections);"
    )
    cursor.execute(query)
    result = cursor.fetchall()
    disconnect_mysql(db)
    return result


def process_membox_capacity_payload(devices_payload):
    num_devices = 0
    num_hosts = 0
    for dev in devices_payload:
        num_devices += 1
        num_hosts += 1 if dev['hosts_attached'] else 0
    total_capacity = 256 * num_devices
    used_capacity = 256 * num_hosts
    devices_payload = [{
        "total_capacity": total_capacity,
        "used_capacity": used_capacity,
        "used_capacity_percentage": (
            math.floor((used_capacity/total_capacity) * 100)
        )
    }]
    return devices_payload


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
    # pragma: no cover
    except Exception as error:
        print(f"Failed to connect to Cognos Mysql DB.. {str(error)}")


def disconnect_mysql(db):
    db.close()


def update_metrics_host_filter_table(host):
    try:
        print(f"ATTEMPTING TO UPDATE scmc table with host: {host}")
        db, cursor = connect_to_mysql()
        delete_query = "DELETE FROM scmc;"
        cursor.execute(delete_query)
        db.commit()
        insert_query = (
            "INSERT INTO scmc (metrics_host_filter) VALUES (%s);"
        )
        values = [host]
        cursor.execute(insert_query, values)
        db.commit()
        disconnect_mysql(db)
    except Exception as error:
        print(f"Failed to update metrics host filter table.. {str(error)}")


def get_metrics_host_filter():
    try:
        db, cursor = connect_to_mysql()
        fetch_query = (
            "SELECT metrics_host_filter FROM scmc;"
        )
        cursor.execute(fetch_query)
        row = cursor.fetchone()
        if row:
            return row[0]
        else:
            print("No host filter in scmc DB table..")
            return ''
        disconnect_mysql(db)
    except Exception as error:
        print(f"Failed to get metrics host filter.. {str(error)}")


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
                "(id, name, mem_capacity)"
                "VALUES (%s, %s, %s)"
            )

            values = (
                host['id'], host['name'], host['mem_capacity']
            )
            cursor.execute(insert_query, values)
            db.commit()
        # pragma: no cover
        except Exception as error:
            print(f"Failed to insert into hosts table.. {str(error)}")

    disconnect_mysql(db)


def get_devices_from_db():
    db, cursor = connect_to_mysql()
    try:
        query = (
            "SELECT dev_name, dev_capacity, dev_id, dev_port, "
            "hosts_attached FROM devices"
        )
        cursor.execute(query)
        rows = cursor.fetchall()

        payload = []
        for row in rows:
            obj = {
                "dev_name": row[0],
                "dev_capacity": row[1],
                "dev_id": row[2],
                "dev_port": row[3],
                "hosts_attached": row[4]
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


def remove_device_attached_host(dev_id, removed_host):
    db, cursor = connect_to_mysql()
    prev_hosts_attached = -1
    row = None
    try:
        query = "SELECT hosts_attached FROM devices WHERE dev_id=%s"
        values = [dev_id]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")

    if row:
        prev_hosts_attached = row[0]
    else:
        return

    update_query = ''
    values = None
    if len(prev_hosts_attached.split(',')) > 1:
        # multiple hosts attached
        all_hosts_attached = (
            ','.join(prev_hosts_attached.split(',').remove(removed_host))
        )
        update_query = (
                "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;"
        )
        values = (all_hosts_attached, dev_id)
    elif prev_hosts_attached == -1:
        # no hosts attached
        return
    else:
        # only a single host attached
        update_query = (
            "UPDATE devices SET hosts_attached = null WHERE dev_id = %s;"
        )
        values = [dev_id]

    try:
        cursor.execute(update_query, values)
        db.commit()
    except Exception as error:
        print(f"Failed to update devices table.. {str(error)}")
    disconnect_mysql(db)


def update_device_attached_hosts(dev_id, new_attached_host):
    db, cursor = connect_to_mysql()
    prev_hosts_attached = -1
    row = None
    try:
        query = "SELECT hosts_attached FROM devices WHERE dev_id=%s"
        values = [dev_id]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")

    if row:
        prev_hosts_attached = row[0]
    else:
        return ''

    if prev_hosts_attached != -1:
        all_hosts_attached = (
            ','.join([prev_hosts_attached, new_attached_host])
            if prev_hosts_attached
            else new_attached_host
        )
        try:
            update_query = (
                "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;"
            )
            values = (all_hosts_attached, dev_id)
            cursor.execute(update_query, values)
            db.commit()
        except Exception as error:
            print(f"Failed to update devices table.. {str(error)}")
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


def get_hosts_from_db():
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT name from hosts"
        cursor.execute(query)
        hosts = cursor.fetchall()
    except Exception as error:
        print(f"Failed to fetch from hosts table.. {str(error)}")

    return hosts if hosts else []


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
    row = []
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


def get_host_attached_devices(host):
    db, cursor = connect_to_mysql()
    results = []
    host = host[0] if type(host) is list else host
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


def init_devices_table(devices_payload, dev_port_name_map):
    for i in range(len(devices_payload)):
        dev_name = dev_port_name_map[devices_payload[i]["dev_port"]]
        devices_payload[i]["dev_name"] = dev_name
    insert_devices(devices_payload)


def init_hosts_table(hosts_payload):
    insert_hosts(hosts_payload)


def init_connections_table(devport_hostname_map):
    for dev_port, host_name in devport_hostname_map.items():
        dev_id, dev_name = (
            get_deviceid_and_devicename_from_port(dev_port)
        )
        host_id = get_hostid_from_name(host_name)
        insert_connection(host_id, host_name, dev_id, dev_name)
