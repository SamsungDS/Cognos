#include <iostream>

#include "logic_interface/svk_logic_interface.h"
#include "slat_benchmark.hpp"
#include "svk_logger.h"

using namespace std;

const std::unordered_map<std::string, level_E> log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

using slat_logic_config = struct slat_logic_config {
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

#define MLC_DEFAULT_PATH \
  "/usr/local/svk/feature_modules/slat/logic_modules/svkslatlogic/bin/mlc"
svk_status execute_mlc_logic_sync(svk_logic_cmd *cmd, svk_logic_input *input,
                                  svk_logic_output *output) {
  std::cout << "mlc logic sync" << std::endl;
  std::string result_str;
  argOpts opts = {};
  result_str = runMlc("idle_latency", opts, std::string(MLC_DEFAULT_PATH));
  snprintf((char *)output->output_buffer, output->output_len, "%s",
           result_str.c_str());
  return SVK_STATUS_SUCCESS;
}

svk_status execute_mlc_logic_async(svk_logic_cmd *pass_thru,
                                   svk_postprocess_fn *postprocess_fn) {
  return SVK_STATUS_SUCCESS;
}

svk_status cleanup_mlc_logic_module(void *param) { return SVK_STATUS_SUCCESS; }

extern "C" svk_status initialize_logic_module(void *init_param) {
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status get_supported_logic_details(
    svk_logic_module_details *details) {
  strcpy(details->feature_name, "slat");
  strcpy(details->logic_module_name, "MlcLogic");

  details->execute_logic_sync = &execute_mlc_logic_sync;
  details->execute_logic_async = &execute_mlc_logic_async;
  details->cleanup_logic_module = &cleanup_mlc_logic_module;

  return SVK_STATUS_SUCCESS;
}
