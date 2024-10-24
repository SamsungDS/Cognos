#ifndef __SVK_LOGIC_INTERFACE_H__
#define __SVK_LOGIC_INTERFACE_H__

#include "svk_logic.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize individual logic module
 *
 * This will be called by the parent SVK Logic feature library like SLA Tracker,
 * zETL etc. which loads individual logic module. All data structure
 * initialization needed for the logic module along with reading and caching
 * licensing terms should be done here.
 *
 * @param init_param
 * @return svk_status Refer to framework_struct.h for return codes
 */

svk_status initialize_logic_module(void *init_param);

/**
 * @brief Gets the logic ID supported by the logic module
 *
 * SVK command framework will also call this function to get the logic module
 * name and list of functions supported by the logic module. Logic module should
 * populate the function pointers depending on the implementation.
 *
 * @param logic_details Function pointers and the logic module name to be
 * populated
 * @return svk_status Refer to framework_struct.h for return codes
 */

svk_status get_supported_logic_details(svk_logic_module_details *logic_details);

/**
 * @brief Exact Logic module's execution logic will be implemented here
 *
 * @param pass_thru svk passthrough for command info communication from top
 * level
 * @param input     input buffer struct
 * @param result    output buffer struct
 * @return svk_status Refer to framework_struct.h for return codes
 */

svk_status execute_logic_sync(svk_logic_cmd *pass_thru, svk_logic_input *input,
                              svk_logic_output *output);

/**
 * @brief Logic module async execute implementation.
 *
 * @param pass_thru       svk passthrough for command info communication from
 * top level
 * @param input           input buffer struct
 * @param postprocess_fn  struct containing pointers for async IO, such as
 * callback, IO identifier, and output buffer
 * @return svk_status     Refer to framework_struct.h for return codes
 */

svk_status execute_logic_async(svk_logic_cmd *pass_thru,
                               svk_postprocess_fn *postprocess_fn);

/**
 * @brief Usual cleanup before exit
 *
 * @param param Parameter required for the logic module to perform cleanup
 * @return svk_status Refer to framework_struct.h for return codes
 */

svk_status cleanup_logic_module(void *param);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif /*__SVK_LOGIC_INTERFACE_H__*/
