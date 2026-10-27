import pytest
import sqlparse

from cognos.backend.cmmd import CMMD

from cognos.backend.test.data_constants import (
    DUMMY_DEVICE_DIRECT_INFO, DUMMY_DEVICE_REMOTE_INFO
)


def test_cmmd_init():
    cmmd = CMMD(DUMMY_DEVICE_DIRECT_INFO, "direct")
    assert cmmd is not None


def test_cmmd_parse_device_info():
    cmmd = CMMD(DUMMY_DEVICE_REMOTE_INFO, "remote")
    assert cmmd.device_port == 10
    assert cmmd.device_id == 549755813888
    assert cmmd.attached_type == "remote"
    assert cmmd.capacity == 274877906944
    assert cmmd.device_type == "CMM-D"


def test_cmmd_serialize_insert_query():
    cmmd = CMMD(DUMMY_DEVICE_REMOTE_INFO, "remote")
    try:
        parsed = sqlparse.parse(cmmd.serialize_device_to_insert_query())
        assert len(parsed) > 0  # valid SQL query
    except Exception:
        assert False
