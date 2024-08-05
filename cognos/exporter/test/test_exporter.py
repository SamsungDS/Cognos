import asyncio
import os
import pytest
import pytest_asyncio
import sys
from unittest import mock

sys.path.append(os.path.abspath(  # noqa: E402
    os.path.join(os.path.dirname(__file__), '../..')))  # noqa: E402
from backend.cognos_influxdb_client import CognosInfluxDBClient
from exporter import recv_host_selection_handler, metrics_handler

pytest_plugins = ('pytest_asyncio',)


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
async def test_recv_host_selection_handler(mocker):
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
    try:
        done, pending = await asyncio.wait(
            [recv_host_selection_handler()], timeout=3)
        for task in pending:
            task.cancel()
    except Exception as error:
        print(f"ERROR: {str(error)}")


@pytest.mark.asyncio
async def test_metrics_handler(mock_websocket, mocker):
    influx_functions_to_mock = [
        'get_recent_dram_cxl_usage_data',
        'get_cpu_mem_usage',
        'get_memserver_capacity',
        'get_membox_usage',
        'get_membox_capacity',
        'get_membox_bandwidth',
        'get_attached_devices_count'
    ]
    for influx_fn in influx_functions_to_mock:
        mocker.patch(
            f'backend.cognos_influxdb_client.CognosInfluxDBClient.{influx_fn}',
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
