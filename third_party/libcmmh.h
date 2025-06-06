/*
 * 		The confidential and proprietary information contained in this
 * file may only be used by a person authorised under and to the extent
 * permitted by a subsisting licensing agreement from Samsung Electronics.
 *
 *       (C) COPYRIGHT 2024-2025 Samsung Electronics
 *       ALL RIGHTS RESERVED
 *
 *     	Samsung Secret
 *
 *     	This entire notice must be reproduced on all copies of this file
 *     	and copies of this file may only be made by a person if such person is
 *     	permitted to do so under the terms of a subsisting license agreement
 *     	from Samsung Electronics.
 *
 * 		Filename:        		libcmmh.h
 * 		Created:     			2024-10-05
 * 		Description: 			This a header file for CPE host
 * reference library. Primary Contact:
 *
 */

#ifndef LIBCMMH_H
#define LIBCMMH_H

#include <cstdint>
#include <string>

/*
 *   Defining CMM-H commands return value
 *   @var status: contains the status of the command. CMD_SUCCESS for SUCCESS
 */
enum StatusCpe {
  CMMH_STAT_RC_SUCCESS = 0,
  CMMH_STAT_RC_INVALID_LEN = 1,
  CMMH_STAT_RC_ADDR_NOT_MAPPED = 2,
  CMMH_STAT_RC_ADDR_NOT_VALID = 3,
  CMMH_STAT_RC_PENDING_QUEUE_FULL = 4,
  CMMH_STAT_RC_EXT_THREAD_COUNT = 5,
  CMMH_STAT_RC_ERROR = 6
};

enum StatusProgress {
  CMMH_PROG_RC_COMPLETE = 0,
  CMMH_PROG_RC_PENDING = 1,
  CMMH_PROG_RC_INPROGRESS = 2,
  CMMH_PROG_RC_EXPIRED = 3
};

enum class CxlVersion { CXL1_1 = 0, CXL2_0 = 1, NO_CXL = 2 };

enum class CxlType { NO_CXL = 0, TYPE1 = 1, TYPE2 = 2, TYPE3 = 3 };

struct cmmh_cpe_t {
  StatusCpe status;   /* 0 for success */
  uint16_t commandID; /* command unique ID */
};

struct cmmh_cpe_prog_t {
  StatusProgress progress_status;
  uint8_t progress_perc; /* the command progress. 0-100 */
};

struct cmmh_cpe_config_t {
  int enable_checkprogress; /* 1 for monitoring with cmmh_checkprogress calss */
  int has_callback;         /* 1 if there is a callback function */
  void (*callback_function)(cmmh_cpe_t status); /* function pointer - callback
                                                   upon completion (optional) */
};

struct cmmh_spec_t {
  uint64_t total_capacity; /* total advertised capacity (multiple of 256 MB) */
  uint64_t volatile_capcity; /* total volatile capacity (multiple of 256 MB) */
  uint64_t
      persist_capacity; /* total persistent capacity (multiple of 256 MB) */
  CxlVersion cxl_version;
  CxlType cxl_type;
};

struct cmmh_stat_interface_t {
  uint64_t nvme_read_count;
  uint64_t nvme_write_count;
  uint64_t cxl_read_count;
  uint64_t cxl_write_count;
};

struct cmmh_stat_cache_t {
  double hit_perc;         /* device cache hit percentage */
  uint64_t dirty_cache_gb; /* dirty page in the device cache (GB) */
};

struct cmmh_stat_sensor_t {
  uint64_t fpga_temp; /* the device temperature */
};

/* CMM-H API functions */

/// @brief cmmh init - starts the library
/// @return command status- 0 for success
/// @return command status- 1 for library is initialized before
int cmmh_init(void);

/// @brief cmmh close - close the library and do cleanup
/// @return void
void cmmh_close(void);

/// @brief cmmh evict
/// @param virtual address
/// @param length in bytes. Should be multiple of 4K
/// @return command status
cmmh_cpe_t cmmh_evict(void* virt_addr, size_t length, cmmh_cpe_config_t config);

/// @brief cmmh prefetch
/// @param virtual address
/// @param length in bytes. Should be multiple of 4K
/// @return command status
cmmh_cpe_t cmmh_prefetch(void* virt_addr, size_t length,
                         cmmh_cpe_config_t config);

/// @brief cmmh checkprogress
/// @param commandID
/// @return program progress status
cmmh_cpe_prog_t cmmh_checkprogress(uint16_t commandID);

/// @brief cmmh_get_spec
/// @param None
/// @return the device information
cmmh_spec_t cmmh_get_spec();

/// @brief cmmh_stat_interface
/// @param None
/// @return the device interface information
cmmh_stat_interface_t cmmh_stat_interface();

/// @brief cmmh_stat_cache_info
/// @param None
/// @return the device cache related information
cmmh_stat_cache_t cmmh_stat_cache();

/// @brief cmmh_stat_sensor
/// @param None
/// @return the device sensor stats including temperature
cmmh_stat_sensor_t cmmh_stat_sensor();

/// @brief cmmh_stat_reset
//  reset the cache related HW counters
/// @param None
/// @return void
void cmmh_stat_reset();

#endif /* LIBCPE_H */
