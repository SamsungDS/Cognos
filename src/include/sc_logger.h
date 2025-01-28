#ifndef __LOGGER_WRAPPER_H
#define __LOGGER_WRAPPER_H
#include <string>

#include "svk_logger.h"

#define LOG_CONF_FILE "log.conf"

// default logging constants
constexpr char CXL_LOG_MODULENAME_DEFAULT[] = "CXL";
constexpr char CXL_LOG_FILENAME_DEFAULT[] = "/var/log/svk/svk_cxl_feature.log";
constexpr int CXL_LOGGER_FILE_COUNT_DEFAULT = 10;
constexpr uint64_t CXL_LOGGER_FILE_SIZE_DEFAULT = 1048576ULL;  // 1MB
constexpr char CXL_LOGGER_LEVEL_DEFAULT[] = "INFO";
constexpr char CXL_LOGGER_SINK_TYPE_DEFAULT[] = "rotating_file";

// defined in sc_servicer
extern std::string log_module_name;

#define LOG(level, message) \
  svk_logger(log_module_name.c_str(), level, std::string(message).c_str());

#endif
