import argparse
import errno
import os
import os.path
import sys
import pandas as pd
import time
import zmq
import json
import requests
import threading
import ipaddress
import re

sys.path.append(  # noqa: E402
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../..")  # noqa: E402
    )
)  # noqa: E402
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient
from cognos.backend.sqlite_client import SqliteClient
from cognos.backend.helper import *


def is_valid_ip_or_fqdn(node_id):
    """
    Check If a node_id is a valid IPv4/IPv6, localhost
    or a Fully Qualified Domain Name (FQDN).
    """
    # explicitly allow 'localhost'
    if node_id.lower() == "localhost":
        return True

    try:
        ipaddress.ip_address(node_id)
        return True
    except ValueError:
        # not an ipaddress
        pass

    # Check if it's a valid FQDN
    fqdn_regex = re.compile(
        r"^(?=.{1,255}$)([a-zA-Z0-9-]{1,63}\.)+[a-zA-Z]{2,}$"
    )
    if fqdn_regex.match(node_id):
        return True

    # invalid ip/fqdn
    return False


def validate_file(file_path):
    """
    Validate if a file exists.
    """
    if not os.path.exists(file_path):
        raise argparse.ArgumentTypeError(
            f"The file '{file_path}' does not exist."
        )
    return file_path


def read_input(filename):
    data = []
    with open(filename, "r") as file:

        for line in file:
            # Remove "metric:" prefix and convert to dictionary
            record = eval(line.strip().replace("metric:", ""))
            data.append(record)

    return data


def load_and_validate_config(config_file):
    """
    Load and validate the YAML configuration file.
    """
    try:
        with open(config_file, "r") as file:
            config = json.load(file)

        # Replace place holders with env variable values
        for key, value in config.items():
            if (
                isinstance(value, str)
                and value.startswith("{")
                and value.endswith("}")
            ):
                # Extract the variable name from {VAR}
                env_var = value[1:-1]
                # Replace with env value or keep as is
                config[key] = os.getenv(env_var, value)

        # Validate required fields
        required_fields = [
            "rest_ip",
            "rest_port",
            "publisher_port",
            "publisher_topic",
            "interval",
            "cluster_id",
        ]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field in config: {field}")
        # Ensure valid types
        if not isinstance(config["rest_port"], int) or not isinstance(
            config["publisher_port"], int
        ):
            raise ValueError("Ports must be integers.")
        if not isinstance(config["interval"], int):
            raise ValueError("Interval must be an integer.")
        if not isinstance(config["rest_ip"], str) or not isinstance(
            config["publisher_topic"], str
        ):
            raise ValueError(
                "Rest IP, Publisher Topic, and Cluster ID must be strings."
            )
        return config
    except FileNotFoundError:
        print(f"Config file '{config_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON config: {e}")
        sys.exit(1)
    except ValueError as ve:
        print(f"Invalid configuration: {ve}")
        sys.exit(1)


def get_node_ids(rest_ip, rest_port, cluster_id):
    """
    Fetches the list of node IDs by calling the controller API.
    """
    url = f"http://{rest_ip}:{rest_port}/api/v1/list_cluster_nodes"
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {"cluster_id": cluster_id}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        # Extract node IDs from the response
        node_info = data.get("clusterInfo", [{}])[0].get("nodeInfo", [])
        return [
            node["nodeId"]
            for node in node_info
            if is_valid_ip_or_fqdn(node["nodeId"])
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error calling API: {e}")
        return []


def mock_subscription(mock_file, interval, stop_condition=None) -> None:
    """
    Handles mock subscription by reading from a mock
    file and simulating events.
    """
    # Check if the mock file exists
    if not os.path.exists(mock_file):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), mock_file
        )
    try:
        data = read_input(mock_file)
    except Exception as e:
        print(f"Error reading input file: {e}")
        sys.exit(1)
        return

    # Check if data exists and convert to DataFrame
    if not data:
        print("No data to send to InfluxDB!")
        return

    df = pd.DataFrame(data)

    if df.empty:
        print("DataFrame is empty, no data to send to InfluxDB!")
        return
    # Create an instance of CognosInfluxDBClient
    svk_data_path = "/var/lib/svk/cognos_subscriber.db"
    sql_client = SqliteClient(svk_data_path=svk_data_path, in_mem=True)
    dbobj = CognosInfluxDBClient(sql_client)

    # Set the default stop_condition to an always False condition
    stop_condition = stop_condition or (lambda: False)

    try:
        while not stop_condition():
            for _, row in df.iterrows():
                # Get the current timestamp
                current_time = pd.Timestamp.now()
                # Convert to UTC
                utc_time = current_time.tz_localize("UTC")
                # Add the current timestamp to the row
                row["timestamp"] = utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                # Sleep for the specified interval
                time.sleep(interval)
                # Write event to InfluxDB
                dbobj.write_cognos_event(row.to_dict())
                print(row.to_dict())
    except KeyboardInterrupt:
        print("Process interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred during processing: {e}")
        sys.exit(1)


def zeromq_subscription(
    node_id, publisher_port, topic, interval, stop_condition=None
) -> None:
    """
    Subscribe to ZeroMQ for each node using its node ID and publisher port.
    Write data to InfluxDB.
    """
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    try:
        # Connect to the publisher
        socket.connect(f"tcp://{node_id}:{publisher_port}")
        print(f"Successfully connected to publisher for node: {node_id}:{publisher_port}")
    except zmq.ZMQError as e:
        print(
            f"Failed to connect to server at {node_id}:{publisher_port}: {e}"
        )
        sys.exit(1)
        return
    socket.setsockopt_string(zmq.SUBSCRIBE, topic)

    # Create an instance of CognosInfluxDBClient
    svk_data_path = "/var/lib/svk/cognos_subscriber.db"
    sql_client = SqliteClient(svk_data_path, in_mem=True)
    db_client = CognosInfluxDBClient(sql_client)

    # Set the default stop_condition to always False if none is provided
    stop_condition = stop_condition or (lambda: False)
    try:
        while not stop_condition():
            try:
                print("Attempting to receive data....")
                # Receive a message from the server
                string = socket.recv()
                payload = str(string, "utf-8")
                print(f"Data received... {payload}")
                # Ensure payload contains colon (':') to split
                if ":" not in payload:
                    print("Invalid message format: missing ':' separator")
                    continue
                # Split the topic and message data
                index = payload.index(":")
                topic, messagedata = payload[:index], payload[index+1:]
                # Parse the message data as JSON
                try:
                    data = json.loads(messagedata)
                except json.JSONDecodeError as je:
                    print(f"Failed to parse message data as JSON: {je}")
                    continue
                # Write the event to InfluxDB
                db_client.write_cognos_event(data)
                print(data)
            except zmq.ZMQError as zmqe:
                print(f"ZMQ error during message reception: {zmqe}")
                break
    except KeyboardInterrupt:
        print("Process interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        socket.close()
        context.term()


def main(config_file=None, mock_file=None):
    """
    Main function to manage subscriptions in mock or non-mock mode.
    """
    if mock_file:
        # Mock mode: no YAML file needed
        print(f"Running in mock mode with file: {mock_file}")
        # Default interval for mock
        mock_subscription(mock_file=mock_file, interval=5)
    elif config_file:
        # Non-mock mode: YAML file is required
        print(f"Running in non-mock mode with config: {config_file}")
        config = load_and_validate_config(config_file)
        # Extract configuration values
        rest_ip = config["rest_ip"]
        rest_port = config["rest_port"]
        publisher_port = config["publisher_port"]
        publisher_topic = config["publisher_topic"]
        interval = config["interval"]
        cluster_ids = config["cluster_id"]
        node_ids = []
        for cid in cluster_ids:
            # Fetch node ID from the controller
            node_ids.extend(get_node_ids(rest_ip, rest_port, cid))

        if not node_ids:
            print("No node IDs retrieved. Exiting.")
            sys.exit(1)
        # Subscribe to ZeroMQ for each node ID
        threads = []
        for node_id in node_ids:
            print(f"Subscribing to node: {node_id}")
            t = threading.Thread(
                target=zeromq_subscription,
                args=(node_id, publisher_port, publisher_topic, interval),
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
    else:
        print("Error: Either a config file or a mock file must be provided.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", help="YAML conf", type=validate_file, required=False
    )
    parser.add_argument(
        "--mock", help="Path to the mock data file", required=False
    )
    args = parser.parse_args()
    main(config_file=args.config, mock_file=args.mock)
