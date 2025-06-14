import os
import pytest

from cognos.backend.sqlite_client import SqliteClient
from cognos.backend.test.data_constants import (
    CREATE_DEVICES_TABLE_QUERY,
    DUMMY_INSERT_DEVICE_QUERY,
    DUMMY_DEVICES_FETCH_QUERY,
    DUMMY_DEVICES_SINGLE_FETCH_QUERY,
    DUMMY_COUNT_DEVICES_QUERY
)


def test_create_sqlite_client(mock_sqlite_connection):
    sql_client = SqliteClient(svk_data_path=os.getcwd())
    assert sql_client is not None


def test_execute_query(mock_sqlite_client):
    mock_sqlite_client.execute_query(CREATE_DEVICES_TABLE_QUERY)


def test_table_description(mock_sqlite_client):
    mock_sqlite_client.execute_query(CREATE_DEVICES_TABLE_QUERY)
    mock_sqlite_client.table_description("devices")


def test_table_records(mock_sqlite_client):
    mock_sqlite_client.get_table_records("devices")


def test_exec_query(mock_sqlite_client):
    mock_sqlite_client.execute_query(CREATE_DEVICES_TABLE_QUERY)
    mock_sqlite_client.exec_query(DUMMY_INSERT_DEVICE_QUERY, tuple())


def test_exec_fetch_query(mock_sqlite_client):
    mock_sqlite_client.execute_query(CREATE_DEVICES_TABLE_QUERY)
    mock_sqlite_client.exec_fetch_query(DUMMY_DEVICES_FETCH_QUERY, tuple())


def test_exec_fetch_singlerecord_query(mock_sqlite_client):
    mock_sqlite_client.execute_query(CREATE_DEVICES_TABLE_QUERY)
    mock_sqlite_client.exec_fetch_singlerecord_query(
        DUMMY_DEVICES_SINGLE_FETCH_QUERY, tuple())


def test_count_query(mock_sqlite_client):
    mock_sqlite_client.count_query(DUMMY_COUNT_DEVICES_QUERY)
