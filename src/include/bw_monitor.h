#ifndef BANDWIDTH_MONITOR_H
#define BANDWIDTH_MONITOR_H

#include <atomic>
#include <cstdint>
#include <deque>
#include <mutex>

#include "thread.h"

#if MOCK == 1
#include "mock_libcmmh.h"
#else
#include "libcmmh.h"
#endif

/**
 * @class BandwidthMonitor
 * @brief Utility class to monitor bandwidth usage in the background.
 *
 * This class launches a background thread using SVKThread to periodically
 * sample the read and write counts from the CMMH (or CMMD) interface and
 * calculate average memory bandwidth usage in MB/s.
 *
 * The results are intended to be used for APIs like get_device_stats to provide
 * realtime insights without requiring each API call to perform heavy
 * computations.
 */
class BandwidthMonitor {
 public:
  /**
   * @brief Constructor for BandwidthMonitor.
   *
   * Initializes internal state and sampling interval.
   */
  BandwidthMonitor(uint64_t interval_sec);

  /**
   * @brief Destructor for BandwidthMonitor.
   *
   * Ensures the background thread is stopped before cleanup.
   */
  ~BandwidthMonitor();

  /**
   * @brief Start the background thread for sampling bandwidth usage.
   *
   * starts an internal thread that fetches IO stats every 10 seconds (by
   * default).
   */
  void start();

  /**
   * @brief Stop the background sampling thread.
   *
   * stops the background thread if running.
   */
  void stop();

  /**
   * @brief Get the calculated average bandwidth in MB/s.
   *
   * This method returns the average bandwidth sampled over the last minute.
   * @return Bandwidth in MB/s.
   */
  uint64_t get_average_MBps() const;

 private:
  /**
   * @brief Internal thread loop that performs periodic sampling.
   *
   * This method is invoked by the SVKThread and runs in a loop until stopped.
   * @return nullptr
   */
  static void* sampling_loop(void* arg);

 private:
  // sampling interval in seconds (default: 10)
  uint64_t interval_sec;
  // flag to control thread execution
  bool running;
  std::atomic<uint64_t> cached_avg_MBps;
  // Background sampling thread
  SVKThread sampler_thread;
};

#endif
