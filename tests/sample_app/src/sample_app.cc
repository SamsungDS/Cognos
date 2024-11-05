#include <dirent.h>
#include <dlfcn.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <boost/program_options.hpp>
#include <iostream>
#include <memory>

#include "framework_downstream.h"
#include "framework_struct.h"

namespace po = boost::program_options;
using namespace std;

#define LIBRARY_SUFFIX ".so"

#define LOG_MSG_MAX_SIZE 512

// Function pointer declaration for casting void* from dlsym
using t_initialize = svk_status (*)(void *init_param);
using t_get_supported_feature_list = svk_status (*)(feature_id *feature,
                                                    char *feature_names);
using t_is_license_valid = svk_status (*)(void *);
using t_configure_device_if_any = svk_status (*)(void *config_details,
                                                 svk_device_ctx *device_handles,
                                                 uint64_t length, void *resp);
using t_execute_sync = svk_status (*)(svk_pass_thru_cmd *pass_thru,
                                      svk_input *input, svk_output *output);
using t_execute_async = svk_status (*)(svk_pass_thru_cmd *pass_thru,
                                       svk_postprocess_fn *postprocess_fn);
using t_clean_up = svk_status (*)(void *);

svk_status load_slat_feature(std::string features_dir,
                             svk_feature_details *details) {
  svk_status status = SVK_STATUS_SUCCESS;
  int num_failed_libs = 0;
  char log_msg[LOG_MSG_MAX_SIZE];
  void *init_param = nullptr;

  DIR *dirfp = nullptr;
  struct dirent *entry = nullptr;

  // Open dir with feature libs
  snprintf(log_msg, LOG_MSG_MAX_SIZE, "Loading feature modules from %s",
           features_dir.c_str());
  std::cout << log_msg << std::endl;
  dirfp = opendir(features_dir.c_str());
  if (dirfp == nullptr) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Unable to open feature lib directory: %s\n",
             features_dir.c_str());
    std::cout << log_msg << std::endl;
    return SVK_STATUS_FAIL;
  }

  status = SVK_STATUS_BAD_FEATURE_LIB;

  entry = readdir(dirfp);
  // Loop through all libs in the dir
  for (; entry != nullptr; entry = readdir(dirfp)) {
    // Check if this is a shared lib
    std::string entry_name(entry->d_name);
    std::string feat_lib_suffix(LIBRARY_SUFFIX);
    // If dir entry is smaller than length(.so), skip the entry
    // Otherwise compare the last 3 chars to .so to see if it is valid
    if (entry_name.size() < feat_lib_suffix.size() ||
        entry_name.compare(entry_name.size() - feat_lib_suffix.size(),
                           feat_lib_suffix.size(), feat_lib_suffix) != 0) {
      continue;
    }

    std::string feature_lib_str = features_dir + "/" + entry->d_name;
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Attempting to load feature module functions for %s",
             entry->d_name);
    std::cout << log_msg << std::endl;
    void *handle = dlopen(feature_lib_str.c_str(), RTLD_LAZY);
    if (!handle) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE, "Dlopen failure. Error: %s\n",
               dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }

    // Try to load feature module function APIs from .so
    // If any fail, indicate this in the return value and move to next
    // feature
    details->initialize = (t_initialize)dlsym(handle, "initialize");
    if (details->initialize == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Cannot load symbol initialize for feature module "
               "'%s.' Error: %s\n",
               entry->d_name, dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    details->get_supported_feature_list = (t_get_supported_feature_list)dlsym(
        handle, "get_supported_feature_list");
    if (details->get_supported_feature_list == nullptr) {
      snprintf(
          log_msg, LOG_MSG_MAX_SIZE,
          "Cannot load symbol get_supported_feature_list for feature module "
          "'%s.' Error: %s\n",
          entry->d_name, dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    details->is_license_valid =
        (t_is_license_valid)dlsym(handle, "is_license_valid");
    if (details->is_license_valid == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Cannot load symbol is_license_valid for feature module "
               "'%s.' Error: %s\n",
               entry->d_name, dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    details->execute_sync = (t_execute_sync)dlsym(handle, "execute_sync");
    if (details->execute_sync == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Cannot load symbol execute_sync for feature module "
               "'%s.' Error: %s\n",
               entry->d_name, dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    details->execute_async = (t_execute_async)dlsym(handle, "execute_async");
    if (details->execute_async == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Cannot load symbol execute_async for feature module "
               "'%s.' Error: %s\n",
               entry->d_name, dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    details->clean_up = (t_clean_up)dlsym(handle, "clean_up");
    if (details->clean_up == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Cannot load symbol clean_up for feature module "
               "'%s.' Error: %s\n",
               entry->d_name, dlerror());
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    // This downstream API is optional, don't throw error if it's not there.
    // Just adding info log for now.
    details->configure_device_if_any =
        (t_configure_device_if_any)dlsym(handle, "configure_device_if_any");
    if (details->configure_device_if_any == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Optional downstream API configure_device_if_any was not found "
               "for feature module %s. Ignore this message if it is not "
               "required for this feature module.",
               entry->d_name);
      std::cout << log_msg << std::endl;
    }

    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Running initialize function for feature module %s",
             entry->d_name);
    std::cout << log_msg << std::endl;
    if (details->initialize(init_param)) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Initialization for feature module '%s' returned "
               "non-zero, ignoring this feature module.",
               entry->d_name);
      std::cout << log_msg << std::endl;
      num_failed_libs++;
      continue;
    }
    feature_id curr_feature;
    char feature_names;
    details->get_supported_feature_list(&curr_feature, &feature_names);
  }
  if (num_failed_libs) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE, "%d feature libs failed to load.",
             num_failed_libs);
    std::cout << log_msg << std::endl;
  } else {
    snprintf(log_msg, LOG_MSG_MAX_SIZE, "All features loaded successfully");
    std::cout << log_msg << std::endl;
    status = SVK_STATUS_SUCCESS;
  }
  return status;
}

int main(int argc, char **argv) {
  po::options_description argsDescription("Supported options");
  po::variables_map argsMap;
  struct stat fstat;
  svk_feature_details details;
  svk_status status = SVK_STATUS_FAIL;

  argsDescription.add_options()("help,h", "print help message")(
      "libdir,p", po::value<string>(),
      "Library directory to load the SLAT feature lib")(
      "slatconfig,c", po::value<string>(), "/path/to/slat_config.json")(
      "slatlogicconfig,l", po::value<string>(),
      "/path/to/slat_logic_config.json");

  po::store(po::parse_command_line(argc, argv, argsDescription), argsMap);
  po::notify(argsMap);

  std::cout << "Running sample application to load the sample logic library "
               "for UT purpose"
            << std::endl;

  if (argsMap.count("help")) {
    std::cout << argsDescription << std::endl;
    return 1;
  }

  if (stat(argsMap["libdir"].as<string>().c_str(), &fstat) != 0) {
    std::cout << "Invalid lib dir" << std::endl;
    return -1;
  }
  if (stat(argsMap["slatconfig"].as<string>().c_str(), &fstat) != 0) {
    std::cout << "Invalid slat config file" << std::endl;
    return -1;
  }
  if (stat(argsMap["slatlogicconfig"].as<string>().c_str(), &fstat) != 0) {
    std::cout << "Invalid slat logic config file" << std::endl;
    return -1;
  }
  setenv("SVK_SLAT_CONFIG", argsMap["slatconfig"].as<string>().c_str(), true);
  setenv("SVK_SLAT_LOGIC_CONFIG",
         argsMap["slatlogicconfig"].as<string>().c_str(), true);

  status = load_slat_feature(argsMap["libdir"].as<string>(), &details);
  std::cout << "Status from load_slat_feature - " << status << std::endl;
  if (status != SVK_STATUS_SUCCESS) {
    std::cout << "Running sample application exited with error" << std::endl;
    return status;
  }
  std::cout << "Running sample application exited gracefully" << std::endl;

  return 0;
}