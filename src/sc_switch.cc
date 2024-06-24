#include "sc_switch.h"


sc_switch::sc_switch() : sc_switch(0) {};

sc_switch::sc_switch(uint64_t sc_id) : s_id(sc_id) {}

sc_switch::~sc_switch() {}

std::string sc_switch::to_json() {
    // Create a stringstream to build the JSON-like string
    std::stringstream json;

    // Start the JSON object
    json << "{\n";

    // Add each member's information as key-value pairs
    json << "  \"SwitchID\": " << s_id.get_sc_id() << ",\n";
    json << "  \"Manufacturer\": \"" << s_manufacturer << "\",\n";
    json << "  \"UpstreamPorts\": " << s_nr_upstream_ports << ",\n";
    json << "  \"DownstreamPorts\": " << s_nr_downstream_ports << ",\n";
    json << "  \"ManagementPort\": " << s_mgmt_port << "\n";

    // End the JSON object
    json << "}";

    // Convert the stringstream to a string
    return json.str();
};


void sc_switch::set_manufacturer(const std::string& manufacturer) {
      s_manufacturer = manufacturer;
}

void sc_switch::set_upstream_ports(uint32_t num_ports) {
      s_nr_upstream_ports = num_ports;
}

void sc_switch::set_downstream_ports(uint32_t num_ports) {
      s_nr_downstream_ports = num_ports;
}

void sc_switch::set_mgmt_port(uint32_t port) {
      s_mgmt_port = port;
}

const std::string& sc_switch::get_manufacturer() const {
      return s_manufacturer;
}

uint32_t sc_switch::get_upstream_ports() const {
      return s_nr_upstream_ports;
}

uint32_t sc_switch::get_downstream_ports() const {
      return s_nr_downstream_ports;
}

uint32_t sc_switch::get_mgmt_port() const {
      return s_mgmt_port;
}



