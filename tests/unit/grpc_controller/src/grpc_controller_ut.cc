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

TEST_F(MockTestController, RegisterNode) {
  Status grpc_status;
  std::string cluster_id = "CLUSTER_REGISTER_NODE";
  std::string node_id = "registernode.localdomain.com";
  std::string node_port = "9998";

  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::INFO,
             "RegisterNode UT called");

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_id(cluster_id);
  req->set_node_id(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNode");
  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->status() << std::endl;

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();

  std::string search_str = "Registered the node_id " + node_id + ":" +
                           node_port + " with cluster:" + cluster_id;
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
}

TEST_F(MockTestController, RegisterNodeWithNullClusterID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_node_id("testnode.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), false);
  ASSERT_EQ(grpc_status.error_message(),
            "Invalid input - zero length arg given");
}

TEST_F(MockTestController, RegisterNodeWithNullNodeID) {
  Status grpc_status;

  Client client(CONTROLLER_DEFAULT_ID, CONTROLLER_DEFAULT_PORT);

  svk::RegisterRequest *req(new svk::RegisterRequest());
  svk::RegisterResponse *resp(new svk::RegisterResponse());
  req->set_cluster_id("DUMMY_CLUSTER");
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
  req->set_cluster_id("DUMMY_CLUSTER");
  req->set_node_id("testnode.localdomain.com");

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
  req->set_cluster_id(cluster_id);
  req->set_node_id(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->status() << std::endl;

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->status() << std::endl;

  // Forcefully flush the logs
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
             "Just for flushing logs with RegisterNodeAgain");

  std::ifstream file(CONTROLLER_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  std::string search_str =
      "Found the cluster_id: " + cluster_id + " already registered";
  EXPECT_EQ(true, data.find(search_str) != std::string::npos);
  search_str =
      "Node with node_id " + node_id + ":" + node_port + " already registered";
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
  req->set_cluster_id(cluster_id);
  req->set_node_id(node_id);
  req->set_node_port(node_port);

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->status() << std::endl;

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
  req->set_cluster_id("MY_CLUSTER_ID3");
  req->set_node_id("testnode3.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->status() << std::endl;

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
  req->set_cluster_id("CLUSTER_UNREGISTER_NODE_INVALID_ID");
  req->set_node_id("testnode1.localdomain.com");
  req->set_node_port("9998");

  grpc_status = client.RegisterNode(req, resp);

  ASSERT_EQ(grpc_status.ok(), true);
  std::cout << "Resp message " << resp->status() << std::endl;

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
  req->set_cluster_id(cluster_id_1);
  req->set_node_id(node_id_1);
  req->set_node_port(node_port_1);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  std::cout << "Resp message " << resp->status() << std::endl;

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
  req->set_cluster_id(cluster_id_1);
  req->set_node_id(node_id_1);
  req->set_node_port(node_port_1);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  req->set_cluster_id(cluster_id_2);
  req->set_node_id(node_id_2);
  req->set_node_port(node_port_2);

  grpc_status = client.RegisterNode(req, resp);
  ASSERT_EQ(grpc_status.ok(), true);

  svk_logger_close(CONTROLLER_LOGGER_MODULE_NAME);

  std::cout << "Resp message " << resp->status() << std::endl;

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
