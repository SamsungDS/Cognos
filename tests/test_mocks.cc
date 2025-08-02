#include <cstdint>
#include <string>

// mock struct declarations
struct cmmh_stat_sensor_t {
  uint64_t fpga_temp;
};

struct cmmh_stat_cache_t {
  double hit_perc;
  uint64_t dirty_cache_gb;
};

struct cmmh_stat_interface_t {
  uint64_t nvme_read_count;
  uint64_t nvme_write_count;
  uint64_t cxl_read_count;
  uint64_t cxl_write_count;
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

enum StatusCpe {
  CMMH_STAT_RC_SUCCESS = 0,
  CMMH_STAT_RC_INVALID_LEN = 1,
  CMMH_STAT_RC_ADDR_NOT_MAPPED = 2,
  CMMH_STAT_RC_ADDR_NOT_VALID = 3,
  CMMH_STAT_RC_PENDING_QUEUE_FULL = 4,
  CMMH_STAT_RC_EXT_THREAD_COUNT = 5,
  CMMH_STAT_RC_INVALID_ID = 6,
  CMMH_STAT_RC_ERROR = 7
};

struct cmmh_spec_t {
  StatusCpe status;
  uint64_t total_capacity;
  uint64_t volatile_capcity;
  uint64_t persist_capacity;
  CxlVersion cxl_version;
  CxlType cxl_type;
  uint64_t uuid;
  uint64_t hdm_base;
  uint64_t hdm_range;
  bool cpe_supported;
};

extern "C" __attribute__((weak)) cmmh_stat_sensor_t cmmh_stat_sensor() {
  return {.fpga_temp = 55};
}

extern "C" __attribute__((weak)) cmmh_stat_cache_t cmmh_stat_cache() {
  return {.hit_perc = 88.8, .dirty_cache_gb = 12};
}

extern "C" __attribute__((weak)) cmmh_stat_interface_t cmmh_stat_interface() {
  return {.nvme_read_count = 100,
          .nvme_write_count = 200,
          .cxl_read_count = 4096,
          .cxl_write_count = 2048};
}

extern "C" __attribute__((weak)) int cmmh_init() { return 0; }

extern "C" __attribute__((weak)) void cmmh_close() {}

extern "C" uint64_t get_physical_cxl_address_from_lspci(
    const std::string& location) {
  if (location == "0000:5e:00.0") return 0xABCDEF00;
  if (location == "0000:5e:00.1") return 0xABCDEF10;
  return 0;
}

extern "C" __attribute__((weak)) int cmmh_get_device_count() { return 0; }

extern "C" __attribute__((weak)) cmmh_spec_t cmmh_get_spec(int i) {
  cmmh_spec_t s{};
  s.status = CMMH_STAT_RC_SUCCESS;
  s.hdm_base = 0;
  return s;
}
