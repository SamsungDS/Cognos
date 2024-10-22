from unittest import mock
from influxdb_client import InfluxDBClient
import asyncio
import os
import sys
import pytest
import pytest_asyncio
import websockets
paths = ['../..', '.', '../../..', '..']
for p in paths:
    sys.path.append(os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), p)))  # noqa: E402
from cognos.backend.cognos_influxdb_client import (  # noqa: E402
    CognosInfluxDBClient
)
from cognos.exporter.exporter import (
    recv_host_selection_handler, metrics_handler,  # noqa: E402
    send_metrics_event
)
from cognos.backend.helper import get_cognos_influx_functions  # noqa: E402

pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def mock_db(mocker):
    mock_connection = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()

    mocker.patch('mysql.connector.connect', return_value=mock_connection)
    mock_connection.cursor.return_value = mock_cursor
    mock_cursor.execute.return_value = True

    mocker.patch('cognos.backend.helper.connect_to_mysql',
                 return_value=(mock_connection, mock_cursor))
    mocker.patch('cognos.backend.helper.disconnect_mysql', return_value=True)

    return mock_connection, mock_cursor


@pytest_asyncio.fixture(scope="session")
async def mock_websocket():
    mock_ws = mock.Mock()
    mock_ws.recv = mock.AsyncMock(side_effect=[
        '{"type": "message", "data": "Hello"}',
        '{"type": "message", "data": "World"}',
        None  # Needed to signify end of messages
    ])
    mock_ws.send = mock.AsyncMock(side_effect=[
        '{"type": "test_event", "data": "metric_data"}',
    ])
    return mock_ws


@pytest.mark.asyncio
async def test_mock_websocket_send(mock_websocket):
    await mock_websocket.send('{"type": "test_event", "data": "metric_data"}')


@pytest.mark.asyncio
async def test_mock_websocket_recv(mock_websocket):
    message = await mock_websocket.recv()
    assert message


@pytest.mark.asyncio
async def test_send_metrics_event(mock_websocket):
    mock_event_type = "dram_cxl_usage"
    mock_data = [{"dram_usage": 22, "cxl_usage": 54}]
    stop_event = asyncio.Event()
    send_metrics_event(mock_websocket, mock_event_type, mock_data, stop_event)


@pytest.mark.asyncio
async def test_recv_host_selection_handler(mocker, mock_websocket):
    mocker.patch(
        'json.loads',
        return_value=(
            {
                "host": {
                    "value": "samsung.host1.com",
                    "label": "samsung.host1.com"
                }
            }
        )
    )
    mocker.patch('cognos.exporter.exporter.ws', mock_websocket)
    mocker.patch(
        'cognos.backend.helper.get_metrics_host_filter',
        return_value=''
    )
    stop_event = asyncio.Event()
    try:
        done, pending = await asyncio.wait(
            [recv_host_selection_handler(stop_event)], timeout=3)
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")


@pytest.mark.asyncio
async def test_recv_host_timeout_error(mocker, mock_websocket, mock_db):
    mocker.patch(
        'json.loads',
        return_value=(
            {
                "host": {
                    "value": "samsung.host1.com",
                    "label": "samsung.host1.com"
                }
            }
        ),
        side_effect=asyncio.TimeoutError("Mocked timeout..")
    )
    mocker.patch('cognos.exporter.exporter.ws', mock_websocket)
    try:
        done, pending = await asyncio.wait(
            [recv_host_selection_handler()], timeout=3)
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")


@pytest.mark.asyncio
async def test_recv_host_general_exception(mocker, mock_websocket):
    mocker.patch(
        'json.loads',
        return_value=(
            {
                "host": {
                    "value": "samsung.host1.com",
                    "label": "samsung.host1.com"
                }
            }
        ),
        side_effect=Exception("Mocked exception..")
    )
    mocker.patch('cognos.exporter.exporter.ws', mock_websocket)
    try:
        done, pending = await asyncio.wait(
            [recv_host_selection_handler()], timeout=3)
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")


@pytest.mark.asyncio
async def test_metrics_handler(mock_websocket, mocker):
    mocker.patch('influxdb_client.InfluxDBClient')
    influx_functions_to_mock = get_cognos_influx_functions()
    cognos_influx_db_lib_path = (
        'cognos.backend.cognos_influxdb_client.CognosInfluxDBClient'
    )
    for influx_fn in influx_functions_to_mock:
        mocker.patch(
            f'{cognos_influx_db_lib_path}.{influx_fn}',
            return_value=(
                {
                    "type": "test_event",
                    "data": [{"dram_usage": 22, "cxl_usage": 54}]
                }
            )
        )

    influx_client = CognosInfluxDBClient()
    influx_client.get_recent_dram_cxl_usage_data()
    influx_client.get_cpu_mem_usage()
    influx_client.get_memserver_capacity()
    influx_client.get_membox_usage()
    influx_client.get_membox_capacity()
    influx_client.get_membox_bandwidth()
    influx_client.get_attached_devices_count()

    try:
        stop_event = asyncio.Event()
        done, pending = (
            await asyncio.wait(
                [metrics_handler(mock_websocket, stop_event)],
                timeout=3
            )
        )
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")


@pytest.mark.asyncio
async def test_metrics_handler_with_failing_websocket(mocker):
    mocker.patch('influxdb_client.InfluxDBClient')
    influx_functions_to_mock = get_cognos_influx_functions()
    cognos_influx_db_lib_path = (
        'cognos.backend.cognos_influxdb_client.CognosInfluxDBClient'
    )
    for influx_fn in influx_functions_to_mock:
        mocker.patch(
            f'{cognos_influx_db_lib_path}.{influx_fn}',
            return_value=(
                {
                    "type": "test_event",
                    "data": [{"dram_usage": 22, "cxl_usage": 54}]
                }
            )
        )

    influx_client = CognosInfluxDBClient()
    influx_client.get_recent_dram_cxl_usage_data()
    influx_client.get_cpu_mem_usage()
    influx_client.get_memserver_capacity()
    influx_client.get_membox_usage()
    influx_client.get_membox_capacity()
    influx_client.get_membox_bandwidth()
    influx_client.get_attached_devices_count()

    bad_ws = mocker.patch('websockets.connect', new_callable=mock.AsyncMock)

    bad_ws.return_value.__aenter__.return_value.send = mock.AsyncMock(
        side_effect=Exception("send failed")
    )

    try:
        stop_event = asyncio.Event()
        done, pending = (
            await asyncio.wait(
                [metrics_handler(bad_ws, stop_event)],
                timeout=3
            )
        )
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")


@pytest.mark.asyncio
async def test_failed_influx_queries(mocker, mock_websocket):
    mocker.patch('influxdb_client.InfluxDBClient')
    influx_functions_to_mock = get_cognos_influx_functions()
    cognos_influx_db_lib_path = (
        'cognos.backend.cognos_influxdb_client.CognosInfluxDBClient'
    )
    for influx_fn in influx_functions_to_mock:
        mocker.patch(
            f'{cognos_influx_db_lib_path}.{influx_fn}',
            return_value=(
                {
                    "type": "test_event",
                    "data": [{"dram_usage": 22, "cxl_usage": 54}]
                }
            ),
            side_effect=Exception("Mocked Exception..")
        )

    influx_client = CognosInfluxDBClient()

    try:
        stop_event = asyncio.Event()
        done, pending = (
            await asyncio.wait(
                [metrics_handler(mock_websocket, stop_event)],
                timeout=3
            )
        )
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")
