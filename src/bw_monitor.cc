#include "bw_monitor.h"

#include <sys/syscall.h>  //for SYS_gettid
#include <unistd.h>       // for getpid()

#include <chrono>
#include <ctime>    // for std::time_t, std::localtime
#include <iomanip>  // for std::put_time
#include <iostream>
#include <numeric>
#include <sstream>  // for std::ostringstream
#include <thread>

#include "sc_logger.h"

namespace {
constexpr int WINDOW_SIZE = 10;  // fixed window size
}

static void* bw_monitor(void* arg);

/**
 * @brief Constructor initializes sampling interval and thread flag.
 */
BandwidthMonitor::BandwidthMonitor(int d_index, uint64_t interval)
    : device_index(d_index),
      interval_sec(interval),
      running(false),
      cached_avg_Bps(0),
      sampler_thread(bw_monitor, this) {}

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
    LOG(level_E::INFO,
        "BandwidthMonitor started for device " + std::to_string(device_index));
  }
}

/**
 * @brief Stops the sampling thread and cleans up.
 */
void BandwidthMonitor::stop() {
  if (!running) return;
  running = false;
  sampler_thread.stop();
  LOG(level_E::INFO,
      "BandwidthMonitor stopped for device " + std::to_string(device_index));
}

/**
 * @brief Internal thread loop that performs periodic sampling.
 *
 * This method is invoked by the SVKThread and runs in a loop until stopped.
 * @return nullptr
 */
static void* bw_monitor(void* arg) {
  pthread_setname_np(pthread_self(), "bw_monitor");
  BandwidthMonitor* bm = static_cast<BandwidthMonitor*>(arg);
  uint64_t prev_cxl_read = 0, prev_cxl_write = 0;
  uint64_t prev_nvme_read = 0, prev_nvme_write = 0;
  uint64_t sum_bytes = 0;
  std::deque<uint64_t> cxl_nvme_byte_deltas;
  int sample_count = 0;
  uint64_t mon_interval = bm->get_interval();

  while (bm->bw_mon_is_running()) {
    cmmh_stat_interface_t stats = cmmh_stat_interface(bm->get_device_index());

    uint64_t curr_cxl_read = stats.cxl_read_count;
    uint64_t curr_cxl_write = stats.cxl_write_count;
    uint64_t curr_nvme_read = stats.nvme_read_count;
    uint64_t curr_nvme_write = stats.nvme_write_count;

    if (sample_count == 0) {
      prev_cxl_read = curr_cxl_read;
      prev_cxl_write = curr_cxl_write;
      prev_nvme_read = curr_nvme_read;
      prev_nvme_write = curr_nvme_write;
    } else {
      uint64_t delta_cxl_read = curr_cxl_read - prev_cxl_read;
      uint64_t delta_cxl_write = curr_cxl_write - prev_cxl_write;
      /* CXL IO size 64 bytes, covert, IO count to bytes */
      uint64_t delta_cxl_bytes = (delta_cxl_read + delta_cxl_write) * 64;
      uint64_t delta_nvme_read = curr_nvme_read - prev_nvme_read;
      uint64_t delta_nvme_write = curr_nvme_write - prev_nvme_write;
      /* NVMe IO size is 4096, convert IO count to bytes */
      uint64_t delta_nvme_bytes = (delta_nvme_read + delta_nvme_write) * 4096;
      uint64_t delta_bytes = delta_cxl_bytes + delta_nvme_bytes;

      prev_cxl_read = curr_cxl_read;
      prev_cxl_write = curr_cxl_write;
      prev_nvme_read = curr_nvme_read;
      prev_nvme_write = curr_nvme_write;

      // Update deque + sum
      cxl_nvme_byte_deltas.push_back(delta_bytes);
      sum_bytes += delta_bytes;
    }

    sample_count++;
    if (sample_count > WINDOW_SIZE) {
      sum_bytes -= cxl_nvme_byte_deltas.front();
      cxl_nvme_byte_deltas.pop_front();
      sample_count--;
    }
    if (sample_count == WINDOW_SIZE) {
      uint64_t avg_Bps = sum_bytes / (WINDOW_SIZE * mon_interval);
      bm->set_average_Bps(avg_Bps);
    }

    std::this_thread::sleep_for(std::chrono::seconds(mon_interval));
  }

  return nullptr;
}

bool BandwidthMonitor::bw_mon_is_running() { return running; }

uint64_t BandwidthMonitor::get_interval() { return interval_sec; }

uint32_t BandwidthMonitor::get_device_index() { return device_index; }

void BandwidthMonitor::set_average_Bps(uint64_t avg_Bps) {
  cached_avg_Bps.store(avg_Bps);
}

/**
 * @brief Returns average bandwidth over the past interval samples in B/s.
 */
uint64_t BandwidthMonitor::get_average_Bps() const {
  return cached_avg_Bps.load();
}
