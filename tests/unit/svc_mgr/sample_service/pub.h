#ifndef __PUB_H__
#define __PUB_H__

#include <string>

#include "svc.h"
#include "svc_mgr.h"

class Publisher : public Service {
 public:
  Publisher(ServiceManager *mgr, std::string bind_addr, uint64_t bind_port,
            uint32_t q_len);
  int publish(std::string topic_prefix, std::string data);
  int ServiceStart(void);
  void ServiceStop(void);
  void *p_pub;
  bool p_stop;

 private:
  ServiceManager *p_svc_mgr;
  std::string p_addr;
  uint64_t p_port;
  uint32_t p_qlen;
  void *p_context;
};
#endif
