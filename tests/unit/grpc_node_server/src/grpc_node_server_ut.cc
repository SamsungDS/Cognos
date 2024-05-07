#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdio.h>
#include <stdlib.h>

#include "framework/framework_mock.grpc.pb.h"
#include "grpc_server.h"

using ::testing::_;
using ::testing::AtLeast;
using ::testing::DoAll;
using ::testing::Return;
using ::testing::SetArgPointee;
using ::testing::StartsWith;
using ::testing::StrEq;

#define FRAMEWORK_LIB_PATH "/usr/local/svk/core/lib64/libsvkframework.so";
#define FEATURES_DIR "/usr/local/svk/core/tests/sample_feature/";

// Mock free function interface
class MockFreeInterface : public SystemLibraryInterface {
 public:
  MOCK_METHOD(void *, get_sym, (void *handle, const char *fn_name),
              (const, override));
  MOCK_METHOD(void *, open_lib, (const char *ft_lib_str), (const, override));
  MOCK_METHOD(int, close_lib, (void *handle), (const, override));
  MOCK_METHOD(int, get_stat, (const char *file, struct stat *fstat),
              (const, override));
};

int create_svk_mgmt_fw_conf_json(std::string conf_file,
                                 std::string framework_lib_path,
                                 std::string fw_conf_file,
                                 std::string sink_type, int log_file_count,
                                 uint64_t log_file_size, std::string log_level,
                                 std::string features_dir) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_node.framework.lib_path", framework_lib_path);
  root.put("svk_mgmt_fw_node.framework.conf_file", fw_conf_file);
  root.put("svk_mgmt_fw_node.cluster.id", "CL_ID_1");
  root.put("svk_mgmt_fw_node.controller.id", "localhost");
  root.put("svk_mgmt_fw_node.controller.port", "9999");
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
    std::string conf_file, std::string framework_lib_path,
    std::string fw_conf_file, std::string sink_type, int log_file_count,
    uint64_t log_file_size, std::string log_level, std::string features_dir) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  root.put("svk_mgmt_fw_node.framework.lib_path", framework_lib_path);
  root.put("svk_mgmt_fw_node.framework.conf_file", fw_conf_file);
  root.put("svk_mgmt_fw_node.cluster.id", "CL_ID_1");
  root.put("svk_mgmt_fw_node.controller.id", "localhost");
  root.put("svk_mgmt_fw_node.controller.port", "9999");
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
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  auto server = Init(svcr);
  ASSERT_NE(server, nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitSuccessWithInvalidFeatureDir) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = (char *)"/tmp/abcd";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  auto server = Init(svcr);
  ASSERT_NE(server, nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitSuccessWithNullServicerObject) {
  auto server = Init(nullptr);
  ASSERT_EQ(server, nullptr);
}

TEST(InitTest, InitWithInvalidLogger) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "console", 10, 1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithInvalidJSONConfFile) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = "";
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(conf_file.c_str(), conf_file.length(), 1, fp);
  fclose(fp);
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithEmptyJSONConfFile) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = "";
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutFWKey) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = "";
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{\"svk_mgmt_fw_node\":{}}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithEmtpyFWKey) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = "";
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content = "{\"svk_mgmt_fw_node\":{\"framework\":{}}}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutFWConfKey) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\"}}}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithCompleteFWentries) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file + "\"}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithJSONConfFileWithoutClusterID) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, DEFAULT_CLUSTER_ID);
  EXPECT_EQ(config.controller_id, DEFAULT_CONTROLLER_ID);
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

TEST(InitTest, InitWithJSONConfFileWithoutController) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, DEFAULT_CONTROLLER_ID);
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

TEST(InitTest, InitWithJSONConfFileWithEmptyController) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, \"controller\":{}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
  node_config config = svcr->get_svk_config();
  EXPECT_EQ(config.cluster_id, "CL_ID");
  EXPECT_EQ(config.controller_id, DEFAULT_CONTROLLER_ID);
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

TEST(InitTest, InitWithJSONConfFileWithMissingControllerPort) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhostx\"}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
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
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9876}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
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
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhostx\", \"port\":8765}, \"node\":{}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
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

TEST(InitTest, InitWithJSONConfFileWithoutNodePort) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhostx\"}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
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

TEST(InitTest, InitWithJSONConfFileWithNode) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhosty\", \"port\":99998}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
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
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  std::string content =
      "{\"svk_mgmt_fw_node\":{\"framework\":{\"lib_path\":\"" +
      framework_lib_path + "\", \"conf_file\":\"" + conf_file +
      "\"}, \"cluster\":{\"id\":\"CL_ID\"}, "
      "\"controller\":{\"id\":\"localhost\", \"port\":9999}, "
      "\"node\":{\"id\":\"localhost\", \"port\":9998}, \"logger\":{}}}";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  std::cout << "content written " << content << std::endl;
  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
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

TEST(InitTest, InitWithEmptyFwLibPath) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = "";
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithEmptyMgmtFWSectionConfFile) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, "",
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithoutMgmtFWInJSONConfFile) {
  SystemLibraryInterface sl;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json_without_mgmt_fw(conf_file, "rotating_file", 10,
                                               1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

TEST(InitTest, InitWithoutMgmtLoggerInJSONConfFile) {
  SystemLibraryInterface sl;
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json_without_logger(conf_file, framework_lib_path,
                                              conf_file, "rotating_file", 10,
                                              1048576, "INFO", features_dir);

  Servicer *svcr(new Servicer(conf_file, sl));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() != nullptr);
  unlink(conf_file.c_str());
}

// Test if stat fails
TEST(InitTest, FailedStatCall) {
  MockFreeInterface dep_inj;
  ON_CALL(dep_inj, get_stat)
      .WillByDefault([&dep_inj](const char *filename, struct stat *fstat) {
        return dep_inj.SystemLibraryInterface::get_stat(filename, fstat);
      });
  EXPECT_CALL(dep_inj, get_stat(_, _)).Times(1).WillOnce(Return(-1));
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, dep_inj));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

// Test if dlopen (open_lib) fails
TEST(InitTest, FailedOpenLibCall) {
  MockFreeInterface dep_inj;
  ON_CALL(dep_inj, get_stat)
      .WillByDefault([&dep_inj](const char *filename, struct stat *fstat) {
        return dep_inj.SystemLibraryInterface::get_stat(filename, fstat);
      });

  EXPECT_CALL(dep_inj, open_lib(_)).Times(1).WillOnce(Return(nullptr));
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, dep_inj));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

// Test if dlsym (get_sym) fails
TEST(InitTest, FailedDlSymInitializeSVKCall) {
  MockFreeInterface dep_inj;
  ON_CALL(dep_inj, get_stat)
      .WillByDefault([&dep_inj](const char *filename, struct stat *fstat) {
        return dep_inj.SystemLibraryInterface::get_stat(filename, fstat);
      });

  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *filename) {
    return dep_inj.SystemLibraryInterface::open_lib(filename);
  });
  ON_CALL(dep_inj, close_lib).WillByDefault([&dep_inj](void *handle) {
    return dep_inj.SystemLibraryInterface::close_lib(handle);
  });
  EXPECT_CALL(dep_inj, get_sym(_, _)).Times(1).WillOnce(Return(nullptr));
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, dep_inj));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  unlink(conf_file.c_str());
}

// Test if dlsym (get_sym) fails
TEST(InitTest, FailedDlSymSVKExecuteSyncCall) {
  MockFreeInterface dep_inj;
  ON_CALL(dep_inj, get_stat)
      .WillByDefault([&dep_inj](const char *filename, struct stat *fstat) {
        return dep_inj.SystemLibraryInterface::get_stat(filename, fstat);
      });

  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *filename) {
    return dep_inj.SystemLibraryInterface::open_lib(filename);
  });
  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.SystemLibraryInterface::get_sym(handle, fn_name);
      });

  EXPECT_CALL(dep_inj, get_sym(_, _)).Times(::testing::AnyNumber());

  EXPECT_CALL(dep_inj, get_sym(_, StrEq("execute_svk_feature_sync")))
      .Times(1)
      .WillOnce(Return(nullptr));
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, dep_inj));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
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
    SystemLibraryInterface sl;
    std::string framework_lib_path = FRAMEWORK_LIB_PATH;
    char *cw_dir = get_current_dir_name();
    std::string features_dir = FEATURES_DIR;

    std::string conf_file = std::string(cw_dir) + "/conf.json";
    create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                                 "rotating_file", 10, 1048576, "INFO",
                                 features_dir);
    Servicer *svcr(new Servicer(conf_file, sl));
    server_ = Init(svcr);

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
    SystemLibraryInterface sl;
    std::string framework_lib_path = FRAMEWORK_LIB_PATH;
    char *cw_dir = get_current_dir_name();
    std::string features_dir = FEATURES_DIR;

    std::string conf_file = std::string(cw_dir) + "/conf.json";
    create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                                 "rotating_file", 10, 1048576, "INFO",
                                 features_dir);
    Servicer *svcr(new Servicer(conf_file, sl));
    server_ = Init(svcr);

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

// Test if dlsym (get_sym) fails
TEST(InitTest, ProcessCommandWithFailedDlSymSVKExecuteSyncCall) {
  MockFreeInterface dep_inj;
  ON_CALL(dep_inj, get_stat)
      .WillByDefault([&dep_inj](const char *filename, struct stat *fstat) {
        return dep_inj.SystemLibraryInterface::get_stat(filename, fstat);
      });

  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *filename) {
    return dep_inj.SystemLibraryInterface::open_lib(filename);
  });
  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.SystemLibraryInterface::get_sym(handle, fn_name);
      });

  EXPECT_CALL(dep_inj, get_sym(_, _)).Times(::testing::AnyNumber());

  EXPECT_CALL(dep_inj, get_sym(_, StrEq("execute_svk_feature_sync")))
      .Times(1)
      .WillOnce(Return(nullptr));
  std::string framework_lib_path = FRAMEWORK_LIB_PATH;
  char *cw_dir = get_current_dir_name();
  std::string features_dir = FEATURES_DIR;
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, framework_lib_path, conf_file,
                               "rotating_file", 10, 1048576, "INFO",
                               features_dir);

  Servicer *svcr(new Servicer(conf_file, dep_inj));
  EXPECT_TRUE(svcr->get_execute_svk_feature_sync_ptr() == nullptr);
  auto server_ = Init(svcr);

  std::unique_ptr<svk::CommandFwk::Stub> fwk_stub_;
  std::shared_ptr<Channel> channel =
      grpc::CreateChannel("127.0.0.1:9998", grpc::InsecureChannelCredentials());
  fwk_stub_ = svk::CommandFwk::NewStub(channel);

  svk::CommandRequest req;
  svk::CommandResponse *resp = new (svk::CommandResponse);
  req.set_feature_id((feature_id)100);
  req.set_node_id("localhost");
  req.set_feature_params("Test=Value");

  FakeClient client(fwk_stub_.get());

  Status status = client.ProcessNodeCommand(req, resp);
  ASSERT_EQ(status.ok(), false);

  unlink(conf_file.c_str());
}
