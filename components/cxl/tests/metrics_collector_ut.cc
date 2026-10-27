#include <gtest/gtest.h>

#include "metrics_collector.h"

using namespace std;

class MetricsCollectorTest : public ::testing::Test {
 protected:
  MetricsCollector mc;

  void SetUp() override { mc = MetricsCollector(); }
};

TEST_F(MetricsCollectorTest, CheckMemoryMetrics) {
  EXPECT_NO_THROW(mc.get_memory_metrics());
  EXPECT_FALSE(mc.dram_memory_capacity == 0);
  EXPECT_FALSE(mc.system_total_memory_capacity == 0);
  EXPECT_FALSE(mc.system_total_memory_current_usage == 0);
}

TEST_F(MetricsCollectorTest, CheckCPUMetrics) {
  EXPECT_NO_THROW(mc.get_cpu_metrics());
}

TEST_F(MetricsCollectorTest, CheckSystemMetrics) {
  EXPECT_EQ(mc.get_system_metrics(), 0);
}
