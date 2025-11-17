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
  EXPECT_EQ(out, "status=failed");

  out = runMlc("invalid_test", opts, std::string(TEST_BIN_PATH));
  EXPECT_EQ(out, "status=failed");

  opts.insert(std::make_pair("numa_node", "0"));
  out = runMlc("idle_latency", opts, std::string(MLC_TEST_BIN_PATH));
  EXPECT_NE(std::string::npos, out.find("status=success;avgLatencyns="));

  out = runMlc("idle_latency", opts, std::string("/path/does/not/exist"));
  EXPECT_EQ(out, "status=failed");
}

TEST(TestRunBinWithLatencyMatrix, RunMlcBinaryWithLatencyMatrixSuccess) {
  std::string out;
  argOpts opts = {};

  // No numa provided
  out = runMlc("latency_matrix", opts, std::string(MLC_TEST_BIN_PATH));
  EXPECT_EQ(out, "status=failed");

  // Valid numa
  opts.insert(std::make_pair("numa_node", "0"));
  out = runMlc("latency_matrix", opts, std::string(MLC_TEST_BIN_PATH));
  EXPECT_NE(std::string::npos, out.find("status=success;avgLatencyns="));

  // Invalid numa
  opts = {};
  opts.insert(std::make_pair("numa_node", "2"));
  out = runMlc("latency_matrix", opts, std::string(MLC_TEST_BIN_PATH));
  EXPECT_EQ(out, "status=failed");

  // Read from the mock file (mlc_bin_mock.cc) to parse non-existent numas
  opts = {};
  opts.insert(std::make_pair("numa_node", "2"));
  out =
      runMlc("latency_matrix", opts, std::string(MLC_BIN_MOCK_EXECUTABLE_PATH));
  EXPECT_NE(std::string::npos, out.find("status=success;avgLatencyns=781.4"));

  opts = {};
  opts.insert(std::make_pair("numa_node", "3"));
  out =
      runMlc("latency_matrix", opts, std::string(MLC_BIN_MOCK_EXECUTABLE_PATH));
  EXPECT_NE(std::string::npos, out.find("status=success;avgLatencyns=809"));

  opts = {};
  opts.insert(std::make_pair("numa_node", "4"));
  out =
      runMlc("latency_matrix", opts, std::string(MLC_BIN_MOCK_EXECUTABLE_PATH));
  EXPECT_EQ(out, "status=failed");
}
