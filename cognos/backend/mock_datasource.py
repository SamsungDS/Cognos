from collections import namedtuple
from datetime import datetime
from flask import request, jsonify
import math
import socket

from cognos.backend.base_datasource import DataSource
from cognos.backend.mock_constants import (
    MOCK_CXL_SETUP,
    MOCK_CXL_DEVICES,
    MOCK_CXL_HOSTS,
    MOCK_FM_CXL_SETUP,
)
from cognos.backend.helper import (
    process_membox_capacity_payload,
    get_available_devices_fromdb,
    get_dummy_mb_info,
    get_devport_name_map,
    get_devport_hostname_map,
    init_devices_table,
    init_hosts_table,
    init_connections_table,
    fetch_topology,
    get_hosts_from_db,
    get_devices_from_db,
    get_host_attached_devices,
    get_devid_from_name,
    get_hostid_from_name,
    delete_connection,
    connect_to_mysql,
    disconnect_mysql,
    get_devname_from_id,
    update_device_attached_hosts,
    remove_device_attached_host,
    update_metrics_host_filter_table,
    get_fm_devices_info,
    get_fm_host_info,
    get_scmc_version_file
)


class Mock(DataSource):
    def init(self):
        return jsonify({"mock_data": 193821})

    def get_scmc_version(self):
        scmc_version_file = get_scmc_version_file()
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

    def get_metrics(self):
        payload = {"data": [datetime.now(), 0.5, 0.7]}
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def update_metrics_host_filter(self):
        request_data = request.get_json()
        host = request_data["host"]["value"]
        update_metrics_host_filter_table(host)
        payload = {"status": 200}
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_topology(self):
        payload = fetch_topology()
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_hosts(self):
        hosts = get_hosts_from_db()
        payload = []
        for host in hosts:
            data = {"value": host, "label": host}
            payload.append(data)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def post_devices(self):
        payload = get_devices_from_db()
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def membox_capacity(self):
        payload = self.get_devices_info()
        response = jsonify(process_membox_capacity_payload(payload))
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def host_devices(self):
        request_data = request.get_json()
        host = request_data["host"]
        payload = get_host_attached_devices(host)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def available_devices(self):
        response = jsonify(get_available_devices_fromdb())
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def detach_device(self):
        request_data = request.get_json()
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"][0]
        dev_id = get_devid_from_name(dev_name)
        host_id = get_hostid_from_name(host_name)
        delete_connection(int(dev_id), int(host_id))
        # remove attached host from device
        remove_device_attached_host(dev_id, host_name)
        # Return response for host/attached-devices table
        payload = get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def attach_device(self):
        request_data = request.get_json()
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"][0]
        dev_id = get_devid_from_name(dev_name)
        host_id = get_hostid_from_name(host_name)

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

        # Update Attached hosts for device
        update_device_attached_hosts(dev_id, host_name)

        # Return response for host/attached-devices table
        payload = get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_mb_info(self):
        response = jsonify(get_dummy_mb_info())
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    def get_setup_info(self):
        return MOCK_FM_CXL_SETUP

    def get_devices_info(self):
        payload = MOCK_CXL_DEVICES

        # convert bytes into GB & add device names
        for i in range(len(payload)):
            payload[i]["dev_capacity"] = math.trunc(
                payload[i]["dev_capacity"] / (1024 * 1024 * 1024)
            )
            dev_id = payload[i]["dev_id"]
            payload[i]["dev_name"] = get_devname_from_id(payload[i]["dev_id"])

        return payload

    def get_hosts_info(self):
        return MOCK_CXL_HOSTS

    def setup_tables(self):
        # get setup info
        payload = self.get_setup_info()
        for fm in payload["fabric_managers"]:

            dev_port_name_map = get_devport_name_map(fm["Devices"])
            devport_hostname_map = get_devport_hostname_map(fm["Hosts"])

            # get device info
            devices_payload = get_fm_devices_info(
                fm["Devices"], devport_hostname_map
            )
            init_devices_table(
                devices_payload,
                dev_port_name_map,
                devport_hostname_map,
                fm["type"],
            )

            # get hosts info
            hosts_payload = get_fm_host_info(fm["Hosts"])
            init_hosts_table(hosts_payload, fm["type"])
            # store connections
            init_connections_table(devport_hostname_map)
