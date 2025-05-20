#include "sc_servicer.h"

#include <sys/stat.h>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <variant>
#include <vector>

#include "framework_downstream.h"
#include "sc_api_structs.h"
#include "sc_dev_manager.h"
#include "sc_global.h"
#include "sc_logger.h"
#include "sc_mbox.h"
#include "sc_plugin_manager.h"
#include "sc_utility.h"
#include "tuner.h"
#include "yaml-cpp/yaml.h"

extern "C" {
#include "mbox_a1.h"
}

constexpr char DELIMITER[] = ",";
using namespace std;
sc_global cxl_global;

// function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);
using CommandFuncMap = std::function<std::string(
    const std::unordered_map<std::string, std::string>&)>;

// Global tuner object
tuner mt_obj;

// GLobal DeviceManager for API access
DeviceManager* g_dev_mgr = nullptr;

/**
 * @brief Start Memory tuner
 * @param command string which includes memory tier params,
 * sla params, application params
 * @return status code of tuner start: 0 = success
 */
std::string StartTuning(const std::string& input) {
  unordered_map<string, string> tokens_map = token_helper(input);
  int ret;
  ret = mt_obj.tuner_start(tokens_map, PAGE_MOVER_DAMO);
  return to_string(ret);
}

/**
 * @brief Stop Memory tuner
 * @param command string
 * @return status code of tuner stop: 0 = success
 */
std::string StopTuning(const std::string& input) {
  unordered_map<string, string> tokens_map = token_helper(input);
  pair<string, unsigned long> tuner_context_key =
      make_pair(tokens_map["application"], stoul(tokens_map["application_id"]));
  int ret;
  ret = mt_obj.tuner_stop(tuner_context_key);
  return to_string(ret);
}

int init_log(const std::string& config_file) {
  try {
    if (!std::filesystem::exists(config_file)) {
      std::cerr << "Logger config file not found: " << config_file
                << ". Using default values." << std::endl;
      return -ENOENT;
    }

    boost::property_tree::ptree root;
    boost::property_tree::read_json(LOG_CONF_FILE, root);

    auto logger_info = root.get_child("cxl.logger");
    log_module_name = logger_info.get<std::string>("log_module_name",
                                                   CXL_LOG_MODULENAME_DEFAULT);
    std::string log_level_ =
        logger_info.get<std::string>("log_level", CXL_LOGGER_LEVEL_DEFAULT);
    std::string log_filename =
        logger_info.get<std::string>("log_file_name", CXL_LOG_FILENAME_DEFAULT);
    int log_file_count =
        logger_info.get<int>("log_file_count", CXL_LOGGER_FILE_COUNT_DEFAULT);
    uint64_t log_file_size = logger_info.get<uint64_t>(
        "log_file_size", CXL_LOGGER_FILE_SIZE_DEFAULT);
    std::string log_sink_type =
        logger_info.get<std::string>("sink_type", CXL_LOGGER_SINK_TYPE_DEFAULT);

    auto it = log_level_map.find(log_level_);
    if (it == log_level_map.end()) {
      std::cerr << "Invalid log level [" << log_level_
                << "], defaulting to INFO.\n";
      log_level_ = CXL_LOGGER_LEVEL_DEFAULT;
    }

    auto log_level_enum = log_level_map.at(log_level_);
    if (svk_logger_init(log_module_name.c_str(), log_filename.c_str(),
                        log_level_enum, log_file_count, log_file_size,
                        log_sink_type.c_str()) == 0) {
      return 0;
    } else {
      std::cerr << "SVK-CXL: Logger initialization failed.\n";
      return -EIO;
    }
  } catch (const std::exception& ex) {
    std::cerr << "Error initializing logger: " << ex.what() << std::endl;
    return -EFAULT;
  }
}

bool process_json_request(
    const std::string& input_str, std::string& command,
    std::unordered_map<std::string, std::string>& params) {
  LOG(level_E::INFO, "Processing JSON request.");
  json_error_t error;
  json_t* root = json_loads(input_str.c_str(), 0, &error);

  if (!root) {
    LOG(level_E::ERROR, "Failed to parse JSON: " + std::string(error.text));
    return false;
  }

  // Extract command_name
  json_t* command_json = json_object_get(root, "command_name");
  if (!command_json || !json_is_string(command_json)) {
    LOG(level_E::ERROR, "Missing or invalid 'command_name' in JSON request.");
    json_decref(root);
    return false;
  }
  command = json_string_value(command_json);
  LOG(level_E::INFO, "Extracted command_name: " + command);

  // Extract command_params
  json_t* params_json = json_object_get(root, "command_params");
  if (params_json && json_is_object(params_json)) {
    LOG(level_E::INFO, "Extracting command_params...");
    const char* key;
    json_t* value;

    json_object_foreach(params_json, key, value) {
      if (json_is_string(value)) {
        params[key] = json_string_value(value);
        LOG(level_E::INFO, "Param extracted - Key: " + std::string(key) +
                               ", Value: " + params[key]);
      } else if (json_is_integer(value)) {
        params[key] = std::to_string(json_integer_value(value));
        LOG(level_E::INFO, "Param extracted (integer) - Key: " +
                               std::string(key) + ", Value: " + params[key]);
      } else {
        // Fallback for arrays, booleans, objects
        params[key] = json_dumps(value, JSON_COMPACT);
        LOG(level_E::INFO,
            "Param extracted (JSON dump) - Key: " + std::string(key));
      }
    }
  } else {
    LOG(level_E::INFO, "No command_params found in JSON request.");
  }

  json_decref(root);
  LOG(level_E::INFO, "JSON request processed successfully.");
  return true;
}

/**
@brief Validate the format of an IPv4 address
@param ip_address - the IP address to validate
@return true if the IP address is valid, false otherwise
*/
bool is_valid_ip(const std::string& ip_address) {
  LOG(level_E::INFO, "Validating IP address: " + ip_address);
  std::string trimmed_ip = ip_address;
  // Trim whitespace
  trimmed_ip.erase(0, trimmed_ip.find_first_not_of(" \t\n\r"));
  trimmed_ip.erase(trimmed_ip.find_last_not_of(" \t\n\r") + 1);
  const std::regex ip_pattern(
      "(^(1[0-9]{0,2}|2[0-4][0-9]|25[0-5]|[1-9][0-9]?)\\."
      "(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\\."
      "(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\\."
      "(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)$)");
  bool is_valid = std::regex_match(trimmed_ip, ip_pattern);
  if (is_valid) {
    LOG(level_E::INFO, "IP address is valid.");
  } else {
    LOG(level_E::ERROR, "Invalid IP address format: " + ip_address);
  }
  return is_valid;
}

/**
 * @brief get the value of "ip_address" from the JSON file
 * @param filename - switch config file having ip_address
 * @return ip_address
 */
int get_ip_address(const std::string& filename, std::string& out_ip) {
  LOG(level_E::INFO, "Fetching IP address from: " + filename);
  json_error_t error;
  json_t* root = json_load_file(filename.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::ERROR, "Error loading JSON file: " + std::string(error.text));
    return -ENOENT;
  }
  json_t* switch_obj = json_object_get(root, "switch");
  if (!switch_obj || !json_is_object(switch_obj)) {
    LOG(level_E::ERROR,
        "`switch` key not found or not an object in config file: " + filename);
    json_decref(root);
    return -EINVAL;
  }
  json_t* ip_address = json_object_get(switch_obj, "ip_address");
  if (!ip_address) {
    LOG(level_E::ERROR,
        "`ip_address` key not found in config file: " + filename);
    json_decref(root);
    return -ENODATA;
  }

  if (!json_is_string(ip_address)) {
    LOG(level_E::ERROR,
        "`ip_address` is not a string in config file: " + filename);
    json_decref(root);
    return -EINVAL;
  }

  std::string ip_value = json_string_value(ip_address);
  if (!is_valid_ip(ip_value)) {
    LOG(level_E::ERROR, "Invalid IP address format: " + ip_value);
    json_decref(root);
    return -EINVAL;
  }
  out_ip = ip_value;
  json_decref(root);
  return 0;
}

/**
 * @brief tokenize input based on ';' and generate key values.
 * @param input - input string having Cluster ID, Command, Device ID etc.
 * @return tokens unordered map
 */
const std::unordered_map<std::string, std::string> tokenize(std::string input) {
  LOG(level_E::INFO, "Parsing tokens from input string: " + input);
  char* s = (char*)input.c_str();
  char* tok = strtok(s, ";");
  char key[256], val[256];
  static std::unordered_map<std::string, std::string> tokens;
  while (tok != NULL) {
    sscanf(tok, "%[a-zA-Z0-9_]=%[/a-zA-Z0-9]", key, val);
    tokens[key] = val;
    tok = strtok(NULL, ";");
  }
  LOG(level_E::INFO, "Tokenization complete. Parsed " +
                         std::to_string(tokens.size()) + " tokens.");
  return tokens;
}

/**
 * @brief tokenization helper function which invokes tokenize function.
 * @param input - input string having Cluster ID, Command, Device ID etc.
 * @return tokens unordered map
 */
const std::unordered_map<std::string, std::string> token_helper(
    std::string input) {
  LOG(level_E::INFO, "Tokenizing input string...");
  return tokenize(input);
}

/**
 * @brief ListDevices - invokes list_devices function of Device Class.
 * @param input string having Cluster ID, Command, FM_ID, FM_Endpoint.
 * @return output CXL devices info in json string.
 */
std::string ListDevices(const std::string& input) {
  LOG(level_E::INFO, "ListDevices called with input: " + input);
  std::string output = "";
  std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
  std::string buffer;
  size_t bytes_written = cxl_global.list_devices(buffer);
  buffer.resize(bytes_written);
  output += buffer;
  LOG(level_E::INFO, "ListDevices completed successfully.");
  return output;
}

/**
 * @brief ListHosts - invokes list_hosts function of Device Class.
 * @param input string having Cluster ID, Command, ID.
 * @return output Hosts list in json string.
 */
std::string ListHosts(const std::string& input) {
  LOG(level_E::INFO, "ListHosts called with input: " + input);
  std::string output = "";
  std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
  std::string buffer;
  size_t bytes_written = cxl_global.list_hosts(buffer);
  buffer.resize(bytes_written);
  output += buffer;
  LOG(level_E::INFO, "ListHosts completed successfully.");
  return output;
}

/**
 * @brief attach device to host.
 * @param input string having Cluster ID, Command, device_id, host_id & mode.
 * @return output Success/Failure in json string.
 */
std::string AttachMemory(const std::string& input) {
  LOG(level_E::INFO, "AttachMemory called with input: " + input);
  std::string output = "";
  std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
  if (tokens_map.find("dev_id") == tokens_map.end() ||
      tokens_map.find("host_id") == tokens_map.end() ||
      tokens_map.find("mode") == tokens_map.end()) {
    LOG(level_E::ERROR, "AttachMemory: Missing required parameters in input.");
    return "";
  }
  std::string buffer;
  //@todo fm_id 203, 204
  size_t bytes_written = cxl_global.dev_attach(stoull(tokens_map["dev_id"]),
                                               stoull(tokens_map["host_id"]),
                                               tokens_map["mode"], 203, buffer);
  buffer.resize(bytes_written);
  output += buffer;
  LOG(level_E::INFO, "AttachMemory completed successfully.");
  return output;
}

/**
 * @brief detach device from host.
 * @param input string having Cluster ID, Command, device_id, host_id & mode.
 * @return output Success/Failure in json string.
 */
std::string DetachMemory(const std::string& input) {
  LOG(level_E::INFO, "DetachMemory called with input: " + input);
  std::string output = "";
  std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
  if (tokens_map.find("dev_id") == tokens_map.end() ||
      tokens_map.find("host_id") == tokens_map.end() ||
      tokens_map.find("mode") == tokens_map.end()) {
    LOG(level_E::ERROR, "DetachMemory: Missing required parameters in input.");
    return "";
  }
  std::string buffer;
  size_t bytes_written = cxl_global.dev_detach(stoull(tokens_map["dev_id"]),
                                               stoull(tokens_map["host_id"]),
                                               tokens_map["mode"], 203, buffer);
  buffer.resize(bytes_written);
  output += buffer;
  LOG(level_E::INFO, "DetachMemory completed successfully.");
  return output;
}

/**
 * @brief provide switch setupinfo such as hosts, devices,
 * endpoints.
 * @param input string having Cluster ID, Command, ID.
 * @return setup details as string.
 */
std::string SetupInfo(const std::string& input) {
  LOG(level_E::INFO, "SetupInfo called with input: " + input);
  std::string output;
  std::string buffer;
  std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
  LOG(level_E::INFO, "Fetching setup info for CMMB...");
  // Call global function to fetch setup info
  size_t bytes_written = cxl_global.fetch_setup_info(buffer);
  buffer.resize(bytes_written);
  output = buffer;
  LOG(level_E::INFO, "SetupInfo completed successfully.");
  return output;
}

bool is_file_empty_or_missing(const std::string& file_path) {
  struct stat file_stat;
  LOG(level_E::INFO, "Checking if file exists and is non-empty: " + file_path);
  if (stat(file_path.c_str(), &file_stat) != 0) {
    LOG(level_E::ERROR, "Cannot access file: " + file_path);
    return true;
  }
  if (file_stat.st_size == 0) {
    LOG(level_E::ERROR, "File is empty: " + file_path);
    return true;
  }
  LOG(level_E::INFO, "File check passed: " + file_path);
  return false;
}

std::string handle_list_devices(
    const std::unordered_map<std::string, std::string>& params) {
  std::unordered_set<uint64_t> device_ids;
  std::string error;

  try {
    auto it = params.find("device_id");
    if (it != params.end()) {
      const std::string& value = it->second;

      if (!value.empty() && value.front() == '[' && value.back() == ']') {
        json_error_t jerr;
        json_t* arr = json_loads(value.c_str(), 0, &jerr);
        if (!arr || !json_is_array(arr)) {
          return posix_err_to_json(EINVAL, "Invalid device_id array format");
        }

        size_t index;
        json_t* val;
        json_array_foreach(arr, index, val) {
          if (json_is_string(val)) {
            uint64_t id;
            std::string err;
            if (str_to_int(json_string_value(val), id, err)) {
              device_ids.insert(id);
            } else {
              json_decref(arr);
              return err;
            }
          } else {
            json_decref(arr);
            return posix_err_to_json(EINVAL,
                                     "device_id array must contain strings");
          }
        }
        json_decref(arr);
      } else {
        uint64_t id;
        if (!str_to_int(value, id, error)) return error;
        device_ids.insert(id);
      }
    }
  } catch (const std::exception& e) {
    LOG(level_E::ERROR,
        "Exception in handle_list_devices: " + std::string(e.what()));
    return posix_err_to_json(EIO, "Exception while parsing device_id");
  }

  std::vector<sc_device> devices = device_ids.empty()
                                       ? g_dev_mgr->list_devices()
                                       : g_dev_mgr->list_devices(device_ids);

  // Return early if filtered but got no matching devices
  if (!device_ids.empty() && devices.empty()) {
    return posix_err_to_json(ENOENT, "No matching device IDs found");
  }

  // Serialize response
  json_t* root = json_object();
  json_t* array = json_array();
  for (const auto& dev : devices) {
    DevInfo info = dev.to_device_info();
    json_t* obj = json_object();
    json_object_set_new(obj, "device_id",
                        json_integer(info.static_info.device_id));
    json_object_set_new(
        obj, "vendor_device_type",
        json_string(info.static_info.vendor_device_type.c_str()));
    json_object_set_new(obj, "pcie_addr",
                        json_string(info.static_info.location.c_str()));
    json_array_append_new(array, obj);
  }
  json_object_set_new(root, "devices", array);
  char* json_str = json_dumps(root, JSON_COMPACT);
  std::string result(json_str);
  free(json_str);
  json_decref(root);
  return result;
}

std::string handle_get_device_info(
    const std::unordered_map<std::string, std::string>& params) {
  std::unordered_map<std::string, std::string> values;
  std::string error;
  if (!extract_required_params(params, {"device_id"}, values, error)) {
    return error;
  }
  uint64_t device_id;
  if (!str_to_int(values["device_id"], device_id, error)) {
    return error;
  }
  std::optional<DevInfo> info = g_dev_mgr->get_device_info(device_id);
  if (!info.has_value()) {
    return posix_err_to_json(ENOENT, "Device not found or error occurred");
  }
  const DevInfo& dev = info.value();
  json_t* root = json_object();
  json_object_set_new(root, "api_version", json_real(1.0));
  // Static fields
  json_object_set_new(root, "device_id",
                      json_integer(dev.static_info.device_id));
  json_object_set_new(root, "manufacturer",
                      json_string(dev.static_info.manufacturer.c_str()));
  json_object_set_new(root, "serial_number",
                      json_integer(dev.static_info.serial_number));
  json_object_set_new(root, "FW_revision",
                      json_string(dev.static_info.fw_revision.c_str()));
  json_object_set_new(root, "location",
                      json_string(dev.static_info.location.c_str()));
  json_object_set_new(root, "total_capacity_MB",
                      json_integer(dev.static_info.total_capacity_MB));
  json_object_set_new(root, "feature_supported",
                      json_string(dev.static_info.feature_supported.c_str()));
  json_object_set_new(root, "vendor_device_type",
                      json_string(dev.static_info.vendor_device_type.c_str()));
  json_object_set_new(root, "cxl_device_type",
                      json_string(dev.static_info.cxl_device_type.c_str()));
  json_object_set_new(root, "protocol",
                      json_string(dev.static_info.protocol.c_str()));
  json_object_set_new(root, "port_type",
                      json_string(dev.static_info.port_type.c_str()));
  json_object_set_new(root, "mode_discovered",
                      json_string(dev.static_info.mode_discovered.c_str()));
  json_object_set_new(root, "connection_type",
                      json_string(dev.static_info.connection_type.c_str()));
  json_object_set_new(root, "domain_type",
                      json_string(dev.static_info.domain_type.c_str()));
  json_object_set_new(root, "domain_id",
                      json_integer(dev.static_info.domain_id));
  json_object_set_new(root, "link_speed",
                      json_integer(dev.static_info.link_speed));
  json_object_set_new(root, "link_width",
                      json_integer(dev.static_info.link_width));

  // Dynamic fields
  json_object_set_new(root, "available_capacity_MB",
                      json_integer(dev.available_capacity_MB));
  json_object_set_new(root, "status", json_string(dev.status.c_str()));
  json_object_set_new(root, "aspm_active", json_boolean(dev.aspm_active));
  json_object_set_new(root, "sris_active", json_boolean(dev.sris_active));
  json_object_set_new(root, "lock_active", json_boolean(dev.lock_active));
  json_object_set_new(root, "numa_attached", json_integer(dev.numa_attached));
  // Capabilities
  json_t* caps = json_object();
  json_object_set_new(
      caps, "Power Management version",
      json_integer(dev.static_info.capabilities.power_management_version));
  json_object_set_new(root, "capabilities", caps);
  // QoS
  json_t* qos = json_object();
  json_object_set_new(qos, "avg_latency",
                      json_real(dev.static_info.advertized_qos.avg_latency));
  json_object_set_new(qos, "p99_latency",
                      json_real(dev.static_info.advertized_qos.p99_latency));
  json_object_set_new(qos, "io_per_sec",
                      json_real(dev.static_info.advertized_qos.io_per_sec));
  json_object_set_new(qos, "BW_per_sec",
                      json_real(dev.static_info.advertized_qos.bw_per_sec));
  json_object_set_new(qos, "io_size",
                      json_real(dev.static_info.advertized_qos.io_size));
  json_object_set_new(qos, "qd", json_real(dev.static_info.advertized_qos.qd));
  json_object_set_new(root, "advertized_qos", qos);
  // Finalize JSON
  char* json_str = json_dumps(root, JSON_COMPACT);
  std::string result(json_str);
  free(json_str);
  json_decref(root);
  return result;
}

int cmmb_a1_init() {
  LOG(level_E::INFO, "Starting `cmmb_a1_init`...");
  struct StaticPortInfo pinfo;
  std::string ip_address;

  int ip_status = get_ip_address(CXL_CONF_FILE, ip_address);
  if (ip_status != 0) {
    switch (ip_status) {
      case -ENOENT:
        LOG(level_E::ERROR,
            "Config file not found: " + std::string(CXL_CONF_FILE));
        break;
      case -EINVAL:
        LOG(level_E::ERROR,
            "Invalid config file format in: " + std::string(CXL_CONF_FILE));
        break;
      case -ENODATA:
        LOG(level_E::ERROR,
            "Missing IP address in config file: " + std::string(CXL_CONF_FILE));
        break;
      default:
        LOG(level_E::ERROR, "Unknown error retrieving IP from config: " +
                                std::string(CXL_CONF_FILE) +
                                ", Error code: " + std::to_string(ip_status));
        break;
    }
    return ip_status;
  }

  set_ip(ip_address.c_str());
  init();
  LOG(level_E::INFO, "Fetching `mbox_get_static_config`...");
  mbox_get_static_config(&pinfo);
  LOG(level_E::INFO, "Creating memory box...");
  if (int mret = cxl_global.g_create_mbox(&pinfo); mret != 0) {
    LOG(level_E::ERROR, "Error creating memory box: " + std::to_string(mret));
    return mret;
  }
  LOG(level_E::INFO, "Memory box created successfully.");
  return 0;
}

/**
 * @brief init tm functionality
 * @details As cxl cleanup is not called,
 * deleting left over config files explicitly.
 */
void tm_init() {
  /*clean up cgroup
  TODO: Cgroup delete needs yaml parsing
  ret = cgroup_delete();
  */
  damo_global_config_cleanup();
}

/**
 * @brief init function
 * @details This function will be triggered first for any requests from client
 * side.
 */
int init_cxl_plugin() {
  LOG(level_E::INFO, "Invoked `init_cxl_plugin`.");
  int mret = cmmb_a1_init();
  LOG(level_E::INFO,
      "CMMB A1 initialization returned: " + std::to_string(mret));
  // fm_init();
  tm_init();
  return mret;
}

/**
 * ########################################
 * # Start SVK Core Framework Integration #
 * ########################################
 */

/**
 * @brief Initialize individual feature module
 *
 * This will be called when individual feature module will be loaded by
 * framework.
 * @return svk_status  Refer to framework_struct.h for return codes
 */
svk_status initialize(void*) {
  int log_status = init_log(LOG_CONF_FILE);
  // Translate POSIX error codes to SVK status enums
  switch (log_status) {
    case 0:
      LOG(level_E::INFO, "Logger initialized for module: " + log_module_name);
      break;  // success, continue execution
    case -ENOENT:
      LOG(level_E::ERROR, "Log configuration file missing.");
      return SVK_STATUS_INVALID_CONFIG;
    case -EINVAL:
      LOG(level_E::ERROR, "Invalid Log configuration.");
      return SVK_STATUS_INVALID_CONFIG;
    default:
      LOG(level_E::ERROR, "Unexpected error initializing logger: " +
                              std::to_string(log_status));
      return SVK_STATUS_FAIL;
  }

  if (init_cxl_plugin() == 0) {
    LOG(level_E::INFO, "CXL plugin initialized successfully.");
  } else {
    LOG(level_E::ERROR, "CXL plugin initialization failed.");
    return SVK_STATUS_FAIL;
  }

  try {
    std::string plugin_dir;
    int plugin_path_status =
        parse_json_key(CXL_CONF_FILE, "plugin_dir", plugin_dir);
    if (plugin_path_status != 0) {
      LOG(level_E::ERROR, "Plugin directory not configured or invalid.");
      return SVK_STATUS_FAIL;
    }

    int json_status = validate_json_file(CXL_ID_TYPE_MAP_FILE);
    if (json_status != 0) {
      LOG(level_E::ERROR, "Device ID mapping JSON not found.");
      return SVK_STATUS_FAIL;
    }
    // Load and cache device type map globally
    const auto& map = load_dev_type_mapping_json(CXL_ID_TYPE_MAP_FILE);
    set_global_dev_type_map(map);
    static DeviceManager mgr;
    g_dev_mgr = &mgr;
    static PluginManager plugin_mgr(mgr);
    plugin_mgr.loadAllPlugins(plugin_dir);
    mgr.discover_devices();
    LOG(level_E::INFO,
        "Device Discovery is completed successfully from `init`.");
  } catch (const std::exception& e) {
    LOG(level_E::ERROR, "Initialization failed: " + std::string(e.what()));
    return SVK_STATUS_FAIL;
  }

  return SVK_STATUS_SUCCESS;
}

/*
 * Feature modules set feature_id to the *feat_id pointer if
 * it isn't set already.
 * SVK command framework will call this function to get the feature names
 * this feature module will support.
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status get_supported_feature_list(feature_id* feat_id, char*) {
  LOG(level_E::INFO, "get_supported_feature_list function called.");
  //*feat_id = feature_id::CXL;
  return SVK_STATUS_FAIL;
}

/**
 * @brief Check if license is valid
 * Every request needs to validate if license is valid before moving on
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status is_license_valid(void*) {
  LOG(level_E::INFO, "is_license_valid function called.");
  // License validation logic can be added here
  return SVK_STATUS_SUCCESS;
}

/**
 * @brief API for feature modules that need to access/initialize a device
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status configure_device_if_any(void*, svk_device_ctx*, uint64_t length,
                                   void*) {
  LOG(level_E::INFO, "configure_device_if_any function called with length: " +
                         std::to_string(length));
  return SVK_STATUS_SUCCESS;
}

/**
@brief Command mapping for New API execution.
*/
const std::unordered_map<std::string, CommandFuncMap> command_map = {
    {"list_devices", handle_list_devices},
    {"get_device_info", handle_get_device_info}};

/**
 * @brief Dispatches a command to its corresponding legacy handler function.
 *
 * This function maps legacy-style API commands to their corresponding handler
 * functions defined in `fw_hooks` and invokes the appropriate function.
 *
 * @param command Name of the command to execute (e.g., "SetupInfo").
 * @param input_str Raw input string passed to the legacy handler.
 * @return JSON string result from the legacy API handler. Returns an error JSON
 * if the command is unknown.
 */
std::string dispatch_fw_hook_command(const std::string& command,
                                     const std::string& input_str) {
  static const std::unordered_map<std::string, CommandFunc> fw_hooks = {
      {"ListDevices", ListDevices},   {"ListHosts", ListHosts},
      {"SetupInfo", SetupInfo},       {"AttachMemory", AttachMemory},
      {"DetachMemory", DetachMemory}, {"StartTuning", StartTuning},
      {"StopTuning", StopTuning}};

  auto it = fw_hooks.find(command);
  if (it == fw_hooks.end()) {
    LOG(level_E::ERROR, "Command not found in fw_hooks: " + command);
    return posix_err_to_json(ENOSYS, "Unsupported command: " + command);
  }

  return it->second(input_str);
}

/**
 * @brief Executes API commands synchronously for both old and new formats.
 *
 * This function supports:
 * 1. Modern API style (JSON with `command_params`)
 * 2. Legacy JSON API (stringified JSON without `command_params`)
 * 3. Legacy flat style (semicolon-delimited string)

 * @param pass_thru svk passthrough for command info communication from top
 * level
 * @param input Input buffer containing the request payload
 * @param output Output buffer where the response will be stored
 * @return svk_status, Refer to framework_struct.h for return codes*
*/
svk_status execute_sync(svk_pass_thru_cmd*, svk_input* input,
                        svk_output* output) {
  LOG(level_E::INFO, "execute_sync function called.");
  if (!input || !output) {
    LOG(level_E::ERROR, "execute_sync received null input/output buffers.");
    return SVK_STATUS_FAIL;
  }
  std::string input_str(reinterpret_cast<char*>(input->input_buffer),
                        input->len);
  LOG(level_E::INFO, "Received API Request: " + input_str);
  std::string result;
  std::unordered_map<std::string, std::string> params;
  std::string command;
  try {
    if (!process_json_request(input_str, command, params)) {
      throw std::invalid_argument("Invalid JSON format");
    }
    LOG(level_E::INFO, "Parsed JSON command: " + command);
    // New style JSON with params
    if (!params.empty()) {
      auto it = command_map.find(command);
      if (it == command_map.end()) {
        LOG(level_E::ERROR, "Command not found in command_map: " + command);
        // convert to legacy flat string and throw to trigger fallback
        std::string flat;
        for (const auto& [k, v] : params) {
          flat += k + "=" + v + ";";
        }
        if (!flat.empty() && flat.back() == ';') {
          flat.pop_back();  // remove trailing semi
        }
        // fallback will handle string
        throw std::runtime_error(flat);
      }
      result = it->second(params);
    } else {
      // Old JSON without params
      result = dispatch_fw_hook_command(command, input_str);
    }
  } catch (const std::exception& e) {
    LOG(level_E::WARN, "Falling back to legacy flat API parsing due to: " +
                           std::string(e.what()));
    // Legacy flat style
    // If runtime_error was thrown with a flattened string
    std::string flat_input = input_str;
    const auto* re = dynamic_cast<const std::runtime_error*>(&e);
    if (re) {
      // flattened key-value pair
      flat_input = re->what();
      LOG(level_E::INFO,
          "Using flattened string from exception: " + flat_input);
    }
    params = token_helper(flat_input);
    if (params.find("command") == params.end()) {
      LOG(level_E::ERROR, "Missing 'command' in legacy flat request.");
      return SVK_STATUS_FAIL;
    }
    command = params["command"];
    result = dispatch_fw_hook_command(command, input_str);
  }
  output->output_buffer = reinterpret_cast<uint8_t*>(strdup(result.c_str()));
  output->len = result.size();
  output->status = SVK_STATUS_SUCCESS;
  LOG(level_E::INFO, "execute_sync completed successfully.");
  return SVK_STATUS_SUCCESS;
}

/**
 * @brief Feature module async execute implementation.
 *
 * @param pass_thru       svk passthrough for command info communication from
 * top level
 * @param input           input buffer struct
 * @param postprocess_fn  struct containing pointers for async IO, such as
 * callback, IO identifier, and output buffer
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status execute_async(svk_pass_thru_cmd*, svk_postprocess_fn*) {
  LOG(level_E::INFO, "execute_async function called.");
  return SVK_STATUS_SUCCESS;
}

/**
 * @brief Usual cleanup before exit
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status clean_up(void*) {
  LOG(level_E::INFO, "clean_up function called.");
  return SVK_STATUS_SUCCESS;
}

/**
 * ######################################
 * # END SVK Core Framework Integration #
 * ######################################
 */
