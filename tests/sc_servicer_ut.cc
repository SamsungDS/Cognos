#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "sc_global.h"
#include "sc_mbox.h"
#include "sc_servicer.h"
#include "framework_downstream.h"


extern "C"{
#include "jansson.h"
#include "mbox_a1.h"
}

using namespace std;

// Global instance
sc_global cxl_global;
const std::string json_filepath = "cxl.conf";

using ::testing::_;
using ::testing::Return;

//function pointers for the commands
typedef std::string (*CommandFunc)(const std::string&);

class MockScGlobal : public sc_global {
public:
    MOCK_METHOD(int, g_create_mbox, (StaticPortInfo*), ());
};


// Test fixture
MockScGlobal mock_cxl_global;
class ServicerTest : public ::testing::Test {
protected:
    void SetUp() override {
        cxl_global = mock_cxl_global;
    }
    void TearDown() override {
        // Cleanup if necessary
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


TEST_F(ServicerTest, ExecuteSyncSetUPTest) {
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
