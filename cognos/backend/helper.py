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
