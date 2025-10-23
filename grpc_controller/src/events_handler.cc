#include <cstring>
#include <iostream>
#include <mutex>
#include <vector>

#include "circular_queue.h"
#include "grpc_controller.h"
#include "nlohmann/json.hpp"
#include "svk_logger.h"

using json = nlohmann::json;

// Queue is initialized to hold 4K events by default
CircularQueue<json> g_events_data_queue(MAX_EVENTS_IN_QUEUE);
std::mutex g_events_data_mutex;

// Function to set the new size of the events queue
void resize_event_queue(uint64_t queue_size) {
  CircularQueue<json> new_event_queue(queue_size);
  json event_data;
  std::lock_guard<std::mutex> lock(g_events_data_mutex);

  // Swap the contents
  while (!g_events_data_queue.isEmpty()) {
    event_data = g_events_data_queue.dequeue();
    new_event_queue.enqueue(event_data);
  }

  g_events_data_queue = std::move(new_event_queue);
  return;
}

int insert_event_to_controller_map(const json event_data) {
  std::string logger_str;
  // Extract event header information
  auto event_header = event_data.value("event_header", json{});
  std::string node_name = event_header.value("node_name", "");

  // Node name is the minimum requirement
  if (node_name.empty()) {
    logger_str = "Failed to insert the event because of missing node name - " +
                 event_data.dump();
    svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::ERROR,
               logger_str.c_str());
    return -1;
  }

  std::lock_guard<std::mutex> lock(g_events_data_mutex);

  g_events_data_queue.enqueue(event_data);

  logger_str =
      "Inserted the event to the Controller's event_map - " + event_data.dump();
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::TRACE, logger_str.c_str());

  return 0;
}

int get_events_from_controller_map(const std::string& cluster_name,
                                   const std::string& node_name,
                                   uint64_t min_epoch, uint64_t num_events,
                                   json& event_data) {
  std::string logger_str;
  json events = json::array();
  uint64_t event_count = 0;
  json event;

  std::lock_guard<std::mutex> lock(g_events_data_mutex);

  logger_str =
      "get_events_from_controller_map called with params- cluster_name: " +
      cluster_name + ", node_name: " + node_name +
      ", min_epoch: " + std::to_string(min_epoch) +
      ", num_events: " + std::to_string(num_events);
  svk_logger(CONTROLLER_LOGGER_MODULE_NAME, level_E::TRACE, logger_str.c_str());

  for (auto it = g_events_data_queue.begin(); it != g_events_data_queue.end();
       ++it) {
    event = *it;
    if (cluster_name.length() &&
        event["event_header"]["cluster_name"] != cluster_name) {
      continue;
    }
    if (node_name.length() && event["event_header"]["node_name"] != node_name) {
      continue;
    }
    if (min_epoch > 0 && event["event_payload"]["timestamp"] < min_epoch) {
      continue;
    }
    events.push_back(event);
    event_count++;
    if (event_count >= num_events) {
      break;
    }
  }

  event_data = std::move(events);
  return 0;
}

int clear_all_events_from_controller_map() {
  std::lock_guard<std::mutex> lock(g_events_data_mutex);
  while (!g_events_data_queue.isEmpty()) {
    g_events_data_queue.dequeue();
  }
  return 0;
}