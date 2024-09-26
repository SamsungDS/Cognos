import pytest
import sys
import os
from unittest import mock
from unittest.mock import patch, MagicMock
sys.path.append(  # noqa: E402
    os.path.abspath(os.path.join(  # noqa: E402
        os.path.dirname(__file__), '../../..')))  # noqa: E402
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient
from cognos.backend.helper import *
from cognos.subscriber.sub_client import *

# Sample data for testing
sample_file_content = "metric:{'field1': 'value1', 'field2': 'value2'}\n"
sample_data = [{'field1': 'value1', 'field2': 'value2'}]


# Test for mock_subscription using real dataset
@patch('cognos.backend.cognos_influxdb_client.CognosInfluxDBClient')
@patch('time.sleep', return_value=None)  # To skip the actual sleep
def test_mock_subscription_with_real_data(mock_sleep, mock_influxdb_client):
    # Path to the real dataset in the source folder
    basedir = os.path.split(os.path.dirname(__file__))[0]
    dataset_path = os.path.join(basedir,'test_mock_publisher_events.output')
    # Modify sys.argv to pass the real dataset file as an argument
    sys.argv = ['sub_client.py', dataset_path]
    # Mock the CognosInfluxDBClient instance
    mock_influxdb_instance = mock_influxdb_client.return_value

    # Ensure the dataset path is correct
    assert os.path.exists(dataset_path), f"Dataset file {dataset_path} not found."
    # Create a stop condition to stop after 2 iterations
    iteration_count = [0]
    def stop_condition():
        iteration_count[0] += 1
        return iteration_count[0] > 2  # Stop after 2 iterations
    # Call the function directly with the real data and stop condition
    mock_subscription(1, stop_condition=stop_condition)


def test_read_input(monkeypatch):
    # Mock open() and simulate a file with sample data
    monkeypatch.setattr('builtins.open', mock.mock_open(read_data=sample_file_content))
    result = read_input('fakefile.txt')
    assert result == sample_data, "read_input should correctly parse the file into a list of dictionaries"


def test_mock_subscription_file_not_found(monkeypatch):
    # Simulate file not existing
    monkeypatch.setattr('os.path.exists', lambda x: False)
    with pytest.raises(FileNotFoundError):
        mock_subscription(5)


# Test case for error while reading the input file (Generic Exception)
@patch('sys.exit')  # Mock sys.exit to prevent the test from exiting
def test_mock_subscription_error_reading_file(mock_sys_exit, capfd):
    with patch('os.path.exists', return_value=True):  # Simulate the file exists
        # Simulate an error in read_input function
        with patch('cognos.subscriber.sub_client.read_input', side_effect=Exception("Failed to read file")):
            mock_subscription(5)
            # Capture printed output
            captured = capfd.readouterr()
            # Check the correct error message
            assert "Error reading input file: Failed to read file" in captured.out
            mock_sys_exit.assert_called_once_with(1)


def test_zeromq_subscription_invalid_hostname():
    with pytest.raises(SystemExit):
        zeromq_subscription("invalid_hostname", "topic", 1)


# Test case to handle ZMQError during socket connection
@patch('sys.exit')  # Mock sys.exit to prevent the test from exiting
@patch('zmq.Context')  # Mock zmq context to control socket behavior
def test_zeromq_subscription_zmq_error(mock_zmq_context, mock_sys_exit, capfd):
    # Mock the socket
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Simulate ZMQError when trying to connect to the server
    mock_socket.connect.side_effect = zmq.ZMQError("Simulated connection failure")
    # Call zeromq_subscription with valid hostname:port to trigger the ZMQError
    zeromq_subscription("localhost:5555", "topic", 1)
    # Ensure sys.exit(1) is called
    mock_sys_exit.assert_called_once_with(1)
    # Capture printed output and verify the correct error message
    captured = capfd.readouterr()
    assert "Failed to connect to server: Simulated connection failure" in captured.out


# Test case for invalid JSON in message and sys.exit handling
@patch('sys.exit')  # Mock sys.exit to prevent the test from exiting
@patch('zmq.Context')
def test_zeromq_subscription_invalid_json_sys_exit(mock_zmq_context, mock_sys_exit, capfd):
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Define a message that will cause a JSONDecodeError
    mock_socket.recv.side_effect = [
        b"topic1:metric:{invalid_json_data}"  # Invalid JSON format
    ]
    # Call the zeromq_subscription function
    zeromq_subscription("localhost:5555", "topic", 1)
    # Ensure sys.exit(1) is called when the error occurs
    mock_sys_exit.assert_called_once_with(1)
    # Capture the printed output and check the error message
    captured = capfd.readouterr()
    assert "Failed to parse message data as JSON" in captured.out


# Test case to handle ValueError for invalid hostname and port
@patch('sys.exit')  # Mock sys.exit to prevent the test from exiting
def test_zeromq_subscription_mock_hostname_parsing(mock_sys_exit, capfd):
    # Invalid hostname without colon (should raise ValueError for invalid format)
    zeromq_subscription("invalid_hostname", "topic", 1)
    # Ensure sys.exit(1) is called
    mock_sys_exit.assert_called_once_with(1)
    # Capture printed output and verify error message
    captured = capfd.readouterr()
    assert "Error parsing hostname or port: Invalid <hostname:port> format." in captured.out
    # Reset mock_sys_exit for the next test case
    mock_sys_exit.reset_mock()
    # Simulate valid hostname but invalid port (non-integer)
    with patch('builtins.int', side_effect=ValueError("invalid literal for int()")):
        zeromq_subscription("localhost:notaport", "topic", 1)
        # Ensure sys.exit(1) is called for invalid port
        mock_sys_exit.assert_called_once_with(1)
        # Capture printed output and verify the error message for the invalid port
        captured = capfd.readouterr()
        assert "Error parsing hostname or port: invalid literal for int()" in captured.out

# Test case to handle ValueError when port is not an integer
@patch('sys.exit')  # Mock sys.exit to prevent the test from exiting
def test_zeromq_subscription_invalid_port_sys_exit(mock_sys_exit, capfd):
    # Test hostname with invalid port, should trigger ValueError and sys.exit(1)
    zeromq_subscription("localhost:notaport", "topic", 1)
    # Check that sys.exit(1) was called
    mock_sys_exit.assert_called_once_with(1)
    # Capture printed output and check that the error message was printed
    captured = capfd.readouterr()
    assert "Error parsing hostname or port: invalid literal for int()" in captured.out

# Test for zeromq_subscription using mock ZeroMQ socket
@patch('cognos.backend.cognos_influxdb_client.CognosInfluxDBClient')
@patch('time.sleep', return_value=None)  # To skip the actual sleep
@patch('zmq.Context')
def test_zeromq_subscription_with_mock_zmq(mock_zmq_context, mock_sleep, mock_influxdb_client):
    # Mock ZeroMQ context and socket
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Define the metric messages to simulate ZeroMQ receiving them
    mock_socket.recv.side_effect = [
        b"metric:{\"type\": \"metric\", \"source\": \"localhost\", \"source_type\": \"application server\", \"timestamp\": \"2024-08-06T20:58:28Z\", \"description\": \"host cpu memory\", \"category\": \"host system metrics\", \"application\": \"cognos metric test\", \"observations\": {\"dram_capacity_mb\": 515709, \"dram_usage_mb\": 454043, \"cxl_capacity_mb\": 258006, \"cxl_usage_mb\": 84865, \"cpu_usage\": 73.0}}",
        b"metric:{\"type\": \"metric\", \"source\": \"localhost\", \"source_type\": \"application server\", \"timestamp\": \"2024-08-06T20:58:35Z\", \"description\": \"host cpu memory\", \"category\": \"host system metrics\", \"application\": \"cognos metric test\", \"observations\": {\"dram_capacity_mb\": 515709, \"dram_usage_mb\": 281167, \"cxl_capacity_mb\": 258006, \"cxl_usage_mb\": 174461, \"cpu_usage\": 82.0}}"
    ]
    # Mock the CognosInfluxDBClient instance
    mock_influxdb_instance = mock_influxdb_client.return_value
    # Create a stop condition to stop after 2 messages
    iteration_count = [0]
    def stop_condition():
        iteration_count[0] += 1
        return iteration_count[0] > 2  # Stop after 2 iterations
    # Call the zeromq_subscription function with the stop condition
    zeromq_subscription("localhost:5555", "metric", 1, stop_condition=stop_condition)
    # Check that recv is called twice (for 2 messages)
    assert mock_socket.recv.call_count == 2
    
