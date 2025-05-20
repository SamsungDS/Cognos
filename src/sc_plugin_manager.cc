#include "sc_plugin_manager.h"  // PluginManager, register_plugin_func

#include <dirent.h>  // DIR, opendir, readdir, closedir
#include <dlfcn.h>   // dlopen, dlsym, dlclose, dlerror
#include <errno.h>   // errno, POSIX error codes

#include <string>  // std::string

#include "sc_logger.h"  // LOG

/**
 * @brief Typedef for the symbol exposed by each plugin.
 *
 * Every plugin must define a function:
 * extern "C" void register_plugin(DeviceManager&);
 */
typedef void (*register_plugin_func)(DeviceManager&);

/**
 * @brief Constructor for PluginManager.
 *
 * @param manager Reference to the DeviceManager instance used during plugin
 * registration.
 */
PluginManager::PluginManager(DeviceManager& manager) : manager_(manager) {}

/**
 * @brief Destructor: Unloads all loaded plugins.
 */
PluginManager::~PluginManager() { unloadAllPlugins(); }

/**
 * @brief Loads all `.so` plugin files from the given directory.
 *
 * This function scans the directory, identifies `.so` files,
 * and dynamically loads them via dlopen + dlsym.
 * It invokes the exported `register_plugin(DeviceManager&)` symbol to allow
 * the plugin to register itself with the DeviceManager.
 *
 * @param plugin_dir The directory path containing `.so` plugin files.
 * @return 0 on success, or negative POSIX error code on failure.
 */
int PluginManager::loadAllPlugins(const std::string& plugin_dir) {
  DIR* dir = opendir(plugin_dir.c_str());
  if (!dir) {
    LOG(level_E::ERROR, "Failed to open plugin directory: " + plugin_dir);
    return -errno;
  }

  LOG(level_E::INFO, "Scanning plugin directory: " + plugin_dir);

  struct dirent* entry;
  while ((entry = readdir(dir)) != nullptr) {
    std::string file_name(entry->d_name);

    // Only load .so files
    if (file_name.size() > 3 &&
        file_name.substr(file_name.size() - 3) == ".so") {
      std::string full_path = plugin_dir + "/" + file_name;
      int status = loadPlugin(full_path);
      if (status < 0) {
        LOG(level_E::ERROR, "Warning: Failed to load plugin: " + full_path +
                                ", error code: " + std::to_string(status));
      } else {
        LOG(level_E::INFO, "Successfully loaded plugin: " + full_path);
      }
    }
  }

  closedir(dir);
  return 0;
}

/**
 * @brief Loads a specific plugin `.so` file and registers it with the
 * DeviceManager.
 *
 * This loads the shared object using dlopen, resolves the `register_plugin`
 * symbol, and invokes it to register the adapter with the DeviceManager.
 *
 * @param plugin_file Absolute or relative path to the plugin `.so` file.
 * @return 0 on success, or negative POSIX error code on failure.
 */
int PluginManager::loadPlugin(const std::string& plugin_file) {
  if (loaded_plugins_.count(plugin_file)) {
    LOG(level_E::WARN, "Plugin already loaded: " + plugin_file);
    return -EEXIST;
  }

  // void* handle = dlopen(plugin_file.c_str(), RTLD_NOW | RTLD_GLOBAL);
  void* handle = dlopen(plugin_file.c_str(), RTLD_LAZY);
  if (!handle) {
    LOG(level_E::ERROR, "dlopen failed for " + plugin_file + ": " + dlerror());
    return -EINVAL;
  }

  // Clear any existing error
  dlerror();

  register_plugin_func reg_fn =
      reinterpret_cast<register_plugin_func>(dlsym(handle, "register_plugin"));

  const char* dlsym_error = dlerror();
  if (dlsym_error != nullptr) {
    LOG(level_E::ERROR, "dlsym error in " + plugin_file + ": " + dlsym_error);
    dlclose(handle);
    return -ENOENT;
  }

  try {
    LOG(level_E::INFO, "Registering plugin: " + plugin_file);
    reg_fn(manager_);
  } catch (...) {
    LOG(level_E::ERROR, "Exception during plugin registration: " + plugin_file);
    dlclose(handle);
    return -EFAULT;
  }

  loaded_plugins_[plugin_file] = handle;
  return 0;
}

/**
 * @brief Unloads a specific plugin by file name.
 *
 * Removes the plugin handle from memory and internal state.
 *
 * @param plugin_file The file path originally used to load the plugin.
 * @return 0 on success, or negative POSIX error code if plugin was not loaded.
 */
int PluginManager::unloadPlugin(const std::string& plugin_file) {
  auto it = loaded_plugins_.find(plugin_file);
  if (it == loaded_plugins_.end()) {
    LOG(level_E::WARN, "Plugin not found for unload: " + plugin_file);
    return -ENOENT;
  }

  if (it->second != nullptr) {
    dlclose(it->second);
  }
  loaded_plugins_.erase(it);
  LOG(level_E::INFO, "Unloaded plugin: " + plugin_file);
  return 0;
}

/**
 * @brief Unloads all loaded plugin handles and clears internal state.
 *
 * @return 0 on success.
 */
int PluginManager::unloadAllPlugins() {
  for (const auto& [path, handle] : loaded_plugins_) {
    if (handle) {
      dlclose(handle);
      LOG(level_E::INFO, "Unloaded plugin: " + path);
    } else {
      LOG(level_E::INFO, "Skipping Unload for null plugin handle: " + path);
    }
  }
  loaded_plugins_.clear();
  return 0;
}

/**
 * @brief Returns list of currently loaded plugin file paths.
 *
 * @return Vector of file names (keys) for loaded plugins.
 */
std::vector<std::string> PluginManager::getAvailablePlugins() const {
  std::vector<std::string> result;
  for (const auto& [file, _] : loaded_plugins_) {
    result.push_back(file);
  }
  return result;
}
