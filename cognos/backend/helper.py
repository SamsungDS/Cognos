import json
import os


def fetch_cognos_configs(parent_dir, file_name):
    config_file_path = os.path.join(parent_dir, 'config', file_name)
    configs = ''
    try:
        with open(config_file_path, 'r') as config_file:
            configs = json.load(config_file)
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve cognos influx configs: {str(error)}"
        )
    return configs


def fetch_api_version(parent_dir):
    try:
        with open(os.path.join(parent_dir, 'VERSION'), 'r') as v:
            API_VERSION = v.read().strip()
            return API_VERSION
    except Exception as error:
        raise RuntimeError(
            f"Unable to retrieve API version: {str(error)}"
        )
