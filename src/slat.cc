#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <iostream>
#include <memory>

#include "logic_interface/svk_logic_struct.h"
#include "svk_logger.h"
#include "svk_slat.hpp"

#define LOG_MSG_MAX_SIZE (1024)
#define LIBRARY_SUFFIX ".so"
using namespace std;

// Global variable to use for Framework service commands
const std::unique_ptr<SLATrackerSvc> g_slat_service =
    std::make_unique<SLATrackerSvc>();

#define LOGIC_OUT_BUFFER_LEN (256)
/* Private SLATrackerSvc helper methods */
std::string SLATrackerSvc::run_benchmark(slat_benchmark_config config) {
  svk_status status;

  svk_logic_module_details *details;
  svk_logic_cmd logic_cmd;
  svk_logic_input logic_input = {};
  svk_logic_output logic_output;
  char *out[LOGIC_OUT_BUFFER_LEN] = {};

  logic_output.output_buffer = (uint8_t *)out;
  logic_output.output_len = LOGIC_OUT_BUFFER_LEN;

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

void SLATrackerSvc::parse_result(slat_benchmark_config config,
                                 std::string result) {
  char *ptr = nullptr;
  char parsed_result[LOGIC_OUT_BUFFER_LEN];
  if (config.benchmark_tool == "mlc") {
    ptr = strstr((char *)result.c_str(), "avgReadLatency");
    if (ptr == nullptr) {
      std::cout << "Error parsing result" << std::endl;
      return;
    }
    sscanf(ptr, "logic_module=%[.0-9]", parsed_result);
    uint64_t avgReadLatency = atof(parsed_result);
    this->th_data.benchmark_data.avgReadLatency = avgReadLatency;
  }
}

void SLATrackerSvc::benchmarking_thread_fn(void) {
  std::string benchmark_result_str;
  int rc;

  std::cout << "Started benchmarking thread" << std::endl;
  while (1) {
    for (slat_benchmark_config bconfig : this->th_data.benchmark_list) {
      benchmark_result_str = run_benchmark(bconfig);
      parse_result(bconfig, benchmark_result_str);
    }

    rc = publish(&this->th_data.zmq_socket,
                 "DEVICE_SLA:", &this->th_data.benchmark_data);
    if (rc == -1) {
      std::cout << " failed to publish sla results" << std::endl;
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
      config->log_level = logger_info_pt.get<std::string>(
          "log_level", SLAT_LOGGER_LEVEL_DEFAULT);
      config->log_filename = logger_info_pt.get<std::string>(
          "log_file_name", SLAT_LOG_FILENAME_DEFAULT);
      config->log_file_count = logger_info_pt.get<uint64_t>(
          "log_file_count", SLAT_LOGGER_FILE_COUNT_DEFAULT);
      config->log_file_size = logger_info_pt.get<uint64_t>(
          "log_file_size", SLAT_LOGGER_FILE_SIZE_DEFAULT);
      config->log_sink_type = logger_info_pt.get<std::string>(
          "sink_type", SLAT_LOGGER_SINK_TYPE_DEFAULT);
    } catch (std::exception &e) {
      std::cout << "Unable to read Logger section of SLAT in the config file. "
                   "Falling back to default values. Error -> "
                << e.what() << std::endl;
      // Assign defaults
      config->log_level = SLAT_LOGGER_LEVEL_DEFAULT;
      config->log_filename = SLAT_LOG_FILENAME_DEFAULT;
      config->log_file_count = SLAT_LOGGER_FILE_COUNT_DEFAULT;
      config->log_file_size = SLAT_LOGGER_FILE_SIZE_DEFAULT;
      config->log_sink_type = SLAT_LOGGER_SINK_TYPE_DEFAULT;
    }
  } catch (std::exception &e) {
    std::cerr << "Unable to read SLAT config file. Assigning default value. "
                 "Error -> "
              << e.what() << std::endl;
    config->slat_logic_lib_dir = SLAT_FEATURE_LOGIC_MODULES_PATH;

    // Assign defaults
    config->log_level = SLAT_LOGGER_LEVEL_DEFAULT;
    config->log_filename = SLAT_LOG_FILENAME_DEFAULT;
    config->log_file_count = SLAT_LOGGER_FILE_COUNT_DEFAULT;
    config->log_file_size = SLAT_LOGGER_FILE_SIZE_DEFAULT;
    config->log_sink_type = SLAT_LOGGER_SINK_TYPE_DEFAULT;
  }

  return status;
}

svk_status SLATrackerSvc::initialize_logger(const slat_config config) const {
  svk_status status = SVK_STATUS_FAIL;
  auto found = log_level_map.find(config.log_level);
  if (found == log_level_map.end()) {
    std::cout << "Matching log level for the [" << config.log_level
              << "] not found. Exiting" << std::endl;
    return status;
  }

  if (svk_logger_init(SLAT_LOGGER_MODULE_NAME, config.log_filename.c_str(),
                      found->second, config.log_file_count,
                      config.log_file_size,
                      config.log_sink_type.c_str()) == SVK_STATUS_SUCCESS) {
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO,
               "SVK SLAT logger is initialized");
    status = SVK_STATUS_SUCCESS;
  } else {
    std::cout << "SVK SLAT logger initialization failed" << std::endl;
  }
  return status;
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
    std::string entry_name(entry->d_name);
    std::string library_suffix(LIBRARY_SUFFIX);
    std::string full_path(logic_modules_lib_dir + "/" + entry_name);

    stat(full_path.c_str(), &st);
    if (S_ISDIR(st.st_mode)) {
      std::string file(full_path + "/lib64/lib" + entry_name + ".so");
      entry_name = file;
    }

    // If dir entry is smaller than length(.so), skip the entry
    // Otherwise compare the last 3 chars to .so to see if it is valid
    if (entry_name.compare(entry_name.size() - library_suffix.size(),
                           library_suffix.size(), library_suffix) != 0) {
      continue;
    }

    std::string logic_module_lib_str =
        logic_modules_lib_dir + "/" + entry->d_name;
    snprintf(log_msg, LOG_MSG_MAX_SIZE,
             "Attempting to load feature module functions for %s",
             entry->d_name);
    svk_logger(SLAT_LOGGER_MODULE_NAME, level_E::INFO, log_msg);
    void *handle = dlopen_fn(logic_module_lib_str.c_str(), RTLD_LAZY);
    if (!handle) {
      snprintf(log_msg, LOG_MSG_MAX_SIZE, "dlopen failure for %s. Error: %s\n",
               logic_module_lib_str.c_str(), dlerror());
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

    slat_benchmark_config bc;
    bc.benchmark_tool = "mlc";
    bc.benchmark_out_field = "avgLatencyus";

    this->th_data.benchmark_list.push_back(bc);
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
