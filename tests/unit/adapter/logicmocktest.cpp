#include <dlfcn.h>
#include <gtest/gtest.h>

#include <fstream>
#include <iostream>
#include <streambuf>
#include <string>
#include <vector>

#include "logicmock.h"
#include "test_inputs.h"

using namespace std;
// using namespace rapidjson;

// The fixture for testing class Foo.
class LogicMockTest : public testing::Test {
 protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  LogicMockTest() {
    // You can do set-up work for each test here.
    cfg_file = "../../../adapters/mock_adapter/config/mock_config.json";
  }

  ~LogicMockTest() override {
    // You can do clean-up work that doesn't throw exceptions here.
  }

  // If the constructor and destructor are not enough for setting up
  // and cleaning up each test, you can define the following methods:

  void SetUp() override {}

  void TearDown() override {
    // Code here will be called immediately after each test (right
    // before the destructor).
  }

  // Class members declared here can be used by all tests in the test suite
  // for Foo.
  string cfg_file;
};

TEST_F(LogicMockTest, InputVariationForMockLogicSync) {
  svk_logic_cmd *cmd = nullptr;
  svk_logic_input *input = nullptr;
  svk_logic_output *output = nullptr;

  EXPECT_EQ(execute_mock_logic_sync(cmd, input, output), SVK_STATUS_FAIL);

  svk_logic_cmd cmd1 = {"mock", (void *)"", 256};
  svk_logic_input input1 = {inp1, strlen((const char *)inp1)};
  uint8_t out[256];
  svk_logic_output output1 = {SVK_STATUS_BAD_FEATURE_LIB, (uint8_t *)out, 256};

  EXPECT_EQ(execute_mock_logic_sync(&cmd1, &input1, &output1), SVK_STATUS_FAIL);

  svk_logic_cmd cmd2 = {"mock", (void *)"", 256};
  svk_logic_input input2 = {inp2, strlen((const char *)inp2)};
  uint8_t out2[256];
  svk_logic_output output2 = {SVK_STATUS_BAD_FEATURE_LIB, (uint8_t *)out2, 256};
  EXPECT_EQ(execute_mock_logic_sync(&cmd2, &input2, &output2), SVK_STATUS_FAIL);

  svk_logic_cmd cmd3 = {"mock", (void *)"", 256};
  svk_logic_input input3{nullptr, 0};
  uint8_t out3[256];
  svk_logic_output output3 = {SVK_STATUS_BAD_FEATURE_LIB, (uint8_t *)out3, 256};
  EXPECT_EQ(execute_mock_logic_sync(&cmd3, &input3, &output3), SVK_STATUS_FAIL);
}

TEST_F(LogicMockTest, InitializeLogicModule) {
  char p[] = {};
  EXPECT_EQ(initialize_logic_module((void *)p), SVK_STATUS_FAIL);

  EXPECT_EQ(initialize_logic_module((void *)CONFIG_FILE), SVK_STATUS_SUCCESS);

#undef CONFIG_FILE
#define CONFIG_FILE "config/config1.json"
  EXPECT_EQ(startup(CONFIG_FILE), SVK_STATUS_INVALID_CONFIG);
}
int main(int argc, char **argv) {
  testing::InitGoogleTest(&argc, argv);
  testing::FLAGS_gtest_catch_exceptions = true;
  return RUN_ALL_TESTS();
}
