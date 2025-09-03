
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

#define RAS_LOG "ras_internal.log"

// TODO: Hardcoding this path for now. This will be provided by the header from
// the svk-core repo in the future
#define SVK_FEATURE_MODULE_PATH "/usr/local/svk/feature_modules"

#define FEATURE_MODULE_RAS_PATH SVK_FEATURE_MODULE_PATH "/ras"
#define FEATURE_MODULE_RAS_CONFIG_PATH FEATURE_MODULE_RAS_PATH "/config"
#define FEATURE_MODULE_RAS_LIB_PATH FEATURE_MODULE_RAS_PATH "/lib64"
#define RAS_CONFIG_FILE_DEFAULT FEATURE_MODULE_RAS_CONFIG_PATH "/config.json"

#define RAS_LOGGER_LEVEL_DEFAULT "TRACE"
#define RAS_LOGGER_FILE_NAME_DEFAULT "/var/log/svk/ras.log"
#define RAS_LOGGER_FILE_COUNT_DEFAULT 1
#define RAS_LOGGER_FILE_SIZE_DEFAULT 1048576
#define RAS_LOGGER_SINK_TYPE_DEFAULT "rotating_file"

#define RAS_DEFAULT_ADAPTERS_DIRECTORY "/usr/local/svk/ras/adapters"

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
#endif  // __RAS_HPP__
