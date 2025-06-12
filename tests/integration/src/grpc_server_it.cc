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
#include "grpc_controller.h"
#include "grpc_controller_hlpr.h"
#include "grpc_server.h"
#include "grpc_server_hlpr.h"
#include "sla_hlpr_fns.h"
#include "svk_publisher.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
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
  root.put("svk_mgmt_fw_controller.logger.log_file_count", log_file_count);
  root.put("svk_mgmt_fw_controller.logger.log_file_size", log_file_size);
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
  observations_map["device_name"] = device_name;
  observations_map["host_name"] = host_name;
  observations_map["app_name"] = app_name;
  observations_map["avg_latency_ns"] = 1000;
  observations_map["message"] = "Device SLA deviation";

  json_map["domain"] = "observability";
  json_map["category"] = feature_name;
  json_map["severity"] = "warning";

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
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");

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
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "InitControllerNodeServerWithSignal in CheckPoller");
  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return -1;
  }

  std::string json_data_str =
      get_sla_deviation_data("sla", "DEV1", "localhost", "TESTAPP", 100);
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());

  sleep(3);
  cleanup_publisher();

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Done with InitControllerNodeServerWithSignal in CheckPoller");

  // Raise the interrupt signal for the server to go down gracefully
  std::thread::id node_thread_id = node_thr.get_id();
  std::thread::id ctrlr_thread_id = server_thr.get_id();

  auto node_native_handle =
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

TEST(InitIntegrationTest, InitControllerNodeServerWithSignal) {
  GTEST_FLAG_SET(death_test_style, "threadsafe");
  EXPECT_DEATH(CheckPoller(), "");
  EXPECT_EQ(
      true,
      is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                    "Device's numa DEV1 on host localhost for the app TESTAPP "
                    "deviated than expected - Reported latency_ns = 100"));
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

TEST(InitIntegrationTest, ControllerNodeManualServicerStart) {
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
  std::thread *sla_thread = new std::thread(&StartSLAThreadForTiering, c_svcr);

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
  std::string json_data_str =
      get_sla_deviation_data("sla", "DEV11", "localhost1", "TESTAPP1", 1000);
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(10);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            filedata.find(
                "Device's numa DEV11 on host localhost1 for the app TESTAPP1 "
                "deviated than expected - Reported latency_ns = 1000") !=
                std::string::npos);

  unlink(conf_file.c_str());
}

// Trimmed down version of node feature output
#define NODE_FEATURE_OUTPUT                                              \
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
#define CXL_DEVICE_LIST_OUTPUT                                                \
  "{\"devices\":[{\"device_id\":29690035288064,\"vendor_device_type\":\"CMM-" \
  "D\",\"pcie_addr\":\"0000:b8:00.0\"}]}"
#define CXL_DEVICE_INFO_OUTPUT                                               \
  "{\"api_version\":1.0,\"device_id\":29690035288064,\"manufacturer\":"      \
  "\"Samsung\",\"serial_number\":305419896,\"FW_revision\":\"1.0.0\","       \
  "\"location\":\"0000:b8:00.0\",\"total_capacity_MB\":129007,\"feature_"    \
  "supported\":\"basic\",\"vendor_device_type\":\"CMM-D\",\"cxl_device_"     \
  "type\":\"Type3\",\"protocol\":\"CXL "                                     \
  "2.0\",\"port_type\":\"root\",\"mode_discovered\":\"auto\",\"connection_"  \
  "type\":\"CXL.mem\",\"domain_type\":\"PCIe\",\"domain_id\":0,\"link_"      \
  "speed\":16,\"link_width\":8,\"available_capacity_MB\":127080,\"status\":" \
  "\"active\",\"aspm_active\":false,\"sris_active\":false,\"lock_active\":"  \
  "false,\"numa_attached\":1,\"capabilities\":{\"Power Management "          \
  "version\":1},\"advertised_qos\":{\"avg_latency\":120,\"p99_latency\":"    \
  "350,\"io_per_sec\":50000,\"BW_per_sec\":1000000,\"io_size\":4096,"        \
  "\"qd\":32}}"

class FakeNodeServicer : public Servicer {
 public:
  FakeNodeServicer(std::string conf_file) : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      if (req->command_name() == "get_node_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(NODE_FEATURE_OUTPUT);
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
        response->set_output(CXL_DEVICE_INFO_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }
    std::cout << "FakeProcessNodeCommand called for the command "
              << req->feature_params() << std::endl;
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

TEST(InitIntegrationTest,
     ControllerNodeServicerStartWithIncorrectPublishedData) {
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
  std::thread *sla_thread = new std::thread(&StartSLAThreadForTiering, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }
  Servicer *n_svcr(new Servicer(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(5);

  std::string json_data_str =
      get_sla_deviation_data("sla", "12", "localhost2", "TESTAPP2", 1000);
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());
  std::cout << "Published data result successfully" << std::endl;
  sleep(10);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(
      true,
      filedata.find("Device's numa 12 on host localhost2 for the app TESTAPP2 "
                    "deviated than expected - Reported latency_ns = 1000") !=
          std::string::npos);

  unlink(conf_file.c_str());
}

class FakeNodeServicerForTM : public Servicer {
 public:
  FakeNodeServicerForTM(std::string conf_file) : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      if (req->command_name() == "get_node_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(NODE_FEATURE_OUTPUT);
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
        response->set_output(CXL_DEVICE_INFO_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      }
    }

    std::string command_name =
        req->command_name().length() ? req->command_name() : "";
    std::cout
        << "FakeProcessNodeCommand called for the command StartTuning with "
        << req->command_params() << std::endl;
    if (command_name == "StartTuning") {
      svk::CommandResponse_NodeResponse *response = resp->add_node_responses();
      response->set_output("{status = \"0\"}");
    }
    return Status::OK;
  }
};

TEST(InitIntegrationTest, ControllerNodeManualServicerStartForTMOperation) {
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
  std::thread *sla_thread = new std::thread(&StartSLAThreadForTiering, c_svcr);

  int rc = initialize_publisher(conf_file.c_str());
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return;
  }
  Servicer *n_svcr(new FakeNodeServicerForTM(conf_file));
  if (n_svcr->get_state() == false) {
    std::cout << "Node Servicer is not initialized properly. Exiting"
              << std::endl;
    return;
  }
  auto n_server = InitializeNodeServicer(n_svcr);
  ASSERT_NE(n_server, nullptr);

  sleep(5);

  std::string json_data_str =
      get_sla_deviation_data("sla", "DEVTM", "localhost", "TESTAPP1", 1000);
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  sleep(10);

  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());
  std::cout << "Published data result " << rc << "one more time" << std::endl;
  sleep(3);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            filedata.find(
                "Device's numa DEVTM on host localhost for the app TESTAPP1 "
                "deviated than expected - Reported latency_ns = 1000") !=
                std::string::npos);

  unlink(conf_file.c_str());
}

class FakeNodeServicerWithoutCXLDevices : public Servicer {
 public:
  FakeNodeServicerWithoutCXLDevices(std::string conf_file)
      : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
    if (req->command_name().length() > 0) {
      if (req->command_name() == "get_node_info") {
        std::string output = NODE_FEATURE_OUTPUT;
        output = std::regex_replace(
            output, std::regex("cxl", std::regex_constants::icase), "test");
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(output);
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
      if (req->command_name() == "get_node_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(NODE_FEATURE_OUTPUT);
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "list_devices") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output("{\"devices\": \"xyz\"}");
        response->set_node_id(req->node_id());
        return Status::OK;
      } else if (req->command_name() == "get_device_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(CXL_DEVICE_INFO_OUTPUT);
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
  ASSERT_EQ(server, nullptr);

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
      if (req->command_name() == "get_node_info") {
        svk::CommandResponse_NodeResponse *response =
            resp->add_node_responses();
        response->set_output(NODE_FEATURE_OUTPUT);
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
  ASSERT_EQ(server, nullptr);

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
  std::thread *sla_thread = new std::thread(&StartSLAThreadForTiering, c_svcr);

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
  std::string json_data_str =
      get_sla_deviation_data("sla", "DEV11", "localhost1", "TESTAPP1", 1000);
  json json_data = json::parse(json_data_str);
  json_data.erase("observations");
  json_data_str = json_data.dump();
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());

  std::cout << "Published data result " << rc << std::endl;
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Parse error for zmq data"));
  sleep(2);

  json_data_str = "dummyjson=true";
  rc = publish_data((char *)"alerts", (uint8_t *)json_data_str.c_str(),
                    json_data_str.length());
  std::cout << "Published data result " << rc << std::endl;
  EXPECT_EQ(true, is_str_in_log(CONTROLLER_NODE_DEFAULT_LOG_FILE,
                                "Parse error for zmq data"));
  sleep(10);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;
  cleanup_publisher();

  unlink(conf_file.c_str());
}
