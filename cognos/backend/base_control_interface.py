from abc import ABC, abstractmethod


class BaseControlInterface(ABC):
    @property
    @abstractmethod
    def cognos_endpoint(self):
        pass

    @property
    @abstractmethod
    def api_version(self):
        pass

    @property
    @abstractmethod
    def cognos_commands(self):
        pass

    @property
    @abstractmethod
    def feature_map(self):
        pass

    @abstractmethod
    def list_clusters(self):
        pass

    @abstractmethod
    def list_nodes(self):
        pass

    @abstractmethod
    def list_devices(self):
        pass

    @abstractmethod
    def create_cluster(self):
        pass

    @abstractmethod
    def delete_cluster(self):
        pass
