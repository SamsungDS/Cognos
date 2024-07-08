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
    std::string expected_output = "test_input;device names=";
    std::string buffer;
    size_t bytes_written = cxl_global.list_devices(buffer);
    if (bytes_written > 0 && bytes_written <= buffer.size()) {
	buffer.resize(bytes_written);    
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, ListHostsTest) {
    std::string input = "test_input";
    std::string result = ListHosts(input);
    std::string expected_output = "test_input;host names=";
    std::string buffer;
    size_t bytes_written = cxl_global.list_hosts(buffer);
    if (bytes_written > 0 && bytes_written <= buffer.size()) {
	buffer.resize(bytes_written);    
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, AttachMemoryTest) {
    std::string input = "dev_id=1;host_id=1;mode=rw";
    std::string result = AttachMemory(input);
    std::string expected_output = "dev_id=1;host_id=1;mode=rw;AttachMemory=";
    std::string buffer;
    size_t bytes_written = cxl_global.dev_attach(1, 1, "rw", 203, buffer);
    if (bytes_written > 0 && bytes_written <= buffer.size()) {
	buffer.resize(bytes_written);    
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, DetachMemoryTest) {
    std::string input = "dev_id=1;host_id=1;mode=rw";
    std::string result = DetachMemory(input);
    std::string expected_output = "dev_id=1;host_id=1;mode=rw;DetachMemory=";
    std::string buffer;
    size_t bytes_written = cxl_global.dev_detach(1, 1, "rw", 203, buffer);
    if (bytes_written > 0 && bytes_written <= buffer.size()) {
	buffer.resize(bytes_written);    
        expected_output += buffer;
    }
    ASSERT_EQ(result, expected_output);
}


TEST_F(ServicerTest, SetupInfoTest) {
    std::string input = "test_input";
    std::string result = SetupInfo(input);
    std::string expected_output = "test_input;setup_info=";
    std::string buffer;
    size_t bytes_written = cxl_global.fetch_setup_info(buffer);
    if (bytes_written > 0 && bytes_written <= buffer.size()) {
	buffer.resize(bytes_written);    
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

