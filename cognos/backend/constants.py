import os

import cognos.backend.helper as helper


CONFIGS = helper.fetch_cognos_configs(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)
COGNOS_ENDPOINT = CONFIGS["cognos_endpoint"]

COGNOS_NORTHBOUND_ENDPOINTS = {
    "list_clusters": COGNOS_ENDPOINT + "clusters",
    "list_nodes": COGNOS_ENDPOINT + "nodes",
    "list_cluster_nodes": COGNOS_ENDPOINT + "clusters/"
}
