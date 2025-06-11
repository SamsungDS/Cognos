#include "bw_monitor.h"

#include <sys/syscall.h>  //for SYS_gettid
#include <unistd.h>       // for getpid()

#include <chrono>
#include <deque>
#include <iostream>
#include <mutex>
#include <thread>

#include "sc_logger.h"

namespace {
std::mutex bw_mutex;
// stores timestamped cumulative I/O in MB
std::deque<std::pair<uint64_t, uint64_t>> io_history;
uint64_t last_read = 0;
uint64_t last_write = 0;
// page size in bytes used for bandwidth calculation
const uint64_t page_size = 4096;
}  // namespace

/**
 * @brief Constructor initializes sampling interval and thread flag.
 */
BandwidthMonitor::BandwidthMonitor()
    : interval_sec_(10),
      running_(false),
      sampler_thread_(&BandwidthMonitor::thread_entry, this) {}

/**
 * @brief Destructor stops the background thread cleanly.
 */
BandwidthMonitor::~BandwidthMonitor() { stop(); }

/**
 * @brief Starts the background sampling thread.
 */
void BandwidthMonitor::start() {
  if (running_) return;
  running_ = true;
  int rc = sampler_thread_.start();
  LOG(level_E::INFO, "BandwidthMonitor started rc=" + std::to_string(rc));
}

/**
 * @brief Stops the sampling thread and cleans up.
 */
void BandwidthMonitor::stop() {
  if (!running_) return;
  running_ = false;
  sampler_thread_.stop();
  LOG(level_E::INFO, "BandwidthMonitor stopped");
}

/**
 * @brief static entry point that delegates to instance method.
 */
void* BandwidthMonitor::thread_entry(void* arg) {
  std::cout << "BandwidthMonitor::thread_entry - entered" << std::endl;
  return static_cast<BandwidthMonitor*>(arg)->sampling_loop();
}

/**
 * @brief thread loop that periodically samples I/O counters and updates
 * history.
 */
void* BandwidthMonitor::sampling_loop() {
  std::cout << "BandwidthMonitor::sampling_loop - started" << std::endl;
  std::cout << "[Thread] PID: " << getpid() << ", TID: " << syscall(SYS_gettid)
            << std::endl;
  pthread_setname_np(pthread_self(), "bw_monitor");
  while (running_) {
    uint64_t now = get_time_ms();
    auto stats = cmmh_stat_interface();
    uint64_t curr_read = stats.cxl_read_count;
    uint64_t curr_write = stats.cxl_write_count;
    uint64_t delta =
        (curr_read - last_read + curr_write - last_write) * page_size;
    uint64_t delta_MB = delta / (1024 * 1024);
    std::cout << "Sampled I/O - Read: " << std::to_string(curr_read)
              << ", Write: " << std::to_string(curr_write)
              << ", Delta MB: " << std::to_string(delta_MB) << std::endl;
    {
      std::lock_guard<std::mutex> lock(bw_mutex);
      io_history.emplace_back(
          now, delta_MB + (io_history.empty() ? 0 : io_history.back().second));
      while (!io_history.empty() && now - io_history.front().first > 60000) {
        io_history.pop_front();
      }
      std::cout << "Updated IO history size: "
                << std::to_string(io_history.size()) << std::endl;
    }
    last_read = curr_read;
    last_write = curr_write;
    std::this_thread::sleep_for(std::chrono::seconds(interval_sec_));

    std::cout << "[LOOP] still alive..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(2));
  }
  std::cout << "BandwidthMonitor::sampling_loop - exiting" << std::endl;
  return nullptr;
}

/**
 * @brief Returns average bandwidth over the past 60 seconds in MB/s.
 */
uint64_t BandwidthMonitor::get_average_MBps() const {
  std::lock_guard<std::mutex> lock(bw_mutex);
  if (io_history.size() < 2) return 0;

  const auto& first = io_history.front();
  const auto& last = io_history.back();

  uint64_t delta_time = last.first - first.first;
  if (delta_time == 0) return 0;

  double delta_MB = static_cast<double>(last.second - first.second);
  return delta_MB / (delta_time / 1000);
}

/**
 * @brief Returns the current time in milliseconds since the epoch.
 */
uint64_t BandwidthMonitor::get_time_ms() const {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}
