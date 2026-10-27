#ifndef _RAS_REQUEST__HPP_
#define _RAS_REQUEST__HPP_

#pragma once

#include <fmt/format.h>

#include <condition_variable>
#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <unordered_map>

#include "ras.hpp"
#include "ras_device.h"
#include "ras_exports.h"
#include "svk_logger.hpp"
using json = nlohmann::json;

#define RAS_COMMAND_COMMAND_STR "command_name"
#define RAS_COMMAND_PARAMS_STR "command_params"
#define RAS_COMMAND_DEVICE_STR "device_id"
#define RAS_COMMAND_DEVICE_NUMA_STR "device_numa"
#define RAS_COMMAND_RESULT_STR "result"
#define RAS_COMMAND_STATUS_CODE_STR "ras_cmd_status_code"
#define RAS_COMMAND_STATUS_MESSAGE_STR "ras_cmd_status_str"
#define RAS_COMMAND_DEVICE_ADAPTER_NAME_STR "device_adapter"
#define RAS_COMMAND_PARAMS_CONFIGURE_OPTIONS_STR "configure_options"
#define RAS_COMMAND_PARAMS_ERROR_COUNT_THRESHOLD "error_count_threshold"

#define RAS_RESULT_CODE_FAILED_STR "failed"
#define RAS_RESULT_CODE_SUCCESS_STR "success"

#define RAS_RESULT_MESSAGE_STR_CMD_UNSUPPORTED "Command Unsupported"
#define RAS_RESULT_MESSAGE_STR_CMD_INVALID "Invalid command"
#define RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID "Invalid command parameters"

#define RAS_DEVICE_DEFAULT_MONITOR_INTERVAL g_monitor_interval

class ras_monitor;

class ras_request {
 public:
  ras_request(bool is_sync_request, struct ras_context_s *ras_context,
              bool is_internal_request = true,
              std::optional<const char *> command_input_cstr = std::nullopt,
              std::optional<const size_t> command_input_len = std::nullopt)
      : is_sync_request(is_sync_request),
        ras_context(ras_context),
        is_internal_request(is_internal_request),
        command_input_cstr(command_input_cstr),
        command_input_len(command_input_len) {
    is_completed = false;
    cmd_obj_valid = false;
  }

  bool is_sync_request;
  struct ras_context_s *ras_context;
  bool is_internal_request;
  std::optional<const char *> command_input_cstr;
  std::optional<const size_t> command_input_len;

  bool parse_input_command_to_json(void) {
    if (this->command_input_cstr == std::nullopt ||
        this->command_input_len == std::nullopt) {
      svk_logger(RAS_LOGGER, level_E::ERROR, "command c-string or len not set");
      return false;
    }
    try {
      this->command_obj = json::parse(*this->command_input_cstr);
    } catch (json::parse_error &e) {
      svk_logger(
          RAS_LOGGER, level_E::ERROR,
          fmt::format("Invalid json {}", std::string(*this->command_input_cstr))
              .c_str());
      // Since json parse failed we will not update the result in the json
      // object
      return false;
    }

    // Command was successfully parsed and json object created

    this->cmd_obj_valid = true;

    auto command_str = get_command_string();
    if (command_str == std::nullopt) {
      svk_logger(RAS_LOGGER, level_E::ERROR, "Command string not found");
      mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_INVALID);
      return false;
    } else {
      this->command = *command_str;
    }
    return true;
  }

  std::string get_json_object_string(void) {
    return this->command_obj.dump(2 /*Indent by two spaces*/);
  }

  bool command_object_valid(void) const { return cmd_obj_valid; }

  void mark_request_failed(std::string message_str) {
    this->is_successfull = false;
    this->command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR] =
        RAS_RESULT_CODE_FAILED_STR;
    this->command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_MESSAGE_STR] =
        message_str;
  }

  /**Derived or set during processing */
  json command_obj;
  std::string command;
  bool is_completed;
  bool is_successfull;
  std::mutex sync_mutex;
  std::condition_variable sync_cv;

  void execute_feature_command(void);
  void execute_internal_command(void);
  std::optional<json> get_command_params_for(
      std::string command_param_to_lookup) const {
    if (!this->command_object_valid()) {
      return std::nullopt;
    }

    if (!this->command_obj.contains(RAS_COMMAND_PARAMS_STR)) {
      return std::nullopt;
    }

    json params = this->command_obj[RAS_COMMAND_PARAMS_STR];

    if (!params.is_object()) {
      return std::nullopt;
    }

    if (!params.contains(command_param_to_lookup)) {
      return std::nullopt;
    }
    return params[command_param_to_lookup];
  }
  friend class RequestHandlerUnitTest;

 private:
  bool cmd_obj_valid;

  std::optional<std::string> get_command_string(void) {
    if (this->command_obj.contains(RAS_COMMAND_COMMAND_STR) &&
        this->command_obj[RAS_COMMAND_COMMAND_STR].is_string()) {
      return this->command_obj[RAS_COMMAND_COMMAND_STR];
    } else {
      return std::nullopt;
    }
  }
};

bool ras_submit_timed_request(ras_request *req, int interval);
void execute_request_by_monitor_(ras_request &req);
bool ras_submit_timed_request(ras_request *req, int interval);
std::optional<device_unique_identifier> get_device_identifier_from_request(
    const ras_request &req);

std::optional<device_unique_identifier>
get_numa_node_as_device_identifier_from_request(const ras_request &req);

std::shared_ptr<ras_device_manager> ras_monitor_get_device_manager(
    ras_monitor *m);

ras_request *build_device_monitor_request(ras_context_s *ras_context,
                                          device_unique_identifier device_name);

namespace cognos::ras {
class request_helper {
 public:
  static void clear_results_from_request(ras_request &request) {
    request.command_obj[RAS_COMMAND_RESULT_STR].clear();
  }
};
}  // namespace cognos::ras
#endif  // _RAS_REQUEST__HPP_
