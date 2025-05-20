#ifndef _UTILITY_H
#define _UTILITY_H

#include <numa.h>
#include <numaif.h>

#include <cstdint>
#include <iostream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "sc_device.h"
#include "sc_logger.h"

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
 * @brief Loads the device type mapping from a JSON file, once per process.
 *
 * This function reads a structured JSON file containing device type mappings in
 * the following format:
 *
 * @code
 * {
 * "device_map": [
 * { "device_type": "CMM-H", "vendor_id": "1e98", "device_id": "0ddb" },
 * { "device_type": "CMM-D", "vendor_id": "1b00", "device_id": "c001" }
 * ]
 * }
 * @endcode
 *
 * It parses the vendor ID and device ID (as hex strings) and maps them to the
 * corresponding device type string. The mapping is cached and only loaded once
 * during the process lifetime. On subsequent calls, it returns the cached
 * result.
 *
 * The map is stored in a global singleton-style reference for use by
 * discovery functions.
 *
 * @param filepath Absolute path to the JSON file containing device type
 * mappings.
 * @return Reference to the internally cached device type map.
 */
const DevTypeMap& load_dev_type_mapping_json(const std::string& filepath);

/**
 * @brief Get NUMA node memory capacity and free memory (in MB)
 */
bool get_numa_memory_info(int node_id, uint64_t& total_mb, uint64_t& free_mb);

/**
 * @brief Validates that a JSON file exists and logs accordingly.
 * @param filepath Full path to the JSON file.
 * @return 0 if found, -ENOENT if not.
 */
int validate_json_file(const std::string& filepath);

/**
 * @brief Parses a JSON file and checks whether the given key exists.
 * @param json_file Full path to the JSON file.
 * @param key Key to look up inside the file.
 * @param value Reference to string where the key's value will be stored.
 * @return 0 if key exists and value is extracted, otherwise -ENOENT or -EINVAL.
 */
int parse_json_key(const std::string& json_file, const std::string& key,
                   std::string& value);

/**
 * @brief Shared PCI-based device discovery logic.
 *
 * This utility function performs PCI enumeration, filters devices using the
 * given vendor/device ID map, and constructs a map of sc_device objects with
 * static and dynamic metadata. The caller is expected to handle device
 * registration and ownership after this function returns.
 *
 * @param dev_type_map Mapping of {vendor_id, device_id} to device type strings.
 * @return Map of discovered sc_device objects indexed by sc_id.
 */
std::unordered_map<sc_id, sc_device, hash_sc_id> discover_cxl_devices_shared(
    const DevTypeMap& dev_type_map);

/**
 * @brief Retrieves the NUMA node for a given PCI device based on its BDF
 * string.
 *
 * This function reads the `/sys/bus/pci/devices/<BDF>/numa_node` sysfs entry
 * to determine the NUMA node associated with the specified PCI device.
 *
 * @param bdf PCI address in the format "0000:xx:yy.z"
 * (domain:bus:device.function).
 * @return The NUMA node ID if found otherwise -1 if the file is missing or
 * unreadable.
 */
int get_numa_node_from_sysfs(const std::string& bdf);

/**
 * @brief Generate a 48-bit unique device ID
 */
uint64_t generate_dev_id(uint16_t vendor_id, uint16_t device_id, uint8_t bus);

#endif
