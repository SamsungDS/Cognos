import json
import cognos.telegraf.poll as poll
from requests.models import Response


def test_esc():
    dummy_string = 'string with "" quotes'
    poll.esc(dummy_string)


def test_esc_str():
    dummy_string = 'string with "" quotes'
    poll.esc_str(dummy_string)


def test_get_nodes(mocker):
    dummy_list_nodes_response = {
        "commandResponse": json.dumps({
            "node_info": [
                {
                    "node_name": "cognos_node1",
                    "node_port": "9998",
                    "node_ip": "x.x.x.x",
                    "status": "online/offline",
                }
            ]
        })
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_list_nodes_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_nodes()


def test_get_clusters(mocker):
    dummy_list_clusters_response = {
        "commandResponse": json.dumps({
            "clusters": [
                {"cluster_name": "cluster_name_0"},
                {"cluster_name": "cluster_name_1"},
                {"cluster_name": "cluster_name_2"}
            ]
        })
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_list_clusters_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_clusters()


def test_get_cluster_nodes(mocker):
    dummy_list_cluster_nodes_response = {
        "commandResponse": json.dumps({
            "clusters": [{
                "cluster_name": "name",
                "nodes": [
                    {
                        "node_name": "node1",
                        "status": "online/offline"
                    },
                    {
                        "node_name": "node2",
                        "status": "online/offline"
                    }
                ]
            }]
        })
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_list_cluster_nodes_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_cluster_nodes("CL_ID_1")


def test_get_device_ids(mocker):
    dummy_list_devices_response = {
        "response": [
            json.dumps({
                "devices": [{
                    "device_id": 33638416341504,
                    "vendor_device_type": "CMM-H",
                    "pcie_addr": "0000:5a:00.0"
                }]
            })
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_list_devices_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_device_ids("CL_ID_1", "node_1")


def test_get_cxl_device_metrics(mocker):
    dummy_get_metrics_response = {
        "response": [
            json.dumps({
                "domain": "observability",
                "feature_id": 3,
                "category": "metric",
                "severity": "info",
                "source": 33235991715328,
                "source_type": "device",
                "power_state": "L0",
                "timestamp": 1754385158,
                "observability": {
                    "numa_node": 0,
                    "total_memory_MB": 8192,
                    "used_memory_MB": 4096,
                    "available_memory_MB": 4096,
                    "total_bandwidth_MBps": 20000,
                    "used_bandwidth_Bps": 1104548,
                    "cache_hit_perc": 98,
                    "dirty_cache_gb": 3,
                    "fpga_temp_in_F": 42
                }
            })
        ]
    }
    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_get_metrics_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_cxl_device_metrics("CL_ID_1", "node_1", 23123132)


def test_get_cognos_events(mocker):
    dummy_detach_response = {
        "errorIdOrStringIfAny": "", "errorCode": 0, "apiVersion": "0.1",
        "response": (
            "[{\"event_header\":{\"cluster_name\":\"CL_ID_1\","
            "\"node_name\":\"node_1\"},\"event_payload\":"
            "{\"category\":\"thermal\",\"domain\":\"cxl_device\","
            "\"feature_name\":\"cxl\",\""
            "observations\":{\"fpga_temp_in_F\":530,"
            "\"fpga_threshold_in_F\":100},\"severity\":\"critical\","
            "\"source\":33235991846400,\"source_type\":\"device\","
            "\"timestamp\":7335626863}}]"
        )
    }

    dummy_response = Response()
    dummy_response.status_code = 200
    dummy_response._content = (
        json.dumps(dummy_detach_response).encode("utf-8")
    )
    mocker.patch(
        'requests.post',
        return_value=dummy_response
    )
    poll.get_cognos_events()


def test_get_cognos_device_stats(mocker):
    dummy_clusters = ['CL_ID_1']
    dummy_cluster_ndoes = ['node1', 'node2']
    dummy_device_ids = [
        3442423432324,
        646353543534
    ]
    dummy_cxl_device_metrics = {
        "domain": "observability",
        "feature_id": 3,
        "category": "metric",
        "severity": "info",
        "source": 33235991715328,
        "source_type": "device",
        "power_state": "L0",
        "timestamp": 1754385158,
        "observability": {
            "numa_node": 0,
            "total_memory_MB": 8192,
            "used_memory_MB": 4096,
            "available_memory_MB": 4096,
            "total_bandwidth_MBps": 20000,
            "used_bandwidth_Bps": 1104548,
            "cache_hit_perc": 98,
            "dirty_cache_gb": 3,
            "fpga_temp_in_F": 42
        }
    }
    mocker.patch(
        'cognos.telegraf.poll.get_clusters',
        return_value=dummy_clusters
    )
    mocker.patch(
        'cognos.telegraf.poll.get_cluster_nodes',
        return_value=dummy_cluster_ndoes
    )
    mocker.patch(
        'cognos.telegraf.poll.get_device_ids',
        return_value=dummy_device_ids
    )
    mocker.patch(
        'cognos.telegraf.poll.get_cxl_device_metrics',
        return_value=dummy_cxl_device_metrics
    )
    poll.get_cognos_device_stats()


def test_convert_stats_to_influx_line_protocol():
    dummy_stats = [{
        "domain": "observability",
        "feature_id": 3,
        "category": "metric",
        "severity": "info",
        "source": 33235991715328,
        "source_type": "device",
        "power_state": "L0",
        "timestamp": 1754385158,
        "observability": {
            "numa_node": 0,
            "total_memory_MB": 8192,
            "used_memory_MB": 4096,
            "available_memory_MB": 4096,
            "total_bandwidth_MBps": 20000,
            "used_bandwidth_Bps": 1104548,
            "cache_hit_perc": 98,
            "dirty_cache_gb": 3,
            "fpga_temp_in_F": 42
        }
    }]
    poll.convert_stats_to_influx_line_protocol(dummy_stats)
