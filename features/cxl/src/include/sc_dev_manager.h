#ifndef DEVICE_MANAGER_H
#define DEVICE_MANAGER_H

#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>

#include "sc_cxl_dev_adapter.h"
#include "sc_device.h"
#include "sc_id.h"

class CXLDeviceAdapter;

/**
 * @class DeviceManager
 * @brief Singleton class responsible for managing device operations.
 *
 * The DeviceManager handles high-level device operations such as listing
 * devices, fetching device information, and performing attach/detach
 * operations. It interacts with the DeviceRegistry to manage and query
 * registered device adapters.
 **/
class DeviceManager {
 public:
  /**
   * @brief Constructs a DeviceManager instance for library use.
   */
  DeviceManager();

  /**
   * @brief Destructor for DeviceManager.
   */
  ~DeviceManager();

  /**
   * @brief Deleted copy constructor to prevent duplication.
   */
  DeviceManager(const DeviceManager&) = delete;

  /**
   * @brief Deleted assignment operator to prevent duplication.
   */
  DeviceManager& operator=(const DeviceManager&) = delete;

  /**
   * @brief Lists all registered devices.
   *
   * Overload: No parameters — returns all devices.
   * @return A vector of sc_device representing all discovered devices.
   */
  std::vector<sc_device> list_devices();

  /**
   * @brief Lists all registered devices with a filter on device IDs.
   *
   * Extracts device filter parameters, retrieves device lists from adapters,
   * and compiles a unified JSON response.
   *
   * @param[in] d_ids Set of device IDs to retrieve.
   * @return A vector of sc_device filtered by the given device IDs.
   */
  std::vector<sc_device> list_devices(
      const std::unordered_set<uint64_t>& d_ids);

  /**
   * @brief Retrieves detailed information about a specific device.
   *
   * @param[in] d_id Device ID.
   * @return DevInfo containing device info on success,
   * or if the device is not found an error occurs.
   */
  DevInfo get_device_info(uint64_t d_id);

  /**
   * @brief Retrieves runtime statistics for a specific device.
   *
   * For a given numeric device ID, this method resolves the internal sc_id,
   * identifies the corresponding adapter, and invokes its implementation of
   * get_device_stats(). This is typically used by APIs to retrieve real time
   * telemetry from the device (e.g bandwidth, memory usage, temperature).
   *
   * @param d_id device ID for which stats are requested.
   * @return StatInfo containing the device stats if successful,
   * or if the device is not found an error occurs.
   */
  StatInfo get_device_stats(uint64_t d_id);

  /**
   * @brief Retrieves real-time metrics information for a specific device.
   *
   * This method returns the metrics associated with the given device ID,
   * such as bandwidth, temperature, memory usage, and other telemetry stats.
   * It typically aggregates information from get_device_stats() &
   * get_device_info().
   *
   * @param d_id device ID for which stats are requested.
   * @return MetricsInfo structure containing the current metrics for the
   * device.
   * @throws std::runtime_error if the device is not found or metrics are
   * unavailable.
   */
  // MetricsInfo get_device_metrics(uint64_t d_id);

  /**
   * @brief Attaches the memory of a device to the local host.
   *
   * Resolves the owning adapter and invokes its attach_memory()
   * implementation. Adapters that do not support the operation return
   * -ENOTSUP.
   *
   * @param d_id Device ID.
   * @param params Attach parameters (requested mode).
   * @return 0 on success, -ENODEV if the device is unknown, or the negative
   * POSIX error code returned by the adapter.
   */
  int attach_memory(uint64_t d_id, const AttachParams& params) const;

  /**
   * @brief Detaches the memory of a device from the local host.
   *
   * @param d_id Device ID.
   * @return 0 on success, -ENODEV if the device is unknown, or the negative
   * POSIX error code returned by the adapter.
   */
  int detach_memory(uint64_t d_id) const;

  /**
   * @brief Performs a pool-level operation on a named adapter.
   *
   * On success the adapter is asked to rediscover its devices, so that pool
   * membership changes become visible.
   *
   * @param adapter_name Name the adapter was registered with.
   * @param op The pool operation.
   * @param params Operation parameters.
   * @return 0 on success, -ENODEV if the adapter is unknown, or the negative
   * POSIX error code returned by the adapter.
   */
  int pool_operation(const std::string& adapter_name, PoolOp op,
                     const PoolOpParams& params);

  /**
   * @brief Resolves a given device ID to its internal sc_id and associated
   * adapter.
   *
   * This utility is used by APIs like get_device_info() and get_device_stats()
   * to translate a 48-bit device ID to the corresponding internal `sc_id` and
   * `CXLDeviceAdapter*`. If the device ID is invalid or the adapter mapping
   * is missing, the function returns std::nullopt.
   *
   * @param d_id The 48-bit unique device identifier.
   * @return std::optional<std::pair<sc_id, CXLDeviceAdapter*>> containing the
   * resolved sc_id and adapter pointer if found; std::nullopt otherwise.
   */
  std::optional<std::pair<sc_id, CXLDeviceAdapter*>> resolve_adapter(
      uint64_t d_id) const;

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
   * @brief Retrieves a read-only reference to all registered adapters.
   *
   * This methid allows querying of all currently registered adapters.
   *
   * @return A const reference to adapter map (thread safe access).
   */
  const std::unordered_map<std::string, CXLDeviceAdapter*>& get_adapters();

  /**
   * @brief Registers a discovered device with the manager.
   *
   * This function is called by adapters during setup/discovery. It stores the
   * mapping between the device's sc_id and its owning adapter, and also maps
   * the numeric device_id for fast lookup.
   *
   * @param[in] id The device's sc_id (unique identifier).
   * @param[in] adapter Pointer to the owning CXL adapter.
   */
  void register_device(const sc_id& id, CXLDeviceAdapter* adapter);

  /**
   * @brief Unregisters all devices associated with a given adapter.
   *
   * This function is called when an adapter is unregistered or unloaded.
   * It ensures that all device-to-adapter mappings held by the DeviceManager
   * are also cleaned up to avoid dangling references.
   *
   * @param adapter Pointer to the adapter being unregistered.
   */
  void unregister_device(CXLDeviceAdapter* adapter);

  /**
   * @brief Triggers discovery or rediscovery of devices from all registered
   * adapters.
   *
   * This method is called during system startup or runtime hotplug detection.
   * It loops through all registered adapters and invokes their
   * discover_devices() method. Each adapter scans for connected hardware,
   * creates `sc_device` objects, and registers new devices with DeviceManager.
   * Already-known devices are skipped.
   */
  void discover_devices();

  // debug
  const std::unordered_map<uint64_t, sc_id>& get_d_id_map() const;
  const std::unordered_map<sc_id, CXLDeviceAdapter*, hash_sc_id>&
  get_sc_id_adapter_map() const;
  // debug

 private:
  /**
   * @brief Map storing registered adapters.
   */
  std::unordered_map<std::string, CXLDeviceAdapter*> adapterMap;

  /**
   * @brief Map storing id to id object
   */
  std::unordered_map<uint64_t, sc_id> d_id_to_sc_id;

  /**
   * @brief Map storing id object to adapter.
   */
  std::unordered_map<sc_id, CXLDeviceAdapter*, hash_sc_id> sc_id_to_adapter;
};

#endif
