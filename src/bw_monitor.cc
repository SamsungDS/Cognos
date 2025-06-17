#include "bw_monitor.h"

#include <sys/syscall.h>  //for SYS_gettid
#include <unistd.h>       // for getpid()

#include <chrono>
#include <iostream>
#include <numeric>
#include <thread>

#include "sc_logger.h"

namespace {
constexpr int WINDOW_SIZE = 10;  // fixed window size
const uint64_t PAGE_SIZE = static_cast<uint64_t>(::sysconf(_SC_PAGESIZE));
}  // namespace

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
  std::deque<std::pair<uint64_t, uint64_t>> window;
  uint64_t sum_bytes = 0;
  int sample_count = 0;

  while (self->running) {
    auto stats = cmmh_stat_interface();
    uint64_t curr_read = stats.cxl_read_count;
    uint64_t curr_write = stats.cxl_write_count;

    // Store in window and update sum
    window.push_back({curr_read, curr_write});
    sum_bytes += (curr_read + curr_write) * PAGE_SIZE;
    sample_count++;

    if (sample_count > WINDOW_SIZE) {
      auto old = window.front();
      window.pop_front();
      sum_bytes -= (old.first + old.second) * PAGE_SIZE;
      sample_count--;
    }

    if (sample_count == WINDOW_SIZE) {
      double avg_MBps =
          static_cast<double>(sum_bytes) / WINDOW_SIZE / (1024.0 * 1024.0);
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
