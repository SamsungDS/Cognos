/** @file framework_struct.h
 * @brief Supporting structs for SVK framework
 *
 * Structs for SVK framework to pass/hold information about the feature modules
 */

#ifndef FRAMEWORK_STRUCT_H
#define FRAMEWORK_STRUCT_H

#include <cstdint>

// Enum for feature_id codes
typedef enum : uint32_t { POWER_THROTTLE, ZERO_ETL, RAID, CXL, QLC } feature_id;

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
struct svk_pass_thru_cmd {
  feature_id feat_id;
  void *out_format;
  uint32_t len;
};

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
struct svk_input {
  uint8_t *input_buffer;
  uint64_t len;
};

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
struct svk_output {
  svk_status status;
  uint8_t *output_buffer;
  uint64_t len;
};

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
struct svk_storage_ctx {
  svk_status status;
  char *db_name;
  void *db_interface;
  uint64_t pool_id;
  uint64_t storage_dev_id;
};

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
 * @var svk_aio_construct::out_data
 *  Function output (svk_output)
 *
 * @var svk_aio_construct::num_out_data
 *
 *
 */
struct svk_aio_construct {
  svk_status result;
  void *private_data_1;
  void *svk_io_identifier;
  svk_output *out_data;
  uint32_t num_out_data;
};

/**
 * @struct svk_postprocess_fn
 * @brief Postprocess function for SVK execute_async
 *
 * Contains data and callback for async IO request.
 * NOTE: This data should NOT be freed until the callback (svk_aio_cb) returns.
 *
 * @var svk_postprocess_fn::svk_aio_cb
 *  Callback fn for execute async case
 *
 * @var svk_postprocess_fn::private_data_1
 *  Private data address passed by caller
 *
 * @var svk_postprocess_fn::svk_io_identifier
 *  Unique IO identifier
 *
 * @var svk_postprocess_fn::input
 *  Input buffer from application to feature module
 *
 * @var svk_postprocess_fn::out_data
 *  Output buffer for feature module to populate
 *
 * @var svk_postprocess_fn::num_out_data
 *  Number of output data that is being returned
 *
 */
struct svk_postprocess_fn {
  void (*svk_aio_cb)(svk_aio_construct *ops, int32_t num_op);
  void *private_data_1;
  void *svk_io_identifier;
  svk_input *input;
  svk_output *out_data;
  uint32_t num_out_data;
};

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
struct svk_feature_details {
  int (*initialize)(void *init_param);
  int (*get_supported_feature_list)(feature_id *feature, char *feature_names);
  int (*is_license_valid)(void *);
  int (*execute_sync)(svk_pass_thru_cmd *pass_thru, svk_input *input,
                      svk_output *output);
  int (*execute_async)(svk_pass_thru_cmd *pass_thru,
                       svk_postprocess_fn *postprocess_fn);
  int (*clean_up)(void *);
};

#endif  // FRAMEWORK_STRUCT_H
