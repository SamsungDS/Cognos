#include <dirent.h>
#include <fcntl.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>

#include "logic_interface/svk_logic_struct.h"
#include "svk_slat_hlpr.hpp"

using ::testing::_;
using ::testing::Return;
using ::testing::StrEq;

// Format for running code before specific test suite, in this case InitTest
class ConfigTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    slat_conf.put("slat.logic_lib_dir", "/tmp");

    logger_conf.put("log_level", "ERROR");
    logger_conf.put("log_file_name", "slat_conf/slat.log");
    logger_conf.put("log_file_count", 1);
    logger_conf.put("log_file_size", 1048576);
    logger_conf.put("sink_type", "rotating_file");

    slat_conf.put_child("slat.logger", logger_conf);
    boost::property_tree::write_json("slat.json", slat_conf);
  }

  static boost::property_tree::ptree slat_conf;
  static boost::property_tree::ptree logger_conf;
};

// These variables will be global to only the ConfigTest suite
// Since order of execution is not guaranteed, we can only assume these are
// available for that test suite.
boost::property_tree::ptree ConfigTest::slat_conf;
boost::property_tree::ptree ConfigTest::logger_conf;

TEST_F(ConfigTest, MissingLoggerConf) {
  slat_conf.get_child("slat").erase("logger");
  boost::property_tree::write_json("missing_logger_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "missing_logger_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));

  slat_conf.put_child("slat.logger", logger_conf);
  unlink("missing_logger_conf.json");
}

TEST_F(ConfigTest, InvalidSinkType) {
  logger_conf.erase("sink_type");
  logger_conf.put("sink_type", "invalid");
  slat_conf.erase("slat.logger");
  slat_conf.put_child("slat.logger", logger_conf);
  boost::property_tree::write_json("invalid_sink_type.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "invalid_sink_type.json", true);

  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));

  logger_conf.put("log_level", "ERROR");
  slat_conf.put_child("slat.logger", logger_conf);
  unlink("invalid_sink_type.json");
}

TEST_F(ConfigTest, InvalidLogLevel) {
  logger_conf.erase("log_level");
  logger_conf.put("log_level", "invalid");
  slat_conf.erase("slat.logger");
  slat_conf.put_child("slat.logger", logger_conf);
  boost::property_tree::write_json("invalid_log_level.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "invalid_log_level.json", true);

  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));

  logger_conf.put("log_level", "ERROR");
  slat_conf.put_child("slat.logger", logger_conf);
  unlink("invalid_log_level.json");
}

TEST_F(ConfigTest, LoggerConfFailWithoutEnv) {
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
}

TEST_F(ConfigTest, LoggerConfWithoutEnv) {
  mkdir("/etc/svk", 0755);
  boost::property_tree::write_json(SLAT_CONFIG_FILE_DEFAULT, slat_conf);

  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  unlink(SLAT_CONFIG_FILE_DEFAULT);
}

TEST_F(ConfigTest, NoLoggerConfFailure) {
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
}

TEST_F(ConfigTest, InitializeSuccess) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));

  slat_conf.put_child("slat.logger", logger_conf);
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, GetFeatureListFailCase1) {
  EXPECT_EQ(SVK_STATUS_FAIL, get_supported_feature_list(nullptr, nullptr));
}

TEST_F(ConfigTest, GetFeatureListFailCase2) {
  feature_id f_id;

  EXPECT_EQ(SVK_STATUS_FAIL, get_supported_feature_list(&f_id, nullptr));
}

TEST_F(ConfigTest, GetFeatureListSuccess) {
  feature_id f_id;
  char feature_name[128];

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            get_supported_feature_list(&f_id, &feature_name[0]));
  EXPECT_EQ(f_id, feature_id::SLA_TRACKER);
}

TEST_F(ConfigTest, LicenseValidFnFail) {
  EXPECT_EQ(SVK_STATUS_FAIL, is_license_valid(nullptr));
}

TEST_F(ConfigTest, LicenseValidFnSuccess) {
  char license[256];
  EXPECT_EQ(SVK_STATUS_SUCCESS, is_license_valid(&license));
}

TEST_F(ConfigTest, ConfigureDeviceFnFail) {
  EXPECT_EQ(SVK_STATUS_FAIL,
            configure_device_if_any(nullptr, nullptr, 10, nullptr));
}

TEST_F(ConfigTest, ConfigureDeviceFnSuccess) {
  char config_details[256];
  svk_device_ctx device_handles;
  uint64_t length = 256;
  char resp[256];

  EXPECT_EQ(
      SVK_STATUS_SUCCESS,
      configure_device_if_any(&config_details, &device_handles, length, &resp));
}

TEST_F(ConfigTest, ExecuteSyncFnFail) {
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(nullptr, nullptr, nullptr));
}

TEST_F(ConfigTest, ExecuteSyncFnSuccess) {
  svk_pass_thru_cmd cmd;
  svk_input input;
  svk_output output;

  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, ExecuteASyncFnFail) {
  EXPECT_EQ(SVK_STATUS_FAIL, execute_async(nullptr, nullptr));
}

TEST_F(ConfigTest, ExecuteASyncFnSuccess) {
  svk_pass_thru_cmd pass_thru;
  svk_postprocess_fn postprocess_fn;

  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_async(&pass_thru, &postprocess_fn));
}

TEST_F(ConfigTest, CleanupFnFail) {
  EXPECT_EQ(SVK_STATUS_FAIL, clean_up(nullptr));
}

TEST_F(ConfigTest, CleanupFnSuccess) {
  char param[256];
  EXPECT_EQ(SVK_STATUS_SUCCESS, clean_up(&param));
}
