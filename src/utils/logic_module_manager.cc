#include "utils/logic_module_manager.hpp"

#include <dlfcn.h>

#include <iostream>
#include <sstream>

#include "ras_exports.h"
#include "svk_logger.hpp"

logic_module_name logic_module_manager::load_logic_module(
    const std::string &logic_module_location, const std::string &feature_name) {
  std::stringstream logger_ss;

  void *handle = dlopen(logic_module_location.c_str(), RTLD_LAZY);
  if (!handle) {
    logger_ss << "Unable to open logic module" << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    return std::nullopt;
  }

  auto details =
      (svk_logic_module_details *)malloc(sizeof(svk_logic_module_details));
  if (details == nullptr) {
    logger_ss << "Memory allocation failed for module details loading from path"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    dlclose(handle);
    return std::nullopt;
  }

  details->initialize_logic_module =
      (initialize_logic_module_dlsym)dlsym(handle, "initialize_logic_module");

  if (details->initialize_logic_module == nullptr) {
    logger_ss << "Unable to load intitalize logic module pointer while loading"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    free(details);
    dlclose(handle);
    return std::nullopt;
  }

  details->get_supported_logic_details =
      (get_supported_logic_details_dlsym)dlsym(handle,
                                               "get_supported_logic_details");

  if (details->get_supported_logic_details == nullptr) {
    logger_ss << "Unable to load get supported details pointer while loading"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    free(details);
    dlclose(handle);
    return std::nullopt;
  }

  if (details->initialize_logic_module(nullptr)) {
    logger_ss << "Initialze logic module failed while loading"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    free(details);
    dlclose(handle);
    return std::nullopt;
  }

  if (details->get_supported_logic_details(details) != SVK_STATUS_SUCCESS) {
    logger_ss << "Get supported detail call failed while loading"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    free(details);
    dlclose(handle);
    return std::nullopt;
  }

  if (strcmp(details->feature_name, feature_name.c_str()) != 0) {
    logger_ss << "Feature name mismatch for logic module"
              << "expecting" << std::string(details->feature_name)
              << "but loaded by" << feature_name << "while loading"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    free(details);
    dlclose(handle);
    return std::nullopt;
  }

  // insert logic_id/function pointers into map
  auto [iterator, inserted] = this->logic_modules_map.insert(
      make_pair(std::string(details->logic_module_name), details));
  if (!inserted) {
    logger_ss << "Failed to insert to map while loading"
              << logic_module_location;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
    free(details);
    dlclose(handle);
    return std::nullopt;
  }

  dlclose(handle);
  return std::string(details->logic_module_name);
}

// ... existing code ...

void logic_module_manager::unload_logic_module(
    const std::string &logic_module_name) {
  auto it = this->logic_modules_map.find(logic_module_name);
  if (it != this->logic_modules_map.end()) {
    // Free the details
    free(it->second);

    // Remove the module from the map
    this->logic_modules_map.erase(it);
  } else {
    std::stringstream logger_ss;
    logger_ss << "Logic module not found: " << logic_module_name;
    svk_logger(RAS_LOGGER, level_E::ERROR, logger_ss.str().c_str());
  }
}

logic_module_ctx logic_module_manager::get_logic_module_details(
    const std::string &logic_module_name) {
  auto it = this->logic_modules_map.find(logic_module_name);
  if (it != this->logic_modules_map.end()) {
    return it->second;
  }
  return nullptr;  // Return nullptr if module not found
}