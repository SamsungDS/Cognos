#ifndef __SVK_ZMQ_API__
#define __SVK_ZMQ_API__

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <zmq.h>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>

#define MAX_TOPIC_LEN 32

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  char host_name[64];
  char app_name[64];
  char device_name[64];
  uint64_t avgLatencyus;
  uint64_t iops;
  uint64_t bandwidthGBps;
  uint64_t avgReadLatency;
  uint64_t avgWriteLatency;
  uint64_t avgUpdateLatency;
  uint64_t avgReadIOPS;
  uint64_t avgWriteIOPS;
  uint64_t avgP99Latency;  // TBD
  uint64_t ioBytesRead;
  uint64_t ioBytesWritten;
  uint64_t ioBytesRewrite;
} svk_slat_logic_output;

/** ZMQ Subscriber APIs */

/**
 * @brief Initialize subscriber service
 *
 * @param ctx reference to handle which will be set to new zmq context
 * @param publisher reference to handle which will be set to new zmq publisher
 *                  socket
 * @param ip_addr IP address to connect to as a string
 * @param port Port as a string
 * @return int 0 on success, -1 on failure
 */
int initialize_sub(void **ctx, void **subscriber, const char *ip_addr,
                   const char *port, const char *filter);

/**
 * @brief Set filter for the subscriber, which will only pick up messages from
 * publishers that use the same topic
 *
 * @param subscriber reference to socket handle for setting the filter
 * @param filter string to filter
 * @return int 0 on success, -1 on failure
 */
int set_socket_filters(void **subscriber, const char *filter);

/**
 * @brief Connect subscriber to a new IP and add a filter for the subscriber
 *
 * @param subscriber reference to socket handle to listen on given IP
 * @param addr IP address to connect to as string
 * @param port port to use as string
 * @param filter string to filter
 * @return int 0 on success, -1 on failure
 */
int connect_sub(void **subscriber, const char *addr, const char *port,
                const char *filter);

/**
 * @brief Retrieve data from publisher. This will receive a single message
 * comprised of a topic and data and the data will be put into given pointer on
 * success
 *
 * @param subscriber reference to socket handle to recieve data from
 * @param data pointer to copy data to after retrieving from publisher
 * @return int Amount of bytes read (topic + data size) on success, -1 if error
 */
int get_data(void **subscriber, svk_slat_logic_output *data);

/** Publisher APIs */

/**
 * @brief Initialize publisher service
 *
 * @param ctx reference to handle which will be set to new zmq context
 * @param publisher reference to handle which will be set to new zmq publisher
 *                  socket
 * @param ip_addr IP address to bind to as string
 * @param port port to use as string
 * @return int 0 on success, -1 on failure
 */
int initialize_pub(void **ctx, void **publisher, const char *ip_addr,
                   const char *port);

/**
 * @brief Publish data to given topic. Subscribers that filter this topic will
 * pick up this data
 *
 * @param publisher reference to socket to send data across
 * @param topic Topic to publish data to
 * @param data output data for subscriber to receive
 * @return int amount of bytes sent (topic + data size) if successful, -1 if
 * failure
 */
int publish(void **publisher, const char *topic, svk_slat_logic_output *data);

/**
 * @brief Cleanup zmq socket and context
 *
 * @return int 0 on success, -1 if failure
 */
int cleanup_zmq(void **ctx, void **socket);

#ifdef __cplusplus
}
#endif

#endif /*__SVK_ZMQ_API__*/
