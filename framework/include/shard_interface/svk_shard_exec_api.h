#ifndef _SVK_SHARDED_EXEC_API_H_
#define _SVK_SHARDED_EXEC_API_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Shard status return codes */
typedef enum svk_shard_status {
  SVK_SHARD_EXEC_STATUS_SUCCESS = 0,
  SVK_SHARD_EXEC_STATUS_ERROR = -1,
  SVK_SHARD_EXEC_STATUS_ENOMEM = -2,
  SVK_SHARD_EXEC_STATUS_ENODEV = -3,
} svk_shard_status_t;

/** Callback function for shard_exec_fn */
typedef svk_shard_status_t (*svk_shard_exec_fn)(void* cmd_req, void* cmd_resp);

/** Shard execute postprocess struct, fn should be set for async IO*/
typedef struct svk_shard_exec_fn_s {
  uint32_t parent_op_code;
  uint32_t sub_op_code;
  svk_shard_exec_fn fn;

} svk_shard_exec_fn_t;

/** Any QOS settings that app wants to pass */
typedef struct svk_shard_qos_s {
  uint64_t max_iops_needed;
  uint64_t max_bw_inmb_needed;
  uint64_t max_lat_in_ns;
} svk_shard_qos_t;

/** List of shards, feature modules will implement shard_units */
typedef struct svk_shard_unit_details_s {
  void* shard_units;  // This will be maped to svkc_shard_t* for svkc
  uint16_t num_shard_unit;
  svk_shard_qos_t* qos_needed;

} svk_shard_unit_details_t;

/** Opaque Configuration passed to underlying DB connector */
typedef struct svk_shard_exec_config_s {
  uint64_t shard_exec_ctx_id;
  svk_shard_unit_details_t* shard_details;
  svk_shard_exec_fn_t* svk_shard_exec_fn_map;
  uint16_t total_number_of_shard_fn;

} svk_shard_exec_config_t;

/** Shard handle to be used for all operations */
typedef void* svk_shard_exec_handle_t;

/**
 * @brief Create shard context
 *
 * @param config
 * @param handle
 * @return svk_shard_status_t
 */
svk_shard_status_t svk_shard_context_open(svk_shard_exec_config_t* config,
                                          svk_shard_exec_handle_t** handle);

/**
 * @brief Close shard context
 *
 * @param handle
 * @return svk_shard_status_t
 */
svk_shard_status_t svk_shard_context_close(svk_shard_exec_handle_t* handle);

/**
 * @brief Register a shard fn with an associated handle
 *
 * @param handle
 * @param one_fn
 * @return svk_shard_status_t
 */
svk_shard_status_t svk_shard_context_register_exec_fn(
    svk_shard_exec_handle_t* handle, svk_shard_exec_fn_t* one_fn);

/**
 * @brief Submit async IO with shard handle
 *
 * @param handle
 * @param cmd_req
 * @return svk_shard_status_t
 */
svk_shard_status_t svk_shard_context_submit_io_async(
    svk_shard_exec_handle_t* handle, void* cmd_req);

/**
 * @brief Check for IOs that are completed
 *
 * @param handle List of handles
 * @param cmd_resp
 * @param num_completed Number of IOs completed
 * @return svk_shard_status_t
 */
svk_shard_status_t svk_shard_context_poll_completion(
    svk_shard_exec_handle_t* handle, void* cmd_resp, uint32_t num_completed);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif  // _SVK_SHARDED_EXEC_API_H_
