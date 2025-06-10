import builtins
import io
import json
import logging
import os
import sys
import types

import pytest
cwd = os.getcwd()
# Assuming we are running from tests dir for now
script_path = cwd + "/../../../src/node_info/"
sys.path.append(script_path)
import find_node_info as fn


# ------------- Helpers -----------------------------------------------------


class DummySnic(types.SimpleNamespace):
    """Simple stand in for psutil's snicaddr namedtuple."""
    pass


def make_open_map():
    """
    Returns a function suitable for patching builtins.open which
    provides canned file contents for the various network attributes.
    """
    contents = {
        "/sys/class/net/eth0/mtu": "1500",
        "/sys/class/net/eth0/operstate": "up",
        "/sys/class/net/eth0/carrier": "1",
        "/sys/class/net/eth0/speed": "1000",
        "/sys/class/net/eth0/duplex": "full",
    }

    def _mock_open(path, *args, **kwargs):
        if path in contents:
            return io.StringIO(contents[path])
        raise FileNotFoundError(path)

    return _mock_open


# ------------- get_system_info ---------------------------------------------

def test_get_system_info(monkeypatch):
    """Verify that get_system_info collects information from the platform."""
    monkeypatch.setattr(fn.platform, "node", lambda: "testnode")
    monkeypatch.setattr(fn.socket, "getfqdn", lambda: "testnode.example.com")
    monkeypatch.setattr(fn.socket, "gethostbyname_ex", lambda host: ("testnode", [], ["10.1.1.1"]))
    monkeypatch.setattr(fn.socket, "gethostbyname", lambda host : ("10.0.1.1"))
    monkeypatch.setattr(fn.distro, "name", lambda pretty=True: "MyLinux")
    mock_uname = types.SimpleNamespace(release="5.10.0")
    monkeypatch.setattr(fn.platform, "uname", lambda: mock_uname)

    result = fn.get_system_info()
    assert result == {
        "server-info": {
            "hostname": "testnode",
            "fqdn": "testnode.example.com",
            "ip-address": "10.1.1.1",
            "os-release": "MyLinux",
            "kernel-version": "5.10.0",
        }
    }

def test_get_system_info_localhost_ip(monkeypatch):
    """Verify that get_system_info excludes localhost IP addresses."""
    monkeypatch.setattr(fn.platform, "node", lambda: "testnode")
    monkeypatch.setattr(fn.socket, "getfqdn", lambda: "testnode.example.com")
    monkeypatch.setattr(fn.socket, "gethostbyname_ex", lambda host: ("testnode", "", ["127.0.0.1", "10.1.1.1"]))
    monkeypatch.setattr(fn.socket, "gethostbyname", lambda host : ("10.0.1.1"))
    monkeypatch.setattr(fn.distro, "name", lambda pretty=True: "MyLinux")
    mock_uname = types.SimpleNamespace(release="5.10.0")
    monkeypatch.setattr(fn.platform, "uname", lambda: mock_uname)

    result = fn.get_system_info()
    assert result == {
        "server-info": {
            "hostname": "testnode",
            "fqdn": "testnode.example.com",
            "ip-address": "10.1.1.1",
            "os-release": "MyLinux",
            "kernel-version": "5.10.0",
        }
    }
    
def test_get_system_info_default_ip(monkeypatch):
    """Verify that get_system_info defaults to what is returned by socket.gethostbyname()"""
    monkeypatch.setattr(fn.platform, "node", lambda: "testnode")
    monkeypatch.setattr(fn.socket, "getfqdn", lambda: "testnode.example.com")
    monkeypatch.setattr(fn.socket, "gethostbyname_ex", lambda host: ("testnode", "", ["127.0.0.1"]))
    monkeypatch.setattr(fn.socket, "gethostbyname", lambda host : ("10.0.1.1"))
    monkeypatch.setattr(fn.distro, "name", lambda pretty=True: "MyLinux")
    mock_uname = types.SimpleNamespace(release="5.10.0")
    monkeypatch.setattr(fn.platform, "uname", lambda: mock_uname)

    result = fn.get_system_info()
    assert result == {
        "server-info": {
            "hostname": "testnode",
            "fqdn": "testnode.example.com",
            "ip-address": "10.0.1.1",
            "os-release": "MyLinux",
            "kernel-version": "5.10.0",
        }
    }
    
def test_get_system_info_ipv6_localhost(monkeypatch):
    """Verify that get_system_info returns ipv6 address"""
    monkeypatch.setattr(fn.platform, "node", lambda: "testnode")
    monkeypatch.setattr(fn.socket, "getfqdn", lambda: "testnode.example.com")
    monkeypatch.setattr(fn.socket, "gethostbyname_ex", lambda host: ("testnode", "", ["::1", "2001:0db8:85a3:0000:0000:8a2e:0370:7334"]))
    monkeypatch.setattr(fn.socket, "gethostbyname", lambda host : ("10.0.1.1"))
    monkeypatch.setattr(fn.distro, "name", lambda pretty=True: "MyLinux")
    mock_uname = types.SimpleNamespace(release="5.10.0")
    monkeypatch.setattr(fn.platform, "uname", lambda: mock_uname)

    result = fn.get_system_info()
    assert result == {
        "server-info": {
            "hostname": "testnode",
            "fqdn": "testnode.example.com",
            "ip-address": "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "os-release": "MyLinux",
            "kernel-version": "5.10.0",
        }
    }


# ------------- get_network_adapters_info -----------------------------------

def test_get_network_adapters_info_single_adapter(monkeypatch):
    """Validate network adapter parsing including lshw integration."""
    snic_v4 = DummySnic(family=fn.socket.AF_INET,
                        address="192.168.0.2",
                        netmask="255.255.255.0")
    snic_v6 = DummySnic(family=fn.socket.AF_INET6,
                        address="fe80::1",
                        netmask=None)

    # psutil.net_if_addrs returns adapters including 'lo' which should be skipped
    monkeypatch.setattr(
        fn.psutil,
        "net_if_addrs",
        lambda: {"lo": [snic_v4],
                 "eth0": [snic_v4, snic_v6]},
    )

    lshw_data = json.dumps(
        [{"logicalname": "eth0",
          "businfo": "pci@0000:01:00.0",
          "vendor": "Intel"}]
    ).encode()
    monkeypatch.setattr(fn.subprocess, "check_output",
                        lambda *a, **kw: lshw_data)

    # all files exist for eth0 and return canned values
    monkeypatch.setattr(fn.os.path, "exists", lambda path: True)
    monkeypatch.setattr(builtins, "open", make_open_map())

    result = fn.get_network_adapters_info()
    assert result == {
        "network-adapters-info": {
            "eth0": {
                "ip-address": "192.168.0.2",
                "ipv6-address": "fe80::1",
                "netmask": "255.255.255.0",
                "mtu": "1500",
                "operational-state": "up",
                "link-detected": True,
                "speed": "1000",
                "duplex": "full",
                "pci-address": "01:00.0",
                "device-vendor": "Intel",
            }
        }
    }


def test_get_network_adapters_info_missing_files(monkeypatch):
    """If sysfs paths are absent the fields should be omitted."""
    snic_v4 = DummySnic(family=fn.socket.AF_INET,
                        address="10.0.0.1",
                        netmask="255.255.255.0")
    monkeypatch.setattr(fn.psutil, "net_if_addrs",
                        lambda: {"eth0": [snic_v4]})
    lshw_data = json.dumps(
        [{"logicalname": "eth0", "businfo": "pci@0000:02:00.0",
          "vendor": "Vendor"}]
    ).encode()
    monkeypatch.setattr(fn.subprocess, "check_output",
                        lambda *a, **kw: lshw_data)

    # no files exist -> os.path.exists returns False
    monkeypatch.setattr(fn.os.path, "exists", lambda path: False)

    # builtins.open will never be called, but patch defensively
    monkeypatch.setattr(builtins, "open", make_open_map())

    result = fn.get_network_adapters_info()
    assert result == {
        "network-adapters-info": {
            "eth0": {
                "ip-address": "10.0.0.1",
                "ipv6-address": "",
                "netmask": "255.255.255.0",
                "pci-address": "02:00.0",
                "device-vendor": "Vendor",
            }
        }
    }


# ------------- get_cpu_info ------------------------------------------------

def test_get_cpu_info(monkeypatch):
    """Ensure CPU information is gathered from psutil."""
    monkeypatch.setattr(fn.psutil, "cpu_count",
                        lambda logical=True: 8 if logical else 4)
    cpu_freq = types.SimpleNamespace(current=2500.0, max=3500.0, min=800.0)
    monkeypatch.setattr(fn.psutil, "cpu_freq", lambda: cpu_freq)
    monkeypatch.setattr(fn.psutil, "cpu_percent", lambda interval=0.5: 12.5)

    result = fn.get_cpu_info()
    assert result == {
        "cpu_info": {
            "physical-cores": 4,
            "total-cores": 8,
            "current-frequency": 2500.0,
            "max-frequency": 3500.0,
            "min-frequency": 800.0,
            "cpu-percentage": 12.5,
        }
    }


# ------------- get_memory_info ---------------------------------------------

def test_get_memory_info(monkeypatch):
    """Verify conversion of psutil virtual memory info."""
    vm = types.SimpleNamespace(
        total=10, available=9, used=1, percent=10,
        active=2, inactive=3, buffers=4, cached=5
    )
    monkeypatch.setattr(fn.psutil, "virtual_memory", lambda: vm)

    result = fn.get_memory_info()
    assert result == {
        "memory_info": {
            "total": 10,
            "available": 9,
            "used": 1,
            "percentage": 10,
            "active": 2,
            "inactive": 3,
            "buffers": 4,
            "cached": 5,
        }
    }


# ------------- get_pci_info ------------------------------------

def test_get_pci_info(monkeypatch):
    """Devices of unknown class should be skipped while NVMe/CXL are reported."""
    lspci = (
        "Slot:\t00:01.0\n"
        "Class:\tNon-Volatile memory controller\n"
        "Vendor:\tSamsung\n"
        "NUMANode:\t0\n\n"
        "Slot:\t00:02.0\n"
        "Class:\tCXL device\n"
        "Vendor:\tAcme\n"
        "NUMANode:\t1\n\n"
        "Slot:\t00:03.0\n"
        "Class:\tEthernet controller\n"
        "Vendor:\tFoo\n"
        "NUMANode:\t0\n\n"
    )
    monkeypatch.setattr(
        fn.subprocess,
        "check_output",
        lambda *a, **kw: lspci.encode(),
    )

    result = fn.get_pci_info()
    assert result == {
        "pci-info": [
            {
                "pci_address": "00:01.0",
                "device_manufacturer": "Samsung",
                "NUMA node": "0",
                "device_type": "nvme",
            },
            {
                "pci_address": "00:02.0",
                "device_manufacturer": "Acme",
                "NUMA node": "1",
                "device_type": "cxl",
            },
        ]
    }


# ------------- get_all_info ------------------------------------------------

def test_get_all_info_aggregates(monkeypatch):
    """get_all_info should merge dictionaries from the component functions."""
    monkeypatch.setattr(fn, "get_system_info",
                        lambda: {"system": 1})
    monkeypatch.setattr(fn, "get_cpu_info",
                        lambda: {"cpu": 2})
    monkeypatch.setattr(fn, "get_network_adapters_info",
                        lambda: {"net": 3})
    monkeypatch.setattr(fn, "get_memory_info",
                        lambda: {"mem": 4})
    monkeypatch.setattr(fn, "get_pci_info",
                        lambda: {"dev": 5})

    result = fn.get_all_info()
    assert result == {"system": 1, "cpu": 2, "net": 3, "mem": 4, "dev": 5}


# ------------- parse_args --------------------------------------------------

def test_parse_args_defaults(monkeypatch):
    """No arguments should produce default values."""
    monkeypatch.setattr(sys, "argv", ["prog"])

    args = fn.parse_args()
    assert args == {
        "info_type": "all",
        "log_level": "INFO",
        "log_file_path": "/var/log/svk/find_node_info.log",
    }


def test_parse_args_custom_values(monkeypatch):
    """Provided CLI flags should override defaults."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["prog", "--info-type", "network",
         "--log-level", "DEBUG"],
    )
    args = fn.parse_args()
    assert args == {
        "info_type": "network",
        "log_level": "DEBUG",
        "log_file_path": "/var/log/svk/find_node_info.log",
    }


# ------------- init_logger -------------------------------------------------

def test_init_logger_success(monkeypatch, tmp_path):
    """Logger should be created when the directory exists."""
    log_file = tmp_path / "out.log"

    monkeypatch.setattr(
        logging, "FileHandler", lambda path: logging.NullHandler()
    )
    fn.init_logger("INFO", str(log_file))
    assert isinstance(fn.logger, logging.Logger)
    assert fn.logger.level == logging.INFO
    # file handler should be present
    assert len(fn.logger.handlers) == 1


def test_init_logger_bad_directory(monkeypatch):
    """Invalid log directory leaves logger as None."""
    monkeypatch.setattr(logging, "FileHandler", lambda path: logging.NullHandler())
    fn.logger = None
    # Directory does not exist -> FileNotFoundError
    fn.init_logger("INFO", "/nonexistent/path/out.log")
    assert fn.logger is None


# ------------- get_command -------------------------------------------------

@pytest.mark.parametrize("info_type, func",
                         [("network", fn.get_network_adapters_info),
                          ("memory", fn.get_memory_info),
                          ("cpu", fn.get_cpu_info),
                          ("system", fn.get_system_info),
                          ("pci", fn.get_pci_info),
                          ("all", fn.get_all_info)])
def test_run_command_mapping(info_type, func):
    """get_command should return the function mapped to the info type."""
    assert fn.get_command(info_type) is func


# ------------- main --------------------------------------------------------

def test_main_non_linux(monkeypatch):
    """If the platform is unsupported an informative message should be printed."""
    monkeypatch.setattr(fn.platform, "system", lambda: "Windows")
    printed = []

    monkeypatch.setattr(builtins, "print", lambda msg: printed.append(msg))

    fn.main()
    assert printed == ["Platform not supported"]


def test_main_logger_failure(monkeypatch):
    """When the logger cannot be initialised the script should abort."""
    monkeypatch.setattr(fn.platform, "system", lambda: "Linux")
    monkeypatch.setattr(fn, "parse_args", lambda: {
        "info_type": "cpu",
        "log_level": "debug",
        "log_file_path": "/tmp/out.log",
    })
    monkeypatch.setattr(fn, "init_logger", lambda level, path: None)
    fn.logger = None  # simulate failure in init_logger

    printed = []
    monkeypatch.setattr(builtins, "print", lambda msg: printed.append(msg))

    fn.main()
    assert "Logger not initialized, couldn't run find node info" in printed


def test_main_success(monkeypatch):
    """Happy path where all helpers work and JSON is printed."""
    monkeypatch.setattr(fn.platform, "system", lambda: "Linux")
    monkeypatch.setattr(fn, "parse_args", lambda: {
        "info_type": "system",
        "log_level": "info",
        "log_file_path": "/tmp/out.log",
    })
    monkeypatch.setattr(fn, "init_logger",
                        lambda level, path: setattr(fn, 'logger', logging.getLogger("test")))
    monkeypatch.setattr(fn, "get_command",
                        lambda info: lambda: {"result": 42})
    printed = []
    monkeypatch.setattr(builtins, "print", lambda msg: printed.append(msg))

    fn.main()

    # The last printed line should be the JSON dump of the command result
    assert json.loads(printed[-1]) == {"result": 42}
