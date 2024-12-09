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
