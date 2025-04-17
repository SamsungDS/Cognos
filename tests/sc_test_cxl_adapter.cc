#include "sc_test_cxl_adapter.h"

#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <jansson.h>

#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>

#include "sc_id.h"

std::vector<sc_device> TestCXLDeviceAdapter::list_devices() const {
  if (mockListStatus == -EIO) {
    throw std::runtime_error("simulated list_devices failure");
  }
  if (mockListStatus == -ENOTSUP || mockListStatus == -EINVAL) {
    return {};
  }
  return mockDevices;
}

sc_device TestCXLDeviceAdapter::get_device_object(const sc_id& sid) const {
  if (mockListStatus == -EINVAL || mockDevStatus == -EIO) {
    throw std::runtime_error("Simulated failure for get_device_object");
  }
  auto it = deviceMap.find(sid);
  if (it != deviceMap.end()) {
    return it->second;
  }
  throw std::runtime_error("Device not found for get_device_object");
}

DevInfo TestCXLDeviceAdapter::get_device_info(const sc_id& sid) const {
  if (mockDevStatus == -EIO) {
    throw std::runtime_error("Simulated failure for get_device_info");
  }

  auto it = deviceMap.find(sid);
  if (it != deviceMap.end()) {
    return it->second.to_device_info();
  }

  throw std::runtime_error("Device not found for get_device_info");
}

void TestCXLDeviceAdapter::discover_devices(DeviceManager& mgr) {
  for (auto& dev : mockDevices) {
    sc_id sid = dev.d_get_id();
    mgr.register_device(sid, this);
  }
}

std::vector<sc_host> TestCXLDeviceAdapter::list_hosts() { return mockHosts; }

int TestCXLDeviceAdapter::setup_info() { return mockSetupInfoStatus; }

void TestCXLDeviceAdapter::add_mock_device(const sc_device& dev) {
  mockDevices.push_back(dev);
  deviceMap[dev.d_get_id()] = dev;
}

void TestCXLDeviceAdapter::add_mock_host(const sc_host& host) {
  mockHosts.push_back(host);
}

void TestCXLDeviceAdapter::set_setup_info_status(int status) {
  mockSetupInfoStatus = status;
}

void TestCXLDeviceAdapter::setListDevicesStatus(int status) {
  mockListStatus = status;
}

void TestCXLDeviceAdapter::setGetDevicesInfoStatus(int status) {
  mockDevStatus = status;
}
