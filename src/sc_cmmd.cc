#include "sc_cmmd.h"

#include "sc_logger.h"

DevCMMD::DevCMMD(json_t* config) : FabricManager(config) {
  LOG(level_E::INFO, "DevCMMD instance created.");
}

DevCMMD::~DevCMMD() {}

size_t DevCMMD::setup_info(std::string& buffer) {
  LOG(level_E::INFO, "DevCMMD::setup_info called.");

  // Call base class setup_info to get the setup
  size_t bytes_written = FabricManager::setup_info(buffer);
  LOG(level_E::INFO, "DevCMMD::setup_info completed. Bytes written: " +
                         std::to_string(bytes_written));
  return bytes_written;
}
