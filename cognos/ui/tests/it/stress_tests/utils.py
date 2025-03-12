#!/usr/bin/env python
import os
import json
import time
import random
from locust import HttpUser, task, between


def send_request(client, endpoint, payload=None, method="GET"):
    """
    Send an HTTP request and log details.
    """
    start_time = time.time()
    try:
        if method == "POST" and payload:
            response = client.post(endpoint, json=payload)
        elif method == "DELETE" and payload:
            response = client.delete(endpoint, json=payload)
        else:
            response = client.get(endpoint)
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        print(
            f"Request: {endpoint} | Method: {method} | "
            f"Status: {response.status_code} | "
            f"Time: {response_time_ms:.2f} ms | "
            f"Payload: {json.dumps(payload) if payload else None}"
        )
        # Validate response
        if response.status_code != 200:
            print(
                f"Error: {endpoint} | Status: {response.status_code} | "
                f"Response: {response.text}"
            )
        else:
            print(f"Response: {response.text[:200]}...")
        return response
    except Exception as exc:
        print(f"Exception in request: {endpoint} | Error: {exc}")
        return None
