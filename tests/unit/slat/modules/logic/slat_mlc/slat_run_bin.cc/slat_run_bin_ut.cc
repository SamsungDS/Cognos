#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <string>

#include "slat_benchmark.hpp"
#include "slat_run_bin.hpp"
#include "test_bin.h"

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

  opts.insert(std::make_pair("numa_node", "0"));
  out = runMlc("idle_latency", opts, std::string(MLC_TEST_BIN_PATH));
  std::cout << out << std::endl;
}
