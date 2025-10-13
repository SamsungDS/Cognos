import json
import os
import requests
import sys
import time


COGNOS_NORTHBOUND_ENDPOINT = ""
config_file_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config",
    "config.json"
)

try:
    with open(config_file_path, "r") as config_file:
        configs = json.load(config_file)
        if configs.get("cognos_endpoint"):
            COGNOS_NORTHBOUND_ENDPOINT = configs.get("cognos_endpoint")
            if not COGNOS_NORTHBOUND_ENDPOINT[-1] == "/":
                COGNOS_NORTHBOUND_ENDPOINT += "/"
# pragma: no cover
except Exception as error:
    print(
        (
            f"Unable to retrieve collector configs: {error}. "
            f"Config file path: {config_file_path}"
        ),
        file=sys.stderr
    )
    raise RuntimeError()

REQUEST_HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
}

TAG_KEYS = [
    "cluster_name", "node_name", "domain", "msg", "feature_name",
    "category", "severity", "source", "source_type"
]


def esc(s):
    return str(s).replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def esc_str(s):
    return '"' + str(s).replace("\\", r"\\").replace('"', r'\"') + '"'


def get_nodes():
    request_args = {"command_name": "list_nodes"}
    response = requests.post(
        COGNOS_NORTHBOUND_ENDPOINT + "nodes",
        json=request_args,
        headers=REQUEST_HEADERS
    )
    output = response.json()
    payload = json.loads(output['commandResponse'])
    nodes = []
    for node in payload['node_info']:
        nodes.append(node["node_name"])
    return nodes


def get_clusters():
    request_args = {"command_name": "list_clusters"}
    response = requests.post(
        COGNOS_NORTHBOUND_ENDPOINT + "clusters",
        json=request_args,
        headers=REQUEST_HEADERS
    )
    output = response.json()
    payload = json.loads(output['commandResponse'])
    return (
        [
            v for cluster in payload["clusters"]
            for v in cluster.values()
        ]
    )


def get_cluster_nodes(cluster):
    request_args = {"command_name": "list_nodes_in_cluster"}
    response = requests.post(
        COGNOS_NORTHBOUND_ENDPOINT + "clusters/" + cluster,
        json=request_args,
        headers=REQUEST_HEADERS
    )
    output = response.json()
    payload = json.loads(output["commandResponse"])
    # print("CLuster nodes: ")
    # print(payload)
    # {'clusters': [{'cluster_name': 'CL_ID_1', 'nodes': [{'node_name':
    #  'node_1', 'status': 'online'}]}]}
    nodes = []
    for c in payload['clusters']:
        for node in c['nodes']:
            nodes.append(node['node_name'])
    # print(f"Nodes in cluster: {cluster} are {nodes}")
    return nodes


def get_device_ids(cluster, node):
    # need to get device ids from both direct and remote
    device_ids = []

    # get direct device ids
    # request_args = {"command_name"}
    request_body = {
        "cluster_name": cluster,
        "command_name": "list_devices",
        "command_params": json.dumps({"device_id": []})
    }
    response = requests.post(
        COGNOS_NORTHBOUND_ENDPOINT + f"nodes/{node}/features/cxl",
        json=request_body,
        headers=REQUEST_HEADERS
    )
    devices = (
        json.loads(response.json()['response'][0])['devices']
    )
    # print(f"DEVICES: {devices}")
    for dev in devices:
        device_ids.append(dev['device_id'])
    # print(f"DEVICE IDS: {device_ids}")
    return device_ids


def get_cxl_device_metrics(cluster, node, device_id):
    request_body = {
        "cluster_name": cluster,
        "command_name": "get_device_metrics",
        "command_params": json.dumps({
            "domain_id": "",
            "device_id": device_id
        })
    }
    response = requests.post(
        COGNOS_NORTHBOUND_ENDPOINT + f"nodes/{node}/features/cxl",
        json=request_body,
        headers=REQUEST_HEADERS
    )
    device_metrics = json.loads(response.json()['response'][0])
    return device_metrics


def get_cognos_device_stats():
    # step 1: Get Topology
    device_stats = []
    clusters = get_clusters()
    topology = []  # [{cluster: [{node: [device_ids]}]}]
    i = 0
    for cluster in clusters:
        topology.append({cluster: []})
        cluster_nodes = get_cluster_nodes(cluster)
        for node in cluster_nodes:
            device_ids = get_device_ids(cluster, node)
            topology[i][cluster].append({node: device_ids})
        i += 1

    # step 2: Get all devices stats for all device IDs
    for cluster in topology:
        for cluster_name, nodes in cluster.items():
            for node in nodes:
                for node_name, device_ids in node.items():
                    for id in device_ids:
                        device_stats.append(
                            get_cxl_device_metrics(cluster_name, node_name, id)
                        )

    # step 3: Format data into flux line protocol
    convert_stats_to_influx_line_protocol(device_stats)
    return


def get_cognos_events():
    request_url = COGNOS_NORTHBOUND_ENDPOINT + "clusters/events"
    request_args = {
        "command_name": "cluster_events"
    }
    try:
        response = requests.post(
            request_url, json=request_args, headers=REQUEST_HEADERS
        )
        if response.ok:
            try:
                events = json.loads(response.json()['response'])
                convert_data_to_influx_line_protocol(events)
            except Exception as error:
                print(f"Failed to parse cognos event request", file=sys.stderr)
        else:
            raise requests.ConnectionError
    except requests.ConnectionError as error:
        print(f"Connection Error: failed to get cognos event: {str(error)}",
              file=sys.stderr)
    except Exception as error:
        print(f"ERROR: {str(error)}", file=sys.stderr)


def valid_event_structure(event):
    # TODO: validate incoming event structures are correct
    pass


def convert_stats_to_influx_line_protocol(stats):
    for stat in stats:
        ts = int(time.time()) * 1_000_000_000
        tags = []
        for k in TAG_KEYS:
            tag = stat.get(k)
            if tag is not None:
                tags.append(f"{esc(k)}={esc(tag)}")
        tag_str = ",".join(tags)

        # get fields from observations
        fields = []
        obs = stat.get("observations", {})
        for k, v in obs.items():
            k_esc = esc(k)
            if isinstance(v, bool):
                fields.append(f"{k_esc}={'true' if v else 'false'}")
            elif isinstance(v, int):
                fields.append(f"{k_esc}={v}i")
            elif isinstance(v, float):
                fields.append(f"{k_esc}={esc_str(v)}")
        if not fields:
            return
        print(f"stats,{tag_str} " + ",".join(fields) + f" {ts}")


def convert_data_to_influx_line_protocol(events):
    for event in events:
        # get epoch timestamp and convert to ns for influxdb
        # TODO: get ts directly once feature modules currently set epoch
        # ts = int(event['event_payload']['timestamp']) * 1_000_000_000
        ts = int(time.time()) * 1_000_000_000

        # get tags
        tags = []
        for k in TAG_KEYS:
            payload = (
                event['event_header']
                if k in event['event_header']
                else event['event_payload']
            )
            tag = payload.get(k)
            if tag is not None:
                tags.append(f"{esc(k)}={esc(tag)}")
        tag_str = ",".join(tags)

        # get fields from observations
        fields = []
        obs = event['event_payload'].get("observations", {})
        for k, v in obs.items():
            k_esc = esc(k)
            if isinstance(v, bool):
                fields.append(f"{k_esc}={'true' if v else 'false'}")
            elif isinstance(v, int):
                fields.append(f"{k_esc}={v}i")
            elif isinstance(v, float):
                fields.append(f"{k_esc}={esc_str(v)}")
        if not fields:
            return
        print(f"events,{tag_str} " + ",".join(fields) + f" {ts}")


def main():
    get_cognos_events()
    get_cognos_device_stats()


if __name__ == "__main__":
    get_cognos_events()
    get_cognos_device_stats()
