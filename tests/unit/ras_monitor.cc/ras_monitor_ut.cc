#include <gtest/gtest.h>
#include <ras_monitor.h>

TEST(RasMonitorTest, TestClass) {
  std::unique_ptr<ras_monitor> test_mon_inst = std::make_unique<ras_monitor>();
  ras_request *dummy_request = (ras_request *)0xff001;
  bool result = false;

  result = test_mon_inst->ras_submit_request(nullptr);
  ASSERT_EQ(false, result);

  result = test_mon_inst->ras_submit_request(dummy_request);
  ASSERT_EQ(true, result);

  // Sleep for 1 second to allow enough time for requests to complete
  std::this_thread::sleep_for(std::chrono::milliseconds(1000));
}