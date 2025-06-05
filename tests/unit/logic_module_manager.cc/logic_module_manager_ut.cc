#include <stdlib.h>

#include "gmock/gmock.h"
#include "gtest/gtest.h"
#include "logic_interface/svk_logic_struct.h"
#include "mock/mock_dlfcn.h"
#include "mock/mock_logger.h"
#include "utils/logic_module_manager.hpp"

using ::testing::_;
using ::testing::Return;
using ::testing::StrEq;

std::string test_feature_name1 = "test_feature1";
std::string lmn = "test_logic";

extern "C" {
svk_status mock_initialize_logic_module_function(void *init_param) {
  const char *env_string_ilm;
  env_string_ilm = std::getenv("MOCK_INITIALIZE_LOGIC_MODULE_FN_FAIL");
  if (env_string_ilm && strcmp(env_string_ilm, "true") == 0) {
    return SVK_STATUS_FAIL;
  }
  return SVK_STATUS_SUCCESS;
}

svk_status mock_cleanup_logic_module(void *) { return SVK_STATUS_SUCCESS; }
svk_status mock_get_supported_logic_details_fn(
    svk_logic_module_details *details) {
  const char *env_string_gsld;
  const char *env_string_feature_name;

  env_string_gsld = std::getenv("MOCK_GET_SUPPORTED_LOGIC_DETAILS_FN_FAIL");
  if (env_string_gsld && strcmp(env_string_gsld, "true") == 0) {
    return SVK_STATUS_FAIL;
  }

  env_string_feature_name = std::getenv("MOCK_SET_MODULE_FEATURE_NAME");
  if (env_string_gsld && !strcmp(env_string_feature_name, "") == 0) {
    return SVK_STATUS_FAIL;
  }

  strncpy(details->feature_name, env_string_feature_name, 256);
  strncpy(details->logic_module_name, lmn.c_str(), 256);
  details->cleanup_logic_module = mock_cleanup_logic_module;

  return SVK_STATUS_SUCCESS;
}
}

TEST(LogicModuleManagerTest, LoadLogicModuleSuccess) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_TRUE(result == lmn);
  ASSERT_TRUE(result.has_value());
  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, GetLogicModuleDetails_Valid) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);

  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  ASSERT_TRUE(result == lmn);
  ASSERT_TRUE(result.has_value());

  logic_module_ctx module_ctx = manager.get_logic_module_details(lmn);
  ASSERT_TRUE(module_ctx != nullptr);
  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, LoadLogicModule_MultipleSuccess) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module multiple times
  logic_module_name result1 =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  logic_module_name result2 =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_TRUE(result1 == lmn);
  ASSERT_TRUE(result2 == std::nullopt);
  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, LoadLogicDlopenFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "false", true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  ASSERT_EQ(result, std::nullopt);
}

TEST(LogicModuleManagerTest, LoadLogicModuleInitFnFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_TRUE(result == std::nullopt);
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, LoadLogicModuleDlsymFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  ASSERT_EQ(result, std::nullopt);

  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, GetLogicModuleDetails_NotFound) {
  logic_module_manager manager;
  std::string logic_module_name = "non_existent_module";

  logic_module_ctx result = manager.get_logic_module_details(logic_module_name);

  ASSERT_EQ(result, nullptr);
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, LoadLogicModuleGetDetailsFnFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_TRUE(result == std::nullopt);
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, InitializeLogicModuleFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("MOCK_INITIALIZE_LOGIC_MODULE_FN_FAIL", "true", true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_EQ(result, std::nullopt);
  unsetenv("MOCK_DLOPEN_SUCCESS");
  unsetenv("MOCK_INITIALIZE_LOGIC_MODULE_FN_FAIL");
}

TEST(LogicModuleManagerTest, GetSupportedLogicDetailsFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);
  setenv("MOCK_GET_SUPPORTED_LOGIC_DETAILS_FN_FAIL", "true", true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_EQ(result, std::nullopt);
  unsetenv("MOCK_DLOPEN_SUCCESS");
  unsetenv("MOCK_GET_SUPPORTED_LOGIC_DETAILS_FN_FAIL");
}

TEST(LogicModuleManagerTest, LoadLogicModule_FailMultipleTimes) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module multiple times
  logic_module_name result1 =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  logic_module_name result2 =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_TRUE(result1 == lmn);
  ASSERT_TRUE(result2 == std::nullopt);
  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, LoadLogicModule_FailFeatureMismatch) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", "wrong_feature_name", true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module multiple times
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);

  ASSERT_TRUE(result == std::nullopt);
  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, UnloadLogicModule_Success) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  ASSERT_TRUE(result == lmn);
  ASSERT_TRUE(result.has_value());

  // Unload the logic module
  manager.unload_logic_module(lmn);

  // Verify that the module is unloaded
  logic_module_ctx module_ctx = manager.get_logic_module_details(lmn);
  ASSERT_EQ(module_ctx, nullptr);

  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, UnloadLogicModule_ModuleNotFound) {
  logic_module_manager manager;

  // Unload a non-existent logic module
  manager.unload_logic_module("non_existent_module");
}

TEST(LogicModuleManagerTest, UnloadLogicModule_MultipleTimes) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  ASSERT_TRUE(result == lmn);
  ASSERT_TRUE(result.has_value());

  // Unload the logic module multiple times
  manager.unload_logic_module(lmn);
  manager.unload_logic_module(lmn);

  // Verify that the module is unloaded
  logic_module_ctx module_ctx = manager.get_logic_module_details(lmn);
  ASSERT_EQ(module_ctx, nullptr);

  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}

TEST(LogicModuleManagerTest, UnloadLogicModuleDlcloseFail) {
  logic_module_manager manager;
  std::string logic_module_location = "/path/to/module";
  setenv("MOCK_DLOPEN_SUCCESS", "true", true);
  setenv("MOCK_SET_MODULE_FEATURE_NAME", test_feature_name1.c_str(), true);
  setenv("initialize_logic_module",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_initialize_logic_module_function))
             .c_str(),
         true);
  setenv("get_supported_logic_details",
         std::to_string(
             reinterpret_cast<uintptr_t>(mock_get_supported_logic_details_fn))
             .c_str(),
         true);

  // Load the logic module
  logic_module_name result =
      manager.load_logic_module(logic_module_location, test_feature_name1);
  ASSERT_TRUE(result == lmn);
  ASSERT_TRUE(result.has_value());

  // Mock dlclose to fail
  setenv("MOCK_DLCLOSE_FAIL", "true", true);

  // Unload the logic module
  manager.unload_logic_module(lmn);

  // Verify that an error is logged
  unsetenv("MOCK_DLCLOSE_FAIL");
  unsetenv("MOCK_SET_MODULE_FEATURE_NAME");
  unsetenv("MOCK_DLOPEN_SUCCESS");
}