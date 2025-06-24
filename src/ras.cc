#include "ras.hpp"

#include <fmt/format.h>

#include <filesystem>

#include "ras_monitor.h"

struct ras_context_s {
  ras_monitor *monitor_context;
  bool initialized;
  logic_module_manager adapters;
  std::mutex ctx_mutex;
};
struct ras_context_s g_ras_context = {.monitor_context = nullptr,
                                      .initialized = false};

svk_status parsing_ras_conf(std::string ras_conf_path, ras_conf *ras_configs) {
  boost::property_tree::ptree root_conf;
  static boost::property_tree::ptree logger_conf;
  try {
    boost::property_tree::read_json(ras_conf_path, root_conf);
  } catch (std::exception &e) {
    std::cout << "Unable to read ras config. Error -> " << e.what() << "."
              << std::endl
              << "Using the default config" << std::endl;
  }
  try {
    logger_conf = root_conf.get_child("ras.logger");
  } catch (std::exception &e) {
    std::cout << "Unable to read ras logger config. Error -> " << e.what()
              << "." << std::endl
              << "Using the default config" << std::endl;
  }
  ras_configs->log_file_name = logger_conf.get<std::string>(
      "log_file_name", RAS_LOGGER_FILE_NAME_DEFAULT);
  ras_configs->log_level =
      logger_conf.get<std::string>("log_level", RAS_LOGGER_LEVEL_DEFAULT);
  ras_configs->log_file_count =
      logger_conf.get<int>("log_file_count", RAS_LOGGER_FILE_COUNT_DEFAULT);
  ras_configs->log_file_size =
      logger_conf.get<int>("log_file_size", RAS_LOGGER_FILE_SIZE_DEFAULT);
  ras_configs->log_sink_type =
      logger_conf.get<std::string>("sink_type", RAS_LOGGER_SINK_TYPE_DEFAULT);

  ras_configs->adapters_directory = root_conf.get<std::string>(
      "adapters_directory", RAS_DEFAULT_ADAPTERS_DIRECTORY);
  if (!(std::filesystem::exists(ras_configs->adapters_directory) &&
        std::filesystem::is_directory(ras_configs->adapters_directory))) {
    std::cout << "Adapters Directory does not exist." << std::endl;
    return SVK_STATUS_FAIL;
  }
  return SVK_STATUS_SUCCESS;
}

static inline bool validate_lib_entry(const std::string &lib_path_str) {
  std::filesystem::path lib_path = lib_path_str;
  if (!std::filesystem::exists(lib_path)) {
    svk_logger(RAS_LOGGER, level_E::WARN,
               fmt::format("Library not found {}", lib_path_str).c_str());

    return false;
  }
  return true;
}
/**
 * NOTE: RAS adpaters are dynamic (.so) libraries that are compliant to svk
 * logic interface. The loading is tried on each directory listing given in the
 * load path `ras_adapters_dir`. If the directory name is <name> then if
 * lib64/lib<name>.so exists then it will be loaded, if it complies with the svk
 * logic interface.
 */
static inline svk_status load_ras_adapters(
    const std::string &ras_adapters_dir) {
  std::filesystem::path load_dir = ras_adapters_dir;

  for (const auto &entry : std::filesystem::directory_iterator(load_dir)) {
    auto entry_path_str = entry.path().string();
    if (!entry.is_directory()) {
      svk_logger(RAS_LOGGER, level_E::WARN,
                 fmt::format("Skipping non directory entry {}", entry_path_str)
                     .c_str());
      continue;
    }

    std::string lib_path_str = fmt::format("{}/lib64/lib{}.so", entry_path_str,
                                           entry.path().filename().string());

    if (validate_lib_entry(lib_path_str)) {
      auto logic_module_name = g_ras_context.adapters.load_logic_module(
          lib_path_str, std::string(RAS_FEATURE_MODULE_NAME));
      if (logic_module_name == std::nullopt) {
        svk_logger(
            RAS_LOGGER, level_E::WARN,
            fmt::format("Failed to load adapter {}", lib_path_str).c_str());
        continue;
      }
    } else {
      svk_logger(
          RAS_LOGGER, level_E::WARN,
          fmt::format("Skipping non compliant directory {}", entry_path_str)
              .c_str());
    }
  }
  return SVK_STATUS_SUCCESS;
}

// initialize_svk(char* config_file, void *details) will initialize svk_logger_0
// according to the config file path and the function here will enable an
// internal ras logger (svk_logger_1) which can log without svk-core
extern "C" svk_status initialize(void *details) {
  svk_status rc = SVK_STATUS_FAIL;
  std::string ras_conf_path;
  const char *env_p;
  if ((env_p = std::getenv("SVK_RAS_CONFIG")) != nullptr) {
    ras_conf_path = env_p;
  } else {
    ras_conf_path = RAS_CONFIG_FILE_DEFAULT;
  }
  ras_conf *ras_configs = new ras_conf();
  rc = parsing_ras_conf(ras_conf_path, ras_configs);
  if (rc != SVK_STATUS_SUCCESS) {
    return rc;
  }
  // TODO: in the next version with more stuff to init in this function
  // we should refactor this init function and put logger related map &
  // initialization in the ras_logger_init function
  if (svk_logger_init(RAS_LOGGER, ras_configs->log_file_name.c_str(),
                      log_level_map.at(ras_configs->log_level),
                      ras_configs->log_file_count, ras_configs->log_file_size,
                      ras_configs->log_sink_type.c_str()) == 0) {
    svk_logger(RAS_LOGGER, level_E::INFO,
               "ras init called & logger is initialized");
  } else {
    std::cerr << "ras logger init fail" << std::endl;
    return SVK_STATUS_INVALID_CONFIG;
  }

  std::lock_guard<std::mutex> lock(g_ras_context.ctx_mutex);

  // Load adapters
  load_ras_adapters(ras_configs->adapters_directory);

  if (g_ras_context.monitor_context == nullptr) {
    g_ras_context.monitor_context = new ras_monitor();
    if (g_ras_context.monitor_context == nullptr) {
      svk_logger("ras", level_E::ERROR, "ras monitor context init fail");
      return SVK_STATUS_FAIL;
    }
    g_ras_context.initialized = true;
  }

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status get_supported_feature_list(feature_id *feature,
                                                 char *feature_names) {
  *feature = feature_id::ZERO_ETL;
  std::string msg = "ras get_supported_feature_list called";
  svk_logger("ras", level_E::INFO, msg.c_str());

  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status is_license_valid(void *) {
  std::string msg = "ras is_license_valid called";
  svk_logger("ras", level_E::INFO, msg.c_str());
  return SVK_STATUS_SUCCESS;
}

// Assuming that input and output buffers contain strings
extern "C" svk_status execute_sync(svk_pass_thru_cmd *cmd, svk_input *input,
                                   svk_output *output) {
  char debug_info[2048];

  if (cmd == nullptr || input == nullptr || output == nullptr ||
      input->input_buffer == nullptr || output->output_buffer == nullptr) {
    svk_logger(RAS_LOGGER, level_E::ERROR,
               "execute_sync function called with nullptr params");
    return SVK_STATUS_FAIL;
  }

  output->status = SVK_STATUS_FAIL;

  // Assuming null terminated string with input->len set to length of the string
  if (strnlen((char *)input->input_buffer, input->len + 1) == input->len + 1) {
    return SVK_STATUS_FAIL;
  }

  snprintf(debug_info, sizeof(debug_info),
           "ras execute_sync called.\ninput buffer: %s\noutput buffer:%s\n",
           (char *)input->input_buffer, (char *)output->output_buffer);
  svk_logger(RAS_LOGGER, level_E::INFO, debug_info);

  ras_request request(
      true, g_ras_context.monitor_context, false, (char *)input->input_buffer,
      input->len);  // Local variable okay since this will be sync

  // Initialize request command json
  if (request.parse_input_command_to_json() == false) {
    svk_logger(RAS_LOGGER, level_E::INFO, "json parse failed");
    return SVK_STATUS_FAIL;
  }

  bool submit_okay = false;

  submit_okay = g_ras_context.monitor_context->ras_submit_request(&request);
  if (submit_okay != true) {
    svk_logger(RAS_LOGGER, level_E::INFO, "submit failed");
    return SVK_STATUS_FAIL;
  }

  if (request.is_successfull == false) {
    output->status = SVK_STATUS_FAIL;
    return SVK_STATUS_FAIL;
  }

  output->status = SVK_STATUS_SUCCESS;
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status execute_async(svk_pass_thru_cmd *pass_thru,
                                    svk_postprocess_fn *postprocess_fn) {
  std::string msg = "ras execute_async called";
  svk_logger("ras", level_E::INFO, msg.c_str());
  return SVK_STATUS_SUCCESS;
}

extern "C" svk_status clean_up(void *) {
  std::string msg = "ras clean_up called";
  svk_logger("ras", level_E::INFO, msg.c_str());
  std::lock_guard<std::mutex> lock(g_ras_context.ctx_mutex);
  if (g_ras_context.initialized == true) {
    delete g_ras_context.monitor_context;
    g_ras_context.monitor_context = nullptr;
    g_ras_context.initialized = false;
  }
  return SVK_STATUS_SUCCESS;
}
