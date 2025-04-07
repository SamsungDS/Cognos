#include "sc_dev_registry.h"

#include "sc_logger.h"

/**
 * @brief Retrieves the singleton instance of DeviceRegistry.
 */
DeviceRegistry& DeviceRegistry::getInstance() {
  static DeviceRegistry instance;
  return instance;
}

DeviceRegistry::~DeviceRegistry() {
  std::lock_guard<std::mutex> lock(registryMutex);
  for (auto& [name, adapter] : adapterMap) {
    delete adapter;
    LOG(level_E::INFO,
        "Adapter '" + name + "' deleted during registry cleanup.");
  }
  adapterMap.clear();
  LOG(level_E::INFO, "DeviceRegistry destroyed and cleaned up.");
}

/**
 * @brief Registers a new device adapter.
 */
void DeviceRegistry::registerAdapter(const std::string& name,
                                     CXLDeviceAdapter* adapter) {
  // Lock before modifying
  std::lock_guard<std::mutex> lock(registryMutex);
  adapterMap[name] = adapter;
  LOG(level_E::INFO, "Adapter '" + name + "' registered successfully.");
}

/**
 * @brief Unregisters a device adapter.
 */
void DeviceRegistry::unregisterAdapter(const std::string& name) {
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
CXLDeviceAdapter* DeviceRegistry::getAdapter(const std::string& name) {
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

/**
 * @brief Retrieves an adapter handling a specific device.
 */
CXLDeviceAdapter* DeviceRegistry::getAdapterForDevice(uint64_t d_id) {
  std::lock_guard<std::mutex> lock(registryMutex);
  for (const auto& pair : adapterMap) {
    if (pair.second->handlesDevice(d_id)) {
      return pair.second;
    }
  }
  return nullptr;
}

const std::unordered_map<std::string, CXLDeviceAdapter*>&
DeviceRegistry::get_adapters() {
  std::lock_guard<std::mutex> lock(registryMutex);
  return adapterMap;
}
