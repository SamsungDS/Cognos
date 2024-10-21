#include "sc_cmmd.h"

DevCMMD::DevCMMD(json_t* config) : FabricManager(config) {
}

DevCMMD::~DevCMMD() {
}

size_t DevCMMD::setup_info(std::string &buffer) {
    // Call base class setup_info to get the setup
    return FabricManager::setup_info(buffer);
}

