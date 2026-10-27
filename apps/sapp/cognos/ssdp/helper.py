import json
import os
import sys
import uuid
import random

# Add the backend directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))

SKU_FILE_PATH = os.path.join(current_dir, 'sku.txt')


def load_config():
    config_path = os.path.join(current_dir, 'config', 'config.json')
    with open(config_path, 'r') as config_file:
        return json.load(config_file)


def get_or_generate_sku():
    if os.path.exists(SKU_FILE_PATH):
        with open(SKU_FILE_PATH, 'r') as sku_file:
            return sku_file.read().strip()
    else:
        sku = ''.join(
            random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=7)
        )
        with open(SKU_FILE_PATH, 'w') as sku_file:
            sku_file.write(sku)
        return sku


def generate_ssdp_response():
    config = load_config()

    # Generate response
    response = {
        'device_type': config['device_type'],
        'manufacturer': config['manufacturer'],
        'mgmt_ip': config['mgmt_endpoint'].split('//')[1].split(':')[0],
        'mgmt_port': config['mgmt_endpoint'].split(':')[-1],
        'capacity': config['capacity'],
        'cxl_version': config['cxl_version'],
        'pcie_version': config['pcie_version'],
        'upstream_ports': config['upstream_ports'],
        'downstream_ports': config['downstream_ports'],
        'sku': get_or_generate_sku()
    }

    return json.dumps(response)


def get_ssdp_response():
    UUID = str(uuid.uuid4())
    extra_fields = generate_ssdp_response()

    ssdp_response = (
        'HTTP/1.1 200 OK\r\n'
        'ST: Samsung:Cognos\r\n'
        f'USN: uuid:{UUID}\r\n'
        'AL: <cognos:mgmt><https://samsungcognos.com>\r\n'
        f'EXTRA_FIELDS: {extra_fields}\r\n'
    )

    return ssdp_response
