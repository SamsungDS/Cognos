#!/usr/bin/env python
import json
import os
import requests
from tests.logger import setup_logger

logger = setup_logger()


class ProcessController:

    """Handles the interaction with the API for process control."""
    def __init__(self, api_url):

        self.api_url = api_url

    @staticmethod
    def load_config():
        """Loads configuration from the config file."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, '..', 'config', 'config.json')
        with open(config_path) as config_file:
            config = json.load(config_file)
        return config

    def send_request(self, payload):
        """
        Sends a POST request to the API URL with the provided payload.
        Args:
            payload (dict): Data to be sent in the POST request.
        Returns:
            Response object or None if an exception occurs.
        """
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }
        logger.info(f"Sending POST to {self.api_url}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
        try:
            response = requests.post(self.api_url, headers=headers,
                                     data=json.dumps(payload))
            logger.info(f"Response: {response.status_code} - {response.text}")
            return response
        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            return None
