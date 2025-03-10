#ifndef CXL_DEVICE_ADAPTER_H
#define CXL_DEVICE_ADAPTER_H

#include <error.h>

#include <string>
#include <unordered_set>
/**
 * @class CXLDeviceAdapter
 * @brief Abstract Base Class for CXL Device Adapters (DevCMMB, DevCMMD,
 * DevCMMH)
 */
class CXLDeviceAdapter {
 public:
  virtual ~CXLDeviceAdapter() = default;
  /**
   * @brief Retrieve the list of devices managed by this adapter, filtered if
   * necessary.
   *
   * @param[in] dev_ids_out Set of device id's to filter (empty set means return
   * all devices).
   * @param[out] buffer JSON-formatted device list.
   * @return int success or posix error code.
   */
  virtual int list_devices(const std::unordered_set<uint64_t>& dev_ids_out,
                           std::string& buffer) = 0;

  /**
   * @brief Retrieve the list of hosts managed by this adapter.
   *
   * @param[out] buffer JSON-formatted host list.
   * @return Number of bytes written.
   */
  virtual int list_hosts(std::string& buffer) = 0;

  /**
   * @brief Fetch detailed information about a specific device.
   *
   * @param[in] d_id The ID of the device.
   * @param[out] buffer JSON-formatted device info.
   * @return Number of bytes written.
   */
  virtual int get_device_info(uint64_t d_id, std::string& buffer) = 0;

  /**
   * @brief Attach a device to a host (only applicable for CMMB).
   *
   * @param[in] d_id The ID of the device.
   * @param[in] h_id The ID of the host.
   * @param[out] buffer JSON-formatted response.
   * @return Status code (0 for success, negative for error).
   */
  virtual int attach_memory(uint64_t d_id, uint64_t h_id, std::string& buffer) {
    return -EPERM;
  }

  /**
   * @brief Detach a device from a host (only applicable for CMMB).
   *
   * @param[in] d_id The ID of the device.
   * @param[in] h_id The ID of the host.
   * @param[out] buffer JSON-formatted response.
   * @return Status code (0 for success, negative for error).
   */
  virtual int detach_memory(uint64_t d_id, uint64_t h_id, std::string& buffer) {
    return -EPERM;
  }

  /**
   * @brief Initialize the adapter and load necessary configurations.
   *
   * @return Status code (0 for success, negative for error).
   */
  virtual int setup_info() = 0;

  /**
   * @brief Checks if this adapter manages a specific device.
   *
   * @param[in] d_id The device identifier.
   * @return True if this adapter handles the device, false otherwise.
   */
  virtual bool handlesDevice(uint64_t d_id) const = 0;
};
#endif
