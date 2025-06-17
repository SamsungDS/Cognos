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
struct cmmh_stat_sensor_t {
  uint64_t fpga_temp;  // the device temperature
};

// Mocked function declarations (weak symbols)
cmmh_stat_interface_t cmmh_stat_interface();
cmmh_stat_cache_t cmmh_stat_cache();
cmmh_stat_sensor_t cmmh_stat_sensor();
void cmmh_close();
}
