#include "sc_global.h"

#include <errno.h>
#include <stdint.h>

#include <memory>
#include <typeinfo>

#include "jansson.h"
#include "sc_host.h"
#include "sc_logger.h"
#include "sc_mbox.h"
#include "sc_mld.h"
#include "sc_sld.h"

using namespace std;

/**
 * @brief create memory box as per the json configuration.
 * @details This method takes struct portinfo as parameter
 *          and parses board, list of devices, hosts & endpoints information.
 * @param port_info memory box json struct reference.
 * @param dsize number of devices in the memory box.
 * @param hsize number of hosts in the memory box.
 */
int sc_global::g_create_mbox(struct StaticPortInfo* port_info) {
  LOG(level_E::INFO, "Creating mbox for given StaticPortInfo.");
  if (port_info == nullptr) {
    LOG(level_E::ERROR, "Port info is null. Returning -ENOENT.");
    return -ENOENT;
  }
  uint32_t mb_id = 102;
  sc_switch sw(mb_id + 102);
  sc_mbox* mb = new sc_mbox(mb_id, mb_id + 101, sw);
  for (int i = 0; i < port_info->num_dev; i++) {
    struct StaticDevInfo* dev_info = &port_info->dev[i];
    if (i % 2 == 0) {
      sc_sld sld(dev_info->mem_addr, dev_info->name, dev_info->mem_size,
                 dev_info->port);
      mb->addSld(sld);
      LOG(level_E::INFO, std::string("Added SLD device: ") + dev_info->name);
    } else {
      sc_mld mld(dev_info->mem_addr, dev_info->name, dev_info->mem_size,
                 dev_info->port);
      mb->addMld(mld);
      LOG(level_E::INFO, std::string("Added MLD device: ") + dev_info->name);
    }
  }
  for (int i = 0; i < port_info->num_host; i++) {
    struct StaticHostInfo* host_info = &port_info->host[i];
    sc_host h(host_info->mem_addr);
    h.set_host_name(host_info->name);
    h.set_host_port(host_info->port);
    h.set_capacity(host_info->mem_size);
    for (int i = 0; i < host_info->ep_cnt; i++) {
      struct StaticEndpointInfo* ep_info = &host_info->ep[i];
      h.set_target_ports(ep_info->port);
    }
    mb->addHost(h);
    LOG(level_E::INFO, std::string("Added Host: ") + host_info->name);
  }
  sc_devices[mb_id + 101] = mb;
  mb_objs.push_back(mb);
  LOG(level_E::INFO, "Mbox creation complete. Stored in sc_devices with ID: " +
                         to_string(mb_id + 101));
  return 0;
}

// get sc_devices map
unordered_map<uint64_t, sc_mbox*>& sc_global::get_mbox_map() {
  LOG(level_E::INFO, "Fetching sc_devices map.");
  return sc_devices;
}

sc_mbox* sc_global::mbox_find(uint64_t fm_id) {
  LOG(level_E::INFO, "Searching for mbox with ID: " + to_string(fm_id));
  for (auto& pair : get_mbox_map()) {
    if (pair.first == fm_id) {
      LOG(level_E::INFO, "Mbox found for ID: " + to_string(fm_id));
      sc_mbox* mb = pair.second;
      return mb;
    }
  }
  LOG(level_E::WARN, "Mbox not found for ID: " + to_string(fm_id));
  return nullptr;
}

/**
@details This method invokes sc_mbox class d_connect method which attaches a
device to the host.
*/
size_t sc_global::dev_attach(uint64_t d_id, uint64_t h_id, string mode,
                             uint64_t fm_id, string& buffer) {
  LOG(level_E::INFO, "Attempting to attach device " + to_string(d_id) +
                         " to host " + to_string(h_id) + " under FM ID " +
                         to_string(fm_id));
  int rc;
  sc_mbox* mb = mbox_find(fm_id);
  if (mb == NULL) {
    rc = -ENOENT;
    LOG(level_E::ERROR, "Mbox not found for FM ID: " + to_string(fm_id) +
                            ". Returning -ENOENT.");
  } else {
    rc = mb->d_attach(d_id, h_id, mode);
    LOG(level_E::INFO, "Device attach result: " + to_string(rc));
  }
  return to_json(rc, buffer);
}

/**
@details This method invokes sc_mbox class d_disconnect method which detaches a
device from the host.
*/
size_t sc_global::dev_detach(uint64_t d_id, uint64_t h_id, string mode,
                             uint64_t fm_id, string& buffer) {
  LOG(level_E::INFO, "Attempting to detach device " + to_string(d_id) +
                         " from host " + to_string(h_id) + " under FM ID " +
                         to_string(fm_id));
  int rc;
  sc_mbox* mb = mbox_find(fm_id);
  if (mb == NULL) {
    rc = -ENOENT;
    LOG(level_E::ERROR, "Mbox not found for FM ID: " + to_string(fm_id) +
                            ". Returning -ENOENT.");
  } else {
    rc = mb->d_detach(d_id, h_id, mode);
    LOG(level_E::INFO, "Device detach result: " + to_string(rc));
  }
  return to_json(rc, buffer);
}

/**
@details Create JSON object using the input provided.
 */
size_t sc_global::to_json(int ret, string& buffer) {
  LOG(level_E::INFO,
      "Converting return code " + to_string(ret) + " to JSON format.");
  json_t* root = json_object();
  json_t* jtemp = json_integer(ret);
  json_object_set_new(root, "rc", jtemp);
  // Dump the JSON object to the buffer
  size_t bytes_written =
      json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  if (bytes_written == 0 || bytes_written >= buffer.size()) {
    size_t buffer_size = bytes_written + 1;
    buffer.resize(buffer_size);
    bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  }
  json_decref(root);
  LOG(level_E::INFO,
      "JSON conversion completed. Bytes written: " + to_string(bytes_written));
  return bytes_written;
}

/**
@brief create json response by iterating over persisted device objects.
 */
size_t sc_global::to_device_json(string& buffer) {
  LOG(level_E::INFO, "Generating JSON response for device objects.");
  json_t* root = json_object();
  json_t* temp = json_array();
  json_object_set_new(root, "devices", temp);
  for (const auto& pair : get_mbox_map()) {
    sc_mbox* mb = pair.second;
    LOG(level_E::INFO, "Processing sc_mbox with ID: " + to_string(pair.first));
    for (auto& sld : mb->mbox_list_connected_slds()) {
      json_t* jroot = json_object();
      json_t* jtemp = NULL;
      jtemp = json_integer(sld.d_get_id().get_sc_id());
      json_object_set_new(jroot, "dev_id", jtemp);
      jtemp = json_integer(sld.d_get_capacity());
      json_object_set_new(jroot, "dev_capacity", jtemp);
      jtemp = json_integer(sld.d_get_port());
      json_object_set_new(jroot, "dev_port", jtemp);
      jtemp = json_array();
      json_object_set_new(jroot, "hosts_attached", jtemp);
      list<sc_id>& hl = mb->get_phost()[sld.d_get_port()];
      if (hl.empty()) {
        json_object_set_new(jroot, "hosts_attached", json_array());
        LOG(level_E::WARN, "No hosts attached to SLD device ID: " +
                               to_string(sld.d_get_id().get_sc_id()));
      } else {
        for (auto& sc_h : hl) {
          json_array_append_new(
              jtemp,
              json_string(mb->get_hosts_map()[sc_h].get_host_name().c_str()));
        }
        LOG(level_E::INFO, "Hosts attached to SLD device ID: " +
                               to_string(sld.d_get_id().get_sc_id()));
      }
      json_array_append(temp, jroot);
    }
    for (auto& mld : mb->mbox_list_connected_mlds()) {
      json_t* jroot = json_object();
      json_t* jtemp = NULL;
      jtemp = json_integer(mld.d_get_id().get_sc_id());
      json_object_set_new(jroot, "dev_id", jtemp);
      jtemp = json_integer(mld.d_get_capacity());
      json_object_set_new(jroot, "dev_capacity", jtemp);
      jtemp = json_integer(mld.d_get_port());
      json_object_set_new(jroot, "dev_port", jtemp);
      jtemp = json_array();
      json_object_set_new(jroot, "hosts_attached", jtemp);
      list<sc_id>& hl = mb->get_phost()[mld.d_get_port()];
      if (hl.empty()) {
        json_object_set_new(jroot, "hosts_attached", json_array());
        LOG(level_E::WARN, "No hosts attached to MLD device ID: " +
                               to_string(mld.d_get_id().get_sc_id()));
      } else {
        for (auto& sc_h : hl) {
          json_array_append_new(
              jtemp,
              json_string(mb->get_hosts_map()[sc_h].get_host_name().c_str()));
        }
        LOG(level_E::INFO, "Hosts attached to MLD device ID: " +
                               to_string(mld.d_get_id().get_sc_id()));
      }
      json_array_append(temp, jroot);
    }
  }
  size_t bytes_written =
      json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  if (bytes_written == 0 || bytes_written >= buffer.size()) {
    size_t buffer_size = bytes_written + 1;
    buffer.resize(buffer_size);
    bytes_written = json_dumpb(root, &buffer[0], buffer_size, JSON_INDENT(0));
  }
  json_decref(root);
  LOG(level_E::INFO,
      "Device JSON response generation completed. Bytes written: " +
          to_string(bytes_written));
  return bytes_written;
}

/**
@brief create json response by iterating over persisted host objects.
 */
size_t sc_global::to_host_json(string& buffer) {
  LOG(level_E::INFO, "Generating JSON response for host objects.");
  json_t* root = json_object();
  json_t* temp = json_array();
  json_object_set_new(root, "hosts", temp);
  for (const auto& pair : get_mbox_map()) {
    sc_mbox* mb = pair.second;
    LOG(level_E::INFO, "Processing sc_mbox with ID: " + to_string(pair.first));
    for (auto& h : mb->mbox_list_connected_hosts()) {
      json_t* jroot = json_object();
      json_t* jtemp = NULL;
      uint64_t h_id = h.get_id();
      jtemp = json_integer(h_id);
      json_object_set_new(jroot, "id", jtemp);
      std::string h_name = h.get_host_name();
      jtemp = json_string(h_name.c_str());
      json_object_set_new(jroot, "name", jtemp);
      jtemp = json_integer(h.get_capacity());
      json_object_set_new(jroot, "mem_capacity", jtemp);
      jtemp = json_array();
      json_object_set_new(jroot, "host_target_ports", jtemp);
      for (auto& v : h.get_target_ports()) {
        json_array_append_new(jtemp, json_integer(v));
      }
      json_array_append(temp, jroot);
      LOG(level_E::INFO,
          "Processed host: " + h_name + " with ID: " + to_string(h_id));
    }
  }
  size_t bytes_written =
      json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  if (bytes_written == 0 || bytes_written >= buffer.size()) {
    size_t buffer_size = bytes_written + 1;
    buffer.resize(buffer_size);
    bytes_written = json_dumpb(root, &buffer[0], buffer_size, JSON_INDENT(0));
  }
  json_decref(root);
  LOG(level_E::INFO,
      "Host JSON response generation completed. Bytes written: " +
          to_string(bytes_written));
  return bytes_written;
}

size_t sc_global::to_setup_json(string& buffer) {
  LOG(level_E::INFO, "Loading setup JSON from input.json");
  json_t* root;
  json_error_t error;
  root = json_load_file("input.json", 0, &error);
  if (!root) {
    LOG(level_E::ERROR, "Failed to load input.json: " + string(error.text));
    return 0;
  }
  LOG(level_E::INFO, "Successfully loaded input.json, serializing to buffer.");
  // Dump the JSON object to the buffer
  size_t bytes_written =
      json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  // Check if buffer size was sufficient
  if (bytes_written == 0 || bytes_written >= buffer.size()) {
    LOG(level_E::WARN,
        "Buffer too small, resizing and retrying serialization.");
    size_t buffer_size = bytes_written + 1;
    buffer.resize(buffer_size);
    bytes_written = json_dumpb(root, &buffer[0], buffer_size, JSON_INDENT(0));
  }
  LOG(level_E::INFO, "Setup JSON serialization completed. Bytes written: " +
                         to_string(bytes_written));
  // Clean up
  json_decref(root);
  return bytes_written;
}

size_t sc_global::fetch_setup_info(string& buffer) {
  LOG(level_E::INFO, "Fetching setup information.");
  return to_setup_json(buffer);
}

size_t sc_global::list_devices(string& buffer) {
  LOG(level_E::INFO, "Listing connected devices.");
  return to_device_json(buffer);
}

size_t sc_global::list_hosts(string& buffer) {
  LOG(level_E::INFO, "Listing connected hosts.");
  return to_host_json(buffer);
}

void sc_global::clear_mbox_objects() {
  LOG(level_E::INFO, "Clearing all stored mbox objects.");
  mb_objs.clear();
}

void sc_global::add_fm(const sc_id& id, FabricManager& manager) {
  LOG(level_E::INFO,
      "Adding FabricManager with ID: " + to_string(id.get_sc_id()));
  // Store the address of the FabricManager reference in the map
  fm_map[id] = &manager;
}

void sc_global::del_fm(const sc_id& id) {
  LOG(level_E::INFO, "Attempting to delete FabricManager with ID: " +
                         to_string(id.get_sc_id()));
  auto it = fm_map.find(id);
  if (it != fm_map.end()) {
    // Delete the FabricManager object to prevent memory leaks
    delete it->second;
    // Remove the entry from the map
    fm_map.erase(it);
    LOG(level_E::INFO,
        "Deleted FabricManager with ID: " + to_string(id.get_sc_id()));
  } else {
    LOG(level_E::WARN,
        "FabricManager with ID: " + to_string(id.get_sc_id()) + " not found.");
  }
}

FabricManager* sc_global::find_fm(const sc_id& id) {
  LOG(level_E::INFO,
      "Searching for FabricManager with ID: " + to_string(id.get_sc_id()));
  auto it = fm_map.find(id);
  if (it != fm_map.end()) {
    LOG(level_E::INFO,
        "FabricManager found with ID: " + to_string(id.get_sc_id()));
    // Return the pointer to the FabricManager object
    return it->second;
  }
  LOG(level_E::WARN,
      "FabricManager with ID: " + to_string(id.get_sc_id()) + " not found.");
  // Return nullptr if the sc_id is not found
  return nullptr;
}

std::vector<sc_id> sc_global::get_fm_keys() const {
  LOG(level_E::INFO, "Fetching all FabricManager keys.");
  std::vector<sc_id> keys;
  for (const auto& entry : fm_map) {
    keys.push_back(entry.first);
  }
  LOG(level_E::INFO,
      "Total FabricManager keys fetched: " + to_string(keys.size()));
  return keys;
}

void sc_global::cleanup_fm_map() {
  for (auto& entry : fm_map) {
    // Delete each dynamically allocated FabricManager
    delete entry.second;
  }
  // Clear the map to remove all entries
  fm_map.clear();
}

sc_global::~sc_global() { cleanup_fm_map(); }
