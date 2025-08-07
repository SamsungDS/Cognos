/** @file framework_upstream.h
 * @brief Upstream APIs for application to use for controlling SVK
 *
 * Upstream APIs that are exposed to the GRPC server or application to control
 * SVK library initialization, cleanup, and feature execution
 */

#ifndef FRAMEWORK_UPSTREAM_H
#define FRAMEWORK_UPSTREAM_H
#include "framework_struct.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialize the SVK library and feature modules
 *
 * When the front-end application/server calls this, configure the SVK
 * service and attempt to initialize all the given features by calling their
 * init functions. Also load the execute functions to be called later.
 *
 * @param svk_conf_file Path to configuration file
 *
 */
svk_status initialize_svk(const char *svk_conf_file, void *);

/**
 * @brief Get the features loaded in SVK in a JSON object
 *
 * @return svk_status true if feature list was successfully formed, false if not
 */
svk_status get_registered_features(svk_output *output);

/**
 * @brief API for feature modules that need to access/initialize a device
 * NOTE: This is an optional API, not all feature modules need to implement this
 *
 * @param pass_thru svk passthrough for command info communication from top
 * level
 * @param config_details Config allocated by app to be given to feature to use
 * @param device_handles List of device contexts
 * @param length Num of device contexts
 * @param resp Pointer for volume and cstore uuid
 * @return svk_status Refer to framework_struct.h for return codes
 */
svk_status configure_svk_device_if_any(svk_pass_thru_cmd *pass_thru,
                                       void *config_details,
                                       svk_device_ctx *device_handles,
                                       uint64_t length, void *resp);

/**
 * @brief Function to be called by App for feature execution.
 *
 * Application should call this API to execute a feature function. The
 * application and feature module should implement and populate the structs
 * in the parameters for this function, as defined in framework_struct.h
 *
 * @param pass_thru Struct that should be populated by application and passed
 * through this function to the feature module
 * @param input     svk_input populated with necessary info to send to the
 * feature
 * @param output    svk_output with status and buffers for the feature to
 * populate if needed
 */
svk_status execute_svk_feature_sync(svk_pass_thru_cmd *pass_thru,
                                    svk_input *input, svk_output *output);

/**
 * @brief Execute feature function asynchronously
 *
 * @param pass_thru         Struct that should be populated by application
 * and passed through this function to the feature module
 * @param input             svk_input populated with necessary info to send
 * to the feature
 * @param postprocess_fn    Post-process function for async
 */
svk_status execute_svk_feature_async(svk_pass_thru_cmd *pass_thru,
                                     svk_postprocess_fn *postprocess_fn);

/**
 * @brief Execute cleanup of SVK framework and features
 *
 * API for application to call to initiate SVK cleanup
 *
 * @param ctx
 *
 */
svk_status cleanup_svk(svk_device_ctx *ctx, void *);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // FRAMEWORK_UPSTREAM_H
