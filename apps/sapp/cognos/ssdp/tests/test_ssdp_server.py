import socket
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock
from cognos.ssdp.ssdp_server import (
    handle_requests,
    Request,
    load_config,
    get_ssdp_response,
    server,
    interface_addresses,
    Response
)

CONFIG_CONTENT = json.dumps({
    "device_type": "TestDevice",
    "manufacturer": "TestManufacturer",
    "mgmt_endpoint": "http://192.168.1.1:5000",
    "api_endpoint": "http://192.168.1.1:5000/api/v2.0/devices",
    "cxl_version": "1.1",
    "pcie_version": "gen6",
    "upstream_ports": "2",
    "downstream_ports": "4",
    "MCAST_GRP": "239.255.255.250",
    "MCAST_PORT": "1900"
})


@pytest.fixture
def mock_config_file():
    with patch('builtins.open', mock_open(read_data=CONFIG_CONTENT)):
        yield


@pytest.fixture
def mock_socket():
    with patch('socket.socket') as mock_sock:
        yield mock_sock


@pytest.fixture
def mock_request():
    return (
        b'M-SEARCH * HTTP/1.1\r\n'
        b'HOST: 239.255.255.250:1900\r\n'
        b'ST: urn:schemas-upnp-org:device:basic:1\r\n'
        b'MAN: "ssdp:discover"\r\n'
        b'MX: 1\r\n\r\n'
    )


@patch('cognos.ssdp.ssdp_server.get_ssdp_response',
       return_value='HTTP/1.1 200 OK\r\n')
def test_handle_requests(
    mock_get_ssdp_response,
        mock_socket, mock_request, mock_config_file):
    mock_socket_instance = mock_socket.return_value
    mock_socket_instance.recvfrom.return_value = (mock_request,
                                                  ('192.168.1.100', 1900))
    handle_requests(mock_socket_instance)
    mock_socket_instance.sendto.assert_called_once_with(
        b'HTTP/1.1 200 OK\r\n', ('192.168.1.100', 1900)
    )


def test_load_config(mock_config_file):
    config = load_config()
    assert config['device_type'] == 'TestDevice'
    assert config['manufacturer'] == 'TestManufacturer'
    assert config['mgmt_endpoint'] == 'http://192.168.1.1:5000'


def test_request_send_error():
    request_text = b""
    request = Request(request_text)
    request.send_error(404, "Not Found")
    assert request.error_code == 404
    assert request.error_message == "Not Found"


def test_response_initialization():
    response_text = "HTTP/1.1 200 OK\r\n"
    response = Response(response_text)
    response.begin()
    assert response.fp.getvalue() == response_text
    assert response.debuglevel == 0
    assert response.strict == 0


def test_interface_addresses():
    with patch('socket.getaddrinfo') as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [(socket.AF_INET, 0, 0, 0,
                                          ('192.168.1.1', 0))]
        addresses = list(interface_addresses())
        assert addresses == ['192.168.1.1']


def test_server_initialization():
    with patch('socket.socket') as mock_socket, patch(
            'socket.setdefaulttimeout') as mock_settimeout:
        mock_socket_instance = mock_socket.return_value
        mock_socket_instance.recvfrom.return_value = (
            b"M-SEARCH * HTTP/1.1\r\n"
            b"ST: urn:ssdp:all\r\n"
            b"MAN:\"ssdp:discover\"\r\n",
            ('192.168.1.100', 1900)
        )
        mock_socket_instance.bind.return_value = None
        mock_socket_instance.setsockopt.return_value = None
        mock_socket_instance.close.return_value = None
        mock_socket_instance.fileno.return_value = 1

        with patch('select.select') as mock_select:
            mock_select.side_effect = [([mock_socket_instance], [], []),
                                       StopIteration]

            try:
                server(360)
            except StopIteration:
                print("Caught StopIteration as expected.")

        mock_settimeout.assert_called_with(360)
        mock_socket_instance.setsockopt.assert_any_call
        (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        mock_socket_instance.setsockopt.assert_any_call
        (socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        mock_socket_instance.bind.assert_called_with(('0.0.0.0', 1900))
        mock_socket_instance.close.assert_called_once()
