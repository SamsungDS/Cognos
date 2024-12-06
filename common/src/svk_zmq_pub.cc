#include "svk_zmq_api.h"

using namespace std;

int initialize_pub(void **ctx, void **publisher, const char *ip_addr,
                   const char *port) {
  *ctx = zmq_ctx_new();
  if (!*ctx) {
    cout << "ZMQ context could not be initialized: " << strerror(errno) << endl;
    return -1;
  }

  *publisher = zmq_socket(*ctx, ZMQ_PUB);
  if (!*publisher) {
    cout << "ZMQ publisher socket could not be created: " << strerror(errno)
         << endl;
    return -1;
  }

  string bind_addr = "tcp://" + string(ip_addr) + ":" + string(port);
  if (zmq_bind(*publisher, bind_addr.c_str()) == -1) {
    cout << "zmq_bind for publisher socket failed: " << strerror(errno) << endl;
    return -1;
  }

  return 0;
}

int publish(void **publisher, const char *topic, svk_slat_logic_output *data) {
  void *p = *publisher;
  if (!p) {
    cout << "Invalid publisher socket given." << endl;
    return -1;
  }
  if (!data) {
    cout << "Invalid data given." << endl;
    return -1;
  }
  char buffer[sizeof(svk_slat_logic_output)];
  int len = sizeof(svk_slat_logic_output);
  int topic_size, data_size;

  topic_size =
      zmq_send(p, topic, strnlen(topic, MAX_TOPIC_LEN - 1), ZMQ_SNDMORE);
  if (topic_size == -1) {
    cout << "ZMQ send topic failed." << endl;
    return -1;
  }

  memcpy(buffer, data, len);
  data_size = zmq_send(p, buffer, len, 0);
  if (data_size == -1) {
    cout << "ZMQ send data failed." << endl;
    return -1;
  }

  return topic_size + data_size;
}

int cleanup_zmq(void **ctx, void **socket) {
  if (*socket) {
    zmq_close(*socket);
    if (*ctx) {
      zmq_ctx_destroy(*ctx);
      return 0;
    }
  }
  return -1;
}
