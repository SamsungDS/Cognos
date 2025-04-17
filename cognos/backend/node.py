

class Node():
    def __init__(self, node_name, node_ip, node_fmtype, node_type,
                 devices=None, cluster_name=None):
        self.cluster_name = cluster_name
        self.node_name = node_name
        self.node_ip = node_ip
        self.node_fmtype = node_fmtype
        self.node_type = node_type
        self.devices = devices  # list[BaseDevice]
        self.node_info = None
        self.node_status = None
        self.port = None
        self.config_params = None
        self.applications = None
        self.features = None  # list[Feature]
        self.license = None
        self.application_devices = None  # { Application: list[BaseDevice]}

    def get_node_info(self):
        pass

    def get_node_stats(self):
        pass

    def get_node_errors(self):
        pass

    def get_node_alerts(self):
        pass

    def get_node_health(self):
        pass

    def list_devices(self):
        pass

    def list_registered_applications(self):
        pass

    def attach_device(self):
        pass

    def detach_device(self):
        pass

    def get_node_config_parameters(self):
        pass

    def configure_node(self):
        pass

    def get_enabled_features(self):
        pass

    def list_feature_commands(self):
        pass

    def get_feature_command_info(self):
        pass

    def get_feature_modules(self):
        pass

    def add_feature_module(self):
        pass

    def update_feature_module(self):
        pass

    def remove_feature_module(self):
        pass

    def get_feature_params(self):
        pass

    def set_feature_params(self):
        pass

    def list_available_cxl_mem_domains(self):
        pass

    def get_memory_domain_info(self):
        pass

    def list_available_cxl_ports_and_types(self):
        pass

    def get_port_status(self):
        pass

    def register_application(self):
        pass

    def unregister_application(self):
        pass
