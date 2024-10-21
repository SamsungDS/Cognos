#include <gtest/gtest.h>
#include "sc_cmmh.h"
#include <jansson.h>
#include <string>
#include <iostream>

const std::string json_filepath = "input.conf";

// Test fixture for DevCMMH
class DevCMMHTest : public ::testing::Test {
protected:
    DevCMMH* devCmmh;
    json_t* config;

    void SetUp() override {
        // Load the JSON configuration from the file
        config = load_json_file(json_filepath);
        ASSERT_NE(config, nullptr) << "Failed to load JSON config from file";
        json_t* fabric_managers = json_object_get(config, "fabric_managers");
        ASSERT_TRUE(json_is_array(fabric_managers)) << "Expected fabric_managers to be an array";
        json_t* first_fabric_manager = json_array_get(fabric_managers, 0);
        ASSERT_NE(first_fabric_manager, nullptr) << "Failed to get the first fabric manager entry";
        devCmmh = new DevCMMH(first_fabric_manager);
    }

    void TearDown() override {
        delete devCmmh;
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


// Test setup_info method to ensure it generates expected output
TEST_F(DevCMMHTest, SetupInfo_) {
    std::string buffer(4096, '\0');
    size_t bytes_written = devCmmh->setup_info(buffer);
    EXPECT_GT(bytes_written, 0);
    buffer.resize(bytes_written);  
}

// Test cleanup method to clear data
TEST_F(DevCMMHTest, Cleanup_) {
    devCmmh->cleanup();
    std::string buffer;
    size_t bytes_written = devCmmh->setup_info(buffer);
    EXPECT_EQ(bytes_written, 0); 
    EXPECT_TRUE(buffer.empty()); 
}

