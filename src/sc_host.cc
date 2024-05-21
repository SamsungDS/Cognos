#include "sc_host.h"

#include <regex>
#include <stdexcept>

using namespace std;

// constructor delegation
sc_host::sc_host() : sc_host(0){};

/**
 * @brief creates a sc_host object with the given parameter.
 * @details This constructor takes host id as parameter.
 * @param ci client input host id.
 */
sc_host::sc_host(uint64_t ci) : h_id(ci) {}

/**
 * @brief set host name.
 * @param h_name host name.
 */
void sc_host::set_host_name(string const& host) {
  // Validate the hostname using a regular expression
  regex validHostname("^[A-Za-z0-9-.$]+$");
  if (regex_match(host, validHostname)) {
    h_name = host;
  } else {
    throw std::invalid_argument("Invalid hostname: " + host);
  }
}

/**
 * @brief set host port.
 * @param h_port host port.
 */
void sc_host::set_host_port(uint64_t const& port) {
  // Check if the port value is valid
  if (port < 0 || port > 65535) {
    throw std::invalid_argument("Invalid port value: " + std::to_string(port));
  }

  h_port = port;
}

/**
 * @brief set host capacity.
 * @param h_capacity host capacity.
 */
void sc_host::set_capacity(uint64_t const& capacity) {
  // Check if the capacit is an overflow
  if (capacity < 0 || capacity > 5024ull * 1024ull * 1024ull * 1024ull) {
    throw std::invalid_argument("over capacity: " + std::to_string(capacity));
  }
  this->h_capacity = capacity;
}

void sc_host::set_target_ports(uint32_t const& tp) {
  target_ports.push_back(tp);
}

string sc_host::get_host_name() const { return h_name; }

uint32_t sc_host::get_host_port() const { return h_port; }

uint64_t sc_host::get_capacity() const { return h_capacity; }

uint64_t sc_host::get_id() const { return h_id.get_sc_id(); }

sc_id sc_host::get_composite_obj() const { return this->h_id; }

list<uint32_t> sc_host::get_target_ports() const { return target_ports; }
