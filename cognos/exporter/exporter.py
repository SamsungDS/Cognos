import argparse
import asyncio
import click
import functools
import json
import os
import sys
import websockets
import time

sys.path.append(os.path.abspath(  # noqa: E402
    os.path.join(os.path.dirname(__file__), '..')))  # noqa: E402
from backend.cognos_influxdb_client import CognosInfluxDBClient
from backend.helper import fetch_cognos_configs

ws = None
global influx_client
influx_client = CognosInfluxDBClient()


async def recv_host_selection_handler():
    while True:
        if ws:
            message = json.loads(await ws.recv())
            if message:
                influx_client.filter_hosts = True
                selected_host = message['host']['value']
                influx_client.selected_host = selected_host[0] if type(selected_host) is list else selected_host
        await asyncio.sleep(1)
        time.sleep(1)


async def metrics_handler(websocket, stop_event=False):
    global ws
    ws = websocket
    while not stop_event.is_set():
        try:
            event = {
                "type": "dram_cxl_usage",
                "data":  influx_client.get_recent_dram_cxl_usage_data()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            event = {
                "type": "cpu_mem_usage",
                "data": influx_client.get_cpu_mem_usage()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            event = {
                "type": "memserver_capacity",
                "data": influx_client.get_memserver_capacity()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            event = {
                "type": "cmmb_usage",
                "data": influx_client.get_membox_usage()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            event = {
                "type": "cmmb_capacity",
                "data": influx_client.get_membox_capacity()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            event = {
                "type": "cmmb_bandwidth",
                "data": influx_client.get_membox_bandwidth()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            event = {
                "type": "devices_count",
                "data": influx_client.get_attached_devices_count()
            }
            try:
                await websocket.send(json.dumps(event))
            except Exception:
                pass

            await asyncio.sleep(5)
            time.sleep(5)
        except StopAsyncIteration:
            stop_event.set()
        except Exception as e:
            print(f"ERROR: {str(e)} TYPE: {type(e)}")


# @click.command()
# @click.option('--mock', '-m', is_flag=True, help="mock mode")
# def set_mode(mock):
#     influx_client.mock = mock
#     print(f"Running exporter in mock mode: {influx_client.mock}")

async def main():
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    configs = fetch_cognos_configs(parent_dir, 'config.json')
    stop_event = asyncio.Event()
    metrics_handler_with_stop_event = functools.partial(
        metrics_handler, stop_event=stop_event)
    start_server = websockets.serve(
        metrics_handler_with_stop_event,
        configs['exporter_ip'],
        configs['exporter_port'],
        ping_timeout=None
    )
    tasks = [start_server, recv_host_selection_handler()]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mock', action='store_true')
    args = parser.parse_args()
    influx_client.mock = args.mock
    print(f"Running exporter in mock mode: {influx_client.mock} ..")
    asyncio.run(main())
