#include "sc_switch.h"

#include "sc_logger.h"

sc_switch::sc_switch() : sc_switch(0) {
  LOG(level_E::INFO, "sc_switch default constructor called.");
}

sc_switch::sc_switch(uint64_t sc_id) : s_id(sc_id) {
  LOG(level_E::INFO,
      "sc_switch object created with ID: " + std::to_string(sc_id));
}

sc_switch::~sc_switch() {
  LOG(level_E::INFO,
      "sc_switch object with ID: " + std::to_string(s_id.get_sc_id()) +
          " is being destroyed.");
}

std::string sc_switch::to_json() {
  LOG(level_E::INFO,
      "Generating JSON representation of sc_switch object with ID: " +
          std::to_string(s_id.get_sc_id()));
  std::stringstream json;
  json << "{\n";
  json << "  \"SwitchID\": " << s_id.get_sc_id() << ",\n";
  if (!s_manufacturer.empty()) {
    json << "  \"Manufacturer\": \"" << s_manufacturer << "\",\n";
  } else {
    json << "  \"Manufacturer\": \"Unknown\",\n";
  }
  if (s_nr_upstream_ports > 0) {
    json << "  \"UpstreamPorts\": " << s_nr_upstream_ports << ",\n";
  } else {
    json << "  \"UpstreamPorts\": 0,\n";
  }
  if (s_nr_downstream_ports > 0) {
    json << "  \"DownstreamPorts\": " << s_nr_downstream_ports << ",\n";
  } else {
    json << "  \"DownstreamPorts\": 0,\n";
  }
  if (s_mgmt_port > 0) {
    json << "  \"ManagementPort\": " << s_mgmt_port << "\n";
  } else {
    json << "  \"ManagementPort\": 0\n";
  }
  json << "}";
  LOG(level_E::INFO, "Generated JSON for sc_switch: " + json.str());
  return json.str();
}

void sc_switch::set_manufacturer(const std::string& manufacturer) {
  LOG(level_E::INFO, "Setting manufacturer for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         " to: " + manufacturer);
  s_manufacturer = manufacturer;
}

void sc_switch::set_upstream_ports(uint32_t num_ports) {
  LOG(level_E::INFO, "Setting upstream ports for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         " to: " + std::to_string(num_ports));
  s_nr_upstream_ports = num_ports;
}

void sc_switch::set_downstream_ports(uint32_t num_ports) {
  LOG(level_E::INFO, "Setting downstream ports for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         " to: " + std::to_string(num_ports));
  s_nr_downstream_ports = num_ports;
}

void sc_switch::set_mgmt_port(uint32_t port) {
  LOG(level_E::INFO, "Setting management port for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         " to: " + std::to_string(port));
  s_mgmt_port = port;
}

const std::string& sc_switch::get_manufacturer() const {
  LOG(level_E::INFO, "Retrieving manufacturer for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         ". Manufacturer: " + s_manufacturer);
  return s_manufacturer;
}

uint32_t sc_switch::get_upstream_ports() const {
  LOG(level_E::INFO, "Retrieving upstream ports for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         ". Ports: " + std::to_string(s_nr_upstream_ports));
  return s_nr_upstream_ports;
}

uint32_t sc_switch::get_downstream_ports() const {
  LOG(level_E::INFO, "Retrieving downstream ports for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         ". Ports: " + std::to_string(s_nr_downstream_ports));
  return s_nr_downstream_ports;
}

uint32_t sc_switch::get_mgmt_port() const {
  LOG(level_E::INFO, "Retrieving management port for sc_switch ID: " +
                         std::to_string(s_id.get_sc_id()) +
                         ". Port: " + std::to_string(s_mgmt_port));
  return s_mgmt_port;
}
