from flask import Flask
import click
import os
import sys
from flask_cors import CORS

sys.path.append(
    os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), "../..")
    )
)  # noqa: E402

import cognos.backend.helper as helper
from cognos.backend.cognos_client import Cognos


current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIGS = helper.fetch_cognos_configs(current_script_dir, "config.json")
CAL_API_VERSION = helper.fetch_cal_api_version(current_script_dir)

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
    cognos = Cognos(mock=mock)

    @app.get(f"/api/{CAL_API_VERSION}/scmc_version")
    def get_version():
        """
        Returns SCMC Version
        """
        if not cognos.scmc_version:
            return helper.create_notfound_response_from_payload({})
        elif "error" in cognos.scmc_version:
            return helper.create_notfound_response_from_payload(
                cognos.scmc_version
            )
        else:
            return helper.create_response_from_payload(cognos.scmc_version)

    @app.get(f"/api/{CAL_API_VERSION}/topology")
    def get_topology():
        """
        Returns topology of Cognos System
        """
        return helper.create_response_from_payload(
            cognos.fetch_topology()
        )

    @app.get(f"/api/{CAL_API_VERSION}/hosts")
    def get_hosts():
        return helper.create_response_from_payload(
            cognos.get_remote_hosts()
        )

    @app.get(f"/api/{CAL_API_VERSION}/nodes")
    def get_nodes():
        """
        Returns all node_names of Cognos System
        """
        return helper.create_response_from_payload(
            cognos.get_nodes()
        )

    @app.post(f"/api/{CAL_API_VERSION}/devices")
    def remote_devices():
        """
        Gets device information for all remote
        attached devices
        """
        return helper.create_response_from_payload(
            cognos.get_remote_devices()
        )

    @app.post(f"/api/{CAL_API_VERSION}/membox_capacity")
    def membox_capacity():
        return helper.create_response_from_payload(
            cognos.membox_capacity()
        )

    @app.post(f"/api/{CAL_API_VERSION}/host_devices")
    def host_devices():
        """
        Input: {"host": <hostname>}
        Returns: JSON of devices and their information that
                 are attached to the input host
        """
        return helper.create_response_from_payload(
            cognos.host_devices()
        )

    @app.get(f"/api/{CAL_API_VERSION}/available_devices")
    def available_devices():
        """
        Returns list of device names
        """
        return helper.create_response_from_payload(
            cognos.available_remote_devices()
        )

    @app.delete(f"/api/{CAL_API_VERSION}/detach_device")
    def detach_device():
        """
        Performs Detach Operation

        Returns list of json objects containing attached device information
        """
        return helper.create_response_from_payload(
            cognos.detach_remote_device()
        )

    @app.post(f"/api/{CAL_API_VERSION}/attach_device")
    def attach_device():
        """
        Performs Attach Operation

        Returns list of json objects containing attached device information
        """
        return helper.create_response_from_payload(
            cognos.attach_remote_device()
        )

    @app.get(f"/api/{CAL_API_VERSION}/all_hosts")
    def get_all_hosts():
        """
        Returns list of hosts in format {"value": host, "label": host}
        """
        return helper.create_response_from_payload(
            cognos.get_hosts()
        )

    @app.post(f"/api/{CAL_API_VERSION}/metrics")
    def get_metrics():
        """
        Temporary Implementation to transition fixed event structure
        from websockets to long-polling

        TODO: Implement Cognos event schema, support custom query requests
        """
        return helper.create_response_from_payload(
            cognos.get_metrics()
        )

    return app


def get_ssl_context():
    ssl_cert = CONFIGS["ssl_cert"]
    ssl_key = CONFIGS["ssl_key"]
    context = (ssl_cert, ssl_key)
    return context


def validate_ssl_enabled():
    ssl_flag = CONFIGS["ssl"]
    ssl_cert = CONFIGS["ssl_cert"]
    ssl_key = CONFIGS["ssl_key"]
    return ssl_flag and os.path.exists(ssl_cert) and os.path.exists(ssl_key)


@click.command()
@click.option("--mock", "-m", is_flag=True, help="mock mode")
@click.option("--host", "-h", required=True, help="IP of host of CAL")
@click.option("--port", "-p", required=True, help="Port to run CAL on")
def main(mock, host, port):
    app = create_app(mock)

    if validate_ssl_enabled():
        app.run(host=host, port=port, ssl_context=get_ssl_context())
    else:
        app.run(host=host, port=port)


if __name__ == "__main__":
    main()
