#ifndef DEV_DIRECT_CMMH_H
#define DEV_DIRECT_CMMH_H
#include "sc_fm.h"

class DevCMMH : public FabricManager {
 public:
  explicit DevCMMH(json_t* config);
  virtual ~DevCMMH();
  size_t setup_info(std::string& buffer) override;
};

#endif
