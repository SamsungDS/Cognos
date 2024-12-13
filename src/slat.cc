#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <boost/algorithm/string.hpp>
#include <boost/tokenizer.hpp>
#include <iostream>
#include <map>
#include <memory>
#include <ranges>

#include "logic_interface/svk_logic_struct.h"
#include "svk_slat.hpp"

#define LOG_MSG_MAX_SIZE (1024)
#define LIBRARY_SUFFIX ".so"

#define APP_MAX_LEN (64)
#define HOSTNAME_MAX_LEN (64)
#define APP_DEFAULT_TOLERANCE_PERCENT (10)

// Global variable to use for Framework service commands
const std::unique_ptr<SLATrackerSvc> g_slat_service =
    std::make_unique<SLATrackerSvc>();

#define LOGIC_OUT_BUFFER_LEN (256)
/* Private SLATrackerSvc helper methods */
std::string SLATrackerSvc::run_benchmark(slat_benchmark_config &config) {
  svk_status status;

  svk_logic_module_details *details;
  svk_logic_cmd logic_cmd;
  svk_logic_input logic_input = {};
  svk_logic_output logic_output;
  char out[LOGIC_OUT_BUFFER_LEN] = {};

  logic_output.output_buffer = (uint8_t *)out;
  logic_output.output_len = LOGIC_OUT_BUFFER_LEN;

  // TODO: Use NUMA node
  if (config.benchmark_tool == "mlc") {
    strncpy(logic_cmd.logic_name, "MlcLogic", 256);

    details = g_slat_service->getLogicDetails(logic_cmd.logic_name);
    if (details == nullptr) {
      std::cout << "Logic module not found" << std::endl;
      return "status=failed";
    }
  } else {
    std::cout << "Unsupported benchmark [" << config.benchmark_tool << "]"
              << std::endl;
    return "status=failed";
  }

  if (details->execute_logic_sync == nullptr) {
    std::cout << "logic module's execute_logic_sync is null. Exiting."
              << std::endl;
    return "status=failed";
  }

  status = details->execute_logic_sync(&logic_cmd, &logic_input, &logic_output);
  if (status == SVK_STATUS_SUCCESS) {
    std::string out_str((const char *)out);
    return out_str;
  } else {
    std::cout << "failed" << std::endl;
    return "status=failed";
  }
}

void SLATrackerSvc::parse_result(slat_benchmark_config &config,
                                 std::string result) {
  char *ptr = nullptr;
  char parsed_result[LOGIC_OUT_BUFFER_LEN];
  if (config.benchmark_tool == "mlc") {
    ptr = strstr((char *)result.c_str(), "avgLatencyns");
    if (ptr == nullptr) {
      std::cout << "Error parsing result" << std::endl;
      return;
    }
    sscanf(ptr, "avgLatencyns=%[.0-9]", parsed_result);
    uint64_t avgReadLatency = atof(parsed_result);
    config.device_current_sla = avgReadLatency;
  }
}

void SLATrackerSvc::update_app_sla_with_device_sla(
    slat_benchmark_config &config) {
  for (auto &[app_name, app_sla_config] : config.app_sla_list) {
    app_sla_config.app_current_sla.avgLatencyns = config.device_current_sla;
  }
}

void SLATrackerSvc::publish_app_degraded_sla(slat_benchmark_config &config) {
  int rc;

  for (const auto &[app_name, app_sla_config] : config.app_sla_list) {
    rc = publish(&this->th_data.zmq_socket, "APP_SLA_DEGRADED:",
                 (svk_slat_logic_output *)&app_sla_config.app_current_sla);
    if (rc == -1) {
      std::cout << " failed to publish sla results" << std::endl;
    }
  }
}

void SLATrackerSvc::add_pending_app_sla_monitoring(void) {
  this->th_data.benchmark_pending_list_lock.lock();
  for (slat_app_benchmark_sla_to_add &to_add :
       this->th_data.benchmark_pending_list_to_add) {
    const std::string app_name = to_add.app_sla.app_current_sla.app_name;
    for (const auto &device : to_add.device_sla_list) {
      std::string device_numa = device.device_numa_node;
      auto it = this->th_data.benchmark_device_config_list.find(device_numa);
      if (it == this->th_data.benchmark_device_config_list.end()) {
        slat_benchmark_config cfg = {};
        cfg.benchmark_tool = "mlc";
        cfg.benchmark_out_field = "avgLatencyns";
        cfg.device_current_sla = 0;
        cfg.device_advertised_sla = device.device_advertised_sla;
        cfg.device_numa_node = device_numa;
        cfg.device_sla_tolerance_percent = APP_DEFAULT_TOLERANCE_PERCENT;
        cfg.app_sla_list[app_name] = to_add.app_sla;

        std::cout << "Adding device " << device_numa << " and app " << app_name
                  << std::endl;
        this->th_data.benchmark_device_config_list[device_numa] = cfg;
        continue;
      }
      std::cout << "Device already exist for " << device_numa
                << "]. Updating for app " << app_name << std::endl;
      slat_benchmark_config &cfg = it->second;
      cfg.device_advertised_sla = device.device_advertised_sla;
      cfg.app_sla_list[app_name] = to_add.app_sla;
    }
  }
  this->th_data.benchmark_pending_list_to_add.clear();
  this->th_data.benchmark_pending_list_lock.unlock();
}

void SLATrackerSvc::benchmarking_thread_fn(void) {
  std::string benchmark_result_str;

  std::cout << "Started benchmarking thread" << std::endl;
  while (1) {
    this->add_pending_app_sla_monitoring();

    for (auto &[device_numa, device_benchmark_config] :
         this->th_data.benchmark_device_config_list) {
      benchmark_result_str = this->run_benchmark(device_benchmark_config);
      this->parse_result(device_benchmark_config, benchmark_result_str);
      this->update_app_sla_with_device_sla(device_benchmark_config);

      if (device_benchmark_config.device_current_sla >
          (device_benchmark_config.device_advertised_sla +
           ((device_benchmark_config.device_advertised_sla *
             device_benchmark_config.device_sla_tolerance_percent / 100)))) {
        std::cout << "Detected App degraded SLA "
                  << device_benchmark_config.device_current_sla << " > "
                  << device_benchmark_config.device_sla_tolerance_percent
                  << "% of " << device_benchmark_config.device_advertised_sla
                  << std::endl;
        this->publish_app_degraded_sla(device_benchmark_config);
      }
    }

    std::cout << "Benchmark thread sleeping for "
              << this->th_data.benchmark_run_interval << " seconds"
              << std::endl;
    std::this_thread::sleep_for(
        std::chrono::seconds(this->th_data.benchmark_run_interval));
    if (this->th_data.shutdown_bm_thread) {
      break;
    }
  }
  return;
}

svk_status update_sla_details(
    const std::map<std::string, std::string> &param_map, const char *key,
    char *dest, unsigned int max_len) {
  auto it = param_map.find(key);
  if (it == param_map.end()) {
    std::cout << key << " not found" << std::endl;
    return SVK_STATUS_FAIL;
  } else {
    std::string value = it->second;
    if (value.length() >= max_len) {
      std::cout << key << " length greater than " << max_len << " not supported"
                << std::endl;
      return SVK_STATUS_FAIL;
    }
    strncpy(dest, value.c_str(), max_len);
  }
  return SVK_STATUS_SUCCESS;
}

svk_status SLATrackerSvc::parse_and_add_new_sla_monitor(
    std::string sla_details) {
  svk_status rc;
  slat_app_benchmark_sla_to_add app_sla_to_add = {};

  std::map<std::string, std::string> sla_kv_pairs;

  boost::char_separator<char> sep(";");
  boost::tokenizer<boost::char_separator<char>> tokens(sla_details, sep);

  // app_name=TestApp;app_sla_latency_ns=10;devices=0;device_sla_latency_ns=10;host_name=localhost;logic_module=default
  for (const auto &token : tokens) {
    std::vector<std::string> params;
    boost::split(params, token, boost::is_any_of("="));
    if (params.size() != 2) {
      std::cout << "Invalid param found [" << token << "]" << std::endl;
      return SVK_STATUS_FAIL;
    }
    sla_kv_pairs[params[0]] = params[1];
  }

  rc = update_sla_details(sla_kv_pairs, "app_name",
                          app_sla_to_add.app_sla.app_current_sla.app_name,
                          APP_MAX_LEN);
  if (rc != SVK_STATUS_SUCCESS) {
    return rc;
  }
  rc = update_sla_details(sla_kv_pairs, "host_name",
                          app_sla_to_add.app_sla.app_current_sla.host_name,
                          HOSTNAME_MAX_LEN);
  if (rc != SVK_STATUS_SUCCESS) {
    return rc;
  }

  app_sla_to_add.app_sla.app_current_sla.avgLatencyns = 0;
  app_sla_to_add.app_sla.app_sla_tolerance_percent =
      APP_DEFAULT_TOLERANCE_PERCENT;

  if (sla_kv_pairs.find("app_sla_latency_ns") == sla_kv_pairs.end()) {
    std::cout << "app_sla_latency_ns "
              << " not found" << std::endl;
    return SVK_STATUS_FAIL;
  } else {
    app_sla_to_add.app_sla.app_requested_sla_ns =
        atoi(sla_kv_pairs["app_sla_latency_ns"].c_str());
  }

  boost::char_separator<char> multi_item_sep(",");
  boost::tokenizer<boost::char_separator<char>> device_numas(
      sla_kv_pairs["devices"], multi_item_sep);
  boost::tokenizer<boost::char_separator<char>> device_latencies(
      sla_kv_pairs["device_sla_latency_ns"], multi_item_sep);

  int i = 0;
  std::vector<uint64_t> dev_sla_list;
  for (auto dl : device_latencies) {
    dev_sla_list.push_back(atoi(dl.c_str()));
  }

  for (auto d : device_numas) {
    slat_device_sla_config dc;
    dc.device_current_sla = 0;
    dc.device_advertised_sla = dev_sla_list[i++];
    dc.device_numa_node = d;

    app_sla_to_add.device_sla_list.push_back(dc);
  }

  this->th_data.benchmark_pending_list_lock.lock();
  this->th_data.benchmark_pending_list_to_add.push_back(app_sla_to_add);
  this->th_data.benchmark_pending_list_lock.unlock();

  std::cout << "Queued app sla for monitoring "
            << app_sla_to_add.app_sla.app_current_sla.app_name << std::endl;
  return SVK_STATUS_SUCCESS;
}

svk_status SLATrackerSvc::read_slat_config_file(
    const std::string slat_conf_file, slat_config *config) const {
  svk_status status = SVK_STATUS_SUCCESS;
  namespace pt = boost::property_tree;

  try {
    pt::ptree root;
    pt::read_json(slat_conf_file, root);
    pt::ptree slat_config_pt = root.get_child(SLAT_CONF_SECTION_TAG);

    config->slat_logic_lib_dir =
        slat_config_pt.get<std::string>("logic_lib_dir");

    try {
      std::string disable_bg_thread =
          slat_config_pt.get<std::string>("disable_bg_thread");
      if (disable_bg_thread == "true") {
        config->enable_bg_thread = false;
      } else {
        config->enable_bg_thread = true;
      }
    } catch (std::exception &e) {
      config->enable_bg_thread = true;
    }
    try {
      std::string benchmark_run_interval =
          slat_config_pt.get<std::string>("benchmark_run_interval");
      config->benchmark_run_interval = atoi(benchmark_run_interval.c_str());
    } catch (std::exception &e) {
      config->benchmark_run_interval = 10;  // 10 Seconds
    }
    try {
      pt::ptree logger_info_pt = slat_config_pt.get_child("logger");
      status = read_slat_logger_config(logger_info_pt, config->logger_config);
    } catch (std::exception &e) {
      std::cout << "Unable to read Logger section of SLAT in the config file. "
                   "Falling back to default values. Error -> "
                << e.what() << std::endl;
      // Assign defaults
      config->logger_config.log_level = SLAT_LOGGER_LEVEL_DEFAULT;
      config->logger_config.log_filename = SLAT_LOG_FILENAME_DEFAULT;
      config->logger_config.log_file_count = SLAT_LOGGER_FILE_COUNT_DEFAULT;
      config->logger_config.log_file_size = SLAT_LOGGER_FILE_SIZE_DEFAULT;
      config->logger_config.log_sink_type = SLAT_LOGGER_SINK_TYPE_DEFAULT;
    }
  } catch (std::exception &e) {
    std::cerr << "Unable to read SLAT config file. Assigning default value. "
                 "Error -> "
              << e.what() << std::endl;
    config->slat_logic_lib_dir = SLAT_FEATURE_LOGIC_MODULES_PATH;

    // Assign defaults
    config->logger_config.log_level = SLAT_LOGGER_LEVEL_DEFAULT;
    config->logger_config.log_filename = SLAT_LOG_FILENAME_DEFAULT;
    config->logger_config.log_file_count = SLAT_LOGGER_FILE_COUNT_DEFAULT;
    config->logger_config.log_file_size = SLAT_LOGGER_FILE_SIZE_DEFAULT;
    config->logger_config.log_sink_type = SLAT_LOGGER_SINK_TYPE_DEFAULT;
  }

  return status;
}

svk_status SLATrackerSvc::initialize_logger(const slat_config config) const {
  slat_logger_config c;

  c.log_file_count = config.logger_config.log_file_count;
  c.log_file_size = config.logger_config.log_file_size;
  c.log_filename = config.logger_config.log_filename;
  c.log_level = config.logger_config.log_level;
  c.log_sink_type = config.logger_config.log_sink_type;
  c.log_module_name = SLAT_FEATURE_MODULE_NAME;

  return slat_initialize_logger(c);
}

void *dlopen_fn(const char *filename, int flags) {
  return dlopen(filename, flags);
}

void *dlsym_fn(void *handle, const char *symbol) {
  return dlsym(handle, symbol);
}

int dlclose_fn(void *handle) { return dlclose(handle); }

// Load logic modules from config directory, using the interface for file/lib
// related functions
svk_status SLATrackerSvc::load_logic_modules(
    const std::string &logic_modules_lib_dir) const {
  svk_status status = SVK_STATUS_SUCCESS;
  int num_failed_libs = 0;
  char log_msg[LOG_MSG_MAX_SIZE];
  struct stat st;

  DIR *dirfp = nullptr;
  struct dirent *entry = nullptr;
  // Open dir with feature libs
  snprintf(log_msg, LOG_MSG_MAX_SIZE, "Loading logic modules from %s",
           logic_modules_lib_dir.c_str());
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO, log_msg);
  dirfp = opendir(logic_modules_lib_dir.c_str());
  if (dirfp == nullptr) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Unable to open logic modules lib directory: %s\n",
             logic_modules_lib_dir.c_str());
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
    return SVK_STATUS_FAIL;
  }

  entry = readdir(dirfp);
  // Loop through all libs in the dir
  for (; entry != nullptr; entry = readdir(dirfp)) {
    // Skip the file names starting with "."
    if (strncmp(entry->d_name, ".", 1) == 0 ||
        strlen(entry->d_name) <= strlen(LIBRARY_SUFFIX)) {
      continue;
    }
    // Check if this is a shared lib
    std::string entry_name(logic_modules_lib_dir + "/" + entry->d_name);
    std::string library_suffix(LIBRARY_SUFFIX);

    stat(entry_name.c_str(), &st);
    if (S_ISDIR(st.st_mode)) {
      std::string file(entry_name + "/lib64/lib" + entry->d_name + ".so");
      entry_name = file;
    }

    // If dir entry is smaller than length(.so), skip the entry
    // Otherwise compare the last 3 chars to .so to see if it is valid
    if (entry_name.compare(entry_name.size() - library_suffix.size(),
                           library_suffix.size(), library_suffix) != 0) {
      continue;
    }

    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Attempting to load feature module functions for %s",
             entry_name.c_str());
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO, log_msg);
    void *handle = dlopen_fn(entry_name.c_str(), RTLD_LAZY);
    if (!handle) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE, "dlopen failure for %s. Error: %s\n",
               entry_name.c_str(), dlerror());
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      continue;
    }

    auto details =
        (svk_logic_module_details *)malloc(sizeof(svk_logic_module_details));
    if (details == nullptr) {
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
                 "Failed to allocate memory for svk_logic_module_details");
      continue;
    }

    // Try to load feature module function APIs from .so
    // If any fail, indicate this in the return value and move to next
    // feature
    details->initialize_logic_module = (initialize_logic_module_dlsym)dlsym_fn(
        handle, "initialize_logic_module");

    if (details->initialize_logic_module == nullptr) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "Cannot load symbol initialize_logic_module for logic module "
               "'%s.' Error: %s\n",
               entry->d_name, dlerror());
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      free(details);
      dlclose_fn(handle);
      continue;
    }

    details->get_supported_logic_details =
        (get_supported_logic_details_dlsym)dlsym_fn(
            handle, "get_supported_logic_details");

    if (details->get_supported_logic_details == nullptr) {
      snprintf(
          log_msg, LOG_MSG_MAX_SIZE,
          "Cannot load symbol get_supported_logic_details for logic module "
          "'%s.' Error: %s\n",
          entry->d_name, dlerror());
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      free(details);
      dlclose_fn(handle);
      continue;
    }

    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Running initialize_logic_module function for logic module %s",
             entry->d_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO, log_msg);
    if (details->initialize_logic_module(nullptr)) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "initialize_logic_module for logic module '%s' returned "
               "non-zero, ignoring this logic module.",
               entry->d_name);
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      status = SVK_STATUS_BAD_FEATURE_LIB;
      num_failed_libs++;
      free(details);
      dlclose_fn(handle);
      continue;
    }

    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Running get_supported_logic_details function for logic module %s",
             entry->d_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO, log_msg);
    if (details->get_supported_logic_details(details) != SVK_STATUS_SUCCESS) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "get_supported_logic_details for logic module '%s' returned "
               "non-zero, ignoring this logic module.",
               entry->d_name);
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      status = SVK_STATUS_BAD_FEATURE_LIB;
      num_failed_libs++;
      free(details);
      dlclose_fn(handle);
      continue;
    }

    if (strcmp(details->feature_name, SLAT_FEATURE_MODULE_NAME) != 0) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE,
               "get_supported_logic_details for logic module '%s' returned "
               "invalid feature name %s, ignoring this logic module.",
               entry->d_name, details->feature_name);
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      free(details);
      dlclose_fn(handle);
      continue;
    }

    // insert logic_id/function pointers into map
    auto [iterator, inserted] = logic_modules_map.insert(
        make_pair(std::string(details->logic_module_name), details));
    if (!inserted) {
      snprintf(
          log_msg, LOG_MSG_MAX_SIZE,
          "SVK SLAT logic module details for logic lib %s wasn't able to be "
          "added to map. You may be getting this error if multiple logic "
          "module libs with the same logic id are in the logic modules lib "
          "dir.",
          entry->d_name);
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
      num_failed_libs++;
      status = SVK_STATUS_BAD_FEATURE_LIB;
      free(details);
      dlclose_fn(handle);
    }
  }
  if (num_failed_libs) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE, "%d logic module libs failed to load.",
             num_failed_libs);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
  } else {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
               "All logic module libs loaded successfully.");
  }

  return status;
}

svk_status SLATrackerSvc::Initialize(const char *slat_config_file) {
  svk_status status = SVK_STATUS_FAIL;
  slat_config config;

  status = this->read_slat_config_file(slat_config_file, &config);
  if (status != SVK_STATUS_SUCCESS) {
    return SVK_STATUS_INVALID_CONFIG;
  }

  status = this->initialize_logger(config);
  if (status != SVK_STATUS_SUCCESS) {
    return status;
  }

  status = this->load_logic_modules(config.slat_logic_lib_dir);
  if (status != SVK_STATUS_SUCCESS) {
    return status;
  }

  this->th_data.shutdown_bm_thread = false;
  this->th_data.thread_running = false;

  if (config.enable_bg_thread) {
    int rc;

    this->th_data.benchmark_run_interval = config.benchmark_run_interval;

    rc = initialize_pub(&this->th_data.zmq_context, &this->th_data.zmq_socket,
                        "0", "5555");
    if (rc != 0) {
      std::cout << "Failed to initialize publisher" << std::endl;
      return SVK_STATUS_FAIL;
    }
    std::cout << "Initialized publisher" << std::endl;

    this->th_data.benchmarking_thread =
        std::thread(&SLATrackerSvc::benchmarking_thread_fn, this);
    this->th_data.thread_running = true;
  }

  return status;
}

svk_logic_module_details *SLATrackerSvc::getLogicDetails(
    char *logic_module_name) {
  char log_msg[LOG_MSG_MAX_SIZE];
  svk_logic_module_details *details = nullptr;

  auto found = this->logic_modules_map.find(std::string(logic_module_name));
  if (found == this->logic_modules_map.end()) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Matching logic module for the [%s] not found. Exiting.",
             logic_module_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
    return details;
  }
  details = found->second;
  return details;
}

void SLATrackerSvc::clean_up(void) {
  int rc;
  if (this->th_data.thread_running) {
    this->th_data.shutdown_bm_thread = true;
    this->th_data.benchmarking_thread.join();

    rc = cleanup_zmq(&this->th_data.zmq_context, &this->th_data.zmq_socket);
    if (rc) {
      std::cout << "Zero MQ Cleanup failed\n" << std::endl;
    }

    std::cout << "Cleanup publisher" << std::endl;
  }
}

// Actual implementation of the feature module functions

extern "C" svk_status initialize(void *details) {
  const char *env_p;
  svk_status status = SVK_STATUS_FAIL;
  std::string conf_path;
  struct stat f_stat;

  if ((env_p = std::getenv("SVK_SLAT_CONFIG"))) {
    conf_path = env_p;
  } else {
    conf_path = SLAT_CONFIG_FILE_DEFAULT;
  }

  if (stat(conf_path.c_str(), &f_stat) != 0) {
    std::cerr << "SLA Tracker service couldn't find the config file - "
              << conf_path << std::endl;
    status = SVK_STATUS_FAIL;
    return status;
  }

  if (g_slat_service == nullptr) {
    std::cerr << "SLA Tracker service object was unable to be allocated"
              << std::endl;
    status = SVK_STATUS_FAIL;
  } else {
    status = g_slat_service->Initialize(conf_path.c_str());
  }

  return status;
}

extern "C" svk_status get_supported_feature_list(feature_id *feature,
                                                 char *feature_names) {
  if (feature == nullptr || feature_names == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "Get supported feature list called with nullptr params");
    return SVK_STATUS_FAIL;
  }
  *feature = feature_id::SLA_TRACKER;
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "Get supported feature list returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status is_license_valid(void *license) {
  if (license == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "is_license_valid function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "License validated successfully.");
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status configure_device_if_any(void *config_details,
                                              svk_device_ctx *device_handles,
                                              uint64_t length, void *resp) {
  if (config_details == nullptr || device_handles == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "configure_device_if_any function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "configure_device_if_any returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status execute_sync(svk_pass_thru_cmd *cmd, svk_input *input,
                                   svk_output *output) {
  char *ptr = NULL;
  char logic_module_name[256];
  svk_logic_module_details *details;
  char log_msg[LOG_MSG_MAX_SIZE];
  svk_logic_cmd logic_cmd;
  svk_logic_input logic_input;
  svk_logic_output logic_output;
  svk_status status;

  if (cmd == nullptr || input == nullptr || output == nullptr ||
      input->input_buffer == nullptr || output->output_buffer == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "execute_sync function called with nullptr params");
    return SVK_STATUS_FAIL;
  }

  ptr = strstr((char *)input->input_buffer, "logic_module");
  if (ptr == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "execute_sync function called without the keyword "
               "'logic_module' in the input structure");
    return SVK_STATUS_FAIL;
  }
  sscanf(ptr, "logic_module=%[a-zA-Z0-9]", logic_module_name);
  details = g_slat_service->getLogicDetails(logic_module_name);
  if (details == nullptr) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Matching logic module for the [%s] not found. Exiting.",
             logic_module_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
    return SVK_STATUS_FAIL;
  }

  if (strstr((const char *)input->input_buffer, "app_name") != nullptr) {
    if (strlen((const char *)input->input_buffer) >= input->len) {
      svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
                 "string length exceeds input buffer length");
      return SVK_STATUS_FAIL;
    }
    return g_slat_service->parse_and_add_new_sla_monitor(
        (const char *)input->input_buffer);
  }

  if (details->execute_logic_sync == nullptr) {
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "logic module [%s]'s execute_logic_sync is null. Exiting.",
             logic_module_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR, log_msg);
    return SVK_STATUS_FAIL;
  }
  strcpy(logic_cmd.logic_name, logic_module_name);
  logic_input.input_buffer = input->input_buffer;
  logic_input.input_len = input->len;
  logic_output.output_buffer = output->output_buffer;
  logic_output.output_len = output->len;
  status = details->execute_logic_sync(&logic_cmd, &logic_input, &logic_output);
  if (status == SVK_STATUS_SUCCESS) {
    output->len = logic_output.output_len;
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
               "execute_sync returned successfully.");
  } else {
    output->len = 0;
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "execute_sync for the logic module [%s] failed",
             logic_module_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO, log_msg);
  }

  return status;
}

extern "C" svk_status execute_async(svk_pass_thru_cmd *pass_thru,
                                    svk_postprocess_fn *postprocess_fn) {
  if (pass_thru == nullptr || postprocess_fn == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "execute_async function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "execute_async returned successfully.");

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status clean_up(void *param) {
  if (param == nullptr) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::ERROR,
               "clean_up function called with nullptr param");
    return SVK_STATUS_FAIL;
  }
  svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
             "clean_up returned successfully.");

  g_slat_service->clean_up();

  return SVK_STATUS_SUCCESS;
}
