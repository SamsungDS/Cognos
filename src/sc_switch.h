#ifndef __CXL_PLUGIN_SWITCH_H__
#define __CXL_PLUGIN_SWITCH_H__

#include <stdint.h>

#include <iostream>
#include <sstream>
#include <string>

#include "sc_id.h"

using namespace std;

/**
 * @brief switch class.
 * @details This class holds switch related information.
 */
class sc_switch {
 public:
  sc_switch() : sc_switch(0){};
  /**
   * @brief parameterized switch constructor.
   * @details This constructor takes s_id as parameter.
   */
  sc_switch(uint64_t sc_id) : s_id(sc_id) {}

  ~sc_switch() {}

  /**
   * @brief get switch information
   */
  string s_get_info() {
    // Create a stringstream to build the JSON-like string
    stringstream json;

    // Start the JSON object
    json << "{\n";

    // Add each member's information as key-value pairs
    json << "  \"SwitchID\": " << s_id.get_sc_id() << ",\n";
    json << "  \"Manufacturer\": \"" << s_manufacturer << "\",\n";
    json << "  \"UpstreamPorts\": " << s_nr_upstream_ports << ",\n";
    json << "  \"DownstreamPorts\": " << s_nr_downstream_ports << ",\n";
    json << "  \"ManagementPort\": " << s_mgmt_port << "\n";

    // End the JSON object
    json << "}";

    // Convert the stringstream to a string
    return json.str();
  }

 private:
  sc_id s_id;                        /**< switch id.*/
  char s_manufacturer[1024]{};       /**< switch manufacturer.*/
  uint32_t s_nr_upstream_ports{0};   /**< number of upstream ports.*/
  uint32_t s_nr_downstream_ports{0}; /**< number of downstream ports.*/
  uint32_t s_mgmt_port{0};           /**< switch management port.*/
                                     /* switch features - TBD */
};

#endif
