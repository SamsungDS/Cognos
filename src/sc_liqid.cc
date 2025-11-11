#include "sc_liqid.h"

#include <errno.h>

#include "sc_logger.h"
using namespace std;

// Constructor delegation
sc_liqid::sc_liqid() : sc_mbox(0, 0, 0) {
  LOG(level_E::INFO, "sc_liqid object created with default constructor.");
}

/**
@brief Creates a `sc_mbox` object with the given parameters.
 */
sc_liqid::sc_liqid(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch)
    : sc_mbox(mb_id, mb_fm_id, mb_switch) {
  LOG(level_E::INFO, "sc_liqid created - ID: " + to_string(mb_id) +
                         ", FM_ID: " + to_string(mb_fm_id));
}

sc_liqid::~sc_liqid() {
  LOG(level_E::INFO, "sc_liqid object with ID " +
                         to_string(d_get_id().get_sc_id()) +
                         " is being destroyed.");
}

/**
@brief Retrieves `d_get_id()`.
 */
sc_id sc_liqid::d_get_id() const { return sc_device::d_get_id(); }

/**
@details This function invokes STG API to detach a device from a host.
 */
int sc_liqid::d_detach(uint64_t d_id, uint64_t h_id, string mode) {
  return sc_mbox::d_detach(d_id, h_id, mode);

}

/**
@details This function invokes STG API to attach device to host.
 */
int sc_liqid::d_attach(uint64_t d_id, uint64_t h_id, string mode) {
  return sc_mbox::d_attach(d_id, h_id, mode);

}

// get mbox_connected_slds
unordered_map<sc_id, sc_sld, hash_sc_id> sc_liqid::get_slds_map() const {
  LOG(level_E::INFO, "Fetching liqid_connected_slds map.");
  return sc_mbox::get_slds_map();
}

// get mbox_connected_mlds
unordered_map<sc_id, sc_mld, hash_sc_id> sc_liqid::get_mlds_map() const {
  LOG(level_E::INFO, "Fetching liqid_connected_mlds map.");
  return sc_mbox::get_mlds_map();
}

// get mbox_connected_hosts
unordered_map<sc_id, sc_host, hash_sc_id> sc_liqid::get_hosts_map() const {
  LOG(level_E::INFO, "Fetching liqid_connected_hosts map.");
  return sc_mbox::get_hosts_map();
}

