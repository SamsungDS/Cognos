from cognos.backend.base_device import BaseDevice


class CMMH(BaseDevice):
    def __init__(self, device_name):
        self._device_name = device_name

    @property
    def node_name(self):
        pass

    @property
    def device_name(self):
        return self._device_name

    @property
    def device_id(self):
        pass

    @property
    def device_type(self):
        return "cmmh"

    @property
    def device_info(self):
        pass

    @property
    def device_status(self):
        pass

    @property
    def fm_type(self):
        pass

    @property
    def capacity(self):
        pass

    def get_device_info(self):
        pass

    def get_device_stats(self):
        pass

    def get_device_errors(self):
        pass

    def get_device_alerts(self):
        pass

    def get_device_health(self):
        pass

    def configure_device(self):
        pass

    def get_device_features(self):
        pass

    def get_device_QOS_params(self):
        pass

    def set_device_QOS_params(self):
        pass

    def get_device_maintenance_operations(self):
        pass

    def get_device_capabilities(self):
        pass

    def get_device_event_records(self):
        pass
