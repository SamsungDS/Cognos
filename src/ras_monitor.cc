#include "ras_monitor.h"

#include <boost/property_tree/json_parser.hpp>
#include <sstream>

#include "ras.hpp"

using namespace std;

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
  if (req == nullptr) return;

  try {
    std::stringstream ss;
    ss << req->input;
    boost::property_tree::ptree pt;
    boost::property_tree::read_json(ss, pt);
    std::string cmd_name = pt.get<std::string>("command");
    std::cout << "Command Name:" << cmd_name << std::endl;
  } catch (const boost::property_tree::ptree_error &e) {
    std::cout << e.what() << std::endl;
  }

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
