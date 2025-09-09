
#ifndef _RAS_MONITOR_CHECK_DEVICE_STATUS__H_
#define _RAS_MONITOR_CHECK_DEVICE_STATUS__H_

#include "ras_device.h"
#include "ras_event_publisher.hpp"
#include "ras_request.h"
#include "utils/command_handler.hpp"
#include "utils/ras_json_validate.hpp"

class ras_check_device_status_handler
    : public cognos::utils::CommandHandlerImpl<ras_request> {
 public:
  /**
   * @brief Validates the incoming request.
   *
   * @param r The request to be validated.
   * @return True if the request is valid, false otherwise.
   */
  bool validate(ras_request& r) override {
    // Calling validate_json_request
    if (validate_ras_json_request(r.command_obj[RAS_COMMAND_PARAMS_STR],
                                  required_params) == false) {
      return false;
    }
    return true;
  }

  void execute(ras_request& r) override {
    // Get the device manager instance
    auto device_manager =
        ras_monitor_get_device_manager(r.ras_context->monitor_context);

    device_unique_identifier device_id =
        r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_STR];

    auto device = device_manager->try_get_device(device_id);

    if (device.has_value() == false) {
      r.is_successfull = false;
      svk_logger(
          RAS_LOGGER, level_E::WARN,
          fmt::format(
              "Device {} not found. Might have been removed from monitoring",
              device_id)
              .c_str());
      /** NOTE: Since this request was dynamically allocated during add device
       * this needs to be deleted */
      delete &r;
      return;
    }

    r.is_successfull =
        check_device_error_count_threshold_status(r.ras_context, *device);
    if (r.is_successfull == false) {
      // If device status check was not successfull then mark request as failed
      svk_logger(
          RAS_LOGGER, level_E::ERROR,
          fmt::format("Device {} status check failed", device_id).c_str());
      /** NOTE: Since this request was dynamically allocated during add device
       * this needs to be deleted */
      delete &r;
      return;
    }

    // If device status check was successfull then clear the results and
    // resubmit request
    cognos::ras::request_helper::clear_results_from_request(r);
    bool submission_successfull =
        ras_submit_timed_request(&r, device.value().monitor_interval);
    if (submission_successfull == false) {
      r.mark_request_failed("Failed to submit monitor request");
      svk_logger(RAS_LOGGER, level_E::ERROR,
                 fmt::format("Failed to submit monitor request for device {} ",
                             device_id)
                     .c_str());
      /** NOTE: Since this request was dynamically allocated during add device
       * this needs to be deleted */
      delete &r;
      return;
    }

    return;
  }

  /**
   * @brief Gets the command handled by this class.
   *
   * @return The command string.
   */
  std::string get_command(void) override { return command; };

  friend class CheckDeviceStatusUnitTest;

 private:
  /**
   * @brief List of required parameters for the command.
   */
  std::vector<std::string> required_params = {RAS_COMMAND_DEVICE_STR};

  /**
   * @brief The command handled by this class.
   */
  std::string command = "ras_monitor_check_device_status";

  bool check_device_error_count_threshold_status(ras_context_s* ras_ctx,
                                                 ras_device& device) {
    if (device.ect.valid == false) {
      // Error count threshold to monitor not valid
      return false;
    }

    auto device_error_count =
        ras_ctx->ras_adapter_helper_->get_device_correctable_error_count(
            device.get_adapter_name(), device.get_device_name_in_adapter());

    if (device_error_count.has_value() == false) {
      // Device error count query failed
      return false;
    }

    if (device_error_count.value() > device.ect.error_count_threshold) {
      if (device.ect.degraded == false) {
        // Publish the alert
        cognos::ras::publisher::send_ras_threshold_warning_event(
            device.get_device_name(), "Correctable error threshold exceeded");
        device.ect.degraded = true;
      }
      return true;
    }

    if (device.ect.degraded == true) {
      device.ect.degraded = false;
      // No alert to publish continue monitoring
    }

    return true;
  }
};

#endif  // _RAS_MONITOR_CHECK_DEVICE_STATUS__H_