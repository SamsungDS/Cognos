#include "sc_cmmx.h"

CMMX::CMMX(json_t* config) : FabricManager(config) {}

CMMX::~CMMX() {}

size_t CMMX::setup_info(std::string& buffer) {
  // Call base class setup_info to get the setup
  return FabricManager::setup_info(buffer);
}
