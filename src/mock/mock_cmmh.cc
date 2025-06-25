#include "mock_cmmh.h"

#include <string>

#include "sc_logger.h"
#include "sc_servicer.h"
#include "sc_utility.h"

MockCMMH::MockCMMH() = default;
MockCMMH::~MockCMMH() = default;

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
  LOG(level_E::INFO, "MockCMMH: Loading devices from config...");

  // const std::string json_path = CXL_ID_TYPE_MAP_FILE;
  const char* env_path = getenv("CXL_ID_TYPE_MAP_FILE");
  std::string json_path =
      env_path ? std::string(env_path) : CXL_ID_TYPE_MAP_FILE;

  json_error_t error;

  json_t* root = json_load_file(json_path.c_str(), 0, &error);
  if (!root || !json_is_object(root)) {
    LOG(level_E::ERROR,
        "Failed to parse mock JSON: " + std::string(error.text));
    return;
  }

  json_t* dev_map = json_object_get(root, "device_map");
  if (!dev_map || !json_is_array(dev_map)) {
    LOG(level_E::ERROR, "Missing or invalid 'device_map' in config.");
    json_decref(root);
    return;
  }

  size_t index;
  json_t* entry;
  json_array_foreach(dev_map, index, entry) {
    if (json_is_true(json_object_get(entry, "mock_empty"))) {
      LOG(level_E::INFO,
          "Skipping mock_empty device at index: " + std::to_string(index));
      continue;
    }

    uint64_t scid_raw =
        std::stoull(get_json_str(entry, "mock_device_id"), nullptr, 16);
    sc_id sid(scid_raw);

    DevStaticInfo static_info;
    static_info.device_id = scid_raw;
    static_info.manufacturer = get_json_str(entry, "manufacturer");
    static_info.serial_number =
        std::stoull(get_json_str(entry, "serial_number"), nullptr, 0);
    static_info.fw_revision = get_json_str(entry, "fw_revision");
    static_info.location = get_json_str(entry, "location");
    static_info.total_capacity_MB = get_json_int(entry, "total_capacity_MB");
    static_info.feature_supported = get_json_str(entry, "feature_supported");
    static_info.vendor_device_type = get_json_str(entry, "device_type");
    static_info.cxl_device_type = get_json_str(entry, "cxl_device_type");
    static_info.domain_id = get_json_int(entry, "domain_id");
    static_info.domain_type = get_json_str(entry, "domain_type");
    static_info.connection_type = get_json_str(entry, "connection_type");
    static_info.mode_discovered = get_json_str(entry, "mode_discovered");
    static_info.protocol = get_json_str(entry, "protocol");
    static_info.link_speed = get_json_int(entry, "lane_speed");
    static_info.link_width = get_json_int(entry, "lane_width");
    static_info.port_type = get_json_str(entry, "port_type");
    static_info.advertised_qos = parse_qos_info(entry);
    static_info.capabilities = parse_capabilities(entry);

    DevInfo dev_info;
    dev_info.static_info = static_info;
    dev_info.status = get_json_str(entry, "status");
    dev_info.available_capacity_MB =
        get_json_int(entry, "available_capacity_MB");
    dev_info.numa_attached = get_json_int(entry, "numa_node");

    sc_device device(sid.get_sc_id(), static_info.vendor_device_type,
                     static_info.total_capacity_MB, 1);
    device.d_set_static_info(static_info);
    device.d_set_dynamic_info(dev_info);

    // StatInfo
    json_t* stat = json_object_get(entry, "stat_info");
    StatInfo stat_info;
    if (stat) {
      stat_info.device_id = scid_raw;
      stat_info.protocol = static_info.protocol;
      stat_info.port_type = static_info.port_type;
      stat_info.status = dev_info.status;
      stat_info.total_memory_MB = get_json_int(stat, "total_memory_MB");
      stat_info.used_memory_MB = get_json_int(stat, "used_memory_MB");
      stat_info.available_memory_MB = get_json_int(stat, "available_memory_MB");
      stat_info.total_bandwidth_MBps =
          get_json_int(stat, "total_bandwidth_MBps");
      stat_info.used_bandwidth_MBps = get_json_int(stat, "used_bandwidth_MBps");
      stat_info.rw_errors = get_json_int(stat, "rw_errors");
      stat_info.latency_us = get_json_int(stat, "latency_us");
      stat_info.sensor_stats = parse_sensor_stats(stat);
    }

    device_map_[sid] = device;
    stats_map_[sid] = stat_info;
    mgr.register_device(sid, this);

    LOG(level_E::INFO, "MockCMMH: Registered mock device ID = " +
                           std::to_string(sid.get_sc_id()));
  }

  json_decref(root);
  LOG(level_E::INFO, "MockCMMH: Discovery completed.");
}

sc_device MockCMMH::get_device_object(const sc_id& sid) const {
  auto it = device_map_.find(sid);
  if (it != device_map_.end()) {
    return it->second;
  }
  throw std::runtime_error("MockCMMH: device object not found for sid=" +
                           std::to_string(sid.get_sc_id()));
}

QoSInfo MockCMMH::parse_qos_info(json_t* entry) {
  QoSInfo qos;

  json_t* qos_json = json_object_get(entry, "advertised_qos");
  if (!qos_json || !json_is_object(qos_json)) {
    return qos;
  }

  qos.avg_latency = get_json_int(qos_json, "avg_latency");
  qos.p99_latency = get_json_int(qos_json, "p99_latency");
  qos.io_per_sec = get_json_int(qos_json, "io_per_sec");
  qos.bw_per_sec = get_json_int(qos_json, "bw_per_sec");
  qos.io_size = get_json_int(qos_json, "io_size");
  qos.qd = get_json_int(qos_json, "qd");

  return qos;
}

Capabilities MockCMMH::parse_capabilities(json_t* entry) {
  Capabilities caps;

  json_t* caps_json = json_object_get(entry, "capabilities");
  if (!caps_json || !json_is_object(caps_json)) {
    return caps;
  }

  caps.power_management_version =
      get_json_int(caps_json, "power_management_version");

  json_t* vendor_specific = json_object_get(caps_json, "vendor_specific");
  if (vendor_specific && json_is_object(vendor_specific)) {
    const char* key;
    json_t* val;
    json_object_foreach(vendor_specific, key, val) {
      if (json_is_string(val)) {
        caps.vendor_specific[key] = json_string_value(val);
      }
    }
  }

  return caps;
}

std::optional<cmmh_stat_sensor_t> MockCMMH::parse_sensor_stats(json_t* obj) {
  cmmh_stat_sensor_t s{};
  json_t* stats = json_object_get(obj, "sensor_stats");
  if (!stats || !json_is_object(stats)) return std::nullopt;
  s.fpga_temp = get_json_int(stats, "fpga_temp");
  return s;
}
