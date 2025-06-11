#ifndef BANDWIDTH_MONITOR_H
#define BANDWIDTH_MONITOR_H

#include <cstdint>

#include "libcmmh.h"
#include "thread.h"

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
  BandwidthMonitor();

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
  void* sampling_loop();

  /**
   * @brief Static entry point wrapper for the thread.
   *
   * Casts the input argument to BandwidthMonitor and delegates to
   * sampling_loop().
   * @param arg Pointer to BandwidthMonitor instance.
   * @return nullptr
   */
  static void* thread_entry(void* arg);

  /**
   * @brief Get the current time in milliseconds.
   *
   * Used to timestamp each sample and calculate deltas.
   * @return Time in milliseconds since epoch.
   */
  uint64_t get_time_ms() const;

 private:
  // sampling interval in seconds (default: 10)
  uint64_t interval_sec_;
  // flag to control thread execution
  bool running_;
  // Background sampling thread
  SVKThread sampler_thread_;
};

#endif
