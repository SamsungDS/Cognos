#include "sc_test_cxl_adapter.h"

#include <gmock/gmock.h>
#include <gtest/gtest.h>
#include <jansson.h>

#include <memory>
#include <string>
#include <unordered_set>

#include "sc_id.h"

int TestCXLDeviceAdapter::list_devices(std::string& buffer) {
  if (mockListStatus == -ENOTSUP) return -ENOTSUP;
  if (mockListStatus == -EINVAL) return -EINVAL;

  // Return all devices in the mock
  std::ostringstream oss;
  oss << R"({"id": "1", "type": "1", "pcie_addr": "0x1234"}, {"id": "2", "type": "2", "pcie_addr": "0x5678"})";
  buffer = oss.str();
  return buffer.size();
}

int TestCXLDeviceAdapter::list_devices(const sc_id& sid, std::string& buffer) {
  if (mockListStatus == -EINVAL) return -EINVAL;
  if (mockEmptyResponse) {
    buffer = R"()";
    return buffer.size();
  } else if (!mockResponse.empty()) {
    buffer = mockResponse;
    return buffer.size();
  } else if (mockErrorCode != 0) {
    // simulate error code
    std::ostringstream oss;
    oss << R"({"rc": ")" << std::to_string(mockErrorCode)
        << R"(", "message": ")"
        << R"(Invalid JSON format")"
        << R"(})";
    buffer = oss.str();
    return mockErrorCode;
  } else {
    std::ostringstream oss;
    bool first = true;
    if (sid.get_sc_id() == 1) {
      if (!first) oss << ",";
      oss << R"({"id": "1", "type": "1", "pcie_addr": "0x1234"})";
      first = false;
    }
    buffer = oss.str();
  }

  return 0;
}

int TestCXLDeviceAdapter::get_device_info(const sc_id& sid,
                                          std::string& buffer) {
  if (mockDevStatus == -EIO) return -EIO;
  if (mockErrorCode != 0) return mockErrorCode;
  if (sid.get_sc_id() == 1) {
    buffer = R"({"id": "1", "type": "1", "pcie_addr": "0x1234"})";
    return buffer.size();
  } else if (sid.get_sc_id() == 2) {
    buffer = R"({"id": "2", "type": "2", "pcie_addr": "0x5678"})";
    return buffer.size();
  } else if (sid.get_sc_id() == 1999) {
    buffer.clear();
    return -EIO;
  }
  return -ENOENT;
}

int TestCXLDeviceAdapter::list_hosts(std::string& buffer) {
  buffer = R"({"hosts": [{"id": "srf07.msl.lab"}, {"id": "emr02.msl.lab"}]})";
  return buffer.size();
}

int TestCXLDeviceAdapter::setup_info() { return 0; }

void TestCXLDeviceAdapter::setMockError(int errorCode) {
  mockErrorCode = errorCode;
}

void TestCXLDeviceAdapter::setEmptyResponse() { mockEmptyResponse = true; }

void TestCXLDeviceAdapter::setLargeDeviceListResponse(size_t device_count) {
  std::ostringstream oss;
  oss << "[";

  for (size_t i = 0; i < device_count; ++i) {
    if (i > 0) oss << ",";
    oss << R"({"id": ")" << i << R"(", "type": "1", "pcie_addr": "0x)"
        << std::hex << (0x1000 + i) << R"("})";
  }

  oss << "]";
  mockResponse = oss.str();
}

void TestCXLDeviceAdapter::setMalformedJsonResponse() {
  mockErrorCode = -22;  // EINVAL
}
void TestCXLDeviceAdapter::setListDevicesStatus(int status) {
  mockListStatus = status;
}

void TestCXLDeviceAdapter::setGetDeviceInfoStatus(int status) {
  mockDevStatus = status;
}
