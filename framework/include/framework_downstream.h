/** @file framework_downstream.h
 * @brief Downstream APIs for feature module
 *
 * Downstream APIs that should be implemented by the feature module
 *
 */

#ifndef FRAMEWORK_DOWNSTREAM_H
#define FRAMEWORK_DOWNSTREAM_H
#include "framework_struct.h"

extern "C"
{
  /**
   * @brief Initialize individual feature module
   *
   * This will be called when individual feature module will be loaded by
   * framework. All data structure initialization needed for the feature module
   * along with reading and caching licensing terms should be done here.
   *
   * @param init_param
   * @return int
   */
  int initialize (void *init_param);

  /**
   * @brief Show features the feature module will support
   *
   * SVK command framework will call this function to get the feature names
   * this feature module will support
   *
   * @param feat_id Feature id code
   * @param feature_names
   * @return int
   */
  int get_supported_feature_list (feature_id *feat_id, char *feature_names);

  /**
   * @brief Check if license is valid
   *
   * Every request needs to validate if license is valid before moving on
   *
   * @return int
   */
  int is_license_valid (void *);

  /**
   * @brief Exact feature execution logic will be implemented here
   *
   * @param cmd       svk passthrough for command info communication from top
   * level
   * @param input     input buffer struct
   * @param result    output buffer struct
   * @return int
   */
  int execute (svk_pass_thru_cmd *cmd, svk_input *input, svk_output *result);

  /**
   * @brief Usual cleanup before exit
   *
   * @param ctx the storage context to use
   * @return int
   */
  int clean_up (svk_storage_ctx *ctx, void *);

} // extern "C"

#endif // FRAMEWORK_DOWNSTREAM_H
