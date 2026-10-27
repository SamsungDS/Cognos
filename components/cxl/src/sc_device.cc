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

string sc_device::d_get_dev_name() const { return d_name; }

uint32_t sc_device::d_get_port() const { return d_port; }

uint64_t sc_device::d_get_capacity() const { return d_capacity; }

sc_id sc_device::d_get_id() const { return d_id; }

void sc_device::d_set_static_info(const DevStaticInfo& static_info) {
  d_info.static_info = static_info;
}

void sc_device::d_set_dynamic_info(const DevInfo& dynamic_info) {
  // Only copy dynamic fields — static info remains untouched
  d_info.status = dynamic_info.status;
  d_info.aspm_active = dynamic_info.aspm_active;
  d_info.sris_active = dynamic_info.sris_active;
  d_info.lock_active = dynamic_info.lock_active;
  d_info.numa_node = dynamic_info.numa_node;
  d_info.available_capacity_MB = dynamic_info.available_capacity_MB;
}

const DevInfo& sc_device::d_get_info() const { return d_info; }

DevInfo sc_device::to_device_info() const { return d_info; }
