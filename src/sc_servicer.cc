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
#include "sc_cmmb.h"
#include "sc_cmmd.h"
#include "sc_cmmh.h"
#include "sc_dev_manager.h"
#include "sc_fm.h"
#include "sc_global.h"
#include "sc_logger.h"
#include "sc_mbox.h"
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
static DeviceManager* g_dev_mgr = nullptr;

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

/**
 * @brief Parses a JSON input string to extract command name and parameters.
 *
 * This method handles both modern and legacy JSON input formats.
 *
 * @param input_str JSON stringified input (must contain `command_name` key).
 * @param[out] command Extracted command name.
 * @param[out] params Flattened key-value pairs from "command_params" if
 * present.
 * @return true if JSON was parsed successfully and command was found, false
 * otherwise.
 */
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
  // Extract `command_name`
  json_t* command_json = json_object_get(root, "command_name");
  if (!command_json || !json_is_string(command_json)) {
    LOG(level_E::ERROR, "Missing or invalid 'command_name' in JSON request.");
    json_decref(root);
    return false;
  }
  command = json_string_value(command_json);
  LOG(level_E::INFO, "Extracted command_name: " + command);
  // Extract `command_params`
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
      } else {
        params[key] = json_dumps(value, JSON_COMPACT);
        LOG(level_E::INFO,
            "Param extracted (Non-string) - Key: " + std::string(key));
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
 * @brief provide direct attached host or switch setup such as hosts, devices,
 * endpoints.
 * @param input string having Cluster ID, Command, ID.
 * @return setup details as string.
 */
std::string SetupInfo(const std::string& input) {
  LOG(level_E::INFO, "SetupInfo called with input: " + input);
  std::string output;
  std::string buffer;
  std::unordered_map<std::string, std::string> tokens_map = token_helper(input);
  // Retrieve all sc_id keys from cxl_global
  std::vector<sc_id> fm_keys = cxl_global.get_fm_keys();
  output += "[";
  // Counter to track the number of FabricManagers parsed
  uint32_t fm_count = 0;
  // Iterate over each key, retrieve the FabricManager, and call setup_info
  for (auto& id : fm_keys) {
    FabricManager* manager = cxl_global.find_fm(id);
    if (manager) {
      LOG(level_E::INFO, "Calling setup_info for FabricManager ID: " +
                             std::to_string(id.get_sc_id()));
      size_t bytes_written = manager->setup_info(buffer);
      buffer.resize(bytes_written);
      if (fm_count > 0) {
        output += std::string(DELIMITER);
      }
      output += buffer;
      ++fm_count;
    }
  }
  output += "]";
  if (fm_count == 0) {
    LOG(level_E::WARN, "SetupInfo: No FabricManager found.");
  } else {
    LOG(level_E::INFO,
        "SetupInfo completed successfully. FabricManagers processed: " +
            std::to_string(fm_count));
  }
  return output;
}

void create_dev_cmmd(json_t* config) {
  // Allocate DevCMMD on the heap
  LOG(level_E::INFO, "Creating DevCMMD fabric manager...");
  DevCMMD* manager = new DevCMMD(config);
  cxl_global.add_fm(manager->get_fmid(), *manager);
  LOG(level_E::INFO, "Added DevCMMD to fabric manager map.");
}

void create_dev_cmmh(json_t* config) {
  // Allocate DevCMMH on the heap
  LOG(level_E::INFO, "Creating DevCMMH fabric manager...");
  DevCMMH* manager = new DevCMMH(config);
  cxl_global.add_fm(manager->get_fmid(), *manager);
  LOG(level_E::INFO, "Added DevCMMH to fabric manager map.");
}

void create_dev_cmmb(json_t* config) {
  // Allocate DevCMMB on the heap
  LOG(level_E::INFO, "Creating DevCMMB fabric manager...");
  DevCMMB* manager = new DevCMMB(config);
  cxl_global.add_fm(manager->get_fmid(), *manager);
  LOG(level_E::INFO, "Added DevCMMB to fabric manager map.");
}

const std::unordered_map<std::string, std::function<void(json_t*)>>
    factory_map = {{"FM_DIRECT_CMMD", create_dev_cmmd},
                   {"FM_DIRECT_CMMH", create_dev_cmmh},
                   {"FM_REMOTE_CMMB", create_dev_cmmb}};

/**
 * Helper function to create cmmb fabric manager map dynamically
 */
json_t* parse_input_config(std::string& buffer) {
  LOG(level_E::INFO, "Fetching setup info for CMMB fabric manager...");
  size_t bytes_written = cxl_global.fetch_setup_info(buffer);
  buffer.resize(bytes_written);
  json_error_t error;
  json_t* parsed_buffer = json_loads(buffer.c_str(), 0, &error);
  json_t* hosts = json_object_get(parsed_buffer, "Hosts");
  json_t* devices = json_object_get(parsed_buffer, "Devices");
  if (!hosts || !devices) {
    LOG(level_E::ERROR, "Missing 'Hosts' or 'Devices' in parsed JSON.");
    json_decref(parsed_buffer);
    return nullptr;
  }
  LOG(level_E::INFO, "Constructing CMMB fabric manager entry...");
  json_t* cmmb_fm = json_object();
  json_object_set_new(cmmb_fm, "id", json_integer(4004));
  json_object_set_new(cmmb_fm, "type", json_string("FM_REMOTE_CMMB"));
  json_object_set(cmmb_fm, "Hosts", hosts);
  json_object_set(cmmb_fm, "Devices", devices);
  LOG(level_E::INFO, "CMMB fabric manager entry constructed successfully.");
  json_decref(parsed_buffer);
  return cmmb_fm;
}

/**
 * @brief function would take each fabric_manager entry, check for a valid type
 *        and handle unknown types
 */
int process_fabric_manager(json_t* fabric_manager) {
  LOG(level_E::INFO, "Processing a fabric_manager entry...");
  json_t* type_json = json_object_get(fabric_manager, "type");
  if (!json_is_string(type_json)) {
    LOG(level_E::ERROR, "Missing or invalid 'type' field in fabric_manager.");
    return 1;
  }
  std::string type_str = json_string_value(type_json);
  LOG(level_E::INFO, "Fabric manager type detected: " + type_str);
  auto it = factory_map.find(type_str);
  if (it != factory_map.end()) {
    LOG(level_E::INFO,
        "Executing factory function for fabric manager type: " + type_str);
    it->second(fabric_manager);
  } else {
    LOG(level_E::ERROR, "Unknown fabric_manager type: " + type_str);
    return 2;
  }
  LOG(level_E::INFO, "Fabric manager processing completed.");
  return 0;
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

/**
 * @brief  Function to load the JSON config file with path availability check,
 *         error handling and return the json_t object
 */
json_t* direct_config(const std::string& input_config) {
  LOG(level_E::INFO, "Loading JSON configuration from: " + input_config);
  json_error_t error;
  json_t* config_json = json_load_file(input_config.c_str(), 0, &error);
  if (!config_json) {
    LOG(level_E::ERROR, "Error loading JSON file: " + std::string(error.text));
  }
  return config_json;
}

/**
 * @brief  load and validate the JSON structure, ensuring the file is correctly
 * parsed and contains a fabric_managers array
 */
json_t* load_json_config(const std::string& config_path) {
  LOG(level_E::INFO, "Loading JSON configuration: " + config_path);
  json_t* root = direct_config(config_path);
  if (!root || !json_is_object(root)) {
    LOG(level_E::ERROR,
        "Failed to load or parse configuration file: " + config_path);
    return nullptr;
  }
  json_t* fabric_managers = json_object_get(root, "fabric_managers");
  if (!json_is_array(fabric_managers)) {
    LOG(level_E::ERROR,
        "Invalid or missing `fabric_managers` array in configuration file: " +
            config_path);
    json_decref(root);
    return nullptr;
  }
  LOG(level_E::INFO,
      "Successfully loaded JSON configuration from: " + config_path);
  return root;
}

std::string handle_list_devices(
    const std::unordered_map<std::string, std::string>& params) {
  std::unordered_set<uint64_t> device_ids;
  std::string error;
  try {
    auto it = params.find("device_id");
    if (it != params.end()) {
      const std::string& value = it->second;
      // Handle array input: ["123", "456"]
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
      }
      // Handle single value input: "123"
      else {
        uint64_t id;
        if (!str_to_int(value, id, error)) {
          return error;
        }
        device_ids.insert(id);
      }
    }
  } catch (const std::exception& e) {
    LOG(level_E::ERROR,
        "Exception in handle_list_devices: " + std::string(e.what()));
    return posix_err_to_json(EIO, "Exception while parsing device_id");
  }
  // Empty set = return all devices
  std::string result = g_dev_mgr->list_devices(device_ids);
  if (!device_ids.empty() && is_device_list_empty(result)) {
    return posix_err_to_json(ENOENT, "No matching device IDs found");
  }
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
  return g_dev_mgr->get_device_info(device_id);
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

void fm_init() {
  LOG(level_E::INFO, "Initializing Fabric Manager...");
  if (is_file_empty_or_missing(INPUT_CONF_FILE)) {
    LOG(level_E::WARN,
        "Skipping Fabric Manager initialization due to missing or empty input "
        "config: " +
            std::string(INPUT_CONF_FILE));
    return;
  }
  LOG(level_E::INFO, "Loading Fabric Manager configuration...");
  json_t* root = load_json_config(INPUT_CONF_FILE);
  if (!root) {
    LOG(level_E::ERROR, "Error loading JSON configuration from " +
                            std::string(INPUT_CONF_FILE));
    return;
  }
  LOG(level_E::INFO, "Extracting `fabric_managers` array...");
  json_t* fabric_managers = json_object_get(root, "fabric_managers");
  std::string buffer;
  json_t* cmmb_fm = parse_input_config(buffer);
  if (cmmb_fm) {
    LOG(level_E::INFO,
        "Adding CMMB fabric manager to `fabric_managers` array.");
    json_array_append_new(fabric_managers, cmmb_fm);
  } else {
    LOG(level_E::ERROR,
        "CMMB fabric manager is null; skipping addition to `fabric_managers` "
        "array.");
  }
  size_t index;
  json_t* fabric_manager;
  json_array_foreach(fabric_managers, index, fabric_manager) {
    LOG(level_E::INFO, "Processing Fabric Manager " + std::to_string(index));
    if (process_fabric_manager(fabric_manager) != 0) {
      LOG(level_E::WARN,
          "Error processing Fabric Manager at index " + std::to_string(index));
      continue;
    }
  }
  LOG(level_E::INFO, "Fabric Manager initialization completed.");
  json_decref(root);
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
  fm_init();
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
    static DeviceManager mgr;
    g_dev_mgr = &mgr;
    // PluginManager plugin_mgr(g_dev_mgr);
    // plugin_mgr.loadAllPlugins();
    LOG(level_E::INFO, "All singletons initialized successfully.");
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
  *feat_id = feature_id::CXL;
  return SVK_STATUS_SUCCESS;
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
        return SVK_STATUS_FAIL;
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
    params = token_helper(input_str);
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
