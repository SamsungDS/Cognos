#ifndef DEV_DIRECT_CMMD_H
#define DEV_DIRECT_CMMD_H
#include "sc_fm.h"

class DevCMMD : public FabricManager {
public:
    explicit DevCMMD(json_t* config);
    virtual ~DevCMMD();
    size_t setup_info(std::string &buffer) override;
};

#endif
