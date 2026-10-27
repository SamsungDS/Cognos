
MOCK_RECENT_DRAM_CXL_USAGE = [
    ['Mem Usage', 'DRAM', 'CXL'],
    ['02:03:18', 99, 70],
    ['02:03:25', 99, 70],
    ['02:03:32', 99, 70],
    ['02:03:39', 99, 70],
    ['02:03:46', 99, 70],
    ['02:03:53', 99, 70],
    ['02:04:00', 99, 70],
    ['02:04:08', 99, 70],
    ['02:04:15', 99, 70]
]

MOCK_GET_CPU_MEM_USAGE = [
    ['CPU vs Memory Usage', 'Mem (CXL+DRAM)', 'CPU'],
    ['02:03:18', 80.30884732664056, 5.0],
    ['02:03:25', 80.30882310433404, 5.0],
    ['02:03:32', 80.3088876971514, 5.0],
    ['02:03:39', 80.3088876971514, 5.0],
    ['02:03:46', 80.30899266047965, 5.0],
    ['02:03:53', 80.30904110509267, 5.0],
    ['02:04:00', 80.30910569791006, 5.0],
    ['02:04:08', 80.30900880868398, 5.0],
    ['02:04:15', 80.30911377201222, 5.0]
]

MOCK_HOSTVIEW_CAPACITY = {
    'hostview_capacity': {'total_capacity': 12384},
    'hostview_memserver_capacity': [
        ['Memtype', 'Capacity Used'],
        ['DRAM', 4127],
        ['CXL', 8257]
    ]
}

MOCK_MEMSERVER_CAPACITY = [
    ['Memtype', 'Capacity Used'],
    ['CXL', 8063],
    ['DRAM', 4031]
]

MOCK_HOSTVIEW_USAGE = [
    ['Time', 'DRAM', 'CXL'],
    ['01:59:15', 4113437, 5833011],
    ['01:59:20', 4113433, 5833011],
    ['01:59:25', 4113431, 5833011],
    ['01:59:35', 4113436, 5833011],
    ['01:59:40', 4113437, 5833011],
    ['01:59:50', 4113445, 5833011]
]

MOCK_MEMBOX_USAGE = [
    ['Membox Usage', 'Usage MB'],
    ['02:03:12', 11666022],
    ['02:03:18', 0],
    ['02:03:24', 11666022],
    ['02:03:30', 11666022],
    ['02:03:36', 11666022],
    ['02:03:42', 11666022],
    ['02:03:48', 11666022],
    ['02:03:54', 11666022],
    ['02:04:06', 11666022],
    ['02:04:09', 11666022]
]

MOCK_HOSTVIEW_BANDWIDTH = {}

MOCK_HOSTVIEW_DEVICES_COUNT = {'num_cxl_devices': 5, 'num_hosts': 2}

MOCK_NODE_BANDWIDTH = {
    "max_bandwidth": 128,
    "used_bandwidth": 32,
    "used_percentage_bandwidth": 25
}


def get_mock_device_stats(device_id, stat_key):
    if stat_key == "total_memory_MB":
        return {
            device_id: [
                ['00:45:54', 'total_memory_MB', 2064382],
                ['00:45:59', 'total_memory_MB', 2064382],
                ['00:46:00', 'total_memory_MB', 2064382],
                ['00:46:05', 'total_memory_MB', 2064382],
                ['00:46:10', 'total_memory_MB', 2064382],
                ['00:46:15', 'total_memory_MB', 2064382],
                ['00:46:16', 'total_memory_MB', 2064382],
                ['00:46:20', 'total_memory_MB', 2064382],
                ['00:46:25', 'total_memory_MB', 2064382],
                ['00:46:30', 'total_memory_MB', 2064382],
                ['00:46:31', 'total_memory_MB', 1024],
                ['00:46:36', 'total_memory_MB', 2064382],
                ['00:46:41', 'total_memory_MB', 2064382],
                ['00:46:46', 'total_memory_MB', 2064382]
            ]
        }
    elif stat_key == "used_memory_MB":
        return {
            device_id: [
                ['00:45:54', 'used_memory_MB', 2021538],
                ['00:45:59', 'used_memory_MB', 2021538],
                ['00:46:00', 'used_memory_MB', 2021538],
                ['00:46:05', 'used_memory_MB', 2021538],
                ['00:46:10', 'used_memory_MB', 2021538],
                ['00:46:15', 'used_memory_MB', 2021538],
                ['00:46:16', 'used_memory_MB', 2021538],
                ['00:46:20', 'used_memory_MB', 2021538],
                ['00:46:25', 'used_memory_MB', 2021538],
                ['00:46:30', 'used_memory_MB', 2021538],
                ['00:46:31', 'used_memory_MB', 1024],
                ['00:46:36', 'used_memory_MB', 2021538],
                ['00:46:41', 'used_memory_MB', 2021538],
                ['00:46:46', 'used_memory_MB', 2021538]
            ]
        }
    elif stat_key == "used_bandwidth_Bps":
        return {
            device_id: [
                ['00:45:49', 'used_bandwidth_Bps', 605589],
                ['00:45:54', 'used_bandwidth_Bps', 601456],
                ['00:45:59', 'used_bandwidth_Bps', 601456],
                ['00:46:00', 'used_bandwidth_Bps', 601456],
                ['00:46:05', 'used_bandwidth_Bps', 596525],
                ['00:46:10', 'used_bandwidth_Bps', 596525],
                ['00:46:15', 'used_bandwidth_Bps', 586774],
                ['00:46:16', 'used_bandwidth_Bps', 586774],
                ['00:46:20', 'used_bandwidth_Bps', 586774],
                ['00:46:25', 'used_bandwidth_Bps', 599516],
                ['00:46:30', 'used_bandwidth_Bps', 599516],
                ['00:46:31', 'used_bandwidth_Bps', 0],
                ['00:46:36', 'used_bandwidth_Bps', 602302],
                ['00:46:41', 'used_bandwidth_Bps', 602302]
            ]
        }
    elif stat_key == "total_bandwidth_MBps":
        return {
            device_id: [
                ['00:45:49', 'total_bandwidth_MBps', 32000],
                ['00:45:54', 'total_bandwidth_MBps', 32000],
                ['00:45:59', 'total_bandwidth_MBps', 32000],
                ['00:46:00', 'total_bandwidth_MBps', 32000],
                ['00:46:05', 'total_bandwidth_MBps', 32000],
                ['00:46:10', 'total_bandwidth_MBps', 32000],
                ['00:46:15', 'total_bandwidth_MBps', 32000],
                ['00:46:16', 'total_bandwidth_MBps', 32000],
                ['00:46:20', 'total_bandwidth_MBps', 32000],
                ['00:46:25', 'total_bandwidth_MBps', 32000],
                ['00:46:30', 'total_bandwidth_MBps', 32000],
                ['00:46:31', 'total_bandwidth_MBps', 32000],
                ['00:46:36', 'total_bandwidth_MBps', 32000],
                ['00:46:41', 'total_bandwidth_MBps', 32000]
            ]
        }
    elif stat_key == "fpga_temp_in_F":
        return {
            device_id: [
                ['00:45:49', 'fpga_temp_in_F', 43],
                ['00:45:54', 'fpga_temp_in_F', 43],
                ['00:45:59', 'fpga_temp_in_F', 43],
                ['00:46:00', 'fpga_temp_in_F', 43],
                ['00:46:05', 'fpga_temp_in_F', 42],
                ['00:46:10', 'fpga_temp_in_F', 43],
                ['00:46:15', 'fpga_temp_in_F', 43],
                ['00:46:16', 'fpga_temp_in_F', 43],
                ['00:46:20', 'fpga_temp_in_F', 43],
                ['00:46:25', 'fpga_temp_in_F', 42],
                ['00:46:30', 'fpga_temp_in_F', 42],
                ['00:46:31', 'fpga_temp_in_F', 50],
                ['00:46:36', 'fpga_temp_in_F', 43],
                ['00:46:41', 'fpga_temp_in_F', 43],
                ['00:46:46', 'fpga_temp_in_F', 43]
            ]
        }
    elif stat_key == "available_memory_MB":
        return {
            device_id: [
                ['00:45:49', 'available_memory_MB', 42840],
                ['00:45:54', 'available_memory_MB', 42840],
                ['00:45:59', 'available_memory_MB', 42840],
                ['00:46:00', 'available_memory_MB', 42840],
                ['00:46:05', 'available_memory_MB', 42840],
                ['00:46:10', 'available_memory_MB', 42840],
                ['00:46:15', 'available_memory_MB', 42840],
                ['00:46:16', 'available_memory_MB', 42840],
                ['00:46:20', 'available_memory_MB', 42840],
                ['00:46:25', 'available_memory_MB', 42840],
                ['00:46:30', 'available_memory_MB', 42840],
                ['00:46:31', 'available_memory_MB', 42840],
                ['00:46:36', 'available_memory_MB', 42840],
                ['00:46:41', 'available_memory_MB', 42840]
            ]
        }
    else:
        raise ValueError(f"Stat Key: {stat_key} not supported...")
