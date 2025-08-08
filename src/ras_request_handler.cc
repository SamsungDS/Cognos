
#include "ras_device.h"
#include "ras_request.h"

std::optional<device_unique_identifier> get_device_identifier_from_request(
    const ras_request& req) {
  auto device_name = req.get_command_params_for(RAS_COMMAND_DEVICE_STR);
  if (device_name == std::nullopt) {
    return std::nullopt;
  }
  return (*device_name).get<std::string>();
}

std::optional<device_unique_identifier>
get_numa_node_as_device_identifier_from_request(const ras_request& req) {
  auto numa_node = req.get_command_params_for(RAS_COMMAND_DEVICE_NUMA_STR);
  if (numa_node == std::nullopt) {
    return std::nullopt;
  }
  return std::to_string((*numa_node).get<int>());
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