#include <chrono>
#include <errno.h>
#include <stdexcept>
#include <iostream>
#include <sstream>
#include <string>

#include "cme_publisher.h"
#include "framework_extern.h"
#include "cme_logger.h"
#include "cme_utils.h"

using namespace std;

const std::string topic = "events";

int publish_cme_event(struct cme_event& event_obj)
{
        CME_ENTRY();
        int ret = -1;
        std::string cme_event_json_string = event_obj.event_json.dump();
        CME_LOG("INFO",  "Publishing CME event: size=", (uint64_t)cme_event_json_string.size());
        CME_LOG("INFO",  cme_event_json_string);
        ret = publish_event_data_to_core((char*)topic.c_str(), (uint8_t *)cme_event_json_string.c_str(), (uint64_t)cme_event_json_string.size());
        return ret;
}