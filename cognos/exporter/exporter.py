import sys
import os
import argparse
import asyncio
import functools
import ssl
import json
import websockets
import time
paths = ['../..', '.', '..']
for p in paths:
    sys.path.append(os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), p)))  # noqa: E402
from cognos.backend.cognos_influxdb_client import (  # noqa: E402
    CognosInfluxDBClient
)
from cognos.backend.helper import fetch_cognos_configs, get_metrics_host_filter  # noqa: E402


ws = None
global influx_client
influx_client = CognosInfluxDBClient()
global ssl_context
ssl_context = None


async def send_metrics_event(websocket, event_type, data, stop_event):
    print("IN SEND METRICS EVENT")
    try:
        event = {
            "type": event_type,
            "data":  data
        }
        await websocket.send(json.dumps(event))
        print(f"sent metrics for {event_type} with data {data}")
    except websockets.exceptions.ConnectionClosedOK:
        print("FOUND WEBSOCKET RECV MSG WHILE CLOSING")
        # stop_event.set()

    except websockets.exceptions.ConnectionClosedError:
        print("FOUND WEBSOCKET CONNECTION CLOSED ERROR")
        # stop_event.set()
    except Exception as e:
        print(f"{event_type} failed: {str(e)}")
        print(f"Exception Type: {type(e).__name__}")
        pass


async def recv_host_selection_handler(stop_event):
    try:

        print(f"stop event type: {stop_event}")
        while not stop_event.is_set():
            # search for filter in DB
            latest_host_selected = get_metrics_host_filter()
            print(f"RECVD LATEST HOST: {latest_host_selected}")
            if latest_host_selected and latest_host_selected != '':
                influx_client.filter_hosts = True
                influx_client.selected_host = latest_host_selected
                print(f"INFLUX FILTER IS SET TO: {influx_client.selected_host}")
            """
            max_idle_time = 20
            last_message_time = time.time()
            print("Running recv host routine")
            if ws and ws.open and ((time.time() - last_message_time) < max_idle_time):
                print("Websocket connection is open")
                try:
                    await ws.ping()
                    print("WAITING TO RECV MSG FROM UI")
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
                    last_message_time = time.time()
                    #async for message in ws:
                    print(f"RECV'D MSG FROM UI: {message}")

                    if not message or not message['host']:
                        continue
                    # elif message:
                    #     influx_client.filter_hosts = True
                    #     selected_host = message['host']['value']
                    #     influx_client.selected_host = (
                    #         selected_host[0]
                    #         if type(selected_host) is list else selected_host
                    #     )
                except asyncio.TimeoutError:
                    print("timeout occured while waiting for message")
                except websockets.exceptions.ConnectionClosedError:
                    print("Websocket connection closed unexpectedly")
                except Exception as error:
                    print(f"Error while receiving message {str(error)}")
            elif ws and ((time.time() - last_message_time) > max_idle_time):
                print("Exporter host handler waited to long for msg, closing ws..")
                await ws.close()
                break
            else:
                print("Waiting for websocket to come online")
            """
            await asyncio.sleep(0.1)
            time.sleep(0.1)
    except websockets.ConnectionClosed:
        print("Connection closed, waiting for new connection.. ")
        # stop_event.set()
    except Exception as error:
        print(f"Error while running host select handler: {str(error)}")


async def metrics_handler(websocket, stop_event=None):
    global ws
    ws = websocket
    # stop_event = asyncio.Event()
    while not stop_event.is_set():
        print("Running metrics handler routine")
        try:
            print(f"CURR SELECTED HOST FROM UI: {influx_client.selected_host}")
            if ws.open:
                try:
                    await ws.send(json.dumps({"type": "ping"}))
                    print("ping from exporter to UI successful")
                except Exception:
                    print("Ping failed")
                    raise websockets.ConnectionClosed(
                        3000, 'Manually close the connection')
                    break
            
                await send_metrics_event(
                    websocket,
                    "dram_cxl_usage",
                    influx_client.get_recent_dram_cxl_usage_data(),
                    stop_event
                )
            
                await send_metrics_event(
                    websocket,
                    "cpu_mem_usage",
                    influx_client.get_cpu_mem_usage(),
                    stop_event
                )
            
                await send_metrics_event(
                    websocket,
                    "memserver_capacity",
                    influx_client.get_memserver_capacity(),
                    stop_event
                )
            
                await send_metrics_event(
                    websocket,
                    "cmmb_usage",
                    influx_client.get_membox_usage(),
                    stop_event
                )
            
                await send_metrics_event(
                    websocket,
                    "cmmb_capacity",
                    influx_client.get_membox_capacity(),
                    stop_event
                )

                await send_metrics_event(
                    websocket,
                    "cmmb_bandwidth",
                    influx_client.get_membox_bandwidth(),
                    stop_event
                )
            
                await send_metrics_event(
                    websocket,
                    "devices_count",
                    influx_client.get_attached_devices_count(),
                    stop_event
                )

            await asyncio.sleep(3)
            time.sleep(3)
        except StopAsyncIteration:
            stop_event.set()
        except websockets.ConnectionClosed:
            print("Closing server side websocket..")
            await ws.close()
            print("Connection closed, waiting for new connection.. ")
            # stop_event.set()
            break
        except ZeroDivisionError:
            print("Hit Zero Division Error, closing websocket.. ")
            await ws.close()
            # stop_event.set()
            break
        except Exception as e:
            print(f"ERROR: {str(e)} TYPE: {type(e)}")
            print("Closing server side websocket..")
            await ws.close()
            print("Connection closed, waiting for new connection.. ")
            # stop_event.set()
            break
    print("exited main metrics handler loop")
    await asyncio.sleep(0.1)
    time.sleep(1)




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

    await recv_host_selection_handler(stop_event=stop_event)

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
