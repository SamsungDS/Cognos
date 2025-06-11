#include "sc_cmmh.h"  // implements all functions declared in cmmh.h

#include "sc_utility.h"  // generate_dev_id, get_numa_memory_info,
// discover_cxl_devices_shared, get_global_dev_type_map,
// get_numa_node_from_sysfs

/**
 * @brief DevCMMH constructor.
 */
DevCMMH::DevCMMH() { LOG(level_E::INFO, "DevCMMH adapter constructed"); }

/**
 * @brief DevCMMH destructor.
 */
DevCMMH::~DevCMMH() {
  LOG(level_E::INFO, "DevCMMH adapter destroyed");
  bandwidth_monitor_.stop();
  cmmh_close();
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
  LOG(level_E::DEBUG, "DevCMMH::get_device_info called");

  if (it == device_map_.end()) {
    return DevInfo{};
  }

  // get existing device
  sc_device& dev = const_cast<sc_device&>(it->second);
  DevInfo dinfo = dev.d_get_info();

  // extract BDF location from static info
  const std::string& bdf = dinfo.static_info.location;

  // utility function to fetch updated NUMA node
  int numa_node = get_numa_node_from_sysfs(bdf);

  // fetch updated memory info if node is valid
  uint64_t total_mb = 0, free_mb = 0;
  if (numa_node >= 0) {
    get_numa_memory_info(numa_node, total_mb, free_mb);
  }

  // update dynamic fields
  dinfo.numa_attached = numa_node;
  dinfo.available_capacity_MB = free_mb;

  dev.d_set_dynamic_info(dinfo);

  return dinfo;
}

/**
 * @brief Returns StatInfo for a given device ID.
 */
StatInfo DevCMMH::get_device_stats(const sc_id& sid) const {
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
      info.static_info.link_speed * info.static_info.link_width * 125;

  stats.rw_errors = 0;
  stats.latency_us = 0;
  stats.sensor_stats = cmmh_stat_sensor();
  stats.cache_stats = cmmh_stat_cache();
  stats.used_bandwidth_MBps = bandwidth_monitor_.get_average_MBps();

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
  const auto* global_map = get_global_dev_type_map();
  if (!global_map) {
    LOG(level_E::ERROR, "Device ID mapping not initialized.");
    return;
  }

  // shared utility discover devices and return the map
  auto discovered_devices = discover_cxl_devices_shared(*global_map);

  for (const auto& [scid, dev] : discovered_devices) {
    device_map_[scid] = dev;
    // registration
    mgr.register_device(scid, this);
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
