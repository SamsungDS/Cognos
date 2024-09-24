#ifndef __CXL_PLUGIN_HOST_H__
#define __CXL_PLUGIN_HOST_H__

#include <cstddef>
#include <cstdint>
#include <list>
#include <string>

#include "sc_id.h"
#include "types.h"

/**
 * @brief Represents an application server.
 * @details Maintains information about an application server including its
 *          total memory capacity, upstream connected CXL switch ports, and
 *          corresponding connected CXL devices through downstream ports.
 */
class sc_host {
 public:
  sc_host();

  explicit sc_host(uint64_t ci);

  ~sc_host() = default;

  void set_host_name(std::string const& host);

  void set_host_port(uint64_t const& port);

  void set_capacity(uint64_t const& capacity);

  void set_target_ports(uint32_t const& tp);

  std::string get_host_name() const;

  uint64_t get_host_port() const;

  /**< Total memory capacity of this application server. */
  uint64_t get_capacity() const;

  uint64_t get_id() const;

  std::list<uint32_t> get_target_ports() const;

  /* get host id */
  sc_id d_get_id() const;

 private:
  /**< Application server connected to memory box */
  std::string h_name;

  /**
   * PCIe upstream port by which the application server is connected to
   * memory box
   */
  uint64_t h_port;

  /**< Host total memory capacity, including DRAM and CXL memory */
  uint64_t h_capacity{1};

  /**
   * A std::std::list of CXL memory modules connected to this host via
   * corresponding downstream PCIe ports
   */
  std::list<uint32_t> h_target_ports;

  /**< host id */
  sc_id h_id;
};

#endif
