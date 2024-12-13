#include <logger_util.hpp>

svk_status read_slat_logger_config(pt::ptree &logger_info_pt,
                                   slat_logger_config &config) {
  config.log_level =
      logger_info_pt.get<std::string>("log_level", SLAT_LOGGER_LEVEL_DEFAULT);
  config.log_filename = logger_info_pt.get<std::string>(
      "log_file_name", SLAT_LOG_FILENAME_DEFAULT);
  config.log_file_count = logger_info_pt.get<uint64_t>(
      "log_file_count", SLAT_LOGGER_FILE_COUNT_DEFAULT);
  config.log_file_size = logger_info_pt.get<uint64_t>(
      "log_file_size", SLAT_LOGGER_FILE_SIZE_DEFAULT);
  config.log_sink_type = logger_info_pt.get<std::string>(
      "sink_type", SLAT_LOGGER_SINK_TYPE_DEFAULT);

  return SVK_STATUS_SUCCESS;
}

svk_status slat_initialize_logger(slat_logger_config config) {
  svk_status status = SVK_STATUS_FAIL;
  auto found = log_level_map.find(config.log_level);
  if (found == log_level_map.end()) {
    std::cout << "Matching log level for the [" << config.log_level
              << "] not found. Exiting" << std::endl;
    return status;
  }

  if (svk_logger_init(config.log_module_name.c_str(),
                      config.log_filename.c_str(), found->second,
                      config.log_file_count, config.log_file_size,
                      config.log_sink_type.c_str()) == SVK_STATUS_SUCCESS) {
    svk_logger(config.log_module_name.c_str(), level_E::INFO,
               "SVK logger is initialized");
    status = SVK_STATUS_SUCCESS;
  } else {
    std::cout << "SVK" << config.log_module_name
              << "logger initialization failed" << std::endl;
  }
  return status;
}