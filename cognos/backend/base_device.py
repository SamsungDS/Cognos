from abc import ABC, abstractmethod


class BaseDeviceObject(ABC):
    """
    Abstract Definition for Cognos Devices
    """
    @property
    @abstractmethod
    def device_id(self):
        pass

    @property
    @abstractmethod
    def device_type(self):
        pass

    @property
    @abstractmethod
    def device_port(self):
        pass

    @property
    @abstractmethod
    def capacity(self):
        pass

    @property
    @abstractmethod
    def attached_type(self):
        pass

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def _parse_device_info(self):
        pass
