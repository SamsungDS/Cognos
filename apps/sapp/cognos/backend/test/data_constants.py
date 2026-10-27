

DUMMY_NODE_INFO = {
    "node_name": "node_1",
    "fm_type": "FM_REMOTE_CMMD",
    "mem_capacity": 76535464645,
    "target_ports": [10, 11],
    "ip_addr": "0.0.0.0",
    "hostname": "lab-device-xyz.com",
    "remote_id": 123145241
}


DUMMY_DEVICE_REMOTE_INFO = {
    "dev_id": 549755813888,
    "dev_capacity": 274877906944,
    "dev_port": 10,
    "hosts_attached": ["node2"]
}

DUMMY_REMOTE_LIST_DEVICES_OUTPUT = [
    {
        "dev_id": 549755813888,
        "dev_capacity": 274877906944,
        "dev_port": 10,
        "hosts_attached": ["node2"]
    },
    {
        "dev_id": 454353231,
        "dev_capacity": 353252352,
        "dev_port": 11,
        "hosts_attached": ["node2"]
    }
]

DUMMY_DEVICE_DIRECT_INFO = {
    "api_version": 1.0,
    "device_id": 33638416369152,
    "manufacturer": "Samsung",
    "serial_number": 305419896,
    "FW_revision": "1.0.0",
    "location": "0000:c6:00.0",
    "total_capacity_MB": 516079,
    "feature_supported": "basic",
    "vendor_device_type": "CMM-H",
    "cxl_device_type": "Type3",
    "protocol": "CXL 2.0",
    "port_type": "root",
    "mode_discovered": "auto",
    "connection_type": "CXL.mem",
    "domain_type": "PCIe",
    "domain_id": 0,
    "link_speed": 32,
    "link_width": 8,
    "available_capacity_MB": 443507,
    "status": "active",
    "aspm_active": False,
    "sris_active": False,
    "lock_active": False,
    "numa_attached": 1,
    "capabilities": {"Power Management version": 1},
    "advertised_qos": {
        "avg_latency": 120, "p99_latency": 350, "io_per_sec": 50000,
        "BW_per_sec": 1000000, "io_size": 4096, "qd": 32
    }
}

CREATE_DEVICES_TABLE_QUERY = (
    "CREATE TABLE IF NOT EXISTS devices ("
    "id BIGINT UNSIGNED NOT NULL, "
    "mem_capacity BIGINT UNSIGNED, "
    "port INT UNSIGNED, "
    "type VARCHAR(32), "
    "mode VARCHAR(15), "
    "name VARCHAR(32), "
    "PRIMARY KEY (id)"
    ");"
)


DUMMY_INSERT_DEVICE_QUERY = (
    "INSERT INTO devices "
    "(id, mem_capacity, port, type, mode, name) "
    "VALUES (32312, 593502, 32, 'CMM-D', 'direct', 'DEV10.321')"
)


DUMMY_DEVICES_FETCH_QUERY = (
    "SELECT * FROM devices "
)

DUMMY_DEVICES_SINGLE_FETCH_QUERY = (
    "SELECT id from devices WHERE mode = 'direct' LIMIT 1"
)

DUMMY_COUNT_DEVICES_QUERY = (
    "SELECT COUNT(*) FROM devices"
)


DUMMY_INIT_DATA = {
    "nodeResponses": [
        {
            "nodeId": "localhost",
            "output": [
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
                                }
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
                        }
                    ],
                }
            ],
        }
    ]
}

DUMMY_HOSTS_DATA = [
    {
        "host_target_ports": [11, 10],
        "id": 551903297536,
        "mem_capacity": 547608330240,
        "name": "Host 1 LNK0",
    }
]

DUMMY_DEVICES_DATA = [
    {
        "dev_capacity": 274877906944,
        "dev_id": 549755813888,
        "dev_port": 10,
        "hosts_attached": ["Host 1 LNK0"],
    },
    {
        "dev_capacity": 274877906944,
        "dev_id": 824633720832,
        "dev_port": 11,
        "hosts_attached": ["Host 1 LNK0"],
    },
]


dummy_init_data = {
    "nodeResponses": [
        {
            "nodeId": "localhost",
            "output": str(
                [
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
                                    }
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
                            }
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
                ]
            ),
        }
    ]
}
