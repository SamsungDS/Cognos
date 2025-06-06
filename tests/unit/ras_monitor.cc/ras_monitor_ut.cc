#include <gtest/gtest.h>
#include <ras_monitor.h>

#include <thread>

TEST(RasMonitorTest, TestClass) {
  std::unique_ptr<ras_monitor> test_mon_inst = std::make_unique<ras_monitor>();
  ras_request *dummy_request =
      new ras_request(false, true, test_mon_inst.get());
  bool result = false;

  result = test_mon_inst->ras_submit_request(nullptr);
  ASSERT_EQ(false, result);

  result = test_mon_inst->ras_submit_request(dummy_request);
  ASSERT_EQ(true, result);

  result = test_mon_inst->ras_submit_timed_request(nullptr);
  ASSERT_EQ(false, result);

  int n = 115;
  std::thread t[n];
  ras_monitor m;
  bool ret;

  for (int i = 0; i < n; ++i) {
    t[i] = std::thread([&]() {
      ret = m.ras_submit_timed_request(dummy_request);
      EXPECT_EQ(ret, true);
    });
  }

  for (int i = 0; i < n; ++i) {
    t[i].join();  // Wait for each thread to complete
  }

  delete dummy_request;
}
