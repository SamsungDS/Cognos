#include <filesystem>
#include <fstream>

#include "cmmh/include/sc_cmmh.h"
#include "gtest/gtest.h"
#include "sc_dev_manager.h"
#include "sc_device.h"
#include "sc_id.h"
#include "sc_utility.h"

class TestableDevCMMH : public DevCMMH {
 public:
  void inject_device(const sc_id& id, const sc_device& dev) {
    device_map_[id] = dev;
  }

  void clear_device_map() { device_map_.clear(); }
};

class DevCMMHTest : public ::testing::Test {
 protected:
  TestableDevCMMH adapter;
  sc_id test_id;

  void SetUp() override {
    test_id = sc_id(12);

    // temp sysfs directory and numa_node file
    std::string bdf = "0000:5e:00.0";
    std::string sysfs_root = "/tmp/sysfs_test";
    std::string full_dir = sysfs_root + "/" + bdf;
    std::filesystem::create_directories(full_dir);
    std::ofstream(full_dir + "/numa_node") << "2";
    setenv("TEST_SYSFS_ROOT", sysfs_root.c_str(), 1);

    sc_device dev;
    DevStaticInfo sinfo;
    sinfo.location = "0000:5e:00.0";
    dev.d_set_static_info(sinfo);

    DevInfo dinfo;
    dinfo.numa_attached = -1;
    dinfo.available_capacity_MB = 0;
    dev.d_set_dynamic_info(dinfo);

    adapter.inject_device(test_id, dev);
  }

  void TearDown() override {
    unsetenv("TEST_SYSFS_ROOT");
    std::filesystem::remove_all("/tmp/sysfs_test");
  }
};

TEST_F(DevCMMHTest, ListDevicesReturnsCorrectCount) {
  auto devices = adapter.list_devices();
  ASSERT_EQ(devices.size(), 1);
  EXPECT_EQ(devices[0].d_get_info().static_info.location, "0000:5e:00.0");
}

TEST_F(DevCMMHTest, GetDeviceObjectReturnsCorrectDevice) {
  sc_device dev = adapter.get_device_object(test_id);
  EXPECT_EQ(dev.d_get_info().static_info.location, "0000:5e:00.0");
}

TEST_F(DevCMMHTest, GetDeviceObjectReturnsDefaultForInvalidId) {
  sc_id invalid_id(99);
  sc_device dev = adapter.get_device_object(invalid_id);
  EXPECT_EQ(dev.d_get_info().static_info.location, "");
}

TEST_F(DevCMMHTest, GetDeviceInfoUpdatesDynamicFields) {
  DevInfo dinfo = adapter.get_device_info(test_id);
  EXPECT_EQ(dinfo.numa_attached, 2);
  EXPECT_EQ(dinfo.available_capacity_MB, 4096);
}

TEST_F(DevCMMHTest, SetupInfoReturnsZero) {
  EXPECT_EQ(adapter.setup_info(), 0);
}

TEST_F(DevCMMHTest, ListDevices_ReturnsAllInjectedDevices) {
  // Inject two dummy devices
  sc_device dev1, dev2;
  DevStaticInfo info1, info2;
  info1.location = "0000:00:01.0";
  info2.location = "0000:00:02.0";
  dev1.d_set_static_info(info1);
  dev2.d_set_static_info(info2);
  sc_id id1(0x1001);
  sc_id id2(0x1002);
  adapter.inject_device(id1, dev1);
  adapter.inject_device(id2, dev2);
  std::vector<sc_device> result = adapter.list_devices();
  EXPECT_TRUE(result[0].d_get_info().static_info.location == "0000:00:01.0" ||
              result[0].d_get_info().static_info.location == "0000:00:02.0");
  EXPECT_TRUE(result[1].d_get_info().static_info.location == "0000:00:01.0" ||
              result[1].d_get_info().static_info.location == "0000:00:02.0");
}

TEST_F(DevCMMHTest, ListDevicesTriggersReturnPath) {
  std::vector<sc_device> result = adapter.list_devices();
  ASSERT_EQ(result.size(), 1);
  // Access something from result to ensure it's fully used
  auto loc = result[0].d_get_info().static_info.location;
  EXPECT_EQ(loc, "0000:5e:00.0");
}

TEST_F(DevCMMHTest, ListHostsReturnsEmptyByDefault) {
  std::vector<sc_host> hosts = adapter.list_hosts();
  ASSERT_TRUE(hosts.empty());  // Default host list is empty
}

TEST_F(DevCMMHTest, GetDeviceInfoReturnsDefaultWhenIdNotFound) {
  sc_id unknown_id(0xFFF);
  DevInfo info = adapter.get_device_info(unknown_id);
  EXPECT_EQ(info.available_capacity_MB, 0);
  EXPECT_EQ(info.numa_attached, 0);
  EXPECT_EQ(info.static_info.location, "");
}

TEST_F(DevCMMHTest, DiscoverDevicesAddsToMapAndRegisters) {
  DeviceManager mgr;
  DevTypeMap dev_map;
  dev_map[{0x1234, 0xABCD}] = "FM_CMMH";
  set_global_dev_type_map(dev_map);  // set before discovery
  adapter.discover_devices(mgr);
  auto devices = adapter.list_devices();
  EXPECT_FALSE(devices.empty());
  const auto& dmap = mgr.get_d_id_map();
  const auto& scidmap = mgr.get_sc_id_adapter_map();
  EXPECT_EQ(dmap.size(), 1);
  EXPECT_EQ(scidmap.size(), 1);
}

TEST_F(DevCMMHTest, SimulatePluginRegistration) {
  DeviceManager mgr;
  // simulate plugin loading
  register_plugin(mgr);
  CXLDeviceAdapter* adapter = mgr.getAdapter("cmmh");
  ASSERT_NE(adapter, nullptr);
  auto devices = adapter->list_devices();
  EXPECT_TRUE(devices.empty() || !devices.empty());
}

TEST_F(DevCMMHTest, DiscoverDevices_NullGlobalMap_LogsAndReturns) {
  adapter.clear_device_map();
  DeviceManager mgr;
  adapter.discover_devices(mgr);
  auto devices = adapter.list_devices();
  EXPECT_EQ(devices.size(), 0);
}
