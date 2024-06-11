import pytest

from db_setup import (
    create_database, get_database_connection, check_db_exists,
    setup_devices_table, setup_host_device_connections_table,
    setup_hosts_table, setup_mem_box_table
)


def test_create_database(mocker, mock_db):
    mocker.patch('db_setup.get_database_connection', return_value=True)
    mocker.patch('db_setup.check_db_exists', return_value=True)
    create_database("test_cognos_db")
    mocker.patch('db_setup.check_db_exists', return_value=False)
    with pytest.raises(Exception) as error:
        create_database("test_cognos_db")


def test_check_db_exists(mocker):
    cursor = mocker.MagicMock()
    dummy_data = [
        ("testdb1",)
    ]
    cursor.fetchall.return_value = dummy_data
    expected_db_name = "testdb1"
    non_expected_db_name = "azsdhasodaj"
    assert check_db_exists(expected_db_name, cursor)
    assert not check_db_exists(non_expected_db_name, cursor)


def test_get_database_connection(mock_db):
    get_database_connection("test_cognos")


def test_setup_devices_table(mock_db):
    mock_connection, mock_cursor = mock_db
    setup_devices_table(mock_connection, mock_cursor)


def test_setup_host_device_connections_table(mock_db):
    mock_connection, mock_cursor = mock_db
    setup_host_device_connections_table(mock_connection, mock_cursor)


def test_setup_hosts_table(mock_db):
    mock_connection, mock_cursor = mock_db
    setup_hosts_table(mock_connection, mock_cursor)


def test_setup_membox_table(mock_db):
    mock_connection, mock_cursor = mock_db
    setup_mem_box_table(mock_connection, mock_cursor)
