#include "sc_sld.h"

// constructor delegation
sc_sld::sc_sld() : sc_sld(0, "", 0, 0) {};

/**
 * @brief creates a sc_mld object with the given parameters such as d_id,
 * d_name, capacity and port.
 * @param d_id delegated to sc_device and then to sc_id class.
 * @param d_name device name, delegated to sc_device class.
 * @param capacity device capacity, delegated to sc_device class.
 * @param port device port, delegated to sc_device class.
 */
sc_sld::sc_sld(uint64_t d_id, string d_name, uint64_t capacity,
               uint32_t port)
    : sc_device(d_id, d_name, capacity, port) {}

sc_sld::~sc_sld() {}

/** override set device port */
void sc_sld::d_set_port(uint32_t port) { sc_device::d_set_port(port); }

/** override set device capacity */
void sc_sld::d_set_capacity(uint64_t capacity) {
  sc_device::d_set_capacity(capacity);
}

/** override set device name */
void sc_sld::d_set_dev_name(string d_name) {
  sc_device::d_set_dev_name(d_name);
}

/** override d_get_id */
uint64_t sc_sld::d_get_id() { return sc_device::d_get_id(); }

/** override get device capacity */
uint64_t sc_sld::d_get_capacity() const { return sc_device::d_get_capacity(); }

/** override get device name */
string sc_sld::d_get_dev_name() { return sc_device::d_get_dev_name(); }

/** override get device port */
uint32_t sc_sld::d_get_port() { return sc_device::d_get_port(); }

/* override get_composite_obj */
sc_id sc_sld::get_composite_obj() { return sc_device::get_composite_obj(); }

list<sc_device> sc_sld::list_sld_devices() {
  list<sc_device> ldList;
  for (const auto& entry : sd_lds) {
    ldList.push_back(entry.second);
  }
  return ldList;}

int sc_sld::sd_create_ld(uint64_t ldId) {
  // Create an empty sc_device instance for the LD
  sc_device newLd(ldId, "", 0, 0);

  // Add the LD to the map
  sd_lds[newLd.get_composite_obj()] = newLd;

  // Return success status
  return 0;
}

int sc_sld::sd_delete_ld(uint64_t ldId) {
  sc_id id(ldId);
  // Check if the LD exists
  auto it = sd_lds.find(id);
  if (it == sd_lds.end()) {
    // LD not found
    return -1;
  }

  sd_lds.erase(it);

  return 0;
}

