#ifndef _RAS_ADD_DEVICE_HANDLER__HPP_
#define _RAS_ADD_DEVICE_HANDLER__HPP_

#include <fmt/format.h>

#include <iostream>
#include <memory>

#include "ras.hpp"
#include "ras_device.h"
#include "ras_request.h"
#include "utils/command_handler.hpp"
#include "utils/ras_json_validate.hpp"
/**
 * @class add_ras_monitor_for_device_handler
 * @brief Handles the command to add a reliability monitor for a device.
 */
class add_ras_monitor_for_device_handler
    : public cognos::utils::CommandHandlerImpl<ras_request> {
 public:
  /**
   * @brief Validates the incoming request.
   *
   * @param r The request to be validated.
   * @return True if the request is valid, false otherwise.
   */
  bool validate(ras_request &r) {
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
  void execute(ras_request &r) {
    // Get the device manager instance
    auto device_manager =
        ras_monitor_get_device_manager(r.ras_context->monitor_context);

    // Get the device identifier from the request
    auto device_unique_id = get_device_identifier_from_request(r);
    if (device_unique_id == std::nullopt) {
      // Mark the request as invalid if the device identifier is missing
      r.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID);
      return;
    }

    std::optional<device_unique_identifier> numa_node_identifier = std::nullopt;
    auto adapter_name =
        r.ras_context->ras_adapter_helper_->try_get_adapter_for_device(
            *device_unique_id);
    if (adapter_name == std::nullopt) {
      // TRY one more time with numa node as device name.
      // If this needs to be a general approach for mutiple types of device IDs
      // then this code needs refactoring
      auto numa_node = get_numa_node_as_device_identifier_from_request(r);
      if (numa_node == std::nullopt) {
        // Mark the request as invalid if the device identifier is missing
        r.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID);
        return;
      }
      adapter_name =
          r.ras_context->ras_adapter_helper_->try_get_adapter_for_device(
              *numa_node);
      if (adapter_name == std::nullopt) {
        // Mark the request as invalid no adapter detected for the device
        r.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID);
        return;
      }
      // set the device identifier based on numa node
      numa_node_identifier = *numa_node;
    }

    // Create a new device instance
    std::unique_ptr<ras_device> dev = std::make_unique<ras_device>(
        r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_STR], "", true,
        r.command_obj[RAS_COMMAND_PARAMS_STR]
                     [RAS_COMMAND_PARAMS_CONFIGURE_OPTIONS_STR]
                     [RAS_COMMAND_PARAMS_ERROR_COUNT_THRESHOLD],
        false, 0, 0, g_monitor_interval, adapter_name.value(),
        r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_NUMA_STR],
        numa_node_identifier);

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
      return;
    }

    // Set the status code to indicate success
    r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
        RAS_RESULT_CODE_SUCCESS_STR;

    ras_request *monitor_req =
        build_device_monitor_request(r.ras_context, device_unique_id.value());
    if (monitor_req == nullptr) {
      svk_logger(RAS_LOGGER, level_E::ERROR,
                 fmt::format("Failed to build device monitor request for "
                             "device {} ",
                             device_unique_id.value())
                     .c_str());
      r.mark_request_failed(
          fmt::format("Failed to start device monitoring for device {} ",
                      device_unique_id.value()));
      return;
    }

    // Execute request in 1 second for the first time
    bool res = ras_submit_timed_request(monitor_req, 1);
    if (res == false) {
      delete monitor_req;
      r.mark_request_failed(
          fmt::format("Failed to start device monitoring for device {} ",
                      device_unique_id.value()));
      return;
    }
    svk_logger(RAS_LOGGER, level_E::INFO,
               fmt::format("Started device monitoring for "
                           "device {} ",
                           device_unique_id.value())
                   .c_str());

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
};

#endif  // _RAS_ADD_DEVICE_HANDLER__HPP_
