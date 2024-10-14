#!/bin/bash

# Function to check if a machine is online using ping
check_ping() {
    local host="$1"
    if ping -c 1 "$host" &> /dev/null; then
        echo "Ping to $host successful."
    else
        echo "Ping to $host failed."
    fi
}

# Function to check if a application endpoint is reachable using curl
check_application_url() {
    local url="$1"
    if curl -s --head "$url" | head -n 1 | grep "200 OK" &> /dev/null; then
        echo "Endpoint $url is reachable."
    else
        echo "Endpoint $url is not reachable."
    fi
}

# Function to check if a port is in use using lsof
check_port() {
    local port="$1"
    echo "Checking port: $port"

    if ss -tuln | grep ":$port" &> /dev/null; then
        echo "Port $port is in use."
    else
        echo "Port $port is not in use."
    fi
}


# Function to check if a process is running
check_process() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "Service $service_name is active (running)."
    else
        echo "Service $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}

# Function to check MySQL service
check_mysql_service() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "MySQL service $service_name is active (running)."
    else
        echo "MySQL service $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}

# Function to check MySQL service
check_influxdb_service() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "Influxdb service $service_name is active (running)."
    else
        echo "Influxdb service $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}

# Function to check if sub_client.py process is running
check_subscriber_process() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "Subscriber client process $service_name is active (running)."
    else
        echo "Subscriber client process $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}

# Check if app.py is running
check_app_process() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "app.py process $service_name is active (running)."
    else
        echo "app.py process $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}

# Check if exporter.py is running
check_exporter_process() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "exporter.py process $service_name is active (running)."
    else
        echo "exporter.py process $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}

# Check if UI is running
check_ui_process() {
    local service_name="$1"
    if systemctl is-active --quiet "$service_name"; then
        echo "UI process $service_name is active (running)."
    else
        echo "UI process $service_name is not active."

        # Debugging: Print systemctl status output
        echo "Detailed systemctl status output:"
        systemctl status "$service_name"

        # Debugging: Check the result of is-active command
        local status_check=""
        status_check=$(systemctl is-active "$service_name")
        echo "Output of systemctl is-active: $status_check"
    fi
}


# Function to test a single API endpoint
test_api_endpoint() {
  local API_URL=$1
  local EXPECTED_STATUS=200

  # Send a GET request and get the HTTP status code
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL")

  # Check if the status code matches the expected status
  if [ "$HTTP_STATUS" -eq "$EXPECTED_STATUS" ]; then
    echo "API endpoint $API_URL is working. Status code: $HTTP_STATUS"
  else
    echo "API endpoint $API_URL test failed. Status code: $HTTP_STATUS"
  fi
}

# Get the hostname or IP of the current VM
HOSTNAME=$(hostname)
IP_ADDRESS=$(hostname -I | awk '{print $1}') 

if [[ "$IP_ADDRESS" == "105.128.44.83" ]]; then
  echo "Running checks for VM with Host server"

  # Check if the local loopback interface is up
  check_ping "105.128.44.83"

  # Check if the Controller Server is running
  check_process "svk-controller"

  # Check if the Node Server is running
  check_process "svk-node"

  # Check if the REST API Server is running
  check_process "svk-restserver"

elif [[ "$IP_ADDRESS" == "105.128.44.84" ]]; then
  echo "Running checks for VM with management server"

  # Check if the local loopback interface is up
  check_ping "105.128.44.84"

  # Check if the application endpoint is reachable
  check_application_url "http://105.128.44.84:5000"

  # check if the backend endpoint is reachable 
  check_application_url "http://105.128.44.84:4001"

  # Check if the port 5000 4000 is in use
  check_port "5000"
  check_port "4001"

  # Run the MySQL server checks
  check_mysql_service "mysql"

  # Run the Influex DB checks
  check_influxdb_service "influxdb"
 
  # Run checks for cognos-ui and cognos-app cognos-subscribe cognos-exporter
  check_ui_process "cognos-ui"
  check_subscriber_process "cognos-subscriber"
  check_exporter_process "cognos-exporter"
  check_app_process "cognos-app"

  # List of API endpoints to test
  API_ENDPOINTS=(
    "http://105.128.44.84:4000/api/v2.0.1/host_devices"
    "http://105.128.44.84:4000/api/v2.0.1/topology"
    "http://105.128.44.84:4000//api/v2.0.1/hosts"
  )

  # Loop through each API endpoint and run the test function
  for ENDPOINT in "${API_ENDPOINTS[@]}"; do
    test_api_endpoint "$ENDPOINT"
  done

else
  echo "Unknown VM: No checks defined for IP $IP_ADDRESS. Check your IP address by running ip route, then update the IP address in the smoke_test.sh script using vi if necessary"
fi