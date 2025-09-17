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
# pragma: no cover
except Exception as error:
    print(
        f"Unable to retrieve collector configs: {str(error)}",
        file=sys.stderr
    )
    raise RuntimeError()

REQUEST_HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json",
}

TAG_KEYS = [
    "cluster_name", "node_name", "domain", "feature_name",
    "category", "severity", "source", "source_type"
]


def esc(s):
    return str(s).replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def esc_str(s):
    return '"' + str(s).replace("\\", r"\\").replace('"', r'\"') + '"'


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


if __name__ == "__main__":
    get_cognos_events()
