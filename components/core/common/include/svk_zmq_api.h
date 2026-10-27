#ifndef __SVK_ZMQ_API_H__
#define __SVK_ZMQ_API_H__

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <zmq.h>

#include <chrono>
#include <iostream>
#include <stdexcept>
#include <string>
#include <zmq.hpp>

#define MAX_TOPIC_LEN 64

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
  char topic[MAX_TOPIC_LEN];
  uint64_t payload_len;
} payload_header;

/** ZMQ Subscriber APIs */

/**
 * @brief Initialize ZMQ subscriber logger with the feature_name.
 *
 * @param feature_name Feature name with which the svk_logger is initialized
 */
int zmq_init_subscriber_logger(const char *feature_name);

/**
 * @brief Initialize subscriber service
 *
 * @param ctx reference to handle which will be set to new zmq context
 * @param socket reference to handle which will be set to new zmq publisher
 *                  socket
 * @param ip_addr IP address to connect to as a string
 * @param port Port as a string
 * @param topic topic string to subscribe (Receives data that matches with the
 * topic only). If nullptr provided, it receives all the data sent over this
 * subscriber
 * @return int 0 on success, -1 on failure
 */
int zmq_init_subscriber(void **ctx, void **socket, const char *ip_addr,
                        const char *port, const char *topic);

/**
 * @brief Set filter for the given subscriber, which will only pick up messages
 * from publishers that use the same topic This can be called multiple times to
 * add different filters on the messages for the same subscriber
 *
 * @param socket reference to socket handle for setting the filter
 * @param topic topic string to subscribe (Receives data that matches with the
 * topic only)
 * @return int 0 on success, -1 on failure
 */
int zmq_subscribe_topic(void *socket, const char *topic);

/**
 * @brief add the new publisher endpoint for the given subscriber
 *
 * @param socket reference to socket handle to listen on given IP
 * @param addr IP address to connect to as string
 * @param port port to use as string
 * @return int 0 on success, -1 on failure
 */
int zmq_add_publisher_endpoint_to_subscriber(void *socket, const char *addr,
                                             const char *port);

/**
 * @brief Retrieve data from publisher. This will receive a multipart message
 * comprised of a payload_header and data and the data will be put into given
 * pointer on success. In the blocking mode, the socket will be in blocking
 * state until there is data on the socket or the subscriber socket/context
 * is closed.
 *
 * @param socket reference to socket handle to receive data from
 * @param data_buffer pointer to the incoming publisher's data
 * @param data_buffer_len Maximum amount of data to copy into the buffer
 * @param blocking_flag blocking mode (true) or non-blocking mode (false)
 * @return int Amount of bytes read data size on success, -1 if error or
 * the data received is bigger than the buffer allocated. -ENOTSOCK when the
 * subscriber socket/context is closed.
 */
int zmq_receive_data(void *socket, uint8_t *data_buffer,
                     uint64_t data_buffer_len, bool blocking_flag);

/**
 * @brief Close the subscriber socket and free the resources
 *
 * @param ctx reference to context created as part of initialize_sub
 * @param socket reference to socket handle to receive data from
 * @return 0 on success, -1 if error */
int zmq_cleanup_subscriber(void *ctx, void *socket);

/** Publisher APIs */

/**
 * @brief Initialize ZMQ publisher logger with the feature_name.
 *
 * @param feature_name Feature name with which the svk_logger is initialized
 */

int zmq_init_publisher_logger(const char *feature_name);

/**
 * @brief Initialize publisher service
 *
 * @param ctx reference to handle which will be set to new zmq context
 * @param socket reference to handle which will be set to new zmq publisher
 *                  socket
 * @param ip_addr IP address to bind to as string
 * @param port port to use as string
 * @return int 0 on success, -1 on failure
 */
int zmq_init_publisher(void **ctx, void **socket, const char *ip_addr,
                       const char *port);

/**
 * @brief Publish data to given topic. Subscribers that filter this topic will
 * pick up this data
 *
 * @param socket reference to socket to send data across
 * @param hdr contains the topic (fixed size) and the payload length (variable)
 * to send
 * @param payload_data output data (payload) to publish
 * @return int amount of bytes sent data size if successful, -1 if
 * failure
 */
int zmq_publish_data(void *socket, payload_header *hdr, uint8_t *payload_data);

/**
 * @brief close the socket and free up the resources associated
 * @param ctx reference to handle which will be set to new zmq context
 * @param socket reference to handle which will be set to new zmq publisher
 *                  socket
 * @return int 0 on success, -1 if failure
 */
int zmq_cleanup_publisher(void *ctx, void *socket);

#ifdef __cplusplus
}
#endif

#endif /*__SVK_ZMQ_API_H__*/
