#include "sc_host.h"

#include <regex>
#include <stdexcept>

#include "sc_logger.h"

using namespace std;

// constructor delegation
sc_host::sc_host() : sc_host(0) {
  LOG(level_E::INFO, "sc_host object created with default constructor.");
};

/**
 * @brief creates a sc_host object with the given parameter.
 * @details This constructor takes host id as parameter.
 * @param ci client input host id.
 */
sc_host::sc_host(uint64_t ci) : h_id(ci) {
  LOG(level_E::INFO, "sc_host object created with ID: " + std::to_string(ci));
}

/**
 * @brief set host name.
 * @param h_name host name.
 */
void sc_host::set_host_name(string const& host) {
  LOG(level_E::INFO, "Setting host name: " + host);
  // Validate the hostname using a regular expression
  regex validHostname("^[A-Za-z0-9- .$]+$");
  if (regex_match(host, validHostname)) {
    h_name = host;
    LOG(level_E::INFO, "Host name set successfully: " + host);
  } else {
    LOG(level_E::ERROR, "Invalid hostname provided: " + host);
    throw std::invalid_argument("Invalid hostname: " + host);
  }
}

/**
 * @brief set host port.
 * @param h_port host port.
 */
void sc_host::set_host_port(uint64_t const& port) {
  LOG(level_E::INFO, "Setting host port: " + std::to_string(port));
  // Check if the port value is valid
  if (port > 65535) {
    LOG(level_E::ERROR, "Invalid port value: " + std::to_string(port));
    throw std::invalid_argument("Invalid port value: " + std::to_string(port));
  }

  h_port = port;
  LOG(level_E::INFO, "Host port set successfully: " + std::to_string(port));
}

/**
 * @brief set host capacity.
 * @param h_capacity host capacity.
 */
void sc_host::set_capacity(uint64_t const& capacity) {
  LOG(level_E::INFO, "Setting host capacity: " + std::to_string(capacity));
  // Check if the capacit is an overflow
  if (capacity > 5024ull * 1024ull * 1024ull * 1024ull) {
    LOG(level_E::ERROR, "Over capacity: " + std::to_string(capacity));
    throw std::invalid_argument("over capacity: " + std::to_string(capacity));
  }
  h_capacity = capacity;
  LOG(level_E::INFO,
      "Host capacity set successfully: " + std::to_string(capacity));
}

void sc_host::set_target_ports(uint32_t const& tp) {
  LOG(level_E::INFO, "Adding target port: " + std::to_string(tp));
  h_target_ports.push_back(tp);
}

string sc_host::get_host_name() const {
  LOG(level_E::INFO, "Retrieving host name: " + h_name);
  return h_name;
}

uint64_t sc_host::get_host_port() const {
  LOG(level_E::INFO, "Retrieving host port: " + std::to_string(h_port));
  return h_port;
}

uint64_t sc_host::get_capacity() const {
  LOG(level_E::INFO, "Retrieving host capacity: " + std::to_string(h_capacity));
  return h_capacity;
}

uint64_t sc_host::get_id() const {
  LOG(level_E::INFO, "Retrieving host ID: " + std::to_string(h_id.get_sc_id()));
  return h_id.get_sc_id();
}

sc_id sc_host::d_get_id() const {
  LOG(level_E::INFO, "Retrieving d_get_id() - host ID.");
  return h_id;
}

list<uint32_t>& sc_host::get_target_ports() {
  LOG(level_E::INFO, "Retrieving target ports list.");
  return h_target_ports;
}
