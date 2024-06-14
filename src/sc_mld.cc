#include "sc_mld.h"
#include <errno.h>

using namespace std;

sc_mld::sc_mld() : sc_mld(0, "", 0, 0) {};

/**
 * @brief creates a sc_mld object with the given parameters such as d_id,
 * d_name, capacity and port.
 * @param d_id delegated to sc_device and then to sc_id class.
 * @param d_name device name, delegated to sc_device class.
 * @param capacity device capacity, delegated to sc_device class.
 * @param port device port, delegated to sc_device class.
 */
sc_mld::sc_mld(uint64_t d_id, string d_name, uint64_t capacity,
               uint32_t port)
    : sc_device(d_id, d_name, capacity, port) {}

sc_mld::~sc_mld() {}

/** override set device port */
void sc_mld::d_set_port(uint32_t port) { sc_device::d_set_port(port); }

/** override set device capacity */
void sc_mld::d_set_capacity(uint64_t capacity) {
  sc_device::d_set_capacity(capacity);
}

/** override set device name */
void sc_mld::d_set_dev_name(string d_name) {
  sc_device::d_set_dev_name(d_name);
}

/** override get device capacity */
uint64_t sc_mld::d_get_capacity() const { return sc_device::d_get_capacity(); }

/** override get device name */
string sc_mld::d_get_dev_name() const { return sc_device::d_get_dev_name(); }

/** override get device port */
uint32_t sc_mld::d_get_port() const { return sc_device::d_get_port(); }

/* override d_get_id */
sc_id sc_mld::d_get_id() const { return sc_device::d_get_id(); }

list<sc_device> sc_mld::list_mld_devices() {
  list<sc_device> ldList;
  // Iterate through the map and add LDs to the list
  for (const auto& entry : md_lds) {
    ldList.push_back(entry.second);
  }
  return ldList;}

/*
 * @brief create mld.
 */
int sc_mld::mld_id(uint64_t ldId) {
  // Create an empty sc_device instance for the LD
  sc_device mld(ldId, "", 0, 0);
  md_lds[mld.d_get_id()] = mld;
  return 0;
}

/*
 * @brief delete mld.
 */
int sc_mld::md_delete_ld(uint64_t ldId) {
  sc_id id(ldId);
  // Check if the LD exists
  auto it = md_lds.find(id);
  if (it == md_lds.end()) {
    return -ENOENT;
  }
  md_lds.erase(it);
  return 0;
}

