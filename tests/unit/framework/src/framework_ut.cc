#include <dirent.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <stdlib.h>

#include "framework_service.h"
#include "framework_upstream.h"

using ::testing::_;
using ::testing::Return;
using ::testing::StrEq;

// Mock free function interface
class MockFreeInterface : public featureInterface
{
public:
  MOCK_METHOD (void *, get_sym, (void *handle, const char *fn_name),
               (const, override));
  MOCK_METHOD (void *, open_lib, (const char *ft_lib_str), (const, override));
  MOCK_METHOD (DIR *, open_dir, (const char *dir_str), (const, override));
};

// Test successful init by calling extern api with regular dlopen/dlsym
TEST (InitTest, InitSuccess)
{
  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);

  // Using relative path to config in SVK core for testing
  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";
  svk_storage_ctx *ctx = new svk_storage_ctx ();

  EXPECT_EQ (SVK_STATUS_SUCCESS, initialize_svk (conf.c_str (), (void *)ctx));
  cleanup_svk (ctx, (void *)conf.c_str ());
  delete ctx;
}

TEST (InitTest, InitFail)
{
  MockFreeInterface dep_inj;

  auto *dummy_init
      = static_cast<int (*) (void *)> ([] (void *details) { return 1; });

  ON_CALL (dep_inj, get_sym)
      .WillByDefault ([&dep_inj] (void *handle, const char *fn_name) {
        return dep_inj.featureInterface::get_sym (handle, fn_name);
      });
  ON_CALL (dep_inj, open_dir).WillByDefault ([&dep_inj] (const char *dir_str) {
    return dep_inj.featureInterface::open_dir (dir_str);
  });
  ON_CALL (dep_inj, open_lib)
      .WillByDefault ([&dep_inj] (const char *ft_lib_str) {
        return dep_inj.featureInterface::open_lib (ft_lib_str);
      });

  EXPECT_CALL (dep_inj, get_sym (_, ::testing::A<const char *> ()))
      .Times (6)
      .WillOnce (Return ((void *)dummy_init));

  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);

  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  FrameworkSvc *test_fwsvc1 = new FrameworkSvc ();

  EXPECT_EQ (
      SVK_STATUS_BAD_FEATURE_LIB,
      test_fwsvc1->FrameworkSvcInit (conf.c_str (), (void *)ctx, dep_inj));
  cleanup_svk (ctx, (void *)conf.c_str ());
}

TEST (InitTest, FailMapEntry)
{
  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);

  // Using relative path to config in SVK core for testing
  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  initialize_svk (conf.c_str (), (void *)ctx);
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB,
             initialize_svk (conf.c_str (), (void *)ctx));
  cleanup_svk (ctx, (void *)conf.c_str ());
  delete ctx;
}

// Test failed init by giving invalid config file path
TEST (InitTest, InvalidConfigPath)
{
  std::string conf = "invalid_conf_path";
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  EXPECT_EQ (SVK_STATUS_INVALID_CONFIG,
             initialize_svk (conf.c_str (), (void *)ctx));
  cleanup_svk (ctx, (void *)conf.c_str ());
  delete ctx;
}

TEST (InitTest, DefaultConfig)
{
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  std::string conf;
  EXPECT_EQ (SVK_STATUS_INVALID_CONFIG, initialize_svk (nullptr, (void *)ctx));
  cleanup_svk (ctx, (void *)conf.c_str ());
}

TEST (InitTest, EnvConfig)
{
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  setenv ("SVK_FW_CONFIG", "../../../../../config/test_config.json", 1);
  EXPECT_EQ (SVK_STATUS_SUCCESS, initialize_svk (nullptr, (void *)ctx));
  cleanup_svk (ctx, (void *)ctx);
}

TEST (InitTest, BadDir)
{
  MockFreeInterface dep_inj;
  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);
  // Using relative path to config in SVK core for testing
  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";

  FrameworkSvc *fw_svc1 = new FrameworkSvc ();
  EXPECT_CALL (dep_inj, open_dir (::testing::A<const char *> ()))
      .Times (1)
      .WillOnce (Return (nullptr));
  EXPECT_EQ (SVK_STATUS_FAIL,
             fw_svc1->FrameworkSvcInit (conf.c_str (), (void *)conf.c_str (),
                                        dep_inj));
  delete fw_svc1;
}

// Test if dlopen fails
TEST (InitTest, FailedDlopen)
{
  MockFreeInterface dep_inj;
  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);
  // Using relative path to config in SVK core for testing
  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";
  ON_CALL (dep_inj, open_dir).WillByDefault ([&dep_inj] (const char *dir_str) {
    return dep_inj.featureInterface::open_dir (dir_str);
  });
  FrameworkSvc *fw_svc1 = new FrameworkSvc ();
  EXPECT_CALL (dep_inj, open_lib (::testing::A<const char *> ()))
      .Times (1)
      .WillOnce (Return (nullptr));
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB,
             fw_svc1->FrameworkSvcInit (conf.c_str (), (void *)conf.c_str (),
                                        dep_inj));
  delete fw_svc1;
}

// Test failed init by calling fw svc api and either pass in mock api or
// indicate somehow
TEST (InitTest, FailedDlsym)
{
  MockFreeInterface dep_inj;
  // Dummy function pointers to allow dlsym to pass without error
  auto *dummy_init
      = static_cast<int (*) (void *)> ([] (void *details) { return 0; });
  auto *dummy_get_supported_feature_list
      = static_cast<int (*) (feature_id *, char *)> (
          [] (feature_id *feature, char *feature_names) { return 0; });
  auto *dummy_is_license_valid
      = static_cast<int (*) (void *)> ([] (void *details) { return 0; });
  auto *dummy_exec_sync = static_cast<int (*) (
      svk_pass_thru_cmd *pass_thru, svk_input *input, svk_input *output)> (
      [] (svk_pass_thru_cmd *pass_thru, svk_input *input, svk_input *output) {
        return 0;
      });
  auto *dummy_exec_async
      = static_cast<int (*) (svk_pass_thru_cmd *pass_thru, svk_input *input,
                             svk_postprocess_fn *postprocess_fn)> (
          [] (svk_pass_thru_cmd *pass_thru, svk_input *input,
              svk_postprocess_fn *postprocess_fn) { return 0; });

  // These make it so the functionality implemented in the interface
  // will be used instead of the mocked child class
  ON_CALL (dep_inj, open_dir).WillByDefault ([&dep_inj] (const char *dir_str) {
    return dep_inj.featureInterface::open_dir (dir_str);
  });
  ON_CALL (dep_inj, open_lib)
      .WillByDefault ([&dep_inj] (const char *ft_lib_str) {
        return dep_inj.featureInterface::open_lib (ft_lib_str);
      });

  // Set default return values of get_sym to nullptr for testing
  ON_CALL (dep_inj, get_sym (_, StrEq ("initialize")))
      .WillByDefault (Return (nullptr));
  ON_CALL (dep_inj, get_sym (_, StrEq ("get_supported_feature_list")))
      .WillByDefault (Return (nullptr));
  ON_CALL (dep_inj, get_sym (_, StrEq ("is_license_valid")))
      .WillByDefault (Return (nullptr));
  ON_CALL (dep_inj, get_sym (_, StrEq ("execute_sync")))
      .WillByDefault (Return (nullptr));
  ON_CALL (dep_inj, get_sym (_, StrEq ("execute_async")))
      .WillByDefault (Return (nullptr));
  ON_CALL (dep_inj, get_sym (_, StrEq ("clean_up")))
      .WillByDefault (Return (nullptr));

  // Test all error handling by hitting each error handling statement
  // These statements will force get_sym to return dummy function pointers
  // for the cases where we don't want errors
  EXPECT_CALL (dep_inj, get_sym (_, StrEq ("initialize")))
      .Times (6)
      .WillOnce (Return ((void *)dummy_init))
      .WillOnce (Return ((void *)dummy_init))
      .WillOnce (Return ((void *)dummy_init))
      .WillOnce (Return ((void *)dummy_init))
      .WillOnce (Return ((void *)dummy_init));
  EXPECT_CALL (dep_inj, get_sym (_, StrEq ("get_supported_feature_list")))
      .Times (5)
      .WillOnce (Return ((void *)dummy_get_supported_feature_list))
      .WillOnce (Return ((void *)dummy_get_supported_feature_list))
      .WillOnce (Return ((void *)dummy_get_supported_feature_list))
      .WillOnce (Return ((void *)dummy_get_supported_feature_list));
  EXPECT_CALL (dep_inj, get_sym (_, StrEq ("is_license_valid")))
      .Times (4)
      .WillOnce (Return ((void *)dummy_is_license_valid))
      .WillOnce (Return ((void *)dummy_is_license_valid))
      .WillOnce (Return ((void *)dummy_is_license_valid));
  EXPECT_CALL (dep_inj, get_sym (_, StrEq ("execute_sync")))
      .Times (3)
      .WillOnce (Return ((void *)dummy_exec_sync))
      .WillOnce (Return ((void *)dummy_exec_sync));
  EXPECT_CALL (dep_inj, get_sym (_, StrEq ("execute_async")))
      .Times (2)
      .WillOnce (Return ((void *)dummy_exec_async));
  EXPECT_CALL (dep_inj, get_sym (_, StrEq ("clean_up")))
      .Times (1)
      .WillOnce (Return (nullptr));

  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);

  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";
  FrameworkSvc *test_fwsvc1 = new FrameworkSvc ();
  int run1 = test_fwsvc1->FrameworkSvcInit (conf.c_str (),
                                            (void *)conf.c_str (), dep_inj);
  test_fwsvc1->FrameworkSvcCleanup ();
  int run2 = test_fwsvc1->FrameworkSvcInit (conf.c_str (),
                                            (void *)conf.c_str (), dep_inj);
  test_fwsvc1->FrameworkSvcCleanup ();
  int run3 = test_fwsvc1->FrameworkSvcInit (conf.c_str (),
                                            (void *)conf.c_str (), dep_inj);
  test_fwsvc1->FrameworkSvcCleanup ();
  int run4 = test_fwsvc1->FrameworkSvcInit (conf.c_str (),
                                            (void *)conf.c_str (), dep_inj);
  test_fwsvc1->FrameworkSvcCleanup ();
  int run5 = test_fwsvc1->FrameworkSvcInit (conf.c_str (),
                                            (void *)conf.c_str (), dep_inj);
  test_fwsvc1->FrameworkSvcCleanup ();
  int run6 = test_fwsvc1->FrameworkSvcInit (conf.c_str (),
                                            (void *)conf.c_str (), dep_inj);
  test_fwsvc1->FrameworkSvcCleanup ();

  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB, run1);
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB, run2);
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB, run3);
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB, run4);
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB, run5);
  EXPECT_EQ (SVK_STATUS_BAD_FEATURE_LIB, run6);
  delete test_fwsvc1;
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
  char buff[FILENAME_MAX];
  getcwd (buff, FILENAME_MAX);
  std::string current_working_dir (buff);

  // Using relative path to config in SVK core for testing
  std::string conf
      = current_working_dir + "/../../../../../config/test_config.json";
  svk_storage_ctx *ctx = new svk_storage_ctx ();
  EXPECT_EQ (SVK_STATUS_SUCCESS, initialize_svk (conf.c_str (), (void *)ctx));

  svk_feature_details *details = new svk_feature_details ();
  EXPECT_EQ (SVK_STATUS_SUCCESS, cleanup_svk (ctx, (void *)details));
}