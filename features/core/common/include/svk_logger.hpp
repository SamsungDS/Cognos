#ifndef __SVK_LOGGER_HPP__
#define __SVK_LOGGER_HPP__
#include <unordered_map>

#include "svk_logger.h"

const std::unordered_map<std::string, level_E> log_level_map = {
    {"TRACE", level_E::TRACE},       {"DEBUG", level_E::DEBUG},
    {"INFO", level_E::INFO},         {"NOTICE", level_E::NOTICE},
    {"WARN", level_E::WARN},         {"ERROR", level_E::ERROR},
    {"CRITICAL", level_E::CRITICAL}, {"ALERT", level_E::ALERT},
    {"FATAL", level_E::FATAL},       {"OFF", level_E::OFF}};

#endif /*__SVK_LOGGER_HPP__*/