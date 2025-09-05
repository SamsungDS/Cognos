#include <cstring>
#include <iostream>
#include <mutex>
#include <vector>

#include "grpc_controller.h"
#include "nlohmann/json.hpp"
#include "svk_logger.h"

using json = nlohmann::json;

json g_events_data;
std::mutex g_events_data_mutex;

#define EVENTS "events"

int insert_event_to_controller_map(const json event_data) {
  std::string logger_str;
  // Extract event header information
  auto event_header = event_data.value("event_header", json{});
  std::string node_name = event_header.value("node_name", "");

  // Node name is the minimum requirement
  if (node_name.empty()) {
    logger_str = "Failed to insert the event to the Controller's event_map";
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return -1;
  }

  std::lock_guard<std::mutex> lock(g_events_data_mutex);
  // Insert all the events into "events" section
  if (!g_events_data.contains(EVENTS)) {
    g_events_data[EVENTS] = json::array();
  }
  g_events_data[EVENTS].push_back(event_data);

  logger_str =
      "Inserted the event to the Controller's event_map - " + event_data.dump();
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::TRACE, logger_str.c_str());

  return 0;
}

int get_events_from_controller_map(json &event_data) {
  std::string logger_str;
  std::lock_guard<std::mutex> lock(g_events_data_mutex);

  if (g_events_data.empty() || !g_events_data.contains(EVENTS)) {
    event_data = json::array();
  } else {
    event_data = g_events_data[EVENTS];
  }

  logger_str = "Events from the controller's event_map - " + event_data.dump();
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::TRACE, logger_str.c_str());
  g_events_data.clear();

  return 0;
}

int clear_all_events_from_controller_map() {
  std::lock_guard<std::mutex> lock(g_events_data_mutex);
  g_events_data.clear();
  return 0;
}