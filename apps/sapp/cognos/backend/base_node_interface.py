from abc import ABC, abstractmethod


class BaseNodeInterface(ABC):
    @property
    @abstractmethod
    def node_type(self):
        pass

    @abstractmethod
    def list_devices(self):
        pass
