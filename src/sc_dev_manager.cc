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
 * @return vector of sc_device.
 */
std::vector<sc_device> DeviceManager::list_devices() {
  LOG(level_E::INFO,
      "DeviceManager::list_devices - No filter, returning all devices.");
  std::vector<sc_device> result;

  for (const auto& [adapter_name, adapter] : get_adapters()) {
    if (!adapter) continue;

    try {
      // Adapter returns a list of its managed devices
      std::vector<sc_device> adapter_devices = adapter->list_devices();

      // Append adapter’s devices to the aggregated result
      result.insert(result.end(), adapter_devices.begin(),
                    adapter_devices.end());
    } catch (const std::exception& ex) {
      LOG(level_E::ERROR,
          "Adapter list_devices threw exception: " + std::string(ex.what()));
    }
  }

  return result;
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
std::vector<sc_device> DeviceManager::list_devices(
    const std::unordered_set<uint64_t>& d_ids) {
  LOG(level_E::INFO, "DeviceManager::list_devices - Filtered by device IDs.");

  std::vector<sc_device> result;

  for (const auto& d_id : d_ids) {
    // Map device_id to sc_id
    auto id_it = d_id_to_sc_id.find(d_id);
    if (id_it == d_id_to_sc_id.end()) {
      LOG(level_E::WARN,
          "Device ID not found in registry: " + std::to_string(d_id));
      continue;  // skip unknown device
    }

    const sc_id& sid = id_it->second;
    // Get adapter mapped to this sc_id
    auto adapter_it = sc_id_to_adapter.find(sid);
    if (adapter_it == sc_id_to_adapter.end() || adapter_it->second == nullptr) {
      LOG(level_E::WARN,
          "No adapter found for sc_id: " + std::to_string(sid.get_sc_id()));
      continue;
    }

    CXLDeviceAdapter* adapter = adapter_it->second;
    try {
      // Fetch the specific device via adapter
      const sc_device& dev = adapter->get_device_object(sid);
      result.push_back(dev);
    } catch (const std::exception& ex) {
      LOG(level_E::ERROR,
          "Error retrieving device " + std::to_string(d_id) + ": " + ex.what());
    }
  }

  return result;
}

/**
 * @brief Retrieves detailed information about a specific device.
 */
std::optional<FullDeviceInfo> DeviceManager::get_device_info(uint64_t d_id) {
  LOG(level_E::INFO, "Fetching device info for ID: " + std::to_string(d_id));

  auto id_it = d_id_to_sc_id.find(d_id);
  if (id_it == d_id_to_sc_id.end()) {
    LOG(level_E::ERROR, "Invalid device_id: " + std::to_string(d_id));
    return std::nullopt;
  }

  const sc_id& scid = id_it->second;
  auto adapter_it = sc_id_to_adapter.find(scid);
  if (adapter_it == sc_id_to_adapter.end()) {
    LOG(level_E::ERROR, "No adapter mapped for sc_id: " + std::to_string(d_id));
    return std::nullopt;
  }

  CXLDeviceAdapter* adapter = adapter_it->second;
  try {
    const sc_device& dev = adapter->get_device_object(scid);
    return dev.to_device_info();
  } catch (const std::exception& ex) {
    LOG(level_E::ERROR,
        "Failed to retrieve device info: " + std::string(ex.what()));
    return std::nullopt;
  }
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
