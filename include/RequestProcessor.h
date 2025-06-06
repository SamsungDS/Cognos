// RequestProcessor.h
#ifndef REQUEST_PROCESSOR_H
#define REQUEST_PROCESSOR_H

#include <atomic>
#include <chrono>
#include <functional>
#include <thread>

#include "RequestManager.h"

template <typename Request>
class RequestProcessor {
 private:
  RequestManager<Request>* requestManager_;
  std::atomic<bool> running_;  // Flag to control the monitoring thread
  std::thread monitorThread_;  // The monitoring thread
  std::function<void(Request*)> processRequestCallback_;

 public:
  /**
   * Constructor.
   * @param requestManager The RequestManager instance to use.
   * @param processRequestCallback The callback function to process requests.
   */
  RequestProcessor(std::function<void(Request*)> processRequestCallback)
      : running_(true), processRequestCallback_(processRequestCallback) {
    requestManager_ = new RequestManager<Request>();
    monitorThread_ = std::thread(&RequestProcessor::monitor, this);
  }

  /**
   * Destructor.
   */
  ~RequestProcessor() {
    running_ = false;
    if (monitorThread_.joinable()) {
      monitorThread_.join();
    }
    delete (requestManager_);
  }

  /**
   * Submit a request to the queue.
   * @param request The request to submit.
   */
  void submitRequest(Request* request) { requestManager_->enqueue(request); }

 private:
  /**
   * Monitoring thread function.
   */
  void monitor() {
    while (running_) {
      Request* request = requestManager_->dequeue();
      if (request != nullptr) {
        processRequestCallback_(request);
      } else {
        // If the queue is empty, sleep for a short period to avoid busy-waiting
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
      }
    }
  }
};

#endif  // REQUEST_PROCESSOR_H
