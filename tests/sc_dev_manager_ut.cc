#include <gtest/gtest.h>

#include "sc_cxl_dev_adapter.h"
#include "sc_dev_manager.h"
#include "sc_device.h"

class ThrowingAdapter : public CXLDeviceAdapter {
 public:
  enum class Mode { THROW_STD_EXCEPTION, THROW_UNKNOWN_EXCEPTION, NONE };
  Mode throw_mode = Mode::NONE;

  std::vector<sc_device> list_devices() const override { return {}; }

  sc_device get_device_object(const sc_id&) const override {
    throw std::runtime_error("Simulated exception in get_device_object");
  }

  DevInfo get_device_info(const sc_id&) const override { return {}; }

  StatInfo get_device_stats(const sc_id&) const override {
    throw std::runtime_error("Simulated get_device_stats error");
  }

  void discover_devices(DeviceManager& mgr) override {
    switch (throw_mode) {
      case Mode::THROW_STD_EXCEPTION:
        throw std::runtime_error("Simulated discover_devices std::exception");
      case Mode::THROW_UNKNOWN_EXCEPTION:
        throw 42;  // Non-standard exception
      case Mode::NONE:
        mgr.register_device(sc_id(1234567), const_cast<ThrowingAdapter*>(this));
        break;
    }
  }

  int setup_info() override { return 0; }

  std::vector<sc_host> list_hosts() { return {}; }
};

class DummyAdapter : public CXLDeviceAdapter {
 public:
  bool simulate_throw = false;
  std::vector<sc_device> list_devices() const override {
    sc_device dev(123456, "TestDevice", 2048, 1);

    DevStaticInfo static_info;
    static_info.device_id = 123456;
    static_info.manufacturer = "Samsung";
    static_info.serial_number = 987654321;
    static_info.total_capacity_MB = 2048;
    static_info.vendor_device_type = "CMM-H";

    DevInfo info;
    info.static_info = static_info;
    info.available_capacity_MB = 1024;
    info.status = "active";

    dev.d_set_static_info(static_info);
    dev.d_set_dynamic_info(info);

    return {dev};
  }

  sc_device get_device_object(const sc_id& sid) const override {
    auto devices = list_devices();
    return !devices.empty() ? devices.front() : sc_device();
  }

  DevInfo get_device_info(const sc_id& sid) const override {
    if (simulate_throw) throw std::runtime_error("simulated error");
    return list_devices().front().d_get_info();
  }

  void discover_devices(DeviceManager& mgr) override {
    sc_id id(123456);
    mgr.register_device(id, const_cast<DummyAdapter*>(this));
  }

  int setup_info() override { return 0; }

  std::vector<sc_host> list_hosts() { return {}; }

  StatInfo get_device_stats(const sc_id& sid) const override {
    StatInfo stats{};
    stats.device_id = sid.get_sc_id();
    stats.status = "active";
    stats.total_memory_MB = 2048;
    stats.available_memory_MB = 1024;
    stats.used_memory_MB = 1024;
    stats.total_bandwidth_MBps = 64000;
    stats.used_bandwidth_Bps = 0;
    stats.rw_errors = 0;
    stats.latency_us = 0;
    return stats;
  }
};

class DeviceManagerTest : public ::testing::Test {
 protected:
  DeviceManager mgr;
  DummyAdapter adapter;

  void SetUp() override {
    mgr.registerAdapter("dummy", &adapter);
    adapter.discover_devices(mgr);
  }

  void TearDown() override {
    mgr.unregisterAdapter("dummy");
    mgr.unregister_device(&adapter);
  }
};

TEST_F(DeviceManagerTest, RegisterAndRetrieveAdapter) {
  EXPECT_NE(mgr.getAdapter("dummy"), nullptr);
}

TEST_F(DeviceManagerTest, ListDevicesReturnsDiscoveredDevice) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  EXPECT_EQ(devices[0].d_get_dev_name(), "TestDevice");
}

TEST_F(DeviceManagerTest, GetDeviceInfoReturnsCorrectDetails) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  // Register device ID with manager for lookup
  const sc_device& device = devices[0];
  mgr.register_device(device.d_get_id(), &adapter);
  uint64_t d_id = device.d_get_id().get_sc_id();
  auto info = mgr.get_device_info(d_id);
  // ASSERT_TRUE(info.has_value());
  EXPECT_EQ(info.static_info.manufacturer, "Samsung");
}

TEST_F(DeviceManagerTest, ListDevicesByIdReturnsOnlyMatching) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  // Register device ID
  const sc_device& device = devices[0];
  mgr.register_device(device.d_get_id(), &adapter);
  std::unordered_set<uint64_t> ids = {device.d_get_id().get_sc_id()};
  auto filtered = mgr.list_devices(ids);
  ASSERT_EQ(filtered.size(), 1);
  EXPECT_EQ(filtered[0].d_get_dev_name(), "TestDevice");
}

TEST_F(DeviceManagerTest, UnregisterDeviceRemovesMappings) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  mgr.unregister_device(&adapter);
  auto d_id = devices[0].d_get_id().get_sc_id();
  EXPECT_THROW(mgr.get_device_info(d_id), std::runtime_error);
}

TEST_F(DeviceManagerTest, UnregisterNonexistentAdapterIsSafe) {
  mgr.unregisterAdapter("nonexistent");
}

TEST_F(DeviceManagerTest, GetAdapterReturnsCorrectInstance) {
  auto* found = mgr.getAdapter("dummy");
  ASSERT_NE(found, nullptr);
  EXPECT_EQ(found, &adapter);
}

TEST(DeviceManagerEmptyTest, DiscoverDevicesSkipsNullAdapters) {
  DeviceManager mgr_local;
  // Inject null adapter
  mgr_local.registerAdapter("null_adapter", nullptr);
  mgr_local.discover_devices();
}

TEST_F(DeviceManagerTest, GetAdapterReturnsNullIfNotFound) {
  auto* result = mgr.getAdapter("nonexistent_adapter");
  EXPECT_EQ(result, nullptr);
}

TEST_F(DeviceManagerTest, GetDIdMapReflectsRegisteredDevice) {
  auto d_id_map = mgr.get_d_id_map();
  EXPECT_EQ(d_id_map.size(), 1);
  uint64_t expected_id = 123456;
  EXPECT_EQ(d_id_map.count(expected_id), 1);
}

TEST_F(DeviceManagerTest, ListDevicesSkipsNullAdapter) {
  mgr.registerAdapter("null_adapter", nullptr);  // simulate null
  auto devices = mgr.list_devices();
  EXPECT_FALSE(devices.empty());
  EXPECT_EQ(devices.size(), 1);
}

TEST_F(DeviceManagerTest, ListDevicesHandlesExceptionInDeviceRetrieval) {
  ThrowingAdapter bad_adapter;
  mgr.registerAdapter("thrower", &bad_adapter);
  bad_adapter.discover_devices(mgr);
  std::unordered_set<uint64_t> ids = {1234567};
  auto result = mgr.list_devices(ids);
  EXPECT_TRUE(result.empty());
  mgr.unregisterAdapter("thrower");
  mgr.unregister_device(&bad_adapter);
}

TEST_F(DeviceManagerTest, ListDevicesHandlesAdapterException) {
  DeviceManager mgr;
  ThrowingAdapter bad_adapter;
  mgr.registerAdapter("thrower", &bad_adapter);
  bad_adapter.discover_devices(mgr);
  std::vector<sc_device> result = mgr.list_devices();
  EXPECT_TRUE(result.empty());
  mgr.unregisterAdapter("thrower");
  mgr.unregister_device(&bad_adapter);
}

TEST_F(DeviceManagerTest, ListDevicesHandlesMissingAdapter) {
  // ID that won't be registered
  sc_id fake_id(999999);
  // simulate missing adapter
  mgr.register_device(fake_id, nullptr);
  std::unordered_set<uint64_t> ids = {fake_id.get_sc_id()};
  auto result = mgr.list_devices(ids);
  EXPECT_TRUE(result.empty());
}

TEST_F(DeviceManagerTest, ListDevicesFilteredCompletesSuccessfully) {
  auto devices = mgr.list_devices();  // get valid id
  ASSERT_FALSE(devices.empty());
  uint64_t id = devices[0].d_get_id().get_sc_id();
  std::unordered_set<uint64_t> ids = {id};
  auto result = mgr.list_devices(ids);
  EXPECT_FALSE(result.empty());
  EXPECT_EQ(result[0].d_get_dev_name(), "TestDevice");
}

TEST_F(DeviceManagerTest, GetDeviceInfoReturnsExpected) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  uint64_t id = devices[0].d_get_id().get_sc_id();
  auto result = mgr.get_device_info(id);
  // ASSERT_TRUE(result.has_value());
  EXPECT_EQ(result.status, "active");
  EXPECT_EQ(result.available_capacity_MB, 1024);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_DeviceIdNotFound) {
  EXPECT_THROW(mgr.get_device_info(56), std::runtime_error);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_ScIdNotMapped) {
  // Remove adapter to create missing mapping
  mgr.unregister_device(&adapter);
  EXPECT_THROW(mgr.get_device_info(56), std::runtime_error);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_NoAdapterMapped) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  sc_id sid = devices[0].d_get_id();
  uint64_t d_id = sid.get_sc_id();
  // bypass const accessor by casting to non-const to erase adapter entry
  auto& adapter_map =
      const_cast<std::unordered_map<sc_id, CXLDeviceAdapter*, hash_sc_id>&>(
          mgr.get_sc_id_adapter_map());
  adapter_map.erase(sid);
  EXPECT_THROW(mgr.get_device_info(d_id), std::runtime_error);
}

TEST_F(DeviceManagerTest, GetDeviceInfo_AdapterThrowsException) {
  adapter.simulate_throw = true;
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  uint64_t d_id = devices[0].d_get_id().get_sc_id();
  EXPECT_THROW(mgr.get_device_info(d_id), std::runtime_error);
}

TEST_F(DeviceManagerTest, DiscoverDevicesHandlesStdException) {
  ThrowingAdapter adapter;
  adapter.throw_mode = ThrowingAdapter::Mode::THROW_STD_EXCEPTION;
  mgr.registerAdapter("thrower", &adapter);
  EXPECT_NO_THROW(mgr.discover_devices());
}

TEST_F(DeviceManagerTest, DiscoverDevicesHandlesUnknownException) {
  ThrowingAdapter adapter;
  adapter.throw_mode = ThrowingAdapter::Mode::THROW_UNKNOWN_EXCEPTION;
  mgr.registerAdapter("thrower", &adapter);
  EXPECT_NO_THROW(mgr.discover_devices());
}

TEST_F(DeviceManagerTest, DiscoverDevicesSkipsNullAdapter) {
  mgr.registerAdapter("null_adapter", nullptr);
  mgr.discover_devices();
  mgr.unregisterAdapter("null_adapter");
  SUCCEED();
}

TEST_F(DeviceManagerTest, ListDevicesReturnsFromAllAdapters) {
  auto result = mgr.list_devices();
  ASSERT_FALSE(result.empty());
}

TEST_F(DeviceManagerTest, ListDevicesFilteredReturnsExpectedDevice) {
  auto devices = mgr.list_devices();
  ASSERT_FALSE(devices.empty());
  uint64_t id = devices[0].d_get_id().get_sc_id();
  std::unordered_set<uint64_t> d_ids = {id};
  auto filtered = mgr.list_devices(d_ids);
  ASSERT_EQ(filtered.size(), 1);
  EXPECT_EQ(filtered[0].d_get_dev_name(), "TestDevice");
}

TEST_F(DeviceManagerTest, GetDeviceStatsAdapterMissing) {
  DeviceManager mgr;
  EXPECT_THROW(
      {
        try {
          mgr.get_device_stats(99999);
        } catch (const std::runtime_error& e) {
          EXPECT_STREQ(e.what(), "No adapter found for device ID: 99999");
          throw;
        }
      },
      std::runtime_error);
}

TEST_F(DeviceManagerTest, GetDeviceStatsCorrectInfo) {
  StatInfo stats = mgr.get_device_stats(123456);
  EXPECT_EQ(stats.device_id, 123456);
  EXPECT_EQ(stats.total_memory_MB, 2048);
  EXPECT_EQ(stats.available_memory_MB, 1024);
  EXPECT_EQ(stats.status, "active");
}

TEST_F(DeviceManagerTest, MemoryOperationsDefaultToNotSupported) {
  EXPECT_EQ(mgr.attach_memory(123456, AttachParams{"numa"}), -ENOTSUP);
  EXPECT_EQ(mgr.detach_memory(123456), -ENOTSUP);
  EXPECT_EQ(mgr.pool_operation("dummy", PoolOp::CREATE, PoolOpParams{}),
            -ENOTSUP);
}

TEST_F(DeviceManagerTest, MemoryOperationsRejectUnknownDevice) {
  EXPECT_EQ(mgr.attach_memory(99999, AttachParams{"numa"}), -ENODEV);
  EXPECT_EQ(mgr.detach_memory(99999), -ENODEV);
  EXPECT_EQ(mgr.pool_operation("missing", PoolOp::CREATE, PoolOpParams{}),
            -ENODEV);
}
