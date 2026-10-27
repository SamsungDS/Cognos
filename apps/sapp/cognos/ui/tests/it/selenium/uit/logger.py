#!/usr/bin/env python
import logging
import os
import json


def setup_logger():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_file_path = os.path.join(script_dir, '..', 'config', 'config.json')
    with open(config_file_path) as config_file:
        config = json.load(config_file)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    log_dir = config['log_dir']
    log_file_name = config['log_file_name']
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, log_file_name)
    test_handler = logging.FileHandler(log_file, mode="w")
    test_handler.setLevel(logging.INFO)
    test_handler.setFormatter(formatter)
    logger.addHandler(test_handler)
    return logger
