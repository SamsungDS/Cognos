#include "sc_utility.h"  // all functions from utility class

#include <jansson.h>  // json_loads, json_dumps, json_array_foreach, json_object_get, json_load_file

#include <cerrno>      // EINVAL, ENOENT, ERANGE, etc.
#include <chrono>      // system_clock, duration_cast, seconds
#include <filesystem>  // std::filesystem::exists
#include <fstream>     // std::ifstream
#include <iostream>    // std::cerr
#include <mutex>       // std::once_flag, std::call_once
#include <sstream>     // std::ostringstream, std::istringstream
#include <string>      // std::string and conversions

#include "sc_api_structs.h"

extern "C" {
#include <pci/pci.h>  // pci_alloc, pci_init, pci_scan_bus, pci_fill_info, pci_cleanup
}

#ifndef PCI_CAP_PTR
#define PCI_CAP_PTR 0x34  ///< Offset in PCI config space to capability list
#endif

#ifndef PCI_CAP_ID_EXP
#define PCI_CAP_ID_EXP 0x10  ///< PCI Express Capability ID
#endif

// forward declaration for helpers
static int parse_and_load_device_map(json_t* root, const std::string& filepath,
                                     DevTypeMap& map);
static bool parse_device_entry(json_t* entry, size_t index, DevJsonHints& hint);
static int parse_capabilities(json_t* entry, DevJsonHints& hint);
static int parse_qos(json_t* entry, DevJsonHints& hint);

struct MetricsParseError : std::runtime_error {
  using std::runtime_error::runtime_error;
};

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

  std::string error_code_str = error_map.count(error_code)
                                   ? error_map.at(error_code)
                                   : std::to_string(error_code);
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

static const DevTypeMap* dev_type_map = nullptr;
void set_dev_type_map(const DevTypeMap& external_map) {
  dev_type_map = &external_map;
}
const DevTypeMap* find_dev_type_map() { return dev_type_map; }

static MetricsInfo metrics_info;
void set_metrics_info(const MetricsInfo& info) { metrics_info = info; }
const MetricsInfo& get_metrics_info() { return metrics_info; }

int load_dev_type_mapping_json(const std::string& filepath) {
  static DevTypeMap internal_map;
  static std::once_flag init_flag;
  static int load_status = 0;
  std::call_once(init_flag, [&]() {
    json_error_t error;
    json_t* root = json_load_file(filepath.c_str(), 0, &error);
    if (!root || !json_is_object(root)) {
      LOG(level_E::ERROR, "Failed to parse JSON: " + filepath +
                              " Error: " + std::string(error.text));
      load_status = -EINVAL;
      return;
    }
    int map_status = parse_and_load_device_map(root, filepath, internal_map);
    int metrics_status = parse_metrics_config(root, filepath);
    json_decref(root);
    if (map_status == 0 && metrics_status == 0) {
      set_dev_type_map(internal_map);
      load_status = 0;
      LOG(level_E::INFO, "Total CXL device entries loaded: " +
                             std::to_string(internal_map.size()));
    } else {
      load_status = (map_status != 0) ? map_status : metrics_status;
    }
  });
  return load_status;
}

/**
 * @brief Helper function to parse and load device map from the root JSON
 * object.
 *
 * @param root Parsed JSON root object
 * @param filepath Path to the original JSON file.
 * @param map Reference to the internal DevTypeMap to populate
 * @return 0 on success, negative error code on failure
 */
static int parse_and_load_device_map(json_t* root, const std::string& filepath,
                                     DevTypeMap& map) {
  json_t* arr = json_object_get(root, "device_map");
  if (!arr || !json_is_array(arr)) {
    LOG(level_E::ERROR,
        "`device_map` key missing or not an array in: " + filepath);
    return -EINVAL;
  }

  size_t index;
  json_t* entry;
  json_array_foreach(arr, index, entry) {
    DevJsonHints hint;
    if (!parse_device_entry(entry, index, hint)) {
      continue;
    }

    uint16_t vendor = std::stoul(
        json_string_value(json_object_get(entry, "vendor_id")), nullptr, 16);
    uint16_t device = std::stoul(
        json_string_value(json_object_get(entry, "device_id")), nullptr, 16);
    std::string bdf = json_string_value(json_object_get(entry, "location"));
    map[{vendor, device, bdf}] = hint;

    LOG(level_E::INFO, "Loaded: vendor=0x" + to_hex(vendor) + " device=0x" +
                           to_hex(device) + " type=" + hint.vendor_device_type);
  }

  return 0;
}

/**
 * @brief Helper function to parse a single device entry from the JSON array.
 *
 * @param entry JSON object representing a single device
 * @param index Index in the device_map array (used for logging)
 * @param hint Output parameter to fill with parsed values
 * @return true if parsing succeeded, false if the entry is skipped
 */
static bool parse_device_entry(json_t* entry, size_t index,
                               DevJsonHints& hint) {
  const char* vendor_str =
      json_string_value(json_object_get(entry, "vendor_id"));
  const char* device_str =
      json_string_value(json_object_get(entry, "device_id"));
  const char* dev_type =
      json_string_value(json_object_get(entry, "device_type"));

  if (!vendor_str || !device_str || !dev_type) {
    LOG(level_E::WARN,
        "Skipping incomplete entry at index " + std::to_string(index));
    return false;
  }

  try {
    hint.vendor_device_type = dev_type;
    hint.lane_speed_GT_s = get_json_int(entry, "lane_speed_GT_s", 32);
    hint.lane_width = get_json_int(entry, "lane_width", 8);
    hint.manufacturer = get_json_str(entry, "manufacturer", "Unknown");
    hint.fw_revision = get_json_str(entry, "fw_revision", "N/A");
    hint.feature_supported = get_json_str(entry, "feature_supported", "basic");
    hint.cxl_device_type = get_json_str(entry, "cxl_device_type", "Type3");
    hint.domain_type = get_json_str(entry, "domain_type", "PCIe");
    hint.connection_type = get_json_str(entry, "connection_type", "CXL.mem");
    hint.mode_discovered = get_json_str(entry, "mode_discovered", "auto");
    hint.protocol = get_json_str(entry, "protocol", "CXL 2.0");
    hint.port_type = get_json_str(entry, "port_type", "root");
    hint.status = get_json_str(entry, "status", "Healthy");

    if (json_t* sn = json_object_get(entry, "serial_number");
        json_is_string(sn)) {
      hint.serial_number = std::stoull(json_string_value(sn), nullptr, 16);
    }

    if (parse_capabilities(entry, hint) < 0) {
      LOG(level_E::WARN,
          "Failed to parse capabilities at index " + std::to_string(index));
      return false;
    }

    if (parse_qos(entry, hint) < 0) {
      LOG(level_E::WARN,
          "Failed to parse QoS at index " + std::to_string(index));
      return false;
    }

    /*
     parse 'interval_sec' from "used_bandwidth" in config/cxl_dev_id_map.json.
     The 'interval_sec' value specifies how frequently the BandwidthMonitor's
     sampling loop reads hardware I/O counters (read/write page counts) from
     libcmmh. This ensures that the reported "used_bandwidth" metric is based on
     measurements taken at the intended polling frequency.
    */
    const json_t* ub = json_object_get(entry, "used_bandwidth");
    if (ub && json_is_object(ub)) {
      const json_t* interval_json = json_object_get(ub, "interval_sec");
      if (interval_json && json_is_integer(interval_json)) {
        hint.bw_interval_sec = json_integer_value(interval_json);
        LOG(level_E::INFO, "Parsed interval_seconds = " +
                               std::to_string(hint.bw_interval_sec));
      }
    }

    return true;

  } catch (const std::exception& ex) {
    LOG(level_E::ERROR,
        "Parse error at index " + std::to_string(index) + ": " + ex.what());
    return false;
  }
}

/**
 * @brief Helper fucntion whcih extracts capabilities object into the
 * DevJsonHints structure.
 *
 * @param entry JSON object of the device
 * @param hint Output structure to store capabilities
 * @return 0 on success, negative error code on failure
 */
static int parse_capabilities(json_t* entry, DevJsonHints& hint) {
  json_t* caps = json_object_get(entry, "capabilities");
  if (!caps || !json_is_object(caps)) {
    LOG(level_E::WARN, "`capabilities` missing or invalid");
    return -EINVAL;
  }
  hint.capabilities.power_management_version =
      get_json_int(caps, "power_management_version", 0);
  json_t* vs = json_object_get(caps, "vendor_specific");
  if (vs && json_is_object(vs)) {
    const char* key;
    json_t* val;
    json_object_foreach(vs, key, val) {
      if (json_is_string(val)) {
        hint.capabilities.vendor_specific[key] = json_string_value(val);
      }
    }
  }
  return 0;
}

/**
 * @brief Helper function whcih extracts QoS fields into the DevJsonHints
 * structure.
 *
 * @param entry JSON object of the device
 * @param hint Output structure to store QoS metrics
 * @return 0 on success, negative error code on failure
 */
static int parse_qos(json_t* entry, DevJsonHints& hint) {
  json_t* qos = json_object_get(entry, "advertised_qos");
  if (!qos || !json_is_object(qos)) {
    LOG(level_E::WARN, "`advertised_qos` missing or not an object");
    return -EINVAL;
  }
  hint.advertised_qos.avg_latency_ns = get_json_int(qos, "avg_latency_ns");
  hint.advertised_qos.p99_latency_ns = get_json_int(qos, "p99_latency_ns");
  hint.advertised_qos.io_per_sec = get_json_int(qos, "io_per_sec");
  hint.advertised_qos.bw_per_sec = get_json_int(qos, "bw_per_sec");
  hint.advertised_qos.io_size_in_bytes = get_json_int(qos, "io_size_in_bytes");
  hint.advertised_qos.qd = get_json_int(qos, "qd");
  return 0;
}

int parse_metrics_config(const json_t* root, const std::string& filepath) {
  json_t* metrics = json_object_get(root, "metrics");
  if (!metrics || !json_is_object(metrics)) {
    LOG(level_E::ERROR,
        "`metrics` block missing or not an object in: " + filepath);
    return -EINVAL;
  }
  try {
    MetricsInfo cfg;

    if (auto v = json_object_get(metrics, "domain")) {
      if (!json_is_string(v))
        throw MetricsParseError("metrics.domain must be string");
      cfg.domain = json_string_value(v);
    }
    if (auto v = json_object_get(metrics, "feature_id")) {
      if (!json_is_integer(v))
        throw MetricsParseError("metrics.feature_id must be integer");
      cfg.feature_id = json_integer_value(v);
    }
    if (auto v = json_object_get(metrics, "category")) {
      if (!json_is_string(v))
        throw MetricsParseError("metrics.category must be string");
      cfg.category = json_string_value(v);
    }
    if (auto v = json_object_get(metrics, "severity")) {
      if (!json_is_string(v))
        throw MetricsParseError("metrics.severity must be string");
      cfg.severity = json_string_value(v);
    }
    if (auto v = json_object_get(metrics, "source_type")) {
      if (!json_is_string(v))
        throw MetricsParseError("metrics.source_type must be string");
      cfg.source_type = json_string_value(v);
    }
    if (auto v = json_object_get(metrics, "power_state")) {
      if (!json_is_string(v))
        throw MetricsParseError("metrics.power_state must be string");
      cfg.power_state = json_string_value(v);
    }
    if (auto v = json_object_get(metrics, "interval_seconds")) {
      if (!json_is_integer(v))
        throw MetricsParseError("metrics.interval_seconds must be integer");
      cfg.interval_seconds = json_integer_value(v);
    }

    set_metrics_info(cfg);
    LOG(level_E::INFO, "Loaded metrics configuration from: " + filepath);
    return 0;
  } catch (const MetricsParseError& e) {
    LOG(level_E::ERROR,
        "Failed to parse 'metrics' block: " + std::string(e.what()));
    return -EIO;
  }
}

uint64_t get_epoch() {
  auto now = std::chrono::system_clock::now();
  return std::chrono::duration_cast<std::chrono::seconds>(
             now.time_since_epoch())
      .count();
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

std::string run_command(const std::string& cmd) {
  LOG(level_E::INFO, "Executing command: " + cmd);

  char buffer[4096];
  std::string result;

  FILE* pipe = popen(cmd.c_str(), "r");
  if (!pipe) {
    LOG(level_E::ERROR, "popen() failed for command: " + cmd);
    throw std::runtime_error(
        posix_err_to_json(EIO, "Failed to execute shell command"));
  }

  while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
    result += buffer;
  }

  int ret_code = pclose(pipe);
  if (ret_code != 0) {
    LOG(level_E::WARN,
        "Command returned non-zero exit code: " + std::to_string(ret_code));
  }

  return result;
}

uint64_t get_physical_cxl_address_from_python(const std::string& bdf) {
  std::string command = "python3 cxl_utils.py get_base_address " + bdf;
  FILE* pipe = popen(command.c_str(), "r");
  if (!pipe) {
    throw std::runtime_error("Failed to run Python script.");
  }
  char buffer[128];
  std::string result;
  while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
    result += buffer;
  }
  int status = pclose(pipe);
  if (status != 0) {
    throw std::runtime_error("Python script failed with non-zero exit code");
  }
  try {
    return std::stoull(result);
  } catch (...) {
    throw std::runtime_error(
        "Failed to parse address returned by Python script");
  }
}

RangeToNumaMap get_range_numa_map_from_lsmem() {
  return get_range_numa_map_from_lsmem("lsmem -o range,node -J");
}

RangeToNumaMap get_range_numa_map_from_lsmem(
    const std::string& cmd = "lsmem -o range,node -J") {
  LOG(level_E::INFO, "Invoking lsmem to retrieve memory range -> NUMA mapping");

  std::map<std::pair<uint64_t, uint64_t>, int> range_to_numa;
  std::string json_output;

  json_output = run_command(cmd);
  json_error_t error;
  json_t* root = json_loads(json_output.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::ERROR,
        "JSON parse error from lsmem output: " + std::string(error.text));
    throw std::runtime_error(
        posix_err_to_json(EINVAL, "Failed to parse lsmem JSON output"));
  }

  json_t* memory_array = json_object_get(root, "memory");
  if (!json_is_array(memory_array)) {
    json_decref(root);
    LOG(level_E::ERROR, "Missing or invalid 'memory' array in lsmem output");
    throw std::runtime_error(
        posix_err_to_json(EINVAL, "Invalid lsmem JSON structure"));
  }

  size_t index;
  json_t* entry;
  size_t valid_count = 0;

  json_array_foreach(memory_array, index, entry) {
    json_t* range_json = json_object_get(entry, "range");
    json_t* node_json = json_object_get(entry, "node");

    if (!json_is_string(range_json) || !json_is_integer(node_json)) continue;

    std::string range_str = json_string_value(range_json);
    int node = json_integer_value(node_json);

    size_t dash_pos = range_str.find('-');
    if (dash_pos == std::string::npos) continue;

    std::string start_hex = range_str.substr(0, dash_pos);
    std::string end_hex = range_str.substr(dash_pos + 1);

    try {
      uint64_t start = std::stoull(start_hex, nullptr, 16);
      uint64_t end = std::stoull(end_hex, nullptr, 16);
      range_to_numa[{start, end}] = node;
      valid_count++;

      LOG(level_E::DEBUG, "Parsed range 0x" + start_hex + " - 0x" + end_hex +
                              " mapped to NUMA node " + std::to_string(node));
    } catch (const std::exception& ex) {
      LOG(level_E::WARN, "Failed to parse memory range: " + range_str +
                             " at index " + std::to_string(index) + ": " +
                             ex.what());
      continue;
    }
  }

  json_decref(root);

  LOG(level_E::INFO, "Successfully loaded " + std::to_string(valid_count) +
                         " memory ranges from lsmem for NUMA mapping");

  return range_to_numa;
}

std::unordered_map<uint64_t, int> hdm_base_to_device_index;
void set_hdm_base_to_device_index(
    const std::unordered_map<uint64_t, int>& input_map) {
  hdm_base_to_device_index = input_map;
}

int get_hdm_base_to_device_index(uint64_t hdm_base) {
  auto it = hdm_base_to_device_index.find(hdm_base);
  if (it != hdm_base_to_device_index.end()) return it->second;
  return -1;
}

std::unordered_map<sc_id, sc_device, hash_sc_id> discover_cxl_devices_shared(
    const DevTypeMap& dev_hint_map) {
  std::unordered_map<sc_id, sc_device, hash_sc_id> device_map;

  struct pci_access* pacc = pci_alloc();
  pci_init(pacc);
  pci_scan_bus(pacc);

  for (pci_dev* dev = pacc->devices; dev; dev = dev->next) {
    pci_fill_info(dev, PCI_FILL_IDENT | PCI_FILL_BASES);

    uint16_t vendor = dev->vendor_id;
    uint16_t device = dev->device_id;
    // Build PCI BDF string
    char bdf[32];
    snprintf(bdf, sizeof(bdf), "%04x:%02x:%02x.%x", dev->domain, dev->bus,
             dev->dev, dev->func);
    std::string bdf_str(bdf);

    auto it = dev_hint_map.find({vendor, device, bdf_str});
    if (it == dev_hint_map.end()) continue;

    const DevJsonHints& hint = it->second;
    LOG(level_E::INFO, "Discovered CXL device: vendor=0x" + to_hex(vendor) +
                           " device=0x" + to_hex(device) +
                           " type=" + hint.vendor_device_type);

    // Link info from hints
    int link_speed = hint.lane_speed_GT_s;
    int link_width = hint.lane_width;

    // Get physical address and map to NUMA node
    uint64_t base_addr = 0;
    try {
      base_addr = get_physical_cxl_address_from_python(bdf_str);
    } catch (const std::exception& ex) {
      LOG(level_E::WARN, "Unable to resolve CXL physical address for BDF " +
                             bdf_str + ": " + ex.what());
    }

    const RangeToNumaMap& range_map = get_global_range_numa_map();
    int numa_node = find_numa_node_from_range_map(base_addr, range_map);
    if (numa_node < 0) {
      LOG(level_E::WARN, "Could not map address 0x" +
                             std::to_string(base_addr) +
                             " to NUMA node for device " + bdf_str);
    }

    // Memory info
    uint64_t total_mb = 1024, free_mb = 1024;
    if (numa_node >= 0) {
      get_numa_memory_info(numa_node, total_mb, free_mb);
    } else {
      LOG(level_E::WARN, "NUMA node unavailable for device at " + bdf_str);
    }

    // Generate 48-bit device ID
    uint64_t dev_id_val = generate_dev_id(vendor, device, dev->bus);
    sc_id scid(dev_id_val);

    // Construct sc_device
    sc_device scdev;
    scdev.d_set_dev_name("cmmh");
    scdev.d_set_capacity(total_mb);
    scdev.d_set_port(dev->dev);

    // Static info from hint
    DevStaticInfo static_info;
    static_info.device_id = dev_id_val;
    static_info.manufacturer = hint.manufacturer;
    static_info.serial_number = hint.serial_number;
    static_info.fw_revision = hint.fw_revision;
    static_info.location = bdf_str;
    static_info.total_capacity_MB = total_mb;
    static_info.feature_supported = hint.feature_supported;
    static_info.vendor_device_type = hint.vendor_device_type;
    static_info.cxl_device_type = hint.cxl_device_type;
    static_info.domain_id = dev->domain;
    static_info.domain_type = hint.domain_type;
    static_info.connection_type = hint.connection_type;
    static_info.mode_discovered = hint.mode_discovered;
    static_info.protocol = hint.protocol;
    static_info.link_speed_GT_s = link_speed;
    static_info.link_width = link_width;
    static_info.port_type = hint.port_type;
    static_info.capabilities = hint.capabilities;
    static_info.advertised_qos = hint.advertised_qos;
    static_info.bw_interval_sec = hint.bw_interval_sec;
    static_info.device_index = get_hdm_base_to_device_index(base_addr);

    // Dynamic info
    DevInfo dyn_info;
    dyn_info.static_info = static_info;
    dyn_info.available_capacity_MB = free_mb;
    dyn_info.numa_node = numa_node;
    dyn_info.status = hint.status;

    // Assign into sc_device
    scdev.d_set_static_info(static_info);
    scdev.d_set_dynamic_info(dyn_info);

    device_map[scid] = scdev;

    LOG(level_E::INFO, "Discovered device " + hint.vendor_device_type + " at " +
                           bdf_str + " NUMA=" + std::to_string(numa_node) +
                           " total=" + std::to_string(total_mb) +
                           "MB"
                           " free=" +
                           std::to_string(free_mb) + "MB");
  }

  pci_cleanup(pacc);
  LOG(level_E::INFO, "discover_cxl_devices_shared() completed. Found " +
                         std::to_string(device_map.size()) + " devices.");

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

int find_numa_node_from_range_map(uint64_t base_addr,
                                  const RangeToNumaMap& range_map) {
  LOG(level_E::INFO,
      "Finding NUMA node for base address: 0x" + std::to_string(base_addr));
  for (const auto& [range, node] : range_map) {
    LOG(level_E::DEBUG, "Checking range: 0x" + std::to_string(range.first) +
                            " - 0x" + std::to_string(range.second) +
                            ", for base: 0x" + std::to_string(base_addr) +
                            ", node: " + std::to_string(node));
    if (base_addr >= range.first && base_addr <= range.second) {
      LOG(level_E::INFO, "Matched! Returning node: " + std::to_string(node));
      return node;
    }
  }
  LOG(level_E::WARN, "No NUMA node match found for base address: 0x" +
                         std::to_string(base_addr));
  return -1;
}

static RangeToNumaMap global_range_numa_map;

void set_global_range_numa_map(const RangeToNumaMap& external_map) {
  global_range_numa_map = external_map;
  LOG(level_E::INFO, "Global range-to-NUMA map set with " +
                         std::to_string(external_map.size()) + " entries");
}

const RangeToNumaMap& get_global_range_numa_map() {
  return global_range_numa_map;
}

int get_numa_node_from_bdf(const std::string& bdf_str) {
  const RangeToNumaMap& range_map = get_global_range_numa_map();
  uint64_t base_addr = 0;
  try {
    base_addr = get_physical_cxl_address_from_python(bdf_str);
    LOG(level_E::DEBUG, "Resolved base address for " + bdf_str + ": " +
                            std::to_string(base_addr));

  } catch (const std::exception& ex) {
    LOG(level_E::WARN, "Unable to resolve CXL physical address for BDF " +
                           bdf_str + ": " + ex.what());
    return -1;
  }

  int numa_node = find_numa_node_from_range_map(base_addr, range_map);
  if (numa_node < 0) {
    LOG(level_E::WARN, "Could not map address " + std::to_string(base_addr) +
                           " to NUMA node for device " + bdf_str);
  }
  return numa_node;
}

std::string get_json_str(json_t* obj, const std::string& key,
                         const std::string& fallback) {
  json_t* val = json_object_get(obj, key.c_str());
  return (val && json_is_string(val)) ? json_string_value(val) : fallback;
}

int get_json_int(json_t* obj, const std::string& key, int fallback) {
  json_t* val = json_object_get(obj, key.c_str());
  return (val && json_is_integer(val)) ? json_integer_value(val) : fallback;
}

std::string to_hex(uint16_t val) {
  std::ostringstream oss;
  oss << std::hex << std::showbase << val;
  return oss.str();
}

static std::unordered_map<std::string, int> bdf_to_numa_map;
void set_bdf_to_numa_map(const std::unordered_map<std::string, int>& bdf_map) {
  bdf_to_numa_map = bdf_map;
}
