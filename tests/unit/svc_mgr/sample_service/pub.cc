#include "pub.h"

#include <assert.h>
#include <pthread.h>
#include <zmq.h>

#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>

static void *_run(void *arg) {
  int rc;
  Publisher *pub = (Publisher *)arg;
  /* read from the queue */
  while (!pub->p_stop) {
    rc = zmq_send(pub->p_pub, "Host1/mem/capacity:1.5T",
                  std::strlen("Host1/mem/capacity:1.5T"), 0);
    assert(rc == std::strlen("Host1/mem/capacity:1.5T"));
  }

  return pub;
}

int register_svk_service(ServiceManager *svc_mgr) {
  std::cout << "Registering publisher service" << std::endl;
  Publisher *pub = new Publisher(svc_mgr, "tcp://127.0.0.1", 5556, 10);
  svc_mgr->ServiceAdd(pub);

  return 0;
}

Publisher::Publisher(ServiceManager *svc_mgr, std::string bind_addr,
                     uint64_t bind_port, uint32_t q_len) {
  int rc;

  p_svc_mgr = svc_mgr;
  p_addr = bind_addr;
  p_port = bind_port;
  p_qlen = q_len;
  p_stop = false;

  p_context = zmq_ctx_new();
  p_pub = zmq_socket(p_context, ZMQ_PUB);
  std::string endpoint = std::string("tcp://") + p_addr + std::string(":") +
                         std::to_string(p_port);
  rc = zmq_bind(p_pub, endpoint.c_str());
  if (rc != 0) {
    std::string msg = std::string("Failed to initialize publisher") +
                      std::string(", rc: ") + std::to_string(rc);
    throw std::invalid_argument(msg.c_str());
  }

  Service(std::string("publisher"), _run);
}

int Publisher::ServiceStart() {
  int rc;

  rc = Service::ServiceStart();
  if (rc != 0)
    throw std::invalid_argument(std::string("Failed to start publisher") +
                                std::string(", rc: ") + std::to_string(rc));
  return rc;
}

void Publisher::ServiceStop(void) {
  p_stop = true;
  Service::ServiceStop();
  zmq_close(p_pub);
  zmq_ctx_destroy(p_context);
}
