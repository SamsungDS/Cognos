#include <cstdint>

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
