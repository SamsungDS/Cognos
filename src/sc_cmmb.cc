#include "sc_cmmb.h"

DevCMMB::DevCMMB(json_t* config) : FabricManager(config) {
}

DevCMMB::~DevCMMB() {
}

size_t DevCMMB::setup_info(std::string &buffer) {
    // Call base class setup_info to get the setup
    return FabricManager::setup_info(buffer);
}

