/**
 * @file sc_dev_manager.cc
 * @brief Implementation of the DeviceManager class responsible for managing
 * device operations.
 */

#include "sc_dev_manager.h"

#include <jansson.h>

#include <iostream>
#include <sstream>

#include "sc_logger.h"
#include "sc_utility.h"

/**
 * @brief Gets the singleton instance of DeviceManager.
 */
DeviceManager& DeviceManager::getInstance() {
  static DeviceManager instance;
  return instance;
}

/**
 * @brief Private constructor for DeviceManager (Singleton).
 */
DeviceManager::DeviceManager() {
  LOG(level_E::INFO, "DeviceManager initialized.");
}

/**
 * @brief Parses the device_id JSON field and extracts device IDs.
 */
int DeviceManager::fetch_dev_ids_from_req(
    const std::string& json_request,
    std::unordered_set<uint64_t>& dev_ids_out) {
  json_error_t error;
  json_t* root = json_loads(json_request.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::ERROR, "JSON Parsing Error: " + std::string(error.text));
    return -EINVAL;
  }
  // Extract `device_id`
  json_t* device_id_field = json_object_get(root, "device_id");
  if (!device_id_field) {
    LOG(level_E::INFO, "No `device_id` provided, returning all devices.");
    json_decref(root);
    return 0;
  }
  // Helper lambda to parse and insert device ID
  auto _parse_and_insert_device_id = [&](json_t* value) {
    if (!json_is_string(value)) {
      LOG(level_E::ERROR, "Invalid `device_id` format. Must be string.");
      return;
    }
    uint64_t parsed_id;
    std::string error_response;
    if (str_to_int(json_string_value(value), parsed_id, error_response)) {
      dev_ids_out.insert(parsed_id);
    } else {
      LOG(level_E::ERROR, "Failed to parse device_id: " + error_response);
    }
  };
  // Process single string or array of strings
  if (json_is_string(device_id_field)) {
    _parse_and_insert_device_id(device_id_field);
  } else if (json_is_array(device_id_field)) {
    size_t index;
    json_t* value;
    json_array_foreach(device_id_field, index, value) {
      _parse_and_insert_device_id(value);
    }
  } else {
    LOG(level_E::ERROR, "Invalid `device_id` format. Must be string or array.");
    json_decref(root);
    return -EINVAL;
  }
  json_decref(root);
  return 0;
}

/**
 * @brief Fetches and aggregates device information from all registered
 * adapters.
 */
int DeviceManager::fetch_all_devices(
    const std::unordered_set<uint64_t>& dev_ids_out,
    std::string& device_result) {
  LOG(level_E::INFO, "Fetching all registered devices...");
  std::ostringstream oss;
  oss << R"({"devices":[)";
  int init_stream_pos = oss.tellp();
  for (const auto& entry : DeviceRegistry::getInstance().get_adapters()) {
    CXLDeviceAdapter* adapter = entry.second;
    if (!adapter) continue;
    LOG(level_E::INFO, "Querying adapter: " + entry.first);
    std::string adapter_result;
    int status = adapter->list_devices(dev_ids_out, adapter_result);
    if (status < 0) {
      LOG(level_E::ERROR, "list_devices failed for adapter: " + entry.first +
                              ", error: " + std::to_string(-status));
      return status;
    }
    if (!adapter_result.empty()) {
      if (oss.tellp() > init_stream_pos) oss << ",";
      oss << adapter_result;
    }
  }
  oss << "]}";
  device_result = oss.str();

  LOG(level_E::INFO, "DeviceManager::fetch_all_devices - Completed.");
  return 0;
}

/**
 * @brief Lists all registered devices based on provided filters.
 */
std::string DeviceManager::list_devices(
    const std::unordered_map<std::string, std::string>& params) {
  LOG(level_E::INFO,
      "DeviceManager::list_devices - Listing all registered devices.");

  std::unordered_set<uint64_t> dev_ids_out;

  // Extract device IDs from command parameters if present
  auto it = params.find("command_params");
  if (it != params.end()) {
    int status = fetch_dev_ids_from_req(it->second, dev_ids_out);
    if (status < 0) {
      LOG(level_E::ERROR, "Failed to fetch_dev_ids_from_req. Error Code: " +
                              std::to_string(status));
      return posix_err_to_json(std::abs(status), "Invalid request parameters");
    }
    LOG(level_E::INFO,
        "Device filter applied, filtering for specific device IDs.");
  } else {
    LOG(level_E::INFO,
        "Missing 'command_params' in request,  No device filter applied, "
        "listing all devices.");
  }

  std::string response;
  // Fetch & Aggregate Device Data
  int status = fetch_all_devices(dev_ids_out, response);
  if (status < 0) {
    return posix_err_to_json(std::abs(status),
                             "Failed to retrieve device list");
  }
  return response;
}

/**
 * @brief Retrieves detailed information about a specific device.
 */
std::string DeviceManager::get_device_info(
    const std::unordered_map<std::string, std::string>& params) {
  LOG(level_E::INFO, "Fetching device info...");
  //@to-do consider `domain_id` as part of auto device discovery
  auto it = params.find("device_id");
  if (it == params.end()) {
    LOG(level_E::ERROR, "Missing 'device_id' parameter in request.");
    return posix_err_to_json(EINVAL, "Missing 'device_id' parameter");
  }

  uint64_t d_id;
  std::string error_response;
  if (!str_to_int(it->second, d_id, error_response)) {
    return error_response;
  }
  CXLDeviceAdapter* adapter =
      DeviceRegistry::getInstance().getAdapterForDevice(d_id);
  if (!adapter) {
    LOG(level_E::ERROR,
        "No adapter found for device ID: " + std::to_string(d_id));
    return posix_err_to_json(ENOENT, "No adapter found for device ID");
  }
  std::string buffer;
  int status = adapter->get_device_info(d_id, buffer);
  if (status < 0) {
    LOG(level_E::ERROR, "Failed to retrieve device info for device ID: " +
                            std::to_string(d_id));
    return posix_err_to_json(std::abs(status),
                             "Failed to retrieve device info");
  }
  return buffer;
}

/**
 * @brief Handles the attachment of a device to a host (Only applicable for
 * CMMB).
 */
std::string DeviceManager::attach_memory(
    const std::unordered_map<std::string, std::string>& params) {
  LOG(level_E::INFO, "Attaching device...");
  // Extract device_id and host_id (node_id)
  auto d_it = params.find("device_id");
  auto h_it = params.find("host_id");
  if (d_it == params.end() || h_it == params.end()) {
    LOG(level_E::ERROR,
        "Missing required parameters 'device_id' or 'host_id'.");
    return posix_err_to_json(EINVAL, "Missing device_id or host_id");
  }
  uint64_t d_id, h_id;
  std::string error_response;
  if (!str_to_int(d_it->second, d_id, error_response) ||
      !str_to_int(h_it->second, h_id, error_response)) {
    return error_response;
  }

  CXLDeviceAdapter* adapter =
      DeviceRegistry::getInstance().getAdapterForDevice(d_id);
  if (!adapter) {
    LOG(level_E::ERROR,
        "No adapter found for device ID: " + std::to_string(d_id));
    return posix_err_to_json(ENOENT, "No adapter found for device ID");
  }
  std::string buffer;
  int status = adapter->attach_memory(d_id, h_id, buffer);
  if (status < 0) {
    LOG(level_E::ERROR, "Failed to attach memory: " + std::to_string(-status));
    return posix_err_to_json(std::abs(status), "Failed to attach memory");
  }
  return buffer;
}

/**
 * @brief Handles the detachment of a device from a host (Only applicable for
 * CMMB).
 */
std::string DeviceManager::detach_memory(
    const std::unordered_map<std::string, std::string>& params) {
  LOG(level_E::INFO, "Detaching device...");
  // Extract device_id and host_id
  auto d_it = params.find("device_id");
  auto h_it = params.find("host_id");
  if (d_it == params.end() || h_it == params.end()) {
    LOG(level_E::ERROR,
        "Missing required parameters 'device_id' or 'host_id'.");
    return posix_err_to_json(EINVAL, "Missing device_id or host_id");
  }
  uint64_t d_id, h_id;
  std::string error_response;
  if (!str_to_int(d_it->second, d_id, error_response) ||
      !str_to_int(h_it->second, h_id, error_response)) {
    return error_response;
  }
  CXLDeviceAdapter* adapter =
      DeviceRegistry::getInstance().getAdapterForDevice(d_id);
  if (!adapter) {
    LOG(level_E::ERROR,
        "No adapter found for device ID: " + std::to_string(d_id));
    return posix_err_to_json(ENOENT, "No adapter found for device ID");
  }
  std::string buffer;
  int status = adapter->detach_memory(d_id, h_id, buffer);
  if (status < 0) {
    LOG(level_E::ERROR,
        "detach_memory failed with error: " + std::to_string(-status));
    return posix_err_to_json(std::abs(status), "Failed to detach memory");
  }
  return buffer;
}
