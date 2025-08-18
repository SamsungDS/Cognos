#include <dirent.h>
#include <dlfcn.h>
// #include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdlib.h>
#include <sys/inotify.h>

#include <atomic>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <memory>
#include <string>
#include <thread>
#include <unordered_map>

#include "ras.hpp"
#include "ras_ut_config.h"

#define WAIT_FOR_FLUSH 2

//  Format for running code before specific test suite, in this case InitTest
class ConfigUnitTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    logger_conf.put("log_level", "TRACE");  // log_level being "ERROR" will
                                            // disable the "INFO" level logging
    logger_conf.put("log_file_name", RAS_LOG);
    logger_conf.put("log_file_count", 1);
    logger_conf.put("log_file_size", 1048576);
    logger_conf.put("sink_type", "rotating_file");

    top_conf.put_child("ras.logger", logger_conf);
    top_conf.put("ras.adapters_directory", RAS_UT_ADAPTERS_DIR);
    boost::property_tree::write_json("conf.json", top_conf);
  }

  static boost::property_tree::ptree top_conf;
  static boost::property_tree::ptree logger_conf;
};
// These variables will be global to only the ConfigTest suite
// Since order of execution is not guaranteed, we can only assume these are
// available for that test suite.
boost::property_tree::ptree ConfigUnitTest::top_conf;
boost::property_tree::ptree ConfigUnitTest::logger_conf;

TEST_F(ConfigUnitTest, SVKCLEANUP) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  EXPECT_EQ(SVK_STATUS_SUCCESS, clean_up(nullptr));
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos, logs.find("[ras] [info] ras clean_up called"));
}

TEST_F(ConfigUnitTest, SVKInit) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras init called & logger is initialized"));
  clean_up(nullptr);
}

TEST_F(ConfigUnitTest, WrongConfigFileName) {
  setenv("SVK_RAS_CONFIG", "wrong_name.json", true);
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
}

TEST_F(ConfigUnitTest, UndefinedConfig) {
  unsetenv("SVK_RAS_CONFIG");
  EXPECT_EQ(SVK_STATUS_FAIL, initialize(nullptr));
}

TEST_F(ConfigUnitTest, MissingLoggerConfig) {
  top_conf.get_child("ras").erase("logger");
  boost::property_tree::write_json("missing_logger_conf.json", top_conf);
  setenv("SVK_RAS_CONFIG", "missing_logger_conf.json", true);
  EXPECT_EQ(SVK_STATUS_SUCCESS, initialize(nullptr));
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras init called & logger is initialized"));
  clean_up(nullptr);
  top_conf.put_child("ras.logger", logger_conf);
  unlink("missing_logger_conf.json");
}

TEST_F(ConfigUnitTest, InvalidLoggerConfig) {
  logger_conf.erase("sink_type");
  logger_conf.put("sink_type", "invalid");
  top_conf.erase("ras.logger");
  top_conf.put_child("ras.logger", logger_conf);
  boost::property_tree::write_json("invalid_sink_type.json", top_conf);
  setenv("SVK_RAS_CONFIG", "invalid_sink_type.json", true);
  EXPECT_EQ(SVK_STATUS_INVALID_CONFIG, initialize(nullptr));
  clean_up(nullptr);
  logger_conf.put("log_level", "ERROR");
  top_conf.put_child("ras.logger", logger_conf);
  unlink("invalid_sink_type.json");
}

TEST_F(ConfigUnitTest, SVKGetFeatureList) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  feature_id feature = feature_id::POWER_THROTTLE;
  char *feat_names = nullptr;
  initialize(nullptr);
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_SUCCESS,
            get_supported_feature_list(&feature, feat_names));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras get_supported_feature_list called"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKLicense) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_SUCCESS, is_license_valid(nullptr));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras is_license_valid called"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInvalidInputPointer) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input *input = nullptr;
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInvalidOutputPointer) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  input.input_buffer = (uint8_t *)"dummy";  // Invalid input buffer
  input.len = 5;
  svk_output *output = nullptr;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInvalidInputBuffer) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  input.input_buffer = nullptr;  // Invalid input buffer
  input.len = 0;
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECNullOutputBuffer) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = nullptr;  // Null output buffer
  output.len = 0;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECINvalidInputLen) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length() - 1;
  svk_output output;
  output.output_buffer = nullptr;  // Null output buffer
  output.len = 0;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInvalidCommand) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "invalid_command" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECMissingCommandParams) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device"
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECNullOutputBufferRemDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = nullptr;  // Null output buffer
  output.len = 0;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECINvalidInputLenRemDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length() - 1;
  svk_output output;
  output.output_buffer = nullptr;  // Null output buffer
  output.len = 0;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInvalidCommandRemDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "invalid_command" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECMissingCommandParamsRemDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device"
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInvalidJSONInput) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "invalid json"
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 128);
  output.len = 128;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInsufficentOutputBufferLen) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 8);
  output.len = 8;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECInsufficentOutputBufferLenRemDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 8);
  output.len = 8;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECAddDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECAddNumaDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev234",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECAddNonExistentDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev1234",
        "device_numa" : 7,
        "configure_options" : {
          "error_count_threshold" : 500
        }
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECAddNonExistentDeviceWithoutNumaInRequest) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev1234",
        "configure_options" : {
          "error_count_threshold" : 500
        }
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECRemDeviceNullDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECRemNonExistingDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        },
        "test_param1" : "value1"
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_FAIL, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));
  clean_up(nullptr);
  unlink("conf.json");
}
TEST_F(ConfigUnitTest, SVKEXECAddAndRemoveDevice) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_input input;
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev1234",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        }
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  svk_output output;
  output.output_buffer = (uint8_t *)calloc(1, 512);
  output.len = 512;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_sync called."));
  EXPECT_NE(std::string::npos, logs.find("output buffer:"));

  input_str = R"(
    {
      "command_name" : "remove_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev1234",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        }
      }
    }
  )";
  input.input_buffer = (uint8_t *)input_str.c_str();
  input.len = input_str.length();
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_sync(&pass_thru, &input, &output));
  sleep(WAIT_FOR_FLUSH);
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, SVKEXECASYNC) {
  setenv("SVK_RAS_CONFIG", "conf.json", true);
  initialize(nullptr);
  svk_pass_thru_cmd pass_thru;
  pass_thru.feat_id = ZERO_ETL;
  svk_postprocess_fn *postprocess_fn = nullptr;
  EXPECT_EQ(0, svk_logger_set_flush_interval(1));
  EXPECT_EQ(SVK_STATUS_SUCCESS, execute_async(&pass_thru, postprocess_fn));
  sleep(WAIT_FOR_FLUSH);
  std::ifstream logFile(RAS_LOG);
  std::string logs((std::istreambuf_iterator<char>(logFile)),
                   (std::istreambuf_iterator<char>()));
  logFile.close();
  EXPECT_NE(std::string::npos,
            logs.find("[ras] [info] ras execute_async called"));
  clean_up(nullptr);
  unlink("conf.json");
}

TEST_F(ConfigUnitTest, TestAdapterDeviceCorrectableErrorCount) {
  boost::property_tree::ptree root_conf;
  ras_conf conf;

  try {
    boost::property_tree::read_json("conf.json", root_conf);
  } catch (std::exception &e) {
    std::cout << "Unable to read ras config. Error -> " << e.what() << "."
              << std::endl
              << "Using the default config" << std::endl;
  }

  conf.adapters_directory = root_conf.get<std::string>(
      "ras.adapters_directory", RAS_DEFAULT_ADAPTERS_DIRECTORY);
  initialize(nullptr);
  std::unique_ptr<ras_adapter_helper> adapter_helper_ =
      std::make_unique<ras_adapter_helper>();

  adapter_helper_->load_ras_adapters(conf.adapters_directory);
  adapter_helper_->get_device_correctable_error_count("ras_adapter_ut",
                                                      "dev123");

  clean_up(nullptr);
  top_conf.put_child("ras.logger", logger_conf);
  unlink("missing_logger_conf.json");
}

TEST(RasAdapterHelperUnitTest, TestDeviceCorrectableErrorCount) {
  std::unique_ptr<ras_adapter_helper> adapter_helper_ =
      std::make_unique<ras_adapter_helper>();

  auto num_adapters = adapter_helper_->load_ras_adapters(RAS_UT_ADAPTERS_DIR);
  // Mock adapter and UT adapter are loaded
  EXPECT_EQ(num_adapters, 2);
  auto error_count_o = adapter_helper_->get_device_correctable_error_count(
      "ras_adapter_ut", "dev123");
  EXPECT_TRUE(error_count_o.has_value());
  EXPECT_EQ(error_count_o.value(), 100);
}

TEST(RasAdapterHelperUnitTest, TestDeviceCorrectableErrorCountInvalidDevice) {
  std::unique_ptr<ras_adapter_helper> adapter_helper_ =
      std::make_unique<ras_adapter_helper>();

  auto num_adapters = adapter_helper_->load_ras_adapters(RAS_UT_ADAPTERS_DIR);
  // Mock adapter and UT adapter are loaded
  EXPECT_EQ(num_adapters, 2);
  auto error_count_o = adapter_helper_->get_device_correctable_error_count(
      "ras_adapter_ut", "dev_invalid");
  EXPECT_FALSE(error_count_o.has_value());
}

TEST(RasAdapterHelperUnitTest, TestLoadAdapters) {
  std::unique_ptr<ras_adapter_helper> adapter_helper_ =
      std::make_unique<ras_adapter_helper>();

  auto num_adapters = adapter_helper_->load_ras_adapters(RAS_UT_ADAPTERS_DIR);
  // Mock adapter and UT adapter are loaded
  EXPECT_EQ(num_adapters, 2);
}