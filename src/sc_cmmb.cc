#include "sc_cmmb.h"

#include "sc_logger.h"

DevCMMB::DevCMMB(json_t* config) : FabricManager(config) {
  LOG(level_E::INFO, "DevCMMB instance created.");
}

DevCMMB::~DevCMMB() {}

size_t DevCMMB::setup_info(std::string& buffer) {
  LOG(level_E::INFO, "DevCMMB::setup_info called.");

  // Call base class setup_info to get the setup
  size_t bytes_written = FabricManager::setup_info(buffer);
  LOG(level_E::INFO, "DevCMMB::setup_info completed. Bytes written: " +
                         std::to_string(bytes_written));
  return bytes_written;
}
