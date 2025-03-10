#ifndef __CXL_PLUGIN_SC_SERVICER_H__
#define __CXL_PLUGIN_SC_SERVICER_H__

extern "C" {
#include "jansson.h"
}
#include <bits/stdc++.h>

#include <cmath>
#include <functional>
#include <string>
#include <unordered_map>

#include "framework_downstream.h"
#include "svk_logger.hpp"
#include "types.h"

#define CXL_CONF_FILE "cxl.conf"
#define INPUT_CONF_FILE "input.conf"
#define LOG_CONF_FILE "log.conf"

const std::unordered_map<std::string, std::string> tokenize(std::string input);

const std::unordered_map<std::string, std::string> token_helper(
    std::string input);

std::string ListDevices(std::string input);

std::string ListHosts(std::string input);

std::string AttachMemory(std::string input);

std::string DetachMemory(std::string input);

std::string SetupInfo(std::string input);

int get_ip_address(const std::string& filename, std::string& out_ip);

json_t* direct_config(const std::string& config_path);

json_t* load_json_config(const std::string& config_path);

std::string StartTuning(std::string input);

std::string StopTuning(std::string input);

int process_fabric_manager(json_t* fabric_manager);

void create_dev_cmmb(json_t* config);

extern const std::unordered_map<std::string, std::function<void(json_t*)>>
    factory_map;

int init_log(const std::string& config_file);

extern "C" {
int init_cxl_plugin();
}

#endif
