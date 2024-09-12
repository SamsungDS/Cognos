import argparse
import asyncio
import functools
import ssl
import json
import os
import sys
import websockets
import time

sys.path.append(os.path.abspath(  # noqa: E402
    os.path.join(os.path.dirname(__file__), '../..')))  # noqa: E402
from cognos.backend.cognos_influxdb_client import CognosInfluxDBClient
from cognos.backend.helper import fetch_cognos_configs

ws = None
global influx_client
influx_client = CognosInfluxDBClient()
global ssl_context
ssl_context = None


async def recv_host_selection_handler():
    try:
        while True:
            if ws:
                try:
                    message = json.loads(await asyncio.wait_for(ws.recv(), 3))
                    if message:
                        influx_client.filter_hosts = True
                        selected_host = message['host']['value']
                        influx_client.selected_host = (
                            selected_host[0]
                            if type(selected_host) is list else selected_host
                        )
                except asyncio.TimeoutError:
                    print("timeout occured while waiting for message")
                except Exception as error:
                    print(f"Error while receiving message {str(error)}")
            await asyncio.sleep(1)
            time.sleep(1)
    except websockets.ConnectionClosed:
        print("Connection closed, waiting for new connection.. ")
    except Exception as error:
        print(f"Error while running host select handler: {str(error)}")


async def metrics_handler(websocket, stop_event=False):
    global ws
    ws = websocket
    stop_event = asyncio.Event()
    while not stop_event.is_set():
        try:
            try:
                await ws.send(json.dumps({"type": "ping"}))
            except Exception:
                print("Ping failed")
                raise websockets.ConnectionClosed(
                    1000, 'Manually close the connection')

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
        except websockets.ConnectionClosed:
            print("Closing server side websocket..")
            await ws.close()
            print("Connection closed, waiting for new connection.. ")
            stop_event.set()
            break
        except Exception as e:
            print(f"ERROR: {str(e)} TYPE: {type(e)}")
            print("Closing server side websocket..")
            await ws.close()
            print("Connection closed, waiting for new connection.. ")
            stop_event.set()
            break


async def main():
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    configs = fetch_cognos_configs(parent_dir, 'config.json')
    stop_event = asyncio.Event()
    metrics_handler_with_stop_event = functools.partial(
        metrics_handler, stop_event=stop_event)
    if ssl_context:
        server = await websockets.serve(
            metrics_handler_with_stop_event,
            configs['exporter_ip'],
            configs['exporter_port'],
            ssl=ssl_context,
            ping_timeout=None
        )
    else:
        server = await websockets.serve(
            metrics_handler_with_stop_event,
            configs['exporter_ip'],
            configs['exporter_port'],
            ping_timeout=None
        )

    await recv_host_selection_handler()

    try:
        await server.wait_closed()
    except asyncio.CancelledError:
        print("Server has been stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--ssl', action='store_true')
    args = parser.parse_args()
    influx_client.mock = args.mock

    if args.ssl:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # Generate with Lets Encrypt, copied to this location,
        # chown to current user and 400 permissions
        ssl_cert = "/home/ubuntu/aws-deployment/cognos/exporter/fullchain.pem"
        ssl_key = "/home/ubuntu/aws-deployment/cognos/exporter/privkey.pem"
        ssl_context.load_cert_chain(ssl_cert, keyfile=ssl_key)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
