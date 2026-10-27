#include <gtest/gtest.h>

#include "sc_sld.h"

using namespace std;

class ScSldTest : public ::testing::Test {
 protected:
  sc_sld defaultSld;
  sc_sld paramSld;

  void SetUp() override { paramSld = sc_sld(123, "TestDevice", 1024, 8080); }
};

TEST_F(ScSldTest, DefaultConstructor) {
  // Test default constructor
  EXPECT_EQ(defaultSld.d_get_dev_name(), "");
  EXPECT_EQ(defaultSld.d_get_capacity(), 0);
  EXPECT_EQ(defaultSld.d_get_port(), 0);
}

TEST_F(ScSldTest, ParameterizedConstructor) {
  // Test parameterized constructor
  EXPECT_EQ(paramSld.d_get_dev_name(), "TestDevice");
  EXPECT_EQ(paramSld.d_get_capacity(), 1024);
  EXPECT_EQ(paramSld.d_get_port(), 8080);
}

TEST_F(ScSldTest, SettersAndGetters) {
  // Test setters and getters
  defaultSld.d_set_dev_name("NewDevice");
  defaultSld.d_set_capacity(2048);
  defaultSld.d_set_port(9090);

  EXPECT_EQ(defaultSld.d_get_dev_name(), "NewDevice");
  EXPECT_EQ(defaultSld.d_get_capacity(), 2048);
  EXPECT_EQ(defaultSld.d_get_port(), 9090);
}

TEST_F(ScSldTest, OverCapacity) {
  // Test over capacity
  EXPECT_THROW(
      paramSld.d_set_capacity(6000ull * 1024ull * 1024ull * 1024ull + 1),
      std::invalid_argument);
}

TEST_F(ScSldTest, InvalidDeviceName) {
  // Test invalid device name
  EXPECT_THROW(paramSld.d_set_dev_name("Invalid$Name"), std::invalid_argument);
}

TEST_F(ScSldTest, InvalidPortRange) {
  // Test invalid port range
  EXPECT_THROW(paramSld.d_set_port(70000), std::invalid_argument);
}

TEST_F(ScSldTest, UnderCapacity) {
  // Test under capacity
  EXPECT_THROW(paramSld.d_set_capacity(-1), std::invalid_argument);
}

TEST_F(ScSldTest, EmptyDeviceName) {
  // Test empty device name
  EXPECT_THROW(paramSld.d_set_dev_name(""), std::invalid_argument);
}

TEST_F(ScSldTest, GetCompositeObj) {
  // Test d_get_id method
  sc_id compositeId = paramSld.d_get_id();
  EXPECT_EQ(compositeId.get_sc_id(), 123);
}

TEST_F(ScSldTest, ListSldDevices_NonEmptyList) {
  sc_sld sld;
  // Create an LD (which is an empty device)
  sld.sld_id(123);
  sld.sld_id(456);

  auto devices = sld.list_sld_devices();

  // Assert: Verify that the list contains the expected number of devices
  EXPECT_EQ(devices.size(), 2);
}

TEST_F(ScSldTest, CreateLd_Success) {
  sc_sld sld;

  int result = sld.sld_id(123);

  // Assert: Verify that LD creation was successful
  EXPECT_EQ(result, 0);
}

TEST_F(ScSldTest, DeleteLd_ExistingLd) {
  // Arrange: Create an instance of sc_sld and add an LD
  sc_sld sld;
  uint64_t ldId = 898;
  sld.sld_id(ldId);

  // Act: Call sd_delete_ld() with the LD's ID
  int result = sld.sd_delete_ld(ldId);

  // Assert: Verify that LD deletion was successful
  EXPECT_EQ(result, 0);

  // Additional assertion: Check that the LD no longer exists
  EXPECT_EQ(sld.sd_delete_ld(ldId), -2);
}

TEST_F(ScSldTest, DeleteLd_NonExistentLd) {
  sc_sld sld;

  int result = sld.sd_delete_ld(12345);

  // Assert: Verify that it fails due to non-existent LD
  EXPECT_EQ(result, -2);
}
