#ifndef __EVENTS_HANDLER_H__
#define __EVENTS_HANDLER_H__

#include "nlohmann/json.hpp"

using json = nlohmann::json;

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
 * @param[out] event_data An array of events registered fpr all clusters
 *
 * @return 0 on success or -1 on failure
 */
int get_events_from_controller_map(json &event_data);

/**
 * @brief Clears all the events from the Controller memory map
 *
 * @return 0 on success or -1 on failure
 */
int clear_all_events_from_controller_map();

#endif /*__EVENTS_HANDLER_H__*/