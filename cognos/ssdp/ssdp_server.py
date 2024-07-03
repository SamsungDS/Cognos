from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler
from io import StringIO, BytesIO
import os
import socket
import select
import sys
from cognos.ssdp.helper import get_ssdp_response, load_config


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
sys.path.append(PROJECT_ROOT)

config = load_config()
MCAST_GRP = config['MCAST_GRP']
MCAST_PORT = int(config['MCAST_PORT'])


class Request(BaseHTTPRequestHandler):
    def __init__(self, request_text):
        self.rfile = BytesIO(request_text)
        self.raw_requestline = self.rfile.readline()
        self.error_code = self.error_message = None
        self.parse_request()

    def send_error(self, code, message=None, explain=None):
        self.error_code = code
        self.error_message = message
        self.error_explain = None


class Response(HTTPResponse):
    def __init__(self, response_text):
        self.fp = StringIO(response_text)
        self.debuglevel = 0
        self.strict = 0
        self.msg = None
        self.headers = {}
        self._method = None
        self.begin()


def interface_addresses(family=socket.AF_INET):
    for fam, _, _, _, sockaddr in socket.getaddrinfo('', None):
        if family == fam:
            yield sockaddr[0]


def server(timeout=360):
    socket.setdefaulttimeout(timeout)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.bind(('0.0.0.0', MCAST_PORT))

    while True:
        reads, _, _ = select.select([sock], [], [], 3 + 2)
        if reads:
            handle_requests(sock)
        sock.close()


def handle_requests(sock):
    data, addr = sock.recvfrom(4096)
    request = Request(data)
    if (not request.error_code and
            request.command == 'M-SEARCH' and
            request.path == '*' and
            request.headers['ST'].startswith('urn') and
            request.headers['MAN'] == '"ssdp:discover"'):
        ssdp_response = get_ssdp_response()
        sock.sendto(ssdp_response.encode('utf-8'), addr)

    return True


if __name__ == '__main__':
    server()
