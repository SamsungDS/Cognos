#ifndef _RAS_EXPORTS__H_
#define _RAS_EXPORTS__H_

// Expects the logic modules to provide the feature_name as "ras" as part of
// get_supported_logic_details If not provided, then we ignore the logic module
#define RAS_FEATURE_MODULE_NAME "ras"
#define RAS_LOGGER RAS_FEATURE_MODULE_NAME

#endif  // _RAS_EXPORTS__H_
