###########################
# CMMB supported commands #
###########################
 
1. `SetupInfo`

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"SetupInfo", "command_params":"{}" }'


{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"Board\": {\"board_name\": \"Example Direct Config\", \"Mgmt_port_type\": \"PCIe\", \"json_version\": \"0100\", \"switch_mode\": \"direct\", \"management_port\": 1}, \"Hosts\": [{\"host_name\": \"Host 1 LNK0\", \"host_port\": 2, \"deinit_active\": 1, \"host_port_type\": \"CXL_11\", \"classcode\": 0, \"host_aspm_active\": 1, \"host_sris_active\": 1, \"host_equalization\": 1, \"host_speed\": 5, \"host_width\": 8, \"host_addr\": \"0x008080000000\", \"host_size\": \"0x007f80000000\", \"endpoint\": [{\"memdev\": \"mem- 10\", \"target\": 10, \"mem_addr\": \"0x008080000000\", \"mem_size\": \"0x003f80000000\", \"dev_offset\": \"0\"}, {\"memdev\": \"mem- 11\", \"target\": 11, \"mem_addr\": \"0x00C000000000\", \"mem_size\": \"0x004000000000\", \"dev_offset\": \"0\"}]}], \"Devices\": [{\"dev_name\": \"DEV_10-256G\", \"dev_port\": 10, \"dev_addr\": \"0x008000000000\", \"dev_size\": \"0x004000000000\", \"dev_aspm_active\": 1, \"dev_sris_active\": 1, \"dev_lock_active\": 1, \"dev_speed\": 5, \"dev_width\": 8, \"dev_port_type\": \"CXL_20\"}, {\"dev_name\": \"DEV_11-256G\", \"dev_port\": 11, \"dev_addr\": \"0x00C000000000\", \"dev_size\": \"0x004000000000\", \"dev_aspm_active\": 1, \"dev_sris_active\": 1, \"dev_lock_active\": 1, \"dev_speed\": 5, \"dev_width\": 8, \"dev_port_type\": \"CXL_20\"}]}"]}


2. `ListDevices` 

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"ListDevices", "command_params":"{\"command\":\"ListDevices\",\"cluster_id\":\"CL_ID_1\", \"FM_id\":\"203\",\"FM_endpoint\":\"samsung.com\"}" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"devices\": [{\"dev_id\": 549755813888, \"dev_capacity\": 274877906944, \"dev_port\": 10, \"hosts_attached\": [\"Host 1 LNK0\"]}, {\"dev_id\": 824633720832, \"dev_capacity\": 274877906944, \"dev_port\": 11, \"hosts_attached\": [\"Host 1 LNK0\"]}]}"]}


3. `ListHosts`

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"ListHosts", "command_params":"{}" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"hosts\": [{\"id\": 551903297536, \"name\": \"Host 1 LNK0\", \"mem_capacity\": 547608330240, \"host_target_ports\": [10, 11]}]}"]}


4. `DetachMemory`

-- detach device 10 
curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"DetachMemory", "command_params":"{\"command\":\"DetachMemory\",\"cluster_id\":\"CL_ID_1\", \"dev_id\":\"549755813888\",\"host_id\":\"551903297536\", \"mode\":\"direct\"}" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"rc\": 0}"]}


--detach device 11

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"DetachMemory", "command_params":"{\"command\":\"DetachMemory\",\"cluster_id\":\"CL_ID_1\", \"dev_id\":\"824633720832\",\"host_id\":\"551903297536\", \"mode\":\"direct\"}" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"rc\": 0}"]}


5. `AttachMemory`

-- attach device 10

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"AttachMemory", "command_params":"{\"command\":\"AttachMemory\",\"cluster_id\":\"CL_ID_1\", \"dev_id\":\"549755813888\",\"host_id\":\"551903297536\", \"mode\":\"direct\"}" }'
{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"rc\": 0}"]}


--attach device 11

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"AttachMemory", "command_params":"{\"command\":\"AttachMemory\",\"cluster_id\":\"CL_ID_1\", \"dev_id\":\"824633720832\",\"host_id\":\"551903297536\", \"mode\":\"direct\"}" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"rc\": 0}"]}


################################
# CMMD/CMMH supported commands #
################################

1. `list_devices` - to list all the devices in a node 

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"list_devices", "command_params":"{\"device_id\": [] }" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"devices\":[{\"device_id\":33638416328448,\"vendor_device_type\":\"CMM-H\",\"pcie_addr\":\"0000:27:00.0\"},{\"device_id\":33638416360448,\"vendor_device_type\":\"CMM-H\",\"pcie_addr\":\"0000:a4:00.0\"}]}"]}


2. `list_devices` - to list a specific device in a node 

curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"list_devices", "command_params":"{\"device_id\": [\"33638416328448\"] }" }'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"devices\":[{\"device_id\":33638416328448,\"vendor_device_type\":\"CMM-H\",\"pcie_addr\":\"0000:27:00.0\"}]}"]}

3. `get_device_info` - to get a specific detailed device information in a node 

 curl -X 'POST' 'http://105.128.44.80:8001/api/v1/nodes/node_1/features/cxl' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_name": "CL_ID_1", "command_name":"get_device_info", "command_params":"{ \"domain_id\": \"\", \"device_id\": \"33638416360448\" }"}'

{"errorIdOrStringIfAny":"", "errorCode":0, "apiVersion":"0.1", "response":["{\"api_version\":1.0,\"device_id\":33638416360448,\"manufacturer\":\"Samsung\",\"serial_number\":305419896,\"FW_revision\":\"1.0.0\",\"location\":\"0000:a4:00.0\",\"total_capacity_MB\":516079,\"feature_supported\":\"basic\",\"vendor_device_type\":\"CMM-H\",\"cxl_device_type\":\"Type3\",\"protocol\":\"CXL 2.0\",\"port_type\":\"root\",\"mode_discovered\":\"auto\",\"connection_type\":\"CXL.mem\",\"domain_type\":\"PCIe\",\"domain_id\":0,\"link_speed\":16,\"link_width\":8,\"available_capacity_MB\":467515,\"status\":\"active\",\"aspm_active\":false,\"sris_active\":false,\"lock_active\":false,\"numa_attached\":1,\"capabilities\":{\"Power Management version\":1},\"advertised_qos\":{\"avg_latency\":120.0,\"p99_latency\":350.0,\"io_per_sec\":50000.0,\"BW_per_sec\":1000000.0,\"io_size\":4096.0,\"qd\":32.0}}"]} 

