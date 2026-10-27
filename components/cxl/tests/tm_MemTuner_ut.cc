#include <gtest/gtest.h>
#include <unistd.h>

#include <cstdio>
#include <map>
#include <mutex>
#include <unordered_map>

#include "pm_damo.h"
#include "sc_servicer.h"
#include "tuner.h"
#include "utils.h"

using namespace std;

unordered_map<string, string> tokens_map;

class tunerTest : public ::testing::Test {
 protected:
  tuner mt_obj;

  void SetUp() override {}
};

TEST_F(tunerTest, DISABLED_Checktuner) {
  tuner mt;
  tokens_map["application"] = "gemfire_test";
  tokens_map["application_id"] = "1234";
  tokens_map["dram_node"] = "0";
  tokens_map["cxl_node"] = "1";
  tokens_map["sla_iops"] = "150000";
  tokens_map["sla_size"] = "1024";
  tokens_map["sla_latencyus"] = "750";
  pair<string, unsigned long> tuner_context_key =
      make_pair(tokens_map["application"], stoul(tokens_map["application_id"]));
  pair<string, unsigned long> tuner_context_key_ne =
      make_pair("application_ne", 1234);

  // negative cases for application ID not a real process ID
  EXPECT_TRUE(mt.tuner_start(tokens_map, PAGE_MOVER_DAMO) == -EINVAL);
  EXPECT_TRUE(mt.tuner_stop(tuner_context_key) == -EINVAL);
  EXPECT_TRUE(mt.tuner_stop(tuner_context_key_ne) == -EINVAL);

  // invalid page mover type
  EXPECT_TRUE(mt.tuner_start(tokens_map, PAGE_MOVER_INVALID) == -EINVAL);

  // success path test cases
  tokens_map["application"] = "gemfire";
  tokens_map["application_id"] = to_string(getpid());
  tuner_context_key =
      make_pair(tokens_map["application"], stoul(tokens_map["application_id"]));
  EXPECT_TRUE(mt.tuner_start(tokens_map, PAGE_MOVER_DAMO) == 0);
  EXPECT_TRUE(mt.tuner_stop(tuner_context_key) == -EINVAL);

  damo_global_config_cleanup();
}
