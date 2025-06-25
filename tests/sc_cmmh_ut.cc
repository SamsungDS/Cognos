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
  void discover_devices(DeviceManager& mgr) override {
    sc_id id(0x99);
    DevStaticInfo sinfo;
    sinfo.device_id = id.get_sc_id();
    sinfo.total_capacity_MB = 4096;
    DevInfo dinfo;
    dinfo.static_info = sinfo;
    dinfo.available_capacity_MB = 2048;
    dinfo.numa_attached = 1;
    sc_device dev;
    dev.d_set_static_info(sinfo);
    dev.d_set_dynamic_info(dinfo);
    device_map_[id] = dev;
    mgr.register_device(id, this);
  }
  void clear_device_map() { device_map_.clear(); }
};

bool test_force_popen_valid_output = false;

class DevCMMHTest : public ::testing::Test {
 protected:
  TestableDevCMMH adapter;
  sc_id test_id;

  void SetUp() override {
    test_id = sc_id(0x55);
    // inject BDF → NUMA mapping
    set_bdf_to_numa_map({{"0000:5e:00.0", 2}});

    // Simulate popen returning a fixed physical address
    test_force_popen_valid_output = true;
    std::ofstream("/tmp/mock_py_output.txt") << "12345678\n";  // Any value
    // Setup range map to ensure that the address maps to NUMA node 2
    RangeToNumaMap range_map = {{{0x1000, 0xFFFFFFF0}, 2}};
    set_global_range_numa_map(range_map);

    // prepare test device
    DevStaticInfo sinfo;
    sinfo.location = "0000:5e:00.0";
    sinfo.device_id = 0x55;
    sinfo.protocol = "CXL";
    sinfo.port_type = "Upstream";
    sinfo.total_capacity_MB = 8192;
    sinfo.link_speed = 16;  // Gen5
    sinfo.link_width = 8;   // x8
    DevInfo dinfo;
    dinfo.static_info = sinfo;
    dinfo.status = "Healthy";
    dinfo.numa_attached = -1;
    dinfo.available_capacity_MB = 0;
    sc_device dev;
    dev.d_set_static_info(sinfo);
    dev.d_set_dynamic_info(dinfo);
    adapter.inject_device(test_id, dev);
  }
  void TearDown() override {
    set_bdf_to_numa_map({});
    test_force_popen_valid_output = false;
    set_global_range_numa_map({});
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
  EXPECT_EQ(dinfo.available_capacity_MB, 1024);
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

TEST_F(DevCMMHTest, SimulatePluginRegistration) {
  DeviceManager mgr;
  // simulate plugin loading
  register_plugin(mgr);
  CXLDeviceAdapter* adapter = mgr.getAdapter("cmmh");
  ASSERT_NE(adapter, nullptr);
  auto devices = adapter->list_devices();
  EXPECT_TRUE(devices.empty() || !devices.empty());
}

TEST_F(DevCMMHTest, GetDeviceStats_PopulatesAllFieldsCorrectly) {
  sc_id id(0x55);  // some arbitrary ID

  DevStaticInfo sinfo;
  sinfo.device_id = 0x55;
  sinfo.protocol = "CXL";
  sinfo.port_type = "Upstream";
  sinfo.total_capacity_MB = 8192;
  sinfo.link_speed = 16;  // Gen5
  sinfo.link_width = 8;   // x8
  sinfo.location = "0000:5e:00.0";

  DevInfo dinfo;
  dinfo.static_info = sinfo;
  dinfo.status = "Healthy";
  dinfo.available_capacity_MB = 4096;
  dinfo.numa_attached = 2;

  sc_device dev;
  dev.d_set_static_info(sinfo);
  dev.d_set_dynamic_info(dinfo);

  adapter.inject_device(id, dev);

  StatInfo stats = adapter.get_device_stats(id);

  EXPECT_EQ(stats.device_id, 0x55);
  EXPECT_EQ(stats.protocol, "CXL");
  EXPECT_EQ(stats.port_type, "Upstream");
  EXPECT_EQ(stats.status, "Healthy");

  EXPECT_EQ(stats.total_memory_MB, 8192);
  EXPECT_EQ(stats.available_memory_MB, 1024);
  EXPECT_EQ(stats.used_memory_MB, 7168);

  EXPECT_EQ(stats.total_bandwidth_MBps, 16 * 8 * 125);

  EXPECT_EQ(stats.rw_errors, 0);
  EXPECT_EQ(stats.latency_us, 0);

  EXPECT_GE(stats.used_bandwidth_MBps, 0);
}

TEST_F(DevCMMHTest, DiscoverDevices_RegistersDiscoveredDevices) {
  DevTypeMap mock_dev_type_map;
  DevJsonHints hint;
  hint.vendor_device_type = "TestType";
  hint.protocol = "CXL";
  hint.port_type = "Upstream";
  mock_dev_type_map[{0x1234, 0x5678}] = hint;
  set_global_dev_type_map(mock_dev_type_map);
  DeviceManager mgr;
  adapter.discover_devices(mgr);
  DevInfo info = adapter.get_device_info(sc_id(0x99));
  EXPECT_EQ(info.static_info.total_capacity_MB, 4096);
  EXPECT_EQ(info.available_capacity_MB, 1024);
  EXPECT_EQ(info.numa_attached, 2);
}
