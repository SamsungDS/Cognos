#include "sc_cmmh.h"

#include "sc_logger.h"

DevCMMH::DevCMMH(json_t* config) : FabricManager(config) {
  LOG(level_E::INFO, "DevCMMH instance created.");
}

DevCMMH::~DevCMMH() {
  // LOG(level_E::INFO, "DevCMMH instance destroyed.");
}

size_t DevCMMH::setup_info(std::string& buffer) {
  LOG(level_E::INFO, "DevCMMH::setup_info called.");

  // Call base class setup_info to get the setup
  size_t bytes_written = FabricManager::setup_info(buffer);
  LOG(level_E::INFO, "DevCMMH::setup_info completed. Bytes written: " +
                         std::to_string(bytes_written));
  return bytes_written;
}
