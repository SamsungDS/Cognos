#ifndef __SC_SERVICER_INTERNAL_H__
#define __SC_SERVICER_INTERNAL_H__

#include <bits/stdc++.h>

#include <cmath>
#include <functional>
#include <string>
#include <unordered_map>

#include "types.h"

std::string ListDevices(std::string input);

std::string ListHosts(std::string input);

std::string AttachMemory(std::string input);

std::string DetachMemory(std::string input);

std::string SetupInfo(std::string input);

std::string get_ip_address(const std::string& filename);

json_t* direct_config(const std::string& config_path);

json_t* load_json_config(const std::string& config_path);

int process_fabric_manager(json_t* fabric_manager);

extern const std::unordered_map<std::string, std::function<void(json_t*)>>
    factory_map;

json_t* parse_input_config(std::string& buffer);

bool is_file_empty_or_missing(const std::string& file_path);

bool is_valid_ip(const std::string& ip_address);

bool process_json_request(const std::string& input_str, std::string& command,
                          std::unordered_map<std::string, std::string>& params);

int a1_init();

std::string handle_list_devices(
    const std::unordered_map<std::string, std::string>& params);
std::string handle_get_device_info(
    const std::unordered_map<std::string, std::string>& params);
std::string handle_get_device_stats(
    const std::unordered_map<std::string, std::string>& params);

std::string handle_get_device_metrics(
    const std::unordered_map<std::string, std::string>& params);
#endif
