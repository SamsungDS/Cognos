#ifndef DEVICE_REGISTRY_H
#define DEVICE_REGISTRY_H

#include <mutex>
#include <unordered_map>

#include "sc_cxl_dev_adapter.h"

/**
 * @class DeviceRegistry
 * @brief Singleton class responsible for managing device adapters.
 *
 * The DeviceRegistry maintains a mapping between adapter names and their
 * corresponding instances. It provides methods to register, unregister, and
 * retrieve device adapters. Thread safety is ensured using a mutex.
 */
class DeviceRegistry {
 public:
  /**
   * @brief Gets the singleton instance of DeviceRegistry.
   *
   * Ensures a single instance of the registry exists across the application.
   *
   * @return Reference to the singleton instance.
   */
  static DeviceRegistry& getInstance();

  DeviceRegistry() = default;

  // Prevent copying
  DeviceRegistry(const DeviceRegistry&) = delete;
  DeviceRegistry& operator=(const DeviceRegistry&) = delete;

  /**
   * @brief Destructor for DeviceRegistry. Cleans up all adapter objects.
   */
  ~DeviceRegistry();

  /**
   * @brief Registers a new device adapter.
   *
   * Adds the specified adapter to the internal mapping.
   *
   * @param[in] name Name of the adapter.
   * @param[in] adapter Pointer to the CXLDeviceAdapter instance.
   */
  void registerAdapter(const std::string& name, CXLDeviceAdapter* adapter);

  /**
   * @brief Unregisters a device adapter.
   *
   * Removes the adapter entry from the registry.
   *
   * @param[in] name Name of the adapter to be unregistered.
   */
  void unregisterAdapter(const std::string& name);

  /**
   * @brief Retrieves an adapter by its name.
   *
   * Searches for an adapter registered under the given name.
   *
   * @param[in] name Name of the adapter.
   * @return Pointer to the CXLDeviceAdapter if found, otherwise nullptr.
   */
  CXLDeviceAdapter* getAdapter(const std::string& name);

  /**
   * @brief Retrieves an adapter associated with a specific device ID.
   *
   * Finds the adapter responsible for handling the given device.
   * if no adapter is found, `nullptr` is returned.
   *
   * @param[in] device_id The unique device identifier.
   * @return Pointer to the CXLDeviceAdapter handling the given device.
   */
  CXLDeviceAdapter* getAdapterForDevice(uint64_t device_id);

  /**
   * @brief Retrieves a read-only reference to all registered adapters.
   *
   * This methid allows querying of all currently registered adapters.
   *
   * @return A const reference to adapter map (thread safe access).
   */
  const std::unordered_map<std::string, CXLDeviceAdapter*>& get_adapters();

 private:
  /**
   * @brief Map storing registered adapters.
   */
  std::unordered_map<std::string, CXLDeviceAdapter*> adapterMap;

  /**
   * @brief Mutex for thread-safe access.
   */
  std::mutex registryMutex;
};

#endif
