#include <gtest/gtest.h>

#include "sc_mld.h"

using namespace std;

class ScMldTest : public ::testing::Test {
 protected:
  sc_mld defaultMld;
  sc_mld paramMld;

  void SetUp() override { paramMld = sc_mld(123, "TestDevice", 1024, 8080); }
};

TEST_F(ScMldTest, DefaultConstructor) {
  // Test default constructor
  EXPECT_EQ(defaultMld.d_get_dev_name(), "");
  EXPECT_EQ(defaultMld.d_get_capacity(), 0);
  EXPECT_EQ(defaultMld.d_get_port(), 0);
}

TEST_F(ScMldTest, ParameterizedConstructor) {
  // Test parameterized constructor
  EXPECT_EQ(paramMld.d_get_dev_name(), "TestDevice");
  EXPECT_EQ(paramMld.d_get_capacity(), 1024);
  EXPECT_EQ(paramMld.d_get_port(), 8080);
}

TEST_F(ScMldTest, SettersAndGetters) {
  // Test setters and getters
  defaultMld.d_set_dev_name("NewDevice");
  defaultMld.d_set_capacity(2048);
  defaultMld.d_set_port(9090);

  EXPECT_EQ(defaultMld.d_get_dev_name(), "NewDevice");
  EXPECT_EQ(defaultMld.d_get_capacity(), 2048);
  EXPECT_EQ(defaultMld.d_get_port(), 9090);
}

TEST_F(ScMldTest, OverCapacity) {
  // Test over capacity
  EXPECT_THROW(
      paramMld.d_set_capacity(6000ull * 1024ull * 1024ull * 1024ull + 1),
      std::invalid_argument);
}

TEST_F(ScMldTest, InvalidDeviceName) {
  // Test invalid device name
  EXPECT_THROW(paramMld.d_set_dev_name("Invalid$Name"), std::invalid_argument);
}

TEST_F(ScMldTest, InvalidPortRange) {
  // Test invalid port range
  EXPECT_THROW(paramMld.d_set_port(70000), std::invalid_argument);
}

TEST_F(ScMldTest, UnderCapacity) {
  // Test under capacity
  EXPECT_THROW(paramMld.d_set_capacity(-1), std::invalid_argument);
}

TEST_F(ScMldTest, EmptyDeviceName) {
  // Test empty device name
  EXPECT_THROW(paramMld.d_set_dev_name(""), std::invalid_argument);
}

TEST_F(ScMldTest, GetCompositeObj) {
  // Test d_get_id method
  sc_id compositeId = paramMld.d_get_id();
  EXPECT_EQ(compositeId.get_sc_id(), 123);
}

TEST_F(ScMldTest, ListMldDevices_EmptyList) {
  sc_mld mld;
  auto devices = mld.list_mld_devices();

  EXPECT_TRUE(devices.empty());
}

TEST_F(ScMldTest, ListMldDevices_NonEmptyList) {
  sc_mld mld;
  // Create an LD (which is an empty device)
  mld.mld_id(123);
  mld.mld_id(456);

  auto devices = mld.list_mld_devices();

  // Assert: Verify that the list contains the expected number of devices
  EXPECT_EQ(devices.size(), 2);
}

TEST_F(ScMldTest, CreateLd_Success) {
  sc_mld mld;

  int result = mld.mld_id(123);

  // Assert: Verify that LD creation was successful
  EXPECT_EQ(result, 0);
}

TEST_F(ScMldTest, DeleteLd_ExistingLd) {
  // Arrange: Create an instance of sc_mld and add an LD
  sc_mld mld;
  uint64_t ldId = 898;
  mld.mld_id(ldId);  // Create an LD

  // Act: Call md_delete_ld() with the LD's ID
  int result = mld.md_delete_ld(ldId);

  // Assert: Verify that LD deletion was successful
  EXPECT_EQ(result, 0);

  // Additional assertion: Check that the LD no longer exists
  EXPECT_EQ(mld.md_delete_ld(ldId), -2);
}

TEST_F(ScMldTest, DeleteLd_NonExistentLd) {
  sc_mld mld;

  int result = mld.md_delete_ld(12345);

  // Assert: Verify that it fails due to non-existent LD
  EXPECT_EQ(result, -2);
}
