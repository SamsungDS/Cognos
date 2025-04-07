#ifndef DEVICE_MANAGER_H
#define DEVICE_MANAGER_H

#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>

#include "sc_dev_registry.h"

/**
 * @class DeviceManager
 * @brief Singleton class responsible for managing device operations.
 *
 * The DeviceManager handles high-level device operations such as listing
 * devices, fetching device information, and performing attach/detach
 * operations. It interacts with the DeviceRegistry to manage and query
 * registered device adapters.
 **/
class DeviceManager {
 public:
  /**
   * @brief Gets the singleton instance of DeviceManager.
   *
   * Ensures a single instance of the DeviceManager exists across the
   * application.
   * @return Reference to the singleton instance.
   */
  static DeviceManager& getInstance();

  /**
   * @brief Constructs a DeviceManager instance for library use.
   *
   * This constructor allows embedding DeviceManager in external applications
   * by injecting a DeviceRegistry instance.
   *
   * @param registry Reference to an externally managed DeviceRegistry instance.
   */
  explicit DeviceManager(DeviceRegistry& registry);

  /**
   * @brief Destructor for DeviceManager.
   */
  ~DeviceManager();

  /**
   * @brief Deleted copy constructor to prevent duplication.
   **/
  DeviceManager(const DeviceManager&) = delete;

  /**
   * @brief Deleted assignment operator to prevent duplication.
   */
  DeviceManager& operator=(const DeviceManager&) = delete;

  /**
   * @brief Lists all registered devices based on provided filters.
   *
   * Extracts device filter parameters, retrieves device lists from adapters,
   * and compiles a unified JSON response.
   *
   * @param[in] params Map containing API request parameters, including
   * "command_params".
   * @return JSON string containing the list of devices or an error response.
   *
   * @error EINVAL If request format is invalid or missing required parameters.
   * @error EIO If device retrieval fails.
   */
  std::string list_devices(
      const std::unordered_map<std::string, std::string>& params);

  /**
   * @brief Retrieves detailed information about a specific device.
   *
   * Validates the input, retrieves the corresponding adapter, and calls
   * `get_device_info`. Returns a JSON response with the device information or
   * an appropriate error.
   *
   * @param[in] params Map containing "device_id".
   * @return JSON string containing device details or an error response.
   *
   * @error EINVAL If "device_id" is missing or improperly formatted.
   * @error ENOENT If the specified device is not found.
   * @error EIO If fetching device details fails.
   */
  std::string get_device_info(
      const std::unordered_map<std::string, std::string>& params);

  /**
   * @brief Handles the attachment of a device to a host (Only applicable for
   * CMMB).
   *
   * This function validates the input parameters, retrieves the corresponding
   * adapter, and calls the `attach_memory` function on the adapter. If any
   * error occurs during the process, a proper error response is generated.
   *
   * @param[in] params Map containing "device_id", "node_id" or "host_id".
   * @return JSON response as a string.
   *
   * @error EINVAL  If "device_id" or "host_id" is missing or invalid.
   * @error ENOENT  If no adapter is found for the given device ID.
   * @error Other POSIX error codes from `detach_memory` if the operation fails.
   */
  std::string attach_memory(
      const std::unordered_map<std::string, std::string>& params);

  /**
   * @brief Handles the detachment of a device from a host (Only applicable for
   * CMMB).
   *
   * This function validates the input parameters, retrieves the appropriate
   * adapter, and calls the `detach_memory` function on the adapter. If any
   * error occurs during the process, a proper error response is generated.
   *
   * @param[in] params Map containing "device_id" and "host_id".
   * @return JSON response as a string.
   *
   * @error EINVAL  If "device_id" or "host_id" is missing or invalid.
   * @error ENOENT  If no adapter is found for the given device ID.
   * @error Other POSIX error codes from `detach_memory` if the operation fails.
   */
  std::string detach_memory(
      const std::unordered_map<std::string, std::string>& params);

  /**
   * @brief Extracts and validates device IDs from a JSON string.
   *
   * Parses the "command_params" JSON to extract the "device_id" field, which
   * can be a string or an array. Validates and stores the device IDs in
   * `dev_ids_out`.
   *
   * @param[in] json_request JSON string containing device filter parameters.
   * @param[out] dev_ids_out Set to store extracted device IDs.
   * @return 0 on success, or a negative POSIX error code on failure.
   *
   * @error EINVAL If the JSON format is invalid or "device_id" is improperly
   * formatted.
   */
  int fetch_dev_ids_from_req(const std::string& json_request,
                             std::unordered_set<uint64_t>& dev_ids_out);

  /**
   * @brief Retrieves and aggregates device information from all registered
   * adapters.
   *
   * Iterates through all registered adapters in the `DeviceRegistry`, calling
   * their `list_devices` method. The results are processed and flattened into a
   * unified JSON response.
   *
   * @param[in] dev_ids_out Set containing device IDs to filter the results. If
   * empty, all devices are listed.
   * @param[in] device_result to capture flattened list of devices.
   * @return JSON string containing the aggregated list of devices or an error
   * response.
   *
   * @error EIO If an adapter fails to retrieve device data.
   * @error EINVAL If an adapter returns an invalid JSON format.
   */
  int fetch_all_devices(const std::unordered_set<uint64_t>& dev_ids_out,
                        std::string& device_result);

 private:
  // Registry reference (injected)
  DeviceRegistry& registry_;
};

#endif
