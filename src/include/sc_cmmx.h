#ifndef _CMMX_H
#define _CMMX_H
#include "sc_fm.h"

class CMMX : public FabricManager {
public:
    explicit CMMX(json_t* config);
    virtual ~CMMX();
    size_t setup_info(std::string &buffer) override;
};

#endif
