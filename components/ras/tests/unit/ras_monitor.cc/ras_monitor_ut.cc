#include <gtest/gtest.h>
#include <ras_monitor.h>

#include <ras.hpp>

#include "mock/mock_svk_publisher.h"

struct ras_context_s ras_context;

TEST(RasMonitorTest, TestClass) {
  ras_monitor* test_mon_inst = new ras_monitor();

  ras_context.monitor_context = test_mon_inst;

  ras_request* dummy_request = new ras_request(true, &ras_context, false);
  bool result = false;

  result = test_mon_inst->ras_submit_request(nullptr);
  ASSERT_EQ(false, result);

  result = test_mon_inst->ras_submit_timed_request(nullptr, 3);
  ASSERT_EQ(true, result);

  int n = 11, interval = 3;
  bool ret;

  for (int i = 0; i < n; ++i) {
    ret = false;
    ret = test_mon_inst->ras_submit_timed_request(dummy_request, interval);
    EXPECT_EQ(ret, true);
  }

  delete dummy_request;
  delete test_mon_inst;
}
