#include <gtest/gtest.h>

#include "sc_device.h"

using namespace std;

class ScDeviceTest : public ::testing::Test {
 protected:
  sc_device defaultDevice;
  sc_device paramDevice;

  void SetUp() override {
    paramDevice = sc_device(123, "TestDevice", 1024, 8080);
  }
};

TEST_F(ScDeviceTest, DefaultConstructor) {
  // Test default constructor
  EXPECT_EQ(defaultDevice.d_get_dev_name(), "");
  EXPECT_EQ(defaultDevice.d_get_capacity(), 0);
  EXPECT_EQ(defaultDevice.d_get_port(), 0);
}

TEST_F(ScDeviceTest, ParameterizedConstructor) {
  // Test parameterized constructor
  EXPECT_EQ(paramDevice.d_get_dev_name(), "TestDevice");
  EXPECT_EQ(paramDevice.d_get_capacity(), 1024);
  EXPECT_EQ(paramDevice.d_get_port(), 8080);
}

TEST_F(ScDeviceTest, SettersAndGetters) {
  // Test setters and getters
  defaultDevice.d_set_dev_name("NewDevice");
  defaultDevice.d_set_capacity(2048);
  defaultDevice.d_set_port(9090);

  EXPECT_EQ(defaultDevice.d_get_dev_name(), "NewDevice");
  EXPECT_EQ(defaultDevice.d_get_capacity(), 2048);
  EXPECT_EQ(defaultDevice.d_get_port(), 9090);
}

TEST_F(ScDeviceTest, OverCapacity) {
  // Test over capacity
  EXPECT_THROW(
      paramDevice.d_set_capacity(6000ull * 1024ull * 1024ull * 1024ull + 1),
      std::invalid_argument);
}

TEST_F(ScDeviceTest, InvalidDeviceName) {
  // Test invalid device name
  EXPECT_THROW(paramDevice.d_set_dev_name("Invalid$Name"),
               std::invalid_argument);
}

TEST_F(ScDeviceTest, InvalidPortRange) {
  // Test invalid port range
  EXPECT_THROW(paramDevice.d_set_port(70000), std::invalid_argument);
}

TEST_F(ScDeviceTest, UnderCapacity) {
  // Test under capacity
  EXPECT_THROW(paramDevice.d_set_capacity(-1), std::invalid_argument);
}

TEST_F(ScDeviceTest, EmptyDeviceName) {
  // Test empty device name
  EXPECT_THROW(paramDevice.d_set_dev_name(""), std::invalid_argument);
}

TEST_F(ScDeviceTest, GetCompositeObj) {
  // Test d_get_id method
  sc_id compositeId = paramDevice.d_get_id();
  EXPECT_EQ(compositeId.get_sc_id(), 123);
}

TEST_F(ScDeviceTest, SetDevName_ValidName) {
  string validName = "ValidName";
  ASSERT_NO_THROW(paramDevice.d_set_dev_name(validName));
  EXPECT_EQ(validName, paramDevice.d_get_dev_name());
}

TEST_F(ScDeviceTest, SetDevName_InvalidName) {
  string invalidName = "Invalid Name!";
  EXPECT_THROW(paramDevice.d_set_dev_name(invalidName), std::invalid_argument);
}

TEST_F(ScDeviceTest, InvalidDeviceNameException) {
  // Contains spaces and special characters
  string invalidName = "Invalid Name!";
  try {
    paramDevice.d_set_dev_name(invalidName);
    FAIL() << "Expected std::invalid_argument exception, but no exception was "
              "thrown.";
  } catch (const std::invalid_argument& e) {
    EXPECT_TRUE(std::string(e.what()).find("Invalid device name: ") !=
                std::string::npos);
  }
}

TEST_F(ScDeviceTest, SetPortValidValue) {
  uint32_t validPort = 8080;
  ASSERT_NO_THROW(paramDevice.d_set_port(validPort));
  EXPECT_EQ(paramDevice.d_get_port(), validPort);
}

TEST_F(ScDeviceTest, SetPortInvalidValue) {
  uint32_t invalidPort = 70000;
  EXPECT_THROW(paramDevice.d_set_port(invalidPort), std::invalid_argument);
}

TEST_F(ScDeviceTest, SetCapacityValidValue) {
  // valid capacity (1 GB)
  uint64_t validCapacity = 1024ull * 1024ull * 1024ull;
  ASSERT_NO_THROW(paramDevice.d_set_capacity(validCapacity));
  EXPECT_EQ(paramDevice.d_get_capacity(), validCapacity);
}

TEST_F(ScDeviceTest, SetCapacityInvalidValue) {
  // invalid capacity (70 GB)
  uint64_t invalidCapacity = 70000ull * 1024ull * 1024ull;

  try {
    paramDevice.d_set_capacity(invalidCapacity);
  } catch (const std::invalid_argument& e) {
    EXPECT_TRUE(std::string(e.what()).find("Invalid capacity value: ") !=
                std::string::npos);
  } catch (...) {
    FAIL() << "Unexpected exception type.";
  }
}

TEST_F(ScDeviceTest, set_get_manufacturer) {
  paramDevice.d_set_manufacturer("Samsung");
  EXPECT_EQ(paramDevice.d_get_manufacturer(), "Samsung");
}

TEST_F(ScDeviceTest, set_get_serial_number) {
  paramDevice.d_set_serial_number(123);
  EXPECT_EQ(paramDevice.d_get_serial_number(), 123);
}

TEST_F(ScDeviceTest, set_get_fw_revision) {
  paramDevice.d_set_fw_revision("1.0.0");
  EXPECT_EQ(paramDevice.d_get_fw_revision(), "1.0.0");
}

TEST_F(ScDeviceTest, set_get_location) {
  paramDevice.d_set_location("slotA");
  EXPECT_EQ(paramDevice.d_get_location(), "slotA");
}

TEST_F(ScDeviceTest, set_get_status) {
  paramDevice.d_set_status("active");
  EXPECT_EQ(paramDevice.d_get_status(), "active");
}

TEST_F(ScDeviceTest, set_get_feature_supported) {
  paramDevice.d_set_feature_supported("SLD");
  EXPECT_EQ(paramDevice.d_get_feature_supported(), "SLD");
}

TEST_F(ScDeviceTest, set_get_device_type) {
  paramDevice.d_set_device_type("CMMB");
  EXPECT_EQ(paramDevice.d_get_device_type(), "CMMB");
}

TEST_F(ScDeviceTest, set_get_cxl_type) {
  paramDevice.d_set_cxl_type("Type1");
  EXPECT_EQ(paramDevice.d_get_cxl_type(), "Type1");
}

TEST_F(ScDeviceTest, set_get_domain_id) {
  paramDevice.d_set_domain_id(42);
  EXPECT_EQ(paramDevice.d_get_domain_id(), 42);
}

TEST_F(ScDeviceTest, set_get_domain_type) {
  paramDevice.d_set_domain_type("Fabric");
  EXPECT_EQ(paramDevice.d_get_domain_type(), "Fabric");
}

TEST_F(ScDeviceTest, set_get_connection_type) {
  paramDevice.d_set_connection_type("local");
  EXPECT_EQ(paramDevice.d_get_connection_type(), "local");
}

TEST_F(ScDeviceTest, set_get_mode_discovered) {
  paramDevice.d_set_mode_discovered("auto");
  EXPECT_EQ(paramDevice.d_get_mode_discovered(), "auto");
}

TEST_F(ScDeviceTest, set_get_protocol_version) {
  paramDevice.d_set_protocol_version("1.1");
  EXPECT_EQ(paramDevice.d_get_protocol_version(), "1.1");
}

TEST_F(ScDeviceTest, set_get_aspm_active) {
  paramDevice.d_set_aspm_active(true);
  EXPECT_EQ(paramDevice.d_get_aspm_active(), true);
}

TEST_F(ScDeviceTest, set_get_sris_active) {
  paramDevice.d_set_sris_active(false);
  EXPECT_EQ(paramDevice.d_get_sris_active(), false);
}

TEST_F(ScDeviceTest, set_get_lock_active) {
  paramDevice.d_set_lock_active(true);
  EXPECT_EQ(paramDevice.d_get_lock_active(), true);
}

TEST_F(ScDeviceTest, set_get_link_speed) {
  paramDevice.d_set_link_speed(8);
  EXPECT_EQ(paramDevice.d_get_link_speed(), 8);
}

TEST_F(ScDeviceTest, set_get_link_width) {
  paramDevice.d_set_link_width(16);
  EXPECT_EQ(paramDevice.d_get_link_width(), 16);
}

TEST_F(ScDeviceTest, set_get_port_type) {
  paramDevice.d_set_port_type("dh");
  EXPECT_EQ(paramDevice.d_get_port_type(), "dh");
}

TEST_F(ScDeviceTest, set_get_numa_attached) {
  paramDevice.d_set_numa_attached(12);
  EXPECT_EQ(paramDevice.d_get_numa_attached(), 12);
}

TEST_F(ScDeviceTest, set_get_QoSInfo) {
 QoSInfo qos{1.1, 2.2, 3.3, 4.4, 5.5, 6.6};
 paramDevice.d_set_qos_info(qos);
 const QoSInfo& retrieved = paramDevice.d_get_qos_info();
 EXPECT_DOUBLE_EQ(retrieved.avg_latency, 1.1);
 EXPECT_DOUBLE_EQ(retrieved.p99_latency, 2.2);
 EXPECT_DOUBLE_EQ(retrieved.io_per_sec, 3.3);
 EXPECT_DOUBLE_EQ(retrieved.bw_per_sec, 4.4);
 EXPECT_DOUBLE_EQ(retrieved.io_size, 5.5);
 EXPECT_DOUBLE_EQ(retrieved.qd, 6.6);
}

TEST_F(ScDeviceTest, set_get_capabilities) {
 Capabilities cap;
 cap.power_management_version = 3;
 paramDevice.d_set_capabilities(cap);
 const Capabilities& retrieved = paramDevice.d_get_capabilities();
 EXPECT_EQ(retrieved.power_management_version, 3);
}


TEST_F(ScDeviceTest, set_get_pcie_addr) {
  paramDevice.d_set_pcie_addr("0000:04:00.0");
  EXPECT_EQ(paramDevice.d_get_pcie_addr(), "0000:04:00.0");
}

TEST_F(ScDeviceTest, set_get_type) {
  paramDevice.d_set_type(device_type::MLD);
  EXPECT_EQ(paramDevice.d_get_type(), device_type::MLD);
}

TEST_F(ScDeviceTest, AvailableCapacity_Positive) {
  paramDevice.d_set_capacity(1000);
  paramDevice.d_set_used_capacity(300);
  EXPECT_EQ(paramDevice.d_get_available_capacity(), 700);
}

TEST_F(ScDeviceTest, AvailableCapacity_Zero) {
  paramDevice.d_set_capacity(500);
  paramDevice.d_set_used_capacity(600);
  EXPECT_EQ(paramDevice.d_get_available_capacity(), 0);
}

TEST_F(ScDeviceTest, ToDeviceInfo_Validation) {
  paramDevice.d_set_manufacturer("Samsung");
  paramDevice.d_set_serial_number(123456);
  paramDevice.d_set_fw_revision("1.2.3");
  paramDevice.d_set_location("slotA");
  paramDevice.d_set_status("active");
  paramDevice.d_set_feature_supported("SLD");
  paramDevice.d_set_device_type("CMMB");
  paramDevice.d_set_cxl_type("Type1");
  paramDevice.d_set_protocol_version("1.1");
  paramDevice.d_set_aspm_active(true);
  paramDevice.d_set_sris_active(false);
  paramDevice.d_set_lock_active(true);
  paramDevice.d_set_link_speed(8);
  paramDevice.d_set_link_width(16);
  paramDevice.d_set_port_type("dh");
  paramDevice.d_set_numa_attached(1);
  paramDevice.d_set_connection_type("direct");
  paramDevice.d_set_domain_type("core");
  paramDevice.d_set_mode_discovered("auto");
  paramDevice.d_set_domain_id(42);

  QoSInfo qos{1.1, 2.2, 3.3, 4.4, 5.5, 6.6};
  paramDevice.d_set_qos_info(qos);


  Capabilities caps{7};
  paramDevice.d_set_capabilities(caps);

  DevInfo info = paramDevice.to_device_info();

  EXPECT_EQ(info.manufacturer, "Samsung");
  EXPECT_EQ(info.serial_number, 123456);
  EXPECT_EQ(info.fw_revision, "1.2.3");
  EXPECT_EQ(info.location, "slotA");
  EXPECT_EQ(info.status, "active");
  EXPECT_EQ(info.feature_supported, "SLD");
  EXPECT_EQ(info.device_type, "CMMB");
  EXPECT_EQ(info.cxl_type, "Type1");
  EXPECT_EQ(info.protocol, "1.1");
  EXPECT_EQ(info.aspm_active, true);
  EXPECT_EQ(info.sris_active, false);
  EXPECT_EQ(info.lock_active, true);
  EXPECT_EQ(info.link_speed, 8u);
  EXPECT_EQ(info.link_width, 16u);
  EXPECT_EQ(info.port_type, "dh");
  EXPECT_EQ(info.numa_attached, 1u);
  EXPECT_EQ(info.connection_type, "direct");
  EXPECT_EQ(info.domain_type, "core");
  EXPECT_EQ(info.mode_discovered, "auto");
  EXPECT_EQ(info.domain_id, 42u);

  EXPECT_DOUBLE_EQ(info.advertized_qos.avg_latency, 1.1);
  EXPECT_DOUBLE_EQ(info.advertized_qos.p99_latency, 2.2);
  EXPECT_DOUBLE_EQ(info.advertized_qos.io_per_sec, 3.3);
  EXPECT_DOUBLE_EQ(info.advertized_qos.bw_per_sec, 4.4);
  EXPECT_DOUBLE_EQ(info.advertized_qos.io_size, 5.5);
  EXPECT_DOUBLE_EQ(info.advertized_qos.qd, 6.6);

  EXPECT_EQ(info.capabilities.power_management_version, 7);
}

