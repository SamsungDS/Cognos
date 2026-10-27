#!/usr/bin/env python
import json
import os
from locust import HttpUser, task, between, events
from utils import send_request


def load_config():
    """Load configuration from the config.json file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file_path = os.path.join(script_dir, "config.json")
    with open(config_file_path, encoding="utf-8") as config_file:
        return json.load(config_file)


# Load configuration
CONFIG = load_config()
DEVICES = CONFIG["devices"]
HOST = CONFIG["host"]


class StressTestUser(HttpUser):

    """
    Locust user class for performing stress tests.
    This class attaches and detaches devices in a loop.
    """
    wait_time = between(0.2, 0.5)
    total_requests = 0
    total_devices = len(DEVICES)

    @task
    def attach_and_detach(self):
        """Attach a device to the host and then immediately detach it."""
        if self.total_requests >= 240:
            self.environment.runner.quit()
            return
        device_index = (self.total_requests // 2) % self.total_devices
        device = DEVICES[device_index]
        # Attach device
        attach_payload = {
            "host_name": HOST,
            "dev_name": device,
        }
        send_request(
            self.client,
            CONFIG["endpoints"]["attach_device"],
            attach_payload,
            method="POST",
        )
        self.total_requests += 1
        # Detach device
        detach_payload = {
            "host_name": HOST,
            "dev_name": device,
        }
        send_request(
            self.client,
            CONFIG["endpoints"]["detach_device"],
            detach_payload,
            method="DELETE",
        )
        self.total_requests += 1
        print(
            f"Attach/Detach Complete: {device} - Total Requests: "
            f"{self.total_requests}"
        )


@events.quitting.add_listener
def stop_on_completion(environment, **kwargs):
    """Log final test results when the test run completes."""
    stats = environment.stats.total
    print(f"Test completed: {stats.num_requests} requests made.")
    print(f"Avg response time: {stats.avg_response_time:.2f} ms")
