import argparse
import errno
import os
import os.path
import sys
import pandas as pd
import time
import zmq
import json

sys.path.append(  # noqa: E402
    os.path.abspath(os.path.join(  # noqa: E402
        os.path.dirname(__file__), '../..')))  # noqa: E402
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient
from cognos.backend.helper import *


def read_input(filename):
    data = []
    with open(filename, "r") as file:

        for line in file:
            # Remove "metric:" prefix and convert to dictionary
            record = eval(line.strip().replace("metric:", ""))
            data.append(record)

    return data


def mock_subscription(interval) -> None:

    # Check if the file exists
    if not os.path.exists(sys.argv[1]):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
              sys.argv[1])
    try:
        data = read_input(sys.argv[1])
    except Exception as e:
        print(f"Error reading input file: {e}")
        sys.exit(1)

    # Check if data exists and convert to DataFrame
    if not data:
        print("No data to send to InfluxDB!")
        return
    df = pd.DataFrame(data)

    if df.empty:
        print("DataFrame is empty, no data to send to InfluxDB!")
        return

    # Create an instance of CognosInfluxDBClient
    dbobj = CognosInfluxDBClient()

    try:
        while True:
            for _, row in df.iterrows():
                # Get the current timestamp
                current_time = pd.Timestamp.now()
                # Convert to UTC
                utc_time = current_time.tz_localize('UTC')
                # Add the current timestamp to the row
                row["timestamp"] = utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                # Sleep for the specified interval
                time.sleep(interval)
                # Write event to InfluxDB
                dbobj.write_cognos_event(row.to_dict())
    except KeyboardInterrupt:
        print("Process interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred during processing: {e}")
        sys.exit(1)


def zeromq_subscription(hostname, topic, interval) -> None:

    try:
        # Parse hostname and port
        if ':' not in hostname:
            raise ValueError("Invalid <hostname:port> format.")
        host, port = hostname.split(":")
        # Ensure the port is a valid integer
        port = int(port)
    except ValueError as ve:
        print(f"Error parsing hostname or port: {ve}")
        sys.exit(1)

    # Initialize ZMQ context and socket
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    try:
        # Connect to the server
        socket.connect(f"tcp://{host}:{port}")
    except zmq.ZMQError as e:
        print(f"Failed to connect to server: {e}")
        sys.exit(1)

    # Subscribe to the provided topic
    socket.setsockopt_string(zmq.SUBSCRIBE, topic)

    # Create an instance of CognosInfluxDBClient
    dbobj = CognosInfluxDBClient()
    try:
        while True:
            try:
                # Receive a message from the server
                string = socket.recv()
                # Convert the message to string format
                payload = str(string, 'utf-8')
                # Ensure payload contains colon (':') to split
                if ':' not in payload:
                    print("Invalid message format: missing ':' separator")
                    continue
                # Split the topic and message data
                index = payload.index(':')
                topic, messagedata = payload[:index], payload[index + 1:]
                # Parse the message data as JSON
                try:
                    data = json.loads(messagedata)
                except json.JSONDecodeError as je:
                    print(f"Failed to parse message data as JSON: {je}")
                    continue
                # Write the event to InfluxDB
                dbobj.write_cognos_event(data)
            except zmq.ZMQError as zmqe:
                print(f"ZMQ error during message reception: {zmqe}")
                break
    except KeyboardInterrupt:
        print("Process interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)


def main(hostname=None, topic=None, interval=5, use_mock=False):
    if use_mock:
        # Check if enough arguments are passed
        if len(sys.argv) < 3:
            print('Usage: subscriber.py <publisher_output_file> --mock <i>')
            sys.exit(1)
        mock_subscription(interval)
    else:
        if len(sys.argv) < 3:
            print('Usage: subscriber.py <hostname:port> <topic> <interval>')
            sys.exit(1)
        elif hostname and topic:
            zeromq_subscription(hostname, topic, interval)
        else:
            print("Hostname and topic are required for ZeroMQ subscriber.")
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # Add common arguments
    parser.add_argument('-i', '--interval', help="sleep", type=int, default=5)
    parser.add_argument('--mock', action='store_true', help="mock flag")

    # Positional arguments are optional depending on --mock flag
    parser.add_argument('hostname', nargs='?', help="Hostname:port for ZeroMQ")
    parser.add_argument('topic', nargs='?', help="Topic to subscribe to")
    args = parser.parse_args()

    if args.mock:
        main(interval=args.interval, use_mock=True)
    else:
        if args.hostname and args.topic:
            main(args.hostname, args.topic, args.interval)
        else:
            print("Error: For ZeroMQ sub, hostname & topic must be provided.")
