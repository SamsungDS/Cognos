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
#include "mock_client.hpp"
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

    // For each node, perform initialization and setup
    for (int j = 0; j < num_nodes; j++) {
      pt::ptree node;
      // e.g., "node.0.0.com"
      node_ip = "node." + std::to_string(i) + "." + std::to_string(j) + ".com";
      node_port = "9998";
      // e.g., "Node_0_0"
      node_name = "Node_" + std::to_string(i) + "_" + std::to_string(j);

      node.put("node_name", node_name);
      nodes.push_back(std::make_pair("", node));

      reg_req->set_node_name(node_name);
      reg_req->set_node_ip(node_ip);
      reg_req->set_node_port(node_port);

      EXPECT_CALL(*mockClient, CreateClient(_, _))
          .Times(AtLeast(1))
          .WillRepeatedly([](std::string node_id, std::string node_port) {
            return std::make_unique<FakeClient>(node_id, node_port);
          });
      grpc_status = client.RegisterNode(reg_req, reg_resp);
      ASSERT_EQ(grpc_status.ok(), true);
    }
    params.add_child("nodes", nodes);

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
    //                 "node_name": "Node_0_0"
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

    mockClient = new MockClient;
    // auto c = std::make_unique<Client>("localhost", "9998");
    // ON_CALL(*mockClient, CreateClient(_,
    // _)).WillByDefault(Return(std::make_unique<FakeClient>("localhost",
    // "9998")));

    ASSERT_NE(server_, nullptr);
    EXPECT_TRUE(svcr->get_state() == true);
    EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  }

  void TearDown() override {
    server_->Shutdown();
    delete mockClient;
  }

  std::shared_ptr<Server> server_;
};

TEST_F(MockTestController, TestMock) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);
}

TEST_F(MockTestController, RegisterNode) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNode UT called");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);
  svk::ClusterRequest *c_req(new svk::ClusterRequest());
  svk::ClusterResponse *c_resp(new svk::ClusterResponse());

  c_req->set_command_name("list_clusters");
  grpc_status = client.ClusterAPI(c_req, c_resp);
  ASSERT_EQ(grpc_status.ok(), true);
  std::string expected_json =
      "{\"clusters\":[{\"cluster_name\":\"CLUSTER_REGISTER_NODE\"}]}";
  EXPECT_EQ(c_resp->command_response(), expected_json);

  c_req->set_cluster_name(cluster_id);
  c_req->set_command_name("list_nodes_in_cluster");

  grpc_status = client.ClusterAPI(c_req, c_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

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

  expected_json =
      "{\"clusters\":[{\"cluster_name\":\"CLUSTER_REGISTER_NODE\",\"nodes\":[{"
      "\"node_name\":\"registernode.localdomain.com\",\"status\":\"online\"}]}]"
      "}";
  std::cout << grpc_status.error_message() << std::endl;
  EXPECT_EQ(c_resp->command_response(), expected_json);
}

TEST_F(MockTestController, RegisterNodeWithoutClusterName) {
  Status grpc_status;

  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";
  std::string node_name = "test_node";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNode UT called");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());

  req->set_node_ip(node_id);
  req->set_node_port(node_port);
  req->set_node_name(node_name);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk::NodeRequest *n_req(new svk::NodeRequest());
  svk::NodeResponse *n_resp(new svk::NodeResponse());

  n_req->set_command_name("list_nodes");

  grpc_status = client.NodeAPI(n_req, n_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  std::string search_str =
      "Registered the node " + node_name + " with controller";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  std::string expected_json =
      "{\"node_info\":[{\"node_ip\":\"registernode.localdomain.com\",\"node_"
      "name\":\"test_node\",\"node_port\":\"9998\",\"status\":\"online\"}]}";
  std::cout << n_resp->command_response() << std::endl;
  EXPECT_EQ(n_resp->command_response(), expected_json);
}

TEST_F(MockTestController, RegisterNodeWithMultipleNodesInCluster) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Register another node with same cluster
  req->set_cluster_name("CLUSTER_REGISTER_NODE");
  req->set_node_ip("registernode.localdomain2.com");
  req->set_node_port("9999");
  req->set_node_name("test_node");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk::ClusterRequest *c_req(new svk::ClusterRequest());
  svk::ClusterResponse *c_resp(new svk::ClusterResponse());

  c_req->set_command_name("list_clusters");
  grpc_status = client.ClusterAPI(c_req, c_resp);
  ASSERT_EQ(grpc_status.ok(), true);
  std::string expected_json =
      "{\"clusters\":[{\"cluster_name\":\"CLUSTER_REGISTER_NODE\"}]}";
  ;
  EXPECT_EQ(c_resp->command_response(), expected_json);

  c_req->set_cluster_name(cluster_id);
  c_req->set_command_name("list_nodes_in_cluster");

  grpc_status = client.ClusterAPI(c_req, c_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

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

  search_str =
      "Registered the node_id registernode.localdomain2.com:9999 with "
      "cluster:" +
      cluster_id;
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
  search_str = "Registered the node " + node_id + " with controller.";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  expected_json =
      "{\"clusters\":[{\"cluster_name\":\"CLUSTER_REGISTER_NODE\",\"nodes\":[{"
      "\"node_name\":\"registernode.localdomain.com\",\"status\":\"online\"},{"
      "\"node_name\":\"test_node\",\"status\":\"online\"}]}]}";
  EXPECT_EQ(c_resp->command_response(), expected_json);
}

TEST_F(MockTestController, SetNodeStatus) {
  Status grpc_status;
  std::vector<int> nodes_for_each_cluster = {1};
  prepare_clusters(nodes_for_each_cluster);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::SetNodeStatusRequest *req(new svk::SetNodeStatusRequest());
  svk::SetNodeStatusResponse *resp(new svk::SetNodeStatusResponse());

  req->set_node_name("Node_0_0");
  req->set_node_status("offline");

  grpc_status = client.SetNodeStatus(req, resp);
  EXPECT_TRUE(grpc_status.ok());
  std::string search_str = "Updated node Node_0_0's status to offline";
  EXPECT_TRUE(is_str_in_log(search_str));

  // Check internal structure is updated
  svk::NodeRequest *n_req(new svk::NodeRequest());
  svk::NodeResponse *n_resp(new svk::NodeResponse());

  n_req->set_command_name("list_nodes");

  grpc_status = client.NodeAPI(n_req, n_resp);
  EXPECT_EQ(grpc_status.ok(), true);
  std::string command_resp = n_resp->command_response();
  std::string expected_resp =
      "{\"node_info\":[{\"node_ip\":\"node.0.0.com\",\"node_"
      "name\":\"Node_0_0\",\"node_port\":\"9998\","
      "\"status\":\"offline\"}]}";
  EXPECT_EQ(command_resp, expected_resp);

  // Set to online
  req->set_node_name("Node_0_0");
  req->set_node_status("online");

  grpc_status = client.SetNodeStatus(req, resp);
  EXPECT_TRUE(grpc_status.ok());
  search_str = "Updated node Node_0_0's status to online";
  EXPECT_TRUE(is_str_in_log(search_str));

  // Check internal structure is updated
  n_req->set_command_name("list_nodes");

  grpc_status = client.NodeAPI(n_req, n_resp);
  EXPECT_EQ(grpc_status.ok(), true);
  command_resp = n_resp->command_response();
  expected_resp =
      "{\"node_info\":[{\"node_ip\":\"node.0.0.com\",\"node_"
      "name\":\"Node_0_0\",\"node_port\":\"9998\","
      "\"status\":\"online\"}]}";
  EXPECT_EQ(command_resp, expected_resp);
}

TEST_F(MockTestController, SetNodeStatusEmptyParams) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::SetNodeStatusRequest *req(new svk::SetNodeStatusRequest());
  svk::SetNodeStatusResponse *resp(new svk::SetNodeStatusResponse());

  req->set_node_name("");
  req->set_node_status("offline");

  grpc_status = client.SetNodeStatus(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str = "Invalid node name or status";
  EXPECT_TRUE(is_str_in_log(search_str));

  req->set_node_name("Node_0_0");
  req->set_node_status("");

  grpc_status = client.SetNodeStatus(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  search_str = "Invalid node name or status";
  EXPECT_TRUE(is_str_in_log(search_str));
}

TEST_F(MockTestController, SetNodeStatusInvalidParams) {
  Status grpc_status;
  std::vector<int> nodes_for_each_cluster = {1};
  prepare_clusters(nodes_for_each_cluster);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::SetNodeStatusRequest *req(new svk::SetNodeStatusRequest());
  svk::SetNodeStatusResponse *resp(new svk::SetNodeStatusResponse());

  req->set_node_name("invalid");
  req->set_node_status("offline");

  grpc_status = client.SetNodeStatus(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str = "Node invalid not found";
  EXPECT_TRUE(is_str_in_log(search_str));

  req->set_node_name("Node_0_0");
  req->set_node_status("invalid");

  grpc_status = client.SetNodeStatus(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  search_str = "Invalid status given: invalid. Could not update node status.";
  EXPECT_TRUE(is_str_in_log(search_str));
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

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

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
  EXPECT_EQ(grpc_status.error_message(),
            "ClusterAPI received invalid command name");
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
  EXPECT_EQ(grpc_status.error_message(),
            "ClusterAPI received invalid command name");
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

TEST_F(MockTestController, EmptyClusterParamsCreateCluster) {
  Status grpc_status;
  std::string cluster_name = "cluster1";
  std::string command_name = "";

  using json = nlohmann::json;

  json cmd_params;
  json nodes = json::array();
  cmd_params["nodes"] = nodes;
  std::string command_params = cmd_params.dump();
  // namespace pt = boost::property_tree;
  // pt::ptree cmd;
  // pt::ptree nodes;

  // pt::ptree node;
  // //node.put("node_name", "NODE_CREATE_CLUSTER");

  // nodes.push_back(std::make_pair("", node));
  // cmd.add_child("nodes", nodes);

  // std::stringstream ss;
  // pt::write_json(ss, cmd, false);
  // std::string command_params = ss.str();
  // std::cout << command_params << std::endl;

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_cluster_name(cluster_name);
  req->set_command_name(command_name);
  req->set_command_params(command_params);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(grpc_status.error_message(),
            "ClusterAPI received invalid command name");

  req->set_cluster_name("");
  req->set_command_name("create_cluster");
  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(grpc_status.error_message(),
            "Invalid request parameters for CreateCluster");

  req->set_cluster_name("cluster1");
  req->set_command_params("");
  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(grpc_status.error_message(),
            "Invalid request parameters for CreateCluster");

  req->set_command_params(cmd_params.dump());
  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(grpc_status.error_message(), "No nodes found in command_params");

  json invalid_node;
  invalid_node["node_name"] = "invalid_node";
  nodes.push_back(invalid_node);
  cmd_params["nodes"] = nodes;
  req->set_command_params(cmd_params.dump());
  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(
      grpc_status.error_message(),
      "Node invalid_node is offline or not registered, could not be added "
      "to cluster");
}

TEST_F(MockTestController, CreateClusterWithUnregisteredNodes) {
  Status grpc_status;

  std::string cluster_name = "CLUSTER_CREATE_CLUSTER";
  std::string command_name = "create_cluster";

  using json = nlohmann::json;
  json cmd;
  json nodes = json::array();
  json node;
  node["node_name"] = "NODE_CREATE_CLUSTER";
  nodes.push_back(node);
  node["node_name"] = "NODE_CREATE_CLUSTER_2";
  nodes.push_back(node);
  cmd["nodes"] = nodes;
  std::cout << cmd.dump() << std::endl;
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

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

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
  req->set_command_params(cmd.dump());

  grpc_status = client.ClusterAPI(req, resp);
  ASSERT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs");
  std::ifstream file2(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data2((std::istreambuf_iterator<char>(file2)),
                    (std::istreambuf_iterator<char>()));
  file2.close();
  search_str =
      "Node NODE_CREATE_CLUSTER_2 is offline or not registered, could not be "
      "added to cluster";
  EXPECT_EQ(true, data2.find(search_str) != std::string::npos);

  req->set_command_name("list_clusters");

  grpc_status = client.ClusterAPI(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);
  EXPECT_EQ(resp->command_response(), "{\"clusters\":[]}");

  search_str = "ListClusters returns 0 cluster names";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, ListNodes) {
  Status grpc_status;

  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNode UT called");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());
  reg_req->set_cluster_name(cluster_id);
  reg_req->set_node_ip(node_id);
  reg_req->set_node_port(node_port);

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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

TEST_F(MockTestController, DeleteClusterInvalidParam) {
  Status grpc_status;
  std::string command_name = "delete_cluster";
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name(command_name);
  req->set_cluster_name("");
  req->set_command_params("");

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);

  std::string error_str =
      "Invalid request parameters for DeleteCluster: cluster_name is null.";
  EXPECT_EQ(is_str_in_log(error_str), true);

  EXPECT_EQ(grpc_status.error_message(), error_str);
}

TEST_F(MockTestController, DeleteClusterNotFound) {
  Status grpc_status;
  std::string command_name = "delete_cluster";
  std::string cluster_name = "Cluster_999";
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name(command_name);
  req->set_cluster_name(cluster_name);
  req->set_command_params("");

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);

  std::string error_str =
      "Invalid request parameters for DeleteCluster: " + cluster_name +
      " not found in deletion";
  EXPECT_EQ(is_str_in_log(error_str), true);

  EXPECT_EQ(grpc_status.error_message(), error_str);
}

TEST_F(MockTestController, DeleteCluster) {
  Status grpc_status;
  std::vector<int> nodes_for_each_cluster = {2, 3};

  svk_logger_change_log_level(CONTROLLER_LOGGER_MODULE_NAME, level_E::TRACE);

  // Create two clusters (Cluster_0 and Cluster_1) with 2 and 3 nodes,
  // respectively.
  prepare_clusters(nodes_for_each_cluster);

  std::string command_name = "delete_cluster";
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name(command_name);
  req->set_cluster_name("Cluster_0");
  req->set_command_params("");

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.ok(), true);

  std::string search_str = "Cluster Cluster_0 removed.";
  EXPECT_EQ(is_str_in_log(search_str), true);

  search_str = "Node Node_0_0 changes its cluster_name to null.";
  EXPECT_EQ(is_str_in_log(search_str), true);

  search_str = "Node Node_0_1 changes its cluster_name to null.";
  EXPECT_EQ(is_str_in_log(search_str), true);

  svk_logger_change_log_level(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO);
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

TEST_F(MockTestController, ListNodesInCluster) {
  std::vector<int> nodes_for_each_cluster = {1};
  Status grpc_status;
  std::string command_name;
  prepare_clusters(nodes_for_each_cluster);

  command_name = "list_nodes_in_cluster";
  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name(command_name);
  req->set_cluster_name("Cluster_0");

  grpc_status = client.ClusterAPI(req, resp);

  EXPECT_EQ(grpc_status.ok(), true);
  std::string expected_json =
      "{\"clusters\":[{\"cluster_name\":\"Cluster_0\",\"nodes\":[{"
      "\"node_name\":\"Node_0_0\",\"status\":\"online\"}]}]}";
  EXPECT_EQ(resp->command_response(), expected_json);
}

TEST_F(MockTestController, ListNodesInInvalidCluster) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name("list_nodes_in_cluster");
  req->set_cluster_name("Cluster_0");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::NOT_FOUND);
  std::string search_str = "Cluster Cluster_0 not found";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, ListNodesEmptyClusterName) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name("list_nodes_in_cluster");
  req->set_cluster_name("");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str = "ListNodesInCluster called with empty cluster name";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddNodeToCluster) {
  Status grpc_status;

  using json = nlohmann::json;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  reg_req->set_node_name("test_node1");
  reg_req->set_node_ip("localhost");
  reg_req->set_node_port("9998");

  // Registering 2 nodes
  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  reg_req->set_node_name("test_node2");
  reg_req->set_node_ip("localhost2");

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Creating a cluster
  svk::ClusterRequest *cluster_req(new svk::ClusterRequest());
  svk::ClusterResponse *cluster_resp(new svk::ClusterResponse());
  cluster_req->set_cluster_name("test_cluster");
  cluster_req->set_command_name("create_cluster");
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "test_node1";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  std::cout << command_params.dump() << std::endl;
  cluster_req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(cluster_req, cluster_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Add other node to the cluster
  svk::ClusterRequest *add_node_req(new svk::ClusterRequest());
  svk::ClusterResponse *add_node_resp(new svk::ClusterResponse());

  add_node_req->set_cluster_name("test_cluster");
  add_node_req->set_command_name("add_node_to_cluster");
  // Set up json req
  single_node["node_name"] = "test_node2";
  nodes.clear();
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;

  std::cout << command_params.dump() << std::endl;
  add_node_req->set_command_params(command_params.dump());
  grpc_status = client.ClusterAPI(add_node_req, add_node_resp);
  ASSERT_EQ(grpc_status.ok(), true);
  std::string resp_json = add_node_resp->command_response();
  std::string expected_json =
      "{\"clusters\":[{\"cluster_name\":\"test_cluster\",\"nodes\":[{"
      "\"node_name\":\"test_node1\",\"status\":\"online\"},{"
      "\"node_name\":\"test_node2\",\"status\":\"online\"}]}]}";
  EXPECT_EQ(resp_json, expected_json);

  std::string search_str =
      "Nodes successfully added/removed from cluster test_cluster";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddNodeEmptyParams) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_params("");
  req->set_command_name("add_node_to_cluster");
  req->set_cluster_name("test_cluster");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str =
      "add_node_to_cluster called with no cluster_name or command_params";
  EXPECT_EQ(is_str_in_log(search_str), true);

  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "test_node1";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  req->set_command_params(command_params.dump());
  req->set_cluster_name("");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddNodeInvalidJson) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_name("add_node_to_cluster");
  req->set_command_params("invalid");
  req->set_cluster_name("invalid");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str = "JSON error: ";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddNodeInvalidParams) {
  Status grpc_status;

  std::vector<int> cluster_vec = {1};
  prepare_clusters(cluster_vec);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_name("add_node_to_cluster");
  req->set_cluster_name("invalid");
  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "invalid";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;

  req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str =
      "Invalid cluster or node, could not add/remove node from cluster.";
  EXPECT_EQ(is_str_in_log(search_str), true);

  single_node["node_name"] = "Node_0";
  nodes.clear();
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  search_str =
      "Invalid cluster or node, could not add/remove node from cluster.";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddNodeEmptyNodeList) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_name("add_node_to_cluster");
  req->set_cluster_name("Cluster_0");

  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  command_params["nodes"] = nodes;
  req->set_command_params(command_params.dump());
  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str = "add_node_to_cluster called with empty nodes list";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddSameNodeToCluster) {
  Status grpc_status;

  using json = nlohmann::json;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  reg_req->set_node_name("test_node1");
  reg_req->set_node_ip("localhost");
  reg_req->set_node_port("9998");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk::ClusterRequest *cluster_req(new svk::ClusterRequest());
  svk::ClusterResponse *cluster_resp(new svk::ClusterResponse());
  cluster_req->set_cluster_name("test_cluster");
  cluster_req->set_command_name("create_cluster");
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "test_node1";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  std::cout << command_params.dump() << std::endl;
  cluster_req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(cluster_req, cluster_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk::ClusterRequest *add_node_req(new svk::ClusterRequest());
  svk::ClusterResponse *add_node_resp(new svk::ClusterResponse());

  add_node_req->set_cluster_name("test_cluster");
  add_node_req->set_command_name("add_node_to_cluster");

  std::cout << command_params.dump() << std::endl;
  add_node_req->set_command_params(command_params.dump());
  grpc_status = client.ClusterAPI(add_node_req, add_node_resp);
  ASSERT_EQ(grpc_status.error_code(), grpc::ALREADY_EXISTS);

  std::string search_str = "Node test_node1 is already part of a cluster";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, AddRemovedNodeToNewCluster) {
  Status grpc_status;

  using json = nlohmann::json;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  // Register 2 nodes and add to a cluster
  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  reg_req->set_node_name("test_node1");
  reg_req->set_node_ip("127.0.0.1");
  reg_req->set_node_port("9998");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  reg_req->set_node_name("test_node2");
  reg_req->set_node_ip("127.0.0.2");
  reg_req->set_node_port("9998");

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk::ClusterRequest *cluster_req(new svk::ClusterRequest());
  svk::ClusterResponse *cluster_resp(new svk::ClusterResponse());
  cluster_req->set_cluster_name("test_cluster1");
  cluster_req->set_command_name("create_cluster");

  json command_params1;
  json nodes1 = json::array();
  json test_node1;
  test_node1["node_name"] = "test_node1";
  nodes1.push_back(test_node1);
  json test_node2;
  test_node2["node_name"] = "test_node2";
  nodes1.push_back(test_node2);
  command_params1["nodes"] = nodes1;

  cluster_req->set_command_params(command_params1.dump());

  grpc_status = client.ClusterAPI(cluster_req, cluster_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Register 1 node and add to a different cluster
  reg_req->set_node_name("test_node3");
  reg_req->set_node_ip("127.0.0.3");
  reg_req->set_node_port("9998");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  cluster_req->set_cluster_name("test_cluster2");
  cluster_req->set_command_name("create_cluster");
  json command_params2;
  json nodes2 = json::array();
  json test_node3;
  test_node3["node_name"] = "test_node3";
  nodes2.push_back(test_node3);
  command_params2["nodes"] = nodes2;

  cluster_req->set_command_params(command_params2.dump());

  grpc_status = client.ClusterAPI(cluster_req, cluster_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Delete first cluster
  svk::ClusterRequest *delete_cluster_req(new svk::ClusterRequest());
  svk::ClusterResponse *delete_cluster_resp(new svk::ClusterResponse());

  delete_cluster_req->set_cluster_name("test_cluster1");
  delete_cluster_req->set_command_name("delete_cluster");

  grpc_status = client.ClusterAPI(delete_cluster_req, delete_cluster_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Add a node from deleted cluster to new cluster
  svk::ClusterRequest *add_node_req(new svk::ClusterRequest());
  svk::ClusterResponse *add_node_resp(new svk::ClusterResponse());

  add_node_req->set_cluster_name("test_cluster2");
  add_node_req->set_command_name("add_node_to_cluster");

  json command_params3;
  json nodes3 = json::array();
  nodes3.push_back(test_node2);
  command_params3["nodes"] = nodes3;

  add_node_req->set_command_params(command_params3.dump());
  grpc_status = client.ClusterAPI(add_node_req, add_node_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // std::string search_str = "Node test_node1 is already part of a cluster";
  // EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RemoveNodeFromCluster) {
  Status grpc_status;

  using json = nlohmann::json;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk_logger_change_log_level(CONTROLLER_LOGGER_MODULE_NAME, level_E::TRACE);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  reg_req->set_node_name("test_node1");
  reg_req->set_node_ip("localhost");
  reg_req->set_node_port("9998");

  // Registering 2 nodes
  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  reg_req->set_node_name("test_node2");
  reg_req->set_node_ip("localhost2");

  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Creating a cluster with 2 nodes
  svk::ClusterRequest *cluster_req(new svk::ClusterRequest());
  svk::ClusterResponse *cluster_resp(new svk::ClusterResponse());
  cluster_req->set_cluster_name("test_cluster");
  cluster_req->set_command_name("create_cluster");
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "test_node1";
  nodes.push_back(single_node);
  single_node["node_name"] = "test_node2";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  cluster_req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(cluster_req, cluster_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  // Remove node
  svk::ClusterRequest *remove_node_req(new svk::ClusterRequest());
  svk::ClusterResponse *remove_node_resp(new svk::ClusterResponse());

  remove_node_req->set_cluster_name("test_cluster");
  remove_node_req->set_command_name("remove_node_from_cluster");
  // Set up json req
  nodes.clear();
  single_node["node_name"] = "test_node1";
  nodes.push_back(single_node);

  command_params["nodes"] = nodes;

  remove_node_req->set_command_params(command_params.dump());
  grpc_status = client.ClusterAPI(remove_node_req, remove_node_resp);
  ASSERT_EQ(grpc_status.ok(), true);
  std::string resp_json = remove_node_resp->command_response();
  std::string expected_json =
      "{\"clusters\":[{\"cluster_name\":\"test_cluster\",\"nodes\":[{"
      "\"node_name\":\"test_node2\",\"status\":\"online\"}]}]}";
  EXPECT_EQ(resp_json, expected_json);

  std::string search_str =
      "Nodes successfully added/removed from cluster test_cluster";
  EXPECT_EQ(is_str_in_log(search_str), true);
  search_str =
      "Node test_node1 removed from cluster test_cluster, cluster now contains "
      "1 nodes.";
  EXPECT_EQ(is_str_in_log(search_str), true);

  svk_logger_change_log_level(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO);
}

TEST_F(MockTestController, RemoveNodeEmptyParams) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_params("");
  req->set_command_name("remove_node_from_cluster");
  req->set_cluster_name("test_cluster");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str =
      "remove_node_from_cluster called with no cluster_name or command_params";
  EXPECT_EQ(is_str_in_log(search_str), true);

  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "test_node1";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  req->set_command_params(command_params.dump());
  req->set_cluster_name("");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RemoveNodeInvalidJson) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_name("remove_node_from_cluster");
  req->set_command_params("invalid");
  req->set_cluster_name("invalid");

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str = "JSON error: ";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RemoveNodeInvalidParams) {
  Status grpc_status;

  std::vector<int> cluster_vec = {1};
  prepare_clusters(cluster_vec);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_name("remove_node_from_cluster");
  req->set_cluster_name("invalid");
  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "invalid";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;

  req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str =
      "Invalid cluster or node, could not add/remove node from cluster.";
  EXPECT_EQ(is_str_in_log(search_str), true);

  single_node["node_name"] = "Node_0";
  nodes.clear();
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;
  req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  search_str =
      "Invalid cluster or node, could not add/remove node from cluster.";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RemoveNodeEmptyNodeList) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);
  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());
  req->set_command_name("remove_node_from_cluster");
  req->set_cluster_name("Cluster_0");

  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  command_params["nodes"] = nodes;
  req->set_command_params(command_params.dump());
  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::INVALID_ARGUMENT);
  std::string search_str =
      "remove_node_from_cluster called with empty nodes list";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RemoveInvalidNode) {
  Status grpc_status;

  std::vector<int> cluster_vec = {1};
  prepare_clusters(cluster_vec);

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *reg_req(new svk::RegisterRequest());
  svk::RegisterResponse *reg_resp(new svk::RegisterResponse());

  reg_req->set_node_name("invalid_node");
  reg_req->set_node_ip("localhost");
  reg_req->set_node_port("1234");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  grpc_status = client.RegisterNode(reg_req, reg_resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk::ClusterRequest *req(new svk::ClusterRequest());
  svk::ClusterResponse *resp(new svk::ClusterResponse());

  req->set_command_name("remove_node_from_cluster");
  req->set_cluster_name("Cluster_0");
  using json = nlohmann::json;
  json command_params;
  json nodes = json::array();
  json single_node;
  single_node["node_name"] = "invalid_node";
  nodes.push_back(single_node);
  command_params["nodes"] = nodes;

  req->set_command_params(command_params.dump());

  grpc_status = client.ClusterAPI(req, resp);
  EXPECT_EQ(grpc_status.error_code(), grpc::NOT_FOUND);
  std::string search_str =
      "Node invalid_node not found in cluster Cluster_0, could not remove it "
      "from cluster.";
  EXPECT_EQ(is_str_in_log(search_str), true);
}

TEST_F(MockTestController, RegisterNodeWithNullClusterID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_node_ip("testnode.localdomain.com");
  req->set_node_port("9998");

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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

TEST_F(MockTestController, UnRegisterNodeWithClusterID) {
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

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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
  ureq->set_node_name(node_id);

  grpc_status = client.UnregisterNode(ureq, uresp);
  ASSERT_NE(grpc_status.ok(), true);
  ASSERT_EQ(grpc_status.error_message(),
            "Node is part of cluster. Remove from the cluster");
}

TEST_F(MockTestController, UnRegisterNodeWithoutClusterID) {
  Status grpc_status;
  std::string node_id = "unregisternode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "UnRegisterNode UT called");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  // Register the node initially
  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_node_ip(node_id);
  req->set_node_port(node_port);

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->error_id_or_string_if_any()
            << std::endl;

  svk_logger_flush(CONTROLLER_LOGGER_MODULE_NAME);
  // Read the file after 3 seconds to see whether the message is flushed
  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  std::string search_str =
      "Registered the node " + node_id + " with controller.";

  EXPECT_EQ(true, data.find(search_str) != std::string::npos);

  // Now unregister the node
  svk::UnregisterRequest *ureq(new svk::UnregisterRequest());
  svk::UnregisterResponse *uresp(new svk::UnregisterResponse());
  ureq->set_node_name(node_id);

  grpc_status = client.UnregisterNode(ureq, uresp);
  svk_logger_flush(CONTROLLER_LOGGER_MODULE_NAME);
  ASSERT_EQ(grpc_status.ok(), true);

  std::ifstream file1(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data1((std::istreambuf_iterator<char>(file1)),
                    (std::istreambuf_iterator<char>()));
  file1.close();

  search_str = "Unregistered the node_name " + node_id + " successfully";
  EXPECT_EQ(true, data1.find(search_str) != std::string::npos);
}

TEST_F(MockTestController, UnregisterNodeWithNullNodeID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::UnregisterRequest *req(new svk::UnregisterRequest());
  svk::UnregisterResponse *resp(new svk::UnregisterResponse());

  grpc_status = client.UnregisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Invalid input - zero length node_name given");
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

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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
  ureq->set_node_name("testnode2.localdomain.com");

  grpc_status = client.UnregisterNode(ureq, uresp);
  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Node not registered testnode2.localdomain.com");
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

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
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

TEST_F(MockTestController, RegisterNodeWithoutDeviceSLAConf) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE_SLA";
  std::string node_id = "registernodesla.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNodeWithoutDeviceSLAConf UT called");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_name(cluster_id);
  req->set_node_name(node_id);
  req->set_node_ip("127.0.0.1");
  req->set_node_port(node_port);

  EXPECT_CALL(*mockClient, CreateClient(_, _))
      .Times(AtLeast(1))
      .WillRepeatedly([](std::string node_id, std::string node_port) {
        return std::make_unique<FakeClient>(node_id, node_port);
      });
  grpc_status = client.RegisterNode(req, resp);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNodeWithoutDeviceSLAConf");
  svk_logger_flush(CONTROLLER_LOGGER_MODULE_NAME);

  std::string search_str =
      "Error in getting node info for the node 127.0.0.1 or the CXL device is "
      "not present";
  EXPECT_TRUE(is_str_in_log(search_str));

  ASSERT_EQ(grpc_status.ok(), true);
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

TEST(InitControllerTest, InitSuccessWithPubSubConfig) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  boost::property_tree::ptree pt;

  boost::property_tree::read_json(conf_file, pt);
  pt.put("pubsub.port", 5432);

  boost::property_tree::ptree topics;
  boost::property_tree::ptree element1;
  element1.put_value("events");
  boost::property_tree::ptree element2;
  element2.put_value("metrics");

  topics.push_back(std::make_pair("", element1));
  topics.push_back(std::make_pair("", element2));
  pt.add_child("pubsub.topics", topics);
  boost::property_tree::write_json(conf_file, pt);
  FILE *fp = fopen(conf_file.c_str(), "r");
  char buf[4096];
  EXPECT_LE(fread(buf, 4096, 1, fp), 4096);
  fclose(fp);
  std::cout << "PUBSUB conf " << buf << std::endl;

  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  EXPECT_TRUE(svcr->get_state() == true);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, ProcessRASEventWithParseErrorWithMissingField) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  const std::shared_ptr<SLADeviceHelper> g_sla_device_hlpr =
      std::make_shared<SLADeviceHelper>();

  json observations_map;
  observations_map["device_name"] = "1234";

  json json_data;
  json_data["observations"] = observations_map;
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  ProcessRASEvent(json_data, svcr);
  unlink(conf_file.c_str());
}

class NewSLADeviceHelperFakeDeviceInfo : public SLADeviceHelper {
 public:
  NewSLADeviceHelperFakeDeviceInfo() : SLADeviceHelper(){};
  int GetDeviceInfo(std::string device_id, DeviceInfo &device_info) {
    return -1;
  }
};

TEST(InitControllerTest, ProcessRASEventWithSLAHlprGetDeviceInfoFailure) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  const std::shared_ptr<NewSLADeviceHelperFakeDeviceInfo> g_sla_device_hlpr =
      std::make_shared<NewSLADeviceHelperFakeDeviceInfo>();

  json observations_map;
  observations_map["device_id"] = "1234";

  json json_data;
  json_data["observations"] = observations_map;
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  ProcessRASEvent(json_data, svcr);
  unlink(conf_file.c_str());
}

class NewSLADeviceHelperFakeAppInfo : public SLADeviceHelper {
 public:
  NewSLADeviceHelperFakeAppInfo() : SLADeviceHelper(){};
  int GetDeviceInfo(std::string device_id, DeviceInfo &device_info) {
    return 0;
  }
  int GetAppInfo(std::string device_id, App_Info &app_info) { return -1; }
};

TEST(InitControllerTest, ProcessRASEventWithSLAHlprGetAppInfoFailure) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  const std::shared_ptr<NewSLADeviceHelperFakeAppInfo> g_sla_device_hlpr =
      std::make_shared<NewSLADeviceHelperFakeAppInfo>();

  json observations_map;
  observations_map["device_id"] = "1234";

  json json_data;
  json_data["observations"] = observations_map;
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  ProcessRASEvent(json_data, svcr);
  unlink(conf_file.c_str());
}

TEST(InitControllerTest, ProcessSLAEventWithParseErrorWithMissingField) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, CONTROLLER_LOGGER_DEFAULT_SINK_TYPE,
      CONTROLLER_LOGGER_DEFAULT_FILE_COUNT, CONTROLLER_LOGGER_DEFAULT_FILE_SIZE,
      CONTROLLER_LOGGER_DEFAULT_LEVEL);

  const std::shared_ptr<SLADeviceHelper> g_sla_device_hlpr =
      std::make_shared<SLADeviceHelper>();

  json observations_map;
  observations_map["device_id"] = "1234";

  json json_data;
  json_data["observations"] = observations_map;
  ControllerServicer *svcr(new ControllerServicer(conf_file));
  auto server = InitializeServicer(svcr);
  ASSERT_NE(server, nullptr);
  ProcessSLAEvent(json_data, svcr);
  unlink(conf_file.c_str());
}
