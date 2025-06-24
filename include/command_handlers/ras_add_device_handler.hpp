#ifndef _RAS_ADD_DEVICE_HANDLER__HPP_
#define _RAS_ADD_DEVICE_HANDLER__HPP_

#include <iostream>
#include <string>

#include "ras_device.h"
#include "ras_request.h"
#include "utils/command_handler.hpp"

class add_ras_monitor_for_device_handler
    : public CommandHandlerImpl<ras_request> {
 public:
  bool validate(ras_request& r) {
    json& params = r.command_obj[RAS_COMMAND_PARAMS_STR];
    for (auto required_param : this->required_params) {
      auto valid = this->validate_nested_json(params, required_param);
      if (!valid) {
        r.mark_request_invalid_params();
        return false;
      }
    }
    return true;
  }
  void execute(ras_request& r) {
    auto device_manager = ras_monitor_get_device_manager(r.monitor_instance);

    auto device_unique_id = get_device_identifier_from_request(r);
    if (device_unique_id == std::nullopt) {
      r.mark_request_invalid_params();
      return;
    }

    auto dev = std::make_unique<ras_device>();

    // TODO: This needs to be detected from loaded adapters
    dev->adapter_name = "mock";

    dev->name = r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_STR];
    dev->numa_node =
        r.command_obj[RAS_COMMAND_PARAMS_STR][RAS_COMMAND_DEVICE_NUMA_STR];
    dev->ect.valid = true;
    dev->ect.error_count_threshold =
        r.command_obj[RAS_COMMAND_PARAMS_STR]
                     [RAS_COMMAND_PARAMS_CONFIGURE_OPTIONS_STR]
                     [RAS_COMMAND_PARAMS_ERROR_COUNT_THRESHOLD];
    dev->twt.valid = false;
    dev->monitor_interval = RAS_DEVICE_DEFAULT_MONITOR_INTERVAL;

    r.is_successfull =
        device_manager->try_add_device(*device_unique_id, std::move(dev));
    if (r.is_successfull == false) {
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
          RAS_RESULT_CODE_FAILED_STR;
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_MESSAGE_STR] =
          "Failed to add device";
    } else {
      r.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
          RAS_RESULT_CODE_SUCCESS_STR;
    }
    return;
  }
  std::string get_command(void) { return command; };

 private:
  std::vector<std::string> required_params = {
      RAS_COMMAND_DEVICE_STR, RAS_COMMAND_DEVICE_NUMA_STR,
      RAS_COMMAND_PARAMS_CONFIGURE_OPTIONS_STR
      "." RAS_COMMAND_PARAMS_ERROR_COUNT_THRESHOLD};
  std::string command = "add_reliability_monitoring_for_device";

  bool validate_nested_json(json& obj,
                            std::string dot_seperated_key_hierarchy) {
    char delimter = '.';
    size_t delim_pos = dot_seperated_key_hierarchy.find(delimter);
    if (delim_pos != std::string::npos) {
      std::string key = dot_seperated_key_hierarchy.substr(0, delim_pos);
      std::string str_to_process =
          dot_seperated_key_hierarchy.substr(delim_pos + 1);

      if (obj.contains(key)) {
        return validate_nested_json(obj[key], str_to_process);
      } else {
        return false;
      }
    } else {
      if (obj.contains(dot_seperated_key_hierarchy)) {
        return true;
      } else {
        return false;
      }
    }
  }
};
#endif  // _RAS_ADD_DEVICE_HANDLER__HPP_
