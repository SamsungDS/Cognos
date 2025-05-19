#include <gtest/gtest.h>
#include <ras_monitor.h>

TEST(RasMonitorTest, TestClass) {
  std::unique_ptr<ras_monitor> test_mon_inst = std::make_unique<ras_monitor>();
  ras_request *dummy_request =
      new ras_request(false, true, test_mon_inst.get());
  bool result = false;

  result = test_mon_inst->ras_submit_request(nullptr);
  ASSERT_EQ(false, result);

  result = test_mon_inst->ras_submit_request(dummy_request);
  ASSERT_EQ(true, result);

  delete dummy_request;
}