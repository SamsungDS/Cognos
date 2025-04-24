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
#include "sla_hlpr_fns.h"

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

int create_device_sla_conf_json() {
  char command[256];
  char data[1024];
  FILE *fp;
  struct stat fstat;
  int status = -1;

  if (stat(SLA_CONFIG_FILE, &fstat) == 0) {
    return 0;
  }

  sprintf(command, "mkdir -p %s", SLA_CONFIG_DIR);
  status = system(command);
  if (status != 0) {
    return -1;
  }

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen(SLA_CONFIG_FILE, "w+");
  if (fp == NULL) {
    return -1;
  }
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);
  return 0;
}

int CheckPoller() {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL, FEATURES_DIR, DEFAULT_CONTROLLER_ID);

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;

  int rc = initialize_pub(&zmq_context, &zmq_socket, "0", "5555");
  if (rc != 0) {
    std::cout << "Failed to initialize publisher" << std::endl;
    return -1;
  }

  std::thread server_thr(StartServer, conf_file, true);
  std::thread node_thr(StartNodeServer, conf_file, true);
  // Sleep for a while for the server processes to stablize
  sleep(5);

  strcpy(data.host_name, "localhost");
  strcpy(data.device_name, "1");
  strcpy(data.app_name, "TESTAPP");
  data.avgLatencyns = 100;

  rc = publish(&zmq_socket, "APP_SLA_DEGRADED", &data);
  std::cout << "Published data result " << rc << std::endl;
  sleep(10);

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
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            data.find("Device's numa 1 on host localhost for the app TESTAPP "
                      "deviated than expected - Reported latency_ns = 100") !=
                std::string::npos);
  EXPECT_EQ(true, data.find("Updated node localhost's status to offline") !=
                      std::string::npos);
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

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;

  int rc = initialize_pub(&zmq_context, &zmq_socket, "0", "5555");
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

  strcpy(data.host_name, "localhost1");
  strcpy(data.device_name, "11");
  strcpy(data.app_name, "TESTAPP1");
  data.avgLatencyns = 1000;

  rc = publish(&zmq_socket, "APP_SLA_DEGRADED", &data);
  std::cout << "Published data result " << rc << std::endl;
  sleep(10);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(
      true,
      filedata.find("Device's numa 11 on host localhost1 for the app TESTAPP1 "
                    "deviated than expected - Reported latency_ns = 1000") !=
          std::string::npos);

  unlink(conf_file.c_str());
}

class FakeNodeServicer : public Servicer {
 public:
  FakeNodeServicer(std::string conf_file) : Servicer(conf_file){};
  Status ProcessNodeCommand(ServerContext *ctxt, const svk::CommandRequest *req,
                            svk::CommandResponse *resp) override {
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

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;
  std::string topic = "APP_SLA_DEGRADED";

  int rc = initialize_pub(&zmq_context, &zmq_socket, "0", "5555");
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

  strcpy(data.host_name, "localhost2");
  strcpy(data.device_name, "12");
  strcpy(data.app_name, "TESTAPP2");
  data.avgLatencyns = 1000;

  // rc = publish(&zmq_socket, "APP_SLA_DEGRADED", &data);

  char buffer[sizeof(svk_slat_logic_output)];
  int len = sizeof(svk_slat_logic_output);
  int topic_size, data_size;

  topic_size = zmq_send(zmq_socket, topic.c_str(),
                        strnlen(topic.c_str(), MAX_TOPIC_LEN - 1), ZMQ_SNDMORE);
  if (topic_size == -1) {
    std::cout << "ZMQ send topic failed." << std::endl;
    return;
  }

  memcpy(buffer, (void *)&data, len);
  data_size = zmq_send(zmq_socket, buffer, len - 2, 0);
  if (data_size == -1) {
    std::cout << "ZMQ send data failed." << std::endl;
    return;
  }

  std::cout << "Published data result successfully" << std::endl;
  sleep(10);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(
      false,
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
    std::string feature_params = req->feature_params();
    std::cout << "FakeProcessNodeCommand called for the command "
              << feature_params << std::endl;
    if (feature_params.find("StartTuning") != std::string::npos) {
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

  void *zmq_context;
  void *zmq_socket;
  svk_slat_logic_output data;

  int rc = initialize_pub(&zmq_context, &zmq_socket, "0", "5555");
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

  strcpy(data.host_name, "localhost");
  strcpy(data.device_name, "11");
  strcpy(data.app_name, "TESTAPP1");
  data.avgLatencyns = 1000;

  rc = publish(&zmq_socket, "APP_SLA_DEGRADED", &data);
  std::cout << "Published data result " << rc << std::endl;
  sleep(10);

  rc = publish(&zmq_socket, "APP_SLA_DEGRADED", &data);
  std::cout << "Published data result " << rc << "one more time" << std::endl;
  sleep(3);

  StopSLAThreadForTiering(c_svcr);
  sla_thread->join();
  delete c_svcr;
  delete n_svcr;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string filedata((std::istreambuf_iterator<char>(file)),
                       (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, filedata.find(
                      "Device's numa 11 on host localhost for the app TESTAPP1 "
                      "deviated than expected - Reported latency_ns = 1000") !=
                      std::string::npos);

  unlink(conf_file.c_str());
}