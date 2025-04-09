#include "ras_monitor.h"

ras_monitor::ras_monitor(/* args */) {
  ras_monitor_ = std::make_unique<RequestProcessor<ras_request>>(
      ras_monitor::process_request);
}

ras_monitor::~ras_monitor() {}

bool ras_monitor::ras_submit_request(ras_request *req) {
  if (req != nullptr) {
    ras_monitor_->submitRequest(req);
    return true;
  } else {
    return false;
  }
}