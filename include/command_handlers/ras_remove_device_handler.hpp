#ifndef _RAS_REMOVE_DEVICE_HANDLER__HPP_
#define _RAS_REMOVE_DEVICE_HANDLER__HPP_

#include <iostream>
#include <memory>

#include "ras_device.h"
#include "ras_request.h"
#include "utils/command_handler.hpp"
#include "utils/ras_json_validate.hpp"

/**
 * @class add_ras_monitor_for_device_handler
 * @brief Handles the command to add a reliability monitor for a device.
 */
class remove_ras_monitor_for_device_handler
    : public cognos::utils::CommandHandlerImpl<ras_request> {
 public:
  /**
   * @brief Validates the incoming request.
   *
   * @param r The request to be validated.
   * @return True if the request is valid, false otherwise.
   */
  bool validate(ras_request& r) {
    // Calling validate_json_request
    bool ret = validate_ras_json_request(r.command_obj[RAS_COMMAND_PARAMS_STR],
                                         required_params);
    if (ret == false) {
      r.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID);
      return false;
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
      r.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID);
      return;
    }

    // Attempt to remove the device using the device manager
    r.is_successfull = device_manager->try_remove_device(*device_unique_id);

    // Update the response based on the result
    if (r.is_successfull == false) {
      // Set the status code and message to indicate failure
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
          RAS_RESULT_CODE_FAILED_STR;
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_MESSAGE_STR] =
          "Failed to remove device";
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
  std::vector<std::string> required_params = {RAS_COMMAND_DEVICE_STR,
                                              RAS_COMMAND_DEVICE_NUMA_STR};

  /**
   * @brief The command handled by this class.
   */
  std::string command = "remove_reliability_monitoring_for_device";
};
#endif  // _RAS_REMOVE_DEVICE_HANDLER__HPP_
