#ifndef _RAS_DEVICE__H_
#define _RAS_DEVICE__H_

#include <cstdint>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

struct ras_device {
  std::string name;
  std::string type;
  struct {
    bool valid;
    uint64_t error_count_threshold;
  } ect; /** Error Count Threshold - global error count above which device
            should be marked as degrading */
  struct {
    bool valid;
    uint64_t error_count;
    uint64_t time_window;
  } twt; /** Time Window Threshold - When error count within time window is
            observed device should be marked as degrading */
  uint64_t monitor_interval;  // Monitoring interval for the device
  std::string adapter_name;   // RAS Adapter associated with the device
  int64_t numa_node;
};

using device_unique_identifier = std::string;

/**
 * @class ras_device_manager
 * @brief Manages a collection of RAS devices, ensuring thread-safe addition and
 * retrieval of devices.
 */
class ras_device_manager {
  /**
   * @brief Mutex to synchronize access to the device manager.
   */
  std::mutex device_manager_lock;

  /**
   * @brief Map of unique device identifiers to their corresponding ras_device
   * objects.
   */
  std::unordered_map<device_unique_identifier, std::unique_ptr<ras_device>>
      devices;

 public:
  /**
   * @brief Attempts to add a device to the device manager.
   *
   * @param device_unique_id Unique identifier for the device.
   * @param device The device to be added.
   *
   * @return True if the device was successfully added, false otherwise.
   */
  bool try_add_device(device_unique_identifier device_unique_id,
                      std::unique_ptr<ras_device> device) {
    // Acquire a scoped lock to ensure exclusive access to the device manager.
    std::scoped_lock lk{device_manager_lock};

    // Check if a device with the given unique ID already exists.
    if (this->devices.find(device_unique_id) != this->devices.end()) {
      // If the device already exists, return false to indicate failure.
      return false;
    }

    // Attempt to insert the device into the map.
    if (auto [iterator, inserted] = this->devices.insert(
            std::make_pair(device_unique_id, std::move(device)));
        !inserted) {
      // If the insertion failed, return false to indicate failure.
      return false;
    }
    // If the insertion succeeded, return true to indicate success.
    return true;
  }
};

#endif  // _RAS_DEVICE__H_