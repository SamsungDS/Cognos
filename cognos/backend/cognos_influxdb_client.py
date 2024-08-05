from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from datetime import datetime
import time
import json
import math
import os
import random
import requests
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def fetch_cognos_configs(file_name):
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file_path = os.path.join(current_script_dir,
                                    'config', file_name)
    configs = ''
    try:
        with open(config_file_path, 'r') as config_file:
            configs = json.load(config_file)
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
    return configs


class CognosInfluxDBClient():
    def __init__(self, url=None, token=None, org=None, bucket=None):
        if any(arg is None for arg in [url, token, org, bucket]):
            configs = fetch_cognos_configs('influxdb_config.json')
            self.bucket = configs['bucket']
            self.url = configs['url']
            self.token = configs['token']
            self.org = configs['org']
        else:
            self.url = url
            self.token = token
            self.org = org
            self.bucket = bucket

        self.client = InfluxDBClient(url=self.url, token=self.token,
                                     org=self.org)
        self.write_client = self.client.write_api(write_options=SYNCHRONOUS)
        self.read_client = self.client.query_api()
        self.filter_hosts = False
        self.selected_host = None

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

        if self.selected_host == 'loaner-emr02':
            self.selected_host += '.msl.lab'
        elif self.selected_host == 'msl-stg-emr03':
            self.selected_host += '.msl.lab'

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
            dram_metric = math.floor((
                data_set[t]['dram_usage_mb'] / data_set[t]['dram_capacity_mb']
            ) * 100)
            cxl_metric = math.floor((
                data_set[t]['cxl_usage_mb'] / data_set[t]['cxl_capacity_mb']
            ) * 100)
            export_data.append([
                metric_time,
                dram_metric,
                cxl_metric
            ])
        return export_data

    def get_cpu_mem_usage(self):
        params = {
            "_desc": True
        }

        if self.selected_host == 'loaner-emr02':
            self.selected_host += '.msl.lab'
        elif self.selected_host == 'msl-stg-emr03':
            self.selected_host += '.msl.lab'

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
            export_data.append([
                t.strftime('%H:%M:%S'),
                (
                    ((data_set[t]['dram_usage_mb']+data_set[t]['cxl_usage_mb'])
                     / (data_set[t]['dram_capacity_mb']
                        + data_set[t]['cxl_capacity_mb'])
                     )*100
                ),
                data_set[t]['cpu_usage']
            ])
        return export_data

    def get_memserver_capacity(self):
        params = {
            "_desc": True
        }

        if self.selected_host == 'loaner-emr02':
            self.selected_host += '.msl.lab'
        elif self.selected_host == 'msl-stg-emr03':
            self.selected_host += '.msl.lab'

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

        export_data = [["Memtype", "Capacity Used"]]
        total_capacity = 0
        for metric in data:
            for k, v in metric.items():
                if k == '_value':
                    total_capacity += v

        for metric in data:
            memtype = metric['_field'].split('_')[0].upper()
            export_data.append([memtype, (metric['_value']//1024)])
        return export_data

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
                data_set[curr_time][field] = value

        export_data = [["Membox Usage", "Usage MB"]]
        ordered_timeset = sorted(list(time_set))
        for t in ordered_timeset:
            export_data.append([
                t.strftime('%H:%M:%S'),
                data_set[t]['cxl_usage_mb']
            ])
        return export_data

    def get_membox_bandwidth(self):
        """
        upstream port bandwidth = 8 lanes per port* 4GB/s per lane
        32G per upstream port
        """
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(
            "http://hpos-vroc04:8081/api/v1/process_controller_command",
            json={"input": "cluster_id=CLUST1;command=SetupInfo"},
            headers=headers
        )

        payload = json.loads(response.json()['output'])["hpos-vroc04:9998"]
        max_bandwidth = 512
        num_upstream_ports = len(payload['Hosts'])
        used_bandwidth = 32 * num_upstream_ports
        used_percentage_bandwidth = math.floor(
            (used_bandwidth / max_bandwidth) * 100)
        return {
            "max_bandwidth": max_bandwidth,
            "used_bandwidth": used_bandwidth,
            "used_percentage_bandwidth": used_percentage_bandwidth
        }

    def get_attached_devices_count(self):
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(
            "http://hpos-vroc04:8081/api/v1/process_controller_command",
            json={"input": "cluster_id=CLUST1;command=SetupInfo"},
            headers=headers
        )

        payload = json.loads(response.json()['output'])["hpos-vroc04:9998"]
        num_hosts = len(payload['Hosts'])
        num_cxl_devices = len(payload['Devices'])
        return {
            "num_hosts": num_hosts,
            "num_cxl_devices": num_cxl_devices
        }

    def get_membox_capacity(self):
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = requests.post(
            "http://hpos-vroc04:8081/api/v1/process_controller_command",
            json={"input": "cluster_id=CLUST1;command=SetupInfo"},
            headers=headers
        )

        payload = json.loads(response.json()['output'])["hpos-vroc04:9998"]
        num_attached_devices = 0
        for host in payload['Hosts']:
            num_attached_devices += (
                len(host['endpoint']) if host['endpoint'] else 0
            )
        num_cxl_devices = len(payload['Devices'])
        total_capacity = 256 * num_cxl_devices
        used_capacity = 256 * num_attached_devices
        used_capacity_percentage = math.floor(
            (used_capacity/total_capacity) * 100)
        return {
            "total_capacity": total_capacity,
            "used_capacity": used_capacity,
            "used_capacity_percentage": used_capacity_percentage
        }
