#ifndef DEV_CMMH_H
#define DEV_CMMH_H

#include <unordered_map>

#include "sc_cxl_dev_adapter.h"
#include "sc_logger.h"

/**
 * @class DevCMMH
 * @brief CXL Adapter implementation for CMM-H devices.
 *
 * DevCMMH is a plugin that inherits from CXLDeviceAdapter. It manages CMM-H
 * class devices, maintains an internal map of discovered devices and provides
 * APIs for device enumeration, information access and discovery.
 */
class DevCMMH : public CXLDeviceAdapter {
 public:
  /**
   * @brief Constructor.
   */
  DevCMMH();

  /**
   * @brief Destructor — Cleans up resources.
   */
  ~DevCMMH() override;

  /**
   * @brief Returns a list of all devices discovered by this adapter.
   * @return Vector of sc_device objects.
   */
  std::vector<sc_device> list_devices() const override;

  /**
   * @brief Retrieves a specific device from the internal map.
   * @param sid The device identifier (sc_id).
   * @return The sc_device object if found, otherwise a default sc_device.
   */
  sc_device get_device_object(const sc_id& sid) const override;

  /**
   * @brief Returns the list of hosts.
   * @return Vector of sc_host objects.
   */
  std::vector<sc_host> list_hosts() override;

  /**
   * @brief Returns DevInfo structure for a given device.
   * @param sid The device identifier.
   * @return DevInfo struct, or empty if not found.
   */
  DevInfo get_device_info(const sc_id& sid) const override;

  /**
   * @brief Performs PCI-based discovery and populates device map.
   * @param mgr Reference to DeviceManager for device registration.
   */
  void discover_devices(DeviceManager& mgr) override;

  /**
   * @brief Initializes adapter configuration.
   * @return 0 on success.
   */
  int setup_info() override;

 private:
  /** Map of device ID to device object */
  std::unordered_map<sc_id, sc_device, hash_sc_id> device_map_;

  /** List of associated hosts (currently unused) */
  std::vector<sc_host> hosts_;
};

/**
 * @brief Plugin entry point called by PluginManager.
 *
 * This function creates and registers the DevCMMH adapter with the
 * DeviceManager.
 *
 * @param mgr Reference to DeviceManager for adapter registration.
 */
extern "C" void register_plugin(DeviceManager& mgr);

#endif
