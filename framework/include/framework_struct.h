/** @file framework_struct.h
 * @brief Supporting structs for SVK framework
 *
 * Structs for SVK framework to pass/hold information about the feature modules
 */

#ifndef FRAMEWORK_STRUCT_H
#define FRAMEWORK_STRUCT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
// Enum for feature_id codes
typedef enum { POWER_THROTTLE, ZERO_ETL, RAID, CXL, QLC } feature_id;

// Status enum for svk_output
typedef enum {
  SVK_STATUS_SUCCESS,
  SVK_STATUS_FAIL,
  SVK_STATUS_INVALID_CONFIG,
  SVK_STATUS_BAD_FEATURE_LIB
} svk_status;

/**
 * @struct svk_pass_thru_cmd
 * @brief Passthrough command to the feature execute function
 *
 * Passthrough command struct is used for communication between the
 * top and lower levels
 *
 * @var svk_pass_thru_cmd::cmd_id
 *  Specifies which feature to run command (like PT, zETL, RAID, CXL, QLC)
 *
 * @var svk_pass_thru_cmd::out_format
 *  Output for the feature command (specific for specific cmd)
 *
 * @var svk_pass_thru_cmd::len
 *  Length field if needed
 */
typedef struct {
  feature_id feat_id;
  void *out_format;
  uint32_t len;
} svk_pass_thru_cmd;

/**
 * @struct svk_input
 * @brief Passthrough buffer info for SVK function input
 *
 * @var svk_input::input_buffer
 *  Buffer for the application to use to pass any required info for
 *  feature execution
 *
 * @var svk_input::len
 *  Length of the input_buffer
 *
 */
typedef struct {
  uint8_t *input_buffer;
  uint64_t len;
} svk_input;

/**
 * @struct svk_output
 * @brief Passthrough buffer for SVK function output
 *
 * @var svk_output::status
 *  Status code from feature execution
 *
 * @var svk_output::output_buffer
 *  Buffer for feature module to use to send any output to
 *  application
 *
 * @var svk_output::len
 *  Length of buffer for the output_buffer
 *
 */
typedef struct {
  svk_status status;
  uint8_t *output_buffer;
  uint64_t len;
} svk_output;

/**
 * @struct svk_storage_ctx
 * @brief
 *
 * @var svk_storage_ctx::status
 *
 * @var svk_storage_ctx::db_name
 *
 * @var svk_storage_ctx::db_interface
 *
 * @var svk_storage_ctx::pool_id
 *
 * @var svk_storage_ctx::storage_dev_id
 *
 *
 */
typedef struct {
  int32_t status;
  uint8_t device_type;
  char *device_name;
  void *device_interface_if_any;
  uint64_t parent_id_if_any;
  uint64_t dev_id;
} svk_device_ctx;

/**
 * @struct svk_aio_construct
 * @brief Data for aio postprocess fn
 *
 * Structure containing svk_output data along with operation return value.
 *
 * @var svk_aio_construct::result
 *  Return code (svk_status)
 *
 * @var svk_aio_construct::private_data_1
 *  Private data address passed by caller
 *
 * @var svk_aio_construct::svk_io_identifier
 *  Unique IO identifier
 *
 * @var svk_aio_construct::input
 *  Input buffer for feature to use
 *
 * @var svk_aio_construct::out_data
 *  Output buffer for feature module to populate
 *
 * @var svk_aio_construct::num_out_data
 *  Number of buffers that out_data is pointing to
 *
 */
typedef struct {
  svk_status result;
  void *private_data_1;
  void *svk_io_identifier;
  svk_input *input;
  svk_output *out_data;
  uint32_t num_out_data;
} svk_aio_construct;

/**
 * @struct svk_postprocess_fn
 * @brief Postprocess function for SVK execute_async
 *
 * Contains data and callback for async IO request.
 * NOTE: This data should NOT be freed until the callback (svk_aio_cb) returns.
 *
 * @var svk_postprocess_fn::svk_aio_cb
 *  Callback fn for execute async case. Application should set this and
 *  feature module should call callback to signal to application that
 *  it is done working.
 *
 * @var svk_postprocess_fn::num_op
 *  Number of aio_construct in this context in case of batch IO.
 *
 * @var svk_postprocess_fn::ops
 *  Pointer to aio construct. Should be allocated by application and given to
 *  feature module to populate and return through callback.
 *
 */
typedef struct {
  void (*svk_aio_cb)(svk_aio_construct *ops, int32_t num_op);
  int32_t num_op;
  svk_aio_construct *ops;
} svk_postprocess_fn;

/**
 * @struct svk_feature_details
 * @brief Struct of downstream APIs to pass to feature modules during init
 *
 * Struct for each feature module to keep track of function pointers. Passed to
 * feature modules during init to populate
 *
 * @var svk_feature_details::initialize
 *  @param init_param    Feature module defined pointer to pass through
 *
 * @var svk_feature_details::get_supported_feature_list
 *  Pointer to function that will give back a list of feature names that the
 * feature module will support
 *  @param feature        feature_id which should be populated by feature module
 *  @param feature_names  List of subfeatures
 *
 * @var svk_feature_details::is_license_valid
 *  Pointer to function that will check for valid license
 *
 * @var svk_feature_details::configure_device_if_any
 *  Function that feature modules that require device initialization can use
 *  Note: this is an optional function, not every feature module will need to
 * implement this
 *
 * @var svk_feature_details::execute_sync
 *  Pointer to the execute function that each feature module should define
 *  so the framework can use it generically
 *  @param pass_thru    Feature command details to pass through the function
 * for execution
 *  @param input        Input info structure
 *  @param output       Output info structure
 *
 * @var svk_feature_details::execute_async
 *  Function pointer for async request, which will pass structs like callback fn
 * to feature module
 *  @param pass_thru      Feature command details to pass through the function
 * for execution
 *  @param postprocess_fn Contains callback and various data for async request
 *
 * @var svk_feature_details::clean_up
 *  Pointer to the cleanup function for this feature module that framework will
 *  call on shutdown
 * @param void            Pointer to give to feature module cleanup
 */
typedef struct {
  svk_status (*initialize)(void *init_param);
  svk_status (*get_supported_feature_list)(feature_id *feature,
                                           char *feature_names);
  svk_status (*is_license_valid)(void *);
  svk_status (*configure_device_if_any)(svk_device_ctx *device_handles,
                                        uint64_t length);
  svk_status (*execute_sync)(svk_pass_thru_cmd *pass_thru, svk_input *input,
                             svk_output *output);
  svk_status (*execute_async)(svk_pass_thru_cmd *pass_thru,
                              svk_postprocess_fn *postprocess_fn);
  svk_status (*clean_up)(void *);
} svk_feature_details;

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // FRAMEWORK_STRUCT_H
