#include "sc_utility.h"  // all functions from utility class

#include <jansson.h>  // json_loads, json_dumps, json_array_foreach, json_object_get, json_load_file

#include <cerrno>      // EINVAL, ENOENT, ERANGE, etc.
#include <filesystem>  // std::filesystem::exists
#include <fstream>     // std::ifstream
#include <iostream>    // std::cerr
#include <mutex>       // std::once_flag, std::call_once
#include <sstream>     // std::ostringstream, std::istringstream
#include <string>      // std::string and conversions

extern "C" {
#include <pci/pci.h>  // pci_alloc, pci_init, pci_scan_bus, pci_fill_info, pci_cleanup
}

bool str_to_int(const std::string& id_str, uint64_t& id,
                std::string& error_response) {
  try {
    id = std::stoull(id_str);
    return true;
  } catch (const std::invalid_argument& e) {
    LOG(level_E::ERROR, "Invalid id format: " + std::string(e.what()));
    error_response = posix_err_to_json(EINVAL, "Invalid id format");
  } catch (const std::out_of_range& e) {
    LOG(level_E::ERROR, "id out of range: " + std::string(e.what()));
    error_response = posix_err_to_json(ERANGE, "id value out of range");
  }
  return false;
}

// Mapping POSIX error codes to human-readable error names
const std::unordered_map<int, std::string> error_map = {
    {EINVAL, "EINVAL"},
    {ENOENT, "ENOENT"},
    {EIO, "EIO"},
    {EPERM, "EPERM"},
    {EBUSY, "EBUSY"},
    {ENOMEM, "ENOMEM"},
    {ERANGE, "ERANGE"},
    {EEXIST, "EEXIST"},
    {ENOEXEC, "ENOEXEC"},
    {EPROTO, "EPROTO"},
    {EFAULT, "EFAULT"},
    {ETIMEDOUT, "ETIMEDOUT"},
    {ECONNREFUSED, "ECONNREFUSED"}

};

std::string posix_err_to_json(int error_code,
                              const std::string& custom_message) {
  std::string message;

  switch (error_code) {
    case EINVAL:
      message = "Invalid request parameters";
      break;
    case ENOENT:
      message = "Requested resource not found";
      break;
    case EIO:
      message = "Internal I/O error occurred";
      break;
    case EPERM:
      message = "Operation not permitted";
      break;
    case EBUSY:
      message = "Resource is busy, try again later";
      break;
    case ENOMEM:
      message = "Memory allocation failure";
      break;
    case ERANGE:
      message = "Value out of range";
      break;
    case EEXIST:
      message = "Resource already exists";
      break;
    case ENOEXEC:
      message = "Executable format error (plugin load failed)";
      break;
    case EPROTO:
      message = "Plugin registration error";
      break;
    case EFAULT:
      message = "System fault occurred";
      break;
    case ETIMEDOUT:
      message = "Operation timed out";
      break;
    case ECONNREFUSED:
      message = "Connection refused";
      break;
    default:
      message = "Unknown error occurred";
      break;
  }

  // If a custom message is provided, override the default message
  if (!custom_message.empty()) {
    message = custom_message;
  }

  // human-readable error name (default to numeric if not found)
  std::string error_code_str = error_map.count(error_code)
                                   ? error_map.at(error_code)
                                   : std::to_string(error_code);
  // Construct JSON response
  std::ostringstream json;
  json << R"({"rc": ")" << error_code_str << R"(", "message": ")" << message
       << R"("})";

  return json.str();
}

bool extract_required_params(
    const std::unordered_map<std::string, std::string>& input,
    const std::vector<std::string>& keys,
    std::unordered_map<std::string, std::string>& output,
    std::string& error_response) {
  LOG(level_E::INFO, "Extracting required parameters...");
  for (const auto& key : keys) {
    auto it = input.find(key);
    if (it == input.end()) {
      LOG(level_E::ERROR, "Missing required parameter: " + key);
      error_response = posix_err_to_json(EINVAL, "Missing parameter: " + key);
      return false;
    }
    output[key] = it->second;
    LOG(level_E::INFO,
        "Extracted parameter - Key: " + key + ", Value: " + output[key]);
  }
  LOG(level_E::INFO, "All required parameters extracted successfully.");
  return true;
}

bool is_device_list_empty(const std::string& json_response) {
  LOG(level_E::INFO, "Checking if device list is empty...");
  json_error_t error;
  json_t* root = json_loads(json_response.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::ERROR, "JSON parse failed while checking empty device list: " +
                            std::string(error.text));
    return true;
  }
  json_t* devices = json_object_get(root, "devices");
  if (!devices || !json_is_array(devices)) {
    LOG(level_E::WARN, "`devices` key missing or not an array.");
    json_decref(root);
    return true;
  }
  size_t count = json_array_size(devices);
  LOG(level_E::INFO,
      "Device list contains " + std::to_string(count) + " entries.");
  json_decref(root);
  return count == 0;
}

static const DevTypeMap* global_dev_type_map = nullptr;

void set_global_dev_type_map(const DevTypeMap& external_map) {
  global_dev_type_map = &external_map;
}

const DevTypeMap* get_global_dev_type_map() { return global_dev_type_map; }

const DevTypeMap& load_dev_type_mapping_json(const std::string& filepath) {
  static DevTypeMap internal_map;
  static std::once_flag init_flag;

  std::call_once(init_flag, [&]() {
    json_error_t error;
    json_t* root = json_load_file(filepath.c_str(), 0, &error);
    if (!root || !json_is_object(root)) {
      LOG(level_E::ERROR,
          "Failed to parse JSON file or root is not an object: " +
              std::string(error.text));
      return;
    }

    json_t* arr = json_object_get(root, "device_map");
    if (!arr || !json_is_array(arr)) {
      LOG(level_E::ERROR,
          "`device_map` key missing or not an array in: " + filepath);
      json_decref(root);
      return;
    }

    size_t index;
    json_t* entry;
    json_array_foreach(arr, index, entry) {
      if (!json_is_object(entry)) continue;

      const char* type_str =
          json_string_value(json_object_get(entry, "device_type"));
      const char* vendor_str =
          json_string_value(json_object_get(entry, "vendor_id"));
      const char* device_str =
          json_string_value(json_object_get(entry, "device_id"));

      if (!type_str || !vendor_str || !device_str) {
        LOG(level_E::WARN,
            "Skipping incomplete entry at index " + std::to_string(index));
        continue;
      }

      try {
        uint16_t vendor = std::stoul(vendor_str, nullptr, 16);
        uint16_t device = std::stoul(device_str, nullptr, 16);
        internal_map[{vendor, device}] = std::string(type_str);
      } catch (const std::exception& ex) {
        LOG(level_E::WARN, "Failed to parse vendor/device ID at index " +
                               std::to_string(index) + ": " + ex.what());
      }
    }

    json_decref(root);
    LOG(level_E::INFO, "Loaded " + std::to_string(internal_map.size()) +
                           " device ID mappings from JSON: " + filepath);
    global_dev_type_map = &internal_map;
  });

  return *global_dev_type_map;
}

int validate_json_file(const std::string& filepath) {
  if (std::filesystem::exists(filepath)) {
    LOG(level_E::INFO, "JSON mapping file found: " + filepath);
    return 0;
  } else {
    LOG(level_E::ERROR, "JSON mapping file missing: " + filepath);
    return -ENOENT;
  }
}

int parse_json_key(const std::string& json_file, const std::string& key,
                   std::string& value) {
  json_error_t error;
  json_t* root = json_load_file(json_file.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::ERROR,
        "Failed to load JSON file: " + json_file + " error: " + error.text);
    return -ENOENT;
  }

  json_t* jval = json_object_get(root, key.c_str());
  if (!jval || !json_is_string(jval)) {
    json_decref(root);
    LOG(level_E::ERROR, "Key missing or not a string: " + key);
    return -EINVAL;
  }

  value = json_string_value(jval);
  LOG(level_E::INFO, "Extracted key " + key + " with value: " + value);
  json_decref(root);
  return 0;
}

/**
 * @brief Generate a 48-bit unique device ID
 */
uint64_t generate_dev_id(uint16_t vendor_id, uint16_t device_id, uint8_t bus) {
  uint64_t dev_id = 0;
  dev_id |= ((uint64_t)(vendor_id & 0xFFFF)) << 32;
  dev_id |= ((uint64_t)(device_id & 0xFFFF)) << 16;
  dev_id |= ((uint64_t)(bus & 0xFF)) << 8;
  return dev_id;
}

std::unordered_map<sc_id, sc_device, hash_sc_id> discover_cxl_devices_shared(
    const DevTypeMap& dev_type_map) {
  std::unordered_map<sc_id, sc_device, hash_sc_id> device_map;

  struct pci_access* pacc = pci_alloc();
  pci_init(pacc);
  pci_scan_bus(pacc);

  for (pci_dev* dev = pacc->devices; dev; dev = dev->next) {
    pci_fill_info(dev, PCI_FILL_IDENT | PCI_FILL_BASES);

    uint16_t vendor = dev->vendor_id;
    uint16_t device = dev->device_id;
    auto it = dev_type_map.find({vendor, device});
    if (it == dev_type_map.end()) continue;
    LOG(level_E::INFO,
        "Discovered CXL device: vendor=" + std::to_string(vendor) +
            " device=" + std::to_string(device) + " type=" + it->second);
    std::string dev_type = it->second;

    // Build PCI BDF string
    char bdf[32];
    snprintf(bdf, sizeof(bdf), "%04x:%02x:%02x.%x", dev->domain, dev->bus,
             dev->dev, dev->func);
    std::string bdf_str(bdf);
    int numa_node = get_numa_node_from_sysfs(bdf_str);

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

    device_map[scid] = scdev;

    LOG(level_E::INFO, "Discovered " + dev_type + " @ " + bdf_str +
                           " NUMA=" + std::to_string(numa_node) +
                           " total=" + std::to_string(total_mb) +
                           "MB free=" + std::to_string(free_mb) + "MB");
  }

  pci_cleanup(pacc);
  LOG(level_E::INFO, "utility::discover_cxl_devices_shared completed");
  LOG(level_E::INFO,
      "Total CXL devices discovered: " + std::to_string(device_map.size()));
  return device_map;
}

bool get_numa_memory_info(int node_id, uint64_t& total_mb, uint64_t& free_mb) {
  try {
    const uint64_t MB = 1024 * 1024;
    long long free_bytes = 0;
    long long total_bytes = numa_node_size64(node_id, &free_bytes);
    if (total_bytes == -1) {
      LOG(level_E::WARN,
          "NUMA node size query failed for node " + std::to_string(node_id));
      return false;
    }
    total_mb = total_bytes / MB;
    free_mb = free_bytes / MB;
    return true;
  } catch (...) {
    LOG(level_E::ERROR, "Exception in get_numa_memory_info for node " +
                            std::to_string(node_id));
    return false;
  }
}

int get_numa_node_from_sysfs(const std::string& bdf) {
  const char* test_root = std::getenv("TEST_SYSFS_ROOT");
  std::string base_path =
      test_root ? std::string(test_root) : "/sys/bus/pci/devices";
  std::string path = base_path + "/" + bdf + "/numa_node";

  int node = -1;
  std::ifstream nfile(path);
  if (nfile.is_open()) {
    nfile >> node;
  } else {
    LOG(level_E::WARN, "NUMA node file missing for " + bdf);
  }
  return node;
}
