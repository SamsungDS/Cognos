#include "sc_cmmh.h"  // implements all functions declared in cmmh.h

#include "sc_utility.h"  // generate_dev_id, get_numa_memory_info, discover_cxl_devices_shared, get_global_dev_type_map

/**
 * @brief DevCMMH constructor.
 */
DevCMMH::DevCMMH() { LOG(level_E::INFO, "DevCMMH adapter constructed"); }

/**
 * @brief DevCMMH destructor.
 */
DevCMMH::~DevCMMH() { LOG(level_E::INFO, "DevCMMH adapter destroyed"); }

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
  return it != device_map_.end() ? it->second.d_get_info() : DevInfo{};
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
