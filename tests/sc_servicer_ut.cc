#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <cstdio>
#include <fstream>
#include <iostream>

#include "framework_downstream.h"
#include "log_utils.h"
#include "sc_test_utils.h"
#include "sc_dev_manager.h"
#include "sc_global.h"
#include "sc_mbox.h"
#include "sc_servicer.h"
#include "sc_servicer_internal.h"
#include "sc_test_cxl_adapter.h"
#include "tuner.h"

extern "C" {
#include "jansson.h"
#include "mbox_a1.h"
}

#define DELIMITER ","
#define LOG_CONF_FILE "log.conf"

using namespace std;

extern DeviceManager* g_dev_mgr;
//DeviceManager* g_dev_mgr = nullptr;

// Global instance
sc_global cxl_global;
const std::string json_filepath = "cxl.conf";
const std::string input_conf_path = "input.conf";

using ::testing::_;
using ::testing::Return;

// function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);

class MockScGlobal : public sc_global {
 public:
  MOCK_METHOD(int, g_create_mbox, (StaticPortInfo*), ());
  MOCK_METHOD(FabricManager*, find_fm, (sc_id id), ());
  MOCK_METHOD(std::vector<sc_id>, get_fm_keys, (), ());
};

// Test fixture
MockScGlobal mock_cxl_global;

class ServicerTest : public ::testing::Test {
 protected:
  std::string temp_filename;
  TestCXLDeviceAdapter testAdapter;

  void SetUp() override {
    cxl_global = mock_cxl_global;
    temp_filename.clear();

    // Valid CXL Config
    std::string valid_json = R"({
        "switch": {
            "ip_address": "192.168.1.1"
        }
    })";
    create_file("valid_cxl.json", valid_json);
    // Config file missing "switch" object
    std::string no_switch_json = R"({
        "router": {
            "ip_address": "192.168.1.100"
        }
    })";
    create_file("test_no_switch.json", no_switch_json);
    // Config file missing "ip_address"
    std::string no_ip_address_json = R"({
        "switch": {}
    })";
    create_file("test_no_ip_address.json", no_ip_address_json);
    // Corrupt JSON file
    std::string corrupt_json = R"({
        "switch": "bad_format"
    })";
    create_file("test_corrupt.json", corrupt_json);

    static DeviceManager dev_mgr;
    g_dev_mgr = &dev_mgr;

    // Register adapters and devices
    g_dev_mgr->registerAdapter("Test", &testAdapter);
    sc_id sid(1);
    g_dev_mgr->register_device(sid, &testAdapter);

    // testAdapter.setLargeDeviceListResponse(R"([{"id": "1", "type": "1",
    // "pcie_addr": "0x1234"}])");
  }

  void TearDown() override {
    // Clean up temporary file
    if (!temp_filename.empty()) {
      remove(temp_filename.c_str());
    }
    // Clean up temporary files
    remove("empty_file.json");
    remove("valid_file.json");
    remove(LOG_CONF_FILE);

    if (std::filesystem::exists("temp_config.json"))
      std::filesystem::remove("temp_config.json");

    remove("valid_cxl.json");
    remove("test_no_switch.json");
    remove("test_no_ip_address.json");
    remove("test_corrupt.json");
    g_dev_mgr->unregister_device(&testAdapter);
    g_dev_mgr->unregisterAdapter("Test");
  }

  // Helper function to load JSON from a file
  json_t* load_json_from_file(const std::string& file_path) {
    json_error_t error;
    json_t* root = json_load_file(file_path.c_str(), 0, &error);
    if (!root) {
      std::cerr << "Error loading JSON from file: " << error.text << " at line "
                << error.line << std::endl;
      return nullptr;
    }
    return root;
  }

  // Helper function to create the JSON configuration dynamically
  json_t* create_dev_cmmb_config() {
    // Create the root JSON object
    json_t* root = json_object();
    // Create the `fabric_managers` array
    json_t* fabric_managers = json_array();
    // Create a single fabric manager object
    json_t* fabric_manager = json_object();
    json_object_set_new(fabric_manager, "id", json_integer(1007));
    json_object_set_new(fabric_manager, "type", json_string("FM_REMOTE_CMMB"));

    // Create the Hosts array
    json_t* hosts_array = json_array();
    // Create a host object
    json_t* host = json_object();
    json_object_set_new(host, "host_name", json_string("Host1"));
    json_object_set_new(host, "host_port", json_integer(1));
    // Create an endpoint array within the host
    json_t* endpoint_array = json_array();
    // Create an endpoint object
    json_t* endpoint = json_object();
    json_object_set_new(endpoint, "memdev", json_string("DEVM"));
    json_object_set_new(endpoint, "target", json_integer(15));
    json_array_append_new(endpoint_array, endpoint);
    // Add the endpoint array to the host object
    json_object_set_new(host, "endpoint", endpoint_array);
    // Add the host object to the hosts array
    json_array_append_new(hosts_array, host);
    // Add the hosts array to the fabric manager object
    json_object_set_new(fabric_manager, "Hosts", hosts_array);
    // Create the Devices array within the fabric manager
    json_t* devices_array = json_array();
    // Create a device object
    json_t* device = json_object();
    json_object_set_new(device, "dev_name", json_string("DEVJA-256G"));
    json_object_set_new(device, "dev_port", json_integer(15));
    json_object_set_new(device, "dev_addr", json_string("0x00H000000000"));
    json_object_set_new(device, "dev_size", json_string("0x004000000000"));
    json_object_set_new(device, "dev_aspm_active", json_integer(1));
    json_object_set_new(device, "dev_sris_active", json_integer(1));
    json_object_set_new(device, "dev_lock_active", json_integer(1));
    json_object_set_new(device, "dev_speed", json_integer(5));
    json_object_set_new(device, "dev_width", json_integer(8));
    json_object_set_new(device, "dev_port_type", json_string("dh"));
    // Add the device object to the devices array
    json_array_append_new(devices_array, device);
    // Add the devices array to the fabric manager object
    json_object_set_new(fabric_manager, "Devices", devices_array);
    // Add the fabric manager object to the `fabric_managers` array
    json_array_append_new(fabric_managers, fabric_manager);
    // Add the `fabric_managers` array to the root object
    json_object_set_new(root, "fabric_managers", fabric_managers);
    return root;
  }

  std::string write_json_to_temp_file(const std::string& json_content) {
    std::string temp_filename = "temp_config.json";
    std::ofstream temp_file(temp_filename);
    temp_file << json_content;
    temp_file.close();
    return temp_filename;
  }

  // Helper function to create temporary files
  void create_file(const std::string& file_name, const std::string& content) {
    std::ofstream file(file_name);
    file << content;
    file.close();
  }

  // Utility function to copy test files into CXL_CONF_FILE location
  void use_test_config(const std::string& test_filename) {
    std::ifstream src(test_filename, std::ios::binary);
    std::ofstream dest("cxl.conf", std::ios::binary);
    dest << src.rdbuf();
  }

std::string get_json_value(const std::string& json_str,
                           const std::string& key) {
  json_error_t error;
  std::string result;
  json_t* root = json_loads(json_str.c_str(), 0, &error);
  if (!root) {
    result = "";
  }
  json_t* value = json_object_get(root, key.c_str());
  if (!value) {
    result = "";
  }
  std::cout << "input " << json_str.c_str() << std::endl;
  // If value is an array, return its string representation
  if (json_is_array(value)) {
    char* json_str = json_dumps(value, JSON_COMPACT);
    result = json_str ? json_str : "";
    std::cout << "its an array , result: " << result << std::endl;
    free(json_str);
  } else if (json_is_string(value)) {
    result = json_string_value(value);
  } else if (json_is_integer(value)) {
    result = std::to_string(json_integer_value(value));
  }

  json_decref(root);
  std::cout << "final return value " << result << std::endl;
  return result;
}

};

TEST_F(ServicerTest, InitCxlPluginSuccess) {
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).WillOnce(Return(0));
  int result = init_cxl_plugin();
  EXPECT_EQ(result, 0);
}

TEST_F(ServicerTest, InitializeSuccessTest) {
  create_log_config_file();
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).WillOnce(Return(0));
  svk_status status = initialize(nullptr);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(ServicerTest, InitializeFailureTest) {
  remove(LOG_CONF_FILE);
  EXPECT_CALL(mock_cxl_global, g_create_mbox(nullptr)).WillOnce(Return(-1));
  svk_status status = initialize(nullptr);
  ASSERT_EQ(status, SVK_STATUS_INVALID_CONFIG);
}

TEST_F(ServicerTest, InitLogSuccess) {
  // Create a valid log configuration file
  create_log_config_file();
  int status = init_log(LOG_CONF_FILE);
  ASSERT_EQ(status, 0);
}

TEST_F(ServicerTest, InitLogFailure) {
  // Ensure log.conf file is missing
  create_log_config_file();
  remove_log_config_file();
  int status = init_log(LOG_CONF_FILE);
  ASSERT_EQ(status, -ENOENT);
}

TEST_F(ServicerTest, InitLog_MissingLoggerNode) {
  // Create log.conf without "cxl.logger" node
  std::ofstream out(LOG_CONF_FILE);
  out << R"({
        "cxl": {
            "feature_lib_dir": "/usr/local/svk/cxl/lib64"
        }
    })";
  out.close();
  int status = init_log(LOG_CONF_FILE);
  ASSERT_EQ(status, -EFAULT);
}

TEST_F(ServicerTest, InitLog_InvalidLogLevel) {
  // Create log.conf with an invalid log level
  std::ofstream out(LOG_CONF_FILE);
  out << R"({
        "cxl": {
            "logger": {
                "log_module_name": "CXL",
                "log_level": "INVALID_LEVEL",
                "log_file_name": "/var/log/cxl.log",
                "log_file_count": 1,
                "log_file_size": 1048576,
                "sink_type": "rotating_file"
            }
        }
    })";
  out.close();
  int status = init_log(LOG_CONF_FILE);
  // invalid log levels default to `CXL_LOGGER_LEVEL_DEFAULT=INFO`
  ASSERT_EQ(status, 0);
}

TEST_F(ServicerTest, InitLog_LoggerInitializationFails) {
  // Create valid log.conf
  std::ofstream out(LOG_CONF_FILE);
  out << R"({
        "cxl": {
            "logger": {
                "log_module_name": "CXL",
                "log_level": "INFO",
                "log_file_name": null,
                "log_file_count": 1,
                "log_file_size": 1048576,
                "sink_type": null
            }
        }
    })";
  out.close();
  int status = init_log(LOG_CONF_FILE);
  ASSERT_EQ(status, -EIO);
}

TEST_F(ServicerTest, TokenizeTest) {
  string input = "key1=value1;key2=value2;key3=value3";
  unordered_map<string, string> tokens = tokenize(input);
  EXPECT_EQ(tokens.size(), 3);
  EXPECT_EQ(tokens["key1"], "value1");
  EXPECT_EQ(tokens["key2"], "value2");
  EXPECT_EQ(tokens["key3"], "value3");
}

TEST_F(ServicerTest, TokenHelperTest) {
  string input = "key1=value1;key2=value2;key3=value3";
  unordered_map<string, string> tokens = token_helper(input);
  EXPECT_EQ(tokens.size(), 3);
  EXPECT_EQ(tokens["key1"], "value1");
  EXPECT_EQ(tokens["key2"], "value2");
  EXPECT_EQ(tokens["key3"], "value3");
}

TEST_F(ServicerTest, GetSupportedFeatureListTest) {
  feature_id feat_id;
  char feature_names[256];
  svk_status status = get_supported_feature_list(&feat_id, feature_names);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(ServicerTest, IsLicenseValidTest) {
  svk_status status = is_license_valid(nullptr);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(ServicerTest, ExecuteAsyncTest) {
  svk_pass_thru_cmd pass_thru;
  svk_postprocess_fn postprocess_fn;
  svk_status status = execute_async(&pass_thru, &postprocess_fn);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(ServicerTest, CleanUpTest) {
  svk_status status = clean_up(nullptr);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(ServicerTest, ConfigureDeviceIfAnyTest) {
  svk_device_ctx device_handles;
  void* config_details = nullptr;
  uint64_t length = 0;
  void* resp = nullptr;
  svk_status status =
      configure_device_if_any(config_details, &device_handles, length, resp);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(ServicerTest, ExecuteSyncDevTest) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer =
      reinterpret_cast<uint8_t*>(strdup("command=ListDevices"));
  input.len = strlen("command=ListDevices");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ExecuteSyncHostTest) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=ListHosts"));
  input.len = strlen("command=ListHosts");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ExecuteSyncDetachTest) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(
      strdup("command=DetachMemory;dev_id=549755813888;host_id=551903297536;"
             "mode=direct"));
  input.len = strlen(
      "command=DetachMemory;dev_id=549755813888;host_id=551903297536;mode="
      "direct");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ExecuteSyncAttachTest) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(
      strdup("command=AttachMemory;dev_id=549755813888;host_id=551903297536;"
             "mode=direct"));
  input.len = strlen(
      "command=AttachMemory;dev_id=549755813888;host_id=551903297536;mode="
      "direct");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, GetIPAddressSuccess) {
  std::string ip;
  int status = get_ip_address(json_filepath, ip);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(ip, "105.140.86.13");
}

TEST_F(ServicerTest, MissingSwitchObject) {
  // Create a mock JSON file with no "switch" object
  std::string json_content = R"(
      {
          "router": {
              "ip_address": "192.168.1.100"
          }
      })";
  std::ofstream out("test_no_switch.json");
  out << json_content;
  out.close();
  std::string ip;
  int status = get_ip_address("test_no_switch.json", ip);
  // Expect -EINVAL since "switch" object is missing
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(ip.empty());
  std::remove("test_no_switch.json");
}

TEST_F(ServicerTest, MissingIPAddressField) {
  // Create a mock JSON file with no "ip_address" field
  std::string json_content = R"(
      {
          "switch": {}
      })";
  std::ofstream out("test_no_ip_address.json");
  out << json_content;
  out.close();
  std::string ip;
  int status = get_ip_address("test_no_ip_address.json", ip);
  // Expect -ENODATA since "ip_address" field is missing
  EXPECT_EQ(status, -ENODATA);
  EXPECT_TRUE(ip.empty());
  std::remove("test_no_ip_address.json");
}

TEST_F(ServicerTest, FailToLoadJsonFile) {
  std::string ip;
  std::string invalid_filepath = "non_existent.json";
  int status = get_ip_address(invalid_filepath, ip);
  // Expect -ENOENT since file doesn't exist
  EXPECT_EQ(status, -ENOENT);
  EXPECT_TRUE(ip.empty());
}

TEST_F(ServicerTest, IPAddressIsNotString) {
  std::string json_content = R"(
      {
          "switch": {
              "ip_address": 12345
          }
      })";
  std::ofstream out("test_ip_not_string.json");
  out << json_content;
  out.close();
  std::string ip;
  int status = get_ip_address("test_ip_not_string.json", ip);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(ip.empty());
  std::remove("test_ip_not_string.json");
}

/**
 * @brief Test for direct_config function with valid config path
 */
TEST_F(ServicerTest, DirectConfigSuccessTest) {
  std::string config_path = "valid_config.json";
  // Create a valid JSON configuration file for the test
  std::ofstream config_file(config_path);
  config_file << "{\"id\": 100, \"id_type\": \"Direct\"}";
  config_file.close();
  json_t* result = direct_config(config_path);
  ASSERT_NE(result, nullptr);
  json_decref(result);
  remove(config_path.c_str());
}

/**
 * @brief Test for direct_config function with invalid config path
 */
TEST_F(ServicerTest, DirectConfigFailureTest) {
  std::string invalid_config_path = "non_existent_config.json";
  // Test direct_config with an invalid file path
  json_t* result = direct_config(invalid_config_path);
  EXPECT_EQ(result, nullptr);
}

/**
 * @brief SetupInfo with a valid FabricManager instance
 */
TEST_F(ServicerTest, SetupInfoWithFM) {
  // Load configuration from file and add a FabricManager instance
  json_t* config = load_json_from_file(input_conf_path);
  ASSERT_NE(config, nullptr) << "Failed to load input.conf";
  json_t* fabric_managers = json_object_get(config, "fabric_managers");
  ASSERT_TRUE(json_is_array(fabric_managers))
      << "fabric_managers should be an array";
  json_t* first_fabric_manager = json_array_get(fabric_managers, 0);
  ASSERT_NE(first_fabric_manager, nullptr);
  FabricManager* manager = new FabricManager(first_fabric_manager);
  cxl_global.add_fm(manager->get_fmid(), *manager);
  // Free the config JSON after adding the manager
  json_decref(config);

  // Set up and invoke `execute_sync` for `SetupInfo`
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=SetupInfo"));
  input.len = strlen("command=SetupInfo");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

/**
 * @brief SetupInfo with no FabricManager instances
 */
TEST_F(ServicerTest, SetupInfoNoManagers) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=SetupInfo"));
  input.len = strlen("command=SetupInfo");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  free(input.input_buffer);
}

TEST_F(ServicerTest, SetupInfoWithMultipleFMs) {
  // Load configuration from file and add multiple FabricManager instances
  json_t* config = load_json_from_file(input_conf_path);
  ASSERT_NE(config, nullptr) << "Failed to load input.conf";
  json_t* fabric_managers = json_object_get(config, "fabric_managers");
  ASSERT_TRUE(json_is_array(fabric_managers))
      << "fabric_managers should be an array";
  // Add multiple FabricManagers
  for (size_t i = 0; i < json_array_size(fabric_managers); ++i) {
    json_t* fabric_manager = json_array_get(fabric_managers, i);
    ASSERT_NE(fabric_manager, nullptr);
    FabricManager* manager = new FabricManager(fabric_manager);
    cxl_global.add_fm(manager->get_fmid(), *manager);
  }
  // Free the config JSON
  json_decref(config);
  // Set up and invoke `execute_sync` for `SetupInfo`
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=SetupInfo"));
  input.len = strlen("command=SetupInfo");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  // Verify delimiter exists in output
  std::string result(reinterpret_cast<char*>(output.output_buffer), output.len);
  ASSERT_TRUE(result.find(",") != std::string::npos)
      << "Output should contain delimiter.";
  // Clean up
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, SetupInfoWithNullManager) {
  // Mock cxl_global to simulate find_fm returning nullptr
  EXPECT_CALL(mock_cxl_global, find_fm(_)).WillRepeatedly(Return(nullptr));
  // Set up and invoke `execute_sync` for `SetupInfo`
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=SetupInfo"));
  input.len = strlen("command=SetupInfo");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  // Verify the function handles the case correctly
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  std::string result(reinterpret_cast<char*>(output.output_buffer), output.len);
  ASSERT_EQ(result, "[]")
      << "Output should be an empty JSON array when no managers are found.";
  // Clean up
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, SetupInfoWithNoFMKeys) {
  // Mock cxl_global to return an empty list of keys
  EXPECT_CALL(mock_cxl_global, get_fm_keys())
      .WillRepeatedly(Return(std::vector<sc_id>{}));
  // Set up and invoke `execute_sync` for `SetupInfo`
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=SetupInfo"));
  input.len = strlen("command=SetupInfo");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  // Verify the function returns an empty JSON array
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  std::string result(reinterpret_cast<char*>(output.output_buffer), output.len);
  ASSERT_EQ(result, "[]")
      << "Output should be an empty JSON array when no keys are present.";
  // Clean up
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, MissingFabricManagersArray) {
  // Create JSON content without the `fabric_managers` key
  std::string json_content = R"({
        "some_other_key": 123
    })";
  // Write the content to a temporary file
  temp_filename = write_json_to_temp_file(json_content);
  json_t* result = load_json_config(temp_filename);
  EXPECT_EQ(result, nullptr);
}

TEST_F(ServicerTest, FabricManagersNotArray) {
  std::string json_content = R"({
        "fabric_managers": {
            "id": 1001
        }
    })";
  // Write the content to a temporary file
  temp_filename = write_json_to_temp_file(json_content);
  json_t* result = load_json_config(temp_filename);
  // Verify the result
  EXPECT_EQ(result, nullptr);
}

TEST_F(ServicerTest, ValidFabricManagersArray) {
  // Create JSON content with `fabric_managers` as an array
  std::string json_content = R"({
        "fabric_managers": []
    })";
  // Write the content to a temporary file
  temp_filename = write_json_to_temp_file(json_content);
  // Capture stderr output to verify no error message
  testing::internal::CaptureStderr();
  json_t* result = load_json_config(temp_filename);
  std::string output = testing::internal::GetCapturedStderr();
  EXPECT_NE(result, nullptr);
  EXPECT_TRUE(output.empty());
  // Clean up JSON object
  json_decref(result);
}

TEST_F(ServicerTest, CreateDevCMMB) {
  // Create the JSON configuration for DevCMMB
  json_t* config = create_dev_cmmb_config();
  // Call the function to create and add DevCMMB to cxl_global
  create_dev_cmmb(config);
}

TEST_F(ServicerTest, FmapiSetupSuccess) {
  std::string buffer;
  json_t* result = parse_input_config(buffer);
  ASSERT_NE(result, nullptr);
  json_t* type = json_object_get(result, "type");
  ASSERT_TRUE(json_is_string(type));
  EXPECT_STREQ(json_string_value(type), "FM_REMOTE_CMMB");
  json_decref(result);
}

TEST_F(ServicerTest, ProcessFMInvalidTypeField) {
  json_t* fabric_manager = json_object();
  json_object_set_new(fabric_manager, "id", json_integer(123));
  json_object_set_new(fabric_manager, "type", json_integer(123));
  int result = process_fabric_manager(fabric_manager);
  EXPECT_EQ(result, 1);
  json_decref(fabric_manager);
}

TEST_F(ServicerTest, ProcessFMUnknownType) {
  // Create a JSON fabric manager with an unknown type
  json_t* fabric_manager = json_object();
  json_object_set_new(fabric_manager, "id", json_integer(123));
  json_object_set_new(fabric_manager, "type", json_string("UNKNOWN"));
  int result = process_fabric_manager(fabric_manager);
  EXPECT_EQ(result, 2);
  json_decref(fabric_manager);
}

TEST_F(ServicerTest, LoadJsonConfigInvalidRootType) {
  std::string invalid_json_content = R"([{"key": "value"}])";
  std::string path = write_json_to_temp_file(invalid_json_content);
  json_t* result = load_json_config(path);
  EXPECT_EQ(result, nullptr);
}

TEST_F(ServicerTest, LoadJsonConfigMissingFabricManagers) {
  // Write a JSON object without the "fabric_managers" field
  std::string invalid_json_content = R"({"other_key": "value"})";
  std::string path = write_json_to_temp_file(invalid_json_content);
  json_t* result = load_json_config(path);
  EXPECT_EQ(result, nullptr);
}

TEST_F(ServicerTest, MissingFile) {
  // Ensure the file does not exist
  std::string missing_file = "missing_file.json";
  remove(missing_file.c_str());
  ASSERT_TRUE(is_file_empty_or_missing(missing_file))
      << "The function should return true for a missing file.";
}

TEST_F(ServicerTest, EmptyFile) {
  // Create an empty file
  std::string empty_file = "empty_file.json";
  create_file(empty_file, "");
  ASSERT_TRUE(is_file_empty_or_missing(empty_file))
      << "The function should return true for an empty file.";
}

TEST_F(ServicerTest, ValidNonEmptyFile) {
  // Create a valid non-empty file
  std::string valid_file = "valid_file.json";
  create_file(valid_file, R"({"key": "value"})");
  ASSERT_FALSE(is_file_empty_or_missing(valid_file))
      << "The function should return false for a valid non-empty file.";
}

TEST_F(ServicerTest, IsValidIP) {
  ASSERT_TRUE(is_valid_ip("192.168.1.1"))
      << "Valid IP address should return true.";
  ASSERT_FALSE(is_valid_ip("300.168.1.1"))
      << "Invalid IP address should return false.";
  ASSERT_FALSE(is_valid_ip("192.168.1"))
      << "Incomplete IP address should return false.";
  ASSERT_FALSE(is_valid_ip("0.123.123.123"))
      << "InValid IP address should return false.";
  ASSERT_FALSE(is_valid_ip("abc.def.ghi.jkl"))
      << "Non-numeric IP address should return false.";
}

TEST_F(ServicerTest, StartTuning) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  std::string cmd =
      "command=StartTuning;application=gemfire;application_id=101010;dram_node="
      "0;cxl_node=1;sla_iops=150000;sla_size=1024;sla_latencyus=750";
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup(cmd.c_str()));
  input.len = strlen(cmd.c_str());
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, StopTuning) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  std::string cmd =
      "command=StopTuning;application=gemfire;application_id=101010";
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup(cmd.c_str()));
  input.len = strlen(cmd.c_str());
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ProcessJsonRequest_ValidJsonWithParams) {
  std::string input_str = R"({
    "command_name": "list_devices",
    "command_params": {
      "device_type": "CMMD",
      "vendor": "Samsung"
    }
  })";
  std::string command;
  std::unordered_map<std::string, std::string> params;
  bool result = process_json_request(input_str, command, params);
  EXPECT_TRUE(result);
  EXPECT_EQ(command, "list_devices");
  EXPECT_EQ(params["device_type"], "CMMD");
  EXPECT_EQ(params["vendor"], "Samsung");
}

TEST_F(ServicerTest, ProcessJsonRequest_ValidJsonWithoutParams) {
  std::string input_str = R"({
    "command_name": "get_device_info"
  })";
  std::string command;
  std::unordered_map<std::string, std::string> params;
  bool result = process_json_request(input_str, command, params);
  EXPECT_TRUE(result);
  EXPECT_EQ(command, "get_device_info");
  EXPECT_TRUE(params.empty());
}

TEST_F(ServicerTest, ProcessJsonRequest_MissingCommandName) {
  std::string input_str = R"({
    "command_params": {
      "device_id": "1234"
    }
  })";
  std::string command;
  std::unordered_map<std::string, std::string> params;
  bool result = process_json_request(input_str, command, params);
  // Should fail due to missing "command_name"
  EXPECT_FALSE(result);
}

TEST_F(ServicerTest, ProcessJsonRequest_InvalidJsonFormat) {
  std::string input_str = R"({
    "command_name": "attach_memory",
    "command_params": {
      "device_id": "789",
      "host_id": "1234"  // Missing closing quote
  })";
  std::string command;
  std::unordered_map<std::string, std::string> params;
  bool result = process_json_request(input_str, command, params);
  // Should fail due to JSON syntax error
  EXPECT_FALSE(result);
}

TEST_F(ServicerTest, ProcessJsonRequest_EmptyJson) {
  std::string input_str = "{}";
  std::string command;
  std::unordered_map<std::string, std::string> params;
  bool result = process_json_request(input_str, command, params);
  // Should fail due to missing "command_name"
  EXPECT_FALSE(result);
}

TEST_F(ServicerTest, ProcessJsonRequest_ArrayParams) {
  std::string input_str = R"({
    "command_name": "list_devices",
    "command_params": {
      "device_id": [1, 2]
    }
  })";
  std::string command;
  std::unordered_map<std::string, std::string> params;
  bool result = process_json_request(input_str, command, params);
  EXPECT_TRUE(result);
  EXPECT_EQ(command, "list_devices");
  // The array should be stored as a JSON string in the map
  EXPECT_EQ(params["device_id"], "[1,2]");
}

TEST_F(ServicerTest, ExecuteSync_NullInputOutput) {
  svk_status status = execute_sync(nullptr, nullptr, nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, ExecuteSync_LegacyCommandFormat) {
  std::string legacy_input =
      "cluster_id=CL_ID_1;command=ListDevices;FM_id=203;FM_endpoint=samsung."
      "com";
  svk_input input;
  svk_output output;
  input.input_buffer =
      reinterpret_cast<uint8_t*>(const_cast<char*>(legacy_input.c_str()));
  input.len = legacy_input.size();
  svk_status status = execute_sync(nullptr, &input, &output);
  EXPECT_EQ(status, SVK_STATUS_SUCCESS);
  // Ensure response is not empty
  std::string response(reinterpret_cast<char*>(output.output_buffer));
  EXPECT_FALSE(response.empty());
}

TEST_F(ServicerTest, ExecuteSync_ListDevices) {
  std::string json_input = R"({
    "feature_id": "3",
    "command_name": "list_devices",
    "command_params": {
      "device_id": [121, 122]
    }
  })";
  svk_input input;
  svk_output output;
  input.input_buffer =
      reinterpret_cast<uint8_t*>(const_cast<char*>(json_input.c_str()));
  input.len = json_input.size();
  svk_status status = execute_sync(nullptr, &input, &output);
  EXPECT_EQ(status, SVK_STATUS_SUCCESS);
  // Verify DeviceManager::list_devices() was executed
  std::string response(reinterpret_cast<char*>(output.output_buffer));
  EXPECT_FALSE(response.empty());
}

TEST_F(ServicerTest, ExecuteSync_GetDeviceInfo) {
  std::string json_input = R"({
    "command_name": "get_device_info",
    "command_params": {
      "domain_id": "",
      "device_id": []
    }
  })";
  svk_input input;
  svk_output output;
  input.input_buffer =
      reinterpret_cast<uint8_t*>(const_cast<char*>(json_input.c_str()));
  input.len = json_input.size();
  svk_status status = execute_sync(nullptr, &input, &output);
  EXPECT_EQ(status, SVK_STATUS_SUCCESS);
  std::string response(reinterpret_cast<char*>(output.output_buffer));
  EXPECT_FALSE(response.empty());
}

TEST_F(ServicerTest, CmmbA1_Success) {
  use_test_config("valid_cxl.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).WillOnce(Return(0));
  int status = cmmb_a1_init();
  EXPECT_EQ(status, 0);
}

TEST_F(ServicerTest, CmmbA1_ConfigFileNotFound) {
  use_test_config("non_existent.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = cmmb_a1_init();
  EXPECT_EQ(status, -ENOENT);
}

TEST_F(ServicerTest, CmmbA1_MissingSwitchObject) {
  use_test_config("test_no_switch.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = cmmb_a1_init();
  EXPECT_EQ(status, -EINVAL);
}

TEST_F(ServicerTest, CmmbA1_MissingIPAddressField) {
  use_test_config("test_no_ip_address.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = cmmb_a1_init();
  EXPECT_EQ(status, -ENODATA);
}

TEST_F(ServicerTest, CmmbA1_CorruptJsonFile) {
  use_test_config("test_corrupt.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = cmmb_a1_init();
  EXPECT_EQ(status, -EINVAL);
}

/*TEST_F(ServicerTest, ListDevices_EmptyInput_ReturnsAllDevices) {
  std::unordered_map<std::string, std::string> params;
  std::string result = handle_list_devices(params);
  EXPECT_FALSE(result.empty());
  EXPECT_TRUE(result.find("devices") != std::string::npos);
}*/

TEST_F(ServicerTest, ListDevices_InvalidArrayFormat_ReturnsError) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"([123, 456])"}  
  };
  std::string result = handle_list_devices(params);
  EXPECT_TRUE(result.find("device_id array must contain strings") !=
              std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ExceptionHandling) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "not_a_number"}};
  std::string result = handle_list_devices(params);
  EXPECT_TRUE(result.find("Exception") != std::string::npos ||
              result.find("Invalid") != std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_MissingParam_ReturnsError) {
  std::unordered_map<std::string, std::string> params;
  std::string result = handle_get_device_info(params);
  EXPECT_TRUE(result.find("Missing parameter") != std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_InvalidIdString_ReturnsError) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "invalid"}};
  std::string result = handle_get_device_info(params);
  EXPECT_TRUE(result.find("Invalid") != std::string::npos);
}

/*TEST_F(ServicerTest, ListDevices_InvalidJsonArrayFormat) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[not_valid_json"}
  };
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("EINVAL"), std::string::npos);
}*/

TEST_F(ServicerTest, ListDevices_InvalidDeviceIdInArray) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"(["abc123"])"}
  };
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("EINVAL"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_NonStringArrayElement) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"([1234])"}
  };
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("device_id array must contain strings"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ValidSingleDeviceId) {
  // Setup mock adapter and device
  auto adapter = std::make_shared<TestCXLDeviceAdapter>();
  sc_device dev(1234, "mock_dev", 1024, 1);
  dev.d_set_pcie_addr("0000:00:01.0");

  adapter->add_mock_device(dev);  // add to adapter
  g_dev_mgr->registerAdapter("mock_adapter", adapter.get()); 
  g_dev_mgr->register_device(dev.d_get_id(), adapter.get()); 

  // Now run the test
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "1234"}
  };
  std::string response = handle_list_devices(params);

  EXPECT_NE(response.find("devices"), std::string::npos);
  EXPECT_NE(response.find("1234"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ValidResultJson) {
  auto adapter = std::make_shared<TestCXLDeviceAdapter>();
  sc_device dev(1234, "mock_dev", 1024, 1);
  dev.d_set_pcie_addr("0000:00:01.0");
  adapter->add_mock_device(dev);
  g_dev_mgr->registerAdapter("mock_adapter", adapter.get());
  g_dev_mgr->register_device(dev.d_get_id(), adapter.get());
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"1234\"]"}
  };
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("\"id\":"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ExceptionWhileParsing) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "throws_exception"}
  };
  // str_to_int mock throws std::runtime_error
  std::string response = handle_list_devices(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL"); 
  EXPECT_EQ(get_json_value(response, "message"),"Invalid id format");
}

TEST_F(ServicerTest, ListDevices_NoFilter_FetchAll) {
  std::unordered_map<std::string, std::string> params;
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("devices"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_FilterNoMatch) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"999999\"]"}
  };
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("No matching device IDs found"), std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_MissingParam) {
  std::unordered_map<std::string, std::string> params = {};
  std::string response = handle_get_device_info(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL"); 
  EXPECT_EQ(get_json_value(response, "message"),"Missing parameter: device_id");
}


TEST_F(ServicerTest, GetDeviceInfo_InvalidParamFormat) {
  std::unordered_map<std::string, std::string> params = {
    {"device_id", "abcde"}
  };
  std::string response = handle_get_device_info(params);

  EXPECT_NE(response.find("Invalid id format"), std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_DeviceNotFound) {
  std::unordered_map<std::string, std::string> params = {
    {"device_id", "9999"}
  };
  std::string response = handle_get_device_info(params);

  EXPECT_NE(response.find("Device not found or error occurred"), std::string::npos);
}


TEST_F(ServicerTest, GetDeviceInfo_Success) {
  sc_device dev(1234, "mydev", 1024, 1);
  //dev.d_set_dev_name("mydev");
  dev.d_set_serial_number(123456);
  dev.d_set_fw_revision("1.0.0");
  dev.d_set_location("slotA");
  //dev.d_set_capacity(1024);
  dev.d_set_status("active");
  dev.d_set_feature_supported("SLD");
  dev.d_set_device_type("CMMB");
  dev.d_set_cxl_type("type1");
  dev.d_set_protocol_version("1.1");
  dev.d_set_aspm_active(true);
  dev.d_set_sris_active(true);
  dev.d_set_lock_active(false);
  dev.d_set_link_speed(5);
  dev.d_set_link_width(16);
  dev.d_set_port_type("dh");
  dev.d_set_numa_attached(0);
  dev.d_set_mode_discovered("system-mem");
  dev.d_set_connection_type("local");
  dev.d_set_domain_type("direct");
  dev.d_set_domain_id(20);

  Capabilities caps;
  caps.power_management_version = 3;
  dev.d_set_capabilities(caps);

  QoSInfo qos;
  qos.avg_latency = 1.5;
  qos.p99_latency = 2.0;
  qos.io_per_sec = 5000;
  qos.bw_per_sec = 1000;
  qos.io_size = 128;
  qos.qd = 32;
  dev.d_set_qos_info(qos);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);

  std::unordered_map<std::string, std::string> params = {
    {"device_id", "1234"}
  };

  std::string response = handle_get_device_info(params);
  std::cout << "Test case response #### "<<response << std::endl;
  
  EXPECT_EQ(get_json_value(response, "id"), "1234");
  EXPECT_EQ(get_json_value(response, "manufacturer"), "Samsung");
  EXPECT_EQ(get_json_value(response, "device_type"), "CMMB");
  EXPECT_EQ(get_json_value(response, "serial_number"), "123456");
  EXPECT_EQ(get_json_value(response, "FW_revision"), "1.0.0");
  EXPECT_EQ(get_json_value(response, "status"), "active");
  EXPECT_EQ(get_json_value(response, "cxl_type"), "type1");
  EXPECT_EQ(get_json_value(response, "connection_type"), "local");
}

TEST_F(ServicerTest, ListDevices_InvalidJsonArrayFormat) {
  // {"device_id", "[{\"invalid_key\":\"invalid_value\"}]"

  std::unordered_map<std::string, std::string> params = {
    {"device_id", "[\"1234\", invalid_value]"}
  };
  std::string response = handle_list_devices(params);
  //std::cout << "Test case response #### "<<response << std::endl;
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL"); 
  EXPECT_EQ(get_json_value(response, "message"),"Invalid device_id array format");
}

TEST_F(ServicerTest, ListDevices_ArrayContainsInvalidId) {
  std::unordered_map<std::string, std::string> params = {
    {"device_id", "[\"1234\", \"bad_id\"]"}
  };
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("Invalid id format"), std::string::npos);
}


