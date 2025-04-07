#include <gtest/gtest.h>

#include "sc_test_utils.h"
#include "sc_utility.h"

class ScUtilityTest : public ::testing::Test {};

TEST_F(ScUtilityTest, JsonArrToStr_ValidJsonObject) {
  std::string input = R"({"id":1,"name":"Device"})";
  std::string output;
  int status = json_arr_to_str(input, output);
  EXPECT_EQ(status, 0);
  EXPECT_EQ(output, input);
}

TEST_F(ScUtilityTest, JsonArrToStr_ValidJsonArray) {
  std::string input = R"([{"id":1}, {"id":2}])";
  std::string output;
  int status = json_arr_to_str(input, output);
  EXPECT_EQ(status, 0);
  // Flattened w/o brackets
  EXPECT_EQ(output, R"({"id":1},{"id":2})");
}

TEST_F(ScUtilityTest, JsonArrToStr_EmptyJsonArray) {
  std::string input = R"([])";
  std::string output;
  int status = json_arr_to_str(input, output);
  EXPECT_EQ(status, 0);
  EXPECT_TRUE(output.empty());
}

TEST_F(ScUtilityTest, JsonArrToStr_MalformedJson) {
  // Missing closing brace
  std::string input = R"({"id": 1, "name": "Device")";
  std::string output;
  int status = json_arr_to_str(input, output);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(output.empty());
}

TEST_F(ScUtilityTest, JsonArrToStr_InvalidType) {
  // Not an object or array
  std::string input = R"("InvalidString")";
  std::string output;
  int status = json_arr_to_str(input, output);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(output.empty());
}

TEST_F(ScUtilityTest, StrToInt_Valid) {
  uint64_t id;
  std::string error_response;
  std::string number = "11107";
  bool result = str_to_int(number, id, error_response);
  EXPECT_TRUE(result);
}

TEST_F(ScUtilityTest, StrToInt_OutOfRange) {
  uint64_t id;
  std::string error_response;
  // Too large for uint64_t
  std::string large_number = "999999999999999999999999999999999";
  bool result = str_to_int(large_number, id, error_response);
  EXPECT_FALSE(result);  // Expect failure
  std::cout << error_response << std::endl;
  EXPECT_EQ(get_json_value(error_response, "rc"), "ERANGE");
  EXPECT_EQ(get_json_value(error_response, "message"), "id value out of range");
}

TEST_F(ScUtilityTest, StrToInt_InvalidArgs) {
  uint64_t id;
  std::string error_response;
  std::string large_number = "samsung";
  bool result = str_to_int(large_number, id, error_response);
  EXPECT_FALSE(result);  // Expect failure
  EXPECT_EQ(get_json_value(error_response, "rc"), "EINVAL");
}

TEST_F(ScUtilityTest, PosixErrToJson_Coverage) {
  EXPECT_EQ(get_json_value(posix_err_to_json(EIO, ""), "message"),
            "Internal I/O error occurred");
  EXPECT_EQ(get_json_value(posix_err_to_json(EPERM, ""), "message"),
            "Operation not permitted");
  EXPECT_EQ(get_json_value(posix_err_to_json(EBUSY, ""), "message"),
            "Resource is busy, try again later");
  EXPECT_EQ(get_json_value(posix_err_to_json(ENOMEM, ""), "message"),
            "Memory allocation failure");
  EXPECT_EQ(get_json_value(posix_err_to_json(EINVAL, ""), "message"),
            "Invalid request parameters");
  EXPECT_EQ(get_json_value(posix_err_to_json(ENOENT, ""), "message"),
            "Requested resource not found");
  EXPECT_EQ(get_json_value(posix_err_to_json(EEXIST, ""), "message"),
            "Resource already exists");
  EXPECT_EQ(get_json_value(posix_err_to_json(ENOEXEC, ""), "message"),
            "Executable format error (plugin load failed)");
  EXPECT_EQ(get_json_value(posix_err_to_json(EPROTO, ""), "message"),
            "Plugin registration error");
  EXPECT_EQ(get_json_value(posix_err_to_json(EFAULT, ""), "message"),
            "System fault occurred");
  EXPECT_EQ(get_json_value(posix_err_to_json(ETIMEDOUT, ""), "message"),
            "Operation timed out");
  EXPECT_EQ(get_json_value(posix_err_to_json(ECONNREFUSED, ""), "message"),
            "Connection refused");
  // Testing the default case (passing an unknown error code)
  EXPECT_EQ(get_json_value(posix_err_to_json(9999, ""), "message"),
            "Unknown error occurred");
}

TEST_F(ScUtilityTest, JsonArrToStr_InvalidJson) {
  std::string input = "{invalid_json";
  std::string output;
  int status = json_arr_to_str(input, output);
  EXPECT_EQ(status, -EINVAL);
  EXPECT_TRUE(output.empty());
}

/*TEST(UtilityTest, JsonArrToStr_NotArrayOrObject) {
    std::string input = R"("just_a_string")";  // JSON is a string, not an array
or object std::string output; int status = json_arr_to_str(input, output);
    EXPECT_EQ(status, -EINVAL);
    EXPECT_TRUE(output.empty());
}*/
