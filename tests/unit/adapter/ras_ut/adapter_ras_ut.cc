#include "adapter_ras_ut.h"

#include <logic_interface/svk_logic_interface.h>

#include "nlohmann/json.hpp"
#include "ras_exports.h"

using json = nlohmann::json;

class ras_ut_adapter_command_handler {
  std::vector<std::string> deviceList = {"dev123", "0"};

 public:
  json get_device_list(json command) {
    json resp;
    resp["command_response"] = command["command_name"];
    resp["command_params"] = command["command_params"];
    resp["result"]["commandSuccessfull"] = true;
    resp["result"]["deviceList"] = deviceList;

    return resp;
  }

  json get_error_count(json command) {
    json resp;
    resp["command_response"] = command["command_name"];
    resp["command_params"] = command["command_params"];
    resp["result"]["commandSuccessfull"] = true;
    resp["result"]["errorCount"] = 100;

    return resp;
  }
};

ras_ut_adapter_command_handler handler_;

svk_status execute_ut_adapter_logic_sync(svk_logic_cmd *cmd,
                                         svk_logic_input *input,
                                         svk_logic_output *output) {
  json input_command = json::parse((char *)input->input_buffer);
  json output_json;
  std::string cmd_name_str = input_command["command_name"];

  output->status = SVK_STATUS_FAIL;

  if (cmd_name_str == "getDeviceList") {
    output_json = handler_.get_device_list(input_command);
  } else if (cmd_name_str == "getErrorCount") {
    std::string device = input_command["command_params"]["device"];
    if (device == "dev123") {
      output_json = handler_.get_error_count(input_command);
    }
  }

  std::string output_str = output_json.dump();
  if (output_str.length() >= output->output_len) {
    output->status = SVK_STATUS_FAIL;
  } else {
    strncpy((char *)output->output_buffer, output_str.c_str(),
            output->output_len);
    output->status = SVK_STATUS_SUCCESS;
  }
  return output->status;
}

inline svk_status execute_ut_adapter_logic_async(
    svk_logic_cmd *pass_thru, svk_postprocess_fn *postprocess_fn) {
  return SVK_STATUS_FAIL;
}

inline svk_status cleanup_ut_adapter_logic_module(void *param) {
  return SVK_STATUS_SUCCESS;
}

inline svk_status configure_ut_adapter_logic(
    const std::string slat_logic_conf_file) {
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status initialize_logic_module(void *init_param) {
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status get_supported_logic_details(
    svk_logic_module_details *details) {
  strcpy(details->feature_name, RAS_FEATURE_MODULE_NAME);
  strcpy(details->logic_module_name, UT_ADPATER_NAME);

  details->execute_logic_sync = &execute_ut_adapter_logic_sync;
  details->execute_logic_async = &execute_ut_adapter_logic_async;
  details->cleanup_logic_module = &cleanup_ut_adapter_logic_module;

  return SVK_STATUS_SUCCESS;
}
