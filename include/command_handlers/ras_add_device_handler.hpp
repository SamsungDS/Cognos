#ifndef _RAS_ADD_DEVICE_HANDLER__HPP_
#define _RAS_ADD_DEVICE_HANDLER__HPP_

#include <iostream>
#include <string>

#include "ras_device.h"
#include "ras_request.h"
#include "utils/command_handler.hpp"

/**
 * @class add_ras_monitor_for_device_handler
 * @brief Handles the command to add a reliability monitor for a device.
 */
class add_ras_monitor_for_device_handler
    : public CommandHandlerImpl<ras_request> {
 public:
  /**
   * @brief Validates the incoming request.
   *
   * @param r The request to be validated.
   * @return True if the request is valid, false otherwise.
   */
  bool validate(ras_request& r) {
    // Get the parameters from the request
    json& params = r.command_obj[RAS_COMMAND_PARAMS_STR];

    // Iterate over the required parameters
    for (auto required_param : this->required_params) {
      // Validate each required parameter
      auto valid = this->validate_nested_json(params, required_param);
      if (!valid) {
        // Mark the request as invalid if any parameter is missing
        r.mark_request_invalid_params();
        return false;
      }
    }
    return true;
  }

  /**
   * @brief Executes the command to add a reliability monitor for a device.
   *
   * @param r The request to be executed.
   */
  void execute(ras_request& r) {
    // Get the device manager instance
    auto device_manager = ras_monitor_get_device_manager(r.monitor_instance);

    // Get the device identifier from the request
    auto device_unique_id = get_device_identifier_from_request(r);
    if (device_unique_id == std::nullopt) {
      // Mark the request as invalid if the device identifier is missing
      r.mark_request_invalid_params();
      return;
    }

    // Create a new device instance
    auto dev = std::make_unique<ras_device>();

    // TODO: This needs to be detected from loaded adapters
    // Set the adapter name (currently hardcoded to "mock")
    dev->adapter_name = "mock";

    // Set the device name from the request
    dev->name = r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_STR];

    // Set the NUMA node from the request
    dev->numa_node =
        r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_NUMA_STR];

    // Initialize the error count threshold
    dev->ect.valid = true;
    dev->ect.error_count_threshold =
        r.command_obj[RAS_COMMAND_PARAMS_STR]
                     [RAS_COMMAND_PARAMS_CONFIGURE_OPTIONS_STR]
                     [RAS_COMMAND_PARAMS_ERROR_COUNT_THRESHOLD];

    // Initialize the time window threshold (currently not valid)
    dev->twt.valid = false;

    // Set the monitor interval (currently set to default)
    dev->monitor_interval = RAS_DEVICE_DEFAULT_MONITOR_INTERVAL;

    // Attempt to add the device to the device manager
    r.is_successfull =
        device_manager->try_add_device(*device_unique_id, std::move(dev));

    // Update the response based on the result
    if (r.is_successfull == false) {
      // Set the status code and message to indicate failure
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
          RAS_RESULT_CODE_FAILED_STR;
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_MESSAGE_STR] =
          "Failed to add device";
    } else {
      // Set the status code to indicate success
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
          RAS_RESULT_CODE_SUCCESS_STR;
    }
    return;
  }

  /**
   * @brief Gets the command handled by this class.
   *
   * @return The command string.
   */
  std::string get_command(void) { return command; };

 private:
  /**
   * @brief List of required parameters for the command.
   */
  std::vector<std::string> required_params = {
      RAS_COMMAND_DEVICE_STR, RAS_COMMAND_DEVICE_NUMA_STR,
      RAS_COMMAND_PARAMS_CONFIGURE_OPTIONS_STR
      "." RAS_COMMAND_PARAMS_ERROR_COUNT_THRESHOLD};

  /**
   * @brief The command handled by this class.
   */
  std::string command = "add_reliability_monitoring_for_device";

  /**
   * @brief Validates a nested JSON object.
   *
   * @param obj The JSON object to be validated.
   * @param dot_seperated_key_hierarchy The dot-separated key hierarchy.
   * @return True if the JSON object is valid, false otherwise.
   */
  bool validate_nested_json(json& obj,
                            std::string dot_seperated_key_hierarchy) {
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
        return validate_nested_json(obj[key], str_to_process);
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
};
#endif  // _RAS_ADD_DEVICE_HANDLER__HPP_
