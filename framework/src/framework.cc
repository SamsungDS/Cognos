#include <bits/stdc++.h>
#include <errno.h>
#include <sys/select.h>
#include <sys/stat.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <utility>

#include "framework_service.hpp"
#include "framework_upstream.h"

using namespace std;
class FrameworkSvc;

/**
 * @cond INTERNAL
 */
// Function pointer declaration for casting void* from dlsym
using initialize = svk_status (*)(void *init_param);
using get_supported_feature_list = svk_status (*)(feature_id *feature,
                                                  char *feature_names);
using is_license_valid = svk_status (*)(void *);
using configure_device_if_any = svk_status (*)(void *config_details,
                                               svk_device_ctx *device_handles,
                                               uint64_t length, void *resp);
using execute_sync = svk_status (*)(svk_pass_thru_cmd *pass_thru,
                                    svk_input *input, svk_output *output);
using execute_async = svk_status (*)(svk_pass_thru_cmd *pass_thru,
                                     svk_postprocess_fn *postprocess_fn);
using clean_up = svk_status (*)(void *);

// Global variable to use for Framework service commands
const std::unique_ptr<FrameworkSvc> g_fw_service =
    std::make_unique<FrameworkSvc>();

// Global for actual functionality of C APIs. Need to keep this global for
// config reload thread since if it goes out of scope, the thread will crash
const featureInterface dl;

/* Private FrameworkSvc helper methods */

// Check if function pointer was set properly
bool FrameworkSvc::report_sym_error(void *fn, const dirent *entry, void *handle,
                                    const char *sym_name, int &num_failed_libs,
                                    svk_status &status,
                                    const featureInterface &feature_api) const {
  if (fn == nullptr) {
    const char *dlsym_error = dlerror();
    char err_msg[LOG_MSG_MAX_SIZE];
    snprintf(err_msg, LOG_MSG_MAX_SIZE,
             "Cannot load symbol '%s' for feature module '%s.' Error: %s\n",
             sym_name, entry->d_name, dlsym_error);
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, err_msg);

    feature_api.close_lib(handle);
    num_failed_libs++;
    status = SVK_STATUS_BAD_FEATURE_LIB;
    return true;
  } else {
    return false;
  }
}
// Load feature modules from config directory, using the interface for file/lib
// related functions
svk_status FrameworkSvc::load_feature_modules(
    const std::string &features_dir, void *init_param,
    const featureInterface &feature_api) const {
  svk_status status = SVK_STATUS_SUCCESS;
  svk_status &get_status = status;
  int num_failed_libs = 0;
  int &get_failed_libs = num_failed_libs;
  char log_msg[LOG_MSG_MAX_SIZE];

  DIR *dirfp = nullptr;
  struct dirent *entry = nullptr;
  // Open dir with feature libs
  snprintf(log_msg, LOG_MSG_MAX_SIZE, "Loading feature modules from %s",
           features_dir.c_str());
  svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
  dirfp = feature_api.open_dir(features_dir.c_str());
  if (dirfp == nullptr) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Unable to open feature lib directory: %s\n",
             features_dir.c_str());
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    return SVK_STATUS_FAIL;
  }

  entry = readdir(dirfp);
  // Loop through all libs in the dir
  for (; entry != nullptr; entry = readdir(dirfp)) {
    // Check if this is a shared lib
    std::string entry_name(entry->d_name);
    std::string feat_lib_suffix(FEAT_LIB_SUFFIX);
    // If dir entry is smaller than length(.so), skip the entry
    // Otherwise compare the last 3 chars to .so to see if it is valid
    if (entry_name.size() < feat_lib_suffix.size() ||
        entry_name.compare(entry_name.size() - feat_lib_suffix.size(),
                           feat_lib_suffix.size(), feat_lib_suffix) != 0) {
      continue;
    }

    // Check lib naming format for libsvk<feature_name>.so
    std::string feature_name = "";
    if (entry_name.length() > 9 && entry_name.substr(0, 6) == "libsvk") {
      // Only use <feature_name> for the key
      feature_name = entry_name.substr(6, entry_name.length() - 9);
    }

    std::string feature_lib_str = features_dir + "/" + entry->d_name;
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Attempting to load feature module functions for %s",
             entry->d_name);
    svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
    void *handle = feature_api.open_lib(feature_lib_str.c_str());
    if (!handle) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE, "Dlopen failure. Error: %s\n",
               dlerror());
      svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
      status = SVK_STATUS_BAD_FEATURE_LIB;
      num_failed_libs++;
      continue;
    }

    auto details = (svk_feature_details *)malloc(sizeof(svk_feature_details));

    // Try to load feature module function APIs from .so
    // If any fail, indicate this in the return value and move to next
    // feature
    details->initialize = (initialize)feature_api.get_sym(handle, "initialize");
    if (report_sym_error((void *)details->initialize, entry, handle,
                         "initialize", get_failed_libs, get_status,
                         feature_api)) {
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }
    details->get_supported_feature_list =
        (get_supported_feature_list)feature_api.get_sym(
            handle, "get_supported_feature_list");
    if (report_sym_error((void *)details->get_supported_feature_list, entry,
                         handle, "get_supported_feature_list", get_failed_libs,
                         get_status, feature_api)) {
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }
    details->is_license_valid =
        (is_license_valid)feature_api.get_sym(handle, "is_license_valid");
    if (report_sym_error((void *)details->is_license_valid, entry, handle,
                         "is_license_valid", get_failed_libs, get_status,
                         feature_api)) {
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }
    details->execute_sync =
        (execute_sync)feature_api.get_sym(handle, "execute_sync");
    if (report_sym_error((void *)details->execute_sync, entry, handle,
                         "execute_sync", get_failed_libs, get_status,
                         feature_api)) {
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }
    details->execute_async =
        (execute_async)feature_api.get_sym(handle, "execute_async");
    if (report_sym_error((void *)details->execute_async, entry, handle,
                         "execute_async", get_failed_libs, get_status,
                         feature_api)) {
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }
    details->clean_up = (clean_up)feature_api.get_sym(handle, "clean_up");
    if (report_sym_error((void *)details->clean_up, entry, handle, "clean_up",
                         get_failed_libs, get_status, feature_api)) {
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }
    // This downstream API is optional, don't throw error if it's not there.
    // Just adding info log for now.
    details->configure_device_if_any =
        (configure_device_if_any)feature_api.get_sym(handle,
                                                     "configure_device_if_any");
    if (details->configure_device_if_any == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Optional downstream API configure_device_if_any was not found "
               "for feature module %s. Ignore this message if it is not "
               "required for this feature module.",
               entry->d_name);
      svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
    }

    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Running initialize function for feature module %s",
             entry->d_name);
    svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
    if (details->initialize(init_param)) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Initialization for feature module '%s' returned "
               "non-zero, ignoring this feature module.",
               entry->d_name);
      svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
      status = SVK_STATUS_BAD_FEATURE_LIB;
      num_failed_libs++;
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
      continue;
    }

    bool inserted;
    if (feature_name.length() == 0) {
      // Use feature_id map if feature_name is not set
      feature_id curr_feature;
      char feature_names;
      details->get_supported_feature_list(&curr_feature, &feature_names);
      // insert fid/function pointers into map
      inserted = feature_map.insert(make_pair(curr_feature, details)).second;
      if (inserted) {
        snprintf(log_msg, LOG_MSG_MAX_SIZE,
                 "Feature module %s has been added to feature map using "
                 "feature id: %d.",
                 entry->d_name, curr_feature);
        svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
      }
    } else {
      // insert feature_name/function pointers into map if feature_name exists
      inserted =
          feature_name_map.insert(make_pair(feature_name, details)).second;
      if (inserted) {
        snprintf(log_msg, LOG_MSG_MAX_SIZE,
                 "Feature module %s has been added to feature map using "
                 "feature name %s.",
                 entry->d_name, feature_name.c_str());
        svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
      }
    }
    if (!inserted) {
      snprintf(
          log_msg, LOG_MSG_MAX_SIZE,
          "svk_feature_details for feature lib %s wasn't able to be "
          "added to map. You may be getting this error if multiple feature "
          "libs with the same feature id are in the features dir.",
          entry->d_name);
      svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
      num_failed_libs++;
      status = SVK_STATUS_BAD_FEATURE_LIB;
      free(details);
      // Set to null to ensure free only happens once
      details = nullptr;
    }
  }
  if (num_failed_libs) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE, "%d feature libs failed to load.",
             num_failed_libs);
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
  } else {
    svk_logger(CORE_LOGGER_NAME, level_E::INFO,
               "All feature libs loaded successfully.");
  }

  return status;
}
// Attempt to load logger options from the config, use defaults for any options
// that can't be found
svk_status FrameworkSvc::init_logger(
    boost::property_tree::ptree const &logger_info) {
  std::string log_level_str =
      logger_info.get<std::string>("log_level", CORE_DEFAULT_LOG_LEVEL);
  level_E log_level;
  try {
    log_level = log_level_map.at(log_level_str);
  } catch (std::out_of_range &) {
    // handle exception
    std::cout << "Invalid log level given, using default log level ERROR"
              << std::endl;
    log_level = log_level_map.at(CORE_DEFAULT_LOG_LEVEL);
  }

  curr_log_level = log_level_str;
  std::string file_name =
      logger_info.get<std::string>("log_file_name", CORE_DEFAULT_LOG_FILE);
  int file_count = logger_info.get<int>("log_file_count", 2);
  uint64_t file_size = logger_info.get<uint64_t>(
      "log_file_size", 1048576);  // 1MB default max file size
  std::string sink_type =
      logger_info.get<std::string>("sink_type", "rotating_file");

  if (svk_logger_init(CORE_LOGGER_NAME, file_name.c_str(), log_level,
                      file_count, file_size, sink_type.c_str()) == 0) {
    svk_logger(CORE_LOGGER_NAME, level_E::INFO, "Core logger is initialized");
    return SVK_STATUS_SUCCESS;
  } else {
    return SVK_STATUS_INVALID_CONFIG;
  }
}

// return svk status
svk_status FrameworkSvc::read_config(boost::property_tree::ptree &pt) const {
  try {
    boost::property_tree::read_json(svk_conf_path, pt);
  } catch (boost::property_tree::json_parser_error &e) {
    cerr << "Unable to read SVK config. Error -> " << e.what() << endl;
    return SVK_STATUS_INVALID_CONFIG;
  }

  return SVK_STATUS_SUCCESS;
}

/* Reload config helper functions */
int FrameworkSvc::initialize_inotify(int flags) const {
  char log_msg[LOG_MSG_MAX_SIZE];
  int fd;
  fd = inotify_init1(flags);
  if (fd < 0) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "inotify_init() error, unable to start config reload thread: %s",
             strerror(errno));
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
  }
  return fd;
}

int FrameworkSvc::set_file_watch(int fd, char const *watch_file_path) const {
  char log_msg[LOG_MSG_MAX_SIZE];
  // Add a watch to the specified filepath which will signal when a file is
  // modified Only return for errors unrelated to nonexistent config
  int wd = inotify_add_watch(fd, watch_file_path, IN_CLOSE_WRITE | IN_CREATE);
  if (int err = errno; wd < 0 && err != ENOENT) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "inotify_add_watch() error, unable to start config reload "
             "thread: %s",
             strerror(err));
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
  }
  return wd;
}

int FrameworkSvc::poll_for_config_change(int nfds, fd_set *readfds,
                                         fd_set *writefds, fd_set *exceptfds,
                                         timespec *timeout) const {
  char log_msg[LOG_MSG_MAX_SIZE];
  // When inotify detects a change in the file, select will unblock
  int ret_val = pselect(nfds, readfds, writefds, exceptfds, timeout, NULL);
  if (ret_val < 0) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "reload_config select() error, unable to continue config "
             "reload thread: %s",
             strerror(errno));
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
  }
  return ret_val;
}

/**
 * @brief Function for thread to monitor config changes
 *
 *
 */
void FrameworkSvc::reload_config() {
  size_t event_size = sizeof(struct inotify_event);
  int fd;
  char buffer[event_size];
  char log_msg[LOG_MSG_MAX_SIZE];
  // Initialize inotify with no flags, exit thread if invalid fd returned
  fd = initialize_inotify(0);
  if (fd < 0) {
    return;
  }

  fd_set descriptors;
  FD_ZERO(&descriptors);
  // timeout for checking for cleanup
  struct timespec ts;
  ts.tv_nsec = 0;

  while (reload_flag) {
    // Add watch to file in the loop in case original file is deleted
    // due to editor behavior or user deletion
    if (set_file_watch(fd, svk_conf_path.c_str()) == -1) {
      // Couldn't watch file, stop thread
      close(fd);
      return;
    }

    ts.tv_sec = conf_poll_timer;
    // Add inotify to select() fd set
    FD_SET(fd, &descriptors);
    if (poll_for_config_change(fd + 1, &descriptors, NULL, NULL, &ts) < 0) {
      // pselect returned error, stop thread
      close(fd);
      return;
    } else if (FD_ISSET(fd, &descriptors)) {  // If file was created or modified
      if (ssize_t length = read(fd, buffer, event_size); length < 0) {
        snprintf(log_msg, LOG_MSG_MAX_SIZE, "reload_config read() error: %s",
                 strerror(errno));
        svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
      }

      // reload config func
      // Change log level
      level_E new_log_level;
      boost::property_tree::ptree pt;
      if (read_config(pt) != SVK_STATUS_SUCCESS) {
        svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
                   "Invalid config was attempted to be read, ignoring "
                   "this change to config file.");
        continue;
      }
      // Check if new poll timer
      conf_poll_timer = pt.get<int>("core.conf_poll_timer", conf_poll_timer);

      // if the log level from config is invalid, use current log level
      // no need to exit, just continue loop
      std::string level =
          pt.get<std::string>("core.logger.log_level", curr_log_level);
      if (level != curr_log_level) {
        try {
          // check if log level is proper
          snprintf(log_msg, LOG_MSG_MAX_SIZE,
                   "New log level: %s; old log level: %s", level.c_str(),
                   curr_log_level.c_str());
          svk_logger(CORE_LOGGER_NAME, level_E::DEBUG, log_msg);
          new_log_level = log_level_map.at(level);
          svk_logger_change_log_level(CORE_LOGGER_NAME, new_log_level);
          curr_log_level = level;
        } catch (std::out_of_range &) {
          svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
                     "Invalid log level given in config, ignoring "
                     "new log level.");
        }
      } else {  // Same log level, continue loop
        snprintf(log_msg, LOG_MSG_MAX_SIZE, "Same log level given: %s",
                 level.c_str());
        svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);

        continue;
      }

      // Update feature modules when load API is done in the future
    }
  }
  close(fd);
  return;
}

svk_status FrameworkSvc::get_feature_details(
    svk_feature_details const **details, feature_key feat_key) const {
  char log_msg[LOG_MSG_MAX_SIZE];
  try {
    if (std::holds_alternative<std::string>(feat_key)) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Feature name given, using feature_name_map for getting feature "
               "details.");
      svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
      *details = feature_name_map.at(std::get<std::string>(feat_key));
    } else {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Feature name not given, using feature_id for getting feature "
               "details.");
      svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg);
      *details = feature_map.at(std::get<feature_id>(feat_key));
    }
  } catch (std::out_of_range &e) {
    snprintf(
        log_msg, LOG_MSG_MAX_SIZE,
        "Feature id or name is not registered with the map, unable to run "
        "execute or configure_devices with this feature module. Exception: %s",
        e.what());
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    return SVK_STATUS_FAIL;
  }
  return SVK_STATUS_SUCCESS;
}

svk_status FrameworkSvc::destroy_feat_map(void *param) const {
  char log_msg[LOG_MSG_MAX_SIZE];
  for (const auto &[key, value] : feature_map) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Clearing up svk_feature_details for feature_id %d.",
             (uint32_t)key);
    svk_logger(CORE_LOGGER_NAME, level_E::DEBUG, log_msg);
    value->clean_up(param);
    free(value);
  }
  feature_map.clear();
  for (const auto &[key, value] : feature_name_map) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Clearing up svk_feature_details for feature_name %s.",
             key.c_str());
    svk_logger(CORE_LOGGER_NAME, level_E::DEBUG, log_msg);
    value->clean_up(param);
    free(value);
  }
  feature_name_map.clear();
  if (feature_map.empty()) {
    svk_logger(CORE_LOGGER_NAME, level_E::INFO,
               "Feature map cleared successfully.");
    return SVK_STATUS_SUCCESS;
  } else {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Feature map unable to be cleared.");
    return SVK_STATUS_FAIL;
  }
}

/* End of private helper methods */

/* Public FrameworkSvc functions */

// Injecting dlInterface dependency for testing, only to be used while loading
// feature libs
svk_status FrameworkSvc::FrameworkSvcInit(const char *svk_config,
                                          void *init_param,
                                          const featureInterface &dep_inj) {
  svk_status status = SVK_STATUS_FAIL;
  svk_conf_path = svk_config;
  // Set config tree for convenience
  boost::property_tree::ptree pt;
  status = read_config(pt);
  if (status != SVK_STATUS_SUCCESS) {
    // Return if config file is not able to be set
    return status;
  }

  // Initialize logger using config
  boost::property_tree::ptree logger_info;
  try {
    logger_info = pt.get_child("core.logger");
  } catch (boost::property_tree::ptree_error &e) {
    std::cerr << "Error while parsing logger config section: " << e.what()
              << ". Logger defaults will be used." << std::endl;
  }
  status = init_logger(logger_info);
  if (status != SVK_STATUS_SUCCESS) {
    std::cerr << "Logger unable to be initialized" << std::endl;
    return status;
  }

  // Load feature modules
  std::string features_dir =
      pt.get<std::string>("core.feat_modules_dir", CORE_DEFAULT_LIBS_PATH);
  status = load_feature_modules(features_dir, init_param, dep_inj);

  // Check if we want to run config reload thread
  reload_flag = pt.get<bool>("core.reload_config", false);
  conf_poll_timer = pt.get<int>("core.conf_poll_timer", 5);
  // Start config reload thread
  if (reload_flag) {
    try {
      conf_reload = std::thread(&FrameworkSvc::reload_config, this);
    } catch (std::exception &e) {
      char log_msg[LOG_MSG_MAX_SIZE];
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Exception while spawning config reload thread: %s.", e.what());
      svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    }
  }

  return status;
}

svk_status FrameworkSvc::FrameworkSvcConfigureDev(
    svk_pass_thru_cmd const *pass_thru, void *config_details,
    svk_device_ctx *device_handles, uint64_t length, void *resp) const {
  char log_msg[LOG_MSG_MAX_SIZE];
  svk_feature_details const *feature_details = nullptr;
  if (svk_status res =
          get_feature_details(&feature_details, pass_thru->feat_id);
      res != SVK_STATUS_SUCCESS) {
    return res;
  }
  if (!feature_details->configure_device_if_any) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "configure_device_if_any function called but not is not set for "
             "feature_id %d.",
             (uint32_t)pass_thru->feat_id);
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    return SVK_STATUS_FAIL;
  }
  return feature_details->configure_device_if_any(config_details,
                                                  device_handles, length, resp);
}

svk_status FrameworkSvc::FrameworkSvcProcessCommand(
    svk_pass_thru_cmd *pass_thru, svk_input *input, svk_output *output,
    svk_postprocess_fn *postprocess_fn) const {
  svk_status exec_res = SVK_STATUS_FAIL;
  char log_msg[LOG_MSG_MAX_SIZE];
  svk_feature_details const *feature_details = nullptr;
  if (pass_thru->len) {
    // If the feature name/len is provided, use it to get the feature details
    char feature_name[pass_thru->len + 1];
    snprintf(feature_name, sizeof(feature_name), "%s",
             (char *)pass_thru->out_format);
    exec_res = get_feature_details(&feature_details, std::string(feature_name));
  } else {
    exec_res = get_feature_details(&feature_details, pass_thru->feat_id);
  }

  if (exec_res != SVK_STATUS_SUCCESS) return exec_res;

  // Synchrounous execute
  if (postprocess_fn == nullptr) {
    exec_res = feature_details->execute_sync(pass_thru, input, output);
    if (exec_res != SVK_STATUS_SUCCESS) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Synchronous execute failed for feature_id %d.",
               (uint32_t)pass_thru->feat_id);
      svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    }
  } else {  // Postprocess fn exists, this is async IO
    exec_res = feature_details->execute_async(pass_thru, postprocess_fn);
    if (exec_res != SVK_STATUS_SUCCESS) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Async execute call for feature_id %d returned an error.",
               (uint32_t)pass_thru->feat_id);
      svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    }
  }

  return exec_res;
}

svk_status FrameworkSvc::FrameworkSvcCleanup(void *param) {
  svk_status status = SVK_STATUS_SUCCESS;
  if (reload_flag) {
    reload_flag = false;
    conf_reload.join();
  }

  status = destroy_feat_map(param);

  return status;
}

/**
 * @endcond
 */

extern "C" svk_status initialize_svk(const char *svk_conf_file,
                                     void *init_param) {
  // Ignoring storage context stuff for now
  svk_status status = SVK_STATUS_SUCCESS;
  std::string conf_path;
  const char *env_p;
  if (svk_conf_file == nullptr) {
    if ((env_p = std::getenv("SVK_FW_CONFIG"))) {
      conf_path = env_p;
    } else {
      conf_path = CORE_DEFAULT_CONF;
    }
  } else {
    conf_path = svk_conf_file;
  }

  if (g_fw_service == nullptr) {
    std::cerr << "FrameworkSvc object was unable to be allocated" << std::endl;
    status = SVK_STATUS_FAIL;
  } else {
    status = g_fw_service->FrameworkSvcInit(conf_path.c_str(), init_param, dl);
  }

  return status;
}

extern "C" svk_status configure_svk_device_if_any(
    svk_pass_thru_cmd *pass_thru, void *config_details,
    svk_device_ctx *device_handles, uint64_t length, void *resp) {
  return g_fw_service->FrameworkSvcConfigureDev(pass_thru, config_details,
                                                device_handles, length, resp);
}

extern "C" svk_status execute_svk_feature_sync(svk_pass_thru_cmd *pass_thru,
                                               svk_input *input,
                                               svk_output *output) {
  svk_status status = SVK_STATUS_SUCCESS;
  status =
      g_fw_service->FrameworkSvcProcessCommand(pass_thru, input, output, NULL);
  return status;
}

extern "C" svk_status execute_svk_feature_async(
    svk_pass_thru_cmd *pass_thru, svk_postprocess_fn *postprocess_fn) {
  svk_status status = SVK_STATUS_SUCCESS;
  status = g_fw_service->FrameworkSvcProcessCommand(pass_thru, NULL, NULL,
                                                    postprocess_fn);
  return status;
}

extern "C" svk_status cleanup_svk(svk_device_ctx *ctx, void *param) {
  svk_status status = SVK_STATUS_SUCCESS;
  status = g_fw_service->FrameworkSvcCleanup(param);
  svk_logger(CORE_LOGGER_NAME, level_E::INFO, "SVK Cleanup finished.");
  svk_logger_close(CORE_LOGGER_NAME);
  return status;
}
