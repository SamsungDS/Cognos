#include <gtest/gtest.h>
#include <ras_monitor.h>

TEST(RasMonitorTest, TestClass) {
  std::unique_ptr<ras_monitor> test_mon_inst = std::make_unique<ras_monitor>();
  ras_request *dummy_request =
      new ras_request(false, true, test_mon_inst.get());
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
}
