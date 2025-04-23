#include <dlfcn.h>
#include <gtest/gtest.h>

#include <fstream>
#include <iostream>
#include <streambuf>
#include <string>
#include <vector>

#include "libmock.h"
#include "test_inputs.h"

using namespace std;
using namespace rapidjson;

// The fixture for testing class Foo.
class LibMockTest : public testing::Test {
 protected:
  // You can remove any or all of the following functions if their bodies would
  // be empty.

  LibMockTest() {
    // You can do set-up work for each test here.
    cfg_file = "../../../adapters/mock_adapter/config/mock_config.json";
  }

  ~LibMockTest() override {
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

TEST_F(LibMockTest, ReadConfigFileAndFormJson) {
  int ret = startup(cfg_file.c_str());

  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReadNonExistentConfigFileAndFormJson) {
  string cfg_file = "config101.json";
  int ret = startup(cfg_file.c_str());

  EXPECT_EQ(ret, CONFIG_FILE_NOT_AVAILABLE_ERR);
}

TEST_F(LibMockTest, ReturnConfigFileSize) {
  int ret = get_file_size(cfg_file);

  EXPECT_GT(ret, 0);
}

TEST_F(LibMockTest, ReturnZeroConfigFileSize) {
  string cfg = "mock_config0.json";
  ofstream file(cfg);
  file.close();
  int ret = get_file_size(cfg);
  unlink(cfg.c_str());

  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalBadConfig) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)badconfig_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, CONFIG_FILE_PARSE_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig1) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)config1_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, GREP_CXL_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig2) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)config2_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, GREP_ACPI_SRAT_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig3) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)config3_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, REGEX_IOMEM_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig4) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)config4_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, REGEX_ADDR_RANGE_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig5) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)config5_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, RASDAEMON_EXEC_COMMAND_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig6) {
  int ret = 0;
  string str, phy_addr_range;
  str.assign((const char*)config6_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, RASMCCTL_ERROR_ADDRESSES_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusgetErrorCount_validate) {
  string device_id, type = "correctable";
  device_id.assign((const char*)"0");

  int ret = getErrorCount_validate(device_id);
  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCount_validate) {
  string device_id, type = "correctable";
  device_id.assign(to_string(numa_max_node() + 1));

  int ret = getErrorCount_validate(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCount_validateNeg) {
  string device_id = to_string(-1), type = "correctable";

  int ret = getErrorCount_validate(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCount_validateAlpha) {
  string device_id = "abc", type = "correctable";

  int ret = getErrorCount_validate(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusverify_node) {
  int device_id = 0;

  int ret = verify_node(device_id);
  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReturnNonZeroStatusverify_node) {
  int device_id = numa_max_node() + 1;

  int ret = verify_node(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusverify_nodeNeg) {
  int device_id = -1;

  int ret = verify_node(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCount) {
  string device_id = to_string(numa_max_node() + 1), type = "correctable";

  string res = getErrorCount(device_id, type);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_NUMA_INDEX_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountNeg) {
  string device_id = to_string(-1), type = "correctable";

  string res = getErrorCount(device_id, type);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_NUMA_INDEX_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountAlpha) {
  string device_id = "abc", type = "correctable";

  string res = getErrorCount(device_id, type);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_NUMA_INDEX_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountEmpty) {
  string device_id = "", type = "correctable";

  string res = getErrorCount(device_id, type);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_NUMA_INDEX_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountValid) {
  string device_id, type = "correctable";
  device_id.assign((const char*)"0");

  string res = getErrorCount(device_id, type);
  Document document;
  document.Parse(res.c_str());
  EXPECT_TRUE(((strcmp(document["Status"].GetString(), "OK")) == 0) ||
              (strcmp(document["Status"].GetString(), "CMD_EXEC_ERR") == 0) ||
              (strcmp(document["Status"].GetString(),
                      "UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR") == 0));
}

TEST_F(LibMockTest, ReturnGetNumaAddrRange1) {
  string phy_addr_range;
  bool cxl_node = false;
  int node = 0;

  int ret = get_numa_node_address_range(node, cxl_node, phy_addr_range);
  EXPECT_TRUE((ret == OK) || (ret == CMD_EXEC_ERR) ||
              (ret == UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR));
}

TEST_F(LibMockTest, ReturnGetNumaAddrRange2) {
  string phy_addr_range;
  bool cxl_node = false;
  int node = numa_max_node() + 1;

  int ret;
  ret = get_numa_node_address_range(node, cxl_node, phy_addr_range);
  EXPECT_TRUE((ret == OK) || (ret == CMD_EXEC_ERR) ||
              (ret == UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR));
}

TEST_F(LibMockTest, ReturnGetNumaAddrRange3) {
  string phy_addr_range;
  bool cxl_node = false;
  int node = -1;

  int ret;
  ret = get_numa_node_address_range(node, cxl_node, phy_addr_range);
  EXPECT_TRUE((ret == OK) || (ret == CMD_EXEC_ERR) ||
              (ret == UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR));
}

TEST_F(LibMockTest, ReturnEmptyAddrRangesEmptyInput) {
  string out, phy_addr_range;
  out = "";

  bool cxl_node = false;
  int ret = determine_physical_address_range(out, cxl_node, phy_addr_range);
  EXPECT_TRUE((ret == OK) || (ret == CMD_EXEC_ERR) ||
              (ret == UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR));
}

TEST_F(LibMockTest, ReturnAddrRanges) {
  int ret = 0;
  size_t len = strlen(kernel_log_inp_c);
  for (size_t i = 0; i < len; ++i) {
    if (kernel_log_inp[i] != static_cast<unsigned char>(kernel_log_inp[i])) {
      ret = -1;
      break;
    }
  }
  EXPECT_EQ(ret, 0);
  string out((const char*)kernel_log_inp);
  string phy_addr_range;

  bool cxl_node = false;
  ret = determine_physical_address_range(out, cxl_node, phy_addr_range);
  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReturnStatusUsingcalculateErrorCount1) {
  int ret = 0;
  size_t len = strlen(ras_err_c);
  for (size_t i = 0; i < len; ++i) {
    if (ras_err[i] != static_cast<unsigned char>(ras_err_c[i])) {
      ret = -1;
      break;
    }
  }
  EXPECT_EQ(ret, 0);
  string ras_str, addr_range = "0x100000000-0x207fffffff";
  ras_str.assign((const char*)ras_err);

  string res = calculateErrorCount(ras_str, addr_range);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "OK");
}

TEST_F(LibMockTest, ReturnStatusUsingcalculateErrorCount2) {
  string ras_str = "", addr_range = "0x100000000-0x207fffffff";
  string res = calculateErrorCount(ras_str, addr_range);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(),
               "UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR");
}

TEST_F(LibMockTest, ReturnStatusUsingcalculateErrorCount3) {
  string ras_str = "", addr_range = "0x100000000-";
  string res = calculateErrorCount(ras_str, addr_range);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(),
               "UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidCommand) {
  const char* jsonString =
      R"({"command": "getErrorCount1", "device": 0, "type": "correctable"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_INPUT_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForValidCommand) {
  const char* jsonString =
      R"({"command": "getErrorCount", "device": 0, "type": "correctable"})";
  string req;
  req.assign(jsonString);
  string res;

  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_TRUE(((strcmp(document["Status"].GetString(), "OK")) == 0) ||
              (strcmp(document["Status"].GetString(), "CMD_EXEC_ERR") == 0) ||
              (strcmp(document["Status"].GetString(),
                      "UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR") == 0));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidDeviceAlpha) {
  const char* jsonString =
      R"({"command": "getErrorCount", "device": abc, "type": "correctable"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INPUT_JSON_PARSE_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidDeviceString) {
  const char* jsonString =
      R"({"command": "getErrorCount", "device": "abc", "type": "correctable"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_NUMA_INDEX_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidJSONInput) {
  const char* jsonString =
      R"({"command": "getErrorCount", "device": 19 "type": "correctable"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INPUT_JSON_PARSE_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForMissingItem) {
  const char* jsonString = R"({"command": "getErrorCount", "device": 19})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_INPUT_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForEmptyInput) {
  const char* jsonString = R"()";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INPUT_JSON_PARSE_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForBadInput) {
  const char* jsonString = R"({"command"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INPUT_JSON_PARSE_ERR");
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidParam) {
  const char* jsonString =
      R"({"command": "getErrorCount", "invalid_device": 1,
         "type": "correctable"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_STREQ(document["Status"].GetString(), "INVALID_INPUT_ERR");
}

int main(int argc, char** argv) {
  testing::InitGoogleTest(&argc, argv);
  testing::FLAGS_gtest_catch_exceptions = true;
  return RUN_ALL_TESTS();
}
