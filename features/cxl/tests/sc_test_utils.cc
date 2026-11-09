#include "sc_test_utils.h"

#include <jansson.h>

#include <iostream>

std::string get_json_value(const std::string& json_str,
                           const std::string& key) {
  json_error_t error;
  std::string result;
  json_t* root = json_loads(json_str.c_str(), 0, &error);
  if (!root) {
    result = "";
  }
  json_t* value = json_object_get(root, key.c_str());
  if (!value) {
    result = "";
  }
  std::cout << "input " << json_str.c_str() << std::endl;
  // If value is an array, return its string representation
  if (json_is_array(value)) {
    char* json_str = json_dumps(value, JSON_COMPACT);
    result = json_str ? json_str : "";
    std::cout << "its an array , result: " << result << std::endl;
    free(json_str);
  } else if (json_is_string(value)) {
    result = json_string_value(value);
  } else if (json_is_integer(value)) {
    result = std::to_string(json_integer_value(value));
  }

  json_decref(root);
  std::cout << "final return value " << result << std::endl;
  return result;
}
