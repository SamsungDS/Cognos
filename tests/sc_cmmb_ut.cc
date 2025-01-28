#include <gtest/gtest.h>
#include <jansson.h>

#include <iostream>
#include <string>

#include "sc_cmmb.h"
#include "svk_logger.h"

const std::string json_filepath = "input.conf";

// Test fixture for DevCMMB
class DevCMMBTest : public ::testing::Test {
 protected:
  DevCMMB* devCmmb;
  json_t* config;
  void SetUp() override {
    // Load the JSON configuration from the file
    config = load_json_file(json_filepath);
    ASSERT_NE(config, nullptr) << "Failed to load JSON config from file";
    json_t* fabric_managers = json_object_get(config, "fabric_managers");
    ASSERT_TRUE(json_is_array(fabric_managers))
        << "Expected fabric_managers to be an array";
    json_t* first_fabric_manager = json_array_get(fabric_managers, 0);
    ASSERT_NE(first_fabric_manager, nullptr)
        << "Failed to get the first fabric manager entry";
    // Initialize DevCMMB (testing the constructor)
    devCmmb = new DevCMMB(first_fabric_manager);
  }
  void TearDown() override {
    // Test the destructor by deleting devCmmb
    delete devCmmb;
    json_decref(config);
    svk_logger_close("CXL");
  }

 public:
  json_t* load_json_file(const std::string& file_path) {
    json_error_t error;
    json_t* root = json_load_file(file_path.c_str(), 0, &error);
    if (!root) {
      std::cerr << "Error loading JSON from file: " << error.text << " at line "
                << error.line << std::endl;
      return nullptr;
    }
    return root;
  }
};

// Constructor Test
TEST_F(DevCMMBTest, ConstructorInitialization) {
  // Verify that DevCMMB was initialized with expected values
  EXPECT_EQ(devCmmb->get_fm_type(), "FM_DIRECT_CMMD");
  EXPECT_NE(devCmmb->get_fmid().get_sc_id(), 0);
}

// Indirect Destructor Test
TEST_F(DevCMMBTest, Destructor) { SUCCEED(); }

// Test for correct initialization and type retrieval
TEST_F(DevCMMBTest, Initialization) {
  EXPECT_EQ(devCmmb->get_fm_type(), "FM_DIRECT_CMMD");
}

// Test setup_info method to ensure it generates expected output
TEST_F(DevCMMBTest, SetupInfo) {
  std::string buffer(4096, '\0');
  size_t bytes_written = devCmmb->setup_info(buffer);
  EXPECT_GT(bytes_written, 0);
  buffer.resize(bytes_written);
}

// Test cleanup method to clear data
TEST_F(DevCMMBTest, Cleanup) {
  devCmmb->cleanup();
  std::string buffer;
  size_t bytes_written = devCmmb->setup_info(buffer);
  std::cout << "cmmb bytes written -> " << bytes_written << std::endl;
  EXPECT_EQ(bytes_written, 0);
  EXPECT_TRUE(buffer.empty());
}
