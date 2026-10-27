#include <gtest/gtest.h>

#include "mock/mock.h"
#include "ras.hpp"
#include "ras_monitor.h"
#include "ras_ut_config.h"

DEFINE_STUB(ras_submit_timed_request, bool, (ras_request * req, int interval),
            true)

DEFINE_STUB(build_device_monitor_request, ras_request *,
            (ras_context_s * ras_context, device_unique_identifier device_name),
            nullptr)

class AddDeviceHandlerUnitTest : public testing::Test {
 protected:
  static void SetUpTestSuite() {
    adapter_helper_ = std::make_unique<ras_adapter_helper>();
    adapter_helper_->load_ras_adapters(RAS_UT_ADAPTERS_DIR);
    test_ras_ctx.ras_adapter_helper_ = adapter_helper_.get();
    test_ras_ctx.monitor_context = new ras_monitor();

    add_device_handler_ =
        std::make_unique<add_ras_monitor_for_device_handler>();
  }

  static std::unique_ptr<ras_adapter_helper> adapter_helper_;
  static ras_context_s test_ras_ctx;
  static std::unique_ptr<add_ras_monitor_for_device_handler>
      add_device_handler_;
};

std::unique_ptr<ras_adapter_helper> AddDeviceHandlerUnitTest::adapter_helper_;
ras_context_s AddDeviceHandlerUnitTest::test_ras_ctx;
std::unique_ptr<add_ras_monitor_for_device_handler>
    AddDeviceHandlerUnitTest::add_device_handler_;

TEST_F(AddDeviceHandlerUnitTest, AddMonitorRequestSubmitFailure) {
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        }
      }
    }
  )";
  ras_request req(true, &test_ras_ctx, true, input_str.c_str(),
                  input_str.size());
  auto res = req.parse_input_command_to_json();
  EXPECT_TRUE(res);

  ras_request *g_dummy_monitor_req = new ras_request(false, nullptr);
  MOCK_SET(build_device_monitor_request, g_dummy_monitor_req);
  MOCK_SET(ras_submit_timed_request, false);
  add_device_handler_->execute(req);
  MOCK_CLEAR(ras_submit_timed_request);
  MOCK_CLEAR(build_device_monitor_request);
  EXPECT_FALSE(req.is_successfull);
}

TEST_F(AddDeviceHandlerUnitTest, AddMonitorBuildRequestFailure) {
  std::string input_str = R"(
    {
      "command_name" : "add_reliability_monitoring_for_device",
      "command_params" : {
        "device_id" : "dev123",
        "device_numa" : 0,
        "configure_options" : {
          "error_count_threshold" : 500
        }
      }
    }
  )";
  ras_request req(true, &test_ras_ctx, false, input_str.c_str(),
                  input_str.size());
  auto res = req.parse_input_command_to_json();
  EXPECT_TRUE(res);

  add_device_handler_->execute(req);
  EXPECT_FALSE(req.is_successfull);
}