from flask import Flask, request, jsonify,  make_response,  send_file
import click
import logging
from pathlib import Path
import os
import sys
import time
import json
from flask_cors import CORS
from gunicorn.app.base import BaseApplication
import multiprocessing

sys.path.append(
    os.path.abspath(  # noqa: E402
        os.path.join(os.path.dirname(__file__), "../..")
    )
)  # noqa: E402

import cognos.backend.helper as helper
from cognos.backend.cognos_client import Cognos
from cognos.backend.logger import create_logger
from cognos.backend.sqlite_client import SqliteClient


current_script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIGS = helper.fetch_cognos_configs(current_script_dir, "config.json")
CAL_API_VERSION = helper.fetch_cal_api_version(current_script_dir)

global AGENT_ENDPOINT
AGENT_ENDPOINT = CONFIGS["agent_endpoint"]
# TODO: support multiple Node Servers / Agents at scale
global NODE_ENDPOINT
NODE_ENDPOINT = CONFIGS["node_endpoint"]
global DOWNLOAD_ARTIFACT_MODE
DOWNLOAD_ARTIFACT_MODE = CONFIGS["download_artifact_mode"]

CAL_LOGGER = create_logger("svkapp-cal-logger", log_dir="/var/log/svk",
                           level=logging.DEBUG)
artifact_config_path = os.path.join(current_script_dir, "artifacts", "artifact_info.json")

if os.path.isfile(artifact_config_path):
    with open(artifact_config_path, "r") as f:
        artifact_config = json.load(f)
    ARTIFACTS = artifact_config.get("ARTIFACTS", [])
else:
    ARTIFACTS = []

ARTIFACTS_DIR = os.path.join(current_script_dir, "artifacts")


def create_app(mock=False):
    """Implements endpoints of Flask App"""
    app = Flask(__name__)
    CORS(app)
    app.config["CORS_HEADERS"] = "Content-Type"
    cognos = Cognos(CAL_LOGGER, mock=mock)

    @app.get(f"/api/{CAL_API_VERSION}/scmc_version")
    def get_version():
        """
        Returns SCMC Version
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
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
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.fetch_topology()
        )

    @app.get(f"/api/{CAL_API_VERSION}/hosts")
    def get_hosts():
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.get_remote_hosts()
        )

    @app.get(f"/api/{CAL_API_VERSION}/nodes")
    def get_nodes():
        """
        Returns all node_names of Cognos System
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.get_nodes()
        )

    @app.post(f"/api/{CAL_API_VERSION}/devices")
    def remote_devices():
        """
        Gets device information for all remote
        attached devices
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.get_remote_devices()
        )

    @app.post(f"/api/{CAL_API_VERSION}/membox_capacity")
    def membox_capacity():
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
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
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.host_devices()
        )

    @app.get(f"/api/{CAL_API_VERSION}/available_devices")
    def available_devices():
        """
        Returns list of device names
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.available_remote_devices()
        )

    @app.delete(f"/api/{CAL_API_VERSION}/detach_device")
    def detach_device():
        """
        Performs Detach Operation

        Returns list of json objects containing attached device information
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.detach_remote_device()
        )

    @app.post(f"/api/{CAL_API_VERSION}/attach_device")
    def attach_device():
        """
        Performs Attach Operation

        Returns list of json objects containing attached device information
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.attach_remote_device()
        )

    @app.get(f"/api/{CAL_API_VERSION}/all_hosts")
    def get_all_hosts():
        """
        Returns list of hosts in format {"value": host, "label": host}
        """
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
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
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.get_metrics()
        )

    @app.get(f"/api/{CAL_API_VERSION}/events")
    def get_events():
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.get_events()
        )

    @app.post(f"/api/{CAL_API_VERSION}/device_stats")
    def get_device_stats():
        CAL_LOGGER.debug(
            helper.serialize_request_metadata(
                helper.get_request_metadata(request)
            )
        )
        return helper.create_response_from_payload(
            cognos.get_device_stats()
        )

    @app.get(f"/api/{CAL_API_VERSION}/application_status")
    def get_application_status():
        """
        # TODO: replace data_moved with msg
        Application | PID | Server Node | Target Throughput (OP/s) |
        Target Read P99 Latency (us) | Target Write P99 Latency (us) |
        Status | Msg

        Returns:
        [
            {
                "app_name": "<app name>",
                "app_pid": <app_pid>,
                "server_name": "<server_name>",
                "throughput_ops_per_sec": "<throughput_ops_per_sec>",
                "targetread_p99_latency": "<targetread_p99_latency>",
                "targetwrite_p99_latency": "<targetwrite_p99_latency>",
                "status": "<status>",
                "message": "",
                "data_moved": "<data_moved>"
            },
            {
            },
            ....
        ]
        """
        # get applications
        data = cognos.get_applications()
        return helper.create_response_from_payload(data if data else {})

    @app.post(f"/api/{CAL_API_VERSION}/set_app_sla")
    def set_app_sla():
        """
        {"app_pid":64452,"app_name":"testapp","server_name":"localhost","avg_latency_ns":9339832429,"throughput_ops_per_sec":5000,"targetread_p99_latency":4999,"targetwrite_p99_latency":2999}
        Args: {
            "app_name": <app_name>,
            "app_pid": <app_pid>,
            "server_name": <server_name>,
            "avg_latency_ns": <avg_latency_ns>,
            "throughput_ops_per_sec": <throughput_ops_per_sec>,
            "targetread_p99_latency": <targetread_p99_latency>,
            "targetwrite_p99_latency": <targetwrite_p99_latency>
        }
        Returns: 200 status code
        """
        try:
            cognos.set_app_sla()
            return helper.create_response_from_payload({})
        except Exception as error:
            return helper.failed_response(str(error))

    @app.get(f"/api/{CAL_API_VERSION}/list_artifact")
    def list_artifact():
        if not DOWNLOAD_ARTIFACT_MODE:
            return jsonify({"error": "Artifact download is not enabled"}), 503

        enriched = []
        for artifact in ARTIFACTS:
            file_path = os.path.join(ARTIFACTS_DIR, artifact["name"])
            details = artifact.get("ARTIFACT_DETAILS", {})
            enriched.append({
                "id": artifact.get("id"),
                "name": artifact.get("name"),
                "available": os.path.isfile(file_path),
                "release_name": details.get("release_name"),
                "release_date": details.get("release_date"),
                "feature_list": details.get("feature_list", []),
                "release_notes": details.get("release_notes")
            })
        return jsonify({"artifacts": enriched}), 200

    @app.get(f"/api/{CAL_API_VERSION}/artifact/<int:artifact_id>/download_artifact")
    def download_artifact(artifact_id: int):
        if not DOWNLOAD_ARTIFACT_MODE:
            return jsonify({"error": "Artifact download is not enabled."}), 403

        artifact = next((a for a in ARTIFACTS if a["id"] == artifact_id), None)

        if artifact is None:
            return jsonify({"error": f"Artifact id={artifact_id} not found."}), 404

        file_path = os.path.join(ARTIFACTS_DIR, artifact["name"])

        if not os.path.isfile(file_path):
            return jsonify({
                "error": (
                    f"File '{artifact['name']}' is registered but missing on system. "
                    f"Please place it in: {ARTIFACTS_DIR}"
                )
            }), 404

        return send_file(
            file_path,
            mimetype="application/x-tar",
            as_attachment=True,
            download_name=artifact["name"],
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


def init_sqlite_db_file(svk_data_path="/var/lib/svk"):
    # create Cognos.db file, only to be created by cognos-app service
    db_file = svk_data_path + os.sep + 'cognos.db'
    db_file_path = Path(db_file)

    # create data directory
    if not os.path.exists(svk_data_path):
        os.makedirs(svk_data_path)

    # create DB file
    if not os.path.exists(db_file):
        db_file_path.touch(exist_ok=True)


def clear_cognos_db(mock=False):
    sql_client = SqliteClient(mock=mock, logger=CAL_LOGGER)
    with sql_client.get_sqlite_connection() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.executescript(
                "DROP TABLE IF EXISTS devices;"
                "DROP TABLE IF EXISTS hosts;"
                "DROP TABLE IF EXISTS connections;"
                "DROP TABLE IF EXISTS applications;"
            )
            conn.commit()
            time.sleep(0.5)
        except Exception as error:
            CAL_LOGGER.critical("Unable to clear Cognos DB tables..")
            conn.rollback()
            raise


def init_cognos_db(mock=False):
    sql_client = SqliteClient(mock=mock, logger=CAL_LOGGER)

    with sql_client.get_sqlite_connection() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn.executescript(
                "CREATE TABLE IF NOT EXISTS devices ("
                "id BIGINT UNSIGNED NOT NULL, "
                "mem_capacity BIGINT UNSIGNED, "
                "port INT UNSIGNED, "
                "type VARCHAR(32), "
                "mode VARCHAR(15), "
                "name VARCHAR(32), "
                "PRIMARY KEY (id)"
                ");"
                "CREATE TABLE IF NOT EXISTS connections ("
                "cluster_name VARCHAR(64), "
                "node_name VARCHAR(255), "
                "device_id BIGINT UNSIGNED"
                ");"
                "CREATE TABLE IF NOT EXISTS hosts ("
                "node_name VARCHAR(255) NOT NULL, "
                "fm_type VARCHAR(32), "
                "mem_capacity BIGINT UNSIGNED, "
                "target_ports VARCHAR(64), "
                "ip_addr VARCHAR(32), "
                "hostname VARCHAR(255), "
                "remote_id BIGINT UNSIGNED, "
                "PRIMARY KEY (node_name)"
                ");"
                "CREATE TABLE IF NOT EXISTS applications ("
                "app_name VARCHAR(255) NOT NULL, "
                "app_pid BIGINT UNSIGNED NOT NULL, "
                "server_name VARCHAR(64) NOT NULL, "
                "throughput_ops_per_sec BIGINT UNSIGNED, "
                "targetread_p99_latency BIGINT UNSIGNED, "
                "targetwrite_p99_latency BIGINT UNSIGNED, "
                "status VARCHAR(32), "
                "message VARCHAR(255), "
                "data_moved VARCHAR(128), "
                "PRIMARY KEY (app_pid)"
                ");"
            )
            conn.commit()
            time.sleep(0.5)
            CAL_LOGGER.info("Successfully created Cognos DB schema..")
        except Exception:
            CAL_LOGGER.critical("Unable to create Cognos DB schema..")
            conn.rollback()
            raise
        finally:
            sql_client.table_description("devices")
            sql_client.table_description("hosts")
            sql_client.table_description("connections")


class StandaloneApplication(BaseApplication):
    """Custom Gunicorn application to run from Python code."""

    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        """Load Gunicorn config from self.options dict."""
        config = {key: value for key, value in self.options.items()
                  if key in self.cfg.settings and value is not None}
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        """Return WSGI application."""
        return self.application


@click.command()
@click.option("--mock", "-m", is_flag=True, help="mock mode")
@click.option("--host", "-h", required=True, help="IP of host of CAL")
@click.option("--port", "-p", required=True, help="Port to run CAL on")
def main(mock, host, port):
    init_sqlite_db_file()
    clear_cognos_db(mock=mock)
    init_cognos_db(mock=mock)
    app = create_app(mock)

    options = {
        "bind": f"{host}:{port}",  # Host:Port
        "workers": multiprocessing.cpu_count() // 2 + 1,  # 1 worker max per 2 CPU
        "worker_class": "sync",
        "timeout": 30
    }

    # Check if https mode
    if validate_ssl_enabled():
        options["certfile"] = CONFIGS["ssl_cert"]
        options["keyfile"] = CONFIGS["ssl_key"]

    StandaloneApplication(app, options).run()


if __name__ == "__main__":
    main()
