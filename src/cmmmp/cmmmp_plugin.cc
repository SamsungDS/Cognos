#include "sc_cmmmp.h"

/**
 * @brief Entry point for plugin registration.
 * Called by PluginManager using dlsym().
 */
extern "C" void register_plugin(DeviceManager& mgr) {
  register_cmmmp_adapter(mgr);
}
