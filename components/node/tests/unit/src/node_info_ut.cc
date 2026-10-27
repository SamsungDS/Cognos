#include <gtest/gtest.h>
#include <stdlib.h>

#include <cstdio>
#include <filesystem>
#include <fstream>

#include "framework_upstream.h"
#include "helper_fns.hpp"
#include "node_info.hpp"

using json = nlohmann::json;

TEST(HelperFnsTests, TestInitLoggerInvalidLogLevel) {
  json logger_config;
  logger_config["log_level"] = "invalid";
  EXPECT_EQ(-1, initialize_logger(logger_config));
}

TEST(HelperFnsTests, TestInitLoggerDefaultValues) {
  json logger_config;
  // Giving dummy json so obj isn't null
  logger_config["key"] = "value";
  EXPECT_EQ(0, initialize_logger(logger_config));
}

TEST(HelperFnsTests, TestInitLoggerInvalidConfig) {
  using json = nlohmann::json;

  json logger_config;
  logger_config["log_file_count"] = 0;
  EXPECT_EQ(-1, initialize_logger(logger_config));
}

TEST(HelperFnsTests, TestFindNodeInfoBadScriptPath) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(0, status);

  std::string info_type = "system";
  std::string script_path = "bad_path";
  std::string output;

  EXPECT_EQ(-1, find_node_info(info_type, script_path, output));
  clean_up((void *)param.c_str());
}

// Adding this test to try individual info call
TEST(HelperFnsTests, TestFindNodeInfoCPU) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(0, status);

  std::string info_type = "cpu";
  std::string script_path = "node/scripts/find_node_info.py";
  std::string output;

  EXPECT_EQ(0, find_node_info(info_type, script_path, output));
  nlohmann::json output_json = nlohmann::json::parse(output);
  std::cout << output_json.dump(4) << std::endl;
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, TestInitialize) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(0, status);
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, TestInitializeNoConfig) {
  using json = nlohmann::json;
  std::string param = "";
  std::string config_path = std::string("node/config/node_mgmt_conf.json");

  std::ifstream config_file(config_path);
  json j = json::parse(config_file);
  std::remove(config_path.c_str());
  sleep(1);

  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG, status);
  sleep(1);
  std::ofstream output_file(config_path);
  output_file << std::setw(4) << j << std::endl;
  output_file.close();
}

TEST(DownstreamAPITests, TestInitializeInvalidConfig) {
  using json = nlohmann::json;
  std::string param = "";
  std::string config_path = std::string("node/config/node_mgmt_conf.json");

  std::ifstream config_file(config_path);
  json j = json::parse(config_file);
  std::remove(config_path.c_str());

  std::ofstream output_file(config_path);
  json bad_config;
  bad_config["invalid"] = "no logger";
  output_file << std::setw(4) << bad_config << std::endl;
  output_file.close();
  sleep(1);

  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG, status);
  sleep(1);
  std::remove(config_path.c_str());
  std::ofstream new_output_file(config_path);
  new_output_file << std::setw(4) << j << std::endl;
  new_output_file.close();
}

TEST(DownstreamAPITests, TestInitializeInvalidLogLevel) {
  using json = nlohmann::json;
  std::string param = "";
  std::string config_path = std::string("node/config/node_mgmt_conf.json");

  std::ifstream config_file(config_path);
  json j = json::parse(config_file);
  std::remove(config_path.c_str());

  std::ofstream output_file(config_path);
  j["logger"]["log_level"] = "invalid";
  output_file << std::setw(4) << j << std::endl;
  output_file.close();
  sleep(1);

  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG, status);
  sleep(1);
  std::remove(config_path.c_str());
  j["logger"]["log_level"] = "INFO";
  std::ofstream new_output_file(config_path);
  new_output_file << std::setw(4) << j << std::endl;
  new_output_file.close();
}

TEST(DownstreamAPITests, GetSupportedFeatureList) {
  // Should return failure for new feature modules
  EXPECT_EQ(SVK_STATUS_FAIL, get_supported_feature_list(nullptr, nullptr));
}

TEST(DownstreamAPITests, IsLicenseValid) {
  // Returning fail for not implemented
  EXPECT_EQ(SVK_STATUS_FAIL, is_license_valid(nullptr));
}

TEST(DownstreamAPITests, ExecuteSyncSuccessForNodeStats) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  using json = nlohmann::json;
  json command_json;
  command_json["command_name"] = "node_stats";

  std::string command_json_str = command_json.dump();
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, ExecuteSyncSuccess) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  using json = nlohmann::json;
  json command_json;
  command_json["command_name"] = "get_node_info";

  json command_params;
  // Get all info
  command_params["info_type"] = "";
  command_json["command_params"] = command_params;

  std::string command_json_str = command_json.dump();
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, ExecuteSyncNoInfoType) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  using json = nlohmann::json;
  json command_json;
  command_json["command_name"] = "get_node_info";
  command_json["command_params"] = "";
  // Get all info if info_type is not specified
  // Command params is guaranteed to be provied from controller

  std::string command_json_str = command_json.dump();
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, ExecuteSyncInvalidCommandName) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  using json = nlohmann::json;
  json command_json;
  command_json["command_name"] = "invalid";

  json command_params;
  // Get all info
  command_params["info_type"] = "";
  command_json["command_params"] = command_params;

  std::string command_json_str = command_json.dump();
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_FAIL, status);
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, ExecuteSyncInvalidCommandParams) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  std::string command_json_str = "invalid";
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_FAIL, status);
  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, ExecuteSyncInvalidDataType) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  using json = nlohmann::json;
  json command_json;
  command_json["command_name"] = "get_node_info";

  json command_params;

  command_params["info_type"] = "invalid";
  command_json["command_params"] = command_params;

  std::string command_json_str = command_json.dump();
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_FAIL, status);

  clean_up((void *)param.c_str());
}

TEST(DownstreamAPITests, ExecuteSyncInvalidPythonLogLevel) {
  using json = nlohmann::json;
  std::string param = "";
  std::string config_path = std::string("node/config/node_mgmt_conf.json");

  std::ifstream config_file(config_path);
  json j = json::parse(config_file);
  std::remove(config_path.c_str());

  std::ofstream output_file(config_path);
  j["logger"]["log_level"] = "TRACE";
  output_file << std::setw(4) << j << std::endl;
  output_file.close();
  sleep(1);

  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));
  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);
  sleep(1);

  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  using json = nlohmann::json;
  json command_json;
  command_json["command_name"] = "get_node_info";

  json command_params;

  command_params["info_type"] = "all";
  command_json["command_params"] = command_params;

  std::string command_json_str = command_json.dump();
  input.input_buffer =
      reinterpret_cast<uint8_t *>(strdup(command_json_str.c_str()));
  input.len = command_json_str.length();

  status = execute_sync(&cmd, &input, &output);
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  clean_up((void *)param.c_str());

  sleep(1);
  std::remove(config_path.c_str());
  j["logger"]["log_level"] = "INFO";
  std::ofstream new_output_file(config_path);
  new_output_file << std::setw(4) << j << std::endl;
  new_output_file.close();
}

TEST(DownstreamAPITests, ExecuteAsync) {
  svk_pass_thru_cmd cmd;
  svk_postprocess_fn fn;
  EXPECT_EQ(SVK_STATUS_FAIL, execute_async(&cmd, &fn));
}

TEST(DownstreamAPITests, CleanupSuccess) {
  std::string param = "";
  EXPECT_EQ(0, set_node_name("node1", strlen("node1")));

  svk_status status = initialize((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);

  status = clean_up((void *)param.c_str());
  EXPECT_EQ(SVK_STATUS_SUCCESS, status);
}
