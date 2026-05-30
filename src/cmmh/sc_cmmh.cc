#include "sc_cmmh.h"  // implements all functions declared in cmmh.h

#include "sc_utility.h"  // generate_dev_id, get_numa_memory_info,
// discover_cxl_devices_shared, find_dev_type_map,
// get_numa_node_from_bdf, get_metrics_info, set_hdm_base_to_device_index

#include <string>

#include "sc_api_structs.h"

/**
 * @brief DevCMMH constructor.
 */
DevCMMH::DevCMMH() { LOG(level_E::INFO, "DevCMMH adapter constructed"); }

/**
 * @brief DevCMMH destructor.
 */
DevCMMH::~DevCMMH() {
  LOG(level_E::INFO, "DevCMMH adapter destroyed");
  // stop all per-device monitors
  for (auto& [id, monitor] : dev_to_bwmon) {
    if (monitor) {
      monitor->stop();
    }
  }
  dev_to_bwmon.clear();
  cmmh_close();
  LOG(level_E::DEBUG, "DevCMMH destroyed and bandwidth monitors stopped.");
}

/**
 * @brief Check if users wants to restart cmmh_driver service via boolean
 * value in cxl.conf
 */
bool check_for_cmmh_driver_restart() {
  json_t* root;
  json_error_t error;

  // Load the JSON file
  root = json_load_file(CXL_CONF_FILE, 0, &error);
  if (!root) {
    LOG(level_E::ERROR,
        "Unable to load " + std::string(CXL_CONF_FILE) + " json file");
    return false;
  }

  // Ensure the root is an object
  if (!json_is_object(root)) {
    json_decref(root);
    return false;
  }

  // Extract the boolean value
  // The "b" format character expects a C int variable
  int is_enabled = 0;
  if (json_unpack(root, "{s:b}", "auto_restart_cmmh_driver", &is_enabled) !=
      0) {
    LOG(level_E::ERROR,
        "Error: failed to unpack 'auto_restart_cmmh_driver' key-value pair");
    json_decref(root);
    return false;
  }

  if (is_enabled) {
    LOG(level_E::INFO, "Restart of cmmh_driver service enabled");
    json_decref(root);
    return true;
  }

  return false;
}

/**
 * @brief Function to restart CMMH driver service
 */
void restart_cmmh_driver() {
  int result = std::system("systemctl restart cmmh_driver.service &");

  if (result != 0) {
    LOG(level_E::ERROR, "Unable to restart cmmh_driver service");
    return;
  }
  LOG(level_E::INFO, "Successfuly restarted cmmh_driver service");
}

/**
 * @brief Returns all discovered devices.
 */
std::vector<sc_device> DevCMMH::list_devices() const {
  LOG(level_E::INFO, "DevCMMH::list_devices() called");
  std::vector<sc_device> result;
  for (const auto& [id, dev] : device_map_) {
    result.push_back(dev);
  }
  LOG(level_E::DEBUG, "DevCMMH::list_devices returned " +
                          std::to_string(result.size()) + " devices");
  return result;
}

/**
 * @brief Returns a specific device object from internal map.
 */
sc_device DevCMMH::get_device_object(const sc_id& sid) const {
  auto it = device_map_.find(sid);
  LOG(level_E::DEBUG, "DevCMMH::get_device_object called");
  return it != device_map_.end() ? it->second : sc_device{};
}

/**
 * @brief Returns list of associated hosts.
 */
std::vector<sc_host> CXLDeviceAdapter::list_hosts() const {
  LOG(level_E::DEBUG, "DevCMMH::list_hosts called");
  return hosts_;
}

/**
 * @brief Returns DevInfo for a given device ID.
 */
DevInfo DevCMMH::get_device_info(const sc_id& sid) const {
  auto it = device_map_.find(sid);
  LOG(level_E::INFO, "DevCMMH::get_device_info called");

  if (it == device_map_.end()) {
    return DevInfo{};
  }

  // get existing device
  sc_device& dev = const_cast<sc_device&>(it->second);
  DevInfo dinfo = dev.d_get_info();

  // extract BDF location from static info
  const std::string& bdf = dinfo.static_info.location;

  // utility function to fetch updated NUMA node
  int numa_node = get_numa_node_from_bdf(bdf);

  // fetch updated memory info if node is valid
  uint64_t total_mb = 0, free_mb = 0;
  if (numa_node >= 0) {
    get_numa_memory_info(numa_node, total_mb, free_mb);
  }

  // update dynamic fields
  dinfo.numa_node = numa_node;
  dinfo.available_capacity_MB = free_mb;
  dev.d_set_dynamic_info(dinfo);

  return dinfo;
}

/**
 * @brief Returns StatInfo for a given device ID.
 */
StatInfo DevCMMH::get_device_stats(const sc_id& sid) const {
  LOG(level_E::INFO, "DevCMMH::get_device_stat called");
  DevInfo info = get_device_info(sid);

  StatInfo stats;
  stats.device_id = info.static_info.device_id;
  stats.protocol = info.static_info.protocol;
  stats.port_type = info.static_info.port_type;
  stats.status = info.status;

  stats.total_memory_MB = info.static_info.total_capacity_MB;
  stats.available_memory_MB = info.available_capacity_MB;
  stats.used_memory_MB = stats.total_memory_MB - stats.available_memory_MB;

  /*
   * @brief Estimate total theoretical bandwidth in MBps
   * - Each PCIe lane provides ~125 MB/s per 1 GT/s (after 128b/130b encoding
   *   overhead)
   * - for instance, Gen5 (32 GT/s) * x8 lanes = 32 * 8 * 125 = 32000 MB/s
   * - Note: This is an upper bound; real bandwidth may be lower due to
   *   protocol overhead
   *   assuming its one direction, for bidirectional (rx+tx) we need to multiply
   *   by 2
   */
  stats.total_bandwidth_MBps =
      info.static_info.link_speed_GT_s * info.static_info.link_width * 125;

  stats.rw_errors = 0;
  stats.latency_us = 0;

  LOG(level_E::INFO, "DevCMMH::getting sensor and cache stats");
  stats.sensor_stats = cmmh_stat_sensor(info.static_info.device_index);

  uint64_t t;
  if (stats.sensor_stats.has_value()) {
    // Log temperature reading and check if returned status is
    // CMMH_STAT_RC_SUCCESS If not, restart CMMH driver service
    if (stats.sensor_stats->status == CMMH_STAT_RC_SUCCESS) {
      t = stats.sensor_stats->fpga_temp;

      LOG(level_E::INFO, "Temperature recorded for device id: " +
                             std::to_string(sid.get_sc_id()) + " is " +
                             std::to_string(t) + " degree F");
      // Restart CMMH driver service if temperarture recorded is ouside of valid
      // operational range
      if ((t < 32) || (t > 212)) {
        LOG(level_E::ERROR, "Temperature recorded for device id: " +
                                std::to_string(sid.get_sc_id()) +
                                " is outside of operational range.");
        stats.sensor_stats->fpga_temp = 0;

        if (check_for_cmmh_driver_restart()) {
          LOG(level_E::INFO, "Restarting CMMH driver service.");
          restart_cmmh_driver();
        }
      }
    } else {
      stats.sensor_stats->fpga_temp = 0;
      if (check_for_cmmh_driver_restart()) {
        LOG(level_E::INFO,
            "Sensor stats status did not return success. Restarting CMMH "
            "driver service.");
        restart_cmmh_driver();
      }
    }
  } else {
    stats.sensor_stats->fpga_temp = 0;
    LOG(level_E::INFO, "Sensor stats did not record any value.");
  }

  stats.cache_stats = cmmh_stat_cache(info.static_info.device_index);
  LOG(level_E::INFO, "DevCMMH::got sensor and cache stats");

  // get bandwidth from per-device monitor
  LOG(level_E::INFO, "DevCMMH::getting bandwidth stats");
  auto it = dev_to_bwmon.find(sid);
  if (it != dev_to_bwmon.end() && it->second) {
    stats.used_bandwidth_Bps = it->second->get_average_Bps();
  } else {
    LOG(level_E::WARN,
        "BandwidthMonitor missing for scid=" + std::to_string(sid.get_sc_id()) +
            "returning 0 MBps");
    stats.used_bandwidth_Bps = 0;
  }

  LOG(level_E::INFO, "DevCMMH::get_device_stats completed");
  return stats;
}

/**
 * @brief Perform PCI-based device discovery for CMMH devices.
 *
 * This function invokes a shared utility to discover CXL memory devices (based
 * on PCI), filters them using the global vendor/device ID map, and populates
 * the adapter's internal `device_map_`. It then registers the discovered
 * devices with the provided `DeviceManager`.
 *
 * The shared discovery logic is located in `sc_utility.cc`, and this function
 * is responsible for adapter-specific behavior like naming, ownership, and
 * registration.
 *
 * @param mgr Reference to the DeviceManager used to register discovered
 * devices.
 */
void DevCMMH::discover_devices(DeviceManager& mgr) {
  LOG(level_E::INFO, "DevCMMH::discover_devices started");
  // populate hdm_base -> device_index map
  build_hdm_base_to_device_index_map();

  // get device type map
  const auto* dt_map = find_dev_type_map();
  if (!dt_map || dt_map->empty()) {
    LOG(level_E::ERROR, "Device ID mapping not initialized.");
    return;
  }

  // shared utility : discover devices and return the map
  auto discovered_devices = discover_cxl_devices_shared(*dt_map);

  for (const auto& [scid, dev] : discovered_devices) {
    device_map_[scid] = dev;
    // registration
    mgr.register_device(scid, this);

    // start bandwidth monitor for each device
    DevStaticInfo sinfo = dev.d_get_info().static_info;
    if (dev_to_bwmon.find(scid) == dev_to_bwmon.end()) {
      auto monitor = std::make_unique<BandwidthMonitor>(sinfo.device_index,
                                                        sinfo.bw_interval_sec);
      monitor->start();
      dev_to_bwmon[scid] = std::move(monitor);
      LOG(level_E::INFO,
          "Started BandwidthMonitor for scid=" +
              std::to_string(sinfo.device_id) +
              " with interval=" + std::to_string(sinfo.bw_interval_sec));
    }
  }

  LOG(level_E::INFO, "DevCMMH::discover_devices completed");
}

/**
 * @brief Initializes adapter-specific configuration (stub).
 * @return Always returns 0 for now.
 */
int DevCMMH::setup_info() {
  LOG(level_E::INFO, "DevCMMH::setup_info called");
  return 0;
}

void DevCMMH::build_hdm_base_to_device_index_map() {
  std::unordered_map<uint64_t, int> mapping;

  if (cmmh_init() != 0) {
    LOG(level_E::ERROR,
        "cmmh_init failed. Skipping hdm_base to device index mapping.");
    return;
  }

  int dev_count = cmmh_get_device_count();
  LOG(level_E::INFO, "CMMH device count = " + std::to_string(dev_count));

  for (int i = 0; i < dev_count; ++i) {
    auto spec = cmmh_get_spec(i);
    if (spec.status == CMMH_STAT_RC_SUCCESS) {
      mapping[spec.hdm_base] = i;
      LOG(level_E::DEBUG, "Mapped hdm_base=" + std::to_string(spec.hdm_base) +
                              " to device_index=" + std::to_string(i));
    } else {
      LOG(level_E::WARN, "Skipping device index " + std::to_string(i) +
                             " due to invalid spec status");
    }
  }

  set_hdm_base_to_device_index(mapping);
}

/**
 * @brief Entry point for plugin registration.
 * Called by PluginManager using dlsym().
 */
extern "C" void register_plugin(DeviceManager& mgr) {
  LOG(level_E::INFO, "CMMH plugin registering with DeviceManager");
  static DevCMMH* adapter = new DevCMMH();
  mgr.registerAdapter("cmmh", adapter);
  LOG(level_E::INFO, "DevCMMH plugin registered successfully");
}
