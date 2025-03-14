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
#include "sla_hlpr_fns.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StartsWith;
using ::testing::StrEq;

int create_svk_mgmt_fw_conf_json(std::string conf_file,
                                 std::string fw_conf_file,
                                 std::string sink_type, int log_file_count,
                                 uint64_t log_file_size,
                                 std::string log_level) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_controller.controller.id", CONTROLLER_DEFAULT_ID);
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

int create_svk_mgmt_fw_conf_json_without_logger(std::string conf_file) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_controller.controller.id", "localhost");
  root.put("svk_mgmt_fw_controller.controller.port", "9999");
  pt::write_json(json_file, root);

  return 0;
}

/**
 * Prepares clusters based on the provided number of nodes for each cluster.
 *
 * @param num_nodes_for_each_cluster A vector containing the number of nodes for
 * each cluster.
 *
 */
void prepare_clusters(std::vector<int> num_nodes_for_each_cluster) {
  int num_nodes;
  Status grpc_status;
  std::string cluster_name;
  std::string command_name;
  std::string node_name;
  namespace pt = boost::property_tree;

  // Initialize variables and perform initial checks
  int num_clusters = num_nodes_for_each_cluster.size();

  command_name = "create_cluster";

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  std::string node_ip;
  std::string node_port;

  // Iterate over each cluster and perform necessary operations
  for (int i = 0; i < num_clusters; i++) {
    num_nodes = num_nodes_for_each_cluster[i];

    cluster_name = "Cluster_" + std::to_string(i);

    pt::ptree params;
    pt::ptree cmd;
    pt::ptree nodes;

    params.put("cluster_name", cluster_name);
    params.put("command_name", command_name);
    // For each node, perform initialization and setup
    for (int j = 0; j < num_nodes; j++) {
      pt::ptree node;
      node_ip = "node." + std::to_string(i * 1000 + j) + ".com";
      node_port = "9998";
      node_name = "Node_" + std::to_string(i * 1000 + j);

      node.put("node_name", node_name);
      nodes.push_back(std::make_pair("", node));

      reg_req->set_node_name(node_name);
      reg_req->set_node_ip(node_ip);
      reg_req->set_node_port(node_port);

      grpc_status = client.RegisterNode(reg_req, reg_resp);
      ASSERT_EQ(grpc_status.ok(), true);
    }
    cmd.add_child("nodes", nodes);
    params.add_child("command_params", cmd);

    std::stringstream ss;
    pt::write_json(ss, params, false);
    std::string json_str = ss.str();
    // test json:
    // {
    //     "cluster_name": "Cluster_0",
    //     "command_name": "create_cluster",
    //     "command_params": {
    //         "nodes": [
    //             {
    //                 "node_name": "Node_0"
    //             }
    //         ]
    //     }
    // }
    svk::ClusterRequest *req(new svk::ClusterRequest());
    svk::ClusterResponse *resp(new svk::ClusterResponse());
    req->set_cluster_name(cluster_name);
    req->set_command_name(command_name);
    req->set_command_params(json_str);

    grpc_status = client.ClusterAPI(req, resp);
    ASSERT_EQ(grpc_status.ok(), true);
  }
}

/**
 * Checks if a given string exists in the log file.
 *
 * @param search_str The string to search for in the log file.
 * @return True if the string is found in the log file, false otherwise.
 */
bool is_str_in_log(std::string search_str) {
  // Use this call to flush logs immediately
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");

  // Check if the log file exists
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  if (!file.good()) {
    const char *message = CONTROLLER_NODE_DEFAULT_LOG_FILE " doesn't exist";
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

TEST(InitControllerTest, InitSuccess) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  EXPECT_TRUE(svcr->get_state() == true);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, InitSuccessWithDestructor) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  EXPECT_TRUE(svcr->get_state() == true);
  svcr->~ControllerServicer();
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, InitSuccessWithNullControllerServicerObject) {
  auto server = InitializeServicer(nullptr);
  ASSERT_EQ(server, nullptr);
}

TEST(InitControllerTest, InitWithInvalidLoggerLevel) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file,
                               CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
                               CONTROLLER_LOGGER_DEFAULT_FILE_COUNT,
                               CONTROLLER_LOGGER_DEFAULT_FILE_SIZE, "INFOX");

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, InitWithInvalidLoggerSinkType) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, "console", CONTROLLER_LOGGER_DEFAULT_FILE_COUNT,
      CONTROLLER_LOGGER_DEFAULT_FILE_SIZE, CONTROLLER_LOGGER_DEFAULT_LEVEL);

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, InitWithInvalidJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(conf_file.c_str(), conf_file.length(), 1, fp);
  fclose(fp);
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, InitWithEmptyJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string content = "{}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, InitWithoutLoggerEntries) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json_without_logger(conf_file);

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  unlink(conf_file.c_str());
}

// Test if stat fails
TEST(InitControllerTest, FailedStatCall) {
  std::string conf_file = "invalid_dir/conf.json";
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

class MockTestController : public ::testing::Test {
 protected:
  MockTestController() {}

  void SetUp() override {
    char *cw_dir = get_current_dir_name();
    std::string conf_file = std::string(cw_dir) + "/conf.json";
    create_svk_mgmt_fw_conf_json(
        conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
        CONTROLLER_LOGGER_DEFAULT_FILE_COUNT,
        CONTROLLER_LOGGER_DEFAULT_FILE_SIZE, CONTROLLER_LOGGER_DEFAULT_LEVEL);
    ControllerServicer *svcr(new ControllerServicer(conf_file));
    server_ = InitializeServicer(svcr);

    ASSERT_NE(server_, nullptr);
    EXPECT_TRUE(svcr->get_state() == true);
    EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  }

  void TearDown() override { server_->Shutdown(); }

  std::shared_ptr<Server> server_;
};

TEST_F(MockTestController, RegisterNodeWithoutDeviceSLAConf) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE_SLA";
  std::string node_id = "registernodesla.localdomain.com";
  std::string node_port = "9998";

  unlink(SLA_CONFIG_FILE);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNodeWithoutDeviceSLAConf UT called");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  ASSERT_EQ(grpc_status.ok(), true);
}

TEST_F(MockTestController, RegisterNode) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNode UT called");

  ASSERT_EQ(create_device_sla_conf_json(), 0);
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  std::string search_str = "Registered the node_id " + node_id + ":" +
                           node_port + " with cluster:" + cluster_id;
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
  search_str = "Registered the node " + node_id + " with controller.";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
}

TEST_F(MockTestController, CreateCluster) {
  Status grpc_status;

  std::string cluster_name = "CLUSTER_CREATE_CLUSTER";
  std::string command_name = "create_cluster";

  namespace pt = boost::property_tree;
  pt::ptree cmd;
  pt::ptree nodes;

  pt::ptree node;
  node.put("node_name", "NODE_CREATE_CLUSTER");

  nodes.push_back(std::make_pair("", node));
  cmd.add_child("nodes", nodes);

  std::stringstream ss;
  pt::write_json(ss, cmd, false);
  std::string json_str = ss.str();
  // test json:
  // {
  //     "cluster_name": "CLUSTER_CREATE_CLUSTER",
  //     "command_name": "create_cluster",
  //     "command_params": {
  //         "nodes": [
  //             {
  //                 "node_name": "NODE_CREATE_CLUSTER"
  //             }
  //         ]
  //     }
  // }

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  std::string node_id = "registernodesla.localdomain.com";
  std::string node_port = "9998";
  std::string node_name = "NODE_CREATE_CLUSTER";

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  reg_req->set_node_name(node_name);
  reg_req->set_node_ip(node_id);
  reg_req->set_node_port(node_port);

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  std::string search_str =
      "Registered the node " + node_name + " with controller.";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_cluster_name(cluster_name);
  req->set_command_name(command_name);
  req->set_command_params(json_str);

  grpc_status = client.ClusterAPI(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  std::string resp_json = resp->command_response();
  std::string expected_json =
      "{\"clusters\":[{\"cluster_name\":\"CLUSTER_CREATE_CLUSTER\",\"nodes\":[{"
      "\"node_name\":\"NODE_CREATE_CLUSTER\",\"status\":\"online\"}]}]}";
  EXPECT_EQ(resp_json, expected_json);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");
  std::ifstream file2(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data2((std::istreambuf_iterator<char>(file2)),
                    (std::istreambuf_iterator<char>()));
  file2.close();
  search_str = "Cluster id " + cluster_name + " created";
  EXPECT_EQ(true, data2.find(search_str) != std::string::npos);
}

TEST_F(MockTestController, InvalidParamsClusterAPI) {
  Status grpc_status;
  std::string cluster_name = "";
  std::string command_name = "";
  std::string command_params = "";
  std::string logger_str;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_cluster_name(cluster_name);
  req->set_command_name(command_name);
  req->set_command_params(command_params);

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.ok(), false);
  EXPECT_EQ(grpc_status.error_message(), "Invalid request parameters");
}

TEST_F(MockTestController, InvalidCommandClusterAPI) {
  Status grpc_status;
  std::string cluster_name = "CLUSTER_CREATE_CLUSTER";
  std::string command_name = "invalid";
  std::string command_params = "test";
  std::string logger_str;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_cluster_name(cluster_name);
  req->set_command_name(command_name);
  req->set_command_params(command_params);

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.ok(), false);
  EXPECT_EQ(grpc_status.error_message(), "Invalid command name");
}

TEST_F(MockTestController, InvalidClusterParamsCreateCluster) {
  Status grpc_status;
  std::string cluster_name = "CLUSTER_CREATE_CLUSTER";
  std::string command_name = "create_cluster";
  std::string command_params = "invalid";

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_cluster_name(cluster_name);
  req->set_command_name(command_name);
  req->set_command_params(command_params);
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.ok(), false);
  EXPECT_EQ(grpc_status.error_message(), "Error parsing json command_params");
}

TEST_F(MockTestController, ListNodes) {
  Status grpc_status;

  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNode UT called");

  ASSERT_EQ(create_device_sla_conf_json(), 0);
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());
  reg_req->set_cluster_name(cluster_id);
  reg_req->set_node_ip(node_id);
  reg_req->set_node_port(node_port);

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  ASSERT_EQ(grpc_status.ok(), true);

  svk::NodeRequest *req(new svk::NodeRequest());
  svk::NodeResponse *resp(new svk::NodeResponse());

  req->set_command_name("list_nodes");

  grpc_status = client.NodeAPI(req, resp);
  EXPECT_EQ(grpc_status.ok(), true);
  std::string command_resp = resp->command_response();
  std::string expected_resp =
      "{\"node_info\":[{\"node_ip\":\"registernode.localdomain.com\",\"node_"
      "name\":\"registernode.localdomain.com\",\"node_port\":\"9998\","
      "\"status\":\"online\"}]}";
  EXPECT_EQ(command_resp, expected_resp);
}

TEST_F(MockTestController, ListNodesInvalidCommandName) {
  Status grpc_status;

  svk::NodeRequest *req(new svk::NodeRequest());
  svk::NodeResponse *resp(new svk::NodeResponse());

  req->set_command_name("invalid");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  grpc_status = client.NodeAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);

  req->set_command_name("");
  grpc_status = client.NodeAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
}

TEST_F(MockTestController, ListClustersEmpty) {
  Status grpc_status;
  std::string command_name = "list_clusters";
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name(command_name);
  req->set_cluster_name("");
  req->set_command_params("");

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.ok(), true);
  EXPECT_EQ(resp->command_response(), "{\"clusters\":[]}");

  std::string search_str = "ListClusters returns 0 cluster names";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, ListClusters) {
  std::vector<int> nodes_for_each_cluster = {2, 3};
  Status grpc_status;
  std::string command_name;
  prepare_clusters(nodes_for_each_cluster);

  command_name = "list_clusters";
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name(command_name);

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.ok(), true);

  // The order of two cluster names may be different, because controller uses
  // unsorted map.
  std::string str1 =
      "{\"clusters\":[{\"cluster_name\":\"Cluster_0\"},"
      "{\"cluster_name\":\"Cluster_1\"}]}";
  std::string str2 =
      "{\"clusters\":[{\"cluster_name\":\"Cluster_1\"},"
      "{\"cluster_name\":\"Cluster_0\"}]}";
  std::cout << "Expected response (str1): " << str1 << std::endl;
  std::cout << "Expected response (str2): " << str2 << std::endl;
  std::cout << "Actual response: " << resp->command_response() << std::endl;
  EXPECT_TRUE(resp->command_response() == str1 ||
              resp->command_response() == str2);

  std::string search_str = "ListClusters returns 2 cluster names";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RegisterNodeWithNullClusterID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_node_ip("testnode.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
}

TEST_F(MockTestController, RegisterNodeWithNullNodeID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name("DUMMY_CLUSTER");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Invalid input - zero length arg given");
}

TEST_F(MockTestController, RegisterNodeWithNullNodePort) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name("DUMMY_CLUSTER");
  req->set_node_ip("testnode.localdomain.com");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Invalid input - zero length arg given");
}

TEST_F(MockTestController, RegisterSameNodeAgain) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_SAME_NODE";
  std::string node_id = "registersamenode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterSameNodeAgain UT called");

  ASSERT_EQ(create_device_sla_conf_json(), 0);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  // Forcefully flush the logs
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNodeAgain");

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  std::string search_str =
      "Found the cluster_name: " + cluster_id + " already registered";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
  search_str =
      "Node with node_id " + node_id + ":" + node_port + " already registered";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
  search_str = "Node " + node_id +
               " is already registered with the controller, coming online";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
}

TEST_F(MockTestController, UnRegisterNode) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_UNREGISTER_NODE";
  std::string node_id = "unregisternode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "UnRegisterNode UT called");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  // Register the node initially
  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with UnRegisterNode");
  // Read the file after 3 seconds to see whether the message is flushed
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  std::string search_str = "Registered the node_id " + node_id + ":" +
                           node_port + " with cluster:" + cluster_id;

  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  // Now unregister the node
  svk::UnregisterRequest *ureq(new svk::UnregisterRequest());
  svk::UnregisterResponse *uresp(new svk::UnregisterResponse());
  ureq->set_cluster_id(cluster_id);
  ureq->set_node_id(node_id);
  ureq->set_node_port(node_port);

  grpc_status = client.UnregisterNode(ureq, uresp);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << uresp->status() << std::endl;

  std::ifstream file1(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data1((std::istreambuf_iterator<char>(file1)),
                    (std::istreambuf_iterator<char>()));
  file1.close();

  search_str = "Found the registered cluster_id: " + cluster_id;
  EXPECT_EQ(true, data1.find(search_str) != std::string::npos);
  search_str = "Unregistered the node_id " + node_id + " successfully";
  EXPECT_EQ(true, data1.find(search_str) != std::string::npos);
}

TEST_F(MockTestController, UnregisterNodeWithNullClusterID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::UnregisterRequest *req(new svk::UnregisterRequest());
  svk::UnregisterResponse *resp(new svk::UnregisterResponse());
  req->set_node_id("testnode.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.UnregisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Invalid input - zero length arg given");
}

TEST_F(MockTestController, UnregisterNodeWithNullNodeID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::UnregisterRequest *req(new svk::UnregisterRequest());
  svk::UnregisterResponse *resp(new svk::UnregisterResponse());
  req->set_cluster_id("DUMMY_CLUSTER");
  req->set_node_port("9998");

  grpc_status = client.UnregisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Invalid input - zero length arg given");
}

TEST_F(MockTestController, UnRegisterNodeWithInvalidClusterID) {
  Status grpc_status;

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "UnRegisterNodeWithInvalidClusterID UT called");
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  // Register the node initially
  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name("MY_CLUSTER_ID3");
  req->set_node_ip("testnode3.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            data.find("Registered the node_id testnode3.localdomain.com:9998 "
                      "with cluster:MY_CLUSTER_ID3") != std::string::npos);

  // Now unregister the node
  svk::UnregisterRequest *ureq(new svk::UnregisterRequest());
  svk::UnregisterResponse *uresp(new svk::UnregisterResponse());
  ureq->set_cluster_id("INVALID_CLUSTER_ID");
  ureq->set_node_id("testnode3.localdomain.com");
  ureq->set_node_port("9998");

  grpc_status = client.UnregisterNode(ureq, uresp);
  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(), "cluster_id not found");
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");
  std::ifstream file1(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data1((std::istreambuf_iterator<char>(file1)),
                    (std::istreambuf_iterator<char>()));
  file1.close();
  EXPECT_EQ(true,
            data1.find(
                "Unregistering the cluster_id: INVALID_CLUSTER_ID not found") !=
                std::string::npos);
}

TEST_F(MockTestController, UnRegisterNodeWithInvalidNodeID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  // Register the node initially
  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name("CLUSTER_UNREGISTER_NODE_INVALID_ID");
  req->set_node_ip("testnode1.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            data.find("Registered the node_id testnode1.localdomain.com:9998 "
                      "with cluster:CLUSTER_UNREGISTER_NODE_INVALID_ID") !=
                std::string::npos);

  // Now unregister the node
  svk::UnregisterRequest *ureq(new svk::UnregisterRequest());
  svk::UnregisterResponse *uresp(new svk::UnregisterResponse());
  ureq->set_cluster_id("CLUSTER_UNREGISTER_NODE_INVALID_ID");
  ureq->set_node_id("testnode2.localdomain.com");
  ureq->set_node_port("9998");

  grpc_status = client.UnregisterNode(ureq, uresp);
  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(), "node_id not found");
}

int KillProcess() {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  std::thread server_thr(StartServer, conf_file, true);
  // Sleep for a while for the server process to stablize
  sleep(3);
  // Raise the interrupt signal for the server to go down gracefully
  std::raise(SIGINT);
  // Wait for > 5 seconds for the signal handler to be processed on the server
  // node
  sleep(7);
  unlink(conf_file.c_str());
  return 0;
}

TEST(InitControllerTest, InitControllerWithSignal) {
  GTEST_FLAG_SET(death_test_style, "threadsafe");
  EXPECT_DEATH(KillProcess(), "");
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, data.find("gRPC Controller server is shutdown") !=
                      std::string::npos);
}

TEST(InitControllerTest, InitControllerServerInNonBlocking) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  StartServer(conf_file, false);
}

TEST(InitControllerTest, SignalHandlerFunction) { signal_handler(SIGINT); }

TEST_F(MockTestController, ListClusterNodesWithSingleCluster) {
  Status grpc_status;
  std::string cluster_id_1 = "CLUSTER_LIST_NODE1";
  std::string node_id_1 = "listnode1.localdomain.com";
  std::string node_port_1 = "9998";

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id_1);
  req->set_node_ip(node_id_1);
  req->set_node_port(node_port_1);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  std::string search_str = "Registered the node_id " + node_id_1 + ":" +
                           node_port_1 + " with cluster:" + cluster_id_1;
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  svk::ListClusterCommandRequest l_req;
  svk::ListClusterCommandResponse l_resp;

  l_req.set_cluster_id(cluster_id_1);
  grpc_status = client.ListClusterNodes(&l_req, &l_resp);
  ASSERT_EQ(grpc_status.ok(), true);
  ASSERT_EQ(l_resp.cluster_info().size(), 1);
  ASSERT_EQ(l_resp.cluster_info(0).cluster_id().c_str(), cluster_id_1);
  ASSERT_EQ(l_resp.cluster_info(0).node_info().size(), 1);
  ASSERT_EQ(l_resp.cluster_info(0).node_info(0).node_id().c_str(), node_id_1);
}

TEST_F(MockTestController, ListClusterNodesWithMultipleClusters) {
  Status grpc_status;
  std::string cluster_id_1 = "CLUSTER_LIST_NODE1";
  std::string node_id_1 = "listnode1.localdomain.com";
  std::string node_port_1 = "9998";

  std::string cluster_id_2 = "CLUSTER_LIST_NODE2";
  std::string node_id_2 = "listnode2.localdomain.com";
  std::string node_port_2 = "9998";

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id_1);
  req->set_node_ip(node_id_1);
  req->set_node_port(node_port_1);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  req->set_cluster_name(cluster_id_2);
  req->set_node_ip(node_id_2);
  req->set_node_port(node_port_2);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  std::string search_str = "Registered the node_id " + node_id_1 + ":" +
                           node_port_1 + " with cluster:" + cluster_id_1;
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
  search_str = "Registered the node_id " + node_id_2 + ":" + node_port_2 +
               " with cluster:" + cluster_id_2;
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  svk::ListClusterCommandRequest l_req;
  svk::ListClusterCommandResponse l_resp;

  grpc_status = client.ListClusterNodes(&l_req, &l_resp);
  ASSERT_EQ(grpc_status.ok(), true);
  ASSERT_EQ(l_resp.cluster_info().size(), 2);
  if (l_resp.cluster_info(0).cluster_id() == cluster_id_1) {
    ASSERT_EQ(l_resp.cluster_info(1).cluster_id().c_str(), cluster_id_2);

    ASSERT_EQ(l_resp.cluster_info(0).node_info().size(), 1);
    ASSERT_EQ(l_resp.cluster_info(0).node_info(0).node_id().c_str(), node_id_1);
  } else {
    ASSERT_EQ(l_resp.cluster_info(0).cluster_id().c_str(), cluster_id_2);
    ASSERT_EQ(l_resp.cluster_info(0).node_info().size(), 1);
    ASSERT_EQ(l_resp.cluster_info(0).node_info(0).node_id().c_str(), node_id_2);
  }

  if (l_resp.cluster_info(1).cluster_id() == cluster_id_1) {
    ASSERT_EQ(l_resp.cluster_info(0).cluster_id().c_str(), cluster_id_2);

    ASSERT_EQ(l_resp.cluster_info(1).node_info().size(), 1);
    ASSERT_EQ(l_resp.cluster_info(1).node_info(0).node_id().c_str(), node_id_1);
  } else {
    ASSERT_EQ(l_resp.cluster_info(1).cluster_id().c_str(), cluster_id_2);
    ASSERT_EQ(l_resp.cluster_info(1).node_info().size(), 1);
    ASSERT_EQ(l_resp.cluster_info(1).node_info(0).node_id().c_str(), node_id_2);
  }
}

TEST_F(MockTestController, ListClusterNodesWithInvalidClusterID) {
  Status grpc_status;
  std::string cluster_id_1 = "CLUSTER_LIST_NODE1";

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::ListClusterCommandRequest l_req;
  svk::ListClusterCommandResponse l_resp;

  l_req.set_cluster_id(cluster_id_1);
  grpc_status = client.ListClusterNodes(&l_req, &l_resp);
  ASSERT_EQ(grpc_status.ok(), false);
}

TEST(SLAFunction, DeviceSLAHelperFunctionFailure) {
  FILE *fp = nullptr;
  fp = fopen("test.conf", "w+");
  fclose(fp);
  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, -1);
}

TEST(SLAFunction, DeviceSLAHelperFunctionSuccess) {
  FILE *fp = nullptr;
  char data[1024];

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, 0);
}

TEST(SLAFunction, DeviceSLAHelperGetDeviceForAppRequirements) {
  FILE *fp = nullptr;
  char data[1024];
  std::vector<DeviceInfo> devices;

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");

  status = device_hlpr_class.GetDeviceForAppRequirements(50, 100, devices);

  ASSERT_EQ(status, 0);
  ASSERT_EQ(devices.size(), 1);
}

TEST(SLAFunction, DeviceSLAHelperGetDeviceForAppRequirementsNotMet) {
  FILE *fp = nullptr;
  char data[1024];
  std::vector<DeviceInfo> devices;

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, 0);

  status = device_hlpr_class.GetDeviceForAppRequirements(5, 100, devices);

  ASSERT_EQ(status, -1);
  ASSERT_EQ(devices.size(), 0);
}

TEST(SLAFunction, DeviceSLAHelperGetDeviceForAppRequirementsAndUpdate) {
  FILE *fp = nullptr;
  char data[1024];
  std::vector<DeviceInfo> devices;
  App_Device_List dev_data;

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, 0);

  status = device_hlpr_class.GetDeviceForAppRequirements(50, 100, devices);

  ASSERT_EQ(status, 0);
  ASSERT_EQ(devices.size(), 1);

  dev_data.appLatencyns = 50;
  dev_data.device_info = devices;

  status = device_hlpr_class.SetSLADataForApp("TestingApp", dev_data);
  ASSERT_EQ(status, 0);
}

TEST(SLAFunction, DeviceUnregister) {
  FILE *fp = nullptr;
  char data[1024];
  std::vector<DeviceInfo> devices;
  App_Device_List dev_data;

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"},"
         "{\"dev_name\": \"DEV2-256G\",\"dev_size\": "
         "\"274877906944\",\"dev_numa\": "
         "2,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, 0);

  status = device_hlpr_class.UnregisterDevicesForNode("localhost");
  ASSERT_EQ(status, 0);
}

TEST(SLAFunction, DeviceUnregisterWithDeviceInUse) {
  FILE *fp = nullptr;
  char data[1024];
  std::string logger_msg;

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"},"
         "{\"dev_name\": \"DEV2-256G\",\"dev_size\": "
         "\"274877906944\",\"dev_numa\": "
         "2,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");

  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, 0);

  std::vector<DeviceInfo> devices = device_hlpr_class.GetDevices();
  DeviceInfo dev = devices.front();
  dev.free_flag = false;
  devices.front() = dev;
  device_hlpr_class.SetDevices(devices);
  std::vector<DeviceInfo> ndevices = device_hlpr_class.GetDevices();
  status = device_hlpr_class.UnregisterDevicesForNode("localhost");
  ASSERT_EQ(status, -1);
}

TEST(SLAFunction, DeviceUnregisterWithInvalidNode) {
  FILE *fp = nullptr;
  char data[1024];
  std::vector<DeviceInfo> devices;
  App_Device_List dev_data;

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  int status = device_hlpr_class.GetDeviceInfo("localhost", "9998");
  ASSERT_EQ(status, 0);

  status = device_hlpr_class.UnregisterDevicesForNode("localhost1");
  ASSERT_EQ(status, 0);
}

TEST(SLAFunction, SLADeviceHelperDestructor) {
  FILE *fp = nullptr;
  char data[1024];

  memset(data, 0, sizeof(data));
  strcpy(data,
         "[{\"type\": \"FM_DIRECT_CMMD\",\"Devices\": [{\"dev_name\": "
         "\"DEV1-256G\",\"dev_size\": \"274877906944\",\"dev_numa\": "
         "0,\"sla_avg_latency_ns\": 10, \"node_name\": \"localhost\"}]}]");
  fp = fopen("test.conf", "w+");
  fwrite((void *)&data[0], strlen(data), 1, fp);
  fclose(fp);

  SLADeviceHelper device_hlpr_class = SLADeviceHelper("test.conf");
  device_hlpr_class.~SLADeviceHelper();
}

TEST(ServicerFunctions, ServicerFunctionValidation) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  svcr->set_config_changed(true);
  ASSERT_EQ(svcr->is_config_changed(), true);
  svcr->set_config_changed(false);
  ASSERT_EQ(svcr->is_config_changed(), false);

  std::unordered_map<std::string, std::unordered_map<std::string, std::string>>
      cluster_map;
  cluster_map["cluster1"]["localhost1"] = "1234";
  cluster_map["cluster1"]["localhost2"] = "1234";
  svcr->set_cluster_map(cluster_map);
  cluster_map = svcr->get_cluster_map();
  ASSERT_EQ(cluster_map.find("cluster1") == cluster_map.end(), false);

  ASSERT_EQ(svcr->get_svk_config_controller_port(), CONTROLLER_DEFAULT_PORT);
  ASSERT_EQ(svcr->get_svk_config_controller_id(), CONTROLLER_DEFAULT_ID);
}

TEST(SLAStatsManager, addEntryTest) {
  SLAStatsManager mgr;
  std::string app_name = "test_app";
  std::string host_name = "test_host";
  std::string device_name = "test_device";
  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_device",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};

  bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
  ASSERT_TRUE(rc);
}

TEST(SLAStatsManager, addDuplicateEntry) {
  SLAStatsManager mgr;
  std::string app_name = "test_app";
  std::string host_name = "test_host";
  std::string device_name = "test_device";
  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_device",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};

  bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
  ASSERT_TRUE(rc);
  rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
  ASSERT_TRUE(rc);
}

TEST(SLAStatsManager, getDataTest) {
  SLAStatsManager mgr;
  std::string app_name = "test_app";
  std::string host_name = "test_host";
  std::string device_name = "test_device";
  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_device",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};

  bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
  ASSERT_TRUE(rc);

  svk_slat_logic_output stats =
      mgr.getSLAData("test_app", "test_host", "test_device");
  ASSERT_STREQ(data.host_name, stats.host_name);
}

TEST(SLAStatsManager, getDataFail) {
  SLAStatsManager mgr;
  EXPECT_THROW(mgr.getSLAData("test_app", "test_host", "test_device"),
               std::runtime_error);
}

TEST(SLAStatsManager, updateDataTest) {
  SLAStatsManager mgr;
  std::string app_name = "test_app";
  std::string host_name = "test_host";
  std::string device_name = "test_device";
  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_device",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};

  bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
  ASSERT_TRUE(rc);

  svk_slat_logic_output data2 = {.host_name = "test_host2",
                                 .app_name = "test_app2",
                                 .device_name = "test_device2",
                                 .avgLatencyns = 1,
                                 .iops = 1,
                                 .avgReadLatency = 1,
                                 .avgWriteLatency = 1,
                                 .avgUpdateLatency = 1,
                                 .avgReadIOPS = 1,
                                 .avgWriteIOPS = 1,
                                 .avgP99Latency = 1,  // TBD
                                 .ioBytesRead = 1,
                                 .ioBytesWritten = 1,
                                 .ioBytesRewrite = 1};
  rc = mgr.updateSLAData(app_name, host_name, device_name, data2);
  ASSERT_TRUE(rc);

  svk_slat_logic_output stats =
      mgr.getSLAData(app_name, host_name, device_name);
  ASSERT_STREQ(data2.host_name, stats.host_name);
}

TEST(SLAStatsManager, updateDataFail) {
  SLAStatsManager mgr;
  svk_slat_logic_output data;

  bool rc = mgr.updateSLAData("test_app", "test_host", "test_device", data);
  ASSERT_FALSE(rc);
}

TEST(SLAStatsManager, searchTest) {
  SLAStatsManager mgr;
  for (int x = 0; x < 5; x++) {
    std::string app_name = "test_app";
    std::string host_name = "test_host" + std::to_string(x);
    std::string device_name = "test_device" + std::to_string(x);

    svk_slat_logic_output data = {.host_name = "test_host",
                                  .app_name = "test_app",
                                  .device_name = "test_device",
                                  .avgLatencyns = 1,
                                  .iops = 1,
                                  .avgReadLatency = 1,
                                  .avgWriteLatency = 1,
                                  .avgUpdateLatency = 1,
                                  .avgReadIOPS = 1,
                                  .avgWriteIOPS = 1,
                                  .avgP99Latency = 1,
                                  .ioBytesRead = 1,
                                  .ioBytesWritten = 1,
                                  .ioBytesRewrite = 1};

    bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
    ASSERT_TRUE(rc);
  }
  for (int x = 0; x < 3; x++) {
    std::string app_name = "test_app2";
    std::string host_name = "test_host" + std::to_string(x);
    std::string device_name = "test_device" + std::to_string(x);
    svk_slat_logic_output data = {.host_name = "test_host2",
                                  .app_name = "test_app2",
                                  .device_name = "test_device2",
                                  .avgLatencyns = 1,
                                  .iops = 1,
                                  .avgReadLatency = 1,
                                  .avgWriteLatency = 1,
                                  .avgUpdateLatency = 1,
                                  .avgReadIOPS = 1,
                                  .avgWriteIOPS = 1,
                                  .avgP99Latency = 1,
                                  .ioBytesRead = 1,
                                  .ioBytesWritten = 1,
                                  .ioBytesRewrite = 1};

    bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
    ASSERT_TRUE(rc);
  }

  std::map<std::tuple<std::string, std::string, std::string>,
           svk_slat_logic_output>
      results;
  results = mgr.searchSLAData("test_app");

  ASSERT_EQ(5, results.size());
}

TEST(SLAStatsManager, searchFail) {
  SLAStatsManager mgr;
  std::map<std::tuple<std::string, std::string, std::string>,
           svk_slat_logic_output>
      results;
  results = mgr.searchSLAData("test_app");
  ASSERT_EQ(0, results.size());
}

TEST(SLAStatsManager, writeReadFile) {
  SLAStatsManager mgr;
  std::string app_name = "test_app";
  std::string host_name = "test_host";
  std::string device_name = "test_device";
  svk_slat_logic_output data = {.host_name = "test_host",
                                .app_name = "test_app",
                                .device_name = "test_device",
                                .avgLatencyns = 1,
                                .iops = 1,
                                .avgReadLatency = 1,
                                .avgWriteLatency = 1,
                                .avgUpdateLatency = 1,
                                .avgReadIOPS = 1,
                                .avgWriteIOPS = 1,
                                .avgP99Latency = 1,
                                .ioBytesRead = 1,
                                .ioBytesWritten = 1,
                                .ioBytesRewrite = 1};

  bool rc = mgr.addSLADataEntry(app_name, host_name, device_name, data);
  ASSERT_TRUE(rc);

  rc = mgr.writeToFile("testfile.bin");
  ASSERT_TRUE(rc);

  SLAStatsManager mgr2;
  rc = mgr2.readFromFile("testfile.bin");
  ASSERT_TRUE(rc);

  svk_slat_logic_output data2;
  EXPECT_NO_THROW(data2 =
                      mgr2.getSLAData("test_app", "test_host", "test_device"));
  // data2 = mgr2.getSLAData("test_app", "test_host", "test_device");
  ASSERT_STREQ(data.host_name, data2.host_name);
}

TEST(SLAStatsManager, readFileFail) {
  SLAStatsManager mgr;

  bool rc = mgr.readFromFile("badfile");
  ASSERT_FALSE(rc);
}
