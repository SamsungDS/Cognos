#include <gtest/gtest.h>

#include "ras_device.h"

TEST(RasDeviceTest, TestDeviceCreation) {
  auto test_dev_inst = std::make_unique<ras_device>(
      "dev123", "", true, 100, false, 0, 0, 60, "dummy", 0);
  EXPECT_EQ(test_dev_inst->get_device_name_in_adapter(), "dev123");
  EXPECT_EQ(test_dev_inst->get_device_name(), "dev123");

  test_dev_inst =
      std::make_unique<ras_device>("dev123", "", true, 100, false, 0, 0, 60,
                                   "dummy", 0, "dev123_adapter_name");
  EXPECT_EQ(test_dev_inst->get_device_name_in_adapter(), "dev123_adapter_name");
  EXPECT_EQ(test_dev_inst->get_device_name(), "dev123");
}

class RasDeviceManagerUnitTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    rdm = std::make_unique<ras_device_manager>();
    auto test_dev_inst = std::make_unique<ras_device>(
        "dev1", "", true, 100, false, 0, 0, 60, "dummy", 0);

    auto test_dev_inst1 = std::make_unique<ras_device>(
        "dev2", "", true, 100, false, 0, 0, 60, "dummy", 0);

    bool result = rdm->try_add_device("dev1", std::move(test_dev_inst));
    EXPECT_TRUE(result);
    result = rdm->try_add_device("dev2", std::move(test_dev_inst1));
  }
  static std::unique_ptr<ras_device_manager> rdm;
};

std::unique_ptr<ras_device_manager> RasDeviceManagerUnitTest::rdm;

TEST_F(RasDeviceManagerUnitTest, AddNewDevice) {
  auto test_dev_inst = std::make_unique<ras_device>(
      "dev3", "", true, 100, false, 0, 0, 60, "dummy", 0);
  bool result = rdm->try_add_device("dev3", std::move(test_dev_inst));
  EXPECT_TRUE(result);
}

TEST_F(RasDeviceManagerUnitTest, AddExistingDevice) {
  auto test_dev_inst = std::make_unique<ras_device>(
      "dev2", "", true, 100, false, 0, 0, 60, "dummy", 0);
  bool result;

  // Trying to add the device with the same name that was already added should
  // fail
  result = rdm->try_add_device("dev2", std::move(test_dev_inst));
  EXPECT_FALSE(result);
}

TEST_F(RasDeviceManagerUnitTest, GetDevice) {
  // Trying to add the device with the same name that was already added should
  // fail
  auto result = rdm->try_get_device("dev2");
  ASSERT_TRUE(result.has_value());
}

TEST_F(RasDeviceManagerUnitTest, GetNonExistingDevice) {
  // Trying to get the device with the same name that was already added should
  // fail
  auto result = rdm->try_get_device("dev4");
  ASSERT_FALSE(result.has_value());
}

TEST_F(RasDeviceManagerUnitTest, RemoveDevice) {
  bool result = rdm->try_remove_device("dev2");
  EXPECT_TRUE(result);
}

TEST_F(RasDeviceManagerUnitTest, RemoveNonExistingDevice) {
  bool result = rdm->try_remove_device("dev4");
  EXPECT_FALSE(result);
}

TEST_F(RasDeviceManagerUnitTest, AddRemoveGetRemovedDevice) {
  auto test_dev_inst = std::make_unique<ras_device>(
      "dev3", "", true, 100, false, 0, 0, 60, "dummy", 0);
  bool result = rdm->try_add_device("dev3", std::move(test_dev_inst));
  EXPECT_TRUE(result);

  result = rdm->try_remove_device("dev3");
  EXPECT_TRUE(result);

  auto removed_dev = rdm->try_get_device("dev3");
  ASSERT_FALSE(removed_dev.has_value());
}

TEST_F(RasDeviceManagerUnitTest, RemoveAndAddBackDevice) {
  auto test_dev_inst = std::make_unique<ras_device>(
      "dev2", "", true, 100, false, 0, 0, 60, "dummy", 0);
  bool result = rdm->try_remove_device("dev2");
  EXPECT_TRUE(result);

  result = rdm->try_add_device("dev2", std::move(test_dev_inst));
  EXPECT_TRUE(result);

  auto added_dev = rdm->try_get_device("dev2");
  ASSERT_TRUE(added_dev.has_value());
}

TEST_F(RasDeviceManagerUnitTest, AddMultipleDevices) {
  auto test_dev_inst1 = std::make_unique<ras_device>(
      "dev4", "", true, 100, false, 0, 0, 60, "dummy", 0);
  auto test_dev_inst2 = std::make_unique<ras_device>(
      "dev5", "", true, 100, false, 0, 0, 60, "dummy", 0);
  auto test_dev_inst3 = std::make_unique<ras_device>(
      "dev6", "", true, 100, false, 0, 0, 60, "dummy", 0);

  bool result1 = rdm->try_add_device("dev4", std::move(test_dev_inst1));
  bool result2 = rdm->try_add_device("dev5", std::move(test_dev_inst2));
  bool result3 = rdm->try_add_device("dev6", std::move(test_dev_inst3));

  EXPECT_TRUE(result1);
  EXPECT_TRUE(result2);
  EXPECT_TRUE(result3);

  auto dev4 = rdm->try_get_device("dev4");
  auto dev5 = rdm->try_get_device("dev5");
  auto dev6 = rdm->try_get_device("dev6");

  ASSERT_TRUE(dev4.has_value());
  ASSERT_TRUE(dev5.has_value());
  ASSERT_TRUE(dev6.has_value());
}

TEST_F(RasDeviceManagerUnitTest, RemoveMultipleDevices) {
  auto test_dev_inst1 = std::make_unique<ras_device>(
      "dev4", "", true, 100, false, 0, 0, 60, "dummy", 0);
  auto test_dev_inst2 = std::make_unique<ras_device>(
      "dev5", "", true, 100, false, 0, 0, 60, "dummy", 0);
  auto test_dev_inst3 = std::make_unique<ras_device>(
      "dev6", "", true, 100, false, 0, 0, 60, "dummy", 0);

  bool result1 = rdm->try_add_device("dev4", std::move(test_dev_inst1));
  bool result2 = rdm->try_add_device("dev5", std::move(test_dev_inst2));
  bool result3 = rdm->try_add_device("dev6", std::move(test_dev_inst3));

  EXPECT_TRUE(result1);
  EXPECT_TRUE(result2);
  EXPECT_TRUE(result3);

  auto dev4 = rdm->try_get_device("dev4");
  auto dev5 = rdm->try_get_device("dev5");
  auto dev6 = rdm->try_get_device("dev6");

  ASSERT_TRUE(dev4.has_value());
  ASSERT_TRUE(dev5.has_value());
  ASSERT_TRUE(dev6.has_value());

  result1 = rdm->try_remove_device("dev4");
  result2 = rdm->try_remove_device("dev5");
  result3 = rdm->try_remove_device("dev6");

  EXPECT_TRUE(result1);
  EXPECT_TRUE(result2);
  EXPECT_TRUE(result3);

  dev4 = rdm->try_get_device("dev4");
  dev5 = rdm->try_get_device("dev5");
  dev6 = rdm->try_get_device("dev6");

  ASSERT_FALSE(dev4.has_value());
  ASSERT_FALSE(dev5.has_value());
  ASSERT_FALSE(dev6.has_value());
}

TEST_F(RasDeviceManagerUnitTest, AddNullDevice) {
  bool result = rdm->try_add_device("dev7", nullptr);
  EXPECT_FALSE(result);
}

TEST_F(RasDeviceManagerUnitTest, AddDeviceWithEmptyName) {
  auto test_dev_inst = std::make_unique<ras_device>("", "", true, 100, false, 0,
                                                    0, 60, "dummy", 0);
  bool result = rdm->try_add_device("", std::move(test_dev_inst));
  EXPECT_FALSE(result);
}