import argparse
import errno
import os
import os.path
import sys
import pandas as pd
import time

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


def main(interval, mock_file=None) -> None:
    if len(sys.argv) < 2:
        print('usage: subscriber.py <publisher_output_file>')
        sys.exit(1)

    if not os.path.exists(mock_file):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                mock_file)

    data = None
    if mock_file:
        data = read_input(mock_file)
    if data:
        # Create a DataFrame
        df = pd.DataFrame(data)
    else:
        print("No data to send to influxDB!!")
        sys.exit(0)

    # create an instance of CognosInfluxDBClient
    dbobj = CognosInfluxDBClient()

    try:
        while True:

            for _, row in df.iterrows():
                # Get the current timestamp
                current_time = pd.Timestamp.now()

                # Convert to UTC
                utc_time = current_time.tz_localize('UTC')

                # Add current timestamp
                row["timestamp"] = utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")

                # Sleep for 5 seconds
                time.sleep(interval)

                # write event to influxdb
                dbobj.write_cognos_event(row.to_dict())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mock', type=str)
    parser.add_argument('--interval', nargs='?', default=5, required=False)
    args = parser.parse_args()
    if args.interval:
        main(args.interval, mock_file=(args.mock if args.mock else None))
    else:
        main(5, mock_file=(args.mock if args.mock else None))
