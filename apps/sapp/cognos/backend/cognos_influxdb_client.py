from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from datetime import datetime
import json
import math
import os
import requests
import sys
from typing import Dict, List

sys.path.append(
    os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), "..")
    )
)  # noqa: E402
import cognos.backend.helper as helper
import cognos.backend.db_query_constants as dbq
from cognos.backend.mock_constants import MOCK_CXL_SETUP, MOCK_EVENTS

import cognos.backend.mock_metrics as mock_metrics


class CognosInfluxDBClient:
    """
    Direct InfluxDB Client for querying Cognos Events
    """
    def __init__(
        self, sql_client, url=None, token=None, org=None,
        bucket=None, mock=False,
    ):
        self.sql_client = sql_client
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

    def write_cognos_event(self, event: Dict) -> None:
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

    def query_cognos_events(self, time_window: int) -> List:
        """
        Returns all cognos events within a given time window
        """
        return self.read_client.query(
            f'from(bucket:"internal") |> range(start: -{time_window}) '
            "|> last(6)"
        )

    def query_node_cognos_events(self, time_window: int, category: str,
                                 source_type: str, source: str,
                                 event_keys: Dict) -> List:
        """
        Performs a query for a specific node's events

        TODO: Port to new Cognos observability event structure

        {
            domain: <string>,
            category: <string>,
            severity: <string>, (optional)
            source: <string>,
            source_type: <string>,
            timestamp: <timestamp>,
            observations: { <key>: <value> }
        }
        """
        return self.read_client.query(
            f'from(bucket:"internal") |> range(start: -{time_window}) '
            "|> last(6)"
        )

    def get_cognos_device_stats(self, time_in_mins, device, stats_key):
        params = {"_desc": True}

        try:
            tables = self.read_client.query(
                f"""
                    from(bucket: "internal")
                    |> range(start: -{time_in_mins}m)
                    |> filter(
                    fn: (r) => r._measurement == "stats" and
                    r.source == "{device}" and
                    r._field == "{stats_key}"
                    )
                """,
                params=params
            )
            flux_query_output = json.loads(tables.to_json())
            """
            paylaod format
            {
              'device_id1': [[ts, key, value], [ts, key, value], ...],
            }
            """
            device_id = flux_query_output[0]['source']
            time_set = set()
            data_set = {}
            for data_point in flux_query_output:
                timestamp = data_point["_time"].replace("+00:00", "+0000")
                curr_time = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S%z')
                time_set.add(curr_time)
                field = data_point["_field"]
                value = data_point["_value"]
                if curr_time not in data_set:
                    data_set[curr_time] = {field: value}
                elif field not in data_set[curr_time].keys():
                    data_set[curr_time][field] = value

            ordered_timeset = sorted(list(time_set))
            export_data = {device_id: []}
            for t in ordered_timeset:
                metric_time = t.strftime("%H:%M:%S")
                value = data_set[t][stats_key]
                export_data[device_id].append([metric_time, stats_key, value])
            return export_data
        except Exception as error:
            print(
                (
                    f"Failed to query for device stats from InfluxDB: {error}"
                )
            )

    def get_latest_application_event(self, app_pid):
        try:
            tables = self.read_client.query(
                f'''
                from(bucket: "internal")
                    |> range(start: -5m)
                    |> filter(fn: (r) => r._measurement == "events")
                    |> filter(fn: (r) => r.source_type == "application")
                    |> filter(fn: (r) => r.category == "health")
                    |> filter(fn: (r) => r.source =~ /{str(app_pid)}/)
                    |> keep(columns: ["_time", "severity", "msg"])
                    |> group(columns: [])
                    |> sort(columns: ["_time"], desc: true)
                    |> limit(n: 1)
                '''
            )
            flux_query_output = json.loads(tables.to_json())
            print(f"***** LATEST APP EVENT FROM FLUX QUERY ******")
            print(flux_query_output)
            return flux_query_output
        except Exception as error:
            print(f"ERROR testing cognos events: {str(error)}")

    def get_cognos_events_past(self, time_in_mins):
        if self.mock:
            return MOCK_EVENTS

        params = {"_desc": False}
        cols_string = (
            '["_time", "_measurement", "_field", "_value", '
            '"cluster_name", "node_name", "msg", "domain", "feature_name", '
            '"category", "severity", "source", "source_type"]'
        ).strip('\n')
        tags_string = (
            '["cluster_name", "node_name", "domain", "msg", "feature_name", '
            '"category", "severity", "source", "source_type"]'
        )
        flux_query_output = {}
        try:
            tables = self.read_client.query(
                f"""
                from(bucket: "internal")
                    |> range(start: -{time_in_mins}m)
                    |> filter(fn: (r) => r._measurement == "events")
                    |> window(every: 5s)
                    |> map(fn: (r) => ({{
                        r with t: r.t,
                        kv: (
                            "\\\"" + string(v: r._field) +
                            "\\\":\\\"" + string(v: r._value) + "\\\""
                            )
                        }}))
                    |> group(columns: {tags_string})
                    |> reduce(
                        identity: ({{
                            t: time(v: 0),
                            cluster_name: "",
                            node_name: "",
                            domain: "",
                            msg: "",
                            feature_name: "",
                            category: "",
                            severity: "",
                            source: "",
                            source_type: "",
                            payload: ""}}),
                        fn: (r, accumulator) => (({{
                            t: if exists r._stop then r._stop
                                else accumulator.t,
                            cluster_name: r.cluster_name,
                            node_name: r.node_name,
                            domain: r.domain,
                            msg: r.msg,
                            feature_name: r.feature_name,
                            category: r.category,
                            severity: r.severity,
                            source: r.source,
                            source_type: r.source_type,
                            payload: (
                                if accumulator.payload == "" then
                                r.kv else accumulator.payload + "," + r.kv
                            )
                        }}))
                       )
                    |> map(fn: (r) => ({{
                        _time: r.t,
                        cluster_name: r.cluster_name,
                        node_name: r.node_name,
                        domain: r.domain,
                        msg: r.msg,
                        feature_name: r.feature_name,
                        category: r.category,
                        severity: r.severity,
                        source: r.source,
                        source_type: r.source_type,
                        payload: "{{" + r.payload + "}}"
                    }}))

                """,
                params=params
            )
            flux_query_output = json.loads(tables.to_json())
            response_payload = []
            for measurement in flux_query_output:
                point = {
                    "timestamp": measurement['_time'],
                    "msg": measurement['msg'],
                    "payload": measurement['payload'],
                    "cluster_name": measurement['cluster_name'],
                    "node_name": measurement['node_name'],
                    "category": measurement['category'],
                    "domain": measurement['domain'],
                    "severity": measurement['severity'],
                    "source": measurement['source'],
                    "source_type": measurement['source_type'],
                }
                response_payload.append(point)
            return response_payload
        except Exception as error:
            print(
                f"Failed to query for cognos events..: {str(error)}"
            )

    def get_recent_dram_cxl_usage_data(self, cluster="") -> List[List]:
        """
        Returns a series of data points associated with recent DRAM and
        CXL usage data
        """
        if self.mock:
            return mock_metrics.MOCK_RECENT_DRAM_CXL_USAGE
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

    def get_cpu_mem_usage(self, cluster="") -> List[List]:
        """
        Returns a series of data points associated with recent
        CPU and MEM usage data
        """
        if self.mock:
            return mock_metrics.MOCK_GET_CPU_MEM_USAGE

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

    def get_hostview_capacity(self, cluster=""):
        if self.mock:
            return mock_metrics.MOCK_HOSTVIEW_CAPACITY

        try:
            query_nodes = (
                "SELECT DISTINCT(node_name) FROM connections "
                f"WHERE cluster_name = '{cluster}' "
                "and (node_name IS NOT NULL and node_name <> '');"
            )
            query_nodes_result = self.sql_client.exec_fetch_query(
                    query_nodes,
                    tuple()
                )
            cluster_nodes = [x[0] for x in query_nodes_result]
            nodes_flux = json.dumps(cluster_nodes)

            tables = self.read_client.query(
                f'''
                nodes = {nodes_flux}
                from(bucket: "internal")
                |> range(start: -5m)
                |> filter(fn: (r) => r._measurement == "metric"
                    and (r._field == "cxl_capacity_mb" or
                            r._field == "dram_capacity_mb")
                    and r.source_type == "application server"
                )
                |> filter(fn: (r) => contains(
                    value: r.source,
                    set: nodes
                ))
                |> group(columns: ["source", "_field"])
                |> last()
                |> group(columns: ["_field"])
                |> sum(column: "_value")
                |> map(fn: (r) => ({{ r with key: "total" }}))
                |> pivot(
                    rowKey: ["key"],
                    columnKey: ["_field"],
                    valueColumn: "_value"
                )
                |> keep(columns: ["cxl_capacity_mb", "dram_capacity_mb"])
            '''
            )
            flux_query_output = json.loads(tables.to_json())
            dram_capacity = flux_query_output[0]['dram_capacity_mb'] // 1000
            cxl_capacity = flux_query_output[0]['cxl_capacity_mb'] // 1000
            total_capacity = dram_capacity + cxl_capacity

            payload = {
                "hostview_capacity": {
                    "total_capacity": total_capacity,
                },
                "hostview_memserver_capacity": [
                    ["Memtype", "Capacity Used"],
                    ["DRAM", dram_capacity],
                    ["CXL", cxl_capacity],
                ]
            }
            return payload
        except Exception as error:
            print(f"Unable to get host view usage for cluster: {cluster}")
            payload = {
                "hostview_capacity": {
                    "total_capacity": None,
                },
                "hostview_memserver_capacity": [
                    ["Memtype", "Capacity Used"],
                    ["DRAM", None],
                    ["CXL", None],
                ]
            }
            return payload

    def get_memserver_capacity(self, cluster="") -> List[List]:
        """
        Returns a series of data points associated with recent
        Memserver Capacity Data
        """
        if self.mock:
            return mock_metrics.MOCK_MEMSERVER_CAPACITY

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

    def get_hostview_usage(self, cluster=""):
        if self.mock:
            return mock_metrics.MOCK_HOSTVIEW_USAGE

        try:
            query_string = (
                "SELECT DISTINCT(node_name) FROM connections "
                f"WHERE cluster_name = '{cluster}' "
                "and (node_name IS NOT NULL and node_name <> '');"
            )
            sql_query = self.sql_client.exec_fetch_query(
                query_string,
                tuple()
            )
            cluster_nodes = [x[0] for x in sql_query]
            nodes_flux = json.dumps(cluster_nodes)

            tables = self.read_client.query(
                f'''
                nodes = {nodes_flux}
                from(bucket: "internal")
                    |> range(start: -5m)
                    |> filter(fn: (r) =>
                            r._measurement == "metric" and
                            (r._field == "dram_usage_mb"
                                or r._field == "cxl_usage_mb")
                            and r.source_type == "application server"
                        )
                    |> filter(fn: (r) => contains(
                        value: r.source,
                        set: nodes
                    ))
                    |> keep(columns: ["_time", "_value", "source", "_field"])
                    |> group(columns: ["source", "_field"])
                    |> aggregateWindow(every: 5s, fn: last, createEmpty: false)
                    |> group(columns: ["_time", "_field"])
                    |> sum(column: "_value")
                    |> group(columns: ["_time"])
                    |> pivot(
                        rowKey: ["_time"],
                        columnKey: ["_field"],
                        valueColumn: "_value"
                    )
                    |> keep(
                        columns: ["_time", "dram_usage_mb", "cxl_usage_mb"]
                    )
                    |> group()
                    |> sort(columns: ["_time"], desc: true)
                    |> tail(n: 6)
                    |> sort(columns: ["_time"])
                '''
            )
            flux_query_output = json.loads(tables.to_json())
            output = [["Time", "DRAM", "CXL"]]
            for m in flux_query_output:
                curr_time = datetime.strptime(
                        m["_time"].split("+")[0].split(".")[0],
                        "%Y-%m-%dT%H:%M:%S"
                ).strftime("%H:%M:%S")
                output.append(
                    [curr_time, m["dram_usage_mb"], m["cxl_usage_mb"]]
                )
            return output
        except Exception as error:
            print(f"Unable to get host view usage for {cluster}")
            output = [[None, None, None]]
            return output

    def get_membox_usage(self, cluster="") -> List[List]:
        """
        Returns a series of data points associated with recent
        memory box mem usage data
        """
        if self.mock:
            return mock_metrics.MOCK_MEMBOX_USAGE

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

    def get_hostview_bandwidth(self, cluster=""):
        if self.mock:
            return {
                "max_bandwidth": 128.0,
                "used_bandwidth": 32.0,
                "used_percentage_bandwidth": 25.0
            }

        try:
            tables = self.read_client.query(
                f'''
                from(bucket: "internal")
                    |> range(start: -5m)
                    |> filter(fn: (r) => r.cluster_name == "{cluster}")
                    |> filter(fn: (r) => r._measurement == "stats"
                        and (r._field == "used_bandwidth_Bps"
                                or r._field == "total_bandwidth_MBps")
                    )
                    |> filter(fn: (r) => r.source_type == "device")
                    |> toFloat()
                    |> group(
                        columns: [
                            "cluster_name",
                            "node_name",
                            "source",
                            "_field"
                        ]
                    )
                    |> last()
                    |> pivot(
                        rowKey: [
                            "_time",
                            "cluster_name",
                            "node_name",
                            "source"
                        ],
                        columnKey: ["_field"],
                        valueColumn: "_value"
                    )
                    |> group(columns: ["cluster_name", "node_name", "source"])
                    |> reduce(
                        identity: {{totalUsed: 0.0, totalTotal: 0.0}},
                        fn: (r, accumulator) => ({{
                            totalUsed:
                                accumulator.totalUsed + r.used_bandwidth_Bps,
                            totalTotal:
                                accumulator.totalTotal + r.total_bandwidth_MBps
                        }})

                    )
                    |> group()
                    |> reduce(
                        identity: {{totalUsed: 0.0, totalTotal: 0.0}},
                        fn: (r, accumulator) => ({{
                        totalUsed: accumulator.totalUsed + r.totalUsed,
                        totalTotal: accumulator.totalTotal + r.totalTotal
                        }})
                    )
                '''
            )
            flux_query_output = json.loads(tables.to_json())
            # Bps, convert to GBps
            total_used_bw = round(
                flux_query_output[0]['totalUsed'] / 1_000_000_000, 4
            )
            # MBps, convert to GBps
            total_total_bw = round(
                flux_query_output[0]['totalTotal'] / 1000,
                4
            )
            used_bw_percentage = round(
                total_used_bw / total_total_bw * 100,
                2
            )
            payload = {
                "max_bandwidth": total_total_bw,
                "used_bandwidth": total_used_bw,
                "used_percentage_bandwidth": used_bw_percentage
            }
            return payload
        except Exception as error:
            print(f"Unable to get bandwidth data for cluster: {cluster}")
            payload = {
                "max_bandwidth": None,
                "used_bandwidth": None,
                "used_percentage_bandwidth": None
            }
            return payload

    def get_hostview_devices_count(self, cluster=""):
        """
        Output Format:  {"num_cxl_devices":1,"num_hosts":1}
        """
        if self.mock:
            return mock_metrics.MOCK_HOSTVIEW_DEVICES_COUNT

        try:
            num_hosts_query = (
                "SELECT COUNT(DISTINCT(node_name)) FROM "
                "connections WHERE cluster_name = ?"
            )
            num_hosts = (
                self.sql_client.exec_fetch_singlerecord_query(
                    num_hosts_query,
                    (cluster,)
                )
            )
            num_cxl_devices_query = (
                "SELECT COUNT(*) FROM (SELECT DISTINCT node_name, device_id "
                "FROM connections WHERE device_id IS NOT NULL AND "
                "cluster_name = ?);"
            )
            num_cxl_devices = (
                self.sql_client.exec_fetch_singlerecord_query(
                    num_cxl_devices_query,
                    (cluster,)
                )
            )
            payload = {
                "num_cxl_devices": num_cxl_devices,
                "num_hosts": num_hosts
            }
            return payload
        except Exception as error:
            print(f"ERROR: {str(error)}")

    def get_node_bandwidth(self, cluster="") -> dict:
        """
        Returns CXL bandwidth usage data of a single server
        """
        if self.mock:
            return mock_metrics.MOCK_NODE_BANDWIDTH

        # get all applicable CXL devices based on host
        data = self.sql_client.exec_fetch_query(
            "SELECT device_id FROM connections WHERE node_name = ?",
            (self.selected_host,)
        )

        device_ids = []
        for row in data:
            if row and row[0]:
                device_ids.append(int(row[0]))

        flux_devices_list = ", ".join(f'"{d}"' for d in device_ids)

        tables = self.read_client.query(
            f'''
            from(bucket: "internal")
                |> range(start: -5m)
                |> filter(fn: (r) => r._measurement == "stats"
                    and (r._field == "used_bandwidth_Bps"
                            or r._field == "total_bandwidth_MBps")
                )
                |> filter(fn: (r) => r.source_type == "device")
                |> filter(fn: (r) =>
                    contains(
                        value: r.source,
                        set: [{flux_devices_list}]
                    )
                )
                |> toFloat()
                |> group(columns: ["source", "_field"])
                |> last()
                |> pivot(
                    rowKey: ["_time", "source"],
                    columnKey: ["_field"],
                    valueColumn: "_value"
                )
                |> group()
                |> reduce(
                    identity: {{totalUsed: 0.0, totalTotal: 0.0}},
                    fn: (r, accumulator) => ({{
                        totalUsed:
                            accumulator.totalUsed + r.used_bandwidth_Bps,
                        totalTotal:
                            accumulator.totalTotal + r.total_bandwidth_MBps
                    }})

                )
            '''
        )
        flux_query_output = json.loads(tables.to_json())
        # Bps, convert to GBps
        total_used_bw = round(
            flux_query_output[0]['totalUsed'] / 1_000_000_000, 4
        )
        # MBps, convert to GBps
        total_total_bw = round(flux_query_output[0]['totalTotal'] / 1000, 4)
        used_bw_percentage = round(total_used_bw / total_total_bw * 100, 2)
        payload = {
            "max_bandwidth": total_total_bw,
            "used_bandwidth": total_used_bw,
            "used_percentage_bandwidth": used_bw_percentage
        }
        return payload

    def get_attached_devices_count(self, cluster="") -> Dict:
        """
        Returns the total # of devices in the cognos system
        """
        if self.mock:
            payload = MOCK_CXL_SETUP
            return {"num_hosts": 1, "num_cxl_devices": 2}
        else:
            try:
                num_hosts = self.sql_client.exec_fetch_singlerecord_query(
                    "SELECT COUNT(DISTINCT(node_name)) FROM connections;",
                    tuple()
                )
                num_cxl_devices = (
                    self.sql_client.exec_fetch_singlerecord_query(
                        "SELECT COUNT(DISTINCT(device_id)) "
                        "FROM connections;",
                        tuple()
                    )
                )
            except Exception as e:
                print(f"Error while fetching attached devices count: {e}")
                # Default values in case of an exception
                num_hosts = 0
                num_cxl_devices = 0
        return {"num_hosts": num_hosts, "num_cxl_devices": num_cxl_devices}

    def get_membox_capacity(self, cluster="") -> Dict:
        """
        Returns Memory Box memory capacity and usage data
        """
        if self.mock:
            payload = MOCK_CXL_SETUP
            return {
                "total_capacity": 512,
                "used_capacity": 256,
                "used_capacity_percentage": 50,
            }
        else:
            try:
                total_capacity = (
                    self.sql_client.exec_fetch_singlerecord_query(
                        "SELECT SUM(mem_capacity) as total_capacity "
                        "FROM devices;",
                        tuple()
                    )
                )
                total_capacity = (
                    round(total_capacity / 1000000000, 2)
                    if total_capacity
                    else 0
                )

                used_capacity = (
                    self.sql_client.exec_fetch_singlerecord_query(
                        "SELECT SUM(mem_capacity) FROM devices "
                        "WHERE id IN "
                        "(SELECT device_id FROM connections);",
                        tuple()
                    )
                )
                used_capacity = (
                    round(used_capacity / 1000000000, 2)
                    if used_capacity
                    else 0
                )

                used_capacity_percentage = (
                    float((used_capacity / total_capacity) * 100)
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
