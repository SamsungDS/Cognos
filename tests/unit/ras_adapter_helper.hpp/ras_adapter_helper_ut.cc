#include <dirent.h>
#include <dlfcn.h>
#include <gtest/gtest.h>
#include <stdlib.h>
#include <sys/inotify.h>

#include <atomic>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <memory>
#include <string>
#include <thread>
#include <unordered_map>

#include "ras.hpp"
#include "ras_adapters_helper.hpp"
#include "ras_ut_config.h"
//  Format for running code before specific test suite, in this case InitTest
class RasAdapterHelperUnitTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    adapter_helper_ = std::make_unique<ras_adapter_helper>();

    auto num_adapters = adapter_helper_->load_ras_adapters(RAS_UT_ADAPTERS_DIR);
    // Mock adapter and UT adapter are loaded
    EXPECT_EQ(num_adapters, 2);
  }
  static std::unique_ptr<ras_adapter_helper> adapter_helper_;

  auto run_execute_sync_command(std::string command, std::string cmd) {
    return adapter_helper_->execute_adapter_sync_command(command, cmd);
  }
};
std::unique_ptr<ras_adapter_helper> RasAdapterHelperUnitTest::adapter_helper_;

TEST_F(RasAdapterHelperUnitTest, TestDeviceCorrectableErrorCount) {
  adapter_helper_->get_device_correctable_error_count("ras_adapter_ut",
                                                      "dev123");
}

TEST_F(RasAdapterHelperUnitTest, TestCmdWithoutResult) {
  std::string cmd = R"({"command_name": "getWithoutResult"})";
  auto res = run_execute_sync_command("ras_adapter_ut", cmd);
  EXPECT_FALSE(res.has_value());
}

TEST_F(RasAdapterHelperUnitTest, TestCmdWithoutCmdSuccessful) {
  std::string cmd = R"({"command_name": "getWithoutCommandSuccessful"})";
  auto res = run_execute_sync_command("ras_adapter_ut", cmd);
  EXPECT_FALSE(res.has_value());
}

TEST_F(RasAdapterHelperUnitTest, TestCmdResultFalse) {
  std::string cmd = R"({"command_name": "getResultFalse"})";
  auto res = run_execute_sync_command("ras_adapter_ut", cmd);
  EXPECT_FALSE(res.has_value());
}