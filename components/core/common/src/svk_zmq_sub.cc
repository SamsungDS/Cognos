#include "svk_logger.h"
#include "svk_zmq_api.h"

using namespace std;
std::string g_zmq_sub_feature_name;

void log_message_subscriber(level_E level, std::string log_msg) {
  if (g_zmq_sub_feature_name.length() > 0) {
    svk_logger(g_zmq_sub_feature_name.c_str(), level, log_msg.c_str());
  } else {
    std::cout << log_msg << std::endl;
  }
  return;
}

int zmq_init_subscriber_logger(const char *feature_name) {
  if (feature_name == nullptr) {
    std::cout << "init_subscriber_logger called with nullptr. Will log all "
                 "messages to stdout"
              << std::endl;
    return 0;
  }

  if (is_svk_logger_initialized(feature_name) == true) {
    g_zmq_sub_feature_name = std::string(feature_name);
    svk_logger(feature_name, level_E::INFO,
               "Initializing the subscriber logger");
  } else {
    std::cout << "subscriber don't have logger initialized for feature "
              << feature_name << std::endl;
    std::cout << "Will log all messages to stdout" << std::endl;
  }

  return 0;
}

int zmq_init_subscriber(void **ctx, void **subscriber, const char *ip_addr,
                        const char *port, const char *topic) {
  std::string log_msg;

  if (ctx == nullptr || subscriber == nullptr) {
    log_message_subscriber(
        level_E::ERROR, "Input given for context/subscriber is of null type");
    return -1;
  }

  if (ip_addr == nullptr || port == nullptr) {
    log_message_subscriber(level_E::ERROR,
                           "Input args IP address or port is of null type");
    return -1;
  }

  *ctx = zmq_ctx_new();

  if (*ctx == nullptr) {
    log_msg = "ZMQ context could not be initialized: ";
    log_msg += strerror(errno);
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  *subscriber = zmq_socket(*ctx, ZMQ_SUB);
  if (*subscriber == nullptr) {
    log_msg = "ZMQ publisher socket could not be created: ";
    log_msg += strerror(errno);
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  if (zmq_add_publisher_endpoint_to_subscriber(*subscriber, ip_addr, port) ==
      -1) {
    log_msg = "zmq_connect for subscriber socket failed: ";
    log_msg += strerror(errno);
    log_message_subscriber(level_E::ERROR, log_msg);

    return -1;
  }

  int rc = -1;
  if (topic == nullptr || strlen(topic) == 0) {
    // No topic been given. Set to receive all messages
    rc = zmq_subscribe_topic(*subscriber, "");
  } else {
    rc = zmq_subscribe_topic(*subscriber, topic);
  }

  return rc;
}

int zmq_subscribe_topic(void *subscriber, const char *topic) {
  std::string log_msg;
  log_msg = "Setting the socket filter to " + std::string(topic);
  log_message_subscriber(level_E::INFO, log_msg);

  return zmq_setsockopt(subscriber, ZMQ_SUBSCRIBE, topic,
                        strnlen(topic, MAX_TOPIC_LEN));
}

int zmq_add_publisher_endpoint_to_subscriber(void *subscriber, const char *addr,
                                             const char *port) {
  std::string endpoint = "tcp://" + std::string(addr) + ":" + std::string(port);
  std::string log_msg;
  log_msg = "Connecting the subscriber to " + endpoint;
  log_message_subscriber(level_E::INFO, log_msg);

  int rc = zmq_connect(subscriber, endpoint.c_str());
  return rc;
}

// This function gets data from the socket. It is an internal function
// assuming the data is readily available on the socket.
static int get_data(void *subscriber, uint8_t *data_buffer,
                    uint64_t data_buffer_len, bool blocking_flag) {
  payload_header payload_hdr;
  int topic_size, data_size, recv_more;
  size_t opt_len = sizeof(int);
  int flags = ZMQ_DONTWAIT;
  std::string log_msg;

  if (subscriber == nullptr) {
    log_message_subscriber(level_E::ERROR, "subscriber is not valid");
    return -1;
  }
  if (data_buffer == nullptr || data_buffer_len == 0) {
    log_message_subscriber(level_E::ERROR,
                           "Data buffer is null or zero length given");
    return -1;
  }

  if (blocking_flag == true) {
    flags = 0;
  }

  // Receive topic first, check/receive data
  topic_size =
      zmq_recv(subscriber, &payload_hdr, sizeof(payload_header), flags);
  if (topic_size == -1) {
    log_msg = "zmq_recv couldn't receive message: ";
    log_msg += strerror(errno);
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  log_msg = "received topic header of size " + to_string(topic_size) +
            " topic " + std::string(payload_hdr.topic);
  log_message_subscriber(level_E::DEBUG, log_msg);

  // Check for data
  zmq_getsockopt(subscriber, ZMQ_RCVMORE, &recv_more, &opt_len);
  // receive data
  if (recv_more == false) {
    log_msg = "zmq subscriber couldn't find data in received message";
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  data_size = zmq_recv(subscriber, data_buffer, data_buffer_len, 0);
  if (data_size == -1) {
    log_msg = "zmq_recv returned error while retrieving data, errno: ";
    log_msg += strerror(errno);
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  if (data_size < (int)payload_hdr.payload_len) {
    log_msg = "zmq_recv got data of size " + std::to_string(data_size) +
              " less than the expected size " +
              std::to_string(payload_hdr.payload_len);
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  log_msg = "received data size " + std::to_string(data_size);
  log_message_subscriber(level_E::DEBUG, log_msg);

  if (data_size > (int)data_buffer_len) {
    log_msg =
        "zmq_recv received truncated message because of less buffer. Received "
        "[" +
        std::to_string(data_size) + "] than expected - [" +
        std::to_string(data_buffer_len) + "]";
    log_message_subscriber(level_E::ERROR, log_msg);
    return -1;
  }

  return data_size;
}

int zmq_receive_data(void *subscriber, uint8_t *data_buffer,
                     uint64_t data_buffer_len, bool blocking_flag) {
  int size = -1;
  std::string log_msg;

  if (subscriber == nullptr) {
    log_message_subscriber(level_E::ERROR, "subscriber is not valid");
    return -1;
  }

  if (data_buffer == nullptr || data_buffer_len == 0) {
    log_message_subscriber(level_E::ERROR,
                           "Data buffer is null or zero length given");
    return -1;
  }

  if (blocking_flag == false) {
    size = get_data(subscriber, data_buffer, data_buffer_len, false);
    return size;
  }

  zmq::pollitem_t items[1];
  items[0] = {subscriber, 0, ZMQ_POLLIN, 0};
  try {
    while (true) {
      int rc = zmq::poll(&items[0], 1, std::chrono::milliseconds(1000));
      if (rc > 0) {
        if (items[0].revents && ZMQ_POLLIN) {
          size = get_data(items[0].socket, data_buffer, data_buffer_len, false);
        }
        break;
      } else if (rc == 0) {  // timeout
        continue;
      } else {  // Failure or interrupted
        log_msg = "Subscriber receiver got interrupted";
        log_message_subscriber(level_E::ERROR, log_msg);
        return -errno;
      }
    }
  } catch (zmq::error_t &e) {
    std::string errorMessage = e.what();
    log_msg = "Exception in the subscriber poller - " + errorMessage;
    log_message_subscriber(level_E::ERROR, log_msg);

    return -errno;
  }

  return size;
}

int zmq_cleanup_subscriber(void *ctx, void *subscriber) {
  int rc = -1;
  int linger = 0;
  std::string log_msg;

  if (subscriber == nullptr || ctx == nullptr) {
    log_message_subscriber(level_E::ERROR,
                           "zmq subscriber socket or context is of null type");
    return rc;
  }
  // Returns 0 on success or -ETERM if already closed in ctxt
  rc = zmq_setsockopt(subscriber, ZMQ_LINGER, &linger, sizeof(linger));
  log_msg =
      "zmq subscriber close linger socket with ret value " + std::to_string(rc);
  log_message_subscriber(level_E::INFO, log_msg);
  rc = zmq_close(subscriber);
  log_msg = "zmq subscriber socket closed with ret value " + std::to_string(rc);
  log_message_subscriber(level_E::INFO, log_msg);
  rc = zmq_ctx_term(ctx);
  log_msg = "zmq_ctx_term for subscriber with ret value " + std::to_string(rc);
  log_message_subscriber(level_E::INFO, log_msg);
  return rc;
}
