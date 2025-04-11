#ifndef PLUGIN_MANAGER_H
#define PLUGIN_MANAGER_H
#include <string>
#include <unordered_map>
#include <vector>

#include "sc_dev_manager.h"

/**
 * @class PluginManager
 * @brief Manages dynamic loading and unloading of cxladapter plugin modules.
 *
 * PluginManager is responsible for discovering, loading, unloading, and
 * managing dynamically linked plugin libraries (e.g. cmm-h.so, cmm-d.so and
 * cmm-b.so). It supports both individual plugin handling and bulk operations.
 */
class PluginManager {
 public:
  /**
   * @brief Constructs a PluginManager.
   *
   * Initializes the plugin manager with plugin directory and a reference to
   * DeviceManager.
   * @param plugin_dir Path to the directory containing plugin `.so` files.
   * @param manager reference to DeviceManager instance for
   * registering/unregistering adapters.
   */
  explicit PluginManager(const std::string& plugin_dir, DeviceManager& manager);

  /**
   * @brief Destructor. Ensures all loaded plugins are properly unloaded.
   */
  ~PluginManager();

  /**
   * @brief Loads all plugin libraries from the plugin directory.
   *
   * Scans the specified directory, attempts to load each `.so` file, and
   * registers the plugin via a known symbol.
   *
   * @return 0 on success, or negative POSIX error code on failure.
   */
  int loadAllPlugins();

  /**
   * @brief Unloads all currently loaded plugins.
   *
   * Invokes cleanup on all loaded plugin handles and clears internal state.
   *
   * @return 0 on success, or negative POSIX error code on failure.
   */
  int unloadAllPlugins();

  /**
   * @brief Loads a specific plugin by its file name.
   *
   * Dynamically loads the given shared object and resolves its registration
   * symbol.
   *
   * @param plugin_file Full or relative path to the plugin `.so` file.
   * @return 0 on success, or negative POSIX error code on failure.
   */
  int loadPlugin(const std::string& plugin_file);

  /**
   * @brief Unloads a specific plugin by name.
   *
   * Frees the dynamic handle and removes it from internal tracking.
   *
   * @param plugin_file File name or key of the plugin to unload.
   * @return 0 on success, or negative POSIX error code on failure.
   */
  int unloadPlugin(const std::string& plugin_file);

  /**
   * @brief Returns the list of currently available (loaded) plugins.
   *
   * @return A vector of plugin file names or identifiers.
   */
  std::vector<std::string> getAvailablePlugins() const;

 private:
  // Path to plugin directory
  std::string plugin_dir_;
  // Device Manager
  DeviceManager& manager_;
  // Stores loaded plugin handles (e.g. from dlopen)
  std::unordered_map<std::string, void*> loaded_plugins_;
};
#endif
