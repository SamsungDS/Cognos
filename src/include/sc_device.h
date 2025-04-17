#ifndef __CXL_PLUGIN_SC_DEVICES_H__
#define __CXL_PLUGIN_SC_DEVICES_H__
#define INVALID_DEV_PORT 0xFFFFFFFFU

#include <stdint.h>

#include <algorithm>
#include <cstring>
#include <iostream>
#include <list>
#include <string>
#include <unordered_map>
#include <vector>

#include "mbox_a1.h"
#include "sc_api_structs.h"
#include "sc_endpoint.h"
#include "sc_host.h"
#include "sc_id.h"
#include "sc_switch.h"
#include "types.h"

enum device_type { MBOX = 1, SLD = 2, MLD = 3, LD = 4, DCD = 5 };

class sc_host;

/**
 * @brief Device class
 * @details This class holds all device related information.
 */
class sc_device {
 public:
  sc_device();

  /**
   * @brief Device constructor.
   * @param sc_id device id.
   * @param d_name device name.
   * @param capacity device capacity.
   * @param port device port.
   */
  sc_device(uint64_t d_id, std::string d_name, uint64_t capacity,
            uint32_t port);

  virtual ~sc_device();

  /**
   * @brief Get total capacity of the device (MB).
   */
  virtual uint64_t d_get_capacity() const;

  /**
   * @brief get device name
   */
  virtual std::string d_get_dev_name() const;

  /**
   * @brief get device port.
   */
  virtual uint32_t d_get_port() const;

  /**
   * @brief set device port.
   */
  virtual void d_set_port(uint32_t port);

  /**
   * @brief set device capacity.
   */
  virtual void d_set_capacity(uint64_t capacity);

  /**
   * @brief set device name.
   */
  virtual void d_set_dev_name(std::string d_name);

  /*
   * @brief get parent sc_device.
   */
  sc_device* d_get_parent() const;

  /*
   * @brief set parent of this device.
   */
  void d_set_parent(sc_device* parent);

  /* get sc_id class object */
  virtual sc_id d_get_id() const;

  /**  
   * @brief Sets the static portion of the device info.  
   * Typically used during discovery/setup phase.  
   * @param static_info The DevStaticInfo struct to assign.  
   */
  void d_set_static_info(const DevStaticInfo& static_info);

  /**
   * @brief Sets the dynamic portion of the device info.
   * Should be used by adapters to update runtime/device state.
   * @param dynamic_info The dynamic fields (status, capacity, flags, etc.).
   */
  void d_set_dynamic_info(const DevInfo& dynamic_info);

  /**
   * @brief Returns a read-only reference to the full DevInfo.
   * Useful for internal reads and testing.
   * @return const DevInfo& - Reference to internal device info.
   */
  const DevInfo& d_get_info() const;

  /**
   * @brief Converts the internal sc_device object into a public-facing
   * DeviceInfo struct.
   *
   * This method is intended for library users who want structured access to
   * device attributes instead of raw JSON. The result can be converted to JSON
   * externally at the API/HTTP layer.
   *
   * @return A populated DeviceInfo struct representing this device.
   */
  DevInfo to_device_info() const;

 private:
  /*           8 bits                            56 bits
   *   +----------------------+----------------------------------------------+
   *   |     device type id   |                  device id                   |
   *   +----------------------+----------------------------------------------+
   */

  /**< Composition: sc_device has an instance of sc_id*/
  sc_id d_id;

  /**< device size */
  uint64_t d_capacity{1};

  /**< device free memory */
  uint64_t d_used_capacity{1};

  /**< device port */
  uint32_t d_port;

  /**< device name */
  std::string d_name;

  /**< device object */
  sc_device* d_parent;

  /**< simple class endpoint object */
  endpoint epobj;

  // holds both static and dynamic data for the device.
  DevInfo d_info;
};

#endif
