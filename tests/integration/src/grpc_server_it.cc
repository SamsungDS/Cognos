#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdio.h>
#include <stdlib.h>

#include <csignal>
#include <regex>
#include <thread>

#include "client_library.h"
#include "framework/framework_mock.grpc.pb.h"
#include "framework_extern.h"
#include "grpc_controller.h"
#include "grpc_controller_hlpr.h"
#include "grpc_server.h"
#include "grpc_server_hlpr.h"
#include "sla_hlpr_fns.h"
#include "svk_publisher.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::HasSubstr;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StartsWith;
using ::testing::StrEq;

using json = nlohmann::json;

#define FEATURES_DIR "/usr/local/svk/core/tests/sample_feature/"

int create_svk_mgmt_fw_conf_json(std::string conf_file,
                                 std::string fw_conf_file,
                                 std::string sink_type, int log_file_count,
                                 uint64_t log_file_size, std::string log_level,
                                 std::string features_dir,
                                 std::string controller_id) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_node.framework.conf_file", fw_conf_file);
  root.put("svk_mgmt_fw_node.cluster.id", DEFAULT_CLUSTER_ID);
  root.put("svk_mgmt_fw_node.controller.id", controller_id);
  root.put("svk_mgmt_fw_node.controller.port", DEFAULT_CONTROLLER_PORT);
  root.put("svk_mgmt_fw_node.node.id", DEFAULT_NODE_ID);
  root.put("svk_mgmt_fw_node.node.ip", DEFAULT_NODE_ID);
  root.put("svk_mgmt_fw_node.node.port", DEFAULT_NODE_PORT);
  root.put("svk_mgmt_fw_node.logger.log_level", log_level);
  root.put("svk_mgmt_fw_node.logger.log_file_name",
           "/var/log/svk/svk_mgmt_fw_node.log");
  root.put("svk_mgmt_fw_node.logger.log_file_count", log_file_count);
  root.put("svk_mgmt_fw_node.logger.log_file_size", log_file_size);
  root.put("svk_mgmt_fw_node.logger.sink_type", sink_type);

  root.put("core.feat_modules_dir", FEATURES_DIR);
  root.put("core.logger.log_level", log_level);
  root.put("core.logger.log_file_name", "/var/log/svk/svk_framework.log");
  root.put("core.logger.log_file_count", log_file_count);
  root.put("core.logger.log_file_size", log_file_size);
  root.put("core.logger.sink_type", sink_type);

  root.put("svk_mgmt_fw_controller.controller.id", controller_id);
  root.put("svk_mgmt_fw_controller.controller.port", CONTROLLER_DEFAULT_PORT);
  root.put("svk_mgmt_fw_controller.logger.log_level", log_level);
  root.put("svk_mgmt_fw_controller.logger.log_file_name",
           CONTROLLER_NODE_DEFAULT_LOG_FILE);
  root.put("svk_mgmt_fw_controller.logger.log_file_count", 10);
  root.put("svk_mgmt_fw_controller.logger.log_file_size", (1024 * 1024 * 1024));
  root.put("svk_mgmt_fw_controller.logger.sink_type", sink_type);

  pt::write_json(json_file, root);

  return 0;
}

static std::string get_epoch_string() {
  auto now = std::chrono::system_clock::now();
  auto epoch =
      std::chrono::duration_cast<std::chrono::seconds>(now.time_since_epoch())
          .count();

  // Convert the epoch time to a string
  return std::to_string(epoch);
}

static std::string get_sla_deviation_data(std::string feature_name,
                                          std::string device_name,
                                          std::string host_name,
                                          std::string app_name,
                                          uint64_t latency) {
  json json_map;
  json observations_map;
  observations_map["device_id"] =
      generate_unique_device_id(host_name, device_name);
  observations_map["host_name"] = host_name;
  observations_map["app_name"] = app_name;
  observations_map["avg_latency_ns"] = latency;
  observations_map["message"] = "Device SLA deviation";
  observations_map["feature_name"] = feature_name;

  json_map["domain"] = "observability";
  json_map["category"] = feature_name;
  json_map["severity"] = "warning";
  json_map["feature_name"] = feature_name;
  json_map["msg"] = "Downgraded SLA detected";

  json_map["source"] = "node";
  json_map["source_type"] = host_name;
  json_map["timestamp"] = get_epoch_string();
  json_map["observations"] = observations_map;

  std::string json_data_str = json_map.dump();
  return json_data_str;
}

static std::string generate_ras_event(std::string feature_name,
                                      std::string numa, std::string host_name,
                                      std::string app_name,
                                      uint64_t error_cnt) {
  json json_map;
  json observations_map;
  observations_map["device_id"] = generate_unique_device_id(host_name, numa);
  observations_map["device_name"] = generate_unique_device_id(host_name, numa);
  observations_map["error_cnt"] = error_cnt;
  observations_map["message"] = "Device RAS error count hit the threshold";
  observations_map["feature_name"] = feature_name;

  json_map["domain"] = "observability";
  json_map["category"] = feature_name;
  json_map["severity"] = "warning";
  json_map["feature_name"] = feature_name;

  json_map["source"] = "node";
  json_map["source_type"] = host_name;
  json_map["timestamp"] = get_epoch_string();
  json_map["observations"] = observations_map;

  std::string json_data_str = json_map.dump();
  return json_data_str;
}

/**
 * Checks if a given string exists in the log file.
 *
 * @param search_str The string to search for in the log file.
 * @return True if the string is found in the log file, false otherwise.
 */
bool is_str_in_log(std::string file_name, std::string search_str) {
  // Use this call to flush logs immediately
  svk_logger_flush(CONTROLLER_LOGGER_MODULE_NAME);
  sleep(0.5);

  // Check if the log file exists
  std::ifstream file(file_name);
  if (!file.good()) {
    const char *message = (file_name + " doesn't exist").c_str();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR, message);
    return false;
  }
  // Read the entire log file into a string
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));

  // Close the file
  file.close();

  // Check if the search string is found in the log file
  return data.find(search_str) != std::string::npos;
}

TEST(InitIntegrationTest, InitControllerAndNodeServerSuccess) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, FeatureAPISuccess) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::FeatureRequest req;
  svk::FeatureResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);

  req.set_feature_name("new_sample_feature");
  req.set_command_name("FeatureAPI_command");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.FeatureAPI(&req, &resp);
  ASSERT_TRUE(status.ok());
  std::cout << "FeatureAPI response: " << resp.response(0) << std::endl;
  EXPECT_THAT(resp.response(0),
              StartsWith("{\"output_key\":\"output_value\"}"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, FeatureAPINoNodeName) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::FeatureRequest req;
  svk::FeatureResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name("");

  req.set_feature_name("new_sample_feature");
  req.set_command_name("FeatureAPI_command");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.FeatureAPI(&req, &resp);
  ASSERT_TRUE(status.ok());
  std::cout << "FeatureAPI response: " << resp.response(0) << std::endl;
  EXPECT_THAT(resp.response(0),
              StartsWith("{\"output_key\":\"output_value\"}"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, FeatureAPINoCommand) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::FeatureRequest req;
  svk::FeatureResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);

  req.set_feature_name("new_sample_feature");
  req.set_command_name("");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.FeatureAPI(&req, &resp);
  ASSERT_FALSE(status.ok());

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, FeatureAPINoClusterName) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::FeatureRequest req;
  svk::FeatureResponse resp;

  req.set_cluster_name("");
  req.set_node_name(DEFAULT_NODE_ID);

  req.set_feature_name("new_sample_feature");
  req.set_command_name("FeatureAPI_command");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.FeatureAPI(&req, &resp);
  ASSERT_TRUE(status.ok());
  std::cout << "FeatureAPI response: " << resp.response(0) << std::endl;
  EXPECT_THAT(resp.response(0),
              StartsWith("{\"output_key\":\"output_value\"}"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, FeatureAPINoClusterOrNode) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::FeatureRequest req;
  svk::FeatureResponse resp;

  req.set_cluster_name("");
  req.set_node_name("invalid");

  req.set_feature_name("new_sample_feature");
  req.set_command_name("FeatureAPI_command");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.FeatureAPI(&req, &resp);
  ASSERT_FALSE(status.ok());

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, FeatureAPIRegisteredNodeNotInCluster) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  svk::RegisterRequest reg_req;
  svk::RegisterResponse reg_resp;
  reg_req.set_node_name("node_no_cluster");
  reg_req.set_node_ip("127.0.0.1");
  reg_req.set_node_port("9998");

  Status status = client.RegisterNode(&reg_req, &reg_resp);
  ASSERT_TRUE(status.ok());

  svk::FeatureRequest req;
  svk::FeatureResponse resp;

  req.set_cluster_name("");
  req.set_node_name("node_no_cluster");

  req.set_feature_name("new_sample_feature");
  req.set_command_name("FeatureAPI_command");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");

  status = client.FeatureAPI(&req, &resp);
  ASSERT_FALSE(status.ok());

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandSuccess) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id(DEFAULT_NODE_ID);
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "ProcessSampleCommand Output: "
            << resp->node_responses(0).output() << std::endl;
  EXPECT_THAT(resp->node_responses(0).output().c_str(),
              StartsWith("sample_key=value"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandStrKeySuccess) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_name("new_sample_feature");
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id(DEFAULT_NODE_ID);
  req.set_command_params("{\"sample_key\":\"sample_value\"}");
  req.set_command_name("sample_command");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "ProcessSampleCommand Output: "
            << resp->node_responses(0).output() << std::endl;
  EXPECT_THAT(resp->node_responses(0).output().c_str(),
              StartsWith("{\"output_key\":\"output_value\"}"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandSuccessWithClusterIDOnly) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "ProcessSampleCommand Output: "
            << resp->node_responses(0).output() << std::endl;
  EXPECT_THAT(resp->node_responses(0).output().c_str(),
              StartsWith("sample_key=value"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandWithInvalidCluster) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id("INVALID_CLUSTER");
  req.set_node_id(DEFAULT_NODE_ID);
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandWithoutClusterID) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_node_id(DEFAULT_NODE_ID);
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandWithInvalidNode) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id("node.dummy.net");
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest,
     ProcessControllerCommandWithOneValidAndOneInvalidNode) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id("localhost,dummynode");
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandWithInvalidFeatureID) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)100);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id(DEFAULT_NODE_ID);
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  ASSERT_EQ(resp->node_responses().size(), 0);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandWithInvalidFeatureParams) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id(DEFAULT_NODE_ID);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  ASSERT_EQ(resp->node_responses().size(), 0);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, InitControllerAndNodeServerWithInvalidController) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  std::string conf_file1 = std::string(cw_dir) + "/conf1.json";
  create_svk_mgmt_fw_conf_json(
      conf_file1, conf_file1, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, "Invalid_Controller");

  Servicer *svcr(new Servicer(conf_file1));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_EQ(server, nullptr);
  unlink(conf_file.c_str());
  unlink(conf_file1.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandWithoutNodeRegistration) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_feature_params("Test=Value");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandForAllocateMemoryFailure) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params("sla_latency_ns=10;app_name=TestApp;size=1024");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  req.set_command_id("allocate_memory");
  req.set_feature_params("sla_latency_ns=10");

  status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  req.set_command_id("allocate_memory");
  req.set_feature_params("app_name=TestApp");

  status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  req.set_command_id("allocate_memory");
  req.set_feature_params("size=100");

  status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=10;app_name=TestApp;size=1024;logic_module=default");

  status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}

int CheckPoller() {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  std::thread server_thr(StartServer, conf_file, true);
  std::thread node_thr(StartNodeServer, conf_file, true);
  // Sleep for a while for the server processes to stablize
  sleep(10);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "InitControllerNodeServerWithSignal in CheckPoller");

  // Raise the interrupt signal for the server to go down gracefully
  std::thread::id node_thread_id = node_thr.get_id();
  std::thread::id ctrlr_thread_id = server_thr.get_id();

  auto node_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&node_thread_id);
  auto ctrlr_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&ctrlr_thread_id);

  pthread_kill(node_native_handle, SIGINT);
  // Wait for > 5 seconds for the signal handler to be processed on the server
  // node
  sleep(10);

  pthread_kill(ctrlr_native_handle, SIGINT);
  // Wait for > 5 seconds for the signal handler to be processed on the server
  // node
  sleep(10);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "Done with InitControllerNodeServerWithSignal in CheckPoller");

  unlink(conf_file.c_str());
  return 0;
}

TEST(InitIntegrationTest, InitControllerNodeServerWithSignal) {
  GTEST_FLAG_SET(death_test_style, "threadsafe");
  EXPECT_DEATH(CheckPoller(), "");
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Updated node localhost's status to offline"));
}

int CheckNodeStatus() {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);
  std::thread server_thr(StartServer, conf_file, true);
  std::thread node_thr(StartNodeServer, conf_file, true);
  // Sleep for a while for the server processes to stablize
  sleep(5);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  // Check internal structure is updated
  svk::NodeRequest *n_req(new svk::NodeRequest());
  svk::NodeResponse *n_resp(new svk::NodeResponse());

  n_req->set_command_name("list_nodes");

  Status grpc_status = client.NodeAPI(n_req, n_resp);
  EXPECT_EQ(grpc_status.ok(), true);
  std::string command_resp = n_resp->command_response();
  std::string expected_resp =
      "{\"node_info\":[{\"node_ip\":\"localhost\",\"node_"
      "name\":\"localhost\",\"node_port\":\"9998\","
      "\"status\":\"online\"}]}";
  std::cout << "List nodes response on startup: " << command_resp << std::endl;
  EXPECT_EQ(command_resp, expected_resp);
  sleep(1);
  // Raise the interrupt signal for the server to go down gracefully
  std::thread::id node_thread_id = node_thr.get_id();
  auto node_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&node_thread_id);
  pthread_kill(node_native_handle, SIGINT);
  sleep(5);

  // Check the nodes status after server shutdown
  grpc_status = client.NodeAPI(n_req, n_resp);
  EXPECT_EQ(grpc_status.ok(), true);
  command_resp = n_resp->command_response();
  expected_resp =
      "{\"node_info\":[{\"node_ip\":\"localhost\",\"node_"
      "name\":\"localhost\",\"node_port\":\"9998\","
      "\"status\":\"offline\"}]}";
  EXPECT_EQ(command_resp, expected_resp);
  std::cout << "List nodes response on shutdown: " << command_resp << std::endl;
  sleep(1);

  // Start node again
  std::thread node_thr2(StartNodeServer, conf_file, true);
  sleep(5);
  // Check the nodes status after server restart
  grpc_status = client.NodeAPI(n_req, n_resp);
  EXPECT_EQ(grpc_status.ok(), true);
  command_resp = n_resp->command_response();
  expected_resp =
      "{\"node_info\":[{\"node_ip\":\"localhost\",\"node_"
      "name\":\"localhost\",\"node_port\":\"9998\","
      "\"status\":\"online\"}]}";
  EXPECT_EQ(command_resp, expected_resp);
  std::cout << "List nodes response on restart: " << command_resp << std::endl;

  sleep(1);
  node_thread_id = node_thr2.get_id();
  std::thread::id ctrlr_thread_id = server_thr.get_id();
  node_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&node_thread_id);
  auto ctrlr_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&ctrlr_thread_id);
  pthread_kill(node_native_handle, SIGINT);
  pthread_kill(ctrlr_native_handle, SIGINT);
  // Wait for > 5 seconds for the signal handler to be processed on the server
  // node
  sleep(5);
  unlink(conf_file.c_str());
  return 0;
}

TEST(InitIntegrationTest, CheckNodeStatusUpdated) {
  std::string output;
  GTEST_FLAG_SET(death_test_style, "threadsafe");
  EXPECT_DEATH(CheckNodeStatus(), "");
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, data.find("Updated node localhost's status to offline") !=
                      std::string::npos);
  EXPECT_EQ(
      true,
      data.find("Marking all the devices of the node localhost to offline") !=
          std::string::npos);
}

TEST(InitIntegrationTest, UnregisterNodeServer) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::UnregisterRequest req;
  svk::UnregisterResponse *resp = new (svk::UnregisterResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_node_id(DEFAULT_NODE_ID);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.UnregisterNode(&req, resp);
  ASSERT_EQ(status.ok(), true);
  unlink(conf_file.c_str());
}

// Trimmed down version of node feature output
#define NODE_PCI_FEATURE_OUTPUT                                          \
  "{\"pci-info\":[{\"NUMA "                                              \
  "node\":\"0\",\"device_manufacturer\":\"Samsung Electronics Co "       \
  "Ltd\",\"device_type\":\"nvme\",\"pci_address\":\"2c:00.0\"},{\"NUMA " \
  "node\":\"0\",\"device_manufacturer\":\"Montage Technology Co., "      \
  "Ltd.\",\"device_type\":\"cxl\",\"pci_address\":\"4c:00.0\"},{\"NUMA " \
  "node\":\"0\",\"device_manufacturer\":\"Samsung Electronics Co "       \
  "Ltd\",\"device_type\":\"nvme\",\"pci_address\":\"6e:00.0\"},{\"NUMA " \
  "node\":\"0\",\"device_manufacturer\":\"Samsung Electronics Co "       \
  "Ltd\",\"device_type\":\"nvme\",\"pci_address\":\"6f:00.0\"},{\"NUMA " \
  "node\":\"1\",\"device_manufacturer\":\"Montage Technology Co., "      \
  "Ltd.\",\"device_type\":\"cxl\",\"pci_address\":\"b8:00.0\"}]}"

#define NODE_DEVICE_FEATURE_OUTPUT                                             \
  "{\"device-info\":{\"XYZ-ABC\":{\"device_id\":0,\"serial_number\":\"XYZ-"    \
  "ABC\",\"numa_node\":0,\"total_capacity_MB\":409600,\"available_capacity_"   \
  "MB\":204800, "                                                              \
  "\"vendor_device_type\":\"DRAM\",\"status\":\"online\",\"advertised_qos\":{" \
  "\"avg_latency_ns\":200,\"p99_latency_ns\":100,\"io_per_sec\":1000000,\"BW_" \
  "per_sec\":1000,\"io_size_in_bytes\":4096,\"qd\":32}}}}"

#define NODE_EMPTY_DEVICE_FEATURE_OUTPUT "{\"device-info\":{}}"
#define NODE_INVALID_DEVICE_FEATURE_OUTPUT \
  "{\"device-info\":\"dummy-failure-value\"}"

#define NODE_FEATURE_STATS_OUTPUT                                          \
  "{\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{\"available_memory_" \
  "mb\":10663},\"node_name\":\"node_1\"}}"

#define CXL_DEVICE_LIST_OUTPUT                                                \
  "{\"devices\":[{\"device_id\":29690035288064,\"vendor_device_type\":\"CMM-" \
  "D\",\"pcie_addr\":\"0000:b8:00.0\"}, "                                     \
  "{\"device_id\":30690035288064,\"vendor_device_type\":\"CMM-"               \
  "D\",\"pcie_addr\":\"0000:b8:00.0\"}]}"

#define CXL_DEVICE_LIST_OUTPUT_WITH_ONE_DEVICE                                \
  "{\"devices\":[{\"device_id\":29690035288064,\"vendor_device_type\":\"CMM-" \
  "D\",\"pcie_addr\":\"0000:b8:00.0\"}]}"

#define CXL_DEVICE_INFO_OUTPUT1                                                \
  "{\"api_version\":1.0,\"device_id\":29690035288064,\"manufacturer\":"        \
  "\"Samsung\",\"serial_number\":305419896,\"FW_revision\":\"1.0.0\","         \
  "\"location\":\"0000:b8:00.0\",\"total_capacity_MB\":129007,\"feature_"      \
  "supported\":\"basic\",\"vendor_device_type\":\"CMM-D\",\"cxl_device_"       \
  "type\":\"Type3\",\"protocol\":\"CXL "                                       \
  "2.0\",\"port_type\":\"root\",\"mode_discovered\":\"auto\",\"connection_"    \
  "type\":\"CXL.mem\",\"domain_type\":\"PCIe\",\"domain_id\":0,\"link_"        \
  "speed\":16,\"link_width\":8,\"available_capacity_MB\":127080,\"status\":"   \
  "\"active\",\"aspm_active\":false,\"sris_active\":false,\"lock_active\":"    \
  "false,\"numa_node\":1,\"capabilities\":{\"Power Management "                \
  "version\":1},\"advertised_qos\":{\"avg_latency_ns\":1200,\"p99_latency_"    \
  "ns\":350,\"io_per_sec\":50000,\"BW_per_sec\":1000000,\"io_size_in_bytes\":" \
  "4096,\"qd\":32}}"

#define CXL_DEVICE_INFO_OUTPUT2                                                \
  "{\"api_version\":1.0,\"device_id\":30690035288064,\"manufacturer\":"        \
  "\"Samsung\",\"serial_number\":305419896,\"FW_revision\":\"1.0.0\","         \
  "\"location\":\"0000:b8:00.0\",\"total_capacity_MB\":129007,\"feature_"      \
  "supported\":\"basic\",\"vendor_device_type\":\"CMM-H\",\"cxl_device_"       \
  "type\":\"Type3\",\"protocol\":\"CXL "                                       \
  "2.0\",\"port_type\":\"root\",\"mode_discovered\":\"auto\",\"connection_"    \
  "type\":\"CXL.mem\",\"domain_type\":\"PCIe\",\"domain_id\":0,\"link_"        \
  "speed\":16,\"link_width\":8,\"available_capacity_MB\":127080,\"status\":"   \
  "\"active\",\"aspm_active\":false,\"sris_active\":false,\"lock_active\":"    \
  "false,\"numa_node\":2,\"capabilities\":{\"Power Management "                \
  "version\":1},\"advertised_qos\":{\"avg_latency_ns\":3200,\"p99_latency_"    \
  "ns\":350,\"io_per_sec\":50000,\"BW_per_sec\":1000000,\"io_size_in_bytes\":" \
  "4096,\"qd\":32}}"

class FakeNodeServicer : public Servicer {
 public:
  FakeNodeServicer(std::string conf_file) : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();
      if (req->command_name() == "get_node_info") {
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_DEVICE_FEATURE_OUTPUT);
        }
        if (req->command_params().find("stats") != std::string::npos) {
          response->set_output(NODE_FEATURE_STATS_OUTPUT);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        response->set_output(CXL_DEVICE_LIST_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        if (req->command_params().find("29690035288064") != std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT1);
        } else if (req->command_params().find("30690035288064") !=
                   std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT2);
        } else {
          response->set_output("FakeProcessNodeCommandSuccess");
        }

        response->set_node_id(req->node_id());
        return Status::OK;
      }
      response->set_output("FakeProcessNodeCommandSuccess");
    }
    std::cout << "FakeProcessNodeCommand called for the command "
              << req->command_name() << std::endl;

    return Status::OK;
  }
};

TEST(InitIntegrationTest, AllocateMemorySuccessWithFakeProcessNodeCommand) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1000;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest,
     ProcessControllerCommandForAllocateMemoryFailureWithZeroDevicesSLAMet) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params("sla_latency_ns=50;app_name=TestApp;size=1024");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ControllerNodeServicerStartWithSLAEvent) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }
  Servicer *n_svcr(new FakeNodeServicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(10);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1200;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);

  std::string json_data_str = get_sla_deviation_data(
      SLAT_FEATURE_MODULE_NAME, "1", "localhost", "TestApp", 2000);
  rc = publish_event_data_to_core((char *)"alerts",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());
  std::cout << "Published data result successfully" << std::endl;
  sleep(2);

  // Receive the events and check for SLA event as well as Auto tier event from
  // controller itself
  svk::EventRequest event_req;
  Status event_status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  event_req.set_command_name("cluster_events");

  event_status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(event_status.ok(), true);
  std::cout << "event response is " << event_resp->response() << std::endl;
  EXPECT_NE(std::string::npos,
            event_resp->response().find("Downgraded SLA detected"));

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            filedata.find(
                "Device name localhost_1 on host localhost for the app TestApp "
                "deviated than expected - Reported latency_ns = 2000") !=
                std::string::npos);

  unlink(conf_file.c_str());
}

class FakeNodeServicerForTM : public Servicer {
 public:
  FakeNodeServicerForTM(std::string conf_file) : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      if (req->command_name() == "get_node_info") {
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_DEVICE_FEATURE_OUTPUT);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        response->set_output(CXL_DEVICE_LIST_OUTPUT_WITH_ONE_DEVICE);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        if (req->command_params().find("29690035288064") != std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT1);
        } else if (req->command_params().find("30690035288064") !=
                   std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT2);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }

    std::string command_name =
        req->command_name().length() ? req->command_name() : "";
    if (command_name == "StartTuning") {
      std::cout
          << "FakeProcessNodeCommand called for the command StartTuning with "
          << req->command_params() << std::endl;
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();
      response->set_output("{status = \"0\"}");
    } else if (command_name == "move") {
      std::cout << "FakeProcessNodeCommand called for the command move with "
                << req->command_params() << std::endl;
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();
      response->set_output("{status = \"0\"}");
    }

    return Status::OK;
  }
};

TEST(InitIntegrationTest, ControllerNodeDuplicateDevices) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);

  Servicer *n_svcr(new FakeNodeServicerForTM(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }

  // Register the node with the controller
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  // delete c_svcr;
  delete n_svcr;

  Servicer *n_svcr2(new FakeNodeServicerForTM(conf_file));
  if (n_svcr2->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  // Register the same node again with the controller  to check duplicate device
  // validation
  auto n_server2 = InitializeNodeServicer(n_svcr2);
  ASSERT_NE(n_server2, nullptr);

  delete c_svcr;
  delete n_svcr2;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, filedata.find(
                      "Device id <localhost_0> from node localhost is added "
                      "to controller device map.") != std::string::npos);
  EXPECT_EQ(true, filedata.find(
                      "Device id <localhost_1> from node localhost is added "
                      "to controller device map.") != std::string::npos);
  EXPECT_EQ(true,
            filedata.find("Device id <localhost_0> has already been added to "
                          "controller device map") != std::string::npos);
  EXPECT_EQ(true,
            filedata.find("Device id <localhost_1> has already been added to "
                          "controller device map") != std::string::npos);
  unlink(conf_file.c_str());
}

class FakeNodeServicerWithoutCXLDevices : public Servicer {
 public:
  FakeNodeServicerWithoutCXLDevices(std::string conf_file)
      : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      if (req->command_name() == "get_node_info") {
        std::string output = NODE_PCI_FEATURE_OUTPUT;

        // Replace all cxl strings with some dummy so that there are no CXL
        // devices
        output = std::regex_replace(
            output, std::regex("cxl", std::regex_constants::icase), "test");
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(output);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_DEVICE_FEATURE_OUTPUT);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }
    std::cout << "FakeNodeServicerWithoutCXLDevices called for the command "
              << req->feature_params() << std::endl;
    return Status(grpc::INVALID_ARGUMENT, "Should not land here");
  }
};

TEST(InitIntegrationTest, AllocateMemoryFailureWithoutCXLDevices) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicerWithoutCXLDevices(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1000;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

class FakeNodeServicerInvalidCXLDeviceList : public Servicer {
 public:
  FakeNodeServicerInvalidCXLDeviceList(std::string conf_file)
      : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      if (req->command_name() == "get_node_info") {
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_INVALID_DEVICE_FEATURE_OUTPUT);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        response->set_output("{\"devices\": \"xyz\"}");
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        if (req->command_params().find("29690035288064") != std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT1);
        } else if (req->command_params().find("30690035288064") !=
                   std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT2);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }

    std::string feature_params =
        req->feature_params().length() ? req->feature_params() : "";
    std::cout << "FakeProcessNodeCommand called for the command "
              << feature_params << std::endl;
    if (feature_params.find("StartTuning") != std::string::npos) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      response->set_output("{status = \"0\"}");
    }
    return Status::OK;
  }
};

TEST(InitIntegrationTest, AllocateMemoryFailureInvalidCXLDeviceList) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicerInvalidCXLDeviceList(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1000;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

class FakeNodeServicerInvalidCXLDeviceInfo : public Servicer {
 public:
  FakeNodeServicerInvalidCXLDeviceInfo(std::string conf_file)
      : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      if (req->command_name() == "get_node_info") {
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_INVALID_DEVICE_FEATURE_OUTPUT);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        response->set_output(CXL_DEVICE_LIST_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        // Sending empty data as if it is invalid
        response->set_output("{}");
        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }

    std::string feature_params =
        req->feature_params().length() ? req->feature_params() : "";
    std::cout << "FakeProcessNodeCommand called for the command "
              << feature_params << std::endl;
    if (feature_params.find("StartTuning") != std::string::npos) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      response->set_output("{status = \"0\"}");
    }
    return Status::OK;
  }
};

TEST(InitIntegrationTest, AllocateMemoryFailureInvalidCXLDeviceInfo) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicerInvalidCXLDeviceInfo(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1000;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, SLATheadForTMWithMissingData) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  Servicer *n_svcr(new Servicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(5);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  // Remove observations section from the SLA event and ProcessSLAEvent should
  // return parse error
  std::string json_data_str = get_sla_deviation_data(
      SLAT_FEATURE_MODULE_NAME, "DEV11", "localhost1", "TESTAPP1", 1000);
  json json_data = json::parse(json_data_str);
  json json_data_orig = json_data;
  json_data.erase("observations");
  json_data_str = json_data.dump();
  rc = publish_event_data_to_core((char *)"alerts",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());
  sleep(1);

  std::cout << "Published data result " << rc << std::endl;
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Parse json data error in ProcessSLAEvent"));

  // Remove observations section from the RAS event and ProcessRASEvent should
  // return parse error
  json_data["feature_name"] = RAS_FEATURE_MODULE_NAME;
  json_data_str = json_data.dump();
  rc = publish_event_data_to_core((char *)"alerts",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  sleep(1);
  std::cout << "Published data result " << rc << std::endl;
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Parse json data error in ProcessRASEvent"));

  // Make the node_name in the event_header to empty so that the insert_event
  // into controller's memory fails
  json event_data = json();
  event_data["event_header"] = json();
  event_data["event_header"]["cluster_name"] = "CL_ID_1";
  event_data["event_header"]["node_name"] = "";
  event_data["event_payload"] = json_data_orig;
  std::string event_data_str = event_data.dump();
  rc = publish_data((char *)"alerts", (uint8_t *)event_data_str.c_str(),
                    event_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  EXPECT_EQ(
      true,
      is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                    "Failed to insert the event because of missing node name"));

  // Event payload missing
  event_data["event_header"]["node_name"] = "localhost";
  event_data.erase("event_payload");

  event_data_str = event_data.dump();
  rc = publish_data((char *)"alerts", (uint8_t *)event_data_str.c_str(),
                    event_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "Event data not per observability spec - event_payload missing"));

  json_data_str = "dummyjson=true";
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Parse error for zmq data"));

  sleep(1);

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, PublishDataWithUnregisteredTopic) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);
  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  Servicer *n_svcr(new Servicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(5);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  // This event should not be published in the log
  std::string json_data_str = get_sla_deviation_data(
      "unregistered", "DEV11", "localhost1", "UNREGISTERED_APP", 1000);
  rc = publish_event_data_to_core((char *)"unregistered_alert",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(2);

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(
      false,
      filedata.find(
          "Device's numa DEV11 on host localhost1 for the app UNREGISTERED_APP "
          "deviated than expected - Reported latency_ns = 1000") !=
          std::string::npos);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, SendingEventWithUnregisteredMetric) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  Servicer *n_svcr(new Servicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(5);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  // This event should be published in the log
  std::string json_data_str =
      get_sla_deviation_data("dummyfeature", "DEVFeatureNotHandled",
                             "localhost1", "REGISTERED_APP", 1000);
  rc = publish_event_data_to_core((char *)"metrics  ",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(2);

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);

  sla_thread->join();
  subscriber_thread->join();

  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();

  EXPECT_EQ(
      false,
      filedata.find(
          "Device name localhost1_DEVFeatureNotHandled on host localhost1 "
          "for the app REGISTERED_APP "
          "deviated than expected - Reported latency_ns = 1000") !=
          std::string::npos);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ControllerNodeManualServicerStartForRASOperation) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Add pubsub section
  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  sleep(1);
  Servicer *n_svcr(new FakeNodeServicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status;

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1500;app_name=TESTAPPRAS;size=1024;logic_module=default");

  status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);

  sleep(2);

  std::string json_data_str = generate_ras_event(
      RAS_FEATURE_MODULE_NAME, "1", "localhost", "TESTAPPRAS", 2000);
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(2);

  // Generate another event such that no replacement drive available
  json_data_str = generate_ras_event(RAS_FEATURE_MODULE_NAME, "0", "localhost",
                                     "TESTAPPRAS", 2000);
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(2);

  // Receive the events and check for SLA event as well as data migration event
  // from controller itself
  svk::EventRequest event_req;
  Status event_status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  event_req.set_command_name("cluster_events");

  event_status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(event_status.ok(), true);
  std::cout << "event response is " << event_resp->response() << std::endl;
  EXPECT_NE(std::string::npos,
            event_resp->response().find(
                "Initiated data migration for the app TESTAPPRAS from the "
                "NUMA node 1 to NUMA node 0"));
  // Another event related to no replacement drive should be present
  EXPECT_NE(std::string::npos, event_resp->response().find(
                                   "Replacement device not found for device id "
                                   "localhost_0 to initiate move_all"));

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  EXPECT_EQ(true, is_str_in_log(
                      CONTROLLER_NODE_DEFAULT_LOG_FILE,
                      "Enable RAS tracking with params "
                      "{\"configure_options\":{\"error_count_threshold\":5},"
                      "\"device_id\":\"localhost_1\",\"device_numa\":1,"
                      "\"device_type\":\"CMM-D\"}"));

  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Device localhost_1 on host "
                                "localhost for the app TESTAPPRAS "
                                "reported the error cnt = 2000"));

  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Disabled RAS tracking on device localhost_1"));

  // Since there is app_pid in the output, we need to split to two parts to
  // validate the output
  EXPECT_EQ(
      true,
      is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                    "Send command to the node with command_name: move_all and "
                    "command_params: "
                    "{\"app\":\"TESTAPPRAS\""));

  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                ",\"command\":\"move_"
                                "all\",\"dst\":\"0\",\"src\":\"1\",\"tm_attr\":"
                                "\"0\"} is successful"));

  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "device localhost_1on node localhost with numa 1 is marked faulty"));

  EXPECT_EQ(
      true,
      is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                    "replacement device not found for device id localhost_0"));
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, IntegrationTestRASOperationWithoutApp) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Add pubsub section
  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  sleep(1);
  Servicer *n_svcr(new FakeNodeServicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(2);

  std::string json_data_str = generate_ras_event(
      RAS_FEATURE_MODULE_NAME, "1", "localhost", "NOAPPFORRAS", 2000);
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(2);

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  EXPECT_EQ(true, is_str_in_log(
                      CONTROLLER_NODE_DEFAULT_LOG_FILE,
                      "Enable RAS tracking with params "
                      "{\"configure_options\":{\"error_count_threshold\":5},"
                      "\"device_id\":\"localhost_1\",\"device_numa\":1,"
                      "\"device_type\":\"CMM-D\"}"));

  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Device localhost_1 on host "
                                "localhost for the app  "
                                "reported the error cnt = 2000"));

  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Disabled RAS tracking on device localhost_1"));

  // Since there is no app for the device, there shoud not be move_all command
  // initiation log
  EXPECT_NE(
      true,
      is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                    "Send command to the node with command_name: move_all and "
                    "command_params: {\"app\":\"NOAPPFORRAS\""));

  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "device localhost_1on node localhost with numa 1 is marked faulty"));

  unlink(conf_file.c_str());
}

class FakeNodeServicerFailForAddRemoveSLADeviceTracker : public Servicer {
 public:
  FakeNodeServicerFailForAddRemoveSLADeviceTracker(std::string conf_file,
                                                   bool sla_add_fail)
      : Servicer(conf_file) {
    this->sla_add_fail = sla_add_fail;
  };
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      if (this->sla_add_fail == true &&
          req->command_name() == "add_devices_to_sla_tracker") {
        return Status(grpc::INVALID_ARGUMENT,
                      "add_devices_to_sla_tracker failed");
      } else if (this->sla_add_fail == false &&
                 req->command_name() == "remove_devices_from_sla_tracker") {
        return Status(grpc::INVALID_ARGUMENT,
                      "remove_devices_from_sla_tracker failed");
      }

      if (req->command_name() == "get_node_info") {
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_DEVICE_FEATURE_OUTPUT);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        response->set_output(CXL_DEVICE_LIST_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        if (req->command_params().find("29690035288064") != std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT1);
        } else if (req->command_params().find("30690035288064") !=
                   std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT2);
        }

        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }

    return Status::OK;
  }

 private:
  // Flag to simulate failure for add_device_to_sla_tracker or
  // remove_device_from_sla_tracker
  bool sla_add_fail;
};

// The node service FakeNodeServicerFailForAddRemoveSLADeviceTracker fails the
// call coming with remove_device_from_sla_tracking

TEST(InitIntegrationTest, AllocateMemoryCommandWithAddSLADeviceTrackerFailure) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(
      new FakeNodeServicerFailForAddRemoveSLADeviceTracker(conf_file, true));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1000;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_NE(status.ok(), true);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ControllerNodeTMOperationWithRemoveSLADeviceFailure) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }
  Servicer *n_svcr(
      new FakeNodeServicerFailForAddRemoveSLADeviceTracker(conf_file, false));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=1500;app_name=TESTAPPRAS;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);
  sleep(5);

  std::string json_data_str = generate_ras_event(
      RAS_FEATURE_MODULE_NAME, "1", "localhost", "TESTAPPRAS", 2000);

  rc = publish_event_data_to_core((char *)"alerts",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(3);

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, filedata.find("Disabled SLA tracking on device 1") !=
                      std::string::npos);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ControllerNodeServicerWithEventValidation) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Add pubsub section
  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }

  std::thread server_thr(StartServer, conf_file, true);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  sleep(1);
  Servicer *n_svcr(new FakeNodeServicerForTM(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  svk::RegisterRequest reg_req;
  svk::RegisterResponse reg_resp;
  svk::EventRequest event_req;
  Status status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  event_req.set_command_name("cluster_events");
  event_req.set_command_params("{}");

  status = client.EventAPI(&event_req, event_resp);
  std::cout << "Error message - " << status.error_message() << std::endl;
  ASSERT_EQ(status.ok(), true);
  std::string expected_resp_str = "[]";
  std::cout << "Event response - " << event_resp->response() << std::endl;
  ASSERT_EQ(event_resp->response(), expected_resp_str);

  reg_req.set_cluster_name("RASCluster1");
  reg_req.set_node_name("testnode");
  reg_req.set_node_ip("127.0.0.1");
  reg_req.set_node_port("9998");

  status = client.RegisterNode(&reg_req, &reg_resp);
  ASSERT_TRUE(status.ok());

  std::string json_data_str =
      "{\"category\":\"test_feature\","
      "\"domain\":\"observability\",\"feature_name\":\"test_feature\","
      "\"observations\":{\"device_id\":\"29690035288064\",\"error_cnt\":2000,"
      "\"feature_name\":\"test_feature\",\"message\":\"Device RAS error count "
      "hit the "
      "threshold\"},\"severity\":\"warning\",\"source\":\"node\",\"source_"
      "type\":\"localhost\",\"timestamp\":1234567890}";
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(5);

  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  expected_resp_str =
      "[{\"event_header\":{\"cluster_name\":\"CL_ID_1\",\"node_name\":"
      "\"localhost\"},\"event_payload\":{\"category\":\"test_feature\","
      "\"domain\":\"observability\",\"feature_name\":\"test_feature\","
      "\"observations\":{\"device_id\":\"29690035288064\",\"error_cnt\":2000,"
      "\"feature_name\":\"test_feature\",\"message\":\"Device RAS error count "
      "hit the "
      "threshold\"},\"severity\":\"warning\",\"source\":\"node\",\"source_"
      "type\":\"localhost\",\"timestamp\":1234567890}}]";
  std::cout << "Event response - " << event_resp->response() << std::endl;
  ASSERT_EQ(event_resp->response(), expected_resp_str);

  // Prior cluster events should not clear the list. Check whether the list is
  // intact.
  event_req.set_command_name("cluster_events");
  status = client.EventAPI(&event_req, event_resp);
  std::cout << "Error message - " << status.error_message() << std::endl;
  ASSERT_EQ(status.ok(), true);
  std::cout << "Event response - " << event_resp->response() << std::endl;
  ASSERT_EQ(event_resp->response(), expected_resp_str);

  // Clear the events explicitly and check the list is empty
  event_req.set_command_name("clear_events");

  status = client.EventAPI(&event_req, event_resp);
  std::cout << "Error message - " << status.error_message() << std::endl;
  ASSERT_EQ(status.ok(), true);
  expected_resp_str = "";
  std::cout << "Event response - " << event_resp->response() << std::endl;
  ASSERT_EQ(event_resp->response(), expected_resp_str);

  delete n_svcr;
  cleanup_publisher();

  std::thread::id ctrlr_thread_id = server_thr.get_id();

  auto ctrlr_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&ctrlr_thread_id);

  pthread_kill(ctrlr_native_handle, SIGINT);
  server_thr.join();

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, EventAPITests) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Add pubsub section
  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }
  std::thread server_thr(StartServer, conf_file, true);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }

  sleep(1);
  Servicer *n_svcr(new FakeNodeServicerForTM(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  svk::RegisterRequest reg_req;
  svk::RegisterResponse reg_resp;
  svk::EventRequest event_req;
  Status status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  json command_params_json;

  // Clear the old events if any
  event_req.set_command_name("clear_events");
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);

  reg_req.set_cluster_name("RASCluster1");
  reg_req.set_node_name("testnode");
  reg_req.set_node_ip("127.0.0.1");
  reg_req.set_node_port("9998");

  status = client.RegisterNode(&reg_req, &reg_resp);
  ASSERT_TRUE(status.ok());

  std::string json_data_str =
      "{\"category\":\"test_feature\","
      "\"domain\":\"observability\",\"feature_name\":\"test_feature\","
      "\"observations\":{\"device_id\":\"29690035288064\",\"error_cnt\":2000,"
      "\"feature_name\":\"test_feature\",\"message\":\"Device RAS error count "
      "hit the "
      "threshold\"},\"severity\":\"warning\",\"source\":\"node\",\"source_"
      "type\":\"localhost\",\"timestamp\":1234567890}";
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;

  // Create another event with later timestamp
  json_data_str =
      "{\"category\":\"test_feature\","
      "\"domain\":\"observability\",\"feature_name\":\"test_feature\","
      "\"observations\":{\"device_id\":\"29690035288064\",\"error_cnt\":2000,"
      "\"feature_name\":\"test_feature\",\"message\":\"Device RAS error count "
      "hit the "
      "threshold\"},\"severity\":\"warning\",\"source\":\"node\",\"source_"
      "type\":\"localhost\",\"timestamp\":1234567900}";
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(5);

  event_req.set_command_name("cluster_events");
  event_req.set_command_params("{}");
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  std::string resp_str = event_resp->response();
  std::cout << "All cluster events - Event response - " << resp_str
            << std::endl;
  json resp_json = json::parse(resp_str);
  // In the docker, the events are getting replicated (inconsistently) causing
  // the total events doubled sometimes and fail the checks
  ASSERT_GE(resp_json.size(), 2);

  // Get just 1 event rather than all.
  event_req.set_command_name("cluster_events");
  command_params_json.clear();
  command_params_json["event_count"] = 1;
  event_req.set_command_params(command_params_json.dump());
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  resp_str = event_resp->response();
  std::cout << "1 Cluster event - Event response - " << resp_str << std::endl;
  resp_json = json::parse(resp_str);
  ASSERT_GE(resp_json.size(), 1);

  // Call again. Prior cluster events should not be cleared. Check whether the
  // list is intact.
  event_req.set_cluster_name("CL_ID_1");
  event_req.set_node_name("localhost");
  command_params_json.clear();
  // Set a time later than the first event
  command_params_json["min_timestamp"] = 1234567891;
  event_req.set_command_params(command_params_json.dump());
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "Minimum timestamp - Event response - " << event_resp->response()
            << std::endl;
  resp_str = event_resp->response();
  resp_json = json::parse(resp_str);
  ASSERT_GE(resp_json.size(), 1);

  // Call with invalid cluster name
  event_req.set_cluster_name("CL_ID_2");
  event_req.set_node_name("localhost");
  event_req.clear_command_params();
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "Invalid cluster name - Event response - "
            << event_resp->response() << std::endl;
  resp_str = event_resp->response();
  resp_json = json::parse(resp_str);
  ASSERT_EQ(resp_json.size(), 0);

  // Call with invalid node name
  event_req.set_cluster_name("CL_ID_1");
  event_req.set_node_name("localhost2");
  event_req.clear_command_params();
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "Invalid node naem - Event response - " << event_resp->response()
            << std::endl;
  resp_str = event_resp->response();
  resp_json = json::parse(resp_str);
  ASSERT_EQ(resp_json.size(), 0);

  // Call with timestamp later than the last event
  event_req.set_cluster_name("CL_ID_1");
  event_req.set_node_name("localhost");
  command_params_json["min_timestamp"] = 1234567901;

  event_req.set_command_params(command_params_json.dump());
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "Event response - " << event_resp->response() << std::endl;
  resp_str = event_resp->response();
  resp_json = json::parse(resp_str);
  ASSERT_EQ(resp_json.size(), 0);

  // Call with invalid json of command params
  event_req.set_cluster_name("CL_ID_1");
  event_req.set_node_name("localhost");

  event_req.set_command_params("invalid_data_not_json_format");
  status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(status.ok(), false);

  delete n_svcr;
  cleanup_publisher();
  std::thread::id ctrlr_thread_id = server_thr.get_id();

  auto ctrlr_native_handle =
      *reinterpret_cast<std::thread::native_handle_type *>(&ctrlr_thread_id);

  pthread_kill(ctrlr_native_handle, SIGINT);
  server_thr.join();

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ControllerNodeServicerWithInvalidEventCommand) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Add pubsub section
  std::ifstream in_file(conf_file);
  std::string conf_data((std::istreambuf_iterator<char>(in_file)),
                        (std::istreambuf_iterator<char>()));
  in_file.close();
  json json_data = json::parse(conf_data);
  json_data["pubsub"] = {{"ip_address", "127.0.0.1"},
                         {"port", 5555},
                         {"topics", {"metrics", "events", "alerts"}},
                         {"transport_type", "zmq"}};

  conf_data = json_data.dump();
  std::ofstream out_file(conf_file);
  if (out_file.is_open()) {
    out_file << conf_data;
    out_file.close();
  }

  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  svk::RegisterRequest reg_req;
  svk::RegisterResponse reg_resp;
  svk::EventRequest event_req;
  Status status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  event_req.set_command_name("cluster_events_invalid_command");

  status = client.EventAPI(&event_req, event_resp);
  std::cout << "Error message - " << status.error_message() << std::endl;
  ASSERT_NE(status.ok(), true);
}

class FakeNodeServicerForFailureScenarios : public Servicer {
 public:
  FakeNodeServicerForFailureScenarios(std::string conf_file,
                                      std::string failure_string)
      : Servicer(conf_file) {
    m_failure_string = failure_string;
  };
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();

      if (req->command_name() == "get_node_info") {
        if (m_failure_string == "get_node_info=fail") {
          return Status(grpc::UNKNOWN, "get-node-info failed");
        }
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          std::string device_output = NODE_DEVICE_FEATURE_OUTPUT;
          // Set the total capacity of the DRAM devices to 200MB so that the
          // value can be used to simulate failure easily
          std::string replacement_str = "\"total_capacity_MB\":409600";
          size_t pos = device_output.find(replacement_str);
          if (pos != std::string::npos)
            device_output.replace(device_output.find(replacement_str),
                                  replacement_str.length(),
                                  "\"total_capacity_MB\":200");

          replacement_str = "\"available_capacity_MB\":204800";
          pos = device_output.find(replacement_str);
          if (pos != std::string::npos)
            device_output.replace(device_output.find(replacement_str),
                                  replacement_str.length(),
                                  "\"available_capacity_MB\":200");
          response->set_output(device_output);
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        if (m_failure_string == "list_devices=fail") {
          return Status(grpc::UNKNOWN, "list_devices failed");
        }
        response->set_output(CXL_DEVICE_LIST_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        if (m_failure_string == "get_device_info=fail") {
          return Status(grpc::UNKNOWN, "get_device_info failed");
        }
        if (req->command_params().find("29690035288064") != std::string::npos) {
          std::string device_output = CXL_DEVICE_INFO_OUTPUT1;
          if (m_failure_string == "device_id_faking") {
            std::string replacement_str = "\"device_id\":29690035288064";
            size_t pos = device_output.find(replacement_str);
            std::cout << "POS " << pos << std::endl;
            if (pos != std::string::npos)
              device_output.replace(pos, replacement_str.length(),
                                    "\"device_id\":12345678901234567890");
            std::cout << "Device OUTPUT " << device_output << std::endl;
          } else {
            // Set the total capacity of the DRAM devices to 200MB so that the
            // value can be used to simulate failure easily
            std::string replacement_str = "\"total_capacity_MB\":129007";
            size_t pos = device_output.find(replacement_str);
            if (pos != std::string::npos)
              device_output.replace(pos, replacement_str.length(),
                                    "\"total_capacity_MB\":200");

            replacement_str = "\"available_capacity_MB\":127080";
            pos = device_output.find(replacement_str);
            if (pos != std::string::npos)
              device_output.replace(device_output.find(replacement_str),
                                    replacement_str.length(),
                                    "\"available_capacity_MB\":200");
          }
          response->set_output(device_output);
        } else if (req->command_params().find("30690035288064") !=
                   std::string::npos) {
          std::string device_output = CXL_DEVICE_INFO_OUTPUT2;
          // Set the total capacity of the DRAM devices to 200MB so that the
          // value can be used to simulate failure easily
          std::string replacement_str = "\"total_capacity_MB\":129007";
          size_t pos = device_output.find(replacement_str);
          if (pos != std::string::npos)
            device_output.replace(device_output.find(replacement_str),
                                  replacement_str.length(),
                                  "\"total_capacity_MB\":200");
          replacement_str = "\"available_capacity_MB\":127080";
          pos = device_output.find(replacement_str);
          if (pos != std::string::npos)
            device_output.replace(device_output.find(replacement_str),
                                  replacement_str.length(),
                                  "\"available_capacity_MB\":200");

          response->set_output(device_output);
        }

        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }
    std::cout << "FakeNodeServicerForFailureScenarios called for the command "
              << req->command_name() << std::endl;
    return Status::OK;
  };

 private:
  std::string m_failure_string;
};

TEST(InitIntegrationTest, AllocateMemoryGetDeviceInfoFailure1) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Simulate the DRAM device failure by returning errors for get_node_info call
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, "get_node_info=fail"));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=500;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, AllocateMemoryGetDeviceInfoFailure2) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Simulate the CXL device failure by returning errors for list_devices call
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, "list_devices=fail"));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=500;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, AllocateMemoryGetDeviceInfoFailure3) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Simulate the CXL device failure by returning error for get_device_info call
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file,
                                              "get_device_info=fail"));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=500;app_name=TestApp;size=200;logic_module=default");

  // Since the DRAM device is there, the allocate_memory call should succeed
  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), true);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, AllocateMemoryGetDeviceInfoWithExtraLargeCapacity) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Simulate the CXL device failure by faking the device id
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, ""));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_cluster_id(DEFAULT_CLUSTER_ID);
  req.set_command_id("allocate_memory");
  req.set_feature_params(
      "sla_latency_ns=4500;app_name=TestApp;size=1024;logic_module=default");

  // Since the 3 device total capacity is 600MB, the allocate_memory call should
  // fail
  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "device localhost_0 with numa 0 and latency "
                                "200 added to the list for consumption"));
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "device localhost_1 with numa 1 and latency "
                                "1200 added to the list for consumption"));
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "device localhost_2 with numa 2 and latency "
                                "3200 added to the list for consumption"));
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "No device found for the given latency or "
                                "enough free capacity available"));
}

TEST(InitIntegrationTest, GetDeviceLatencyRequirements) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, ""));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  std::vector<DeviceInfo> app_devices;
  std::vector<std::string> node_ips;
  node_ips.push_back("localhost");
  int status = g_sla_device_hlpr->GetDeviceForLatencyRequirements(
      4500, 500, node_ips, -1, app_devices);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(app_devices.size(), 3);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, GetDeviceLatencyRequirementsForInvalidHost) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, ""));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  std::vector<DeviceInfo> app_devices;
  std::vector<std::string> node_ips;
  node_ips.push_back("localhost1");
  int status = g_sla_device_hlpr->GetDeviceForLatencyRequirements(
      4500, 500, node_ips, -1, app_devices);

  EXPECT_EQ(status, -1);
  EXPECT_EQ(app_devices.size(), 0);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, UnregisterDevices) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, ""));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  // Unregister the devices for the node "localhost"
  int status = g_sla_device_hlpr->UnregisterDevicesForNode("localhost");
  EXPECT_EQ(status, 0);
  // Try to get all the devices to see if the device is still there
  std::vector<DeviceInfo> app_devices;
  std::vector<std::string> node_ips;
  node_ips.push_back("localhost");
  status = g_sla_device_hlpr->GetDeviceForLatencyRequirements(
      4500, 500, node_ips, -1, app_devices);

  EXPECT_EQ(status, -1);
  EXPECT_EQ(app_devices.size(), 0);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, UnregisterDevicesForInUseDevice) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, ""));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  // Get all the devices with the node "localhost"
  std::vector<DeviceInfo> app_devices;
  node_ips.push_back("localhost");
  int status = g_sla_device_hlpr->GetDeviceForLatencyRequirements(
      4500, 500, node_ips, -1, app_devices);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(app_devices.size(), 3);

  // Unregister the devices for the node "localhost"
  status = g_sla_device_hlpr->UnregisterDevicesForNode("localhost");
  EXPECT_EQ(status, 0);

  EXPECT_EQ(true,
            is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                          "device localhost_0 with numa 0 is still in use"));

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, UpdateDeviceStatus) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicerForFailureScenarios *svcr(
      new FakeNodeServicerForFailureScenarios(conf_file, ""));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  // Get all the devices with the node "localhost"
  std::vector<DeviceInfo> app_devices;
  node_ips.push_back("localhost");
  int status = g_sla_device_hlpr->GetDeviceForLatencyRequirements(
      4500, 500, node_ips, -1, app_devices);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(app_devices.size(), 3);

  // Unregister the devices for the node "localhost"
  status = g_sla_device_hlpr->UpdateAllDevicesWithStatus(
      "localhost", Device_Status_E::DEVICE_OFFLINE);
  EXPECT_EQ(status, 0);

  DeviceInfo dev;
  status = g_sla_device_hlpr->GetDeviceInfo("localhost_0", dev);
  EXPECT_TRUE(dev.internal_status == Device_Status_E::DEVICE_OFFLINE);

  // Expect the node is coming online with the devices marked as faulty.
  // Status should not change to online from faulty
  status = g_sla_device_hlpr->UpdateAllDevicesWithStatus(
      "localhost", Device_Status_E::DEVICE_FAULTY);
  EXPECT_EQ(status, 0);

  status = g_sla_device_hlpr->UpdateAllDevicesWithStatus(
      "localhost", Device_Status_E::DEVICE_ONLINE);
  EXPECT_EQ(status, 0);

  status = g_sla_device_hlpr->GetDeviceInfo("localhost_0", dev);
  EXPECT_TRUE(dev.internal_status == Device_Status_E::DEVICE_FAULTY);

  unlink(conf_file.c_str());
}

class SLAManagementServicer : public ControllerServicer {
 public:
  SLAManagementServicer(std::string conf_file)
      : ControllerServicer(conf_file){};

  Status SLAManagementServicer_SetAppSLACommand(
      const std::string &cluster_name, const std::string &node_name,
      const std::string &command_params_str, std::string &output) {
    return SetAppSLACommand(cluster_name, node_name, command_params_str,
                            output);
  };
};

TEST(SLAMgmtIntegration, SLAManagementAPIFailure) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  SLAManagementServicer *ctrl_svcr(new SLAManagementServicer(conf_file));
  ASSERT_FALSE(ctrl_svcr->get_state() == false);
  auto ctrl_server = InitializeServicer(ctrl_svcr);
  ASSERT_FALSE(ctrl_server == nullptr);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status;

  // Empty cluster/node name
  req.set_cluster_name("");
  req.set_node_name("");
  req.set_command_name("get_devices_with_sla_info");

  status = client.SLAManagementAPI(&req, &resp);
  ASSERT_NE(status.ok(), true);
  ASSERT_EQ(status.error_code(), grpc::INVALID_ARGUMENT);

  // Invalid node name
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name("invalid_host_name");
  req.set_command_name("get_devices_with_sla_info");

  status = client.SLAManagementAPI(&req, &resp);
  ASSERT_NE(status.ok(), true);
  ASSERT_EQ(status.error_code(), grpc::UNKNOWN);
  ASSERT_EQ(status.error_message(),
            "Invalid node name given - invalid_host_name");

  // Empty command
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name("localhost");
  req.set_command_name("");

  status = client.SLAManagementAPI(&req, &resp);
  ASSERT_NE(status.ok(), true);
  ASSERT_EQ(status.error_code(), grpc::INVALID_ARGUMENT);

  // Empty command params
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name("localhost");
  req.set_command_name("set_app_sla");

  status = client.SLAManagementAPI(&req, &resp);
  ASSERT_NE(status.ok(), true);
  ASSERT_EQ(status.error_code(), grpc::INVALID_ARGUMENT);

  // Provide empty node name
  std::string output;
  std::string command_params_str;
  status = ctrl_svcr->SLAManagementServicer_SetAppSLACommand(
      "cluster1", "", command_params_str, output);
  ASSERT_EQ(status.error_message(), "Empty node name provided");

  unlink(conf_file.c_str());
}

TEST(SLAMgmtIntegration, GetDevicesWithSLAInfo) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);

  req.set_command_name("get_devices_with_sla_info");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.SLAManagementAPI(&req, &resp);
  ASSERT_TRUE(status.ok());
  std::cout << "OUTPUT " << resp.response() << std::endl;
  json output = json::parse(resp.response());
  json devices = output["localhost"];
  ASSERT_EQ(output.size(), 1);
  ASSERT_EQ(devices.size(), 3);
  unlink(conf_file.c_str());
}

TEST(SLAMgmtIntegration, SetAppSLACommand) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  json command_params;

  command_params["app_name"] = "gemfire";
  command_params["app_pid"] = 987654321;
  command_params["app_total_data_set_MB"] = 4096;
  command_params["hot_data_size_MB"] = 2048;

  json qos_params;
  qos_params["avg_latency_ns"] = 2500;
  command_params["app_desired_qos"] = qos_params;

  json device;
  device["device_numa"] = "2";
  device["device_allocated_capacity_mb"] = 4096;
  json device_array = json::array();
  device_array.push_back(device);
  command_params["devices"] = device_array;

  std::cout << command_params.dump() << std::endl;

  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);
  req.set_command_name("set_app_sla");
  req.set_command_params(command_params.dump());

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  DeviceInfo dev_info_1;
  int status = g_sla_device_hlpr->GetDeviceInfo("localhost_2", dev_info_1);
  ASSERT_TRUE(status == 0);
  EXPECT_TRUE(dev_info_1.internal_status == Device_Status_E::DEVICE_ONLINE);

  Status cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_TRUE(cmd_status.ok());

  // Get the device info to check the allocated capacity is accounted properly
  DeviceInfo dev_info_2;
  status = g_sla_device_hlpr->GetDeviceInfo("localhost_2", dev_info_2);
  ASSERT_TRUE(status == 0);

  ASSERT_EQ(dev_info_2.allocated_capacity_mb,
            dev_info_1.allocated_capacity_mb + 4096);

  std::cout << "Response - " << resp.response() << std::endl;

  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "Command with command_params "
          "{\"app_name\":\"gemfire\",\"app_sla_latency_ns\":2500,\"devices\":[{"
          "\"device_id\":\"localhost_2\",\"device_numa\":\"2\",\"device_sla_"
          "latency_ns\":3200}],\"host_name\":\"localhost\",\"logic_module\":"
          "\"mlc\"} is passed to node localhost"));

  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "Enable RAS tracking with "
          "params "
          "{\"configure_options\":{\"error_count_threshold\":5},\"device_"
          "id\":\"localhost_2\",\"device_numa\":2,\"device_type\":\"CMM-H\"}"));

  unlink(conf_file.c_str());
}

TEST(SLAMgmtIntegration, SetAppSLACommandWithoutDeviceCapacity) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  json command_params;

  command_params["app_name"] = "gemfire";
  command_params["app_pid"] = 987654321;
  command_params["app_total_data_set_MB"] = 40960;

  json qos_params;
  qos_params["avg_latency_ns"] = 2500;
  command_params["app_desired_qos"] = qos_params;

  json device;
  device["device_numa"] = "2";
  json device_array = json::array();
  device_array.push_back(device);
  command_params["devices"] = device_array;

  std::cout << command_params.dump() << std::endl;

  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);
  req.set_command_name("set_app_sla");
  req.set_command_params(command_params.dump());

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  Status cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_TRUE(cmd_status.ok());

  // Get the device info to check the allocated capacity is accounted properly
  DeviceInfo dev_info;
  int status = g_sla_device_hlpr->GetDeviceInfo("localhost_2", dev_info);
  ASSERT_TRUE(status == 0);

  // Available capacity should be 0 since the whole device is consumed
  ASSERT_EQ(dev_info.available_capacity_mb, 0);

  std::cout << "Response - " << resp.response() << std::endl;

  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "Command with command_params "
          "{\"app_name\":\"gemfire\",\"app_sla_latency_ns\":2500,\"devices\":[{"
          "\"device_id\":\"localhost_2\",\"device_numa\":\"2\",\"device_sla_"
          "latency_ns\":3200}],\"host_name\":\"localhost\",\"logic_module\":"
          "\"mlc\"} is passed to node localhost"));

  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "Enable RAS tracking with "
          "params "
          "{\"configure_options\":{\"error_count_threshold\":5},\"device_"
          "id\":\"localhost_2\",\"device_numa\":2,\"device_type\":\"CMM-H\"}"));

  unlink(conf_file.c_str());
}

TEST(SLAMgmtIntegration, SetAppSLACommandFailureException) {
  char *cw_dir = get_current_dir_name();
  std::vector<std::string> node_ips;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  sleep(5);

  json command_params;
  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);
  req.set_command_name("set_app_sla");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status cmd_status;

  // App name not set. Should throw exception and return grpc::UNKNOWN
  command_params["app_pid"] = 987654321;
  command_params["app_total_data_set_MB"] = 4096;
  command_params["hot_data_size_MB"] = 2048;

  json qos_params;
  qos_params["avg_latency_ns"] = 2500;
  command_params["app_desired_qos"] = qos_params;

  json device;
  device["device_numa"] = "2";
  device["device_allocated_capacity_mb"] = 4096;
  json device_array = json::array();
  device_array.push_back(device);
  command_params["devices"] = device_array;
  req.set_command_params(command_params.dump());

  cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_EQ(cmd_status.error_code(), grpc::UNKNOWN);

  // Add the app name and make the device invalid
  command_params["app_name"] = "gemfire";
  device["device_numa"] = "100";  // Invalid device
  device["device_allocated_capacity_mb"] = 4096;
  device_array.push_back(device);
  command_params["devices"] = device_array;
  req.set_command_params(command_params.dump());
  cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_EQ(cmd_status.error_code(), grpc::UNKNOWN);
  ASSERT_EQ(cmd_status.error_message(),
            "Invalid device id provided - localhost_100");

  // Mark a device as faulty and should get a failure
  g_sla_device_hlpr->MarkTheDeviceFaulty("localhost_2");
  device["device_numa"] = "2";
  device["device_allocated_capacity_mb"] = 4096;
  device_array.clear();
  device_array.push_back(device);
  command_params["devices"] = device_array;
  req.set_command_params(command_params.dump());
  cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_EQ(cmd_status.error_code(), grpc::UNKNOWN);
  ASSERT_EQ(cmd_status.error_message(),
            "Device id provided - localhost_2 is invalid/faulty/offline");

  // Allocate device capacity more than the actual capacity
  device["device_numa"] = "0";
  device["device_allocated_capacity_mb"] = 409600000000000;
  device_array.clear();
  device_array.push_back(device);
  command_params["devices"] = device_array;
  req.set_command_params(command_params.dump());
  cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_EQ(cmd_status.error_code(), grpc::UNKNOWN);
  ASSERT_EQ(cmd_status.error_message(),
            "Device id provided - localhost_0 is allocated more than "
            "the available capacity");

  // Devices field is not an array
  command_params["devices"] = "localhost_0";
  req.set_command_params(command_params.dump());
  cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_EQ(cmd_status.error_code(), grpc::UNKNOWN);
  ASSERT_EQ(cmd_status.error_message(),
            "Device array is not provided in JSON input");

  // Empty device array
  device_array.clear();
  command_params["devices"] = device_array;
  req.set_command_params(command_params.dump());
  cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_EQ(cmd_status.error_code(), grpc::UNKNOWN);
  ASSERT_EQ(cmd_status.error_message(), "Device array is empty");

  unlink(conf_file.c_str());
}

TEST(SLAMgmtIntegration, AutoTieringValidationWithSLAMgmt) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Start mgmt controller
  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  EXPECT_EQ(rc, 0);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *n_svcr(new FakeNodeServicer(conf_file));
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);
  sleep(5);

  json command_params;

  command_params["app_name"] = "TESTAPPTM";
  command_params["app_pid"] = 987654321;
  command_params["app_total_data_set_MB"] = 4096;
  command_params["hot_data_size_MB"] = 2048;

  json qos_params;
  qos_params["avg_latency_ns"] = 2500;
  command_params["app_desired_qos"] = qos_params;

  json device;
  device["device_numa"] = "0";
  device["device_allocated_capacity_mb"] = 4096;
  json device_array = json::array();
  device_array.push_back(device);
  device["device_numa"] = "1";
  device["device_allocated_capacity_mb"] = 4096;
  device_array.push_back(device);

  command_params["devices"] = device_array;

  std::cout << command_params.dump() << std::endl;

  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);
  req.set_command_name("set_app_sla");
  req.set_command_params(command_params.dump());

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  Status cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_TRUE(cmd_status.ok());

  sleep(2);

  // Generate a SLA event that the deviation is detected
  std::string json_data_str = get_sla_deviation_data(
      SLAT_FEATURE_MODULE_NAME, "1", "localhost", "TESTAPPTM", 2500);
  rc = publish_event_data_to_core((char *)"alerts",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(3);

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  // Check the logs with the deviation detected
  EXPECT_EQ(
      true,
      filedata.find(
          "Device name localhost_1 on host localhost for the app TESTAPPTM "
          "deviated than expected - Reported latency_ns = 2500") !=
          std::string::npos);

  // A move command is initiated
  EXPECT_EQ(true,
            filedata.find("Send command to the node with command_name: move "
                          "and command_params: "
                          "{\"app\":\"TESTAPPTM\"") != std::string::npos);
  // Since the PID is part of the output, we need to break it into two separate
  // checks as the PID is dynamic Move command with the parameters are logged
  EXPECT_EQ(true,
            filedata.find("\"command\":\"move\",\"fast_tier\":\"0\",\"slow_"
                          "tier\":\"1\",\"tm_attr\":\"MOVER_AGGRESSIVENESS_"
                          "LOW\"} is successful") != std::string::npos);

  // Generate one more event. Now there should be no more devices to move
  // Generate a SLA event for the new device that the deviation is detected
  json_data_str = get_sla_deviation_data(SLAT_FEATURE_MODULE_NAME, "0",
                                         "localhost", "TESTAPPTM", 1700);
  rc = publish_event_data_to_core((char *)"alerts",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());
  std::cout << "Published data result " << rc << "one more time" << std::endl;
  sleep(3);

  // Check the logs with the deviation detected
  EXPECT_EQ(
      true,
      is_str_in_log(
          CONTROLLER_NODE_DEFAULT_LOG_FILE,
          "Device name localhost_0 on host localhost for the app TESTAPPTM "
          "deviated than expected - Reported latency_ns = 1700"));

  EXPECT_EQ(true,
            is_str_in_log(
                CONTROLLER_NODE_DEFAULT_LOG_FILE,
                "GetTieredDevice- Found app device for tiering localhost_0"));

  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "GetTieredDevice- No device found for tiering "
                                "of the given device localhost_0"));

  // Receive the events and check for SLA event as well as auto tiering event
  // from controller itself
  svk::EventRequest event_req;
  Status event_status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  event_req.set_command_name("cluster_events");

  event_status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(event_status.ok(), true);
  std::cout << "event response is " << event_resp->response() << std::endl;
  EXPECT_NE(std::string::npos,
            event_resp->response().find(
                "Initiated Auto-tiering for the app TESTAPPTM from the "
                "NUMA node 1 to NUMA node 0"));
  // Another event related to no equivalent drive found for auto tiering
  EXPECT_NE(std::string::npos,
            event_resp->response().find(
                "Equivalent tiered device not found for device id localhost_0 "
                "to initiate auto tiering"));

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  unlink(conf_file.c_str());
}

TEST(SLAMgmtIntegration, RASDeviceValidationWithSLAMgmtAPI) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  // Start mgmt controller
  ControllerServicer *c_svcr(new ControllerServicer(conf_file));
  auto c_server = InitializeServicer(c_svcr);
  ASSERT_NE(c_server, nullptr);
  EXPECT_TRUE(c_svcr->get_state() == true);
  std::thread *subscriber_thread =
      new std::thread(&StartThreadForZMQSubscriberConfiguration, c_svcr);

  std::thread *sla_thread =
      new std::thread(&StartEventProcessingThread, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  EXPECT_EQ(rc, 0);

  // Using the servicer just for simulating the smaller capacity devices
  FakeNodeServicer *n_svcr(new FakeNodeServicer(conf_file));
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);
  sleep(5);

  json command_params;

  command_params["app_name"] = "TESTSLAMGMTRAS";
  command_params["app_pid"] = 1234567890;
  command_params["app_total_data_set_MB"] = 4096;
  command_params["hot_data_size_MB"] = 2048;

  json qos_params;
  qos_params["avg_latency_ns"] = 2500;
  command_params["app_desired_qos"] = qos_params;

  json device;
  device["device_numa"] = "1";
  device["device_allocated_capacity_mb"] = 4096;
  json device_array = json::array();
  device_array.push_back(device);
  device["device_numa"] = "2";
  device["device_allocated_capacity_mb"] = 4096;
  device_array.push_back(device);

  command_params["devices"] = device_array;

  std::cout << command_params.dump() << std::endl;

  svk::SLAManagementRequest req;
  svk::SLAManagementResponse resp;

  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_node_name(DEFAULT_NODE_ID);
  req.set_command_name("set_app_sla");
  req.set_command_params(command_params.dump());

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  Status cmd_status = client.SLAManagementAPI(&req, &resp);
  ASSERT_TRUE(cmd_status.ok());

  sleep(2);

  std::string json_data_str = generate_ras_event(
      RAS_FEATURE_MODULE_NAME, "1", "localhost", "TESTSLAMGMTRAS", 2000);
  std::cout << "Publish event to core " << json_data_str << std::endl;
  rc = publish_event_data_to_core((char *)"events",
                                  (uint8_t *)json_data_str.c_str(),
                                  json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(2);

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();

  // Receive the events and check for SLA event as well as auto tiering event
  // from controller itself
  svk::EventRequest event_req;
  Status event_status;
  svk::EventResponse *event_resp = new (svk::EventResponse);
  event_req.set_command_name("cluster_events");

  event_status = client.EventAPI(&event_req, event_resp);
  ASSERT_EQ(event_status.ok(), true);
  std::cout << "event response is " << event_resp->response() << std::endl;
  EXPECT_NE(std::string::npos,
            event_resp->response().find(
                "Initiated data migration for the app TESTSLAMGMTRAS from the "
                "NUMA node 1 to NUMA node 0"));
  App_Info app_info;
  // The app should be associated with the new device
  EXPECT_EQ(g_sla_device_hlpr->GetAppInfo("localhost_2", app_info), 0);
  // The app should not be associated for the faulty device
  EXPECT_EQ(g_sla_device_hlpr->GetAppInfo("localhost_1", app_info), -1);

  StopAllThreads(c_svcr);
  StopEventProcessingThread(c_svcr);
  sla_thread->join();
  subscriber_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, NodeStatsSuccessful) {
  Status status;
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  // Register another node to validate multi-node cluster
  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());
  reg_req->set_cluster_name(DEFAULT_CLUSTER_ID);
  reg_req->set_node_ip("127.0.0.1");
  reg_req->set_node_port(DEFAULT_NODE_PORT);
  reg_req->set_node_name("node-x");

  status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(status.ok(), true);

  svk::StatsRequest req;
  svk::StatsResponse *resp = new (svk::StatsResponse);

  // Only cluster name is set. No node name
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_feature_name("node");
  req.set_command_name("get_node_info");
  req.set_command_params("{\"info_type\":\"stats\"}");

  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), true);

  std::string expected_resp_str =
      "{\"localhost\":{\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{"
      "\"available_memory_mb\":10663},\"node_name\":\"node_1\"}},\"node-x\":{"
      "\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{\"available_memory_"
      "mb\":10663},\"node_name\":\"node_1\"}}}";
  std::cout << "Only cluster name - Event response - " << resp->response()
            << std::endl;
  ASSERT_EQ(resp->response(), expected_resp_str);

  // node name is set along with cluster name
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_feature_name("node");
  req.set_node_name(DEFAULT_NODE_ID);
  req.set_command_name("get_node_info");
  req.set_command_params("{\"info_type\":\"stats\"}");

  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), true);

  expected_resp_str =
      "{\"localhost\":{\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{"
      "\"available_memory_mb\":10663},\"node_name\":\"node_1\"}}}";
  std::cout << "Node and cluster name set - Event response - "
            << resp->response() << std::endl;
  ASSERT_EQ(resp->response(), expected_resp_str);

  // Only node name is set. No clustername
  req.set_cluster_name("");
  req.set_feature_name("node");
  req.set_node_name("node-x");
  req.set_command_name("get_node_info");
  req.set_command_params("{\"info_type\":\"stats\"}");

  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), true);

  expected_resp_str =
      "{\"node-x\":{\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{"
      "\"available_memory_mb\":10663},\"node_name\":\"node_1\"}}}";
  std::cout << "Only node name - Event response - " << resp->response()
            << std::endl;
  ASSERT_EQ(resp->response(), expected_resp_str);

  // No node name or cluster name set
  req.set_cluster_name("");
  req.set_node_name("");
  req.set_feature_name("node");
  req.set_command_name("get_node_info");
  req.set_command_params("{\"info_type\":\"stats\"}");

  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), true);

  expected_resp_str =
      "{\"localhost\":{\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{"
      "\"available_memory_mb\":10663},\"node_name\":\"node_1\"}},\"node-x\":{"
      "\"node-stats\":{\"cpu\":{\"cores\":4},\"memory\":{\"available_memory_"
      "mb\":10663},\"node_name\":\"node_1\"}}}";
  std::cout << "No node or cluster name - Event response - " << resp->response()
            << std::endl;
  ASSERT_EQ(resp->response(), expected_resp_str);

  // Invalid node name is set along with valid cluster name
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_feature_name("node");
  req.set_node_name("node-invalid");
  req.set_command_name("get_node_info");
  req.set_command_params("{\"info_type\":\"stats\"}");

  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), true);

  json empty_obj;
  expected_resp_str = empty_obj.dump();
  std::cout << "invalid node and valid cluster - Event response - "
            << resp->response() << std::endl;
  ASSERT_EQ(resp->response(), expected_resp_str);

  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, NodeStatsFailureCases) {
  Status status;
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  svk::StatsRequest req;
  svk::StatsResponse *resp = new (svk::StatsResponse);

  // No command name set. Should fail
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_command_name("");
  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), false);

  // Invalid cluster name. Should fail
  req.set_cluster_name("invalid-cluster");
  req.set_command_name("get_node_info");
  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), false);

  // Invalid node name. Should fail
  req.set_cluster_name("");
  req.set_node_name("invalid_node");
  req.set_feature_name("node");
  req.set_command_name("get_node_info");
  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}

class FakeNodeServicerWithInvalidDataForStats : public Servicer {
 public:
  FakeNodeServicerWithInvalidDataForStats(std::string conf_file)
      : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      if (req->command_name() == "get_node_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        if (req->command_params().find("pci") != std::string::npos) {
          response->set_output(NODE_PCI_FEATURE_OUTPUT);
        }
        if (req->command_params().find("device") != std::string::npos) {
          response->set_output(NODE_DEVICE_FEATURE_OUTPUT);
        }
        if (req->command_params().find("stats") != std::string::npos) {
          response->set_output("");
        }
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(CXL_DEVICE_LIST_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        if (req->command_params().find("29690035288064") != std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT1);
        } else if (req->command_params().find("30690035288064") !=
                   std::string::npos) {
          response->set_output(CXL_DEVICE_INFO_OUTPUT2);
        }

        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }
    std::cout
        << "FakeNodeServicerWithInvalidDataForStats called for the command "
        << req->command_params() << std::endl;
    return Status::OK;
  }
};

TEST(InitIntegrationTest, NodeStatsWithInvalidJSONOutput) {
  Status status;
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  StartServer(conf_file, false);

  Servicer *svcr(new FakeNodeServicerWithInvalidDataForStats(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);

  svk::StatsRequest req;
  svk::StatsResponse *resp = new (svk::StatsResponse);
  req.set_cluster_name(DEFAULT_CLUSTER_ID);
  req.set_command_name("get_node_info");
  req.set_command_params("{\"info_type\":\"stats\"}");
  req.set_feature_name("node");
  status = client.StatsAPI(&req, resp);
  ASSERT_EQ(status.ok(), false);
  EXPECT_THAT(status.error_message(),
              HasSubstr("Error in parsing the output json string"));
}
