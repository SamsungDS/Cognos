#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "sc_global.h"
#include "sc_mbox.h"
#include "sc_servicer.h"



extern "C"{
#include "jansson.h"
#include "/opt/stg/mbox_a1.h"
}

using namespace std;

// Global instance
sc_global cxl_global;



class MockScGlobal : public sc_global{
public:
    MOCK_METHOD(int, g_create_mbox, (struct StaticPortInfo*), ());
    int init_cxl_plugin() {
        struct StaticPortInfo pinfo;
        mbox_get_static_config(&pinfo);
        int result = g_create_mbox(&pinfo);
        return result;
    }

    int mock_register_plugin(std::unordered_map<std::string, std::function<std::string(std::string)>>& function_map) {
        std::cout << "Mocked register_plugin function called" << std::endl;
        function_map["ListDevices"] = ListDevices;
        function_map["ListHosts"] = ListHosts;
        function_map["AttachMemory"] = AttachMemory;
        function_map["DetachMemory"] = DetachMemory;
        function_map["SetupInfo"] = SetupInfo;
        init_cxl_plugin();
        return 0;
    }

    // Redirect cxl_global to use this mock instance
    static MockScGlobal& instance() {
        static MockScGlobal mock;
        return mock;
    }

};



class ServicerTest : public ::testing::Test {
protected:
    void SetUp() override {
	function_map.clear();
        mock_cxl_global = &MockScGlobal::instance();
    }
    void TearDown() override {
	::testing::Mock::VerifyAndClearExpectations(mock_cxl_global);
        ::testing::Mock::AllowLeak(mock_cxl_global);
    }
    std::unordered_map<std::string, std::function<std::string(std::string)>> function_map;
    MockScGlobal* mock_cxl_global;
};


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

TEST_F(ServicerTest, ListDevicesTest) {
    std::string input = "test_input";
    std::string result = ListDevices(input);
    std::string expected_output = "test_input;device names={\"devices\": []}";
    std::string buffer;
    size_t SIZE_B = 0;
    size_t bytes_written = cxl_global.list_devices(buffer, SIZE_B);
    if (bytes_written > 0 && bytes_written <= SIZE_B) {
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, ListHostsTest) {
    std::string input = "test_input";
    std::string result = ListHosts(input);
    std::string expected_output = "test_input;host names={\"hosts\": []}";
    std::string buffer;
    size_t SIZE_B = 0;
    size_t bytes_written = cxl_global.list_hosts(buffer, SIZE_B);
    if (bytes_written > 0 && bytes_written <= SIZE_B) {
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, AttachMemoryTest) {
    std::string input = "dev_id=1;host_id=1;mode=rw";
    std::string result = AttachMemory(input);
    std::string expected_output = "dev_id=1;host_id=1;mode=rw;AttachMemory={\"rc\": 1}";
    std::string buffer;
    size_t SIZE_B = 0;
    size_t bytes_written = cxl_global.dev_attach(1, 1, "rw", 203, buffer, SIZE_B);
    if (bytes_written > 0 && bytes_written <= SIZE_B) {
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, DetachMemoryTest) {
    std::string input = "dev_id=1;host_id=1;mode=rw";
    std::string result = DetachMemory(input);
    std::string expected_output = "dev_id=1;host_id=1;mode=rw;DetachMemory={\"rc\": 1}";
    std::string buffer;
    size_t SIZE_B = 0;
    size_t bytes_written = cxl_global.dev_detach(1, 1, "rw", 203, buffer, SIZE_B);
    if (bytes_written > 0 && bytes_written <= SIZE_B) {
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, SetupInfoTest) {
    std::string input = "test_input";
    std::string result = SetupInfo(input);
    std::string expected_output = "test_input;setup_info={\"Board\": {\"board_name\": \"Example Direct Config\", \"Mgmt_port_type\": \"PCIe\", \"json_version\": \"0100\", \"switch_mode\": \"direct\", \"management_port\": 1}, \"Hosts\": [{\"host_name\": \"Host 1 LNK0\", \"host_port\": 3, \"deinit_active\": 1, \"host_port_type\": \"CXL_11\", \"classcode\": 0, \"host_aspm_active\": 1, \"host_sris_active\": 1, \"host_equalization\": 1, \"host_speed\": 5, \"host_width\": 8, \"host_addr\": \"0x008080000000\", \"host_size\": \"0x007f80000000\", \"endpoint\": [{\"memdev\": \"mem- 7\", \"target\": 7, \"mem_addr\": \"0x00c000000000\", \"mem_size\": \"0x004000000000\", \"dev_offset\": \"0\"}, {\"memdev\": \"mem- 5\", \"target\": 5, \"mem_addr\": \"0x008080000000\", \"mem_size\": \"0x003f80000000\", \"dev_offset\": \"0\"}]}], \"Devices\": [{\"dev_name\": \"DEV_5-256G\", \"dev_port\": 5, \"dev_addr\": \"0x008080000000\", \"dev_size\": \"0x003f80000000\", \"dev_aspm_active\": 1, \"dev_sris_active\": 1, \"dev_lock_active\": 1, \"dev_speed\": 5, \"dev_width\": 8, \"dev_port_type\": \"CXL_20\"}, {\"dev_name\": \"DEV_7-256G\", \"dev_port\": 7, \"dev_addr\": \"0x00c000000000\", \"dev_size\": \"0x004000000000\", \"dev_aspm_active\": 1, \"dev_sris_active\": 1, \"dev_lock_active\": 1, \"dev_speed\": 5, \"dev_width\": 8, \"dev_port_type\": \"CXL_20\"}]}";
    std::string buffer;
    size_t SIZE_B = 0;
    size_t bytes_written = cxl_global.fetch_setup_info(buffer, SIZE_B);
    if (bytes_written > 0 && bytes_written <= SIZE_B) {
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}




TEST_F(ServicerTest, RegisterPluginTest) {
    EXPECT_CALL(*mock_cxl_global, g_create_mbox(testing::_))
        .WillOnce(testing::Return(0));
    int result = mock_cxl_global->mock_register_plugin(function_map);
    EXPECT_EQ(result, 0);
    EXPECT_EQ(function_map.size(), 5);
    EXPECT_NE(function_map.find("ListDevices"), function_map.end());
    EXPECT_NE(function_map.find("ListHosts"), function_map.end());
    EXPECT_NE(function_map.find("AttachMemory"), function_map.end());
    EXPECT_NE(function_map.find("DetachMemory"), function_map.end());
    EXPECT_NE(function_map.find("SetupInfo"), function_map.end());
}

