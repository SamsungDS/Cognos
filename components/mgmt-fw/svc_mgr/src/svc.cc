#include "svc.h"

#include <assert.h>

#include <cassert>
#include <iostream>

#include "svc_mgr.h"

Service::Service() {}

Service::Service(std::string name, void* (*svc_func)(void* arg)) {
  assert(!name.empty() && svc_func != NULL);

  svc_name = name;
  svc_handle = SVKThread(svc_func, this);
}

int Service::ServiceStart(void) {
  int rc;

  SVC_MGR_LOG(level_E::INFO, "Starting ", svc_name);
  rc = svc_handle.start();

  return rc;
}

void Service::ServiceStop() { svc_handle.stop(); }
