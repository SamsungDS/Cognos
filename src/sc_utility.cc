#include "sc_utility.h"

#include <jansson.h>

#include <cerrno>
#include <iostream>
#include <sstream>
#include <unordered_map>

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
    {EINVAL, "EINVAL"}, {ENOENT, "ENOENT"}, {EIO, "EIO"},      {EPERM, "EPERM"},
    {EBUSY, "EBUSY"},   {ENOMEM, "ENOMEM"}, {ERANGE, "ERANGE"}

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
      std::cout << "I am in erange" << std::endl;
      message = "Value out of range";
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
