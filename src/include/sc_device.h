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
   * @brief Get available (free) capacity (MB).
   */
  virtual uint64_t d_get_available_capacity();

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
   * @brief set used device capacity.
   */
  virtual void d_set_used_capacity(uint64_t used_capacity); 

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

  /** @brief Set device manufacturer string */
  void d_set_manufacturer(const std::string& mfg);

  /** @brief Get device manufacturer string */
  std::string d_get_manufacturer() const;

  /** @brief Set device serial number */
  void d_set_serial_number(const uint64_t sn);

  /** @brief Get device serial number */
  uint64_t d_get_serial_number() const;

  /** @brief Set firmware revision */
  void d_set_fw_revision(const std::string& rev);

  /** @brief Get firmware revision */
  std::string d_get_fw_revision() const;

  /** @brief Set PCIe location string */
  void d_set_location(const std::string& loc);

  /** @brief Get PCIe location string */
  std::string d_get_location() const;

  /** @brief Set device status. */
  void d_set_status(const std::string& val);

  /** @brief Get device status. */
  std::string d_get_status() const;

  /** @brief Set supported feature (e.g., SLD/MLD). */
  void d_set_feature_supported(const std::string& val);

  /** @brief Get supported feature. */
  std::string d_get_feature_supported() const;

  /** @brief Set device type (e.g., cmmb). */
  void d_set_device_type(const std::string& val);

  /** @brief Get device type. */
  std::string d_get_device_type() const;

  /** @brief Set CXL type or HBM. */
  void d_set_cxl_type(const std::string& val);

  /** @brief Get CXL type. */
  std::string d_get_cxl_type() const;

  /** @brief Set domain ID. */
  void d_set_domain_id(uint32_t val);

  /** @brief Get domain ID. */
  uint32_t d_get_domain_id() const;

  /** @brief Set domain type (pooled/direct). */
  void d_set_domain_type(const std::string& val);

  /** @brief Set domain type. */
  std::string d_get_domain_type() const;

  /** @brief Set connection type (local/remote). */
  void d_set_connection_type(const std::string& val);

  /** @brief Get connection type. */
  std::string d_get_connection_type() const;

  /** @brief Set mode discovered (system-mem/dax). */
  void d_set_mode_discovered(const std::string& val);

  /** @brief Get mode discovered. */
  std::string d_get_mode_discovered() const;

  /** @brief Set CXL protocol version. */
  void d_set_protocol_version(const std::string& val);

  /** @brief Get CXL protocol version. */
  std::string d_get_protocol_version() const;

  /** @brief Set ASPM flag. */
  void d_set_aspm_active(bool val);

  /** @brief Get ASPM flag. */
  bool d_get_aspm_active() const;

  /** @brief Set SRIS flag. */
  void d_set_sris_active(bool val);

  /** @brief Get SRIS flag. */
  bool d_get_sris_active() const;

  /** @brief Set lock flag. */
  void d_set_lock_active(bool val);

  /** @brief Get lock flag. */
  bool d_get_lock_active() const;

  /** @brief Set link speed */
  void d_set_link_speed(uint32_t speed);

  /** @brief Get link speed */
  uint32_t d_get_link_speed() const;

  /** @brief Set link width. */
  void d_set_link_width(uint32_t val);

  /** @brief Get link width */
  uint32_t d_get_link_width() const;

  /** @brief Set port type. */
  void d_set_port_type(const std::string& val);

  /** @brief Get device port type */
  std::string d_get_port_type() const;

  /** @brief Set NUMA info. */
  void d_set_numa_attached(uint32_t val);

  /** @brief Get numa attached */
  uint32_t d_get_numa_attached() const;

  /** @brief Set QoS parameter (e.g., avg_latency, io_per_sec) */
  void d_set_qos_info(const QoSInfo& qos);

  /** @brief Get all QoS parameters */
  const QoSInfo& d_get_qos_info() const;

  /** @brief Set capabilities parameter (e.g., power_management) */
  void d_set_capabilities(const Capabilities cap);

  /** @brief Get the full capability */
  const Capabilities& d_get_capabilities() const;

  /** @brief Set PCIe address */
  void d_set_pcie_addr(const std::string& addr);

  /** @brief Get PCIe address */
  const std::string& d_get_pcie_addr() const;

  /** @brief Set device type (e.g., MBOX, SLD, MLD) */
  void d_set_type(device_type type);

  /** @brief Get device type */
  device_type d_get_type() const;

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

  // New Attributes
  device_type d_type;
  std::string d_pcie_address;
  std::string d_manufacturer = "Samsung";
  uint64_t d_serial_number;
  std::string d_fw_revision;
  std::string d_location;
  std::string d_status = "active";
  std::string d_feature_supported;
  std::string d_device_type;
  std::string d_cxl_type;
  uint64_t d_domain_id{0};
  std::string d_domain_type;
  std::string d_connection_type;
  std::string d_mode_discovered;
  std::string d_protocol;
  bool d_aspm_active = true;
  bool d_sris_active = true;
  bool d_lock_active = true;
  uint32_t d_link_speed{0};
  uint32_t d_link_width{0};
  std::string d_port_type;
  uint32_t d_numa_attached{0};

  Capabilities d_cap_info;
  QoSInfo d_qos_info;
};

#endif
