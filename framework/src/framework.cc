#include <algorithm>
#include <bits/stdc++.h>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <dirent.h>
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
FrameworkSvc::report_sym_error (void *fn, const char *entry_name, void *handle,
                                int &num_failed_libs, svk_status &status,
                                const featureInterface &feature_api,
                                svk_feature_details *details) const
{
  if (fn == nullptr)
    {

      const char *dlsym_error = dlerror ();
      std::cerr << "Cannot load symbol 'initialize' for feature module "
                << entry_name
                << ", ignoring this feature module. Error: " << dlsym_error
                << std::endl;
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

  DIR *dirfp = nullptr;
  struct dirent *entry = nullptr;
  // Open dir with feature libs
  dirfp = feature_api.open_dir (features_dir.c_str ());
  if (dirfp == nullptr)
    {
      std::cerr << "unable to open feature lib directory" << std::endl;
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
      void *handle = feature_api.open_lib (feature_lib_str.c_str ());
      if (!handle)
        {
          std::cerr << "Dlopen failure: " << dlerror () << std::endl;
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
      if (report_sym_error ((void *)details->initialize, entry->d_name, handle,
                            get_failed_libs, get_status, feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->get_supported_feature_list
          = (get_supported_feature_list)feature_api.get_sym (
              handle, "get_supported_feature_list");
      if (report_sym_error ((void *)details->get_supported_feature_list,
                            entry->d_name, handle, get_failed_libs, get_status,
                            feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->is_license_valid
          = (is_license_valid)feature_api.get_sym (handle, "is_license_valid");
      if (report_sym_error ((void *)details->is_license_valid, entry->d_name,
                            handle, get_failed_libs, get_status, feature_api,
                            details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->execute_sync
          = (execute_sync)feature_api.get_sym (handle, "execute_sync");
      if (report_sym_error ((void *)details->execute_sync, entry->d_name,
                            handle, get_failed_libs, get_status, feature_api,
                            details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->execute_async
          = (execute_async)feature_api.get_sym (handle, "execute_async");
      if (report_sym_error ((void *)details->execute_async, entry->d_name,
                            handle, get_failed_libs, get_status, feature_api,
                            details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }
      details->clean_up = (clean_up)feature_api.get_sym (handle, "clean_up");
      if (report_sym_error ((void *)details->clean_up, entry->d_name, handle,
                            get_failed_libs, get_status, feature_api, details))
        {
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
          continue;
        }

      if (details->initialize (init_param))
        {
          std::cerr << "Initialization for feature module " << entry->d_name
                    << "returned non-zero, ignoring this feature module."
                    << std::endl;
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
          std::cerr << "svk_feature_details for feature lib " << entry->d_name
                    << "wasn't able to be added to map" << std::endl;

          num_failed_libs++;
          status = SVK_STATUS_BAD_FEATURE_LIB;
          free (details);
          // Set to null to ensure free only happens once
          details = nullptr;
        }
    }
  std::cerr << num_failed_libs << " feature libs failed to load" << std::endl;
  // return amount of feature modules that failed to load
  return status;
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
  std::string log_level
      = pt.get<std::string> ("core.log_level", CORE_DEFAULT_LOG_LEVEL);

  std::string features_dir
      = pt.get<std::string> ("core.feat_modules_dir", CORE_DEFAULT_LIBS_PATH);

  status = load_feature_modules (features_dir, init_param, dep_inj);

  return status;
}

svk_status
FrameworkSvc::destroy_feat_map () const
{
  for (const auto &[key, value] : feature_map)
    {
      free (value);
    }
  feature_map.clear ();
  if (feature_map.empty ())
    {
      return SVK_STATUS_SUCCESS;
    }
  else
    {
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
  svk_status status = SVK_STATUS_SUCCESS;
  return status;
}

svk_status
FrameworkSvc::FrameworkSvcCleanup () const
{
  svk_status status = SVK_STATUS_SUCCESS;
  status = destroy_feat_map ();
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
cleanup_svk (svk_storage_ctx *ctx, void *)
{
  int status = 0;
  status = g_fw_service->FrameworkSvcCleanup ();
  std::cout << "SVK Cleanup finished." << std::endl;
  return status;
}
