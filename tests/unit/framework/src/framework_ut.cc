#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdlib.h>

#include <cstdio>
#include <filesystem>
#include <nlohmann/json.hpp>

#include "framework_service.hpp"
#include "framework_upstream.h"
#include "test_config.h"

using ::testing::_;
using ::testing::Return;
using ::testing::StrEq;

// Mock free function interface
class MockFreeInterface : public featureInterface {
 public:
  MOCK_METHOD(void *, get_sym, (void *handle, const char *fn_name),
              (const, override));
  MOCK_METHOD(void *, open_lib, (const char *ft_lib_str), (const, override));
  MOCK_METHOD(DIR *, open_dir, (const char *dir_str), (const, override));
  MOCK_METHOD(int, wrap_snprintf, (char *str, size_t size, const char *resp),
              (const, override));
};

// Format for running code before specific test suite, in this case InitTest
class ConfigTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    core_conf.put("core.feat_modules_dir", "../../../sample_feature");
    core_conf.put("core.reload_config", false);
    core_conf.put("core.conf_poll_timer", 5);

    logger_conf.put("log_level", "ERROR");
    logger_conf.put("log_file_name", "core_conf/framework.log");
    logger_conf.put("log_file_count", 1);
    logger_conf.put("log_file_size", 1048576);
    logger_conf.put("sink_type", "rotating_file");

    core_conf.put_child("core.logger", logger_conf);
    boost::property_tree::write_json("conf.json", core_conf);
  }

  static boost::property_tree::ptree core_conf;
  static boost::property_tree::ptree logger_conf;
};
// These variables will be global to only the ConfigTest suite
// Since order of execution is not guaranteed, we can only assume these are
// available for that test suite.
boost::property_tree::ptree ConfigTest::core_conf;
boost::property_tree::ptree ConfigTest::logger_conf;

TEST_F(ConfigTest, MissingLoggerConf) {
  core_conf.get_child("core").erase("logger");
  boost::property_tree::write_json("bad_logger_conf.json", core_conf);
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            initialize_svk("bad_logger_conf.json", (void *)&ctx));
  cleanup_svk(&ctx, (void *)&ctx);

  core_conf.put_child("core.logger", logger_conf);
}

TEST_F(ConfigTest, InvalidSinkType) {
  logger_conf.erase("sink_type");
  logger_conf.put("sink_type", "invalid");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
  boost::property_tree::write_json("invalid_sink_type.json", core_conf);
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG,
            initialize_svk("invalid_sink_type.json", (void *)&ctx));

  logger_conf.put("log_level", "ERROR");
  core_conf.put_child("core.logger", logger_conf);
}

TEST_F(ConfigTest, ReloadConfig) {
  core_conf.put("core.reload_config", true);
  boost::property_tree::write_json("conf_reload.json", core_conf);

  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            initialize_svk("conf_reload.json", (void *)&ctx));

  logger_conf.erase("log_level");
  logger_conf.put("log_level", "INFO");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
  boost::property_tree::write_json("conf_reload.json", core_conf);

  cleanup_svk(&ctx, (void *)nullptr);

  logger_conf.erase("log_level");
  logger_conf.put("log_level", "ERROR");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
}

TEST_F(ConfigTest, ReloadInvalidLogLevel) {
  core_conf.put("core.reload_config", true);
  boost::property_tree::write_json("conf_reload.json", core_conf);

  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            initialize_svk("conf_reload.json", (void *)&ctx));

  logger_conf.erase("log_level");
  logger_conf.put("log_level", "invalid");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
  boost::property_tree::write_json("conf_reload.json", core_conf);

  cleanup_svk(&ctx, (void *)nullptr);

  logger_conf.erase("log_level");
  logger_conf.put("log_level", "ERROR");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
}

TEST_F(ConfigTest, ReloadDuplicateConfig) {
  core_conf.put("core.reload_config", true);
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            initialize_svk("conf_reload.json", (void *)&ctx));

  logger_conf.erase("log_level");
  logger_conf.put("log_level", "INFO");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
  boost::property_tree::write_json("conf_reload.json", core_conf);
  // Write same file, sleep to make sure file exists
  sleep(1);
  boost::property_tree::write_json("conf_reload.json", core_conf);
  cleanup_svk(&ctx, (void *)nullptr);

  logger_conf.erase("log_level");
  logger_conf.put("log_level", "ERROR");
  core_conf.erase("core.logger");
  core_conf.put_child("core.logger", logger_conf);
}

TEST_F(ConfigTest, ReloadNonExistentConfig) {
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            initialize_svk("conf_reload.json", (void *)&ctx));
  // Give thread time to poll for the change
  sleep(1);
  remove("conf_reload.json");
  sleep(1);

  cleanup_svk(&ctx, (void *)nullptr);
  core_conf.put("core.reload_config", true);
  boost::property_tree::write_json("conf_reload.json", core_conf);
}

TEST_F(ConfigTest, FailInotifyInit) {
  MockFreeInterface dep_inj;

  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });

  svk_device_ctx ctx;
  FrameworkSvc test_fwsvc1;

  EXPECT_EQ(SVK_STATUS_SUCCESS, test_fwsvc1.FrameworkSvcInit(
                                    "conf_reload.json", (void *)&ctx, dep_inj));
  sleep(1);

  EXPECT_EQ(-1, test_fwsvc1.initialize_inotify(-1));
  test_fwsvc1.FrameworkSvcCleanup((void *)&ctx);
  sleep(1);
  core_conf.put("core.reload_config", true);
  boost::property_tree::write_json("conf_reload.json", core_conf);
}

TEST_F(ConfigTest, FailAddWatchToFile) {
  MockFreeInterface dep_inj;

  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });

  svk_device_ctx ctx;
  FrameworkSvc test_fwsvc1;

  EXPECT_EQ(SVK_STATUS_SUCCESS, test_fwsvc1.FrameworkSvcInit(
                                    "conf_reload.json", (void *)&ctx, dep_inj));

  sleep(1);

  EXPECT_EQ(-1, test_fwsvc1.set_file_watch(-1, "conf_reload.json"));
  sleep(1);
  test_fwsvc1.FrameworkSvcCleanup((void *)&ctx);
}

TEST_F(ConfigTest, FailPollForConfigChange) {
  MockFreeInterface dep_inj;

  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });

  svk_device_ctx ctx;
  FrameworkSvc test_fwsvc1;

  EXPECT_EQ(SVK_STATUS_SUCCESS, test_fwsvc1.FrameworkSvcInit(
                                    "conf_reload.json", (void *)&ctx, dep_inj));

  sleep(1);

  EXPECT_EQ(-1, test_fwsvc1.poll_for_config_change(-1, NULL, NULL, NULL, NULL));
  sleep(1);
  test_fwsvc1.FrameworkSvcCleanup((void *)&ctx);
}

bool is_str_in_log(std::string search_str) {
  svk_logger(CORE_LOGGER_NAME, level_E::ERROR, "Just for flushing logs");

  std::ifstream file(CORE_DEFAULT_LOG_FILE);
  if (!file.good()) {
    const char *message = CORE_DEFAULT_LOG_FILE " doesn't exist";
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, message);
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

// Test successful init by calling extern api with regular dlopen/dlsym
TEST(InitTest, InitSuccess) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Copy the new sample feature to feature module directory for testing
  std::string new_sample_feat_path =
      current_working_dir +
      "/../../../sample_feature/new_sample_feature/lib64/"
      "libsvknew_sample_feature.so";
  std::string temp_sample_feat_path =
      current_working_dir +
      "/../../../sample_feature/libsvktemp_sample_feature.so";
  std::filesystem::copy(new_sample_feat_path, temp_sample_feat_path);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize_svk(conf.c_str(), (void *)&ctx));

  std::string search_str =
      "Feature module libsample_feature.so has been added to feature map using "
      "feature id: 0.";
  EXPECT_TRUE(is_str_in_log(search_str));
  search_str =
      "Feature module libsvknew_sample_feature.so has been added to feature "
      "map using feature name new_sample_feature.";
  EXPECT_TRUE(is_str_in_log(search_str));
  search_str =
      "Feature module libsvktemp_sample_feature.so has been added to feature "
      "map using feature name temp_sample_feature.";
  EXPECT_TRUE(is_str_in_log(search_str));

  std::remove(std::string(temp_sample_feat_path).c_str());
  cleanup_svk(&ctx, (void *)conf.c_str());
}

TEST(InitTest, InitFail) {
  MockFreeInterface dep_inj;

  auto *dummy_init =
      static_cast<int (*)(void *)>([](void *details) { return 1; });

  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });

  EXPECT_CALL(dep_inj, get_sym(_, ::testing::A<const char *>()))
      .Times(14)
      .WillOnce(Return((void *)dummy_init));

  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  FrameworkSvc test_fwsvc1;

  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB,
            test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)&ctx, dep_inj));
  test_fwsvc1.FrameworkSvcCleanup((void *)conf.c_str());
}

TEST(InitTest, FailMapEntry) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  initialize_svk(conf.c_str(), (void *)&ctx);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB,
            initialize_svk(conf.c_str(), (void *)&ctx));
  cleanup_svk(&ctx, (void *)conf.c_str());
}

// Test failed init by giving invalid config file path
TEST(InitTest, InvalidConfigPath) {
  std::string conf = "invalid_conf_path";
  svk_device_ctx ctx;
  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG,
            initialize_svk(conf.c_str(), (void *)&ctx));
}

TEST(InitTest, DefaultConfig) {
  svk_device_ctx ctx;
  std::string conf;
  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG, initialize_svk(nullptr, (void *)&ctx));
}

TEST(InitTest, EnvConfig) {
  svk_device_ctx ctx;
  setenv("SVK_FW_CONFIG", "../../../../../config/test_config.json", 1);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize_svk(nullptr, (void *)&ctx));
  cleanup_svk(&ctx, (void *)&ctx);
}

TEST(InitTest, BadDir) {
  MockFreeInterface dep_inj;
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);
  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");

  FrameworkSvc fw_svc1;
  EXPECT_CALL(dep_inj, open_dir(::testing::A<const char *>()))
      .Times(1)
      .WillOnce(Return(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, fw_svc1.FrameworkSvcInit(
                                 conf.c_str(), (void *)conf.c_str(), dep_inj));
  fw_svc1.FrameworkSvcCleanup((void *)conf.c_str());
}

// Test if dlopen fails
TEST(InitTest, FailedDlopen) {
  MockFreeInterface dep_inj;
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);
  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  FrameworkSvc fw_svc1;
  EXPECT_CALL(dep_inj, open_lib(::testing::A<const char *>()))
      .Times(2)
      .WillOnce(Return(nullptr));
  EXPECT_EQ(
      SVK_STATUS_BAD_FEATURE_LIB,
      fw_svc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj));
  fw_svc1.FrameworkSvcCleanup((void *)conf.c_str());
}

// Test failed init by calling fw svc api and either pass in mock api or
// indicate somehow
TEST(InitTest, FailedDlsym) {
  MockFreeInterface dep_inj;
  // Dummy function pointers to allow dlsym to pass without error
  auto *dummy_init =
      static_cast<int (*)(void *)>([](void *details) { return 0; });
  auto *dummy_get_supported_feature_list =
      static_cast<int (*)(feature_id *, char *)>(
          [](feature_id *feature, char *feature_names) { return 0; });
  auto *dummy_is_license_valid =
      static_cast<int (*)(void *)>([](void *details) { return 0; });
  auto *dummy_exec_sync = static_cast<int (*)(
      svk_pass_thru_cmd *pass_thru, svk_input *input, svk_input *output)>(
      [](svk_pass_thru_cmd *pass_thru, svk_input *input, svk_input *output) {
        return 0;
      });
  auto *dummy_exec_async = static_cast<int (*)(
      svk_pass_thru_cmd *pass_thru, svk_postprocess_fn *postprocess_fn)>(
      [](svk_pass_thru_cmd *pass_thru, svk_postprocess_fn *postprocess_fn) {
        return 0;
      });

  // These make it so the functionality implemented in the interface
  // will be used instead of the mocked child class
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });

  // Set default return values of get_sym to nullptr for testing
  ON_CALL(dep_inj, get_sym(_, StrEq("initialize")))
      .WillByDefault(Return(nullptr));
  ON_CALL(dep_inj, get_sym(_, StrEq("get_supported_feature_list")))
      .WillByDefault(Return(nullptr));
  ON_CALL(dep_inj, get_sym(_, StrEq("is_license_valid")))
      .WillByDefault(Return(nullptr));
  ON_CALL(dep_inj, get_sym(_, StrEq("execute_sync")))
      .WillByDefault(Return(nullptr));
  ON_CALL(dep_inj, get_sym(_, StrEq("execute_async")))
      .WillByDefault(Return(nullptr));
  ON_CALL(dep_inj, get_sym(_, StrEq("clean_up")))
      .WillByDefault(Return(nullptr));

  // Test all error handling by hitting each error handling statement
  // These statements will force get_sym to return dummy function pointers
  // for the cases where we don't want errors
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("initialize")))
      .Times(12)  // 12 times because we are testing 2 different libs
      .WillOnce(Return((void *)dummy_init))
      .WillOnce(Return((void *)dummy_init))
      .WillOnce(Return((void *)dummy_init))
      .WillOnce(Return((void *)dummy_init))
      .WillOnce(Return((void *)dummy_init));
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("get_supported_feature_list")))
      .Times(5)
      .WillOnce(Return((void *)dummy_get_supported_feature_list))
      .WillOnce(Return((void *)dummy_get_supported_feature_list))
      .WillOnce(Return((void *)dummy_get_supported_feature_list))
      .WillOnce(Return((void *)dummy_get_supported_feature_list));
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("is_license_valid")))
      .Times(4)
      .WillOnce(Return((void *)dummy_is_license_valid))
      .WillOnce(Return((void *)dummy_is_license_valid))
      .WillOnce(Return((void *)dummy_is_license_valid));
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("execute_sync")))
      .Times(3)
      .WillOnce(Return((void *)dummy_exec_sync))
      .WillOnce(Return((void *)dummy_exec_sync));
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("execute_async")))
      .Times(2)
      .WillOnce(Return((void *)dummy_exec_async));
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("clean_up")))
      .Times(1)
      .WillOnce(Return(nullptr));

  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  FrameworkSvc test_fwsvc1;
  int run1 =
      test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  test_fwsvc1.FrameworkSvcCleanup((void *)buff);
  int run2 =
      test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  test_fwsvc1.FrameworkSvcCleanup((void *)buff);
  int run3 =
      test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  test_fwsvc1.FrameworkSvcCleanup((void *)buff);
  int run4 =
      test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  test_fwsvc1.FrameworkSvcCleanup((void *)buff);
  int run5 =
      test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  test_fwsvc1.FrameworkSvcCleanup((void *)buff);
  int run6 =
      test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  test_fwsvc1.FrameworkSvcCleanup((void *)buff);

  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, run1);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, run2);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, run3);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, run4);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, run5);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, run6);
}

TEST(ConfigureDeviceTest, ConfigureDevSuccess) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = POWER_THROTTLE;

  svk_device_ctx dummy_config;
  svk_device_ctx device_handle;
  svk_device_ctx dummy_resp;

  EXPECT_EQ(SVK_STATUS_SUCCESS,
            configure_svk_device_if_any(&pass_thru, &dummy_config,
                                        &device_handle, 1, &dummy_resp));
}

TEST(ConfigureDeviceTest, ConfigureDevInvalidFeature) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;

  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;

  svk_device_ctx dummy_config;
  svk_device_ctx device_handle;
  svk_device_ctx dummy_resp;

  EXPECT_EQ(SVK_STATUS_FEATURE_NOT_LOADED,
            configure_svk_device_if_any(&pass_thru, &dummy_config,
                                        &device_handle, 1, &dummy_resp));
}

TEST(ConfigureDeviceTest, ConfigureDevFunctionNotLoaded) {
  MockFreeInterface dep_inj;

  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });
  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });

  EXPECT_CALL(dep_inj, get_sym(_, _)).Times(::testing::AnyNumber());
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("configure_device_if_any")))
      .Times(2)
      .WillRepeatedly(Return(nullptr))
      .RetiresOnSaturation();

  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");

  FrameworkSvc test_fwsvc;
  EXPECT_EQ(
      SVK_STATUS_SUCCESS,
      test_fwsvc.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj));

  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = POWER_THROTTLE;
  pass_thru.len = 0;
  svk_device_ctx dummy_config;
  svk_device_ctx ctx;
  svk_device_ctx dummy_resp;
  EXPECT_EQ(SVK_STATUS_FAIL,
            test_fwsvc.FrameworkSvcConfigureDev(&pass_thru, &dummy_config, &ctx,
                                                1, &dummy_resp));
}

TEST(ExecTest, GetFeatures) {
  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(1024);
  output.len = 1024;

  EXPECT_EQ(0, get_registered_features(&output));
  std::string ret = (char *)output.output_buffer;
  EXPECT_STREQ("{\"feature_list\":[\"new_sample_feature\"]}", ret.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, GetFeaturesTruncatedResp) {
  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(32);
  output.len = 32;

  EXPECT_EQ(SVK_STATUS_FAIL, get_registered_features(&output));
  std::string ret = (char *)output.output_buffer;
  std::cout << ret.length() << std::endl;
  EXPECT_STREQ("{\"feature_list\":[\"new_sample_fe", ret.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, GetFeaturesError) {
  MockFreeInterface dep_inj;
  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });
  EXPECT_CALL(dep_inj, wrap_snprintf(_, _, _)).Times(1).WillOnce(Return(-1));
  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");

  FrameworkSvc test_fwsvc1;
  test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);

  svk_output output;
  EXPECT_EQ(SVK_STATUS_FAIL,
            test_fwsvc1.FrameworkSvcGetRegisteredFeatures(&output, dep_inj));
  test_fwsvc1.FrameworkSvcCleanup((void *)conf.c_str());
}

TEST(ExecTest, ExecuteSyncSuccess) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = POWER_THROTTLE;
  pass_thru.len = 0;
  // Need to test new input/output with json
  svk_input input;
  std::string input_str = "test input";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  std::string node_name = "node1";
  std::string cluster_name = "cluster1";
  EXPECT_EQ(0, set_node_name(node_name.c_str(), node_name.length()));
  EXPECT_EQ(0, set_cluster_name(cluster_name.c_str(), cluster_name.length()));

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(128);
  output.len = 128;
  EXPECT_EQ(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  std::cout << "test exec_sync output buffer: " << (char *)output.output_buffer
            << std::endl;
  std::string search_str =
      "Feature name not given, using feature_id 0 for getting feature details.";
  EXPECT_TRUE(is_str_in_log(search_str));
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, GetSetClusterNodeNameValidationFailureCase) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);
  char node_var[256];
  char cluster_var[256];
  int node_var_length = sizeof(node_var);
  int cluster_var_length = sizeof(cluster_var);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));
  // Invalid pointer
  EXPECT_EQ(SVK_STATUS_FAIL, get_node_name(nullptr, &node_var_length));
  EXPECT_EQ(SVK_STATUS_FAIL, get_cluster_name(nullptr, &cluster_var_length));
  EXPECT_EQ(SVK_STATUS_FAIL, set_node_name(nullptr, node_var_length));
  EXPECT_EQ(SVK_STATUS_FAIL, set_cluster_name(nullptr, cluster_var_length));

  // Valid buffer, but zero length passed
  node_var_length = 0;
  cluster_var_length = 0;
  EXPECT_EQ(SVK_STATUS_FAIL, get_node_name(node_var, &node_var_length));
  EXPECT_EQ(SVK_STATUS_FAIL,
            get_cluster_name(cluster_var, &cluster_var_length));
  EXPECT_EQ(SVK_STATUS_FAIL, set_node_name(node_var, node_var_length));
  EXPECT_EQ(SVK_STATUS_FAIL, set_cluster_name(cluster_var, cluster_var_length));

  node_var_length = sizeof(node_var);
  cluster_var_length = sizeof(cluster_var);

  // Node name or cluster name not set yet
  EXPECT_EQ(SVK_STATUS_FAIL, get_node_name(node_var, &node_var_length));
}

TEST(ExecTest, GetSetClusterNodeNameValidationSuccess) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);
  char node_var[256];
  char cluster_var[256];
  int node_var_length = sizeof(node_var);
  int cluster_var_length = sizeof(cluster_var);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  // cluster_name not set. But success with zero length
  EXPECT_EQ(SVK_STATUS_SUCCESS,
            get_cluster_name(cluster_var, &cluster_var_length));
  EXPECT_EQ(0, cluster_var_length);

  // Set the node name and the cluster name
  std::string node_name = "node1";
  std::string cluster_name = "cluster1";
  node_var_length = sizeof(node_var);
  cluster_var_length = sizeof(cluster_var);
  EXPECT_EQ(0, set_node_name(node_name.c_str(), node_name.length()));
  EXPECT_EQ(0, set_cluster_name(cluster_name.c_str(), cluster_name.length()));

  // Get the node name and cluster name and cross-check
  EXPECT_EQ(SVK_STATUS_SUCCESS, get_node_name(node_var, &node_var_length));
  EXPECT_EQ(SVK_STATUS_SUCCESS,
            get_cluster_name(cluster_var, &cluster_var_length));
  EXPECT_EQ(0, strcmp(node_name.c_str(), node_var));
  EXPECT_EQ(0, strcmp(cluster_name.c_str(), cluster_var));
}

TEST(ExecTest, GetClusterNodeNameValidationFailureWithSmallBuffer) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);
  char node_var[256];
  char cluster_var[256];
  int node_var_length = sizeof(node_var);
  int cluster_var_length = sizeof(cluster_var);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  // cluster_name not set. But success with zero length
  EXPECT_EQ(SVK_STATUS_SUCCESS,
            get_cluster_name(cluster_var, &cluster_var_length));
  EXPECT_EQ(0, cluster_var_length);

  // Set the node name and the cluster name
  std::string node_name = "node1";
  std::string cluster_name = "cluster1";
  node_var_length = sizeof(node_var);
  cluster_var_length = sizeof(cluster_var);
  EXPECT_EQ(0, set_node_name(node_name.c_str(), node_name.length()));
  EXPECT_EQ(0, set_cluster_name(cluster_name.c_str(), cluster_name.length()));

  node_var_length = 3;
  cluster_var_length = 3;
  // Get the node name and cluster name and cross-check
  EXPECT_EQ(SVK_STATUS_INSUFFICIENT_BUFFER,
            get_node_name(node_var, &node_var_length));
  EXPECT_EQ(SVK_STATUS_INSUFFICIENT_BUFFER,
            get_cluster_name(cluster_var, &cluster_var_length));
}

TEST(ExecTest, ExecuteSyncWithStrKey) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  std::string feature_name = "new_sample_feature";
  // Send null-terminated string
  pass_thru.out_format = (void *)feature_name.c_str();
  pass_thru.len = feature_name.length() + 1;

  svk_input input;
  std::string input_str = "test input";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(128);
  output.len = 128;
  EXPECT_EQ(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  std::string search_str =
      "Feature name new_sample_feature given, using feature_name_map for "
      "getting feature details.";
  EXPECT_TRUE(is_str_in_log(search_str));
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, ExecuteSyncFailureFromSampleFeature) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = POWER_THROTTLE;
  pass_thru.len = 0;

  svk_input input;
  std::string input_str = "Passing a SampleFeatureFailure string";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(128);
  output.len = 128;
  EXPECT_NE(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  std::cout << "test exec_sync output buffer: " << (char *)output.output_buffer
            << std::endl;
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, ExecuteSyncInvalidFeatureID) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = (feature_id)100;
  pass_thru.len = 0;

  svk_input input;
  svk_output output;

  EXPECT_EQ(SVK_STATUS_FEATURE_NOT_LOADED,
            execute_svk_feature_sync(&pass_thru, &input, &output));

  cleanup_svk(&ctx, (void *)conf.c_str());
}

TEST(ExecTest, ExecuteSyncFail) {
  MockFreeInterface dep_inj;
  auto *dummy_exec_sync = static_cast<int (*)(
      svk_pass_thru_cmd *pass_thru, svk_input *input, svk_output *output)>(
      [](svk_pass_thru_cmd *pass_thru, svk_input *input, svk_output *output) {
        return 1;
      });
  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });
  EXPECT_CALL(dep_inj, get_sym(_, _)).Times(::testing::AnyNumber());
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("execute_sync")))
      .Times(2)
      .WillRepeatedly(Return((void *)dummy_exec_sync))
      .RetiresOnSaturation();

  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  FrameworkSvc test_fwsvc1;
  test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(), dep_inj);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = feature_id::POWER_THROTTLE;
  pass_thru.len = 0;
  svk_input input;
  svk_output output;
  EXPECT_EQ(SVK_STATUS_FAIL, test_fwsvc1.FrameworkSvcProcessCommand(
                                 &pass_thru, &input, &output, nullptr));
  test_fwsvc1.FrameworkSvcCleanup((void *)conf.c_str());
}

TEST(ExecTest, ExecuteSyncWithPublishEvent) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");

  std::ifstream config_file(conf);
  nlohmann::json orig_data = nlohmann::json::parse(config_file);
  nlohmann::json data = orig_data;
  config_file.close();
  data["core"]["logger"]["log_level"] = "TRACE";

  std::ofstream outFile(conf);
  outFile << data.dump(2);
  outFile.close();

  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  std::string feature_name = "new_sample_feature";
  // Send null-terminated string
  pass_thru.out_format = (void *)feature_name.c_str();
  pass_thru.len = feature_name.length() + 1;

  set_node_name("node1", strlen("node1"));
  set_cluster_name("cluster1", strlen("cluster1"));

  svk_input input;
  std::string input_str = "PublishEvent";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(256);
  output.len = 256;
  EXPECT_EQ(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  std::string search_str =
      "{\"event_header\":{\"cluster_name\":\"cluster1\",\"node_name\":"
      "\"node1\"},\"event_payload\":{\"output_key\":\"output_value\"}}";
  EXPECT_TRUE(is_str_in_log(search_str));
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
  outFile.open(conf, std::ios_base::out | std::ios_base::trunc);
  ASSERT_EQ(true, outFile.is_open());
  outFile << orig_data.dump(2);
  outFile.close();
}

TEST(ExecTest, ExecuteSyncWithPublishEventFailureWithoutNodeNameSet) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");

  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  std::string feature_name = "new_sample_feature";
  // Send null-terminated string
  pass_thru.out_format = (void *)feature_name.c_str();
  pass_thru.len = feature_name.length() + 1;

  // Node Name is not set. The PublishEvent should return failure
  svk_input input;
  std::string input_str = "PublishEvent";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(256);
  output.len = 256;
  EXPECT_NE(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, ExecuteSyncWithInvalidJSONData) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  std::string feature_name = "new_sample_feature";
  // Send null-terminated string
  pass_thru.out_format = (void *)feature_name.c_str();
  pass_thru.len = feature_name.length() + 1;

  set_node_name("node1", strlen("node1"));
  set_cluster_name("cluster1", strlen("cluster1"));

  svk_input input;
  std::string input_str = "InvalidJSONData";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(256);
  output.len = 256;
  EXPECT_NE(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  std::string search_str = "Unable to parse or dump the json data";
  EXPECT_TRUE(is_str_in_log(search_str));
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, ExecuteSyncForPublishEventFailureCheck) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  std::string feature_name = "new_sample_feature";
  // Send null-terminated string
  pass_thru.out_format = (void *)feature_name.c_str();
  pass_thru.len = feature_name.length() + 1;

  set_node_name("node1", strlen("node1"));
  set_cluster_name("cluster1", strlen("cluster1"));

  svk_input input;
  std::string input_str = "FailureCheckForEvent";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();

  svk_output output;
  output.output_buffer = (uint8_t *)malloc(256);
  output.len = 256;
  EXPECT_NE(0, execute_svk_feature_sync(&pass_thru, &input, &output));
  cleanup_svk(&ctx, (void *)conf.c_str());
  free(output.output_buffer);
}

TEST(ExecTest, ExecuteAsyncSuccess) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(0, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_pass_thru_cmd pass_thru;
  svk_postprocess_fn postprocess_fn;

  pass_thru.feat_id = POWER_THROTTLE;
  pass_thru.len = 0;

  EXPECT_EQ(0, execute_svk_feature_async(&pass_thru, &postprocess_fn));

  cleanup_svk(&ctx, (void *)conf.c_str());
}

TEST(ExecTest, ExecuteAsyncFail) {
  MockFreeInterface dep_inj;
  auto *dummy_exec_async = static_cast<int (*)(
      svk_pass_thru_cmd *pass_thru, svk_postprocess_fn *postprocess_fn)>(
      [](svk_pass_thru_cmd *pass_thru, svk_postprocess_fn *post_process_fn) {
        return 1;
      });
  ON_CALL(dep_inj, get_sym)
      .WillByDefault([&dep_inj](void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym(handle, fn_name);
      });
  ON_CALL(dep_inj, open_dir).WillByDefault([&dep_inj](const char *dir_str) {
    return dep_inj.featureInterface::open_dir(dir_str);
  });
  ON_CALL(dep_inj, open_lib).WillByDefault([&dep_inj](const char *ft_lib_str) {
    return dep_inj.featureInterface::open_lib(ft_lib_str);
  });
  EXPECT_CALL(dep_inj, get_sym(_, _)).Times(::testing::AnyNumber());
  EXPECT_CALL(dep_inj, get_sym(_, StrEq("execute_async")))
      .Times(2)
      .WillRepeatedly(Return((void *)dummy_exec_async))
      .RetiresOnSaturation();

  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  FrameworkSvc test_fwsvc1;
  EXPECT_EQ(SVK_STATUS_SUCCESS,
            test_fwsvc1.FrameworkSvcInit(conf.c_str(), (void *)conf.c_str(),
                                         dep_inj));

  svk_pass_thru_cmd pass_thru;
  svk_postprocess_fn postprocess_fn;

  pass_thru.feat_id = POWER_THROTTLE;
  pass_thru.len = 0;

  EXPECT_EQ(SVK_STATUS_FAIL, test_fwsvc1.FrameworkSvcProcessCommand(
                                 &pass_thru, NULL, NULL, &postprocess_fn));

  test_fwsvc1.FrameworkSvcCleanup((void *)conf.c_str());
}

TEST(CleanupTest, Cleanup) {
  char buff[FILENAME_MAX];
  getcwd(buff, FILENAME_MAX);
  std::string current_working_dir(buff);

  // Using relative path to config in SVK core for testing
  std::string conf = TEST_CONFIG_DIR + std::string("/test_config.json");
  svk_device_ctx ctx;
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize_svk(conf.c_str(), (void *)&ctx));

  svk_feature_details details;
  EXPECT_EQ(SVK_STATUS_SUCCESS, cleanup_svk(&ctx, (void *)&details));
}

TEST_F(ConfigTest, InvalidPubSub) {
  core_conf.put("pubsub.transport_type", "grpc");

  boost::property_tree::write_json("bad_pubsub_conf.json", core_conf);
  svk_device_ctx ctx;
  EXPECT_EQ(SVK_STATUS_FAIL,
            initialize_svk("bad_pubsub_conf.json", (void *)&ctx));
}
