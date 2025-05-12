#include "sc_cmmh.h"

#include <fstream>

#include "sc_utility.h"

extern "C" {
#include <pci/pci.h>
}

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
std::vector<sc_host> DevCMMH::list_hosts() {
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
 * @brief Generate a 48-bit unique device ID
 */
inline uint64_t generate_dev_id(uint16_t vendor_id, uint16_t device_id,
                                uint8_t bus) {
  uint64_t dev_id = 0;
  dev_id |= ((uint64_t)(vendor_id & 0xFFFF)) << 32;
  dev_id |= ((uint64_t)(device_id & 0xFFFF)) << 16;
  dev_id |= ((uint64_t)(bus & 0xFF)) << 8;
  return dev_id;
}

/**
 * @brief Perform PCI-based device discovery and register CMMH devices.
 *
 * This function uses libpci to enumerate PCI devices, filters based on
 * vendor/device ID pairs (loaded from a global mapping), and looks up NUMA
 * node attachment via sysfs. For each supported device, it builds a
 * corresponding `sc_device` with static and dynamic metadata, registers it
 * with the DeviceManager, and stores it in the adapter's internal map.
 *
 * Device ID is a 48-bit value composed of vendor ID, device ID, and bus.
 *
 * @param mgr Reference to DeviceManager to register discovered devices with.
 */
void DevCMMH::discover_devices(DeviceManager& mgr) {
  LOG(level_E::INFO, "DevCMMH::discover_devices started");

  const auto* global_map = get_global_dev_type_map();
  if (!global_map) {
    LOG(level_E::ERROR,
        "Device ID mapping not initialized. Aborting discovery.");
    return;
  }
  const auto& dev_type_map = *global_map;

  struct pci_access* pacc = pci_alloc();
  pci_init(pacc);
  pci_scan_bus(pacc);

  for (pci_dev* dev = pacc->devices; dev; dev = dev->next) {
    pci_fill_info(dev, PCI_FILL_IDENT | PCI_FILL_BASES);

    uint16_t vendor = dev->vendor_id;
    uint16_t device = dev->device_id;

    auto it = dev_type_map.find({vendor, device});
    if (it == dev_type_map.end()) continue;

    std::string dev_type = it->second;

    // Build PCI BDF string
    char bdf[32];
    snprintf(bdf, sizeof(bdf), "%04x:%02x:%02x.%x", dev->domain, dev->bus,
             dev->dev, dev->func);
    std::string bdf_str(bdf);
    std::string sysfs_path = "/sys/bus/pci/devices/" + bdf_str + "/numa_node";

    // NUMA node detection
    int numa_node = -1;
    std::ifstream nfile(sysfs_path);
    if (nfile.is_open()) {
      nfile >> numa_node;
    } else {
      LOG(level_E::WARN,
          "NUMA node file missing: " + sysfs_path + " — assuming -1");
    }

    // Get memory metrics
    uint64_t total_mb = 1024, free_mb = 1024;
    if (numa_node >= 0) {
      get_numa_memory_info(numa_node, total_mb, free_mb);
    } else {
      LOG(level_E::WARN, "Invalid NUMA node for BDF " + bdf_str);
    }

    // Generate 48-bit device ID
    uint64_t dev_id_val = generate_dev_id(vendor, device, dev->bus);
    sc_id scid(dev_id_val);

    // Create device
    sc_device scdev;
    scdev.d_set_dev_name("cmmh");
    scdev.d_set_capacity(total_mb);
    scdev.d_set_port(dev->dev);

    // Static info
    DevStaticInfo static_info;
    static_info.device_id = dev_id_val;
    static_info.manufacturer = "Samsung";
    static_info.serial_number = 0x12345678;
    static_info.fw_revision = "1.0.0";
    static_info.location = bdf_str;
    static_info.total_capacity_MB = total_mb;
    static_info.feature_supported = "basic";
    static_info.vendor_device_type = dev_type;
    static_info.cxl_device_type = "Type3";
    static_info.domain_id = dev->domain;
    static_info.domain_type = "PCIe";
    static_info.connection_type = "CXL.mem";
    static_info.mode_discovered = "auto";
    static_info.protocol = "CXL 2.0";
    static_info.link_speed = 16;
    static_info.link_width = 8;
    static_info.port_type = "root";
    static_info.capabilities.power_management_version = 1;
    static_info.capabilities.vendor_specific["latency_hint"] = "enabled";
    static_info.advertized_qos = {.avg_latency = 120,
                                  .p99_latency = 350,
                                  .io_per_sec = 50000,
                                  .bw_per_sec = 1000000,
                                  .io_size = 4096,
                                  .qd = 32};

    // Dynamic info
    DevInfo dyn_info;
    dyn_info.static_info = static_info;
    dyn_info.available_capacity_MB = free_mb;
    dyn_info.numa_attached = numa_node;
    dyn_info.status = "active";

    // Final assignment
    scdev.d_set_static_info(static_info);
    scdev.d_set_dynamic_info(dyn_info);

    device_map_[scid] = scdev;
    mgr.register_device(scid, this);

    LOG(level_E::INFO, "Registered " + dev_type + " @ " + bdf_str +
                           " NUMA=" + std::to_string(numa_node) +
                           " total=" + std::to_string(total_mb) +
                           "MB free=" + std::to_string(free_mb) + "MB");
  }

  pci_cleanup(pacc);
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
