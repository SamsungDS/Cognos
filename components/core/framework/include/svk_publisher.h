#ifndef __SVK_PUB_SUB_H__
#define __SVK_PUB_SUB_H__

#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

/**
 * @brief Initialize publisher service. The publisher is binded to the
 * ip_address and the port mentioned under the "pubsub" section in the json file
 *
 * @param config_json_file JSON config file with the pubsub section of the
 * format
 * {
 *   "pubsub": {
 *      # This field is to add future transport types
 *      # like grpc if supported
 *      "transport_type": "zmq",
 *      # Wild card IP Address of the node agent
 *      "ip_address": "0",
 *      # Port number of the node agent to publish/subscribe
 *      "port": <PORT>,
 *      # Default topics used by the feature modules.
 *      # Can be added more in future
 *      "topics": ["metrics", "alerts", "events"]
 *    }
 * }
 *
 * @return int 0 on success, -1 on failure
 */
int initialize_publisher(const char* config_json_file);

/**
 * @brief Publish the data with the given topic.
 *
 * TODO: Need to add support where the function expects total event data
 * (event_header + event_payload) as part of payload_data
 *
 * @param topic Topic for the subscriber to receive data
 * @param payload_data Payload data buffer pointer
 * @param data_len Data length of the payload
 * @return int 0 on success, -1 on failure
 */
int publish_data(char* topic, uint8_t* payload_data, uint64_t data_len);

/**
 * @brief Cleanup the publisher
 *
 * @return int 0 on success, -1 on failure
 */

int cleanup_publisher();

#endif /*__SVK_PUB_SUB_H__*/
