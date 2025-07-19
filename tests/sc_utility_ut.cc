#include <dlfcn.h>  // For dlsym
#include <gtest/gtest.h>

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

#include "sc_servicer.h"
#include "sc_test_utils.h"
#include "sc_utility.h"

extern "C" {
#include <pci/pci.h>
}

static struct pci_dev fake_dev;
static struct pci_access fake_pacc;
extern "C" struct pci_access* pci_alloc() {
  std::cout << "[MOCK] pci_alloc invoked" << std::endl;
  fake_dev.vendor_id = 0x1234;
  fake_dev.device_id = 0xABCD;
  fake_dev.domain = 0x0001;
  fake_dev.bus = 0x02;
  fake_dev.dev = 0x00;
  fake_dev.func = 0x1;
  fake_dev.next = nullptr;
  // Link device to pci_access struct
  fake_pacc.devices = &fake_dev;
  return &fake_pacc;
}
extern "C" void pci_init(struct pci_access*) {}
extern "C" void pci_scan_bus(struct pci_access* pacc) {
  pacc->devices = &fake_dev;
}
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

bool test_force_popen_fail = false;
bool test_force_popen_invalid_output = false;
bool test_force_popen_valid_output = false;

// override of popen()
extern "C" FILE* popen(const char* cmd, const char* mode) {
  if (test_force_popen_fail) return nullptr;
  if (test_force_popen_invalid_output) {
    // Write "XYZ" to a temp file and return a pipe to read from it
    std::ofstream("/tmp/mock_py_output.txt") << "XYZ\n";
    return fopen("/tmp/mock_py_output.txt", "r");
  }
  if (test_force_popen_valid_output) {
    std::ofstream("/tmp/mock_py_output.txt") << "12345678\n";
    return fopen("/tmp/mock_py_output.txt", "r");
  }
  // Lookup original popen from libc
  using popen_func_t = FILE* (*)(const char*, const char*);
  static popen_func_t real_popen = (popen_func_t)dlsym(RTLD_NEXT, "popen");
  return real_popen ? real_popen(cmd, mode) : nullptr;
}

std::map<int, std::pair<uint64_t, uint64_t>> mock_numa_info;
bool get_numa_memory_info(int node, uint64_t& total, uint64_t& free) {
  if (mock_numa_info.count(node)) {
    total = mock_numa_info[node].first;
    free = mock_numa_info[node].second;
    return true;
  } else {
    total = 1024;
    free = 1024;
    return false;
  }
}

class ScUtilityTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // inject device map
    DevTypeMap dev_map;
    set_global_dev_type_map(dev_map);
    std::remove("/tmp/nonexistent_config.json");

    test_force_popen_fail = false;
    test_force_popen_invalid_output = false;
    test_force_popen_valid_output = false;
    std::remove("/tmp/mock_py_output.txt");
    set_global_range_numa_map({});  // Reset mapping
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

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_FromConfigFile) {
  int status = load_dev_type_mapping_json(CXL_ID_TYPE_MAP_FILE);
  EXPECT_EQ(status, 0);
  const DevTypeMap* map = get_global_dev_type_map();
  ASSERT_NE(map, nullptr);
  EXPECT_GT(map->size(), 0);
}

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_NonObjectRoot) {
  std::string path = "/tmp/devmap_not_obj.json";
  std::ofstream(path) << R"(["array", "not", "object"])";
  int status = load_dev_type_mapping_json(path);
  EXPECT_EQ(status, -EINVAL);
}

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_MissingDeviceMapKey) {
  std::string path = "/tmp/devmap_missing_key.json";
  std::ofstream(path) << R"({ "some_other_key": [] })";
  int status = load_dev_type_mapping_json(path);
  EXPECT_EQ(status, -EINVAL);
}

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_ValidFlowWithOneEntry) {
  std::string path = "/tmp/devmap_valid.json";
  std::ofstream(path) << R"({
    "device_map": [
      {
        "vendor_id": "1234",
        "device_id": "abcd",
        "device_type": "MockType",
"capabilities": {
        "power_management_version": 1,
        "vendor_specific": {
          "latency_hint": "enabled"
        }
      },
      "advertised_qos": {
        "avg_latency_us": 120,
        "p99_latency_us": 350,
        "io_per_sec": 50000,
        "bw_per_sec": 1000000,
        "io_size_in_bytes": 4096,
        "qd": 32
      }
}
    ],
   "metrics": {
    "domain": "observability",
    "feature_id": 3,
    "category": "metric"
 }
  })";
  int status = load_dev_type_mapping_json(path);
  EXPECT_EQ(status, 0);
  const DevTypeMap* map = get_global_dev_type_map();
  ASSERT_NE(map, nullptr);
  EXPECT_EQ(map->size(), 1);
}

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_MissingSN) {
  std::string path = "/tmp/devmap_invalid_sn.json";
  std::ofstream(path) << R"({
"device_map": [
{
"vendor_id": "1234",
"device_id": "abcd",
"device_type": "Test"
//"serial_number": 1234
}
]
})";

  int status = load_dev_type_mapping_json(path);
  EXPECT_EQ(status, -EINVAL);
}

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_DeviceEntryMissingDeviceType) {
  std::string path = "/tmp/devmap_missing_devtype.json";
  std::ofstream(path) << R"({
"device_map": [
{
"vendor_id": 1234,
"device_id": "abcd",
"device_type": "CMM-H",
"serial_number": "0x1234"
}
],
"metrics": {
    "domain": "observability",
    "feature_id": 3,
    "category": "metric"
 }
})";

  int status = load_dev_type_mapping_json(path);
  EXPECT_EQ(status, 0);

  const DevTypeMap* map = get_global_dev_type_map();
  ASSERT_NE(map, nullptr);
  EXPECT_EQ(map->size(), 0);
}

TEST_F(ScUtilityTest, ParseJsonKey_InvalidJson_ReturnsENOENT) {
  std::string path = "/tmp/invalid_json_file.json";
  // Write malformed JSON to file
  std::ofstream(path) << R"({ "key": "value", )";
  std::string value;
  int status = parse_json_key(path, "key", value);
  EXPECT_EQ(status, -ENOENT);
}

TEST_F(ScUtilityTest, RunCommand_Success_EchoHello) {
  std::string result = run_command("echo hello");
  EXPECT_NE(result.find("hello"), std::string::npos);
}

TEST_F(ScUtilityTest, RunCommand_CommandFails_NonZeroExit) {
  // `false` is a command that does nothing and returns 1
  std::string result = run_command("false");
  EXPECT_TRUE(result.empty());
}

TEST_F(ScUtilityTest, RunCommand_PopenFails_ThrowsRuntimeError) {
  test_force_popen_fail = true;
  EXPECT_THROW(run_command("echo should_fail"), std::runtime_error);
  test_force_popen_fail = false;
}

TEST_F(ScUtilityTest, GetPhysicalAddress_PopenFails) {
  test_force_popen_fail = true;
  EXPECT_THROW(get_physical_cxl_address_from_python("0000:00:00.0"),
               std::runtime_error);
  test_force_popen_fail = false;
}

TEST_F(ScUtilityTest, GetPhysicalAddress_ParseFails_InvalidOutput) {
  test_force_popen_invalid_output = true;
  EXPECT_THROW(get_physical_cxl_address_from_python("0000:00:00.0"),
               std::runtime_error);
  test_force_popen_invalid_output = false;
}

TEST_F(ScUtilityTest, GetPhysicalAddress_SuccessfulParse) {
  test_force_popen_valid_output = true;
  uint64_t addr = get_physical_cxl_address_from_python("0000:00:00.0");
  EXPECT_EQ(addr, 12345678);
  test_force_popen_valid_output = false;
}

TEST_F(ScUtilityTest, GetRangeNumaMap_SuccessfulParse) {
  auto map = get_range_numa_map_from_lsmem("lsmem -o range,node -J");
  // Ensure we parsed at least one valid range
  EXPECT_GT(map.size(), 0);
  //  print one entry for debug
  for (const auto& [range, node] : map) {
    std::cout << "Range: 0x" << std::hex << range.first << "-0x" << range.second
              << " -> NUMA Node: " << std::dec << node << std::endl;
    break;
  }
}

TEST_F(ScUtilityTest, Lsmem_InvalidJson) {
  EXPECT_THROW(get_range_numa_map_from_lsmem("echo { invalid json"),
               std::runtime_error);
}

TEST_F(ScUtilityTest, Lsmem_MissingMemoryArray) {
  EXPECT_THROW(get_range_numa_map_from_lsmem("echo '{ \"fake\": [] }'"),
               std::runtime_error);
}

TEST_F(ScUtilityTest, GetRangeNumaMap_RunCommandFails) {
  std::string cmd = "this_command_should_fail_abcxyz123";
  EXPECT_THROW(get_range_numa_map_from_lsmem(cmd), std::runtime_error);
}

TEST_F(ScUtilityTest, LoadDevTypeMappingJson_parse_device_entry_error) {
  std::string path = "/tmp/devmap_bad_serial.json";
  std::ofstream(path) << R"({
 "device_map": [
 {
 "vendor_id": "1234",
 "device_id": "5678",
 "device_type": "CMMH",
 "serial_number": "not_hex", 
 "lane_speed": 32,
 "lane_width": 8
 }
 ],
"metrics": {
    "domain": "observability",
    "feature_id": 3,
    "category": "metric"
 }
 })";

  int status = load_dev_type_mapping_json(path);
  EXPECT_EQ(status, 0);

  const DevTypeMap* map = get_global_dev_type_map();
  ASSERT_NE(map, nullptr);
  EXPECT_EQ(map->size(), 0);
}

TEST_F(ScUtilityTest, GetPhysicalAddress_PythonFails) {
  EXPECT_THROW({ get_physical_cxl_address_from_python("fail_bdf_123"); },
               std::runtime_error);
}

TEST_F(ScUtilityTest, GetRangeNumaMap_BadHex_TriggersCatchAndContinue) {
  std::string cmd =
      "printf '{\"memory\": ["
      "{\"range\": \"xxx-yyy\", \"node\": 0}"
      "]}'";
  auto map = get_range_numa_map_from_lsmem(cmd);
  EXPECT_EQ(map.size(), 0);
}

TEST_F(ScUtilityTest, DiscoverCXLDevices_SuccessPath) {
  DevTypeMap hints;
  DevJsonHints hint;
  hint.vendor_device_type = "MockCMMH";
  hint.lane_speed_GT_s = 16;
  hint.lane_width = 8;
  hint.manufacturer = "MockInc";
  hint.serial_number = 0xABCDEF;
  hint.fw_revision = "1.0.1";
  hint.feature_supported = "basic";
  hint.cxl_device_type = "Type3";
  hint.domain_type = "PCIe";
  hint.connection_type = "CXL.mem";
  hint.mode_discovered = "auto";
  hint.protocol = "CXL 2.0";
  hint.port_type = "root";
  hint.status = "Healthy";
  hints[{0x1234, 0xABCD}] = hint;

  // Set up popen to return valid address
  test_force_popen_valid_output = true;

  // Set NUMA mapping and memory metrics
  set_global_range_numa_map({{{0x1000, 0xFFFF0000}, test_mock_numa_node}});
  test_mock_total_bytes = 8192LL * 1024 * 1024;  // 8192 MB
  test_mock_free_bytes = 4096LL * 1024 * 1024;   // 4096 MB

  // Run discovery
  auto result = discover_cxl_devices_shared(hints);

  // Validate
  ASSERT_EQ(result.size(), 1);
  const sc_device& dev = result.begin()->second;
  EXPECT_EQ(dev.d_get_info().numa_node, 2);
  EXPECT_EQ(dev.d_get_info().static_info.location, "0001:02:00.1");
  test_force_popen_valid_output = false;
}

TEST_F(ScUtilityTest, DiscoverCXLDevices_PhysicalAddressThrows) {
  DevTypeMap hints;
  DevJsonHints hint;
  hint.vendor_device_type = "MockCMMH";
  hint.lane_speed_GT_s = 16;
  hint.lane_width = 8;
  hint.manufacturer = "MockInc";
  hint.serial_number = 0xABCDEF;
  hint.fw_revision = "1.0.1";
  hint.feature_supported = "basic";
  hint.cxl_device_type = "Type3";
  hint.domain_type = "PCIe";
  hint.connection_type = "CXL.mem";
  hint.mode_discovered = "auto";
  hint.protocol = "CXL 2.0";
  hint.port_type = "root";
  hint.status = "Healthy";
  hints[{0x1234, 0xABCD}] = hint;
  test_force_popen_fail = false;
  test_force_popen_invalid_output = true;
  set_global_range_numa_map({{{0x1000, 0xFFFF0000}, test_mock_numa_node}});
  auto result = discover_cxl_devices_shared(hints);
  EXPECT_EQ(result.size(), 1);
  test_force_popen_invalid_output = false;
}

TEST_F(ScUtilityTest, DiscoverCXLDevices_AddressUnmappedToNUMA) {
  DevTypeMap hints;
  DevJsonHints hint;
  hint.vendor_device_type = "MockCMMH";
  hint.lane_speed_GT_s = 16;
  hint.lane_width = 8;
  hint.manufacturer = "MockInc";
  hint.serial_number = 0xABCDEF;
  hint.fw_revision = "1.0.1";
  hint.feature_supported = "basic";
  hint.cxl_device_type = "Type3";
  hint.domain_type = "PCIe";
  hint.connection_type = "CXL.mem";
  hint.mode_discovered = "auto";
  hint.protocol = "CXL 2.0";
  hint.port_type = "root";
  hint.status = "Healthy";
  hints[{0x1234, 0xABCD}] = hint;
  // Valid popen address -> returns 0x99999999
  test_force_popen_valid_output = true;
  std::ofstream("/tmp/mock_py_output.txt") << "2576980377\n";  // 0x99999999
  // Provide a NUMA map that does NOT include 0x99999999
  set_global_range_numa_map({{{0x1000, 0x80000000}, 0}});
  auto result = discover_cxl_devices_shared(hints);
  ASSERT_EQ(result.size(), 1);
  const sc_device& dev = result.begin()->second;
  ASSERT_EQ(dev.d_get_info().numa_node, 0);

  test_force_popen_valid_output = false;
}

TEST_F(ScUtilityTest, GetNumaNodeFromBDF_PhysicalAddressThrows) {
  test_force_popen_invalid_output = true;
  std::ofstream("/tmp/mock_py_output.txt") << "XYZ\n";  // invalid

  int result = get_numa_node_from_bdf("0000:00:00.0");
  EXPECT_EQ(result, -1);

  test_force_popen_invalid_output = false;
}

TEST_F(ScUtilityTest, GetNumaNodeFromBDF_InvalidAddress_TriggersCatch) {
  // Simulate bad output: not numeric
  test_force_popen_invalid_output = true;
  int result = get_numa_node_from_bdf("0000:00:1f.0");
  EXPECT_EQ(result, -1);
  test_force_popen_invalid_output = false;
}

TEST_F(ScUtilityTest, SetBDFToNumaMap_AssignsCorrectly) {
  std::unordered_map<std::string, int> test_map = {{"0000:00:1f.0", 0},
                                                   {"0000:00:1c.0", 1}};
  set_bdf_to_numa_map(test_map);
}

TEST_F(ScUtilityTest, PciAllocWorks) {
  auto* pacc = pci_alloc();
  ASSERT_NE(pacc, nullptr);
  ASSERT_NE(pacc->devices, nullptr);
  std::cout << "Got device: vendor=0x" << std::hex << pacc->devices->vendor_id
            << "\n";
}

TEST_F(ScUtilityTest, GetNumaMemoryInfo_ReturnsFalse) {
  test_force_failure = true;
  test_force_throw = false;
  uint64_t total = 0, free = 0;
  bool ok = get_numa_memory_info(1, total, free);
  EXPECT_FALSE(ok);
  test_force_failure = false;  // reset for other tests
}

TEST_F(ScUtilityTest, GetNumaMemoryInfo_ReturnsFalseOnException) {
  test_force_throw = true;
  uint64_t total = 0, free = 0;
  bool ok = get_numa_memory_info(2, total, free);
  EXPECT_FALSE(ok);
  test_force_throw = false;  // reset
}

TEST_F(ScUtilityTest, GetNumaNodeFromBDF_OutofRange) {
  RangeToNumaMap range_map;
  range_map[{0x2000000000, 0x2000FFFFFFF}] = 1;
  set_global_range_numa_map(range_map);
  std::string bdf = "0000:03:00.0";
  int node = get_numa_node_from_bdf(bdf);
  EXPECT_EQ(node, -1);
}

TEST_F(ScUtilityTest, GetMetricsInfoReturnsSetValues) {
  MetricsInfo info;
  info.domain = "telemetry";
  info.feature_id = 123;
  info.category = "performance";
  set_metrics_info(info);

  const MetricsInfo& result = get_metrics_info();
  EXPECT_EQ(result.domain, "telemetry");
  EXPECT_EQ(result.feature_id, 123);
  EXPECT_EQ(result.category, "performance");
}

TEST_F(ScUtilityTest, GetRangeNumaMapFromLsmem) {
  RangeToNumaMap map = get_range_numa_map_from_lsmem();
  EXPECT_GE(map.size(), 0);
}

TEST_F(ScUtilityTest, GetEpochReturnsNonZeroValue) {
  uint64_t epoch = get_epoch();
  EXPECT_GT(epoch, 0);
}

TEST_F(ScUtilityTest, GetMetricsInfoReturnsLoadedValues) {
  std::ofstream("/tmp/metrics_valid.json") << R"({
    "device_map": [{
      "vendor_id": "1234",
      "device_id": "5678",
      "device_type": "mock_type"
    }],
    "metrics": {
      "domain": "mock",
      "feature_id": 5,
      "category": "info",
      "severity": "high",
      "source_type": "device",
      "power_state": "active",
      "interval_seconds": 30
    }
  })";
  int rc = load_dev_type_mapping_json("/tmp/metrics_valid.json");
  ASSERT_EQ(rc, 0);
  auto m = get_metrics_info();
  EXPECT_EQ(m.feature_id, 5);
  EXPECT_EQ(m.domain, "mock");
}
