#pragma once

#include <unordered_map>

#include "sc_cxl_dev_adapter.h"
#include "sc_device.h"

class MockCMMH : public CXLDeviceAdapter {
 public:
  /**
   * @brief Constructor.
   */
  MockCMMH();

  /**
   * @brief Destructor — Cleans up resources.
   */
  ~MockCMMH() override;

  std::vector<sc_device> list_devices() const override;

  DevInfo get_device_info(const sc_id& sid) const override;

  StatInfo get_device_stats(const sc_id& sid) const override;

  void discover_devices(DeviceManager& mgr) override;

  int setup_info() override { return 0; }

  sc_device get_device_object(const sc_id& sid) const override;

 private:
  std::unordered_map<sc_id, sc_device, hash_sc_id> device_map_;
  std::unordered_map<sc_id, StatInfo, hash_sc_id> stats_map_;
};
