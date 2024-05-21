#ifndef _SVK_DBC_API_H_
#define _SVK_DBC_API_H_

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Status codes for DB connector
typedef enum svk_dbc_status {
  SVK_DBC_STATUS_SUCCESS = 0,
  SVK_DBC_STATUS_ERROR = -1,
  SVK_DBC_STATUS_ENOMEM = -2,
  SVK_DBC_STATUS_ENODEV = -3,
} svk_dbc_status_t;

// DB connector operations
typedef enum svk_dbc_op_type {
  SVK_DBC_READ = 0,
  SVK_DBC_WRITE,
  SVK_DBC_PUT,
  SVK_DBC_GET,
  SVK_DBC_DEL

} svk_dbc_op_type_t;

/** Opaque Configuration passed to underlying DB connector */
typedef void* svk_dbc_config_t;

/** DB Connector handle to be used for all operations */
typedef void* svk_dbc_handle_t;

// Callback function for submit_io
typedef void (*svk_dbc_complete_fn)(svk_dbc_task_t* task,
                                    svk_dbc_status_t status);

/** Opaque Structure to hold operations that are batched */
typedef struct svk_dbc_task_s {
  svk_dbc_op_type opc;
  void* dbc_task_identifier;
  union {
    struct {
      struct iovec* iov;
      int32_t iov_cnt;
      size_t offset;
      size_t len;
    } io_task_rw;

    struct {
      uint8_t* buffer;
      size_t len;
    } io_task_generic;

  } task_info;

  void* private_data_if_needed;
  svk_dbc_complete_fn cb;

} svk_dbc_task_t;

/**
 * @brief Open device API for DB connector
 *
 * @param config Opaque Configuration passed to underlying DB connector
 * @param handle List of handles to use for operations
 * @return svk_dbc_status_t Return code
 */
svk_dbc_status_t svk_dbc_open(svk_dbc_config_t* config,
                              svk_dbc_handle_t** handle);

/**
 * @brief Close device API for DB connector
 *
 * @param handle DB connector handle to close
 * @return svk_dbc_status_t Return code
 */
svk_dbc_status_t svkc_dbc_close(svk_dbc_handle_t* handle);

/**
 * @brief Submit IO API for DB connector
 *
 * @param handle DB connector to submit IO to
 * @param task Task structure for holding op data.
 *  If callback (svk_dbc_task_t->cb) is empty, treat as sync IO
 * @return svk_dbc_status_t Return code
 */
svk_dbc_status_t svkc_dbc_submit_io(svk_dbc_handle_t* handle,
                                    svk_dbc_task_t* task);

#ifdef __cplusplus
}  // extern "C"
#endif

#endif