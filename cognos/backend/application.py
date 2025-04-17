

class Application():
    def __init__(self):
        self.application_id = None
        self.application_name = None
        self.nodes = None  # list[Node]
        self.slat_enabled = False
        self.pid_node_map = None  # { Node: pid }

    def get_app_sla(self):
        pass

    def set_app_sla(self):
        pass

    def attach_memory(self):
        pass

    def detach_memory(self):
        pass

    def get_app_stats(self):
        pass

    def start_app_profiling(self):
        pass

    def stop_app_profiling(self):
        pass

    def start_app_mem_tiering(self):
        pass

    def stop_app_mem_tiering(self):
        pass

    def get_app_resource_limits(self):
        pass

    def set_app_resource_limits(self):
        pass
