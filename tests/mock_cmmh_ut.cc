#include <gtest/gtest.h>

#include "mock_cmmh.h"
#include "sc_dev_manager.h"
#include "sc_servicer.h"

class MockCMMHTest : public ::testing::Test {
 protected:
  MockCMMH adapter;
  DeviceManager mgr;

  void SetUp() override {
    std::cout << "[INFO] Loading mock config from: " << CXL_ID_TYPE_MAP_FILE
              << std::endl;
    adapter.discover_devices(mgr);
    auto devices = adapter.list_devices();
    ASSERT_FALSE(devices.empty())
        << "Device discovery failed. Check config file at: "
        << CXL_ID_TYPE_MAP_FILE;
  }
};

TEST_F(MockCMMHTest, DiscoverDevicesRegistersDevice) {
  auto devices = adapter.list_devices();
  ASSERT_EQ(devices.size(), 2);
  EXPECT_EQ(devices[0].d_get_info().static_info.device_id, 0x1E3A5B7ADE00);
}

TEST_F(MockCMMHTest, GetDeviceInfoReturnsCorrectInfo) {
  sc_id sid(0x1E3A5B7CDE00);
  DevInfo info = adapter.get_device_info(sid);
  EXPECT_EQ(info.static_info.manufacturer, "samsung");
  EXPECT_EQ(info.static_info.vendor_device_type, "CMM-H");
  EXPECT_EQ(info.status, "Healthy");
}

TEST_F(MockCMMHTest, GetDeviceStatsReturnsCorrectStats) {
  sc_id sid(0x1E3A5B7CDE00);
  StatInfo stats = adapter.get_device_stats(sid);
  EXPECT_EQ(stats.total_memory_MB, 8192);
  EXPECT_EQ(stats.used_bandwidth_MBps, 1104548);
  ASSERT_TRUE(stats.sensor_stats.has_value());
  EXPECT_EQ(stats.sensor_stats->fpga_temp, 46);
}

TEST_F(MockCMMHTest, GetDeviceObjectReturnsDevice) {
  sc_id sid(0x1E3A5B7CDE00);
  sc_device dev = adapter.get_device_object(sid);
  EXPECT_EQ(dev.d_get_id().get_sc_id(), 33235991846400);
}

TEST_F(MockCMMHTest, GetDeviceInfoThrowsForInvalidId) {
  sc_id invalid(999999);
  EXPECT_THROW(adapter.get_device_info(invalid), std::runtime_error);
}

TEST_F(MockCMMHTest, GetDeviceStatsThrowsForInvalidId) {
  sc_id invalid(999999);
  EXPECT_THROW(adapter.get_device_stats(invalid), std::runtime_error);
}

TEST_F(MockCMMHTest, GetDeviceObjectThrowsForInvalidId) {
  sc_id invalid(999999);
  EXPECT_THROW(adapter.get_device_object(invalid), std::runtime_error);
}

TEST_F(MockCMMHTest, DiscoverFailsOnInvalidJsonFile) {
  // Backup the original path
  const std::string bad_path = "/tmp/invalid.json";
  std::ofstream ofs(bad_path);
  ofs << "{ invalid_json: }";  // malformed
  ofs.close();

  setenv("CXL_ID_TYPE_MAP_FILE", bad_path.c_str(), 1);
  MockCMMH bad_adapter;
  DeviceManager dm;
  testing::internal::CaptureStdout();
  bad_adapter.discover_devices(dm);
  std::string err = testing::internal::GetCapturedStdout();
  EXPECT_TRUE(err.find("Failed to parse mock JSON") != std::string::npos);
}

TEST_F(MockCMMHTest, DiscoverFailsWhenDeviceMapMissing) {
  const std::string no_devmap_path = "/tmp/no_devmap.json";
  std::ofstream ofs(no_devmap_path);
  ofs << R"({ "not_device_map": [] })";
  ofs.close();

  setenv("CXL_ID_TYPE_MAP_FILE", no_devmap_path.c_str(), 1);
  MockCMMH bad_adapter;
  DeviceManager dm;
  testing::internal::CaptureStdout();
  bad_adapter.discover_devices(dm);
  std::string err = testing::internal::GetCapturedStdout();
  EXPECT_TRUE(err.find("Missing or invalid 'device_map'") != std::string::npos);
}

TEST_F(MockCMMHTest, DiscoverSkipsMockEmptyDevice) {
  const std::string skip_mock_path = "/tmp/skip_mock.json";
  std::ofstream ofs(skip_mock_path);
  ofs << R"({
"device_map": [
{ "mock_device_id": "0x1", "mock_empty": true }
]
})";
  ofs.close();

  setenv("CXL_ID_TYPE_MAP_FILE", skip_mock_path.c_str(), 1);
  MockCMMH empty_adapter;
  DeviceManager dm;
  testing::internal::CaptureStdout();
  empty_adapter.discover_devices(dm);
  std::string err = testing::internal::GetCapturedStdout();
  EXPECT_TRUE(err.find("Skipping mock_empty device at index: 0") !=
              std::string::npos);
  EXPECT_TRUE(empty_adapter.list_devices().empty());
}
