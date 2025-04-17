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

TEST_F(ScDeviceTest, get_info_valid) {
  sc_device dev(1001, "sample_dev", 2048, 2);

  DevStaticInfo static_info;
  static_info.id = 1001;
  static_info.location = "slot-B";
  static_info.manufacturer = "AcmeCorp";
  static_info.device_type = "CMMH";
  dev.d_set_static_info(static_info);

  DevInfo dynamic_info;
  dynamic_info.aspm_active = true;
  dynamic_info.status = "active";
  dynamic_info.available_capacity_MB = 1024;
  dev.d_set_dynamic_info(dynamic_info);

  const DevInfo& info = dev.d_get_info();

  EXPECT_EQ(info.static_info.id, 1001);
  EXPECT_EQ(info.static_info.location, "slot-B");
  EXPECT_EQ(info.static_info.manufacturer, "AcmeCorp");
  EXPECT_EQ(info.static_info.device_type, "CMMH");

  EXPECT_EQ(info.status, "active");
  EXPECT_TRUE(info.aspm_active);
  EXPECT_EQ(info.available_capacity_MB, 1024);
}
