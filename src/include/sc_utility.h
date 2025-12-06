#ifndef _UTILITY_H
#define _UTILITY_H

#include <jansson.h>
#include <numa.h>
#include <numaif.h>

#include <cstdint>
#include <iostream>
#include <map>
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


struct TupleHash {
    std::size_t operator()(const std::tuple<uint16_t, uint16_t, std::string>& t) const noexcept {
        // Simple hash combination technique (implement a robust one if needed)
        std::size_t h1 = std::hash<unsigned short>{}(std::get<0>(t));
        std::size_t h2 = std::hash<unsigned short>{}(std::get<1>(t));
        std::size_t h3 = std::hash<std::string>{}(std::get<2>(t));

        // Combine the hashes (e.g., using a simple xor combination)
        return h1 ^ (h2 << 1) ^ (h3 << 2);
    }
};

/**
 * @typedef DevTypeMap
 * @brief Maps (vendor_id, device_id) → full device metadata from JSON config.
 *
 * This map is populated from the device mapping JSON file at startup in real
 * mode. Each entry contains structured metadata (via DevJsonHints) used to
 * enrich hardware-discovered CXL devices with additional information such as:
 * - Device type name (e.g. "CMMD", "CMMH")
 * - PCIe link configuration (lane speed, lane width)
 * - Vendor information (manufacturer, serial number, firmware revision)
 * - CXL protocol details (type, mode, connection type, domain type)
 * - QoS and capability attributes
 *
 * Example:
 * @code
 * {
 * {0x8086, 0x0A54} → DevJsonHints{ vendor_device_type = "CMMD", link_speed =
 * 32, ... }, {0x1234, 0x5678} → DevJsonHints{ vendor_device_type = "CMMH",
 * link_speed = 16, ... }
 * }
 * @endcode
 */
using DevTypeMap =
    std::unordered_map<std::tuple<uint16_t, uint16_t, std::string>, DevJsonHints, TupleHash>;

/**
 * @brief Inject an external device type map (used when calling the library
 * directly).
 * @param external_map A map from {vendor_id, device_id} to device_type string.
 *
 * Example:
 * DevTypeMap map;
 * map[{0x8086, 0x0A54}] = "CMMD";
 * set_dev_type_map(map);
 */
void set_dev_type_map(const DevTypeMap& external_map);

/**
 * @brief Access the global device type map if already set
 */
const DevTypeMap* find_dev_type_map();

/**
 * @brief Load CXL device mapping JSON file and populate DevHintMap.
 *
 * This function reads the JSON file containing CXL device hints and populates
 * a map from (vendor_id, device_id) to DevJsonHints. It is used in real mode
 * to enrich PCIe-discovered devices with static metadata such as link config,
 * vendor info, protocol, capabilities, and QoS metrics.
 *
 * @param filepath Path to the device mapping JSON file.
 * @return 0 on success, -EINVAL if the file is invalid or malformed,
 * -ERANGE if a vendor/device ID or serial conversion fails.
 */

int load_dev_type_mapping_json(const std::string& filepath);

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
 * @brief Generate a 48-bit unique device ID
 */
uint64_t generate_dev_id(uint16_t vendor_id, uint16_t device_id, uint8_t bus);

using RangeToNumaMap = std::map<std::pair<uint64_t, uint64_t>, int>;

/**
 * @brief Retrieves a NUMA range-to-node mapping from the system's `lsmem`
output.
 *
 * This is a convenience wrapper that uses the default command
`* lsmem -o range,node -J` to extract memory address ranges and their
 * associated NUMA node IDs. Internally, it delegates to the overloaded
 * function that takes a command string.
 *
 * @return RangeToNumaMap A mapping of memory address ranges to NUMA nodes.
 */
RangeToNumaMap get_range_numa_map_from_lsmem();

/**
 * @brief Parses the memory range-to-NUMA mapping from `lsmem -o range,node -J`.
 *
 * This function runs the `lsmem` command in JSON output mode to obtain
 * memory ranges and their associated NUMA nodes. It then parses the JSON output
 * using the Jansson library and constructs a map where each key is a
 * (start_addr, end_addr) range and the value is the corresponding NUMA node.
 *
 * This mapping is used to determine the NUMA node for a CXL device based on
 * its memory-mapped address.
 *
 * @return A map from memory address ranges (start, end) to NUMA node indices.
 *
 * @throws std::runtime_error If the JSON output cannot be parsed.
 */
RangeToNumaMap get_range_numa_map_from_lsmem(const std::string& cmd);

/**
 * @brief Finds the NUMA node for a given device base address using a range map.
 *
 * This function searches the provided memory range-to-NUMA map for the first
 * range that contains the given base address. It returns the corresponding
 * NUMA node ID if found.
 *
 * This is used to map a CXL device's memory address to the correct NUMA node,
 * ensuring accurate memory accounting and affinity settings.
 *
 * @param base_addr The physical base address of the device (e.g. from PCI BAR).
 * @param range_map A map from address ranges (start, end) to NUMA node IDs.
 * @return The NUMA node index if found; otherwise -1.
 */
int find_numa_node_from_range_map(
    uint64_t base_addr,
    const std::map<std::pair<uint64_t, uint64_t>, int>& range_map);

/**
 * @brief Executes a shell command and captures its standard output.
 *
 * This function runs the specified shell command using `popen()` and reads
 * its output into a string. If the command fails to execute, it throws a
 * `std::runtime_error` with a JSON-formatted POSIX error response using
 * `posix_err_to_json()`. The function also logs execution and failure details.
 *
 * @param[in] cmd The shell command to execute.
 * @return A string containing the full standard output of the command.
 *
 * @throws std::runtime_error if `popen()` fails or the command cannot be read.
 *
 * @note This is a general-purpose utility used for capturing CLI output
 * (e.g. `lsmem`, `lspci`).
 *
 * @see posix_err_to_json
 */
std::string run_command(const std::string& cmd);

/**
 * @brief Extracts the physical CXL memory base address from lspci output.
 *
 * This function runs `lspci -vvv -s <BDF>` and parses the "Range1" field,
 * which corresponds to the physical address range of the CXL memory exposed
 * by the device's HDM decoder. It returns the start address of that range,
 * which is required for mapping the device to its NUMA node.
 *
 * Logging is provided for traceability, and POSIX-style error messages
 * are thrown in case of command failure, missing Range1 entry, or
 * invalid address formatting.
 *
 * @param[in] bdf The PCI address of the device in the format
 * "domain:bus:device.function" (e.g. "0000:27:00.0").
 * @return The 64-bit physical base address (start of Range1) in bytes.
 *
 * @throws std::runtime_error if the lspci command fails, Range1 is missing,
 * or the base address cannot be parsed.
 *
 * @note This function assumes the system supports CXL 2.x devices and has
 * appropriate `lspci` output with DVSEC Range1 decoding.
 *
 * @see run_command, find_numa_node_from_range_map
 */
uint64_t get_physical_cxl_address_from_python(const std::string& bdf);

/**
 * @brief Stores a copy of the global memory range -> NUMA map.
 * @param external_map Range-to-NUMA map parsed from lsmem.
 */
void set_global_range_numa_map(const RangeToNumaMap& external_map);

/**
 * @brief Access the global memory range -> NUMA map.
 * @return A reference to the internal global map.
 * @throws std::runtime_error if not initialized.
 */
const RangeToNumaMap& get_global_range_numa_map();

/**
 * @brief Resolves NUMA node for a given PCI BDF address.
 *
 * This function looks up the CXL device's physical base address
 * using `lspci`, then matches that address against the cached
 * memory range -> NUMA map loaded from `lsmem`.
 *
 * @param bdf_str PCI BDF address in "dddd:bb:dd.f" format.
 * @return NUMA node ID on success, -1 on failure.
 */
int get_numa_node_from_bdf(const std::string& bdf_str);

/**
 * @brief Extract an integer value from a JSON object.
 *
 * Retrieves the integer value associated with the given key in a JSON object.
 * If the key does not exist or is not an integer, the fallback value is
 * returned.
 *
 * @param obj JSON object to search.
 * @param key Key to extract from the JSON object.
 * @param fallback Default integer to return if the key is missing or invalid.
 * @return Extracted integer value, or the fallback if not found.
 */
int get_json_int(json_t* obj, const std::string& key, int fallback = -99);

/**
 * @brief Extract a string value from a JSON object.
 *
 * Looks up the key in the given JSON object and returns the string value
 * if present and valid. If the key is missing or not a string, the fallback
 * value is returned instead.
 *
 * @param obj JSON object to search.
 * @param key Key to extract from the JSON object.
 * @param fallback Default value to return if the key is missing or invalid.
 * @return Extracted string value, or the fallback if not found.
 */
std::string get_json_str(json_t* obj, const std::string& key,
                         const std::string& fallback = "");

/**
 * @brief Convert a 16-bit integer to a hexadecimal string.
 *
 * Formats the given integer as a hex string with a 0x prefix.
 * Useful for logging vendor/device IDs in human-readable form.
 *
 * @param val The 16-bit integer to convert.
 * @return Hexadecimal string representation (e.g., "0x1e98").
 */
std::string to_hex(uint16_t val);

/**
 * @brief Sets the MetricsInfo loaded from config file.
 * @param info MetricsInfo struct containing the config values.
 */
void set_metrics_info(const MetricsInfo& info);

/**
 * @brief Returns the MetricsInfo previously loaded from config file.
 * @return const reference to MetricsInfo.
 */
const MetricsInfo& get_metrics_info();

/**
 * @brief Returns the current Unix epoch time (in seconds) as a string.
 *
 * @return Epoch timestamp, e.g 1721173902
 */
uint64_t get_epoch();

void set_bdf_to_numa_map(const std::unordered_map<std::string, int>& bdf_map);

/**
 *  @brief Global map storing mapping from HDM base address to CMMH device
 * index. This is populated by the CMMH discovery initialization logic.
 */
extern std::unordered_map<uint64_t, int> hdm_base_to_device_index;

/**
 * @brief Set the global HDM(Host Managed Device Memory) base to device index
 * mapping.
 *
 * This function is typically called after parsing cmmh device information
 * from the `cmmh_get_spec()` API. It allows other modules to access
 * device index based on HDM base address.
 *
 * @param input_map A map of HDM base address to corresponding device index.
 */
void set_hdm_base_to_device_index(
    const std::unordered_map<uint64_t, int>& input_map);

/**
 * @brief Retrieve the CMMH device index corresponding to the given HDM base
 * address.
 *
 * This is used during CXL device discovery to correlate physical memory address
 * (HDM base) to CMMH device index needed for cmmh_stat_sensor, cmmh_stat_cache
 * and cmmh_stat_interface APIs.
 *
 * @param hdm_base The HDM base address of the CXL device.
 * @return The device index (0-based) if found, otherwise -1.
 */
int get_hdm_base_to_device_index(uint64_t hdm_base);

/**
 * @brief Parses the 'metrics' block in the given JSON root and updates
 * MetricsInfo.
 *
 * @param root Parsed JSON root object
 * @param filepath Path to the original JSON file
 * @return int 0 on success, negative errno on failure
 */
int parse_metrics_config(const json_t* root, const std::string& filepath);

#endif
