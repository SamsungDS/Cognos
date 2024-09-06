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

# Function to check if a service endpoint is reachable using curl
check_curl() {
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
    if lsof -i:"$port" &> /dev/null; then
        echo "Port $port is in use."
    else
        echo "Port $port is not in use."
    fi
}

# Function to check if a process is running
check_process() {
    local process_name="$1"
    if pgrep "$process_name" &> /dev/null; then
        echo "Process $process_name is running."
    else
        echo "Process $process_name is not running."
    fi
}

# Check if the Controller Server is running
check_process "ctrlr_server"

# Check if the Node Server is running
check_process "node_server"

# Check if the REST API Server is running
check_process "main.go"

# Check if the local loopback interface is up
check_ping "127.0.0.1"

# Check if the local service endpoint is reachable
check_curl "http://localhost:5000"

# Check if the port 5000 is in use
check_port "5000"