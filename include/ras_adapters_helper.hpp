#ifndef _RAS_ADAPTERS_HELPER__HPP_
#define _RAS_ADAPTERS_HELPER__HPP_

#include <fmt/format.h>

#include <nlohmann/json.hpp>
#include <optional>
#include <string>

#include "ras_device.h"
#include "ras_exports.h"
#include "svk_logger.hpp"
#include "utils/logic_module_manager.hpp"

using json = nlohmann::json;

#define MAX_OUTPUT_BUFFER_LEN (4096)

class ras_adapter_helper {
  std::optional<json> execute_adapter_sync_command(
      const std::string adapter, const std::string command) const {
    logic_module_ctx adapter_details =
        adapters->get_logic_module_details(adapter);
    if (adapter_details == std::nullopt) {
      svk_logger(RAS_LOGGER, level_E::ERROR,
                 fmt::format("Invalid adapter {}", adapter).c_str());
      return std::nullopt;
    }

    svk_logic_module_details_t *adapter_details_p = *adapter_details;
    char *out_buff[MAX_OUTPUT_BUFFER_LEN];

    svk_logic_cmd lcmd = {.out_format = nullptr, .out_format_len = 0};
    svk_logic_input linput = {.input_buffer = (uint8_t *)command.c_str(),
                              .input_len = command.length()};
    svk_logic_output loutput = {.output_buffer = (uint8_t *)out_buff,
                                .output_len = MAX_OUTPUT_BUFFER_LEN};

    snprintf(lcmd.logic_name, sizeof(lcmd.logic_name), "%s",
             adapter_details_p->logic_module_name);
    svk_status rc =
        adapter_details_p->execute_logic_sync(&lcmd, &linput, &loutput);
    std::cout << std::string((char *)loutput.output_buffer) << std::endl;
    if (rc == SVK_STATUS_SUCCESS) {
      try {
        json out_json = json::parse(loutput.output_buffer);
        return out_json;
      } catch (json::parse_error &e) {
        svk_logger(RAS_LOGGER, level_E::ERROR,
                   fmt::format("Invalid json output. Exception: {}", e.what())
                       .c_str());
        return std::nullopt;
      }
    }
    svk_logger(RAS_LOGGER, level_E::ERROR,
               fmt::format("execute sync failed for adapter {} command {}",
                           adapter, command)
                   .c_str());
    return std::nullopt;
  }

  std::optional<std::vector<std::string>> get_device_list_in_adapter(
      const std::string &adapter_name) const {
    const std::string list_devices_cmd = R"(
      {
      "command_name" : "getDeviceList",
      "command_params" : {}
      }
    )";

    auto device_list_response_o =
        execute_adapter_sync_command(adapter_name, list_devices_cmd);
    if (device_list_response_o != std::nullopt) {
      json device_list_response = *device_list_response_o;
      json device_list_json = device_list_response["result"]["deviceList"];
      std::vector<std::string> device_list(device_list_json.begin(),
                                           device_list_json.end());
      if (device_list.size() != 0) {
        return device_list;
      }
    }
    return std::nullopt;
  }

  bool check_device_in_adapter(const std::string &adapter_name,
                               device_unique_identifier device_id) const {
    auto device_list = get_device_list_in_adapter(adapter_name);
    if (device_list == std::nullopt) {
      svk_logger(
          RAS_LOGGER, level_E::INFO,
          fmt::format("No device found for adapter {}", adapter_name).c_str());
      return false;
    }
    for (auto device_name : *device_list) {
      svk_logger(
          RAS_LOGGER, level_E::INFO,
          fmt::format("Adapter: {} device name {}", adapter_name, device_name)
              .c_str());
      if (device_name == device_id) {
        return true;
      } else {
        svk_logger(RAS_LOGGER, level_E::INFO,
                   fmt::format("Adapter: {} device: {} does not match "
                               "retrieved device name {}",
                               adapter_name, device_id, device_name)
                       .c_str());
      }
    }
    return false;
  }

 public:
  std::unique_ptr<logic_module_manager> adapters;
  ras_adapter_helper() { adapters = std::make_unique<logic_module_manager>(); };

  std::optional<std::string> try_get_adapter_for_device(
      device_unique_identifier device_id) {
    auto loaded_adapters = adapters->get_loaded_modules();
    if (loaded_adapters == std::nullopt) {
      return std::nullopt;
    }
    for (auto adapter : *loaded_adapters) {
      if (check_device_in_adapter(adapter, device_id) == true) {
        return adapter;
      }
    }
    return std::nullopt;
  }
};
#endif  // _RAS_ADAPTERS_HELPER__HPP_