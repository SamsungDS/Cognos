#include "sc_utility.h"

#include <jansson.h>

#include <cerrno>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>

#include "sc_logger.h"

int json_arr_to_str(const std::string& json_str,
                    std::string& flattened_result) {
  LOG(level_E::INFO, "Flattening JSON array...");
  json_error_t error;
  json_t* root = json_loads(json_str.c_str(), 0, &error);
  if (!root) {
    LOG(level_E::ERROR, "JSON Parsing Error: " + std::string(error.text));
    return -EINVAL;
  }
  std::ostringstream oss;
  if (json_is_object(root)) {
    char* json_value = json_dumps(root, JSON_COMPACT);
    flattened_result = json_value;
    free(json_value);
    json_decref(root);
    return 0;
  } else if (json_is_array(root)) {
    // extract and flatten elements
    size_t index;
    json_t* value;
    json_array_foreach(root, index, value) {
      // Add comma only after the first element
      if (oss.tellp() > 0) oss << ",";
      char* json_value = json_dumps(value, JSON_COMPACT);
      oss << json_value;
      free(json_value);
    }
    json_decref(root);
    flattened_result = oss.str();
    return 0;
  }

  json_decref(root);
  // neither object nor array
  return -EINVAL;
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

const DevTypeMap& load_dev_type_mapping_csv(const std::string& filepath) {
  static DevTypeMap internal_map;
  static std::once_flag init_flag;

  std::call_once(init_flag, [&]() {
    std::ifstream infile(filepath);
    if (!infile.is_open()) {
      LOG(level_E::ERROR,
          "Failed to open device type mapping file: " + filepath);
      return;
    }

    std::string line;
    while (std::getline(infile, line)) {
      // skip comments, blank lines
      if (line.empty() || line[0] == '#') continue;
      std::istringstream ss(line);
      std::string type, vendor_str, device_str;

      if (std::getline(ss, type, ',') && std::getline(ss, vendor_str, ',') &&
          std::getline(ss, device_str, ',')) {
        try {
          uint16_t vendor = std::stoul(vendor_str, nullptr, 16);
          uint16_t device = std::stoul(device_str, nullptr, 16);
          internal_map[{vendor, device}] = type;
        } catch (const std::exception& ex) {
          LOG(level_E::WARN,
              "Failed to parse line: " + line + " — " + ex.what());
        }
      }
    }

    LOG(level_E::INFO, "Loaded " + std::to_string(internal_map.size()) +
                           " device ID mappings from: " + filepath);
    global_dev_type_map = &internal_map;
  });

  return *global_dev_type_map;
}

int validate_csv_file(const std::string& filepath) {
  if (std::filesystem::exists(filepath)) {
    LOG(level_E::INFO, "CSV file found: " + filepath);
    return 0;
  } else {
    LOG(level_E::ERROR, "CSV file missing: " + filepath);
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
