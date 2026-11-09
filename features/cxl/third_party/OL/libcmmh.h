/*
 *	The confidential and proprietary information contained in this file may
 *     	only be used by a person authorised under and to the extent permitted
 *     	by a subsisting licensing agreement from Samsung Electronics.
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
 *
 *	CMM-H API Library
 *
 *	The library provides access to the CMM-H advanced features including:
 *	  - Prefetch : Move memory span on CMM-H into device cache.
 *	  - Evict    : Remove memory span on the CMM-H from the device cache.
 *
 *	Operation completion has a couple of options:
 *	  - Set and Forget
 *	  - Use cmmh_checkprogress() to monitor for progress_perc == 100.
 *
 *
 *	The library also provides access to CMM-H information and statistics
 *	including:
 *	  - CXL capacity, version and type
 *	  - CXL/NVMe interface counts
 *	  - Cache hit rate
 *
 */
#ifndef LIBCMMH_H
#define LIBCMMH_H

#include <string>
#include <cstdint>     

/* CMM-H API return values */
enum StatusCpe {
	CMMH_STAT_RC_SUCCESS=0,			/* command accepted, check progress if enabled */
	CMMH_STAT_RC_INVALID_LEN=1, 		/* invalid length - should be in 4096 increments */
	CMMH_STAT_RC_ADDR_NOT_MAPPED=2, 	/* physical address not mapped */
	CMMH_STAT_RC_ADDR_NOT_VALID=3, 		/* physical address not within CMM-H range */
	CMMH_STAT_RC_PENDING_QUEUE_FULL=4,	/* pending queue is full. Application should retry */
	CMMH_STAT_RC_EXT_THREAD_COUNT=5, 	/* thread count exceeded maximum */
	CMMH_STAT_RC_INVALID_ID=6,		/* device ID is invalid */
	CMMH_STAT_RC_ERROR=7			/* command error */
}; 

/* CMM-H Check Progress API return values */
enum StatusProgress {
	CMMH_PROG_RC_COMPLETE=0,	/* command completed successfully */
	CMMH_PROG_RC_PENDING=1, 	/* command in the pending queue waiting to be submitted */
	CMMH_PROG_RC_INPROGRESS=2, 	/* command is submitted, waiting for completion */
	CMMH_PROG_RC_EXPIRED=3		/* command completed and was removed from pending table */
}; 

/* CXL Version */
enum class CxlVersion {
	CXL1_1=0,	/* CXL 1.1 */
	CXL2_0=1,
	NO_CXL=2
}; 

/* CXL Device Type */
enum class CxlType { 
	NO_CXL=0,
	TYPE1=1,
	TYPE2=2,
	TYPE3=3		/* Memory Expander */
}; 

struct cmmh_cpe_t {
	StatusCpe status;	/* API return value */
	uint16_t commandID;	/* unique command ID */
}; 

struct cmmh_cpe_prog_t {
	StatusProgress progress_status; /* Check Progress API return value */
	uint8_t progress_perc;		/* command progress. 0-100 % */
}; 

/* Command completion options */
struct cmmh_cpe_config_t {
	int enable_checkprogress;	/* 1 for monitoring with cmmh_checkprogress calls */
};

/* CMM-H CXL details and capacity */
struct cmmh_spec_t {
	StatusCpe status;		/* Other fields valid if status == CMMH_STAT_RC_SUCCESS */
	uint64_t total_capacity; 	/* total advertised device capacity (multiple of 256 MB) */
	uint64_t volatile_capcity;	/* device volatile capacity (multiple of 256 MB) */
	uint64_t persist_capacity; 	/* device persistent capacity (multiple of 256 MB) */
	CxlVersion cxl_version;  	/* CXL version */
	CxlType cxl_type;		/* CXL type */
	uint64_t uuid;			/* device unique ID */
	uint64_t hdm_base;		/* HDM Base address */
	uint64_t hdm_range;		/* HDM Range */
	bool cpe_supported;		/* CPE APIs (prefetch/evict) supported */
};

/* CMM-H internal debug counters */
struct cmmh_stat_interface_t {
	StatusCpe status;		/* Other fields valid if status == CMMH_STAT_RC_SUCCESS */
	uint64_t nvme_read_count; 	/* internal NVMe Read count */
	uint64_t nvme_write_count; 	/* internal NVMe Write count */
	uint64_t cxl_read_count;	/* CXL Load request count */
	uint64_t cxl_write_count; 	/* CXL Store request count */
};

/* CMM-H cache information */
struct cmmh_stat_cache_t {
	StatusCpe status;		/* Other fields valid if status == CMMH_STAT_RC_SUCCESS */
	double hit_perc; 		/* device cache hit percentage */
	uint64_t dirty_cache_gb; 	/* dirty page in the device cache (GB) */
};

/* CMM-H sensor information */
struct cmmh_stat_sensor_t {
	StatusCpe status;		/* Other fields valid if status == CMMH_STAT_RC_SUCCESS */
	uint64_t fpga_temp;		/* FPGA temperature (C) */
};


/* CMM-H API functions */

/// @brief cmmh init - starts the library
/// @return command status- 0 for success
/// @return command status- 1 for library is initialized before
int cmmh_init (void);

/// @brief cmmh close - close the library and do cleanup
void cmmh_close (void);

/// @brief cmmh_get_device_count 
/// @return the number of discovered CMM-H devices in the system
int cmmh_get_device_count ();

/// @brief cmmh evict - evict (virt_addr - virt_addr+length) from device cache
/// @param virtual address
/// @param length in bytes. Should be multiple of 4K 
/// @return command status
cmmh_cpe_t cmmh_evict (void* virt_addr, size_t length, cmmh_cpe_config_t config);

/// @brief cmmh prefetch - prefetch (virt_addr - virt_addr+length) to device cache
/// @param virtual address
/// @param length in bytes. Should be multiple of 4K 
/// @return command status
cmmh_cpe_t cmmh_prefetch (void* virt_addr, size_t length, cmmh_cpe_config_t config);

/// @brief cmmh flush - flush (virt_addr - virt_addr+length) from device cache (if dirty)
/// @param virtual address
/// @param length in bytes. Should be multiple of 4K 
/// @return command status
cmmh_cpe_t cmmh_flush(void* virt_addr, size_t length, cmmh_cpe_config_t config);

/// @brief cmmh checkprogress - check progress of prefetch/evict
/// @param commandID
/// @return program progress status
cmmh_cpe_prog_t cmmh_checkprogress (uint16_t commandID); 

/// @brief cmmh_get_spec 
/// @param device_id - default:0
/// @return the device information including capacity, cxl type and version
cmmh_spec_t cmmh_get_spec (int device_id=0);

/// @brief cmmh_stat_interface 
/// @param device_id - default:0
/// @return the device interface information
cmmh_stat_interface_t cmmh_stat_interface (int device_id=0); 

/// @brief cmmh_stat_cache_info 
/// @param device_id - default:0
/// @return the device cache related information
cmmh_stat_cache_t cmmh_stat_cache (int device_id=0);

/// @brief cmmh_stat_sensor 
/// @param device_id - default:0
/// @return the device sensor stats including temperature 
cmmh_stat_sensor_t cmmh_stat_sensor (int device_id=0);

/// @brief cmmh_stat_reset 
//  reset the cache related HW counters 
/// @param device_id - default:0
void cmmh_stat_reset (int device_id=0); 

#endif /* LIBCMMH_H */
