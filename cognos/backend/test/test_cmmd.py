import pytest

from cognos.backend.cmmd import CMMD


def test_cmmd_init():
    cmmd = CMMD("DEV1")
    assert cmmd.device_name == "DEV1"


# TODO: placeholder, node name currently not defined
def test_cmmd_node_name():
    cmmd = CMMD("DEV1")
    cmmd.node_name


# TODO: placeholder, device id currently not defined
def test_cmmd_device_id():
    cmmd = CMMD("DEV1")
    cmmd.device_id


def test_cmmd_device_type():
    cmmd = CMMD("DEV1")
    assert cmmd.device_type == "cmmd"


# TODO: placeholder, device info currently not defined
def test_cmmd_device_info():
    cmmd = CMMD("DEV1")
    cmmd.device_info


# TODO: placeholder, device status currently not defined
def test_cmmd_device_status():
    cmmd = CMMD("DEV1")
    cmmd.device_status


# TODO: placeholder, fm type currently not defined
def test_cmmd_fmtype():
    cmmd = CMMD("DEV1")
    cmmd.fm_type


# TODO: placeholder, capacity currently not defined
def test_cmmd_capacity():
    cmmd = CMMD("DEV1")
    cmmd.capacity


# TODO: placeholder, attach to node currently not defined
def test_attach_to_node():
    cmmd = CMMD("DEV1")
    cmmd.attach_to_node()


# TODO: placeholder, detach from node currently not defined
def test_cmmd_detach_from_node():
    cmmd = CMMD("DEV1")
    cmmd.detach_from_node()


# TODO: placeholder, get device info currently not defined
def test_cmmd_get_device_info():
    cmmd = CMMD("DEV1")
    cmmd.get_device_info()


# TODO: placeholder, get device stats currently not defined
def test_cmmd_get_device_stats():
    cmmd = CMMD("DEV1")
    cmmd.get_device_stats()


# TODO: placeholder, get device errors currently not defined
def test_cmmd_get_device_errors():
    cmmd = CMMD("DEV1")
    cmmd.get_device_errors()


# TODO: placeholder, get device alerts currently not defined
def test_cmmd_get_device_alerts():
    cmmd = CMMD("DEV1")
    cmmd.get_device_alerts()


# TODO: placeholder, get device health currently not defined
def test_cmmd_get_device_health():
    cmmd = CMMD("DEV1")
    cmmd.get_device_health()


# TODO: placeholder, configure device currently not defined
def test_cmmd_configure_device():
    cmmd = CMMD("DEV1")
    cmmd.configure_device()


# TODO: placeholder, get device features currently not defined
def test_cmmd_get_device_features():
    cmmd = CMMD("DEV1")
    cmmd.get_device_features()


# TODO: placeholder, get device QOS params currently not defined
def test_cmmd_get_device_QOS_params():
    cmmd = CMMD("DEV1")
    cmmd.get_device_QOS_params()


# TODO: placeholder, set device QOS params currently not defined
def test_cmmd_set_device_QOS_params():
    cmmd = CMMD("DEV1")
    cmmd.set_device_QOS_params()


# TODO: placeholder, get_device_maintenance operations currently not defined
def test_cmmd_get_device_maintenance_operations():
    cmmd = CMMD("DEV1")
    cmmd.get_device_maintenance_operations()


# TODO: placeholder, get device capabilities not defined
def test_cmmd_get_device_capabilities():
    cmmd = CMMD("DEV1")
    cmmd.get_device_capabilities()


# TODO: placeholder, get device event records currently not defined
def test_cmmd_get_device_event_records():
    cmmd = CMMD("DEV1")
    cmmd.get_device_event_records()
