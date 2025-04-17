from abc import ABC, abstractmethod


class BaseDevice(ABC):
    @property
    @abstractmethod
    def node_name(self):
        pass

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
    def device_info(self):
        pass

    @property
    @abstractmethod
    def device_status(self):
        pass

    @property
    @abstractmethod
    def fm_type(self):
        pass

    @property
    @abstractmethod
    def capacity(self):
        pass

    @property
    @abstractmethod
    def device_name(self):
        pass

    @abstractmethod
    def get_device_info(self):
        pass

    @abstractmethod
    def get_device_stats(self):
        pass

    @abstractmethod
    def get_device_errors(self):
        pass

    @abstractmethod
    def get_device_alerts(self):
        pass

    @abstractmethod
    def get_device_health(self):
        pass

    @abstractmethod
    def configure_device(self):
        pass

    @abstractmethod
    def get_device_features(self):
        pass

    @abstractmethod
    def get_device_QOS_params(self):
        pass

    @abstractmethod
    def set_device_QOS_params(self):
        pass

    @abstractmethod
    def get_device_maintenance_operations(self):
        pass

    @abstractmethod
    def get_device_capabilities(self):
        pass

    @abstractmethod
    def get_device_event_records(self):
        pass
