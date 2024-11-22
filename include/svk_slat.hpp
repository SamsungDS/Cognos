#ifndef __SVK_SLAT_HPP__
#define __SVK_SLAT_HPP__

#include <dirent.h>
#include <dlfcn.h>
#include <sys/inotify.h>

#include <string>
#include <thread>
#include <unordered_map>

#include "svk_logger.hpp"

// Hardcoding this path for now. This will be provided by the header from the
// svk-core repo in the future
#define SVK_FEATURE_MODULE_PATH "/usr/local/svk/feature_modules"

#define FEATURE_MODULE_SLAT_PATH SVK_FEATURE_MODULE_PATH "/slat"
#define FEATURE_MODULE_SLAT_CONFIG_PATH FEATURE_MODULE_SLAT_PATH "/config"
#define FEATURE_MODULE_SLAT_LIB_PATH FEATURE_MODULE_SLAT_PATH "/lib64"
#define SLAT_FEATURE_LOGIC_MODULES_PATH \
  FEATURE_MODULE_SLAT_PATH "/logic_modules"

#define SLAT_CONFIG_FILE_DEFAULT FEATURE_MODULE_SLAT_CONFIG_PATH "/config.json"

// Expects the logic modules to provide the feature_name as "slat" as part of
// get_supported_logic_details If not provided, then we ignore the logic module
#define SLAT_FEATURE_MODULE_NAME "slat"

#define SLAT_LOG_FILENAME_DEFAULT "/var/log/svk/slat.log"
#define SLAT_CONF_SECTION_TAG SLAT_FEATURE_MODULE_NAME
#define SLAT_LOGGER_MODULE_NAME SLAT_FEATURE_MODULE_NAME
#define SLAT_LOGGER_FILE_COUNT_DEFAULT 10
#define SLAT_LOGGER_FILE_SIZE_DEFAULT 1048576ULL  // 1MB default max file size
#define SLAT_LOGGER_LEVEL_DEFAULT "INFO"
#define SLAT_LOGGER_SINK_TYPE_DEFAULT "rotating_file"

using slat_config = struct slat_config {
  std::string slat_logic_lib_dir;
  std::string log_level;
  std::string log_filename;
  std::string log_sink_type;
  int log_file_count;
  uint64_t log_file_size;
};

// Making this global to be able to mock functions for testing
class SLATrackerSvc {
 private:
  mutable std::unordered_map<std::string, svk_logic_module_details *>
      logic_modules_map;
  std::string curr_log_level;
  std::string svk_conf_path;
  svk_status read_slat_config_file(const std::string slat_conf_file,
                                   slat_config *config) const;
  svk_status initialize_logger(const slat_config config) const;
  svk_status load_logic_modules(const std::string &logic_modules_lib_dir) const;

 public:
  // In order to comply with Rule-of-Zero, manage class init and deletion
  // through APIs and not through constructors/destructors. Must call init and
  // cleanup from this class to ensure resources are managed properly
  svk_status Initialize(const char *svk_config);
  svk_logic_module_details *getLogicDetails(char *logic_module_name);
};

extern "C" {
// Creating the dlsym function wrapper for mocking in the UTs
void *my_dlopen(const char *filename, int flags);
void *my_dlsym(void *handle, const char *symbol);
int my_dlclose(void *handle);
}

#endif /* __SVK_SLAT_HPP__ */
