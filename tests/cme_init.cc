#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "cme_init.h"
#include "tuner.h"
#include "framework_downstream.h"

extern "C"{
#include "jansson.h"
}


#define DELIMITER ","

using namespace std;

using ::testing::_;
using ::testing::Return;

//function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);

TEST_F(cmeTest, InitCxlPluginSuccess) {
    EXPECT_CALL(mock_cxl_global, g_create_mbox(_))
        .WillOnce(Return(0));  
    int result = init_cxl_plugin();
    EXPECT_EQ(result, 0);
}


TEST_F(cmeTest, InitializeSuccessTest) {
    EXPECT_CALL(mock_cxl_global, g_create_mbox(_))
        .WillOnce(Return(0));  
    svk_status status = initialize(nullptr);
    ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}


TEST_F(cmeTest, InitializeFailureTest) {
    EXPECT_CALL(mock_cxl_global, g_create_mbox(nullptr))
        .WillOnce(Return(-1));  
    svk_status status = initialize(nullptr);
    ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}


TEST_F(cmeTest, TokenizeTest) {
    string input = "key1=value1;key2=value2;key3=value3";
    unordered_map<string, string> tokens = tokenize(input);
    EXPECT_EQ(tokens.size(), 3);
    EXPECT_EQ(tokens["key1"], "value1");
    EXPECT_EQ(tokens["key2"], "value2");
    EXPECT_EQ(tokens["key3"], "value3");
}


TEST_F(cmeTest, TokenHelperTest) {
    string input = "key1=value1;key2=value2;key3=value3";
    unordered_map<string, string> tokens = token_helper(input);
    EXPECT_EQ(tokens.size(), 3);
    EXPECT_EQ(tokens["key1"], "value1");
    EXPECT_EQ(tokens["key2"], "value2");
    EXPECT_EQ(tokens["key3"], "value3");
}


TEST_F(cmeTest, GetSupportedFeatureListTest) {
    feature_id feat_id;
    char feature_names[256];
    svk_status status = get_supported_feature_list(&feat_id, feature_names);
    ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}


TEST_F(cmeTest, IsLicenseValidTest) {
    svk_status status = is_license_valid(nullptr);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(cmeTest, ExecuteAsyncTest) {
    svk_pass_thru_cmd pass_thru;
    svk_postprocess_fn postprocess_fn;
    svk_status status = execute_async(&pass_thru, &postprocess_fn);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(cmeTest, CleanUpTest) {
    svk_status status = clean_up(nullptr);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(cmeTest, ConfigureDeviceIfAnyTest) {
    svk_device_ctx device_handles;
    void *config_details = nullptr;
    uint64_t length = 0;
    void *resp = nullptr;
    svk_status status = configure_device_if_any(config_details, &device_handles, length, resp);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(cmeTest, ExecuteSyncDevTest) {
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


TEST_F(cmeTest, ExecuteSyncHostTest) {
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


TEST_F(cmeTest, ExecuteSyncDetachTest) {
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


TEST_F(cmeTest, ExecuteSyncAttachTest) {
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


TEST_F(cmeTest, ExecuteSyncInvalidCommandTest) {
    svk_input input;
    svk_output output;
    svk_pass_thru_cmd pass_thru;
    input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=InvalidCommand"));
    input.len = strlen("command=InvalidCommand");
    svk_status status = execute_sync(&pass_thru, &input, &output);
    ASSERT_EQ(status, SVK_STATUS_FAIL); 
    free(input.input_buffer);
}


TEST_F(cmeTest, GetIPAddressSuccess) {
    std::string ip = get_ip_address(json_filepath);
    EXPECT_EQ(ip, "105.140.86.13");  
}

TEST_F(cmeTest, IPAddressIsNotString) {
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

TEST_F(cmeTest, MissingFile) {
    // Ensure the file does not exist
    std::string missing_file = "missing_file.json";
    remove(missing_file.c_str());
    ASSERT_TRUE(is_file_empty_or_missing(missing_file))
        << "The function should return true for a missing file.";
}

TEST_F(cmeTest, EmptyFile) {
    // Create an empty file
    std::string empty_file = "empty_file.json";
    create_file(empty_file, "");
    ASSERT_TRUE(is_file_empty_or_missing(empty_file))
        << "The function should return true for an empty file.";
}

TEST_F(cmeTest, ValidNonEmptyFile) {
    // Create a valid non-empty file
    std::string valid_file = "valid_file.json";
    create_file(valid_file, R"({"key": "value"})");
    ASSERT_FALSE(is_file_empty_or_missing(valid_file))
        << "The function should return false for a valid non-empty file.";
}

TEST_F(cmeTest, IsValidIP) {
    ASSERT_TRUE(is_valid_ip("192.168.1.1")) << "Valid IP address should return true.";
    ASSERT_FALSE(is_valid_ip("300.168.1.1")) << "Invalid IP address should return false.";
    ASSERT_FALSE(is_valid_ip("192.168.1")) << "Incomplete IP address should return false.";
    ASSERT_FALSE(is_valid_ip("0.123.123.123")) << "InValid IP address should return false.";
    ASSERT_FALSE(is_valid_ip("abc.def.ghi.jkl")) << "Non-numeric IP address should return false.";
}

TEST_F(cmeTest, StartTuning) {
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

TEST_F(cmeTest, StopTuning) {
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
