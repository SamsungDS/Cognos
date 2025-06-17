#include <gtest/gtest.h>

#include "mock_cmmh.h"
#include "sc_dev_manager.h"

class MockCMMHTest : public ::testing::Test {
 protected:
  MockCMMH adapter;
  DeviceManager mgr;

  void SetUp() override { adapter.discover_devices(mgr); }
};

TEST_F(MockCMMHTest, DiscoverDevicesRegistersDevice) {
  auto devices = adapter.list_devices();
  ASSERT_EQ(devices.size(), 1);
  EXPECT_EQ(devices[0].d_get_info().static_info.device_id, 0x1E3A5B7CDE00);
}

TEST_F(MockCMMHTest, GetDeviceInfoReturnsCorrectInfo) {
  sc_id sid(0x1E3A5B7CDE00);
  DevInfo info = adapter.get_device_info(sid);
  EXPECT_EQ(info.static_info.manufacturer, "Mock");
  EXPECT_EQ(info.static_info.vendor_device_type, "Mock");
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
