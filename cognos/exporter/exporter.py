import sys
import os
import argparse
import asyncio
import functools
import ssl
import json
import websockets
import time

paths = ["../..", ".", ".."]
for p in paths:
    sys.path.append(
        os.path.abspath(  # noqa: E402
            os.path.join(os.path.dirname(__file__), p)
        )
    )  # noqa: E402
from cognos.backend.cognos_influxdb_client import (  # noqa: E402
    CognosInfluxDBClient
)
from cognos.backend.helper import (
    fetch_cognos_configs,
    get_metrics_host_filter
)  # noqa: E402


ws = None
global influx_client
influx_client = CognosInfluxDBClient()


async def send_metrics_event(websocket, event_type, data, stop_event):
    try:
        event = {"type": event_type, "data": data}
        await websocket.send(json.dumps(event))
    except websockets.exceptions.ConnectionClosedOK:
        print("FOUND WEBSOCKET RECV MSG WHILE CLOSING")
    except websockets.exceptions.ConnectionClosedError:
        print("FOUND WEBSOCKET CONNECTION CLOSED ERROR")
    except Exception as e:
        print(f"{event_type} failed: {str(e)}")
        print(f"Exception Type: {type(e).__name__}")
        pass


async def recv_host_selection_handler(stop_event):
    try:
        while not stop_event.is_set():
            # search for filter in DB
            latest_host_selected = get_metrics_host_filter()
            if latest_host_selected and latest_host_selected != "":
                influx_client.filter_hosts = True
                influx_client.selected_host = latest_host_selected
            await asyncio.sleep(0.1)
            time.sleep(0.1)
    except websockets.ConnectionClosed:
        print("Connection closed, waiting for new connection.. ")
    except Exception as error:
        print(f"Error while running host select handler: {str(error)}")


async def metrics_handler(websocket, stop_event=None):
    global ws
    ws = websocket
    while not stop_event.is_set():
        print("Running metrics handler routine")
        try:
            try:
                await ws.send(json.dumps({"type": "ping"}))
            except Exception:
                print("Ping failed, closing websocket connection")
                raise websockets.ConnectionClosed(
                    3000, "Manually close the connection"
                )

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
            break
        except ZeroDivisionError:
            print("Hit Zero Division Error, closing websocket.. ")
            await ws.close()
            break
        except Exception as e:
            print(f"ERROR: {str(e)} TYPE: {type(e)}")
            await ws.close()
            break
    print("exited main metrics handler loop")
    await asyncio.sleep(0.1)
    time.sleep(1)


def get_sslcontext_with_certchain(configs):
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_cert = configs["ssl_cert"]
    ssl_key = configs["ssl_key"]
    ssl_context.load_cert_chain(ssl_cert, keyfile=ssl_key)
    return ssl_context


async def main():
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    configs = fetch_cognos_configs(parent_dir, "config.json")
    stop_event = asyncio.Event()
    metrics_handler_with_stop_event = functools.partial(
        metrics_handler, stop_event=stop_event
    )
    if configs["ssl"]:
        server = await websockets.serve(
            metrics_handler_with_stop_event,
            configs["exporter_ip"],
            configs["exporter_port"],
            ssl=get_sslcontext_with_certchain(configs),
            ping_timeout=None
        )
    else:
        server = await websockets.serve(
            metrics_handler_with_stop_event,
            configs["exporter_ip"],
            configs["exporter_port"],
            ping_timeout=None
        )

    await recv_host_selection_handler(stop_event=stop_event)

    try:
        await server.wait_closed()
    except asyncio.CancelledError:
        print("Server has been stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    influx_client.mock = args.mock

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
