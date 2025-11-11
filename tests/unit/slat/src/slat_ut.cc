#include <dirent.h>
#include <fcntl.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>

#include <boost/property_tree/xml_parser.hpp>
#include <nlohmann/json.hpp>

#include "logic_interface/svk_logic_struct.h"
#include "svk_slat.hpp"

using ::testing::_;
using ::testing::Return;
using ::testing::StrEq;

#define MOCK_STRUCT_INIT(...) \
  { __VA_ARGS__ }

#define DEFINE_RETURN_MOCK(fn, ret) \
  bool ut_##fn##_mocked = false;    \
  ret ut_##fn

svk_status my_initialize_logic_module_function(void *init_param) {
  const char *env_string_ilm;
  env_string_ilm = std::getenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_FN_FAIL");
  if (env_string_ilm && strcmp(env_string_ilm, "true") == 0) {
    return SVK_STATUS_FAIL;
  }
  return SVK_STATUS_SUCCESS;
}

svk_status my_get_supported_logic_details_fn(
    svk_logic_module_details *details) {
  const char *env_string_gsld;
  env_string_gsld = std::getenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_FN_FAIL");
  if (env_string_gsld && strcmp(env_string_gsld, "true") == 0) {
    return SVK_STATUS_FAIL;
  }
  return SVK_STATUS_SUCCESS;
}

DEFINE_RETURN_MOCK(dlopen_fn, void *);
void *dlopen_fn(const char *filename, int flags) {
  char *ptr;
  const char *env_string;
  env_string = getenv("SVK_SLAT_DLOPEN_SIM");
  if (env_string && strcmp(env_string, "true") == 0) {
    // Return some valid pointer for simulation purpose
    std::cout << "Returning dummy pointer from dlopen" << std::endl;
    ptr = (char *)malloc(16);
    return (void *)ptr;
  }

  return dlopen(filename, flags);
}

DEFINE_RETURN_MOCK(dlclose_fn, int);
int dlclose_fn(void *handle) {
  const char *env_string;
  env_string = getenv("SVK_SLAT_DLOPEN_SIM");
  if (env_string && strcmp(env_string, "true") == 0) {
    // Return some valid pointer for simulation purpose
    return 0;
  }

  return dlclose(handle);
}

DEFINE_RETURN_MOCK(dlsym_fn, void *);
void *dlsym_fn(void *handle, const char *symbol) {
  const char *env_string_ilm;
  const char *env_string_gsld;

  env_string_ilm = std::getenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR");
  env_string_gsld = std::getenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR");

  if (strcmp(symbol, "initialize_logic_module") == 0) {
    if (env_string_ilm) {
      if (strcmp(env_string_ilm, "nullptr") == 0) {
        std::cout << "ILM pointer is null" << std::endl;
        return nullptr;
      }
      if (strcmp(env_string_ilm, "sim") == 0) {
        std::cout << "ILM pointer is sim" << std::endl;
        return (void *)&my_initialize_logic_module_function;
      }
    }
  }
  if (strcmp(symbol, "get_supported_logic_details") == 0) {
    if (env_string_gsld) {
      if (strcmp(env_string_gsld, "nullptr") == 0) {
        std::cout << "GSLD pointer is null" << std::endl;
        return nullptr;
      }
      if (strcmp(env_string_gsld, "sim") == 0) {
        std::cout << "ILM pointer is sim" << std::endl;
        return (void *)&my_get_supported_logic_details_fn;
      }
    }
  }
  std::cout << "calling DLSYM" << std::endl;

  return dlsym(handle, symbol);
}

// Format for running code before specific test suite, in this case InitTest
class ConfigTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    slat_conf.put("slat.logic_lib_dir", "/tmp");
    slat_conf.put("slat.disable_bg_thread", "true");

    logger_conf.put("log_level", "INFO");
    logger_conf.put("log_file_name", "/var/log/svk/test_slat.log");
    logger_conf.put("log_file_count", 1);
    logger_conf.put("log_file_size", 1048576);
    logger_conf.put("sink_type", "rotating_file");

    slat_conf.put_child("slat.logger", logger_conf);
  }

  static boost::property_tree::ptree slat_conf;
  static boost::property_tree::ptree logger_conf;
};

// These variables will be global to only the ConfigTest suite
// Since order of execution is not guaranteed, we can only assume these are
// available for that test suite.
boost::property_tree::ptree ConfigTest::slat_conf;
boost::property_tree::ptree ConfigTest::logger_conf;

TEST_F(ConfigTest, MissingConf) {
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
}

TEST_F(ConfigTest, MissingLoggerConfSection) {
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

TEST_F(ConfigTest, LoggerConfDefault) {
  char command[256];
  sprintf(command, "mkdir -p %s", FEATURE_MODULE_SLAT_CONFIG_PATH);
  EXPECT_EQ(system(command), 0);
  boost::property_tree::write_json(SLAT_CONFIG_FILE_DEFAULT, slat_conf);

  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  sprintf(command, "rm -rf %s", SVK_FEATURE_MODULE_PATH);
  EXPECT_EQ(system(command), 0);
  unlink(SLAT_CONFIG_FILE_DEFAULT);
}

TEST_F(ConfigTest, NoLoggerConfFailure) {
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
}

TEST_F(ConfigTest, InitializeSuccess) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));

  unlink("slat_conf.json");
}

TEST_F(ConfigTest, InvalidLogicLibDir) {
  slat_conf.erase("slat.logic_lib_dir");
  slat_conf.put("slat.logic_lib_dir", "/tmpx");

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));

  unlink("slat_conf.json");
}

TEST_F(ConfigTest, InvalidLogicLibrary) {
  slat_conf.erase("slat.logic_lib_dir");
  slat_conf.put("slat.logic_lib_dir", "/tmp");

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  int fd = open("/tmp/libunittest.so", O_RDWR | O_CREAT, 0660);
  close(fd);
  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);

  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  unlink("/tmp/libunittest.so");
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, LogicLibDirMissing) {
  FILE *fp = NULL;
  std::string buf = "{\"slat\":{}}";

  fp = fopen("slat_conf_logic.json", "w+");
  fwrite(buf.c_str(), buf.length(), 1, fp);
  fclose(fp);
  setenv("SVK_SLAT_CONFIG", "slat_conf_logic.json", true);
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
  unlink("slat_conf_logic.json");
}

TEST_F(ConfigTest, GetFeatureListFailCase1) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, get_supported_feature_list(nullptr, nullptr));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, GetFeatureListFailCase2) {
  feature_id f_id;

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, get_supported_feature_list(&f_id, nullptr));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, GetFeatureListSuccess) {
  feature_id f_id;
  char feature_name[128];

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_SUCCESS,
            get_supported_feature_list(&f_id, &feature_name[0]));
  EXPECT_EQ(f_id, feature_id::SLA_TRACKER);
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, InitializeLogicModuleNullPtr) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  int fd = open("/tmp/libunittest.so", O_RDWR | O_CREAT, 0660);
  close(fd);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  setenv("SVK_SLAT_DLOPEN_SIM", "true", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "nullptr", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  setenv("SVK_SLAT_DLOPEN_SIM", "false", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "", true);
  unlink("/tmp/libunittest.so");
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, GetSupportedLogicDetailsNullPtr) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  int fd = open("/tmp/libunittest.so", O_RDWR | O_CREAT, 0660);
  close(fd);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  setenv("SVK_SLAT_DLOPEN_SIM", "true", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "sim", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR", "nullptr", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  setenv("SVK_SLAT_DLOPEN_SIM", "false", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR", "", true);
  unlink("/tmp/libunittest.so");
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, InitializeLogicModuleFnFail) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  int fd = open("/tmp/libunittest.so", O_RDWR | O_CREAT, 0660);
  close(fd);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  setenv("SVK_SLAT_DLOPEN_SIM", "true", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "sim", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR", "sim", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_FN_FAIL", "true", true);
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, initialize(nullptr));
  setenv("SVK_SLAT_DLOPEN_SIM", "false", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR", "", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_FN_FAIL", "", true);
  unlink("/tmp/libunittest.so");
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, GetSupportedLogicDetailsFnFail) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  int fd = open("/tmp/libunittest.so", O_RDWR | O_CREAT, 0660);
  close(fd);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  setenv("SVK_SLAT_DLOPEN_SIM", "true", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "sim", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR", "sim", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_FN_FAIL", "false", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_FN_FAIL", "true", true);
  svk_logger("slat", level_E::ERROR,
             "gsld pointer set to null --------------------");
  EXPECT_EQ(SVK_STATUS_BAD_FEATURE_LIB, initialize(nullptr));
  setenv("SVK_SLAT_DLOPEN_SIM", "false", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_PTR", "", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_PTR", "", true);
  setenv("SVK_SLAT_INITIALIZE_LOGIC_MODULE_FN_FAIL", "", true);
  setenv("SVK_SLAT_GET_SUPPORTED_LOGIC_DETAILS_FN_FAIL", "", true);
  unlink("/tmp/libunittest.so");
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, LicenseValidFnFail) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, is_license_valid(nullptr));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, LicenseValidFnSuccess) {
  char license[256];
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_SUCCESS, is_license_valid(&license));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ConfigureDeviceFnFail) {
  void *dummy = (void *)0xdeadbeef;
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL,
            configure_device_if_any(nullptr, nullptr, 10, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL,
            configure_device_if_any(dummy, nullptr, 10, nullptr));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ConfigureDeviceFnSuccess) {
  char config_details[256];
  svk_device_ctx device_handles;
  uint64_t length = 256;
  char resp[256];

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(
      SVK_STATUS_SUCCESS,
      configure_device_if_any(&config_details, &device_handles, length, &resp));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ExecuteSyncAddDevice) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 1;
  svk_input input;
  svk_output output = {};
  output.output_buffer = (uint8_t *)0xdeadbeef;

  using json = nlohmann::json;

  json command;
  command["command_name"] = "add_devices_to_sla_tracker";

  json command_params;
  command_params["app_name"] = "test_app";
  command_params["app_pid"] = "4321";
  command_params["app_sla_latency_ns"] = 10;
  command_params["host_name"] = "test_host";
  command_params["logic_module"] = "test_logic_module";

  json devices = json::array();
  json device;
  device["device_id"] = "testhost_0";
  device["device_numa"] = "0";
  device["device_sla_latency_ns"] = 10;
  devices.push_back(device);
  command_params["devices"] = devices;

  command["command_params"] = command_params;
  std::string cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, ExecuteSyncInvalidCommandName) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 1;
  svk_input input;
  svk_output output = {};

  using json = nlohmann::json;

  json command;
  command["command_name"] = "invalid_command";
  command["command_params"] = json::object();

  std::string cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();

  output.output_buffer = (uint8_t *)0xdeadbeef;

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, ExecuteSyncInvalidJsonReq) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 1;
  svk_input input;
  svk_output output = {};

  std::string invalid = "invalid";

  input.input_buffer = (uint8_t *)&invalid[0];
  input.len = invalid.length();

  output.output_buffer = (uint8_t *)0xdeadbeef;

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, ExecuteSyncAddDeviceInvalidCmdParams) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 1;
  svk_input input;
  svk_output output = {};

  using json = nlohmann::json;

  json command;
  command["command_name"] = "add_devices_to_sla_tracker";
  json command_params = json::object();
  command["command_params"] = command_params;

  std::string cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();
  input.len = command.dump().length();

  output.output_buffer = (uint8_t *)0xdeadbeef;

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));

  command_params["app_sla_latency_ns"] = 10;

  std::string str(65, ' ');
  command_params["app_name"] = str;
  command_params["app_pid"] = "4321";
  command["command_params"] = command_params;
  cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();
  input.len = command.dump().length();
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
  command_params["app_name"] = "test_app";
  command_params["app_pid"] = "4321";

  command_params["host_name"] = str;
  command["command_params"] = command_params;
  cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();
  input.len = command.dump().length();
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
  command_params["host_name"] = "test_host";

  command_params["logic_module"] = str;
  command["command_params"] = command_params;
  cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();
  input.len = command.dump().length();
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, RemoveDevicesFromSLATrackerSuccess) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 1;
  svk_input input;
  svk_output output = {};
  output.output_buffer = (uint8_t *)0xdeadbeef;

  using json = nlohmann::json;

  json command;
  command["command_name"] = "remove_devices_from_sla_tracker";

  json command_params;
  json devices = json::array();
  json device;
  device["device_numa"] = "0";
  devices.push_back(device);
  command_params["devices"] = devices;

  command["command_params"] = command_params;
  std::string cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();

  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, RemoveDevicesFromSLATrackerInvalidJSONArray) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 1;
  svk_input input;
  svk_output output = {};
  output.output_buffer = (uint8_t *)0xdeadbeef;

  using json = nlohmann::json;

  json command;
  command["command_name"] = "remove_devices_from_sla_tracker";

  json command_params;
  json devices = json::array();
  command_params["invalid"] = devices;

  command["command_params"] = command_params;
  std::string cmd_str = command.dump();
  input.input_buffer = (uint8_t *)&cmd_str[0];
  input.len = cmd_str.length();

  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
}

TEST_F(ConfigTest, ExecuteSyncFnFail) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  svk_pass_thru_cmd cmd;
  cmd.len = 0;
  svk_input input;
  svk_output output = {};

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(nullptr, nullptr, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, nullptr, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
  input.input_buffer = (uint8_t *)0xdeadbeef;
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));

  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ExecuteSyncFnFailWithEmptyInputBuffer) {
  svk_pass_thru_cmd cmd;
  cmd.len = 0;
  svk_input input;
  svk_output output;

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ExecuteSyncFnFailWithInvalidLogicModule) {
  svk_pass_thru_cmd cmd;
  cmd.len = 0;
  svk_input input;
  svk_output output;

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  memset((char *)&input, 0, sizeof(input));
  input.input_buffer = (uint8_t *)malloc(1024);
  strcpy((char *)input.input_buffer, "logic_module=InvalidLogic");
  input.len = strlen("logic_module=InvalidLogic");
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&cmd, &input, &output));
  free(input.input_buffer);
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ExecuteASyncFnFail) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_async(nullptr, nullptr));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, ExecuteASyncFnSuccess) {
  svk_pass_thru_cmd pass_thru;
  svk_postprocess_fn postprocess_fn;

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_async(&pass_thru, &postprocess_fn));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, CleanupFnFail) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, clean_up(nullptr));
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, CleanupFnSuccess) {
  char param[256];
  boost::property_tree::write_json("slat_conf.json", slat_conf);

  setenv("SVK_SLAT_CONFIG", "slat_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(SVK_STATUS_SUCCESS, clean_up(&param));
  unlink("slat_conf.json");
}

DEFINE_RETURN_MOCK(publish_data, int);
int publish_data(char *topic, uint8_t *payload_data, uint64_t data_len) {
  if (ut_publish_data_mocked) {
    return ut_publish_data;
  }
  char *env_string = std::getenv("SVK_SLAT_SKIP_PUBLISHER_INIT");
  if (env_string && strcmp(env_string, "true") == 0) {
    return -1;
  } else {
    return 0;
  }
}

class SLATrackerSvc_Test : public SLATrackerSvc {
 public:
  SLATrackerSvc_Test(){};
  void test_publish_data(slat_benchmark_config &config) {
    std::cout << "TEST PUBLISH DATA CALLED" << std::endl;
    publish_app_degraded_sla(config);
  }
  std::string test_benchmark(slat_benchmark_config &config) {
    return run_benchmark(config);
  }
};

TEST_F(ConfigTest, PublishSuccess) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  SLATrackerSvc_Test svc;
  svc.Initialize("slat_conf.json");

  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = "0";
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  strcpy(app_config.app_current_sla.host_name, "msl-ssg-dummy");
  strcpy(app_config.app_current_sla.app_name, "app1");
  strcpy(app_config.app_current_sla.app_pid, "4321");
  strcpy(app_config.app_current_sla.device_name, "0");
  app_config.app_current_sla.avgLatencyns = 1000;
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
}

using json = nlohmann::json;

// Create mock interface for the publish_event_data_to_core by default
// The core framework is required for this API to run as there is node/cluster
// related registration as prerequisite.
DEFINE_RETURN_MOCK(publish_event_data_to_core, int);
int publish_event_data_to_core(char *filter, uint8_t *data, uint64_t data_len) {
  if (ut_publish_event_data_to_core_mocked) {
    return ut_publish_event_data_to_core;
  }

  return 0;
}

TEST_F(ConfigTest, SLATWithJSONException) {
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  SLATrackerSvc_Test svc;
  svc.Initialize("slat_conf.json");
  char invalid_utf8[] = {'H', 'e', 'l', 'l', 'o', '\x80', '\0'};

  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = 100;
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  strcpy(app_config.app_current_sla.host_name, invalid_utf8);
  strcpy(app_config.app_current_sla.app_name, "app1");
  strcpy(app_config.app_current_sla.app_pid, "4321");
  strcpy(app_config.app_current_sla.device_name, "0");
  app_config.app_current_sla.avgLatencyns = 1000;
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
}

TEST_F(ConfigTest, PublishFailure) {
  EXPECT_EQ(setenv("SVK_SLAT_SKIP_PUBLISHER_INIT", "true", 1), 0);
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  SLATrackerSvc_Test svc;
  svc.Initialize("slat_conf.json");
  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = 100;
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  strcpy(app_config.app_current_sla.host_name, "msl-ssg-dummy");
  strcpy(app_config.app_current_sla.app_name, "app1");
  strcpy(app_config.app_current_sla.app_pid, "4321");
  strcpy(app_config.app_current_sla.device_name, "0");
  app_config.app_current_sla.avgLatencyns = 1000;
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
  EXPECT_EQ(setenv("SVK_SLAT_SKIP_PUBLISHER_INIT", "false", 1), 0);
}

TEST_F(ConfigTest, PublishEventToCoreFailure) {
  ut_publish_event_data_to_core_mocked = true;
  ut_publish_event_data_to_core = -1;

  boost::property_tree::write_json("slat_conf.json", slat_conf);
  SLATrackerSvc_Test svc;
  svc.Initialize("slat_conf.json");
  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = 100;
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  strcpy(app_config.app_current_sla.host_name, "msl-ssg-dummy");
  strcpy(app_config.app_current_sla.app_name, "app1");
  strcpy(app_config.app_current_sla.app_pid, "4321");
  strcpy(app_config.app_current_sla.device_name, "0");
  app_config.app_current_sla.avgLatencyns = 1000;
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
}
