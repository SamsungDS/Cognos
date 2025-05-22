#include "svk_publisher.h"

#include <sys/stat.h>

#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <cstring>
#include <iostream>
#include <map>
#include <mutex>
#include <string>
#include <tuple>

#include "framework_defs.hpp"
#include "svk_logger.h"
#include "svk_pub_sub_struct.h"
#include "svk_zmq_api.h"

typedef struct publisher_t {
  void* socket;
  void* context;
  int (*init_logger_fn)(const char* feature);
  int (*init_pub_fn)(void** ctx, void** socket, const char* ip_addr,
                     const char* port);
  int (*publish_data_fn)(void* socket, payload_header* hdr,
                         uint8_t* payload_data);
  int (*cleanup_pub_fn)(void* ctx, void* socket);
} publisher;

publisher g_publisher;
std::mutex pub_mtx;  // Mutex object
std::vector<std::string> g_topics_vector;

static int read_config_file(const char* config_file, std::string& ip_address,
                            std::string& port, std::string& transport_type,
                            std::vector<std::string>& topics_vector) {
  int rc = -1;
  std::string log_msg;
  boost::property_tree::ptree pt;
  struct stat fstat;

  if (config_file == nullptr || strlen(config_file) == 0 ||
      stat(config_file, &fstat) != 0) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Invalid config file passed to initialize_publisher");
    return rc;
  }

  try {
    boost::property_tree::read_json(config_file, pt);
  } catch (boost::property_tree::json_parser_error& e) {
    log_msg = "Unable to read SVK config. Error -> " + std::string(e.what());
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg.c_str());
    return rc;
  }
  ip_address = pt.get<std::string>("pubsub.ip_address", DEFAULT_PUB_IP_ADDR);
  port = std::to_string(pt.get<int>("pubsub.port", DEFAULT_PUB_SUB_PORT));
  transport_type = pt.get<std::string>("pubsub.transport_type", "zmq");
  log_msg =
      "initialize_publisher called with transport type:" + transport_type +
      " IP: " + ip_address + " Port: " + port;
  svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg.c_str());

  try {
    for (const auto& topic_item : pt.get_child("pubsub.topics")) {
      std::string topic_s = topic_item.second.get_value<std::string>();
      topics_vector.push_back(topic_s);
      log_msg = "Topic added to publisher " + topic_s;
      svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg.c_str());
    }
  } catch (boost::property_tree::ptree_bad_path& e) {
    log_msg =
        "Unable to read the topics section under pubsub of SVK config. Error "
        "-> " +
        std::string(e.what());
    svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg.c_str());
  }

  return 0;
}

int initialize_publisher(const char* config_file) {
  std::string log_msg;
  std::string transport_type;
  std::string ip_s;
  std::string port_s;
  int rc = -1;

  rc = read_config_file(config_file, ip_s, port_s, transport_type,
                        g_topics_vector);
  if (rc != 0) {
    return rc;
  }

  pub_mtx.lock();
  if (g_publisher.socket) {
    // socket already initialized
    rc = 0;
    pub_mtx.unlock();
    log_msg = "Found the publisher socket already created for the IP " + ip_s +
              " port " + port_s;
    svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg.c_str());
    return rc;
  }

  if (transport_type == "zmq") {
    g_publisher.init_logger_fn = &zmq_init_publisher_logger;
    g_publisher.init_pub_fn = &zmq_init_publisher;
    g_publisher.cleanup_pub_fn = &zmq_cleanup_publisher;
    g_publisher.publish_data_fn = &zmq_publish_data;
    void* zmq_socket = nullptr;
    void* zmq_context = nullptr;

    rc = g_publisher.init_logger_fn(CORE_LOGGER_NAME);
    if (rc != 0) {
      svk_logger(
          CORE_LOGGER_NAME, level_E::ERROR,
          "Error in initializing the logger in zmq_init_publisher_logger. Will "
          "be putting the ZMQ logs to stdout");
    }

    // Socket not found. Create one and update the map
    rc = g_publisher.init_pub_fn(&zmq_context, &zmq_socket, ip_s.c_str(),
                                 port_s.c_str());
    g_publisher.socket = zmq_socket;
    g_publisher.context = zmq_context;

  } else {
    pub_mtx.unlock();
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, "Invalid transport type");
    rc = -1;
    return rc;
  }

  pub_mtx.unlock();

  if (rc != 0) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Failed to create publisher socket");
    return rc;
  }

  log_msg = "Created a publisher socket for the IP " + ip_s + " port " + port_s;
  svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg.c_str());

  return rc;
}

int publish_data(char* topic, uint8_t* payload_data, uint64_t data_len) {
  int rc = -1;
  payload_header payload_hdr;
  std::string log_msg;

  if (payload_data == nullptr || data_len == 0) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Payload data ptr is null or the data length is 0");
    return rc;
  }

  if (g_publisher.publish_data_fn == nullptr) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Publisher functions are not initialized");
    return rc;
  }

  if (topic && strlen(topic) >= sizeof(payload_hdr.topic) - 1) {
    log_msg = "Topic " + std::string(topic) +
              " exceeds the length of expected size " +
              std::to_string(sizeof(payload_hdr.topic));
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, log_msg.c_str());
    return rc;
  }

  if (topic == nullptr || strlen(topic) == 0) {
    strcpy(payload_hdr.topic, "");
  } else {
    strcpy(payload_hdr.topic, topic);
  }

  payload_hdr.payload_len = data_len;
  uint32_t data_sent = g_publisher.publish_data_fn(g_publisher.socket,
                                                   &payload_hdr, payload_data);
  if (data_sent != data_len) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR, "Error in publishing data");
    return -1;
  }
  return 0;
}

int cleanup_publisher() {
  int rc = 0;
  std::string log_msg;

  if (g_publisher.cleanup_pub_fn == nullptr) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Publisher functions are not initialized");
    return -1;
  }

  pub_mtx.lock();
  if (g_publisher.socket) {
    rc = g_publisher.cleanup_pub_fn(g_publisher.context, g_publisher.socket);
    if (rc == 0) {
      g_publisher.context = nullptr;
      g_publisher.socket = nullptr;
      log_msg = "Successfully closed the publisher";
    }
  } else {
    log_msg = "Publisher is already closed";
  }
  pub_mtx.unlock();
  if (rc != 0) {
    svk_logger(CORE_LOGGER_NAME, level_E::ERROR,
               "Error in cleaning up the publisher");
    return rc;
  }

  svk_logger(CORE_LOGGER_NAME, level_E::INFO, log_msg.c_str());
  return rc;
}
