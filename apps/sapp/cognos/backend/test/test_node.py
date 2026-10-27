import pytest

from cognos.backend.node import Node

from cognos.backend.test.data_constants import DUMMY_NODE_INFO


def test_node_init(mock_sqlite_client):
    node_name = DUMMY_NODE_INFO["node_name"]
    fm_type = DUMMY_NODE_INFO["fm_type"]
    mem_capacity = DUMMY_NODE_INFO["mem_capacity"]
    target_ports = DUMMY_NODE_INFO["target_ports"]
    ip_addr = DUMMY_NODE_INFO["ip_addr"]
    hostname = DUMMY_NODE_INFO["hostname"]
    remote_id = DUMMY_NODE_INFO["remote_id"]

    node = Node(
        mock_sqlite_client, node_name, fm_type, mem_capacity, target_ports,
        ip_addr, hostname, remote_id
    )

    # test repr function
    print(node)

    assert node is not None


def test_insert_node_into_hosts_table(mock_sqlite_client):
    node_name = DUMMY_NODE_INFO["node_name"]
    fm_type = DUMMY_NODE_INFO["fm_type"]
    mem_capacity = DUMMY_NODE_INFO["mem_capacity"]
    target_ports = DUMMY_NODE_INFO["target_ports"]
    ip_addr = DUMMY_NODE_INFO["ip_addr"]
    hostname = DUMMY_NODE_INFO["hostname"]
    remote_id = DUMMY_NODE_INFO["remote_id"]

    node = Node(
        mock_sqlite_client, node_name, fm_type, mem_capacity, target_ports,
        ip_addr, hostname, remote_id
    )

    node.insert_node_into_hosts_table()
