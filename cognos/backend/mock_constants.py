
MOCK_VERSION_NUMBER = "v1.1.11-1-g22d4"

MOCK_CLUSTERS = ['CL_ID_1']

MOCK_NODES = {
    'node_info': [
        {'node_ip': '000.000.00.001', 'node_name': 'msl-ssg-srf01',
         'node_port': '9998', 'status': 'online'},
        {'node_ip': '000.000.00.003', 'node_name': 'msl-ssg-srf03',
         'node_port': '9998', 'status': 'online'},
    ]
}

MOCK_CLUSTER_NODES = ["msl-ssg-srf01", "msl-ssg-srf03"]

MOCK_DEVICES = {
    "msl-ssg-srf01": [{'device_id': 33638416328448, 'vendor_device_type': 'CMM-H', 'pcie_addr': '0000:27:00.0'}],
    "msl-ssg-srf03": [
        {'device_id': 33638416328448, 'vendor_device_type': 'CMM-H', 'pcie_addr': '0000:27:00.0'},
        {'device_id': 33638416341504, 'vendor_device_type': 'CMM-H', 'pcie_addr': '0000:5a:00.0'},
        {'device_id': 33638416369152, 'vendor_device_type': 'CMM-H', 'pcie_addr': '0000:c6:00.0'},
        {'device_id': 33638416360448, 'vendor_device_type': 'CMM-H', 'pcie_addr': '0000:a4:00.0'}
    ]
}


BASE_DEVICE_INFO = {
    'feature_supported': 'basic',
    'vendor_device_type': 'CMM-H',
    'cxl_device_type': 'Type3',
    'protocol': 'CXL 2.0',
    'port_type': 'root',
    'mode_discovered': 'auto',
    'connection_type': 'CXL.mem',
    'domain_type': 'PCIe',
    'domain_id': 0,
    'link_speed_GT_s': 32,
    'link_width': 8,
    'available_capacity_MB': 0,
    'status': 'Healthy',
    'aspm_active': False,
    'sris_active': False,
    'lock_active': False,
    'numa_node': -1,
    'capabilities': {'Power Management version': 1},
    'advertised_qos': {
        'avg_latency_ns': 120,
        'p99_latency_ns': 350,
        'io_per_sec': 50000,
        'BW_per_sec': 1000000,
        'io_size_in_bytes': 4096,
        'qd': 32
    }
}

MOCK_DEVICE_INFO = {
    "msl-ssg-srf01": {
        33638416328448: {
            'api_version': 1.0,
            'device_id': 33638416328448,
            'manufacturer': 'samsung',
            'serial_number': 305419896,
            'FW_revision': '1.0.0',
            'location': '0000:27:00.0',
            'total_capacity_MB': 2064382,
            'feature_supported': 'basic',
            'vendor_device_type': 'CMM-H',
            'cxl_device_type': 'Type3',
            'protocol': 'CXL 2.0',
            'port_type': 'root',
            'mode_discovered': 'auto',
            'connection_type': 'CXL.mem',
            'domain_type': 'PCIe',
            'domain_id': 0,
            'link_speed_GT_s': 32,
            'link_width': 8,
            'available_capacity_MB': 42845,
            'status': 'Healthy',
            'aspm_active': False,
            'sris_active': False,
            'lock_active': False,
            'numa_node': 2,
            'capabilities': {'Power Management version': 1},
            'advertised_qos': {
                'avg_latency_ns': 120,
                'p99_latency_ns': 350,
                'io_per_sec': 50000,
                'BW_per_sec': 1000000,
                'io_size_in_bytes': 4096,
                'qd': 32
            }
        }
    },
    "msl-ssg-srf03": {
        33638416369152: {
            'api_version': 1.0,
            'device_id': 33638416369152,
            'manufacturer': 'samsung',
            'serial_number': 0,
            'FW_revision': '1.0.0',
            'location': '0000:c6:00.0',
            'total_capacity_MB': 2064312
        }.update(BASE_DEVICE_INFO),
        33638416328448: {
            'api_version': 1.0,
            'device_id': 33638416328448,
            'manufacturer': 'samsung',
            'serial_number': 0,
            'FW_revision': '1.0.0',
            'location': '0000:27:00.0',
            'total_capacity_MB': 2064331
        }.update(BASE_DEVICE_INFO),
        33638416341504: {
            'api_version': 1.0,
            'device_id': 33638416341504,
            'manufacturer': 'samsung',
            'serial_number': 0,
            'FW_revision': '1.0.0',
            'location': '0000:5a:00.0',
            'total_capacity_MB': 2064313,
        }.update(BASE_DEVICE_INFO),
        33638416360448: {
            'api_version': 1.0,
            'device_id': 33638416360448,
            'manufacturer': 'samsung',
            'serial_number': 0,
            'FW_revision': '1.0.0',
            'location': '0000:a4:00.0',
            'total_capacity_MB': 2064398
        }.update(BASE_DEVICE_INFO)
    }
}

MOCK_EVENTS = [
    {
        "timestamp": "2025-07-17T14:32:10Z",
        "msg": "CPU usage exceeded threshold",
        "payload": {
            "cpu_usage": "92",
            "threshold": "85",
            "process": "analytics-service"
        },
        "cluster_name": "CL_ID_1",
        "node_name": "msl-ssg-srf01",
        "category": "performance",
        "domain": "infrastructure",
        "severity": "critical",
        "source": "msl-ssg-srf01",
        "source_type": "node"
    },
    {
        "timestamp": "2025-07-17T14:35:42Z",
        "msg": "Disk space low",
        "payload": {
            "disk_used_percent": "96",
            "mount": "/var/log",
            "available_gb": "4"
        },
        "cluster_name": "CL_ID_1",
        "node_name": "msl-ssg-srf01",
        "category": "storage",
        "domain": "infrastructure",
        "severity": "warning",
        "source": "msl-ssg-srf01",
        "source_type": "node"
    },
    {
        "timestamp": "2025-07-17T14:40:01Z",
        "msg": "User login failed",
        "payload": {
            "username": "admin",
            "ip_address": "10.0.1.45",
            "reason": "invalid_password"
        },
        "cluster_name": "CL_ID_1",
        "node_name": "msl-ssg-srf03",
        "category": "security",
        "domain": "authentication",
        "severity": "warning",
        "source": "auth-service",
        "source_type": "application"
    }
]

MOCK_FM_CXL_SETUP = {
    "fabric_managers": [
        {
            "id": 1007,
            "type": "FM_DIRECT_CMMD",
            "Hosts": [
                {
                    "host_name": "msl-ssg-cx03",
                    "host_port": 2,
                    "deinit_active": 1,
                    "host_port_type": "dh",
                    "classcode": 0,
                    "host_aspm_active": 1,
                    "host_sris_active": 1,
                    "host_equalization": 1,
                    "host_speed": 5,
                    "host_width": 8,
                    "host_addr": "0x001010000000",
                    "host_size": "0x00C000000000",
                    "endpoint": [
                        {
                            "memdev": "mem15",
                            "target": 15,
                            "mem_addr": "0x003000000000",
                            "mem_size": "0x004000000000",
                            "dev_offset": "0",
                        },
                        {
                            "memdev": "mem14",
                            "target": 14,
                            "mem_addr": "0x002000000000",
                            "mem_size": "0x004000000000",
                            "dev_offset": "0",
                        },
                    ],
                }
            ],
            "Devices": [
                {
                    "dev_name": "DEV14-256G",
                    "dev_port": 14,
                    "dev_addr": "0x002000000000",
                    "dev_size": "0x004000000000",
                    "dev_aspm_active": 1,
                    "dev_sris_active": 1,
                    "dev_lock_active": 1,
                    "dev_speed": 5,
                    "dev_width": 8,
                    "dev_port_type": "dh",
                },
                {
                    "dev_name": "DEV15-256G",
                    "dev_port": 15,
                    "dev_addr": "0x003000000000",
                    "dev_size": "0x004000000000",
                    "dev_aspm_active": 1,
                    "dev_sris_active": 1,
                    "dev_lock_active": 1,
                    "dev_speed": 5,
                    "dev_width": 8,
                    "dev_port_type": "dh",
                },
                {
                    "dev_name": "DEV16-256G",
                    "dev_port": 16,
                    "dev_addr": "0x004000000000",
                    "dev_size": "0x004000000000",
                    "dev_aspm_active": 1,
                    "dev_sris_active": 1,
                    "dev_lock_active": 1,
                    "dev_speed": 5,
                    "dev_width": 8,
                    "dev_port_type": "dh",
                },
            ],
        },
        {
            "id": 2007,
            "type": "FM_DIRECT_CMMH",
            "Hosts": [
                {
                    "host_name": "msl-ssg-cx03",
                    "host_port": 2,
                    "deinit_active": 1,
                    "host_port_type": "dh",
                    "classcode": 0,
                    "host_aspm_active": 1,
                    "host_sris_active": 1,
                    "host_equalization": 1,
                    "host_speed": 5,
                    "host_width": 8,
                    "host_addr": "0x001010000000",
                    "host_size": "0x00C000000000",
                    "endpoint": [
                        {
                            "memdev": "mem17",
                            "target": 17,
                            "mem_addr": "0x005000000000",
                            "mem_size": "0x004000000000",
                            "dev_offset": "0",
                        }
                    ],
                }
            ],
            "Devices": [
                {
                    "dev_name": "DEV17-256G",
                    "dev_port": 17,
                    "dev_addr": "0x005000000000",
                    "dev_size": "0x004000000000",
                    "dev_aspm_active": 1,
                    "dev_sris_active": 1,
                    "dev_lock_active": 1,
                    "dev_speed": 5,
                    "dev_width": 8,
                    "dev_port_type": "dh",
                }
            ],
        },
        {
            "id": 3007,
            "type": "FM_REMOTE_CMMB",
            "Hosts": [
                {
                    "host_name": "msl-cti-emr1",
                    "host_port": 2,
                    "deinit_active": 1,
                    "host_port_type": "dh",
                    "classcode": 0,
                    "host_aspm_active": 1,
                    "host_sris_active": 1,
                    "host_equalization": 1,
                    "host_speed": 5,
                    "host_width": 8,
                    "host_addr": "0x002010000000",
                    "host_size": "0x00C000000000",
                    "endpoint": [
                        {
                            "memdev": "mem10",
                            "target": 10,
                            "mem_addr": "0x006000000000",
                            "mem_size": "0x004000000000",
                            "dev_offset": "0",
                        },
                        {
                            "memdev": "mem11",
                            "target": 11,
                            "mem_addr": "0x007000000000",
                            "mem_size": "0x004000000000",
                            "dev_offset": "0",
                        },
                    ],
                }
            ],
            "Devices": [
                {
                    "dev_name": "DEV10-256G",
                    "dev_port": 10,
                    "dev_addr": "0x006000000000",
                    "dev_size": "0x004000000000",
                    "dev_aspm_active": 1,
                    "dev_sris_active": 1,
                    "dev_lock_active": 1,
                    "dev_speed": 5,
                    "dev_width": 8,
                    "dev_port_type": "dh",
                },
                {
                    "dev_name": "DEV11-256G",
                    "dev_port": 11,
                    "dev_addr": "0x007000000000",
                    "dev_size": "0x004000000000",
                    "dev_aspm_active": 1,
                    "dev_sris_active": 1,
                    "dev_lock_active": 1,
                    "dev_speed": 5,
                    "dev_width": 8,
                    "dev_port_type": "dh",
                },
            ],
        },
    ]
}


MOCK_CXL_SETUP = {
    "Board": {
        "board_name": "Example Direct Config",
        "Mgmt_port_type": "PCIe",
        "json_version": "0100",
        "switch_mode": "direct",
        "management_port": 1,
    },
    "Hosts": [
        {
            "host_name": "msl-cti-emr1",
            "host_port": 2,
            "deinit_active": 1,
            "host_port_type": "CXL_11",
            "classcode": 0,
            "host_sris_active": 1,
            "host_aspm_active": 1,
            "host_equalization": 1,
            "host_speed": 5,
            "host_width": 8,
            "host_addr": "0x002080000000",
            "host_size": "0x003f80000000",
            "endpoint": [
                {
                    "memdev": "mem-10",
                    "target": 10,
                    "mem_addr": "0x002080000000",
                    "mem_size": "0x003f80000000",
                    "dev_offset": "0",
                }
            ],
        },
        {
            "host_name": "loaner-emr02",
            "host_port": 3,
            "deinit_active": 1,
            "host_port_type": "CXL_11",
            "classcode": 0,
            "host_sris_active": 1,
            "host_aspm_active": 1,
            "host_equalization": 1,
            "host_speed": 5,
            "host_width": 8,
            "host_addr": "0x008080000000",
            "host_size": "0x003f80000000",
            "endpoint": [
                {
                    "memdev": "mem-11",
                    "target": 11,
                    "mem_addr": "0x008080000000",
                    "mem_size": "0x003f80000000",
                    "dev_offset": "0",
                }
            ],
        },
        {
            "host_name": "msl-stg-emr03",
            "host_port": 4,
            "deinit_active": 1,
            "host_port_type": "CXL_11",
            "classcode": 0,
            "host_sris_active": 1,
            "host_aspm_active": 1,
            "host_equalization": 1,
            "host_speed": 5,
            "host_width": 8,
            "host_addr": "0x010080000000",
            "host_size": "0x007f80000000",
            "endpoint": [
                {
                    "memdev": "mem-5",
                    "target": 5,
                    "mem_addr": "0x010080000000",
                    "mem_size": "0x003f80000000",
                    "dev_offset": "0",
                },
                {
                    "memdev": "mem- 8",
                    "target": 8,
                    "mem_addr": "0x014000000000",
                    "mem_size": "0x004000000000",
                    "dev_offset": "0",
                },
            ],
        },
    ],
    "Devices": [
        {
            "dev_name": "DEV_10-256G",
            "dev_port": 10,
            "dev_addr": "0x002080000000",
            "dev_size": "0x003f80000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
        {
            "dev_name": "DEV_11-256G",
            "dev_port": 11,
            "dev_addr": "0x008080000000",
            "dev_size": "0x003f80000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
        {
            "dev_name": "DEV_5-256G",
            "dev_port": 5,
            "dev_addr": "0x010080000000",
            "dev_size": "0x003f80000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
        {
            "dev_name": "DEV_8-256G",
            "dev_port": 8,
            "dev_addr": "0x014000000000",
            "dev_size": "0x004000000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
        {
            "dev_name": "DEV_9-256G",
            "dev_port": 9,
            "dev_addr": "0x018000000000",
            "dev_size": "0x004000000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
        {
            "dev_name": "DEV_12-256G",
            "dev_port": 12,
            "dev_addr": "0x01C000000000",
            "dev_size": "0x004000000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
        {
            "dev_name": "DEV_13-256G",
            "dev_port": 13,
            "dev_addr": "0x020000000000",
            "dev_size": "0x004000000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20",
        },
    ],
}

MOCK_CXL_DEVICES = [
    {
        "dev_id": 13,
        "dev_capacity": 274877906944,
        "dev_port": 13,
        "hosts_attached": [],
    },
    {
        "dev_id": 9,
        "dev_capacity": 274877906944,
        "dev_port": 9,
        "hosts_attached": [],
    },
    {
        "dev_id": 5,
        "dev_capacity": 272730423296,
        "dev_port": 5,
        "hosts_attached": ["msl-stg-emr03"],
    },
    {
        "dev_id": 10,
        "dev_capacity": 272730423296,
        "dev_port": 10,
        "hosts_attached": ["msl-cti-emr1"],
    },
    {
        "dev_id": 12,
        "dev_capacity": 274877906944,
        "dev_port": 12,
        "hosts_attached": [],
    },
    {
        "dev_id": 8,
        "dev_capacity": 274877906944,
        "dev_port": 8,
        "hosts_attached": ["msl-stg-emr03"],
    },
    {
        "dev_id": 11,
        "dev_capacity": 272730423296,
        "dev_port": 11,
        "hosts_attached": ["loaner-emr02"],
    },
]


MOCK_CXL_HOSTS = [
    {
        "id": 4,
        "name": "msl-stg-emr03",
        "mem_capacity": 547608330240,
        "host_target_ports": [5, 8],
    },
    {
        "id": 3,
        "name": "loaner-emr02",
        "mem_capacity": 272730423296,
        "host_target_ports": [11],
    },
    {
        "id": 2,
        "name": "msl-cti-emr1",
        "mem_capacity": 272730423296,
        "host_target_ports": [10],
    },
]
