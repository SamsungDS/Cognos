#ifndef __SVK_SLAT_HLPR_HPP__
#define __SVK_SLAT_HLPR_HPP__

#include <dirent.h>
#include <dlfcn.h>
#include <sys/inotify.h>

#include <string>
#include <thread>
#include <unordered_map>

// TODO: Need to finalize the default location in case we cannot get this arg
#define SLAT_CONFIG_FILE_DEFAULT "/etc/svk/slat_config.json"

#define SLAT_LOG_FILENAME_DEFAULT "/var/log/svk/slat.log"
#define SLAT_CONF_SECTION_TAG "slat"
#define SLAT_LOGIC_LIB_DIR_DEFAULT "/usr/local/svk/feature_libs/slat/logic_libs"
#define SLAT_LOGGER_MODULE_NAME "slat"
#define SLAT_LOGGER_FILE_COUNT_DEFAULT 10
#define SLAT_LOGGER_FILE_SIZE_DEFAULT 1048576ULL  // 1MB default max file size
#define SLAT_LOGGER_LEVEL_DEFAULT "INFO"
#define SLAT_LOGGER_SINK_TYPE_DEFAULT "rotating_file"

const std::unordered_map<std::string, level_E> slat_log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

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
  const std::unordered_map<std::string, level_E> log_level_map = {
      {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
      {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
      {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
      {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
      {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};
  mutable std::unordered_map<char *, svk_logic_module_details *>
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
};

extern "C" {
// Creating the dlsym function wrapper for mocking in the UTs
void *my_dlopen(const char *filename, int flags);
void *my_dlsym(void *handle, const char *symbol);
int my_dlclose(void *handle);
}

#endif /* __SVK_SLAT_HLPR_HPP__ */
