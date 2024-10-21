#include <gtest/gtest.h>
#include "sc_cmmd.h"
#include <jansson.h>
#include <string>
#include <iostream>

const std::string json_filepath = "input.conf";

// Test fixture for DevCMMB
class DevCMMDTest : public ::testing::Test {
protected:
    DevCMMD* devCmmd;
    json_t* config;
    void SetUp() override {
        // Load the JSON configuration from the file
        config = load_json_file(json_filepath);
        ASSERT_NE(config, nullptr) << "Failed to load JSON config from file";
        json_t* fabric_managers = json_object_get(config, "fabric_managers");
        ASSERT_TRUE(json_is_array(fabric_managers)) << "Expected fabric_managers to be an array";
        json_t* first_fabric_manager = json_array_get(fabric_managers, 0);
        ASSERT_NE(first_fabric_manager, nullptr) << "Failed to get the first fabric manager entry";
        devCmmd = new DevCMMD(first_fabric_manager);
    }
    void TearDown() override {
        delete devCmmd;
        json_decref(config);
    }

public:
    json_t* load_json_file(const std::string& file_path) {
        json_error_t error;
        json_t* root = json_load_file(file_path.c_str(), 0, &error);
        if (!root) {
            std::cerr << "Error loading JSON from file: " << error.text << " at line " << error.line << std::endl;
            return nullptr;
        }
        return root;
    }

};

// Constructor Test
TEST_F(DevCMMDTest, ConstructorInitialization) {
    // Verify that DevCMMB was initialized with expected values
    EXPECT_EQ(devCmmd->get_fm_type(), "FM_DIRECT_CMMD"); 
    EXPECT_NE(devCmmd->get_fmid().get_sc_id(), 0);     
}

//Test for correct initialization and type retrieval
TEST_F(DevCMMDTest, Initialization) {
    EXPECT_EQ(devCmmd->get_fm_type(), "FM_DIRECT_CMMD");
}

// Test setup_info method to ensure it generates expected output
TEST_F(DevCMMDTest, SetupInfo) {
    std::string buffer(4096, '\0');
    size_t bytes_written = devCmmd->setup_info(buffer);
    EXPECT_GT(bytes_written, 0);
    buffer.resize(bytes_written);  
}

// Test cleanup method to clear data
TEST_F(DevCMMDTest, Cleanup) {
    devCmmd->cleanup();
    std::string buffer;
    size_t bytes_written = devCmmd->setup_info(buffer);
    EXPECT_EQ(bytes_written, 0); 
    EXPECT_TRUE(buffer.empty()); 
}

