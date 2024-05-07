#ifndef FRAMEWORK_SERVICE_H
#define FRAMEWORK_SERVICE_H

#include <dirent.h>
#include <dlfcn.h>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <memory>
#include <string>
#include <unordered_map>

#include "framework_struct.h"
#include "svk_logger.h"

// featureInterface for free functions so that we can mock class functions as
// needed
class featureInterface {
 public:
  virtual ~featureInterface() = default;
  virtual void *get_sym(void *handle, const char *fn_name) const {
    return dlsym(handle, fn_name);
  }
  virtual void *open_lib(const char *ft_lib_str) const {
    return dlopen(ft_lib_str, RTLD_LAZY);
  }
  virtual int close_lib(void *handle) const { return dlclose(handle); }
  virtual DIR *open_dir(const char *dir_str) const { return opendir(dir_str); }
};

// Making this global to be able to mock functions for testing
class FrameworkSvc {
 private:
  const std::unordered_map<std::string, level_E> log_level_map = {
      {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
      {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
      {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
      {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
      {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};
  mutable std::unordered_map<feature_id, svk_feature_details *> feature_map;
  std::string svk_conf_path;
  bool report_sym_error(void *fn, const dirent *entry, void *handle,
                        const char *sym_name, int &num_failed_libs,
                        svk_status &status,
                        const featureInterface &feature_api) const;
  svk_status load_feature_modules(const std::string &features_dir,
                                  void *init_param,
                                  const featureInterface &free_api) const;
  svk_status init_logger(boost::property_tree::ptree const &logger_info) const;
  svk_status set_config(void *init_param,
                        const featureInterface &dep_inj) const;
  svk_status get_feature_details(feature_id feat_id,
                                 svk_feature_details const **details) const;
  svk_status destroy_feat_map(void *param) const;

 public:
  // In order to comply with Rule-of-Zero, manage class init and deletion
  // through APIs and not through constructors/destructors. Must call init and
  // cleanup from this class to ensure resources are managed properly
  svk_status FrameworkSvcInit(const char *svk_config, void *init_param,
                              const featureInterface &dep_inj);
  svk_status FrameworkSvcConfigureDev(svk_pass_thru_cmd const *pass_thru,
                                      svk_device_ctx *device_handles,
                                      uint64_t length) const;
  svk_status FrameworkSvcProcessCommand(
      svk_pass_thru_cmd *pass_thru, svk_input *input, svk_output *output,
      svk_postprocess_fn *postprocess_fn) const;
  svk_status FrameworkSvcCleanup(void *param) const;
};

#endif  // FRAMEWORK_SERVICE_H
