#ifndef TEST_CXL_ADAPTER_H
#define TEST_CXL_ADAPTER_H

#include <optional>
#include <vector>

#include "sc_api_structs.h"
#include "sc_cxl_dev_adapter.h"
#include "sc_device.h"
#include "sc_id.h"

class TestCXLDeviceAdapter : public CXLDeviceAdapter {
 public:
  int mockListStatus = 0;
  int mockDevStatus = 0;
  std::vector<sc_device> mockDevices;
  std::vector<sc_host> mockHosts;
  int mockSetupInfoStatus = 0;
  std::unordered_map<sc_id, sc_device, hash_sc_id> deviceMap;
  std::unordered_map<uint64_t, StatInfo> mock_stats;

  std::vector<sc_device> list_devices() const override;

  sc_device get_device_object(const sc_id& sid) const override;

  std::vector<sc_host> list_hosts();

  virtual DevInfo get_device_info(const sc_id& sid) const override;
  virtual StatInfo get_device_stats(const sc_id& sid) const override;
  virtual void discover_devices(DeviceManager& mgr);

  int setup_info() override;

  void add_mock_device(const sc_device& dev);
  void add_mock_host(const sc_host& host);
  void set_setup_info_status(int status);
  void setListDevicesStatus(int status);
  void setGetDevicesInfoStatus(int status);
  void set_stat_info_for_device(const sc_id& id, const StatInfo& s);
};

#endif
