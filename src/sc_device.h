#ifndef __CXL_PLUGIN_SC_DEVICES_H__
#define __CXL_PLUGIN_SC_DEVICES_H__
#define MAX_DEV_NAME_LEN 1024
#define INVALID_DEV_PORT 0xFFFFFFFFU

#include <stdint.h>

#include <algorithm>
#include <cstring>
#include <iostream>
#include <list>
#include <string>
#include <unordered_map>
#include <vector>

#include "sc_endpoint.h"
#include "sc_host.h"
#include "sc_id.h"
#include "sc_switch.h"
#include "types.h"

using namespace std;

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
  sc_device(uint64_t d_id, const char *d_name, uint64_t capacity,
            uint32_t port);

  virtual ~sc_device();

  /**
   * @brief get device ID from sc_id class.
   */
  virtual uint64_t d_get_id();

  /**
   * @brief get device capacity.
   */
  virtual uint64_t d_get_capacity() const;

  /**
   * @brief get device name
   */
  virtual const char *d_get_dev_name();

  /**
   * @brief get device port.
   */
  virtual uint32_t d_get_port();

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
  virtual void d_set_dev_name(const char *d_name);

  /*
   * @brief get parent sc_device.
   */
  sc_device *d_get_parent();

  /*
   * @brief set parent of this device.
   */
  void d_set_parent(sc_device *parent);

  /* get sc_id class object */
  virtual sc_id get_composite_obj();

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
  char d_name[MAX_DEV_NAME_LEN];

  /**< device object */
  sc_device *d_parent;

  /**< simple class endpoint object */
  endpoint epobj;
};

#endif
