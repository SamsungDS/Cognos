from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from datetime import datetime
import json
import math
import os
import requests
import sys

sys.path.append(
    os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), "..")
    )
)  # noqa: E402
import cognos.backend.helper as helper
import cognos.backend.db_query_constants as dbq
from cognos.backend.mock_constants import MOCK_CXL_SETUP
from cognos.backend.helper import parse_svkcxlplugin_response


class CognosInfluxDBClient:
    def __init__(
        self, url=None, token=None, org=None, bucket=None, mock=False
    ):
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        if any(arg is None for arg in [url, token, org, bucket]):
            configs = helper.fetch_cognos_configs(
                current_script_dir, "influxdb_config.json"
            )
            self.bucket = configs["bucket"]
            self.url = configs["url"]
            self.token = configs["token"]
            self.org = configs["org"]
        else:
            self.url = url
            self.token = token
            self.org = org
            self.bucket = bucket
        endpoint_configs = helper.fetch_cognos_configs(
            current_script_dir, "config.json"
        )
        self.agent_endpoint = endpoint_configs["agent_endpoint"]
        self.node_endpoint = endpoint_configs["node_endpoint"]

        self.client = InfluxDBClient(
            url=self.url, token=self.token, org=self.org
        )
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
        records = [
            {
                "measurement": event["type"],
                "tags": {
                    "source": event["source"],
                    "source_type": event["source_type"],
                    "description": event["description"],
                    "category": event["category"],
                    "application": event["application"],
                },
                "fields": event["observations"],
                "timestamp": event["timestamp"],
            }
        ]
        self.write_client.write(self.bucket, self.org, records)

    def query_cognos_events(self, time_window):
        return self.read_client.query(
            f'from(bucket:"internal") |> range(start: -{time_window}) '
            "|> last(6)"
        )

    def get_recent_dram_cxl_usage_data(self):
        params = {"_desc": True}

        tables = self.read_client.query(
            f"""
            from(bucket:"internal")
                |> range(start: -60s)
                |> filter(fn: (r) => r["source"] == "{self.selected_host}")
                |> keep(columns: ["_time", "_field", "_value"])
                |> sort(columns: ["_time"], desc: _desc)
                |> filter(fn: (r) => r._field == "cxl_usage_mb"
                 or r._field == "dram_usage_mb"
                 or r._field == "dram_capacity_mb"
                 or r._field == "cxl_capacity_mb")
        """,
            params=params,
        )

        output = tables.to_json()
        data = json.loads(output)

        try:
            time_set = set()
            data_set = {}
            for m in data:
                timestamp = m["_time"].split(".")[0]
                curr_time = datetime.strptime(timestamp, dbq.DATE_FORMAT)
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
                metric_time = t.strftime("%H:%M:%S")
                dram_metric = (
                    math.floor(
                        (
                            data_set[t]["dram_usage_mb"]
                            / data_set[t]["dram_capacity_mb"]
                        )
                        * 100
                    )
                    if data_set[t]["dram_usage_mb"] > 0
                    else 0
                )
                cxl_metric = (
                    math.floor(
                        (
                            data_set[t]["cxl_usage_mb"]
                            / data_set[t]["cxl_capacity_mb"]
                        )
                        * 100
                    )
                    if data_set[t]["cxl_usage_mb"] > 0
                    else 0
                )
                export_data.append([metric_time, dram_metric, cxl_metric])
            return export_data
        except Exception as error:
            print(f"ERROR during recent_dram vs cxl processing {str(error)}")

    def get_cpu_mem_usage(self):
        params = {"_desc": True}

        tables = self.read_client.query(
            f"""
            from(bucket:"internal")
                |> range(start: -60s)
                |> sort(columns: ["_time"], desc: _desc)
                |> filter(fn: (r) => r["source"] == "{self.selected_host}")
                |> filter(fn: (r) => r._field == "cpu_usage"
                 or r._field == "dram_usage_mb"
                 or r._field == "dram_capacity_mb"
                 or r._field == "cxl_usage_mb"
                 or r._field == "cxl_capacity_mb")
        """,
            params=params,
        )

        output = tables.to_json()
        data = json.loads(output)

        try:
            time_set = set()
            data_set = {}
            for m in data:
                timestamp = m["_time"].split(".")[0]
                curr_time = datetime.strptime(timestamp, dbq.DATE_FORMAT)
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
                    data_set[t]["dram_capacity_mb"]
                    + data_set[t]["cxl_capacity_mb"]
                )
                export_data.append(
                    [
                        t.strftime("%H:%M:%S"),
                        (
                            (
                                (
                                    (
                                        data_set[t]["dram_usage_mb"]
                                        + data_set[t]["cxl_usage_mb"]
                                    )
                                    / (
                                        data_set[t]["dram_capacity_mb"]
                                        + data_set[t]["cxl_capacity_mb"]
                                    )
                                )
                                * 100
                            )
                            if capacity_sum > 0
                            else 0
                        ),
                        data_set[t]["cpu_usage"],
                    ]
                )
            return export_data
        except Exception as error:
            print(f"failed to send recent CPU vs mem usage data {str(error)}")

    def get_memserver_capacity(self):
        params = {"_desc": True}

        tables = self.read_client.query(
            f"""
            from(bucket:"internal")
                |> range(start: -10s)
                |> filter(fn: (r) => r["source"] == "{self.selected_host}")
                |> filter(fn: (r) => r._field == "cxl_capacity_mb"
                 or r._field == "dram_capacity_mb")
                |> keep(columns: ["_field", "_value"])
                |> last()
        """,
            params=params,
        )

        output = tables.to_json()
        data = json.loads(output)

        if self.mock:
            return [["Memtype", "Capacity Used"], ["CXL", 512], ["DRAM", 256]]
        else:
            try:
                export_data = [["Memtype", "Capacity Used"]]
                for metric in data:
                    memtype = metric["_field"].split("_")[0].upper()
                    export_data.append(
                        [memtype, helper.mb_to_GB(metric["_value"])]
                    )

                return export_data

            except Exception as e:
                print(f"Failed to process memserver capacity data {str(e)}")

    def get_membox_usage(self):
        params = {"_desc": True}

        tables = self.read_client.query(
            """
            from(bucket:"internal")
                |> range(start: -60s)
                |> filter(fn: (r) => r._field == "cxl_usage_mb")
                |> keep(columns: ["_field", "_value", "_time"])
                |> aggregateWindow
                (column: "_value", every: 6s, fn: sum, createEmpty: false)
                |> yield(name: "sum")
        """,
            params=params,
        )

        output = tables.to_json()
        data = json.loads(output)

        try:
            time_set = set()
            data_set = {}
            for m in data:
                curr_time = datetime.strptime(
                    m["_time"].split("+")[0].split(".")[0], dbq.DATE_FORMAT
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
                export_data.append(
                    [t.strftime("%H:%M:%S"), data_set[t]["cxl_usage_mb"]]
                )
            return export_data
        except Exception as error:
            # pragma: no cover
            print(f"failed to process membox usage data: {str(error)}")

    def get_membox_bandwidth(self):
        """
        Calculate membox bandwidth:
        Upstream port bandwidth: 8 lanes per port * 4GB/s per
        lane = 32GB per upstream port
        Max bandwidth: 512GB
        """
        max_bandwidth = 512
        default_upstream_ports = 1
        default_used_percentage_bandwidth = 0
        if self.mock:
            # Return mock data if in mock mode
            return {
                "max_bandwidth": max_bandwidth,
                "used_bandwidth": 32 * default_upstream_ports,
                "used_percentage_bandwidth": default_used_percentage_bandwidth,
            }
        try:
            # Fetch the number of upstream ports
            upstream_ports_result = helper.count_host_upstream_ports()
            num_upstream_ports = (
                upstream_ports_result.get(
                    "num_upstream_ports", default_upstream_ports
                )
                if upstream_ports_result
                else default_upstream_ports
            )
            # Calculate used bandwidth and percentage
            used_bandwidth = 32 * num_upstream_ports
            used_percentage_bandwidth = (
                math.floor((used_bandwidth / max_bandwidth) * 100)
                if max_bandwidth > 0
                else default_used_percentage_bandwidth
            )
            return {
                "max_bandwidth": max_bandwidth,
                "used_bandwidth": used_bandwidth,
                "used_percentage_bandwidth": used_percentage_bandwidth,
            }
        except Exception as error:
            print(f"Error processing membox bandwidth: {str(error)}")
            return {
                "max_bandwidth": max_bandwidth,
                # Default to 0 in case of error
                "used_bandwidth": 32,
                "used_percentage_bandwidth": default_used_percentage_bandwidth,
            }

    def get_attached_devices_count(self):
        if self.mock:
            payload = MOCK_CXL_SETUP
            return {"num_hosts": 1, "num_cxl_devices": 2}
        else:
            try:
                headers = {
                    "accept": dbq.APPLICATION_JSON,
                    "Content-Type": dbq.APPLICATION_JSON,
                }
                # Fetch the result
                result = helper.count_attached_devices()
                if not result:
                    # Default values
                    num_hosts = 0
                    num_cxl_devices = 0
                else:
                    num_hosts = result["num_hosts"]
                    num_cxl_devices = result["num_cxl_devices"]
            except Exception as e:
                print(f"Error while fetching attached devices count: {e}")
                # Default values in case of an exception
                num_hosts = 0
                num_cxl_devices = 0
        return {"num_hosts": num_hosts, "num_cxl_devices": num_cxl_devices}

    def get_membox_capacity(self):
        if self.mock:
            payload = MOCK_CXL_SETUP
            return {
                "total_capacity": 512,
                "used_capacity": 256,
                "used_capacity_percentage": 67,
            }
        else:
            try:
                result = helper.fetch_memory_capacity()
                if not result:
                    # Default values for failed query
                    used_capacity = 0
                    total_capacity = 0
                    used_capacity_percentage = 0
                else:
                    # Extract values from the query result
                    used_capacity = int(result["used_capacity"])
                    total_capacity = int(result["total_capacity"])
                    used_capacity_percentage = int(
                        float(result["used_percentage"])
                    )
            except Exception as e:
                print(f"Error fetching memory capacity: {e}")
                # Default values for exceptions
                used_capacity = 0
                total_capacity = 0
                used_capacity_percentage = 0
        return {
            "total_capacity": total_capacity,
            "used_capacity": used_capacity,
            "used_capacity_percentage": used_capacity_percentage,
        }
