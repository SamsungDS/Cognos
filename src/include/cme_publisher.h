#ifndef __CME_PUBLISHER_H__
#define __CME_PUBLISHER_H__

#include <map>
#include <mutex>
#include <unordered_map>
#include <string>
#include <nlohmann/json.hpp>

int publish_cme_event(const std::string&, const nlohmann::json &, const std::string&);

#endif

