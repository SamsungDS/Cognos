#include "mock_cmmh.h"

#include <string>

#include "sc_logger.h"

MockCMMH::MockCMMH() = default;
MockCMMH::~MockCMMH() = default;
// MockCMMH::~MockCMMH() {
//   LOG(level_E::INFO, "MockCMMH destructor called");
// }

std::vector<sc_device> MockCMMH::list_devices() const {
  std::vector<sc_device> result;
  for (const auto& [sid, dev] : device_map_) {
    result.push_back(dev);
  }
  return result;
}

DevInfo MockCMMH::get_device_info(const sc_id& sid) const {
  auto it = device_map_.find(sid);
  if (it != device_map_.end()) {
    return it->second.d_get_info();
  }
  throw std::runtime_error("MockCMMH: device info not found for sid=" +
                           std::to_string(sid.get_sc_id()));
}

StatInfo MockCMMH::get_device_stats(const sc_id& sid) const {
  auto it = stats_map_.find(sid);
  if (it != stats_map_.end()) {
    return it->second;
  }
  throw std::runtime_error("MockCMMH: device stats not found for sid=" +
                           std::to_string(sid.get_sc_id()));
}

void MockCMMH::discover_devices(DeviceManager& mgr) {
  static const uint64_t MOCK_DEVICE_ID = 0x1E3A5B7CDE00;
  sc_id sid(MOCK_DEVICE_ID);

  DevStaticInfo static_info;
  static_info.device_id = MOCK_DEVICE_ID;
  static_info.manufacturer = "Mock";
  static_info.serial_number = 123456789;
  static_info.fw_revision = "0.1.2-mock";
  static_info.location = "mock-bus:00:1f.0";
  static_info.total_capacity_MB = 8192;
  static_info.feature_supported = "bandwidth_monitoring, temperature";
  static_info.vendor_device_type = "Mock";
  static_info.cxl_device_type = "Type3";
  static_info.domain_id = 100;
  static_info.domain_type = "virtual";
  static_info.connection_type = "PCIe";
  static_info.mode_discovered = "x16";
  static_info.protocol = "CXL";
  static_info.link_speed = 32;
  static_info.link_width = 8;
  static_info.port_type = "Upstream";
  static_info.capabilities.power_management_version = 1;
  static_info.advertised_qos = QoSInfo{100, 250, 5000, 1200, 4096, 16};

  DevInfo dev_info;
  dev_info.static_info = static_info;
  dev_info.aspm_active = true;
  dev_info.lock_active = false;
  dev_info.available_capacity_MB = 4096;
  dev_info.status = "Healthy";
  dev_info.numa_attached = 0;

  StatInfo stat_info;
  stat_info.device_id = MOCK_DEVICE_ID;
  stat_info.protocol = "CXL";
  stat_info.port_type = "Upstream";
  stat_info.status = "Active";
  stat_info.total_memory_MB = 8192;
  stat_info.used_memory_MB = 4096;
  stat_info.available_memory_MB = 4096;
  stat_info.total_bandwidth_MBps = 20000;
  stat_info.used_bandwidth_MBps = 1104548;
  stat_info.rw_errors = 0;
  stat_info.latency_us = 120;
  stat_info.sensor_stats = cmmh_stat_sensor_t{.fpga_temp = 46};

  sc_device dev(sid.get_sc_id(), "MockDevice", 8192, 1);
  dev.d_set_static_info(static_info);
  dev.d_set_dynamic_info(dev_info);

  device_map_[sid] = dev;
  stats_map_[sid] = stat_info;
  mgr.register_device(sid, this);

  LOG(level_E::INFO, "MockCMMH: Registered mock device with ID: " +
                         std::to_string(MOCK_DEVICE_ID));
}

sc_device MockCMMH::get_device_object(const sc_id& sid) const {
  auto it = device_map_.find(sid);
  if (it != device_map_.end()) {
    return it->second;
  }
  throw std::runtime_error("MockCMMH: device object not found for sid=" +
                           std::to_string(sid.get_sc_id()));
}
