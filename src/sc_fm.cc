#include "sc_fm.h"

#include <iostream>
#include <unordered_set>

#include "sc_logger.h"

// Constructor that takes a json object
FabricManager::FabricManager(json_t *config) {
  LOG(level_E::INFO, "FabricManager constructor called.");
  // Parse the provided config
  parse_config(config);
  LOG(level_E::INFO, "FabricManager created with ID: " +
                         std::to_string(get_fmid().get_sc_id()));
}

// Destructor
FabricManager::~FabricManager() { cleanup(); }

void FabricManager::cleanup() {
  hosts.clear();
  devs.clear();
}

/*
 * @brief  Helper function to hash the ID from id_json
 */
uint64_t FabricManager::hash_id_json(json_t *id_json,
                                     const std::string &fm_type) {
  if (id_json == nullptr) {
    LOG(level_E::ERROR, "id_json is NULL. Cannot compute hash.");
    // 0 for invalid input
    return 0;
  }
  if (!json_is_integer(id_json)) {
    LOG(level_E::ERROR, "Invalid id format in JSON");
    // 0 for invalid input
    return 0;
  }
  uint64_t id_value = json_integer_value(id_json);
  if (fm_type.empty()) {
    LOG(level_E::ERROR, "fm_type is empty. Cannot compute hash.");
    // 0 for invalid input
    return 0;
  }
  std::ostringstream combined;
  combined << id_value << "_" << fm_type;
  uint64_t full_hash = std::hash<std::string>{}(combined.str());
  uint64_t short_hash = full_hash & 0xFFFFFF;  // Reduce hash to 7 digits
  LOG(level_E::INFO, "Hashed ID computed: " + std::to_string(short_hash));
  return short_hash;
}

/**
 * @brief parse json and populate vector<sc_host> and vector<sc_sld>
 */
void FabricManager::parse_config(json_t *config) {
  LOG(level_E::INFO, "Parsing FabricManager config.");
  // Parse the "id" and "type" fields
  json_t *id_json = json_object_get(config, "id");
  json_t *fm_type_json = json_object_get(config, "type");
  if (json_is_string(fm_type_json)) {
    set_fm_type(json_string_value(fm_type_json));
    // LOG(level_E::INFO, "Set FabricManager type: " + get_fm_type());
  }
  if (json_is_integer(id_json) && json_is_string(fm_type_json)) {
    uint64_t hashed_id = hash_id_json(id_json, get_fm_type());
    // Set the hashed ID in the sc_id member
    id.set_sc_id(hashed_id);
    LOG(level_E::INFO, "FabricManager initialized with hashed ID: " +
                           std::to_string(hashed_id));
  }
  // Parse the "Hosts" array
  json_t *hosts_json = json_object_get(config, "Hosts");
  if (json_is_array(hosts_json)) {
    size_t index;
    json_t *host_json;
    json_array_foreach(hosts_json, index, host_json) {
      const char *h_addr_str =
          json_string_value(json_object_get(host_json, "host_addr"));
      uint64_t h_addr = std::stoull(h_addr_str, nullptr, 16);
      const char *h_size_str =
          json_string_value(json_object_get(host_json, "host_size"));
      uint64_t h_size = std::stoull(h_size_str, nullptr, 16);
      sc_host h(h_addr);
      h.set_capacity(h_size);
      h.set_host_name(
          json_string_value(json_object_get(host_json, "host_name")));
      h.set_host_port(
          json_integer_value(json_object_get(host_json, "host_port")));
      LOG(level_E::INFO, "Parsed Host - ID: " + std::to_string(h.get_id()) +
                             ", Name: " + h.get_host_name());
      // endpoints
      json_t *endpoints = json_object_get(host_json, "endpoint");
      if (json_is_array(endpoints)) {
        size_t endpoint_index;
        json_t *endpoint;
        json_array_foreach(endpoints, endpoint_index, endpoint) {
          uint32_t d_port =
              json_integer_value(json_object_get(endpoint, "target"));
          h.set_target_ports(d_port);
          LOG(level_E::INFO,
              "Added endpoint for Host - Port: " + std::to_string(d_port));
        }
      }
      hosts.push_back(h);
    }
  }
  // Parse the "Devices" array
  json_t *devices_json = json_object_get(config, "Devices");
  if (json_is_array(devices_json)) {
    size_t index;
    json_t *device_json;
    json_array_foreach(devices_json, index, device_json) {
      const char *dev_addr_str =
          json_string_value(json_object_get(device_json, "dev_addr"));
      uint64_t dev_addr = std::stoull(dev_addr_str, nullptr, 16);
      // parse dev_size as a string and convert it to uint64_t
      const char *dev_size_str =
          json_string_value(json_object_get(device_json, "dev_size"));
      // Convert from hex string to uint64_t
      uint64_t dev_size = std::stoull(dev_size_str, nullptr, 16);
      const char *dev_name =
          json_string_value(json_object_get(device_json, "dev_name"));
      uint32_t dev_port =
          json_integer_value(json_object_get(device_json, "dev_port"));
      sc_sld d(dev_addr, dev_name, dev_size, dev_port);
      devs.push_back(d);
      LOG(level_E::INFO, "Parsed Device - Name: " + std::string(dev_name) +
                             ", Address: " + std::to_string(dev_addr) +
                             ", Port: " + std::to_string(dev_port));
    }
  }
}

/**
@brief set_up_info of direct attached device which includes host & device info.
 */
size_t FabricManager::setup_info(std::string &buffer) {
  LOG(level_E::INFO, "FabricManager::setup_info called.");

  if (hosts.empty() && devs.empty()) {
    LOG(level_E::WARN, "No hosts or devices found. Returning empty buffer.");
    buffer.clear();
    return 0;
  }

  LOG(level_E::INFO, "Populating JSON setup info...");

  // Create root object
  json_t *root = json_object();

  // Add id from the sc_id class
  json_object_set_new(root, "id", json_integer(id.get_sc_id()));
  json_object_set_new(root, "type", json_string(get_fm_type().c_str()));

  // Create hosts array
  json_t *hosts_array = json_array();
  // Loop through each host and populate their JSON objects
  for (auto &h : hosts) {
    json_t *host_obj = json_object();
    json_object_set_new(host_obj, "host_name",
                        json_string(h.get_host_name().c_str()));
    json_object_set_new(host_obj, "host_addr",
                        json_string(std::to_string(h.get_id()).c_str()));
    json_object_set_new(host_obj, "host_size",
                        json_string(std::to_string(h.get_capacity()).c_str()));
    json_object_set_new(host_obj, "host_port", json_integer(h.get_host_port()));

    LOG(level_E::INFO, "Processing Host - Name: " + h.get_host_name() +
                           ", Address: " + std::to_string(h.get_id()) +
                           ", Size: " + std::to_string(h.get_capacity()) +
                           ", Port: " + std::to_string(h.get_host_port()));
    // Set default values for fields not covered
    json_object_set_new(host_obj, "deinit_active", json_integer(0));
    json_object_set_new(host_obj, "host_port_type", json_string(""));
    json_object_set_new(host_obj, "classcode", json_integer(0));
    json_object_set_new(host_obj, "host_aspm_active", json_integer(0));
    json_object_set_new(host_obj, "host_sris_active", json_integer(0));
    json_object_set_new(host_obj, "host_equalization", json_integer(0));
    json_object_set_new(host_obj, "host_speed", json_integer(0));
    json_object_set_new(host_obj, "host_width", json_integer(0));

    // Initialize the endpoint array for the current host
    json_t *endpoint_array = json_array();
    // Populate d_ports for this host's target ports
    std::unordered_set<uint32_t> d_ports;

    for (auto &port : h.get_target_ports()) {
      d_ports.insert(port);
    }
    // Loop through each device to match target ports and populate endpoint
    // info
    for (const auto &d : devs) {
      // Match found for target port
      if (d_ports.count(d.d_get_port()) > 0) {
        json_t *endpoint_obj = json_object();
        json_object_set_new(endpoint_obj, "memdev",
                            json_string(d.d_get_dev_name().c_str()));
        json_object_set_new(endpoint_obj, "target",
                            json_integer(d.d_get_port()));
        json_object_set_new(
            endpoint_obj, "mem_addr",
            json_string(std::to_string(d.d_get_id().get_sc_id()).c_str()));
        json_object_set_new(
            endpoint_obj, "mem_size",
            json_string(std::to_string(d.d_get_capacity()).c_str()));
        json_object_set_new(endpoint_obj, "dev_offset", json_string("0"));
        // Append the endpoint object to the endpoint array
        json_array_append_new(endpoint_array, endpoint_obj);

        LOG(level_E::INFO,
            "Added Endpoint - Device: " + d.d_get_dev_name() +
                ", Port: " + std::to_string(d.d_get_port()) +
                ", Address: " + std::to_string(d.d_get_id().get_sc_id()) +
                ", Size: " + std::to_string(d.d_get_capacity()));
      }
    }
    // Add the populated endpoint array to the host object
    json_object_set_new(host_obj, "endpoint", endpoint_array);
    // Append the host object to the hosts array
    json_array_append_new(hosts_array, host_obj);
  }
  // Add hosts array to the root object
  json_object_set_new(root, "Hosts", hosts_array);
  // Create devices array
  json_t *devices_array = json_array();
  // Loop through each device and populate their JSON objects
  for (const auto &d : devs) {
    json_t *dev_obj = json_object();
    json_object_set_new(dev_obj, "dev_name",
                        json_string(d.d_get_dev_name().c_str()));
    json_object_set_new(
        dev_obj, "dev_addr",
        json_string(std::to_string(d.d_get_id().get_sc_id()).c_str()));
    json_object_set_new(
        dev_obj, "dev_size",
        json_string(std::to_string(d.d_get_capacity()).c_str()));
    json_object_set_new(dev_obj, "dev_port", json_integer(d.d_get_port()));
    // Set default values for fields not covered
    json_object_set_new(dev_obj, "dev_aspm_active", json_integer(0));
    json_object_set_new(dev_obj, "dev_sris_active", json_integer(0));
    json_object_set_new(dev_obj, "dev_lock_active", json_integer(0));
    json_object_set_new(dev_obj, "dev_speed", json_integer(0));
    json_object_set_new(dev_obj, "dev_width", json_integer(0));
    json_object_set_new(dev_obj, "dev_port_type", json_string(""));
    // Append the device object to the devices array
    json_array_append_new(devices_array, dev_obj);

    LOG(level_E::INFO,
        "Processed Device - Name: " + d.d_get_dev_name() +
            ", Address: " + std::to_string(d.d_get_id().get_sc_id()) +
            ", Size: " + std::to_string(d.d_get_capacity()) +
            ", Port: " + std::to_string(d.d_get_port()));
  }
  // Add devices array to the root object
  json_object_set_new(root, "Devices", devices_array);
  // Dump the JSON object to the buffer
  size_t bytes_written =
      json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  // Check if buffer size was sufficient
  if (bytes_written == 0 || bytes_written >= buffer.size()) {
    // Resize buffer and try again if the current buffer size is too small
    buffer.resize(bytes_written + 1);
    bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
  }

  LOG(level_E::INFO, "Setup info JSON generated. Bytes written: " +
                         std::to_string(bytes_written));
  // Clean up JSON object
  json_decref(root);
  return bytes_written;
}

void FabricManager::set_fm_type(std::string id_type) {
  LOG(level_E::INFO, "Setting FabricManager type: " + id_type);
  fm_type = id_type;
}

sc_id FabricManager::get_fmid() const {
  LOG(level_E::INFO,
      "Retrieving FabricManager ID: " + std::to_string(id.get_sc_id()));
  return id;
}

std::string FabricManager::get_fm_type() const {
  LOG(level_E::INFO, "Retrieving FabricManager type: " + fm_type);
  return fm_type;
}
