#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdio.h>
#include <stdlib.h>

#include <csignal>
#include <thread>

#include "framework/framework_mock.grpc.pb.h"
#include "grpc_server.h"
#include "grpc_server_hlpr.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StartsWith;
using ::testing::StrEq;

#define FEATURES_DIR "/usr/local/svk/core/tests/sample_feature/";

int create_svk_mgmt_fw_conf_json(std::string conf_file,
                                 std::string fw_conf_file,
                                 std::string sink_type, int log_file_count,
                                 uint64_t log_file_size, std::string log_level,
                                 std::string features_dir) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_node.framework.conf_file", fw_conf_file);
  root.put("svk_mgmt_fw_node.cluster.id", "CL_ID_1");
  root.put("svk_mgmt_fw_node.controller.id", "");
  root.put("svk_mgmt_fw_node.controller.port", "");
  root.put("svk_mgmt_fw_node.node.id", "localhost");
  root.put("svk_mgmt_fw_node.node.port", "9998");
  root.put("svk_mgmt_fw_node.logger.log_level", log_level);
  root.put("svk_mgmt_fw_node.logger.log_file_name",
           "/var/log/svk/svk_mgmt_fw_node.log");
  root.put("svk_mgmt_fw_node.logger.log_file_count", log_file_count);
  root.put("svk_mgmt_fw_node.logger.log_file_size", log_file_size);
  root.put("svk_mgmt_fw_node.logger.sink_type", sink_type);

  root.put("core.feat_modules_dir", features_dir);
  root.put("core.logger.log_level", log_level);
  root.put("core.logger.log_file_name", "/var/log/svk/svk_framework.log");
  root.put("core.logger.log_file_count", log_file_count);
  root.put("core.logger.log_file_size", log_file_size);
  root.put("core.logger.sink_type", sink_type);
  pt::write_json(json_file, root);

  return 0;
}

int create_svk_mgmt_fw_conf_json_without_mgmt_fw(
    std::string conf_file, std::string sink_type, int log_file_count,
    uint64_t log_file_size, std::string log_level, std::string features_dir) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("core.feat_modules_dir", features_dir);
  root.put("core.logger.log_level", log_level);
  root.put("core.logger.log_file_name", "/var/log/svk/svk_framework.log");
  root.put("core.logger.log_file_count", log_file_count);
  root.put("core.logger.log_file_size", log_file_size);
  root.put("core.logger.sink_type", sink_type);
  pt::write_json(json_file, root);

  return 0;
}

int create_svk_mgmt_fw_conf_json_without_logger(
    std::string conf_file, std::string fw_conf_file, std::string sink_type,
    int log_file_count, uint64_t log_file_size, std::string log_level,
    std::string features_dir) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_node.framework.conf_file", fw_conf_file);
  root.put("svk_mgmt_fw_node.cluster.id", "CL_ID_1");
  root.put("svk_mgmt_fw_node.controller.id", "");
  root.put("svk_mgmt_fw_node.controller.port", "");
  root.put("svk_mgmt_fw_node.node.id", "localhost");
  root.put("svk_mgmt_fw_node.node.port", "9998");

  root.put("core.feat_modules_dir", features_dir);
  root.put("core.logger.log_level", log_level);
  root.put("core.logger.log_file_name", "/var/log/svk/svk_framework.log");
  root.put("core.logger.log_file_count", log_file_count);
  root.put("core.logger.log_file_size", log_file_size);
  root.put("core.logger.sink_type", sink_type);
  pt::write_json(json_file, root);

  return 0;
}

TEST(InitTest, InitSuccess) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitSuccessWithInvalidFeatureDir) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = (char *)"/tmp/abcd";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  auto server = InitializeNodeServicer(svcr);
  ASSERT_EQ(server, nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitSuccessWithNullServicerObject) {
  auto server = InitializeNodeServicer(nullptr);
  ASSERT_EQ(server, nullptr);
}

TEST(InitTest, InitWithInvalidLogger) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "console", 10, 1048576,
                               "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithInvalidJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(conf_file.c_str(), conf_file.length(), 1, fp);
  fclose(fp);
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithEmptyJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutFWKey) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{\"svk_mgmt_fw_node\":{}}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmtpyFWKey) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{\"svk_mgmt_fw_node\":{\"framework\":{}}}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutFWConfKey) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{\"svk_mgmt_fw_node\":{\"framework\":{}}}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithCompleteFWentries) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}}, \"core\":{\"feat_modules_dir\":\"" + features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutClusterID) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{}}, \"core\":{\"feat_modules_dir\":\"" + features_dir +
      "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "");
  EXPECT_EQ(config.node_id, DEFAULT_NODE_ID);
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);

  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutController) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.node_id, DEFAULT_NODE_ID);
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmptyController) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, \"controller\":{}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.node_id, DEFAULT_NODE_ID);
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);

  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithMissingControllerPort) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhostx\"}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, "localhostx");
  EXPECT_EQ(config.controller_port, DEFAULT_CONTROLLER_PORT);
  EXPECT_EQ(config.node_id, DEFAULT_NODE_ID);
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);

  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutNode) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9876}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, "localhost");
  EXPECT_EQ(config.controller_port, "9876");
  EXPECT_EQ(config.node_id, DEFAULT_NODE_ID);
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmptyNode) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhostx\", \"port\":8765}, \"node\":{}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, "localhostx");
  EXPECT_EQ(config.controller_port, "8765");
  EXPECT_EQ(config.node_id, DEFAULT_NODE_ID);
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmptyNodeID) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"\", \"port\":9999}, "
      "\"node\":{\"id\":\"\"}}, \"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  EXPECT_TRUE(server == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutNodePort) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhostx\"}}, \"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, "localhost");
  EXPECT_EQ(config.controller_port, "9999");
  EXPECT_EQ(config.node_id, "localhostx");
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmptyNodePort) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhostx\", \"port\":\"\"}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  EXPECT_TRUE(server == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithNode) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhosty\", \"port\":99998}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, "localhost");
  EXPECT_EQ(config.controller_port, "9999");
  EXPECT_EQ(config.node_id, "localhosty");
  EXPECT_EQ(config.node_port, "99998");
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmptyLogger) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhost\", \"port\":9998}, \"logger\":{}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, "localhost");
  EXPECT_EQ(config.controller_port, DEFAULT_CONTROLLER_PORT);
  EXPECT_EQ(config.node_id, "localhost");
  EXPECT_EQ(config.node_port, DEFAULT_NODE_PORT);
  EXPECT_EQ(config.log_level, MGMT_FW_LOGGER_DEFAULT_LEVEL);
  EXPECT_EQ(config.log_filename, MGMT_FW_NODE_DEFAULT_LOG_FILE);
  EXPECT_EQ(config.log_file_count, MGMT_FW_LOGGER_DEFAULT_FILE_COUNT);
  EXPECT_EQ(config.log_file_size, MGMT_FW_LOGGER_DEFAULT_FILE_SIZE);
  EXPECT_EQ(config.log_sink_type, MGMT_FW_LOGGER_DEFAULT_SINK_TYPE);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithEmptyMgmtFWSectionConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, "", "rotating_file", 10, 1048576,
                               "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithoutMgmtFWInJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json_without_mgmt_fw(conf_file, "rotating_file", 10,
                                               1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithoutMgmtLoggerInJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json_without_logger(
      conf_file, conf_file, "rotating_file", 10, 1048576, "INFO", features_dir);
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == true);
  unlink(conf_file.c_str());
}

// Test if stat fails
TEST(InitTest, FailedStatCall) {
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = "invalid_dir/conf.json";
  Servicer *svcr(new Servicer(conf_file));
  EXPECT_TRUE(svcr->get_state() == false);
  unlink(conf_file.c_str());
}

class FakeClient {
 public:
  explicit FakeClient(svk::CommandFwk::StubInterface *stub) : stub_(stub) {}
  Status ProcessNodeCommand(const svk::CommandRequest req,
                            svk::CommandResponse *resp) {
    ClientContext ctxt;
    Status status = stub_->ProcessNodeCommand(&ctxt, req, resp);
    if (!status.ok()) {
      std::cout << "ProcessCommand rpc failed: " << status.error_message()
                << std::endl;
    }
    return status;
  }
  void ResetStub(svk::CommandFwk::StubInterface *stub) { stub_ = stub; }

 private:
  svk::CommandFwk::StubInterface *stub_;
};

class MockTest : public ::testing::Test {
 protected:
  MockTest() {}

  void SetUp() override {
    char *cw_dir = get_current_dir_name();
    std::string features_dir = FEATURES_DIR;

    std::string conf_file = std::string(cw_dir) + "/conf.json";
    create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                                 1048576, "INFO", features_dir);
    Servicer *svcr(new Servicer(conf_file));
    server_ = InitializeNodeServicer(svcr);

    ASSERT_NE(server_, nullptr);
  }

  void TearDown() override { server_->Shutdown(); }

  void ResetStub() {
    std::shared_ptr<Channel> channel = grpc::CreateChannel(
        "127.0.0.1:9998", grpc::InsecureChannelCredentials());
    ;
    fwk_stub_ = svk::CommandFwk::NewStub(channel);
    ;
  }

  std::unique_ptr<svk::CommandFwk::Stub> fwk_stub_;
  std::shared_ptr<Server> server_;
};

TEST_F(MockTest, ProcessCommandMock) {
  ResetStub();
  FakeClient client(fwk_stub_.get());
  svk::MockCommandFwkStub stub;
  svk::CommandResponse resp1;
  svk::CommandResponse_NodeResponse *node_response = resp1.add_node_responses();
  node_response->set_output("hello world");
  EXPECT_CALL(stub, ProcessNodeCommand(_, _, _))
      .Times(AtLeast(1))
      .WillOnce(DoAll(SetArgPointee<2>(resp1), Return(Status::OK)));
  client.ResetStub(&stub);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_node_id("node.dummy.net");
  req.set_feature_params("Test=Value");

  Status status = client.ProcessNodeCommand(req, resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "Resp message " << resp->node_responses(0).output() << std::endl;
}

class GRPCServer : public ::testing::Test {
 protected:
  GRPCServer() {}

  void SetUp() override {
    char *cw_dir = get_current_dir_name();
    std::string features_dir = FEATURES_DIR;

    std::string conf_file = std::string(cw_dir) + "/conf.json";
    create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                                 1048576, "INFO", features_dir);
    Servicer *svcr(new Servicer(conf_file));
    server_ = InitializeNodeServicer(svcr);

    ASSERT_NE(server_, nullptr);
  }

  void TearDown() override { server_->Shutdown(); }

  void ResetStub() {
    std::shared_ptr<Channel> channel = grpc::CreateChannel(
        "127.0.0.1:9998", grpc::InsecureChannelCredentials());
    fwk_stub_ = svk::CommandFwk::NewStub(channel);
  }

  std::shared_ptr<Server> server_;
  std::unique_ptr<svk::CommandFwk::Stub> fwk_stub_;
};

TEST_F(GRPCServer, ProcessNodeCommandWithInvalidFeatureID) {
  ResetStub();
  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)100);
  req.set_node_id("localhost");
  req.set_feature_params("Test=Value");

  FakeClient client(fwk_stub_.get());

  Status status = client.ProcessNodeCommand(req, resp);
  ASSERT_EQ(status.ok(), false);
}

TEST_F(GRPCServer, ProcessSampleCommand) {
  ResetStub();
  FakeClient client(fwk_stub_.get());
  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_node_id("node.dummy.net");
  req.set_feature_params("Test=Value");

  Status status = client.ProcessNodeCommand(req, resp);
  ASSERT_EQ(status.ok(), true);
  std::cout << "ProcessSampleCommand Output: "
            << resp->node_responses(0).output() << std::endl;
  EXPECT_THAT(resp->node_responses(0).output().c_str(),
              StartsWith("sample_key=value"));
}

TEST_F(GRPCServer, ProcessSampleCommandStrKey) {
  ResetStub();
  FakeClient client(fwk_stub_.get());
  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_name("new_sample_feature");
  req.set_node_id("node.dummy.net");
  req.set_command_params("{\"sample_key\":\"sample_value\"}");
  req.set_command_name("sample_command");

  Status status = client.ProcessNodeCommand(req, resp);
  std::cout << "ProcessSampleCommand Output: "
            << resp->node_responses(0).output() << std::endl;
  EXPECT_THAT(resp->node_responses(0).output().c_str(),
              StartsWith("{\"output_key\":\"output_value\"}"));
}

TEST_F(GRPCServer, ProcessSampleCommandStrKeyInvalidJson) {
  ResetStub();
  FakeClient client(fwk_stub_.get());
  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_name("sample_feature");
  req.set_node_id("node.dummy.net");
  req.set_command_params("invalid");
  req.set_command_name("sample_command");

  Status status = client.ProcessNodeCommand(req, resp);
  EXPECT_EQ(status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_THAT(status.error_message(),
              StartsWith("Json parsing error in ProcessNodeCommand:"));
}

TEST_F(GRPCServer, ProcessSampleCommandBadNameOrID) {
  ResetStub();
  FakeClient client(fwk_stub_.get());
  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)-1);

  Status status = client.ProcessNodeCommand(req, resp);
  EXPECT_EQ(status.error_code(), grpc::INVALID_ARGUMENT);
  EXPECT_THAT(
      status.error_message(),
      StartsWith(
          "ProcessNodeCommand received invalid feature_id and feature_name"));
}

TEST_F(GRPCServer, ProcessSampleCommandWithFailure) {
  ResetStub();
  FakeClient client(fwk_stub_.get());
  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)0);
  req.set_node_id("node.dummy.net");
  req.set_feature_params("Testing for SampleFeatureFailure");

  Status status = client.ProcessNodeCommand(req, resp);
  ASSERT_EQ(status.ok(), false);
  EXPECT_THAT(status.error_message(), StartsWith("Failed to run command"));

  std::cout << "OUTPUT UT: " << status.error_message() << std::endl;
}

int KillProcess() {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;

  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  std::thread server_thr(StartNodeServer, conf_file, true);
  // Sleep for a while for the server process to stablize
  sleep(3);
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "sending the signal to kill the process");
  // Raise the interrupt signal for the server to go down gracefully
  std::raise(SIGINT);
  // Wait for > 5 seconds for the signal handler to be processed on the server
  // node
  sleep(7);
  unlink(conf_file.c_str());
  return 0;
}

TEST(InitTest, InitNodeServerWithSignal) {
  GTEST_FLAG_SET(death_test_style, "threadsafe");
  EXPECT_DEATH(KillProcess(), "");
  std::ifstream file(MGMT_FW_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, data.find("Received signal 2") != std::string::npos);
  EXPECT_EQ(true,
            data.find("gRPC Node server is shutdown") != std::string::npos);
  unlink(MGMT_FW_NODE_DEFAULT_LOG_FILE);
}

TEST(InitTest, StartNodeServerWithInvalidFeatureDir) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = (char *)"/tmp/abcd";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  int status = StartNodeServer(conf_file, false);
  ASSERT_EQ(status, -1);
  unlink(conf_file.c_str());
  std::ifstream file(MGMT_FW_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true, data.find("Received signal 2") == std::string::npos);
  unlink(MGMT_FW_NODE_DEFAULT_LOG_FILE);
}

TEST(InitTest, InitNodeServerInNonBlocking) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;

  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  int status = StartNodeServer(conf_file, false);
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "InitNodeServerInNonBlocking UT");
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
             "Flush the logs after InitNodeServerInNonBlocking UT");

  ASSERT_EQ(status, 0);
}

TEST(InitTest, SignalHandlerFunction) { signal_node_handler(SIGINT); }

TEST(InitTest, SetNodeStatusFail) {
  node_config conf;
  conf.node_name = "localhost";
  conf.controller_id = "localhost";
  conf.controller_port = "9998";

  int status = SetNodeStatus(conf, "offline");
  ASSERT_EQ(status, -1);
}

TEST(InitTest, InitSuccessWithDestructor) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  auto server = InitializeNodeServicer(svcr);
  ASSERT_NE(server, nullptr);
  EXPECT_TRUE(svcr->get_state() == true);
  svcr->~Servicer();
  unlink(conf_file.c_str());
}

TEST(InitTest, StartNodeServerWithServicerFailure) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhosty\", \"port\":99998}}, "
      "\"core\":{\"feat_modules_dir\":\"\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "StartNodeServerWithServicerFailure: content written " << content
            << std::endl;

  int ret = StartNodeServer(conf_file, false);
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "StartNodeServerWithServicerFailure UT");
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
             "Flush the logs after StartNodeServerWithServicerFailure UT");

  ASSERT_NE(ret, 0);
  unlink(conf_file.c_str());
}

TEST(InitTest, StartNodeServerWithInitializeNodeServicerFailure) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhosty\", \"port\":99998}}, "
      "\"core\":{\"feat_modules_dir\":\"" +
      features_dir + "\"}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout
      << "StartNodeServerWithInitializeNodeServicerFailure: content written "
      << content << std::endl;

  int ret = StartNodeServer(conf_file, false);
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::INFO,
             "StartNodeServerWithInitializeNodeServicerFailure UT");
  svk_logger(MGMT_FW_LOGGER_MODULE_NAME, level_E::ERROR,
             "Flush the logs after "
             "StartNodeServerWithInitializeNodeServicerFailure UT");

  ASSERT_NE(ret, 0);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitStartServerSuccessWithDestructor) {
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file, "rotating_file", 10,
                               1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file));
  svcr->~Servicer();
  unlink(conf_file.c_str());
}

TEST(InitTest, InitStartServerWithNullConfFile) {
  int ret = StartNodeServer("", true);
  ASSERT_NE(ret, 0);
}
