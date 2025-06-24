
#include "ras_device.h"
#include "ras_request.h"

std::optional<device_unique_identifier> get_device_identifier_from_request(
    const ras_request& req) {
  // TODO: check if exists??
  json params = req.command_obj[RAS_COMMAND_PARAMS_STR];

  if (!params.contains(RAS_COMMAND_DEVICE_STR)) {
    return std::nullopt;
  }

  if (params.contains(RAS_COMMAND_DEVICE_NUMA_STR)) {
    /**
     * Workaround: Till unique device identifier specification is available
     *
     * Note If numa node is present then concatenate device with numa node to
     * get the unique identifier. If numa node is used during device add, it
     * should be present while device update and remove as well.
     */
    return params[RAS_COMMAND_DEVICE_STR].get<std::string>() + "_" +
           std::to_string(params[RAS_COMMAND_DEVICE_NUMA_STR].get<int>());
  } else {
    return params[RAS_COMMAND_DEVICE_STR].get<std::string>();
  }
}

bool validate_generic_request(const ras_request& req) {
  // Check if command exists in json object
  if (!req.command_obj.contains(RAS_COMMAND_COMMAND_STR)) return false;
  // Check if command params exists in json object
  if (!req.command_obj.contains(RAS_COMMAND_PARAMS_STR)) return false;
  return true;
}

void ras_request::execute_feature_command(void) {
  if (this->is_internal_request == true) {
    // Expecting external request
    this->is_successfull = false;
    this->command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
        RAS_RESULT_CODE_FAILED_STR;
    return;
  }

  if (!validate_generic_request(*this)) {
    this->is_successfull = false;
    this->command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
        RAS_RESULT_CODE_FAILED_STR;
    return;
  }

  execute_request_by_monitor_(*this);
  return;
}