#include <unistd.h>

#include <cerrno>

#include "svk_logger.h"
#include "svk_zmq_api.h"

std::string g_zmq_pub_feature_name;
using namespace std;

#define PUB_SOCKET_INITIALIZATION_TIMEOUT 5

void log_message_publisher(level_E level, std::string log_msg) {
  if (g_zmq_pub_feature_name.length() > 0) {
    svk_logger(g_zmq_pub_feature_name.c_str(), level, log_msg.c_str());
  } else {
    std::cout << log_msg << std::endl;
  }
  return;
}

int zmq_init_publisher_logger(const char *feature_name) {
  if (feature_name == nullptr) {
    std::cout << "init_publisher_logger called with nullptr. Will log all "
                 "messages to stdout"
              << std::endl;
    return 0;
  }

  if (is_svk_logger_initialized(feature_name) == true) {
    g_zmq_pub_feature_name = std::string(feature_name);
    svk_logger(feature_name, level_E::INFO,
               "Initializing the publisher logger");
  } else {
    std::cout << "Publisher don't have logger initialized for feature "
              << feature_name << std::endl;
    std::cout << "Will log all messages to stdout" << std::endl;
  }

  return 0;
}

int zmq_init_publisher(void **ctx, void **publisher, const char *ip_addr,
                       const char *port) {
  std::string log_msg;

  if (ctx == nullptr || publisher == nullptr) {
    log_message_publisher(level_E::ERROR,
                          "Input given for context/publisher is of null type");
    return -1;
  }

  if (ip_addr == nullptr || port == nullptr) {
    log_message_publisher(level_E::ERROR,
                          "Input args IP address or port is of null type");
    return -1;
  }

  if (strlen(ip_addr) == 0 || strlen(port) == 0) {
    log_message_publisher(level_E::ERROR, "IP Address / Port length is 0");
    return -1;
  }

  *ctx = zmq_ctx_new();
  if (!*ctx) {
    log_msg = "ZMQ context could not be initialized: ";
    log_msg += strerror(errno);
    log_message_publisher(level_E::ERROR, log_msg);
    return -1;
  }

  *publisher = zmq_socket(*ctx, ZMQ_PUB);
  if (!*publisher) {
    log_msg = "ZMQ publisher socket could not be created: ";
    log_msg += strerror(errno);
    log_message_publisher(level_E::ERROR, log_msg);
    return -1;
  }

  string bind_addr = "tcp://" + string(ip_addr) + ":" + string(port);
  if (zmq_bind(*publisher, bind_addr.c_str()) == -1) {
    log_msg = "zmq_bind for publisher socket failed: ";
    log_msg += strerror(errno);
    log_message_publisher(level_E::ERROR, log_msg);
    return -1;
  }

  // Sleep for few seconds before the subscriber to publisher connection is
  // established
  sleep(PUB_SOCKET_INITIALIZATION_TIMEOUT);

  return 0;
}

int zmq_publish_data(void *publisher, payload_header *payload_hdr,
                     uint8_t *payload_data) {
  std::string log_msg;

  if (!publisher) {
    log_message_publisher(level_E::ERROR, "Invalid publisher socket given");
    return -1;
  }
  if (!payload_hdr || !payload_data) {
    log_message_publisher(level_E::ERROR,
                          "Topic hdr or payload_data is of null type");
    return -1;
  }
  if (payload_hdr->payload_len == 0) {
    log_message_publisher(level_E::ERROR, "payload_hdr payload length is zero");
    return -1;
  }

  int data_size;

  data_size =
      zmq_send(publisher, payload_hdr, sizeof(payload_header), ZMQ_SNDMORE);
  if (data_size == -1) {
    log_msg = "ZMQ send topic header failed: ";
    log_msg += strerror(errno);
    log_message_publisher(level_E::ERROR, log_msg);
    return -1;
  }

  data_size = zmq_send(publisher, payload_data, payload_hdr->payload_len, 0);
  if (data_size == -1) {
    log_msg = "ZMQ send data failed: ";
    log_msg += strerror(errno);
    log_message_publisher(level_E::ERROR, log_msg);
    return -1;
  }

  return data_size;
}

int zmq_cleanup_publisher(void *ctx, void *socket) {
  int rc = -1;

  if (socket == nullptr || ctx == nullptr) {
    log_message_publisher(level_E::ERROR,
                          "zmq socket or context is of null type");
    return rc;
  }
  rc = zmq_close(socket);
  rc = zmq_ctx_term(ctx);
  log_message_publisher(level_E::INFO, "zmq socket or context cleanup done");
  return rc;
}
