from abc import ABC, abstractmethod


class DataSource(ABC):
    @abstractmethod
    def init(self):
        pass

    @abstractmethod
    def get_scmc_version(self):
        pass

    @abstractmethod
    def update_metrics_host_filter(self):
        pass

    @abstractmethod
    def get_topology(self):
        pass

    @abstractmethod
    def get_hosts(self):
        pass

    @abstractmethod
    def post_devices(self):
        pass

    @abstractmethod
    def membox_capacity(self):
        pass

    @abstractmethod
    def host_devices(self):
        pass

    @abstractmethod
    def available_devices(self):
        pass

    @abstractmethod
    def detach_device(self):
        pass

    @abstractmethod
    def attach_device(self):
        pass

    @abstractmethod
    def get_mb_info(self):
        pass

    @abstractmethod
    def get_setup_info(self):
        pass

    @abstractmethod
    def get_devices_info(self):
        pass

    @abstractmethod
    def get_hosts_info(self):
        pass

    @abstractmethod
    def setup_tables(self):
        pass
