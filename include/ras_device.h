#ifndef _RAS_DEVICE__H_
#define _RAS_DEVICE__H_

#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>

using device_unique_identifier = std::string;

struct ras_device {
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
  ras_device(std::string name_, std::string type_, bool ect_valid_,
             uint64_t ect_error_count_threshold_, bool twt_valid_,
             uint64_t twt_error_count_, uint64_t twt_time_window_,
             uint64_t monitor_interval_, std::string adapter_name_,
             int64_t numa_node_,
             std::optional<device_unique_identifier> device_name_in_adapter_ =
                 std::nullopt) {
    name = name_;
    type = type_;
    ect.valid = ect_valid_;
    ect.error_count_threshold = ect_error_count_threshold_;
    twt.valid = twt_valid_;
    twt.error_count = twt_error_count_;
    twt.time_window = twt_time_window_;
    monitor_interval = monitor_interval_;
    adapter_name = adapter_name_;
    numa_node = numa_node_;
    device_name_in_adapter = device_name_in_adapter_;
  }

  device_unique_identifier get_device_name() const { return name; };
  device_unique_identifier get_device_name_in_adapter() const {
    if (device_name_in_adapter.has_value()) {
      return device_name_in_adapter.value();
    } else {
      return get_device_name();
    }
  }

 private:
  device_unique_identifier name;
  std::optional<device_unique_identifier> device_name_in_adapter; /** This is
  the name of the device in the adapter. This is set only if the device name in
  adapter does not match the device name.
  - mock adapter for cxl will report device as numa node string.
  */
};

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
    if (device.get() == nullptr) {
      return false;
    }

    if (device_unique_id.empty() || device->get_device_name().empty()) {
      return false;
    }

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

  /**
   * @brief Attempts to remove a device from the device manager.
   *
   * @param device_unique_id Unique identifier for the device to be removed.
   *
   * @return True if the device was successfully removed, false otherwise.
   */
  bool try_remove_device(device_unique_identifier device_unique_id) {
    // Acquire a scoped lock to ensure exclusive access to the device manager.
    std::scoped_lock lk{device_manager_lock};

    // Attempt to remove the device from the map.
    auto num_rem = this->devices.erase(device_unique_id);

    if (num_rem == 1)
      return true;
    else
      return false;
  }

  /**
   * @brief Attempts to retrieve a device from the device manager.
   *
   * @param device_unique_id Unique identifier for the device to be retrieved.
   *
   * @return An optional ras_device containing the device if found, std::nullopt
   * otherwise.
   */
  std::optional<ras_device> try_get_device(
      device_unique_identifier device_unique_id) {
    std::scoped_lock lk{device_manager_lock};
    auto device = this->devices.find(device_unique_id);
    if (device == this->devices.end()) {
      return std::nullopt;
    }
    return *device->second;
  }
};

#endif  // _RAS_DEVICE__H_
