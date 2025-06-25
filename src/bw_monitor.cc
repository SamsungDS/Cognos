#include "bw_monitor.h"

#include <sys/syscall.h>  //for SYS_gettid
#include <unistd.h>       // for getpid()

#include <chrono>
#include <ctime>    // for std::time_t, std::localtime
#include <iomanip>  // for std::put_time
#include <iostream>
#include <numeric>
#include <thread>

#include "sc_logger.h"

namespace {
constexpr int WINDOW_SIZE = 10;  // fixed window size
}

/**
 * @brief Constructor initializes sampling interval and thread flag.
 */
BandwidthMonitor::BandwidthMonitor(uint64_t interval)
    : interval_sec(interval),
      running(false),
      cached_avg_MBps(0),
      sampler_thread(sampling_loop, this) {}

/**
 * @brief Destructor stops the background thread cleanly.
 */
BandwidthMonitor::~BandwidthMonitor() { stop(); }

/**
 * @brief Starts the background sampling thread.
 */
void BandwidthMonitor::start() {
  if (!running) {
    running = true;
    sampler_thread.start();
    LOG(level_E::INFO, "BandwidthMonitor started.");
  }
}

/**
 * @brief Stops the sampling thread and cleans up.
 */
void BandwidthMonitor::stop() {
  if (!running) return;
  running = false;
  sampler_thread.stop();
  LOG(level_E::INFO, "BandwidthMonitor stopped.");
}

/**
 * @brief thread loop that periodically samples I/O counters and updates
 * history.
 */
void* BandwidthMonitor::sampling_loop(void* arg) {
  pthread_setname_np(pthread_self(), "bw_monitor");
  auto* self = static_cast<BandwidthMonitor*>(arg);

  uint64_t prev_read = 0, prev_write = 0;
  uint64_t sum_bytes = 0;
  std::deque<uint64_t> byte_deltas;
  int sample_count = 0;

  while (self->running) {
    auto stats = cmmh_stat_interface();
    uint64_t curr_read = stats.cxl_read_count;
    uint64_t curr_write = stats.cxl_write_count;

    if (sample_count == 0) {
      prev_read = curr_read;
      prev_write = curr_write;
    }

    uint64_t delta_read = curr_read - prev_read;
    uint64_t delta_write = curr_write - prev_write;
    uint64_t delta_bytes = (delta_read + delta_write);

    prev_read = curr_read;
    prev_write = curr_write;

    // Update deque + sum
    byte_deltas.push_back(delta_bytes);
    sum_bytes += delta_bytes;
    sample_count++;

    if (sample_count > WINDOW_SIZE) {
      sum_bytes -= byte_deltas.front();
      byte_deltas.pop_front();
      sample_count--;
    }

    if (sample_count == WINDOW_SIZE) {
      double avg_MBps = static_cast<double>(sum_bytes) /
                        (WINDOW_SIZE * self->interval_sec * 1024.0 * 1024.0);
      self->cached_avg_MBps.store(static_cast<uint64_t>(avg_MBps));
    }
    std::this_thread::sleep_for(std::chrono::seconds(self->interval_sec));
  }

  return nullptr;
}

/**
 * @brief Returns average bandwidth over the past 10 samples in MB/s.
 */
uint64_t BandwidthMonitor::get_average_MBps() const {
  return cached_avg_MBps.load();
}
