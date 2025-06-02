#ifndef SC_API_STRUCTS_H
#define SC_API_STRUCTS_H

#include <string>
#include <unordered_map>

struct QoSInfo {
  uint64_t avg_latency = 0;
  uint64_t p99_latency = 0;
  uint64_t io_per_sec = 0;
  uint64_t bw_per_sec = 0;
  uint64_t io_size = 0;
  uint64_t qd = 0;
};

struct Capabilities {
  uint32_t power_management_version = 0;
  std::unordered_map<std::string, std::string> vendor_specific;
};

struct DevStaticInfo {
  uint64_t device_id = 0;
  std::string manufacturer;
  uint64_t serial_number;
  std::string fw_revision;
  std::string location;
  uint64_t total_capacity_MB = 0;
  std::string feature_supported;
  std::string vendor_device_type;
  std::string cxl_device_type;
  uint32_t domain_id = 0;
  std::string domain_type;
  std::string connection_type;
  std::string mode_discovered;
  std::string protocol;
  int link_speed = 0;
  int link_width = 0;
  std::string port_type;
  Capabilities capabilities;
  QoSInfo advertised_qos;
};

// Full Device Info Struct (Static + Dynamic)
struct DevInfo {
  DevStaticInfo static_info;
  bool aspm_active = false;
  bool sris_active = false;
  bool lock_active = false;
  uint64_t available_capacity_MB = 0;
  std::string status;
  int numa_attached = 0;
};

#endif
