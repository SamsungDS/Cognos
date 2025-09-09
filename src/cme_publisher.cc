#include <chrono>
#include <errno.h>
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <string>

#include "cme_publisher.h"
#include "framework_extern.h"

using namespace std;

const std::string topic = "events";

int publish_cme_event(const std::string &app_context, const nlohmann::json &event_data, const std::string &time_stamp)
{
        int ret = -1;
        std::cout << string (__FUNCTION__) << " Started : " << app_context << " data size=" << event_data.size() << endl;
        nlohmann::json event_json;
        event_json["domain"] = "observability";
        event_json["feature_name"] = "me";
        event_json["category"] = "log";
        event_json["severity"] = "info";
        event_json["source_type"] = "application";
        event_json["source"] = app_context;
        event_json["timestamp"] = time_stamp;
        event_json["observations"] = event_data;
        std::string cme_event_json_string = event_json.dump();
        std::cout << "Publishing CME event: size=" << (uint64_t)cme_event_json_string.size() << endl << cme_event_json_string << endl;
        ret = publish_event_data_to_core((char*)topic.c_str(), (uint8_t *)cme_event_json_string.c_str(), (uint64_t)cme_event_json_string.size());
        return ret;
}