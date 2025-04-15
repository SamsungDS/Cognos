#ifndef SC_API_STRUCTS_H
#define SC_API_STRUCTS_H

#include <string>
#include <unordered_map>

struct QoSInfo {
double avg_latency = 0;
double p99_latency = 0;
double io_per_sec = 0;
double bw_per_sec = 0;
double io_size = 0;
double qd = 0;
};

struct Capabilities {
  uint32_t power_management_version = 0;
  std::unordered_map<std::string, std::string> vendor_specific;
};

struct FullDeviceInfo {
uint64_t id = 0;
std::string manufacturer;
std::string serial_number;
std::string fw_revision;
std::string location;
uint64_t total_capacity_MB = 0;
uint64_t available_capacity_MB = 0;
std::string status;
std::string feature_supported;
std::string device_type;
std::string cxl_type;
uint32_t domain_id = 0;
std::string domain_type;
std::string connection_type;
std::string mode_discovered;
std::string protocol;
bool aspm_active = false;
bool sris_active = false;
bool lock_active = false;
int link_speed = 0;
int link_width = 0;
std::string port_type;
int numa_attached = 0;
Capabilities capabilities;
QoSInfo advertized_qos;
};

#endif
