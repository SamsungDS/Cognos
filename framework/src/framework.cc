#include "framework_upstream.h"
#include <algorithm>
#include <bits/stdc++.h>
#include <chrono>
#include <cmath>
#include <dirent.h>
#include <dlfcn.h>
#include <iostream>
#include <memory>
#include <string>
#include <sys/stat.h>
#include <unordered_map>

using namespace std;
class FrameworkSvc;

/**
 * @cond INTERNAL
 */

// Global variable to use for Framework service commands
std::unique_ptr<FrameworkSvc> g_fw_service;

class FrameworkSvc
{
public:
  explicit FrameworkSvc (const char *svk_config)
  {
    set_config (svk_config); // Helper function for setting config
    load_feature_modules (); // Load feature modules given in config
  }

  ~FrameworkSvc () { destroy_feat_map (); }

private:
  int
  load_feature_modules () const
  {
    int status = 0;
    return status;
  }

  int
  set_config (const char *svk_config_path) const
  {
    int status = 0;
    return status;
  }

  int
  destroy_feat_map () const
  {
    int status = 0;
    return status;
  }

public:
  int
  FrameworkSvcProcessCommand (svk_pass_thru_cmd *pass_thru, svk_input *input,
                              svk_output *output) const
  {
    int status = 0;
    return status;
  }

private:
  std::unordered_map<feature_id, svk_feature_details *>
      feature_map; // Map of feature data
  std::string feature_libs_path;
};

/**
 * @endcond
 */

extern "C" int
initialize_svk (const char *svk_conf_file, svk_storage_ctx *ctx,
                uint32_t num_ctx)
{
  int status = 0;
  g_fw_service = std::make_unique<FrameworkSvc> (svk_conf_file);
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
  return status;
}
