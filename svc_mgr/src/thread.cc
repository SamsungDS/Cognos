#include "thread.h"

#include <cassert>
#include <iostream>

SVKThread::SVKThread() { st_state = STS_STOPPED; }

SVKThread::SVKThread(void *(*func)(void *), void *arg) {
  assert(st_state == STS_STOPPED);

  st_func = func;
  st_state = STS_READY;
  st_arg = arg;
}

int SVKThread::start(void) {
  assert(st_state == STS_READY);
  int rc;

  rc =
      -pthread_create(&st_h.h_id, &st_h.h_thread_attr_default, st_func, st_arg);

  return rc;
}

int SVKThread::stop(void) {
  assert(st_state == STS_RUNNING);

  int rc;

  rc = -pthread_join(st_h.h_id, NULL);
  if (rc == 0) st_state = STS_STOPPED;
  return rc;
}
