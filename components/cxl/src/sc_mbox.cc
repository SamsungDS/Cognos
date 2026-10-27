#include "sc_mbox.h"

#include <errno.h>

#include "sc_logger.h"
using namespace std;

// Constructor delegation
sc_mbox::sc_mbox() : sc_mbox(0, 0, 0) {
  LOG(level_E::INFO, "sc_mbox object created with default constructor.");
}

/**
@brief Creates a `sc_mbox` object with the given parameters.
 */
sc_mbox::sc_mbox(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch)
    : sc_device(mb_id, "mbox1", 0, INVALID_DEV_PORT),
      mbox_fm_id(mb_fm_id),
      mbox_switch(mb_switch) {
  LOG(level_E::INFO, "sc_mbox created - ID: " + to_string(mb_id) +
                         ", FM_ID: " + to_string(mb_fm_id));
}

sc_mbox::~sc_mbox() {
  LOG(level_E::INFO, "sc_mbox object with ID " +
                         to_string(d_get_id().get_sc_id()) +
                         " is being destroyed.");
}

/**
@brief Deletes a device ID from `d_ids` map.
 */
int sc_mbox::delete_d_ids(sc_device dobj) {
  LOG(level_E::INFO,
      "Deleting device ID: " + to_string(dobj.d_get_id().get_sc_id()));
  auto d_id_it = d_ids.find(dobj.d_get_id().get_sc_id());
  if (d_id_it != d_ids.end()) {
    d_ids.erase(d_id_it);
    LOG(level_E::INFO, "Device ID deleted successfully.");
    return 0;
  }
  LOG(level_E::WARN, "Device ID not found.");
  return -ENOENT;
}

/**
@brief Deletes a device from `pdev` map.
 */
int sc_mbox::delete_pdev(sc_device dobj) {
  LOG(level_E::INFO,
      "Deleting device from pdev with port: " + to_string(dobj.d_get_port()));
  auto pdev_it = pdev.find(dobj.d_get_port());
  if (pdev_it != pdev.end()) {
    pdev.erase(pdev_it);
    LOG(level_E::INFO, "Device deleted successfully from pdev.");
    return 0;
  }
  LOG(level_E::WARN, "Device not found in pdev.");
  return -ENOENT;
}

/**
@brief Deletes an `sc_sld` from `mbox_connected_slds`.
 */
int sc_mbox::mbox_delete_sld(sc_sld sld) {
  LOG(level_E::INFO,
      "Deleting sc_sld with ID: " + to_string(sld.d_get_id().get_sc_id()));
  auto sld_it = mbox_connected_slds.find(sld.d_get_id());
  if (sld_it != mbox_connected_slds.end()) {
    mbox_connected_slds.erase(sld_it);
    LOG(level_E::INFO, "sc_sld deleted successfully.");
    return 0;
  }
  LOG(level_E::WARN, "sc_sld not found.");
  return -ENOENT;
}

/**
@brief Deletes an `sc_mld` from `mbox_connected_mlds`.
 */
int sc_mbox::mbox_delete_mld(sc_mld mld) {
  LOG(level_E::INFO,
      "Deleting sc_mld with ID: " + to_string(mld.d_get_id().get_sc_id()));
  auto mld_it = mbox_connected_mlds.find(mld.d_get_id());
  if (mld_it != mbox_connected_mlds.end()) {
    mbox_connected_mlds.erase(mld_it);
    LOG(level_E::INFO, "sc_mld deleted successfully.");
    return 0;
  }
  LOG(level_E::WARN, "sc_mld not found.");
  return -ENOENT;
}

/**
@brief Fetches memory box switch information.
 */
string sc_mbox::mbox_get_switch_info() {
  LOG(level_E::INFO, "Fetching memory box switch information.");
  return mbox_switch.to_json();
}

/**
@brief Lists connected `sc_sld` devices.
 */
list<sc_sld> sc_mbox::mbox_list_connected_slds() {
  LOG(level_E::INFO, "Listing all connected sc_sld devices.");
  list<sc_sld> values;
  transform(mbox_connected_slds.begin(), mbox_connected_slds.end(),
            back_inserter(values),
            [](const pair<sc_id, sc_sld>& pair) { return pair.second; });
  return values;
}

/**
@brief Lists connected `sc_mld` devices.
 */
list<sc_mld> sc_mbox::mbox_list_connected_mlds() {
  LOG(level_E::INFO, "Listing all connected sc_mld devices.");
  list<sc_mld> values;
  transform(mbox_connected_mlds.begin(), mbox_connected_mlds.end(),
            back_inserter(values),
            [](const pair<sc_id, sc_mld>& pair) { return pair.second; });
  return values;
}

/**
@brief Lists connected `sc_host` devices.
 */
list<sc_host> sc_mbox::mbox_list_connected_hosts() {
  LOG(level_E::INFO, "Listing all connected sc_host devices.");
  list<sc_host> values;
  transform(mbox_connected_hosts.begin(), mbox_connected_hosts.end(),
            back_inserter(values),
            [](const pair<sc_id, sc_host>& pair) { return pair.second; });
  return values;
}

/**
@brief Creates an `sc_sld` with given capacity.
 */
sc_sld sc_mbox::mbox_create_sld(uint64_t capacity) {
  LOG(level_E::INFO, "Creating sc_sld with capacity: " + to_string(capacity));
  sc_sld sld;
  sld.d_set_capacity(capacity);
  return sld;
}

/**
@brief Creates an `sc_mld` with given capacity.
 */
sc_mld sc_mbox::mbox_create_mld(uint64_t capacity) {
  LOG(level_E::INFO, "Creating sc_mld with capacity: " + to_string(capacity));
  sc_mld mld;
  mld.d_set_capacity(capacity);
  return mld;
}

/**
@brief add sld object to mbox_connected_slds, d_ids & pdev.
 */
void sc_mbox::addSld(sc_sld& sld) {
  LOG(level_E::INFO, "Adding sc_sld to mbox.");
  mbox_connected_slds.emplace(sld.d_get_id(), sld);
  d_ids.emplace(sld.d_get_id().get_sc_id(), sld.d_get_id());
  pdev.emplace(sld.d_get_port(), sld.d_get_id());
}

/**
@brief add mld object to mbox_connected_mlds, d_ids & pdev.
 */
void sc_mbox::addMld(sc_mld& mld) {
  LOG(level_E::INFO, "Adding sc_mld to mbox.");
  mbox_connected_mlds.emplace(mld.d_get_id(), mld);
  d_ids.emplace(mld.d_get_id().get_sc_id(), mld.d_get_id());
  pdev.emplace(mld.d_get_port(), mld.d_get_id());
}

/**
@brief Adds an `sc_host` to `mbox_connected_hosts`, h_ids & phost.
 */
void sc_mbox::addHost(sc_host& host) {
  LOG(level_E::INFO, "Adding sc_host to mbox.");
  mbox_connected_hosts.emplace(host.d_get_id(), host);
  h_ids.emplace(host.d_get_id().get_sc_id(), host.d_get_id());
  for (auto& p : host.get_target_ports()) {
    phost[p].push_back(host.d_get_id());
  }
}

/**
@brief Retrieves `d_get_id()`.
 */
sc_id sc_mbox::d_get_id() const { return sc_device::d_get_id(); }

/**
@details Search for `d_id` in SLD/MLD maps to fetch the respective `d_port`.
 */
int sc_mbox::fetch_device_port(uint64_t d_id) {
  LOG(level_E::INFO, "Fetching device port for d_id: " + to_string(d_id));
  uint32_t d_port = 0;
  // Check if the device exists in the SLD map
  if (mbox_connected_slds.find(d_ids[d_id]) != mbox_connected_slds.end()) {
    d_port = mbox_connected_slds[d_ids[d_id]].d_get_port();
    LOG(level_E::INFO, "Device found in SLD map. Port: " + to_string(d_port));
  }
  // Check if the device exists in the MLD map
  else if (mbox_connected_mlds.find(d_ids[d_id]) != mbox_connected_mlds.end()) {
    d_port = mbox_connected_mlds[d_ids[d_id]].d_get_port();
    LOG(level_E::INFO, "Device found in MLD map. Port: " + to_string(d_port));
  } else {
    LOG(level_E::WARN,
        "Device ID: " + to_string(d_id) + " not found in SLD/MLD maps.");
  }
  return d_port;
}

/**
@details This function invokes STG API to detach a device from a host.
 */
int sc_mbox::d_detach(uint64_t d_id, uint64_t h_id, string mode) {
  LOG(level_E::INFO, "Attempting to detach device ID: " + to_string(d_id) +
                         " from host ID: " + to_string(h_id));
  uint32_t d_port = fetch_device_port(d_id);
  if (d_port == 0) {
    LOG(level_E::ERROR,
        "Invalid device ID: " + to_string(d_id) + " - Port not found.");
    return -EINVAL;
  }
  LOG(level_E::INFO, "Checking if device is attached to host...");
  // Device ID and port are valid, now check if device is already connected to
  // host
  for (auto& v : mbox_connected_hosts[h_ids[h_id]].get_target_ports()) {
    if (v == d_port) {
      LOG(level_E::INFO,
          "Device is attached to host. Proceeding with detachment...");
      // Found device-to-host mapping, invoke STG API to disconnect
      int ret = mbox_A1_disconnect(
          mbox_connected_hosts[h_ids[h_id]].get_host_port(), d_port);
      if (ret == 0) {
        LOG(level_E::INFO,
            "Successfully detached device ID: " + to_string(d_id) +
                " from host ID: " + to_string(h_id));
        update_json_and_install();
        list<uint32_t>& h_to_dev_list =
            mbox_connected_hosts[h_ids[h_id]].get_target_ports();
        h_to_dev_list.remove(d_port);
        // Access phost map and remove the matching sc_id for d_port
        auto& phost_map = get_phost();
        if (phost_map.find(d_port) != phost_map.end()) {
          auto& host_objs_list = phost_map[d_port];
          for (auto it = host_objs_list.begin(); it != host_objs_list.end();
               ++it) {
            if (it->get_sc_id() == h_id) {
              host_objs_list.erase(it);
              LOG(level_E::INFO, "Removed host ID from phost map.");
              break;
            }
          }
          // If the list becomes empty, erase the entry from the map
          if (host_objs_list.empty()) {
            phost_map.erase(d_port);
            LOG(level_E::INFO,
                "phost map entry removed for port: " + to_string(d_port));
          }
        }
      } else {
        LOG(level_E::ERROR,
            "STG API failed to detach device ID: " + to_string(d_id) +
                " from host ID: " + to_string(h_id) +
                ". Error Code: " + to_string(ret));
      }
      return ret;
    }
  }
  LOG(level_E::WARN, "Device ID: " + to_string(d_id) +
                         " not attached to host ID: " + to_string(h_id));
  return -ENOENT;
}

/**
@details This function invokes STG API to attach device to host.
 */
int sc_mbox::d_attach(uint64_t d_id, uint64_t h_id, string mode) {
  LOG(level_E::INFO, "Attempting to attach device ID: " + to_string(d_id) +
                         " to host ID: " + to_string(h_id));
  uint32_t d_port = fetch_device_port(d_id);
  if (d_port == 0) {
    LOG(level_E::ERROR,
        "Invalid device ID: " + to_string(d_id) + " - Port not found.");
    return -ENOENT;
  } else if (mbox_connected_hosts.find(h_ids[h_id]) !=
             mbox_connected_hosts.end()) {
    LOG(level_E::INFO,
        "Host ID " + to_string(h_id) +
            " found in connected hosts. Proceeding with STG API call.");
    // Invoke STG API with host_port and dev_port
    int ret = mbox_A1_connect_by_hostport(
        mbox_connected_hosts[h_ids[h_id]].get_host_port(), d_port);
    if (ret == 0) {
      LOG(level_E::INFO,
          "STG API successfully attached device ID: " + to_string(d_id) +
              " to host ID: " + to_string(h_id));
      ret = update_json_and_install();
      if (ret != 0) {
        LOG(level_E::ERROR, "JSON update failed after attach.");
        return ret;
      }
      // Check if the device port is already in target_ports
      bool port_found = false;
      for (auto& v : mbox_connected_hosts[h_ids[h_id]].get_target_ports()) {
        if (v == d_port) {
          LOG(level_E::INFO, "Device port " + to_string(d_port) +
                                 " already present in target_ports.");
          port_found = true;
          break;
        }
      }
      // If port is not present, add it
      if (!port_found) {
        mbox_connected_hosts[h_ids[h_id]].set_target_ports(d_port);
        LOG(level_E::INFO, "Added device port " + to_string(d_port) +
                               " to host target_ports.");
      }
      // Update `phost` map: Check and add sc_id object if not already present
      auto& phost_map = get_phost();
      if (phost_map.find(d_port) != phost_map.end()) {
        auto& host_objs_list = phost_map[d_port];
        bool sc_id_found = false;
        for (auto& sc : host_objs_list) {
          if (sc.get_sc_id() == h_id) {
            LOG(level_E::INFO, "Host ID " + to_string(h_id) +
                                   " already present in phost map.");
            sc_id_found = true;
            break;
          }
        }
        if (!sc_id_found) {
          host_objs_list.push_back(sc_id(h_id));
          LOG(level_E::INFO, "Added host ID " + to_string(h_id) +
                                 " to phost map for port " + to_string(d_port));
        }
      } else {
        phost_map[d_port] = {sc_id(h_id)};
        LOG(level_E::INFO, "Created new phost entry for port " +
                               to_string(d_port) + " with host ID " +
                               to_string(h_id));
      }
    } else {
      LOG(level_E::ERROR,
          "STG API failed to attach device ID: " + to_string(d_id) +
              " to host ID: " + to_string(h_id) +
              ". Error Code: " + to_string(ret));
    }
    return ret;
  }
  LOG(level_E::ERROR,
      "Host ID: " + to_string(h_id) + " not found in connected hosts.");
  return -ENOENT;
}

// get mbox_connected_slds
unordered_map<sc_id, sc_sld, hash_sc_id> sc_mbox::get_slds_map() const {
  LOG(level_E::INFO, "Fetching mbox_connected_slds map.");
  return mbox_connected_slds;
}

// get mbox_connected_mlds
unordered_map<sc_id, sc_mld, hash_sc_id> sc_mbox::get_mlds_map() const {
  LOG(level_E::INFO, "Fetching mbox_connected_mlds map.");
  return mbox_connected_mlds;
}

// get mbox_connected_hosts
unordered_map<sc_id, sc_host, hash_sc_id> sc_mbox::get_hosts_map() const {
  LOG(level_E::INFO, "Fetching mbox_connected_hosts map.");
  return mbox_connected_hosts;
}

unordered_map<uint64_t, sc_id> sc_mbox::get_d_ids() const {
  LOG(level_E::INFO, "Fetching device ID map (d_ids).");
  return d_ids;
}

unordered_map<uint32_t, sc_id> sc_mbox::get_pdev() const {
  LOG(level_E::INFO, "Fetching physical device map (pdev).");
  return pdev;
}

unordered_map<uint32_t, list<sc_id>>& sc_mbox::get_phost() {
  LOG(level_E::INFO, "Fetching phost map.");
  return phost;
}
