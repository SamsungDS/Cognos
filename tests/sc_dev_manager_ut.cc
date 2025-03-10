#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <jansson.h>

#include <memory>
#include <string>
#include <unordered_set>

#include "sc_cxl_dev_adapter.h"
#include "sc_dev_manager.h"
#include "sc_test_utils.h"
#include "sc_utility.h"
class TestCXLDeviceAdapter : public CXLDeviceAdapter {
 public:
  std::string mockResponse;
  int mockErrorCode = 0;
  bool mockEmptyResponse = false;

 public:
  int list_devices(const std::unordered_set<uint64_t>& device_filter,
                   std::string& buffer) override {
    if (mockEmptyResponse) {
      buffer = R"()";
      return buffer.size();
    } else if (!mockResponse.empty()) {
      buffer = mockResponse;
      return buffer.size();
    } else if (mockErrorCode != 0) {
      // simulate error code
      std::ostringstream oss;
      oss << R"({"rc": ")" << std::to_string(mockErrorCode)
          << R"(", "message": ")"
          << R"(Invalid JSON format")"
          << R"(})";
      buffer = oss.str();
      return mockErrorCode;
    } else {
      std::ostringstream oss;
      bool first = true;
      if (device_filter.empty()) {
        if (!first) oss << ",";
        oss << R"({"id": "1", "type": "1", "pcie_addr": "0x1234"})";
        first = false;
        if (!first) oss << ",";
        oss << R"({"id": "2", "type": "2", "pcie_addr": "0x5678"})";
      } else {
        // Apply filtering
        if (device_filter.count(1)) {
          if (!first) oss << ",";
          oss << R"({"id": "1", "type": "1", "pcie_addr": "0x1234"})";
          first = false;
        }
        if (device_filter.count(2)) {
          if (!first) oss << ",";
          oss << R"({"id": "2", "type": "2", "pcie_addr": "0x5678"})";
        }
      }

      buffer = oss.str();
      return 0;
    }
  }

  int get_device_info(uint64_t device_id, std::string& buffer) override {
    if (mockErrorCode != 0) return mockErrorCode;
    if (device_id == 1) {
      buffer = R"({"id": "1", "type": "1", "pcie_addr": "0x1234"})";
      return buffer.size();
    } else if (device_id == 2) {
      buffer = R"({"id": "2", "type": "2", "pcie_addr": "0x5678"})";
      return buffer.size();
    } else if (device_id == 1999) {
      buffer.clear();
      return -EIO;
    }
    return -ENOENT;
  }

  int attach_memory(uint64_t device_id, uint64_t host_id,
                    std::string& buffer) override {
    if (mockErrorCode != 0) return mockErrorCode;
    buffer = R"({"status": "attached", "device_id": )" +
             std::to_string(device_id) + "}";
    return buffer.size();
  }

  int detach_memory(uint64_t device_id, uint64_t host_id,
                    std::string& buffer) override {
    if (mockErrorCode != 0) return mockErrorCode;
    buffer = R"({"status": "detached", "device_id": )" +
             std::to_string(device_id) + "}";
    return buffer.size();
  }

  int list_hosts(std::string& buffer) override {
    buffer = R"({"hosts": [{"id": "srf07.msl.lab"}, {"id": "emr02.msl.lab"}]})";
    return buffer.size();
  }

  int setup_info() override { return 0; }

  bool handlesDevice(uint64_t d_id) const override {
    return d_id == 1 || d_id == 2;
  }

  void setMockError(int errorCode) { mockErrorCode = errorCode; }

  void setEmptyResponse() { mockEmptyResponse = true; }

  void setLargeDeviceListResponse(size_t device_count) {
    std::ostringstream oss;
    oss << "[";

    for (size_t i = 0; i < device_count; ++i) {
      if (i > 0) oss << ",";
      oss << R"({"id": ")" << i << R"(", "type": "1", "pcie_addr": "0x)"
          << std::hex << (0x1000 + i) << R"("})";
    }

    oss << "]";
    mockResponse = oss.str();
  }

  void setMalformedJsonResponse() {
    mockErrorCode = -22;  // EINVAL
  }
};

class DeviceManagerTest : public ::testing::Test {
 protected:
  DeviceManager& devManager = DeviceManager::getInstance();
  DeviceRegistry& devRegistry = DeviceRegistry::getInstance();
  TestCXLDeviceAdapter testAdapter;

  void SetUp() override {
    // Register the test adapter in DeviceRegistry
    devRegistry.registerAdapter("TestAdapter", &testAdapter);
  }
  void TearDown() override {
    // Cleanup after each test
    devRegistry.unregisterAdapter("TestAdapter");
  }

  /**
   * @brief Parses a JSON array response and extracts the value of the "id"
   * field from each object.
   *
   * @param response The JSON response string.
   * @return An unordered_set of device IDs extracted from the response.
   */
  std::unordered_set<std::string> extractDeviceIds(
      const std::string& response) {
    std::unordered_set<std::string> ids;
    json_error_t error;
    json_t* root = json_loads(response.c_str(), 0, &error);
    if (!root) {
      ADD_FAILURE() << "JSON Parsing Failed: " << error.text;
      return ids;
    }
    if (!json_is_object(root)) {
      ADD_FAILURE() << "Expected a JSON object as the root.";
      json_decref(root);
      return ids;
    }
    json_t* devices_array = json_object_get(root, "devices");
    // Ensure the root is a JSON array
    if (!json_is_array(devices_array)) {
      ADD_FAILURE() << "Expected `devices` to be a JSON array.";
      json_decref(root);
      return ids;
    }
    size_t index;
    json_t* value;
    json_array_foreach(devices_array, index, value) {
      json_t* id_field = json_object_get(value, "id");
      if (json_is_string(id_field)) {
        ids.insert(json_string_value(id_field));
      }
    }
    json_decref(root);
    return ids;
  }
};

TEST_F(DeviceManagerTest, ListDevices_NoFilter) {
  std::unordered_map<std::string, std::string> params;
  std::string response = devManager.list_devices(params);
  std::cout << "test response: " << response << std::endl;
  std::unordered_set<std::string> actual_ids = extractDeviceIds(response);
  std::cout << "set values" << std::endl;
  for (auto& id : actual_ids) std::cout << id << std::endl;
  std::unordered_set<std::string> expected_ids = {"1", "2"};
  EXPECT_EQ(actual_ids, expected_ids);
}

TEST_F(DeviceManagerTest, ListDevices_FilterForOne) {
  std::unordered_map<std::string, std::string> params = {
      {"command_params", R"({"device_id": ["1"]})"}};
  std::string response = devManager.list_devices(params);
  std::unordered_set<std::string> actual_ids = extractDeviceIds(response);
  std::unordered_set<std::string> expected_ids = {"1"};
  EXPECT_EQ(actual_ids, expected_ids);
}

TEST_F(DeviceManagerTest, ListDevices_InvalidJson) {
  std::unordered_map<std::string, std::string> params = {
      {"command_params", R"({device_id: 1,2]})"}};
  std::string response = devManager.list_devices(params);
  EXPECT_EQ(response,
            R"({"rc": "EINVAL", "message": "Invalid request parameters"})");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_ValidDevice) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "1"}};
  std::string response = devManager.get_device_info(params);
  EXPECT_FALSE(response.empty());
  EXPECT_EQ(get_json_value(response, "id"), "1");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_InvalidDevice) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "999"}};
  std::string response = devManager.get_device_info(params);
  EXPECT_EQ(get_json_value(response, "message"),
            "No adapter found for device ID");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_MissingDeviceId) {
  std::unordered_map<std::string, std::string> params;
  std::string response = devManager.get_device_info(params);
  EXPECT_EQ(get_json_value(response, "message"),
            "Missing 'device_id' parameter");
}

TEST_F(DeviceManagerTest, AttachDevice_Valid) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "1"},
                                                         {"host_id", "100"}};
  std::string response = devManager.attach_memory(params);
  std::cout << "attach memeory output: " << response << std::endl;
  EXPECT_FALSE(response.empty());
  EXPECT_EQ(get_json_value(response, "status"), "attached");
  EXPECT_EQ(get_json_value(response, "device_id"), "1");
}

TEST_F(DeviceManagerTest, AttachDevice_MissingParameters) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "1"}};
  std::string response = devManager.attach_memory(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Missing device_id or host_id");
}

TEST_F(DeviceManagerTest, AttachMemory_NoAdapter) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "999"},
                                                         {"host_id", "200"}};
  std::string response = devManager.attach_memory(params);
  EXPECT_EQ(get_json_value(response, "rc"), "ENOENT");
  EXPECT_EQ(get_json_value(response, "message"),
            "No adapter found for device ID");
}

TEST_F(DeviceManagerTest, AttachMemory_InvalidDeviceID) {
  std::unordered_map<std::string, std::string> params;
  params["device_id"] = "invalid_id";  // This will trigger EINVAL
  params["host_id"] = "123";
  std::string response = devManager.attach_memory(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"), "Invalid id format");
}

TEST_F(DeviceManagerTest, AttachMemory_AdapterFailure) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  testAdapter->setMalformedJsonResponse();  // Simulate failure
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_map<std::string, std::string> params;
  params["device_id"] = "1";
  params["host_id"] = "123";
  std::string response = devManager.attach_memory(params);
  std::cout << "attach-response, " << response << std::endl;
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, DetachDevice_Valid) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "1"},
                                                         {"host_id", "100"}};
  std::string response = devManager.detach_memory(params);
  EXPECT_FALSE(response.empty());
  EXPECT_EQ(get_json_value(response, "status"), "detached");
  EXPECT_EQ(get_json_value(response, "device_id"), "1");
}

TEST_F(DeviceManagerTest, DetachDevice_MissingParameters) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "1"}};
  std::string response = devManager.detach_memory(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Missing device_id or host_id");
}

TEST_F(DeviceManagerTest, DetachMemory_NoAdapter) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "999"},
                                                         {"host_id", "200"}};
  std::string response = devManager.detach_memory(params);
  EXPECT_EQ(get_json_value(response, "rc"), "ENOENT");
  EXPECT_EQ(get_json_value(response, "message"),
            "No adapter found for device ID");
}

TEST_F(DeviceManagerTest, DetachMemory_InvalidDeviceID) {
  std::unordered_map<std::string, std::string> params;
  params["device_id"] = "invalid_id";
  params["host_id"] = "123";
  std::string response = devManager.detach_memory(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"), "Invalid id format");
}

TEST_F(DeviceManagerTest, DetachMemory_AdapterFailure) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  testAdapter->setMalformedJsonResponse();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_map<std::string, std::string> params;
  params["device_id"] = "1";
  params["host_id"] = "123";
  std::string response = devManager.detach_memory(params);
  std::cout << "attach-response, " << response << std::endl;
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_InvalidDeviceIdFormat) {
  std::unordered_map<std::string, std::string> params = {{"device_id", "abc"}};
  std::string response = devManager.get_device_info(params);
  std::cout << response << std::endl;
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"), "Invalid id format");
}

TEST_F(DeviceManagerTest, ProcessDeviceIds_ValidSingleString) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"device_id": "1"})";
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(device_filter.size(), 1);
  EXPECT_NE(device_filter.find(1), device_filter.end());
}
TEST_F(DeviceManagerTest, ProcessDeviceIds_ValidArray) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"device_id": ["1", "2", "3"]})";
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(device_filter.size(), 3);
  EXPECT_NE(device_filter.find(1), device_filter.end());
  EXPECT_NE(device_filter.find(2), device_filter.end());
  EXPECT_NE(device_filter.find(3), device_filter.end());
}
TEST_F(DeviceManagerTest, ProcessDeviceIds_EmptyArray) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"device_id": []})";
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, 0);
  EXPECT_TRUE(device_filter.empty());
}
TEST_F(DeviceManagerTest, ProcessDeviceIds_InvalidJson) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"device_id": [1, 2,})";  // Malformed JSON
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(device_filter.empty());
}
TEST_F(DeviceManagerTest, ProcessDeviceIds_InvalidType) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"device_id": 12345})";
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(device_filter.empty());
}

TEST_F(DeviceManagerTest, ProcessDeviceIds_MissingDeviceId) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"other_param": "value"})";
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, 0);
  EXPECT_TRUE(device_filter.empty());
}

TEST_F(DeviceManagerTest, ProcessDeviceIds_NullDeviceId) {
  std::unordered_set<uint64_t> device_filter;
  std::string json_request = R"({"device_id": null})";
  int status = devManager.fetch_dev_ids_from_req(json_request, device_filter);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(device_filter.empty());
}

TEST_F(DeviceManagerTest, FetchAllDevices_ReturnsAllDevices) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_set<uint64_t> device_filter;
  std::string response;
  int status = devManager.fetch_all_devices(device_filter, response);
  EXPECT_EQ(status, 0);
  EXPECT_FALSE(response.empty());
  EXPECT_FALSE(get_json_value(response, "devices").empty());
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, FetchAllDevices_WithFilter) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_set<uint64_t> device_filter = {1};
  std::string response;
  int status = devManager.fetch_all_devices(device_filter, response);
  EXPECT_EQ(status, 0);
  EXPECT_FALSE(response.empty());
  EXPECT_NE(get_json_value(response, "devices").find("1"), std::string::npos);
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, FetchAllDevices_InvalidJson) {
  // Malformed JSON
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  testAdapter->setMockError(-EINVAL);
  std::unordered_set<uint64_t> device_filter;
  std::string response;
  devManager.fetch_all_devices(device_filter, response);
  EXPECT_EQ(get_json_value(response, "rc"), "");
}

TEST_F(DeviceManagerTest, FetchAllDevices_EmptyResult) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  testAdapter->setEmptyResponse();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_set<uint64_t> device_filter;
  std::string response;
  int status = devManager.fetch_all_devices(device_filter, response);
  std::cout << "FetchAllDevices_EmptyResult : " << status
            << ", response: " << response << std::endl;
  EXPECT_EQ(status, 0);
  EXPECT_EQ(response, R"({"devices":[]})");
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, FetchAllDevices_MultipleAdapters) {
  auto adapter1 = std::make_shared<TestCXLDeviceAdapter>();
  auto adapter2 = std::make_shared<TestCXLDeviceAdapter>();
  DeviceRegistry::getInstance().registerAdapter("Adapter1", adapter1.get());
  DeviceRegistry::getInstance().registerAdapter("Adapter2", adapter2.get());
  std::unordered_set<uint64_t> device_filter;
  std::string response;
  int status = devManager.fetch_all_devices(device_filter, response);
  EXPECT_EQ(status, 0);
  EXPECT_NE(get_json_value(response, "devices").find("1"), std::string::npos);
  EXPECT_NE(get_json_value(response, "devices").find("2"), std::string::npos);
  DeviceRegistry::getInstance().unregisterAdapter("Adapter1");
  DeviceRegistry::getInstance().unregisterAdapter("Adapter2");
}

TEST_F(DeviceManagerTest, FetchAllDevices_LargeDeviceList) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  testAdapter->setLargeDeviceListResponse(1000);
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_set<uint64_t> device_filter;
  std::string response;
  int status = devManager.fetch_all_devices(device_filter, response);
  EXPECT_EQ(status, 0);
  EXPECT_FALSE(get_json_value(response, "devices").empty());
  EXPECT_GE(get_json_value(response, "devices").size(), 1000);
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, FetchAllDevices_FlattenFailure) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  testAdapter->setMalformedJsonResponse();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());

  std::unordered_set<uint64_t> device_filter;
  std::string response;
  int status = devManager.fetch_all_devices(device_filter, response);
  EXPECT_EQ(status, -EINVAL);
  response =
      posix_err_to_json(std::abs(status), "Error processing device data");
  std::cout << "response :" << response << " , status: " << status << std::endl;
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Error processing device data");

  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_Failure) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  testAdapter->setMalformedJsonResponse();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());
  std::unordered_map<std::string, std::string> params;
  params["device_id"] = "1";
  std::string response = devManager.get_device_info(params);
  EXPECT_EQ(get_json_value(response, "rc"), "EINVAL");
  EXPECT_EQ(get_json_value(response, "message"),
            "Failed to retrieve device info");
  DeviceRegistry::getInstance().unregisterAdapter("TestAdapter");
}

TEST_F(DeviceManagerTest, GetAdapter_SuccessAndFailure) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  DeviceRegistry::getInstance().registerAdapter("TestAdapter",
                                                testAdapter.get());

  std::string adapterName = "TestAdapter";
  // Test successful retrieval
  CXLDeviceAdapter* retrievedAdapter =
      DeviceRegistry::getInstance().getAdapter(adapterName);
  EXPECT_NE(retrievedAdapter, nullptr)
      << "Expected a valid adapter but got nullptr";
  // Test retrieval of a non-existent adapter
  CXLDeviceAdapter* nonExistentAdapter =
      DeviceRegistry::getInstance().getAdapter("NonExistentAdapter");
  EXPECT_EQ(nonExistentAdapter, nullptr)
      << "Expected nullptr for a non-existent adapter";
  // Cleanup
  DeviceRegistry::getInstance().unregisterAdapter(adapterName);
}
