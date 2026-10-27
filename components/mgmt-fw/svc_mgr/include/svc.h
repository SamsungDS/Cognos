#ifndef __SVC_H__
#define __SVC_H__

#include <string>

#include "thread.h"

/**
 * @brief Represents a SVK service
 * @details Typically inherited by respective services implemented by SVK
 *          plugins, e.g. SVK CXL metrics collector and publisher service.
 */
class Service {
 public:
  Service();
  Service(std::string svc_name, void *(*svc_func)(void *arg));
  virtual ~Service() = default;

  /**
   * @brief Creates a thread corresponding to a service and executes
   *        registered service function as thread function,
   *        @see SVKThread::start()
   */
  virtual int ServiceStart(void);
  virtual void ServiceStop(void);

  std::string svc_name;

 private:
  SVKThread svc_handle;
  void *svc_arg;
};

#endif
