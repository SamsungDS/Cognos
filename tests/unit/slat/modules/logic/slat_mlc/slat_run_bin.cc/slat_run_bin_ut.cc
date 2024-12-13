#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <string>

#include "slat_benchmark.hpp"
#include "slat_run_bin.hpp"
#include "test_bin.h"

TEST(TestMlcConfigure, RunTestInvalidConfigFile) {
  EXPECT_EQ(SVK_STATUS_SUCCESS, configure_slat_mlc_logic(""));
}

TEST(TestMlcLogic, RunTestInvalidExecSync) {
  svk_logic_cmd cmd = {};
  svk_logic_input in = {};
  svk_logic_output out = {};

  EXPECT_EQ(SVK_STATUS_FAIL, execute_mlc_logic_sync(nullptr, nullptr, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_mlc_logic_sync(&cmd, nullptr, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_mlc_logic_sync(&cmd, &in, nullptr));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_mlc_logic_sync(&cmd, &in, &out));
}

TEST(TestRunBin, RunTestBinarySuccess) {
  exe_ret_info rinfo;

  rinfo = runExecutable(std::string(TEST_BIN_PATH), std::string("test1 test2"));
  std::cout << rinfo.rc << std::endl;
  std::cout << rinfo.output << std::endl;
}

TEST(TestRunBin, RunMlcBinarySuccess) {
  std::string out;
  argOpts opts = {};

  out = runMlc("idle_latency", opts, std::string(MLC_TEST_BIN_PATH));
  std::cout << out << std::endl;

  out = runMlc("idle_latency", opts, std::string(TEST_BIN_PATH));
  std::cout << out << std::endl;

  out = runMlc("invalid_test", opts, std::string(TEST_BIN_PATH));
  std::cout << out << std::endl;

  opts.insert(std::make_pair("numa_node", "0"));
  out = runMlc("idle_latency", opts, std::string(MLC_TEST_BIN_PATH));
  std::cout << out << std::endl;

  out = runMlc("idle_latency", opts, std::string("/path/does/not/exist"));
  std::cout << out << std::endl;
}
