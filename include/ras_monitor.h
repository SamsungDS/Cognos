#ifndef _RAS_MONITOR_H_
#define _RAS_MONITOR_H_

#include <string>

#include "RequestProcessor.h"

class ras_monitor;

struct ras_request {
  ras_request(bool is_internal_request, bool is_sync_request, std::string in,
              std::string out, ras_monitor *monitor_instance)
      : is_internal_request(is_internal_request),
        is_sync_request(is_sync_request),
        request_details(in),
        response(out),
        monitor_instance(monitor_instance) {
    is_completed = false;
  }

  bool is_internal_request;
  bool is_sync_request;

  bool is_completed;
  std::mutex sync_mutex;
  std::condition_variable sync_cv;

  // Request method and params
  std::string request_details;
  // Response string
  std::string response;

  ras_monitor *monitor_instance;
};

struct ras_device {
  std::string name;
  std::string type;
  struct {
    bool valid;
    uint64_t error_count_threshold;
  } ect; /** Error Count Threshold - global error count above which device
            should be marked as degrading */
  struct {
    bool valid;
    uint64_t error_count;
    uint64_t time_window;
  } twt; /** Time Window Threshold - When error count within time window is
            observed device should be marked as degrading */
};

class ras_monitor {
 private:
  std::unique_ptr<RequestProcessor<ras_request>> ras_monitor_;
  std::vector<ras_device> devices;

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
};

#endif  // _RAS_MONITOR_H_
