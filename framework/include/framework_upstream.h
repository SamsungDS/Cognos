/** @file framework.h
 * @brief Upstream APIs for application to use for controlling SVK
 *
 * Upstream APIs that are exposed to the GRPC server or application to control
 * SVK library initialization, cleanup, and feature execution
 */

#ifndef FRAMEWORK_H
#define FRAMEWORK_H
#include "framework_struct.h"

extern "C"
{

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
  int initialize_svk (const char *svk_conf_file, void *);

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
  int execute_svk_feature_sync (svk_pass_thru_cmd *pass_thru, svk_input *input,
                                svk_output *output);

  /**
   * @brief Execute feature function asynchronously
   *
   * @param pass_thru         Struct that should be populated by application
   * and passed through this function to the feature module
   * @param input             svk_input populated with necessary info to send
   * to the feature
   * @param postprocess_fn    Post-process function for async
   */
  int execute_svk_feature_async (svk_pass_thru_cmd *pass_thru,
                                 svk_input *input,
                                 svk_postprocess_fn *postprocess_fn);

  /**
   * @brief Execute cleanup of SVK framework and features
   *
   * API for application to call to initiate SVK cleanup
   *
   * @param ctx
   *
   */
  int cleanup_svk (svk_storage_ctx *ctx, void *);

} // extern "C"

#endif // FRAMEWORK_H
