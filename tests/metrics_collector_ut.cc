#include <gtest/gtest.h>

#include "metrics_collector.h"

using namespace std;

class MetricsCollectorTest : public ::testing::Test
{
	protected:
  		MetricsCollector mc;
 
  		void SetUp() override
  		{
    			mc = MetricsCollector();
  		}
};

TEST_F(MetricsCollectorTest, CheckMemoryMetrics)
{
	EXPECT_NO_THROW(mc.get_memory_metrics());
	EXPECT_FALSE(mc.dram_memory_capacity == 0);
	EXPECT_FALSE(mc.system_total_memory_capacity == 0);
	EXPECT_FALSE(mc.system_total_memory_current_usage == 0);
}


TEST_F(MetricsCollectorTest, CheckCPUMetrics)
{
        EXPECT_NO_THROW(mc.get_cpu_metrics("dstat --cpu 1 2"));
	EXPECT_THROW(mc.get_cpu_metrics("invalid command"), std::runtime_error);
	EXPECT_THROW(mc.get_cpu_metrics("> /dev/null"), std::runtime_error);
	EXPECT_THROW(mc.get_cpu_metrics("dstat --net 1 2"), std::runtime_error);
}

TEST_F(MetricsCollectorTest, CPUMetricsParser)
{
         EXPECT_THROW(mc.dstat_parser_cpu_usage(""), std::invalid_argument);
	 string dstat_output_test = "  8   0  90   0   0";
	 double test_output_1 = 10.0;
	 EXPECT_EQ(mc.dstat_parser_cpu_usage(dstat_output_test), test_output_1);
	 dstat_output_test = "invalid dstat output";
	 EXPECT_THROW(mc.dstat_parser_cpu_usage(dstat_output_test), std::runtime_error);
	 dstat_output_test = " 8 0 inv  0  0 ";
	 EXPECT_THROW(mc.dstat_parser_cpu_usage(dstat_output_test), std::runtime_error);
}


TEST_F(MetricsCollectorTest, CheckSystemMetrics)
{
	EXPECT_EQ(mc.get_system_metrics(), 0);
}
