import pytest

from cognos.backend.cmmh import CMMH


def test_cmmh_init():
    cmmh = CMMH("DEV2")
    assert cmmh.device_name == "DEV2"


# TODO: placeholder, node name currently not defined
def test_cmmh_node_name():
    cmmh = CMMH("DEV1")
    cmmh.node_name


# TODO: placeholder, device id currently not defined
def test_cmmh_device_id():
    cmmh = CMMH("DEV1")
    cmmh.device_id


def test_cmmh_device_type():
    cmmh = CMMH("DEV1")
    assert cmmh.device_type == "cmmh"


# TODO: placeholder, device info currently not defined
def test_cmmh_device_info():
    cmmh = CMMH("DEV1")
    cmmh.device_info


# TODO: placeholder, device status currently not defined
def test_cmmh_device_status():
    cmmh = CMMH("DEV1")
    cmmh.device_status


# TODO: placeholder, fm type currently not defined
def test_cmmh_fmtype():
    cmmh = CMMH("DEV1")
    cmmh.fm_type


# TODO: placeholder, capacity currently not defined
def test_cmmh_capacity():
    cmmh = CMMH("DEV1")
    cmmh.capacity


# TODO: placeholder, get device info currently not defined
def test_cmmh_get_device_info():
    cmmh = CMMH("DEV1")
    cmmh.get_device_info()


# TODO: placeholder, get device stats currently not defined
def test_cmmh_get_device_stats():
    cmmh = CMMH("DEV1")
    cmmh.get_device_stats()


# TODO: placeholder, get device errors currently not defined
def test_cmmh_get_device_errors():
    cmmh = CMMH("DEV1")
    cmmh.get_device_errors()


# TODO: placeholder, get device alerts currently not defined
def test_cmmh_get_device_alerts():
    cmmh = CMMH("DEV1")
    cmmh.get_device_alerts()


# TODO: placeholder, get device health currently not defined
def test_cmmh_get_device_health():
    cmmh = CMMH("DEV1")
    cmmh.get_device_health()


# TODO: placeholder, configure device currently not defined
def test_cmmh_configure_device():
    cmmh = CMMH("DEV1")
    cmmh.configure_device()


# TODO: placeholder, get device features currently not defined
def test_cmmh_get_device_features():
    cmmh = CMMH("DEV1")
    cmmh.get_device_features()


# TODO: placeholder, get device QOS params currently not defined
def test_cmmh_get_device_QOS_params():
    cmmh = CMMH("DEV1")
    cmmh.get_device_QOS_params()


# TODO: placeholder, set device QOS params currently not defined
def test_cmmh_set_device_QOS_params():
    cmmh = CMMH("DEV1")
    cmmh.set_device_QOS_params()


# TODO: placeholder, get_device_maintenance operations currently not defined
def test_cmmh_get_device_maintenance_operations():
    cmmh = CMMH("DEV1")
    cmmh.get_device_maintenance_operations()


# TODO: placeholder, get device capabilities not defined
def test_cmmh_get_device_capabilities():
    cmmh = CMMH("DEV1")
    cmmh.get_device_capabilities()


# TODO: placeholder, get device event records currently not defined
def test_cmmh_get_device_event_records():
    cmmh = CMMH("DEV1")
    cmmh.get_device_event_records()
