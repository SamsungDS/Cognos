#include "framework_upstream.h"
#include <gtest/gtest.h>

TEST (InitTest, Init)
{
  std::string conf = "conf.json";
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  EXPECT_EQ (0, initialize_svk (conf.c_str (), ctx, 0));
}

TEST (ExecTest, ExecuteSync)
{
  svk_pass_thru_cmd *pass_thru = new svk_pass_thru_cmd ();
  svk_input *input = new svk_input ();
  svk_output *output = new svk_output ();

  EXPECT_EQ (0, execute_svk_feature_sync (pass_thru, input, output));
}

TEST (ExecTest, ExecuteAsync)
{
  svk_pass_thru_cmd *pass_thru = new svk_pass_thru_cmd ();
  svk_input *input = new svk_input ();
  svk_postprocess_fn *postprocess_fn = new svk_postprocess_fn ();

  EXPECT_EQ (0, execute_svk_feature_async (pass_thru, input, postprocess_fn));
}

TEST (CleanupTest, Cleanup)
{
  svk_feature_details *details = new svk_feature_details ();
  svk_storage_ctx *ctx = new svk_storage_ctx ();

  EXPECT_EQ (0, cleanup_svk (ctx, (void *)details));
}