import pytest
from unittest.mock import patch, MagicMock
from db_setup import (
    create_database,
    get_database_connection,
    check_db_exists,
    setup_devices_table,
    setup_host_device_connections_table,
    setup_hosts_table,
    setup_mem_box_table,
    setup_scmc_table,
    shutdown_db_connection,
)


def test_create_database(mocker, mock_db):
    mocker.patch("db_setup.get_database_connection", return_value=True)
    mocker.patch("db_setup.check_db_exists", return_value=True)
    create_database("test_cognos_db")
    mocker.patch("db_setup.check_db_exists", return_value=False)
    with pytest.raises(Exception) as error:
        create_database("test_cognos_db")


def test_check_db_exists(mocker):
    cursor = mocker.MagicMock()
    dummy_data = [("testdb1",)]
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


def test_setup_scmc_table():
    # Create a mock database and cursor
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    # Call the setup_scmc_table function
    setup_scmc_table(mock_db, mock_cursor)

    # Check if the SQL command was executed
    expected_query = (
        "CREATE TABLE IF NOT EXISTS"
        " scmc (metrics_host_filter VARCHAR(255));"
    )
    mock_cursor.execute.assert_called_once_with(expected_query)

    # Check if commit was called on the db
    mock_db.commit.assert_called_once()


def test_shutdown_db_connection():
    mock_db = MagicMock()

    # Call the shutdown_db_connection function
    shutdown_db_connection(mock_db)

    # Assert that the close method was called on the db
    mock_db.close.assert_called_once()


if __name__ == "__main__":
    pytest.main()
