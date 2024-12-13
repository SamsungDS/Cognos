#ifndef LOGGER_UTIL_HPP
#define LOGGER_UTIL_HPP

#include <framework_downstream.h>

#include <iostream>
#include <string>
#include <boost/property_tree/ptree.hpp>

#include "svk_logger.hpp"

#define SLAT_LOG_FILENAME_DEFAULT "/var/log/svk/slat.log"
#define SLAT_LOGGER_FILE_COUNT_DEFAULT 10
#define SLAT_LOGGER_FILE_SIZE_DEFAULT 1048576ULL  // 1MB default max file size
#define SLAT_LOGGER_LEVEL_DEFAULT "INFO"
#define SLAT_LOGGER_SINK_TYPE_DEFAULT "rotating_file"

using slat_logger_config = struct slat_logger_config_s {
  std::string log_module_name;
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

namespace pt = boost::property_tree;

svk_status slat_initialize_logger(slat_logger_config config);
svk_status read_slat_logger_config(pt::ptree &logger_info_pt,
                                   slat_logger_config &config);

#endif  // LOGGER_UTIL_HPP
