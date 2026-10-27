#ifndef CXL_DEVICE_ADAPTER_H
#define CXL_DEVICE_ADAPTER_H

#include <error.h>

#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include "sc_dev_manager.h"
#include "sc_device.h"
#include "sc_host.h"
#include "sc_id.h"

class DeviceManager;

/**
 * @class CXLDeviceAdapter
 * @brief Abstract Base Class for CXL Device Adapters (DevCMMB, DevCMMD,
 * DevCMMH)
 */
class CXLDeviceAdapter {
 public:
  virtual ~CXLDeviceAdapter() = default;

  /**
   * @brief Lists all devices managed by this adapter(unfiltered).
   * This is typically used for full discovery (no filter).
   * @return Vector of sc_device objects.
   */
  virtual std::vector<sc_device> list_devices() const { return {}; }

  /**
   * @brief Retrieves a specific device object by its sc_id.
   *
   * This method is used to fetch a single `sc_device` instance managed by the
   * adapter, based on the provided `sc_id`. Implementing adapters must maintain
   * an internal map or container of devices and return a copy of the matching
   * device.
   *
   * @param sid The system-composed identifier of the device to retrieve.
   * @return A copy of the matching `sc_device` object.
   */
  virtual sc_device get_device_object(const sc_id& sid) const = 0;

  /**
   * @brief Retrieves the full DevInfo (static + dynamic fields) for a given
   * device.
   *
   * This method is typically used during runtime by the Servicer layer or a
   * library  to provide detailed information about a specific device, including
   * its status, available capacity, and operational flags. The static portion
   * (e.g., manufacturer, domain ID) is embedded inside the returned DevInfo
   * struct.
   *
   * @param sid The sc_id object representing the unique device ID.
   * @return A DevInfo struct containing both static and dynamic metadata for
   * the device.
   */
  virtual DevInfo get_device_info(const sc_id& sid) const = 0;

  /**
   * @brief Retrieves runtime stats for a specific device.
   *
   * This method returns dynamic statistics of the device, such as memory usage,
   * bandwidth, error count, latency, and device-specific metrics like
   * temperature and cache hit rates. Implementations typically query
   * hardware-specific APIs like libcmmh to populate this data.
   *
   * @param sid The sc_id object representing the unique device ID.
   * @return StatInfo structure containing runtime stats and optional
   * subcomponents.
   */
  virtual StatInfo get_device_stats(const sc_id& sid) const = 0;

  /**
   * @brief Performs device discovery using PCI or other mechanisms and
   * registers new devices.
   *
   * Called by `DeviceManager::discover_devices()` either during system boot or
   * later rediscovery cycles. The adapter is responsible for:
   * 1. Scanning connected hardware (e.g., using libpci),
   * 2. Building `sc_device` objects with appropriate DevInfo structs,
   * 3. Calling `DeviceManager::register_device()` for newly discovered devices
   * only.
   *
   * @param mgr Reference to the DeviceManager that owns device registration
   * logic.
   */
  virtual void discover_devices(DeviceManager& mgr) = 0;

  /**
   * @brief Initialize the adapter and load necessary configurations.
   *
   * @return Status code (0 for success, negative for error).
   */
  virtual int setup_info() = 0;

  /**
   * @brief Retrieve the list of hosts managed by this adapter.
   *
   * @return Vector of sc_host objects.
   */
  std::vector<sc_host> list_hosts() const;

 protected:
  /** Map of device ID to device object */
  std::unordered_map<sc_id, sc_device, hash_sc_id> device_map_;

  /** List of associated hosts (currently unused) */
  std::vector<sc_host> hosts_;
};
#endif
