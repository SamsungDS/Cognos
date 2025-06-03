#ifndef _LOGIC_MODULE_MANAGER_HPP_
#define _LOGIC_MODULE_MANAGER_HPP_

#include <map>
#include <optional>

#include "logic_interface/svk_logic_interface.h"

using logic_module_name = std::optional<std::string>;
using logic_module_ctx = std::optional<svk_logic_module_details_t *>;

class logic_module_manager {
 private:
  std::map<std::string, svk_logic_module_details_t *> logic_modules_map;

 public:
  logic_module_manager() = default;

  ~logic_module_manager() {
    for (auto &[name, logic_details] : this->logic_modules_map) {
      logic_details->cleanup_logic_module(nullptr);
      free(logic_details);
    }

    this->logic_modules_map.clear();
  }

  logic_module_name load_logic_module(const std::string &logic_module_location,
                                      const std::string &feature_name);
  logic_module_ctx get_logic_module_details(
      const std::string &logic_module_name);
};

#endif  // _LOGIC_MODULE_MANAGER_HPP_
