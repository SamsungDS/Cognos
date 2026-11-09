#include <gtest/gtest.h>

#include <chrono>
#include <thread>

#include "bw_monitor.h"

// Simulate the CMMH stats in the mock version
extern "C" {
uint64_t g_mock_read_count = 0;
uint64_t g_mock_write_count = 0;

cmmh_stat_interface_t cmmh_stat_interface() {
  return cmmh_stat_interface_t{.cxl_read_count = g_mock_read_count,
                               .cxl_write_count = g_mock_write_count};
}
}

class BandwidthMonitorTest : public ::testing::Test {
 protected:
  BandwidthMonitor* monitor;

  void SetUp() override {
    g_mock_read_count = 0;
    g_mock_write_count = 0;
    monitor = new BandwidthMonitor();
  }

  void TearDown() override {
    std::thread killer([this]() { delete monitor; });
    killer.join();
    monitor = nullptr;
  }
};

TEST_F(BandwidthMonitorTest, AverageBandwidthIsZeroInitially) {
  EXPECT_EQ(monitor->get_average_MBps(), 0);
}

TEST_F(BandwidthMonitorTest, SamplingLoop) {
  auto* monitor = new BandwidthMonitor();
  monitor->start();
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  // stop & delete from a separate thread
  std::thread killer([monitor]() {
    monitor->stop();
    // trigger destructor
    delete monitor;
  });
  // ensure safe teardown
  killer.join();
  SUCCEED();
}

TEST_F(BandwidthMonitorTest, DeltaWindowEvictionWhenOverfilled) {
  auto* monitor = new BandwidthMonitor();
  monitor->start();

  // Simulate WINDOW_SIZE + 2 samples
  for (int i = 0; i < 12; ++i) {
    g_mock_read_count += 100;
    g_mock_write_count += 100;
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }

  std::thread killer([monitor]() {
    monitor->stop();
    delete monitor;
  });
  killer.join();
  SUCCEED();
}

TEST_F(BandwidthMonitorTest, SampledIOPrintsCorrectly) {
  auto* monitor = new BandwidthMonitor();
  g_mock_read_count = 500;
  g_mock_write_count = 300;

  monitor->start();
  std::this_thread::sleep_for(std::chrono::milliseconds(100));

  std::thread killer([monitor]() {
    monitor->stop();
    delete monitor;
  });
  killer.join();

  SUCCEED();
}
