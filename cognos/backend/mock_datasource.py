from base_datasource import DataSource
from collections import namedtuple
from flask import request, jsonify
import math
import socket

import mock_constants
import app
import helper


class Mock(DataSource):
    def init(self):
        return jsonify({
            "mock_data": 193821
        })

    def get_topology(self):
        payload = app.fetch_topology()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_hosts(self):
        hosts = app.get_hosts_from_db()
        payload = []
        for host in hosts:
            data = {
                "value": host,
                "label": host
            }
            payload.append(data)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def post_devices(self):
        payload = self.get_devices_info()
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def membox_capacity(self):
        payload = self.get_devices_info()
        response = jsonify(helper.process_membox_capacity_payload(payload))
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
        response = jsonify(helper.get_available_devices_fromdb())
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def detach_device(self):
        request_data = request.get_json()
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"][0]
        dev_id = app.get_devid_from_name(dev_name)
        host_id = app.get_hostid_from_name(host_name)
        app.delete_connection(int(dev_id), int(host_id))
        # Return response for host/attached-devices table
        payload = app.get_host_attached_devices(host_name)
        response = jsonify(payload)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def attach_device(self):
        request_data = request.get_json()
        dev_name = request_data["dev_name"]
        host_name = request_data["host_name"][0]
        dev_id = app.get_devid_from_name(dev_name)
        host_id = app.get_hostid_from_name(host_name)

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
        response = jsonify(helper.get_dummy_mb_info())
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    def get_setup_info(self):
        return mock_constants.MOCK_CXL_SETUP

    def get_devices_info(self):
        payload = mock_constants.MOCK_CXL_DEVICES

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
        return mock_constants.MOCK_CXL_HOSTS

    def setup_tables(self):
        # get setup info
        init_payload = self.get_setup_info()
        dev_port_name_map = (
            helper.get_devport_name_map(init_payload["Devices"])
        )
        devport_hostname_map = (
            helper.get_devport_hostname_map(init_payload["Hosts"])
        )

        # get device info
        devices_payload = self.get_devices_info()
        helper.init_devices_table(devices_payload, dev_port_name_map)

        # get hosts info
        hosts_payload = self.get_hosts_info()
        helper.init_hosts_table(hosts_payload)

        # store connections
        helper.init_connections_table(devport_hostname_map)
