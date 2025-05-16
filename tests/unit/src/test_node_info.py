import json
import os
import pytest
import sys

cwd = os.getcwd()
# Assuming we are running from tests dir for now
script_path = cwd + "/../../../src/node_info/"
sys.path.append(script_path)

from find_node_info import get_system_info, get_network_adapters_info, get_cpu_info, get_memory_info, get_all_info

@pytest.mark.parametrize("func", [
    get_system_info,
    get_network_adapters_info,
    get_cpu_info,
    get_memory_info,
    get_system_info,
])
def test_functions_return_dict(func):
    result = func()
    assert isinstance(result, dict)

def test_json_serialization():
    system_info = get_all_info()
    print(system_info)
    try:
        json.dumps(system_info)
        
    except TypeError as e:
        pytest.fail(f"Failed to serialize system info to JSON: {e}")