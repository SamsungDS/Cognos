#ifndef _LOGIC_MODULE_MANAGER_HPP_
#define _LOGIC_MODULE_MANAGER_HPP_

#include <dlfcn.h>

#include <map>
#include <mutex>
#include <optional>

#include "logic_interface/svk_logic_interface.h"

using logic_module_name = std::optional<std::string>;
using logic_module_ctx = std::optional<svk_logic_module_details_t *>;

class logic_module_manager {
 private:
  struct logic_module_context {
    std::optional<void *> module_so_handle;
    logic_module_ctx module_details;
    ~logic_module_context() {
      if (module_details) {
        if ((*module_details)->cleanup_logic_module) {
          (*module_details)->cleanup_logic_module(nullptr);
        }
        free(*module_details);
      }
      if (module_so_handle) {
        dlclose(*module_so_handle);
      }
    }
  };
  std::map<std::string, std::unique_ptr<logic_module_context>>
      logic_modules_map;
  std::mutex modules_manager_lock;

 public:
  logic_module_manager() = default;
  ~logic_module_manager() = default;

  logic_module_name load_logic_module(const std::string &logic_module_location,
                                      const std::string &feature_name);
  void unload_logic_module(const std::string &logic_module_name);
  logic_module_ctx get_logic_module_details(
      const std::string &logic_module_name);

  std::optional<std::vector<std::string>> get_loaded_modules(void) {
    std::vector<std::string> modules;
    std::scoped_lock lk(modules_manager_lock);
    for (const auto &module_entry : logic_modules_map) {
      modules.push_back(module_entry.first);
    }
    if (modules.size() == 0) {
      return std::nullopt;
    }
    return modules;
  }
};

#endif  // _LOGIC_MODULE_MANAGER_HPP_
