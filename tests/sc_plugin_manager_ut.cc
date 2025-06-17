#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>

#include "sc_dev_manager.h"
#include "sc_plugin_manager.h"

class PluginManagerTest : public ::testing::Test {
 protected:
  DeviceManager dev_mgr;
  PluginManager plugin_mgr{dev_mgr};

  std::string plugin_path =
      std::string(TEST_PLUGIN_DIR) + "/libdummy_plugin.so";

  void SetUp() override {
    ASSERT_TRUE(std::filesystem::exists(plugin_path))
        << "Plugin .so file missing: " << plugin_path;
  }

  void TearDown() override { plugin_mgr.unloadAllPlugins(); }
};

TEST_F(PluginManagerTest, UnloadPlugin_NotFound) {
  EXPECT_EQ(plugin_mgr.unloadPlugin("nonexistent.so"), -ENOENT);
}

TEST_F(PluginManagerTest, LoadAllPlugins_DirectoryDoesNotExist) {
  std::string bad_dir = "/nonexistent/plugin/dir";
  int result = plugin_mgr.loadAllPlugins(bad_dir);
  EXPECT_LT(result, 0);
}

TEST_F(PluginManagerTest, LoadAllPlugins_EmptyDirectory) {
  std::filesystem::create_directory("empty_plugins");
  int result = plugin_mgr.loadAllPlugins("empty_plugins");
  EXPECT_EQ(result, 0);
  EXPECT_TRUE(plugin_mgr.getAvailablePlugins().empty());
  std::filesystem::remove_all("empty_plugins");
}

TEST_F(PluginManagerTest, LoadAllPlugins_BadPluginSymbolFails) {
  std::filesystem::create_directory("bad_plugins");

  // Generate a dummy .so missing register_plugin
  std::string so_path = "bad_plugins/libbad.so";
  std::ofstream cpp_file("bad.cpp");
  cpp_file << "extern \"C\" void dummy() {}";
  cpp_file.close();
  std::string cmd = "g++ -fPIC -shared bad.cpp -o " + so_path;
  ASSERT_EQ(std::system(cmd.c_str()), 0);

  int result = plugin_mgr.loadAllPlugins("bad_plugins");
  EXPECT_EQ(result, 0);
  EXPECT_TRUE(plugin_mgr.getAvailablePlugins().empty());

  // Clean up
  std::filesystem::remove("bad.cpp");
  std::filesystem::remove_all("bad_plugins");
}

TEST_F(PluginManagerTest, LoadPlugin_DlopenFailure) {
  std::string invalid_path = "/nonexistent/path/libdoesnotexist.so";
  int result = plugin_mgr.loadPlugin(invalid_path);
  EXPECT_EQ(result, -EINVAL);
}

TEST_F(PluginManagerTest, LoadPlugin_DlsymFailure) {
  std::string so_path = "libtemp_dlsym_fail.so";
  std::string cpp_file = "temp_dlsym_fail.cpp";

  std::ofstream out(cpp_file);
  out << R"(extern "C" void dummy() {})";
  out.close();

  std::string cmd = "g++ -fPIC -shared " + cpp_file + " -o " + so_path;
  int build_result = std::system(cmd.c_str());
  ASSERT_EQ(build_result, 0) << "Failed to compile test .so";

  ASSERT_TRUE(std::filesystem::exists(so_path));
  int result = plugin_mgr.loadPlugin(so_path);
  EXPECT_EQ(result, -ENOENT);

  std::filesystem::remove(so_path);
  std::filesystem::remove(cpp_file);
}

TEST_F(PluginManagerTest, LoadPlugin_RegistrationThrows) {
  std::string cpp_file = "temp_throwing_plugin.cpp";
  std::string so_file = "libtemp_throwing_plugin.so";

  std::ofstream out(cpp_file);
  ASSERT_TRUE(out.is_open());
  out << R"(
#include <stdexcept>
#include "sc_dev_manager.h"

extern "C" void register_plugin(DeviceManager& mgr) {
throw std::runtime_error("Simulated plugin registration failure");
}
)";
  out.close();

  std::string cmd = "g++ -fPIC -shared -o " + so_file + " " + cpp_file +
                    " -I../../src/include -I../../third_party";
  int compile_result = std::system(cmd.c_str());
  ASSERT_EQ(compile_result, 0) << "Failed to compile plugin .so";

  ASSERT_TRUE(std::filesystem::exists(so_file));
  int result = plugin_mgr.loadPlugin(so_file);
  EXPECT_EQ(result, -EFAULT);

  std::filesystem::remove(so_file);
  std::filesystem::remove(cpp_file);
}
