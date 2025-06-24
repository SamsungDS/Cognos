#ifndef _RAS_MONITOR_H_
#define _RAS_MONITOR_H_

#include "RequestProcessor.h"
#include "ras_command_handlers.hpp"
#include "ras_device.h"
#include "ras_request.h"

class ras_monitor {
 private:
  std::unique_ptr<RequestProcessor<ras_request>> ras_monitor_;
  std::unique_ptr<CommandHandler<ras_request>> ras_command_handlers_;
  std::shared_ptr<ras_device_manager> ras_device_manager_;

  static void process_request(ras_request *req) {
    if (req->is_sync_request) {
      req->monitor_instance->process_request_sync(req);
    }
    return;
  }

  void set_sync_request_completed(ras_request *req);
  void process_request_sync(ras_request *req);

 public:
  ras_monitor(/* args */);
  ~ras_monitor();
  bool ras_submit_request(ras_request *req);

  bool ras_submit_timed_request(ras_request *req, int interval);

  auto execute_request_by_monitor(ras_request &req);

  auto get_device_manager(void) { return this->ras_device_manager_; }
};

#endif  // _RAS_MONITOR_H_
