from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

import time
import json
import os
import random

from helper import fetch_cognos_configs


class CognosInfluxDBClient():
    def __init__(self, url=None, token=None, org=None, bucket=None):
        if any(arg is None for arg in [url, token, org, bucket]):
            configs = fetch_cognos_configs('influxdb_config.json')
            self.bucket = configs['bucket']
            self.url = configs['url']
            self.token = configs['token']
            self.org = configs['org']
        else:
            self.url = url
            self.token = token
            self.org = org
            self.bucket = bucket

        self.client = InfluxDBClient(url=self.url, token=self.token,
                                     org=self.org)
        self.write_client = self.client.write_api(write_options=SYNCHRONOUS)
        self.read_client = self.client.query_api()

    def write_cognos_event(self, event):
        """
        Takes the following schema from Cognos Agent event collectors and
        writes to InfluxDB

        Event {
            type: metric/alert,
            source: <host/application server>,
            source_type: <source_type>,
            timestamp: <timestamp>,
            description: <description>,
            category: <category>,
            application: <app-name>,
            observations: {
                <metric_name>: <metric_value>,
                ...
            }
        }
        """
        records = [{
            "measurement": event['type'],
            "tags": {
                "source": event['source'],
                "source_type": event['source_type'],
                "description": event['description'],
                "category": event['category'],
                "application": event['application']
            },
            "fields": event['observations'],
            "timestamp": event['timestamp']
        }]
        self.write_client.write(self.bucket, self.org, records)

    def query_cognos_events(self, time_window):
        return self.read_client.query(
            f'from(bucket:"internal") |> range(start: -{time_window})'
        )
