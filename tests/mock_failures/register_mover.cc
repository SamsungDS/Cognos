#include <string>
#include "cme_mover.h"
#include "cme_logger.h"

extern "C" cme_mover* register_cme_fn() {

                cout << "mock failure for register_cme_fn" << endl;
                return nullptr;
}