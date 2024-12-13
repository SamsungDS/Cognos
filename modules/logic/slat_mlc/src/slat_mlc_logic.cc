#include <iostream>

#include "logger_util.hpp"
#include "slat_benchmark.hpp"

#define SLAT_DEFAULT_LOGIC_CONFIG_FILE "/etc/svk/slat_logic.json"
#define MLC_DEFAULT_BINARY \
  "/usr/local/svk/feature_modules/slat/logic_modules/mlclogic/bin/mlc"

#define SLAT_MLC_MODULE_NAME "mlclogic"
#define SLAT_MLC_CONF_SECTION_TAG SLAT_MLC_MODULE_NAME

std::string g_mlc_bin = MLC_DEFAULT_BINARY;

svk_status execute_mlc_logic_sync(svk_logic_cmd *cmd, svk_logic_input *input,
                                  svk_logic_output *output) {
  std::cout << "mlc logic sync" << std::endl;
  std::string result_str;
  argOpts opts = {};
  char numa_node[64] = {};
  char *ptr;

  if (cmd == nullptr || input == nullptr || output == nullptr) {
    std::cout << "Invalid input for logic sync params" << std::endl;
    return SVK_STATUS_FAIL;
  }

  if (input->input_buffer == nullptr) {
    std::cout << "NULL input buffer for logic sync params" << std::endl;
    return SVK_STATUS_FAIL;
  }

  ptr = strstr((char *)input->input_buffer, "numa_node");
  if (ptr != nullptr) {
    sscanf(ptr, "numa_node=%[.0-9]", numa_node);
    opts["numa_node"] = numa_node;
  }

  result_str = runMlc("idle_latency", opts, g_mlc_bin);
  snprintf((char *)output->output_buffer, output->output_len, "%s",
           result_str.c_str());
  return SVK_STATUS_SUCCESS;
}

svk_status execute_mlc_logic_async(svk_logic_cmd *pass_thru,
                                   svk_postprocess_fn *postprocess_fn) {
  return SVK_STATUS_SUCCESS;
}

svk_status cleanup_mlc_logic_module(void *param) { return SVK_STATUS_SUCCESS; }

svk_status configure_slat_mlc_logic(const std::string slat_logic_conf_file) {
  slat_logger_config config;
  svk_status status = SVK_STATUS_SUCCESS;
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(slat_logic_conf_file, root);
    pt::ptree slat_config_pt = root.get_child(SLAT_MLC_CONF_SECTION_TAG);

    g_mlc_bin = slat_config_pt.get<std::string>("mlc_bin_dir");
    g_mlc_bin += "/mlc";

    pt::ptree logger_info_pt = slat_config_pt.get_child("logger");
    status = read_slat_logger_config(logger_info_pt, config);

  } catch (std::exception &e) {
    std::cerr << "Error processing SLAT config file. Assigning default value. "
                 "Error -> "
              << e.what() << std::endl;

    // Assign defaults
    config.log_level = SLAT_LOGGER_LEVEL_DEFAULT;
    config.log_filename = SLAT_LOG_FILENAME_DEFAULT;
    config.log_file_count = SLAT_LOGGER_FILE_COUNT_DEFAULT;
    config.log_file_size = SLAT_LOGGER_FILE_SIZE_DEFAULT;
    config.log_sink_type = SLAT_LOGGER_SINK_TYPE_DEFAULT;
  }
  config.log_module_name = SLAT_MLC_MODULE_NAME;
  status = slat_initialize_logger(config);

  return status;
}

extern "C" svk_status initialize_logic_module(void *init_param) {
  const char *env_p;
  std::string conf_path = SLAT_DEFAULT_LOGIC_CONFIG_FILE;

  if ((env_p = std::getenv("SVK_SLAT_LOGIC_CONFIG"))) {
    conf_path = env_p;
  }

  return configure_slat_mlc_logic(conf_path);
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
