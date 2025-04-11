#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <jansson.h>

#include <memory>
#include <string>
#include <unordered_set>

#include "sc_cxl_dev_adapter.h"
#include "sc_dev_manager.h"
#include "sc_test_cxl_adapter.h"
#include "sc_test_utils.h"
#include "sc_utility.h"

class DeviceManagerTest : public ::testing::Test {
 protected:
  TestCXLDeviceAdapter testAdapter;
  DeviceManager devManager;

  DeviceManagerTest() : devManager() {}

  void SetUp() override {
    // Register the test adapter in DeviceRegistry
    devManager.registerAdapter("TestAdapter", &testAdapter);

    // Register devices explicitly into device manager
    sc_id sid1(1);
    sc_id sid2(2);
    devManager.register_device(sid1, &testAdapter);
    devManager.register_device(sid2, &testAdapter);
  }
  void TearDown() override {
    // Cleanup after each test
    devManager.unregister_device(&testAdapter);
    devManager.unregisterAdapter("TestAdapter");
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
  std::string response = devManager.list_devices();
  std::cout << "test response: " << response << std::endl;
  std::unordered_set<std::string> actual_ids = extractDeviceIds(response);
  std::cout << "set values" << std::endl;
  for (auto& id : actual_ids) std::cout << id << std::endl;
  std::unordered_set<std::string> expected_ids = {"1", "2"};
  EXPECT_EQ(actual_ids, expected_ids);
}

TEST_F(DeviceManagerTest, ListDevices_FilterForOne) {
  std::unordered_set<uint64_t> filter = {1};
  std::string response = devManager.list_devices(filter);
  std::unordered_set<std::string> actual_ids = extractDeviceIds(response);
  std::unordered_set<std::string> expected_ids = {"1"};
  EXPECT_EQ(actual_ids, expected_ids);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_ValidDevice) {
  std::string response = devManager.get_device_info(1);
  EXPECT_FALSE(response.empty());
  EXPECT_EQ(get_json_value(response, "id"), "1");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_InvalidDevice) {
  std::string response = devManager.get_device_info(999);
  EXPECT_EQ(get_json_value(response, "message"), "Device ID not found");
}

TEST_F(DeviceManagerTest, GetAdapter_SuccessAndFailure) {
  auto testAdapter = std::make_shared<TestCXLDeviceAdapter>();
  devManager.registerAdapter("TestAdapter", testAdapter.get());

  std::string adapterName = "TestAdapter";
  // Test successful retrieval
  CXLDeviceAdapter* retrievedAdapter = devManager.getAdapter(adapterName);
  EXPECT_NE(retrievedAdapter, nullptr)
      << "Expected a valid adapter but got nullptr";
  // Test retrieval of a non-existent adapter
  CXLDeviceAdapter* nonExistentAdapter =
      devManager.getAdapter("NonExistentAdapter");
  EXPECT_EQ(nonExistentAdapter, nullptr)
      << "Expected nullptr for a non-existent adapter";
  // Cleanup
  devManager.unregisterAdapter(adapterName);
}

TEST_F(DeviceManagerTest, ListDevices_AdapterNotSupported) {
  // Override mock to return -ENOTSUP
  testAdapter.setListDevicesStatus(-ENOTSUP);
  // Register mock adapter
  devManager.registerAdapter("Test", &testAdapter);
  // Call list_devices which should skip the adapter silently
  std::string response = devManager.list_devices();
  // Since ENOTSUP skips, the devices array should be empty
  EXPECT_EQ(get_json_value(response, "devices"), "[]");
}

TEST_F(DeviceManagerTest, ListDevices_StatusFail) {
  testAdapter.setListDevicesStatus(-EINVAL);
  devManager.registerAdapter("Test", &testAdapter);
  std::string response = devManager.list_devices();
  EXPECT_EQ(get_json_value(response, "devices"), "");
}

TEST_F(DeviceManagerTest, ListDevices_MultiArgFail) {
  testAdapter.setListDevicesStatus(-EINVAL);
  // register both maps
  sc_id sid(1);
  devManager.register_device(sid, &testAdapter);
  devManager.registerAdapter("Test", &testAdapter);
  std::string response = devManager.list_devices({1});
  EXPECT_EQ(get_json_value(response, "devices"), "");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_AdapterFailsRetrieval) {
  TestCXLDeviceAdapter testAdapter;
  testAdapter.setGetDeviceInfoStatus(-EIO);  // simulate failure
  sc_id sid(200);
  devManager.register_device(sid, &testAdapter);
  std::string response = devManager.get_device_info(200);
  EXPECT_EQ(get_json_value(response, "rc"), "EIO");
  EXPECT_EQ(get_json_value(response, "message"),
            "Failed to retrieve device info");
}
