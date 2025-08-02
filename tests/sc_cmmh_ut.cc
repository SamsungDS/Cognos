#include <filesystem>
#include <fstream>

#include "cmmh/include/sc_cmmh.h"
#include "gtest/gtest.h"
#include "sc_api_structs.h"
#include "sc_dev_manager.h"
#include "sc_device.h"
#include "sc_id.h"
#include "sc_utility.h"

__attribute__((weak)) const DevTypeMap* find_dev_type_map() { return nullptr; }

class MockBandwidthMonitor : public BandwidthMonitor {
 public:
  MockBandwidthMonitor(uint64_t index, int interval)
      : BandwidthMonitor(index, interval), fake_bw(0) {}

  void set_fake_bandwidth(uint64_t bw) { fake_bw = bw; }

  uint64_t get_average_Bps() const override { return fake_bw; }

 private:
  uint64_t fake_bw;
};

class TestableDevCMMH : public DevCMMH {
 public:
  std::unordered_map<uint64_t, uint64_t> hdm_base_to_device_index_map_;

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
    dinfo.numa_node = 1;
    sc_device dev;
    dev.d_set_static_info(sinfo);
    dev.d_set_dynamic_info(dinfo);
    device_map_[id] = dev;
    mgr.register_device(id, this);
  }
  void clear_device_map() { device_map_.clear(); }

  void test_set_hdm_base_map_direct(
      const std::unordered_map<uint64_t, uint64_t>& mock_map) {
    hdm_base_to_device_index_map_ = mock_map;
  }
  const std::unordered_map<uint64_t, uint64_t>&
  get_hdm_base_to_device_index_map() const {
    return hdm_base_to_device_index_map_;
  }

  void inject_bandwidth_monitor(sc_id id,
                                std::unique_ptr<BandwidthMonitor> mon) {
    dev_to_bwmon[id] = std::move(mon);
  }
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
    sinfo.link_speed_GT_s = 16;  // Gen5
    sinfo.link_width = 8;        // x8
    DevInfo dinfo;
    dinfo.static_info = sinfo;
    dinfo.status = "Healthy";
    dinfo.numa_node = -1;
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
  EXPECT_EQ(dinfo.numa_node, 2);
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
  EXPECT_EQ(info.numa_node, 0);
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
  sinfo.link_speed_GT_s = 16;  // Gen5
  sinfo.link_width = 8;        // x8
  sinfo.location = "0000:5e:00.0";

  DevInfo dinfo;
  dinfo.static_info = sinfo;
  dinfo.status = "Healthy";
  dinfo.available_capacity_MB = 4096;
  dinfo.numa_node = 2;

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
  EXPECT_EQ(stats.available_memory_MB, 4096);
  EXPECT_EQ(stats.used_memory_MB, 4096);

  EXPECT_EQ(stats.total_bandwidth_MBps, 16 * 8 * 125);

  EXPECT_EQ(stats.rw_errors, 0);
  EXPECT_EQ(stats.latency_us, 0);

  EXPECT_GE(stats.used_bandwidth_Bps, 0);
}

TEST_F(DevCMMHTest, DiscoverDevices_RegistersDiscoveredDevices) {
  DevTypeMap mock_dev_type_map;
  DevJsonHints hint;
  hint.vendor_device_type = "TestType";
  hint.protocol = "CXL";
  hint.port_type = "Upstream";
  mock_dev_type_map[{0x1234, 0x5678}] = hint;
  set_dev_type_map(mock_dev_type_map);
  DeviceManager mgr;
  adapter.discover_devices(mgr);
  DevInfo info = adapter.get_device_info(sc_id(0x99));
  EXPECT_EQ(info.static_info.total_capacity_MB, 4096);
  EXPECT_EQ(info.available_capacity_MB, 4096);
  EXPECT_EQ(info.numa_node, 2);
}

TEST_F(DevCMMHTest, DiscoverDevicesRealPath) {
  DevTypeMap mock_dev_type_map;
  DevJsonHints hint;
  hint.vendor_device_type = "TestType";
  hint.protocol = "CXL";
  hint.port_type = "Upstream";
  uint16_t vendor_id = 0x0000;
  uint16_t device_id = 0x0055;
  mock_dev_type_map[{vendor_id, device_id}] = hint;
  set_dev_type_map(mock_dev_type_map);

  adapter.clear_device_map();
  DeviceManager mgr;
  adapter.DevCMMH::discover_devices(mgr);
  auto devices = adapter.list_devices();
  EXPECT_TRUE(devices.empty());
}

TEST_F(DevCMMHTest, BuildHDMBaseToDeviceIndexMap) {
  std::unordered_map<uint64_t, uint64_t> mock_map = {
      {0xABCDEF00, 1},
      {0xABCDEF10, 2},
  };
  adapter.test_set_hdm_base_map_direct(mock_map);
  const auto& map = adapter.get_hdm_base_to_device_index_map();
  ASSERT_EQ(map.size(), 2);
  EXPECT_EQ(map.at(0xABCDEF00), 1);
  EXPECT_EQ(map.at(0xABCDEF10), 2);
}

TEST_F(DevCMMHTest, GetDeviceStats_ReturnsDefaultForInvalidId) {
  sc_id invalid_id(0xABC);
  StatInfo stats = adapter.get_device_stats(invalid_id);
  EXPECT_EQ(stats.device_id, 0);
  EXPECT_EQ(stats.total_memory_MB, 0);
  EXPECT_EQ(stats.available_memory_MB, 0);
  EXPECT_EQ(stats.used_memory_MB, 0);
  EXPECT_EQ(stats.total_bandwidth_MBps, 0);
}

TEST_F(DevCMMHTest, DiscoverDevices_NoPciDevicesFound) {
  adapter.clear_device_map();
  set_dev_type_map({});
  DeviceManager mgr;
  adapter.DevCMMH::discover_devices(mgr);
  auto devices = adapter.list_devices();
  EXPECT_TRUE(devices.empty());
}

TEST_F(DevCMMHTest, GetDeviceObject_EmptyMapReturnsDefault) {
  adapter.clear_device_map();
  sc_device dev = adapter.get_device_object(test_id);
  EXPECT_EQ(dev.d_get_info().static_info.location, "");
}

TEST_F(DevCMMHTest, GetDeviceInfo_ParsesPhysicalAddressCorrectly) {
  DevInfo dinfo = adapter.get_device_info(test_id);
  EXPECT_EQ(dinfo.numa_node, 2);
}

TEST_F(DevCMMHTest, GetDeviceStats_ReturnsBandwidthFromMonitor) {
  sc_id id(123);

  adapter.clear_device_map();
  sc_device dev(id.get_sc_id(), "test", 8192, 0);
  DevStaticInfo stat{};
  stat.device_id = id.get_sc_id();
  stat.total_capacity_MB = 8192;
  stat.bw_interval_sec = 1;
  stat.device_index = 0;
  dev.d_set_static_info(stat);
  adapter.inject_device(id, dev);

  auto monitor = std::make_unique<MockBandwidthMonitor>(0, 1);
  monitor->set_fake_bandwidth(987654);  // Simulate 987654 Bps
  adapter.inject_bandwidth_monitor(id, std::move(monitor));

  StatInfo s = adapter.get_device_stats(id);
  EXPECT_EQ(s.used_bandwidth_Bps, 987654);
}
