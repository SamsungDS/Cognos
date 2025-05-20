#include "sc_cxl_dev_adapter.h"
#include "sc_dev_manager.h"

class DummyAdapter : public CXLDeviceAdapter {
 public:
  std::vector<sc_device> list_devices() const override { return {}; }
  sc_device get_device_object(const sc_id&) const override { return {}; }
  DevInfo get_device_info(const sc_id&) const override { return {}; }
  void discover_devices(DeviceManager&) override {}
  int setup_info() override { return 0; }
};

extern "C" void register_plugin(DeviceManager& mgr) {
  mgr.registerAdapter("dummy", new DummyAdapter());
}
