#ifndef __CXL_PLUGIN_SWITCH_H__
#define __CXL_PLUGIN_SWITCH_H__

#include <stdint.h>

#include <iostream>
#include <sstream>
#include <string>

#include "sc_id.h"

/**
 * @brief switch class.
 * @details This class holds switch related information.
 */
class sc_switch {
 public:
  sc_switch();

  /**
   * @brief parameterized switch constructor.
   * @details This constructor takes s_id as parameter.
   */
  sc_switch(uint64_t sc_id);

  ~sc_switch();

  void set_manufacturer(const std::string& manufacturer);
  void set_upstream_ports(uint32_t num_ports);
  void set_downstream_ports(uint32_t num_ports);
  void set_mgmt_port(uint32_t port);

  const std::string& get_manufacturer() const;
  uint32_t get_upstream_ports() const;
  uint32_t get_downstream_ports() const;
  uint32_t get_mgmt_port() const;

  /**
   * @brief get switch information
   */
  std::string to_json();

 private:
  /**< switch id.*/
  sc_id s_id;

  /**< switch manufacturer.*/
  std::string s_manufacturer;

  /**< number of upstream ports.*/
  uint32_t s_nr_upstream_ports{0};

  /**< number of downstream ports.*/
  uint32_t s_nr_downstream_ports{0};

  /**< switch management port.*/
  uint32_t s_mgmt_port{0};

  /* switch features - TBD */
};

#endif
