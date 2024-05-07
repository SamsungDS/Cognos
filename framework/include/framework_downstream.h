/** @file framework_downstream.h
 * @brief Downstream APIs for feature module
 *
 * Downstream APIs that should be implemented by the feature module
 *
 */

#ifndef FRAMEWORK_DOWNSTREAM_H
#define FRAMEWORK_DOWNSTREAM_H
#include "framework_struct.h"

#ifdef __cplusplus
extern "C" {
#endif
/**
 * @brief Initialize individual feature module
 *
 * This will be called when individual feature module will be loaded by
 * framework. All data structure initialization needed for the feature module
 * along with reading and caching licensing terms should be done here.
 *
 * @param init_param
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status initialize(void *init_param);

/**
 * @brief Show features the feature module will support
 *
 * Feature modules should set their feature_id to the *feat_id pointer if
 * it isn't set already.
 * SVK command framework will also call this function to get the feature names
 * this feature module will support.
 *
 * @param feat_id Feature id code
 * @param feature_names
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status get_supported_feature_list(feature_id *feat_id, char *feature_names);

/**
 * @brief API for feature modules that need to access/initialize a device
 * NOTE: This is an optional API, not all feature modules need to implement this
 *
 * @param device_handles List of device contexts
 * @param length Num of device contexts
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status configure_device_if_any(svk_device_ctx *device_handles,
                                   uint64_t length);

/**
 * @brief Check if license is valid
 *
 * Every request needs to validate if license is valid before moving on
 *
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status is_license_valid(void *);

/**
 * @brief Exact feature execution logic will be implemented here
 *
 * @param pass_thru svk passthrough for command info communication from top
 * level
 * @param input     input buffer struct
 * @param result    output buffer struct
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status execute_sync(svk_pass_thru_cmd *pass_thru, svk_input *input,
                        svk_output *output);

/**
 * @brief Feature module async execute implementation.
 *
 * @param pass_thru       svk passthrough for command info communication from
 * top level
 * @param input           input buffer struct
 * @param postprocess_fn  struct containing pointers for async IO, such as
 * callback, IO identifier, and output buffer
 * @return svk_status     Refer to framework_struct.h for return codes
 */
svk_status execute_async(svk_pass_thru_cmd *pass_thru,
                         svk_postprocess_fn *postprocess_fn);

/**
 * @brief Usual cleanup before exit
 *
 * @param ctx the storage context to use
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status clean_up(void *);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // FRAMEWORK_DOWNSTREAM_H
