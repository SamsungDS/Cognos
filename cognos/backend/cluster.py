

class Cluster():
    def __init__(self, cluster_name, nodes=None):
        self.cluster_name = cluster_name
        self.nodes = nodes  # list[Node]
        self.applications = None  # list[Application]
        self.config_params = None

    def display_cluster(self):
        print(self.cluster_name.center(50, '-'))
        for node in self.nodes:
            print(node.node_name.rjust(10, '>'))
            for device in node.devices:
                print(device.device_name.rjust(20, '>'))

    def add_node(self):
        pass

    def remove_node(self):
        pass

    def get_cluster_config_params(self):
        pass

    def configure_cluster(self):
        pass

    def subscribe_cognos_feature(self):
        pass

    def unsubscribe_cognos_feature(self):
        pass
