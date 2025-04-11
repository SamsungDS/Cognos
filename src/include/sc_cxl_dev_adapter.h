#ifndef CXL_DEVICE_ADAPTER_H
#define CXL_DEVICE_ADAPTER_H

#include <error.h>

#include <string>
#include <unordered_set>

#include "sc_id.h"

/**
 * @class CXLDeviceAdapter
 * @brief Abstract Base Class for CXL Device Adapters (DevCMMB, DevCMMD,
 * DevCMMH)
 */
class CXLDeviceAdapter {
 public:
  virtual ~CXLDeviceAdapter() = default;

  /**
   * @brief Lists all devices managed by this adapter.
   *
   * This optional overload is used when the caller wants to retrieve all
   * devices from the adapter without applying any filter (e.g., in cases where
   * the DeviceManager is iterating over all adapters without device ID
   * filtering).
   *
   * Not all adapters may support unfiltered listing. By default, this method
   * returns `-ENOTSUP`, indicating the operation is not supported unless
   * overridden by the adapter.
   *
   * @param[out] buffer A JSON-formatted string containing the list of devices.
   * @return 0 on success, or a negative POSIX error code (e.g., -ENOTSUP).
   */
  virtual int list_devices(std::string& buffer) { return -ENOTSUP; }

  /**
   * @brief Retrieve the list of devices managed by this adapter, filtered if
   * necessary.
   *
   * @param[in] sc_id object, encapsulated device id.
   * @param[out] buffer JSON-formatted device list.
   * @return int success or posix error code.
   */
  virtual int list_devices(const sc_id& sid, std::string& buffer) = 0;

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
   * @param[in] sid sc_id object.
   * @param[out] buffer JSON-formatted device info.
   * @return Number of bytes written.
   */
  virtual int get_device_info(const sc_id& sid, std::string& buffer) = 0;

  /**
   * @brief Attach a device to a host (only applicable for CMMB).
   *
   * @param[in] d_id encapsulated ID of the device - sc_id object.
   * @param[in] h_id encapsulated ID of the host - sc_id object.
   * @param[out] buffer JSON-formatted response.
   * @return Status code (0 for success, negative for error).
   */
  virtual int attach_memory(const sc_id& d_id, const sc_id& h_id,
                            std::string& buffer) {
    return -EPERM;
  }

  /**
   * @brief Detach a device from a host (only applicable for CMMB).
   *
   * @param[in] d_id encapsulated ID of the device - sc_id object.
   * @param[in] h_id encapsulated ID of the host - sc_id object.
   * @param[out] buffer JSON-formatted response.
   * @return Status code (0 for success, negative for error).
   */
  virtual int detach_memory(const sc_id& d_id, const sc_id& h_id,
                            std::string& buffer) {
    return -EPERM;
  }

  /**
   * @brief Initialize the adapter and load necessary configurations.
   *
   * @return Status code (0 for success, negative for error).
   */
  virtual int setup_info() = 0;
};
#endif
