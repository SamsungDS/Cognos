#ifndef TEST_CXL_ADAPTER_H
#define TEST_CXL_ADAPTER_H

#include "sc_cxl_dev_adapter.h"

class TestCXLDeviceAdapter : public CXLDeviceAdapter {
 public:
  std::string mockResponse;
  int mockErrorCode = 0;
  int mockListStatus = 0;
  int mockDevStatus = 0;
  bool mockEmptyResponse = false;

  int list_devices(std::string& buffer) override;

  int list_devices(const sc_id& sid, std::string& buffer) override;

  int get_device_info(const sc_id& sid, std::string& buffer) override;

  int list_hosts(std::string& buffer) override;

  int setup_info() override;

  void setMockError(int errorCode);

  void setEmptyResponse();

  void setLargeDeviceListResponse(size_t device_count);

  void setMalformedJsonResponse();
  void setListDevicesStatus(int status);

  void setGetDeviceInfoStatus(int status);
};

#endif
