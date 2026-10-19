#include <cstdio>
#include <fstream>
#include <string>

#include "cmmmp/include/sc_cmmmp.h"
#include "gtest/gtest.h"
#include "mock_libmpctl.h"
#include "sc_api_structs.h"
#include "sc_dev_manager.h"
#include "sc_id.h"

namespace {

class TestableDevCMMMP : public DevCMMMP {
 public:
  CmmMpConfig& mutable_config() { return cfg_; }
  bool has_ctx() const { return ctx_ != nullptr; }
};

const uint64_t kPoolId = cmmmp_dev_id(kCmmMpKindPool, 0);

uint64_t mpdev_id(uint16_t slot) { return cmmmp_dev_id(kCmmMpKindMpDev, slot); }
uint64_t mpn_id(uint16_t id) { return cmmmp_dev_id(kCmmMpKindMpn, id); }

std::string vendor_specific(const DevInfo& info, const std::string& key) {
  const auto& vs = info.static_info.capabilities.vendor_specific;
  auto it = vs.find(key);
  return it != vs.end() ? it->second : "";
}

class DevCMMMPTest : public ::testing::Test {
 protected:
  void SetUp() override {
    mock_mpctl::reset();
    // local pooled device in slot 1, remote pooled device in slot 2
    mock_mpctl::add_mpdev(1, true, true, 64, 0xA1B2C3D4);
    mock_mpctl::add_mpdev(2, false, true, 64, 0x11223344);
    mock_mpctl::add_mpn(32, 1, MPCTL_MPN_LOCAL);
    mock_mpctl::add_mpn(32, 2, MPCTL_MPN_REMOTE);
  }

  TestableDevCMMMP adapter;
  DeviceManager mgr;
};

}  // namespace

TEST(CmmMpDevIdTest, EncodesAndDecodesKindAndIndex) {
  EXPECT_EQ(cmmmp_dev_id(kCmmMpKindMpDev, 0x12), 0x1E98FF010012ULL);
  EXPECT_EQ(cmmmp_kind(cmmmp_dev_id(kCmmMpKindPool, 0)), MpKind::POOL);
  EXPECT_EQ(cmmmp_kind(cmmmp_dev_id(kCmmMpKindMpDev, 7)), MpKind::MPDEV);
  EXPECT_EQ(cmmmp_kind(cmmmp_dev_id(kCmmMpKindMpn, 3)), MpKind::MPN);
  EXPECT_EQ(cmmmp_index(cmmmp_dev_id(kCmmMpKindMpn, 3)), 3);
}

TEST(CmmMpDevIdTest, DoesNotMatchPciDerivedIds) {
  // CMM-H style ID: vendor 0x1E98, device 0x0DDB, bus 0x27
  uint64_t cmmh_id = (0x1E98ULL << 32) | (0x0DDBULL << 16) | (0x27 << 8);
  EXPECT_EQ(cmmmp_kind(cmmh_id), MpKind::UNKNOWN);
  EXPECT_EQ(cmmmp_kind(0x1B00FF010001ULL), MpKind::UNKNOWN);
}

TEST(CmmMpMapRcTest, MapsLibraryCodesToErrno) {
  EXPECT_EQ(DevCMMMP::map_rc(MPCTL_RC_SUCCESS), 0);
  EXPECT_EQ(DevCMMMP::map_rc(MPCTL_RC_NO_MP_FOUND), -ENODEV);
  EXPECT_EQ(DevCMMMP::map_rc(MPCTL_RC_POOL_NOT_READY), -EAGAIN);
  EXPECT_EQ(DevCMMMP::map_rc(MPCTL_RC_MPN_NOT_FOUND), -ENOENT);
  EXPECT_EQ(DevCMMMP::map_rc(MPCTL_RC_ERROR), -EIO);
  EXPECT_EQ(DevCMMMP::map_rc(99), -EIO);
}

TEST_F(DevCMMMPTest, ConstructorDoesNotInitializeLibrary) {
  EXPECT_EQ(mock_mpctl::state().init_calls, 0);
  EXPECT_FALSE(adapter.has_ctx());
}

TEST_F(DevCMMMPTest, DiscoverWithoutDeviceRegistersNothing) {
  mock_mpctl::state().init_rc = MPCTL_RC_NO_MP_FOUND;
  adapter.discover_devices(mgr);
  EXPECT_TRUE(adapter.list_devices().empty());
  EXPECT_TRUE(mgr.get_d_id_map().empty());
  EXPECT_FALSE(adapter.has_ctx());
}

TEST_F(DevCMMMPTest, DiscoverRegistersPoolMpDevsAndMpns) {
  adapter.discover_devices(mgr);

  EXPECT_EQ(adapter.list_devices().size(), 5u);
  const auto& ids = mgr.get_d_id_map();
  EXPECT_EQ(ids.size(), 5u);
  EXPECT_TRUE(ids.count(kPoolId));
  EXPECT_TRUE(ids.count(mpdev_id(1)));
  EXPECT_TRUE(ids.count(mpdev_id(2)));
  EXPECT_TRUE(ids.count(mpn_id(0)));
  EXPECT_TRUE(ids.count(mpn_id(1)));
  EXPECT_EQ(mgr.get_sc_id_adapter_map().at(sc_id(kPoolId)), &adapter);
}

TEST_F(DevCMMMPTest, RediscoveryIsIdempotent) {
  adapter.discover_devices(mgr);
  adapter.discover_devices(mgr);
  EXPECT_EQ(adapter.list_devices().size(), 5u);
  EXPECT_EQ(mgr.get_d_id_map().size(), 5u);
  EXPECT_EQ(mock_mpctl::state().init_calls, 1);
}

TEST_F(DevCMMMPTest, RediscoveryPicksUpNewMpn) {
  adapter.discover_devices(mgr);
  mock_mpctl::add_mpn(16, 1, MPCTL_MPN_LOCAL);
  adapter.discover_devices(mgr);
  EXPECT_TRUE(mgr.get_d_id_map().count(mpn_id(2)));
}

TEST_F(DevCMMMPTest, RemoteMpDevsCanBeHidden) {
  adapter.mutable_config().expose_remote_mpdevs = false;
  adapter.discover_devices(mgr);
  EXPECT_TRUE(mgr.get_d_id_map().count(mpdev_id(1)));
  EXPECT_FALSE(mgr.get_d_id_map().count(mpdev_id(2)));
}

TEST_F(DevCMMMPTest, DisabledAdapterSkipsDiscovery) {
  adapter.mutable_config().enabled = false;
  adapter.discover_devices(mgr);
  EXPECT_TRUE(adapter.list_devices().empty());
  EXPECT_EQ(mock_mpctl::state().init_calls, 0);
}

TEST_F(DevCMMMPTest, DuplicateSlotIdGetsFallbackIndex) {
  mock_mpctl::add_mpdev(1, false, false, 64, 0x55667788);
  adapter.discover_devices(mgr);
  EXPECT_TRUE(mgr.get_d_id_map().count(mpdev_id(kCmmMpIndexFallback | 2)));
  DevInfo info =
      adapter.get_device_info(sc_id(mpdev_id(kCmmMpIndexFallback | 2)));
  EXPECT_EQ(info.static_info.serial_number, 0x55667788u);
  EXPECT_EQ(info.status, "Unpooled");
}

TEST_F(DevCMMMPTest, PoolNotReadyWithoutAutoSetupIsReported) {
  mock_mpctl::state().pool.ready = 0;
  adapter.discover_devices(mgr);
  EXPECT_EQ(mock_mpctl::state().host_init_calls, 0);
  EXPECT_EQ(mock_mpctl::state().pool_create_calls, 0);
  EXPECT_EQ(adapter.get_device_info(sc_id(kPoolId)).status, "NotReady");
}

TEST_F(DevCMMMPTest, AutoPoolSetupCreatesPoolAndReinitializes) {
  mock_mpctl::state().pool.ready = 0;
  adapter.mutable_config().auto_pool_setup = true;
  adapter.discover_devices(mgr);
  EXPECT_EQ(mock_mpctl::state().host_init_calls, 1);
  EXPECT_EQ(mock_mpctl::state().pool_create_calls, 1);
  EXPECT_EQ(mock_mpctl::state().init_calls, 2);
  EXPECT_EQ(mock_mpctl::state().open_contexts, 1);
  EXPECT_EQ(adapter.get_device_info(sc_id(kPoolId)).status, "Ready");
}

TEST_F(DevCMMMPTest, AutoPoolSetupFailureKeepsPoolNotReady) {
  mock_mpctl::state().pool.ready = 0;
  mock_mpctl::state().op_rc = MPCTL_RC_ERROR;
  adapter.mutable_config().auto_pool_setup = true;
  adapter.discover_devices(mgr);
  EXPECT_EQ(mock_mpctl::state().pool_create_calls, 0);
  EXPECT_EQ(adapter.get_device_info(sc_id(kPoolId)).status, "NotReady");
}

TEST_F(DevCMMMPTest, PoolInfoIsTranslated) {
  adapter.discover_devices(mgr);
  DevInfo info = adapter.get_device_info(sc_id(kPoolId));
  EXPECT_EQ(info.static_info.device_id, kPoolId);
  EXPECT_EQ(info.static_info.vendor_device_type, "CMM-MP Pool");
  EXPECT_EQ(info.static_info.total_capacity_MB, 128u * 1024);
  EXPECT_EQ(info.available_capacity_MB, 64u * 1024);
  EXPECT_EQ(info.status, "Ready");
  EXPECT_EQ(vendor_specific(info, "mpdev_count"), "2");
  EXPECT_EQ(vendor_specific(info, "mpn_count"), "2");
}

TEST_F(DevCMMMPTest, MpDevInfoIsTranslated) {
  adapter.discover_devices(mgr);
  DevInfo local = adapter.get_device_info(sc_id(mpdev_id(1)));
  EXPECT_EQ(local.static_info.vendor_device_type, "CMM-MP");
  EXPECT_EQ(local.static_info.manufacturer, "samsung");
  EXPECT_EQ(local.static_info.cxl_device_type, "Type3");
  EXPECT_EQ(local.static_info.serial_number, 0xA1B2C3D4u);
  EXPECT_EQ(local.static_info.fw_revision, "fpga 0x0103 / fw 7");
  EXPECT_EQ(local.static_info.total_capacity_MB, 64u * 1024);
  EXPECT_EQ(local.static_info.location, "local");
  EXPECT_EQ(local.static_info.connection_type, "CXL.mem");
  EXPECT_EQ(local.status, "Pooled");
  EXPECT_EQ(vendor_specific(local, "slot_id"), "1");
  EXPECT_EQ(vendor_specific(local, "eth_port0"), "up");
  EXPECT_EQ(vendor_specific(local, "eth_port1"), "up");
  EXPECT_EQ(vendor_specific(local, "parent_id"), "0x1e98ff000000");

  DevInfo remote = adapter.get_device_info(sc_id(mpdev_id(2)));
  EXPECT_EQ(remote.static_info.location, "remote");
  EXPECT_EQ(remote.static_info.connection_type, "Ethernet (pool back-end)");
}

TEST_F(DevCMMMPTest, MpDevLinkDownAndHotIsDegradedAndWarning) {
  adapter.discover_devices(mgr);
  mock_mpctl::state().mpdevs[0].link_status = 0x1;
  mock_mpctl::state().mpdevs[0].fpga_temp = 90;
  DevInfo info = adapter.get_device_info(sc_id(mpdev_id(1)));
  EXPECT_EQ(info.status, "Pooled, Degraded, Warning");
  EXPECT_EQ(vendor_specific(info, "eth_port1"), "down");
}

TEST_F(DevCMMMPTest, MpnInfoIsTranslated) {
  mock_mpctl::state().mpns[1].mode = MPCTL_MPN_MODE_DEVDAX;
  mock_mpctl::state().mpns[1].status = 1;
  snprintf(mock_mpctl::state().mpns[1].dax_devname, STR_MAX, "dax1.0");
  adapter.discover_devices(mgr);

  DevInfo offline = adapter.get_device_info(sc_id(mpn_id(0)));
  EXPECT_EQ(offline.static_info.vendor_device_type, "CMM-MP MPN");
  EXPECT_EQ(offline.static_info.total_capacity_MB, 32u * 1024);
  EXPECT_EQ(offline.available_capacity_MB, 32u * 1024);
  EXPECT_EQ(offline.static_info.mode_discovered, "pmem");
  EXPECT_EQ(offline.static_info.location, "region0");
  EXPECT_EQ(offline.static_info.domain_type, "CXL region");
  EXPECT_EQ(offline.status, "Offline");
  EXPECT_EQ(offline.numa_node, -1);
  EXPECT_EQ(vendor_specific(offline, "mpn_location"), "local");
  EXPECT_EQ(vendor_specific(offline, "hpa"), "0x1000000000");

  DevInfo dax = adapter.get_device_info(sc_id(mpn_id(1)));
  EXPECT_EQ(dax.static_info.mode_discovered, "devdax");
  EXPECT_EQ(dax.static_info.location, "dax1.0");
  EXPECT_EQ(dax.status, "Online");
  EXPECT_EQ(dax.available_capacity_MB, 0u);
  EXPECT_EQ(vendor_specific(dax, "mpn_location"), "remote");
}

TEST_F(DevCMMMPTest, MissingLibraryInfoMarksDeviceUnavailable) {
  adapter.discover_devices(mgr);
  mock_mpctl::state().fail_get_info = true;
  DevInfo info = adapter.get_device_info(sc_id(mpdev_id(1)));
  EXPECT_EQ(info.status, "Unavailable");
  EXPECT_EQ(info.static_info.serial_number, 0xA1B2C3D4u);
  StatInfo stats = adapter.get_device_stats(sc_id(mpdev_id(1)));
  EXPECT_EQ(stats.status, "Unavailable");
  EXPECT_FALSE(stats.sensor_stats.has_value());
}

TEST_F(DevCMMMPTest, ChangedMpDevHandleMarksDeviceUnavailable) {
  adapter.discover_devices(mgr);
  mock_mpctl::state().mpdevs[0].chip_id = 0xDEADBEEF;
  EXPECT_EQ(adapter.get_device_info(sc_id(mpdev_id(1))).status, "Unavailable");
}

TEST_F(DevCMMMPTest, UnknownDeviceReturnsDefaults) {
  adapter.discover_devices(mgr);
  DevInfo info = adapter.get_device_info(sc_id(0x1234));
  EXPECT_EQ(info.static_info.device_id, 0u);
  EXPECT_EQ(adapter.get_device_object(sc_id(0x1234)).d_get_id().get_sc_id(),
            0u);
}

TEST_F(DevCMMMPTest, MpDevStatsReportTemperatureInFahrenheit) {
  adapter.discover_devices(mgr);
  StatInfo stats = adapter.get_device_stats(sc_id(mpdev_id(1)));
  EXPECT_EQ(stats.device_id, mpdev_id(1));
  EXPECT_EQ(stats.total_memory_MB, 64u * 1024);
  EXPECT_EQ(stats.used_bandwidth_Bps, 0u);
  ASSERT_TRUE(stats.sensor_stats.has_value());
  EXPECT_EQ(stats.sensor_stats->status, CMMH_STAT_RC_SUCCESS);
  EXPECT_EQ(stats.sensor_stats->fpga_temp, 122u);  // 50 C
}

TEST_F(DevCMMMPTest, MpnStatsReportMemoryUsage) {
  adapter.discover_devices(mgr);
  StatInfo stats = adapter.get_device_stats(sc_id(mpn_id(0)));
  EXPECT_EQ(stats.total_memory_MB, 32u * 1024);
  EXPECT_EQ(stats.available_memory_MB, 32u * 1024);
  EXPECT_EQ(stats.used_memory_MB, 0u);
  EXPECT_FALSE(stats.sensor_stats.has_value());
}

TEST_F(DevCMMMPTest, AttachNumaOnlinesMpn) {
  adapter.discover_devices(mgr);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}), 0);
  EXPECT_EQ(mock_mpctl::state().online_calls, 1);
  DevInfo info = adapter.get_device_info(sc_id(mpn_id(0)));
  EXPECT_EQ(info.status, "Online");
  EXPECT_EQ(info.static_info.mode_discovered, "numa");
}

TEST_F(DevCMMMPTest, AttachDevdaxEnablesDax) {
  adapter.discover_devices(mgr);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"devdax"}), 0);
  EXPECT_EQ(mock_mpctl::state().enable_dax_calls, 1);
  EXPECT_EQ(adapter.get_device_object(sc_id(mpn_id(0)))
                .d_get_info()
                .static_info.location,
            "dax0.0");
}

TEST_F(DevCMMMPTest, AttachUsesConfiguredDefaultMode) {
  adapter.mutable_config().default_attach_mode = "devdax";
  adapter.discover_devices(mgr);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{}), 0);
  EXPECT_EQ(mock_mpctl::state().enable_dax_calls, 1);
  EXPECT_EQ(mock_mpctl::state().online_calls, 0);
}

TEST_F(DevCMMMPTest, AttachRejectsInvalidRequests) {
  adapter.discover_devices(mgr);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpdev_id(1)), AttachParams{"numa"}),
            -EINVAL);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"fsdax"}),
            -EINVAL);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(9)), AttachParams{"numa"}),
            -ENOENT);
  EXPECT_EQ(mock_mpctl::state().online_calls, 0);
}

TEST_F(DevCMMMPTest, AttachRequiresReadyPool) {
  adapter.discover_devices(mgr);
  mock_mpctl::state().pool.ready = 0;
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}),
            -EAGAIN);
  EXPECT_EQ(mock_mpctl::state().online_calls, 0);
}

TEST_F(DevCMMMPTest, AttachRejectsOnlineMpn) {
  adapter.discover_devices(mgr);
  ASSERT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}), 0);
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}),
            -EBUSY);
  EXPECT_EQ(mock_mpctl::state().online_calls, 1);
}

TEST_F(DevCMMMPTest, AttachMapsLibraryError) {
  adapter.discover_devices(mgr);
  mock_mpctl::state().op_rc = MPCTL_RC_ERROR;
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}),
            -EIO);
  EXPECT_EQ(adapter.get_device_info(sc_id(mpn_id(0))).status, "Offline");
}

TEST_F(DevCMMMPTest, AttachWithoutDeviceReturnsNoDevice) {
  mock_mpctl::state().init_rc = MPCTL_RC_NO_MP_FOUND;
  EXPECT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}),
            -ENODEV);
}

TEST_F(DevCMMMPTest, DetachOfflinesOnlineMpn) {
  adapter.discover_devices(mgr);
  ASSERT_EQ(adapter.attach_memory(sc_id(mpn_id(0)), AttachParams{"numa"}), 0);
  EXPECT_EQ(adapter.detach_memory(sc_id(mpn_id(0))), 0);
  EXPECT_EQ(mock_mpctl::state().offline_calls, 1);
  EXPECT_EQ(adapter.get_device_info(sc_id(mpn_id(0))).status, "Offline");
}

TEST_F(DevCMMMPTest, DetachRejectsOfflineMpnAndNonMpn) {
  adapter.discover_devices(mgr);
  EXPECT_EQ(adapter.detach_memory(sc_id(mpn_id(0))), -EBUSY);
  EXPECT_EQ(adapter.detach_memory(sc_id(kPoolId)), -EINVAL);
  EXPECT_EQ(mock_mpctl::state().offline_calls, 0);
}

TEST_F(DevCMMMPTest, PoolOperationsCallLibrary) {
  EXPECT_EQ(adapter.pool_operation(PoolOp::HOST_INIT_DISCOVERY, {}), 0);
  EXPECT_EQ(mock_mpctl::state().host_init_calls, 1);
  EXPECT_EQ(mock_mpctl::state().init_calls, 1);

  EXPECT_EQ(adapter.pool_operation(PoolOp::CREATE, {}), 0);
  EXPECT_EQ(mock_mpctl::state().pool_create_calls, 1);
  EXPECT_EQ(mock_mpctl::state().init_calls, 2);

  PoolOpParams params;
  params.id = 3;
  EXPECT_EQ(adapter.pool_operation(PoolOp::ADD, params), 0);
  EXPECT_EQ(mock_mpctl::state().pool_add_calls, 1);
  EXPECT_EQ(mock_mpctl::state().last_pool_add_id, 3u);
  EXPECT_EQ(mock_mpctl::state().init_calls, 3);
  EXPECT_EQ(mock_mpctl::state().open_contexts, 1);
}

TEST_F(DevCMMMPTest, PoolOperationMapsLibraryError) {
  mock_mpctl::state().op_rc = MPCTL_RC_POOL_NOT_READY;
  EXPECT_EQ(adapter.pool_operation(PoolOp::ADD, {}), -EAGAIN);
  EXPECT_EQ(mock_mpctl::state().init_calls, 1);
}

TEST_F(DevCMMMPTest, DestructorReleasesContext) {
  {
    DevCMMMP local_adapter;
    DeviceManager local_mgr;
    local_adapter.discover_devices(local_mgr);
    EXPECT_EQ(mock_mpctl::state().open_contexts, 1);
  }
  EXPECT_EQ(mock_mpctl::state().open_contexts, 0);
  EXPECT_EQ(mock_mpctl::state().close_calls, 1);
}

TEST_F(DevCMMMPTest, LoadConfigReadsCmmMpSection) {
  const std::string path = "/tmp/sc_cmmmp_ut_cxl.conf";
  std::ofstream(path) << R"({
    "plugin_dir": "/tmp",
    "cmmmp": {
      "enabled": false,
      "auto_pool_setup": true,
      "default_attach_mode": "devdax",
      "expose_remote_mpdevs": false,
      "fpga_temp_warn_C": 70
    }
  })";
  EXPECT_EQ(adapter.load_config(path), 0);
  EXPECT_FALSE(adapter.config().enabled);
  EXPECT_TRUE(adapter.config().auto_pool_setup);
  EXPECT_EQ(adapter.config().default_attach_mode, "devdax");
  EXPECT_FALSE(adapter.config().expose_remote_mpdevs);
  EXPECT_EQ(adapter.config().fpga_temp_warn_C, 70);
  std::remove(path.c_str());
}

TEST_F(DevCMMMPTest, LoadConfigKeepsDefaults) {
  const std::string path = "/tmp/sc_cmmmp_ut_defaults.conf";
  std::ofstream(path) << R"({"cmmmp": {"default_attach_mode": "fsdax"}})";
  EXPECT_EQ(adapter.load_config(path), 0);
  EXPECT_EQ(adapter.config().default_attach_mode, "numa");
  EXPECT_TRUE(adapter.config().enabled);
  EXPECT_FALSE(adapter.config().auto_pool_setup);

  std::ofstream(path) << R"({"plugin_dir": "/tmp"})";
  EXPECT_EQ(adapter.load_config(path), 0);
  EXPECT_EQ(adapter.config().fpga_temp_warn_C, 85);
  std::remove(path.c_str());

  EXPECT_EQ(adapter.load_config("/tmp/sc_cmmmp_ut_missing.conf"), -ENOENT);
}

TEST_F(DevCMMMPTest, RegisterAdapterUsesCmmMpName) {
  register_cmmmp_adapter(mgr);
  EXPECT_NE(mgr.getAdapter("cmmmp"), nullptr);
}

TEST_F(DevCMMMPTest, DeviceManagerRoutesMemoryOperations) {
  mgr.registerAdapter("cmmmp", &adapter);
  adapter.discover_devices(mgr);

  EXPECT_EQ(mgr.attach_memory(mpn_id(0), AttachParams{"numa"}), 0);
  EXPECT_EQ(mgr.detach_memory(mpn_id(0)), 0);
  EXPECT_EQ(mgr.attach_memory(0x1234, AttachParams{"numa"}), -ENODEV);
  EXPECT_EQ(mgr.detach_memory(0x1234), -ENODEV);
}

TEST_F(DevCMMMPTest, DeviceManagerPoolOperationRediscovers) {
  mgr.registerAdapter("cmmmp", &adapter);
  adapter.discover_devices(mgr);
  mock_mpctl::add_mpn(16, 1, MPCTL_MPN_LOCAL);

  PoolOpParams params;
  params.id = 2;
  EXPECT_EQ(mgr.pool_operation("cmmmp", PoolOp::ADD, params), 0);
  EXPECT_TRUE(mgr.get_d_id_map().count(mpn_id(2)));
  EXPECT_EQ(mgr.pool_operation("missing", PoolOp::ADD, params), -ENODEV);
}
