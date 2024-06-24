#ifndef __CXL_PLUGIN_SC_DEVICES_H__
#define __CXL_PLUGIN_SC_DEVICES_H__
#define INVALID_DEV_PORT 0xFFFFFFFFU

#include <stdint.h>
#include <algorithm>
#include <cstring>
#include <iostream>
#include <string>
#include <list>
#include <unordered_map>
#include <vector>

#include "sc_endpoint.h"
#include "sc_host.h"
#include "sc_id.h"
#include "sc_switch.h"
#include "types.h"

#include "/opt/stg/mbox_a1.h"

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
   * @brief get device capacity.
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
  sc_device *d_get_parent() const;

  /*
   * @brief set parent of this device.
   */
  void d_set_parent(sc_device *parent);

  /* get sc_id class object */
  virtual sc_id d_get_id() const;

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
  sc_device *d_parent;

  /**< simple class endpoint object */
  endpoint epobj;
};

#endif

