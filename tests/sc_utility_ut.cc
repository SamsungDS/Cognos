#include <gtest/gtest.h>

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#include "sc_test_utils.h"
#include "sc_utility.h"

extern "C" {
#include <pci/pci.h>
}

extern "C" struct pci_access* pci_alloc() {
  static struct pci_dev fake_dev = {};
  fake_dev.vendor_id = 0x1234;
  fake_dev.device_id = 0xABCD;
  fake_dev.domain = 0x0001;
  fake_dev.bus = 0x02;
  fake_dev.dev = 0x00;
  fake_dev.func = 0x1;

  static struct pci_access fake_pacc = {
      .devices = &fake_dev,
  };

  return &fake_pacc;
}

extern "C" void pci_init(struct pci_access*) {}
extern "C" void pci_scan_bus(struct pci_access*) {}
extern "C" int pci_fill_info(struct pci_dev*, int) { return 0; }
extern "C" void pci_cleanup(struct pci_access*) {}
bool test_force_numa_failure = false;
int test_mock_node_value = 3;
bool test_force_failure = false;
bool test_force_throw = false;
long long test_mock_total_bytes = 8LL * 1024 * 1024 * 1024;  // 8 GB
long long test_mock_free_bytes = 4LL * 1024 * 1024 * 1024;   // 4 GB
int test_mock_numa_node = 2;

extern "C" long long numa_node_size64(int node, long long* freep) {
  if (test_force_throw) {
    throw std::runtime_error("Simulated exception");
  }
  if (test_force_failure) {
    return -1;
  }
  std::cout << "inside mocked numa_node_size64 " << test_mock_free_bytes
            << " total bytes:" << test_mock_total_bytes << std::endl;
  if (freep) *freep = test_mock_free_bytes;
  return test_mock_total_bytes;
}

class ScUtilityTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // inject device map
    DevTypeMap dev_map;
    dev_map[{0x1e98, 0x0ddb}] = "CMM-H";
    dev_map[{0x1b00, 0xc001}] = "CMM-D";
    set_global_dev_type_map(dev_map);
    std::remove("/tmp/nonexistent_config.json");
  }

  void TearDown() override {}
};

TEST_F(ScUtilityTest, StrToInt_Valid) {
  uint64_t id;
  std::string error_response;
  std::string number = "11107";
  bool result = str_to_int(number, id, error_response);
  EXPECT_TRUE(result);
}

TEST_F(ScUtilityTest, StrToInt_OutOfRange) {
  uint64_t id;
  std::string error_response;
  // Too large for uint64_t
  std::string large_number = "999999999999999999999999999999999";
  bool result = str_to_int(large_number, id, error_response);
  EXPECT_FALSE(result);  // Expect failure
  std::cout << error_response << std::endl;
  EXPECT_EQ(get_json_value(error_response, "rc"), "ERANGE");
  EXPECT_EQ(get_json_value(error_response, "message"), "id value out of range");
}

TEST_F(ScUtilityTest, StrToInt_InvalidArgs) {
  uint64_t id;
  std::string error_response;
  std::string large_number = "samsung";
  bool result = str_to_int(large_number, id, error_response);
  EXPECT_FALSE(result);  // Expect failure
  EXPECT_EQ(get_json_value(error_response, "rc"), "EINVAL");
}

TEST_F(ScUtilityTest, PosixErrToJson_Coverage) {
  EXPECT_EQ(get_json_value(posix_err_to_json(EIO, ""), "message"),
            "Internal I/O error occurred");
  EXPECT_EQ(get_json_value(posix_err_to_json(EPERM, ""), "message"),
            "Operation not permitted");
  EXPECT_EQ(get_json_value(posix_err_to_json(EBUSY, ""), "message"),
            "Resource is busy, try again later");
  EXPECT_EQ(get_json_value(posix_err_to_json(ENOMEM, ""), "message"),
            "Memory allocation failure");
  EXPECT_EQ(get_json_value(posix_err_to_json(EINVAL, ""), "message"),
            "Invalid request parameters");
  EXPECT_EQ(get_json_value(posix_err_to_json(ENOENT, ""), "message"),
            "Requested resource not found");
  EXPECT_EQ(get_json_value(posix_err_to_json(EEXIST, ""), "message"),
            "Resource already exists");
  EXPECT_EQ(get_json_value(posix_err_to_json(ENOEXEC, ""), "message"),
            "Executable format error (plugin load failed)");
  EXPECT_EQ(get_json_value(posix_err_to_json(EPROTO, ""), "message"),
            "Plugin registration error");
  EXPECT_EQ(get_json_value(posix_err_to_json(EFAULT, ""), "message"),
            "System fault occurred");
  EXPECT_EQ(get_json_value(posix_err_to_json(ETIMEDOUT, ""), "message"),
            "Operation timed out");
  EXPECT_EQ(get_json_value(posix_err_to_json(ECONNREFUSED, ""), "message"),
            "Connection refused");
  // Testing the default case (passing an unknown error code)
  EXPECT_EQ(get_json_value(posix_err_to_json(9999, ""), "message"),
            "Unknown error occurred");
}

TEST_F(ScUtilityTest, ExtractRequiredParams_AllKeysPresent) {
  std::unordered_map<std::string, std::string> input = {{"key1", "val1"},
                                                        {"key2", "val2"}};
  std::vector<std::string> keys = {"key1", "key2"};
  std::unordered_map<std::string, std::string> output;
  std::string error;

  bool result = extract_required_params(input, keys, output, error);
  EXPECT_TRUE(result);
  EXPECT_EQ(output["key1"], "val1");
  EXPECT_EQ(output["key2"], "val2");
  EXPECT_TRUE(error.empty());
}

TEST_F(ScUtilityTest, ExtractRequiredParams_KeyMissing) {
  std::unordered_map<std::string, std::string> input = {{"key1", "val1"}};
  std::vector<std::string> keys = {"key1", "key2"};
  std::unordered_map<std::string, std::string> output;
  std::string error;

  bool result = extract_required_params(input, keys, output, error);
  EXPECT_FALSE(result);
  EXPECT_EQ(output.count("key1"), 1);
  EXPECT_EQ(output.count("key2"), 0);
  EXPECT_NE(error.find("Missing parameter: key2"), std::string::npos);
}

TEST_F(ScUtilityTest, IsDeviceListEmpty_EmptyList) {
  std::string json_response = R"({"devices":[]})";
  EXPECT_TRUE(is_device_list_empty(json_response));
}

TEST_F(ScUtilityTest, IsDeviceListEmpty_NonEmptyList) {
  std::string json_response = R"({"devices":[{"id":"1"}]})";
  EXPECT_FALSE(is_device_list_empty(json_response));
}

TEST_F(ScUtilityTest, IsDeviceListEmpty_MalformedJson) {
  std::string json_response = R"({"devices":)";
  EXPECT_TRUE(is_device_list_empty(json_response));
}

TEST_F(ScUtilityTest, IsDeviceListEmpty_MissingDevicesKey) {
  std::string json_response = R"({"data":[]})";
  EXPECT_TRUE(is_device_list_empty(json_response));
}

TEST_F(ScUtilityTest, IsDeviceListEmpty_DevicesNotArray) {
  std::string json_response = R"({"devices":{}})";
  EXPECT_TRUE(is_device_list_empty(json_response));
}

TEST_F(ScUtilityTest, GenerateDevId_ReturnsExpectedValue) {
  uint16_t vendor = 0x1E98;
  uint16_t device = 0x0DDB;
  uint8_t bus = 0x12;

  uint64_t expected = ((uint64_t)vendor << 32) | ((uint64_t)device << 16) |
                      ((uint64_t)bus << 8);
  uint64_t result = generate_dev_id(vendor, device, bus);
  EXPECT_EQ(result, expected);
}

TEST_F(ScUtilityTest, ParseJsonKey_ValidFile) {
  const std::string temp_path = "/tmp/test_valid_config.json";
  std::ofstream file(temp_path);
  file << R"({"version": "1.2.3"})";
  file.close();
  std::string value;
  int result = parse_json_key(temp_path, "version", value);
  EXPECT_EQ(result, 0);
  EXPECT_EQ(value, "1.2.3");
  std::filesystem::remove(temp_path);
}

TEST_F(ScUtilityTest, ParseJsonKey_KeyNotFound) {
  const std::string temp_path = "/tmp/test_invalid_key.json";
  std::ofstream file(temp_path);
  file << R"({"name": "Samsung"})";
  file.close();
  std::string value;
  int result = parse_json_key(temp_path, "version", value);
  EXPECT_EQ(result, -EINVAL);
  EXPECT_EQ(value, "");
  std::filesystem::remove(temp_path);
}

TEST_F(ScUtilityTest, ValidateJsonFile_FileExists) {
  const std::string temp_path = "/tmp/temp.json";
  std::ofstream file(temp_path);
  file << "{}";
  file.close();
  int result = validate_json_file(temp_path);
  EXPECT_EQ(result, 0);
  std::filesystem::remove(temp_path);
}

TEST_F(ScUtilityTest, ValidateJsonFile_FileMissing) {
  std::string path = "test_data/does_not_exist.json";
  int result = validate_json_file(path);
  EXPECT_EQ(result, -ENOENT);
}

TEST_F(ScUtilityTest, LoadDevTypeMapping_ValidFile) {
  std::string path = "/tmp/LDTM_ValidFile.json";

  std::ofstream file(path);
  file << R"({
"device_map": [
{ "device_type": "CMM-H", "vendor_id": "1e98", "device_id": "0ddb" }
]
})";
  file.close();

  const auto& map = load_dev_type_mapping_json(path);
  EXPECT_EQ(map.size(), 1);
  EXPECT_EQ(map.at({0x1e98, 0x0ddb}), "CMM-H");

  std::remove(path.c_str());
}

TEST_F(ScUtilityTest, LoadDevTypeMapping_InvalidJsonRoot) {
  set_global_dev_type_map({});
  std::string path = "/tmp/InvalidJsonRoot.json";

  std::ofstream file(path);
  file << R"([
{ "device_type": "CMM-H" }
])";
  file.close();

  const auto& map = load_dev_type_mapping_json(path);
  EXPECT_TRUE(map.empty());

  std::remove(path.c_str());
}

TEST_F(ScUtilityTest, LoadDevTypeMapping_MissingDeviceMapKey) {
  set_global_dev_type_map({});
  std::string path = "/tmp/MissingDeviceMapKey.json";

  std::ofstream file(path);
  file << R"({
"something_else": []
})";
  file.close();

  const auto& map = load_dev_type_mapping_json(path);
  EXPECT_TRUE(map.empty());

  std::remove(path.c_str());
}

TEST_F(ScUtilityTest, LoadDevTypeMapping_MissingFieldsInEntry) {
  std::string path = "/tmp/MissingFieldsInEntry.json";

  std::ofstream file(path);
  file << R"({
"device_map": [
{ "device_type": "CMM-H", "vendor_id": "1e98" }
]
})";
  file.close();

  const auto& map = load_dev_type_mapping_json(path);
  EXPECT_TRUE(map.empty());

  std::remove(path.c_str());
}

TEST_F(ScUtilityTest, LoadDevTypeMapping_BadVendorDeviceValues) {
  std::string path = "/tmp/BadVendorDeviceValues.json";

  std::ofstream file(path);
  file << R"({
"device_map": [
{ "device_type": "CMM-H", "vendor_id": "ZZZZ", "device_id": "0ddb" }
]
})";
  file.close();

  const auto& map = load_dev_type_mapping_json(path);
  EXPECT_TRUE(map.empty());

  std::remove(path.c_str());
}

TEST_F(ScUtilityTest, ParseJsonKey_FileNotFound_ReturnsENOENT) {
  std::string value;
  int rc = parse_json_key("/nonexistent/config.json", "some_key", value);
  EXPECT_EQ(rc, -ENOENT);
}

TEST_F(ScUtilityTest, ParseJsonKey_KeyMissing_ReturnsEINVAL) {
  std::ofstream out("/tmp/test_config.json");
  out << R"({ "another_key": "value" })";
  out.close();

  std::string value;
  int rc = parse_json_key("/tmp/test_config.json", "missing_key", value);
  EXPECT_EQ(rc, -EINVAL);
}

TEST_F(ScUtilityTest, ParseJsonKey_ValidKey_ReturnsZero) {
  std::ofstream out("/tmp/test_config_valid.json");
  out << R"({ "device_type": "CMM-H" })";
  out.close();

  std::string value;
  int rc = parse_json_key("/tmp/test_config_valid.json", "device_type", value);
  EXPECT_EQ(rc, 0);
  EXPECT_EQ(value, "CMM-H");
}

TEST_F(ScUtilityTest, GetGlobalDevTypeMap_ReturnsCorrectMap) {
  static DevTypeMap dummy_map;
  dummy_map.clear();  // ensure fresh map
  dummy_map[{0x1e98, 0xddb}] = "CMM-H";

  set_global_dev_type_map(dummy_map);

  const DevTypeMap* global_map = get_global_dev_type_map();
  ASSERT_NE(global_map, nullptr);
  ASSERT_EQ(global_map->size(), 1);
  ASSERT_FALSE(global_map->empty());
  for (const auto& [key, value] : *global_map) {
    std::cout << "Vendor ID: 0x" << std::hex << key.first << ", Device ID: 0x"
              << key.second << " => Type: " << value << std::endl;
    EXPECT_FALSE(value.empty());
  }
  std::pair<uint16_t, uint16_t> search_key = std::make_pair(0x1e98, 0xddb);
  auto it = global_map->find(search_key);
  ASSERT_NE(it, global_map->end());
  EXPECT_EQ(it->second, "CMM-H");
}

TEST_F(ScUtilityTest, ParseJsonKey_InvalidFile_ReturnsError) {
  std::string key = "device_type";
  std::string value;
  std::string invalid_file = "/tmp/nonexistent_config.json";
  int status = parse_json_key(invalid_file, key, value);
  EXPECT_EQ(status, -ENOENT);
}

TEST_F(ScUtilityTest, GetNumaMemoryInfo_Success) {
  test_force_failure = false;
  test_force_throw = false;
  uint64_t total_mb = 0, free_mb = 0;
  bool result = get_numa_memory_info(3, total_mb, free_mb);
  EXPECT_TRUE(result);
  EXPECT_EQ(total_mb, 8192);
  EXPECT_EQ(free_mb, 4096);
}

TEST_F(ScUtilityTest, GetNumaMemoryInfo_FailureByReturn) {
  test_force_failure = true;
  uint64_t total_mb = 0, free_mb = 0;
  bool result = get_numa_memory_info(3, total_mb, free_mb);
  EXPECT_FALSE(result);
  test_force_failure = false;
}

TEST_F(ScUtilityTest, DiscoverCxlDevicesShared_ReturnsDiscoveredDevices) {
  test_force_numa_failure = false;
  DevTypeMap dev_type_map;
  dev_type_map[{0x1234, 0xABCD}] = "FM_CMMH";
  auto device_map = discover_cxl_devices_shared(dev_type_map);
  ASSERT_EQ(device_map.size(), 1);
  const sc_device& dev = device_map.begin()->second;
  EXPECT_TRUE(dev.d_get_capacity() == 4096 || dev.d_get_capacity() == 1024);
}

TEST_F(ScUtilityTest, DiscoverCxlDevicesShared_InvalidNumaNodeHandled) {
  test_force_numa_failure = true;
  DevTypeMap dev_type_map;
  dev_type_map[{0x1234, 0xABCD}] = "FM_CMMH";
  auto device_map = discover_cxl_devices_shared(dev_type_map);
  ASSERT_EQ(device_map.size(), 1);
  const sc_device& dev = device_map.begin()->second;
  EXPECT_EQ(dev.d_get_capacity(), 1024);
}

TEST_F(ScUtilityTest, GetNumaMemoryInfo_ValidNode) {
  uint64_t total_mb = 0;
  uint64_t free_mb = 0;
  bool result = get_numa_memory_info(/*node_id=*/0, total_mb, free_mb);
  EXPECT_TRUE(result);
  EXPECT_GT(total_mb, 0);
}

TEST_F(ScUtilityTest, NumaMemoryInfo_APIFailure) {
  test_force_failure = true;

  uint64_t total = 0, free = 0;
  EXPECT_FALSE(get_numa_memory_info(0, total, free));

  test_force_failure = false;
}

TEST_F(ScUtilityTest, NumaMemoryInfo_ThrowsException) {
  test_force_throw = true;

  uint64_t total = 0, free = 0;
  EXPECT_FALSE(get_numa_memory_info(0, total, free));

  test_force_throw = false;
}

TEST_F(ScUtilityTest, GetNumaNodeFromSysfs_ValidFileReturnsNode) {
  std::string bdf = "0000:5e:00.0";
  std::string dir = "/tmp/sysfs_test/" + bdf;
  std::filesystem::create_directories(dir);

  std::ofstream(dir + "/numa_node") << "3";

  setenv("TEST_SYSFS_ROOT", "/tmp/sysfs_test", 1);  // set env var
  int result = get_numa_node_from_sysfs(bdf);
  unsetenv("TEST_SYSFS_ROOT");  // clean up env var

  EXPECT_EQ(result, 3);
  std::filesystem::remove_all("/tmp/sysfs_test");
}

TEST_F(ScUtilityTest, GetNumaNodeFromSysfs_FileMissing) {
  std::string bdf = "0000:5e:00.1";
  std::string dir = "/tmp/sysfs_test/" + bdf;
  std::filesystem::create_directories(dir);
  setenv("TEST_SYSFS_ROOT", "/tmp/sysfs_test", 1);
  int result = get_numa_node_from_sysfs(bdf);
  unsetenv("TEST_SYSFS_ROOT");

  EXPECT_EQ(result, -1);

  std::filesystem::remove_all("/tmp/sysfs_test");
}
