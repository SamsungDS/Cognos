#include <gtest/gtest.h>

#include "sc_id.h"

// Test fixture for sc_id
class ScIdTest : public ::testing::Test {
 protected:
  sc_id scid;

  uint64_t customScIdValue = 456;
  sc_id customId{customScIdValue};

  void SetUp() override { scid.set_sc_id(customScIdValue); }
};

TEST_F(ScIdTest, ParameterizedConstructor) {
  EXPECT_EQ(scid.get_sc_id(), customScIdValue);
}

/*
 * @brief Test with a large value (UINT64_MAX) to ensure that the constructor
 * handles the maximum possible input correctly.
 */
TEST_F(ScIdTest, ParameterizedConstructor_LargeValue) {
  uint64_t large_value = UINT64_MAX;
  sc_id my_id(large_value);
  EXPECT_EQ(my_id.get_sc_id(), large_value);
}

TEST_F(ScIdTest, GetScId) { EXPECT_EQ(scid.get_sc_id(), customScIdValue); }

TEST_F(ScIdTest, SetScId) {
  uint64_t initial_value = 123;
  uint64_t new_value = 456;
  sc_id my_id(initial_value);
  my_id.set_sc_id(new_value);
  EXPECT_EQ(my_id.get_sc_id(), new_value);
}

/*
 * @brief Test setting a new value that is negative
 * */
TEST_F(ScIdTest, SetScId_NegativeValue) {
  uint64_t initial_value = 123;
  int64_t new_negative_value = -456;
  sc_id my_id(initial_value);
  my_id.set_sc_id(new_negative_value);
  EXPECT_EQ(my_id.get_sc_id(), static_cast<uint64_t>(new_negative_value));
}

/*
 * @brief use the custom hash function, and verify
 * that it produces the expected hash value
 */
TEST_F(ScIdTest, HashScId) {
  uint64_t value1 = 123;
  uint64_t value2 = 123;
  sc_id id1(value1);
  sc_id id2(value2);
  hash_sc_id hasher;

  // Check if hash values match
  EXPECT_EQ(hasher(id1), hasher(id2));
}

/*
 * @brief Test two different sc_id instances with the same
 * s_id value but different memory addresses
 */
TEST_F(ScIdTest, HashScId_DistinctObjectsSameValue) {
  uint64_t value = 123;
  sc_id id1(value);
  sc_id id2(value);
  hash_sc_id hasher;

  // Check if hash values match
  EXPECT_EQ(hasher(id1), hasher(id2));
}
