#pragma once
#include <cstdint>
extern "C" {
struct cmmh_stat_interface_t {
  uint64_t nvme_read_count;
  uint64_t nvme_write_count;
  uint64_t cxl_read_count;
  uint64_t cxl_write_count;
};
struct cmmh_stat_cache_t {
  double hit_perc;          // device cache hit percentage
  uint64_t dirty_cache_gb;  // dirty pages in the device
};

enum StatusCpe {
  CMMH_STAT_RC_SUCCESS = 0, /* command accepted, check progress if enabled */
  CMMH_STAT_RC_INVALID_LEN =
      1, /* invalid length - should be in 4096 increments */
  CMMH_STAT_RC_ADDR_NOT_MAPPED = 2, /* physical address not mapped */
  CMMH_STAT_RC_ADDR_NOT_VALID = 3, /* physical address not within CMM-H range */
  CMMH_STAT_RC_PENDING_QUEUE_FULL =
      4, /* pending queue is full. Application should retry */
  CMMH_STAT_RC_EXT_THREAD_COUNT = 5, /* thread count exceeded maximum */
  CMMH_STAT_RC_INVALID_ID = 6,       /* device ID is invalid */
  CMMH_STAT_RC_ERROR = 7             /* command error */
};

struct cmmh_stat_sensor_t {
  StatusCpe status;
  uint64_t fpga_temp;  // the device temperature
};

enum class CxlVersion {
  CXL1_1 = 0, /* CXL 1.1 */
  CXL2_0 = 1,
  NO_CXL = 2
};

/* CXL Device Type */
enum class CxlType {
  NO_CXL = 0,
  TYPE1 = 1,
  TYPE2 = 2,
  TYPE3 = 3 /* Memory Expander */
};

struct cmmh_spec_t {
  StatusCpe status; /* Other fields valid if status == CMMH_STAT_RC_SUCCESS */
  uint64_t total_capacity; /* total advertised device capacity (multiple of 256
                              MB) */
  uint64_t volatile_capcity; /* device volatile capacity (multiple of 256 MB) */
  uint64_t
      persist_capacity;   /* device persistent capacity (multiple of 256 MB) */
  CxlVersion cxl_version; /* CXL version */
  CxlType cxl_type;       /* CXL type */
  uint64_t uuid;          /* device unique ID */
  uint64_t hdm_base;      /* HDM Base address */
  uint64_t hdm_range;     /* HDM Range */
  bool cpe_supported;     /* CPE APIs (prefetch/evict) supported */
};

// Mocked function declarations (weak symbols)
cmmh_stat_interface_t cmmh_stat_interface(int device_id = 0);
cmmh_stat_cache_t cmmh_stat_cache(int device_id = 0);
cmmh_stat_sensor_t cmmh_stat_sensor(int device_id = 0);
void cmmh_close();
int cmmh_init();
int cmmh_get_device_count();
cmmh_spec_t cmmh_get_spec(int device_id = 0);
}
