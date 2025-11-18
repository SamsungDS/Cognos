
#include <dirent.h>
#include <fcntl.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/types.h>

#include <boost/property_tree/xml_parser.hpp>
#include <nlohmann/json.hpp>

#include "logic_interface/svk_logic_struct.h"
#include "svk_slat.hpp"

using ::testing::_;
using ::testing::Return;
using ::testing::StrEq;

#define MOCK_STRUCT_INIT(...) \
  { __VA_ARGS__ }

#define DEFINE_RETURN_MOCK(fn, ret) \
  bool ut_##fn##_mocked = false;    \
  ret ut_##fn

DEFINE_RETURN_MOCK(create_event_in_json_format, int);

int create_event_in_json_format(const slat_benchmark_config &config,
                                const svk_slat_logic_output &app_current_sla,
                                std::string severity, std::string message,
                                json &json_data) {
  std::cout << "create_event_in_json_format MOCK CALLED" << std::endl;
  if (ut_create_event_in_json_format_mocked) {
    std::cout << "Actual create_event_in_json_format function CALLED"
              << std::endl;
    return ut_create_event_in_json_format;
  }
  char *env_string = std::getenv("SVK_SLAT_SKIP_JSON_FORMAT");
  if (env_string && strcmp(env_string, "true") == 0) {
    std::cout << "SKIP JSON CALLED" << std::endl;
    json_data = json();
    return -1;
  }

  env_string = std::getenv("SVK_SLAT_EMPTY_JSON_DATA");
  if (env_string && strcmp(env_string, "true") == 0) {
    std::cout << "EMPTY JSON CALLED" << std::endl;
    json_data = json();
    return 0;
  }
  json json_map;
  json observations_map;
  observations_map["device_name"] =
      std::string(app_current_sla.device_name, 0, SLAT_MAX_STR_LEN);
  observations_map["host_name"] =
      std::string(app_current_sla.host_name, 0, SLAT_MAX_STR_LEN);
  observations_map["app_name"] =
      std::string(app_current_sla.app_name, 0, SLAT_MAX_STR_LEN);
  observations_map["avg_latency_ns"] = app_current_sla.avgLatencyns;
  observations_map["feature_name"] = SLAT_FEATURE_MODULE_NAME;

  json_map["domain"] = "observability";
  json_map["category"] = "slat";
  json_map["msg"] = message;
  json_map["severity"] = severity;

  json_map["source_type"] = "node";
  json_map["source"] =
      std::string(app_current_sla.host_name, 0, SLAT_MAX_STR_LEN);
  json_map["timestamp"] = 123456;
  json_map["observations"] = observations_map;

  json_data = json_map;
  return 0;
}

class SLATrackerSvc_Test : public SLATrackerSvc {
 public:
  SLATrackerSvc_Test(){};
  void test_publish_data(slat_benchmark_config &config) {
    std::cout << "TEST PUBLISH DATA CALLED" << std::endl;
    publish_app_event(config);
  }
  std::string test_benchmark(slat_benchmark_config &config) {
    return run_benchmark(config);
  }
};

// Format for running code before specific test suite, in this case InitTest
class ConfigTestWithMock : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    slat_conf.put("slat.logic_lib_dir", "/tmp");
    slat_conf.put("slat.disable_bg_thread", "true");

    logger_conf.put("log_level", "INFO");
    logger_conf.put("log_file_name", "/var/log/svk/test_slat.log");
    logger_conf.put("log_file_count", 1);
    logger_conf.put("log_file_size", 1048576);
    logger_conf.put("sink_type", "rotating_file");

    slat_conf.put_child("slat.logger", logger_conf);
  }

  static boost::property_tree::ptree slat_conf;
  static boost::property_tree::ptree logger_conf;
};

// These variables will be global to only the ConfigTestWithMock suite
// Since order of execution is not guaranteed, we can only assume these are
// available for that test suite.
boost::property_tree::ptree ConfigTestWithMock::slat_conf;
boost::property_tree::ptree ConfigTestWithMock::logger_conf;

TEST_F(ConfigTestWithMock, SLATWithEmptyJSONData) {
  EXPECT_EQ(setenv("SVK_SLAT_EMPTY_JSON_DATA", "true", 1), 0);
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  SLATrackerSvc_Test svc;
  svc.Initialize("slat_conf.json");

  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = 100;
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  strcpy(app_config.app_current_sla.host_name, "dummyhost");
  strcpy(app_config.app_current_sla.app_name, "app1");
  strcpy(app_config.app_current_sla.app_pid, "4321");
  strcpy(app_config.app_current_sla.device_name, "dummyhost_0");
  app_config.app_current_sla.avgLatencyns = 1000;
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
  EXPECT_EQ(setenv("SVK_SLAT_EMPTY_JSON_DATA", "false", 1), 0);
}

TEST_F(ConfigTestWithMock, SLATWithSkippingJSONError) {
  EXPECT_EQ(setenv("SVK_SLAT_SKIP_JSON_FORMAT", "true", 1), 0);
  boost::property_tree::write_json("slat_conf.json", slat_conf);
  SLATrackerSvc_Test svc;
  svc.Initialize("slat_conf.json");

  slat_benchmark_config config;
  slat_app_sla_config app_config;
  config.device_numa_node = 100;
  config.device_advertised_sla = 100;
  config.device_current_sla = 1000;
  config.device_sla_tolerance_percent = 10;
  app_config.app_requested_sla_ns = 100;
  app_config.app_sla_tolerance_percent = 10;
  strcpy(app_config.app_current_sla.host_name, "dummyhost");
  strcpy(app_config.app_current_sla.app_name, "app1");
  strcpy(app_config.app_current_sla.app_pid, "4321");
  strcpy(app_config.app_current_sla.device_name, "dummyhost_0");
  app_config.app_current_sla.avgLatencyns = 1000;
  config.app_sla_list["app1"] = app_config;
  svc.test_publish_data(config);
  unlink("slat_conf.json");
  EXPECT_EQ(setenv("SVK_SLAT_SKIP_JSON_FORMAT", "false", 1), 0);
}
