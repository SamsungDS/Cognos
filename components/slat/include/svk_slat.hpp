#ifndef __SVK_SLAT_HPP__
#define __SVK_SLAT_HPP__

#include <dirent.h>
#include <dlfcn.h>
#include <sys/inotify.h>

#include <mutex>
#include <nlohmann/json.hpp>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "logger_util.hpp"
#include "svk_publisher.h"

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

#define ALERTS_TOPIC_FILTER "alerts"

#define SLAT_CONF_SECTION_TAG SLAT_FEATURE_MODULE_NAME
#define SLAT_LOGGER_MODULE_NAME SLAT_FEATURE_MODULE_NAME

#define SLAT_MAX_STR_LEN (256)
#define SLAT_MAX_LOGIC_MODULE_NAME_LEN SLAT_MAX_STR_LEN
#define SLAT_MAX_FEATURE_NAME_LEN SLAT_MAX_STR_LEN

using svk_slat_metrics_output = struct svk_slat_metrics_output_s {
  std::string host_name;
  std::string device_name;  // This may contain just numa of device
  uint64_t avgLatencyns;    // Latency in nanoseconds
  uint64_t iops;
  uint64_t bandwidthGBps;
  uint64_t avgReadLatency;
  uint64_t avgWriteLatency;
  uint64_t avgUpdateLatency;
  uint64_t avgReadIOPS;
  uint64_t avgWriteIOPS;
  uint64_t avgP99Latency;
  uint64_t ioBytesRead;
  uint64_t ioBytesWritten;
  uint64_t ioBytesRewrite;
};

using json = nlohmann::json;
using slat_app_sla_config = struct slat_app_sla_config_s {
  std::string app_name;
  std::string app_pid;
  uint64_t app_requested_sla_ns;
  uint64_t app_sla_tolerance_percent;
  svk_slat_metrics_output app_current_sla;
};

using slat_benchmark_config = struct slat_benchmark_config_s {
  std::string device_numa_node;
  uint64_t device_advertised_sla;
  uint64_t device_current_sla;
  uint64_t device_sla_tolerance_percent;
  std::string benchmark_tool;
  std::string benchmark_out_field;
  bool sla_deviation_reported_flag;
  std::map<std::string, slat_app_sla_config> app_sla_list;
};

using slat_device_sla_config = struct slat_device_sla_config_s {
  std::string device_name;
  std::string device_numa_node;
  uint64_t device_advertised_sla;
  uint64_t device_current_sla;
};

using slat_app_benchmark_sla_to_add = struct slat_app_benchmark_sla_to_add_s {
  slat_app_sla_config app_sla;
  std::vector<slat_device_sla_config> device_sla_list;
  std::string sla_benchmark_tool;
};

using slat_config = struct slat_config {
  std::string slat_logic_lib_dir;
  slat_logger_config logger_config;
  bool enable_bg_thread;
  int64_t benchmark_run_interval;
};

using slat_thread_data = struct slat_thread_data_s {
  std::thread benchmarking_thread;
  bool shutdown_bm_thread;
  bool thread_running;

  std::map<std::string, slat_benchmark_config> benchmark_device_config_list;
  int64_t benchmark_run_interval;

  std::vector<slat_app_benchmark_sla_to_add> benchmark_pending_list_to_add;
  std::vector<std::string> devices_to_remove_from_monitoring;
  std::mutex benchmark_pending_list_lock;
};

// Making this global to be able to mock functions for testing
class SLATrackerSvc {
 private:
  mutable std::unordered_map<std::string, svk_logic_module_details *>
      logic_modules_map;
  std::string curr_log_level;
  std::string svk_conf_path;

  slat_thread_data th_data;

  svk_status read_slat_config_file(const std::string slat_conf_file,
                                   slat_config *config) const;
  svk_status initialize_logger(const slat_config config) const;
  svk_status load_logic_modules(const std::string &logic_modules_lib_dir) const;
  virtual void update_app_sla_with_device_sla(slat_benchmark_config &config);
  void process_pending_requests(void);
  // Adding new fn to add the device
  svk_status remove_devices_from_sla_tracker(json command_params);

 protected:
  void benchmarking_thread_fn(void);
  virtual std::string run_benchmark(slat_benchmark_config &config);
  virtual void publish_app_event(slat_benchmark_config &config);
  virtual void parse_result(slat_benchmark_config &config, std::string result);
  virtual svk_status add_devices_to_sla_tracker(json command_params);

 public:
  // In order to comply with Rule-of-Zero, manage class init and deletion
  // through APIs and not through constructors/destructors. Must call init and
  // cleanup from this class to ensure resources are managed properly
  svk_status Initialize(const char *svk_config);
  svk_logic_module_details *getLogicDetails(char *logic_module_name);
  void clean_up(void);
  // Dummy function to trigger all logic module async
  //  To get code coverrage
  // TODO: Remove this
  void dummy_submit_async_all(void);
  svk_status parse_and_add_new_sla_monitor(std::string sla_details);
  svk_status process_json_cmd(svk_input *input, svk_output *output);
};

extern "C" {
// Creating the dlsym function wrapper for mocking in the UTs
void *my_dlopen(const char *filename, int flags);
void *my_dlsym(void *handle, const char *symbol);
int my_dlclose(void *handle);
}

#endif /* __SVK_SLAT_HPP__ */
