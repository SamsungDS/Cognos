#include "sc_cmmh.h"

DevCMMH::DevCMMH(json_t* config) : FabricManager(config) {
}

DevCMMH::~DevCMMH() {
}

size_t DevCMMH::setup_info(std::string &buffer) {
    // Call base class setup_info to get the setup
    return FabricManager::setup_info(buffer);
}

