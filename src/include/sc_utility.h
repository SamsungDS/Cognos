#ifndef _UTILITY_H
#define _UTILITY_H

#include <numa.h>
#include <numaif.h>

#include <iostream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

/**
 * @brief Generates a structured JSON error response based on a POSIX error
 * code.
 *
 * This function maps standard POSIX error codes (e.g., EINVAL, ENOENT) to
 * human-readable messages and formats them into a JSON response.
 *
 * @param[in] error_code The standard POSIX error code.
 * @param[in] custom_message An optional custom error message that overrides the
 * default.
 * @return A JSON string representing the error response.
 *
 * @example Example usage:
 * @code
 * std::string response = generate_error_response(EINVAL, "Invalid device_id
 * format");
 *  // Output: {"rc": "EINVAL", "message": "Invalid device_id format"}
 *  @endcode
 */
std::string posix_err_to_json(int error_code,
                              const std::string& custom_message = "");

/**
 * @brief Parses a ID string and converts it to a uint64_t.
 *
 * This function attempts to convert the given string representation of
 * a ID into a uint64_t value. It handles potential errors such as
 * invalid formats and out-of-range values by returning a structured error
 * response.
 *
 * @param[in] id_str The input device ID as a string.
 * @param[out] id The parsed device ID as a uint64_t.
 * @param[out] error_response JSON-formatted error response in case of failure.
 * @return true if parsing was successful, false if an error occurred.
 */
bool str_to_int(const std::string& id_str, uint64_t& id,
                std::string& error_response);

/**
 * @brief Flattens a JSON array into a comma-separated string.
 *
 * This function processes a JSON string, ensuring that if it is a valid array,
 * all its elements are extracted and concatenated into a single comma-separated
 * string without additional list nesting. If the input is a JSON object, it is
 * returned as is. If the input is not valid JSON, an error code is returned.
 *
 * @param[in] json_str The input JSON string (either an array or an object).
 * @param[out] A flattened JSON string
 * @return status success or error code.
 */
int json_arr_to_str(const std::string& json_str, std::string& flattened_result);

/**
 * @brief Extracts a list of required parameters from the input map.
 *
 * This utility function checks whether all required keys are present in the
 * input parameter map. If any required key is missing, it generates an error
 * response using POSIX error format and returns false. Otherwise, it fills the
 * output map with corresponding key-value pairs.
 *
 * @param[in] input The full input parameter map (e.g., parsed from JSON).
 * @param[in] keys A list of required keys to check and extract from the input
 * map.
 * @param[out] output A map to be populated with key-value pairs for found keys.
 * @param[out] error_response A string containing the error message in JSON
 * format if any required key is missing.
 * @return true if all required keys are present and extracted; false otherwise.
 */
bool extract_required_params(
    const std::unordered_map<std::string, std::string>& input,
    const std::vector<std::string>& keys,
    std::unordered_map<std::string, std::string>& output,
    std::string& error_response);

/**
 * @brief Checks whether the device list in a JSON response is empty.
 *
 * This function parses the given JSON response string and looks for the
 * "devices" array. It then checks if the array exists and whether it contains
 * any elements. It is useful for validating whether any devices were returned
 * from a list operation.
 *
 * @param[in] json_response The JSON-formatted response string to inspect.
 * @return true if the "devices" array is missing, not an array, or has zero
 * entries.
 * @return false if the "devices" array exists and contains at least one device.
 */
bool is_device_list_empty(const std::string& json_response);

/** 
 * @brief Hash function for std::pair<uint16_t, uint16_t> 
 */
struct pairHash {
  std::size_t operator()(const std::pair<uint16_t, uint16_t>& p) const {
    return std::hash<uint16_t>()(p.first) ^
           (std::hash<uint16_t>()(p.second) << 1);
  }
};

// Type alias
using DevTypeMap =
    std::unordered_map<std::pair<uint16_t, uint16_t>, std::string, pairHash>;

/**
 * @brief Manually inject a device map (for library usage)
 */
void set_global_dev_type_map(const DevTypeMap& external_map);

/**
 * @brief Access the global device type map if already set
 */
const DevTypeMap* get_global_dev_type_map();

/**
 * @brief Loads the device type mapping from a CSV file, once per process.
 *
 * This function parses a CSV file containing device type mappings of the
 * format:
 * @code
 * device_type,vendor_id_hex,device_id_hex
 * @endcode
 * Example:
 * @code
 * CMM-H,1e98,0ddb
 * CMM-D,1b00,c001
 * @endcode
 *
 * It stores the result in a static map (singleton style) and sets the global
 * reference `global_dev_type_map`. On subsequent calls, it simply returns the
 * cached map without re-reading the file.
 *
 * This is intended to be called during system/plugin initialization.
 * In library mode, use `set_global_dev_type_map()` to inject a custom map
 * instead.
 *
 * @param filepath Absolute path to the CSV file (used only on first call)
 * @return Reference to the internally cached device type map
 */
const DevTypeMap& load_dev_type_mapping_csv(const std::string& filepath);

/**
 * @brief Get NUMA node memory capacity and free memory (in MB)
 */
inline bool get_numa_memory_info(int node_id, uint64_t& total_mb,
                                 uint64_t& free_mb) {
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

/**
 * @brief Validates that a CSV file exists and logs accordingly.
 * @param filepath Full path to the CSV file.
 * @return 0 if found, -ENOENT if not.
 */
int validate_csv_file(const std::string& filepath);

/**
 * @brief Parses a JSON file and checks whether the given key exists.
 * @param json_file Full path to the JSON file.
 * @param key Key to look up inside the file.
 * @param value Reference to string where the key's value will be stored.
 * @return 0 if key exists and value is extracted, otherwise -ENOENT or -EINVAL.
 */
int parse_json_key(const std::string& json_file, const std::string& key,
                   std::string& value);
#endif
