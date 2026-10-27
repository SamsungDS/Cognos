#Prerequisites

Ensure the following dependencies are installed:

pip install --upgrade pip
pip install pyzmq
pip install 'influxdb-client[ciso]'

#Subscriber Configuration File

Ensure the `sub.yaml` configuration file is available in the subscriber folder. This YAML file is dynamically loaded by environment variables when the `cognos.subscriber` service is executed.

Note: To test the subscriber module independently, the `sub.yaml` file can be manually edited.
make sure to export variables for manual edit. 
export CAL_IP=127.0.0.1
export TOPIC=metric 

#Mock Subscriber

The `mock_subscription` function reads the static file `subscriber/mock_publisher_events.output`, which contains published events related to the CXL memory box. It updates the timestamp to the current UTC time and loads the data into InfluxDB every 5 seconds.

#How to Execute the Mock Subscriber:

/usr/bin/python3 cognos/subscriber/sub_client.py --mock subscriber/mock_publisher_events.output

#ZeroMQ Subscriber

The `zeromq_subscription` function continuously accepts events from the `nodeId/ip_address` (obtained from rest api call `list_cluster_node`) where the publisher process publishes events.

#How to Execute the ZeroMQ Subscriber:

/usr/bin/python3 cognos/subscriber/sub_client.py --config sub.yaml

#How to Execute on Screen

1. Create a screen session 

   `screen -S session_name`

2. Trigger the Subscriber Process:

   - Refer to the Mock Subscriber and ZeroMQ Subscriber sections for the respective execution commands.

3. Detach from the Session:

   `screen -d`

#How to Run Test Cases

To execute test cases for the subscriber program, use the following command:

/usr/bin/python3 -m pytest --cov cognos.subscriber --cov-report=term --cov-report=html subscriber/test/sub_test.py

