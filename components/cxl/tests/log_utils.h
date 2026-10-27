#ifndef TEST_UTILS_H
#define TEST_UTILS_H
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#define LOG_CONF_FILE "log.conf"

// Helper function to create log config file
inline void create_log_config_file() {
  std::ofstream log_conf(LOG_CONF_FILE);
  if (!log_conf) {
    std::cerr << "Error creating log configuration file!" << std::endl;
    return;
  }
  log_conf << R"({
        "cxl": {
            "logger": {
                "log_module_name": "CXL",
                "log_level": "INFO",
                "log_file_name": "test_svk_cxl.log",
                "log_file_count": 1,
                "log_file_size": 1048576,
                "sink_type": "rotating_file"
            }
        }
    })";
  log_conf.close();
}

// Helper function to remove log config file after tests
inline void remove_log_config_file() {
  if (std::filesystem::exists(LOG_CONF_FILE)) {
    if (std::remove(LOG_CONF_FILE) != 0) {
      std::cerr << "Warning: Failed to delete log config file!" << std::endl;
    }
  }
}

#endif
