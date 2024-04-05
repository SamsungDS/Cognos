#include <algorithm>
#include <bits/stdc++.h>
#include <sys/stat.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <utility>

#include "framework_service.h"
#include "framework_upstream.h"

#define CORE_DEFAULT_CONF "/etc/svk/core_config.json"
#define CORE_DEFAULT_LIBS_PATH "/usr/lib"
#define CORE_DEFAULT_LOG_LEVEL "ERROR"
#define CORE_DEFAULT_LOG_FILE "/var/log/core/framework.log"
#define CORE_LOGGER_NAME "core"
#define LOG_MSG_MAX_SIZE 512
#define FEAT_LIB_SUFFIX ".so"

using namespace std;
class FrameworkSvc;

/**
 * @cond INTERNAL
 */
// Function pointer declaration for casting void* from dlsym
using initialize = int (*) (void *init_param);
using get_supported_feature_list
    = int (*) (feature_id *feature, char *feature_names);
using is_license_valid = int (*) (void *);
using execute_sync = int (*) (svk_pass_thru_cmd *pass_thru, svk_input *input,
                              svk_output *output);
using execute_async = int (*) (svk_pass_thru_cmd *pass_thru, svk_input *input,
                               svk_postprocess_fn *postprocess_fn);
using clean_up = int (*) (void *);

// Global variable to use for Framework service commands
const std::unique_ptr<FrameworkSvc> g_fw_service
    = std::make_unique<FrameworkSvc> ();

// Check if function pointer was set properly
bool
FrameworkSvc::report_sym_error (void *fn, const dirent *entry, void *handle,
                                const char *sym_name, int &num_failed_libs,
                                svk_status &status,
                                const featureInterface &feature_api,
                                svk_feature_details *details) const
{
  if (fn == nullptr)
    {

      const char *dlsym_error = dlerror ();
      char err_msg[LOG_MSG_MAX_SIZE];
      snprintf (err_msg, LOG_MSG_MAX_SIZE,
                "Cannot load symbol '%s' for feature module '%s.' Error: %s\n",
                sym_name, entry->d_name, dlsym_error);
      svk_logger (CORE_LOGGER_NAME, level_E::ERROR, err_msg);

      feature_api.close_lib (handle);
      num_failed_libs++;
      status = SVK_STATUS_BAD_FEATURE_LIB;
      return true;
    }
  else
    {
      return false;
    }
}
// Load feature modules from config directory, using the interface for file/lib
// related functions
svk_status
FrameworkSvc::load_feature_modules (const std::string &features_dir,
                                    void *init_param,
                                    const featureInterface &feature_api) const
{
  svk_status status = SVK_STATUS_SUCCESS;
  svk_status &get_status = status;
  int num_failed_libs = 0;
  int &get_failed_libs = num_failed_libs;
  char log_msg[LOG_MSG_MAX_SIZE];

  DIR *dirfp = nullptr;
  struct dirent *entry = nullptr;
  // Open dir with feature libs
  snprintf (log_msg, LOG_MSG_MAX_SIZE, "Loading feature modules from %s",
            features_dir.c_str ());
  svk_logger (CORE_LOGGER_NAME, level_E::INFO, log_msg);
  dirfp = feature_api.open_dir (features_dir.c_str ());
  if (dirfp == nullptr)
    {
      snprintf (log_msg, LOG_MSG_MAX_SIZE,
                "Unable to open feature lib directory: %s\n",
                features_dir.c_str ());
      svk_logger (CORE_LOGGER_NAME, level_E::ERROR, log_msg);
      return SVK_STATUS_FAIL;
    }

  entry = readdir (dirfp);
  // Loop through all libs in the dir
  for (; entry != nullptr; entry = readdir (dirfp))
    {
      if (strstr (entry->d_name, FEAT_LIB_SUFFIX) == nullptr)
        {
          continue;
        }
      std::string feature_lib_str = features_dir + "/" + entry->d_name;
      snprintf (log_msg, LOG_MSG_MAX_SIZE,
                "Attempting to load feature module functions for %s",
                entry->d_name);
      svk_logger (CORE_LOGGER_NAME, level_E::INFO, log_msg);
      void *handle = feature_api.open_lib (feature_lib_str.c_str ());
      if (!handle)
        {
          snprintf (log_msg, LOG_MSG_MAX_SIZE, "Dlopen failure. Error: %s\n",
                    dlerror ());
          svk_logger (CORE_LOGGER_NAME, level_E::ERROR, log_msg);
          status = SVK_STATUS_BAD_FEATURE_LIB;
          num_failed_libs++;
          continue;
        }

      auto details
          = (svk_feature_details *)malloc (sizeof (svk_feature_details));

      // Try to load feature module function APIs from .so
      // If any fail, indicate this in the return value and move to next
      // feature
      details->initialize
          = (initialize)feature_api.get_sym (handle, "initialize");
      if (report_sym_error ((void *)details->initialize, entry, handle,
                            "initialize", get_failed_libs, get_status,
                            feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->get_supported_feature_list
          = (get_supported_feature_list)feature_api.get_sym (
              handle, "get_supported_feature_list");
      if (report_sym_error ((void *)details->get_supported_feature_list, entry,
                            handle, "get_supported_feature_list",
                            get_failed_libs, get_status, feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->is_license_valid
          = (is_license_valid)feature_api.get_sym (handle, "is_license_valid");
      if (report_sym_error ((void *)details->is_license_valid, entry, handle,
                            "is_license_valid", get_failed_libs, get_status,
                            feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->execute_sync
          = (execute_sync)feature_api.get_sym (handle, "execute_sync");
      if (report_sym_error ((void *)details->execute_sync, entry, handle,
                            "execute_sync", get_failed_libs, get_status,
                            feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->execute_async
          = (execute_async)feature_api.get_sym (handle, "execute_async");
      if (report_sym_error ((void *)details->execute_async, entry, handle,
                            "execute_async", get_failed_libs, get_status,
                            feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->clean_up = (clean_up)feature_api.get_sym (handle, "clean_up");
      if (report_sym_error ((void *)details->clean_up, entry, handle,
                            "clean_up", get_failed_libs, get_status,
                            feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      snprintf (log_msg, LOG_MSG_MAX_SIZE,
                "Running initialize function for feature module %s",
                entry->d_name);
      svk_logger (CORE_LOGGER_NAME, level_E::INFO, log_msg);
      if (details->initialize (init_param))
        {
          snprintf (log_msg, LOG_MSG_MAX_SIZE,
                    "Initialization for feature module '%s' returned "
                    "non-zero, ignoring this feature module.",
                    entry->d_name);
          svk_logger (CORE_LOGGER_NAME, level_E::ERROR, log_msg);
          status = SVK_STATUS_BAD_FEATURE_LIB;
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      feature_id curr_feature;
      char feature_names;
      details->get_supported_feature_list (&curr_feature, &feature_names);
      // insert fid/function pointers into map
      auto [iterator, inserted]
          = feature_map.insert (make_pair (curr_feature, details));
      if (!inserted)
        {
          snprintf (log_msg, LOG_MSG_MAX_SIZE,
                    "svk_feature_details for feature lib %s wasn't able to be "
                    "added to map.",
                    entry->d_name);
          svk_logger (CORE_LOGGER_NAME, level_E::ERROR, log_msg);
          num_failed_libs++;
          status = SVK_STATUS_BAD_FEATURE_LIB;
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
        }
    }
  if (num_failed_libs)
    {
      snprintf (log_msg, LOG_MSG_MAX_SIZE, "%d feature libs failed to load.",
                num_failed_libs);
      svk_logger (CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    }
  else
    {
      svk_logger (CORE_LOGGER_NAME, level_E::INFO,
                  "All feature libs loaded successfully.");
    }

  return status;
}
// Attempt to load logger options from the config, use defaults for any options
// that can't be found
svk_status
FrameworkSvc::init_logger (
    boost::property_tree::ptree const &logger_info) const
{
  std::string log_level
      = logger_info.get<std::string> ("log_level", CORE_DEFAULT_LOG_LEVEL);
  std::string file_name
      = logger_info.get<std::string> ("log_file_name", CORE_DEFAULT_LOG_FILE);
  int file_count = logger_info.get<int> ("log_file_count", 2);
  uint64_t file_size = logger_info.get<uint64_t> (
      "log_file_size", 1048576); // 1MB default max file size
  std::string sink_type
      = logger_info.get<std::string> ("sink_type", "rotating_file");

  if (svk_logger_init (CORE_LOGGER_NAME, file_name.c_str (),
                       log_level_map.at (log_level), file_count, file_size,
                       sink_type.c_str ())
      == 0)
    {
      svk_logger (CORE_LOGGER_NAME, level_E::INFO,
                  "Core logger is initialized");
      return SVK_STATUS_SUCCESS;
    }
  else
    {
      return SVK_STATUS_INVALID_CONFIG;
    }
}

// return svk status
svk_status
FrameworkSvc::set_config (void *init_param,
                          const featureInterface &dep_inj) const
{
  svk_status status = SVK_STATUS_SUCCESS;
  boost::property_tree::ptree pt;
  try
    {
      boost::property_tree::read_json (svk_conf_path, pt);
    }
  catch (boost::property_tree::json_parser_error &e)
    {
      cerr << "Unable to read SVK config. Error -> " << e.what () << endl;
      return SVK_STATUS_INVALID_CONFIG;
    }
  // Set logger here as well, once logger code is merged. Need to translate log
  // level properly as well
  boost::property_tree::ptree logger_info;
  try
    {
      logger_info = pt.get_child ("core.logger");
    }
  catch (boost::property_tree::ptree_error &e)
    {
      std::cerr << "Error while parsing logger config section: " << e.what ()
                << ". Logger defaults will be used." << std::endl;
    }
  // Initialize logger
  if (init_logger (logger_info) != SVK_STATUS_SUCCESS)
    { // test
      std::cerr << "Logger unable to be initialized" << std::endl;
      return SVK_STATUS_FAIL;
    }

  std::string features_dir
      = pt.get<std::string> ("core.feat_modules_dir", CORE_DEFAULT_LIBS_PATH);

  status = load_feature_modules (features_dir, init_param, dep_inj);

  return status;
}

svk_status
FrameworkSvc::destroy_feat_map (void *param) const
{
  char log_msg[LOG_MSG_MAX_SIZE];
  for (const auto &[key, value] : feature_map)
    {
      snprintf (log_msg, LOG_MSG_MAX_SIZE,
                "Clearing up svk_feature_details for feature_id %d.",
                (uint32_t)key);
      svk_logger (CORE_LOGGER_NAME, level_E::DEBUG, log_msg);
      value->clean_up (param);
      free (value);
    }
  feature_map.clear ();
  if (feature_map.empty ())
    {
      svk_logger (CORE_LOGGER_NAME, level_E::INFO,
                  "Feature map cleared successfully.");
      return SVK_STATUS_SUCCESS;
    }
  else
    {
      svk_logger (CORE_LOGGER_NAME, level_E::ERROR,
                  "Feature map unable to be cleared.");
      return SVK_STATUS_FAIL;
    }
}

// Injecting dlInterface dependency for testing, only to be used while loading
// feature libs
svk_status
FrameworkSvc::FrameworkSvcInit (const char *svk_config, void *init_param,
                                const featureInterface &dep_inj)
{
  svk_conf_path = svk_config;
  return set_config (init_param, dep_inj);
}

svk_status
FrameworkSvc::FrameworkSvcProcessCommand (svk_pass_thru_cmd *pass_thru,
                                          svk_input *input,
                                          svk_output *output) const
{
  svk_status exec_res = SVK_STATUS_SUCCESS;
  char log_msg[LOG_MSG_MAX_SIZE];
  feature_id curr_feat = pass_thru->feat_id;
  exec_res = (svk_status)feature_map.at (curr_feat)->execute_sync (
      pass_thru, input, output);
  if (exec_res != SVK_STATUS_SUCCESS)
    {
      snprintf (log_msg, LOG_MSG_MAX_SIZE,
                "Synchronous execute failed for feature_id %d.",
                (uint32_t)curr_feat);
      svk_logger (CORE_LOGGER_NAME, level_E::ERROR, log_msg);
    }
  return exec_res;
}

svk_status
FrameworkSvc::FrameworkSvcCleanup (void *param) const
{
  svk_status status = SVK_STATUS_SUCCESS;
  status = destroy_feat_map (param);

  return status;
}

/**
 * @endcond
 */

extern "C" int
initialize_svk (const char *svk_conf_file, void *init_param)
{
  // Ignoring storage context stuff for now
  int status = 0;
  featureInterface dl;
  std::string conf_path;
  const char *env_p;
  if (svk_conf_file == nullptr)
    {
      if ((env_p = std::getenv ("SVK_FW_CONFIG")))
        {
          conf_path = env_p;
        }
      else
        {
          conf_path = CORE_DEFAULT_CONF;
        }
    }
  else
    {
      conf_path = svk_conf_file;
    }

  if (g_fw_service == nullptr)
    {
      std::cerr << "FrameworkSvc object was unable to be allocated"
                << std::endl;
      status = -1;
    }
  else
    {
      status = g_fw_service->FrameworkSvcInit (conf_path.c_str (), init_param,
                                               dl);
    }

  return status;
}

extern "C" int
execute_svk_feature_sync (svk_pass_thru_cmd *pass_thru, svk_input *input,
                          svk_output *output)
{
  int status = 0;
  status = g_fw_service->FrameworkSvcProcessCommand (pass_thru, input, output);
  return status;
}

extern "C" int
execute_svk_feature_async (svk_pass_thru_cmd *pass_thru, svk_input *input,
                           svk_postprocess_fn *postprocess_fn)
{
  int status = 0;
  return status;
}

extern "C" int
cleanup_svk (svk_storage_ctx *ctx, void *param)
{
  int status = 0;
  status = g_fw_service->FrameworkSvcCleanup (param);
  svk_logger (CORE_LOGGER_NAME, level_E::INFO, "SVK Cleanup finished.");
  return status;
}
