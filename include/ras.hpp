
#ifndef __RAS_HPP__
#define __RAS_HPP__

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <iostream>
#include <memory>
#include <unordered_map>

#include "framework_downstream.h"
#include "ras_adapters_helper.hpp"
#include "ras_exports.h"
#include "svk_logger.hpp"
#include "utils/logic_module_manager.hpp"

constexpr const char *RAS_LOG = "ras_internal.log";

// TODO: Hardcoding this path for now. This will be provided by the header from
// the svk-core repo in the future
constexpr const char *SVK_FEATURE_MODULE_PATH =
    "/usr/local/svk/feature_modules";

constexpr const char *FEATURE_MODULE_RAS_PATH =
    "/usr/local/svk/feature_modules/ras";
constexpr const char *FEATURE_MODULE_RAS_CONFIG_PATH =
    "/usr/local/svk/feature_modules/ras/config";
constexpr const char *FEATURE_MODULE_RAS_LIB_PATH =
    "/usr/local/svk/feature_modules/ras/lib64";
constexpr const char *RAS_CONFIG_FILE_DEFAULT =
    "/usr/local/svk/feature_modules/ras/config/config.json";

constexpr const char *RAS_LOGGER_LEVEL_DEFAULT = "TRACE";
constexpr const char *RAS_LOGGER_FILE_NAME_DEFAULT = "/var/log/svk/ras.log";
constexpr int RAS_LOGGER_FILE_COUNT_DEFAULT = 1;
constexpr int RAS_LOGGER_FILE_SIZE_DEFAULT = 1048576;
constexpr int RAS_MONITOR_INTERVAL_DEFAULT = 60;
constexpr const char *RAS_LOGGER_SINK_TYPE_DEFAULT = "rotating_file";

constexpr const char *RAS_DEFAULT_ADAPTERS_DIRECTORY =
    "/usr/local/svk/ras/adapters";

/**
 * @struct ras_conf
 * @brief struct containing ras related configs
 *
 * @var ras_conf::feat_modules_dir
 *  The directory for the svk-ras feature module
 *
 * @var ras_conf::log_level
 *  log level: e.g, the logger intialized with "ERROR" level will disable the
 * "INFO" level logging
 *
 * @var ras_conf::log_file_name
 *  path for the log file
 *
 * @var ras_conf::log_file_count
 *  number of log files
 *
 * @var ras_conf::log_file_size
 *  size of each log file
 *
 * @var ras_conf::log_sink_type
 *  sink type for logger
 *
 */

typedef struct {
  // TODO: Refactor Log config to sub struct
  std::string log_level;
  std::string log_file_name;
  uint64_t log_file_count;
  uint64_t log_file_size;
  uint64_t monitor_interval;
  std::string log_sink_type;
  std::string adapters_directory;
} ras_conf;

class ras_monitor;

struct ras_context_s {
  ras_monitor *monitor_context;
  bool initialized;
  ras_adapter_helper *ras_adapter_helper_;
  std::mutex ctx_mutex;
};
extern uint64_t g_monitor_interval;
svk_status parsing_ras_conf(const std::string &, ras_conf *);

// Check if RAS shutdown has been initiated (for detached threads)
bool ras_is_shutdown();
#endif  // __RAS_HPP__
