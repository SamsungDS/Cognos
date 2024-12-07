from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from datetime import datetime
import json
import math
import os
import requests
import sys

sys.path.append(os.path.abspath(  # noqa: E402
    os.path.join(os.path.dirname(__file__), '..')))  # noqa: E402
from cognos.backend.helper import (
    bytes_to_GB, fetch_cognos_configs, parse_svkcxlplugin_response,
    gen_svkcxlplugin_request_params,
    mb_to_GiB
)

from cognos.backend.db_query_constants import (
    DATE_FORMAT,
    APPLICATION_JSON,
    CLUSTER_SETUP_COMMAND,
)

from cognos.backend.mock_constants import MOCK_CXL_SETUP


class CognosInfluxDBClient():
    def __init__(self, url=None, token=None, org=None, bucket=None,
                 mock=False):
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        if any(arg is None for arg in [url, token, org, bucket]):
            configs = fetch_cognos_configs(current_script_dir,
                                           'influxdb_config.json')
            self.bucket = configs['bucket']
            self.url = configs['url']
            self.token = configs['token']
            self.org = configs['org']
        else:
            self.url = url
            self.token = token
            self.org = org
            self.bucket = bucket
        endpoint_configs = fetch_cognos_configs(current_script_dir,
                                                'config.json')
        self.agent_endpoint = endpoint_configs['agent_endpoint']
        self.node_endpoint = endpoint_configs['node_endpoint']

        self.client = InfluxDBClient(url=self.url, token=self.token,
                                     org=self.org)
        self.write_client = self.client.write_api(write_options=SYNCHRONOUS)
        self.read_client = self.client.query_api()
        self.filter_hosts = False
        self.selected_host = None
        self.mock = mock

    def write_cognos_event(self, event):
        """
        Takes the following schema from Cognos Agent event collectors and
        writes to InfluxDB

        Event {
            type: metric/alert,
            source: <host/application server>,
            source_type: <source_type>,
            timestamp: <timestamp>,
            description: <description>,
            category: <category>,
            application: <app-name>,
            observations: {
                <metric_name>: <metric_value>,
                ...
            }
        }
        """
        records = [{
            "measurement": event['type'],
            "tags": {
                "source": event['source'],
                "source_type": event['source_type'],
                "description": event['description'],
                "category": event['category'],
                "application": event['application']
            },
            "fields": event['observations'],
            "timestamp": event['timestamp']
        }]
        self.write_client.write(self.bucket, self.org, records)

    def query_cognos_events(self, time_window):
        return self.read_client.query(
            f'from(bucket:"internal") |> range(start: -{time_window}) '
            '|> last(6)'
        )

    def get_recent_dram_cxl_usage_data(self):
        params = {
            "_desc": True
        }

        tables = self.read_client.query(f'''
            from(bucket:"internal")
                |> range(start: -60s)
                |> filter(fn: (r) => r["source"] == "{self.selected_host}")
                |> keep(columns: ["_time", "_field", "_value"])
                |> sort(columns: ["_time"], desc: _desc)
                |> filter(fn: (r) => r._field == "cxl_usage_mb"
                 or r._field == "dram_usage_mb"
                 or r._field == "dram_capacity_mb"
                 or r._field == "cxl_capacity_mb")
        ''', params=params)

        output = tables.to_json()
        data = json.loads(output)

        try:
            time_set = set()
            data_set = {}
            for m in data:
                curr_time = datetime.strptime(
                    m['_time'].split('.')[0],
                    '%Y-%m-%dT%H:%M:%S'
                )
                time_set.add(curr_time)
                field = m["_field"]
                value = m["_value"]
                if curr_time not in data_set:
                    data_set[curr_time] = {field: value}
                elif field not in data_set[curr_time].keys():
                    data_set[curr_time][field] = value

            ordered_timeset = sorted(list(time_set))
            export_data = [["Mem Usage", "DRAM", "CXL"]]
            for t in ordered_timeset:
                metric_time = t.strftime('%H:%M:%S')
                dram_metric = (
                    math.floor(
                        (
                            data_set[t]['dram_usage_mb']
                            / data_set[t]['dram_capacity_mb']
                        ) * 100
                    ) if data_set[t]['dram_usage_mb'] > 0 else 0
                )
                cxl_metric = (
                    math.floor(
                        (
                            data_set[t]['cxl_usage_mb']
                            / data_set[t]['cxl_capacity_mb']
                        ) * 100
                    ) if data_set[t]['cxl_usage_mb'] > 0 else 0
                )
                export_data.append([
                    metric_time,
                    dram_metric,
                    cxl_metric
                ])
            return export_data
        except Exception as error:
            print(f"ERROR during recent_dram vs cxl processing {str(error)}")

    def get_cpu_mem_usage(self):
        params = {
            "_desc": True
        }

        tables = self.read_client.query(f'''
            from(bucket:"internal")
                |> range(start: -60s)
                |> sort(columns: ["_time"], desc: _desc)
                |> filter(fn: (r) => r["source"] == "{self.selected_host}")
                |> filter(fn: (r) => r._field == "cpu_usage"
                 or r._field == "dram_usage_mb"
                 or r._field == "dram_capacity_mb"
                 or r._field == "cxl_usage_mb"
                 or r._field == "cxl_capacity_mb")
        ''', params=params)

        output = tables.to_json()
        data = json.loads(output)

        try:
            time_set = set()
            data_set = {}
            for m in data:
                curr_time = datetime.strptime(
                    m['_time'].split('.')[0],
                    '%Y-%m-%dT%H:%M:%S'
                )
                time_set.add(curr_time)
                field = m["_field"]
                value = m["_value"]
                if curr_time not in data_set:
                    data_set[curr_time] = {field: value}
                else:
                    data_set[curr_time][field] = value

            ordered_timeset = sorted(list(time_set))
            export_data = [["CPU vs Memory Usage", "Mem (CXL+DRAM)", "CPU"]]
            for t in ordered_timeset:
                capacity_sum = (
                    data_set[t]['dram_capacity_mb'] +
                    data_set[t]['cxl_capacity_mb']
                )
                export_data.append([
                    t.strftime('%H:%M:%S'),
                    (
                        (
                            (
                                (
                                    data_set[t]['dram_usage_mb']
                                    + data_set[t]['cxl_usage_mb']
                                ) / (
                                    data_set[t]['dram_capacity_mb']
                                    + data_set[t]['cxl_capacity_mb']
                                )
                            ) * 100
                        ) if capacity_sum > 0 else 0
                    ),
                    data_set[t]['cpu_usage']
                ])
            return export_data
        except Exception as error:
            print(f"failed to send recent CPU vs mem usage data {str(error)}")

    def get_memserver_capacity(self):
        params = {
            "_desc": True
        }

        tables = self.read_client.query(f'''
            from(bucket:"internal")
                |> range(start: -10s)
                |> filter(fn: (r) => r["source"] == "{self.selected_host}")
                |> filter(fn: (r) => r._field == "cxl_capacity_mb"
                 or r._field == "dram_capacity_mb")
                |> keep(columns: ["_field", "_value"])
                |> last()
        ''', params=params)

        output = tables.to_json()
        data = json.loads(output)

        # get CXL capacity based on # of attached devices to selected host
        cxl_capacity_gb = -1
        if self.mock:
            cxl_capacity_gb = 256
        else:
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
            body = gen_svkcxlplugin_request_params(
                "cluster_id=CLUST1;command=SetupInfo")
            response = requests.post(
                self.agent_endpoint,
                json=body,
                headers=headers
            )
            payload = parse_svkcxlplugin_response(response)
            for host in payload['Hosts']:
                if host['host_name'] == self.selected_host:
                    cxl_capacity_gb = 0
                    for endpt in host['endpoint']:
                        device_port = endpt['target']
                        for device in payload['Devices']:
                            if device['dev_port'] == device_port:
                                cxl_capacity_gb += (
                                    bytes_to_GB(int(device['dev_size'], 16))
                                )
        try:
            export_data = [["Memtype", "Capacity Used"]]
            for metric in data:
                memtype = metric['_field'].split('_')[0].upper()
                # derive CXL capacity from attach/detached states
                if memtype == 'CXL':
                    export_data.append([memtype, cxl_capacity_gb])
                else:
                    export_data.append([memtype, mb_to_GiB(metric['_value'])])
            return export_data
        except Exception as error:
            print(f"Failed to process memserver capacity data {str(error)}")

    def get_membox_usage(self):
        params = {
            "_desc": True
        }

        tables = self.read_client.query('''
            from(bucket:"internal")
                |> range(start: -60s)
                |> filter(fn: (r) => r._field == "cxl_usage_mb")
                |> keep(columns: ["_field", "_value", "_time"])
                |> aggregateWindow
                (column: "_value", every: 6s, fn: sum, createEmpty: false)
                |> yield(name: "sum")
        ''', params=params)

        output = tables.to_json()
        data = json.loads(output)

        try:
            time_set = set()
            data_set = {}
            for m in data:
                curr_time = datetime.strptime(
                    m['_time'].split('+')[0].split('.')[0],
                    '%Y-%m-%dT%H:%M:%S'
                )
                time_set.add(curr_time)
                field = m["_field"]
                value = m["_value"]
                if curr_time not in data_set:
                    data_set[curr_time] = {field: value}
                else:
                    # pragma: no cover
                    data_set[curr_time][field] = value

            export_data = [["Membox Usage", "Usage MB"]]
            ordered_timeset = sorted(list(time_set))
            for t in ordered_timeset:
                export_data.append([
                    t.strftime('%H:%M:%S'),
                    data_set[t]['cxl_usage_mb']
                ])
            return export_data
        except Exception as error:
            # pragma: no cover
            print(f"failed to process membox usage data: {str(error)}")

    def get_membox_bandwidth(self):
        """
        upstream port bandwidth = 8 lanes per port* 4GB/s per lane
        32G per upstream port
        """
        if self.mock:
            payload = MOCK_CXL_SETUP
        else:
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
            body = gen_svkcxlplugin_request_params(
                "cluster_id=CLUST1;command=SetupInfo")
            response = requests.post(
                self.agent_endpoint,
                json=body,
                headers=headers
            )
            payload = parse_svkcxlplugin_response(response)

        try:
            max_bandwidth = 512
            num_upstream_ports = len(payload['Hosts'])
            used_bandwidth = 32 * num_upstream_ports
            used_percentage_bandwidth = (
                    math.floor((used_bandwidth / max_bandwidth) * 100)
                    if max_bandwidth > 0 else 100
            )
            return {
                "max_bandwidth": max_bandwidth,
                "used_bandwidth": used_bandwidth,
                "used_percentage_bandwidth": used_percentage_bandwidth
            }
        except Exception as error:
            # pragma: no cover
            print(f"failure while processing membox bandwidth {str(error)}")

    def get_attached_devices_count(self):
        if self.mock:
            payload = MOCK_CXL_SETUP
        else:
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
            body = gen_svkcxlplugin_request_params(
                "cluster_id=CLUST1;command=SetupInfo")
            response = requests.post(
                self.agent_endpoint,
                json=body,
                headers=headers
            )
            payload = parse_svkcxlplugin_response(response)
        try:
            num_hosts = len(payload['Hosts'])
            num_cxl_devices = len(payload['Devices'])
            return {
                "num_hosts": num_hosts,
                "num_cxl_devices": num_cxl_devices
            }
        except Exception as error:
            # pragma: no cover
            print(f"Error in processing attached devices count: {str(error)}")

    def get_membox_capacity(self):
        if self.mock:
            payload = MOCK_CXL_SETUP
        else:
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
            body = gen_svkcxlplugin_request_params(
                "cluster_id=CLUST1;command=SetupInfo")
            response = requests.post(
                self.agent_endpoint,
                json=body,
                headers=headers
            )
            payload = parse_svkcxlplugin_response(response)

        try:
            # get used capacity
            used_capacity = 0
            for host in payload['Hosts']:
                for endpt in host['endpoint']:
                    device_port = endpt['target']
                    for device in payload['Devices']:
                        if device['dev_port'] == device_port:
                            used_capacity += (
                                bytes_to_GB(int(device['dev_size'], 16))
                            )

            # get total capacity
            total_capacity = 0
            for device in payload['Devices']:
                total_capacity += (
                    bytes_to_GB(int(device['dev_size'], 16))
                )

            used_capacity_percentage = (
                    math.floor((used_capacity/total_capacity) * 100)
                    if total_capacity > 0 else 100
            )
            return {
                "total_capacity": total_capacity,
                "used_capacity": used_capacity,
                "used_capacity_percentage": used_capacity_percentage
            }
        except Exception as error:
            # pragma: no cover
            print(f"Failure during processing membox capacity: {str(error)}")
