import errno
import os
import os.path
import sys
import pandas as pd
import time

sys.path.append(  # noqa: E402
    os.path.abspath(os.path.join(  # noqa: E402
        os.path.dirname(__file__), '..')))  # noqa: E402
from backend.cognos_influxdb_client import CognosInfluxDBClient
from backend.helper import *


def read_input(filename):
    data = []
    with open(filename, "r") as file:

        for line in file:
            # Remove "metric:" prefix and convert to dictionary
            record = eval(line.strip().replace("metric:", ""))
            data.append(record)

    return data


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: subscriber.py <publisher_output_file>')
        sys.exit(1)

    if not os.path.exists(sys.argv[1]):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                sys.argv[1])

    data = read_input(sys.argv[1])
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
                time.sleep(0.5)

                # write event to influxdb
                dbobj.write_cognos_event(row.to_dict())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
