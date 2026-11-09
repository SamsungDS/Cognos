#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdio.h>
#include <stdlib.h>

#include <csignal>
#include <thread>

#include "svc.h"
#include "svc_mgr.h"

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

  root.put("svk_mgmt_fw_svc_mgr.svc_mgr.feat_sm_svcs_dir", "../sample_service");
  root.put("svk_mgmt_fw_svc_mgr.logger.log_level", log_level);
  root.put("svk_mgmt_fw_svc_mgr.logger.log_file_name",
           SVC_MGR_NODE_DEFAULT_LOG_FILE);
  root.put("svk_mgmt_fw_svc_mgr.logger.log_file_count", log_file_count);
  root.put("svk_mgmt_fw_svc_mgr.logger.log_file_size", log_file_size);
  root.put("svk_mgmt_fw_svc_mgr.logger.sink_type", sink_type);

  pt::write_json(json_file, root);

  return 0;
}

int create_svk_mgmt_fw_conf_json_without_logger(std::string conf_file) {
  namespace pt = boost::property_tree;
  pt::ptree root;
  std::ofstream json_file(conf_file);

  pt::write_json(json_file, root);

  return 0;
}

TEST(InitSVCMGRTest, InitSuccess) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(SVC_MGR_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
      SVC_MGR_LOGGER_DEFAULT_FILE_COUNT, SVC_MGR_LOGGER_DEFAULT_FILE_SIZE,
      SVC_MGR_LOGGER_DEFAULT_LEVEL);

  ServiceManager *svcr(new ServiceManager(conf_file));
  ASSERT_NE(svcr, nullptr);
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitSuccessWithDestructor) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(SVC_MGR_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
      SVC_MGR_LOGGER_DEFAULT_FILE_COUNT, SVC_MGR_LOGGER_DEFAULT_FILE_SIZE,
      SVC_MGR_LOGGER_DEFAULT_LEVEL);

  ServiceManager *svcr(new ServiceManager(conf_file));
  ASSERT_NE(svcr, nullptr);
  svcr->~ServiceManager();
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitAndRegisterServices) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  unlink(SVC_MGR_NODE_DEFAULT_LOG_FILE);
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
      SVC_MGR_LOGGER_DEFAULT_FILE_COUNT, SVC_MGR_LOGGER_DEFAULT_FILE_SIZE,
      SVC_MGR_LOGGER_DEFAULT_LEVEL);

  ServiceManager *svcr(new ServiceManager(conf_file));
  ASSERT_NE(svcr, nullptr);
  svcr->ServicesRegister();
  svcr->~ServiceManager();
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitWithInvalidLoggerLevel) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(conf_file, conf_file,
                               SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
                               SVC_MGR_LOGGER_DEFAULT_FILE_COUNT,
                               SVC_MGR_LOGGER_DEFAULT_FILE_SIZE, "INFOX");
  try {
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_EQ(svcr, nullptr);
  } catch (std::exception &e) {
  }
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitWithInvalidLoggerSinkType) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, "console", SVC_MGR_LOGGER_DEFAULT_FILE_COUNT,
      SVC_MGR_LOGGER_DEFAULT_FILE_SIZE, SVC_MGR_LOGGER_DEFAULT_LEVEL);
  try {
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_EQ(svcr, nullptr);
  } catch (std::exception &e) {
    ASSERT_STREQ("Failed to create logger", e.what());
  }
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitWithInvalidJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(conf_file.c_str(), conf_file.length(), 1, fp);
  fclose(fp);
  try {
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_EQ(svcr, nullptr);
  } catch (std::exception &e) {
  }
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitWithEmptyJSONConfFile) {
  char *cw_dir = get_current_dir_name();
  std::string content = "{}";
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  FILE *fp = fopen(conf_file.c_str(), "a+");
  fwrite(content.c_str(), content.length(), 1, fp);
  fclose(fp);
  try {
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_EQ(svcr, nullptr);
  } catch (std::exception &e) {
  }
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, InitWithoutLoggerEntries) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json_without_logger(conf_file);
  try {
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_EQ(svcr, nullptr);
  } catch (std::exception &e) {
  }
  unlink(conf_file.c_str());
}

TEST(InitSVCMGRTest, FailedStatCall) {
  std::string conf_file = "invalid_dir/conf.json";
  try {
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_EQ(svcr, nullptr);
  } catch (std::exception &e) {
  }
  unlink(conf_file.c_str());
}

class MockTestSVCMGR : public ::testing::Test {
 protected:
  MockTestSVCMGR() {}

  void SetUp() override {
    char *cw_dir = get_current_dir_name();
    std::string conf_file = std::string(cw_dir) + "/conf.json";
    create_svk_mgmt_fw_conf_json(
        conf_file, conf_file, SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
        SVC_MGR_LOGGER_DEFAULT_FILE_COUNT, SVC_MGR_LOGGER_DEFAULT_FILE_SIZE,
        SVC_MGR_LOGGER_DEFAULT_LEVEL);
    ServiceManager *svcr(new ServiceManager(conf_file));
    ASSERT_NE(svcr, nullptr);
    EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  }
};

int KillProcess() {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
      SVC_MGR_LOGGER_DEFAULT_FILE_COUNT, SVC_MGR_LOGGER_DEFAULT_FILE_SIZE,
      SVC_MGR_LOGGER_DEFAULT_LEVEL);

  std::thread server_thr(svc_mgr_server_start, conf_file, true);
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

TEST(InitSVCMGRTest, InitSVCMGRWithSignal) {
  GTEST_FLAG_SET(death_test_style, "threadsafe");
  EXPECT_DEATH(KillProcess(), "");
  std::ifstream file(SVC_MGR_NODE_DEFAULT_LOG_FILE);
  std::string data((std::istreambuf_iterator<char>(file)),
                   (std::istreambuf_iterator<char>()));
  file.close();
  EXPECT_EQ(true,
            data.find("Shutting down Service Manager") != std::string::npos);
}

TEST(InitSVCMGRTest, InitSVCMGRInNonBlocking) {
  char *cw_dir = get_current_dir_name();
  std::string conf_file = std::string(cw_dir) + "/conf.json";
  create_svk_mgmt_fw_conf_json(
      conf_file, conf_file, SVC_MGR_LOGGER_DEFAULT_SINK_TYPE,
      SVC_MGR_LOGGER_DEFAULT_FILE_COUNT, SVC_MGR_LOGGER_DEFAULT_FILE_SIZE,
      SVC_MGR_LOGGER_DEFAULT_LEVEL);

  svc_mgr_server_start(conf_file, false);
}

TEST(InitSVCMGRTest, SignalHandlerFunction) { svc_mgr_signal_handler(SIGINT); }
