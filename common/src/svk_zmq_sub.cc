#include "svk_zmq_api.h"

using namespace std;

int initialize_sub(void **ctx, void **subscriber, const char *ip_addr,
                   const char *port, const char *filter) {
  *ctx = zmq_ctx_new();
  if (*ctx == nullptr) {
    cout << "ZMQ context could not be initialized: " << strerror(errno) << endl;
    return -1;
  }

  *subscriber = zmq_socket(*ctx, ZMQ_SUB);
  if (*subscriber == nullptr) {
    cout << "ZMQ subscriber socket could not be created: " << strerror(errno)
         << endl;
    return -1;
  }

  if (connect_sub(subscriber, ip_addr, port, filter) == -1) {
    cout << "zmq_connect for subscriber socket failed: " << strerror(errno)
         << endl;
    return -1;
  }

  return 0;
}

int set_socket_filters(void **subscriber, const char *filter) {
  return zmq_setsockopt(*subscriber, ZMQ_SUBSCRIBE, filter,
                        strnlen(filter, MAX_TOPIC_LEN));
}

int connect_sub(void **subscriber, const char *addr, const char *port,
                const char *filter) {
  std::string ipaddr = "tcp://" + std::string(addr) + ":" + std::string(port);
  int rc = zmq_connect(*subscriber, ipaddr.c_str());
  if (rc) {
    return rc;
  }

  rc = set_socket_filters(subscriber, filter);
  return rc;
}

int get_data(void **subscriber, svk_slat_logic_output *data) {
  void *sub = *subscriber;
  // Add header to handle different payloads in the future
  char buffer[sizeof(svk_slat_logic_output)];
  char topic[MAX_TOPIC_LEN];

  int topic_size, data_size, recv_more;
  size_t opt_len = sizeof(int);

  // Receive topic first, check/receive data
  topic_size = zmq_recv(sub, topic, MAX_TOPIC_LEN - 1, ZMQ_DONTWAIT);
  // It is possible the return value of recv is greater than given buffer len
  // Need to null terminate properly in either case
  topic[topic_size < MAX_TOPIC_LEN ? topic_size : MAX_TOPIC_LEN - 1] = '\0';
  if (topic_size == -1) {
    cerr << "zmq_recv couldn't receive message: " << strerror(errno) << endl;
    return topic_size;
  }

  // Check for data
  zmq_getsockopt(sub, ZMQ_RCVMORE, &recv_more, &opt_len);
  // receive data
  if (recv_more) {
    data_size = zmq_recv(sub, buffer, sizeof(buffer), ZMQ_DONTWAIT);
    if (data_size == -1) {
      cerr << "zmq_recv returned error while retrieving data, check errno"
           << endl;
      return data_size;
    }
  } else {
    cerr << "zmq subscriber couldn't find data in received message" << endl;
    return -1;
  }

  // copy data to pointer
  memcpy(data, buffer, sizeof(svk_slat_logic_output));
  return topic_size + data_size;
}
