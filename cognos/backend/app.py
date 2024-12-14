from flask import Flask, jsonify
import click
import json
import mysql.connector
import os
import sys
from flask_cors import CORS

sys.path.append(
    os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), "../..")
    )
)  # noqa: E402

import cognos.backend.helper as helper
from cognos.backend.mock_datasource import Mock
from cognos.backend.cxlplugin_datasource import CXLPlugin


current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIGS = helper.fetch_cognos_configs(current_script_dir, "config.json")
API_VERSION = helper.fetch_api_version(current_script_dir)

global AGENT_ENDPOINT
AGENT_ENDPOINT = CONFIGS["agent_endpoint"]
# TODO: support multiple Node Servers / Agents at scale
global NODE_ENDPOINT
NODE_ENDPOINT = CONFIGS["node_endpoint"]


def create_app(mock=False):
    """Implements endpoints of Flask App"""
    app = Flask(__name__)
    CORS(app)
    app.config["CORS_HEADERS"] = "Content-Type"

    data_source = Mock() if mock else CXLPlugin()

    # clear out existing tables
    helper.clear_all_tables()

    @app.get(f"/api/{API_VERSION}/init")
    def init():
        """
        Derives initial configuration and connections between devices
        """
        return data_source.init()

    @app.post(f"/api/{API_VERSION}/update_metrics_host_filter")
    def post_update_metrics_host_filter():
        return data_source.update_metrics_host_filter()

    @app.get(f"/api/{API_VERSION}/topology")
    def get_topology():
        """
        Expected UI topology format - Example layout
        [
            { host: 'Host1',
            devices: [
                'D1',
                'D3',
                'D6'
            ]
            },{
            host: 'Host2',
            devices: [
                'D4'
            ]
            },{
            host: 'Host3',
            devices: [
                'D5'
            ]
            }
        ]
        """
        return data_source.get_topology()

    @app.get(f"/api/{API_VERSION}/hosts")
    def get_hosts():
        return data_source.get_hosts()

    @app.get(f"/api/{API_VERSION}/device_status")
    def get_device_status():
        # TODO: currently not implemented on SVK CXL Plugin end
        return jsonify({"status": 200})

    @app.post(f"/api/{API_VERSION}/devices")
    def post_devices():
        return data_source.post_devices()

    @app.post(f"/api/{API_VERSION}/membox_capacity")
    def membox_capacity():
        return data_source.membox_capacity()

    @app.post(f"/api/{API_VERSION}/host_devices")
    def host_devices():
        return data_source.host_devices()

    @app.get(f"/api/{API_VERSION}/available_devices")
    def available_devices():
        return data_source.available_devices()

    @app.delete(f"/api/{API_VERSION}/detach_device")
    def detach_device():
        return data_source.detach_device()

    @app.post(f"/api/{API_VERSION}/attach_device")
    def attach_device():
        return data_source.attach_device()

    @app.get(f"/api/{API_VERSION}/cxl/mb/info")
    def get_mb_info():
        return data_source.get_mb_info()

    @app.get(f"/api/{API_VERSION}/all_hosts")
    def get_all_hosts():
        return data_source.get_all_hosts_info()

    # setup database tables based on current state during initial boot
    data_source.setup_tables()
    return app


@click.command()
@click.option("--mock", "-m", is_flag=True, help="mock mode")
@click.option("--host", "-h", required=True, help="IP of host of CAL")
@click.option("--port", "-p", required=True, help="Port to run CAL on")
def main(mock, host, port):
    app = create_app(mock)
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
