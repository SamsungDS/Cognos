#ifndef __CME_PUBLISHER_H__
#define __CME_PUBLISHER_H__

#include <map>
#include <mutex>
#include <unordered_map>
#include <string>
#include <nlohmann/json.hpp>

struct cme_event
{
        nlohmann::json event_json;
        
        cme_event()
        {
                event_json["domain"] ="observability";
                event_json["feature_name"] = "me";
                event_json["type"] = "event";
                event_json["tag"] = "";
                event_json["msg"] = "svkme event msg";
                event_json["category"] = "log";
                event_json["severity"] = "info";
                event_json["source_type"] = "application";
                event_json["source"] = "application";
                event_json["timestamp"] = "";
                event_json["timestamp_formatted"] = "";
                event_json["observations"] = "";
        }
};

int publish_cme_event(struct cme_event&);

#endif

