#include <gtest/gtest.h>
#include "sc_fm.h"
#include <jansson.h>
#include <string>
#include <fstream>
#include <iostream>

const std::string json_filepath = "input.conf";

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

// Test fixture for FabricManager
class FabricManagerTest : public ::testing::Test {
protected:
    FabricManager* fabricManager;
    json_t* config;
    void SetUp() override {
        // Load the JSON configuration from the file
        config = load_json_from_file(json_filepath);
        ASSERT_NE(config, nullptr) << "Failed to load JSON config from file";
        // Access the "fabric_managers" array and create the FabricManager instance from the first entry
        json_t* fabric_managers = json_object_get(config, "fabric_managers");
        ASSERT_TRUE(json_is_array(fabric_managers)) << "Expected fabric_managers to be an array";
        json_t* first_fabric_manager = json_array_get(fabric_managers, 0);
        ASSERT_NE(first_fabric_manager, nullptr) << "Failed to get the first fabric manager entry";
        fabricManager = new FabricManager(first_fabric_manager);
    }
    void TearDown() override {
        delete fabricManager;
        json_decref(config);
    }
};

// Test parsing and accessing the type
TEST_F(FabricManagerTest, ParseType) {
    EXPECT_EQ(fabricManager->get_fm_type(), "FM_DIRECT_CMMD");
}

// Test setup_info method to generate JSON output
TEST_F(FabricManagerTest, SetupInfo) {
    std::string buffer(4096, '\0');
    size_t bytes_written = fabricManager->setup_info(buffer);
    // verify that bytes are written and buffer contains expected data
    EXPECT_GT(bytes_written, 0);
    buffer.resize(bytes_written);  

    // ensure null-terminated buffer
    EXPECT_EQ(buffer[bytes_written], '\0');

}

// Test hash_id_json to ensure unique ID hashing
TEST_F(FabricManagerTest, HashIdJson) {
    json_t* id_json = json_integer(1007);
    uint64_t hash_value = fabricManager->hash_id_json(id_json, "FM_DIRECT_CMMD");
    EXPECT_GT(hash_value, 0);
    json_decref(id_json);
}

// Test for the error case where id_json is not an integer
TEST_F(FabricManagerTest, HashIdJsonWithNonIntegerId) {
    json_t* id_json = json_string("not_an_integer");
    uint64_t hash_value = fabricManager->hash_id_json(id_json, "FM_DIRECT_CMMD");
    EXPECT_EQ(hash_value, 0);  // Expect 0 for invalid id format
    json_decref(id_json);
}

// Test cleanup method to clear hosts and devices
TEST_F(FabricManagerTest, Cleanup) {
    fabricManager->cleanup();
    std::string buffer(4096, '\0');
    size_t bytes_written = fabricManager->setup_info(buffer);
    EXPECT_EQ(bytes_written, 0); 
    EXPECT_TRUE(buffer.empty());
}













