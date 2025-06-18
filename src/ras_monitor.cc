#include "ras_monitor.h"

#include <omp.h>

ras_monitor::ras_monitor(/* args */) {
  ras_monitor_ = std::make_unique<RequestProcessor<ras_request>>(
      ras_monitor::process_request);
}

ras_monitor::~ras_monitor() {}

void ras_monitor::set_sync_request_completed(ras_request *req) {
  std::lock_guard<std::mutex> lock(req->sync_mutex);
  req->is_completed = true;
}
void ras_monitor::process_request_sync(ras_request *req) {
  // TODO

  set_sync_request_completed(req);

  req->sync_cv.notify_one();
  return;
}

bool ras_monitor::ras_submit_request(ras_request *req) {
  if (req != nullptr) {
    ras_monitor_->submitRequest(req);
    if (req->is_sync_request) {
      std::unique_lock<std::mutex> lock(req->sync_mutex);
      req->sync_cv.wait(lock, [req] { return req->is_completed; });
    }
    return true;
  } else {
    return false;
  }
}

// Function that sleeps and calls submitRequest
void call_ras_submit_request(ras_request *req, ras_monitor *m, int interval,
                             bool &ret) {
  if (req != nullptr) {
    std::this_thread::sleep_for(std::chrono::seconds(interval));
    ret = m->ras_submit_request(req);
  }
}

// A timer based ras_submit_request wrapper
bool ras_monitor::ras_submit_timed_request(ras_request *req, int interval) {
  bool ret = false, tcall = true;

  std::thread(call_ras_submit_request, req, this, interval, std::ref(ret))
      .detach();
  return tcall;
}
