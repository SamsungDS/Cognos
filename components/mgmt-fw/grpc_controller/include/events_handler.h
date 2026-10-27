#ifndef __EVENTS_HANDLER_H__
#define __EVENTS_HANDLER_H__

#include "nlohmann/json.hpp"

using json = nlohmann::json;
const uint64_t MAX_EVENTS_IN_QUEUE = 4096;

/**
 * @brief Function to resize the event queue
 * @param queue_size New queue size
 */
void resize_event_queue(uint64_t queue_size);

/**
 * @brief  Insert the JSON event data to the controller map.
 * All the events are stored under the "event" section.
 *
 * {
 *   "events": [
 *     {
 *       "event_header": {
 *         "cluster_name": "c1",
 *         "node_name": "n1"
 *       },
 *       "event_payload": {
 *         "..": ""
 *       }
 *     }
 *   ]
 * }
 *
 * @param event_data Expects a JSON data with the fields "event_header" and
 "event_payload"
 * @return 0 on success or -1 on failure
 */
int insert_event_to_controller_map(const json event_data);

/**
 * @brief Get the events from the Controller
 *
 * @param cluster_name Name of the cluster
 * @param node_name Name of the node
 * @param min_epoch Minimum timestamp of the events to be fetched
 * @param num_events Maximum number of events to be aggregated
 * @param[out] event_data An array of events registered fpr the above input
 * requirements
 *
 * @return 0 on success or -1 on failure
 */
int get_events_from_controller_map(const std::string& cluster_name,
                                   const std::string& node_name,
                                   uint64_t min_epoch, uint64_t num_events,
                                   json& event_data);

/**
 * @brief Clears all the events from the Controller memory map
 *
 * @return 0 on success or -1 on failure
 */
int clear_all_events_from_controller_map();

#endif /*__EVENTS_HANDLER_H__*/