import pytest
import sys
import os
from unittest.mock import patch, MagicMock, mock_open
from unittest import mock

sys.path.append(  # noqa: E402
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../..")
    )  # noqa: E402
)  # noqa: E402
from cognos.subscriber.sub_client import *

# Sample data for testing
sample_file_content = "metric:{'field1': 'value1', 'field2': 'value2'}\n"
sample_data = [{"field1": "value1", "field2": "value2"}]


@patch("cognos.subscriber.sub_client.CognosInfluxDBClient")
@patch("time.sleep", return_value=None)
@patch("builtins.open", new_callable=mock_open, read_data=sample_file_content)
@patch("os.path.exists", return_value=True)
def test_mock_subscription_with_real_data(
    mock_exists, mock_open, mock_sleep, mock_db_client
):
    # Prepare mock file path and arguments
    basedir = os.path.split(os.path.dirname(__file__))[0]
    dataset_path = os.path.join(basedir, "test_mock_publisher_events.output")
    sys.argv = ["sub_client.py", dataset_path]
    # Create a mock instance of CognosInfluxDBClient
    mock_db_instance = MagicMock()

    # Return this mock instance whenever CognosInfluxDBClient() is called
    mock_db_client.return_value = mock_db_instance
    # Create a stop condition to stop after 2 iterations
    iteration_count = [0]

    def stop_condition():
        iteration_count[0] += 1
        return iteration_count[0] > 2  # Stop after 2 iterations

    # Run the actual mock_subscription logic
    mock_subscription(dataset_path, 1, stop_condition=stop_condition)
    # write_cognos_event method on the mock instance called twice
    assert (
        mock_db_instance.write_cognos_event.call_count == 2
    ), "write_cognos_event should be called twice."
    # Validate the content passed to write_cognos_event
    call_args_list = mock_db_instance.write_cognos_event.call_args_list
    for call in call_args_list:
        args, _ = call
        data_sent = args[0]  # The data passed to write_cognos_event
        assert (
            "timestamp" in data_sent
        ), "Timestamp should be added before sending to InfluxDB"
        assert data_sent["field1"] == "value1", "Field1 should match"
        assert data_sent["field2"] == "value2", "Field2 should match"


def test_read_input(monkeypatch):
    # Mock open() and simulate a file with sample data
    monkeypatch.setattr(
        "builtins.open", mock.mock_open(read_data=sample_file_content)
    )
    result = read_input("fakefile.txt")
    assert (
        result == sample_data
    ), "read_input should correctly parse the file into a list of dictionaries"


def test_mock_subscription_file_not_found(monkeypatch):
    # Simulate file not existing
    monkeypatch.setattr("os.path.exists", lambda x: False)
    with pytest.raises(FileNotFoundError):
        mock_subscription("", 5)


# Test case for error while reading the input file (Generic Exception)
@patch("sys.exit")  # Mock sys.exit to prevent the test from exiting
def test_mock_subscription_error_reading_file(mock_sys_exit, capfd):
    with patch("os.path.exists", return_value=True):
        # Simulate an error in read_input function
        with patch(
            "cognos.subscriber.sub_client.read_input",
            side_effect=Exception("Failed to read file"),
        ):
            mock_subscription("", 5)
            # Capture printed output
            captured = capfd.readouterr()
            # Check the correct error message
            assert (
                "Error reading input file: Failed to read file" in captured.out
            )
            mock_sys_exit.assert_called_once_with(1)


# Test case to handle ZMQError during socket connection
@patch("sys.exit")  # Mock sys.exit to prevent the test from exiting
@patch("zmq.Context")  # Mock zmq context to control socket behavior
def test_zeromq_subscription_zmq_error(mock_zmq_context, mock_sys_exit, capfd):
    # Mock the socket
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Simulate ZMQError when trying to connect to the server
    mock_socket.connect.side_effect = zmq.ZMQError(
        "Simulated connection failure"
    )
    # Call zeromq_subscription with valid hostname:port to trigger the ZMQError
    zeromq_subscription("localhost", 5555, "topic", 1)
    # Ensure sys.exit(1) is called
    mock_sys_exit.assert_called_once_with(1)
    # Capture printed output and verify the correct error message
    captured = capfd.readouterr()
    print(captured.out)
    expected_msg = "Failed to connect to server at localhost:5555: \
                    Simulated connection failure"
    print(expected_msg)
    assert " ".join(expected_msg.strip().split()) in captured.out


# Test case for invalid JSON in message and sys.exit handling
@patch("sys.exit")  # Mock sys.exit to prevent the test from exiting
@patch("zmq.Context")
def test_zeromq_subscription_invalid_json_sys_exit(
    mock_zmq_context, mock_sys_exit, capfd
):
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Define a message that will cause a JSONDecodeError
    mock_socket.recv.side_effect = [
        b"topic1:metric:{invalid_json_data}"  # Invalid JSON format
    ]
    # Call the zeromq_subscription function
    zeromq_subscription("localhost", 5555, "topic", 1)
    # Ensure sys.exit(1) is called when the error occurs
    mock_sys_exit.assert_called_once_with(1)
    # Capture the printed output and check the error message
    captured = capfd.readouterr()
    assert "Failed to parse message data as JSON" in captured.out


@patch("cognos.subscriber.sub_client.CognosInfluxDBClient")
@patch("time.sleep", return_value=None)  # Skip the actual sleep
@patch("zmq.Context")  # Mock ZeroMQ context
def test_zeromq_subscription_with_mock_zmq(
    mock_zmq_context, mock_sleep, mock_influxdb_client
):
    # Mock ZeroMQ context and socket
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Define the metric messages to simulate ZeroMQ receiving them
    mock_socket.recv.side_effect = [
        b"""
        metric:{"type": "metric", "source": "localhost",
        "source_type": "application server",
        "timestamp": "2024-08-06T20:58:28Z", "description": "host cpu memory",
        "category": "host system metrics", "application": "cognos metric test",
        "observations": {"dram_capacity_mb": 515709, "dram_usage_mb": 454043,
        "cxl_capacity_mb": 258006, "cxl_usage_mb": 84865,
        "cpu_usage": 73.0}}""",
        b"""
        metric:{"type": "metric", "source": "localhost",
        "source_type": "application server",
        "timestamp": "2024-08-06T20:58:35Z", "description": "host cpu memory",
        "category": "host system metrics", "application": "cognos metric test",
        "observations": {"dram_capacity_mb": 515709, "dram_usage_mb": 281167,
        "cxl_capacity_mb": 258006, "cxl_usage_mb": 174461,
        "cpu_usage": 82.0}}""",
    ]
    # Mock the CognosInfluxDBClient instance
    mock_influxdb_instance = mock_influxdb_client.return_value
    # Create a stop condition to stop after 2 messages
    iteration_count = [0]

    def stop_condition():
        iteration_count[0] += 1
        return iteration_count[0] > 2  # Stop after 2 iterations

    # Call the zeromq_subscription function with the stop condition
    zeromq_subscription(
        "localhost", 5555, "metric", 1, stop_condition=stop_condition
    )
    # Check that recv is called twice (for 2 messages)
    assert mock_socket.recv.call_count == 2, "recv should be called twice."
    # Verify that the write_cognos_event method was called twice
    assert (
        mock_influxdb_instance.write_cognos_event.call_count == 2
    ), "write_cognos_event should be called twice."

    call_args_list = mock_influxdb_instance.write_cognos_event.call_args_list
    for call in call_args_list:
        args, _ = call
        data_sent = args[0]  # The data passed to write_cognos_event
        assert (
            "timestamp" in data_sent
        ), "Timestamp should be included in the data sent to InfluxDB."
        assert data_sent["observations"]["cpu_usage"] in [
            73.0,
            82.0,
        ], "CPU usage should match the test data."


def test_mock_subscription_empty_dataframe(monkeypatch):
    # Mock the file exists and returns empty data
    monkeypatch.setattr("os.path.exists", lambda x: True)
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data="[]"))
    with patch("sys.exit") as mock_sys_exit:
        mock_subscription("", 5)
        mock_sys_exit.assert_not_called()


@patch("zmq.Context")
@patch("sys.exit")  # Mock sys.exit to prevent actual exit
def test_zeromq_subscription_keyboard_interrupt(
    mock_sys_exit, mock_zmq_context
):
    # Mock the ZeroMQ context and socket
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    # Simulate a KeyboardInterrupt
    mock_socket.recv.side_effect = KeyboardInterrupt
    zeromq_subscription("localhost", 5555, "topic", 1)
    # Check that sys.exit(0) was called after keyboard interrupt
    mock_sys_exit.assert_called_once_with(0)


def test_mock_subscription_empty_file(monkeypatch):
    # Mock the file exists and open to simulate empty content
    monkeypatch.setattr("os.path.exists", lambda x: True)
    monkeypatch.setattr("builtins.open", mock.mock_open(read_data=""))
    with patch("sys.exit") as mock_sys_exit:
        mock_subscription("", 5)
        mock_sys_exit.assert_not_called()


@patch("cognos.subscriber.sub_client.load_and_validate_config")
@patch("cognos.subscriber.sub_client.get_node_ids", return_value=["node1"])
@patch("cognos.subscriber.sub_client.zeromq_subscription")
def test_main_valid_zeromq_subscription(
    mock_zeromq_subscription, mock_get_node_ids, mock_load_config
):
    # Mock configuration data
    mock_load_config.return_value = {
        "rest_ip": "127.0.0.1",
        "rest_port": 8080,
        "publisher_port": 5555,
        "publisher_topic": "topic",
        "interval": 5,
        "cluster_id": ["cluster123"],
    }
    # Call the main function with config_file argument
    main(config_file="test_config.json")
    # Ensure that zeromq_subscription is called with expected parameters
    mock_zeromq_subscription.assert_called_once_with(
        "node1",
        5555,
        "topic",
        5,
    )


@patch(
    "cognos.subscriber.sub_client.is_valid_ip_or_fqdn",
    side_effect=lambda x: True,
)
@patch("requests.post")
def test_get_node_ids_success_2(mock_post, mock_validation):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "cluster_info": [
            {
                "node_info": [
                    {"node_id": "10.105.81.34"},
                    {"node_id": "ssl-ssg-v9m.msl.lab"},
                ]
            }
        ]
    }
    node_ids = get_node_ids("127.0.0.1", 8080, "cluster123")
    assert node_ids == ["10.105.81.34", "ssl-ssg-v9m.msl.lab"]


@patch("requests.post")
def test_get_node_ids_failure(mock_post):
    mock_post.return_value.status_code = 500
    mock_post.return_value.json.return_value = {}
    node_ids = get_node_ids("127.0.0.1", 8080, "cluster123")
    assert node_ids == []


@patch("cognos.subscriber.sub_client.CognosInfluxDBClient")
@patch("time.sleep", return_value=None)  # Skip the actual sleep
@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="metric:{'field1': 'value1', 'field2': 'value2'}\n",
)
@patch("os.path.exists", return_value=True)
def test_mock_subscription(mock_exists, mock_open, mock_sleep, mock_db_client):
    # Create a mock instance of CognosInfluxDBClient
    mock_db_instance = MagicMock()
    mock_db_client.return_value = mock_db_instance
    # Define a stop condition to stop after exactly 1 iteration
    iteration_count = [0]

    def stop_condition():
        iteration_count[0] += 1
        return iteration_count[0] > 1  # Stops after 1 iteration

    # Run the function
    mock_subscription(
        mock_file="test_mock_publisher_events.output",
        interval=1,
        stop_condition=stop_condition,
    )
    # Check that the function writes to the DB exactly once per iteration
    assert (
        mock_db_instance.write_cognos_event.call_count == 1
    ), f"Expected write_cognos_event to be called once, but was called \
            {mock_db_instance.write_cognos_event.call_count} times."


@patch(
    "builtins.open",
    new_callable=mock_open,
    read_data="""
{"rest_ip": "127.0.0.1",
"rest_port": 8080,
"publisher_port": 5555,
"publisher_topic": "topic",
"interval": 5,
"cluster_id": "cluster123"}
""",
)
@patch("os.path.exists", return_value=True)  # Simulate config file exists
@patch("cognos.subscriber.sub_client.load_and_validate_config")
@patch("cognos.subscriber.sub_client.get_node_ids", return_value=["node1"])
@patch("cognos.subscriber.sub_client.zeromq_subscription")
@patch("sys.exit")  # Prevent test from exiting
def test_main_non_mock_mode(
    mock_sys_exit,
    mock_zeromq_subscription,
    mock_get_node_ids,
    mock_load_config,
    mock_exists,
    mock_open_file,
):
    # Mock configuration data
    mock_load_config.return_value = {
        "rest_ip": "127.0.0.1",
        "rest_port": 8080,
        "publisher_port": 5555,
        "publisher_topic": "topic",
        "interval": 5,
        "cluster_id": ["cluster123"],
    }
    # Run the main function with the mock config file
    main(config_file="test_config.json")
    # Ensure `zeromq_subscription` is called with expected positional arguments
    mock_zeromq_subscription.assert_called_once_with("node1", 5555, "topic", 5)
    # Ensure sys.exit is NOT called since config is now mocked properly
    mock_sys_exit.assert_not_called()


def test_load_and_validate_config_valid():
    valid_json = """
    { "rest_ip": "127.0.0.1",
    "rest_port": 8080,
    "publisher_port": 5555,
    "publisher_topic": "topic",
    "interval": 5,
    "cluster_id": "cluster123"}
    """
    with patch("builtins.open", mock_open(read_data=valid_json)):
        config = load_and_validate_config("test_config.json")
        assert config["rest_ip"] == "127.0.0.1"
        assert config["rest_port"] == 8080


def test_load_and_validate_config_missing_field():
    invalid_json = """
    { "rest_ip": "127.0.0.1",
    "rest_port": 8080
    """
    with patch("builtins.open", mock_open(read_data=invalid_json)):
        with pytest.raises(SystemExit):
            load_and_validate_config("test_config.json")


def test_load_and_validate_config_invalid_yaml():
    invalid_json = "invalid_json: ["
    with patch("builtins.open", mock_open(read_data=invalid_json)):
        with pytest.raises(SystemExit):
            load_and_validate_config("test_config.json")


def test_read_input_valid():
    mock_data = """metric:{"key1": "value1"}\nmetric:{"key2": "value2"}"""
    with patch("builtins.open", mock_open(read_data=mock_data)):
        result = read_input("mock_file.txt")
        assert result == [{"key1": "value1"}, {"key2": "value2"}]


def test_validate_file_valid(tmp_path):
    # Create a temporary file
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("content")
    assert validate_file(str(file_path)) == str(file_path)


def test_validate_file_invalid():
    with pytest.raises(argparse.ArgumentTypeError):
        validate_file("non_existent_file.txt")


@patch("cognos.subscriber.sub_client.CognosInfluxDBClient")
@patch("time.sleep", return_value=None)
@patch("builtins.open", new_callable=mock_open, read_data=sample_file_content)
@patch("os.path.exists", return_value=True)
def test_mock_subscription_with_real_data(
    mock_exists, mock_open, mock_sleep, mock_db_client
):
    # Prepare mock file path and arguments
    basedir = os.path.split(os.path.dirname(__file__))[0]
    dataset_path = os.path.join(basedir, "test_mock_publisher_events.output")


@patch("builtins.open", mock_open(read_data="{}"))  # Empty config
@patch("sys.exit")  # Mock sys.exit to prevent actual exit
def test_load_and_validate_config_empty(mock_sys_exit, capfd):
    load_and_validate_config("test_config.json")
    # Capture the printed output
    captured = capfd.readouterr()
    # Validate the expected error message
    assert (
        "Missing required field" in captured.out
    ), f"Expected error message not found in: {captured.out}"
    # Ensure sys.exit(1) was called
    mock_sys_exit.assert_called_once_with(1)


@patch(
    "builtins.open",
    mock_open(
        read_data="""
        {
            "rest_ip": "127.0.0.1",
            "rest_port": "not_an_int",
            "publisher_port": 5555,
            "publisher_topic": "topic",
            "interval": 5,
            "cluster_id": "cluster123"
        }
        """
    ),
)
@patch("sys.exit")  # Mock sys.exit to prevent actual exit
def test_load_and_validate_config_invalid_type(mock_sys_exit, capfd):
    load_and_validate_config("test_config.json")
    # Capture the printed output
    captured = capfd.readouterr()
    # Validate expected error message
    assert (
        "Ports must be integers" in captured.out
    ), f"Expected error message not found in: {captured.out}"


@patch(
    "cognos.subscriber.sub_client.read_input",
    side_effect=SyntaxError("Eval error"),
)
@patch("sys.exit")
def test_mock_subscription_eval_failure(mock_sys_exit, mock_read_input):
    with patch("os.path.exists", return_value=True):
        mock_subscription("mock_file.txt", 5)
        mock_sys_exit.assert_called_once_with(1)


@patch("zmq.Context")
@patch("sys.exit")
def test_zeromq_subscription_zmqerror(mock_sys_exit, mock_zmq_context):
    mock_socket = MagicMock()
    mock_zmq_context_instance = mock_zmq_context.return_value
    mock_zmq_context_instance.socket.return_value = mock_socket
    mock_socket.connect.side_effect = zmq.ZMQError("Mocked ZMQ error")
    zeromq_subscription("localhost", 5555, "topic", 1)
    mock_sys_exit.assert_called_once_with(1)


@patch("requests.post")
def test_get_node_ids_invalid_json(mock_post):
    # Simulate a valid response but with an invalid JSON structure
    mock_post.return_value.status_code = 200
    # Not expected "clusterInfo"
    mock_post.return_value.json.return_value = {
        "invalid_key": "unexpected_value"
    }
    node_ids = get_node_ids("127.0.0.1", 8080, "cluster123")
    # expected JSON format is missing, the function should return an empty list
    assert node_ids == [], f"Expected empty list, but got: {node_ids}"


@patch("requests.post")
def test_get_node_ids_timeout(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout
    node_ids = get_node_ids("127.0.0.1", 8080, "cluster123")
    assert node_ids == []


def test_is_valid_ip_or_fqdn():
    # Valid IPv4
    assert is_valid_ip_or_fqdn("10.105.80.34") is True
    # Valid IPv6
    assert is_valid_ip_or_fqdn("2001:db8::ff00:42:8329") is True
    # Valid FQDN
    assert is_valid_ip_or_fqdn("msl-ssg-vm53.msl.lab") is True
    assert is_valid_ip_or_fqdn("google.com") is True
    # Invalid Cases
    assert is_valid_ip_or_fqdn("invalid_domain") is False
    # invalid ip
    assert is_valid_ip_or_fqdn("256.256.256.256") is False
    # not a fqdn as last part is misisng atleast 2 characters ex: .org
    assert is_valid_ip_or_fqdn("my-server") is False
    assert is_valid_ip_or_fqdn("localhost") is True
