#!/usr/bin/env python
import subprocess
import unittest
from tests.process_controller import ProcessController
from tests.logger import setup_logger

# Initialize logger
logger = setup_logger()


class StartTuning(unittest.TestCase):

    pid = None

    """Handles starting a tuning process and notifying via API."""
    def setUp(self):
        """Loads configuration and initializes the ProcessController."""
        self.config = ProcessController.load_config()
        self.controller = ProcessController(self.config["api_url"])

    def test_start_process(self):
        """
        Starts the stress process as defined in the config.
        Returns:
            int: Process ID (PID) of the started process.
        """
        logger.info("Starting stress process...")
        stress_command = self.config["stress_command"].split()
        process = subprocess.Popen(stress_command)
        StartTuning.pid = process.pid
        # Save PID to file
        with open("stress.pid", "w") as pid_file:
            pid_file.write(str(StartTuning.pid))
        logger.info(f"Started process with PID: {StartTuning.pid}")
        self.assertIsNotNone(StartTuning.pid, "PID should not None")

    def build_payload(self, pid):
        """
        Constructs the API request payload using the PID.
        Args:
            pid (int): Process ID of the running stress process.
        Returns:
            dict: JSON payload for the API request.
        """
        params = (
            f"cluster_id={self.config['cluster_id']};"
            f"command=StartTuning;"
            f"application={self.config['application']};"
            f"application_id={pid};"
            f"dram_node={self.config['dram_node']};"
            f"cxl_node={self.config['cxl_node']};"
            f"sla_iops={self.config['sla_iops']};"
            f"sla_size={self.config['sla_size']};"
            f"sla_latencyus={self.config['sla_latencyus']}"
        )
        return {
            "cluster_id": self.config["cluster_id"],
            "node_id": self.config["node_id"],
            "feature_id": self.config["feature_id"],
            "feature_params": params
        }

    def test_start_tuning(self):
        """
        Starts the stress process and triggers the API to start tuning.
        """
        payload = self.build_payload(StartTuning.pid)
        response = self.controller.send_request(payload)
        if response and response.ok:
            logger.info("StartTuning API request successful.")
        else:
            logger.error("StartTuning API request failed.")
        self.assertTrue(response and response.ok, "API request failed")


if __name__ == "__main__":
    unittest.main()
