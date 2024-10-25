#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <iostream>
#include <memory>

#include "logic_interface/svk_logic_struct.h"
#include "svk_logger.h"
#include "svk_slat_hlpr.hpp"

#define LOG_MSG_MAX_SIZE (1024)
#define LIBRARY_SUFFIX ".so"
using namespace std;

/**
 * @cond INTERNAL
 */
// Function pointer declaration for casting void* from dlsym
using initialize_logic_module = svk_status (*)(void *init_param);
using get_supported_logic_details =
    svk_status (*)(svk_logic_module_details *details);
using execute_logic_sync = svk_status (*)(svk_logic_cmd *pass_thru,
                                          svk_logic_input *input,
                                          svk_logic_output *output);
using execute_logic_async = svk_status (*)(svk_logic_cmd *pass_thru,
                                           svk_postprocess_fn *postprocess_fn);
using cleanup_logic_module = svk_status (*)(void *);

// Global variable to use for Framework service commands
const std::unique_ptr<SLATrackerSvc> g_slat_service =
    std::make_unique<SLATrackerSvc>();

/* Private SLATrackerSvc helper methods */

svk_status SLATrackerSvc::read_slat_config_file(
    const std::string slat_conf_file, slat_config *config) const {
  svk_status status = SVK_STATUS_SUCCESS;
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(slat_conf_file, root);
    pt::ptree slat_config_pt = root.get_child(SLAT_CONF_SECTION_TAG);

    config->slat_logic_lib_dir =
        slat_config_pt.get("logic_lib_dir", SLAT_LOGIC_LIB_DIR_DEFAULT);

    try {
      pt::ptree logger_info_pt = slat_config_pt.get_child("logger");
      config->log_level = logger_info_pt.get<std::string>(
          "log_level", SLAT_LOGGER_LEVEL_DEFAULT);
      config->log_filename = logger_info_pt.get<std::string>(
          "log_file_name", SLAT_LOG_FILENAME_DEFAULT);
      config->log_file_count = logger_info_pt.get<uint64_t>(
          "log_file_count", SLAT_LOGGER_FILE_COUNT_DEFAULT);
      config->log_file_size = logger_info_pt.get<uint64_t>(
          "log_file_size", SLAT_LOGGER_FILE_SIZE_DEFAULT);
      config->log_sink_type = logger_info_pt.get<std::string>(
          "sink_type", SLAT_LOGGER_SINK_TYPE_DEFAULT);
    } catch (std::exception &e) {
      std::cout << "Unable to read Logger section of SLAT in the config file. "
                   "Falling back to default values. Error -> "
                << e.what() << std::endl;
      // Assign defaults
      config->log_level = SLAT_LOGGER_LEVEL_DEFAULT;
      config->log_filename = SLAT_LOG_FILENAME_DEFAULT;
      config->log_file_count = SLAT_LOGGER_FILE_COUNT_DEFAULT;
      config->log_file_size = SLAT_LOGGER_FILE_SIZE_DEFAULT;
      config->log_sink_type = SLAT_LOGGER_SINK_TYPE_DEFAULT;
    }
  } catch (std::exception &e) {
    std::cerr
        << "Unable to read SLAT config file. Assigning default value. Error -> "
        << e.what() << std::endl;
    config->slat_logic_lib_dir = SLAT_LOGIC_LIB_DIR_DEFAULT;
  }

  return status;
}

svk_status SLATrackerSvc::initialize_logger(const slat_config config) const {
  svk_status status = SVK_STATUS_FAIL;
  auto found = slat_log_level_map.find(config.log_level);
  if (found == slat_log_level_map.end()) {
    std::cout << "Matching log level for the [" << config.log_level
              << "] not found. Exiting" << std::endl;
    return status;
  }

  if (svk_logger_init(SLAT_LOGGER_MODULE_NAME, config.log_filename.c_str(),
                      found->second, config.log_file_count,
                      config.log_file_size,
                      config.log_sink_type.c_str()) == SVK_STATUS_SUCCESS) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
               "SVK SLAT logger is initialized");
    status = SVK_STATUS_SUCCESS;
  } else {
    std::cout << "SVK SLAT logger initialization failed" << std::endl;
  }
  return status;
}

svk_status SLATrackerSvc::Initialize(const char *slat_config_file) {
  svk_status status = SVK_STATUS_FAIL;
  slat_config config;

  status = read_slat_config_file(slat_config_file, &config);
  if (status != SVK_STATUS_SUCCESS) {
    return SVK_STATUS_INVALID_CONFIG;
  }

  status = initialize_logger(config);
  if (status != SVK_STATUS_SUCCESS) {
    return SVK_STATUS_FAIL;
  }

  return status;
}

// Actual implementation of the feature module functions

extern "C" svk_status initialize(void *details) {
  const char *env_p;
  svk_status status = SVK_STATUS_FAIL;
  std::string conf_path;
  struct stat f_stat;

  if ((env_p = std::getenv("SVK_SLAT_CONFIG"))) {
    conf_path = env_p;
  } else {
    conf_path = SLAT_CONFIG_FILE_DEFAULT;
  }

  if (stat(conf_path.c_str(), &f_stat) != 0) {
    std::cerr << "SLA Tracker service couldn't find the config file - "
              << conf_path << std::endl;
    status = SVK_STATUS_FAIL;
    return status;
  }

  if (g_slat_service == nullptr) {
    std::cerr << "SLA Tracker service object was unable to be allocated"
              << std::endl;
    status = SVK_STATUS_FAIL;
  } else {
    status = g_slat_service->Initialize(conf_path.c_str());
  }

  return status;
}

extern "C" svk_status get_supported_feature_list(feature_id *feature,
                                                 char *feature_names) {
  if (feature == nullptr || feature_names == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "Get supported feature list called with nullptr params");
    return SVK_STATUS_FAIL;
  }
  *feature = feature_id::SLA_TRACKER;
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
             "Get supported feature list returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status is_license_valid(void *license) {
  if (license == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "is_license_valid function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "License validated successfully.");
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status configure_device_if_any(void *config_details,
                                              svk_device_ctx *device_handles,
                                              uint64_t length, void *resp) {
  if (config_details == nullptr || device_handles == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "configure_device_if_any function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "configure_device_if_any returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status execute_sync(svk_pass_thru_cmd *cmd, svk_input *input,
                                   svk_output *output) {
  if (cmd == nullptr || input == nullptr || output == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "execute_sync function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "execute_sync returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status execute_async(svk_pass_thru_cmd *pass_thru,
                                    svk_postprocess_fn *postprocess_fn) {
  if (pass_thru == nullptr || postprocess_fn == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "execute_async function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "execute_async returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status clean_up(void *param) {
  if (param == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "clean_up function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "clean_up returned successfully.");

  return SVK_STATUS_SUCCESS;
}
