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

DeviceManager::DeviceManager() {
  LOG(level_E::INFO, "DeviceManager initialized.");
}

DeviceManager::~DeviceManager() {
  LOG(level_E::INFO, "DeviceManager destroyed.");
}

/**
 * @brief Lists all devices discovered across all registered adapters.
 *
 * Only adapters that support bulk listing will be queried.
 *
 * @return JSON-formatted list of all devices.
 */
std::string DeviceManager::list_devices() {
  LOG(level_E::INFO,
      "DeviceManager::list_devices - No filter, returning all devices.");

  std::ostringstream oss;
  oss << R"({"devices":[)";
  int init_stream_pos = oss.tellp();

  for (const auto& [adapter_name, adapter] : get_adapters()) {
    if (!adapter) continue;

    std::string result;
    int status = adapter->list_devices(result);
    if (status == -ENOTSUP) continue;
    if (status < 0) {
      LOG(level_E::ERROR, "Adapter list_devices failed: " + adapter_name);
      return posix_err_to_json(std::abs(status), "Adapter list_devices failed");
    }
    if (!result.empty()) {
      if (oss.tellp() > init_stream_pos) oss << ",";
      oss << result;
    }
  }

  oss << "]}";
  return oss.str();
}

/**
 * @brief Lists devices matching the provided device IDs.
 *
 * Filters the device list based on provided `device_id`s.
 * Devices not found or unmapped to any adapter are ignored.
 *
 * @param[in] d_ids Set of device IDs to retrieve.
 * @return JSON-formatted list of matched devices.
 */
std::string DeviceManager::list_devices(
    const std::unordered_set<uint64_t>& d_ids) {
  LOG(level_E::INFO, "DeviceManager::list_devices - Listing filtered devices.");

  std::ostringstream oss;
  oss << R"({"devices":[)";
  int init_stream_pos = oss.tellp();

  for (const auto& d_id : d_ids) {
    auto id_it = d_id_to_sc_id.find(d_id);
    if (id_it == d_id_to_sc_id.end()) continue;

    const sc_id& sid = id_it->second;
    auto adapter_it = sc_id_to_adapter.find(sid);
    if (adapter_it == sc_id_to_adapter.end()) continue;

    CXLDeviceAdapter* adapter = adapter_it->second;
    std::string adapter_result;
    int status = adapter->list_devices(sid, adapter_result);
    if (status < 0) {
      LOG(level_E::ERROR,
          "Failed to fetch device info for ID: " + std::to_string(d_id));
      return posix_err_to_json(std::abs(status),
                               "Failed to fetch filtered devices");
    }
    if (!adapter_result.empty()) {
      if (oss.tellp() > init_stream_pos) oss << ",";
      oss << adapter_result;
    }
  }

  oss << "]}";
  return oss.str();
}

/**
 * @brief Retrieves detailed information about a specific device.
 */
std::string DeviceManager::get_device_info(uint64_t d_id) {
  LOG(level_E::INFO, "Fetching device info for ID: " + std::to_string(d_id));
  auto id_it = d_id_to_sc_id.find(d_id);
  if (id_it == d_id_to_sc_id.end()) {
    LOG(level_E::ERROR, "Invalid device_id: " + std::to_string(d_id));
    return posix_err_to_json(ENOENT, "Device ID not found");
  }
  const sc_id& scid = id_it->second;
  auto adapter_it = sc_id_to_adapter.find(scid);
  if (adapter_it == sc_id_to_adapter.end()) {
    LOG(level_E::ERROR, "No adapter mapped for sc_id: " + std::to_string(d_id));
    return posix_err_to_json(ENOENT, "No adapter found for device");
  }
  CXLDeviceAdapter* adapter = adapter_it->second;
  std::string buffer;
  int status = adapter->get_device_info(scid, buffer);
  if (status < 0) {
    LOG(level_E::ERROR, "Failed to retrieve device info for device_id: " +
                            std::to_string(d_id));
    return posix_err_to_json(std::abs(status),
                             "Failed to retrieve device info");
  }
  return buffer;
}

void DeviceManager::register_device(const sc_id& sid,
                                    CXLDeviceAdapter* adapter) {
  std::lock_guard<std::mutex> lock(registryMutex);
  uint64_t d_id = sid.get_sc_id();
  d_id_to_sc_id[d_id] = sid;
  sc_id_to_adapter[sid] = adapter;
  LOG(level_E::INFO, "Registered a device: " + std::to_string(d_id));
}

void DeviceManager::unregister_device(CXLDeviceAdapter* adapter) {
  std::lock_guard<std::mutex> lock(registryMutex);
  // Remove all sc_ids associated with this adapter
  std::vector<sc_id> ids_to_remove;
  for (const auto& [scid, registered_adapter] : sc_id_to_adapter) {
    if (registered_adapter == adapter) {
      ids_to_remove.push_back(scid);
    }
  }

  for (const sc_id& sid : ids_to_remove) {
    uint64_t d_id = sid.get_sc_id();
    sc_id_to_adapter.erase(sid);
    d_id_to_sc_id.erase(d_id);
    LOG(level_E::INFO, "Unregistered a device : " + std::to_string(d_id));
  }
}

/**
 * @brief Registers a new device adapter.
 */
void DeviceManager::registerAdapter(const std::string& name,
                                    CXLDeviceAdapter* adapter) {
  // Lock before modifying
  std::lock_guard<std::mutex> lock(registryMutex);
  adapterMap[name] = adapter;
  LOG(level_E::INFO, "Adapter '" + name + "' registered successfully.");
}

/**
 * @brief Unregisters a device adapter.
 */
void DeviceManager::unregisterAdapter(const std::string& name) {
  // Lock before modifying
  std::lock_guard<std::mutex> lock(registryMutex);
  if (adapterMap.erase(name)) {
    LOG(level_E::INFO, "Adapter '" + name + "' unregistered successfully.");
  } else {
    LOG(level_E::WARN,
        "Attempted to unregister non-existent adapter '" + name + "'.");
  }
}

/**
 * @brief Retrieves a registered adapter by name.
 */
CXLDeviceAdapter* DeviceManager::getAdapter(const std::string& name) {
  // Lock before accessing
  std::lock_guard<std::mutex> lock(registryMutex);
  auto it = adapterMap.find(name);
  if (it != adapterMap.end()) {
    LOG(level_E::INFO, "Adapter '" + name + "' retrieved successfully.");
    return it->second;
  }
  LOG(level_E::WARN, "Adapter '" + name + "' not found.");
  return nullptr;
}

const std::unordered_map<std::string, CXLDeviceAdapter*>&
DeviceManager::get_adapters() {
  std::lock_guard<std::mutex> lock(registryMutex);
  return adapterMap;
}
