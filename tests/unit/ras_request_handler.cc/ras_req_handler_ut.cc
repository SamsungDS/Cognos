#include <gtest/gtest.h>
#include <ras_monitor.h>

#include "svk_logger.hpp"
#include "utils/logic_module_manager.hpp"

class RequestHandlerUnitTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    monitor_instance = std::make_unique<ras_monitor>();
  }
  static std::unique_ptr<ras_monitor> monitor_instance;
};

std::unique_ptr<ras_monitor> RequestHandlerUnitTest::monitor_instance;

TEST_F(RequestHandlerUnitTest, ExecFeatureCommandExternalReq) {
  ras_request req(true, nullptr);
  req.execute_feature_command();
  EXPECT_EQ(req.is_successfull, false);
  EXPECT_EQ(
      std::string(
          req.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR]),
      RAS_RESULT_CODE_FAILED_STR);
}

TEST_F(RequestHandlerUnitTest, GetDeviceIdentifierInvalidObj) {
  ras_request req(true, nullptr, false, std::nullopt, std::nullopt);
  auto result = get_device_identifier_from_request(req);
  EXPECT_EQ(result, std::nullopt);
}

TEST_F(RequestHandlerUnitTest, GetDeviceIdentifierNoCommandParams) {
  std::string input_string = R"(
    {
    "command" : "dummy_command"
    }
  )";
  ras_request req(true, nullptr, false, input_string.c_str(),
                  input_string.length());

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, true);

  auto result = get_device_identifier_from_request(req);
  EXPECT_EQ(result, std::nullopt);
}

TEST_F(RequestHandlerUnitTest, GetDeviceIdentifierNonObjectCommandParams) {
  std::string input_string = R"(
    {
    "command" : "dummy_command",
    "command_params" : "non json param"
    }
  )";
  ras_request req(true, nullptr, false, input_string.c_str(),
                  input_string.length());

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, true);

  auto result = get_device_identifier_from_request(req);
  EXPECT_EQ(result, std::nullopt);
}

TEST_F(RequestHandlerUnitTest, GetDeviceIdentifierCommandParamsWithoutDevice) {
  std::string input_string = R"(
    {
    "command" : "dummy_command",
    "command_params" : {
      "dumm_params" : "dummy_param_value1"
      }
    }
  )";
  ras_request req(true, nullptr, false, input_string.c_str(),
                  input_string.length());

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, true);

  auto result = get_device_identifier_from_request(req);
  EXPECT_EQ(result, std::nullopt);
}

TEST_F(RequestHandlerUnitTest, GetDeviceIdentifierSuccess) {
  std::string input_string = R"(
    {
    "command" : "dummy_command",
    "command_params" : {
      "device" : "dev123"
      }
    }
  )";
  ras_request req(true, nullptr, false, input_string.c_str(),
                  input_string.length());

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, true);

  auto result = get_device_identifier_from_request(req);
  EXPECT_EQ(*result, std::string("dev123"));
}

TEST_F(RequestHandlerUnitTest, GetCommandStringInvalidCommandObj) {
  std::string input_string = R"(
    {
    "command1" : "dummy_command",
    "command_params" : {
      "device" : "dev123"
      }
    }
  )";
  ras_request req(true, nullptr, false, input_string.c_str(),
                  input_string.length());

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, false);
}

TEST_F(RequestHandlerUnitTest, ParseJsonFailNullInputStr) {
  ras_request req(true, nullptr, false);

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, false);
}

TEST_F(RequestHandlerUnitTest, ParseJsonInvalidInputLen) {
  std::string input_string = R"(
    {
    "command1" : "dummy_command",
    "command_params" : {
      "device" : "dev123"
      }
    }
  )";
  ras_request req(true, nullptr, false, input_string.c_str(), 2);

  auto parsed = req.parse_input_command_to_json();
  EXPECT_EQ(parsed, false);
}

TEST_F(RequestHandlerUnitTest, MarkRequestInvalidParams) {
  ras_request req(true, nullptr);
  req.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_PARAMS_INVALID);
  EXPECT_EQ(req.is_successfull, false);
  EXPECT_EQ(
      std::string(
          req.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR]),
      RAS_RESULT_CODE_FAILED_STR);
  EXPECT_EQ(std::string(req.command_obj[RAS_COMMAND_RESULT_STR]
                                       [RAS_COMMAND_STATUS_MESSAGE_STR]),
            "Invalid command parameters");
}

TEST_F(RequestHandlerUnitTest, MarkRequestInvalidCommand) {
  ras_request req(true, nullptr);
  req.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_INVALID);
  EXPECT_EQ(req.is_successfull, false);
  EXPECT_EQ(
      std::string(
          req.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR]),
      RAS_RESULT_CODE_FAILED_STR);
  EXPECT_EQ(std::string(req.command_obj[RAS_COMMAND_RESULT_STR]
                                       [RAS_COMMAND_STATUS_MESSAGE_STR]),
            "Invalid command");
}

TEST_F(RequestHandlerUnitTest, MarkRequestUnsupported) {
  ras_request req(true, nullptr);
  req.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_UNSUPPORTED);
  EXPECT_EQ(req.is_successfull, false);
  EXPECT_EQ(
      std::string(
          req.command_obj[RAS_COMMAND_RESULT_STR][RAS_COMMAND_STATUS_CODE_STR]),
      RAS_RESULT_CODE_FAILED_STR);

  EXPECT_EQ(std::string(req.command_obj[RAS_COMMAND_RESULT_STR]
                                       [RAS_COMMAND_STATUS_MESSAGE_STR]),
            "Command Unsupported");
}
