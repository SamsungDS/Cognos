from cognos.backend.base_device import BaseDeviceObject
from typing import Dict


class CMMH(BaseDeviceObject):
    """
    In-Mem Object representation of a CMM-H device

    Enables serialization to underlying sqlite schema
    """
    def __init__(self, device_info: Dict, device_info_type: str):
        self._parse_device_info(device_info, device_info_type)

    @property
    def device_id(self):
        return self._device_id

    @property
    def device_type(self):
        return "CMM-H"

    @property
    def device_port(self):
        return self._device_port

    @property
    def capacity(self):
        return self._capacity

    @property
    def attached_type(self):
        return self._attached_type

    @property
    def name(self):
        return self._name

    def _parse_device_info(self, device_info: Dict,
                           device_info_type: str) -> None:
        """
        Populates device attributes by reading input
        given from CXL Plugin's direct device information
        """
        self._attached_type = device_info_type
        self._device_id = device_info["device_id"]
        self._capacity = device_info["total_capacity_MB"] * 1000000
        self._device_port = None
        self._name = self.device_type + "." + str(self._device_id)[-5:]

    def serialize_device_to_insert_query(self) -> str:
        """
        Returns string query to insert device
        and its attributes into sqlite devices table
        """
        if self.device_port:
            insert_query = (
                "INSERT INTO devices "
                "(id, mem_capacity, port, type, mode, name) "
                f"VALUES ({self.device_id}, {self.capacity}, "
                f"{self.device_port}, '{self.device_type}', "
                f"'{self.attached_type}', '{self.name}')"
            )
            return insert_query
        else:
            insert_query = (
                "INSERT INTO devices "
                "(id, mem_capacity, port, type, mode, name) "
                f"VALUES ({self.device_id}, {self.capacity}, "
                f"'{self.device_port}', '{self.device_type}', "
                f"'{self.attached_type}', '{self.name}')"
            )
            return insert_query
