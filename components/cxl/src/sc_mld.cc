#include "sc_mld.h"

#include <errno.h>

#include "sc_logger.h"
using namespace std;

// Constructor delegation
sc_mld::sc_mld() : sc_mld(0, "", 0, 0) {
  LOG(level_E::INFO, "sc_mld object created with default constructor.");
}

/**
@brief Creates a `sc_mld` object with the given parameters such as d_id,
d_name, capacity, and port.
 */
sc_mld::sc_mld(uint64_t d_id, string d_name, uint64_t capacity, uint32_t port)
    : sc_device(d_id, d_name, capacity, port) {
  LOG(level_E::INFO,
      "sc_mld created - ID: " + to_string(d_id) + ", Name: " + d_name +
          ", Capacity: " + to_string(capacity) + ", Port: " + to_string(port));
}

sc_mld::~sc_mld() {
  LOG(level_E::INFO, "sc_mld object with ID " +
                         to_string(d_get_id().get_sc_id()) +
                         " is being destroyed.");
}

/** Override set device port */
void sc_mld::d_set_port(uint32_t port) {
  LOG(level_E::INFO,
      "Setting port for sc_mld ID: " + to_string(d_get_id().get_sc_id()) +
          " to " + to_string(port));
  sc_device::d_set_port(port);
}

/** Override set device capacity */
void sc_mld::d_set_capacity(uint64_t capacity) {
  LOG(level_E::INFO,
      "Setting capacity for sc_mld ID: " + to_string(d_get_id().get_sc_id()) +
          " to " + to_string(capacity));
  sc_device::d_set_capacity(capacity);
}

/** Override set device name */
void sc_mld::d_set_dev_name(string d_name) {
  LOG(level_E::INFO, "Setting device name for sc_mld ID: " +
                         to_string(d_get_id().get_sc_id()) + " to " + d_name);
  sc_device::d_set_dev_name(d_name);
}

/** Override get device capacity */
uint64_t sc_mld::d_get_capacity() const {
  LOG(level_E::INFO, "Retrieving capacity for sc_mld ID: " +
                         to_string(d_get_id().get_sc_id()));
  return sc_device::d_get_capacity();
}

/** Override get device name */
string sc_mld::d_get_dev_name() const {
  LOG(level_E::INFO, "Retrieving device name for sc_mld ID: " +
                         to_string(d_get_id().get_sc_id()));
  return sc_device::d_get_dev_name();
}

/** Override get device port */
uint32_t sc_mld::d_get_port() const {
  LOG(level_E::INFO,
      "Retrieving port for sc_mld ID: " + to_string(d_get_id().get_sc_id()));
  return sc_device::d_get_port();
}

/** Override d_get_id */
sc_id sc_mld::d_get_id() const { return sc_device::d_get_id(); }

/**
@brief List all sc_mld devices.
 */
list<sc_device> sc_mld::list_mld_devices() {
  LOG(level_E::INFO, "Listing all sc_mld devices.");
  list<sc_device> ldList;
  for (const auto& entry : md_lds) {
    LOG(level_E::INFO,
        "sc_mld device found - ID: " + to_string(entry.first.get_sc_id()));
    ldList.push_back(entry.second);
  }
  return ldList;
}

/**
@brief Add a new sc_mld device by ID.
 */
int sc_mld::mld_id(uint64_t ldId) {
  LOG(level_E::INFO, "Adding new sc_mld device with ID: " + to_string(ldId));
  // Create an empty sc_device instance for the LD
  sc_device mld(ldId, "", 0, 0);
  // Add the LD to the map
  md_lds[mld.d_get_id()] = mld;
  LOG(level_E::INFO,
      "sc_mld device added successfully - ID: " + to_string(ldId));
  return 0;
}

/**
@brief Delete an sc_mld device by ID.
 */
int sc_mld::md_delete_ld(uint64_t ldId) {
  sc_id id(ldId);
  LOG(level_E::INFO,
      "Attempting to delete sc_mld device with ID: " + to_string(ldId));
  // Check if the LD exists
  auto it = md_lds.find(id);
  if (it == md_lds.end()) {
    LOG(level_E::ERROR,
        "sc_mld device not found for deletion - ID: " + to_string(ldId));
    return -ENOENT;
  }
  md_lds.erase(it);
  LOG(level_E::INFO,
      "sc_mld device deleted successfully - ID: " + to_string(ldId));
  return 0;
}
