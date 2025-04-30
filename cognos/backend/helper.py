import json
import math
import re
import mysql.connector
from mysql.connector import Error
import os
import sys
import ast
import socket
from collections import defaultdict, namedtuple
from flask import Flask, jsonify

project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../..")
)
sys.path.insert(0, project_root)
from cognos.backend.db_query_constants import DUMMYIP  # noqa: E402

COGNOS_TABLES = ["devices", "hosts", "mem_box", "host_device_connections"]
current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(current_script_dir, "config", "config.json")


def is_hexadecimal(value):
    # use re to check if the string matches hexadecimal format
    if isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]+", value):
        return True
    return False


def parse_svkcxlplugin_response(response):
    """
    should parse REST response and return a payload similar to the
    output of FM API
    """
    return json.loads(response.json()["nodeResponses"][0]["output"])


def parse_svkcxlplugin_setup_response(response):
    response = json.loads(response.text)["nodeResponses"][0]["output"]
    response = ast.literal_eval(response)
    return [fm for fm in response]


def get_scmc_version_file():
    """
    Returns: Filepath of VERSION file containing svk-app version
             VERSION file will always be located in the root of
             the install location or the development repository
    """
    root_folder = (
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
    return (
        os.path.join(root_folder, 'VERSION')
        if os.path.exists(root_folder + os.sep + 'VERSION')
        else None
    )


def gen_svkcxlplugin_request_params(
    feature_params, mock_request=False, mock_request_data=None
):
    if mock_request and mock_request_data:
        return mock_request_data

    try:
        # Ensure proper splitting and error handling
        params = {}
        for item in feature_params.split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                params[key.strip()] = value.strip()
            else:
                raise ValueError(f"Invalid feature parameter: {item}")
        # Set default node_id if not provided
        node_id = params.get("node_id", "localhost")
        # Build the request parameters
        request_params = {
            "cluster_id": params.get("cluster_id"),
            "node_id": node_id,
            "feature_id": "3",
            "feature_params": feature_params,
        }
        return request_params
    except Exception as e:
        raise ValueError(f"Failed to parse feature parameters - {str(e)}")


def gen_list_cluster_req_params(feature_params):
    params = dict(item.split("=") for item in feature_params.split(";"))
    request_params = {"feature_params": params}
    return request_params


def fetch_cognos_configs(parent_dir, file_name):
    config_file_path = os.path.join(parent_dir, "config", file_name)
    configs = ""
    try:
        with open(config_file_path, "r") as config_file:
            configs = json.load(config_file)
    # pragma: no cover
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
    return configs


def fetch_api_version(parent_dir):
    try:
        with open(os.path.join(parent_dir, "VERSION"), "r") as v:
            API_VERSION = v.read().strip()
            return API_VERSION
    # pragma: no cover
    except Exception as error:
        raise RuntimeError(f"Unable to retrieve API version: {str(error)}")


def mb_to_GB(val):
    return val // 1024


def bytes_to_MB(val):
    return val / (1024 * 1024)


def bytes_to_GB(val):
    return val / (1024**3)


def get_cognos_influx_functions():
    return [
        "get_recent_dram_cxl_usage_data",
        "get_cpu_mem_usage",
        "get_memserver_capacity",
        "get_membox_usage",
        "get_membox_capacity",
        "get_membox_bandwidth",
        "get_attached_devices_count",
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
        "data_ports": 15,
        "mgmt_ports": 1,
        "mgmt_ip": f"{mb_mgmt_ip}",
        "mgmt_port": 5000,
        "mgmt_port_type": "PCIe",
        "mgmt_netmask": DUMMYIP,
        "form_factor": "4U",
        "manufacturer": "Samsung",
        "memory_size": f"{((256 * GB) * 6) / TB}T",
        "power_state": "ON",
        "health": "OK",
        "protocol_version": 2.0,
    }
    return mb_info


def get_available_devices_fromdb():
    db, cursor = connect_to_mysql()
    query = (
        "SELECT dev_name FROM devices WHERE dev_name not in "
        "(SELECT dev_name FROM host_device_connections) and "
        "type='FM_REMOTE_CMMB';"
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
        num_hosts += 1 if dev["hosts_attached"] else 0
    total_capacity = 256 * num_devices
    used_capacity = 256 * num_hosts
    devices_payload = [
        {
            "total_capacity": total_capacity,
            "used_capacity": used_capacity,
            "used_capacity_percentage": (
                math.floor((used_capacity / total_capacity) * 100)
            ),
        }
    ]
    return devices_payload


def get_db_passwd():
    db_pass = ""
    try:
        with open(CONFIG_FILE_PATH, "r") as config_file:
            db_pass = json.load(config_file)
            if not db_pass:
                raise RuntimeError(
                    f"Unable to retrieve mysql db password: {error}"
                )
    except Exception as error:
        raise RuntimeError(f"Unable to retrieve mysql db password: {error}")
    return db_pass["mysql_db_dev_passwd"]


def prepare_response_with_body(payload):
    response = jsonify(payload)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


def failed_response(msg):
    payload = {"status": 500, "error": msg}
    response = jsonify(payload)
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response


def connect_to_mysql():
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="dev",
            passwd=get_db_passwd(),
            database="cognos",
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
        insert_query = "INSERT INTO scmc (metrics_host_filter) VALUES (%s);"
        values = [host]
        cursor.execute(insert_query, values)
        db.commit()
        disconnect_mysql(db)
    except Exception as error:
        print(f"Failed to update metrics host filter table.. {str(error)}")


def get_metrics_host_filter():
    try:
        db, cursor = connect_to_mysql()
        fetch_query = "SELECT metrics_host_filter FROM scmc;"
        cursor.execute(fetch_query)
        row = cursor.fetchone()
        if row:
            return row[0]
        else:
            print("No host filter in scmc DB table..")
            return ""
        disconnect_mysql(db)
    except Exception as error:
        print(f"Failed to get metrics host filter.. {str(error)}")


def get_param_from_request_params(request_params, arg):
    for param in request_params:
        if param.startswith(arg):
            return param.split("=")[1]
    return None


def insert_hosts(payload, fm_type):
    db, cursor = connect_to_mysql()
    for host in payload:
        try:
            insert_query = (
                "INSERT IGNORE INTO hosts (id, name, mem_capacity, "
                "hosts_target_ports, fm_type) "
                "VALUES (%s, %s, %s, %s, %s)"
            )
            values = (
                host["id"],
                host["name"],
                host["mem_capacity"],
                ",".join(map(str, host["host_target_ports"])),
                fm_type,
            )
            cursor.execute(insert_query, values)
            db.commit()
        except Exception as error:
            print(f"Failed to insert into hosts table: {str(error)}")
            db.rollback()
    disconnect_mysql(db)


def insert_devices(payload, devport_hostname_map, fm_type):
    db, cursor = connect_to_mysql()
    for device in payload:
        try:
            hosts_attached = devport_hostname_map.get(device["dev_port"], "")
            insert_query = (
                "INSERT IGNORE INTO devices "
                "(dev_id, dev_name, dev_capacity, dev_port,"
                " hosts_attached, status, type, mode)"
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            values = (
                device["dev_id"],
                device["dev_name"],
                device["dev_capacity"],
                device["dev_port"],
                hosts_attached,
                "active",
                fm_type,
                "direct",
            )
            print(f"Inserting device with values: {values}")
            cursor.execute(insert_query, values)
            db.commit()
        except Exception as error:
            print(f"Failed to insert into devices table: {str(error)}")
            db.rollback()
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
                "hosts_attached": row[4],
            }
            payload.append(obj)
        disconnect_mysql(db)
    except Exception as error:
        print(f"Failed to fetch from devices table.. {str(error)}")
    return payload


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
    if not row or not row[0]:  # No hosts attached
        disconnect_mysql(db)
        return
    prev_hosts_attached = row[0]
    hosts_list = prev_hosts_attached.split(",")
    if removed_host in hosts_list:
        hosts_list.remove(removed_host)
    else:
        disconnect_mysql(db)
        return  # No change needed
    if hosts_list:
        # Multiple hosts still attached
        all_hosts_attached = ",".join(hosts_list)
        update_query = (
            "UPDATE devices SET hosts_attached = %s WHERE dev_id = %s;"
        )
        values = (all_hosts_attached, dev_id)
    else:
        # No hosts left attached
        update_query = (
            "UPDATE devices SET hosts_attached = NULL WHERE dev_id = %s;"
        )
        values = [dev_id]
    try:
        cursor.execute(update_query, values)
        db.commit()
    except Exception as error:
        print(f"Failed to update devices table.. {str(error)}")
    finally:
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
        return ""

    if prev_hosts_attached != -1:
        all_hosts_attached = (
            ",".join([prev_hosts_attached, new_attached_host])
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
            "INSERT IGNORE INTO host_device_connections "
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
            "SELECT DISTINCT h.name AS host, h.fm_type AS fm_type, "
            "GROUP_CONCAT(d.dev_name) AS devices "
            "FROM hosts h "
            "JOIN host_device_connections hdc ON h.id = hdc.host_id "
            "JOIN devices d ON hdc.dev_id = d.dev_id AND h.fm_type = d.type "
            "GROUP BY h.name, h.fm_type;"
        )
        rows = cursor.fetchall()
    except Exception as error:
        print(f"Failed to fetch topology from devices table: {str(error)}")
        rows = []
    for row in rows:
        obj = {"host": row[0], "fm_type": row[1], "devices": row[2].split(",")}
        payload.append(obj)
    disconnect_mysql(db)
    return payload


def get_hosts_from_db():
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT DISTINCT(name) from hosts"
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
        return ""


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
        return ""


def get_cmmb_hostid_from_name(name):
    db, cursor = connect_to_mysql()
    row = []
    try:
        query = (
            "SELECT id FROM hosts WHERE name=%s AND fm_type='FM_REMOTE_CMMB'"
        )
        values = [name]
        cursor.execute(query, values)
        row = cursor.fetchone()
    except Exception as error:
        print(f"Failed to fetch from hosts table.. {str(error)}")
    disconnect_mysql(db)
    if row:
        return row[0]
    else:
        return ""


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
        return ""


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
        return ""


def get_deviceid_and_devicename_from_port(port):
    db, cursor = connect_to_mysql()
    try:
        query = "SELECT dev_id, dev_name FROM devices WHERE dev_port=%s"
        values = [port]
        cursor.execute(query, values)
        row = cursor.fetchone()
        if not row:
            return (0, "")
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
            "dev_name": x[0],
            "status": x[1],
            "dev_port": x[2],
            "type": x[3],
            "mode": x[4],
            "dev_capacity": x[5],
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


def init_devices_table(
    devices_payload, dev_port_name_map, devport_hostname_map, fm_type
):
    for i in range(len(devices_payload)):
        dev_name = dev_port_name_map[devices_payload[i]["dev_port"]]
        devices_payload[i]["dev_name"] = dev_name
    insert_devices(devices_payload, devport_hostname_map, fm_type)


def init_hosts_table(hosts_payload, fm_type):
    insert_hosts(hosts_payload, fm_type)


def init_connections_table(devport_hostname_map):
    for dev_port, host_name in devport_hostname_map.items():
        dev_id, dev_name = get_deviceid_and_devicename_from_port(dev_port)
        host_id = get_hostid_from_name(host_name)
        # insert_connection(host_id, dev_id)
        insert_connection(host_id, host_name, dev_id, dev_name)


def get_fm_devices_info(devices, port_host_map):
    """
    parse list of devices information and transform
    to required format.
    """
    result = []
    for device in devices:
        # Convert hex values to integers
        if is_hexadecimal(device["dev_addr"]):
            dev_id = int(device["dev_addr"], 16)
        else:
            dev_id = int(device["dev_addr"])
        # Convert bytes to GB
        if is_hexadecimal(device["dev_size"]):
            dev_capacity = int(device["dev_size"], 16)
        else:
            dev_capacity = int(device["dev_size"])

        dev_capacity = dev_capacity // (1024**3)
        dev_port = device["dev_port"]
        # get hosts attached from the port_host_map
        hosts_attached = [port_host_map.get(dev_port, "Not Attached")]
        # create the transformed device structure
        transformed_device = {
            "dev_id": dev_id,
            "dev_capacity": dev_capacity,
            "dev_port": dev_port,
            "hosts_attached": hosts_attached,
            "dev_name": device.get("dev_name", "NA"),
        }
        result.append(transformed_device)
    return result


def get_fm_host_info(hosts):
    """
    parse list of host information and transform
    to required format.
    """
    host_info_list = []
    for host in hosts:
        # convert hex values to integers
        if is_hexadecimal(host["host_addr"]):
            host_id = int(host["host_addr"], 16)
        else:
            host_id = int(host["host_addr"])

        if is_hexadecimal(host["host_size"]):
            host_size = int(host["host_size"], 16)
        else:
            host_size = int(host["host_size"])

        host_name = host["host_name"]
        mem_capacity = host_size // (1024**3)
        host_target_ports = [
            endpoint["target"] for endpoint in host.get("endpoint", [])
        ]
        # build transformed host info structure
        host_info = {
            "id": host_id,
            "name": host_name,
            "mem_capacity": mem_capacity,
            "host_target_ports": host_target_ports,
        }
        host_info_list.append(host_info)
    return host_info_list


def count_attached_devices():
    db, cursor = None, None
    try:
        db, cursor = connect_to_mysql()
        if not db or not cursor:
            print("Failed to connect to the database.")
            return None
        query = """
            SELECT
                COUNT(DISTINCT h.id) AS num_hosts,
                COUNT(DISTINCT d.dev_id) AS num_cxl_devices
            FROM
                (SELECT id, fm_type FROM hosts WHERE fm_type=
                'FM_REMOTE_CMMB') h
            LEFT JOIN
                (SELECT dev_id, type, hosts_attached FROM devices
                 WHERE type = 'FM_REMOTE_CMMB' AND hosts_attached IS NOT NULL
                 AND hosts_attached <> '') d
            ON
                h.fm_type = d.type;
        """
        cursor.execute(query)
        result = cursor.fetchall()
        if not result or len(result) == 0:
            return None
        return {"num_hosts": result[0][0], "num_cxl_devices": result[0][1]}
    except Error as err:
        print(f"Error during query execution: {err}")
        return None
    finally:
        disconnect_mysql(db)


def fetch_memory_capacity():
    try:
        db, cursor = connect_to_mysql()
        if not db or not cursor:
            print("Failed to connect to the database.")
            return None
        query = """
            SELECT
                SUM(CASE WHEN hosts_attached IS NOT NULL
                AND hosts_attached <> ''
                THEN dev_capacity ELSE 0 END) AS used_capacity,
                SUM(dev_capacity) AS total_capacity,
                CASE
                    WHEN SUM(dev_capacity) = 0 THEN 0
                    ELSE (SUM(CASE WHEN hosts_attached IS NOT NULL
                    AND hosts_attached <> ''
                    THEN dev_capacity ELSE 0 END) * 100.0 / SUM(dev_capacity))
                END AS used_percentage
            FROM
                devices
            WHERE
                type = 'FM_REMOTE_CMMB';
        """
        cursor.execute(query)
        result = cursor.fetchone()
        if not result or len(result) == 0:
            return None
        return {
            "used_capacity": result[0],
            "total_capacity": result[1],
            "used_percentage": result[2],
        }
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None
    finally:
        disconnect_mysql(db)


def count_host_upstream_ports():
    try:
        db, cursor = connect_to_mysql()
        if not db or not cursor:
            print("Failed to connect to the database.")
            return None
        query = """
            SELECT
                COUNT(1)
            FROM
                hosts
            WHERE
                fm_type = 'FM_REMOTE_CMMB';
        """
        cursor.execute(query)
        result = cursor.fetchone()
        if not result or len(result) == 0:
            return None
        return {
            "num_upstream_ports": result[0],
        }
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None
    finally:
        disconnect_mysql(db)


def get_clusters():
    # @to-do use list cluster names API
    return ["CL_ID_1"]


def get_all_hosts():
    """
    Fetch distinct hostnames from the hosts table.
    """
    try:
        db, cursor = connect_to_mysql()
        if not db or not cursor:
            print("Failed to connect to the database.")
            return None
        # SQL query to get distinct hostnames
        query = """
            SELECT DISTINCT name
            FROM hosts;
        """
        cursor.execute(query)
        results = cursor.fetchall()
        # If no results are found, return None
        if not results or len(results) == 0:
            return None
        # Extract hostnames from results and return them as a list
        return {"hostnames": [row[0] for row in results]}
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None
    finally:
        disconnect_mysql(db)
