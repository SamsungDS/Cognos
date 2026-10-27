#ifndef __THREAD_H__
#define __THREAD_H__

#include <pthread.h>

enum SVKThreadState { STS_STOPPED, STS_READY, STS_RUNNING };

class SVKThreadHandle {
 public:
  pthread_t h_id;
  pthread_attr_t h_thread_attr_default;
};

class SVKThread {
 public:
  SVKThread();
  SVKThread(void *(*func)(void *), void *arg);
  int start(void);
  int stop(void);

 private:
  SVKThreadHandle st_h;
  void *(*st_func)(void *);
  void *st_arg;
  SVKThreadState st_state = STS_STOPPED;
};
#endif
