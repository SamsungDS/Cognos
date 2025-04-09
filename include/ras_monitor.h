#ifndef _RAS_MONITOR_H_
#define _RAS_MONITOR_H_

#include "RequestProcessor.h"

struct ras_request {
  bool is_internal_request;
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
    // TODO
    return;
  }

 public:
  ras_monitor(/* args */);
  ~ras_monitor();
  bool ras_submit_request(ras_request *req);
};

#endif  // _RAS_MONITOR_H_