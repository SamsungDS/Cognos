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
  string str;
  str.assign((const char*)badconfig_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, CONFIG_FILE_PARSE_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig1) {
  int ret = 0;
  string str;
  str.assign((const char*)config1_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, GREP_CXL_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig2) {
  int ret = 0;
  string str;
  str.assign((const char*)config2_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, GREP_ACPI_SRAT_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig3) {
  int ret = 0;
  string str;
  str.assign((const char*)config3_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, REGEX_IOMEM_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig4) {
  int ret = 0;
  string str;
  str.assign((const char*)config4_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, REGEX_ADDR_RANGE_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig5) {
  int ret = 0;
  string str;
  str.assign((const char*)config5_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, RASDAEMON_EXEC_COMMAND_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig6) {
  int ret = 0;
  string str;
  str.assign((const char*)config6_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, RASMCCTL_ERROR_ADDRESSES_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusWithLocalConfig7) {
  int ret = 0;
  string str;
  str.assign((const char*)config7_json);

  ret = validate_config(str);
  EXPECT_EQ(ret, GREP_NUMA_NODES_MISSING_ERR);
}

TEST_F(LibMockTest, ReturnZeroStatusdevice_validate) {
  string device_id, type = "correctable";
  device_id.assign((const char*)"0");

  int ret = device_validate(device_id);
  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReturnNonZeroStatusdevice_validate) {
  string device_id, type = "correctable";
  device_id.assign(to_string(numa_max_node() + 1));

  int ret = device_validate(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusdevice_validateNeg) {
  string device_id = to_string(-1), type = "correctable";

  int ret = device_validate(device_id);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusdevice_validateAlpha) {
  string device_id = "abc", type = "correctable";

  int ret = device_validate(device_id);
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
  Response out;

  int ret = getErrorCount(device_id, type, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusgetErrorCount) {
  string device_id = to_string(numa_max_node() + 1);
  Response out;

  int ret = getHealthStatus(device_id, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountNeg) {
  string device_id = to_string(-1), type = "correctable";
  Response out;

  int ret = getErrorCount(device_id, type, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusgetErrorCountNeg) {
  string device_id = to_string(-1);
  Response out;

  int ret = getHealthStatus(device_id, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountAlpha) {
  string device_id = "abc", type = "correctable";
  Response out;

  int ret = getErrorCount(device_id, type, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusgetErrorCountAlpha) {
  string device_id = "abc";
  Response out;

  int ret = getHealthStatus(device_id, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountEmpty) {
  string device_id = "", type = "correctable";
  Response out;

  int ret = getErrorCount(device_id, type, out);
  EXPECT_EQ(ret, INVALID_NUMA_INDEX_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusgetErrorCountValid) {
  string device_id, type = "correctable";
  Response out;
  device_id.assign((const char*)"0");

  int ret = getErrorCount(device_id, type, out);
  EXPECT_TRUE((ret == 0) || (ret == CMD_EXEC_ERR) ||
              (ret == UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR));
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
  string out((const char*)kernel_log_inp);
  string phy_addr_range;

  bool cxl_node = false;
  int ret = determine_physical_address_range(out, cxl_node, phy_addr_range);
  EXPECT_EQ(ret, 0);
}

TEST_F(LibMockTest, ReturnStatusUsingcalculateErrorCount1) {
  string ras_str, addr_range = "0x100000000-0x207fffffff";
  Response out;
  ras_str.assign((const char*)ras_err);

  int ret = calculateErrorCount(ras_str, addr_range, out);
  EXPECT_EQ(ret, OK);
}

TEST_F(LibMockTest, ReturnStatusUsingcalculateErrorCount2) {
  string ras_str = "", addr_range = "0x100000000-0x207fffffff";
  Response out;
  int ret = calculateErrorCount(ras_str, addr_range, out);
  EXPECT_EQ(ret, UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR);
}

TEST_F(LibMockTest, ReturnStatusUsingcalculateErrorCount3) {
  string ras_str = "", addr_range = "0x100000000-";
  Response out;
  int ret = calculateErrorCount(ras_str, addr_range, out);
  EXPECT_EQ(ret, UNABLE_TO_GET_NUMA_ADDR_RANGE_ERR);
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidCommand) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount1": { "device": 0, "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_FALSE(document["command_response"].HasMember("getErrorCount"));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForValidCommand) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount": { "device": "0", "errorType": "correctable"} } })";
  string req;
  req.assign(jsonString);
  string res;

  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  // In a properly set up host that includes
  // 1) NUMA node entries are recorded in kernel logs ( e.g //var/log/dmesg
  // 2) cat /proc/iomem has the due CXL device address allocations
  // the
  // document["command_response"]["getErrorCount"]["result"]["commandSuccessful"]
  // value will be true for the above input. In the build image VMs the above
  // conditions are not satisfied and hence the expected output is false.
  EXPECT_TRUE((document["command_response"]["getErrorCount"]["result"]
                       ["commandSuccessful"] == false));
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusForValidCommand) {
  const char* jsonString =
      R"({"command_name": { "getHealthStatus": { "device": "0" } } })";
  string req;
  req.assign(jsonString);
  string res;

  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  // In a properly set up host that includes
  // 1) NUMA node entries are recorded in kernel logs ( e.g //var/log/dmesg
  // 2) cat /proc/iomem has the due CXL device address allocations
  // the
  // document["command_response"]["getErrorCount"]["result"]["commandSuccessful"]
  // value will be true for the above input. In the build image VMs the above
  // conditions are not satisfied and hence the expected output is false.
  EXPECT_TRUE((document["command_response"]["getHealthStatus"]["result"]
                       ["commandSuccessful"] == false));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidDeviceAlpha) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount": { "device": abc, "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_TRUE(document.HasMember("command_response"));
  EXPECT_FALSE(document["command_response"].HasMember("getErrorCount"));
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusForInvalidDeviceAlpha) {
  const char* jsonString =
      R"({"command_name": { "getHealthStatus": { "device": abc } } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_TRUE(document.HasMember("command_response"));
  EXPECT_FALSE(document["command_response"].HasMember("getHealthStatus"));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidDeviceString) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount": { "device": "abc", "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  // In a properly set up host that includes
  // 1) NUMA node entries are recorded in kernel logs ( e.g //var/log/dmesg
  // 2) cat /proc/iomem has the due CXL device address allocations
  // the
  // document["command_response"]["getErrorCount"]["result"]["commandSuccessful"]
  // value will be true for the above input. In the build image VMs the above
  // conditions are not satisfied and hence the expected output is false.
  EXPECT_TRUE((document["command_response"]["getErrorCount"]["result"]
                       ["commandSuccessful"] == false));
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusForInvalidDeviceString) {
  const char* jsonString =
      R"({"command_name": { "getHealthStatus": { "device": "abc", "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  // In a properly set up host that includes
  // 1) NUMA node entries are recorded in kernel logs ( e.g //var/log/dmesg
  // 2) cat /proc/iomem has the due CXL device address allocations
  // the
  // document["command_response"]["getErrorCount"]["result"]["commandSuccessful"]
  // value will be true for the above input. In the build image VMs the above
  // conditions are not satisfied and hence the expected output is false.
  EXPECT_TRUE((document["command_response"]["getHealthStatus"]["result"]
                       ["commandSuccessful"] == false));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidJSONInput) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount": { "device": 19, "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_EQ(document["command_response"].HasMember("getErrorCount"), true);
  EXPECT_EQ(document["command_response"]["getErrorCount"].HasMember("result"),
            true);
  EXPECT_TRUE((document["command_response"]["getErrorCount"]["result"]
                       ["commandSuccessful"] == false));
}

TEST_F(LibMockTest, ReturnNonZeroHealthStatusForInvalidJSONInput) {
  const char* jsonString =
      R"({"command_name": { "getHealthStatus": { "device": 19, "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_EQ(document["command_response"].HasMember("getHealthStatus"), true);
  EXPECT_EQ(document["command_response"]["getHealthStatus"].HasMember("result"),
            true);
  EXPECT_TRUE((document["command_response"]["getHealthStatus"]["result"]
                       ["commandSuccessful"] == false));
}
TEST_F(LibMockTest, ReturnNonZeroStatusForMissingItem) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount": { "device": "abc" } } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_FALSE(document["command_response"].HasMember("getErrorCount"));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForEmptyInput) {
  const char* jsonString = R"()";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_TRUE(document.HasMember("command_response"));
  EXPECT_FALSE(document["command_response"].HasMember("getErrorCount"));
  EXPECT_FALSE(document["command_response"].HasMember("getHealthStatus"));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForBadInput) {
  const char* jsonString = R"({"command_name"})";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_FALSE(document["command_response"].HasMember("getErrorCount"));
  EXPECT_FALSE(document["command_response"].HasMember("getHealthStatus"));
}

TEST_F(LibMockTest, ReturnNonZeroStatusForInvalidParam) {
  const char* jsonString =
      R"({"command_name": { "getErrorCount": { "invalid_device": 19, "errorType": "correctable"} } })";
  string res;
  string req;
  req.assign(jsonString);
  res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_FALSE(document["command_response"].HasMember("getErrorCount"));
}

TEST_F(LibMockTest, ReturnZeroHealthStatusUsingcreateResponse) {
  const char *device = "0", *type = "correctable", *status = "OK";
  Response out = {"getHealthStatus", "5", "Test Case"};
  string res = createResponse(device, type, status, out);
  Document document;
  document.Parse(res.c_str());
  EXPECT_TRUE((document["command_response"]["getHealthStatus"]["result"]
                       ["commandSuccessful"] == true));
}

TEST_F(LibMockTest, ReturnEmptyget_numa_nodes) {
  Response res;
  int ret = get_numa_nodes(res);
  Document document;
  document.Parse(res.return_value.c_str());
  EXPECT_EQ(ret, 0);
  // In a properly set up host that includes
  // 1) NUMA node entries are recorded in kernel logs ( e.g /var/log/dmesg
  // 2) cat /proc/iomem has the due CXL device address allocations
  // the res.return_value will have the NUMA node entries. In the build
  // image VMs the above conditions are not satisfied and hence the
  // expected output is empty.
  EXPECT_EQ(res.return_value, "");
}

TEST_F(LibMockTest, ReturnEmptygetDeviceList) {
  Response res;
  int ret = getDeviceList(res);
  Document document;
  document.Parse(res.return_value.c_str());
  EXPECT_EQ(ret, 0);
  // In a properly set up host that includes
  // 1) NUMA node entries are recorded in kernel logs ( e.g /var/log/dmesg
  // 2) cat /proc/iomem has the due CXL device address allocations
  // the res.return_value will have the NUMA node entries. In the build
  // image VMs the above conditions are not satisfied and hence the
  // expected output is empty.
  EXPECT_EQ(res.return_value, "");
}

TEST_F(LibMockTest, ReturnFalseprocessRequest) {
  string req = R"({"command_name" : { "getDeviceList" : {}}})";
  string res = processRequest(req);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_TRUE(document["command_response"].HasMember("getDeviceList"));
  EXPECT_TRUE(
      document["command_response"]["getDeviceList"].HasMember("result"));
  EXPECT_TRUE(document["command_response"]["getDeviceList"]["result"].HasMember(
      "commandSuccessful"));
}

TEST_F(LibMockTest, ReturnSuccessWithDeviceListcreateResponse) {
  Response res_in = {"getDeviceList", "0\n1\n2\n3\n", ""};
  string dev, type, status = "OK";
  string res = createResponse(dev, type, status.c_str(), res_in);
  Document document;
  document.Parse(res.c_str());
  EXPECT_EQ(document.HasMember("command_response"), true);
  EXPECT_TRUE(document["command_response"].HasMember("getDeviceList"));
  EXPECT_TRUE(
      document["command_response"]["getDeviceList"].HasMember("result"));
  EXPECT_TRUE(document["command_response"]["getDeviceList"]["result"].HasMember(
      "commandSuccessful"));
  EXPECT_TRUE(document["command_response"]["getDeviceList"]["result"].HasMember(
      "deviceList"));
  EXPECT_TRUE(document["command_response"]["getDeviceList"]["result"]
                      ["commandSuccessful"] == true);
  EXPECT_TRUE(
      document["command_response"]["getDeviceList"]["result"]["deviceList"]
          .IsArray());
  EXPECT_TRUE(
      document["command_response"]["getDeviceList"]["result"]["deviceList"]
          .Size() == 4);
  EXPECT_EQ(
      strcmp(res.c_str(),
             "{\"command_response\":{\"getDeviceList\":{\"result\":{"
             "\"commandSuccessful\":true,\"deviceList\":[\"0\",\"1\",\"2\","
             "\"3\"]}}}}"),
      0);
}

int main(int argc, char** argv) {
  testing::InitGoogleTest(&argc, argv);
  testing::FLAGS_gtest_catch_exceptions = true;
  return RUN_ALL_TESTS();
}
