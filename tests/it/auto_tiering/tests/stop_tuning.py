#!/usr/bin/env python
import os
import subprocess
import time
import unittest
from tests.process_controller import ProcessController
from tests.logger import setup_logger

logger = setup_logger()


class StopTuning(unittest.TestCase):

    """Handles stopping a tuning process and notifying via API."""
    def setUp(self):
        """Load configuration and initialize ProcessController."""
        self.config = ProcessController.load_config()
        self.controller = ProcessController(self.config["api_url"])

    def get_pid(self):
        """
        Read the PID of the stress process from file.
        Returns:
            str or None: The PID if file exists, else None.
        """
        if not os.path.exists("stress.pid"):
            logger.error("PID file not found.")
            return None
        with open("stress.pid", "r") as pid_file:
            pid = pid_file.read().strip()
        logger.info(f"Retrieved PID: {pid}")
        return pid

    def test_stop_process(self):
        try:
            stop_process_command = self.config.get("stop_process_command")
            logger.info(
                f"Executing stop process command: {stop_process_command}")
            subprocess.run(stop_process_command, shell=True, check=True)
            logger.info(f"Killed process")
            os.remove("stress.pid")
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Stop process command failed: {e}")
        except Exception as e:
            logger.error(f"Error executing stop process command: {e}")

    def build_payload(self, pid):
        """
        Construct the API request payload for StopTuning.
        Args:
            pid (str): Process ID of the running stress process.
        Returns:
            dict: JSON payload for the API request.
        """
        params = (
            f"cluster_id={self.config['cluster_id']};"
            f"command=StopTuning;"
            f"application={self.config['application']};"
            f"application_id={pid}"
        )
        return {
            "cluster_id": self.config["cluster_id"],
            "node_id": self.config["node_id"],
            "feature_id": self.config["feature_id"],
            "feature_params": params
        }

    def test_stop_tuning(self):
        """
        Retrieve PID and trigger StopTuning API call.
        """
        pid = self.get_pid()
        if not pid:
            return
        payload = self.build_payload(pid)
        response = self.controller.send_request(payload)
        if response and response.ok:
            logger.info("StopTuning API request successful.")
        else:
            logger.error("StopTuning API request failed.")
        self.assertTrue(response and response.ok)


if __name__ == "__main__":
    unittest.main()
