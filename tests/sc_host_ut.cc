#include <gtest/gtest.h>

#include "sc_host.h"

// Test fixture for sc_host
class ScHostTest : public ::testing::Test {
 protected:
  sc_host myHost;

  uint64_t customScIdValue = 456;
  sc_host customHost{customScIdValue};
  void SetUp() override {
    myHost.set_host_name("defaultHostName");
    myHost.set_host_port(8080);
  }
};

TEST_F(ScHostTest, ParameterizedConstructor) {
  EXPECT_EQ(customHost.get_id(), customScIdValue);
}

TEST_F(ScHostTest, GetCompositeObj) {
  sc_id compositeId = customHost.get_composite_obj();
  EXPECT_EQ(compositeId.get_sc_id(), customScIdValue);
}

// Negative test case: Empty hostname
TEST_F(ScHostTest, EmptyHostNameTest) {
  try {
    myHost.set_host_name("");  // Empty hostname
    FAIL() << "Expected invalid_argument exception for empty hostname";
  } catch (const std::invalid_argument& e) {
    EXPECT_TRUE(std::string(e.what()).find("Invalid hostname") !=
                std::string::npos);
  }
}

// Test case: Valid host name and port
TEST_F(ScHostTest, ValidHostNameAndPort) {
  EXPECT_EQ(myHost.get_host_name(), "defaultHostName");
  EXPECT_EQ(myHost.get_host_port(), 8080);
}

// Test case: Valid sc_id value
TEST_F(ScHostTest, ValidScId) {
  EXPECT_EQ(customHost.get_id(), customScIdValue);
}

TEST_F(ScHostTest, ValidDeviceName) {
  string validName = "ValidName";

  ASSERT_NO_THROW(myHost.set_host_name(validName));

  EXPECT_EQ(validName, myHost.get_host_name());
}

TEST_F(ScHostTest, InvalidHostNameException) {
  string invalidName = "Invalid Name!";

  try {
    myHost.set_host_name(invalidName);
  } catch (const std::invalid_argument& e) {
    const std::string expectedMessage = "Invalid hostname: " + invalidName;
    EXPECT_EQ(e.what(), expectedMessage)
        << "Actual exception message: " << e.what();
  }
}

// Test case: Invalid port value
TEST_F(ScHostTest, InvalidPortValue) {
  EXPECT_THROW(myHost.set_host_port(-1), std::invalid_argument);
  EXPECT_THROW(myHost.set_host_port(70000), std::invalid_argument);
}

// Edge Test case: Zero capacity
TEST_F(ScHostTest, ZeroCapacity) {
  myHost.set_capacity(0);
  EXPECT_EQ(myHost.get_capacity(), 0);
}

// Test case: Valid capacity
TEST_F(ScHostTest, ValidCapacity) {
  myHost.set_capacity(1024);
  EXPECT_EQ(myHost.get_capacity(), 1024);
}

// Test case: Over capacity
TEST_F(ScHostTest, OverCapacity) {
  // Attempt to set an over capacity value
  EXPECT_THROW(myHost.set_capacity(1ull << 60), std::invalid_argument);
}

// Test case: Adding target ports
TEST_F(ScHostTest, TargetPorts) {
  myHost.set_target_ports(80);
  myHost.set_target_ports(443);

  const auto& targetPorts = myHost.get_target_ports();
  EXPECT_EQ(targetPorts.size(), 2);
  EXPECT_EQ(targetPorts.front(), 80);
  EXPECT_EQ(targetPorts.back(), 443);
}
