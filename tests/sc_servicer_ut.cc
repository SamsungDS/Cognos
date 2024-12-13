#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "sc_global.h"
#include "sc_mbox.h"
#include "sc_servicer.h"
#include "tuner.h"
#include "framework_downstream.h"
#include "sc_servicer_internal.h"

extern "C"{
#include "jansson.h"
#include "mbox_a1.h"
}


#define DELIMITER ","

using namespace std;

// Global instance
sc_global cxl_global;
const std::string json_filepath = "cxl.conf";
const std::string input_conf_path = "input.conf";

using ::testing::_;
using ::testing::Return;

//function pointers for the commands
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

    void SetUp() override {
        cxl_global = mock_cxl_global;
	temp_filename.clear();
    }

    void TearDown() override {
	// Clean up temporary file 
        if (!temp_filename.empty()) {
            remove(temp_filename.c_str());
        }
	// Clean up temporary files
        remove("empty_file.json");
        remove("valid_file.json");
    }

    // Helper function to load JSON from a file
    json_t* load_json_from_file(const std::string& file_path) {
        json_error_t error;
        json_t* root = json_load_file(file_path.c_str(), 0, &error);
        if (!root) {
            std::cerr << "Error loading JSON from file: " << error.text << " at line " << error.line << std::endl;
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

};


TEST_F(ServicerTest, InitCxlPluginSuccess) {
    EXPECT_CALL(mock_cxl_global, g_create_mbox(_))
        .WillOnce(Return(0));  
    int result = init_cxl_plugin();
    EXPECT_EQ(result, 0);
}


TEST_F(ServicerTest, InitializeSuccessTest) {
    EXPECT_CALL(mock_cxl_global, g_create_mbox(_))
        .WillOnce(Return(0));  
    svk_status status = initialize(nullptr);
    ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}


TEST_F(ServicerTest, InitializeFailureTest) {
    EXPECT_CALL(mock_cxl_global, g_create_mbox(nullptr))
        .WillOnce(Return(-1));  
    svk_status status = initialize(nullptr);
    ASSERT_EQ(status, SVK_STATUS_SUCCESS);
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
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(ServicerTest, ExecuteAsyncTest) {
    svk_pass_thru_cmd pass_thru;
    svk_postprocess_fn postprocess_fn;
    svk_status status = execute_async(&pass_thru, &postprocess_fn);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(ServicerTest, CleanUpTest) {
    svk_status status = clean_up(nullptr);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(ServicerTest, ConfigureDeviceIfAnyTest) {
    svk_device_ctx device_handles;
    void *config_details = nullptr;
    uint64_t length = 0;
    void *resp = nullptr;
    svk_status status = configure_device_if_any(config_details, &device_handles, length, resp);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(ServicerTest, ExecuteSyncDevTest) {
    svk_input input;
    svk_output output;
    svk_pass_thru_cmd pass_thru;
    input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=ListDevices"));
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
    input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=DetachMemory;dev_id=549755813888;host_id=551903297536;mode=direct"));
    input.len = strlen("command=DetachMemory;dev_id=549755813888;host_id=551903297536;mode=direct");
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
    input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=AttachMemory;dev_id=549755813888;host_id=551903297536;mode=direct"));
    input.len = strlen("command=AttachMemory;dev_id=549755813888;host_id=551903297536;mode=direct");
    svk_status status = execute_sync(&pass_thru, &input, &output);
    ASSERT_EQ(status, SVK_STATUS_SUCCESS);
    ASSERT_EQ(output.status, SVK_STATUS_SUCCESS);
    ASSERT_NE(output.len, 0);
    ASSERT_NE(output.output_buffer, nullptr);
    free(input.input_buffer);
    free(output.output_buffer);
}


TEST_F(ServicerTest, ExecuteSyncInvalidCommandTest) {
    svk_input input;
    svk_output output;
    svk_pass_thru_cmd pass_thru;
    input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=InvalidCommand"));
    input.len = strlen("command=InvalidCommand");
    svk_status status = execute_sync(&pass_thru, &input, &output);
    ASSERT_EQ(status, SVK_STATUS_FAIL); 
    free(input.input_buffer);
}


TEST_F(ServicerTest, GetIPAddressSuccess) {
    std::string ip = get_ip_address(json_filepath);
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

    // Simulate file creation and reading (or mock the file reading)
    std::ofstream out("test_no_switch.json");
    out << json_content;
    out.close();
    std::string ip = get_ip_address("test_no_switch.json");
    // Expect an empty string because "switch" is missing
    EXPECT_EQ(ip, "");
    // Clean up the test file
    std::remove("test_no_switch.json");
}


TEST_F(ServicerTest, MissingIPAddressField) {
    // Create a mock JSON file with no "ip_address" field
    std::string json_content = R"(
    {
        "switch": {}
    })";
    // Simulate file creation and reading (or mock the file reading)
    std::ofstream out("test_no_ip_address.json");
    out << json_content;
    out.close();
    std::string ip = get_ip_address("test_no_ip_address.json");
    // Expect an empty string because "ip_address" is missing
    EXPECT_EQ(ip, "");
    // Clean up the test file
    std::remove("test_no_ip_address.json");
}


TEST_F(ServicerTest, FailToLoadJsonFile) {
    // Simulate a missing or malformed JSON file
    std::string invalid_filepath = "non_existent.json";
    std::string ip = get_ip_address(invalid_filepath);
    // Expect an empty string since the file cannot be loaded
    EXPECT_EQ(ip, "");
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
    ASSERT_TRUE(json_is_array(fabric_managers)) << "fabric_managers should be an array";
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
    ASSERT_TRUE(json_is_array(fabric_managers)) << "fabric_managers should be an array";
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
    ASSERT_TRUE(result.find(",") != std::string::npos) << "Output should contain delimiter.";
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
    ASSERT_EQ(result, "[]") << "Output should be an empty JSON array when no managers are found.";
    // Clean up
    free(input.input_buffer);
    free(output.output_buffer);
}

TEST_F(ServicerTest, SetupInfoWithNoFMKeys) {
    // Mock cxl_global to return an empty list of keys
    EXPECT_CALL(mock_cxl_global, get_fm_keys()).WillRepeatedly(Return(std::vector<sc_id>{}));
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
    ASSERT_EQ(result, "[]") << "Output should be an empty JSON array when no keys are present.";
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
    // Capture stderr output to verify the error message
    testing::internal::CaptureStderr();
    json_t* result = load_json_config(temp_filename);
    std::string output = testing::internal::GetCapturedStderr();
    EXPECT_EQ(result, nullptr);
    EXPECT_TRUE(output.find("Invalid or missing 'fabric_managers' array in configuration") != std::string::npos);
}


TEST_F(ServicerTest, FabricManagersNotArray) {
    std::string json_content = R"({
        "fabric_managers": {
            "id": 1001
        }
    })";
    // Write the content to a temporary file
    temp_filename = write_json_to_temp_file(json_content);
    // Capture stderr output to verify the error message
    testing::internal::CaptureStderr();
    json_t* result = load_json_config(temp_filename);
    std::string output = testing::internal::GetCapturedStderr();
    // Verify the result
    EXPECT_EQ(result, nullptr);
    EXPECT_TRUE(output.find("Invalid or missing 'fabric_managers' array in configuration") != std::string::npos);
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
    // Capture the output printed to std::cout
    testing::internal::CaptureStdout();
    // Call the function to create and add DevCMMB to cxl_global
    create_dev_cmmb(config);
    std::string output = testing::internal::GetCapturedStdout();
    EXPECT_TRUE(output.find("Added DevCMMB to map.") != std::string::npos);
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
    std::string ip = get_ip_address("test_ip_not_string.json");
    EXPECT_EQ(ip, "");
    std::remove("test_ip_not_string.json");
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
    ASSERT_TRUE(is_valid_ip("192.168.1.1")) << "Valid IP address should return true.";
    ASSERT_FALSE(is_valid_ip("300.168.1.1")) << "Invalid IP address should return false.";
    ASSERT_FALSE(is_valid_ip("192.168.1")) << "Incomplete IP address should return false.";
    ASSERT_FALSE(is_valid_ip("0.123.123.123")) << "InValid IP address should return false.";
    ASSERT_FALSE(is_valid_ip("abc.def.ghi.jkl")) << "Non-numeric IP address should return false.";
}

TEST_F(ServicerTest, StartTuning) {
    svk_input input;
    svk_output output;
    svk_pass_thru_cmd pass_thru;
    std::string cmd = "command=StartTuning;application=gemfire;application_id=101010;dram_node=0;cxl_node=1;sla_iops=150000;sla_size=1024;sla_latencyus=750";
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
    std::string cmd = "command=StopTuning;application=gemfire;application_id=101010";
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
