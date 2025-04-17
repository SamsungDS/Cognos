#include "sc_device.h"

#include <regex>
#include <stdexcept>

using namespace std;

// constructor delegation
sc_device::sc_device() : sc_device(0, "", 0, 0) {}

/**
 * @brief creates sc_device object with the given parameters such as d_id,
 * d_name, capacity and port.
 */
sc_device::sc_device(uint64_t d_id, string d_name, uint64_t capacity,
                     uint32_t port)
    : d_id(d_id), d_name(d_name) {
  d_port = port;
  d_capacity = capacity;
}

sc_device::~sc_device() {}

void sc_device::d_set_dev_name(string d_name) {
  // Validate the device name using a regular expression
  std::regex validDevicename("^[A-Za-z0-9-]+$");
  if (std::regex_match(d_name, validDevicename)) {
    this->d_name = d_name;
  } else {
    throw std::invalid_argument("Invalid device name: " + std::string(d_name));
  }
}

void sc_device::d_set_port(uint32_t port) {
  // Check if the port value is valid
  if (port < 0 || port > 65535) {
    throw std::invalid_argument("Invalid port value: " + std::to_string(port));
  }

  d_port = port;
}

void sc_device::d_set_capacity(uint64_t capacity) {
  // Check if the capacity is within the valid range
  const uint64_t maxCapacity = 5024ull * 1024ull * 1024ull * 1024ull;
  if (capacity < 0 || capacity > maxCapacity) {
    throw std::invalid_argument("Invalid capacity value: " +
                                std::to_string(capacity));
  }
  d_capacity = capacity;
}

void sc_device::d_set_used_capacity(uint64_t used_capacity){
  d_used_capacity = used_capacity; 
}

string sc_device::d_get_dev_name() const { return d_name; }

uint32_t sc_device::d_get_port() const { return d_port; }

uint64_t sc_device::d_get_capacity() const { return d_capacity; }

sc_id sc_device::d_get_id() const { return d_id; }

uint64_t sc_device::d_get_available_capacity() {
  return d_capacity > d_used_capacity ? d_capacity - d_used_capacity : 0;
}


// Device Metadata
void sc_device::d_set_manufacturer(const std::string& mfg) {
  d_manufacturer = mfg;
}
std::string sc_device::d_get_manufacturer() const { return d_manufacturer; }

void sc_device::d_set_serial_number(uint64_t sn) {
  d_serial_number = sn;
}

uint64_t sc_device::d_get_serial_number() const { return d_serial_number; }

void sc_device::d_set_fw_revision(const std::string& rev) {
  d_fw_revision = rev;
}
std::string sc_device::d_get_fw_revision() const { return d_fw_revision; }

void sc_device::d_set_location(const std::string& loc) { d_location = loc; }
std::string sc_device::d_get_location() const { return d_location; }

void sc_device::d_set_status(const std::string& val) { d_status = val; }
std::string sc_device::d_get_status() const { return d_status; }

void sc_device::d_set_feature_supported(const std::string& val) {
  d_feature_supported = val;
}
std::string sc_device::d_get_feature_supported() const {
  return d_feature_supported;
}

void sc_device::d_set_device_type(const std::string& val) {
  d_device_type = val;
}
std::string sc_device::d_get_device_type() const { return d_device_type; }

void sc_device::d_set_cxl_type(const std::string& val) { d_cxl_type = val; }
std::string sc_device::d_get_cxl_type() const { return d_cxl_type; }

void sc_device::d_set_domain_id(uint32_t val) { d_domain_id = val; }
uint32_t sc_device::d_get_domain_id() const { return d_domain_id; }

void sc_device::d_set_domain_type(const std::string& val) {
  d_domain_type = val;
}
std::string sc_device::d_get_domain_type() const { return d_domain_type; }

void sc_device::d_set_connection_type(const std::string& val) {
  d_connection_type = val;
}
std::string sc_device::d_get_connection_type() const {
  return d_connection_type;
}

void sc_device::d_set_mode_discovered(const std::string& val) {
  d_mode_discovered = val;
}
std::string sc_device::d_get_mode_discovered() const {
  return d_mode_discovered;
}

void sc_device::d_set_protocol_version(const std::string& val) {
  d_protocol = val;
}
std::string sc_device::d_get_protocol_version() const { return d_protocol; }

// Flags
void sc_device::d_set_aspm_active(bool val) { d_aspm_active = val; }
bool sc_device::d_get_aspm_active() const { return d_aspm_active; }

void sc_device::d_set_sris_active(bool val) { d_sris_active = val; }
bool sc_device::d_get_sris_active() const { return d_sris_active; }

void sc_device::d_set_lock_active(bool val) { d_lock_active = val; }
bool sc_device::d_get_lock_active() const { return d_lock_active; }

// Link Info
void sc_device::d_set_link_speed(uint32_t speed) { d_link_speed = speed; }
uint32_t sc_device::d_get_link_speed() const { return d_link_speed; }

void sc_device::d_set_link_width(uint32_t val) { d_link_width = val; }
uint32_t sc_device::d_get_link_width() const { return d_link_width; }

void sc_device::d_set_port_type(const std::string& val) { d_port_type = val; }
std::string sc_device::d_get_port_type() const { return d_port_type; }

// NUMA
void sc_device::d_set_numa_attached(uint32_t val) { d_numa_attached = val; }
uint32_t sc_device::d_get_numa_attached() const { return d_numa_attached; }

// QoS & Capabilities
void sc_device::d_set_qos_info(const QoSInfo& qos) { d_qos_info = qos; }
const QoSInfo& sc_device::d_get_qos_info() const { return d_qos_info; }

void sc_device::d_set_capabilities(const Capabilities cap) { d_cap_info = cap; }
const Capabilities& sc_device::d_get_capabilities() const { return d_cap_info; }

// PCIe Address & Device Type
void sc_device::d_set_pcie_addr(const std::string& addr) {
  d_pcie_address = addr;
}
const std::string& sc_device::d_get_pcie_addr() const { return d_pcie_address; }

void sc_device::d_set_type(device_type type) { d_type = type; }
device_type sc_device::d_get_type() const { return d_type; }

DevInfo sc_device::to_device_info() const {
  DevInfo info;
  info.id = d_id.get_sc_id();
  info.manufacturer = d_manufacturer;
  info.serial_number = d_serial_number;
  info.fw_revision = d_fw_revision;
  info.location = d_location;
  info.total_capacity_MB = d_capacity;
  info.available_capacity_MB = d_capacity - d_used_capacity;
  info.status = d_status;
  info.feature_supported = d_feature_supported;
  info.device_type = d_device_type;
  info.cxl_type = d_cxl_type;
  info.domain_id = d_domain_id;
  info.domain_type = d_domain_type;
  info.connection_type = d_connection_type;
  info.mode_discovered = d_mode_discovered;
  info.protocol = d_protocol;
  info.aspm_active = d_aspm_active;
  info.sris_active = d_sris_active;
  info.lock_active = d_lock_active;
  info.link_speed = d_link_speed;
  info.link_width = d_link_width;
  info.port_type = d_port_type;
  info.numa_attached = d_numa_attached;
  info.advertized_qos = d_qos_info;
  info.capabilities = d_cap_info;
  return info;
}
