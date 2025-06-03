#include "node_info.hpp"

#include <cstdio>
#include <fstream>
#include <iostream>

using json = nlohmann::json;

int initialize_logger(json logger_config) {
  std::string log_level_str =
      logger_config.value("log_level", NODE_FEAT_LOGGER_DEFAULT_LEVEL);
  std::string log_file_name =
      logger_config.value("log_file_name", NODE_FEAT_DEFAULT_LOG_FILE);
  uint64_t log_file_count = logger_config.value(
      "log_file_count", NODE_FEAT_LOGGER_DEFAULT_FILE_COUNT);
  uint64_t log_file_size =
      logger_config.value("log_file_size", NODE_FEAT_LOGGER_DEFAULT_FILE_SIZE);
  std::string sink_type =
      logger_config.value("sink_type", NODE_FEAT_LOGGER_DEFAULT_SINK_TYPE);

  level_E log_level;
  try {
    log_level = log_level_map.at(log_level_str);
    // Set log level for python as well
    py_log_level = log_level_str;
  } catch (const std::out_of_range &e) {
    std::cerr << "Invalid log level from log file, unable to initialize Node "
                 "management logger"
              << std::endl;
    return -1;
  }

  if (svk_logger_init(NODE_FEAT_MODULE_NAME, log_file_name.c_str(), log_level,
                      log_file_count, log_file_size, sink_type.c_str()) != 0) {
    std::cerr
        << "Node Management feature module logger unable to be initialized."
        << std::endl;
    return -1;
  }
  svk_logger(NODE_FEAT_MODULE_NAME, level_E::INFO,
             "Node Management feature module logger initialized.");
  return 0;
}

int find_node_info(std::string info_type, std::string node_info_script_path,
                   std::string &output) {
  std::string logger_str;
  //  Valid node info types are system, memory, network, cpu, devices
  //  If info_type is an empty string, get all node info
  if (info_type.length() != 0 &&
      node_info_types.find(info_type) == node_info_types.end()) {
    logger_str = "Invalid info_type given for the get_node_info: " + info_type;
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    return -1;
  }
  // set command string
  std::string info_type_option = "";
  std::string log_level_option = "";
  if (info_type.length()) {
    info_type_option = "-t " + info_type;
  }
  // py_log_level is set when config is read
  if (py_log_level.length()) {
    if (py_log_levels.count(py_log_level) == 1) {
      log_level_option = "-l " + py_log_level;
    } else {
      // Leave log level empty and find_node_info.py will use INFO
      logger_str = "Log level <" + py_log_level +
                   "> unknown for Python logger, will use default log level "
                   "INFO for find_node_info.py. ";
      svk_logger(NODE_FEAT_MODULE_NAME, level_E::INFO, logger_str.c_str());
    }
  }
  std::string command =
      node_info_script_path + " " + info_type_option + " " + log_level_option;
  logger_str = "Executing python script, full command to be run: " + command;
  svk_logger(NODE_FEAT_MODULE_NAME, level_E::DEBUG, logger_str.c_str());
  // Execute python command
  FILE *pipe = popen(command.c_str(), "r");
  if (!pipe) {
    logger_str = "popen returned null when running python script, error: ";
    logger_str += strerror(errno);
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    return -1;
  }

  // Read output from stdout
  std::string node_info_json_str;
  char buffer[MAX_BUF_LEN];
  while (fgets(buffer, MAX_BUF_LEN, pipe) != NULL) {
    node_info_json_str += buffer;
  }

  int status = pclose(pipe);
  if (status == -1) {
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR,
               "pclose returned an error after attempting to run "
               "get_node_info.py script.");
    return -1;
  }
  logger_str = "Successfully ran popen/pclose and received the node info: " +
               node_info_json_str;
  svk_logger(NODE_FEAT_MODULE_NAME, level_E::DEBUG, logger_str.c_str());
  // Verify that the JSON string is a valid JSON object
  try {
    json j = json::parse(node_info_json_str);
    logger_str = "JSON string from find_node_info.py is valid:\n" + j.dump();
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::DEBUG, logger_str.c_str());
    output = j.dump();
  } catch (json::parse_error &e) {
    logger_str = "Invalid JSON string from find_node_info.py; output:\n" +
                 node_info_json_str;
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    return -1;
  }

  return 0;
}

int run_command(const uint8_t *buffer, uint64_t len, std::string &output) {
  std::string logger_str;
  // Attempt to get command_params from input buffer
  std::string command =
      std::string(reinterpret_cast<const char *>(buffer), len);
  std::string command_name;
  std::string info_type = "";
  try {
    json j = json::parse(command);
    command_name = j["command_name"];
    // Check command_name
    if (command_name == "get_node_info") {
      // Give data type to find the proper node info, if none is specified then
      // get all info
      json command_params = j["command_params"];
      if (command_params.is_object()) {
        info_type = command_params.value("info_type", "");
      }
    } else {
      logger_str = "Invalid command_name: " + command_name;
      svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR, logger_str.c_str());
      return -1;
    }
  } catch (json::exception &e) {
    logger_str = "command_params couldn't be parsed: " + command +
                 "; error: " + e.what();
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR, logger_str.c_str());
    return -1;
  }
  std::string node_info_script_path =
      "python3 " + node_feature_path + "/scripts/find_node_info.py";
  logger_str =
      "Successfully parsed json from input buffer, finding node info with "
      "python script located at <" +
      node_info_script_path + "> and info_type <" + info_type + ">.";
  svk_logger(NODE_FEAT_MODULE_NAME, level_E::DEBUG, logger_str.c_str());
  return find_node_info(info_type, node_info_script_path, output);
}

svk_status initialize(void *init_param) {
  std::string config_path = node_feature_path + "/config/node_mgmt_conf.json";
  std::ifstream config_file(config_path);
  json conf;
  if (config_file.is_open()) {
    conf = json::parse(config_file);
  } else {
    std::cerr << "Unable to parse node mgmt config" << std::endl;
    return SVK_STATUS_INVALID_CONFIG;
  }
  int status;
  try {
    status = initialize_logger(conf.at("logger"));
  } catch (const json::exception &e) {
    std::cerr << "Node mgmt logger config is invalid: " << e.what()
              << std::endl;
    return SVK_STATUS_INVALID_CONFIG;
  }
  if (status != 0) {
    return SVK_STATUS_INVALID_CONFIG;
  }

  return SVK_STATUS_SUCCESS;
}

svk_status get_supported_feature_list(feature_id *feat_id,
                                      char *feature_names) {
  // Returning failure to indicate new feature loading
  return SVK_STATUS_FAIL;
}

svk_status is_license_valid(void *) {
  std::cout << "Node mgmt is_license_valid not implemented" << std::endl;
  return SVK_STATUS_FAIL;
}

svk_status execute_sync(svk_pass_thru_cmd *pass_thru, svk_input *input,
                        svk_output *output) {
  int status;

  std::string response_json_str;
  status = run_command(input->input_buffer, input->len, response_json_str);
  if (status != 0) {
    svk_logger(NODE_FEAT_MODULE_NAME, level_E::ERROR,
               "Execute sync failed attempting to retrieve node info");
    return SVK_STATUS_FAIL;
  }
  output->status = SVK_STATUS_SUCCESS;
  output->output_buffer =
      reinterpret_cast<uint8_t *>(strdup(response_json_str.c_str()));
  output->len = response_json_str.length();
  return SVK_STATUS_SUCCESS;
}

svk_status execute_async(svk_pass_thru_cmd *pass_thru,
                         svk_postprocess_fn *postprocess_fn) {
  std::cout << "Node mgmt feature execute_async not implemented" << std::endl;
  return SVK_STATUS_FAIL;
}

svk_status clean_up(void *) {
  int status;
  status = svk_logger_close(NODE_FEAT_MODULE_NAME);
  if (status != 0) {
    std::cerr << "Node mgmt feature logger failed to close during cleanup"
              << std::endl;
    return SVK_STATUS_FAIL;
  }
  return SVK_STATUS_SUCCESS;
}
