import pytest
import sqlparse

from cognos.backend.cmmh import CMMH

from cognos.backend.test.data_constants import DUMMY_DEVICE_DIRECT_INFO


def test_cmmh_init():
    cmmh = CMMH(DUMMY_DEVICE_DIRECT_INFO, "direct")
    assert cmmh is not None


def test_cmmh_parse_info():
    cmmh = CMMH(DUMMY_DEVICE_DIRECT_INFO, "direct")
    assert cmmh.device_id == 33638416369152
    assert cmmh.device_type == "CMM-H"
    assert cmmh.capacity == (516079 * 1000000)
    assert cmmh.attached_type == "direct"


def test_cmmh_serialize_insert_query():
    cmmh = CMMH(DUMMY_DEVICE_DIRECT_INFO, "direct")
    try:
        parsed = sqlparse.parse(cmmh.serialize_device_to_insert_query())
        assert len(parsed) > 0  # valid SQL query
    except Exception:
        assert False
