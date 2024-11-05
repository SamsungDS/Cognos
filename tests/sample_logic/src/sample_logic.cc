#include <string.h>
#include <sys/stat.h>

#include <iostream>
#include <memory>

#include "logic_interface/svk_logic_interface.h"
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

#define SLAT_LOGIC_CONFIG_FILE_DEFAULT "/etc/svk/slat_logic.json"
#define SLAT_LOGIC_LOG_FILENAME_DEFAULT "/var/log/svk/slat_logic.log"
#define SLAT_LOGIC_CONF_SECTION_TAG "sample_logic"
#define SLAT_LOGIC_LOGGER_MODULE_NAME "slat_logic"
#define SLAT_LOGIC_LOGGER_FILE_COUNT_DEFAULT 10
#define SLAT_LOGIC_LOGGER_FILE_SIZE_DEFAULT \
  1048576ULL  // 1MB default max file size
#define SLAT_LOGIC_LOGGER_LEVEL_DEFAULT "INFO"
#define SLAT_LOGIC_LOGGER_SINK_TYPE_DEFAULT "rotating_file"

svk_status read_slat_config_file(const std::string slat_conf_file,
                                 slat_logic_config *config) {
  svk_status status = SVK_STATUS_FAIL;
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(slat_conf_file, root);
    pt::ptree slat_config_pt = root.get_child(SLAT_LOGIC_CONF_SECTION_TAG);

    try {
      pt::ptree logger_info_pt = slat_config_pt.get_child("logger");
      config->log_level = logger_info_pt.get<std::string>(
          "log_level", SLAT_LOGIC_LOGGER_LEVEL_DEFAULT);
      config->log_filename = logger_info_pt.get<std::string>(
          "log_file_name", SLAT_LOGIC_LOG_FILENAME_DEFAULT);
      config->log_file_count = logger_info_pt.get<uint64_t>(
          "log_file_count", SLAT_LOGIC_LOGGER_FILE_COUNT_DEFAULT);
      config->log_file_size = logger_info_pt.get<uint64_t>(
          "log_file_size", SLAT_LOGIC_LOGGER_FILE_SIZE_DEFAULT);
      config->log_sink_type = logger_info_pt.get<std::string>(
          "sink_type", SLAT_LOGIC_LOGGER_SINK_TYPE_DEFAULT);
    } catch (std::exception &e) {
      std::cout << "Unable to read Logger section of SLAT sample-logic in the "
                   "config file. Falling back to default values. Error -> "
                << e.what() << std::endl;
      // Use defaults
      config->log_level = "INFO";
      config->log_filename = SLAT_LOGIC_LOG_FILENAME_DEFAULT;
      config->log_file_count = SLAT_LOGIC_LOGGER_FILE_COUNT_DEFAULT;
      config->log_file_size = SLAT_LOGIC_LOGGER_FILE_SIZE_DEFAULT;
      config->log_sink_type = "rotating_file";
    }
    status = SVK_STATUS_SUCCESS;
  } catch (std::exception &e) {
    std::cerr << "Unable to read SLAT sample-logic config file. Error -> "
              << e.what() << std::endl;
  }

  return status;
}

svk_status initialize_logger(const slat_logic_config config) {
  svk_status status = SVK_STATUS_FAIL;
  auto found = log_level_map.find(config.log_level);
  if (found == log_level_map.end()) {
    std::cout << "Matching log level for the [" << config.log_level
              << "] not found. Exiting" << std::endl;
    return status;
  }

  if (svk_logger_init(SLAT_LOGIC_LOGGER_MODULE_NAME,
                      config.log_filename.c_str(), found->second,
                      config.log_file_count, config.log_file_size,
                      config.log_sink_type.c_str()) == 0) {
    svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO,
               "SVK SLAT Sample Logic logger is initialized");
    status = SVK_STATUS_SUCCESS;
  } else {
    std::cout << "SVK SLAT Sample Logic logger initialization failed"
              << std::endl;
  }
  return status;
}

extern "C" svk_status initialize_logic_module(void *init_param) {
  const char *env_p;
  svk_status status = SVK_STATUS_FAIL;
  std::string conf_path;
  struct stat f_stat;
  slat_logic_config config;

  if ((env_p = std::getenv("SVK_SLAT_LOGIC_CONFIG"))) {
    conf_path = env_p;
  } else {
    conf_path = SLAT_LOGIC_CONFIG_FILE_DEFAULT;
  }

  if (stat(conf_path.c_str(), &f_stat) != 0) {
    std::cerr << "SLA Tracker service couldn't find the config file - "
              << conf_path << std::endl;
    status = SVK_STATUS_FAIL;
    return status;
  }

  status = read_slat_config_file(conf_path, &config);
  if (status != 0) {
    return SVK_STATUS_INVALID_CONFIG;
  }

  status = initialize_logger(config);
  if (status != 0) {
    return SVK_STATUS_FAIL;
  }

  return status;
}

extern "C" svk_status get_supported_logic_details(
    svk_logic_module_details *details) {
  const char *env_string;
  char log_msg[256];

  env_string = std::getenv("SVK_SLAT_SAMPLE_LOGIC_SUPPORT_FAIL");
  sprintf(
      log_msg,
      "sample logic environment var SVK_SLAT_SAMPLE_LOGIC_SUPPORT_FAIL [%s]",
      env_string);
  svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO, log_msg);

  if (details == nullptr && strcmp(env_string, "Fail") == 0) {
    svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO,
               "sample logic's get_supported_logic_details failed");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO,
             "sample logic's get_supported_logic_details called");

  details->execute_logic_sync = &execute_logic_sync;
  details->execute_logic_async = &execute_logic_async;
  details->cleanup_logic_module = &cleanup_logic_module;

  return SVK_STATUS_SUCCESS;
}

// Assuming that input and output buffers contain strings
extern "C" svk_status execute_logic_sync(svk_logic_cmd *cmd,
                                         svk_logic_input *input,
                                         svk_logic_output *output) {
  svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO,
             "sample logic's execute_logic_sync called");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status execute_logic_async(svk_logic_cmd *pass_thru,
                                          svk_postprocess_fn *postprocess_fn) {
  svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO,
             "sample logic's execute_logic_async called");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status cleanup_logic_module(void *param) {
  svk_logger(SLAT_LOGIC_LOGGER_MODULE_NAME, level_E::INFO,
             "sample logic's cleanup_logic_module called");

  return SVK_STATUS_SUCCESS;
}
