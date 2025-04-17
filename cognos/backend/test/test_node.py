import pytest

from cognos.backend.node import Node


def test_node_init():
    dummy_node_name = "node_1"
    dummy_node_ip = "1.2.3.4"
    dummy_node_fmtype = 'FM_DIRECT_CMMD'
    dummy_node_type = "direct attached"
    node = Node(dummy_node_name, dummy_node_ip, dummy_node_fmtype,
                dummy_node_type)
