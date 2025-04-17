#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <jansson.h>

#include <memory>
#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

#include "sc_cxl_dev_adapter.h"
#include "sc_dev_manager.h"
#include "sc_device.h"
#include "sc_test_cxl_adapter.h"
#include "sc_utility.h"

class DeviceManagerTest : public ::testing::Test {
 protected:
  TestCXLDeviceAdapter testAdapter;
  DeviceManager devManager;

  DeviceManagerTest() : devManager() {}

  void SetUp() override {
    // Create sc_device objects using valid constructor
    sc_device dev1(1, "dev1", 1024, 1);
    DevStaticInfo stat1, stat2;
    stat1.id = dev1.d_get_id().get_sc_id();
    stat1.location = "0x1234";
    dev1.d_set_static_info(stat1);

    sc_device dev2(2, "dev2", 2048, 2);
    stat2.id = dev2.d_get_id().get_sc_id();
    stat2.location = "0x5678";
    dev2.d_set_static_info(stat2);

    // Register devices with the test adapter
    testAdapter.add_mock_device(dev1);
    testAdapter.add_mock_device(dev2);

    // Register adapter and devices with the DeviceManager
    devManager.registerAdapter("TestAdapter", &testAdapter);
    devManager.register_device(dev1.d_get_id(), &testAdapter);
    devManager.register_device(dev2.d_get_id(), &testAdapter);
  }

  void TearDown() override {
    devManager.unregister_device(&testAdapter);
    devManager.unregisterAdapter("TestAdapter");
  }
};

TEST_F(DeviceManagerTest, ListDevices_NoFilter) {
  auto devices = devManager.list_devices();
  std::unordered_set<uint64_t> actual_ids;

  for (const auto& dev : devices) {
    actual_ids.insert(dev.d_get_id().get_sc_id());
  }

  std::unordered_set<uint64_t> expected_ids = {1, 2};
  EXPECT_EQ(actual_ids, expected_ids);
}

TEST_F(DeviceManagerTest, ListDevices_FilterForOne) {
  std::unordered_set<uint64_t> filter = {1};
  auto devices = devManager.list_devices(filter);

  ASSERT_EQ(devices.size(), 1);
  EXPECT_EQ(devices[0].d_get_id().get_sc_id(), 1);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_ValidDevice) {
  auto dev_info = devManager.get_device_info(1);
  ASSERT_TRUE(dev_info.has_value());

  EXPECT_EQ(dev_info->static_info.id, 1);
  EXPECT_EQ(dev_info->static_info.location, "0x1234");
}

TEST_F(DeviceManagerTest, GetDeviceInfo_InvalidDevice) {
  auto dev_info = devManager.get_device_info(999);
  EXPECT_FALSE(dev_info.has_value());
}

TEST_F(DeviceManagerTest, GetAdapter_SuccessAndFailure) {
  auto anotherAdapter = std::make_shared<TestCXLDeviceAdapter>();
  devManager.registerAdapter("TempAdapter", anotherAdapter.get());

  auto* valid = devManager.getAdapter("TempAdapter");
  EXPECT_NE(valid, nullptr);

  auto* invalid = devManager.getAdapter("MissingAdapter");
  EXPECT_EQ(invalid, nullptr);

  devManager.unregisterAdapter("TempAdapter");
}

TEST_F(DeviceManagerTest, ListDevices_AdapterNotSupported) {
  testAdapter.setListDevicesStatus(-ENOTSUP);
  auto devices = devManager.list_devices();
  EXPECT_TRUE(devices.empty());
}

TEST_F(DeviceManagerTest, ListDevices_StatusFail) {
  testAdapter.setListDevicesStatus(-EINVAL);
  auto devices = devManager.list_devices();
  EXPECT_TRUE(devices.empty());
}

TEST_F(DeviceManagerTest, ListDevices_MultiArgFail) {
  testAdapter.setListDevicesStatus(-EINVAL);
  std::unordered_set<uint64_t> filter = {1};
  auto devices = devManager.list_devices(filter);
  EXPECT_TRUE(devices.empty());
}

TEST_F(DeviceManagerTest, GetDeviceInfo_AdapterFailsRetrieval) {
  TestCXLDeviceAdapter failingAdapter;
  failingAdapter.setGetDevicesInfoStatus(-EIO);

  sc_device dev(200, "fail_dev", 4096, 3);
  DevStaticInfo stat;
  stat.location = "0xfail";
  dev.d_set_static_info(stat);
  failingAdapter.add_mock_device(dev);

  devManager.register_device(dev.d_get_id(), &failingAdapter);

  auto dev_info = devManager.get_device_info(200);
  EXPECT_FALSE(dev_info.has_value());
}

TEST_F(DeviceManagerTest, ListDevices_AdapterReturnsDevices) {
  auto devices = devManager.list_devices();
  ASSERT_EQ(devices.size(), 2);
  EXPECT_EQ(devices[0].d_get_id().get_sc_id(), 1);
  EXPECT_EQ(devices[1].d_get_id().get_sc_id(), 2);
}

TEST_F(DeviceManagerTest, ListDevices_AdapterThrowsException) {
  testAdapter.setListDevicesStatus(-EIO);
  auto devices = devManager.list_devices();
  EXPECT_TRUE(devices.empty());
}

TEST_F(DeviceManagerTest, ListDevices_Filtered_DeviceIdNotRegistered) {
  // 999 is not registered
  std::unordered_set<uint64_t> filter = {999};
  auto devices = devManager.list_devices(filter);

  // Since 999 is unknown, it should skip
  EXPECT_TRUE(devices.empty());
}

TEST_F(DeviceManagerTest, ListDevices_Filtered_NoAdapterFound) {
  sc_id sid(300);
  // Force null adapter mapping
  devManager.register_device(sid, nullptr);

  std::unordered_set<uint64_t> filter = {300};
  auto devices = devManager.list_devices(filter);

  EXPECT_TRUE(devices.empty());
}

TEST_F(DeviceManagerTest, ListDevices_Filtered_Success) {
  std::unordered_set<uint64_t> filter = {1};
  auto devices = devManager.list_devices(filter);

  ASSERT_EQ(devices.size(), 1);
  EXPECT_EQ(devices[0].d_get_id().get_sc_id(), 1);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_NoAdapterMappedForScId) {
  sc_id fake_scid(1234);
  // Register a valid sc_id mapping
  devManager.register_device(fake_scid, &testAdapter);
  devManager.unregisterAdapter("TestAdapter");

  auto result = devManager.get_device_info(1234);
  // fail with nullopt
  EXPECT_FALSE(result.has_value());
}

TEST_F(DeviceManagerTest, DiscoverDevices_RegistersDevices) {
  TestCXLDeviceAdapter discoveryAdapter;

  DevStaticInfo stat1, stat2;
  sc_device dev1(10, "dA", 128, 10);
  stat1.location = "locA";
  dev1.d_set_static_info(stat1);
  sc_device dev2(20, "dB", 256, 20);
  stat2.location = "locB";
  dev2.d_set_static_info(stat2);

  discoveryAdapter.add_mock_device(dev1);
  discoveryAdapter.add_mock_device(dev2);

  devManager.registerAdapter("DiscoveryAdapter", &discoveryAdapter);
  devManager.discover_devices();
  auto all_devices = devManager.list_devices();
  std::unordered_set<uint64_t> ids;
  for (const auto& d : all_devices) {
    ids.insert(d.d_get_id().get_sc_id());
  }

  std::unordered_set<uint64_t> expected = {1, 2, 10, 20};
  EXPECT_EQ(ids, expected);

  devManager.unregister_device(&discoveryAdapter);
  devManager.unregisterAdapter("DiscoveryAdapter");
}

TEST_F(DeviceManagerTest, DiscoverDevices_AdapterThrowsStdException) {
  class ThrowingAdapter : public TestCXLDeviceAdapter {
   public:
    void discover_devices(DeviceManager& mgr) override {
      throw std::runtime_error("Simulated failure");
    }
  };
  ThrowingAdapter adapter;
  devManager.registerAdapter("ThrowingAdapter", &adapter);
  devManager.discover_devices();
}

TEST_F(DeviceManagerTest, DiscoverDevices_AdapterThrowsUnknownException) {
  class UnknownThrowingAdapter : public TestCXLDeviceAdapter {
   public:
    void discover_devices(DeviceManager& mgr) override { throw 42; }
  };

  UnknownThrowingAdapter adapter;
  devManager.registerAdapter("UnknownAdapter", &adapter);
  devManager.discover_devices();
}
