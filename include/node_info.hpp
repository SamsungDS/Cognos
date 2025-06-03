#ifndef __NODE_INFO_HPP__
#define __NODE_INFO_HPP__

#include <stdexcept>
#include <string>
#include <unordered_set>

#include "feature_module_conf.h"
#include "framework_downstream.h"
#include "helper_fns.hpp"
#include "svk_logger.hpp"

#define NODE_FEAT_MODULE_NAME "node"
#define NODE_FEAT_DEFAULT_LOG_FILE "/var/log/svk/svk_node_feature.log"
#define NODE_FEAT_LOGGER_DEFAULT_FILE_COUNT 10
#define NODE_FEAT_LOGGER_DEFAULT_FILE_SIZE 1048576ULL
#define NODE_FEAT_LOGGER_DEFAULT_LEVEL "INFO"
#define NODE_FEAT_LOGGER_DEFAULT_SINK_TYPE "rotating_file"
#define MAX_BUF_LEN 512

std::unordered_set<std::string> node_info_types = {
    "all", "system", "memory", "network", "cpu", "devices"};
std::unordered_set<std::string> py_log_levels = {"DEBUG", "INFO", "WARNING",
                                                 "ERROR", "CRITICAL"};
std::string py_log_level;

#ifdef BUILD_TESTING
const std::string node_feature_path = "node/";
#else
const std::string node_feature_path =
    std::string(SVK_FEATURE_MODULE_PATH) + "/" + NODE_FEAT_MODULE_NAME;
#endif

#endif /*__NODE_INFO_HPP__*/
