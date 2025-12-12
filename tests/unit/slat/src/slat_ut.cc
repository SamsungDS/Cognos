#include <dirent.h>
#include <fcntl.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <gtest/internal/gtest-port.h>
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
#define SLAT_LOG_FILE_NAME "/var/log/svk/test_slat.log"
#define MOCK_STRUCT_INIT(...) \
  { __VA_ARGS__ }

#define DEFINE_RETURN_MOCK(fn, ret) \
  bool ut_##fn##_mocked = false;    \
  ret ut_##fn

/**
 * Checks if a given string exists in the log file.
 *
 * @param search_str The string to search for in the log file.
 * @return True if the string is found in the log file, false otherwise.
 */
bool is_str_in_log(std::string search_str) {
  std::string file_name = SLAT_LOG_FILE_NAME;
  // Use this call to flush logs immediately
  svk_logger_flush(SLAT_LOGGER_MODULE_NAME);
  sleep(0.5);

  // Check if the log file exists
  std::ifstream file(file_name);
  if (!file.good()) {
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
    logger_conf.put("log_file_name", SLAT_LOG_FILE_NAME);
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
    publish_app_event(config);
  }
  std::string test_benchmark(slat_benchmark_config &config) {
    return run_benchmark(config);
  }
};

// Publish event with SLA deviation and returning back to normal
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

  app_config.app_current_sla.host_name = "msl-ssg-dummy";
  app_config.app_current_sla.device_name = "msl-ssg-dummy_0";
  app_config.app_current_sla.avgLatencyns = 1000;
  app_config.app_name = "app1";
  app_config.app_pid = "4321";

  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  config.device_advertised_sla = 100;
  config.device_current_sla = 95;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
}

class SLATrackerSvc_BenchMarkThread : public SLATrackerSvc {
 public:
  SLATrackerSvc_BenchMarkThread(uint64_t current_sla) {
    thr_current_sla = current_sla;
  };
  virtual std::string run_benchmark(slat_benchmark_config &config) override {
    std::cout << "RUN BENCHMARK called" << std::endl;
    return "";
  }
  virtual void parse_result(slat_benchmark_config &config,
                            std::string result) override {
    std::cout << "PARSE RESULT called" << std::endl;
    return;
  }
  void spl_benchmarking_thread_fn(void) { benchmarking_thread_fn(); }
  virtual void update_app_sla_with_device_sla(
      slat_benchmark_config &config) override {
    slat_app_sla_config app_config;
    config.device_numa_node = "0";
    config.device_advertised_sla = 100;
    config.device_current_sla = thr_current_sla;
    config.device_sla_tolerance_percent = 10;
    app_config.app_requested_sla_ns = 100;
    app_config.app_sla_tolerance_percent = 10;
    app_config.app_current_sla.host_name = "localhost";
    app_config.app_current_sla.device_name = "localhost_0";
    app_config.app_current_sla.avgLatencyns = 1000;
    app_config.app_name = "app1";
    app_config.app_pid = "4321";

    config.app_sla_list["app1"] = app_config;
    return;
  }
  svk_status my_add_devices_to_sla_tracker(json command_params) {
    return add_devices_to_sla_tracker(command_params);
  }
  void set_device_current_sla(uint64_t current_sla) {
    thr_current_sla = current_sla;
  }

 private:
  uint64_t thr_current_sla;
};

using json = nlohmann::json;

// Benchmarking thread
TEST_F(ConfigTest, BenchmarkingThreadForEvents) {
  slat_conf.put("slat.disable_bg_thread", "false");
  slat_conf.put("slat.benchmark_run_interval", 2);

  boost::property_tree::write_json("slat_conf.json", slat_conf);

  SLATrackerSvc_BenchMarkThread svc(70);
  svc.Initialize("slat_conf.json");

  sleep(2);
  json devices = json::array();
  json device;

  device["device_numa"] = "0";
  device["device_sla_latency_ns"] = 100;
  device["device_id"] = "localhost_0";
  devices.push_back(device);

  // Enable SLA tracking for the devices
  json command_params;
  command_params["app_name"] = "app1";
  command_params["app_pid"] = "1234";
  command_params["app_sla_latency_ns"] = 120;
  command_params["host_name"] = "localhost";
  command_params["logic_module"] = "mlc";
  command_params["devices"] = devices;
  svc.my_add_devices_to_sla_tracker(command_params);

  // Add another app to the same device
  command_params["app_name"] = "app2";
  command_params["app_pid"] = "56789";
  command_params["app_sla_latency_ns"] = 110;
  svc.my_add_devices_to_sla_tracker(command_params);

  sleep(5);
  // Set the current latency to above  the device threshold in the next
  // command cycle to trigger degraded event
  svc.set_device_current_sla(150);
  sleep(5);
  // Set the current latency to lower than the device threshold in the next
  // command cycle to trigger normal event
  svc.set_device_current_sla(90);
  sleep(5);

  // Strip the timestamp related and check the rest of message in the log
  std::string msg =
      "[{\"category\":\"slat\",\"domain\":\"observability\",\"feature_name\":"
      "\"slat\",\"msg\":\"SLA degraded, current observed device latency 150ns, "
      "expected  "
      "100ns\",\"observations\":{\"app_name\":\"app1\",\"app_pid\":\"1234\","
      "\"avg_latency_ns\":0,\"device_id\":\"localhost_0\",\"host_name\":"
      "\"localhost\"},\"severity\":\"warning\",\"source\":\"localhost_0\","
      "\"source_type\":\"device\"";
  EXPECT_EQ(true, is_str_in_log(msg));
  msg =
      "[{\"category\":\"slat\",\"domain\":\"observability\",\"feature_name\":"
      "\"slat\",\"msg\":\"SLA corrected, current observed device latency 90ns, "
      "expected  "
      "100ns\",\"observations\":{\"app_name\":\"app1\",\"app_pid\":\"1234\","
      "\"avg_latency_ns\":0,\"device_id\":\"localhost_0\",\"host_name\":"
      "\"localhost\"},\"severity\":\"info\",\"source\":\"localhost_0\","
      "\"source_type\":\"device\"";
  EXPECT_EQ(true, is_str_in_log(msg));
  msg =
      "[{\"category\":\"slat\",\"domain\":\"observability\",\"feature_name\":"
      "\"slat\",\"msg\":\"SLA corrected, current observed device latency 90ns, "
      "expected  "
      "100ns\",\"observations\":{\"app_name\":\"app2\",\"app_pid\":\"56789\","
      "\"avg_latency_ns\":0,\"device_id\":\"localhost_0\",\"host_name\":"
      "\"localhost\"},\"severity\":\"info\",\"source\":\"localhost_0\","
      "\"source_type\":\"device\"";
  EXPECT_EQ(true, is_str_in_log(msg));
  svc.clean_up();
}

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
  std::string invalid_utf8 = "\xFF\xFE\xFD";

  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = 100;
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  app_config.app_current_sla.host_name = invalid_utf8;
  app_config.app_current_sla.device_name = "msl-ssg-dummy_0";
  app_config.app_current_sla.avgLatencyns = 1000;
  app_config.app_name = "app1";
  app_config.app_pid = "4321";
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
  app_config.app_current_sla.host_name = "dummyhost";
  app_config.app_current_sla.device_name = "dummyhost_0";
  app_config.app_current_sla.avgLatencyns = 1000;
  app_config.app_name = "app1";
  app_config.app_pid = "4321";

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
  app_config.app_current_sla.host_name = "dummyhost";
  app_config.app_current_sla.device_name = "dummyhost_0";
  app_config.app_current_sla.avgLatencyns = 1000;
  app_config.app_name = "app1";
  app_config.app_pid = "4321";
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
}
