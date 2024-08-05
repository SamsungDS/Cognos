import time
import random
from cognos_influxdb_client import CognosInfluxDBClient


mock_metrics = [
    {
        "type": "metric",
        "source": "host1.samsung.com",
        "source_type": "host",
        "timestamp": time.time(),
        "description": "host cpu usage",
        "category": "cpu",
        "application": "test",
        "observations": {
            "cpu_usage": random.uniform(0, 100),
        }
    },
    {
        "type": "metric",
        "source": "host1.samsung.com",
        "source_type": "host",
        "timestamp": time.time(),
        "description": "host mem usage",
        "category": "mem",
        "application": "test",
        "observations": {
            "mem_usage": random.uniform(0, 10000),
        }
    },
    {
        "type": "metric",
        "source": "mb1.samsung.com",
        "source_type": "memory_box",
        "timestamp": time.time(),
        "description": "total capacity usage",
        "category": "mem",
        "application": "test",
        "observations": {
            "capacity": random.uniform(0, 1000000),
        }
    },
    {
        "type": "metric",
        "source": "mb1.samsung.com",
        "source_type": "cxl_device",
        "timestamp": time.time(),
        "description": "device usage",
        "category": "cxl",
        "application": "test",
        "observations": {
            "cxl_device_usage": random.uniform(0, 10000000),
        }
    }
]


def run_mock_populator(client, runtime, query_window):
    end_time = time.time() + runtime
    while time.time() < end_time:
        for metric in mock_metrics:
            client.write_cognos_event(metric)
        time.sleep(1)

    print(f"All influxdb cognos records in the past {query_window}..")
    client.query_cognos_events(query_window)


if __name__ == "__main__":
    MOCK_POPULATOR_RUNTIME = 10  # seconds
    TEST_TIME_WINDOW = '10m'
    client = CognosInfluxDBClient()
    run_mock_populator(client, MOCK_POPULATOR_RUNTIME, TEST_TIME_WINDOW)
