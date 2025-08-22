#include "ras_monitor.h"

#include <memory>

#include "ras_command_handlers.hpp"
#include "utils/ras_json_validate.hpp"

std::unique_ptr<cognos::utils::CommandHandler<ras_request>>
get_ras_command_handler(void) {
  std::unique_ptr<cognos::utils::CommandHandler<ras_request>> rch = nullptr;
  rch = std::make_unique<cognos::utils::CommandHandler<ras_request>>();

  if (rch) {
    auto add_ras_device_handler =
        std::make_unique<add_ras_monitor_for_device_handler>();
    rch->register_command(std::move(add_ras_device_handler));

    auto remove_ras_device_handler =
        std::make_unique<remove_ras_monitor_for_device_handler>();
    rch->register_command(std::move(remove_ras_device_handler));

    auto check_ras_device_status_handler =
        std::make_unique<ras_check_device_status_handler>();
    rch->register_command(std::move(check_ras_device_status_handler));

    // Register new command handlers here.
  }
  return rch;
}

ras_monitor::ras_monitor(/* args */) {
  ras_monitor_ = std::make_unique<RequestProcessor<ras_request>>(
      ras_monitor::process_request);
  ras_command_handlers_ = get_ras_command_handler();
  ras_device_manager_ = std::make_shared<ras_device_manager>();
}

ras_monitor::~ras_monitor() {}

void ras_monitor::set_sync_request_completed(ras_request *req) {
  std::lock_guard<std::mutex> lock(req->sync_mutex);
  req->is_completed = true;
}
void ras_monitor::process_request_sync(ras_request *req) {
  if (req->is_internal_request == false) {
    req->execute_feature_command();
  } else {
    req->execute_internal_command();
  }
  set_sync_request_completed(req);

  req->sync_cv.notify_one();
  return;
}

bool ras_monitor::ras_submit_request(ras_request *req) {
  if (req != nullptr) {
    this->ras_monitor_->submitRequest(req);
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

cognos::utils::CommandHandler<ras_request>::command_status
ras_monitor::execute_request_by_monitor(ras_request &req) {
  return this->ras_command_handlers_->execute_command(req.command, req);
}

void execute_request_by_monitor_(ras_request &req) {
  if (auto status =
          req.ras_context->monitor_context->execute_request_by_monitor(req);
      status == cognos::utils::CommandHandler<
                    ras_request>::command_status::COMMAND_UNSUPPORTED) {
    req.mark_request_failed(RAS_RESULT_MESSAGE_STR_CMD_UNSUPPORTED);
  }
  // Other cases should be handled by validator/executor and mark the result
  // appropriately
  return;
}

bool ras_submit_timed_request(ras_request *req, int interval) {
  return req->ras_context->monitor_context->ras_submit_timed_request(req,
                                                                     interval);
}

std::shared_ptr<ras_device_manager> ras_monitor_get_device_manager(
    ras_monitor *m) {
  return m->get_device_manager();
}
