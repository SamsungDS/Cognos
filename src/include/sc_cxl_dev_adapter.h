#ifndef CXL_DEVICE_ADAPTER_H
#define CXL_DEVICE_ADAPTER_H

#include <error.h>

#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include "sc_device.h"
#include "sc_host.h"
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
   * @brief Retrieve the list of hosts managed by this adapter.
   *
   * @return Vector of sc_host objects.
   */
  virtual std::vector<sc_host> list_hosts() = 0;

  /**
   * @brief Get the internal sc_device object for the given device ID.
   * @param sid The sc_id of the device.
   * @return Reference to the internal sc_device object.
   * @throws std::runtime_error if device is not found.
   */
  virtual const sc_device& get_device_info(const sc_id& sid) const = 0;

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
