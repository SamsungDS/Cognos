#ifndef SC_API_STRUCTS_H
#define SC_API_STRUCTS_H

#include <optional>
#include <string>
#include <unordered_map>

#if MOCK == 1
#include "mock_libcmmh.h"
#else
#include "libcmmh.h"
#endif

struct QoSInfo {
  uint64_t avg_latency_us = 0;
  uint64_t p99_latency_us = 0;
  uint64_t io_per_sec = 0;
  uint64_t bw_per_sec = 0;
  uint64_t io_size_in_bytes = 0;
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
  int link_speed_GT_s = 0;
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
  int numa_node = 0;
};

struct StatInfo {
  uint64_t device_id = 0;
  std::string protocol;
  std::string port_type;
  std::string status;
  uint64_t total_memory_MB = 0;
  uint64_t used_memory_MB = 0;
  uint64_t available_memory_MB = 0;
  uint64_t total_bandwidth_MBps = 0;
  uint64_t used_bandwidth_MBps = 0;
  uint64_t rw_errors = 0;
  uint64_t latency_us = 0;
  // Device-specific stats
  std::optional<cmmh_stat_sensor_t> sensor_stats;
  std::optional<cmmh_stat_interface_t> interface_stats;
  std::optional<cmmh_stat_cache_t> cache_stats;
};

/**
 * @brief Device configuration parsed from JSON.
 *
 * This struct holds device attributes from the config/cxl_dev_id_map.json file.
 * It is used in real mode to augment discovered hardware information with
 * additional configuration metadata such as link parameters, vendor info,
 * protocol and QoS.
 */
struct DevJsonHints {
  std::string vendor_device_type;
  int lane_speed_GT_s;
  int lane_width;
  std::string manufacturer;
  uint64_t serial_number;
  std::string fw_revision;
  std::string feature_supported;
  std::string cxl_device_type;
  std::string domain_type;
  std::string connection_type;
  std::string mode_discovered;
  std::string protocol;
  std::string port_type;
  std::string status;
  Capabilities capabilities;
  QoSInfo advertised_qos;
};

/**
 * @struct MetricsInfo
 * @brief Holds metadata and observation values for a CXL device's runtime
 * metrics. This structure encapsulates both metadata (e.g. domain, severity,
 * source) and observation metrics (e.g. memory usage, bandwidth, temperature)
 * for reporting device health and performance.
 */
struct MetricsInfo {
  std::string domain;
  uint32_t feature_id;
  std::string category;
  std::string severity;
  // source ID of the metric, can refer to device ID or other context
  uint64_t source;
  // source of the event belongs to e.g device, node, application & cluster
  std::string source_type;
  /** PCIe power states for managing its power consumption.
      L0 (Active State) - normal operating mode where the device is fully active
     and functioning, consuming the most power. L0s (L0 Standby) a low-power
     standby state that allows for fast recovery back to the L0 state. L1 (L1
     Standby) a deeper low-power standby state compared to L0s L2 (L2 Standby)
     an auxiliary-powered deep-energy-saving state. L3 (Link Off) deepest power
     state where the link is completely powered off. */
  std::string power_state;
  uint64_t timestamp;
  // sampling interval for metrics publisher
  int interval_seconds;

  // Observations
  uint64_t temperature;
  int numa_node;
  uint64_t total_memory;
  uint64_t used_memory;
  uint64_t available_memory;
  uint64_t total_bandwidth;
  uint64_t used_bandwidth;
  uint64_t cache_hit_perc;
  uint64_t dirty_cache_gb;
};
#endif
