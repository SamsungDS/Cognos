#include <nlohmann/json.hpp>
#include <string>

using json = nlohmann::json;

bool validate_ras_nested_json(json& obj,
                              const std::string& dot_seperated_key_hierarchy) {
  char delimter = '.';
  // Find the delimiter in the key hierarchy
  size_t delim_pos = dot_seperated_key_hierarchy.find(delimter);

  // If the delimiter is found, recursively validate the nested JSON
  if (delim_pos != std::string::npos) {
    std::string key = dot_seperated_key_hierarchy.substr(0, delim_pos);
    std::string str_to_process =
        dot_seperated_key_hierarchy.substr(delim_pos + 1);

    // If the key exists in the JSON object, recursively validate the nested
    // JSON
    if (obj.contains(key)) {
      return validate_ras_nested_json(obj[key], str_to_process);
    } else {
      // Return false if the key does not exist
      return false;
    }
  } else {
    // If the delimiter is not found, check if the key exists in the JSON
    // object
    if (obj.contains(dot_seperated_key_hierarchy)) {
      return true;
    } else {
      return false;
    }
  }
}

bool validate_ras_json_request(
    json& params, const std::vector<std::string>& v_required_params) {
  // Iterate over the required parameters
  for (const auto& required_param : v_required_params) {
    // Validate each required parameter
    auto valid = validate_ras_nested_json(params, required_param);
    if (!valid) {
      return false;
    }
  }
  return true;
}
