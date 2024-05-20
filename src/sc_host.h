#ifndef __CXL_PLUGIN_HOST_H__
#define __CXL_PLUGIN_HOST_H__

#include "sc_device.h"
#include "sc_global.h"

using namespace std;

class sc_device;

/**
 * @brief Represents an application server.
 * @details Maintains information about an application server including its
 *          total memory capacity, upstream connected CXL switch ports, and
 *          corresponding connected CXL devices through downstream ports.
 */
class sc_host {
 public:
  sc_host();

  sc_host(uint64_t ci);

  ~sc_host();

  void set_host_name(string h_name);

  void set_host_port(uint64_t h_port);

  void set_capacity(uint64_t h_capacity);

  void set_target_ports(uint32_t tp);

  string get_host_name() const;

  uint32_t get_host_port();

  /**< Total memory capacity of this application server. */
  uint64_t get_capacity();

  uint64_t get_id();

  list<uint32_t>& get_target_ports();

  /* get host id */
  sc_id get_composite_obj();

 private:
  /**< Application server connected to memory box */
  string h_name;

  /**
   * PCIe upstream port by which the application server is connected to
   * memory box
   */
  uint32_t h_port;

  /**< Host total memory capacity, including DRAM and CXL memory */
  uint64_t h_capacity{1};

  /**
   * A list of CXL memory modules connected to this host via corresponding
   * downstream PCIe ports
   */
  list<uint32_t> target_ports;

  /**< free host memory */
  uint64_t h_free_memory{1};

  /**< host id */
  sc_id h_id;
};

#endif
