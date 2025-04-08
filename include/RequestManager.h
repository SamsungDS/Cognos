#ifndef REQUEST_MANAGER_H
#define REQUEST_MANAGER_H

#include <rte_ring.h>

#include <condition_variable>
#include <iostream>
#include <mutex>
#include <vector>

template <typename Request>
class RequestManager {
 private:
  rte_ring* ring_;                        // The RTE ring for primary buffering
  std::vector<Request*> fallbackBuffer_;  // Fallback buffer when ring is full
  std::mutex mtx_;              // Mutex for protecting fallback buffer access
  std::condition_variable cv_;  // Condition variable for synchronization

 public:
  /**
   * Default constructor with default ring size.
   */
  RequestManager() : RequestManager("DEFAULT_RING", 1024) {}

  /**
   * Constructor with custom ring name and size.
   * @param name The name of the ring.
   * @param count The size of the ring.
   */
  RequestManager(const char* name, unsigned count) {
    ring_ = rte_ring_create(name, count, 0);
    if (!ring_) {
      std::cerr << "Failed to create ring\n";
      throw std::runtime_error("Failed to create ring");
    }
  }

  /**
   * Destructor to clean up the RTE ring.
   */
  ~RequestManager() {
    if (ring_) {
      rte_ring_free(ring_);
    }
  }

  /**
   * Enqueue a request into the ring or fallback buffer.
   * @param request The request to enqueue.
   */
  void enqueue(Request* request) {
    // Attempt to enqueue into the ring
    if (rte_ring_enqueue(ring_, request) == 0) {
      return;  // Successfully enqueued
    }

    // If the ring is full, enqueue into the fallback buffer
    {
      std::lock_guard<std::mutex> lock(mtx_);
      fallbackBuffer_.push_back(request);
    }
  }

  /**
   * Dequeue a request from the ring or fallback buffer.
   * @return The dequeued request, or nullptr if both the ring and fallback
   * buffer are empty.
   */
  Request* dequeue() {
    Request* request;
    // First, attempt to dequeue from the ring
    if (rte_ring_dequeue(ring_, (void**)&request) == 0) {
      return request;  // Successfully dequeued from the ring
    }

    // If the ring is empty, try to dequeue from the fallback buffer
    std::lock_guard<std::mutex> lock(mtx_);
    if (!fallbackBuffer_.empty()) {
      request = fallbackBuffer_.front();
      fallbackBuffer_.erase(fallbackBuffer_.begin());
      return request;
    }

    // If both the ring and fallback buffer are empty
    return nullptr;
  }

  /**
   * Enqueue items from the fallback buffer into the ring when the ring is not
   * full.
   */
  void flushFallbackBuffer() {
    std::lock_guard<std::mutex> lock(mtx_);
    while (!fallbackBuffer_.empty() && rte_ring_free_count(ring_) > 0) {
      Request* request = fallbackBuffer_.front();
      fallbackBuffer_.erase(fallbackBuffer_.begin());
      rte_ring_enqueue(ring_, request);  // Enqueue into the ring
    }
  }
};

#endif  // REQUEST_MANAGER_H