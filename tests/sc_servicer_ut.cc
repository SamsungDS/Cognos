#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <cstdio>
#include <fstream>
#include <iostream>

#include "framework_downstream.h"
#include "log_utils.h"
#include "sc_dev_manager.h"
#include "sc_device.h"
#include "sc_global.h"
#include "sc_mbox.h"
#include "sc_servicer.h"
#include "sc_servicer_internal.h"
#include "sc_test_cxl_adapter.h"
#include "sc_test_utils.h"
#include "sc_utility.h"
#include "tuner.h"

extern "C" {
#include "jansson.h"
#include "sc_a1.h"
}

using ::testing::DoAll;
using ::testing::Return;
using ::testing::SetArgReferee;
using ::testing::Throw;

#define DELIMITER ","
#define LOG_CONF_FILE "log.conf"

using namespace std;

extern DeviceManager* g_dev_mgr;

// Global instance
sc_global cxl_global;
const std::string json_filepath = "cxl.conf";

using ::testing::_;
using ::testing::Return;

// function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);

class MockScGlobal : public sc_global {
 public:
  MOCK_METHOD(int, g_create_mbox, (StaticPortInfo*), ());
  MOCK_METHOD(int, init_log, (const std::string&), ());
  MOCK_METHOD(int, init_cxl_plugin, (), ());
  MOCK_METHOD(int, parse_json_key,
              (const std::string&, const std::string&, std::string&), ());
  MOCK_METHOD(int, validate_json_file, (const std::string&), ());
  MOCK_METHOD(DevTypeMap, load_dev_type_mapping_json, (const std::string&), ());
};

// Test fixture
MockScGlobal mock_cxl_global;

class ServicerTest : public ::testing::Test {
 protected:
  std::string temp_filename;
  TestCXLDeviceAdapter testAdapter;
  std::filesystem::path conf_path;
  std::filesystem::path backup_path;
  void SetUp() override {
    cxl_global = mock_cxl_global;
    temp_filename.clear();

    // Valid CXL Config
    std::string valid_json = R"({
        "switch": {
            "ip_address": "105.140.86.13"
        },
        "plugin_dir": "/usr/local/svk/feature_modules/cxl/logic_modules/cmmh/lib64"
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

    // Switch Input JSON
    std::string input_json = R"({
    "Board": {
        "board_name": "Example Direct Config",
        "Mgmt_port_type": "PCIe",
        "json_version": "0100",
        "switch_mode": "direct",
        "management_port": 1
    },
    "Hosts": [
        {
            "host_name": "Host 1 LNK0",
            "host_port": 2,
            "deinit_active": 1,
            "host_port_type": "CXL_11",
            "classcode": 0,
            "host_aspm_active": 1,
            "host_sris_active": 1,
            "host_equalization": 1,
            "host_speed": 5,
            "host_width": 8,
            "host_addr": "0x008080000000",
            "host_size": "0x007f80000000",
            "endpoint": []
        }
    ],
    "Devices": [
        {
            "dev_name": "DEV_10-256G",
            "dev_port": 10,
            "dev_addr": "0x008000000000",
            "dev_size": "0x004000000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20"
        },
        {
            "dev_name": "DEV_11-256G",
            "dev_port": 11,
            "dev_addr": "0x00C000000000",
            "dev_size": "0x004000000000",
            "dev_aspm_active": 1,
            "dev_sris_active": 1,
            "dev_lock_active": 1,
            "dev_speed": 5,
            "dev_width": 8,
            "dev_port_type": "CXL_20"
        }
    ]
})";
    create_file("input.json", input_json);

    static DeviceManager dev_mgr;
    g_dev_mgr = &dev_mgr;

    // Register adapters and devices
    g_dev_mgr->registerAdapter("Test", &testAdapter);
    sc_id sid(1);
    g_dev_mgr->register_device(sid, &testAdapter);
  }

  void TearDown() override {
    // Clean up temporary file
    if (!temp_filename.empty()) {
      remove(temp_filename.c_str());
    }
    // Clean up temporary files
    remove("empty_file.json");
    remove("valid_file.json");
    // remove(LOG_CONF_FILE);

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
  json_t* create_dev_cmm_config() {
    // Create the root JSON object
    json_t* root = json_object();
    // Create the `fabric_managers` array
    json_t* fabric_managers = json_array();
    // Create a single fabric manager object
    json_t* fabric_manager = json_object();
    json_object_set_new(fabric_manager, "id", json_integer(1007));
    json_object_set_new(fabric_manager, "type", json_string("FM_REMOTE_CMM"));

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
    // assert(src && dest);
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

/*
 * TODO: Fix me for Ubuntu24.04
TEST_F(ServicerTest, InitCxlPluginSuccess) {
  // EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).WillOnce(Return(0));
  std::string ip_address;
  int ret;
  ret = get_ip_address("valid_cxl.json", ip_address);
  EXPECT_EQ(ret, 0);

  struct StaticPortInfo pinfo;
  ret = set_ip(ip_address.c_str());
  EXPECT_EQ(ret, 0);

  ret = mbox_get_static_config(&pinfo);
  EXPECT_GE(ret, 0);

  sc_global cxl_global;
  ret = cxl_global.g_create_mbox(&pinfo);
  EXPECT_EQ(ret, 0);
}
*/

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
  ASSERT_EQ(status, SVK_STATUS_FAIL);
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
      reinterpret_cast<uint8_t*>(strdup("command=ListDevices;"));
  input.len = strlen("command=ListDevices;");
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
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=ListHosts;"));
  input.len = strlen("command=ListHosts;");
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
             "mode=direct;"));
  input.len = strlen(
      "command=DetachMemory;dev_id=549755813888;host_id=551903297536;mode="
      "direct;");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ExecuteSyncDetachMemoryMissingParams) {
  svk_input input{};
  svk_output output{};
  svk_pass_thru_cmd pass_thru{};
  input.input_buffer = reinterpret_cast<uint8_t*>(
      strdup("command=DetachMemory;dev_id=1234;mode=direct;"));
  input.len = strlen(reinterpret_cast<char*>(input.input_buffer));
  svk_status status = execute_sync(&pass_thru, &input, &output);
  EXPECT_EQ(status, SVK_STATUS_SUCCESS);
  EXPECT_EQ(output.status, SVK_STATUS_SUCCESS);
  EXPECT_EQ(output.len, 0);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ExecuteSyncAttachTest) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(
      strdup("command=AttachMemory;dev_id=549755813888;host_id=551903297536;"
             "mode=direct;"));
  input.len = strlen(
      "command=AttachMemory;dev_id=549755813888;host_id=551903297536;mode="
      "direct;");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_NE(output.len, 0);
  ASSERT_NE(output.output_buffer, nullptr);
  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, ExecuteSyncAttachMemoryMissingParams) {
  svk_input input{};
  svk_output output{};
  svk_pass_thru_cmd pass_thru{};

  input.input_buffer = reinterpret_cast<uint8_t*>(strdup(
      "command=AttachMemory;dev_id=1234;mode=direct;"));  // missing host_id
  input.len = strlen(reinterpret_cast<const char*>(input.input_buffer));

  svk_status status = execute_sync(&pass_thru, &input, &output);

  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  ASSERT_STREQ(reinterpret_cast<const char*>(output.output_buffer), "");
  ASSERT_EQ(output.len, 0);

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
 * @brief SetupInfo with no FabricManager instances
 */
TEST_F(ServicerTest, SetupInfoNoManagers) {
  svk_input input;
  svk_output output;
  svk_pass_thru_cmd pass_thru;
  input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=SetupInfo;"));
  input.len = strlen("command=SetupInfo;legacy=true");
  svk_status status = execute_sync(&pass_thru, &input, &output);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
  ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
  free(input.input_buffer);
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
      "0;cxl_node=1;sla_iops=150000;sla_size=1024;sla_latencyus=750;";
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
      "command=StopTuning;application=gemfire;application_id=101010;";
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
      "com;legacy=true";
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

TEST_F(ServicerTest, CmmbA1_MissingSwitchObject) {
  use_test_config("test_no_switch.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = a1_init();
  EXPECT_EQ(status, -EINVAL);
}

TEST_F(ServicerTest, CmmbA1_MissingIPAddressField) {
  use_test_config("test_no_ip_address.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = a1_init();
  EXPECT_EQ(status, -ENODATA);
}

TEST_F(ServicerTest, CmmbA1_CorruptJsonFile) {
  use_test_config("test_corrupt.json");
  EXPECT_CALL(mock_cxl_global, g_create_mbox(_)).Times(0);
  int status = a1_init();
  EXPECT_EQ(status, -EINVAL);
}

TEST_F(ServicerTest, NonexistentInputJsonFile) {
  int status = init("input1.json");
  EXPECT_EQ(status, MBOX_CMD_EXEC_FAIL);
}

TEST_F(ServicerTest, ProperInputJsonFile) {
  int status = init("input.json");
  EXPECT_EQ(status, MBOX_SUCCESS);
}

TEST_F(ServicerTest, A1UpdateJsonAndInstall) {
  int status = update_json_and_install();
  EXPECT_EQ(status, MBOX_SUCCESS);
}

TEST_F(ServicerTest, A1UpdateJsonAndInstallOnSwitch) {
  int status = update_json_and_install_on_switch();
  EXPECT_NE(status, MBOX_SUCCESS);
}

TEST_F(ServicerTest, A1IsSwitchAlive) {
  int status = is_switch_alive(100);
  EXPECT_EQ(status, MBOX_PING_FAIL);
}

TEST_F(ServicerTest, A1RebootSwitch) {
  int status = reboot_switch();
  EXPECT_EQ(status, MBOX_REBOOT_FAIL);
}

TEST_F(ServicerTest, A1SetIP) {
  const char* ip = "105.128.101.100";
  int status = set_ip(ip);
  EXPECT_EQ(status, MBOX_SUCCESS);
}

TEST_F(ServicerTest, A1SetIPNull) {
  const char* ip = nullptr;
  int status = set_ip(ip);
  EXPECT_EQ(status, MBOX_NULL_POINTER);
}

/*
 * ToDo: Fix me for Ubuntu 24.04
TEST_F(ServicerTest, CmmbA1_Success) {
  std::string ip_address;
  int ret;
  ret = get_ip_address("valid_cxl.json", ip_address);
  EXPECT_EQ(ret, 0);

  struct StaticPortInfo pinfo;
  ret = set_ip(ip_address.c_str());
  EXPECT_EQ(ret, 0);

  ret = mbox_get_static_config(&pinfo);
  EXPECT_GE(ret, 0);

  sc_global cxl_global;
  ret = cxl_global.g_create_mbox(&pinfo);
  EXPECT_EQ(ret, 0);
}
*/

TEST_F(ServicerTest, ListDevices_InvalidArrayFormat_ReturnsError) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"([123, 456])"}};
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

TEST_F(ServicerTest, ListDevices_InvalidDeviceIdInArray) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"(["abc123"])"}};
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("EINVAL"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_NonStringArrayElement) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"([1234])"}};
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("device_id array must contain strings"),
            std::string::npos);
}
TEST_F(ServicerTest, ListDevices_ValidSingleDeviceId) {
  auto adapter = std::make_shared<TestCXLDeviceAdapter>();
  sc_device dev(1234, "mock_dev", 1024, 1);

  DevStaticInfo stat;
  stat.device_id = dev.d_get_id().get_sc_id();
  stat.location = "0000:00:01.0";
  dev.d_set_static_info(stat);

  adapter->add_mock_device(dev);
  g_dev_mgr->registerAdapter("mock_adapter", adapter.get());
  g_dev_mgr->register_device(dev.d_get_id(), adapter.get());

  std::unordered_map<std::string, std::string> params = {{"device_id", "1234"}};
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("devices"), std::string::npos);
  EXPECT_NE(response.find("1234"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ValidResultJson) {
  auto adapter = std::make_shared<TestCXLDeviceAdapter>();
  sc_device dev(1234, "mock_dev", 1024, 1);

  DevStaticInfo stat;
  stat.location = "0000:00:01.0";
  dev.d_set_static_info(stat);

  adapter->add_mock_device(dev);
  g_dev_mgr->registerAdapter("mock_adapter", adapter.get());
  g_dev_mgr->register_device(dev.d_get_id(), adapter.get());

  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"1234\"]"}};
  std::string response = handle_list_devices(params);

  std::cout << "Test#### " << response << std::endl;
  EXPECT_NE(response.find("\"device_id\""), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ExceptionWhileParsing) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "throws_exception"}};
  std::string response = handle_list_devices(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"), "Invalid id format");
}

TEST_F(ServicerTest, ListDevices_NoFilter_FetchAll) {
  std::unordered_map<std::string, std::string> params;
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("devices"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_FilterNoMatch) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"999999\"]"}};
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("No matching device IDs found"), std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_MissingParam) {
  std::unordered_map<std::string, std::string> params = {};
  std::string response = handle_get_device_info(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Missing parameter: device_id");
}

TEST_F(ServicerTest, GetDeviceInfo_InvalidParamFormat) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "abcde"}};
  std::string response = handle_get_device_info(params);

  EXPECT_NE(response.find("Invalid id format"), std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_DeviceNotFound) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "9999"}};
  EXPECT_THROW({ std::string response = handle_get_device_info(params); },
               std::runtime_error);
}

TEST_F(ServicerTest, GetDeviceInfo_Success) {
  sc_device dev(1234, "mydev", 1024, 1);
  DevStaticInfo stat;
  stat.device_id = dev.d_get_id().get_sc_id();
  stat.manufacturer = "Samsung";
  stat.serial_number = 123456;
  stat.fw_revision = "1.0.0";
  stat.location = "slotA";
  stat.feature_supported = "SLD";
  stat.vendor_device_type = "CMM";
  stat.cxl_device_type = "type1";
  stat.protocol = "1.1";
  stat.link_speed_GT_s = 5;
  stat.link_width = 16;
  stat.port_type = "dh";
  stat.mode_discovered = "system-mem";
  stat.connection_type = "local";
  stat.domain_type = "direct";
  stat.domain_id = 20;

  Capabilities caps;
  caps.power_management_version = 3;
  stat.capabilities = caps;

  QoSInfo qos;
  qos.avg_latency_ns = 1.5;
  qos.p99_latency_ns = 2.0;
  qos.io_per_sec = 5000;
  qos.bw_per_sec = 1000;
  qos.io_size_in_bytes = 128;
  qos.qd = 32;
  stat.advertised_qos = qos;

  dev.d_set_static_info(stat);

  DevInfo dyn;
  dyn.status = "active";
  dyn.numa_node = 0;
  dyn.aspm_active = true;
  dyn.sris_active = true;
  dyn.lock_active = false;
  dev.d_set_dynamic_info(dyn);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);

  std::unordered_map<std::string, std::string> params = {{"device_id", "1234"}};

  std::string response = handle_get_device_info(params);
  std::cout << "Test case response #### " << response << std::endl;

  EXPECT_EQ(get_json_value(response, "device_id"), "1234");
  EXPECT_EQ(get_json_value(response, "manufacturer"), "Samsung");
  EXPECT_EQ(get_json_value(response, "vendor_device_type"), "CMM");
  EXPECT_EQ(get_json_value(response, "serial_number"), "123456");
  EXPECT_EQ(get_json_value(response, "FW_revision"), "1.0.0");
  EXPECT_EQ(get_json_value(response, "status"), "active");
  EXPECT_EQ(get_json_value(response, "cxl_device_type"), "type1");
  EXPECT_EQ(get_json_value(response, "connection_type"), "local");
}

TEST_F(ServicerTest, ListDevices_InvalidJsonArrayFormat) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"1234\", invalid_value]"}};
  std::string response = handle_list_devices(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Invalid device_id array format");
}

TEST_F(ServicerTest, ListDevices_ArrayContainsInvalidId) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"1234\", \"bad_id\"]"}};
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("Invalid id format"), std::string::npos);
}

TEST_F(ServicerTest, ExecuteSync_FallbackWithMissingCommand) {
  svk_input input{};
  svk_output output{};
  svk_pass_thru_cmd pass_thru;

  std::string malformed_json = R"({"fake_command":"val1","unused":"val2"})";
  input.input_buffer =
      reinterpret_cast<uint8_t*>(strdup(malformed_json.c_str()));
  input.len = malformed_json.size();

  svk_status status = execute_sync(&pass_thru, &input, &output);

  EXPECT_EQ(status, SVK_STATUS_FAIL);
  free(input.input_buffer);
}

TEST_F(ServicerTest, ExecuteSync_TriggersRuntimeErrorFallback) {
  svk_input input{};
  svk_output output{};
  svk_pass_thru_cmd pass_thru;

  // valid JSON with a command not in command_map
  std::string json = R"({
 "cluster_name": "CL_ID_1", "command_name":"ListDevices",
 "command_params": {"command": "ListDevices",
 "cluster_id": "CL_ID_1",
 "FM_id": "203",
 "FM_endpoint": "samsung.com"
 }})";

  input.input_buffer = reinterpret_cast<uint8_t*>(strdup(json.c_str()));
  input.len = json.size();

  svk_status status = execute_sync(&pass_thru, &input, &output);

  // Expected fallback due to unknown command
  EXPECT_EQ(status, SVK_STATUS_SUCCESS);

  std::string result(reinterpret_cast<char*>(output.output_buffer), output.len);
  EXPECT_GT(output.len, 0);

  free(input.input_buffer);
  free(output.output_buffer);
}

TEST_F(ServicerTest, InitThrowsException) {
  EXPECT_CALL(mock_cxl_global, init_log(_)).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, init_cxl_plugin()).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, parse_json_key(_, "plugin_dir", _))
      .WillOnce(Throw(std::runtime_error("parse_json_key failed")));
  int status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, InitMissingDeviceIdJson) {
  EXPECT_CALL(mock_cxl_global, init_log(_)).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, init_cxl_plugin()).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, parse_json_key(_, "plugin_dir", _))
      .WillOnce(DoAll(SetArgReferee<2>("logic_modules"), Return(0)));
  EXPECT_CALL(mock_cxl_global, validate_json_file(_)).WillOnce(Return(-1));
  int status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, InitMissingPluginDirKey) {
  EXPECT_CALL(mock_cxl_global, init_log(_)).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, init_cxl_plugin()).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, parse_json_key(_, "plugin_dir", _))
      .WillOnce(Return(-1));
  int status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, InitPluginFailure) {
  EXPECT_CALL(mock_cxl_global, init_log(_)).WillOnce(Return(0));
  EXPECT_CALL(mock_cxl_global, init_cxl_plugin()).WillOnce(Return(-1));
  int status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, InitLoggerUnexpectedError) {
  EXPECT_CALL(mock_cxl_global, init_log(_)).WillOnce(Return(-5));
  int status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, GetDeviceStats_MissingDeviceID) {
  std::unordered_map<std::string, std::string> params = {};  // No device_id
  std::string response = handle_get_device_stats(params);
  EXPECT_THAT(response, ::testing::HasSubstr("Missing parameter: device_id"));
}

TEST_F(ServicerTest, GetDeviceStats_InvalidDeviceIDFormat) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "abc"}};
  std::string response = handle_get_device_stats(params);
  EXPECT_THAT(response, ::testing::HasSubstr("Invalid id format"));
}

TEST_F(ServicerTest, GetDeviceStats_WithSensorStats) {
  sc_device dev(999, "device_stat", 2048, 1);
  DevStaticInfo stat{};
  stat.device_id = 999;
  stat.protocol = "1.1";
  stat.port_type = "ph";
  dev.d_set_static_info(stat);

  DevInfo dyn{};
  dyn.status = "active";
  dev.d_set_dynamic_info(dyn);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);

  StatInfo sinfo{};
  sinfo.device_id = 999;
  sinfo.protocol = "1.1";
  sinfo.port_type = "ph";
  sinfo.status = "active";
  sinfo.total_memory_MB = 1024;
  sinfo.used_memory_MB = 512;
  sinfo.available_memory_MB = 512;
  sinfo.total_bandwidth_MBps = 32000;
  sinfo.used_bandwidth_Bps = 16000;
  sinfo.rw_errors = 0;
  sinfo.latency_us = 10;
  // Assign sensor and cache stats
  sinfo.sensor_stats.emplace();
  sinfo.sensor_stats->fpga_temp = 42;
  sinfo.cache_stats.emplace();
  sinfo.cache_stats->hit_perc = 95;
  sinfo.cache_stats->dirty_cache_gb = 5;

  testAdapter.set_stat_info_for_device(dev.d_get_id(), sinfo);

  std::unordered_map<std::string, std::string> params = {{"device_id", "999"}};
  std::string response = handle_get_device_stats(params);
  EXPECT_EQ(get_json_value(response, "device_id"), "999");
  EXPECT_EQ(get_json_value(response, "used_bandwidth_Bps"), "16000");
}

TEST_F(ServicerTest, GetDeviceStats_WithoutSensorStats) {
  sc_device dev(888, "device_stat_nosensor", 2048, 1);
  DevStaticInfo stat{};
  stat.device_id = 888;
  stat.protocol = "1.1";
  stat.port_type = "ph";
  dev.d_set_static_info(stat);

  DevInfo dyn{};
  dyn.status = "inactive";
  dev.d_set_dynamic_info(dyn);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  StatInfo s;
  s.device_id = 888;
  s.protocol = "1.1";
  s.port_type = "ph";
  s.status = "inactive";
  s.total_memory_MB = 2048;
  s.available_memory_MB = 2048;
  s.used_memory_MB = 0;
  s.total_bandwidth_MBps = 64000;
  s.used_bandwidth_Bps = 0;
  s.rw_errors = 0;
  s.latency_us = 5;
  s.sensor_stats = std::nullopt;

  testAdapter.set_stat_info_for_device(dev.d_get_id(), s);

  std::unordered_map<std::string, std::string> params = {{"device_id", "888"}};
  std::string response = handle_get_device_stats(params);
  EXPECT_EQ(get_json_value(response, "device_id"), "888");
  EXPECT_EQ(get_json_value(response, "status"), "inactive");
}

TEST_F(ServicerTest, InitLog_MissingConfigFile_ReturnsInvalidConfig) {
  remove(LOG_CONF_FILE);
  EXPECT_CALL(mock_cxl_global, g_create_mbox(nullptr)).WillOnce(Return(0));
  svk_status status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_INVALID_CONFIG);
}

TEST_F(ServicerTest, InitLog_Failure_ReturnsFail) {
  create_file(LOG_CONF_FILE, "fail marker");
  svk_status status = initialize(nullptr);
  EXPECT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(ServicerTest, InitLog_Success) {
  create_file(LOG_CONF_FILE, "valid");
  svk_status status = initialize(nullptr);
  EXPECT_NE(status, SVK_STATUS_INVALID_CONFIG);
}

TEST_F(ServicerTest, ListDevices_ArrayContainsNonString) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"([1234, true])"}};
  std::string result = handle_list_devices(params);
  EXPECT_NE(result.find("device_id array must contain strings"),
            std::string::npos);
}

TEST_F(ServicerTest, GetDeviceInfo_EmptyJsonParam) {
  std::unordered_map<std::string, std::string> params = {{"device_id", ""}};
  std::string response = handle_get_device_info(params);
  EXPECT_NE(response.find("Invalid id format"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_ValidAndInvalidIdsInArray) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", R"(["1234", "not_a_number"])"}};
  std::string response = handle_list_devices(params);
  EXPECT_NE(response.find("Invalid id format"), std::string::npos);
}

TEST_F(ServicerTest, ListDevices_InvalidJsonArrayString) {
  std::unordered_map<std::string, std::string> params = {
      {"device_id", "[\"unclosed_string"}};
  std::string result = handle_list_devices(params);
  EXPECT_FALSE(result.find("Invalid device_id array format") !=
               std::string::npos);
}

/*
 * ToDo: Fix me for Ubuntu 24.04
TEST_F(ServicerTest, GetDeviceMetrics_WithCacheAndSensorStats) {
  sc_device dev(1234, "metric_device", 8192, 1);

  DevStaticInfo stat{};
  stat.device_id = 1234;
  stat.total_capacity_MB = 8192;
  stat.protocol = "1.1";
  stat.port_type = "ph";
  dev.d_set_static_info(stat);

  DevInfo dyn{};
  dyn.numa_node = 1;
  dyn.available_capacity_MB = 4096;
  dyn.status = "Healthy";
  dev.d_set_dynamic_info(dyn);

  StatInfo sinfo{};
  sinfo.device_id = 1234;
  sinfo.protocol = "1.1";
  sinfo.port_type = "ph";
  sinfo.status = "Healthy";
  sinfo.total_memory_MB = 8192;
  sinfo.used_memory_MB = 4096;
  sinfo.available_memory_MB = 4096;
  sinfo.total_bandwidth_MBps = 24000;
  sinfo.used_bandwidth_Bps = 12000;
  sinfo.rw_errors = 0;
  sinfo.latency_us = 0;
  // Assign sensor and cache stats
  sinfo.sensor_stats.emplace();
  sinfo.sensor_stats->fpga_temp = 60;
  sinfo.cache_stats.emplace();
  sinfo.cache_stats->hit_perc = 95;
  sinfo.cache_stats->dirty_cache_gb = 5;

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);
  testAdapter.set_stat_info_for_device(dev.d_get_id(), sinfo);

  std::unordered_map<std::string, std::string> params = {{"device_id", "1234"}};
  std::string response = handle_get_device_metrics(params);

  json_error_t error;
  json_t* root = json_loads(response.c_str(), 0, &error);
  ASSERT_NE(root, nullptr) << "Invalid JSON: " << error.text;
  EXPECT_EQ(json_integer_value(json_object_get(root, "source")), 1234);
  json_t* obs = json_object_get(root, "observations");
  ASSERT_NE(obs, nullptr) << "Missing 'observations' field in response";
  EXPECT_EQ(json_integer_value(json_object_get(obs, "total_memory_MB")), 8192);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "used_bandwidth_Bps")),
            12000);
  json_decref(root);
}

TEST_F(ServicerTest, GetDeviceMetrics_MissingParam) {
  std::unordered_map<std::string, std::string> params = {};
  std::string response = handle_get_device_metrics(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Missing parameter: device_id");
}

TEST_F(ServicerTest, GetDeviceMetrics_InvalidFormat) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "abc"}};
  std::string response = handle_get_device_metrics(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"), "Invalid id format");
}

TEST_F(ServicerTest, GetDeviceMetrics_DeviceNotFound) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "9999"}};
  EXPECT_THROW({ handle_get_device_metrics(params); }, std::runtime_error);
}

TEST_F(ServicerTest, HandleGetDeviceMetrics_Observations) {
  MetricsInfo base{};
  base.domain = "telemetry";
  base.feature_id = 99;
  set_metrics_info(base);

  sc_device dev(1234, "metric_device", 8192, 1);
  DevStaticInfo sinfo{};
  sinfo.device_id = 1234;
  dev.d_set_static_info(sinfo);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);

  StatInfo s{};
  s.device_id = 1234;
  s.total_memory_MB = 8192;
  s.used_memory_MB = 4096;
  s.available_memory_MB = 4096;
  s.total_bandwidth_MBps = 24000;
  s.used_bandwidth_Bps = 12000;
  s.rw_errors = 0;
  s.latency_us = 0;

  s.sensor_stats.emplace();
  s.sensor_stats->fpga_temp = 62;

  s.cache_stats.emplace();
  s.cache_stats->hit_perc = 95;
  s.cache_stats->dirty_cache_gb = 7;

  testAdapter.set_stat_info_for_device(dev.d_get_id(), s);

  std::string out = handle_get_device_metrics({{"device_id", "1234"}});

  json_error_t err{};
  json_t* root = json_loads(out.c_str(), 0, &err);
  ASSERT_TRUE(root) << err.text;

  json_t* obs = json_object_get(root, "observations");
  ASSERT_TRUE(obs);

  json_decref(root);
}

TEST_F(ServicerTest, GetDeviceMetrics_AllDynamicFields) {
  sc_device dev(1234, "metric_device", 8192, 1);
  DevStaticInfo stat{};
  stat.device_id = 1234;
  stat.total_capacity_MB = 8192;
  stat.protocol = "1.1";
  stat.port_type = "ph";
  dev.d_set_static_info(stat);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);
  StatInfo s{};
  s.device_id = 1234;
  s.protocol = "1.1";
  s.port_type = "ph";
  s.status = "Healthy";
  s.total_memory_MB = 8192;
  s.used_memory_MB = 4096;
  s.available_memory_MB = 4096;
  s.total_bandwidth_MBps = 24000;
  s.used_bandwidth_Bps = 12000;
  s.rw_errors = 0;
  s.latency_us = 0;

  s.sensor_stats.emplace();
  s.sensor_stats->fpga_temp = 61;
  s.cache_stats.emplace();
  s.cache_stats->hit_perc = 95;
  s.cache_stats->dirty_cache_gb = 7;

  testAdapter.set_stat_info_for_device(dev.d_get_id(), s);
  {
    StatInfo echo = testAdapter.get_device_stats(dev.d_get_id());
    ASSERT_TRUE(echo.sensor_stats.has_value());
    ASSERT_TRUE(echo.cache_stats.has_value());
    EXPECT_EQ(echo.sensor_stats->fpga_temp, 61);
    EXPECT_EQ(echo.cache_stats->hit_perc, 95);
    EXPECT_EQ(echo.cache_stats->dirty_cache_gb, 7);
    EXPECT_EQ(echo.total_memory_MB, 8192u);
    EXPECT_EQ(echo.used_memory_MB, 4096u);
    EXPECT_EQ(echo.available_memory_MB, 4096u);
    EXPECT_EQ(echo.total_bandwidth_MBps, 24000u);
    EXPECT_EQ(echo.used_bandwidth_Bps, 12000u);
  }

  std::unordered_map<std::string, std::string> params = {{"device_id", "1234"}};
  std::string response = handle_get_device_metrics(params);
  json_error_t error;
  json_t* root = json_loads(response.c_str(), 0, &error);
  ASSERT_NE(root, nullptr) << "Invalid JSON: " << error.text;
  EXPECT_EQ(json_integer_value(json_object_get(root, "source")), 1234);
  json_t* obs = json_object_get(root, "observations");
  ASSERT_NE(obs, nullptr) << "Missing 'observations' field";
  EXPECT_EQ(json_integer_value(json_object_get(obs, "total_memory_MB")), 8192);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "used_memory_MB")), 4096);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "available_memory_MB")),
            4096);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "total_bandwidth_MBps")),
            24000);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "used_bandwidth_Bps")),
            12000);
  json_decref(root);
}
*/

TEST_F(ServicerTest, GetDeviceStats_AllFields) {
  sc_device dev(2468, "stats_device", 4096, 2);
  DevStaticInfo sinfo{};
  sinfo.device_id = 2468;
  dev.d_set_static_info(sinfo);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);

  StatInfo s{};
  s.device_id = 2468;
  s.total_memory_MB = 4096;
  s.used_memory_MB = 1024;
  s.available_memory_MB = 3072;
  s.total_bandwidth_MBps = 10000;
  s.used_bandwidth_Bps = 777;
  s.rw_errors = 0;
  s.latency_us = 0;

  s.sensor_stats.emplace();
  s.sensor_stats->fpga_temp = 62;

  s.cache_stats.emplace();
  s.cache_stats->hit_perc = 90;
  s.cache_stats->dirty_cache_gb = 3;

  testAdapter.set_stat_info_for_device(dev.d_get_id(), s);
  std::string out = handle_get_device_stats({{"device_id", "2468"}});

  json_error_t err{};
  json_t* root = json_loads(out.c_str(), 0, &err);
  ASSERT_TRUE(root) << err.text;

  EXPECT_EQ(json_integer_value(json_object_get(root, "total_memory_MB")), 4096);
  EXPECT_EQ(json_integer_value(json_object_get(root, "used_memory_MB")), 1024);
  EXPECT_EQ(json_integer_value(json_object_get(root, "available_memory_MB")),
            3072);
  EXPECT_EQ(json_integer_value(json_object_get(root, "total_bandwidth_MBps")),
            10000);
  EXPECT_EQ(json_integer_value(json_object_get(root, "used_bandwidth_Bps")),
            777);
  EXPECT_EQ(json_integer_value(json_object_get(root, "rw_errors")), 0);
  EXPECT_EQ(json_integer_value(json_object_get(root, "latency")), 0);
  json_decref(root);
}

TEST_F(ServicerTest, GetDeviceStats_noSensor) {
  sc_device dev(1357, "dev", 1024, 4);
  DevStaticInfo sinfo{};
  sinfo.device_id = 1357;
  dev.d_set_static_info(sinfo);

  StatInfo s{};
  s.device_id = 1357;
  s.total_memory_MB = 2048;
  s.used_memory_MB = 512;
  s.available_memory_MB = 1536;
  s.total_bandwidth_MBps = 8000;
  s.used_bandwidth_Bps = 222;

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);
  testAdapter.set_stat_info_for_device(dev.d_get_id(), s);

  std::string out = handle_get_device_stats({{"device_id", "1357"}});

  json_error_t err{};
  json_t* root = json_loads(out.c_str(), 0, &err);
  ASSERT_TRUE(root) << err.text;

  EXPECT_EQ(json_integer_value(json_object_get(root, "total_memory_MB")), 2048);
  EXPECT_EQ(json_integer_value(json_object_get(root, "used_memory_MB")), 512);
  EXPECT_EQ(json_integer_value(json_object_get(root, "available_memory_MB")),
            1536);
  EXPECT_EQ(json_integer_value(json_object_get(root, "total_bandwidth_MBps")),
            8000);
  EXPECT_EQ(json_integer_value(json_object_get(root, "used_bandwidth_Bps")),
            222);

  json_t* rw = json_object_get(root, "rw_errors");
  if (rw) {
    EXPECT_EQ(json_integer_value(rw), 0);
  }
  json_t* lat = json_object_get(root, "latency");
  if (lat) {
    EXPECT_EQ(json_integer_value(lat), 0);
  }

  EXPECT_EQ(json_object_get(root, "fpga_temp_in_F"), nullptr);

  json_decref(root);
}

/*
 * ToDo: Fix me for Ubuntu 24.04
TEST_F(ServicerTest, GetDeviceMetrics_) {
  MetricsInfo base{};
  base.domain = "telemetry";
  base.feature_id = 2;
  set_metrics_info(base);

  sc_device dev(4321, "metric_device2", 4096, 2);
  DevStaticInfo sinfo{};
  sinfo.device_id = 4321;
  dev.d_set_static_info(sinfo);

  g_dev_mgr->register_device(dev.d_get_id(), &testAdapter);
  testAdapter.add_mock_device(dev);

  StatInfo s{};
  s.device_id = 4321;
  s.total_memory_MB = 4096;
  s.used_memory_MB = 1024;
  s.available_memory_MB = 3072;
  s.total_bandwidth_MBps = 10000;
  s.used_bandwidth_Bps = 111;
  s.rw_errors = 0;
  s.latency_us = 0;

  s.sensor_stats.reset();
  s.cache_stats.reset();

  testAdapter.set_stat_info_for_device(dev.d_get_id(), s);

  std::string out = handle_get_device_metrics({{"device_id", "4321"}});

  json_error_t err{};
  json_t* root = json_loads(out.c_str(), 0, &err);
  ASSERT_TRUE(root) << err.text;
  json_t* obs = json_object_get(root, "observations");
  ASSERT_TRUE(obs);

  EXPECT_EQ(json_integer_value(json_object_get(obs, "total_memory_MB")), 4096);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "used_memory_MB")), 1024);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "available_memory_MB")),
            3072);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "total_bandwidth_MBps")),
            10000);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "used_bandwidth_Bps")),
            111);

  EXPECT_EQ(json_integer_value(json_object_get(obs, "cache_hit_perc")), 0);
  EXPECT_EQ(json_integer_value(json_object_get(obs, "fpga_temp_in_F")), 0);
  json_decref(root);
}
*/
