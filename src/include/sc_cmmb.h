#ifndef DEV_CMMB_H
#define DEV_CMMB_H
#include "sc_fm.h"

class DevCMMB : public FabricManager {
public:
    explicit DevCMMB(json_t* config);
    virtual ~DevCMMB();
    size_t setup_info(std::string &buffer) override;
};

#endif
