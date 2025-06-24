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

class ras_device_manager {
  std::mutex device_manager_lock;

  std::unordered_map<device_unique_identifier, std::unique_ptr<ras_device>>
      devices;

 public:
  bool try_add_device(device_unique_identifier device_unique_id,
                      std::unique_ptr<ras_device> device) {
    std::scoped_lock lk{device_manager_lock};

    if (this->devices.find(device_unique_id) != this->devices.end()) {
      return false;
    }

    if (auto [iterator, inserted] = this->devices.insert(
            make_pair(device_unique_id, std::move(device)));
        !inserted) {
      return false;
    }
    return true;
  }
};

#endif  // _RAS_DEVICE__H_