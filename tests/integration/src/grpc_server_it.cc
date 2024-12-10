#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdio.h>
#include <stdlib.h>

#include <csignal>
#include <thread>

#include "client_library.h"
#include "framework/framework_mock.grpc.pb.h"
#include "grpc_controller.h"
#include "grpc_controller_hlpr.h"
#include "grpc_server.h"
#include "grpc_server_hlpr.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StartsWith;
using ::testing::StrEq;

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
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandForAllocateMemoryFailure1) {
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
  req.set_feature_params("sla_latency_ns=10");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandForAllocateMemoryFailure2) {
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
  req.set_feature_params("app_name=TestApp");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest, ProcessControllerCommandForAllocateMemoryFailure3) {
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
  req.set_feature_params("size=100");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest,
     ProcessControllerCommandForAllocateMemoryFailure4WithZeroDevicesSLAMet) {
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
  req.set_feature_params("sla_latency_ns=1;app_name=TestApp;size=1024");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}

TEST(InitIntegrationTest,
     ProcessControllerCommandForAllocateMemoryFailure5WithLogicModule) {
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
  req.set_feature_params(
      "sla_latency_ns=10;app_name=TestApp;size=1024;logic_module=default");

  Client client(DEFAULT_CONTROLLER_ID, DEFAULT_CONTROLLER_PORT);
  Status status = client.ProcessControllerCommand(&req, resp);
  ASSERT_EQ(status.ok(), false);
  unlink(conf_file.c_str());
}
