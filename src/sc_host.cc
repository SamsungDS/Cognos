#include "sc_host.h"
#include <stdexcept> 
#include <regex>

//constructor delegation 
sc_host::sc_host():sc_host(0){};

/**
* @brief creates a sc_host object with the given parameter.
* @details This constructor takes host id as parameter.
* @param ci client input host id.
*/
sc_host::sc_host(uint64_t ci): h_id(ci) {  }

sc_host::~sc_host(){}

/**
 * @brief set host name.
 * @param h_name host name.
*/
void sc_host::set_host_name(string h_name){  
    // Validate the hostname using a regular expression
    regex validHostname("^[A-Za-z0-9-.$]+$");
    if (regex_match(h_name, validHostname)) {
        this->h_name = h_name;
    } 
    else {
	throw std::invalid_argument("Invalid hostname: " + h_name);
    }
 
}

/**
 * @brief set host port.
 * @param h_port host port.
*/
void sc_host::set_host_port(uint64_t h_port){ 
    // Check if the port value is valid
    if (h_port < 0 || h_port > 65535) {
        throw std::invalid_argument("Invalid port value: " + std::to_string(h_port));
    }

    this->h_port=h_port; 
}

/**
 * @brief set host capacity.
 * @param h_capacity host capacity.
*/
void sc_host::set_capacity(uint64_t h_capacity){ 

    // Check if the capacit is an overflow
    if (h_capacity < 0 || h_capacity > 5024ull * 1024ull * 1024ull * 1024ull) {
        throw std::invalid_argument("over capacity: " + std::to_string(h_capacity));
    }
    this->h_capacity=h_capacity;

}

void sc_host::set_target_ports(uint32_t tp){ target_ports.push_back(tp); }

string sc_host::get_host_name() const { return h_name; }

uint32_t sc_host::get_host_port(){ return h_port; }

uint64_t sc_host::get_capacity() { return h_capacity; }

uint64_t sc_host::get_id(){ return h_id.get_sc_id(); }

sc_id sc_host::get_composite_obj() { return this->h_id; }

list<uint32_t>& sc_host::get_target_ports(){ return target_ports; } 

